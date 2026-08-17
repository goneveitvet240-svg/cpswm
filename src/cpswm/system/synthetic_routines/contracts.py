"""M30 contracts for people, object routines, changes, and event plans."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, require_aware
from cpswm.system.reproducibility import content_sha256


class RoutineChangeKind(StrEnum):
    STATIONARY_ROUTINE = "stationary_routine"
    ISOLATED_ANOMALY = "isolated_anomaly"
    TEMPORARY_EXCEPTION = "temporary_exception"
    ABRUPT_CHANGE = "abrupt_change"
    GRADUAL_DRIFT = "gradual_drift"
    PERIODIC_CONTEXT = "periodic_context"
    GUEST_CONTAMINATION = "guest_contamination"
    HOUSEHOLD_TRANSITION = "household_transition"


class RoutineEventType(StrEnum):
    PICK_UP = "pick_up"
    CARRY = "carry"
    USE = "use"
    PLACE = "place"
    HANDOFF = "handoff"


class ObjectRoutineSpec(ContractModel):
    object_instance_id: UUID
    default_actor_id: UUID
    initial_location_id: UUID
    habitual_location_id: UUID
    placement_hour: int = Field(ge=0, le=23)
    placement_minute: int = Field(default=0, ge=0, le=59)
    activity_key: str = Field(min_length=1)
    context_key: str = Field(min_length=1)


class RoutineChangeSpec(ContractModel):
    change_id: UUID
    kind: RoutineChangeKind
    object_instance_id: UUID
    start_day: NonNegativeInt
    target_location_id: UUID
    end_day: int | None = Field(default=None, ge=0)
    actor_override_id: UUID | None = None
    transition_days: PositiveInt = 1
    period_days: PositiveInt = 1

    @model_validator(mode="after")
    def validate_change(self) -> RoutineChangeSpec:
        if self.end_day is not None and self.end_day < self.start_day:
            raise ValueError("end_day must be >= start_day")
        if (
            self.kind == RoutineChangeKind.GUEST_CONTAMINATION
            and self.actor_override_id is None
        ):
            raise ValueError("guest contamination requires actor_override_id")
        return self


class RoutineGenerationConfig(ContractModel):
    household_id: UUID
    start_time: datetime
    duration_days: PositiveInt
    random_seed: NonNegativeInt
    object_routines: tuple[ObjectRoutineSpec, ...] = Field(min_length=1)
    changes: tuple[RoutineChangeSpec, ...] = ()
    generator_version: str = Field(default="synthetic-routines@0.2", min_length=1)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_references(self) -> RoutineGenerationConfig:
        routine_objects = [item.object_instance_id for item in self.object_routines]
        if len(routine_objects) != len(set(routine_objects)):
            raise ValueError("object_routines must define each object once")
        unknown = {
            change.object_instance_id for change in self.changes
        } - set(routine_objects)
        if unknown:
            raise ValueError("routine change references an unknown object")
        change_ids = [change.change_id for change in self.changes]
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("routine change ids must be unique")
        if any(change.start_day >= self.duration_days for change in self.changes):
            raise ValueError("routine change starts outside the generated duration")
        return self


class InteractionEventPlan(ContractModel):
    event_id: UUID
    event_time: datetime
    event_type: RoutineEventType
    actor_id: UUID
    object_instance_id: UUID
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    recipient_actor_id: UUID | None = None
    activity_key: str = Field(min_length=1)
    context_key: str = Field(min_length=1)
    regime_id: str = Field(min_length=1)
    regime_kind: RoutineChangeKind

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def validate_event_semantics(self) -> InteractionEventPlan:
        if self.event_type == RoutineEventType.PLACE and self.destination_location_id is None:
            raise ValueError("place event requires destination_location_id")
        if self.event_type == RoutineEventType.HANDOFF and self.recipient_actor_id is None:
            raise ValueError("handoff event requires recipient_actor_id")
        return self


class RoutinePlan(ContractModel):
    plan_id: UUID
    household_id: UUID
    start_time: datetime
    duration_days: PositiveInt
    random_seed: NonNegativeInt
    generator_version: str = Field(min_length=1)
    generation_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_object_locations: dict[UUID, UUID] = Field(min_length=1)
    events: tuple[InteractionEventPlan, ...] = Field(min_length=1)
    changes: tuple[RoutineChangeSpec, ...] = ()

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_event_order(self) -> RoutinePlan:
        order = [(event.event_time, str(event.event_id)) for event in self.events]
        if order != sorted(order):
            raise ValueError("routine events must be ordered deterministically")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("routine event ids must be unique")
        event_object_ids = {event.object_instance_id for event in self.events}
        if not event_object_ids.issubset(set(self.initial_object_locations)):
            raise ValueError("every planned object requires an explicit initial location")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)
