"""Authorized development diagnosis: posterior, history-read gates, paired utility.

Experimental read policies live in this tool only. Production defaults are unchanged.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path

from analyze_matched_readout import CAUSE, capture, decompose, norm, pick, read_archive
from run_current_event import dataset_for as short_dataset
from run_matched_value import (
    NATIVE,
    CommitBarrier,
    action_payload,
    dataset_for,
    make_state,
    save,
    sources,
    state_audit,
)
from run_research_pilot import tv
from run_short_history_reference import run as short_run
from verify_short_history_reference import verify_replayed_run, verify_traces

from cpswm.contracts import EventMechanism
from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations.structure_two_current_event import CurrentEventRuntime
from cpswm.system.evaluation_operations.structure_two_selected_method import StructureTwoOperator
from cpswm.system.reproducibility import _canonical_value, content_sha256

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("actor_read", "history_read")
REPORT = ROOT / "docs/reviews/pc_a/joint_three_questions_2026-10-25"
OLD = ROOT / "docs/reviews/pc_a/matched_readout_2026-10-25"


def eligible(actor, instance, owner, policy):
    if policy not in (*POLICIES, "original"):
        raise ValueError("unknown read policy")
    return (policy != "original" or actor == owner) and (
        policy == "history_read" or instance == "target_instance"
    )


def scalar_read(raw, policy):
    """Independent raw-statistics reconstruction, never supplied evaluator truth."""
    base = norm(raw["base"])
    locations = raw["locations"]
    if len(locations) != len(set(locations)) or set(locations) != set(base):
        raise ValueError("RB support mismatch")
    accumulated = dict.fromkeys(base, 0.0)
    mass = 0.0
    for p in raw["particles"]:
        if not eligible(p["actor"], p["instance"], raw["owner"], policy):
            continue
        cell = p["owner_cell"]
        if cell is None:
            continue
        if not math.isfinite(p["weight"]) or p["weight"] < 0:
            raise ValueError("invalid weight")
        d = norm(dict(zip(locations, cell["location_alpha"], strict=True)))
        r = norm(
            dict(
                zip(
                    locations,
                    (
                        n / v
                        for n, v in zip(cell["ridge_natural"], cell["ridge_precision"], strict=True)
                    ),
                    strict=True,
                )
            )
        )
        a = (
            p["weight"]
            * CAUSE[p["cause"]]
            * (0.55 if p["unknown_mechanism"] else 1)
            * min(1, 0.55 + 0.08 * p["run_length"])
            * min(1, cell["information_natural"] / cell["information_precision"])
        )
        mass += a
        for k in base:
            accumulated[k] += a * (d[k] + r[k]) / 2
    if not 0 <= mass <= 1 + 1e-10:
        raise ValueError("analytic mass outside simplex")
    pre = norm({k: (1 - mass) * base[k] + accumulated[k] for k in base})
    ledger = raw["ledger"]
    final = (
        pre if ledger is None else norm({k: 0.75 * pre[k] + 0.25 * ledger.get(k, 0) for k in base})
    )
    return {"distribution": final, "action": pick(final), "analytic_mass": mass}


class HistoryReadRuntime(CurrentEventRuntime):
    """Only final action readout changes; internal consolidation reads stay original."""

    def __init__(self, *, read_policy, **kwargs):
        eligible("", "", "", read_policy)
        self.read_policy = read_policy
        super().__init__(**kwargs)

    def _posterior_action_distribution(self, observation, *, include_ledger):
        if not include_ledger:
            return super()._posterior_action_distribution(observation, include_ledger=False)
        base = dict(observation.base_location_distribution)
        total = sum(base.values())
        base = {k: v / total for k, v in base.items()}
        result = dict.fromkeys(base, 0.0)
        consumed = 0.0
        for p in self.particles:
            w = p.world
            if not eligible(
                w.placement_actor,
                w.instance_association_history[-1],
                observation.owner_actor_key,
                self.read_policy,
            ):
                continue
            cell = w.rb_cells.get((observation.owner_actor_key, w.active_regime))
            component = (
                base
                if cell is None
                else cell.combined_location_distribution(observation.known_location_ids, base)
            )
            weight = (
                p.posterior_probability
                * CAUSE[w.change_cause_history[-1].value]
                * (
                    0.55
                    if w.event_chain[-1].startswith(EventMechanism.UNKNOWN_MECHANISM.value)
                    else 1
                )
                * min(1, 0.55 + 0.08 * w.typed_state.run_length)
            )
            consumed += weight
            for k in base:
                result[k] += weight * component[k]
        for k in base:
            result[k] += max(0, 1 - consumed) * base[k]
        total = sum(result.values())
        result = {k: v / total for k, v in result.items()}
        ledger = self.rgrc_ledger.active_distribution
        if ledger is not None and StructureTwoOperator.RGRC not in self.neutralized_operators:
            result = {k: 0.75 * v + 0.25 * ledger.get(k, 0) for k, v in result.items()}
            total = sum(result.values())
            result = {k: v / total for k, v in result.items()}
        return result


def experimental_state(episode, arm, policy):
    state = make_state(episode, arm)
    original = state.runtime
    state.runtime = HistoryReadRuntime(
        read_policy=policy,
        arm=original.arm,
        config=original.config,
        neural_model=original.neural_model,
    )
    return state


def paired_counts(base_actions, actions, truths):
    if not (len(base_actions) == len(actions) == len(truths)):
        raise ValueError("unaligned paired outcomes")
    rows = list(zip(base_actions, actions, truths, strict=True))
    return {
        "points": len(rows),
        "errors": sum(a != t for _, a, t in rows),
        "fixed": sum(b != t and a == t for b, a, t in rows),
        "harmed": sum(b == t and a != t for b, a, t in rows),
        "changed_actions": sum(b != a for b, a, _ in rows),
        "both_wrong": sum(b != t and a != t for b, a, t in rows),
    }


def load_previous():
    manifest = json.loads((OLD / "MANIFEST.json").read_text())
    for name, spec in manifest["files"].items():
        data = (OLD / name).read_bytes()
        if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise ValueError("PR124 artifact mismatch: " + name)
    raw = gzip.decompress((OLD / "evidence/points.json.gz").read_bytes())
    if hashlib.sha256(raw).hexdigest() != manifest["points_uncompressed"]["sha256"]:
        raise ValueError("PR124 decompressed hash mismatch")
    bound = json.loads((OLD / "evidence/manifest.json").read_text())
    for name, digest in bound["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("PR124 bound source mismatch: " + name)
    return json.loads(raw)


def q1_analysis(run):
    """Score only after all reference and sampled predictions have been fixed."""
    dataset = short_dataset("sparse32", [67001])
    episodes = {str(e.episode_id): e for e in dataset.visible_episodes(Split.VALIDATION)}
    joint = {
        (r["episode_id"], r["depth"]): r for r in run["rows"] if r["arm"] == "stateful_full_joint"
    }
    result = []
    for row in run["rows"]:
        episode = episodes[row["episode_id"]]
        truth = dataset.truth_for(episode.episode_id).truth_by_step[
            episode.steps[row["depth"] - 1].step_id
        ]
        common = joint[row["episode_id"], row["depth"]]["reference"]
        variants = [("exact", row["reference"]["marginals"], row["reference"]["action"])]
        variants += [
            (m["method"], {a: v["sampled"] for a, v in m["marginals"].items()}, m["action"])
            for m in row["methods"]
        ]
        for method, marginals, action in variants:
            actor = marginals["placement_actor"]
            result.append(
                {
                    "episode_id": row["episode_id"],
                    "depth": row["depth"],
                    "arm": row["arm"],
                    "method": method,
                    "true_actor": truth.true_actor,
                    "true_mechanism": truth.true_mechanism.value,
                    "truth_habit": str(truth.true_owner_habit_location),
                    "actor_distribution": actor,
                    "habit_distribution": action,
                    "actor_truth_probability": actor.get(truth.true_actor, 0),
                    "actor_error": int(pick(actor) != truth.true_actor),
                    "habit_error": int(pick(action) != str(truth.true_owner_habit_location)),
                    "own_target_tv": {
                        a: tv(v, row["reference"]["marginals"][a]) for a, v in marginals.items()
                    },
                    "common_joint_target_tv": {
                        a: tv(v, common["marginals"][a]) for a, v in marginals.items()
                    },
                }
            )
    return result


def summarize_q1(rows):
    result = {}
    for arm in sorted({r["arm"] for r in rows}):
        for method in sorted({r["method"] for r in rows}):
            values = [r for r in rows if r["arm"] == arm and r["method"] == method]
            result[arm + "/" + method] = {
                "points": len(values),
                "actor_errors": sum(r["actor_error"] for r in values),
                "habit_errors": sum(r["habit_error"] for r in values),
                "mean_true_actor_probability": statistics.mean(
                    r["actor_truth_probability"] for r in values
                ),
                "mean_own_actor_tv": statistics.mean(
                    r["own_target_tv"]["placement_actor"] for r in values
                ),
                "mean_common_joint_actor_tv": statistics.mean(
                    r["common_joint_target_tv"]["placement_actor"] for r in values
                ),
            }
    return result


def summarize_q23(points):
    result = {}
    truths = [p["truth"] for p in points]
    for name in points[0]["variants"]:
        arm = name.split("/")[0]
        values = [p["variants"][name] for p in points]
        actions = [v["action"]["put_back"] for v in values]
        comparisons = {}
        for control in (arm, "latest_owner", "matched_amg"):
            comparisons[control] = paired_counts(
                [p["controls"][control]["put_back"] for p in points], actions, truths
            )
        recurrence = [i for i, p in enumerate(points) if p["old_error_class"] == "recurrence"]
        result[name] = {
            "paired": comparisons,
            "recurrence_errors": sum(actions[i] != truths[i] for i in recurrence),
            "recurrence_points": len(recurrence),
            "raw_scalar_max_error": max(v["scalar_error"] for v in values),
            "offline_live_max_tv": max(v["offline_live_tv"] for v in values),
            "same_feedback_state": sum(v["same_feedback_state"] for v in values),
            "same_write_state": sum(v["same_write_state"] for v in values),
            "same_search": sum(
                v["action"]["search_order"] == p["controls"][arm]["search_order"]
                for p, v in zip(points, values, strict=True)
            ),
            "same_target_budget": sum(v["same_target_budget"] for v in values),
            "changed_distribution": sum(v["original_tv"] > 1e-12 for v in values),
            "mean_analytic_mass": statistics.mean(v["scalar"]["analytic_mass"] for v in values),
        }
    return result


def write_state(runtime):
    return content_sha256({"particles": runtime.particles, "ledger": runtime.rgrc_ledger.head_hash})


def q23_run(output, quick=False):
    archived = read_archive()
    previous = {(p["condition"], p["episode_id"], p["step"]): p for p in load_previous()}
    points = []
    for condition in ("complete32", "sparse32", "long64"):
        dataset = dataset_for(condition)
        selection = archived[condition + "/selection.json"]["methods"]
        for episode in dataset.visible_episodes(Split.TEST):
            old = archived[f"{condition}/evaluation-{episode.episode_id}.json"]
            if content_sha256(episode) != old["episode_sha256"]:
                raise ValueError("public episode changed")
            variants = {
                arm + "/" + policy: experimental_state(episode, arm, policy)
                for arm in NATIVE
                for policy in POLICIES
            }
            controls = {arm: make_state(episode, arm) for arm in NATIVE}
            for method in ("latest_owner", "matched_amg"):
                choice = selection[method]
                parameter = choice["trials"][choice["selected_index"]]["parameter"]
                controls[method] = make_state(episode, method, parameter)
            for index, step in enumerate(episode.steps[:4] if quick else episode.steps):
                p = previous[condition, str(episode.episode_id), index + 1]
                barrier = CommitBarrier([*controls, *variants], content_sha256(step))
                control_actions, readings = {}, {}
                for name, state in controls.items():
                    state.observe(step.model_copy(deep=True))
                    action = action_payload(state.predict(), episode.known_location_ids)
                    if action != old["rows"][name][index]["action"]:
                        raise ValueError("original control replay changed")
                    barrier.commit(name, content_sha256(step), action)
                    control_actions[name] = action
                for name, state in variants.items():
                    arm, policy = name.split("/")
                    delivered = step.model_copy(deep=True)
                    state.observe(delivered)
                    before = write_state(state.runtime)
                    action = action_payload(state.predict(), episode.known_location_ids)
                    barrier.commit(name, content_sha256(delivered), action)
                    raw = capture(state)
                    scalar = scalar_read(raw, policy)
                    error = max(
                        abs(raw["actual"][k] - scalar["distribution"][k]) for k in raw["actual"]
                    )
                    if error > 1e-10 or before != write_state(state.runtime):
                        raise ValueError(
                            "read intervention changed writes or disagreed with scalar"
                        )
                    original = copy.deepcopy(raw)
                    original["actual"] = scalar_read(raw, "original")["distribution"]
                    decompose(original)
                    offline = scalar_read(p["raw"][arm], policy)
                    readings[name] = {
                        "action": action,
                        "raw": raw,
                        "scalar": scalar,
                        "scalar_error": error,
                        "offline_live_tv": tv(offline["distribution"], raw["actual"]),
                        "original_tv": tv(original["actual"], raw["actual"]),
                        "same_write_state": before == write_state(controls[arm].runtime),
                    }
                truth = barrier.release(
                    lambda ds=dataset, eid=episode.episode_id, sid=step.step_id: ds.truth_for(
                        eid
                    ).truth_by_step[sid]
                )
                if str(truth.true_owner_habit_location) != p["truth_owner_habit"]:
                    raise ValueError("truth disagrees with PR124")
                for name, state in controls.items():
                    state.feedback(step.model_copy(deep=True))
                    if (
                        name in NATIVE
                        and _canonical_value(state_audit(state))
                        != old["rows"][name][index]["after_feedback"]
                    ):
                        raise ValueError("original feedback state mismatch")
                for name, state in variants.items():
                    arm = name.split("/")[0]
                    state.feedback(step.model_copy(deep=True))
                    audit = _canonical_value(state_audit(state))
                    baseline = _canonical_value(state_audit(controls[arm]))
                    readings[name].update(
                        {
                            "after_feedback": audit,
                            "same_feedback_state": audit == baseline,
                            "same_target_budget": all(
                                audit[k] == baseline[k]
                                for k in (
                                    "target_evaluations",
                                    "particles",
                                    "extra_ciav_queries",
                                    "paid_location_sources",
                                )
                            ),
                        }
                    )
                old_error = control_actions["native_joint"]["put_back"] != p["truth_owner_habit"]
                error_class = (
                    None
                    if not old_error
                    else (
                        "cold"
                        if p["latest_owner_location"] is None
                        else "recurrence"
                        if p["truth_location_seen_in_public_prefix"]
                        else "new_habit"
                    )
                )
                points.append(
                    {
                        "condition": condition,
                        "episode_id": str(episode.episode_id),
                        "step": index + 1,
                        "input_sha256": content_sha256(step),
                        "truth": str(truth.true_owner_habit_location),
                        "old_error_class": error_class,
                        "controls": control_actions,
                        "variants": readings,
                    }
                )
            print(
                condition,
                episode.episode_id,
                "six native arms and two controls complete",
                flush=True,
            )
            if quick:
                break
    save(output / "points.json", points)
    return summarize_q23(points)


def bound_sources():
    extra = [
        Path(__file__),
        ROOT / "tests/test_joint_three_questions.py",
        REPORT / "PROTOCOL.md",
        ROOT / "tools/run_short_history_reference.py",
        ROOT / "tools/verify_short_history_reference.py",
        ROOT / "tools/run_current_event.py",
        ROOT / "tools/analyze_matched_readout.py",
        OLD / "MANIFEST.json",
        OLD / "evidence/points.json.gz",
    ]
    return {
        **sources(),
        **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in extra},
    }


def run(output, quick=False):
    source = bound_sources()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status and not quick:
        raise ValueError("formal run requires clean worktree")
    output.mkdir(parents=True, exist_ok=False)
    q1dir = output / "q1"
    q1dir.mkdir()
    reference = short_run(q1dir)
    verify_traces(q1dir, reference)
    save(q1dir / "reference.json", reference)
    q1 = q1_analysis(reference)
    save(q1dir / "scored.json", q1)
    summary = {"q1": summarize_q1(q1), "q23": q23_run(output, quick)}
    save(output / "summary.json", summary)
    if source != bound_sources():
        raise ValueError("bound source changed")
    save(
        output / "manifest.json",
        {
            "source_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_status": status,
            "source_unchanged": True,
            "files": source,
            "quick": quick,
            "scientific_acceptance": False,
            "artifacts": {
                str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        },
    )


def verify(output, replay_q1=None):
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["files"] != bound_sources() or not manifest["source_unchanged"]:
        raise ValueError("source mismatch")
    for name, digest in manifest["artifacts"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError("artifact mismatch: " + name)
    summary = json.loads((output / "summary.json").read_text())
    points = json.loads((output / "points.json").read_text())
    previous = {(p["condition"], p["episode_id"], p["step"]): p for p in load_previous()}
    for p in points:
        old = previous[p["condition"], p["episode_id"], p["step"]]
        for name, v in p["variants"].items():
            arm, policy = name.split("/")
            recalculated = scalar_read(v["raw"], policy)
            if recalculated != v["scalar"] or recalculated["action"] != v["action"]["put_back"]:
                raise ValueError("readout/action rescore mismatch")
            offline = scalar_read(old["raw"][arm], policy)
            if tv(offline["distribution"], v["raw"]["actual"]) != v["offline_live_tv"]:
                raise ValueError("offline/live mismatch")
    reference = json.loads((output / "q1/reference.json").read_text())
    trace_count = verify_traces(output / "q1", reference)
    q1 = q1_analysis(reference)
    if q1 != json.loads((output / "q1/scored.json").read_text()) or summary != {
        "q1": summarize_q1(q1),
        "q23": summarize_q23(points),
    }:
        raise ValueError("scoring mismatch")
    if replay_q1 is not None:
        replay_q1.mkdir(parents=True, exist_ok=False)
        verify_replayed_run(reference, short_run(replay_q1))
    save(
        output / "verification.json",
        {
            "status": "SOURCE_AND_SCORING_VERIFIED",
            "points": len(points),
            "readout_checks": sum(len(p["variants"]) for p in points),
            "reference_traces": trace_count,
            "q1_full_replayed": replay_q1 is not None,
            "independent_scientific_review": False,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replay-q1", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.output, args.replay_q1)
    else:
        run(args.output, args.quick)


if __name__ == "__main__":
    main()
