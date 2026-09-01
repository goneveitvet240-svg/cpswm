"""RQ4/RQ6: multi-axis mobility, because the seven documented types are not exclusive.

`项目结构一 §5` lists seven mobility profiles::

    anchored - stable - home-based mobile - multimodal
    activity-carried - wandering - regime-changing

and :mod:`.mobility_profile` implements five *different*, mutually exclusive
classes.  Neither half is right on its own, and the mismatch is the audit
finding:

    RQ4 七类移动性 -- 研究动机合理, 形式有问题 -- 接入前缺口: 七类互斥性或多轴表示;
    文档/代码统一.

The document's seven are not a partition.  A water cup can be *multimodal* and
*activity-carried* at once — two frequent places, both selected by what the
resident is doing.  Keys can be *home-based mobile* and *regime-changing* at
once, during the weeks after a move.  A toy can be *wandering* and
*activity-carried*.  Forcing one label per object therefore has to discard true
statements, and which one it discards depends on threshold order rather than on
the object.

The code's five avoid that by being a genuine partition, but they buy it by
dropping three of the document's distinctions — nothing measures activity
coupling, nothing measures whether the home location itself is moving, and
``MULTI_LOCATION`` merges *multimodal* with *wandering*.

This module resolves the mismatch the other way: **measure independent axes,
and treat the seven names as a projection of those axes rather than as the
representation**.  The projection returns a *set*, because the truth is a set.
When more than one name applies, the profile says so
(:attr:`MobilityResolution.AMBIGUOUS`) and still reports a primary label chosen
by a documented, total ordering, so downstream code has something to switch on
without the ambiguity being hidden.

Five axes, each measurable from the same audited evidence stream and each
answering a question the others cannot:

``displacement``
    How often the object moves at all.  Separates *anchored* from everything.
``return``
    Whether it comes back.  Separates habit from drift — the discriminator
    :mod:`.mobility_profile` already identified as the load-bearing one.
``spread``
    Normalized location entropy.  How many places are in play.
``context_coupling``
    Normalized mutual information ``I(context; location) / H(location)``.  This
    is the axis that makes *activity-carried* measurable: a high value means
    position is explained by what is happening, not by a marginal preference.
``regime_drift``
    Total-variation distance between the first and second half of the
    time-ordered history.  A high value means the *home itself* is moving,
    which is exactly *regime-changing* and is invisible to entropy — a settled
    two-place habit and a one-place-to-another migration can share an entropy.

RQ6's four gaps are answered alongside, because they are properties of the same
history:

    RQ6 多位置与转移 -- 正确 -- 接入前缺口: 加入停留时间, 活动条件, 开放位置质量和未决状态.

``dwell`` (停留时间)
    Median/mean/p90 hours between arriving somewhere and being seen elsewhere.
``contextual`` (活动条件)
    Per-context location distributions and per-context transition counts, so a
    transition matrix can be conditioned on the activity rather than pooled
    across activities that disagree.
``open_world`` (开放位置质量)
    Mass on locations outside the declared candidate set, kept as a first-class
    quantity instead of being renormalized away.  `§7` forbids treating an
    unseen place as impossible.
``resolution`` (未决状态)
    ``INSUFFICIENT_EVIDENCE`` / ``AMBIGUOUS`` / ``RESOLVED``.  A profiler that
    always emits a label cannot express "the evidence does not separate these",
    and `§7` requires exactly that: 无法辨识时必须保留多个候选.

Profiles are keyed on ``(household, object, person)`` with ``person=None``
meaning the pooled household view, which supplies `§5`'s 人物条件化转移矩阵
without forcing every caller to condition.

:mod:`.mobility_profile` is left untouched.  It is an audited baseline with its
own tests, and this module is the richer representation to compare it against —
not a silent replacement.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from math import log
from statistics import fmean, median
from uuid import UUID

from cpswm.contracts.habit_learning import HabitLearningEvidence

__all__ = [
    "MOBILITY_AXES_VERSION",
    "ContextualMobility",
    "DwellStatistics",
    "MobilityAxis",
    "MobilityAxisScores",
    "MobilityResolution",
    "MobilityType",
    "MobilityTypeThresholds",
    "MultiAxisMobilityProfile",
    "MultiAxisMobilityProfiler",
    "OpenWorldMass",
]

MOBILITY_AXES_VERSION = "mobility-axes@0.1"

#: Minimum observations before any axis is reported.  One observation has no
#: displacement, no return and no drift; reporting zeros for them would read as
#: "measured and found to be zero".
MINIMUM_OBSERVATIONS = 2
#: Minimum observations before ``regime_drift`` is meaningful: two per half.
MINIMUM_DRIFT_OBSERVATIONS = 4


class MobilityAxis(StrEnum):
    """The independent quantities the seven documented types project from."""

    DISPLACEMENT = "displacement"
    RETURN = "return"
    SPREAD = "spread"
    CONTEXT_COUPLING = "context_coupling"
    REGIME_DRIFT = "regime_drift"


class MobilityType(StrEnum):
    """`项目结构一 §5`'s seven names, verbatim.  Not a partition."""

    ANCHORED = "anchored"
    STABLE = "stable"
    HOME_BASED_MOBILE = "home_based_mobile"
    MULTIMODAL = "multimodal"
    ACTIVITY_CARRIED = "activity_carried"
    WANDERING = "wandering"
    REGIME_CHANGING = "regime_changing"


