"""Ground-truth-only long-horizon habit trajectories for M29/M31."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware


class GTHabitRegimeKind(StrEnum):
    STABLE = "stable"
    CONTEXTUAL = "contextual"
    TEMPORARY_EXCEPTION = "temporary_exception"
    GRADUAL_CHANGE = "gradual_change"
    ABRUPT_CHANGE = "abrupt_change"


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

    @model_validator(mode="after")
    def validate_event_order(self) -> GroundTruthHabitTrajectory:
        event_times = [event.event_time for event in self.events]
        if event_times != sorted(event_times):
            raise ValueError("ground-truth habit events must be ordered by event_time")
        event_ids = [event.gt_event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("ground-truth habit event ids must be unique")
        return self

