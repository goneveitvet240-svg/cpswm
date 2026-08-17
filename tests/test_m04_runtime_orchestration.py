from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import BaseRecordMetadata, ContractModel, SourceType
from cpswm.foundation.persistence_replay import (
    AppendOnlyTransactionLog,
)
from cpswm.foundation.persistence_replay.contracts import content_hash
from cpswm.foundation.runtime_orchestration import (
    HandlerFailedError,
    HandlerOutput,
    HandlerStatus,
    InProcessRuntime,
    MessageKind,
    ReplayInputBindingError,
    ReplayRun,
    ReplayRunner,
    RetryableHandlerError,
    RetryPolicy,
    RuntimeMessage,
    RuntimeMessageRecord,
    RuntimeProvenanceError,
    VersionBundle,
    build_replay_manifest,
    build_version_bundle,
    compare_replay_runs,
)


class RuntimeOutputRecord(ContractModel):
    metadata: BaseRecordMetadata
    value: float


def versions():
    return VersionBundle(
        code_version="git:step1",
        source_tree_sha256="b" * 64,
        configuration_hash="config:test",
        model_versions={"test": "model@1"},
    )


def make_message(household_id, session_id, now, *, sequence_no=0, value=1.0):
    return RuntimeMessage.create(
        name="observation.process",
        kind=MessageKind.COMMAND,
        schema_version="0.1.0",
        household_id=household_id,
        session_id=session_id,
        trace_id=uuid4(),
        idempotency_key=f"observation-{sequence_no}",
        sequence_no=sequence_no,
        payload={"value": value},
        created_at=now,
    )


def output_record(message, context, value):
    return RuntimeOutputRecord(
        metadata=BaseRecordMetadata(
            record_id=context.deterministic_uuid("output-record"),
            schema_name="test.RuntimeOutputRecord",
            schema_version="0.1.0",
            household_id=message.household_id,
            session_id=message.session_id,
            recorded_time=context.now,
            source_type=SourceType.MODEL,
            source_id=context.handler_name,
            model_version=context.versions.model_versions["test"],
            trace_id=message.trace_id,
        ),
        value=value,
    )


def test_command_dispatch_persists_versioned_output(household_id, session_id, now):
    log = AppendOnlyTransactionLog()
    runtime = InProcessRuntime(transaction_log=log, versions=versions())

    def handler(message, context):
        return HandlerOutput(
            records=(output_record(message, context, message.payload["value"] + 1),)
        )

    runtime.register_command("observation.process", handler_name="test.increment", handler=handler)
    result = runtime.dispatch(make_message(household_id, session_id, now))

    assert result.executions[0].status == HandlerStatus.SUCCEEDED
    assert result.executions[0].versions.code_version == "git:step1"
    assert result.commits[0].watermark.global_commit_seq == 1
    assert result.commits[0].transaction.records[0].envelope.payload["value"] == 2


@pytest.mark.parametrize(
    "invalid_update",
    (
        {"value": "not-a-float"},
        {"injected_extra": "not-declared"},
    ),
    ids=("wrong-field-type", "injected-extra"),
)
def test_handler_output_record_is_fully_revalidated_before_persistence(
    household_id,
    session_id,
    now,
    invalid_update,
):
    log = AppendOnlyTransactionLog()
    runtime = InProcessRuntime(transaction_log=log, versions=versions())

    def handler(message, context):
        invalid = output_record(message, context, 1.0).model_copy(update=invalid_update)
        return HandlerOutput(records=(invalid,))

    runtime.register_command(
        "observation.process",
        handler_name="test.invalid-output-record",
        handler=handler,
    )

    with pytest.raises(HandlerFailedError):
        runtime.dispatch(make_message(household_id, session_id, now))

    assert log.latest_watermark().global_commit_seq == 0


def test_event_subscribers_run_in_deterministic_name_order(household_id, session_id, now):
    runtime = InProcessRuntime(transaction_log=AppendOnlyTransactionLog(), versions=versions())
    order = []

    def make_handler(name):
        def handler(message, context):
            order.append(name)
            return HandlerOutput()

        return handler

    runtime.subscribe_event("belief.updated", handler_name="z-last", handler=make_handler("z-last"))
    runtime.subscribe_event(
        "belief.updated", handler_name="a-first", handler=make_handler("a-first")
    )
    event = RuntimeMessage.create(
        name="belief.updated",
        kind=MessageKind.EVENT,
        schema_version="0.1.0",
        household_id=household_id,
        session_id=session_id,
        trace_id=uuid4(),
        idempotency_key="belief-1",
        sequence_no=0,
        payload={"projection": "B1"},
        created_at=now,
    )
    runtime.dispatch(event)
    assert order == ["a-first", "z-last"]


