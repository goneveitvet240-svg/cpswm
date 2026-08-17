"""Deterministic M30 routine generator for the first F0 vertical slice."""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
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
    """Generate one placement event per object and day with explicit regimes."""

    def generate(self, config: RoutineGenerationConfig) -> RoutinePlan:
        generation_config_sha256 = content_sha256(config)
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
                actor_id, destination_id, regime_id, regime_kind = self._state_for_day(
                    config.random_seed,
                    day,
                    routine,
                    changes_by_object.get(routine.object_instance_id, []),
                )
                event_time = config.start_time + timedelta(
                    days=day,
                    hours=routine.placement_hour,
                    minutes=routine.placement_minute,
                )
                event_id = content_uuid(
                    "routine-event",
                    {
                        "plan_id": plan_id,
                        "day": day,
                        "object_instance_id": routine.object_instance_id,
                        "event_time": event_time,
                        "actor_id": actor_id,
                        "source_location_id": current_locations[
                            routine.object_instance_id
                        ],
                        "destination_location_id": destination_id,
                        "activity_key": routine.activity_key,
                        "context_key": routine.context_key,
                        "regime_id": regime_id,
                        "regime_kind": regime_kind,
                    },
                )
                events.append(
                    InteractionEventPlan(
                        event_id=event_id,
                        event_time=event_time,
                        event_type=RoutineEventType.PLACE,
                        actor_id=actor_id,
                        object_instance_id=routine.object_instance_id,
                        source_location_id=current_locations[routine.object_instance_id],
                        destination_location_id=destination_id,
                        activity_key=routine.activity_key,
                        context_key=routine.context_key,
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
    ) -> tuple[UUID, UUID, str, RoutineChangeKind]:
        actor_id = routine.default_actor_id
        destination_id = routine.habitual_location_id
        regime_id = "stationary-routine"
        regime_kind = RoutineChangeKind.STATIONARY_ROUTINE

        for change in sorted(changes, key=lambda item: (item.start_day, str(item.change_id))):
            if not self._change_applies(seed, day, change):
                continue
            destination_id = change.target_location_id
            actor_id = change.actor_override_id or actor_id
            regime_id = str(change.change_id)
            regime_kind = change.kind
        return actor_id, destination_id, regime_id, regime_kind

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
