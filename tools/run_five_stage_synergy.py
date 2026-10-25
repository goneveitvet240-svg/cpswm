"""Frozen paired audit plus complete RB history traces; no default model change."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
import subprocess
from dataclasses import asdict
from pathlib import Path

from analyze_matched_readout import capture, decompose, pick, read_archive
from run_joint_three_questions import paired_counts
from run_matched_value import (
    CONDITIONS,
    NATIVE,
    CommitBarrier,
    PublicCatalogueAdapter,
    action_payload,
    dataset_for,
    make_state,
    save,
    state_audit,
)
from synergy_runtime import PosteriorParentRuntime

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.reproducibility import _canonical_value, content_sha256

ROOT = Path(__file__).resolve().parents[1]
NEW_SEEDS = (752601, 752602, 752603)


def bound_sources():
    paths = [
        *ROOT.glob("src/**/*.py"),
        *[
            ROOT / "tools" / name
            for name in (
                "run_five_stage_synergy.py",
                "synergy_runtime.py",
                "run_matched_value.py",
                "run_joint_three_questions.py",
                "analyze_matched_readout.py",
                "run_current_event.py",
                "run_research_pilot.py",
                "verify_full_mechanism_value.py",
            )
        ],
        *ROOT.glob("configs/**/*.json"),
        ROOT / "tests/test_five_stage_synergy.py",
        ROOT / "docs/reviews/pc_a/five_stage_synergy_2026-10-25/PROTOCOL.md",
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
    }


def snapshot(state):
    runtime = state.runtime
    raw = capture(state)
    result = {
        "raw": raw,
        "decomposition": decompose(raw),
        "sampling": runtime.sampling_receipts[-1],
        "particles": [],
    }
    for p, receipt in zip(runtime.particles, runtime.importance_revision_receipts[-1], strict=True):
        w = p.world
        cells = []
        for (actor, regime), cell in sorted(w.rb_cells.items()):
            distribution = cell.combined_location_distribution(
                runtime._last_observation.known_location_ids,
                runtime._last_observation.base_location_distribution,
            )
            cells.append(
                {
                    "actor": actor,
                    "regime": regime,
                    "cell": asdict(cell),
                    "active": regime == w.active_regime,
                    "retired": regime in w.retired_regimes,
                    "distribution": {str(k): v for k, v in distribution.items()},
                }
            )
        result["particles"].append(
            {
                "id": str(w.typed_state.particle_id),
                "parent": str(w.typed_state.parent_particle_id),
                "weight": p.posterior_probability,
                "active_regime": w.active_regime,
                "retired_regimes": w.retired_regimes,
                "actor_history": w.ordered_actor_role_history,
                "instance_history": w.instance_association_history,
                "cause_history": w.change_cause_history,
                "regime_history": w.habit_regime_history,
                "cells": cells,
                "receipt": receipt,
            }
        )
    return result


def history_score(trace, truth):
    """Evaluator only, called after all actions committed; never changes a state."""
    totals = dict(
        any_owner_cell=0.0,
        active_owner_cell=0.0,
        retired_owner_cell=0.0,
        selected_readable_owner_cell=0.0,
    )
    owner = trace["raw"]["owner"]
    for p, raw in zip(trace["particles"], trace["raw"]["particles"], strict=True):
        good = [
            c
            for c in p["cells"]
            if c["actor"] == owner
            and c["cell"]["observation_count"] > 0
            and pick(c["distribution"]) == truth
        ]
        active = any(c["active"] for c in good)
        totals["any_owner_cell"] += p["weight"] * bool(good)
        totals["active_owner_cell"] += p["weight"] * active
        totals["retired_owner_cell"] += p["weight"] * any(c["retired"] for c in good)
        totals["selected_readable_owner_cell"] += p["weight"] * (
            active and raw["actor"] == owner and raw["instance"] == "target_instance"
        )
    return totals


def summarize(points):
    result = {}
    for cohort in ("old", "new"):
        rows = [p for p in points if p["cohort"] == cohort]
        if not rows:
            continue
        truths = [p["truth"] for p in rows]
        names = list(rows[0]["actions"])
        comparisons = {}
        for name in names:
            actions = [p["actions"][name]["put_back"] for p in rows]
            comparisons[name] = {
                control: paired_counts(
                    [p["actions"][control]["put_back"] for p in rows], actions, truths
                )
                for control in names
                if control != name
            }
        result[cohort] = {
            "points": len(rows),
            "comparisons": comparisons,
            "native": {
                name: {
                    "mean_ess": statistics.mean(p["stats"][name]["ess"] for p in rows),
                    "low_prior_draws": sum(p["stats"][name]["low_prior_draws"] for p in rows),
                    "mean_analytic_mass": statistics.mean(
                        p["stats"][name]["analytic_mass"] for p in rows
                    ),
                    "budget_equal": all(p["stats"][name]["budget_equal"] for p in rows),
                }
                for name in rows[0]["stats"]
            },
        }
    return result


def run(output, quick=False):
    sources = bound_sources()
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status and not quick:
        raise ValueError("clean source required")
    archive = read_archive()
    output.mkdir(parents=True, exist_ok=False)
    points = []
    for cohort in ("old", "new"):
        for condition in ("complete32", "sparse32", "long64"):
            dataset = (
                dataset_for(condition)
                if cohort == "old"
                else PublicCatalogueAdapter(
                    validation_seeds=(7, 8, 9),
                    test_seeds=NEW_SEEDS,
                    max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
                    dataset_version="mechanism-value-development-20261011:" + condition,
                    sealed_secret="mechanism-value-development-20261011:" + condition,
                    **CONDITIONS[condition],
                ).build()
            )
            selection = archive[condition + "/selection.json"]["methods"]
            for episode in dataset.visible_episodes(Split.TEST):
                states = {
                    arm + "/" + proposal: make_state(episode, arm)
                    for arm in NATIVE
                    for proposal in ("original", "posterior_parent")
                }
                for name, state in states.items():
                    if name.endswith("posterior_parent"):
                        r = state.runtime
                        state.runtime = PosteriorParentRuntime(
                            arm=r.arm, config=r.config, neural_model=r.neural_model
                        )
                for method in ("latest_owner", "matched_amg"):
                    choice = selection[method]
                    parameter = choice["trials"][choice["selected_index"]]["parameter"]
                    states[method] = make_state(episode, method, parameter)
                trace_rows = []
                for index, step in enumerate(episode.steps[:2] if quick else episode.steps):
                    barrier = CommitBarrier(states, content_sha256(step))
                    actions, readings, stats = {}, {}, {}
                    for name, state in states.items():
                        state.observe(step.model_copy(deep=True))
                        action = action_payload(state.predict(), episode.known_location_ids)
                        barrier.commit(name, content_sha256(step), action)
                        actions[name] = action
                        if "/" in name:
                            if cohort == "old" and name.endswith("original"):
                                old = archive[f"{condition}/evaluation-{episode.episode_id}.json"]
                                if action != old["rows"][name.split("/")[0]][index]["action"]:
                                    raise ValueError("original action replay drift")
                            readings[name] = snapshot(state)
                            d = readings[name]["decomposition"]
                            weights = [p.posterior_probability for p in state.runtime.particles]
                            stats[name] = {
                                "ess": sum(weights) ** 2 / sum(w * w for w in weights),
                                "low_prior_draws": readings[name]["raw"]["low_prior_draws"],
                                "analytic_mass": d["analytic_mass"],
                            }
                    truth = barrier.release(
                        lambda ds=dataset, eid=episode.episode_id, sid=step.step_id: ds.truth_for(
                            eid
                        ).truth_by_step[sid]
                    )
                    target = str(truth.true_owner_habit_location)
                    for state in states.values():
                        state.feedback(step.model_copy(deep=True))
                    for name in stats:
                        arm = name.split("/")[0]
                        audit, baseline = (
                            state_audit(states[name]),
                            state_audit(states[arm + "/original"]),
                        )
                        stats[name].update(
                            {
                                "history": history_score(readings[name], target),
                                "budget_equal": all(
                                    audit[k] == baseline[k]
                                    for k in (
                                        "target_evaluations",
                                        "particles",
                                        "extra_ciav_queries",
                                        "paid_location_sources",
                                    )
                                ),
                                "audit": audit,
                            }
                        )
                        if not stats[name]["budget_equal"]:
                            raise ValueError("unequal native budget")
                    points.append(
                        {
                            "cohort": cohort,
                            "condition": condition,
                            "episode_id": str(episode.episode_id),
                            "step": index + 1,
                            "input_sha256": content_sha256(step),
                            "truth": target,
                            "true_actor": truth.true_actor,
                            "actions": actions,
                            "stats": stats,
                        }
                    )
                    if cohort == "old" and condition == "sparse32":
                        trace_rows.append(
                            {"step": index + 1, "truth": target, "readings": readings}
                        )
                if trace_rows:
                    data = json.dumps(
                        _canonical_value(trace_rows), separators=(",", ":"), allow_nan=False
                    ).encode()
                    (output / f"history-{episode.episode_id}.json.gz").write_bytes(
                        gzip.compress(data, mtime=0)
                    )
                save(output / "points.json", points)
                save(output / "summary.json", summarize(points))
                print(cohort, condition, episode.episode_id, "complete", len(points), flush=True)
                if quick:
                    break
    if sources != bound_sources():
        raise ValueError("source changed while running")
    save(
        output / "manifest.json",
        {
            "source_sha": code_sha,
            "git_status": status,
            "sources": sources,
            "new_seeds": NEW_SEEDS,
            "quick": quick,
            "scientific_acceptance": False,
            "artifacts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file()
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    run(args.output, args.quick)
