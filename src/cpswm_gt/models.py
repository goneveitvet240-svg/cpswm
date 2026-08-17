"""Nominal ground-truth types that cannot substitute for M13/M14 records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from cpswm.contracts.base import (
    ContractModel,
    EntityType,
    ValidTimeInterval,
    require_aware,
)


class GTEntity(ContractModel):
    gt_entity_id: UUID = Field(default_factory=uuid4)
    entity_type: EntityType
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class GTRelationAssertion(ContractModel):
    gt_relation_id: UUID = Field(default_factory=uuid4)
    subject_gt_entity_id: UUID
    predicate: str = Field(min_length=1)
    object_gt_entity_id: UUID | None = None
    literal_value: JsonValue | None = None
    valid_time: ValidTimeInterval

    @model_validator(mode="after")
    def validate_object(self) -> GTRelationAssertion:
        has_entity = self.object_gt_entity_id is not None
        has_literal = self.literal_value is not None
        if has_entity == has_literal:
            raise ValueError("ground-truth relation requires exactly one object kind")
        return self


class GTEvent(ContractModel):
    gt_event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(min_length=1)
    participant_gt_entity_ids: dict[str, UUID]
    valid_time: ValidTimeInterval


class GroundTruthWorldState(ContractModel):
    simulation_run_id: UUID
    simulation_time: datetime
    entities: tuple[GTEntity, ...]
    relations: tuple[GTRelationAssertion, ...]
    events: tuple[GTEvent, ...] = ()

    @field_validator("simulation_time")
    @classmethod
    def validate_simulation_time(cls, value: datetime) -> datetime:
        return require_aware(value, "simulation_time")

    @model_validator(mode="after")
    def validate_references(self) -> GroundTruthWorldState:
        entity_ids = {item.gt_entity_id for item in self.entities}
        for relation in self.relations:
            if relation.subject_gt_entity_id not in entity_ids:
                raise ValueError("ground-truth relation has an unknown subject")
            if (
                relation.object_gt_entity_id is not None
                and relation.object_gt_entity_id not in entity_ids
            ):
                raise ValueError("ground-truth relation has an unknown object")
        for event in self.events:
            if not set(event.participant_gt_entity_ids.values()).issubset(entity_ids):
                raise ValueError("ground-truth event has an unknown participant")
        return self