def test_retry_is_bounded_and_idempotent(household_id, session_id, now):
    log = AppendOnlyTransactionLog()
    sleeps = []
    runtime = InProcessRuntime(
        transaction_log=log,
        versions=versions(),
        sleeper=sleeps.append,
    )
    attempts = []

    def flaky(message, context):
        attempts.append(context.attempt)
        if context.attempt == 1:
            raise RetryableHandlerError("temporary")
        return HandlerOutput(records=(output_record(message, context, 4.0),))

    runtime.register_command(
        "observation.process",
        handler_name="test.flaky",
        handler=flaky,
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.1),
    )
    message = make_message(household_id, session_id, now)
    first = runtime.dispatch(message)
    repeated = runtime.dispatch(message)

    assert attempts == [1, 2]
    assert sleeps == [0.1]
    assert first.executions[0].attempts == 2
    assert repeated.executions[0].status == HandlerStatus.IDEMPOTENT_REPLAY
    assert log.latest_watermark().global_commit_seq == 1


def test_invalid_cross_household_output_is_not_committed(household_id, session_id, now):
    log = AppendOnlyTransactionLog()
    runtime = InProcessRuntime(transaction_log=log, versions=versions())

    def invalid_handler(message, context):
        record = output_record(message, context, 1.0)
        bad_metadata = record.metadata.model_copy(update={"household_id": uuid4()})
        return HandlerOutput(records=(record.model_copy(update={"metadata": bad_metadata}),))

    runtime.register_command(
        "observation.process", handler_name="test.invalid", handler=invalid_handler
    )
    with pytest.raises(HandlerFailedError):
        runtime.dispatch(make_message(household_id, session_id, now))
    assert log.latest_watermark().global_commit_seq == 0


def test_runtime_idempotency_keys_are_scoped_by_household(now):
    log = AppendOnlyTransactionLog()
    runtime = InProcessRuntime(transaction_log=log, versions=versions())

    def handler(message, context):
        return HandlerOutput(records=(output_record(message, context, 1.0),))

    runtime.register_command(
        "observation.process", handler_name="test.household-scope", handler=handler
    )
    runtime.dispatch(make_message(uuid4(), uuid4(), now))
    runtime.dispatch(make_message(uuid4(), uuid4(), now))
    assert log.latest_watermark().global_commit_seq == 2


def test_emitted_message_identity_and_order_are_deterministic(household_id, session_id, now):
    incoming = make_message(household_id, session_id, now)

    def build_runtime():
        runtime = InProcessRuntime(
            transaction_log=AppendOnlyTransactionLog(),
            versions=versions(),
            clock=lambda: now,
        )

        def handler(message, context):
            emissions = tuple(
                RuntimeMessage.create(
                    name=f"observation.emitted-{ordinal}",
                    kind=MessageKind.EVENT,
                    schema_version=message.schema_version,
                    household_id=message.household_id,
                    session_id=message.session_id,
                    trace_id=message.trace_id,
                    causation_id=message.message_id,
                    idempotency_key=f"emitted-{ordinal}",
                    sequence_no=ordinal,
                    payload={"ordinal": ordinal},
                )
                for ordinal in range(2)
            )
            return HandlerOutput(emitted_messages=emissions)

        runtime.register_command(
            "observation.process",
            handler_name="test.deterministic-emissions",
            handler=handler,
        )
        return runtime

    first = build_runtime().dispatch(incoming).emitted_messages
    second = build_runtime().dispatch(incoming).emitted_messages

    assert tuple(item.message_id for item in first) == tuple(item.message_id for item in second)
    assert tuple(item.created_at for item in first) == (now, now)
    assert tuple(item.fingerprint for item in first) == tuple(item.fingerprint for item in second)

    empty_log = AppendOnlyTransactionLog()
    common = {
        "manifest_fingerprint": "a" * 64,
        "manifest_numeric_tolerance": 0.0,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": (),
        "output_payloads": (),
        "output_fingerprints": (),
        "execution_provenance": (),
    }
    first_run = ReplayRun(
        **common,
        emitted_message_fingerprints=tuple(item.fingerprint for item in first),
    )
    reordered_run = ReplayRun(
        **common,
        emitted_message_fingerprints=tuple(item.fingerprint for item in reversed(second)),
    )
    changed_identity = second[0].model_copy(update={"message_id": uuid4()})
    changed_identity_run = ReplayRun(
        **common,
        emitted_message_fingerprints=(
            changed_identity.fingerprint,
            second[1].fingerprint,
        ),
    )

    assert not compare_replay_runs(first_run, reordered_run, numeric_tolerance=0.0)
    assert not compare_replay_runs(first_run, changed_identity_run, numeric_tolerance=0.0)


