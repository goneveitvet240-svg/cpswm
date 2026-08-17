"""Public M03 persistence and replay contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from cpswm.contracts.base import (
    ContractModel,
    InputWatermark,
    NonNegativeInt,
    PositiveInt,
    require_aware,
    utc_now,
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class DataPlane(StrEnum):
    CANONICAL = "canonical"
    DERIVED = "derived"


class StorePartition(StrEnum):
    ONLINE = "online"
    TRAINING = "training"
    REPLAY = "replay"


class ExecutionMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    TEST = "test"


class RecordEnvelope(ContractModel):
    record_id: UUID
    schema_name: str = Field(min_length=1)
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    payload: JsonValue
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_hash(self) -> RecordEnvelope:
        if content_hash(self.payload) != self.payload_sha256:
            raise ValueError("payload_sha256 does not match payload")
        return self


class CommittedRecord(ContractModel):
    envelope: RecordEnvelope
    transaction_id: UUID
    global_commit_seq: PositiveInt
    record_index: NonNegativeInt
    committed_at: datetime
    partition: StorePartition
    data_plane: DataPlane

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return require_aware(value, "committed_at")


class CommittedTransaction(ContractModel):
    transaction_id: UUID
    global_commit_seq: PositiveInt
    household_id: UUID
    trace_id: UUID
    idempotency_key: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at: datetime
    records: tuple[CommittedRecord, ...] = Field(min_length=1)

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return require_aware(value, "committed_at")

    @model_validator(mode="after")
    def validate_records(self) -> CommittedTransaction:
        for index, record in enumerate(self.records):
            if record.transaction_id != self.transaction_id:
                raise ValueError("committed record has a different transaction_id")
            if record.global_commit_seq != self.global_commit_seq:
                raise ValueError("committed record has a different global_commit_seq")
            if record.record_index != index:
                raise ValueError("record_index must be contiguous and start at zero")
            if record.committed_at != self.committed_at:
                raise ValueError(
                    "committed record time must match its transaction committed_at"
                )
            if record.envelope.household_id != self.household_id:
                raise ValueError("one transaction cannot mix households")
        request_payload = [item.envelope.model_dump(mode="json") for item in self.records]
        expected_hash = content_hash(request_payload)
        if self.request_sha256 != expected_hash:
            raise ValueError("request_sha256 does not match committed records")
        expected_transaction_id = UUID(bytes=bytes.fromhex(expected_hash[:32]))
        if self.transaction_id != expected_transaction_id:
            raise ValueError("transaction_id does not match committed content")
        return self


class CommitResult(ContractModel):
    transaction: CommittedTransaction
    watermark: InputWatermark
    idempotent_replay: bool = False


class ReplayManifest(ContractModel):
    replay_manifest_id: UUID = Field(default_factory=uuid4)
    input_watermark: InputWatermark
    input_log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    code_version: str = Field(min_length=1)
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_versions: dict[str, str] = Field(default_factory=dict)
    configuration_hash: str = Field(min_length=1)
    random_seed: int
    execution_mode: ExecutionMode = ExecutionMode.REPLAY
    numeric_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        allow_inf_nan=False,
    )
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")

    @property
    def fingerprint(self) -> str:
        # replay_manifest_id is an incidental storage identity. created_at is
        # intentionally retained because M04 uses it as replay logical time.
        payload = self.model_dump(mode="json", exclude={"replay_manifest_id"})
        return content_hash(payload)


class TransactionLogDump(ContractModel):
    format_version: str = "1.0.0"
    partition: StorePartition
    transactions: tuple[CommittedTransaction, ...] = ()

    @model_validator(mode="after")
    def validate_log(self) -> TransactionLogDump:
        expected_sequences = list(range(1, len(self.transactions) + 1))
        actual_sequences = [item.global_commit_seq for item in self.transactions]
        if actual_sequences != expected_sequences:
            raise ValueError("transaction log sequences must be contiguous from one")
        record_ids: list[UUID] = []
        idempotency_keys: set[tuple[UUID, str]] = set()
        for transaction in self.transactions:
            key = (transaction.household_id, transaction.idempotency_key)
            if key in idempotency_keys:
                raise ValueError("transaction log contains a duplicate idempotency key")
            idempotency_keys.add(key)
            for record in transaction.records:
                if record.partition != self.partition:
                    raise ValueError("record partition does not match log partition")
                if record.data_plane != DataPlane.CANONICAL:
                    raise ValueError("canonical transaction log contains derived data")
                record_ids.append(record.envelope.record_id)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("transaction log contains duplicate record IDs")
        return self


class SnapshotManifest(ContractModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    partition: StorePartition
    data_plane: DataPlane
    input_watermark: InputWatermark
    schema_versions: dict[str, str]
    state_ref: str = Field(min_length=1)
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)
    valid: bool = True
    invalidation_reasons: tuple[str, ...] = ()

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_state(self) -> SnapshotManifest:
        if self.valid and self.invalidation_reasons:
            raise ValueError("valid snapshot cannot have invalidation reasons")
        if not self.valid and not self.invalidation_reasons:
            raise ValueError("invalid snapshot must state a reason")
        return self