#: Total ordering used to pick a primary label when several apply.  Ordered by
#: how much the label changes what the robot should *do*, most consequential
#: first: if the home is moving, every other description is of a transient
#: state; if position is explained by activity, a context-conditioned
#: prediction supersedes any marginal one; and so on down to the labels that
#: only say "it rarely moves".
MOBILITY_TYPE_PRECEDENCE: tuple[MobilityType, ...] = (
    MobilityType.REGIME_CHANGING,
    MobilityType.ACTIVITY_CARRIED,
    MobilityType.WANDERING,
    MobilityType.MULTIMODAL,
    MobilityType.HOME_BASED_MOBILE,
    MobilityType.STABLE,
    MobilityType.ANCHORED,
)


class MobilityResolution(StrEnum):
    """Whether the evidence actually picks out a type."""

    #: Exactly one documented type applies.
    RESOLVED = "resolved"
    #: Several apply.  Reported as a set; the primary label is by precedence.
    AMBIGUOUS = "ambiguous"
    #: Too few observations, or no type applies.  Not a label.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class MobilityTypeThresholds:
    """Where each documented name starts.  Declared, never tuned on test data."""

    anchored_displacement: float = 0.05
    stable_displacement: float = 0.25
    stable_primary_share: float = 0.8
    home_primary_share: float = 0.4
    return_floor: float = 0.6
    multimodal_spread: float = 0.5
    wandering_spread: float = 0.8
    coupling_floor: float = 0.5
    drift_floor: float = 0.5
    frequent_coverage: float = 0.9

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if self.anchored_displacement > self.stable_displacement:
            raise ValueError("anchored_displacement must not exceed stable_displacement")
        if self.multimodal_spread > self.wandering_spread:
            raise ValueError("multimodal_spread must not exceed wandering_spread")


@dataclass(frozen=True, slots=True)
class MobilityAxisScores:
    """The five axes.  ``None`` means *not measurable*, never *zero*."""

    displacement: float | None = None
    return_rate: float | None = None
    spread: float | None = None
    context_coupling: float | None = None
    regime_drift: float | None = None

    def as_mapping(self) -> dict[MobilityAxis, float | None]:
        return {
            MobilityAxis.DISPLACEMENT: self.displacement,
            MobilityAxis.RETURN: self.return_rate,
            MobilityAxis.SPREAD: self.spread,
            MobilityAxis.CONTEXT_COUPLING: self.context_coupling,
            MobilityAxis.REGIME_DRIFT: self.regime_drift,
        }

    @property
    def measured_axes(self) -> tuple[MobilityAxis, ...]:
        return tuple(axis for axis, value in self.as_mapping().items() if value is not None)


@dataclass(frozen=True, slots=True)
class DwellStatistics:
    """RQ6 停留时间: how long the object stays put before it is seen elsewhere."""

    samples: int = 0
    median_hours: float | None = None
    mean_hours: float | None = None
    p90_hours: float | None = None

    @property
    def measured(self) -> bool:
        return self.samples > 0