def test_emitted_message_cannot_cross_session_boundary(household_id, session_id, now):
    runtime = InProcessRuntime(transaction_log=AppendOnlyTransactionLog(), versions=versions())

    def handler(message, context):
        emitted = RuntimeMessage.create(
            name="observation.emitted",
            kind=MessageKind.EVENT,
            schema_version=message.schema_version,
            household_id=message.household_id,
            session_id=uuid4(),
            trace_id=message.trace_id,
            causation_id=message.message_id,
            idempotency_key="cross-session-emission",
            sequence_no=0,
            payload={"status": "invalid"},
        )
        return HandlerOutput(emitted_messages=(emitted,))

    runtime.register_command(
        "observation.process",
        handler_name="test.cross-session-emission",
        handler=handler,
    )

    with pytest.raises(HandlerFailedError) as exc_info:
        runtime.dispatch(make_message(household_id, session_id, now))

    assert exc_info.value.execution.error_type == "ValueError"
    assert exc_info.value.execution.error_message == ("emitted messages must preserve session_id")


@pytest.mark.parametrize(
    ("invalid_update", "expected_error_type"),
    (
        ({"payload": {"status": "tampered"}}, "ValidationError"),
        ({"name": ""}, "ValidationError"),
        ({"schema_version": "invalid"}, "ValidationError"),
        ({"sequence_no": -1}, "ValidationError"),
        ({"kind": "invalid-kind"}, "ValidationError"),
        ({"injected_extra": "not-declared"}, "ValueError"),
    ),
    ids=(
        "stale-payload-hash",
        "empty-name",
        "invalid-schema-version",
        "negative-sequence",
        "invalid-kind",
        "injected-extra",
    ),
)
def test_emitted_message_is_fully_revalidated_at_runtime_boundary(
    household_id,
    session_id,
    now,
    invalid_update,
    expected_error_type,
):
    runtime = InProcessRuntime(transaction_log=AppendOnlyTransactionLog(), versions=versions())

    def handler(message, context):
        valid = RuntimeMessage.create(
            name="observation.emitted",
            kind=MessageKind.EVENT,
            schema_version=message.schema_version,
            household_id=message.household_id,
            session_id=message.session_id,
            trace_id=message.trace_id,
            causation_id=message.message_id,
            idempotency_key="invalid-contract-emission",
            sequence_no=0,
            payload={"status": "valid"},
        )
        return HandlerOutput(emitted_messages=(valid.model_copy(update=invalid_update),))

    runtime.register_command(
        "observation.process",
        handler_name="test.invalid-emitted-contract",
        handler=handler,
    )

    with pytest.raises(HandlerFailedError) as exc_info:
        runtime.dispatch(make_message(household_id, session_id, now))

    assert exc_info.value.execution.status == HandlerStatus.FAILED
    assert exc_info.value.execution.error_type == expected_error_type
    assert runtime.transaction_log.latest_watermark().global_commit_seq == 0


def test_valid_emitted_message_is_round_trip_valid_after_normalization(
    household_id, session_id, now
):
    runtime = InProcessRuntime(
        transaction_log=AppendOnlyTransactionLog(),
        versions=versions(),
        clock=lambda: now,
    )

    def handler(message, context):
        emitted = RuntimeMessage.create(
            name="observation.emitted",
            kind=MessageKind.EVENT,
            schema_version=message.schema_version,
            household_id=message.household_id,
            session_id=message.session_id,
            trace_id=message.trace_id,
            causation_id=message.message_id,
            idempotency_key="valid-contract-emission",
            sequence_no=0,
            payload={"status": "valid"},
        )
        return HandlerOutput(emitted_messages=(emitted,))

    runtime.register_command(
        "observation.process",
        handler_name="test.valid-emitted-contract",
        handler=handler,
    )
    message = make_message(household_id, session_id, now)
    emitted = runtime.dispatch(message).emitted_messages[0]

    round_tripped = RuntimeMessage.model_validate(emitted.model_dump(mode="python"))
    assert round_tripped == emitted
    assert emitted.created_at == now
    replayed_emission = runtime.dispatch(message).emitted_messages[0]
    assert emitted.message_id == replayed_emission.message_id


