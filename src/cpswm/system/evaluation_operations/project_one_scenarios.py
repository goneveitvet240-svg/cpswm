"""Deterministic controlled scenarios with exact ground truth (阶段 3, 最小集).

Ten scenarios, each with a fixed sequence and no random number generator, so
every error, every true change and every detection delay is measured against a
known answer rather than an estimate.  Multi-seed randomized variants build on
these definitions and are added once the fixed-threshold ablation (阶段 6) has
a stable reading.

Two conventions make the truth usable:

* ``expected_location`` is where the owner's *true* habit would put the object
  on that day.  An event whose observed location differs from it is an anomaly
  the method is supposed to notice, whether or not it marks a regime change.
* ``true_change_point`` is set on the first day of a genuinely new regime only.
  Transient disturbances, context switches and observation gaps are explicitly
  *not* change points — those scenarios exist to catch false alarms.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .dataset_adapters import InMemoryAdapter
from .project_one_dataset import (
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
)

__all__ = [
    "SCENARIO_NAMES",
    "SCENARIO_VERSION",
    "ProjectOneScenario",
    "ScenarioDay",
    "build_all_scenarios",
    "build_scenario",
    "build_stream",
]

SCENARIO_VERSION = "project-one-controlled-scenarios@0.1"

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
    change_cause: str | None = None


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
            change_cause="transient",
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
            change_cause="owner_habit",
        )
    )
    days.extend(ScenarioDay("desk", "desk", regime_id="regime-1") for _ in range(12))
    return tuple(days)


def _recurring_regime() -> tuple[ScenarioDay, ...]:
    days = [ScenarioDay("dining_table", "dining_table") for _ in range(10)]
    days.append(
        ScenarioDay(
            "desk", "desk", regime_id="regime-1", change_point=True, change_cause="owner_habit"
        )
    )
    days.extend(ScenarioDay("desk", "desk", regime_id="regime-1") for _ in range(9))
    days.append(
        ScenarioDay(
            "dining_table",
            "dining_table",
            regime_id="regime-0",
            change_point=True,
            change_cause="regime_recurrence",
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
            change_cause="context_switch",
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
                change_cause="guest" if guest_day else None,
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
                change_cause="owner_habit" if index == 14 else None,
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
            change_cause="owner_habit",
        )
    )
    days.extend(ScenarioDay("balcony", "balcony", regime_id="regime-1") for _ in range(11))
    return tuple(days)


_Builder = Callable[[], tuple[ScenarioDay, ...]]

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
    """Build one named scenario."""

    try:
        capability, builder = _BUILDERS[name]
    except KeyError as error:
        raise ValueError(f"unknown scenario {name!r}") from error
    return ProjectOneScenario(name=name, capability=capability, days=builder())


def _records_and_truth(
    scenario: ProjectOneScenario,
) -> tuple[list[ProjectOneDatasetRecord], list[ProjectOneGroundTruth]]:
    records: list[ProjectOneDatasetRecord] = []
    truths: list[ProjectOneGroundTruth] = []
    for index, day in enumerate(scenario.days):
        event_id = f"{scenario.name}-{index:03d}"
        records.append(
            ProjectOneDatasetRecord(
                stream_id=scenario.name,
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
                stream_id=scenario.name,
                event_id=event_id,
                expected_location=day.expected_location,
                true_regime_id=day.regime_id,
                true_change_point=day.change_point,
                true_change_cause=day.change_cause,
            )
        )
    return records, truths


def build_stream(name: str) -> tuple[ProjectOneStream, ProjectOneTruthSet]:
    """Build one scenario as a validated stream plus its evaluator truth."""

    scenario = build_scenario(name)
    records, truths = _records_and_truth(scenario)
    adapter = InMemoryAdapter(
        records,
        truths,
        source=SCENARIO_VERSION,
        source_version="0.1",
        preprocessing={"generator": "deterministic", "rng": "none"},
    )
    return adapter.load(stream_id=name, split="controlled")


def build_all_scenarios(
    names: Sequence[str] | None = None,
) -> tuple[tuple[ProjectOneStream, ProjectOneTruthSet], ...]:
    """Build every controlled scenario, in declaration order."""

    return tuple(build_stream(name) for name in (names or SCENARIO_NAMES))