@dataclass(frozen=True, slots=True)
class ContextualMobility:
    """RQ6 活动条件: the same history, split by context instead of pooled."""

    location_distribution: Mapping[str, Mapping[UUID, float]] = field(default_factory=dict)
    transition_counts: Mapping[str, Mapping[tuple[UUID, UUID], int]] = field(default_factory=dict)
    observation_counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def contexts(self) -> tuple[str, ...]:
        return tuple(sorted(self.location_distribution))

    def primary_location(self, context: str) -> UUID | None:
        distribution = self.location_distribution.get(context)
        if not distribution:
            return None
        return min(distribution.items(), key=lambda item: (-item[1], str(item[0])))[0]

    @property
    def contexts_disagree(self) -> bool:
        """Whether two contexts prefer different places.

        The reason a pooled transition matrix is not enough: when this is true,
        the pooled matrix describes an average of behaviours that never occurs.
        """

        primaries = {self.primary_location(context) for context in self.contexts}
        primaries.discard(None)
        return len(primaries) > 1


@dataclass(frozen=True, slots=True)
class OpenWorldMass:
    """RQ6 开放位置质量: mass that fell outside the declared candidate set."""

    declared_locations: tuple[UUID, ...] = ()
    open_location_mass: float = 0.0
    open_location_ids: tuple[UUID, ...] = ()
    undecided_mass: float = 0.0

    @property
    def is_open_world(self) -> bool:
        return bool(self.declared_locations)

    @property
    def accounted_mass(self) -> float:
        """Mass on declared, confidently-observed locations."""

        return max(0.0, 1.0 - self.open_location_mass - self.undecided_mass)


@dataclass(frozen=True, slots=True)
class MultiAxisMobilityProfile:
    """One ``(household, object, person)`` cell's mobility, as axes plus a projection."""

    household_id: UUID
    object_instance_id: UUID
    person_id: str | None
    observation_count: int
    location_distribution: Mapping[UUID, float]
    primary_location_id: UUID | None
    primary_share: float | None
    frequent_location_ids: tuple[UUID, ...]
    axes: MobilityAxisScores
    dwell: DwellStatistics
    contextual: ContextualMobility
    open_world: OpenWorldMass
    transition_counts: Mapping[tuple[UUID, UUID], int]
    applicable_types: tuple[MobilityType, ...]
    primary_type: MobilityType | None
    resolution: MobilityResolution
    model_version: str = MOBILITY_AXES_VERSION

    @property
    def is_ambiguous(self) -> bool:
        return self.resolution is MobilityResolution.AMBIGUOUS

    def summary(self) -> dict[str, object]:
        return {
            "person_id": self.person_id,
            "observation_count": self.observation_count,
            "primary_location_id": (
                None if self.primary_location_id is None else str(self.primary_location_id)
            ),
            "primary_share": None if self.primary_share is None else repr(self.primary_share),
            "axes": {
                axis.value: (None if value is None else repr(value))
                for axis, value in self.axes.as_mapping().items()
            },
            "dwell_median_hours": (
                None if self.dwell.median_hours is None else repr(self.dwell.median_hours)
            ),
            "contexts": list(self.contextual.contexts),
            "contexts_disagree": self.contextual.contexts_disagree,
            "open_location_mass": repr(self.open_world.open_location_mass),
            "undecided_mass": repr(self.open_world.undecided_mass),
            "applicable_types": [item.value for item in self.applicable_types],
            "primary_type": None if self.primary_type is None else self.primary_type.value,
            "resolution": self.resolution.value,
            "model_version": self.model_version,
        }


@dataclass
class _History:
    times: list[datetime] = field(default_factory=list)
    locations: list[UUID] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    undecided_weight: float = 0.0


