"""Matched 32-day production readout/likelihood factorial; semantic fixture only.

All policies receive the same ordered observations. Evaluation truth is opened
only after the rollout. Output commands are planned PUT_BACK actions, not Unity
manipulation. Baselines use the identical current actor masses.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from run_correction_replay_comparison import CIAVOutcomeKind, GroundedTransition, build, raw_for
from run_matched_transition_death_test import digest, save

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    StructureTwoActionScenarioGenerator,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256
from cpswm.system.runtime_readout import current_action_readout
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def choice(d):
    return str(max(sorted(d, key=str), key=d.__getitem__))


def run(output, seeds):
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    paths = [
        *(root / "src").rglob("*.py"),
        Path(__file__),
        root / "tools/run_correction_replay_comparison.py",
        root / "tools/run_controlled_semantic_mechanism.py",
        root / "tests/structure_two_backbone_wiring_probe.py",
    ]
    files = {str(p.relative_to(root)): digest(p) for p in paths}
    source = content_sha256(files)
    configs = dict(
        legacy_slow=ActionReadoutConfig(),
        repaired=current_action_readout(),
        latest_owner=ActionReadoutConfig(readout=ActionReadout.LATEST_OWNER_EVENT),
    )
    cases = []
    # The whole pipeline's readout affects later evidence/context. Therefore run
    # each configured policy end to end, not just a post-hoc readout substitution.
    for seed in seeds:
        for actor_mode in ("legacy_biased_fixture", "presence_only"):
            for name, config in configs.items():
                caseid = f"{seed}-{actor_mode}-{name}"
                db = output / (caseid + ".db")
                probe, producer, stream, store, context = build(
                    db,
                    seed=seed,
                    source=source,
                    action_readout=config,
                    legacy_actor_fixture=actor_mode == "legacy_biased_fixture",
                    ciav_outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION,
                    include_open_world_unknown_events=True,
                )
                rows = []
                started = perf_counter()
                for index, day in enumerate(probe.observed_days()):
                    transition = probe.transition_for(day)
                    when = transition.after.detection_time + timedelta(minutes=1)
                    ids = stream.admit((raw_for(transition, index),), received_at=when)
                    producer.output = GroundedTransition(
                        transition, ids, "CONTROLLED_ORACLE_V1", "ASSUMED_NOT_EMPIRICAL"
                    )
                    receipt = stream.advance(cutoff=when)
                    core = stream._system.core
                    command = stream.prepare_habit_placement(decision_time=when)
                    dist = stream.current_habit_location_distribution()
                    counts = dict.fromkeys(probe.case.locations, 1.0)
                    for event in core._fast_action_events.values():
                        counts[event.location_id] += event.owner_mass
                    # Stronger ordinary recency baselines fixed in advance, not
                    # selected on held-out sequences. Report all, not best-only.
                    recency = {}
                    for half in (1.0, 3.0, 7.0):
                        weighted = dict.fromkeys(probe.case.locations, 1.0)
                        for event in core._fast_action_events.values():
                            age = (
                                transition.after.detection_time - event.evidence.event_time
                            ).total_seconds() / 86400
                            weighted[event.location_id] += event.owner_mass * 2 ** (
                                -max(0, age) / half
                            )
                        recency[str(half)] = choice(weighted)
                    primary = dict(receipt.result.primary_result.actor_posterior)
                    revised = (
                        dict(receipt.result.ciav_receipt.evidence.actor_posterior)
                        if receipt.result.ciav_receipt
                        else None
                    )
                    rows.append(
                        dict(
                            day=day.day,
                            command=choice(dist),
                            command_location=str(command.location_id),
                            distribution={str(k): v for k, v in dist.items()},
                            soft_full_history=choice(counts),
                            soft_recency=recency,
                            primary_actor=primary,
                            ciav_actor=revised,
                            committed=len(core._committed_events),
                            fast=len(core._fast_action_events),
                            operators=receipt.result.executed_operator_count,
                            rationale=receipt.result.primary_result.decision.rationale,
                        )
                    )
                    if rows[-1]["command"] != rows[-1]["command_location"]:
                        raise AssertionError("live command differs from configured readout")
                    if actor_mode == "presence_only" and revised is not None:
                        assert max(abs(primary[k] - revised[k]) for k in primary) < 1e-12
                # Recovery must keep the configured readout and its actual command.
                with sqlite3.connect(output / (caseid + "-resume.db")) as destination:
                    store._db.backup(destination)
                resumed_store = ContinuousStateStore(
                    output / (caseid + "-resume.db"),
                    source_identity=source,
                    dependency_identity=content_sha256(sys.version),
                )
                from run_controlled_semantic_mechanism import OracleProducer

                resumed = ContinuousEvidenceInput.resume(
                    resumed_store, producer=OracleProducer(), context_builder=context
                )
                equal = (
                    content_sha256(semantic_memory_state(stream._system.core))
                    == content_sha256(semantic_memory_state(resumed._system.core))
                    and stream.current_habit_location_distribution()
                    == resumed.current_habit_location_distribution()
                )
                assert equal
                # Truth is evaluator-only, after completion, matching exact visible case.
                case = StructureTwoActionScenarioGenerator(
                    duration_days=32,
                    observation_coverage=1.0,
                    include_open_world_unknown_events=True,
                    unknown_event_days=(1,),
                ).generate(seed)
                assert content_sha256(case.visible) == content_sha256(probe.case)
                for row in rows:
                    truth = str(case.truth_by_day[row["day"]].true_owner_habit_location)
                    row["true_habit"] = truth
                    row["correct"] = {
                        "runtime": row["command"] == truth,
                        "soft_full_history": row["soft_full_history"] == truth,
                        **{
                            f"soft_half_life_{k}": v == truth
                            for k, v in row["soft_recency"].items()
                        },
                    }
                stages = {
                    "all": (0, 32),
                    "initial": (0, 7),
                    "guest": (7, 15),
                    "post_guest": (15, 17),
                    "new_habit": (17, 26),
                    "recurrence": (26, 32),
                }
                metrics = {
                    stage: {
                        "n": sum(lo <= r["day"] < hi for r in rows),
                        "correct": {
                            method: sum(r["correct"][method] for r in rows if lo <= r["day"] < hi)
                            for method in rows[0]["correct"]
                        },
                    }
                    for stage, (lo, hi) in stages.items()
                }
                result = dict(
                    seed=seed,
                    actor_mode=actor_mode,
                    policy=name,
                    config=str(config),
                    rows=rows,
                    metrics=metrics,
                    recovery_equal=equal,
                    seconds=perf_counter() - started,
                    visible_case_sha256=content_sha256(probe.case),
                )
                save(output / (caseid + ".json"), result)
                cases.append({k: v for k, v in result.items() if k != "rows"})
                store.close()
                resumed_store.close()
                print(caseid, metrics["all"], flush=True)
    assert all(digest(root / name) == value for name, value in files.items()), (
        "source changed during run"
    )
    save(
        output / "comparison.json",
        dict(
            source_sha256=source,
            source_files=files,
            cases=cases,
            seeds=seeds,
            days=32,
            scope="CONTROLLED_SEMANTIC_PRODUCTION_COMMANDS_NOT_REAL_HUMAN_CALIBRATION_OR_PHYSICAL_PLACEMENT",
            source_unchanged=True,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[7, 8, 9])
    a = p.parse_args()
    run(a.output, a.seeds)
