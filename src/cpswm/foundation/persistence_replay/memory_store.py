"""Deterministic in-memory reference adapters for M03."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Sequence
from uuid import UUID

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    InputWatermark,
    require_aware,
    utc_now,
)

from .contracts import (
    CommitResult,
    CommittedRecord,
    CommittedTransaction,
    DataPlane,
    RecordEnvelope,
    StorePartition,
    TransactionLogDump,
    canonical_json,
    content_hash,
)


ZERO_UUID = UUID(int=0)
EMPTY_WATERMARK_RECORDED_AT = datetime(1970, 1, 1, tzinfo=timezone.utc)


class IdempotencyConflictError(ValueError):
    """The same idempotency key was reused for different content."""


class RecordAlreadyCommittedError(ValueError):
    """A record ID cannot appear in two canonical transactions."""


def envelope_from_contract(record: ContractModel) -> RecordEnvelope:
    metadata = getattr(record, "metadata", None)
    if not isinstance(metadata, BaseRecordMetadata):
        raise TypeError("persisted top-level contracts must contain BaseRecordMetadata")
    payload = record.model_dump(mode="json")
    return RecordEnvelope(
        record_id=metadata.record_id,
        schema_name=metadata.schema_name,
        schema_version=metadata.schema_version,
        household_id=metadata.household_id,
        session_id=metadata.session_id,
        trace_id=metadata.trace_id,
        payload=payload,
        payload_sha256=content_hash(payload),
    )


class AppendOnlyTransactionLog:
    """Atomic append-only log with a single global transaction sequence."""

    def __init__(self, *, partition: StorePartition = StorePartition.ONLINE) -> None:
        self.partition = partition
        self._transactions: list[CommittedTransaction] = []
        self._idempotency: dict[tuple[UUID, str], CommittedTransaction] = {}
        self._watermarks: dict[UUID, InputWatermark] = {}
        self._record_ids: set[UUID] = set()
        self._source_local_seq: dict[str, int] = {}
        self._lock = RLock()

    def append(
        self,
        records: Sequence[ContractModel],
        *,
        idempotency_key: str,
        committed_at: datetime | None = None,
    ) -> CommitResult:
        if not records:
            raise ValueError("a canonical transaction requires at least one record")
        if not idempotency_key:
            raise ValueError("idempotency_key cannot be empty")
        requested_committed_at = (
            require_aware(committed_at, "committed_at")
            if committed_at is not None
            else None
        )
        envelopes = tuple(envelope_from_contract(record) for record in records)
        batch_record_ids = [item.record_id for item in envelopes]
        if len(batch_record_ids) != len(set(batch_record_ids)):
            raise RecordAlreadyCommittedError(
                "one canonical transaction cannot contain duplicate record IDs"
            )
        households = {item.household_id for item in envelopes}
        traces = {item.trace_id for item in envelopes}
        if len(households) != 1:
            raise ValueError("one canonical transaction cannot mix households")
        if len(traces) != 1:
            raise ValueError("one canonical transaction must share one trace_id")
        household_id = next(iter(households))
        trace_id = next(iter(traces))
        request_payload = [item.model_dump(mode="json") for item in envelopes]
        request_sha256 = content_hash(request_payload)
        scoped_key = (household_id, idempotency_key)

        with self._lock:
            previous = self._idempotency.get(scoped_key)
            if previous is not None:
                if previous.request_sha256 != request_sha256:
                    raise IdempotencyConflictError(
                        "idempotency key was already committed with different content"
                    )
                if (
                    requested_committed_at is not None
                    and previous.committed_at != requested_committed_at
                ):
                    raise IdempotencyConflictError(
                        "idempotency key was already committed at a different time"
                    )
                return CommitResult(
                    transaction=previous,
                    watermark=self._watermarks[previous.transaction_id],
                    idempotent_replay=True,
                )

            duplicate_ids = self._record_ids.intersection(
                item.record_id for item in envelopes
            )
            if duplicate_ids:
                raise RecordAlreadyCommittedError(
                    f"record IDs already committed: {sorted(map(str, duplicate_ids))}"
                )

            transaction_committed_at = requested_committed_at or utc_now()
            global_commit_seq = len(self._transactions) + 1
            transaction_id = UUID(bytes=bytes.fromhex(request_sha256[:32]))
            committed_records = tuple(
                CommittedRecord(
                    envelope=envelope,
                    transaction_id=transaction_id,
                    global_commit_seq=global_commit_seq,
                    record_index=index,
                    committed_at=transaction_committed_at,
                    partition=self.partition,
                    data_plane=DataPlane.CANONICAL,
                )
                for index, envelope in enumerate(envelopes)
            )
            transaction = CommittedTransaction(
                transaction_id=transaction_id,
                global_commit_seq=global_commit_seq,
                household_id=household_id,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                committed_at=transaction_committed_at,
                records=committed_records,
            )

            # Mutation begins only after every contract above has validated.
            self._transactions.append(transaction)
            self._idempotency[scoped_key] = transaction
            self._record_ids.update(item.record_id for item in envelopes)
            for item in envelopes:
                self._source_local_seq[item.schema_name] = (
                    self._source_local_seq.get(item.schema_name, 0) + 1
                )
            watermark = self._watermark_for(transaction)
            self._watermarks[transaction.transaction_id] = watermark
            return CommitResult(
                transaction=transaction,
                watermark=watermark,
            )

    def read(
        self,
        *,
        after_commit_seq: int = 0,
        through_commit_seq: int | None = None,
        household_id: UUID | None = None,
    ) -> tuple[CommittedTransaction, ...]:
        if after_commit_seq < 0:
            raise ValueError("after_commit_seq cannot be negative")
        if through_commit_seq is not None and through_commit_seq < after_commit_seq:
            raise ValueError("through_commit_seq cannot precede after_commit_seq")
        with self._lock:
            return tuple(
                item
                for item in self._transactions
                if item.global_commit_seq > after_commit_seq
                and (
                    through_commit_seq is None
                    or item.global_commit_seq <= through_commit_seq
                )
                and (household_id is None or item.household_id == household_id)
            )

    def latest_watermark(self) -> InputWatermark:
        with self._lock:
            return self.watermark_at(len(self._transactions))

    def watermark_at(self, global_commit_seq: int) -> InputWatermark:
        with self._lock:
            if global_commit_seq == 0:
                return InputWatermark(
                    global_commit_seq=0,
                    transaction_id=ZERO_UUID,
                    source_local_seq={},
                    recorded_at=EMPTY_WATERMARK_RECORDED_AT,
                )
            if global_commit_seq < 0 or global_commit_seq > len(self._transactions):
                raise LookupError(
                    f"global_commit_seq {global_commit_seq} is not present in the log"
                )
            transaction = self._transactions[global_commit_seq - 1]
            return self._watermarks[transaction.transaction_id]

    def fingerprint(self, *, through_commit_seq: int | None = None) -> str:
        with self._lock:
            through = (
                len(self._transactions)
                if through_commit_seq is None
                else through_commit_seq
            )
            self.watermark_at(through)
            payload = {
                "format_version": "1.0.0",
                "partition": self.partition.value,
                "transactions": [
                    item.model_dump(mode="json")
                    for item in self._transactions[:through]
                ],
            }
            return content_hash(payload)

    def dump(self, path: str | Path) -> None:
        target = Path(path)
        snapshot = TransactionLogDump(
            partition=self.partition,
            transactions=tuple(self._transactions),
        )
        target.write_text(
            canonical_json(snapshot.model_dump(mode="json")), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> AppendOnlyTransactionLog:
        source = Path(path)
        snapshot = TransactionLogDump.model_validate_json(source.read_text(encoding="utf-8"))
        log = cls(partition=snapshot.partition)
        for transaction in snapshot.transactions:
            log._transactions.append(transaction)
            log._idempotency[
                (transaction.household_id, transaction.idempotency_key)
            ] = transaction
            for record in transaction.records:
                log._record_ids.add(record.envelope.record_id)
                schema_name = record.envelope.schema_name
                log._source_local_seq[schema_name] = (
                    log._source_local_seq.get(schema_name, 0) + 1
                )
            log._watermarks[transaction.transaction_id] = log._watermark_for(
                transaction
            )
        return log

    def _watermark_for(self, transaction: CommittedTransaction) -> InputWatermark:
        return InputWatermark(
            global_commit_seq=transaction.global_commit_seq,
            transaction_id=transaction.transaction_id,
            source_local_seq=dict(self._source_local_seq),
            recorded_at=transaction.committed_at,
        )


class InMemoryProjectionStore:
    """Separate replaceable storage for derived projections."""

    def __init__(self, *, partition: StorePartition = StorePartition.ONLINE) -> None:
        self.partition = partition
        self._records: dict[UUID, tuple[RecordEnvelope, InputWatermark]] = {}

    def put(self, record: ContractModel, *, input_watermark: InputWatermark) -> None:
        envelope = envelope_from_contract(record)
        self._records[envelope.record_id] = (envelope, input_watermark)

    def get(self, record_id: UUID) -> tuple[RecordEnvelope, InputWatermark]:
        return self._records[record_id]

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


class StoreCatalog:
    """Keeps online, training, and replay stores physically distinct in A0."""

    def __init__(self) -> None:
        self._canonical = {
            partition: AppendOnlyTransactionLog(partition=partition)
            for partition in StorePartition
        }
        self._derived = {
            partition: InMemoryProjectionStore(partition=partition)
            for partition in StorePartition
        }

    def canonical(self, partition: StorePartition) -> AppendOnlyTransactionLog:
        return self._canonical[partition]

    def derived(self, partition: StorePartition) -> InMemoryProjectionStore:
        return self._derived[partition]