class MultiAxisMobilityProfiler:
    """Accumulate mobility evidence and report axes rather than one label.

    The learning firewall is the same as everywhere else in M17: a record whose
    effective training weight is zero — a model prediction, above all — cannot
    shape a profile.
    """

    def __init__(
        self,
        *,
        thresholds: MobilityTypeThresholds | None = None,
        declared_locations: Sequence[UUID] | None = None,
        undecided_weight_ceiling: float = 0.5,
        model_version: str = MOBILITY_AXES_VERSION,
    ) -> None:
        if not 0.0 <= undecided_weight_ceiling < 1.0:
            raise ValueError("undecided_weight_ceiling must lie in [0, 1)")
        self._thresholds = thresholds or MobilityTypeThresholds()
        self._declared = tuple(dict.fromkeys(declared_locations or ()))
        self._undecided_ceiling = undecided_weight_ceiling
        self._model_version = model_version
        self._histories: dict[tuple[UUID, UUID, str | None], _History] = defaultdict(_History)

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def thresholds(self) -> MobilityTypeThresholds:
        return self._thresholds

    # -- learning ------------------------------------------------------------

    def update(self, evidence: HabitLearningEvidence) -> bool:
        """Apply one record to the pooled cell and to each resident's cell.

        Returns ``False`` when the record is filtered out by the firewall.
        """

        weight = evidence.effective_training_weight
        if weight <= 0.0:
            return False
        key_base = (evidence.metadata.household_id, evidence.object_instance_id)
        self._insert(self._histories[(*key_base, None)], evidence, weight)
        for actor, probability in evidence.actor_posterior.items():
            if probability <= 0.0:
                continue
            self._insert(self._histories[(*key_base, actor)], evidence, weight * probability)
        return True

    def update_all(self, records: Iterable[HabitLearningEvidence]) -> int:
        return sum(1 for record in records if self.update(record))

    def _insert(self, history: _History, evidence: HabitLearningEvidence, weight: float) -> None:
        # Order matters for transitions, returns, drift and dwell, so insert by
        # event time rather than by arrival order.
        position = len(history.times)
        while position > 0 and history.times[position - 1] > evidence.event_time:
            position -= 1
        history.times.insert(position, evidence.event_time)
        history.locations.insert(position, evidence.location_id)
        history.contexts.insert(position, evidence.context_key)
        history.weights.insert(position, weight)
        if 0.0 < evidence.effective_training_weight <= self._undecided_ceiling:
            history.undecided_weight += weight

    # -- reporting -----------------------------------------------------------

    def profile(
        self,
        *,
        household_id: UUID,
        object_instance_id: UUID,
        person_id: str | None = None,
    ) -> MultiAxisMobilityProfile:
        history = self._histories.get((household_id, object_instance_id, person_id))
        if history is None or not history.locations:
            return self._empty(household_id, object_instance_id, person_id)

        total = sum(history.weights)
        distribution: dict[UUID, float] = defaultdict(float)
        for location, weight in zip(history.locations, history.weights, strict=True):
            distribution[location] += weight / total
        ranked = sorted(distribution.items(), key=lambda item: (-item[1], str(item[0])))
        primary_location_id, primary_share = ranked[0]

        frequent: list[UUID] = []
        covered = 0.0
        for location, share in ranked:
            frequent.append(location)
            covered += share
            if covered >= self._thresholds.frequent_coverage:
                break

        axes = self._axes(history, dict(distribution), primary_location_id)
        dwell = _dwell(history)
        contextual = _contextual(history)
        open_world = self._open_world(dict(distribution), history, total)
        transitions = Counter(pairwise(history.locations))
        applicable, primary_type, resolution = self._project(
            axes=axes,
            primary_share=primary_share,
            frequent_count=len(frequent),
            observation_count=len(history.locations),
        )
        return MultiAxisMobilityProfile(
            household_id=household_id,
            object_instance_id=object_instance_id,
            person_id=person_id,
            observation_count=len(history.locations),
            location_distribution=dict(distribution),
            primary_location_id=primary_location_id,
            primary_share=primary_share,
            frequent_location_ids=tuple(frequent),
            axes=axes,
            dwell=dwell,
            contextual=contextual,
            open_world=open_world,
            transition_counts=dict(transitions),
            applicable_types=applicable,
            primary_type=primary_type,
            resolution=resolution,
            model_version=self._model_version,
        )

    def profiled_cells(self) -> tuple[tuple[UUID, UUID, str | None], ...]:
        def _key(cell: tuple[UUID, UUID, str | None]) -> tuple[str, str, str]:
            return (str(cell[0]), str(cell[1]), str(cell[2]))

        return tuple(sorted(self._histories, key=_key))

    def _empty(
        self,
        household_id: UUID,
        object_instance_id: UUID,
        person_id: str | None,
    ) -> MultiAxisMobilityProfile:
        return MultiAxisMobilityProfile(
            household_id=household_id,
            object_instance_id=object_instance_id,
            person_id=person_id,
            observation_count=0,
            location_distribution={},
            primary_location_id=None,
            primary_share=None,
            frequent_location_ids=(),
            axes=MobilityAxisScores(),
            dwell=DwellStatistics(),
            contextual=ContextualMobility(),
            open_world=OpenWorldMass(declared_locations=self._declared),
            transition_counts={},
            applicable_types=(),
            primary_type=None,
            resolution=MobilityResolution.INSUFFICIENT_EVIDENCE,
            model_version=self._model_version,
        )

    # -- axes ----------------------------------------------------------------

    def _axes(
        self,
        history: _History,
        distribution: Mapping[UUID, float],
        primary_location_id: UUID,
    ) -> MobilityAxisScores:
        locations = history.locations
        if len(locations) < MINIMUM_OBSERVATIONS:
            return MobilityAxisScores(spread=_spread(distribution))
        pairs = list(pairwise(locations))
        displacement = sum(1 for left, right in pairs if left != right) / len(pairs)
        return MobilityAxisScores(
            displacement=displacement,
            return_rate=_return_rate(locations, primary_location_id),
            spread=_spread(distribution),
            context_coupling=_context_coupling(history),
            regime_drift=_regime_drift(history),
        )

    def _open_world(
        self,
        distribution: Mapping[UUID, float],
        history: _History,
        total: float,
    ) -> OpenWorldMass:
        if not self._declared:
            return OpenWorldMass(
                declared_locations=(),
                undecided_mass=history.undecided_weight / total if total > 0 else 0.0,
            )
        declared = set(self._declared)
        open_ids = tuple(
            sorted((location for location in distribution if location not in declared), key=str)
        )
        open_mass = sum(distribution[location] for location in open_ids)
        return OpenWorldMass(
            declared_locations=self._declared,
            open_location_mass=open_mass,
            open_location_ids=open_ids,
            undecided_mass=history.undecided_weight / total if total > 0 else 0.0,
        )

    # -- projection onto the documented seven --------------------------------

    def _project(
        self,
        *,
        axes: MobilityAxisScores,
        primary_share: float,
        frequent_count: int,
        observation_count: int,
    ) -> tuple[tuple[MobilityType, ...], MobilityType | None, MobilityResolution]:
        if observation_count < MINIMUM_OBSERVATIONS or axes.displacement is None:
            return ((), None, MobilityResolution.INSUFFICIENT_EVIDENCE)
        t = self._thresholds
        applicable: set[MobilityType] = set()

        if axes.displacement <= t.anchored_displacement:
            applicable.add(MobilityType.ANCHORED)
        if axes.displacement <= t.stable_displacement and primary_share >= t.stable_primary_share:
            applicable.add(MobilityType.STABLE)
        if (
            axes.displacement > t.stable_displacement
            and primary_share >= t.home_primary_share
            and axes.return_rate is not None
            and axes.return_rate >= t.return_floor
        ):
            applicable.add(MobilityType.HOME_BASED_MOBILE)
        if (
            frequent_count >= 2
            and axes.spread is not None
            and axes.spread >= t.multimodal_spread
            and axes.return_rate is not None
            and axes.return_rate >= t.return_floor
        ):
            applicable.add(MobilityType.MULTIMODAL)
        if axes.context_coupling is not None and axes.context_coupling >= t.coupling_floor:
            applicable.add(MobilityType.ACTIVITY_CARRIED)
        if (
            axes.spread is not None
            and axes.spread >= t.wandering_spread
            and (axes.return_rate is None or axes.return_rate < t.return_floor)
            and (axes.regime_drift is None or axes.regime_drift < t.drift_floor)
        ):
            applicable.add(MobilityType.WANDERING)
        if axes.regime_drift is not None and axes.regime_drift >= t.drift_floor:
            applicable.add(MobilityType.REGIME_CHANGING)

        if not applicable:
            return ((), None, MobilityResolution.INSUFFICIENT_EVIDENCE)
        ordered = tuple(item for item in MOBILITY_TYPE_PRECEDENCE if item in applicable)
        resolution = (
            MobilityResolution.RESOLVED if len(ordered) == 1 else MobilityResolution.AMBIGUOUS
        )
        return (ordered, ordered[0], resolution)


