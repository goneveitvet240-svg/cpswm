"""Independently recompute saved D0 actions, phase errors and paired differences.

Standard library only: does not call the inference runtime or its metric helpers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

METHODS = (
    "stateful_full_joint",
    "matched_full_state_factorized",
    "matched_amg",
    "shared_spine_latest",
)


def read(path):
    return json.loads(path.read_text())


def paired_interval(values):
    rng = random.Random(0)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(10000))
    return {
        "mean": mean(values),
        "descriptive_seed_bootstrap_95": [samples[249], samples[9749]],
        "per_episode": values,
    }


def verify(folder, root):
    completed = read(folder / "completion.json")
    assert completed["source_unchanged"]
    checks = 1
    for name, digest in read(folder / "source.json")["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
        checks += 1
    report = {}
    for condition, summary in read(folder / "summary.json").items():
        aggregates = {m: Counter() for m in METHODS}
        phases = {m: defaultdict(Counter) for m in METHODS}
        coverage = {m: Counter() for m in METHODS}
        per_episode = {m: [] for m in METHODS}
        settings = summary["settings"]
        selection = read(folder / condition / "selection.json")
        for method, chosen in selection["selected"].items():
            trials = selection["trials"][method]
            assert len(trials) == 3
            expected = min(
                trials, key=lambda r: (r["cumulative_action_regret_per_step"], r["parameter"])
            )["parameter"]
            assert expected == chosen == summary["selection"][method]
            for trial in trials:
                dev = read(folder / condition / f"dev-{method}-{trial['parameter']}.json")
                assert len(dev) == 3
                regret = sum(r["metric"]["cumulative_action_regret"] for r in dev)
                count = sum(r["metric"]["step_count"] for r in dev)
                assert math.isclose(regret / count, trial["cumulative_action_regret_per_step"])
                checks += 2
            checks += 2
        for index in range(len(completed["test_seeds"])):
            visible = read(folder / condition / f"visible-{index}.json")
            truth = read(folder / condition / f"evaluator-truth-{index}.json")["truth_by_step"]
            support = set(visible["known_location_ids"])
            if not support:
                support = {
                    step[key]
                    for step in visible["steps"]
                    for key in (
                        "source_location_id",
                        "attempted_location_id",
                        "observed_destination_location_id",
                    )
                    if step[key] is not None
                }
            results = {m: read(folder / condition / f"test-{index}-{m}.json") for m in METHODS}
            assert len({r["visible_input_sha256"] for r in results.values()}) == 1
            assert len({r["metric"]["visible_input_hash"] for r in results.values()}) == 1
            checks += 2
            for method, result in results.items():
                n = len(result["actions"])
                assert n == len(visible["steps"]) == result["metric"]["step_count"]
                checks += 1
                counts = Counter()
                start = datetime.fromisoformat(visible["steps"][0]["timestamp"]).date()
                for row, step in zip(result["actions"], visible["steps"], strict=True):
                    assert row["step_id"] == step["step_id"]
                    target = truth[row["step_id"]]
                    day = (datetime.fromisoformat(step["timestamp"]).date() - start).days
                    phase = (
                        "recurrence"
                        if day >= settings["recurrence_day"]
                        else "new_habit"
                        if day >= settings["abrupt_day"]
                        else "post_guest"
                        if day > settings["guest_window"][1]
                        else "guest"
                        if day >= settings["guest_window"][0]
                        else "initial"
                    )
                    put = row["put_back"] != target["true_owner_habit_location"]
                    search = row["search_order"][0] != target["true_location"]
                    conflict = target["true_owner_habit_location"] != target["true_location"]
                    coverage[method]["targets_require_distinct_actions"] += conflict
                    coverage[method]["same_put_back_and_search_first"] += (
                        row["put_back"] == row["search_order"][0]
                    )
                    rank = row["search_order"]
                    size = len(support)
                    regret = (
                        rank.index(target["true_location"]) / max(1, size - 1)
                        if target["true_location"] in rank
                        else 1.0
                    )
                    measurements = {
                        "n": 1,
                        "put_errors": int(put),
                        "search_errors": int(search),
                        "action_regret": int(put) + regret,
                    }
                    counts.update(measurements)
                    phases[method][phase].update(measurements)
                    coverage[method]["search_error_while_habit_correct"] += bool(search and not put)
                    if row.get("eligible_fast", 0):
                        assert row["current_readout_choice"] == row["latest_choice"]
                        coverage[method]["eligible_fast_default_equals_latest"] += 1
                    coverage[method]["nonempty_long_term_steps"] += row.get("committed", 0) > 0
                    checks += 1
                for key, expected in (
                    ("put_back_error_rate", counts["put_errors"] / n),
                    ("search_error_rate", counts["search_errors"] / n),
                    ("cumulative_action_regret", counts["action_regret"]),
                ):
                    assert math.isclose(result["metric"][key], expected, abs_tol=1e-10), (
                        method,
                        key,
                    )
                    checks += 1
                aggregates[method].update(counts)
                per_episode[method].append({k: v / n for k, v in counts.items() if k != "n"})
                for k, v in result.get("ledger_operations", {}).items():
                    coverage[method]["ledger_" + k] += v
                for k, v in result.get("operator_changes", {}).items():
                    coverage[method]["changed_" + k] += v
                for trace in result["metric"]["revision_action_traces"]:
                    request = trace["project_one_request"]
                    if request:
                        coverage[method]["request_" + request["kind"]] += 1
                        coverage[method][
                            "request_status_" + trace["request_application_status"]
                        ] += 1
            joint, factor = (results[m]["runtime_audit"]["fairness_receipts"] for m in METHODS[:2])
            assert len(joint) == len(factor) > 0
            for j, f in zip(joint, factor, strict=True):
                assert {
                    k: v for k, v in j.items() if k not in ("arm", "proposal_support_sha256")
                } == {k: v for k, v in f.items() if k not in ("arm", "proposal_support_sha256")}
                checks += 1
            pair = summary["paired"][index]
            for action, key in (
                ("put_back", "put_back_disagreements"),
                ("search_order", "search_disagreements"),
            ):
                assert pair[key] == sum(
                    a[action] != b[action]
                    for a, b in zip(
                        results[METHODS[0]]["actions"], results[METHODS[1]]["actions"], strict=True
                    )
                )
                checks += 1
        for method, counts in aggregates.items():
            for key, metric_key in (
                ("put_errors", "put_back_error_rate"),
                ("search_errors", "search_error_rate"),
            ):
                assert math.isclose(
                    mean(r[key] for r in per_episode[method]),
                    summary["metrics"][method][metric_key],
                    abs_tol=1e-10,
                )
                checks += 1
            assert math.isclose(
                counts["action_regret"] / counts["n"],
                summary["metrics"][method]["cumulative_action_regret_per_step"],
                abs_tol=1e-10,
            )
            checks += 1
        differences = {
            method: {
                key: paired_interval(
                    [j[key] - b[key] for j, b in zip(per_episode[METHODS[0]], rows, strict=True)]
                )
                for key in ("put_errors", "search_errors", "action_regret")
            }
            for method, rows in per_episode.items()
            if method != METHODS[0]
        }
        report[condition] = {
            "counts": aggregates,
            "phases": phases,
            "coverage": coverage,
            "joint_minus_control_lower_is_better": differences,
        }
    return {
        "checks": checks,
        "conditions": report,
        "boundary": "D0 development; bootstrap descriptive, not a new confirmatory gate",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.folder, args.root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checks": result["checks"], "conditions": list(result["conditions"])}))