@pytest.mark.parametrize(
    "invalid_update",
    (
        {"payload": {"status": "tampered"}},
        {"name": ""},
        {"schema_version": "invalid"},
        {"sequence_no": -1},
        {"kind": "invalid-kind"},
        {"injected_extra": "not-declared"},
    ),
    ids=(
        "stale-payload-hash",
        "empty-name",
        "invalid-schema-version",
        "negative-sequence",
        "invalid-kind",
        "injected-extra",
    ),
)
def test_incoming_message_is_fully_revalidated_before_dispatch(
    household_id,
    session_id,
    now,
    invalid_update,
):
    runtime = InProcessRuntime(transaction_log=AppendOnlyTransactionLog(), versions=versions())
    handler_called = False

    def handler(message, context):
        nonlocal handler_called
        handler_called = True
        return HandlerOutput()

    runtime.register_command(
        "observation.process",
        handler_name="test.input-contract-boundary",
        handler=handler,
    )
    invalid = make_message(household_id, session_id, now).model_copy(update=invalid_update)

    with pytest.raises((ValueError, TypeError)):
        runtime.dispatch(invalid)

    assert not handler_called
    assert runtime.transaction_log.latest_watermark().global_commit_seq == 0
    assert runtime.execution_journal == []


def test_replay_is_deterministic_across_fresh_runtimes(household_id, session_id, now):
    repository_root = Path(__file__).resolve().parents[1]
    configuration = {"mode": "test", "handler": "test.seeded"}
    replay_versions = build_version_bundle(
        repository_root,
        configuration=configuration,
        model_versions={"test": "model@1"},
    )
    message = make_message(household_id, session_id, now, value=3.0)
    input_log = AppendOnlyTransactionLog()
    input_log.append([RuntimeMessageRecord.from_message(message)], idempotency_key="replay-input")
    manifest = build_replay_manifest(
        input_log,
        schema_version="0.1.0",
        versions=replay_versions,
        random_seed=123,
        created_at=now,
    )

    def build_runtime(wall_clock):
        runtime = InProcessRuntime(
            transaction_log=AppendOnlyTransactionLog(),
            versions=replay_versions,
            repository_root=repository_root,
            active_configuration=configuration,
            clock=lambda: wall_clock,
        )

        def stochastic_handler(incoming, context):
            value = incoming.payload["value"] + context.random.random()
            return HandlerOutput(records=(output_record(incoming, context, value),))

        runtime.register_command(
            "observation.process",
            handler_name="test.seeded",
            handler=stochastic_handler,
        )
        return runtime

    runner = ReplayRunner()
    first_runtime = build_runtime(now + timedelta(days=1))
    second_runtime = build_runtime(now + timedelta(days=2))
    first = runner.run(runtime=first_runtime, manifest=manifest, input_log=input_log)
    second = runner.run(runtime=second_runtime, manifest=manifest, input_log=input_log)

    first_commit = first_runtime.transaction_log.read()[0]
    second_commit = second_runtime.transaction_log.read()[0]
    assert first_commit.committed_at == manifest.created_at
    assert second_commit.committed_at == manifest.created_at
    assert first_commit.records[0].committed_at == manifest.created_at
    assert first_runtime.transaction_log.fingerprint() == (
        second_runtime.transaction_log.fingerprint()
    )
    assert first.execution_provenance[0]["output_watermark"] == (
        first_runtime.transaction_log.latest_watermark().model_dump(mode="json")
    )
    assert first.output_fingerprints == second.output_fingerprints
    assert compare_replay_runs(first, second, numeric_tolerance=0.0)


