"""Explicit oracle/noise development track; never natural-perception evidence.

The test-only scenario builder provides observations and hypothetical likelihoods.
Actual GroundedTransition, registered P5, posterior, ledger and checkpoint code run.
No physical actuator, empirical calibration or seven-axis neural producer is claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from structure_two_backbone_wiring_probe import (  # noqa: E402
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
    build_execution_feedback_bundle,
)

from cpswm.perception_mapping.adapters.contracts import (  # noqa: E402
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation  # noqa: E402
from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.reproducibility import content_sha256, content_uuid  # noqa: E402
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext  # noqa: E402
from cpswm.system.structure_two_continuous_input import (  # noqa: E402
    ContinuousEvidenceInput,
    GroundedTransition,
)


class OracleProducer:
    """Declared scenario injection, NOT a pixel recognizer or calibrated producer."""

    def __init__(self):
        self.output = None

    def infer(self, visible_prefix, *, cutoff):
        return self.output

    def checkpoint_state(self):
        return {"output": self.output}

    def restore_state(self, state):
        self.output = state["output"]


def source_identity():
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__).resolve(),
        ROOT / "tests/structure_two_backbone_wiring_probe.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    rows = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return content_sha256(rows), rows


def raw_for(transition, index):
    meta = transition.after.metadata
    identity = content_uuid("controlled-oracle-raw", (str(meta.trace_id), index))
    buf = io.BytesIO()
    np.save(buf, np.zeros((4, 4, 3), dtype=np.uint8), allow_pickle=False)
    payload = buf.getvalue()
    when = transition.after.detection_time
    envelope = ObservationEnvelope(
        metadata=meta.model_copy(update={"record_id": identity}),
        identity=ObservationIdentity(
            observation_id=identity,
            household_id=meta.household_id,
            session_id=meta.session_id,
            trace_id=meta.trace_id,
        ),
        sensor=SensorRef(
            sensor_id="ORACLE_PLACEHOLDER_NOT_REAL_IMAGE", modality=SensorModality.RGB
        ),
        capture_time=when,
        arrival_time=when,
        clock_domain="oracle-scenario-utc",
        frame_id=f"oracle-{index}",
        payload=PayloadRef(
            payload_id=identity,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        ),
    )
    return RawModalityObservation(
        envelope.model_dump_json(), payload, content_sha256(envelope), None
    )


def state_summary(stream):
    core = stream._system.core
    distribution = {str(k): v for k, v in stream.current_habit_location_distribution().items()}
    return {
        "distribution": distribution,
        "next_location": str(
            stream.prepare_habit_placement(
                decision_time=max(stream._last_cutoff, stream._last_arrival) + timedelta(minutes=2)
            ).location_id
        ),
        "committed": sorted(str(k) for k in core._committed_events),
        "quarantined": sorted(str(e.revision_id) for e in core._quarantined_events),
        "observed": len(core._observed_events),
        "observed_ids": sorted(str(k) for k in core._observed_events),
        "full_rerun_equivalent": core.verify_hybrid_full_rerun_equivalence().equivalent,
        "execution_traces": len(stream.execution_traces()),
    }


def run_case(output: Path, *, variant: str, source: str, days: int = 12) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    probe = BackboneWiringProbe.build(seed=7)
    producer = OracleProducer()
    dependencies = content_sha256({"python": sys.version, "numpy": np.__version__})
    store = ContinuousStateStore(
        output / "uninterrupted.db", source_identity=source, dependency_identity=dependencies
    )

    def context_builder(system, item, when, step):
        probe.system = system
        probe.step_index = step
        ciav = probe.ciav_input(
            item.transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
        )
        return AdaptiveExecutionContext(
            router_features=probe.router_features(),
            step_index=step,
            ciav_input=ciav,
        )

    transition = probe.transition_for(probe.observed_days()[0])
    meta = transition.after.metadata
    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="registered_p5_first",
        context_builder=context_builder,
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=producer,
        state_store=store,
    )
    rows = []
    for index, day in enumerate(probe.observed_days()[:days]):
        ambiguous = variant == "missing_and_ambiguous" and index in (3, 6)
        transition = probe.transition_for(
            day, evidence_filter=() if ambiguous else ("actor", "mechanism", "role")
        )
        when = transition.after.detection_time + timedelta(minutes=1)
        ids = stream.admit((raw_for(transition, index),), received_at=when)
        missing = variant == "missing_and_ambiguous" and index in (2, 5)
        before = probe.system.adaptive_router_state_sha256()
        producer.output = (
            None
            if missing
            else GroundedTransition(
                transition,
                ids,
                "EXPLICIT_ORACLE_SCENARIO_V1",
                "ASSUMED_NOT_EMPIRICALLY_CALIBRATED",
            )
        )
        receipt = stream.advance(cutoff=when)
        row = {
            "index": index,
            "injected_missing": missing,
            "injected_no_role_actor_evidence": ambiguous,
            "status": receipt.status,
            "source_ids": [str(x) for x in ids],
        }
        if receipt.result is None:
            row["core_unchanged"] = before == probe.system.adaptive_router_state_sha256()
        else:
            result = receipt.result
            primary = result.primary_result
            row.update(
                {
                    "path": result.path_selection.selected_path_id,
                    "executed_operators": result.executed_operator_count,
                    "hypotheses": len(primary.event_history.latest.hypotheses),
                    "actor_posterior": dict(primary.actor_posterior),
                    "ciav_receipt": result.ciav_receipt is not None,
                }
            )
        rows.append(row)
    before = state_summary(stream)
    target_location = before["next_location"]
    targets = [
        (rid, event)
        for rid, event in probe.system.core._committed_events.items()
        if str(event.location_id) == target_location
    ]
    bundles = [
        build_execution_feedback_bundle(
            probe,
            revision_id=rid,
            location_id=event.location_id,
            belief_snapshot_id=event.belief_snapshot_id,
            when=event.evidence.event_time,
            opportunity_id=event.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, event in targets
    ]
    # SQLite backup captures a consistent checkpoint while the first history stays live.
    with sqlite3.connect(output / "resumed.db") as destination:
        store._db.backup(destination)
    restored_store = ContinuousStateStore(
        output / "resumed.db", source_identity=source, dependency_identity=dependencies
    )
    restored = ContinuousEvidenceInput.resume(
        restored_store, producer=OracleProducer(), context_builder=context_builder
    )
    restored_before = state_summary(restored)
    revisions = []
    for candidate in (stream, restored):
        track = []
        for index, (feedback, binding, likelihood) in enumerate(bundles):
            feedback_before = candidate._system.adaptive_router_state_sha256()
            try:
                result = candidate.consume_feedback(
                    feedback=feedback,
                    binding=binding,
                    likelihood_model=likelihood,
                    received_at=when + timedelta(hours=1, seconds=index),
                    policy=CalibratedRetractionPolicy(retraction_delta=-0.2),
                )
            except KeyError as error:
                target_id = UUID(str(feedback.diagnostics["source_revision_id"]))
                eligibility = candidate._system.core.observation_write_eligibility(target_id)
                track.append(
                    {
                        "status": "REJECTED_NONCOMMITTED_TARGET",
                        "target_id": str(target_id),
                        "target_observed": target_id in candidate._system.core._observed_events,
                        "target_write_eligibility": eligibility,
                        "error": str(error),
                        "core_unchanged": feedback_before
                        == candidate._system.adaptive_router_state_sha256(),
                        "target_survives": str(feedback.diagnostics["source_revision_id"])
                        in {str(rid) for rid in candidate._system.core._committed_events},
                    }
                )
            else:
                track.append(
                    {
                        "status": "CONSUMED",
                        "operations": [str(x) for x in result.statistic_operations],
                        "presence_posterior": result.feedback_posterior_probability,
                    }
                )
        revisions.append(track)
    after, resumed_after = state_summary(stream), state_summary(restored)
    restored_store.close()
    rebuilt_store = ContinuousStateStore(
        output / "resumed.db", source_identity=source, dependency_identity=dependencies
    )
    rebuilt = ContinuousEvidenceInput.resume(
        rebuilt_store, producer=OracleProducer(), context_builder=context_builder
    )
    rebuilt._system.core._rebuild_personalized_models()
    rebuilt_state = state_summary(rebuilt)
    targets_inactive_after_rebuild = all(
        not rebuilt._system.core.observation_write_eligibility(rid)["active"] for rid, _ in targets
    )
    summary = {
        "variant": variant,
        "track": "CONTROLLED_ORACLE_NOT_NATURAL",
        "execution_lane": "registered_p5_first",
        "steps": rows,
        "before": before,
        "after": after,
        "feedback": revisions[0],
        "retraction_targets": [str(rid) for rid, _ in targets],
        "simulated_ciav_receipts": sum(bool(row.get("ciav_receipt")) for row in rows),
        "physical_executions": 0,
        "recovery_before_equal": before == restored_before,
        "recovery_after_equal": after == resumed_after,
        "recovery_feedback_equal": revisions[0] == revisions[1],
        "recovery_then_rebuild_equal": after == rebuilt_state,
        "targets_inactive_after_recovery_rebuild": bool(targets) and targets_inactive_after_rebuild,
        "all_targets_absent_from_observed": bool(targets)
        and not ({str(r) for r, _ in targets} & set(after["observed_ids"])),
        "distribution_changed": before["distribution"] != after["distribution"],
        "next_action_changed": before["next_location"] != after["next_location"],
        "all_targets_absent_from_committed": bool(targets)
        and not ({str(r) for r, _ in targets} & set(after["committed"])),
        "all_feedback_consumed": all(row["status"] == "CONSUMED" for row in revisions[0]),
        "full_neural_seven_axis_producer": False,
        "empirical_feedback_calibration": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "traces.json").write_text(
        json.dumps([t.model_dump(mode="json") for t in stream.execution_traces()], indent=2) + "\n"
    )
    store.close()
    rebuilt_store.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source, files = source_identity()
    cases = [
        run_case(args.output / variant, variant=variant, source=source)
        for variant in ("oracle_complete", "missing_and_ambiguous")
    ]
    after, _ = source_identity()
    result = {
        "source_sha256": source,
        "source_files": files,
        "source_unchanged": source == after,
        "cases": cases,
        "claim": "D0 controlled mechanism only; not natural semantic acceptance",
    }
    (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "source_unchanged": source == after,
                "cases": [
                    {
                        k: v
                        for k, v in case.items()
                        if k not in ("steps", "before", "after", "feedback", "retraction_targets")
                    }
                    for case in cases
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
