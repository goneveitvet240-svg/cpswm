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
    handoff_recipient_actor_id: UUID | None = None
    handoff_location_id: UUID | None = None

    @model_validator(mode="after")
    def validate_handoff(self) -> ObjectRoutineSpec:
        if (self.handoff_recipient_actor_id is None) != (self.handoff_location_id is None):
            raise ValueError("routine handoff recipient and location must be declared together")
        if self.handoff_recipient_actor_id == self.default_actor_id:
            raise ValueError("routine handoff recipient must differ from the initial actor")
        return self


class RoutineChangeSpec(ContractModel):
    change_id: UUID
    kind: RoutineChangeKind
    object_instance_id: UUID
    start_day: NonNegativeInt
    target_location_id: UUID
    end_day: int | None = Field(default=None, ge=0)
    actor_override_id: UUID | None = None
    handoff_recipient_actor_override_id: UUID | None = None
    handoff_location_override_id: UUID | None = None
    transition_days: PositiveInt = 1
    period_days: PositiveInt = 1

    @model_validator(mode="after")
    def validate_change(self) -> RoutineChangeSpec:
        if self.end_day is not None and self.end_day < self.start_day:
            raise ValueError("end_day must be >= start_day")
        if self.kind == RoutineChangeKind.GUEST_CONTAMINATION and self.actor_override_id is None:
            raise ValueError("guest contamination requires actor_override_id")
        if (self.handoff_recipient_actor_override_id is None) != (
            self.handoff_location_override_id is None
        ):
            raise ValueError("change handoff recipient and location must be declared together")
        if (
            self.handoff_recipient_actor_override_id is not None
            and self.handoff_recipient_actor_override_id == self.actor_override_id
        ):
            raise ValueError("change handoff recipient must differ from the initial actor")
        return self