@pytest.mark.parametrize(
    "manifest_update",
    (
        {"numeric_tolerance": -1.0},
        {"numeric_tolerance": float("inf")},
        {"injected_extra": "not-declared"},
    ),
    ids=(
        "negative-declared-tolerance",
        "non-finite-declared-tolerance",
        "injected-extra-field",
    ),
)
def test_replay_runner_revalidates_manifest_model_copy_bypass(
    household_id, session_id, now, manifest_update
):
    repository_root = Path(__file__).resolve().parents[1]
    configuration = {"mode": "manifest-boundary"}
    replay_versions = build_version_bundle(
        repository_root,
        configuration=configuration,
        model_versions={"test": "model@1"},
    )
    input_log = AppendOnlyTransactionLog()
    input_log.append(
        [RuntimeMessageRecord.from_message(make_message(household_id, session_id, now))],
        idempotency_key="manifest-boundary-input",
    )
    valid_manifest = build_replay_manifest(
        input_log,
        schema_version="0.1.0",
        versions=replay_versions,
        random_seed=17,
        created_at=now,
    )
    forged_manifest = valid_manifest.model_copy(update=manifest_update)
    runtime = InProcessRuntime(
        transaction_log=AppendOnlyTransactionLog(),
        versions=replay_versions,
        repository_root=repository_root,
        active_configuration=configuration,
    )
    runtime.register_command(
        "observation.process",
        handler_name="test.manifest-boundary",
        handler=lambda message, context: HandlerOutput(
            records=(output_record(message, context, 1.0),)
        ),
    )

    with pytest.raises(ReplayInputBindingError, match="invalid ReplayManifest"):
        ReplayRunner().run(
            runtime=runtime,
            manifest=forged_manifest,
            input_log=input_log,
        )

    assert runtime.transaction_log.latest_watermark().global_commit_seq == 0


def test_replay_comparison_detects_changed_output_log_time(household_id, session_id, now):
    repository_root = Path(__file__).resolve().parents[1]
    configuration = {"mode": "time-binding", "handler": "test.time-binding"}
    replay_versions = build_version_bundle(
        repository_root,
        configuration=configuration,
        model_versions={"test": "model@1"},
    )
    input_log = AppendOnlyTransactionLog()
    input_log.append(
        [RuntimeMessageRecord.from_message(make_message(household_id, session_id, now))],
        idempotency_key="time-binding-input",
    )
    manifest = build_replay_manifest(
        input_log,
        schema_version="0.1.0",
        versions=replay_versions,
        random_seed=7,
        created_at=now,
    )
    runtime = InProcessRuntime(
        transaction_log=AppendOnlyTransactionLog(),
        versions=replay_versions,
        repository_root=repository_root,
        active_configuration=configuration,
    )
    runtime.register_command(
        "observation.process",
        handler_name="test.time-binding",
        handler=lambda message, context: HandlerOutput(
            records=(output_record(message, context, 1.0),)
        ),
    )
    original = ReplayRunner().run(
        runtime=runtime,
        manifest=manifest,
        input_log=input_log,
    )
    provenance = original.execution_provenance[0]
    watermark = provenance["output_watermark"]
    changed_watermark = {
        **watermark,
        "recorded_at": (now + timedelta(seconds=1)).isoformat(),
    }
    changed = original.model_copy(
        update={"execution_provenance": ({**provenance, "output_watermark": changed_watermark},)}
    )

    assert not compare_replay_runs(original, changed, numeric_tolerance=0.0)


def test_replay_comparison_supports_declared_numeric_tolerance():
    empty_log = AppendOnlyTransactionLog()
    common = {
        "manifest_fingerprint": "a" * 64,
        "manifest_numeric_tolerance": 1e-6,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": ("input",),
        "emitted_message_fingerprints": (),
        "execution_provenance": (),
    }
    first = ReplayRun(
        **common,
        output_payloads=({"probability": 0.5000001},),
        output_fingerprints=(content_hash({"probability": 0.5000001}),),
    )
    second = ReplayRun(
        **common,
        output_payloads=({"probability": 0.5000002},),
        output_fingerprints=(content_hash({"probability": 0.5000002}),),
    )
    assert compare_replay_runs(first, second, numeric_tolerance=1e-6)
    assert not compare_replay_runs(first, second, numeric_tolerance=1e-9)
    assert compare_replay_runs(first, second)


