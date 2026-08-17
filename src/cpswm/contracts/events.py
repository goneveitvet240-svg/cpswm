"""M14 episodic-event contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EvidenceScoredMixin,
    SourceType,
    TemporalValidityMixin,
)


class EventType(StrEnum):
    PICK_UP = "pick_up"
    HOLD = "hold"
    CARRY = "carry"
    PLACE = "place"
    USE = "use"
    TRANSFER = "transfer"
    ENTER = "enter"
    LEAVE = "leave"
    OBSERVE = "observe"
    VERIFY_ABSENCE = "verify_absence"


class EventEvidenceClass(StrEnum):
    OBSERVED = "observed"
    REPORTED = "reported"
    INFERRED = "inferred"
    EXECUTED = "executed"


class EventParticipantRole(StrEnum):
    ACTOR = "actor"
    OBJECT = "object"
    SOURCE_LOCATION = "source_location"
    DESTINATION_LOCATION = "destination_location"
    RECIPIENT = "recipient"
    CONTEXT = "context"


class EventParticipant(ContractModel):
    role: EventParticipantRole
    entity: EntityRef


class EventRecord(ContractModel):
    """Immutable event record with explicit evidence class."""

    metadata: BaseRecordMetadata
    temporal: TemporalValidityMixin
    event_type: EventType
    evidence_class: EventEvidenceClass
    participants: tuple[EventParticipant, ...] = Field(min_length=1)
    evidence: EvidenceScoredMixin
    causal_parent_event_ids: tuple[UUID, ...] = ()
    alternative_hypothesis_event_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_source_semantics(self) -> EventRecord:
        source_type = self.metadata.source_type
        allowed = {
            EventEvidenceClass.OBSERVED: {
                SourceType.SENSOR,
                SourceType.MODEL,
                SourceType.SIMULATION,
            },
            EventEvidenceClass.REPORTED: {SourceType.USER, SourceType.IMPORT},
            EventEvidenceClass.INFERRED: {SourceType.INFERENCE},
            EventEvidenceClass.EXECUTED: {SourceType.ACTION},
        }
        if source_type not in allowed[self.evidence_class]:
            raise ValueError(
                f"source_type={source_type.value} is incompatible with "
                f"evidence_class={self.evidence_class.value}"
            )
        if self.metadata.record_id in self.evidence.supersedes:
            raise ValueError("an event record cannot supersede itself")
        return self
