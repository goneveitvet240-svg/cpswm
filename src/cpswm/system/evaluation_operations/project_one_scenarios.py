"""Controlled scenarios with exact ground truth (阶段 3).

Ten scenario families.  Each has a **deterministic anchor** -- a fixed sequence
with no random number generator, so every error, every true change and every
detection delay is measured against a known answer -- and a **seeded randomized
variant** that jitters length, change position, disturbance placement, location
assignment and observation quality while preserving the family's meaning.

The anchors are unchanged and still reachable, so every reading recorded before
multi-seed remains reproducible.  The variants exist because a single sequence
per family gives a confirmation-rate resolution of 0.2 on a five-family split:
at that granularity 0.3 and 0.4 differ by one event, and no comparison between
arms can be anything but ``UNDERPOWERED``.

Two conventions make the truth usable, and they hold for **every seed**:

* ``expected_location`` is where the owner's *true* habit would put the object
  on that day.  An event whose observed location differs from it is an anomaly
  the method is supposed to notice, whether or not it marks a regime change.
* ``true_change_point`` is set on the first day of a genuinely new regime only.
  Transient disturbances, context switches, observation gaps and guest days are
  explicitly *not* change points — those families exist to catch false alarms,
  and a randomizer that quietly labelled them would reward the behaviour the
  project is trying to suppress.

``tests/test_project_one_randomized_scenarios.py`` asserts both invariants
across every family and a sweep of seeds, rather than trusting the builders.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .dataset_adapters import InMemoryAdapter
from .project_one_dataset import (
    ChangeCause,
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
)

__all__ = [
    "LOCATIONS",
    "RANDOMIZED_SCENARIO_VERSION",
    "SCENARIO_NAMES",
    "SCENARIO_VERSION",
    "ZERO_CHANGE_POINT_FAMILIES",
    "ProjectOneScenario",
    "ScenarioDay",
    "build_all_scenarios",
    "build_randomized_scenario",
    "build_scenario",
    "build_stream",
]

SCENARIO_VERSION = "project-one-controlled-scenarios@0.1"

#: Seeded variants carry their own version so a multi-seed run can never be
#: mistaken for, or silently compared against, a single-anchor run.
RANDOMIZED_SCENARIO_VERSION = "project-one-controlled-scenarios@0.2"

#: Families whose whole purpose is to produce **no** change point.  Asserted for
#: every seed; a randomizer that drifted here would turn the false-alarm
#: guardrails into change detectors and quietly reward over-triggering.
ZERO_CHANGE_POINT_FAMILIES: frozenset[str] = frozenset(
    {
        "stable_habit",
        "periodic_habit",
        "short_disturbance",
        "context_change",
        "missing_observations",
        "biased_observation",
    }
)

_EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
_OWNER = "owner"
_GUEST = "guest"
_HOUSEHOLD = "household-1"
_OBJECT = "cup-17"

#: Candidate locations shared by every scenario, so location cardinality never
#: silently differs between arms or scenarios.
LOCATIONS: tuple[str, ...] = ("dining_table", "desk", "balcony", "shelf")


@dataclass(frozen=True, slots=True)
class ScenarioDay:
    """One deterministic day of a controlled scenario."""

    observed_location: str
    expected_location: str
    context_key: str = "weekday"
    context_value: float = 0.0
    actor_id: str = _OWNER
    observation_quality: float = 0.9
    regime_id: str = "regime-0"
    change_point: bool = False
    change_cause: ChangeCause | None = None


@dataclass(frozen=True, slots=True)
class ProjectOneScenario:
    """A named scenario: what it tests, and the exact days that test it."""

    name: str
    capability: str
    days: tuple[ScenarioDay, ...]

    def __post_init__(self) -> None:
        if len(self.days) < 4:
            raise ValueError("a scenario needs at least four days")
        for day in self.days:
            for location in (day.observed_location, day.expected_location):
                if location not in LOCATIONS:
                    raise ValueError(f"location {location!r} is outside LOCATIONS")


def _stable_habit() -> tuple[ScenarioDay, ...]:
    return tuple(ScenarioDay("dining_table", "dining_table") for _ in range(20))


def _periodic_habit() -> tuple[ScenarioDay, ...]:
    days: list[ScenarioDay] = []
    for index in range(24):
        morning = index % 2 == 0
        location = "dining_table" if morning else "desk"
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                context_key="morning" if morning else "evening",
                context_value=0.0 if morning else 1.0,
            )
        )
    return tuple(days)


def _short_disturbance() -> tuple[ScenarioDay, ...]:
    days = [ScenarioDay("dining_table", "dining_table") for _ in range(10)]
    days.append(
        ScenarioDay(
            observed_location="balcony",
            expected_location="dining_table",
            change_cause=ChangeCause.TRANSIENT,
        )
    )
    days.extend(ScenarioDay("dining_table", "dining_table") for _ in range(10))
    return tuple(days)


def _permanent_change() -> tuple[ScenarioDay, ...]:
    days = [ScenarioDay("dining_table", "dining_table") for _ in range(12)]
    days.append(
        ScenarioDay(
            observed_location="desk",
            expected_location="desk",
            regime_id="regime-1",
            change_point=True,
            change_cause=ChangeCause.OWNER_HABIT,
        )
    )
    days.extend(ScenarioDay("desk", "desk", regime_id="regime-1") for _ in range(12))
    return tuple(days)


def _recurring_regime() -> tuple[ScenarioDay, ...]:
    days = [ScenarioDay("dining_table", "dining_table") for _ in range(10)]
    days.append(
        ScenarioDay(
            "desk",
            "desk",
            regime_id="regime-1",
            change_point=True,
            change_cause=ChangeCause.OWNER_HABIT,
        )
    )
    days.extend(ScenarioDay("desk", "desk", regime_id="regime-1") for _ in range(9))
    days.append(
        ScenarioDay(
            "dining_table",
            "dining_table",
            regime_id="regime-0",
            change_point=True,
            change_cause=ChangeCause.REGIME_RECURRENCE,
        )
    )
    days.extend(ScenarioDay("dining_table", "dining_table") for _ in range(9))
    return tuple(days)


def _context_change() -> tuple[ScenarioDay, ...]:
    """The context switches; the habit does not.  Must not create a regime."""

    days = [
        ScenarioDay("dining_table", "dining_table", context_key="weekday", context_value=0.0)
        for _ in range(10)
    ]
    days.extend(
        ScenarioDay(
            "shelf",
            "shelf",
            context_key="weekend",
            context_value=1.0,
            change_cause=ChangeCause.CONTEXT_SWITCH,
        )
        for _ in range(6)
    )
    days.extend(
        ScenarioDay("dining_table", "dining_table", context_key="weekday", context_value=0.0)
        for _ in range(8)
    )
    return tuple(days)


def _missing_observations() -> tuple[ScenarioDay, ...]:
    """A gap in the log is not evidence of a move."""

    days = [ScenarioDay("dining_table", "dining_table") for _ in range(9)]
    days.extend(
        ScenarioDay("dining_table", "dining_table", observation_quality=0.55) for _ in range(3)
    )
    days.extend(ScenarioDay("dining_table", "dining_table") for _ in range(9))
    return tuple(days)


def _biased_observation() -> tuple[ScenarioDay, ...]:
    """A patrol route that under-samples one location, plus guest days."""

    days: list[ScenarioDay] = []
    for index in range(22):
        guest_day = index in {7, 8, 15}
        days.append(
            ScenarioDay(
                observed_location="balcony" if guest_day else "dining_table",
                expected_location="dining_table",
                actor_id=_GUEST if guest_day else _OWNER,
                observation_quality=0.6 if guest_day else 0.9,
                change_cause=ChangeCause.GUEST if guest_day else None,
            )
        )
    return tuple(days)


def _gradual_drift() -> tuple[ScenarioDay, ...]:
    """A deterministic schedule where ``desk`` becomes the majority on day 14."""

    table, desk = "dining_table", "desk"
    schedule = [
        table,
        table,
        table,
        table,
        table,
        table,
        desk,
        table,
        table,
        desk,
        table,
        desk,
        table,
        desk,
        desk,
        desk,
        table,
        desk,
        desk,
        desk,
        desk,
        desk,
        desk,
        desk,
    ]
    days: list[ScenarioDay] = []
    for index, location in enumerate(schedule):
        after = index >= 14
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location="desk" if after else "dining_table",
                regime_id="regime-1" if after else "regime-0",
                change_point=index == 14,
                change_cause=ChangeCause.OWNER_HABIT if index == 14 else None,
            )
        )
    return tuple(days)


def _abrupt_change() -> tuple[ScenarioDay, ...]:
    days = [ScenarioDay("shelf", "shelf") for _ in range(11)]
    days.append(
        ScenarioDay(
            "balcony",
            "balcony",
            regime_id="regime-1",
            change_point=True,
            change_cause=ChangeCause.OWNER_HABIT,
        )
    )
    days.extend(ScenarioDay("balcony", "balcony", regime_id="regime-1") for _ in range(11))
    return tuple(days)


# ---------------------------------------------------------------------------
# Seeded variants
# ---------------------------------------------------------------------------
#
# Every variant jitters four things: how long the stream is, where the
# interesting event sits, which locations play which role, and how good the
# observations are.  What it never jitters is the family's *meaning* -- a
# disturbance family stays a disturbance under every seed.
#
# Warm-up is protected explicitly.  No change or disturbance is placed before
# ``_MIN_WARMUP`` days, because an arm with three observations of history has
# nothing to be surprised by, and a randomizer that put the change on day 2
# would be measuring the baseline window rather than the detector.

#: Days of undisturbed history before anything may happen.
_MIN_WARMUP = 8

#: Days that must remain after an event, so "did it recover?" is answerable.
_MIN_TAIL = 6


def _quality(rng: random.Random, low: float = 0.85, high: float = 0.95) -> float:
    return round(rng.uniform(low, high), 4)


def _pair(rng: random.Random) -> tuple[str, str]:
    """Two distinct locations: the habitual one and the one it moves to."""

    first, second = rng.sample(LOCATIONS, 2)
    return first, second


def _stable_habit_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    home = rng.choice(LOCATIONS)
    return tuple(
        ScenarioDay(home, home, observation_quality=_quality(rng))
        for _ in range(rng.randint(18, 30))
    )


def _periodic_habit_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    morning_location, evening_location = _pair(rng)
    length = rng.randint(20, 32)
    phase = rng.randint(0, 1)
    days: list[ScenarioDay] = []
    for index in range(length):
        morning = (index + phase) % 2 == 0
        location = morning_location if morning else evening_location
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                context_key="morning" if morning else "evening",
                context_value=0.0 if morning else 1.0,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


def _short_disturbance_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    home, away = _pair(rng)
    length = rng.randint(18, 28)
    index = rng.randint(_MIN_WARMUP, length - _MIN_TAIL)
    days = [ScenarioDay(home, home, observation_quality=_quality(rng)) for _ in range(length)]
    # The habit did not move, so ``expected_location`` stays home.  That gap is
    # exactly the anomaly the arm is supposed to notice without escalating.
    days[index] = ScenarioDay(
        observed_location=away,
        expected_location=home,
        change_cause=ChangeCause.TRANSIENT,
        observation_quality=_quality(rng),
    )
    return tuple(days)


def _permanent_change_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    before, after = _pair(rng)
    length = rng.randint(22, 32)
    change = rng.randint(_MIN_WARMUP + 2, length - _MIN_TAIL - 2)
    days: list[ScenarioDay] = []
    for index in range(length):
        post = index >= change
        location = after if post else before
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                regime_id="regime-1" if post else "regime-0",
                change_point=index == change,
                change_cause=ChangeCause.OWNER_HABIT if index == change else None,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


def _recurring_regime_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    first, second = _pair(rng)
    length = rng.randint(28, 38)
    depart = rng.randint(_MIN_WARMUP, length // 2 - 2)
    ret = rng.randint(depart + 6, length - _MIN_TAIL)
    days: list[ScenarioDay] = []
    for index in range(length):
        away = depart <= index < ret
        location = second if away else first
        cause = None
        if index == depart:
            cause = ChangeCause.OWNER_HABIT
        elif index == ret:
            cause = ChangeCause.REGIME_RECURRENCE
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                regime_id="regime-1" if away else "regime-0",
                change_point=index in (depart, ret),
                change_cause=cause,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


def _context_change_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    """The context switches; the habit does not.  Must not create a regime."""

    weekday_location, weekend_location = _pair(rng)
    length = rng.randint(20, 30)
    start = rng.randint(_MIN_WARMUP, length - _MIN_TAIL - 5)
    span = rng.randint(4, 7)
    days: list[ScenarioDay] = []
    for index in range(length):
        weekend = start <= index < start + span
        location = weekend_location if weekend else weekday_location
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                context_key="weekend" if weekend else "weekday",
                context_value=1.0 if weekend else 0.0,
                change_cause=ChangeCause.CONTEXT_SWITCH if weekend else None,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


def _missing_observations_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    """A gap in the log is not evidence of a move."""

    home = rng.choice(LOCATIONS)
    length = rng.randint(18, 28)
    start = rng.randint(_MIN_WARMUP - 1, length - _MIN_TAIL - 4)
    span = rng.randint(2, 5)
    days: list[ScenarioDay] = []
    for index in range(length):
        degraded = start <= index < start + span
        days.append(
            ScenarioDay(
                observed_location=home,
                expected_location=home,
                observation_quality=(_quality(rng, 0.45, 0.6) if degraded else _quality(rng)),
            )
        )
    return tuple(days)


def _biased_observation_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    """A patrol route that under-samples, plus guest days that are not the owner."""

    home, guest_location = _pair(rng)
    length = rng.randint(20, 30)
    guest_days = set(rng.sample(range(_MIN_WARMUP - 2, length), rng.randint(2, 5)))
    days: list[ScenarioDay] = []
    for index in range(length):
        guest = index in guest_days
        days.append(
            ScenarioDay(
                observed_location=guest_location if guest else home,
                # The guest moved it; the owner's habit is untouched.
                expected_location=home,
                actor_id=_GUEST if guest else _OWNER,
                observation_quality=(_quality(rng, 0.55, 0.7) if guest else _quality(rng)),
                change_cause=ChangeCause.GUEST if guest else None,
            )
        )
    return tuple(days)


def _gradual_drift_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    """A ramp whose midpoint *is* the change point, by construction.

    The probability of the new location rises linearly across a window centred
    on ``flip``.  Labelling ``flip`` as the change point is therefore honest
    rather than chosen after the fact: it is the day the generating
    distribution crosses one half.
    """

    before, after = _pair(rng)
    length = rng.randint(24, 34)
    flip = rng.randint(_MIN_WARMUP + 2, length - _MIN_TAIL - 2)
    # The ramp must close before the stream ends, or the drift never finishes
    # and the tail still samples the old location -- which would make the
    # family indistinguishable from a noisy stable habit.
    ramp = rng.randint(4, min(8, length - 2 - flip))
    days: list[ScenarioDay] = []
    for index in range(length):
        progress = (index - (flip - ramp)) / (2.0 * ramp)
        probability = min(1.0, max(0.0, progress))
        location = after if rng.random() < probability else before
        post = index >= flip
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=after if post else before,
                regime_id="regime-1" if post else "regime-0",
                change_point=index == flip,
                change_cause=ChangeCause.OWNER_HABIT if index == flip else None,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


def _abrupt_change_random(rng: random.Random) -> tuple[ScenarioDay, ...]:
    """Same shape as a permanent change, but with no run-up at all."""

    before, after = _pair(rng)
    length = rng.randint(20, 30)
    change = rng.randint(_MIN_WARMUP, length - _MIN_TAIL - 2)
    days: list[ScenarioDay] = []
    for index in range(length):
        post = index >= change
        location = after if post else before
        days.append(
            ScenarioDay(
                observed_location=location,
                expected_location=location,
                regime_id="regime-1" if post else "regime-0",
                change_point=index == change,
                change_cause=ChangeCause.OWNER_HABIT if index == change else None,
                observation_quality=_quality(rng),
            )
        )
    return tuple(days)


_Builder = Callable[[], tuple[ScenarioDay, ...]]
_RandomBuilder = Callable[[random.Random], tuple[ScenarioDay, ...]]

_RANDOM_BUILDERS: dict[str, _RandomBuilder] = {
    "stable_habit": _stable_habit_random,
    "periodic_habit": _periodic_habit_random,
    "short_disturbance": _short_disturbance_random,
    "permanent_change": _permanent_change_random,
    "recurring_regime": _recurring_regime_random,
    "context_change": _context_change_random,
    "missing_observations": _missing_observations_random,
    "biased_observation": _biased_observation_random,
    "gradual_drift": _gradual_drift_random,
    "abrupt_change": _abrupt_change_random,
}

_BUILDERS: dict[str, tuple[str, _Builder]] = {
    "stable_habit": ("must not report a change", _stable_habit),
    "periodic_habit": ("must not treat a cycle as a new regime", _periodic_habit),
    "short_disturbance": ("must flag the anomaly without creating a regime", _short_disturbance),
    "permanent_change": ("must confirm the new habit", _permanent_change),
    "recurring_regime": ("must reactivate the earlier regime", _recurring_regime),
    "context_change": ("must separate context switch from habit change", _context_change),
    "missing_observations": ("missing observation is not a move", _missing_observations),
    "biased_observation": ("must survive patrol and guest bias", _biased_observation),
    "gradual_drift": ("must detect a slow change", _gradual_drift),
    "abrupt_change": ("must detect a sudden change", _abrupt_change),
}

SCENARIO_NAMES: tuple[str, ...] = tuple(_BUILDERS)


def build_scenario(name: str) -> ProjectOneScenario:
    """Build one named scenario's deterministic anchor."""

    try:
        capability, builder = _BUILDERS[name]
    except KeyError as error:
        raise ValueError(f"unknown scenario {name!r}") from error
    return ProjectOneScenario(name=name, capability=capability, days=builder())