def test_replay_comparison_cannot_widen_manifest_numeric_tolerance():
    empty_log = AppendOnlyTransactionLog()
    common = {
        "manifest_fingerprint": "a" * 64,
        "manifest_numeric_tolerance": 0.0,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": ("input",),
        "emitted_message_fingerprints": (),
        "execution_provenance": (),
    }
    left_payload = {"probability": 0.0}
    right_payload = {"probability": 0.75}
    first = ReplayRun(
        **common,
        output_payloads=(left_payload,),
        output_fingerprints=(content_hash(left_payload),),
    )
    second = ReplayRun(
        **common,
        output_payloads=(right_payload,),
        output_fingerprints=(content_hash(right_payload),),
    )

    assert not compare_replay_runs(first, second)
    with pytest.raises(ValueError, match="cannot exceed"):
        compare_replay_runs(first, second, numeric_tolerance=1.0)


@pytest.mark.parametrize("numeric_tolerance", (float("inf"), float("nan")))
def test_replay_comparison_rejects_non_finite_numeric_tolerance(
    numeric_tolerance,
):
    empty_log = AppendOnlyTransactionLog()
    payload = {"value": 1.0}
    run = ReplayRun(
        manifest_fingerprint="a" * 64,
        manifest_numeric_tolerance=1.0,
        input_log_sha256=empty_log.fingerprint(),
        input_watermark=empty_log.latest_watermark(),
        input_fingerprints=(),
        output_payloads=(payload,),
        output_fingerprints=(content_hash(payload),),
        emitted_message_fingerprints=(),
        execution_provenance=(),
    )

    with pytest.raises(ValueError, match="finite and non-negative"):
        compare_replay_runs(
            run,
            run,
            numeric_tolerance=numeric_tolerance,
        )


def test_replay_comparison_rejects_mismatched_manifest_tolerances():
    empty_log = AppendOnlyTransactionLog()
    payload = {"value": 1.0}
    common = {
        "manifest_fingerprint": "a" * 64,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": (),
        "output_payloads": (payload,),
        "output_fingerprints": (content_hash(payload),),
        "emitted_message_fingerprints": (),
        "execution_provenance": (),
    }
    first = ReplayRun(**common, manifest_numeric_tolerance=0.0)
    second = ReplayRun(**common, manifest_numeric_tolerance=1.0)

    assert not compare_replay_runs(first, second)


@pytest.mark.parametrize(
    ("payloads", "fingerprints", "message"),
    (
        (({"value": 1.0},), (), "equal length"),
        (({"value": 1.0},), ("0" * 64,), "does not match"),
    ),
    ids=("length-mismatch", "stale-fingerprint"),
)
def test_replay_run_rejects_unbound_output_fingerprints(payloads, fingerprints, message):
    empty_log = AppendOnlyTransactionLog()

    with pytest.raises(ValidationError, match=message):
        ReplayRun(
            manifest_fingerprint="a" * 64,
            manifest_numeric_tolerance=0.0,
            input_log_sha256=empty_log.fingerprint(),
            input_watermark=empty_log.latest_watermark(),
            input_fingerprints=(),
            output_payloads=payloads,
            output_fingerprints=fingerprints,
            emitted_message_fingerprints=(),
            execution_provenance=(),
        )


def test_replay_comparison_revalidates_model_copy_bypass():
    empty_log = AppendOnlyTransactionLog()
    payload = {"value": 1.0}
    valid = ReplayRun(
        manifest_fingerprint="a" * 64,
        manifest_numeric_tolerance=1.0,
        input_log_sha256=empty_log.fingerprint(),
        input_watermark=empty_log.latest_watermark(),
        input_fingerprints=(),
        output_payloads=(payload,),
        output_fingerprints=(content_hash(payload),),
        emitted_message_fingerprints=(),
        execution_provenance=(),
    )
    stale_hash = valid.model_copy(update={"output_fingerprints": ("0" * 64,)})
    truncated_hashes = valid.model_copy(update={"output_fingerprints": ()})
    injected_extra = valid.model_copy(update={"injected_extra": "not-declared"})

    assert not compare_replay_runs(valid, stale_hash, numeric_tolerance=0.0)
    assert not compare_replay_runs(valid, stale_hash, numeric_tolerance=1.0)
    assert not compare_replay_runs(valid, truncated_hashes, numeric_tolerance=0.0)
    assert not compare_replay_runs(valid, injected_extra, numeric_tolerance=0.0)


