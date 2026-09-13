"""Live sensor/action/recovery probe; no calibrated person-role acceptance.

A single Unity process survives runtime close/resume. A fixed bounded scan probes
the transport while retaining visual readout reasons.
This is not a calibrated P5 action policy.
P5 with semantic writes is separately gated on a calibrated semantic producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cpswm.perception_mapping.natural_vision import (
    NaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationCommand
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem
from cpswm.system.unity_observation import UnityObservationExecutor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-python", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    source = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "src").rglob("*.py"))
    }
    for p in (Path(__file__), root / "tools/unity_observation_worker.py"):
        source[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    source_id = content_sha256(source)
    dependency_id = content_sha256(
        {
            "lock": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
            "weights": hashlib.sha256(args.weights.read_bytes()).hexdigest(),
            "binary": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
            "sdk_python": str(args.sdk_python.resolve()),
        }
    )
    household, session, trace = uuid4(), uuid4(), uuid4()
    scope = dict(household_id=household, session_id=session, trace_id=trace)

    def producer():
        return NaturalVisionEvidenceProducer(
            NaturalAppearanceDetector(weights_path=args.weights, **scope)
        )

    backend = producer()
    system = StructureTwoProductionSystem(
        owner_key="unresolved-visual-observer",
        object_instance_id=uuid4(),
        locations=(uuid4(), uuid4()),
        authorization_scope_id=uuid4(),
    )
    path = args.output / "state.sqlite"

    def open_store():
        return ContinuousStateStore(
            path, source_identity=source_id, dependency_identity=dependency_id
        )

    store = open_store()
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="legacy_component_diagnostic",
        producer=backend,
        state_store=store,
        **scope,
    )
    executor = UnityObservationExecutor(
        python=args.sdk_python,
        worker=root / "tools/unity_observation_worker.py",
        binary=args.binary,
        house=root
        / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json",
        log_dir=args.output / "unity_logs",
        **scope,
    )
    rows = []
    try:
        # Initial acquisition precedes the model's first evidence-grounded request.
        initial = executor.execute(
            ObservationCommand(
                uuid4(),
                system.core.current_snapshot.snapshot_id,
                "Pass",
                0,
                "initial acquisition",
                (),
                datetime.now(UTC),
            )
        )
        stream.admit(initial.observations, received_at=initial.received_at)
        stream.advance(cutoff=initial.received_at)
        last = initial
        for step in range(2):
            readout = backend.interactions()[-1][1]
            command = stream.prepare_observation(
                action="RotateRight",
                degrees=90,
                reason="development_scan; unresolved=" + readout.next_observation_request,
                source_ids=(readout.observation_id,),
                decision_time=datetime.now(UTC),
            )
            delivery = stream.execute_observation(command, executor=executor)
            stream.advance(cutoff=delivery.received_at)
            old_hash = last.observations[0].envelope().payload.payload_sha256
            new_hash = delivery.observations[0].envelope().payload.payload_sha256
            rows.append(
                {
                    "step": step,
                    "action_id": str(command.action_id),
                    "success": delivery.success,
                    "reason": command.reason,
                    "pixel_changed": new_hash != old_hash,
                    "source_ids": [str(x) for x in command.source_ids],
                    "result_observation": str(
                        delivery.observations[0].envelope().identity.observation_id
                    ),
                }
            )
            last = delivery
            if step == 0:
                core_hash = stream._system.adaptive_router_state_sha256()
                store.close()
                store = open_store()
                backend = producer()
                stream = ContinuousEvidenceInput.resume(store, producer=backend)
                assert stream._system.adaptive_router_state_sha256() == core_hash
                assert len(backend.frames()) == 2
        result = {
            "scope": "live Unity camera actions and runtime recovery; no person-role acceptance",
            "source_identity": source_id,
            "dependencies": dependency_id,
            "actions": rows,
            "observations": len(backend.frames()),
            "interaction_frames": len(backend.interactions()),
            "semantic_transitions": len(stream.execution_traces()),
            "recovered_during_same_environment_session": True,
            "complete_sensor_action_probe": all(r["success"] and r["pixel_changed"] for r in rows),
        }
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        executor.close()
        store.close()


if __name__ == "__main__":
    main()
