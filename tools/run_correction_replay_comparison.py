"""Controlled P5 correction, recovery and fresh semantic-sequence replay.

Synthetic semantic observations and assumed CIAV/feedback likelihoods are explicit.
No natural pixels, human truth, neural training or scientific gate pass is claimed.
The invalidation intervention is fixed to the first seven source days before the
run; it is not selected by inspecting which action would improve.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import fields
from datetime import timedelta
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from run_controlled_semantic_mechanism import (  # noqa: E402
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
    OracleProducer,
    build_execution_feedback_bundle,
    raw_for,
    source_identity,
)

from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.reproducibility import canonical_json, content_sha256  # noqa: E402
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext  # noqa: E402
from cpswm.system.structure_two_continuous_input import (  # noqa: E402
    ContinuousEvidenceInput,
    GroundedTransition,
)
from cpswm.system.structure_two_semantic_identity import semantic_memory_state  # noqa: E402


def summary(stream):
    core = stream._system.core
    dist = stream.current_habit_location_distribution()
    semantic = semantic_memory_state(core)
    try:
        joint = stream.current_joint_decision_view()
        joint_readout = {"available": True, "atoms": len(joint.atoms)}
    except ValueError as error:
        joint_readout = {"available": False, "reason": str(error)}
    joint_readout["batch_present"] = core._particle_workspace.batch is not None
    joint_readout["posterior_source_count"] = len(core._particle_workspace.posterior_sources)
    return {
        "semantic_sha256": content_sha256(semantic),
        "semantic_sections": {k: content_sha256(v) for k, v in semantic.items()},
        "joint_readout": joint_readout,
        "distribution": {str(k): v for k, v in sorted(dist.items(), key=lambda x: str(x[0]))},
        "argmax": str(max(sorted(dist, key=str), key=dist.__getitem__)),
        "committed_sources": sorted(
            str(e.source_record_id) for e in core._committed_events.values()
        ),
        "observed_sources": sorted(str(e.source_record_id) for e in core._observed_events.values()),
        "ledger_projection_replay_equivalent": (
            core.verify_hybrid_full_rerun_equivalence().equivalent
        ),
        "traces": len(stream.execution_traces()),
    }


def distance(a, b):
    return max(
        abs(a["distribution"].get(k, 0) - b["distribution"].get(k, 0))
        for k in set(a["distribution"]) | set(b["distribution"])
    )


def build(output, *, seed, source, ciav_journal=None):
    probe = BackboneWiringProbe.build(seed=seed)
    producer = OracleProducer()
    store = ContinuousStateStore(
        output, source_identity=source, dependency_identity=content_sha256(sys.version)
    )
    meta = probe.observed_days()[0].after.metadata

    def context_builder(system, item, when, step):
        probe.system = system
        probe.step_index = step
        key = str(item.transition.after.metadata.record_id)
        if ciav_journal is not None and key in ciav_journal:
            ciav = deepcopy(ciav_journal[key])
        else:
            ciav = probe.ciav_input(
                item.transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            )
            if ciav_journal is not None:
                ciav_journal[key] = deepcopy(ciav)
        return AdaptiveExecutionContext(
            router_features=probe.router_features(),
            step_index=step,
            ciav_input=ciav,
        )

    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="registered_p5_first",
        producer=producer,
        context_builder=context_builder,
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        state_store=store,
    )
    return probe, producer, stream, store, context_builder


def ingest(probe, producer, stream, *, skip_days=(), input_journal=None):
    rows = []
    for index, day in enumerate(probe.observed_days()[:12]):
        if index in skip_days:
            continue
        if input_journal is not None and index in input_journal:
            transition = deepcopy(input_journal[index])
        else:
            transition = probe.transition_for(day)
            if input_journal is not None:
                input_journal[index] = deepcopy(transition)
        when = transition.after.detection_time + timedelta(minutes=1)
        ids = stream.admit((raw_for(transition, index),), received_at=when)
        producer.output = GroundedTransition(
            transition, ids, "CONTROLLED_ORACLE_V1", "ASSUMED_NOT_EMPIRICAL"
        )
        start = perf_counter()
        receipt = stream.advance(cutoff=when)
        rows.append(
            {
                "day_index": index,
                "seconds": perf_counter() - start,
                "operators": receipt.result.executed_operator_count,
                "primary_source": str(transition.after.metadata.record_id),
                "actor_posterior": dict(receipt.result.primary_result.actor_posterior),
            }
        )
    producer.output = None
    return rows


def soft_memory_baseline(probe, event_rows, excluded=()):
    # Same post-inference events and correction targets as P5. This isolates the
    # downstream memory rule, not the upstream inference algorithm or calibration.
    counts = dict.fromkeys(probe.case.locations, 1.0)
    start = perf_counter()
    for rid, event in event_rows:
        if rid not in excluded:
            counts[event.location_id] += event.evidence.actor_posterior[probe.case.owner_actor]
    total = sum(counts.values())
    distribution = {str(k): v / total for k, v in sorted(counts.items(), key=lambda x: str(x[0]))}
    return {
        "distribution": distribution,
        "argmax": max(distribution, key=distribution.__getitem__),
        "seconds": perf_counter() - start,
        "scope": "same post-P5 observed events; unit-prior soft-count memory ablation only",
        "input_events": len(event_rows),
        "excluded_events": len(excluded),
    }


def apply_feedback(stream, bundles, received):
    rows = []
    for index, (feedback, binding, likelihood) in enumerate(bundles):
        start = perf_counter()
        result = stream.consume_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            received_at=received + timedelta(seconds=index),
            policy=CalibratedRetractionPolicy(retraction_delta=-0.2),
        )
        rows.append(
            {
                "operations": [str(x) for x in result.statistic_operations],
                "seconds": perf_counter() - start,
            }
        )
    return rows


def event_key(event):
    # Runtime-generated CIAV record/revision/snapshot UUIDs differ in a new model.
    # Correspondence uses semantics and is required to be unique below.
    return content_sha256(
        (event.evidence.event_time, event.location_id, event.evidence.actor_posterior)
    )


def run(output: Path, seed: int):
    output.mkdir(parents=True, exist_ok=False)
    source, files = source_identity()
    # This runner also belongs to the execution identity.
    import hashlib

    files[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    source = content_sha256(files)
    input_journal, ciav_journal = {}, {}
    probe, producer, stream, store, context = build(
        output / "online.db", seed=seed, source=source, ciav_journal=ciav_journal
    )
    steps = ingest(probe, producer, stream, input_journal=input_journal)
    before = summary(stream)
    event_rows = tuple(stream._system.core._observed_events.items())
    invalid_sources = {probe.observed_days()[i].after.detection_time.date() for i in range(7)}
    targets = [
        (rid, e)
        for rid, e in stream._system.core._committed_events.items()
        if e.evidence.event_time.date() in invalid_sources
    ]
    if not targets:
        raise RuntimeError("no legal nonempty invalidation targets; comparison is not executed")
    target_sources = {e.evidence.event_time.date() for _, e in targets}
    invalid_days = tuple(
        i
        for i, day in enumerate(probe.observed_days()[:12])
        if day.after.detection_time.date() in target_sources
    )
    bundles = [
        build_execution_feedback_bundle(
            probe,
            revision_id=rid,
            location_id=e.location_id,
            belief_snapshot_id=e.belief_snapshot_id,
            when=e.evidence.event_time,
            opportunity_id=e.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, e in targets
    ]
    with sqlite3.connect(output / "resumed.db") as destination:
        store._db.backup(destination)
    resumed_store = ContinuousStateStore(
        output / "resumed.db",
        source_identity=source,
        dependency_identity=content_sha256(sys.version),
    )
    resumed = ContinuousEvidenceInput.resume(
        resumed_store, producer=OracleProducer(), context_builder=context
    )
    received = probe.observed_days()[11].after.detection_time + timedelta(hours=2)
    feedback_rows = [apply_feedback(s, bundles, received) for s in (stream, resumed)]
    for candidate, rows in zip((stream, resumed), feedback_rows, strict=True):
        if any("retract" not in row["operations"] for row in rows) or any(
            rid in candidate._system.core._committed_events
            or rid in candidate._system.core._observed_events
            for rid, _ in targets
        ):
            raise RuntimeError("requested revisions were not actually retracted")
    after, restored = summary(stream), summary(resumed)

    # New system, no online checkpoint: rerun the same ordered semantic inputs,
    # CIAV action/likelihood/realizer configuration and delayed observations.
    replay_probe, replay_producer, replay, replay_store, _ = build(
        output / "full-semantic-replay.db",
        seed=seed,
        source=source,
        ciav_journal=ciav_journal,
    )
    replay_steps = ingest(replay_probe, replay_producer, replay, input_journal=input_journal)
    replay_before = summary(replay)
    replay_bundles = []
    correspondences = []
    for (original_rid, original), (feedback, _, likelihood) in zip(targets, bundles, strict=True):
        matches = [
            (rid, e)
            for rid, e in replay._system.core._committed_events.items()
            if event_key(e) == event_key(original)
        ]
        if len(matches) != 1:
            raise RuntimeError("fresh replay revision correspondence is not unique")
        rid, event = matches[0]
        replay_bundles.append(
            build_execution_feedback_bundle(
                replay_probe,
                revision_id=rid,
                location_id=event.location_id,
                belief_snapshot_id=event.belief_snapshot_id,
                when=event.evidence.event_time,
                opportunity_id=event.evidence.observation_opportunity_id,
                outcome_distribution=feedback.outcome_distribution,
                present_likelihood=likelihood.p_outcome_given_target_present,
                absent_likelihood=likelihood.p_outcome_given_target_absent,
                action_id=feedback.action_id,
                feedback_record_id=feedback.metadata.record_id,
            )
        )
        correspondences.append(
            {
                "original": str(original_rid),
                "replayed": str(rid),
                "semantic_sha256": event_key(event),
            }
        )
    replay_feedback = apply_feedback(replay, replay_bundles, received)
    replay_after = summary(replay)
    fresh_probe, fresh_producer, fresh, fresh_store, _ = build(
        output / "fresh-without-invalid.db",
        seed=seed,
        source=source,
        ciav_journal=ciav_journal,
    )
    fresh_steps = ingest(
        fresh_probe, fresh_producer, fresh, skip_days=invalid_days, input_journal=input_journal
    )
    fresh_summary = summary(fresh)
    result = {
        "seed": seed,
        "track": "CONTROLLED_INVALIDATION_DEVELOPMENT_ONLY",
        "source_sha256": source,
        "source_files": files,
        "invalidation_rule": (
            "primary source day indices 0..6; fixed before run; "
            "only realized cited revision feedback"
        ),
        "steps": steps,
        "before": before,
        "after": after,
        "fresh_without_invalid": fresh_summary,
        "feedback": feedback_rows[0],
        "full_semantic_replay": {
            "before_max_abs_difference": distance(before, replay_before),
            "after_max_abs_difference": distance(after, replay_after),
            "action_equal": after["argmax"] == replay_after["argmax"],
            "semantic_state_equal": after["semantic_sha256"] == replay_after["semantic_sha256"],
            "differing_semantic_sections": [
                k
                for k, value in after["semantic_sections"].items()
                if value != replay_after["semantic_sections"].get(k)
            ],
            "input_journal_sha256": content_sha256(input_journal),
            "steps": replay_steps,
            "feedback": replay_feedback,
            "revision_correspondences": correspondences,
            "scope": "same semantic inputs and assumed observations; fresh runtime IDs rebound; "
            "not byte-identical journal nor independent algorithm ground truth",
        },
        "targets": len(targets),
        "actually_invalidated_day_indices": invalid_days,
        "fresh_without_invalid_semantics": (
            "counterfactual omission of corresponding whole P5 source steps; "
            "not an exact same-journal reference"
        ),
        "recovery_max_abs_difference": distance(after, restored),
        "recovery_semantic_state_equal": after == restored,
        "fresh_inference_max_abs_difference": distance(after, fresh_summary),
        "fresh_inference_action_equal": after["argmax"] == fresh_summary["argmax"],
        "action_changed": before["argmax"] != after["argmax"],
        "fresh_inference_seconds": sum(r["seconds"] for r in fresh_steps),
        "memory_ablation_before": soft_memory_baseline(probe, event_rows),
        "memory_ablation_reversible_after": soft_memory_baseline(
            probe, event_rows, tuple(rid for rid, _ in targets)
        ),
        "memory_ablation_irreversible_after": soft_memory_baseline(probe, event_rows),
        "strong_matched_baseline_completed": False,
        "natural_closed_loop_completed": False,
    }
    journal = {
        "semantic_transitions": input_journal,
        "ciav_configurations": {
            key: {f.name: getattr(value, f.name) for f in fields(value) if f.name != "realizer"}
            for key, value in ciav_journal.items()
        },
        "ciav_realizer": "test fixture deterministic DIFFERENT_LOCATION; source-bound runner",
        "delayed_feedback": bundles,
    }
    (output / "semantic-input-journal.json").write_text(canonical_json(journal) + "\n")
    result["source_unchanged"] = all(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        for name, digest in files.items()
    )
    if not result["source_unchanged"]:
        raise RuntimeError("source changed during comparison")
    (output / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "traces.json").write_text(
        json.dumps([t.model_dump(mode="json") for t in stream.execution_traces()], indent=2) + "\n"
    )
    store.close()
    resumed_store.close()
    fresh_store.close()
    replay_store.close()
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    r = run(a.output, a.seed)
    print(
        json.dumps(
            {
                k: r[k]
                for k in (
                    "targets",
                    "action_changed",
                    "recovery_semantic_state_equal",
                    "fresh_inference_max_abs_difference",
                    "fresh_inference_action_equal",
                )
            },
            indent=2,
        )
    )