# ---------------------------------------------------------------------------
# axis helpers
# ---------------------------------------------------------------------------


def _spread(distribution: Mapping[UUID, float]) -> float | None:
    """Normalized location entropy, or ``None`` when there is nothing to spread."""

    support = [value for value in distribution.values() if value > 0.0]
    if not support:
        return None
    if len(support) == 1:
        # Genuinely zero spread, which is different from *unmeasurable*.
        return 0.0
    entropy = -sum(value * log(value) for value in support)
    return entropy / log(len(support))


def _return_rate(locations: Sequence[UUID], primary_location_id: UUID) -> float | None:
    away = [index for index, location in enumerate(locations) if location != primary_location_id]
    if not away:
        return None
    returns = sum(1 for index in away if primary_location_id in locations[index + 1 :])
    return returns / len(away)


def _context_coupling(history: _History) -> float | None:
    """Normalized mutual information between context and location.

    ``I(C; L) / H(L)`` in ``[0, 1]``: 0 when the context says nothing about
    where the object is, 1 when knowing the context determines it.  This is the
    only axis that can separate *activity-carried* from a marginal preference,
    and it is the one the five-class implementation has no analogue for.
    """

    contexts = history.contexts
    locations = history.locations
    weights = history.weights
    if len({*contexts}) < 2 or len({*locations}) < 2:
        return None
    total = sum(weights)
    if total <= 0.0:
        return None
    joint: dict[tuple[str, UUID], float] = defaultdict(float)
    context_marginal: dict[str, float] = defaultdict(float)
    location_marginal: dict[UUID, float] = defaultdict(float)
    for context, location, weight in zip(contexts, locations, weights, strict=True):
        share = weight / total
        joint[(context, location)] += share
        context_marginal[context] += share
        location_marginal[location] += share
    location_entropy = -sum(
        value * log(value) for value in location_marginal.values() if value > 0.0
    )
    if location_entropy <= 0.0:
        return None
    information = 0.0
    for (context, location), share in joint.items():
        if share <= 0.0:
            continue
        information += share * log(
            share / (context_marginal[context] * location_marginal[location])
        )
    return max(0.0, min(1.0, information / location_entropy))


