from datetime import timedelta
from pathlib import Path

from cpswm.contracts import ValidTimeInterval
from cpswm.foundation.acceptance import AlignmentHandler
from cpswm.foundation.identity_time_frames import (
    FrameTransform,
    IdentityNamespace,
    IdentityTimeFrameService,
    Vector3,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.foundation.runtime_orchestration import (
    InProcessRuntime,
    MessageKind,
    ReplayRunner,
    RuntimeMessage,
    RuntimeMessageRecord,
    build_replay_manifest,
    build_version_bundle,
    compare_replay_runs,
)


def test_step1_identity_log_orchestration_and_strict_replay(now):
    repository_root = Path(__file__).resolve().parents[1]
    configuration = {"handler": "m02.align-observation", "mode": "step1-test"}
    versions = build_version_bundle(repository_root, configuration=configuration, model_versions={})
    semantics = IdentityTimeFrameService()
    household = semantics.identities.issue(IdentityNamespace.HOUSEHOLD)
    session = semantics.identities.issue(IdentityNamespace.SESSION, household_id=household.value)
    transform = FrameTransform(
        household_id=household.value,
        source_frame_id="camera",
        target_frame_id="household_map",
        translation=Vector3(x=1.0, y=2.0, z=0.0),
        valid_time=ValidTimeInterval(start=now - timedelta(minutes=1), end=None),
        transform_version="camera-to-household@1",
    )
    message = RuntimeMessage.create(
        name="observation.align",
        kind=MessageKind.COMMAND,
        schema_version="0.1.0",
        household_id=household.value,
        session_id=session.value,
        trace_id=semantics.identities.issue(
            IdentityNamespace.TRACE, household_id=household.value
        ).value,
        idempotency_key="observation-align-1",
        sequence_no=0,
        payload={
            "source_frame_id": "camera",
            "target_frame_id": "household_map",
            "point": {"x": 0.5, "y": 0.5, "z": 1.0},
            "observed_time": now.isoformat(),
            "transform": transform.model_dump(mode="json"),
        },
        created_at=now,
    )
    input_log = AppendOnlyTransactionLog()
    input_log.append(
        [RuntimeMessageRecord.from_message(message)],
        idempotency_key="step1-input-1",
    )
    manifest = build_replay_manifest(
        input_log,
        versions=versions,
        schema_version="0.1.0",
        random_seed=7,
        created_at=now,
    )

    def build_runtime():
        runtime = InProcessRuntime(
            transaction_log=AppendOnlyTransactionLog(),
            versions=versions,
            repository_root=repository_root,
            active_configuration=configuration,
        )
        runtime.register_command(
            "observation.align",
            handler_name="m02.align-observation",
            handler=AlignmentHandler(),
        )
        return runtime

    runner = ReplayRunner()
    first = runner.run(runtime=build_runtime(), manifest=manifest, input_log=input_log)
    second = runner.run(runtime=build_runtime(), manifest=manifest, input_log=input_log)

    assert first.output_payloads[0]["point"] == {"x": 1.5, "y": 2.5, "z": 1.0}
    assert first.execution_provenance[0]["versions"]["code_version"].startswith("git:")
    assert compare_replay_runs(first, second, numeric_tolerance=0.0)