def scenario_stream_id(name: str, seed: int | None) -> str:
    """Stream identity for a family and seed.

    The seed is part of the identity so a multi-seed run cannot collide with,
    or be silently pooled with, the deterministic anchor.
    """

    return name if seed is None else f"{name}@s{seed:04d}"


def build_randomized_scenario(name: str, seed: int) -> ProjectOneScenario:
    """Build one seeded variant of a scenario family.

    The RNG is seeded from ``name`` *and* ``seed``, so families are independent
    of one another at the same seed.  Seeding from the seed alone would make
    every family's jitter move together, which would look like more data while
    adding only one degree of freedom.
    """

    try:
        capability, _ = _BUILDERS[name]
        builder = _RANDOM_BUILDERS[name]
    except KeyError as error:
        raise ValueError(f"unknown scenario {name!r}") from error
    if seed < 0:
        raise ValueError("seed must be non-negative")
    days = builder(random.Random(f"{RANDOMIZED_SCENARIO_VERSION}:{name}:{seed}"))

    changes = [index for index, day in enumerate(days) if day.change_point]
    if name in ZERO_CHANGE_POINT_FAMILIES and changes:
        raise ValueError(
            f"{name} is a false-alarm family and must produce no change point, "
            f"but seed {seed} produced {changes}"
        )
    if changes and min(changes) < _MIN_WARMUP:
        raise ValueError(
            f"{name} seed {seed} placed a change point at day {min(changes)}, inside the "
            f"{_MIN_WARMUP}-day warm-up; an arm has no history to be surprised by there"
        )
    return ProjectOneScenario(name=name, capability=capability, days=days)


