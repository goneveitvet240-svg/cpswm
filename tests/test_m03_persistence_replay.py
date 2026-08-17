from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import BaseRecordMetadata, ContractModel, SourceType
from cpswm.foundation.persistence_replay import (
    AppendOnlyTransactionLog,
    DataPlane,
    ExecutionMode,
    IdempotencyConflictError,
    RecordAlreadyCommittedError,
    ReplayManifest,
    SnapshotCatalog,
    SnapshotManifest,
    StoreCatalog,
    StorePartition,
)
from cpswm.foundation.persistence_replay.contracts import content_hash


class SampleRecord(ContractModel):
    metadata: BaseRecordMetadata
    value: float


def make_record(metadata_factory, *, value=1.0, metadata=None):
    return SampleRecord(metadata=metadata or metadata_factory(), value=value)


def test_append_assigns_monotonic_transaction_watermarks(metadata_factory):
    log = AppendOnlyTransactionLog()
    first = log.append([make_record(metadata_factory)], idempotency_key="command-1")
    second = log.append([make_record(metadata_factory)], idempotency_key="command-2")

    assert first.transaction.global_commit_seq == 1
    assert second.transaction.global_commit_seq == 2
    assert second.watermark.global_commit_seq == 2
    assert second.watermark.source_local_seq["test.Record"] == 2
    assert [item.global_commit_seq for item in log.read()] == [1, 2]


def test_idempotent_append_returns_original_commit(metadata_factory):
    log = AppendOnlyTransactionLog()
    record = make_record(metadata_factory)
    original = log.append([record], idempotency_key="same-command")
    repeated = log.append([record], idempotency_key="same-command")

    assert repeated.idempotent_replay
    assert repeated.transaction == original.transaction
    assert repeated.watermark == original.watermark
    assert len(log.read()) == 1


def test_idempotency_conflict_and_duplicate_record_are_rejected(metadata_factory):
    log = AppendOnlyTransactionLog()
    record = make_record(metadata_factory)
    log.append([record], idempotency_key="key")

    with pytest.raises(IdempotencyConflictError):
        log.append([make_record(metadata_factory, value=2)], idempotency_key="key")
    with pytest.raises(RecordAlreadyCommittedError):
        log.append([record], idempotency_key="new-key")
    assert log.latest_watermark().global_commit_seq == 1


def test_duplicate_record_id_inside_one_transaction_is_rejected(metadata_factory):
    log = AppendOnlyTransactionLog()
    record = make_record(metadata_factory)
    with pytest.raises(RecordAlreadyCommittedError, match="duplicate record IDs"):
        log.append([record, record], idempotency_key="duplicate-in-batch")
    assert log.read() == ()
    assert log.latest_watermark().global_commit_seq == 0


def test_empty_watermark_and_fingerprint_are_stable():
    first = AppendOnlyTransactionLog()
    second = AppendOnlyTransactionLog()
    assert first.latest_watermark() == first.latest_watermark()
    assert first.latest_watermark() == second.latest_watermark()
    assert first.fingerprint() == second.fingerprint()


def test_failed_multi_household_commit_is_atomic(metadata_factory, now):
    log = AppendOnlyTransactionLog()
    trace_id = uuid4()
    first_metadata = metadata_factory().model_copy(update={"trace_id": trace_id})
    second_metadata = BaseRecordMetadata(
        schema_name="test.Record",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        recorded_time=now,
        source_type=SourceType.MODEL,
        source_id="other-household",
        trace_id=trace_id,
    )

    with pytest.raises(ValueError, match="mix households"):
        log.append(
            [
                make_record(metadata_factory, metadata=first_metadata),
                make_record(metadata_factory, metadata=second_metadata),
            ],
            idempotency_key="invalid-batch",
        )
    assert log.latest_watermark().global_commit_seq == 0
    assert log.read() == ()


def test_read_respects_watermark_and_household(metadata_factory):
    log = AppendOnlyTransactionLog()
    household_id = metadata_factory().household_id
    first = make_record(metadata_factory)
    second = make_record(metadata_factory)
    log.append([first], idempotency_key="first")
    log.append([second], idempotency_key="second")

    selected = log.read(
        after_commit_seq=1,
        through_commit_seq=2,
        household_id=household_id,
    )
    assert len(selected) == 1
    assert selected[0].records[0].envelope.record_id == second.metadata.record_id
    assert log.read(household_id=uuid4()) == ()


