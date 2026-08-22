"""WS4 object mobility profiling for M17.

`项目结构一 §12` WS4 asks for *"fixed location, primary location, several
frequent locations, return patterns, transitions and location entropy"*, and
`§14` lists mobility profiling plus primary/multi-location memory as the next
two things to extend.  `§15.3` then evaluates *"primary location, Top-K frequent
locations and mobility classification"*.

Scope is deliberately ``household x object``: WS4 describes properties of the
*object*, not of a person.  Person-conditioned mobility is a natural extension
once the F0 review gate reopens the multi-person track, and is not attempted
here.

:class:`HierarchicalDirichletHabitModel` is left untouched.  It is an audited
baseline, and its pseudo-counts discard event order, which return patterns and
transitions require.  This profiler therefore consumes the same
:class:`HabitLearningEvidence` stream independently.

The classification rule below encodes one substantive claim:

    Location entropy alone cannot separate *"habitually uses three places"*
    from *"steadily migrating to a new place"*.

Both produce a similar spread.  What separates them is whether the object comes
back, so :attr:`MobilityProfile.recurrence_rate` — not entropy — is the
discriminator between ``MULTI_LOCATION`` and ``MIGRATORY``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from math import isclose, log
from uuid import UUID

from cpswm.contracts.habit_learning import HabitLearningEvidence

#: Share of observations at the primary location above which an object counts
#: as effectively fixed there.
DEFAULT_FIXED_SHARE = 0.9
#: Share above which one location dominates but exceptions still occur.
DEFAULT_PRIMARY_SHARE = 0.6
#: Recurrence below which spread is read as migration rather than as habit.
DEFAULT_RECURRENCE_FLOOR = 0.5
#: Posterior mass a Top-K frequent-location set must cover.
DEFAULT_FREQUENT_COVERAGE = 0.9


class MobilityClass(StrEnum):
    """How an object moves, per WS4."""

    #: Seen in essentially one place.
    FIXED = "fixed"
    #: One dominant place, with exceptions that return to it.
    PRIMARY_WITH_EXCEPTIONS = "primary_with_exceptions"
    #: Several habitual places; the object circulates among them.
    MULTI_LOCATION = "multi_location"
    #: Spread without return: the object is leaving its old places behind.
    MIGRATORY = "migratory"
    #: Fewer than two observations; no profile is claimed.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class MobilityProfile:
    """One object's movement profile within one household."""

    household_id: UUID
    object_instance_id: UUID
    observation_count: int
    location_distribution: dict[UUID, float]
    primary_location_id: UUID | None
    primary_share: float | None
    frequent_location_ids: tuple[UUID, ...]
    normalized_location_entropy: float | None
    recurrence_rate: float | None
    transition_counts: dict[tuple[UUID, UUID], int]
    mobility_class: MobilityClass
    model_version: str

    @property
    def distinct_location_count(self) -> int:
        return len(self.location_distribution)


def _normalized_entropy(distribution: dict[UUID, float]) -> float | None:
    """Return entropy scaled to ``[0, 1]`` by the number of observed places.

    Raw entropy is not comparable across objects seen in different numbers of
    locations, and WS4 compares objects, so the normalised form is the useful
    one.  A single observed location has no spread to report.
    """

    support = [value for value in distribution.values() if value > 0.0]
    if len(support) < 2:
        return None
    entropy = -sum(value * log(value) for value in support)
    return entropy / log(len(support))


def _recurrence_rate(sequence: list[UUID], primary_location_id: UUID) -> float | None:
    """Fraction of away-observations that are eventually followed by a return.

    This is what separates habitual circulation from migration: an object that
    visits three places and keeps coming home is not drifting, even though its
    entropy looks identical to one that never returns.
    """

    away_indices = [
        index for index, location in enumerate(sequence) if location != primary_location_id
    ]
    if not away_indices:
        return None
    returns = sum(1 for index in away_indices if primary_location_id in sequence[index + 1 :])
    return returns / len(away_indices)


@dataclass
class _ObjectHistory:
    sequence: list[UUID] = field(default_factory=list)
    weights: Counter[UUID] = field(default_factory=Counter)
    times: list[datetime] = field(default_factory=list)


