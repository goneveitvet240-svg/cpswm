"""Event-derived habit-update ledger (RGRC reversible consolidation).

结构二 §4.7#5 (RGRC): long-term habit statistics must be reconstructable from a
log and reversible, so that when CHEH/ORRER revises the actor responsibility of
a hidden event (§4.7#2/ORRER: ``branch/revise/retract/rebuild``), the habit
updates *derived from that event* can be retracted without a full recompute, and
the owner model recovers to exactly the state it would have if the contaminating
event had never been attributed to the owner.

This ledger is the binding between the two: every soft-count habit update records
its ``source_event_id``.  An ORRER revision that re-attributes an event triggers
:meth:`retract_event`, which subtracts only that event's derived contributions
(cost = the event's own entries).  A full rerun instead rebuilds the projection
from every surviving entry (cost = all surviving entries).  Both reach the same
owner projection; the ledger exists to prove that equivalence and the cost gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EventDerivedUpdate:
    """One soft-count habit update, bound to the event it was derived from."""

    update_id: UUID
    source_event_id: UUID
    revision_no: int
    actor_key: str
    object_instance_id: UUID
    location_id: UUID
    weight: float
    retracted: bool = False


@dataclass
class _CostMeter:
    """Counts entry-level operations so retract vs rebuild cost is measurable."""

    operations: int = 0


@dataclass
class EventDerivedUpdateLedger:
    """Append-only, per-event-reversible ledger over owner habit soft counts.

    The owner projection is cached and maintained incrementally on ``record``
    and ``retract_event``; :meth:`rebuild_owner_projection` recomputes it from
    scratch over surviving entries for comparison.
    """

    _entries: list[EventDerivedUpdate] = field(default_factory=list)
    _retracted_events: set[UUID] = field(default_factory=set)
    # cached owner projection: (owner_key, object) -> {location: soft count}
    _owner_counts: dict[tuple[str, UUID], dict[UUID, float]] = field(default_factory=dict)

    def record(
        self,
        *,
        source_event_id: UUID,
        revision_no: int,
        actor_key: str,
        object_instance_id: UUID,
        location_id: UUID,
        weight: float,
    ) -> EventDerivedUpdate:
        if weight < 0.0:
            raise ValueError("event-derived update weight must be non-negative")
        entry = EventDerivedUpdate(
            update_id=uuid4(),
            source_event_id=source_event_id,
            revision_no=revision_no,
            actor_key=actor_key,
            object_instance_id=object_instance_id,
            location_id=location_id,
            weight=weight,
        )
        self._entries.append(entry)
        if source_event_id not in self._retracted_events:
            self._add_to_cache(entry, +1.0)
        return entry

    def retract_event(self, source_event_id: UUID) -> int:
        """RGRC targeted retract: reverse only this event's derived updates.

        Returns the number of entries reversed (the retraction cost).
        """

        if source_event_id in self._retracted_events:
            return 0
        self._retracted_events.add(source_event_id)
        reversed_count = 0
        for entry in self._entries:
            if entry.source_event_id == source_event_id and not entry.retracted:
                self._add_to_cache(entry, -1.0)
                reversed_count += 1
        # Mark entries retracted (frozen dataclass -> replace in place).
        self._entries = [
            _mark_retracted(entry) if entry.source_event_id == source_event_id else entry
            for entry in self._entries
        ]
        return reversed_count

    def owner_projection(self, *, owner_key: str, object_instance_id: UUID) -> dict[UUID, float]:
        """Cached owner soft counts (incrementally maintained)."""

        return dict(self._owner_counts.get((owner_key, object_instance_id), {}))

    def rebuild_owner_projection(
        self, *, owner_key: str, object_instance_id: UUID
    ) -> tuple[dict[UUID, float], int]:
        """Full rerun: recompute the owner projection from all surviving entries.

        Returns the projection and the rebuild cost (surviving entries scanned).
        """

        meter = _CostMeter()
        counts: dict[UUID, float] = {}
        for entry in self._entries:
            meter.operations += 1
            if entry.retracted or entry.source_event_id in self._retracted_events:
                continue
            if entry.actor_key == owner_key and entry.object_instance_id == object_instance_id:
                counts[entry.location_id] = counts.get(entry.location_id, 0.0) + entry.weight
        return counts, meter.operations

    def surviving_entry_count(self) -> int:
        return sum(1 for entry in self._entries if not entry.retracted)

    def _add_to_cache(self, entry: EventDerivedUpdate, sign: float) -> None:
        key = (entry.actor_key, entry.object_instance_id)
        table = self._owner_counts.setdefault(key, {})
        updated = table.get(entry.location_id, 0.0) + sign * entry.weight
        # Drop zeroed locations so the cached projection matches a from-log
        # rebuild, which never materialises absent locations.
        if abs(updated) < 1e-12:
            table.pop(entry.location_id, None)
        else:
            table[entry.location_id] = updated


def _mark_retracted(entry: EventDerivedUpdate) -> EventDerivedUpdate:
    if entry.retracted:
        return entry
    return EventDerivedUpdate(
        update_id=entry.update_id,
        source_event_id=entry.source_event_id,
        revision_no=entry.revision_no,
        actor_key=entry.actor_key,
        object_instance_id=entry.object_instance_id,
        location_id=entry.location_id,
        weight=entry.weight,
        retracted=True,
    )


def owner_contamination_rate(projection: dict[UUID, float], *, home_location_id: UUID) -> float:
    """Share of the owner's soft-count mass that is *not* on the home location."""

    total = sum(projection.values())
    if total <= 0.0:
        return 0.0
    return 1.0 - projection.get(home_location_id, 0.0) / total
