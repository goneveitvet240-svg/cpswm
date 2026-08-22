"""Ground-truth-only long-horizon habit trajectories for M29/M31."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, require_aware


class GTHabitRegimeKind(StrEnum):
    STABLE = "stable"
    CONTEXTUAL = "contextual"
    TEMPORARY_EXCEPTION = "temporary_exception"
    GRADUAL_CHANGE = "gradual_change"
    ABRUPT_CHANGE = "abrupt_change"


class GTInteractionEventType(StrEnum):
    """Privileged event vocabulary aligned with the versioned M30 plan."""

    PICK_UP = "pick_up"
    CARRY = "carry"
    USE = "use"
    PLACE = "place"
    HANDOFF = "handoff"


class GTInteractionEvent(ContractModel):
    """One privileged step in a complete object-interaction event chain."""

    gt_event_id: UUID = Field(default_factory=uuid4)
    event_chain_id: UUID
    sequence_no: NonNegativeInt
    event_time: datetime
    event_type: GTInteractionEventType
    actor_gt_entity_id: UUID
    recipient_actor_gt_entity_id: UUID | None = None
    object_gt_entity_id: UUID
    source_location_gt_entity_id: UUID | None = None
    destination_location_gt_entity_id: UUID | None = None
    context_key: str = Field(min_length=1)
    regime_id: str = Field(min_length=1)
    regime_kind: GTHabitRegimeKind

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def validate_event_semantics(self) -> GTInteractionEvent:
        if self.event_type == GTInteractionEventType.PICK_UP:
            if self.source_location_gt_entity_id is None:
                raise ValueError("ground-truth pick-up requires a source location")
        elif self.event_type == GTInteractionEventType.CARRY:
            if (
                self.source_location_gt_entity_id is None
                or self.destination_location_gt_entity_id is None
            ):
                raise ValueError("ground-truth carry requires source and destination")
        elif self.event_type == GTInteractionEventType.HANDOFF:
            if self.recipient_actor_gt_entity_id is None:
                raise ValueError("ground-truth handoff requires a recipient")
            if self.recipient_actor_gt_entity_id == self.actor_gt_entity_id:
                raise ValueError("ground-truth handoff actor and recipient must differ")
        elif (
            self.event_type == GTInteractionEventType.PLACE
            and self.destination_location_gt_entity_id is None
        ):
            raise ValueError("ground-truth placement requires a destination")
        return self


class GTPlacementEvent(ContractModel):
    """Privileged placement truth that production world-model code cannot read."""

    gt_event_id: UUID = Field(default_factory=uuid4)
    event_time: datetime
    actor_gt_entity_id: UUID
    object_gt_entity_id: UUID
    source_location_gt_entity_id: UUID | None = None
    destination_location_gt_entity_id: UUID
    context_key: str = Field(min_length=1)
    regime_id: str = Field(min_length=1)
    regime_kind: GTHabitRegimeKind

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")


class GroundTruthHabitTrajectory(ContractModel):
    simulation_run_id: UUID
    events: tuple[GTPlacementEvent, ...] = Field(min_length=1)
    interaction_events: tuple[GTInteractionEvent, ...] = ()

    @model_validator(mode="after")
    def validate_event_order(self) -> GroundTruthHabitTrajectory:
        event_times = [event.event_time for event in self.events]
        if event_times != sorted(event_times):
            raise ValueError("ground-truth habit events must be ordered by event_time")
        event_ids = [event.gt_event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("ground-truth habit event ids must be unique")
        interaction_order = [
            (event.event_time, str(event.gt_event_id)) for event in self.interaction_events
        ]
        if interaction_order != sorted(interaction_order):
            raise ValueError("ground-truth interaction events must be deterministically ordered")
        interaction_ids = [event.gt_event_id for event in self.interaction_events]
        if len(interaction_ids) != len(set(interaction_ids)):
            raise ValueError("ground-truth interaction event ids must be unique")
        if self.interaction_events:
            placements = {
                event.gt_event_id: event
                for event in self.interaction_events
                if event.event_type == GTInteractionEventType.PLACE
            }
            if set(placements) != set(event_ids):
                raise ValueError(
                    "ground-truth placement projection must match interaction PLACE events"
                )
            for placement in self.events:
                interaction = placements[placement.gt_event_id]
                if (
                    placement.event_time != interaction.event_time
                    or placement.actor_gt_entity_id != interaction.actor_gt_entity_id
                    or placement.object_gt_entity_id != interaction.object_gt_entity_id
                    or placement.source_location_gt_entity_id
                    != interaction.source_location_gt_entity_id
                    or placement.destination_location_gt_entity_id
                    != interaction.destination_location_gt_entity_id
                    or placement.context_key != interaction.context_key
                    or placement.regime_id != interaction.regime_id
                    or placement.regime_kind != interaction.regime_kind
                ):
                    raise ValueError(
                        "ground-truth placement projection disagrees with interaction event"
                    )
        return self