class MobilityProfiler:
    """Accumulate WS4 mobility evidence from the audited evidence stream.

    The same learning firewall applies as in
    :class:`HierarchicalDirichletHabitModel`: a record whose effective training
    weight is zero — notably a model prediction — cannot shape the profile.
    """

    def __init__(
        self,
        *,
        fixed_share: float = DEFAULT_FIXED_SHARE,
        primary_share: float = DEFAULT_PRIMARY_SHARE,
        recurrence_floor: float = DEFAULT_RECURRENCE_FLOOR,
        frequent_coverage: float = DEFAULT_FREQUENT_COVERAGE,
        model_version: str = "mobility-profile@0.1",
    ) -> None:
        if not 0.0 < primary_share <= fixed_share <= 1.0:
            raise ValueError("thresholds must satisfy 0 < primary_share <= fixed_share <= 1")
        if not 0.0 <= recurrence_floor <= 1.0:
            raise ValueError("recurrence_floor must be a probability")
        if not 0.0 < frequent_coverage <= 1.0:
            raise ValueError("frequent_coverage must be in (0, 1]")
        self._fixed_share = fixed_share
        self._primary_share = primary_share
        self._recurrence_floor = recurrence_floor
        self._frequent_coverage = frequent_coverage
        self._model_version = model_version
        self._histories: dict[tuple[UUID, UUID], _ObjectHistory] = defaultdict(_ObjectHistory)

    @property
    def model_version(self) -> str:
        return self._model_version

    def update(self, evidence: HabitLearningEvidence) -> bool:
        """Apply one evidence record. Returns ``False`` when it is filtered out."""

        weight = evidence.effective_training_weight
        if weight <= 0.0:
            return False
        key = (evidence.metadata.household_id, evidence.object_instance_id)
        history = self._histories[key]
        # Order matters for transitions and returns, so insert by event time
        # rather than by arrival order.
        position = len(history.times)
        while position > 0 and history.times[position - 1] > evidence.event_time:
            position -= 1
        history.times.insert(position, evidence.event_time)
        history.sequence.insert(position, evidence.location_id)
        history.weights[evidence.location_id] += weight
        return True

    def update_all(self, records: Iterable[HabitLearningEvidence]) -> int:
        return sum(1 for record in records if self.update(record))

    def profile(self, *, household_id: UUID, object_instance_id: UUID) -> MobilityProfile:
        history = self._histories.get((household_id, object_instance_id))
        if history is None or not history.sequence:
            return MobilityProfile(
                household_id=household_id,
                object_instance_id=object_instance_id,
                observation_count=0,
                location_distribution={},
                primary_location_id=None,
                primary_share=None,
                frequent_location_ids=(),
                normalized_location_entropy=None,
                recurrence_rate=None,
                transition_counts={},
                mobility_class=MobilityClass.INSUFFICIENT_EVIDENCE,
                model_version=self._model_version,
            )

        total_weight = sum(history.weights.values())
        distribution = {
            location: weight / total_weight for location, weight in history.weights.items()
        }
        if not isclose(sum(distribution.values()), 1.0, abs_tol=1e-9):
            raise ValueError("mobility distribution failed to normalise")

        # Ties break on UUID so identical evidence always yields the same
        # primary location, which matters for reproducible evaluation.
        ranked = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
        primary_location_id, primary_share = ranked[0]

        frequent: list[UUID] = []
        covered = 0.0
        for location, share in ranked:
            frequent.append(location)
            covered += share
            if covered >= self._frequent_coverage:
                break

        entropy = _normalized_entropy(distribution)
        recurrence = _recurrence_rate(history.sequence, primary_location_id)
        transitions = Counter(
            (source, destination) for source, destination in pairwise(history.sequence)
        )

        return MobilityProfile(
            household_id=household_id,
            object_instance_id=object_instance_id,
            observation_count=len(history.sequence),
            location_distribution=distribution,
            primary_location_id=primary_location_id,
            primary_share=primary_share,
            frequent_location_ids=tuple(frequent),
            normalized_location_entropy=entropy,
            recurrence_rate=recurrence,
            transition_counts=dict(transitions),
            mobility_class=self._classify(
                observation_count=len(history.sequence),
                distinct_locations=len(distribution),
                primary_share=primary_share,
                recurrence_rate=recurrence,
            ),
            model_version=self._model_version,
        )

    def _classify(
        self,
        *,
        observation_count: int,
        distinct_locations: int,
        primary_share: float,
        recurrence_rate: float | None,
    ) -> MobilityClass:
        if observation_count < 2:
            return MobilityClass.INSUFFICIENT_EVIDENCE
        if distinct_locations == 1 or primary_share >= self._fixed_share:
            return MobilityClass.FIXED
        # Below this point the object is spread over places.  Entropy cannot
        # say whether that spread is habit or drift; only returning can.
        if recurrence_rate is not None and recurrence_rate < self._recurrence_floor:
            return MobilityClass.MIGRATORY
        if primary_share >= self._primary_share:
            return MobilityClass.PRIMARY_WITH_EXCEPTIONS
        return MobilityClass.MULTI_LOCATION

    def profiled_objects(self) -> tuple[tuple[UUID, UUID], ...]:
        return tuple(sorted(self._histories))