def _regime_drift(history: _History) -> float | None:
    """Total-variation distance between the first and second half of the history.

    Entropy cannot tell a settled two-place habit from a migration between two
    places: both spend half their observations in each.  Splitting by time can:
    the settled object looks the same in both halves, the migrating one does
    not.
    """

    locations = history.locations
    weights = history.weights
    if len(locations) < MINIMUM_DRIFT_OBSERVATIONS:
        return None
    midpoint = len(locations) // 2
    first = _weighted_distribution(locations[:midpoint], weights[:midpoint])
    second = _weighted_distribution(locations[midpoint:], weights[midpoint:])
    if first is None or second is None:
        return None
    keys = set(first) | set(second)
    return 0.5 * sum(abs(first.get(key, 0.0) - second.get(key, 0.0)) for key in keys)


def _weighted_distribution(
    locations: Sequence[UUID],
    weights: Sequence[float],
) -> dict[UUID, float] | None:
    total = sum(weights)
    if total <= 0.0:
        return None
    distribution: dict[UUID, float] = defaultdict(float)
    for location, weight in zip(locations, weights, strict=True):
        distribution[location] += weight / total
    return dict(distribution)


def _dwell(history: _History) -> DwellStatistics:
    """Hours from arriving somewhere to first being seen somewhere else."""

    times = history.times
    locations = history.locations
    if len(locations) < MINIMUM_OBSERVATIONS:
        return DwellStatistics()
    durations: list[float] = []
    arrival_index = 0
    for index in range(1, len(locations)):
        if locations[index] != locations[arrival_index]:
            delta = (times[index] - times[arrival_index]).total_seconds() / 3600.0
            if delta > 0.0:
                durations.append(delta)
            arrival_index = index
    if not durations:
        return DwellStatistics()
    ordered = sorted(durations)
    rank = max(0, min(len(ordered) - 1, round(0.9 * (len(ordered) - 1))))
    return DwellStatistics(
        samples=len(ordered),
        median_hours=median(ordered),
        mean_hours=fmean(ordered),
        p90_hours=ordered[rank],
    )


def _contextual(history: _History) -> ContextualMobility:
    by_context_weight: dict[str, dict[UUID, float]] = defaultdict(lambda: defaultdict(float))
    by_context_count: dict[str, int] = defaultdict(int)
    by_context_sequence: dict[str, list[UUID]] = defaultdict(list)
    for context, location, weight in zip(
        history.contexts, history.locations, history.weights, strict=True
    ):
        by_context_weight[context][location] += weight
        by_context_count[context] += 1
        by_context_sequence[context].append(location)
    distribution = {
        context: {location: weight / sum(weights.values()) for location, weight in weights.items()}
        for context, weights in by_context_weight.items()
    }
    transitions = {
        context: dict(Counter(pairwise(sequence)))
        for context, sequence in by_context_sequence.items()
    }
    return ContextualMobility(
        location_distribution=distribution,
        transition_counts=transitions,
        observation_counts=dict(by_context_count),
    )
