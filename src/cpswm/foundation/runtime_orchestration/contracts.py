"""Public M04 message and execution contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    InputWatermark,
    PositiveInt,
    SourceType,
    require_aware,
    utc_now,
)
from cpswm.foundation.persistence_replay.contracts import content_hash


class MessageKind(StrEnum):
    COMMAND = "command"
    EVENT = "event"


class HandlerStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class VersionBundle(ContractModel):
    code_version: str = Field(min_length=1)
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(min_length=1)
    model_versions: dict[str, str] = Field(default_factory=dict)


class RetryPolicy(ContractModel):
    max_attempts: PositiveInt = 1
    backoff_seconds: float = Field(default=0.0, ge=0.0)


class RuntimeMessage(ContractModel):
    message_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    kind: MessageKind
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    causation_id: UUID | None = None
    correlation_id: UUID | None = None
    idempotency_key: str = Field(min_length=1)
    sequence_no: int = Field(ge=0)
    payload: JsonValue
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_payload_hash(self) -> RuntimeMessage:
        if content_hash(self.payload) != self.payload_sha256:
            raise ValueError("payload_sha256 does not match message payload")
        return self

    @classmethod
    def create(
        cls,
        *,
        name: str,
        kind: MessageKind,
        schema_version: str,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        idempotency_key: str,
        sequence_no: int,
        payload: JsonValue,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        message_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> RuntimeMessage:
        values = {
            "name": name,
            "kind": kind,
            "schema_version": schema_version,
            "household_id": household_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "causation_id": causation_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "sequence_no": sequence_no,
            "payload": payload,
            "payload_sha256": content_hash(payload),
        }
        if message_id is not None:
            values["message_id"] = message_id
        if created_at is not None:
            values["created_at"] = created_at
        return cls(**values)

    @property
    def fingerprint(self) -> str:
        """Hash the complete canonical message, including identity and time."""

        return content_hash(self.model_dump(mode="json"))


class RuntimeMessageRecord(ContractModel):
    """Persistable input record decoded by strict log-bound replay."""

    metadata: BaseRecordMetadata
    message: RuntimeMessage

    @model_validator(mode="after")
    def validate_binding(self) -> RuntimeMessageRecord:
        if self.metadata.record_id != self.message.message_id:
            raise ValueError("runtime-message record_id must equal message_id")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(self.metadata, field_name) != getattr(self.message, field_name):
                raise ValueError(f"runtime-message record must preserve {field_name}")
        if self.metadata.schema_version != self.message.schema_version:
            raise ValueError("runtime-message record schema versions must match")
        return self

    @classmethod
    def from_message(
        cls,
        message: RuntimeMessage,
        *,
        source_id: str = "m04.runtime_input",
    ) -> RuntimeMessageRecord:
        return cls(
            metadata=BaseRecordMetadata(
                record_id=message.message_id,
                schema_name="cpswm.RuntimeMessageRecord",
                schema_version=message.schema_version,
                household_id=message.household_id,
                session_id=message.session_id,
                recorded_time=message.created_at,
                source_type=SourceType.IMPORT,
                source_id=source_id,
                trace_id=message.trace_id,
            ),
            message=message,
        )


class HandlerExecutionRecord(ContractModel):
    execution_id: UUID = Field(default_factory=uuid4)
    handler_name: str = Field(min_length=1)
    message_id: UUID
    message_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: UUID
    status: HandlerStatus
    attempts: PositiveInt
    versions: VersionBundle
    started_at: datetime
    finished_at: datetime
    output_watermark: InputWatermark | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return require_aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_status(self) -> HandlerExecutionRecord:
        if self.finished_at < self.started_at:
            raise ValueError("handler execution cannot finish before it starts")
        if self.status == HandlerStatus.FAILED and self.error_type is None:
            raise ValueError("failed execution must include error information")
        if self.status != HandlerStatus.FAILED and (
            self.error_type is not None or self.error_message is not None
        ):
            raise ValueError("successful execution cannot include an error")
        return self
