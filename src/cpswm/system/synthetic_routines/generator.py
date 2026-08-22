"""Deterministic M30 routine generator with versioned full event chains."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from uuid import UUID

from cpswm.system.reproducibility import content_sha256, content_uuid

from .contracts import (
    InteractionEventPlan,
    ObjectRoutineSpec,
    RoutineChangeKind,
    RoutineChangeSpec,
    RoutineEventType,
    RoutineGenerationConfig,
    RoutinePlan,
)


def _stable_rng(seed: int, *parts: object) -> random.Random:
    material = ":".join([str(seed), *(str(part) for part in parts)]).encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(material).digest(), "big"))


class SyntheticRoutineGenerator:
    """Generate legacy placements or complete object-interaction event chains."""

    def generate(self, config: RoutineGenerationConfig) -> RoutinePlan:
        generation_config_sha256 = self._generation_config_sha256(config)
        plan_id = content_uuid(
            "routine-plan",
            {
                "generator_version": config.generator_version,
                "generation_config_sha256": generation_config_sha256,
            },
        )
        changes_by_object: dict[UUID, list[RoutineChangeSpec]] = {}
        for change in config.changes:
            changes_by_object.setdefault(change.object_instance_id, []).append(change)

        events: list[InteractionEventPlan] = []
        current_locations = {
            routine.object_instance_id: routine.initial_location_id
            for routine in config.object_routines
        }
        for day in range(config.duration_days):
            for routine in config.object_routines:
                (
                    actor_id,
                    recipient_actor_id,
                    handoff_location_id,
                    destination_id,
                    regime_id,
                    regime_kind,
                ) = self._state_for_day(
                    config.random_seed,
                    day,
                    routine,
                    changes_by_object.get(routine.object_instance_id, []),
                )
                placement_time = config.start_time + timedelta(
                    days=day,
                    hours=routine.placement_hour,
                    minutes=routine.placement_minute,
                )
                source_location_id = current_locations[routine.object_instance_id]
                if config.generator_version == "synthetic-routines@0.2":
                    events.append(
                        self._legacy_placement_event(
                            plan_id=plan_id,
                            day=day,
                            placement_time=placement_time,
                            actor_id=actor_id,
                            routine=routine,
                            source_location_id=source_location_id,
                            destination_location_id=destination_id,
                            regime_id=regime_id,
                            regime_kind=regime_kind,
                        )
                    )
                else:
                    events.extend(
                        self._interaction_chain(
                            plan_id=plan_id,
                            day=day,
                            placement_time=placement_time,
                            actor_id=actor_id,
                            recipient_actor_id=recipient_actor_id,
                            handoff_location_id=handoff_location_id,
                            routine=routine,
                            source_location_id=source_location_id,
                            destination_location_id=destination_id,
                            regime_id=regime_id,
                            regime_kind=regime_kind,
                        )
                    )
                current_locations[routine.object_instance_id] = destination_id

        events.sort(key=lambda event: (event.event_time, str(event.event_id)))
        return RoutinePlan(
            plan_id=plan_id,
            household_id=config.household_id,
            start_time=config.start_time,
            duration_days=config.duration_days,
            random_seed=config.random_seed,
            generator_version=config.generator_version,
            generation_config_sha256=generation_config_sha256,
            initial_object_locations={
                routine.object_instance_id: routine.initial_location_id
                for routine in config.object_routines
            },
            events=tuple(events),
            changes=config.changes,
        )

    def _state_for_day(
        self,
        seed: int,
        day: int,
        routine: ObjectRoutineSpec,
        changes: list[RoutineChangeSpec],
    ) -> tuple[UUID, UUID | None, UUID | None, UUID, str, RoutineChangeKind]:
        actor_id = routine.default_actor_id
        recipient_actor_id = routine.handoff_recipient_actor_id
        handoff_location_id = routine.handoff_location_id
        destination_id = routine.habitual_location_id
        regime_id = "stationary-routine"
        regime_kind = RoutineChangeKind.STATIONARY_ROUTINE

        for change in sorted(changes, key=lambda item: (item.start_day, str(item.change_id))):
            if not self._change_applies(seed, day, change):
                continue
            destination_id = change.target_location_id
            actor_id = change.actor_override_id or actor_id
            if change.handoff_recipient_actor_override_id is not None:
                recipient_actor_id = change.handoff_recipient_actor_override_id
                handoff_location_id = change.handoff_location_override_id
            regime_id = str(change.change_id)
            regime_kind = change.kind
        if recipient_actor_id == actor_id:
            raise ValueError("resolved handoff recipient must differ from the initial actor")
        return (
            actor_id,
            recipient_actor_id,
            handoff_location_id,
            destination_id,
            regime_id,
            regime_kind,
        )

    @staticmethod
    def _generation_config_sha256(config: RoutineGenerationConfig) -> str:
        if config.generator_version != "synthetic-routines@0.2":
            return content_sha256(config)
        payload = config.model_dump(mode="json")
        for routine in payload["object_routines"]:
            routine.pop("handoff_recipient_actor_id", None)
            routine.pop("handoff_location_id", None)
        for change in payload["changes"]:
            change.pop("handoff_recipient_actor_override_id", None)
            change.pop("handoff_location_override_id", None)
        return content_sha256(payload)

    @staticmethod
    def _legacy_placement_event(
        *,
        plan_id: UUID,
        day: int,
        placement_time: datetime,
        actor_id: UUID,
        routine: ObjectRoutineSpec,
        source_location_id: UUID,
        destination_location_id: UUID,
        regime_id: str,
        regime_kind: RoutineChangeKind,
    ) -> InteractionEventPlan:
        payload = {
            "plan_id": plan_id,
            "day": day,
            "object_instance_id": routine.object_instance_id,
            "event_time": placement_time,
            "actor_id": actor_id,
            "source_location_id": source_location_id,
            "destination_location_id": destination_location_id,
            "activity_key": routine.activity_key,
            "context_key": routine.context_key,
            "regime_id": regime_id,
            "regime_kind": regime_kind,
        }
        return InteractionEventPlan(
            event_id=content_uuid("routine-event", payload),
            event_time=placement_time,
            event_type=RoutineEventType.PLACE,
            actor_id=actor_id,
            object_instance_id=routine.object_instance_id,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            activity_key=routine.activity_key,
            context_key=routine.context_key,
            regime_id=regime_id,
            regime_kind=regime_kind,
        )

    @staticmethod
    def _interaction_chain(
        *,
        plan_id: UUID,
        day: int,
        placement_time: datetime,
        actor_id: UUID,
        recipient_actor_id: UUID | None,
        handoff_location_id: UUID | None,
        routine: ObjectRoutineSpec,
        source_location_id: UUID,
        destination_location_id: UUID,
        regime_id: str,
        regime_kind: RoutineChangeKind,
    ) -> tuple[InteractionEventPlan, ...]:
        chain_payload = {
            "plan_id": plan_id,
            "day": day,
            "object_instance_id": routine.object_instance_id,
            "source_location_id": source_location_id,
            "destination_location_id": destination_location_id,
            "actor_id": actor_id,
            "recipient_actor_id": recipient_actor_id,
            "handoff_location_id": handoff_location_id,
            "placement_time": placement_time,
            "regime_id": regime_id,
        }
        event_chain_id = content_uuid("routine-event-chain", chain_payload)
        specs: tuple[tuple[RoutineEventType, UUID, UUID | None, UUID | None, UUID | None], ...]
        if recipient_actor_id is None:
            specs = (
                (RoutineEventType.PICK_UP, actor_id, source_location_id, None, None),
                (
                    RoutineEventType.CARRY,
                    actor_id,
                    source_location_id,
                    destination_location_id,
                    None,
                ),
                (
                    RoutineEventType.PLACE,
                    actor_id,
                    destination_location_id,
                    destination_location_id,
                    None,
                ),
            )
        else:
            if handoff_location_id is None:
                raise ValueError("handoff chain requires a handoff location")
            specs = (
                (RoutineEventType.PICK_UP, actor_id, source_location_id, None, None),
                (
                    RoutineEventType.CARRY,
                    actor_id,
                    source_location_id,
                    handoff_location_id,
                    None,
                ),
                (
                    RoutineEventType.HANDOFF,
                    actor_id,
                    handoff_location_id,
                    handoff_location_id,
                    recipient_actor_id,
                ),
                (
                    RoutineEventType.PLACE,
                    recipient_actor_id,
                    handoff_location_id,
                    destination_location_id,
                    None,
                ),
            )

        spacing = timedelta(minutes=3)
        first_time = placement_time - spacing * (len(specs) - 1)
        events: list[InteractionEventPlan] = []
        for sequence_no, (
            event_type,
            step_actor_id,
            step_source_id,
            step_destination_id,
            step_recipient_id,
        ) in enumerate(specs):
            event_time = first_time + spacing * sequence_no
            event_payload = {
                "event_chain_id": event_chain_id,
                "sequence_no": sequence_no,
                "event_time": event_time,
                "event_type": event_type,
                "actor_id": step_actor_id,
                "recipient_actor_id": step_recipient_id,
                "object_instance_id": routine.object_instance_id,
                "source_location_id": step_source_id,
                "destination_location_id": step_destination_id,
                "activity_key": routine.activity_key,
                "context_key": routine.context_key,
                "regime_id": regime_id,
                "regime_kind": regime_kind,
            }
            events.append(
                InteractionEventPlan(
                    event_id=content_uuid("routine-interaction-event", event_payload),
                    event_chain_id=event_chain_id,
                    sequence_no=sequence_no,
                    event_time=event_time,
                    event_type=event_type,
                    actor_id=step_actor_id,
                    recipient_actor_id=step_recipient_id,
                    object_instance_id=routine.object_instance_id,
                    source_location_id=step_source_id,
                    destination_location_id=step_destination_id,
                    activity_key=routine.activity_key,
                    context_key=routine.context_key,
                    regime_id=regime_id,
                    regime_kind=regime_kind,
                )
            )
        return tuple(events)

    @staticmethod
    def _change_applies(seed: int, day: int, change: RoutineChangeSpec) -> bool:
        if day < change.start_day:
            return False
        if change.end_day is not None and day > change.end_day:
            return False
        if change.kind == RoutineChangeKind.ISOLATED_ANOMALY:
            return day == change.start_day
        if change.kind in {
            RoutineChangeKind.TEMPORARY_EXCEPTION,
            RoutineChangeKind.GUEST_CONTAMINATION,
        }:
            return True
        if change.kind == RoutineChangeKind.PERIODIC_CONTEXT:
            return (day - change.start_day) % change.period_days == 0
        if change.kind == RoutineChangeKind.GRADUAL_DRIFT:
            progress = min(1.0, (day - change.start_day + 1) / change.transition_days)
            return _stable_rng(seed, change.change_id, day).random() < progress
        return True