class RoutineGenerationConfig(ContractModel):
    household_id: UUID
    start_time: datetime
    duration_days: PositiveInt
    random_seed: NonNegativeInt
    object_routines: tuple[ObjectRoutineSpec, ...] = Field(min_length=1)
    changes: tuple[RoutineChangeSpec, ...] = ()
    generator_version: str = Field(default="synthetic-routines@0.3", min_length=1)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_references(self) -> RoutineGenerationConfig:
        if self.generator_version not in {
            "synthetic-routines@0.2",
            "synthetic-routines@0.3",
        }:
            raise ValueError("unsupported synthetic routine generator version")
        routine_objects = [item.object_instance_id for item in self.object_routines]
        if len(routine_objects) != len(set(routine_objects)):
            raise ValueError("object_routines must define each object once")
        unknown = {change.object_instance_id for change in self.changes} - set(routine_objects)
        if unknown:
            raise ValueError("routine change references an unknown object")
        change_ids = [change.change_id for change in self.changes]
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("routine change ids must be unique")
        if any(change.start_day >= self.duration_days for change in self.changes):
            raise ValueError("routine change starts outside the generated duration")
        if self.generator_version == "synthetic-routines@0.3":
            for routine in self.object_routines:
                changes = tuple(
                    change
                    for change in self.changes
                    if change.object_instance_id == routine.object_instance_id
                )
                can_handoff = routine.handoff_recipient_actor_id is not None or any(
                    change.handoff_recipient_actor_override_id is not None for change in changes
                )
                required_lead_minutes = 9 if can_handoff else 6
                placement_minutes = routine.placement_hour * 60 + routine.placement_minute
                if placement_minutes < required_lead_minutes:
                    raise ValueError("full interaction chain would begin before the generated day")
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
    event_chain_id: UUID | None = None
    sequence_no: NonNegativeInt = 0

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def validate_event_semantics(self) -> InteractionEventPlan:
        if self.event_type == RoutineEventType.PICK_UP:
            if self.source_location_id is None:
                raise ValueError("pick-up event requires source_location_id")
            if self.destination_location_id is not None or self.recipient_actor_id is not None:
                raise ValueError("pick-up event cannot declare destination or recipient")
        elif self.event_type == RoutineEventType.CARRY:
            if self.source_location_id is None or self.destination_location_id is None:
                raise ValueError("carry event requires source and destination locations")
            if self.recipient_actor_id is not None:
                raise ValueError("carry event cannot declare a recipient")
        elif self.event_type == RoutineEventType.PLACE:
            if self.destination_location_id is None:
                raise ValueError("place event requires destination_location_id")
            if self.recipient_actor_id is not None:
                raise ValueError("place event cannot declare a recipient")
        elif self.event_type == RoutineEventType.HANDOFF:
            if self.recipient_actor_id is None:
                raise ValueError("handoff event requires recipient_actor_id")
            if self.recipient_actor_id == self.actor_id:
                raise ValueError("handoff actor and recipient must differ")
            if (
                self.source_location_id is None
                or self.destination_location_id is None
                or self.source_location_id != self.destination_location_id
            ):
                raise ValueError("handoff event requires one unchanged handoff location")
        elif self.recipient_actor_id is not None:
            raise ValueError("only handoff events can declare a recipient")
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
        if self.generator_version not in {
            "synthetic-routines@0.2",
            "synthetic-routines@0.3",
        }:
            raise ValueError("unsupported synthetic routine plan version")
        order = [(event.event_time, str(event.event_id)) for event in self.events]
        if order != sorted(order):
            raise ValueError("routine events must be ordered deterministically")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("routine event ids must be unique")
        event_object_ids = {event.object_instance_id for event in self.events}
        if not event_object_ids.issubset(set(self.initial_object_locations)):
            raise ValueError("every planned object requires an explicit initial location")
        if self.generator_version == "synthetic-routines@0.2":
            if any(
                event.event_type != RoutineEventType.PLACE
                or event.event_chain_id is not None
                or event.sequence_no != 0
                for event in self.events
            ):
                raise ValueError("synthetic-routines@0.2 only supports legacy placement events")
            return self

        if any(event.event_chain_id is None for event in self.events):
            raise ValueError("synthetic-routines@0.3 requires every event to bind a chain")
        chains: dict[UUID, list[InteractionEventPlan]] = {}
        for event in self.events:
            assert event.event_chain_id is not None
            chains.setdefault(event.event_chain_id, []).append(event)
        for chain in chains.values():
            chain.sort(key=lambda event: event.sequence_no)
            self._validate_complete_chain(chain)
        return self

    @staticmethod
    def _validate_complete_chain(chain: list[InteractionEventPlan]) -> None:
        sequence = [event.sequence_no for event in chain]
        if sequence != list(range(len(chain))):
            raise ValueError("interaction event-chain sequence numbers must be contiguous")
        times = [event.event_time for event in chain]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("interaction event-chain times must be strictly increasing")
        immutable_fields = (
            "object_instance_id",
            "activity_key",
            "context_key",
            "regime_id",
            "regime_kind",
        )
        for field_name in immutable_fields:
            if len({getattr(event, field_name) for event in chain}) != 1:
                raise ValueError(f"interaction event chain cannot change {field_name}")

        event_types = tuple(event.event_type for event in chain)
        direct = (
            RoutineEventType.PICK_UP,
            RoutineEventType.CARRY,
            RoutineEventType.PLACE,
        )
        handoff = (
            RoutineEventType.PICK_UP,
            RoutineEventType.CARRY,
            RoutineEventType.HANDOFF,
            RoutineEventType.PLACE,
        )
        if event_types not in {direct, handoff}:
            raise ValueError(
                "complete interaction chain must be pick-up/carry/place or "
                "pick-up/carry/handoff/place"
            )
        pick_up, carry = chain[:2]
        if pick_up.actor_id != carry.actor_id:
            raise ValueError("the picking actor must perform the initial carry")
        if pick_up.source_location_id != carry.source_location_id:
            raise ValueError("pick-up and carry must share the source location")

        place = chain[-1]
        if place.source_location_id != chain[-2].destination_location_id:
            raise ValueError("place source must match the preceding event location")
        if event_types == direct:
            if place.actor_id != carry.actor_id:
                raise ValueError("direct chain must be placed by the carrying actor")
            if carry.destination_location_id != place.destination_location_id:
                raise ValueError("direct carry must end at the placement destination")
        else:
            handoff_event = chain[2]
            if carry.destination_location_id != handoff_event.source_location_id:
                raise ValueError("carry must end at the handoff location")
            if handoff_event.recipient_actor_id != place.actor_id:
                raise ValueError("handoff recipient must perform the final placement")

    @property
    def content_sha256(self) -> str:
        payload = self.model_dump(mode="json")
        if self.generator_version == "synthetic-routines@0.2":
            for event in payload["events"]:
                event.pop("event_chain_id", None)
                event.pop("sequence_no", None)
            for change in payload["changes"]:
                change.pop("handoff_recipient_actor_override_id", None)
                change.pop("handoff_location_override_id", None)
        return content_sha256(payload)
