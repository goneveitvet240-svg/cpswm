"""Many households, many residents, many objects -- in one log.

The controlled families each describe a single object belonging to a single
person.  That is the right shape for asking "can this detector see a change?",
and the wrong shape for almost everything else the project claims to be about:
a real export interleaves dozens of objects across several households, and the
failure it produces is not a crash but a pooled model that learns a
household-average habit belonging to nobody.

This generator builds that shape while keeping exact truth.  Every
``(household, resident, object)`` triple is assigned one scenario family and its
own seed, so the truth for each binding is as precise as the single-object case;
the events are then interleaved into one chronological stream, which is what an
adapter and :func:`~.project_one_stream_binding.bind_stream` actually have to
cope with.

Two choices worth naming.

**The location vocabulary is declared, not observed.**  A ``stable_habit``
triple only ever appears in one place, so a candidate set derived from its own
records would have one member and the binding would be unevaluable.  Real
operators know their household's rooms; the generator emits an explicit
candidate manifest, which is the same path a real deployment would use and which
keeps the false-alarm families in the denominator instead of quietly dropping
them.

**Seeds are derived from the triple, not from a counter.**  Two objects in the
same household must not receive correlated jitter, or the log would look like
many entities while carrying the variation of one.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from .dataset_adapters import InMemoryAdapter
from .project_one_dataset import (
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
)
from .project_one_scenarios import (
    LOCATIONS,
    SCENARIO_NAMES,
    build_randomized_scenario,
)
from .project_one_stream_binding import ProjectOneBindingKey

__all__ = [
    "HOUSEHOLD_LOG_VERSION",
    "HouseholdLog",
    "TripleAssignment",
    "build_household_log",
]

HOUSEHOLD_LOG_VERSION = "project-one-household-log@0.1"

_EPOCH = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)

#: Object names drawn in order, so a household's inventory is readable in the
#: output rather than a list of hashes.
_OBJECTS: tuple[str, ...] = (
    "cup",
    "keys",
    "book",
    "laptop",
    "remote",
    "glasses",
    "bottle",
    "charger",
    "notebook",
    "headphones",
)

_RESIDENTS: tuple[str, ...] = ("alice", "bob", "carol", "dan", "erin")

#: Upper bound on a derived per-triple seed.  Any bound works; a fixed one keeps
#: the assignment table readable.
_SEED_SPACE = 100_000


def _triple_seed(seed: int, household_id: str, actor_id: str, object_id: str) -> int:
    """A stable seed for one entity triple.

    Deliberately not ``hash()``: CPython salts string hashing per process, so a
    log built from it would differ between runs and every "deterministic under a
    seed" claim in this module would be false.
    """

    material = f"{HOUSEHOLD_LOG_VERSION}|{seed}|{household_id}|{actor_id}|{object_id}"
    digest = sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _SEED_SPACE


@dataclass(frozen=True, slots=True)
class TripleAssignment:
    """Which scenario family one entity triple was given, and with which seed."""

    household_id: str
    actor_id: str
    object_id: str
    family: str
    seed: int
    days: int

    @property
    def key(self) -> ProjectOneBindingKey:
        return ProjectOneBindingKey(
            household_id=self.household_id,
            subject_id=self.actor_id,
            object_id=self.object_id,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "household_id": self.household_id,
            "actor_id": self.actor_id,
            "object_id": self.object_id,
            "family": self.family,
            "seed": self.seed,
            "days": self.days,
        }


@dataclass(frozen=True, slots=True)
class HouseholdLog:
    """One interleaved multi-entity stream, its truth, and how it was built."""

    stream: ProjectOneStream
    truth: ProjectOneTruthSet
    assignments: tuple[TripleAssignment, ...]
    candidate_locations: Mapping[ProjectOneBindingKey, tuple[str, ...]]

    def manifest_summary(self) -> dict[str, object]:
        return {
            "generator": HOUSEHOLD_LOG_VERSION,
            "bindings": len(self.assignments),
            "events": len(self.stream),
            "households": len({item.household_id for item in self.assignments}),
            "residents": len({(item.household_id, item.actor_id) for item in self.assignments}),
            "assignments": [item.as_dict() for item in self.assignments],
        }


def build_household_log(
    *,
    households: int = 3,
    residents_per_household: int = 2,
    objects_per_resident: int = 4,
    seed: int = 0,
    families: Sequence[str] | None = None,
    stream_id: str = "household-log",
    split: str = "pilot",
) -> HouseholdLog:
    """Build one interleaved multi-entity log with exact per-binding truth."""

    if households < 1 or residents_per_household < 1 or objects_per_resident < 1:
        raise ValueError("households, residents and objects must each be at least 1")
    if residents_per_household > len(_RESIDENTS):
        raise ValueError(f"at most {len(_RESIDENTS)} residents per household are named")
    if objects_per_resident > len(_OBJECTS):
        raise ValueError(f"at most {len(_OBJECTS)} objects per resident are named")

    pool = tuple(families or SCENARIO_NAMES)
    unknown = sorted(set(pool) - set(SCENARIO_NAMES))
    if unknown:
        raise ValueError(f"unknown scenario families {unknown}")

    chooser = random.Random(f"{HOUSEHOLD_LOG_VERSION}:{seed}")
    assignments: list[TripleAssignment] = []
    records: list[ProjectOneDatasetRecord] = []
    truths: list[ProjectOneGroundTruth] = []

    for house_index in range(households):
        household_id = f"h{house_index + 1}"
        for resident_index in range(residents_per_household):
            actor_id = _RESIDENTS[resident_index]
            for object_index in range(objects_per_resident):
                object_id = _OBJECTS[object_index]
                family = chooser.choice(pool)
                # Derived from the triple so two objects in one household do not
                # share jitter; ``seed`` shifts the whole log as a unit.
                # ``hash()`` is deliberately avoided: Python salts string hashes
                # per process, so it would produce a different log on every run.
                triple_seed = _triple_seed(seed, household_id, actor_id, object_id)
                scenario = build_randomized_scenario(family, triple_seed)
                assignments.append(
                    TripleAssignment(
                        household_id=household_id,
                        actor_id=actor_id,
                        object_id=object_id,
                        family=family,
                        seed=triple_seed,
                        days=len(scenario.days),
                    )
                )
                # A per-triple minute offset keeps the interleaved stream
                # strictly ordered without pretending two households observed
                # the same object at the same instant.
                offset = timedelta(
                    minutes=(house_index * 137 + resident_index * 29 + object_index * 7)
                )
                prefix = f"{household_id}-{actor_id}-{object_id}"
                for day_index, day in enumerate(scenario.days):
                    event_id = f"{prefix}-{day_index:03d}"
                    records.append(
                        ProjectOneDatasetRecord(
                            stream_id=stream_id,
                            event_id=event_id,
                            subject_id=actor_id,
                            household_id=household_id,
                            object_id=object_id,
                            actor_id=day.actor_id if day.actor_id != "owner" else actor_id,
                            timestamp=_EPOCH + timedelta(days=day_index) + offset,
                            context_key=day.context_key,
                            context_value=day.context_value,
                            observed_location=day.observed_location,
                            observation_quality=day.observation_quality,
                        )
                    )
                    truths.append(
                        ProjectOneGroundTruth(
                            stream_id=stream_id,
                            event_id=event_id,
                            expected_location=day.expected_location,
                            true_regime_id=f"{prefix}:{day.regime_id}",
                            true_change_point=day.change_point,
                            true_change_cause=day.change_cause,
                        )
                    )

    adapter = InMemoryAdapter(
        records,
        truths,
        source=HOUSEHOLD_LOG_VERSION,
        source_version="0.1",
        preprocessing={
            "generator": "household-log",
            "seed": str(seed),
            "households": str(households),
            "residents_per_household": str(residents_per_household),
            "objects_per_resident": str(objects_per_resident),
            "bindings": str(len(assignments)),
        },
        change_labels=True,
    )
    stream, truth_set = adapter.load(stream_id=stream_id, split=split)
    return HouseholdLog(
        stream=stream,
        truth=truth_set,
        assignments=tuple(assignments),
        # Declared, not observed -- see the module docstring.
        candidate_locations={item.key: LOCATIONS for item in assignments},
    )