def test_canonical_derived_and_training_stores_are_isolated(metadata_factory):
    stores = StoreCatalog()
    record = make_record(metadata_factory)
    online_log = stores.canonical(StorePartition.ONLINE)
    online_projection = stores.derived(StorePartition.ONLINE)
    training_log = stores.canonical(StorePartition.TRAINING)

    commit = online_log.append([record], idempotency_key="online")
    online_projection.put(record, input_watermark=commit.watermark)

    assert online_log.latest_watermark().global_commit_seq == 1
    assert len(online_projection) == 1
    assert training_log.latest_watermark().global_commit_seq == 0


def test_replay_manifest_fingerprint_ignores_identity_but_binds_logical_time(metadata_factory, now):
    log = AppendOnlyTransactionLog()
    commit = log.append([make_record(metadata_factory)], idempotency_key="input")
    first = ReplayManifest(
        input_watermark=commit.watermark,
        input_log_sha256=log.fingerprint(through_commit_seq=commit.watermark.global_commit_seq),
        schema_version="0.1.0",
        code_version="git:test",
        source_tree_sha256="a" * 64,
        model_versions={"belief": "baseline@1"},
        configuration_hash="config-sha256",
        random_seed=17,
        execution_mode=ExecutionMode.REPLAY,
        created_at=now,
    )
    different_identity = first.model_copy(update={"replay_manifest_id": uuid4()})
    different_logical_time = first.model_copy(update={"created_at": now + timedelta(minutes=1)})

    assert first.fingerprint == different_identity.fingerprint
    assert first.fingerprint != different_logical_time.fingerprint


def test_append_can_bind_canonical_commit_time(metadata_factory, now):
    log = AppendOnlyTransactionLog()
    record = make_record(metadata_factory)
    commit = log.append(
        [record],
        idempotency_key="logical-time",
        committed_at=now,
    )

    assert commit.transaction.committed_at == now
    assert commit.transaction.records[0].committed_at == now
    assert commit.watermark.recorded_at == now

    with pytest.raises(IdempotencyConflictError, match="different time"):
        log.append(
            [record],
            idempotency_key="logical-time",
            committed_at=now + timedelta(seconds=1),
        )


def test_committed_transaction_rejects_record_time_mismatch(metadata_factory, now):
    commit = AppendOnlyTransactionLog().append(
        [make_record(metadata_factory)],
        idempotency_key="transaction-time-binding",
        committed_at=now,
    )
    tampered = commit.transaction.model_dump(mode="python")
    tampered["committed_at"] = now + timedelta(seconds=1)

    with pytest.raises(ValidationError, match="record time must match"):
        type(commit.transaction).model_validate(tampered)


def test_transaction_log_round_trips_through_disk(metadata_factory, tmp_path):
    original = AppendOnlyTransactionLog(partition=StorePartition.REPLAY)
    original.append([make_record(metadata_factory)], idempotency_key="first")
    original.append([make_record(metadata_factory)], idempotency_key="second")
    path = tmp_path / "canonical-log.json"
    original.dump(path)

    restored = AppendOnlyTransactionLog.load(path)
    assert restored.partition == StorePartition.REPLAY
    assert restored.read() == original.read()
    assert restored.latest_watermark() == original.latest_watermark()
    assert restored.fingerprint() == original.fingerprint()


def test_snapshot_invalidation_is_append_semantic(metadata_factory):
    log = AppendOnlyTransactionLog()
    commit = log.append([make_record(metadata_factory)], idempotency_key="snapshot-input")
    state = {"location": {"desk": 0.7, "kitchen": 0.3}}
    manifest = SnapshotManifest(
        household_id=metadata_factory().household_id,
        partition=StorePartition.ONLINE,
        data_plane=DataPlane.DERIVED,
        input_watermark=commit.watermark,
        schema_versions={"BeliefSnapshot": "0.1.0"},
        state_ref="memory://projection/1",
        state_sha256=content_hash(state),
    )
    catalog = SnapshotCatalog()
    catalog.add(manifest)
    invalid = catalog.invalidate(manifest.snapshot_id, reason="evidence retracted")

    assert not invalid.valid
    assert invalid.invalidation_reasons == ("evidence retracted",)
