"""M13 relation-assertion contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EvidenceScoredMixin,
    TemporalValidityMixin,
)


class RelationPredicate(StrEnum):
    LOCATED_AT = "located_at"
    INSIDE = "inside"
    ON_TOP_OF = "on_top_of"
    NEAR = "near"
    BELONGS_TO = "belongs_to"
    USED_BY = "used_by"
    HELD_BY = "held_by"
    CARRIED_BY = "carried_by"
    MOVED_BY = "moved_by"
    SHARED_BY = "shared_by"
    ASSOCIATED_WITH_ACTIVITY = "associated_with_activity"
    USUALLY_LOCATED_AT = "usually_located_at"
    OBSERVED_WITH = "observed_with"
    VISUALLY_SIMILAR_TO = "visually_similar_to"
    AFFORDS = "affords"


class AssertionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    CONTRADICTED = "contradicted"


class EntityRelationObject(ContractModel):
    kind: Literal["entity"] = "entity"
    entity: EntityRef


class LiteralRelationObject(ContractModel):
    kind: Literal["literal"] = "literal"
    value: JsonValue


RelationObject = Annotated[
    Union[EntityRelationObject, LiteralRelationObject],
    Field(discriminator="kind"),
]


class RelationAssertion(ContractModel):
    """An append-only relation claim, never a world-state fact.

    Overlapping valid-time intervals are legal. The store and M16 projection
    decide whether overlap means competing evidence, correction, or conflict.
    A superseding assertion does not mutate the older record.
    """

    metadata: BaseRecordMetadata
    temporal: TemporalValidityMixin
    subject: EntityRef
    predicate: RelationPredicate
    object: RelationObject
    evidence: EvidenceScoredMixin
    status: AssertionStatus = AssertionStatus.ACTIVE

    @model_validator(mode="after")
    def validate_supersedes(self) -> RelationAssertion:
        if self.metadata.record_id in self.evidence.supersedes:
            raise ValueError("a relation assertion cannot supersede itself")
        return self
