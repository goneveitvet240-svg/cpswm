"""Descriptive held-out diagnostics, without selecting or tuning any policy."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from score_executed_search import ARMS, paired_interval, read, score_run, verify


def summarize(base, root):
    totals = {a: Counter() for a in ARMS}
    groups = defaultdict(Counter)
    mechanisms = Counter()
    paired = Counter()
    probability = Counter()
    examples = []
    carry_effect = Counter()
    carry_by_transition = defaultdict(Counter)
    conditions = {}
    carry_seed_differences = {}
    for condition in ("complete32", "sparse32", "long64"):
        folder = base / f"test-{condition}"
        summary = verify(folder, root)
        conditions[condition] = summary
        steps = summary["counts"]["current_rank"]["n"] / len(summary["per_episode"])
        carry_seed_differences[condition] = paired_interval(
            [
                (
                    r["metrics"]["current_no_carry"]["executed_checks"]
                    - r["metrics"]["current_rank"]["executed_checks"]
                )
                / steps
                for r in summary["per_episode"]
            ]
        )
        paired.update(summary["paired"])
        for arm, counts in summary["counts"].items():
            totals[arm].update(counts)
        for i in range(read(folder / "completion.json")["episode_count"]):
            v, t = read(folder / f"visible-{i}.json"), read(folder / f"truth-{i}.json")
            runs = {a: read(folder / f"run-{i}-{a}.json") for a in ARMS}
            scores = {a: score_run(r, v, t)[1] for a, r in runs.items()}
            mechanisms.update(runs["joint_habit"]["ledger_operations"])
            previous_target = None
            for step_index, (j, f, c) in enumerate(
                zip(
                    runs["joint_habit"]["actions"],
                    runs["factor_habit"]["actions"],
                    runs["current_rank"]["actions"],
                    strict=True,
                )
            ):
                js, cs = scores["joint_habit"][step_index], scores["current_rank"][step_index]
                truth = t["truth_by_step"][j["step_id"]]
                no_carry = scores["current_no_carry"][step_index]
                delta = no_carry["executed_checks"] - cs["executed_checks"]
                carry_effect.update(
                    fewer_checks_steps=int(delta > 0),
                    more_checks_steps=int(delta < 0),
                    checks_saved=delta,
                )
                target = truth["true_location"]
                transition = (
                    "no_previous"
                    if previous_target is None
                    else "persisted_location"
                    if target == previous_target
                    else "changed_location"
                )
                carry_by_transition[transition].update(
                    steps=1, checks_saved=delta, helped=int(delta > 0), hurt=int(delta < 0)
                )
                previous_target = target
                target_not_habit = truth["true_location"] != truth["true_owner_habit_location"]
                group = f"current_{'differs_from' if target_not_habit else 'equals'}_habit"
                extra = js["executed_checks"] - cs["executed_checks"]
                for key in (
                    group,
                    "actor_" + truth["true_actor"],
                    "mechanism_" + truth["true_mechanism"],
                ):
                    groups[key].update(
                        steps=1,
                        missing=js["missing_steps"],
                        joint_more_steps=int(extra > 0),
                        joint_fewer_steps=int(extra < 0),
                        net_extra_inspections=extra,
                    )
                jh, fh = (r["active_search"]["habit_proposal"] for r in (j, f))
                hdiff = max(abs(jh[k] - fh[k]) for k in jh)
                udiff = abs(j["unknown_probability"] - f["unknown_probability"])
                probability["habit_different_steps_above_1e-12"] += hdiff > 1e-12
                probability["unknown_different_steps_above_1e-12"] += udiff > 1e-12
                probability["max_habit_probability_difference"] = max(
                    probability["max_habit_probability_difference"], hdiff
                )
                probability["max_unknown_probability_difference"] = max(
                    probability["max_unknown_probability_difference"], udiff
                )
                probability["put_disagreement_steps"] += j["put_back"] != f["put_back"]
                if extra != 0 and len(examples) < 12:
                    examples.append(
                        {
                            "condition": condition,
                            "episode_index": i,
                            "step_index": step_index,
                            "step_id": j["step_id"],
                            "target": truth["true_location"],
                            "habit_target": truth["true_owner_habit_location"],
                            "joint_query_order": j["active_search"]["query_order"],
                            "current_query_order": c["active_search"]["query_order"],
                            "joint_total": js["executed_checks"],
                            "current_total": cs["executed_checks"],
                        }
                    )
    return {
        "all_counts": totals,
        "terminal_memory_effect_current_vs_no_carry": carry_effect,
        "carry_by_location_transition_posthoc": dict(carry_by_transition),
        "carry_checks_saved_per_step_positive_is_better": carry_seed_differences,
        "paired": paired,
        "joint_factor_probability_differences": probability,
        "joint_ledger_operations": mechanisms,
        "posthoc_groups_not_selection": dict(groups),
        "examples": examples,
        "conditions": conditions,
        "scope": "Descriptive D0 oracle diagnostics; no confirmatory gate or policy selection",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    value = summarize(args.folder, Path(__file__).resolve().parents[1])
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in value.items() if k != "conditions"}))
