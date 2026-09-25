"""Explicit prepared-model fixture -> native collector -> live Unity rotation.

This is a mixed controlled-model/live-transport integration probe. The model's
outcome likelihoods, roles and six-dimensional pose observations are test
fixtures, not fitted visual predictions. No natural semantic success is claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_continuous_camera_collection import Model  # noqa: E402
from test_continuous_state_recovery import DurableFixtureProducer  # noqa: E402
from test_native_joint_production import JointFixture  # noqa: E402
from test_structure_two_adaptive_runtime import (  # noqa: E402
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for  # noqa: E402

from cpswm.system.continuous_camera_collection import collect_posterior_step  # noqa: E402
from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext  # noqa: E402
from cpswm.system.structure_two_continuous_input import (  # noqa: E402
    ContinuousEvidenceInput,
    GroundedTransition,
    ObservationCommand,
)
from cpswm.system.unity_observation import UnityObservationExecutor  # noqa: E402


def run(output, sdk_python, binary):
    output.mkdir(parents=True, exist_ok=False)
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        *sorted((ROOT / "tests").rglob("*.py")),
        Path(__file__).resolve(),
        ROOT / "tools/unity_observation_worker.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    source = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source_id = content_sha256(source)
    house = (
        ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    dependencies = {
        "python": sys.version,
        "sdk_python": str(sdk_python.resolve()),
        "sdk_python_sha256": hashlib.sha256(sdk_python.resolve().read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "house_sha256": hashlib.sha256(house.read_bytes()).hexdigest(),
        "joint_model_binding": JointFixture.binding_sha256,
    }
    dependency_id = content_sha256(dependencies)
    path = output / "state.sqlite"

    def open_store():
        return ContinuousStateStore(
            path, source_identity=source_id, dependency_identity=dependency_id
        )

    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    meta = transition.after.metadata
    scope = dict(household_id=meta.household_id, session_id=meta.session_id, trace_id=meta.trace_id)
    producer, joint, store = DurableFixtureProducer(), JointFixture(), open_store()
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        producer=producer,
        context_builder=builder,
        state_store=store,
        joint_producer=joint,
        **scope,
    )
    ids = stream.admit((raw_for(transition),), received_at=ciav.opportunity_time)
    producer.output = GroundedTransition(
        transition, ids, "CONTROLLED_TEST_FIXTURE", "ASSUMED_NOT_CALIBRATED"
    )
    stream.advance(cutoff=ciav.opportunity_time)
    executor = None
    try:
        executor = UnityObservationExecutor(
            python=sdk_python,
            worker=ROOT / "tools/unity_observation_worker.py",
            binary=binary,
            house=house,
            log_dir=output / "unity-logs",
            **scope,
        )
        initial = executor.execute(
            ObservationCommand(
                uuid4(),
                system.core.current_snapshot.snapshot_id,
                "Pass",
                0,
                "initial live acquisition",
                (),
                datetime.now(UTC),
            )
        )
        stream.admit(initial.observations, received_at=initial.received_at)
        stream.advance(cutoff=initial.received_at)
        stream.produce_joint_posterior()
        view = stream.current_joint_decision_view()
        model = Model(stream)
        when = datetime.now(UTC)
        problem = model.problem(view, stream.visible_prefix(cutoff=when), decision_time=when)
        plan, command = stream.prepare_posterior_observation(problem, decision_time=when)
        if command is None:
            raise RuntimeError("configured diagnostic did not select a camera action")
        # Recover the exact saved READY command while keeping the same Unity process.
        store.close()
        store = open_store()
        producer = DurableFixtureProducer()
        joint = JointFixture()
        stream = ContinuousEvidenceInput.resume(
            store, producer=producer, context_builder=builder, joint_producer=joint
        )
        assert stream.current_joint_decision_view() == view
        model = Model(stream)
        result = collect_posterior_step(
            stream, model=model, executor=executor, decision_time=datetime.now(UTC)
        )
        assert result.command is not None and result.delivery is not None
        assert result.recovered_ready_command and result.command.action_id == command.action_id
        assert joint.calls == 1 and model.calls == 0
        for label, delivery in (("initial", initial), ("selected", result.delivery)):
            for i, raw in enumerate(delivery.observations):
                (output / f"{label}-{i}.npy").write_bytes(raw.payload_bytes)
                (output / f"{label}-{i}.envelope.json").write_text(raw.envelope_json)
        old = initial.observations[0].envelope().payload.payload_sha256
        new = result.delivery.observations[0].envelope().payload.payload_sha256
        report = {
            "track": "CONTROLLED_PREPARED_MODEL_LIVE_UNITY_TRANSPORT",
            "source_sha256": source_id,
            "source_files": source,
            "dependencies": dependencies,
            "joint_producer_calls_after_resume": joint.calls,
            "joint_atoms": len(view.atoms),
            "joint_dimension": len(view.atoms[0].statistics.information_vector),
            "selected_action": command.action,
            "degrees": command.degrees,
            "action_id": str(command.action_id),
            "same_ready_command_after_resume": True,
            "success": result.delivery.success,
            "error": result.delivery.error,
            "pixels_changed": new != old,
            "input_pixel_sha256": old,
            "result_pixel_sha256": new,
            "visible_observations": len(stream.visible_prefix(cutoff=result.delivery.received_at)),
            "command_reason": command.reason,
            "plan": plan.model_dump(mode="json"),
            "natural_semantic_transitions": 0,
            "empirical_model_calibration": False,
            "selected_neural_kernel_bound": False,
            "complete_natural_closed_loop": False,
            "source_unchanged": all(
                hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h for n, h in source.items()
            ),
        }
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        if not report["source_unchanged"] or not report["success"] or not report["pixels_changed"]:
            raise RuntimeError("live transport/source invariant failed; inspect result.json")
        return report
    finally:
        if executor is not None:
            executor.close()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-python", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    r = run(args.output, args.sdk_python, args.binary)
    print(
        json.dumps(
            {
                k: r[k]
                for k in (
                    "selected_action",
                    "success",
                    "pixels_changed",
                    "same_ready_command_after_resume",
                    "source_unchanged",
                )
            },
            indent=2,
        )
    )