def _records_and_truth(
    scenario: ProjectOneScenario,
    *,
    stream_id: str,
) -> tuple[list[ProjectOneDatasetRecord], list[ProjectOneGroundTruth]]:
    records: list[ProjectOneDatasetRecord] = []
    truths: list[ProjectOneGroundTruth] = []
    for index, day in enumerate(scenario.days):
        event_id = f"{stream_id}-{index:03d}"
        records.append(
            ProjectOneDatasetRecord(
                stream_id=stream_id,
                event_id=event_id,
                subject_id=_OWNER,
                household_id=_HOUSEHOLD,
                object_id=_OBJECT,
                actor_id=day.actor_id,
                timestamp=_EPOCH + timedelta(days=index),
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
                true_regime_id=day.regime_id,
                true_change_point=day.change_point,
                true_change_cause=day.change_cause,
            )
        )
    return records, truths


def build_stream(
    name: str, *, seed: int | None = None
) -> tuple[ProjectOneStream, ProjectOneTruthSet]:
    """Build one scenario as a validated stream plus its evaluator truth.

    ``seed=None`` gives the deterministic anchor, byte-identical to every
    reading recorded before multi-seed existed.  An integer seed gives a variant
    of the same family.
    """

    stream_id = scenario_stream_id(name, seed)
    if seed is None:
        scenario = build_scenario(name)
        preprocessing = {"generator": "deterministic", "rng": "none"}
        version, source = "0.1", SCENARIO_VERSION
    else:
        scenario = build_randomized_scenario(name, seed)
        preprocessing = {
            "generator": "seeded",
            "rng": "python-random",
            "family": name,
            "seed": str(seed),
            "days": str(len(scenario.days)),
        }
        version, source = "0.2", RANDOMIZED_SCENARIO_VERSION

    records, truths = _records_and_truth(scenario, stream_id=stream_id)
    adapter = InMemoryAdapter(
        records,
        truths,
        source=source,
        source_version=version,
        preprocessing=preprocessing,
        change_labels=True,
    )
    return adapter.load(stream_id=stream_id, split="controlled")


def build_all_scenarios(
    names: Sequence[str] | None = None,
    *,
    seeds: Sequence[int] | None = None,
) -> tuple[tuple[ProjectOneStream, ProjectOneTruthSet], ...]:
    """Build the requested families, optionally once per seed.

    ``seeds=None`` reproduces the ten deterministic anchors.  Otherwise the
    result is the family x seed cross product, families in declaration order and
    seeds in the given order, so a run's stream list is a function of its
    arguments alone.
    """

    families = tuple(names or SCENARIO_NAMES)
    if seeds is None:
        return tuple(build_stream(name) for name in families)
    if not seeds:
        raise ValueError("seeds must be non-empty when supplied")
    return tuple(build_stream(name, seed=seed) for name in families for seed in seeds)
