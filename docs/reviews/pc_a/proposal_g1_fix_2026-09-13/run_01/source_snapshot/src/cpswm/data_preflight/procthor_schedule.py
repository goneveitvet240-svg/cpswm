"""Deterministic D1 exogenous event scheduling, independent of a learned method.

Actors here are scheduler identities, NOT rendered human avatars. Environment
interventions must never be counted as robot-policy manipulation or perception.
Scheduled truth, release timing and event labels remain evaluator-only.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Any

REQUIRED_EVENTS = (
    "direct_move",
    "ordered_handoff",
    "unknown_actor",
    "habit_drift",
    "late_correction",
    "no_move_observation_policy_change",
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ScheduledEvent:
    event_id: str
    day: int
    tick: int
    kind: str
    instance_key: str
    actors: tuple[str, ...]
    source_location: str
    destination_location: str
    phase: str
    observation_selected: bool
    # A later release references the original capture, never edits the old record.
    release_tick: int
    correction_of: str | None = None


@dataclass(frozen=True)
class Schedule:
    schema: str
    house_id: str
    house_sha256: str
    schedule_block_id: str
    partition: str
    seed: int
    days: int
    actors: tuple[str, ...]
    instance_keys: tuple[str, ...]
    location_keys: tuple[str, ...]
    events: tuple[ScheduledEvent, ...]

    def __post_init__(self) -> None:
        # Normalize into detached immutable containers, including caller-owned lists.
        for key in ("actors", "instance_keys", "location_keys"):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        if any(type(event) is not ScheduledEvent for event in self.events):
            raise ValueError("schedule requires typed events")
        object.__setattr__(
            self, "events", tuple(replace(e, actors=tuple(e.actors)) for e in self.events)
        )

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.schema != "procthor-exogenous-schedule@1":
            raise ValueError("unsupported schedule schema")
        if self.partition not in {"train", "development"}:
            raise ValueError("training-preparation scheduler cannot open held-out partitions")
        if not self.house_id or not self.schedule_block_id or len(self.house_sha256) != 64:
            raise ValueError("house and schedule identities required")
        if any(x not in "0123456789abcdef" for x in self.house_sha256):
            raise ValueError("invalid house hash")
        if type(self.days) is not int or not 7 <= self.days <= 14 or not 3 <= len(self.actors) <= 5:
            raise ValueError("frozen D1 requires 3-5 actors and 7-14 days")
        if "unknown_actor" in self.actors:
            raise ValueError("unknown is a visible placeholder, not a simulator actor identity")
        for support in (self.actors, self.instance_keys, self.location_keys):
            if len(set(support)) != len(support) or any(not x for x in support):
                raise ValueError("duplicate or empty support")
        if len(self.instance_keys) < 2 or len(self.location_keys) < 2:
            raise ValueError("multi-instance, multi-location support required")
        known: dict[str, ScheduledEvent] = {}
        locations = {
            x: self.location_keys[i % len(self.location_keys)]
            for i, x in enumerate(self.instance_keys)
        }
        previous_tick = -1
        counts: Counter[str] = Counter()
        for event in self.events:
            for tick in (event.day, event.tick, event.release_tick):
                validate_tick(tick)
            if event.kind not in REQUIRED_EVENTS or event.event_id in known:
                raise ValueError("unknown event type or duplicate event identity")
            if (
                type(event.tick) is not int
                or event.tick <= previous_tick
                or event.tick // 100 != event.day
            ):
                raise ValueError("nonmonotone event clock/day mismatch")
            if not 0 <= event.day < self.days or event.release_tick < event.tick:
                raise ValueError("event/release outside causal clock")
            if type(event.observation_selected) is not bool:
                raise ValueError("observation selection must be explicit boolean")
            if event.phase not in {"baseline", "shifted", "recurrent"}:
                raise ValueError("unknown development phase")
            if (
                event.instance_key not in locations
                or event.source_location != locations[event.instance_key]
            ):
                raise ValueError("instance trajectory source discontinuity")
            if event.destination_location not in self.location_keys:
                raise ValueError("destination outside house support")
            if not event.actors or not set(event.actors) <= set(self.actors):
                raise ValueError("actor outside schedule")
            if event.kind == "ordered_handoff":
                if len(event.actors) < 2 or any(
                    a == b for a, b in zip(event.actors, event.actors[1:], strict=False)
                ):
                    raise ValueError("ordered handoff requires distinct adjacent custodians")
            elif len(event.actors) != 1:
                raise ValueError("non-handoff event has one responsible actor")
            if event.kind == "late_correction":
                parent = known.get(event.correction_of or "")
                if (
                    parent is None
                    or parent.instance_key != event.instance_key
                    or event.release_tick <= event.tick
                ):
                    raise ValueError(
                        "late correction needs an earlier same-instance event and delayed release"
                    )
            elif event.correction_of is not None:
                raise ValueError("only correction can name corrected event")
            if event.kind in {"late_correction", "no_move_observation_policy_change"}:
                if event.destination_location != event.source_location:
                    raise ValueError(
                        "correction/policy-only event cannot secretly move an instance"
                    )
            else:
                if (
                    event.destination_location == event.source_location
                    and event.kind != "habit_drift"
                ):
                    raise ValueError("a movement event must actually change destination")
                locations[event.instance_key] = event.destination_location
            known[event.event_id] = event
            previous_tick = event.tick
            counts[event.kind] += 1
        if set(counts) != set(REQUIRED_EVENTS):
            raise ValueError("schedule must contain all six D1 event categories")
        if set(x.day for x in self.events) != set(range(self.days)):
            raise ValueError("every simulated day needs scheduled activity")
        if not set(self.actors) <= {a for e in self.events for a in e.actors}:
            raise ValueError("declared actor never participates")
        if not set(self.instance_keys) <= {e.instance_key for e in self.events}:
            raise ValueError("declared instance never participates")


def build_schedule(
    *,
    house_id: str,
    house_sha256: str,
    schedule_block_id: str,
    seed: int,
    days: int,
    actors: tuple[str, ...],
    instance_keys: tuple[str, ...],
    location_keys: tuple[str, ...],
    partition: str = "development",
) -> Schedule:
    """Variable daily ordering/roles/instances; no labels for inference operations.

    100 discrete ticks/day are scheduling coordinates, NOT calibrated seconds.
    The scale of a run is explicit; this generator does not change formal D1 scale.
    """
    if type(seed) is not int or type(days) is not int or not 7 <= days <= 14:
        raise ValueError("explicit integer seed and frozen day range required")
    if not 3 <= len(actors) <= 5 or len(instance_keys) < 2 or len(location_keys) < 2:
        raise ValueError("D1 actor/instance/location support missing")
    rng = random.Random(seed)
    locations = {x: location_keys[i % len(location_keys)] for i, x in enumerate(instance_keys)}
    events: list[ScheduledEvent] = []
    earlier: dict[str, str] = {}
    for day in range(days):
        phase = "baseline" if day < days // 3 else "shifted" if day < 2 * days // 3 else "recurrent"
        kinds = list(REQUIRED_EVENTS)
        rng.shuffle(kinds)
        # Corrections need an earlier captured source; postpone only on first day.
        if day == 0:
            kinds.remove("late_correction")
            kinds.append("late_correction")
        for order, kind in enumerate(kinds):
            instance = instance_keys[(day + order) % len(instance_keys)]
            if kind == "late_correction":
                instance = rng.choice(sorted(earlier))
            tick = day * 100 + order * 10
            source = locations[instance]
            destination = source
            if kind not in {"late_correction", "no_move_observation_policy_change"}:
                choices = [x for x in location_keys if x != source]
                destination = choices[(day + order + (phase == "shifted")) % len(choices)]
            custodian = actors[(day + order) % len(actors)]
            if kind == "habit_drift":
                # Explicit development curriculum, not a new scientific prior:
                # the same actor returns objects to a phase-specific destination.
                custodian = actors[0]
                destination = location_keys[1 if phase == "shifted" else 0]
            role_chain: tuple[str, ...] = (custodian,)
            if kind == "ordered_handoff":
                others = [x for x in actors if x != custodian]
                role_chain = (custodian, *rng.sample(others, rng.randint(1, len(others))))
            event_id = f"{schedule_block_id}:{tick}"
            event = ScheduledEvent(
                event_id,
                day,
                tick,
                kind,
                instance,
                role_chain,
                source,
                destination,
                phase,
                kind not in {"unknown_actor", "no_move_observation_policy_change"} or day % 2 == 0,
                tick + 125 if kind == "late_correction" else tick,
                earlier.get(instance) if kind == "late_correction" else None,
            )
            events.append(event)
            if kind not in {"late_correction", "no_move_observation_policy_change"}:
                locations[instance] = destination
                earlier[instance] = event_id
    result = Schedule(
        "procthor-exogenous-schedule@1",
        house_id,
        house_sha256,
        schedule_block_id,
        partition,
        seed,
        days,
        actors,
        instance_keys,
        location_keys,
        tuple(events),
    )
    result.validate()
    return result


def event_chain(event: ScheduledEvent) -> tuple[dict[str, Any], ...]:
    """Evaluator plan with explicit ordered custody, including multi-hop handoffs."""
    if event.destination_location == event.source_location:
        return ({"kind": "no_move", "actor": event.actors[0], "location": event.source_location},)
    chain: list[dict[str, Any]] = [
        {"kind": "pick_up", "actor": event.actors[0], "location": event.source_location},
        {"kind": "carry", "actor": event.actors[0], "location": event.source_location},
    ]
    for giver, receiver in zip(event.actors, event.actors[1:], strict=False):
        chain.append(
            {
                "kind": "handoff",
                "actor": giver,
                "receiver": receiver,
                "location": event.destination_location,
            }
        )
        chain.append({"kind": "carry", "actor": receiver, "location": event.destination_location})
    chain.append(
        {"kind": "place", "actor": event.actors[-1], "location": event.destination_location}
    )
    return tuple(chain)


class ReleaseQueue:
    """Late evidence is append-only delivery of actual capture IDs, not rewritten truth."""

    def __init__(self) -> None:
        self._pending: dict[str, tuple[int, dict[str, Any]]] = {}
        self._seen: set[str] = set()
        self._clock = -1
        self._captures: set[str] = set()
        self._finished = False

    def enqueue(self, event: ScheduledEvent, capture_ref: str) -> None:
        if self._finished:
            raise ValueError("finished delivery history cannot accept new events")
        validate_tick(event.tick)
        validate_tick(event.release_tick)
        if type(event.observation_selected) is not bool:
            raise ValueError("observation selection must be boolean")
        if (
            not isinstance(capture_ref, str)
            or not capture_ref
            or event.event_id in self._seen
            or event.tick < self._clock
        ):
            raise ValueError("missing capture, repeated event, or backdated enqueue")
        if event.release_tick < event.tick:
            raise ValueError("release before occurrence")
        if event.observation_selected and capture_ref in self._captures:
            raise ValueError("capture already registered as evidence")
        self._seen.add(event.event_id)
        if event.observation_selected:
            self._captures.add(capture_ref)
            # No event type, latent actor, phase, seeds or source truth in delivery.
            self._pending[event.event_id] = (
                event.release_tick,
                {
                    "capture_ref": capture_ref,
                    "event_tick": event.tick,
                    "received_tick": event.release_tick,
                },
            )

    def release(self, tick: int) -> tuple[dict[str, Any], ...]:
        if self._finished:
            raise ValueError("finished delivery history cannot be replayed")
        validate_tick(tick)
        if tick < self._clock:
            raise ValueError("release clock cannot move backwards")
        self._clock = tick
        due = sorted(
            (when, key, value) for key, (when, value) in self._pending.items() if when <= tick
        )
        for _, key, _ in due:
            del self._pending[key]
        return tuple(dict(value) for _, _, value in due)

    def finish(self, tick: int) -> tuple[dict[str, Any], ...]:
        validate_tick(tick)
        if any(when > tick for when, _ in self._pending.values()):
            raise ValueError("cannot finish with undelivered captures")
        result = self.release(tick)
        if self._pending:
            raise ValueError("capture delivery conservation failed")
        self._finished = True
        return result


def validate_tick(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative finite integer clock required")


def validate_position(value: dict[str, float]) -> dict[str, float]:
    if set(value) != {"x", "y", "z"} or any(
        type(x) not in {int, float} or not math.isfinite(x) for x in value.values()
    ):
        raise ValueError("position requires finite x/y/z coordinates")
    return dict(value)