def test_zero_tolerance_compares_self_consistent_canonical_output_hashes():
    empty_log = AppendOnlyTransactionLog()
    negative_zero = {"value": -0.0}
    positive_zero = {"value": 0.0}
    common = {
        "manifest_fingerprint": "a" * 64,
        "manifest_numeric_tolerance": 1e-12,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": (),
        "emitted_message_fingerprints": (),
        "execution_provenance": (),
    }
    first = ReplayRun(
        **common,
        output_payloads=(negative_zero,),
        output_fingerprints=(content_hash(negative_zero),),
    )
    second = ReplayRun(
        **common,
        output_payloads=(positive_zero,),
        output_fingerprints=(content_hash(positive_zero),),
    )

    assert negative_zero == positive_zero
    assert first.output_fingerprints != second.output_fingerprints
    assert not compare_replay_runs(first, second, numeric_tolerance=0.0)
    assert compare_replay_runs(first, second, numeric_tolerance=1e-12)


def test_zero_tolerance_compares_large_integers_exactly():
    empty_log = AppendOnlyTransactionLog()
    common = {
        "manifest_fingerprint": "a" * 64,
        "manifest_numeric_tolerance": 0.0,
        "input_log_sha256": empty_log.fingerprint(),
        "input_watermark": empty_log.latest_watermark(),
        "input_fingerprints": (),
        "emitted_message_fingerprints": (),
        "execution_provenance": (),
    }
    first = ReplayRun(
        **common,
        output_payloads=({"counter": 9007199254740992},),
        output_fingerprints=(content_hash({"counter": 9007199254740992}),),
    )
    second = ReplayRun(
        **common,
        output_payloads=({"counter": 9007199254740993},),
        output_fingerprints=(content_hash({"counter": 9007199254740993}),),
    )
    assert not compare_replay_runs(first, second, numeric_tolerance=0.0)


def test_replay_rejects_manifest_runtime_and_input_mismatches(household_id, session_id, now):
    repository_root = Path(__file__).resolve().parents[1]
    configuration = {"mode": "binding-test"}
    replay_versions = build_version_bundle(
        repository_root,
        configuration=configuration,
        model_versions={"test": "model@1"},
    )
    message = make_message(household_id, session_id, now)
    input_log = AppendOnlyTransactionLog()
    input_log.append([RuntimeMessageRecord.from_message(message)], idempotency_key="binding-input")
    manifest = build_replay_manifest(
        input_log,
        versions=replay_versions,
        schema_version="0.1.0",
        random_seed=1,
        created_at=now,
    )

    def runtime():
        instance = InProcessRuntime(
            transaction_log=AppendOnlyTransactionLog(),
            versions=replay_versions,
            repository_root=repository_root,
            active_configuration=configuration,
        )
        instance.register_command(
            "observation.process",
            handler_name="test.binding",
            handler=lambda incoming, context: HandlerOutput(
                records=(output_record(incoming, context, 1.0),)
            ),
        )
        return instance

    runner = ReplayRunner()
    bad_code = manifest.model_copy(update={"code_version": "git:" + "0" * 40})
    with pytest.raises(RuntimeProvenanceError, match="code_version"):
        runner.run(runtime=runtime(), manifest=bad_code, input_log=input_log)

    bad_source = manifest.model_copy(update={"source_tree_sha256": "0" * 64})
    with pytest.raises(RuntimeProvenanceError, match="source_tree_sha256"):
        runner.run(runtime=runtime(), manifest=bad_source, input_log=input_log)

    bad_config = manifest.model_copy(update={"configuration_hash": "wrong"})
    with pytest.raises(RuntimeProvenanceError, match="configuration_hash"):
        runner.run(runtime=runtime(), manifest=bad_config, input_log=input_log)

    bad_models = manifest.model_copy(update={"model_versions": {"test": "wrong"}})
    with pytest.raises(RuntimeProvenanceError, match="model_versions"):
        runner.run(runtime=runtime(), manifest=bad_models, input_log=input_log)

    fake_watermark = manifest.input_watermark.model_copy(update={"global_commit_seq": 999})
    bad_watermark = manifest.model_copy(update={"input_watermark": fake_watermark})
    with pytest.raises(ReplayInputBindingError, match="absent"):
        runner.run(runtime=runtime(), manifest=bad_watermark, input_log=input_log)

    bad_log_hash = manifest.model_copy(update={"input_log_sha256": "0" * 64})
    with pytest.raises(ReplayInputBindingError, match="input_log_sha256"):
        runner.run(runtime=runtime(), manifest=bad_log_hash, input_log=input_log)
