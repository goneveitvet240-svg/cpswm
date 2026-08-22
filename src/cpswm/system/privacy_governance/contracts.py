"""M28 privacy and data-governance contracts.

These records implement the household-scoped capability authorization, the
oracle-channel audit, and the deletion/retention vertical slice.  Every record
carries M01 :class:`BaseRecordMetadata` so the M03 append-only log can persist
and replay them.

Scope honesty (per `技术框架_修改后执行步骤_v1.2.md` §3.5/§12.4):

* this is a vertical slice, not a production security system;
* it is not a claim of full GDPR compliance;
* the capability model is an API boundary against accidental misuse, not a
  sandbox against hostile code running in the same process.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    InputWatermark,
    SourceType,
    ValidTimeInterval,
    require_aware,
)


class CapabilityStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ResourceKind(StrEnum):
    """Resource namespaces a grant can name.

    ``gt.*`` is the evaluator ground-truth namespace.  Ordinary M10-M27
    perception, world-model, language, and action code must never hold a grant
    for it.
    """

    PERCEPTION = "perception"
    WORLD_MODEL = "world_model"
    GT = "gt"
    RAW_STORE = "raw_store"
    AUDIT = "audit"
    PRIVACY = "privacy"


class Operation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


class CapabilityGrant(ContractModel):
    """A versioned, household-scoped capability grant.

    Binds subject, household, resource, operation, purpose, validity interval,
    and issuer so that authorization can be re-checked deterministically.
    """

    metadata: BaseRecordMetadata
    grant_id: UUID = Field(default_factory=uuid4)
    subject: str = Field(min_length=1)
    household_id: UUID
    resource: ResourceKind
    operation: Operation
    purpose: str = Field(min_length=1)
    valid_time: ValidTimeInterval
    issuer: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_grant(self) -> CapabilityGrant:
        if self.household_id != self.metadata.household_id:
            raise ValueError("grant household must match metadata household")
        return self


class CapabilityRevocation(ContractModel):
    """Revokes one grant by ID.

    A revocation is append-only: the old grant record is never rewritten, but
    an authorization check must treat the revoked grant as inactive.
    """

    metadata: BaseRecordMetadata
    revocation_id: UUID = Field(default_factory=uuid4)
    grant_id: UUID
    revoked_by: str = Field(min_length=1)
    revoked_time: datetime
    reason: str = Field(min_length=1)

    @field_validator("revoked_time")
    @classmethod
    def validate_revoked_time(cls, value: datetime) -> datetime:
        return require_aware(value, "revoked_time")


class OracleAccessRequest(ContractModel):
    """A request to read ``gt.*`` ground truth.

    The request must declare ``evaluation_only`` and name the caller, the
    purpose, and the input watermark at which the read would happen.
    """

    metadata: BaseRecordMetadata
    request_id: UUID = Field(default_factory=uuid4)
    caller: str = Field(min_length=1)
    household_id: UUID
    resource: ResourceKind = ResourceKind.GT
    evaluation_only: bool
    purpose: str = Field(min_length=1)
    input_watermark: InputWatermark

    @model_validator(mode="after")
    def validate_request(self) -> OracleAccessRequest:
        if self.resource != ResourceKind.GT:
            raise ValueError("oracle access request must target the gt resource namespace")
        if not self.evaluation_only:
            raise ValueError("oracle access must declare evaluation_only")
        if self.household_id != self.metadata.household_id:
            raise ValueError("request household must match metadata household")
        return self


class OracleAccessDecision(ContractModel):
    """The authorization outcome for one oracle access request."""

    metadata: BaseRecordMetadata
    decision_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    allowed: bool
    decided_by: str = Field(min_length=1)
    decided_time: datetime
    denial_reason: str | None = None
    input_watermark: InputWatermark

    @field_validator("decided_time")
    @classmethod
    def validate_decided_time(cls, value: datetime) -> datetime:
        return require_aware(value, "decided_time")

    @model_validator(mode="after")
    def validate_decision(self) -> OracleAccessDecision:
        if self.allowed and self.denial_reason is not None:
            raise ValueError("an allowed decision cannot carry a denial reason")
        if not self.allowed and self.denial_reason is None:
            raise ValueError("a denied decision requires a denial reason")
        return self


class OracleAccessAuditRecord(ContractModel):
    """Post-hoc audit of one oracle access: caller, purpose, watermark, summary."""

    metadata: BaseRecordMetadata
    audit_id: UUID = Field(default_factory=uuid4)
    decision_id: UUID
    caller: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_watermark: InputWatermark
    output_summary: JsonValue

    @model_validator(mode="after")
    def validate_audit(self) -> OracleAccessAuditRecord:
        # An oracle audit is authored by governance for evaluator-only reads.
        # A physical sensor (SENSOR) can never author one; neither can an
        # inference/model record masquerade as an oracle audit.
        if self.metadata.source_type == SourceType.SENSOR:
            raise ValueError("oracle audit must not originate from a physical sensor")
        return self


class DataRetentionPolicy(ContractModel):
    """A household retention policy with a validity interval."""

    metadata: BaseRecordMetadata
    policy_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    retention_seconds: float = Field(ge=0.0)
    applicable_resource: ResourceKind
    valid_time: ValidTimeInterval

    @model_validator(mode="after")
    def validate_policy(self) -> DataRetentionPolicy:
        if self.household_id != self.metadata.household_id:
            raise ValueError("policy household must match metadata household")
        return self


class UserDeletionRequest(ContractModel):
    """A user request to delete personal data.

    Deletion never rewrites the append-only history.  It produces a tombstone
    that drives a redaction projection; the audit proof remains.
    """

    metadata: BaseRecordMetadata
    deletion_request_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    subject: str = Field(min_length=1)
    target_record_ids: tuple[UUID, ...] = ()
    requested_time: datetime
    authorization_grant_id: UUID | None = None

    @field_validator("requested_time")
    @classmethod
    def validate_requested_time(cls, value: datetime) -> datetime:
        return require_aware(value, "requested_time")

    @model_validator(mode="after")
    def validate_request(self) -> UserDeletionRequest:
        if self.household_id != self.metadata.household_id:
            raise ValueError("deletion household must match metadata household")
        return self


class DeletionExecutionReceipt(ContractModel):
    """Proof that a deletion request was executed as a tombstone projection.

    ``tombstoned_record_ids`` lists the records removed from the redacted
    projection; the underlying append-only log is untouched.
    """

    metadata: BaseRecordMetadata
    receipt_id: UUID = Field(default_factory=uuid4)
    deletion_request_id: UUID
    household_id: UUID
    tombstoned_record_ids: tuple[UUID, ...]
    executed_time: datetime
    projection_version: str = Field(min_length=1)

    @field_validator("executed_time")
    @classmethod
    def validate_executed_time(cls, value: datetime) -> datetime:
        return require_aware(value, "executed_time")

    @model_validator(mode="after")
    def validate_receipt(self) -> DeletionExecutionReceipt:
        if self.household_id != self.metadata.household_id:
            raise ValueError("receipt household must match metadata household")
        return self


__all__ = [
    "CapabilityGrant",
    "CapabilityRevocation",
    "CapabilityStatus",
    "DataRetentionPolicy",
    "DeletionExecutionReceipt",
    "Operation",
    "OracleAccessAuditRecord",
    "OracleAccessDecision",
    "OracleAccessRequest",
    "ResourceKind",
    "UserDeletionRequest",
]
