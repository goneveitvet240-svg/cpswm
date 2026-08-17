from datetime import timedelta

# Legacy duplicate retained for audit only.  The maintained integration test is
# tests/test_step1_a0_integration.py.
__test__ = False

from cpswm.contracts import (
    BaseRecordMetadata,
    ContractModel,
    SourceType,
    ValidTimeInterval,
)
from cpswm.foundation.identity_time_frames import (
    FrameTransform,
    IdentityNamespace,
    IdentityTimeFrameService,
    Vector3,
)
from cpswm.foundation.persistence_replay import (
    AppendOnlyTransactionLog,
    ExecutionMode,
    ReplayManifest,
)
from cpswm.foundation.runtime_orchestration import (
    HandlerOutput,
    InProcessRuntime,
    MessageKind,
    ReplayRunner,
    RuntimeMessage,
    VersionBundle,
    compare_replay_runs,
)


class AlignedObservation(ContractModel):
    metadata: BaseRecordMetadata
    source_frame_id: str
    target_frame_id: str
    point: Vector3
    transform_version: str


def test_step1_identity_frame_commit_orchestration_and_replay(now):
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
    semantics.frames.register(transform)

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
        },
        created_at=now,
    )
    versions = VersionBundle(
        code_version="step1-a0@1",
        configuration_hash="integration-config",
        model_versions={},
    )
    manifest = ReplayManifest(
        input_watermark=AppendOnlyTransactionLog().latest_watermark(),
        schema_version="0.1.0",
        code_version=versions.code_version,
        model_versions={},
        configuration_hash=versions.configuration_hash,
        random_seed=7,
        execution_mode=ExecutionMode.REPLAY,
        created_at=now,
    )

    def build_runtime():
        runtime = InProcessRuntime(transaction_log=AppendOnlyTransactionLog(), versions=versions)

        def align_observation(incoming, context):
            payload = incoming.payload
            resolved = semantics.frames.lookup(
                source_frame_id=payload["source_frame_id"],
                target_frame_id=payload["target_frame_id"],
                household_id=incoming.household_id,
                at_time=now,
            )
            aligned = semantics.frames.transform_point(Vector3(**payload["point"]), resolved)
            record = AlignedObservation(
                metadata=BaseRecordMetadata(
                    record_id=context.deterministic_uuid("aligned-observation"),
                    schema_name="cpswm.AlignedObservation",
                    schema_version="0.1.0",
                    household_id=incoming.household_id,
                    session_id=incoming.session_id,
                    recorded_time=context.now,
                    source_type=SourceType.MODEL,
                    source_id=context.handler_name,
                    trace_id=incoming.trace_id,
                ),
                source_frame_id=payload["source_frame_id"],
                target_frame_id=payload["target_frame_id"],
                point=aligned,
                transform_version=resolved.transform_version,
            )
            return HandlerOutput(records=(record,))

        runtime.register_command(
            "observation.align",
            handler_name="m02.align-observation",
            handler=align_observation,
        )
        return runtime

    runner = ReplayRunner()
    first = runner.run(runtime=build_runtime(), manifest=manifest, messages=[message])
    second = runner.run(runtime=build_runtime(), manifest=manifest, messages=[message])

    assert first.output_payloads[0]["point"] == {"x": 1.5, "y": 2.5, "z": 1.0}
    assert compare_replay_runs(first, second, numeric_tolerance=0.0)
