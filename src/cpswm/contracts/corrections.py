"""User-correction contracts, separate from robot execution feedback."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)


class AuthorityLevel(StrEnum):
    UNVERIFIED_REPORTER = "unverified_reporter"
    AUTHORIZED_REPORTER = "authorized_reporter"
    AUTHORIZED_CORRECTOR = "authorized_corrector"
    HOUSEHOLD_OWNER = "household_owner"
    SYSTEM_ADMIN = "system_admin"


class CorrectionMode(StrEnum):
    ADD = "add"
    SUPERSEDE = "supersede"
    RETRACT = "retract"
    CONFIRM = "confirm"


class AuthorityScope(ContractModel):
    household_id: UUID
    allowed_entity_ids: tuple[UUID, ...] = ()
    allowed_predicates: tuple[str, ...] = ()


class UserCorrectionEvent(ContractModel):
    metadata: BaseRecordMetadata
    actor: EntityRef
    authority_level: AuthorityLevel
    authority_scope: AuthorityScope
    correction_mode: CorrectionMode
    target_record_ids: tuple[UUID, ...] = ()
    replacement_payload: JsonValue | None = None
    user_statement_ref: EvidenceRef
    valid_time: ValidTimeInterval

    @model_validator(mode="after")
    def validate_correction(self) -> UserCorrectionEvent:
        if self.metadata.source_type != SourceType.USER:
            raise ValueError("UserCorrectionEvent must have source_type=user")
        if self.authority_scope.household_id != self.metadata.household_id:
            raise ValueError("authority scope and record household must match")
        if self.correction_mode == CorrectionMode.ADD:
            if self.replacement_payload is None:
                raise ValueError("add correction requires a replacement payload")
        elif self.correction_mode == CorrectionMode.SUPERSEDE:
            if not self.target_record_ids or self.replacement_payload is None:
                raise ValueError("supersede requires targets and a replacement payload")
        elif self.correction_mode in {CorrectionMode.RETRACT, CorrectionMode.CONFIRM}:
            if not self.target_record_ids:
                raise ValueError(f"{self.correction_mode.value} requires target records")
        return self


class AuthorizedCorrection(ContractModel):
    metadata: BaseRecordMetadata
    correction_event_id: UUID
    access_decision_id: UUID
    authorized_mode: CorrectionMode
    target_record_ids: tuple[UUID, ...] = ()
    replacement_payload: JsonValue | None = None

    @model_validator(mode="after")
    def validate_authorization_record(self) -> AuthorizedCorrection:
        if self.metadata.source_type not in {SourceType.MODEL, SourceType.ACTION}:
            raise ValueError("AuthorizedCorrection must come from an authorization service")
        return self
