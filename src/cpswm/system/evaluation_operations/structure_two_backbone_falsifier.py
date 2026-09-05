"""Backbone-scale chained falsifier for the Structure Two typed RBPF.

Protocol: ``docs/结构二/方向结构二_骨干尺度证伪器协议_v0.1.md``.

This module replaces ``structure_two_particle_falsifier`` as the instrument for
the unified inference backbone.  The differences that matter are structural:

*   the latent object is a chain over ``G`` observation gaps, not a static state,
    so the event chain ``H_t``, ordered roles ``R_t``, instance ``I_t``, cause
    ``C_t``, regime destination ``Z_t``, run length ``r_t`` and lineage ``V_t``
    all grow with ``G``;
*   every particle carries a real analytic block
    ``S_t = (alpha, A, b, Lambda, xi)`` whose updates are driven by observations,
    so Rao-Blackwellization and sampled-theta particle filtering are genuinely
    different algorithms;
*   cost is recorded by a single instrumentation layer, and the exact enumerator
    refuses to run for an approximate arm.

Nothing here establishes paper benefit.  It establishes a place where the three
backbone claims (RB gain, typed-revision gain, amortized-proposal gain) can be
measured at all.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, overload

PROTOCOL_ID: Final = "structure-two-backbone-falsifier@0.1"
TASK7_PROTOCOL_ID: Final = "structure-two-windowed-late-correction@0.3"
TASK7_CONDITIONAL_PROTOCOL_ID: Final = "structure-two-windowed-late-correction@0.4"
TASK8_PROTOCOL_ID: Final = "structure-two-relative-probability-joint-coupling@0.3"
TASK7_CHECKPOINT_FORMAT_ID: Final = "structure-two-window-checkpoint@0.2"
UNRESOLVED_KEY: Final = "__unresolved__"
UNRESOLVED_PRIOR: Final = 0.02
RELATIVE_PROBABILITY_SOFT_COUPLING_NATS: Final = 1.5
MIN_MEASURABLE_FACTORIZATION_TV: Final = 0.01
MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE: Final = 0.01
MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE: Final = 0.001
TASK7_BELIEF_AXIS_TV_TOLERANCE: Final = 0.10
TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE: Final = 0.10
TASK7_ACTOR_MARGINAL_TV_TOLERANCE: Final = TASK7_BELIEF_AXIS_TV_TOLERANCE
TASK7_MAX_LIVE_ITEMS_PER_WINDOW_UNIT: Final = 12
TASK8_VERIFY_COST: Final = 0.12
TASK8_UNRESOLVED_SEVERITY: Final = 0.80
TASK8_HANDOFF_ACTOR_SEVERITY: Final = 1.0
TASK8_REGIME_HABIT_SEVERITY: Final = 0.60

FEATURE_DIM: Final = 3
PLACEMENT_BINS: Final = 6
NOISE_VARIANCE: Final = 0.25
RIDGE_LAMBDA: Final = 1.0
DIRICHLET_PRIOR: Final = 0.5
PLACEMENT_BIN_CENTRES: Final = (-2.0, -1.2, -0.4, 0.4, 1.2, 2.0)
LOCATION_COST_WEIGHT: Final = 1.0
ACTOR_COST_WEIGHT: Final = 1.5
ACTION_QUERY_FEATURES: Final = (1.0, 0.0, 1.0)


class Actor(StrEnum):
    OWNER = "owner"
    FAMILY = "family"
    GUEST = "guest"
    ROBOT = "robot"
    UNKNOWN = "unknown_actor"


class Instance(StrEnum):
    TARGET = "target_instance"
    DECOY = "decoy_instance"
    UNKNOWN = "unknown_instance"


class Mechanism(StrEnum):
    DIRECT = "direct"
    HANDOFF = "handoff"


class Cause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    IDENTITY = "identity"
    HABIT = "habit"
    NOISE = "noise"


class RegimeMove(StrEnum):
    STAY = "stay"
    CREATE = "create"
    REACTIVATE = "reactivate"
    UNRESOLVED = "unresolved"


class CallerRole(StrEnum):
    """Who is asking for a computation; the exact enumerator checks this."""

    EXACT_ORACLE = "exact_oracle"
    APPROXIMATE_ARM = "approximate_arm"
    LADDER_DIAGNOSTIC = "ladder_diagnostic"


class ArmName(StrEnum):
    EXACT_ORACLE = "exact_oracle"
    SAMPLED_THETA_PF = "sampled_theta_pf"
    RBPF = "rbpf"
    TYPED_RBPF = "typed_rbpf"
    ADAPTIVE_TYPED_RBPF = "adaptive_typed_rbpf"


APPROXIMATE_ARMS: Final = frozenset(
    {
        ArmName.SAMPLED_THETA_PF,
        ArmName.RBPF,
        ArmName.TYPED_RBPF,
        ArmName.ADAPTIVE_TYPED_RBPF,
    }
)
TYPED_ARMS: Final = frozenset({ArmName.TYPED_RBPF, ArmName.ADAPTIVE_TYPED_RBPF})

ACTORS: Final = tuple(Actor)
INSTANCES: Final = tuple(Instance)
MECHANISMS: Final = tuple(Mechanism)
CAUSES: Final = tuple(Cause)


class FullEnumerationForbiddenError(RuntimeError):
    """Raised when an approximate arm reaches for the exact enumerator.

    Protocol section 3.2 bans approximate arms from internally enumerating the
    full state space, and section 3.3 requires that the ban be enforced in code
    rather than by convention.  The old instrument violated this silently: every
    "approximate" method called ``_top_states``, which scored all 360 states.
    """


class ExactEnumerationBudgetExceeded(RuntimeError):
    """The ladder measured the enumeration boundary instead of crossing it."""

    def __init__(self, gaps: int, budget: int, reached: int) -> None:
        super().__init__(
            f"G={gaps}: exact enumeration exceeded the state budget "
            f"({reached} > {budget}); this is a measured boundary, not a failure"
        )
        self.gaps = gaps
        self.budget = budget
        self.reached = reached


class CheckpointIntegrityError(RuntimeError):
    """A Task-7 checkpoint no longer matches its source stream or particle."""


class NonSelfProposalUnavailableError(RuntimeError):
    """A Task-7 proposal kernel could not draw a genuine state change."""


# ---------------------------------------------------------------------------
# Instrumentation layer (protocol section 3)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CostMeter:
    """The single place cost is recorded.  Arms never self-report."""

    arm: ArmName
    unique_state_target_evaluations: int = 0
    elementary_likelihood_evaluations: int = 0
    proposal_generation_evaluations: int = 0
    analytic_block_updates: int = 0
    resampling_events: int = 0
    particle_count: int = 0
    ancestry_window_length: int = 0
    proposal_radius_sum: int = 0
    proposal_radius_count: int = 0
    rejuvenation_proposals: int = 0
    rejuvenation_accepts: int = 0
    invalid_bridge_proposals: int = 0
    window_gap_target_evaluations: int = 0
    checkpoint_boundary_reads: int = 0
    checkpoint_bytes: int = 0
    replay_fallbacks: int = 0
    fixed_gap_reweight_evaluations: int = 0
    nonself_rejuvenation_proposals: int = 0
    self_draw_rejections: int = 0
    persistent_sequence_nodes_created: int = 0
    persistent_window_items_written: int = 0
    max_repair_live_window_items: int = 0
    untouched_suffix_items_read: int = 0
    untouched_suffix_items_copied: int = 0
    untouched_suffix_items_rehashed: int = 0
    conditional_target_checks: int = 0
    conditional_target_mismatches: int = 0
    wall_clock_seconds: float = 0.0
    peak_tracked_objects: int = 0
    _scored_keys: set[str] = field(default_factory=set)
    _started: float = 0.0

    def start(self) -> None:
        self._started = time.perf_counter()

    def stop(self) -> None:
        self.wall_clock_seconds = time.perf_counter() - self._started

    def score_state(self, key: str) -> None:
        self._scored_keys.add(key)
        self.unique_state_target_evaluations = len(self._scored_keys)

    def elementary(self, count: int = 1) -> None:
        self.elementary_likelihood_evaluations += count

    def proposal(self, count: int = 1) -> None:
        self.proposal_generation_evaluations += count

    def analytic(self, count: int = 1) -> None:
        self.analytic_block_updates += count

    def resample(self) -> None:
        self.resampling_events += 1

    def note_radius(self, radius: int) -> None:
        self.proposal_radius_sum += radius
        self.proposal_radius_count += 1

    def track_live(self, count: int) -> None:
        self.peak_tracked_objects = max(self.peak_tracked_objects, count)

    def track_repair_window(self, count: int) -> None:
        self.max_repair_live_window_items = max(self.max_repair_live_window_items, count)

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "arm": self.arm.value,
            "unique_state_target_evaluations": self.unique_state_target_evaluations,
            "elementary_likelihood_evaluations": self.elementary_likelihood_evaluations,
            "proposal_generation_evaluations": self.proposal_generation_evaluations,
            "analytic_block_updates": self.analytic_block_updates,
            "particle_count": self.particle_count,
            "resampling_events": self.resampling_events,
            "ancestry_window_length": self.ancestry_window_length,
            "peak_tracked_objects": self.peak_tracked_objects,
            "mean_proposal_radius": (
                self.proposal_radius_sum / self.proposal_radius_count
                if self.proposal_radius_count
                else 0.0
            ),
            "rejuvenation_proposals": self.rejuvenation_proposals,
            "rejuvenation_accepts": self.rejuvenation_accepts,
            "rejuvenation_acceptance_rate": (
                self.rejuvenation_accepts / self.rejuvenation_proposals
                if self.rejuvenation_proposals
                else 0.0
            ),
            "fixed_gap_reweight_evaluations": self.fixed_gap_reweight_evaluations,
            "nonself_rejuvenation_proposals": self.nonself_rejuvenation_proposals,
            "self_draw_rejections": self.self_draw_rejections,
            "persistent_sequence_nodes_created": self.persistent_sequence_nodes_created,
            "persistent_window_items_written": self.persistent_window_items_written,
            "max_repair_live_window_items": self.max_repair_live_window_items,
            "untouched_suffix_items_read": self.untouched_suffix_items_read,
            "untouched_suffix_items_copied": self.untouched_suffix_items_copied,
            "untouched_suffix_items_rehashed": self.untouched_suffix_items_rehashed,
            "conditional_target_checks": self.conditional_target_checks,
            "conditional_target_mismatches": self.conditional_target_mismatches,
            "invalid_bridge_proposals": self.invalid_bridge_proposals,
            "window_gap_target_evaluations": self.window_gap_target_evaluations,
            "checkpoint_boundary_reads": self.checkpoint_boundary_reads,
            "checkpoint_bytes": self.checkpoint_bytes,
            "replay_fallbacks": self.replay_fallbacks,
            "wall_clock_seconds": round(self.wall_clock_seconds, 6),
        }


# ---------------------------------------------------------------------------
# Latent chain: the full chi_t
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GapHypothesis:
    """One segment of the event chain covering a single observation gap."""

    mechanism: Mechanism
    giver: Actor
    receiver: Actor
    instance: Instance
    cause: Cause
    regime_move: RegimeMove
    regime_target: str | None

    @property
    def key(self) -> str:
        return "/".join(
            (
                self.mechanism.value,
                self.giver.value,
                self.receiver.value,
                self.instance.value,
                self.cause.value,
                self.regime_move.value,
                self.regime_target or "-",
            )
        )

    def ordered_roles(self, gap_index: int) -> tuple[tuple[str, str], ...]:
        """R_t for this gap: ordered, unique role -> actor bindings."""

        if self.mechanism is Mechanism.DIRECT:
            return (
                (f"g{gap_index}.pickup_actor", self.giver.value),
                (f"g{gap_index}.carrier", self.giver.value),
                (f"g{gap_index}.placer", self.receiver.value),
            )
        return (
            (f"g{gap_index}.pickup_actor", self.giver.value),
            (f"g{gap_index}.carrier", self.giver.value),
            (f"g{gap_index}.handoff_giver", self.giver.value),
            (f"g{gap_index}.handoff_receiver", self.receiver.value),
            (f"g{gap_index}.placer", self.receiver.value),
        )


@dataclass(frozen=True, slots=True)
class PersistentWindowSequence[SequenceItem](Sequence[SequenceItem]):
    """A constant-size overlay replacing one contiguous range of a base sequence.

    The object retains the untouched prefix and suffix by reference.  Creating a
    new accepted Task-7 state therefore writes only the replacement window; it
    does not concatenate, copy, scan, or hash the suffix.  Replacing the same
    range again flattens the prior overlay so lookup depth stays constant across
    rejuvenation sweeps.
    """

    base: Sequence[SequenceItem]
    start: int
    replacement: tuple[SequenceItem, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.start <= len(self.base):
            raise ValueError("persistent-window start lies outside the base")
        if self.start + len(self.replacement) > len(self.base):
            raise ValueError("persistent-window replacement exceeds the base")

    def __len__(self) -> int:
        return len(self.base)

    @overload
    def __getitem__(self, index: int) -> SequenceItem: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[SequenceItem, ...]: ...

    def __getitem__(self, index: int | slice) -> SequenceItem | tuple[SequenceItem, ...]:
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            return tuple(self[position] for position in range(start, stop, step))
        position = index if index >= 0 else len(self) + index
        if not 0 <= position < len(self):
            raise IndexError(index)
        offset = position - self.start
        if 0 <= offset < len(self.replacement):
            return self.replacement[offset]
        return self.base[position]


def _persistent_replace[SequenceItem](
    sequence: Sequence[SequenceItem],
    start: int,
    stop: int,
    replacement: Sequence[SequenceItem],
) -> PersistentWindowSequence[SequenceItem]:
    """Replace ``[start, stop)`` without retaining a tower of prior overlays."""

    if stop - start != len(replacement):
        raise ValueError("persistent replacement must preserve sequence length")
    base = sequence
    if isinstance(sequence, PersistentWindowSequence):
        prior_stop = sequence.start + len(sequence.replacement)
        if sequence.start == start and prior_stop == stop:
            base = sequence.base
    return PersistentWindowSequence(base=base, start=start, replacement=tuple(replacement))


@dataclass(frozen=True, slots=True)
class ChainHypothesis:
    """The complete discrete skeleton chi_t = (H_t, R_t, I_t, C_t, Z_t, r_t, V_t)."""

    gaps: Sequence[GapHypothesis]
    regime_timeline: Sequence[str | None]
    run_lengths: Sequence[int]

    @property
    def key(self) -> str:
        return "|".join(gap.key for gap in self.gaps)

    @property
    def event_chain(self) -> tuple[str, ...]:
        """H_t as an explicit chain, one entry per gap."""

        return tuple(
            f"pick({gap.giver.value})->carry->"
            + (f"handoff({gap.receiver.value})->" if gap.mechanism is Mechanism.HANDOFF else "")
            + f"place({gap.receiver.value},{gap.instance.value})"
            for gap in self.gaps
        )

    @property
    def ordered_actor_roles(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            binding for index, gap in enumerate(self.gaps) for binding in gap.ordered_roles(index)
        )

    @property
    def lineage(self) -> tuple[str, ...]:
        """V_t: the revision lineage, one entry per gap prefix."""

        lineage: list[str] = []
        running = "root"
        for index, gap in enumerate(self.gaps):
            running = f"{running}>g{index}:{gap.regime_move.value}"
            lineage.append(running)
        return tuple(lineage)

    @property
    def final_regime(self) -> str | None:
        return self.regime_timeline[-1] if self.regime_timeline else None

    @property
    def final_run_length(self) -> int:
        return self.run_lengths[-1] if self.run_lengths else 0

    def cell_of(self, gap_index: int) -> tuple[str, str]:
        """The (actor, regime) cell that owns gap ``gap_index``'s statistics."""

        gap = self.gaps[gap_index]
        regime = self.regime_timeline[gap_index] or "unresolved_regime"
        return (gap.receiver.value, regime)


def _regime_successors(
    cause: Cause, current: str | None, retired: tuple[str, ...], created: int
) -> tuple[tuple[RegimeMove, str | None, str | None, tuple[str, ...], int], ...]:
    """Legal (move, target, next_regime, next_retired, next_created) transitions.

    Only a habit-cause particle may create or reactivate a regime; this mirrors
    ``TypedParticleState._validate_typed_state`` in the frozen method contract,
    and it is what makes the branching factor history dependent.
    """

    options: list[tuple[RegimeMove, str | None, str | None, tuple[str, ...], int]] = [
        (RegimeMove.STAY, current, current, retired, created),
        (RegimeMove.UNRESOLVED, None, current, retired, created),
    ]
    if cause is Cause.HABIT:
        fresh = f"R{created + 1}"
        retired_after_create = retired if current is None else (*retired, current)
        options.append((RegimeMove.CREATE, fresh, fresh, retired_after_create, created + 1))
        for candidate in retired:
            remaining = tuple(item for item in retired if item != candidate)
            retired_after = remaining if current is None else (*remaining, current)
            options.append((RegimeMove.REACTIVATE, candidate, candidate, retired_after, created))
    return tuple(options)


def _actor_pairs() -> tuple[tuple[Mechanism, Actor, Actor], ...]:
    pairs: list[tuple[Mechanism, Actor, Actor]] = [
        (Mechanism.DIRECT, actor, actor) for actor in ACTORS
    ]
    pairs.extend((Mechanism.HANDOFF, giver, receiver) for giver in ACTORS for receiver in ACTORS)
    return tuple(pairs)


ACTOR_PAIRS: Final = _actor_pairs()


def iter_chains(gaps: int) -> Iterator[ChainHypothesis]:
    """Yield every legal chain of length ``gaps``.

    The branching factor is history dependent because reactivation targets only
    exist once a regime has been retired, so the total is not a clean power.
    """

    def walk(
        depth: int,
        prefix: tuple[GapHypothesis, ...],
        timeline: tuple[str | None, ...],
        runs: tuple[int, ...],
        current: str | None,
        retired: tuple[str, ...],
        created: int,
    ) -> Iterator[ChainHypothesis]:
        if depth == gaps:
            yield ChainHypothesis(gaps=prefix, regime_timeline=timeline, run_lengths=runs)
            return
        run_so_far = runs[-1] if runs else 0
        for mechanism, giver, receiver in ACTOR_PAIRS:
            for instance in INSTANCES:
                for cause in CAUSES:
                    for move, target, next_regime, next_retired, next_created in _regime_successors(
                        cause, current, retired, created
                    ):
                        gap = GapHypothesis(
                            mechanism=mechanism,
                            giver=giver,
                            receiver=receiver,
                            instance=instance,
                            cause=cause,
                            regime_move=move,
                            regime_target=target,
                        )
                        next_run = (
                            0
                            if move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}
                            else run_so_far + 1
                        )
                        yield from walk(
                            depth + 1,
                            (*prefix, gap),
                            (*timeline, next_regime),
                            (*runs, next_run),
                            next_regime,
                            next_retired,
                            next_created,
                        )

    yield from walk(0, (), (), (), "R0", (), 0)


def count_chains(gaps: int, *, budget: int = 5_000_000) -> int:
    """Measure the enumeration size without materializing likelihoods."""

    total = 0
    for _ in iter_chains(gaps):
        total += 1
        if total > budget:
            raise ExactEnumerationBudgetExceeded(gaps, budget, total)
    return total


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GapObservation:
    """What the robot actually saw across one gap, plus its reliabilities."""

    observed_mechanism: Mechanism
    observed_giver: Actor
    observed_receiver: Actor
    observed_instance: Instance
    observed_cause: Cause
    observed_regime_change: bool
    placement_bin: int
    placement_value: float
    mechanism_reliability: float
    actor_reliability: float
    instance_reliability: float
    cause_reliability: float
    regime_reliability: float


@dataclass(frozen=True, slots=True)
class BackboneScenario:
    scenario_id: str
    gaps: int
    high_attribution_ambiguity: bool
    adverse_delayed_feedback: bool
    open_world_actor: bool
    short_regime: bool
    truth: ChainHypothesis
    observations: tuple[GapObservation, ...]
    corrupt_index: int = 0
    relative_probability_coupling_nats: float = 0.0
    relative_probability_truth_model: bool = False


def _log_match(match: bool, reliability: float, alternatives: int) -> float:
    if alternatives <= 1:
        return 0.0
    if match:
        return math.log(reliability)
    return math.log((1.0 - reliability) / (alternatives - 1))


_AXIS_PRIOR: Final[dict[str, float]] = {
    Actor.OWNER.value: 0.42,
    Actor.FAMILY.value: 0.22,
    Actor.GUEST.value: 0.18,
    Actor.ROBOT.value: 0.10,
    Actor.UNKNOWN.value: 0.08,
    Instance.TARGET.value: 0.55,
    Instance.DECOY.value: 0.30,
    Instance.UNKNOWN.value: 0.15,
    Mechanism.DIRECT.value: 0.65,
    Mechanism.HANDOFF.value: 0.35,
    Cause.OBSERVATION.value: 0.24,
    Cause.ACTOR.value: 0.22,
    Cause.IDENTITY.value: 0.18,
    Cause.HABIT.value: 0.20,
    Cause.NOISE.value: 0.16,
    RegimeMove.STAY.value: 0.55,
    RegimeMove.CREATE.value: 0.18,
    RegimeMove.REACTIVATE.value: 0.15,
    RegimeMove.UNRESOLVED.value: 0.12,
}


def gap_log_prior(gap: GapHypothesis, *, relative_probability_coupling_nats: float = 0.0) -> float:
    """Unnormalised gap prior with an optional full-support interaction.

    The interaction changes relative probabilities without declaring either
    direct or handoff events illegal.  In odds form,

    ``p(handoff | cause=actor) / p(direct | cause=actor)``

    is multiplied by ``exp(relative_probability_coupling_nats)`` while the
    corresponding odds for every other cause are unchanged.  This is the soft
    H x C channel required by Task 8; it is deliberately different from the
    hard ``habit -> create/reactivate`` support rule.
    """

    if relative_probability_coupling_nats < 0.0:
        raise ValueError("relative-probability coupling strength cannot be negative")
    interaction = (
        relative_probability_coupling_nats
        if gap.cause is Cause.ACTOR and gap.mechanism is Mechanism.HANDOFF
        else 0.0
    )
    return (
        math.log(_AXIS_PRIOR[gap.mechanism.value])
        + math.log(_AXIS_PRIOR[gap.giver.value])
        + (0.0 if gap.mechanism is Mechanism.DIRECT else math.log(_AXIS_PRIOR[gap.receiver.value]))
        + math.log(_AXIS_PRIOR[gap.instance.value])
        + math.log(_AXIS_PRIOR[gap.cause.value])
        + math.log(_AXIS_PRIOR[gap.regime_move.value])
        + interaction
    )


def gap_log_likelihood(gap: GapHypothesis, observation: GapObservation, meter: CostMeter) -> float:
    """Discrete evidence terms for one gap.  Continuous terms live in S_t."""

    meter.elementary(5)
    changed = gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}
    return (
        _log_match(
            gap.mechanism is observation.observed_mechanism,
            observation.mechanism_reliability,
            len(MECHANISMS),
        )
        + _log_match(
            gap.giver is observation.observed_giver,
            observation.actor_reliability,
            len(ACTORS),
        )
        + _log_match(
            gap.receiver is observation.observed_receiver,
            observation.actor_reliability,
            len(ACTORS),
        )
        + _log_match(
            gap.instance is observation.observed_instance,
            observation.instance_reliability,
            len(INSTANCES),
        )
        + _log_match(
            gap.cause is observation.observed_cause,
            observation.cause_reliability,
            len(CAUSES),
        )
        + _log_match(
            changed is observation.observed_regime_change, observation.regime_reliability, 2
        )
    )


def gap_features(gap: GapHypothesis) -> tuple[float, float, float]:
    """The regressor x_g attributed to this gap by this hypothesis."""

    return (
        1.0,
        1.0 if gap.mechanism is Mechanism.HANDOFF else 0.0,
        1.0 if gap.instance is Instance.TARGET else 0.0,
    )


# ---------------------------------------------------------------------------
# Analytic block S_t = (alpha, A, b, Lambda, xi)
# ---------------------------------------------------------------------------


def _det3(m: Sequence[Sequence[float]]) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _bilinear_form_inverse(
    m: Sequence[Sequence[float]], u: Sequence[float], v: Sequence[float]
) -> float:
    """Return u^T m^{-1} v for a 3x3 symmetric positive definite ``m``."""

    determinant = _det3(m)
    if determinant <= 0.0 or not math.isfinite(determinant):
        raise ValueError("analytic block matrix must stay positive definite")
    cofactor = (
        (
            m[1][1] * m[2][2] - m[1][2] * m[2][1],
            m[0][2] * m[2][1] - m[0][1] * m[2][2],
            m[0][1] * m[1][2] - m[0][2] * m[1][1],
        ),
        (
            m[1][2] * m[2][0] - m[1][0] * m[2][2],
            m[0][0] * m[2][2] - m[0][2] * m[2][0],
            m[0][2] * m[1][0] - m[0][0] * m[1][2],
        ),
        (
            m[1][0] * m[2][1] - m[1][1] * m[2][0],
            m[0][1] * m[2][0] - m[0][0] * m[2][1],
            m[0][0] * m[1][1] - m[0][1] * m[1][0],
        ),
    )
    total = 0.0
    for i in range(FEATURE_DIM):
        for j in range(FEATURE_DIM):
            total += u[i] * cofactor[i][j] * v[j]
    return total / determinant


def _quadratic_form_inverse(m: Sequence[Sequence[float]], v: Sequence[float]) -> float:
    return _bilinear_form_inverse(m, v, v)


@dataclass(slots=True)
class AnalyticBlock:
    """Real Rao-Blackwellized state for one (actor, regime) cell.

    ``statistic_state_ref`` on a particle points at an instance of this class,
    never at a formatted string.
    """

    alpha: list[float] = field(
        default_factory=lambda: [DIRICHLET_PRIOR for _ in range(PLACEMENT_BINS)]
    )
    a_matrix: list[list[float]] = field(
        default_factory=lambda: [
            [RIDGE_LAMBDA if i == j else 0.0 for j in range(FEATURE_DIM)]
            for i in range(FEATURE_DIM)
        ]
    )
    b_vector: list[float] = field(default_factory=lambda: [0.0] * FEATURE_DIM)
    precision: float = RIDGE_LAMBDA
    xi: float = 0.0
    count: int = 0

    def clone(self) -> AnalyticBlock:
        return AnalyticBlock(
            alpha=list(self.alpha),
            a_matrix=[list(row) for row in self.a_matrix],
            b_vector=list(self.b_vector),
            precision=self.precision,
            xi=self.xi,
            count=self.count,
        )

    def update(self, x: Sequence[float], y: float, placement_bin: int) -> None:
        """Observation-driven update; nothing here is derived from scenario flags."""

        self.alpha[placement_bin] += 1.0
        for i in range(FEATURE_DIM):
            self.b_vector[i] += x[i] * y / NOISE_VARIANCE
            for j in range(FEATURE_DIM):
                self.a_matrix[i][j] += x[i] * x[j] / NOISE_VARIANCE
        self.precision += sum(value * value for value in x) / NOISE_VARIANCE
        self.xi += y * y / NOISE_VARIANCE
        self.count += 1

    def downdate(self, x: Sequence[float], y: float, placement_bin: int) -> None:
        """Remove one previously recorded contribution exactly.

        Task 7 uses this inverse update to move only the observations whose
        latent owner/cell changed inside the rejuvenation window.  Rebuilding
        every analytic block from the complete history would turn a nominally
        local kernel back into an O(G) suffix replay.
        """

        if self.count <= 0 or self.alpha[placement_bin] <= DIRICHLET_PRIOR:
            raise ValueError("analytic block does not contain the requested contribution")
        self.alpha[placement_bin] -= 1.0
        for i in range(FEATURE_DIM):
            self.b_vector[i] -= x[i] * y / NOISE_VARIANCE
            for j in range(FEATURE_DIM):
                self.a_matrix[i][j] -= x[i] * x[j] / NOISE_VARIANCE
        self.precision -= sum(value * value for value in x) / NOISE_VARIANCE
        self.xi -= y * y / NOISE_VARIANCE
        self.count -= 1
        if self.count == 0:
            # Avoid tiny signed round-off in a block returned exactly to prior.
            self.alpha = [DIRICHLET_PRIOR for _ in range(PLACEMENT_BINS)]
            self.a_matrix = [
                [RIDGE_LAMBDA if i == j else 0.0 for j in range(FEATURE_DIM)]
                for i in range(FEATURE_DIM)
            ]
            self.b_vector = [0.0] * FEATURE_DIM
            self.precision = RIDGE_LAMBDA
            self.xi = 0.0

    def log_marginal(self) -> float:
        """log p(y_cell, bins_cell) with theta and the categorical integrated out."""

        if self.count == 0:
            return 0.0
        prior_total = DIRICHLET_PRIOR * PLACEMENT_BINS
        posterior_total = sum(self.alpha)
        categorical = math.lgamma(prior_total) - math.lgamma(posterior_total)
        for value in self.alpha:
            categorical += math.lgamma(value) - math.lgamma(DIRICHLET_PRIOR)
        gaussian = (
            -0.5 * self.count * math.log(2.0 * math.pi * NOISE_VARIANCE)
            - 0.5 * self.xi
            + 0.5 * _quadratic_form_inverse(self.a_matrix, self.b_vector)
            + 0.5 * FEATURE_DIM * math.log(RIDGE_LAMBDA)
            - 0.5 * math.log(_det3(self.a_matrix))
        )
        return categorical + gaussian

    def predictive_bin(self) -> int:
        return max(range(PLACEMENT_BINS), key=lambda index: self.alpha[index])

    def action_log_scores(self, query: Sequence[float]) -> list[float]:
        """Posterior predictive score per placement bin for a future query.

        This is the readout the embodied metric consumes.  It deliberately uses
        BOTH the categorical block and the linear-Gaussian block, so the action
        depends on which gaps this chain attributed to this (actor, regime)
        cell — that is, on actor responsibility, instance association and the
        regime destination, not on the regime label alone.  The previous
        instrument scored the regime label only, which is why its action gate
        had no discriminative power.
        """

        total = sum(self.alpha)
        mean = _bilinear_form_inverse(self.a_matrix, self.b_vector, query)
        variance = NOISE_VARIANCE + _quadratic_form_inverse(self.a_matrix, query)
        scores: list[float] = []
        for index in range(PLACEMENT_BINS):
            centre = PLACEMENT_BIN_CENTRES[index]
            residual = centre - mean
            scores.append(
                math.log(self.alpha[index] / total)
                - 0.5 * math.log(2.0 * math.pi * variance)
                - residual * residual / (2.0 * variance)
            )
        return scores


def analytic_blocks_for(
    chain: ChainHypothesis, observations: Sequence[GapObservation], meter: CostMeter
) -> dict[tuple[str, str], AnalyticBlock]:
    blocks: dict[tuple[str, str], AnalyticBlock] = {}
    for index, gap in enumerate(chain.gaps):
        cell = chain.cell_of(index)
        block = blocks.setdefault(cell, AnalyticBlock())
        observation = observations[index]
        block.update(gap_features(gap), observation.placement_value, observation.placement_bin)
        meter.analytic()
    return blocks


def chain_log_target(
    chain: ChainHypothesis,
    observations: Sequence[GapObservation],
    meter: CostMeter,
    *,
    rao_blackwellized: bool = True,
    rng: random.Random | None = None,
    relative_probability_coupling_nats: float = 0.0,
) -> float:
    """log prior + discrete likelihood + (integrated | sampled) continuous term."""

    meter.score_state(chain.key)
    total = 0.0
    for index, gap in enumerate(chain.gaps):
        total += gap_log_prior(
            gap,
            relative_probability_coupling_nats=relative_probability_coupling_nats,
        )
        total += gap_log_likelihood(gap, observations[index], meter)
    if rao_blackwellized:
        for block in analytic_blocks_for(chain, observations, meter).values():
            total += block.log_marginal()
        return total
    if rng is None:
        raise ValueError("a sampled-theta arm requires a random source")
    total += _sampled_theta_log_likelihood(chain, observations, meter, rng)
    return total


def _sampled_theta_log_likelihood(
    chain: ChainHypothesis,
    observations: Sequence[GapObservation],
    meter: CostMeter,
    rng: random.Random,
) -> float:
    """The sampled-theta arm draws the continuous parameters instead of integrating."""

    sampled: dict[tuple[str, str], tuple[tuple[float, ...], tuple[float, ...]]] = {}
    total = 0.0
    scale = 1.0 / math.sqrt(RIDGE_LAMBDA)
    for index, gap in enumerate(chain.gaps):
        cell = chain.cell_of(index)
        if cell not in sampled:
            theta = tuple(rng.gauss(0.0, scale) for _ in range(FEATURE_DIM))
            weights = [rng.gammavariate(DIRICHLET_PRIOR, 1.0) for _ in range(PLACEMENT_BINS)]
            denominator = sum(weights) or 1.0
            sampled[cell] = (theta, tuple(value / denominator for value in weights))
            meter.analytic()
        theta, categorical = sampled[cell]
        observation = observations[index]
        x = gap_features(gap)
        mean = sum(theta[i] * x[i] for i in range(FEATURE_DIM))
        residual = observation.placement_value - mean
        total += -0.5 * math.log(2.0 * math.pi * NOISE_VARIANCE) - residual * residual / (
            2.0 * NOISE_VARIANCE
        )
        probability = max(categorical[observation.placement_bin], 1e-12)
        total += math.log(probability)
        meter.elementary(2)
    return total


def unresolved_log_target(observations: Sequence[GapObservation]) -> float:
    """Explicit unresolved mass: a formal posterior state, not an error exit.

    It is scored on the same scale as any chain — a maximally diffuse hypothesis
    that explains the discrete reading uniformly and the continuous reading with
    the prior predictive N(0, sigma^2 + 1/lambda).  Scoring it as a free-floating
    constant instead would let it swamp the whole posterior and make total
    variation between arms meaningless.
    """

    uniform_discrete = (
        -math.log(len(MECHANISMS))
        - 2.0 * math.log(len(ACTORS))
        - math.log(len(INSTANCES))
        - math.log(len(CAUSES))
        - math.log(2.0)
        - math.log(PLACEMENT_BINS)
    )
    total = math.log(UNRESOLVED_PRIOR)
    for observation in observations:
        total += _unresolved_observation_log_term(observation, uniform_discrete)
    return total


def _unresolved_observation_log_term(
    observation: GapObservation, uniform_discrete: float | None = None
) -> float:
    if uniform_discrete is None:
        uniform_discrete = (
            -math.log(len(MECHANISMS))
            - 2.0 * math.log(len(ACTORS))
            - math.log(len(INSTANCES))
            - math.log(len(CAUSES))
            - math.log(2.0)
            - math.log(PLACEMENT_BINS)
        )
    predictive_variance = NOISE_VARIANCE + 1.0 / RIDGE_LAMBDA
    value = observation.placement_value
    return (
        uniform_discrete
        - 0.5 * math.log(2.0 * math.pi * predictive_variance)
        - value * value / (2.0 * predictive_variance)
    )


# ---------------------------------------------------------------------------
# Typed constraints (part of the target, not a private advantage)
# ---------------------------------------------------------------------------


def gap_is_admissible(gap: GapHypothesis) -> bool:
    """Hard structured constraints psi_j, applied by every arm's target.

    They encode two project decisions: the robot's own manipulation may not
    found an owner habit regime, and an unidentified instance may not found one
    either.  The typed proposal is allowed to *exploit* them by never proposing
    inadmissible candidates; the bootstrap proposal is not, and that difference
    is exactly what the C -> D comparison is meant to measure.
    """

    founding = gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}
    if founding and gap.receiver is Actor.ROBOT:
        return False
    if founding and gap.instance is Instance.UNKNOWN:
        return False
    return not (gap.mechanism is Mechanism.DIRECT and gap.giver is not gap.receiver)


def chain_is_admissible(chain: ChainHypothesis) -> bool:
    return all(gap_is_admissible(gap) for gap in chain.gaps)


# ---------------------------------------------------------------------------
# Arm A: exact oracle
# ---------------------------------------------------------------------------


def exact_posterior(
    scenario: BackboneScenario,
    meter: CostMeter,
    *,
    caller_role: CallerRole,
    state_budget: int = 5_000_000,
) -> dict[str, float]:
    """Enumerate every admissible chain.  Approximate arms may not call this."""

    posterior, _actions = exact_posterior_with_actions(
        scenario, meter, caller_role=caller_role, state_budget=state_budget
    )
    return posterior


def exact_decision_summary(
    scenario: BackboneScenario,
    meter: CostMeter,
    *,
    caller_role: CallerRole,
    state_budget: int = 5_000_000,
) -> ExactDecisionSummary:
    """Exact posterior plus every decision quantity, in one enumeration sweep.

    Accumulated during enumeration so that no caller ever has to hold every
    ``ChainHypothesis`` object in memory at once — at G=2 that is 9e5 objects.
    """

    if caller_role is not CallerRole.EXACT_ORACLE:
        raise FullEnumerationForbiddenError(
            f"{caller_role.value} may not enumerate the full state space (protocol section 3.2)"
        )
    log_targets: dict[str, float] = {}
    chain_actions: dict[str, int] = {}
    chain_embodied: dict[str, str] = {}
    chain_owner: dict[str, bool] = {}
    visited = 0
    for chain in iter_chains(scenario.gaps):
        visited += 1
        if visited > state_budget:
            raise ExactEnumerationBudgetExceeded(scenario.gaps, state_budget, visited)
        if not chain_is_admissible(chain):
            continue
        key = chain.key
        log_targets[key] = chain_log_target(
            chain,
            scenario.observations,
            meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        chain_actions[key] = chain_action(chain, scenario.observations)
        chain_embodied[key] = chain_embodied_action(chain, scenario.observations).key
        chain_owner[key] = chain.gaps[scenario.corrupt_index].receiver is Actor.OWNER
    meter.track_live(len(log_targets))
    posterior = normalize_log_targets(log_targets, unresolved_log_target(scenario.observations))
    marginal: dict[int, float] = dict.fromkeys(range(PLACEMENT_BINS), 0.0)
    embodied: dict[str, float] = {}
    owner_mass = 0.0
    resolved = 0.0
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        marginal[chain_actions[key]] += probability
        embodied[chain_embodied[key]] = embodied.get(chain_embodied[key], 0.0) + probability
        resolved += probability
        if chain_owner[key]:
            owner_mass += probability
    if resolved > 0.0:
        embodied = {key: value / resolved for key, value in embodied.items()}
    return ExactDecisionSummary(
        posterior=posterior,
        legacy_action_marginal=marginal,
        embodied_action_posterior=embodied,
        owner_responsibility=owner_mass,
    )


@dataclass(frozen=True, slots=True)
class ExactDecisionSummary:
    """Everything the decision metrics need, from a single enumeration pass."""

    posterior: dict[str, float]
    legacy_action_marginal: dict[int, float]
    embodied_action_posterior: dict[str, float]
    owner_responsibility: float


def exact_posterior_with_actions(
    scenario: BackboneScenario,
    meter: CostMeter,
    *,
    caller_role: CallerRole,
    state_budget: int = 5_000_000,
) -> tuple[dict[str, float], dict[int, float]]:
    summary = exact_decision_summary(
        scenario, meter, caller_role=caller_role, state_budget=state_budget
    )
    return summary.posterior, summary.legacy_action_marginal


def normalize_log_targets(
    log_targets: Mapping[str, float], unresolved_log_weight: float
) -> dict[str, float]:
    finite = [value for value in log_targets.values() if math.isfinite(value)]
    maximum = max([unresolved_log_weight, *finite]) if finite else unresolved_log_weight
    masses = {
        key: math.exp(value - maximum) if math.isfinite(value) else 0.0
        for key, value in log_targets.items()
    }
    unresolved_mass = math.exp(unresolved_log_weight - maximum)
    denominator = unresolved_mass + sum(masses.values())
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise ValueError("normalization has no finite probability mass")
    posterior = {key: mass / denominator for key, mass in masses.items()}
    posterior[UNRESOLVED_KEY] = unresolved_mass / denominator
    return posterior


# ---------------------------------------------------------------------------
# Particle arms B/C/D
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LatentBoundary:
    """Sufficient typed state at one gap boundary (before gap ``index``)."""

    current: str | None
    retired: tuple[str, ...]
    created: int
    run_length: int


@dataclass(frozen=True, slots=True)
class WindowCheckpoint:
    """Source-bound checkpoint used by the Task-7 local repair kernel.

    The digest detects accidental or adversarial mutation within one execution.
    It is not an external trust anchor; evidence envelopes must independently
    bind and recompute the run before making a historical-authenticity claim.
    """

    format_id: str
    source_chain_sha256: str
    source_position_xor_sha256: str
    source_observations_sha256: str
    analytic_blocks_sha256: str
    boundary_states: Sequence[LatentBoundary]
    content_sha256: str
    serialized_bytes: int


@dataclass(frozen=True, slots=True)
class PersistentBlockMap(Mapping[tuple[str, str], AnalyticBlock]):
    """Copy-on-write analytic blocks whose overlay is bounded by the window."""

    base: Mapping[tuple[str, str], AnalyticBlock]
    overrides: Mapping[tuple[str, str], AnalyticBlock]
    removed: frozenset[tuple[str, str]] = frozenset()

    def __getitem__(self, key: tuple[str, str]) -> AnalyticBlock:
        if key in self.removed:
            raise KeyError(key)
        if key in self.overrides:
            return self.overrides[key]
        return self.base[key]

    def __iter__(self) -> Iterator[tuple[str, str]]:
        for key in self.base:
            if key not in self.removed and key not in self.overrides:
                yield key
        yield from self.overrides

    def __len__(self) -> int:
        return sum(
            1 for key in self.base if key not in self.removed and key not in self.overrides
        ) + len(self.overrides)


def _persistent_blocks_with_changes(
    blocks: Mapping[tuple[str, str], AnalyticBlock],
    changed: Mapping[tuple[str, str], AnalyticBlock],
) -> PersistentBlockMap:
    """Flatten bounded overlays while never iterating the untouched base map."""

    if isinstance(blocks, PersistentBlockMap):
        base = blocks.base
        overrides = dict(blocks.overrides)
        removed = set(blocks.removed)
    else:
        base = blocks
        overrides = {}
        removed = set()
    for cell, block in changed.items():
        if block.count == 0:
            overrides.pop(cell, None)
            removed.add(cell)
        else:
            overrides[cell] = block
            removed.discard(cell)
    return PersistentBlockMap(base=base, overrides=overrides, removed=frozenset(removed))


@dataclass(slots=True)
class Particle:
    gaps: Sequence[GapHypothesis]
    timeline: Sequence[str | None]
    runs: Sequence[int]
    current: str | None
    retired: tuple[str, ...]
    created: int
    log_weight: float
    blocks: Mapping[tuple[str, str], AnalyticBlock]
    thetas: dict[tuple[str, str], tuple[tuple[float, ...], tuple[float, ...]]]
    ancestry: tuple[str, ...]
    boundary_states: Sequence[LatentBoundary] = ()
    checkpoint: WindowCheckpoint | None = None
    persistent_chain_key: str | None = None
    repair_lineage: tuple[str, ...] = ()
    terminal_responsible_actor: Actor | None = None

    def chain(self) -> ChainHypothesis:
        return ChainHypothesis(gaps=self.gaps, regime_timeline=self.timeline, run_lengths=self.runs)

    def clone(self) -> Particle:
        return Particle(
            gaps=self.gaps,
            timeline=self.timeline,
            runs=self.runs,
            current=self.current,
            retired=self.retired,
            created=self.created,
            log_weight=self.log_weight,
            blocks={cell: block.clone() for cell, block in self.blocks.items()},
            thetas=dict(self.thetas),
            ancestry=self.ancestry,
            boundary_states=self.boundary_states,
            checkpoint=self.checkpoint,
            persistent_chain_key=self.persistent_chain_key,
            repair_lineage=self.repair_lineage,
            terminal_responsible_actor=self.terminal_responsible_actor,
        )

    def clone_sharing_history(self) -> Particle:
        """Clone for Task-7 resampling without copying immutable long history."""

        return Particle(
            gaps=self.gaps,
            timeline=self.timeline,
            runs=self.runs,
            current=self.current,
            retired=self.retired,
            created=self.created,
            log_weight=self.log_weight,
            blocks=self.blocks,
            thetas=self.thetas,
            ancestry=self.ancestry,
            boundary_states=self.boundary_states,
            checkpoint=self.checkpoint,
            persistent_chain_key=self.persistent_chain_key,
            repair_lineage=self.repair_lineage,
            terminal_responsible_actor=self.terminal_responsible_actor,
        )


_LEGAL_GAP_CACHE: dict[
    tuple[str | None, tuple[str, ...], int],
    tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...],
] = {}


def _legal_gaps(
    particle: Particle,
) -> tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...]:
    """Successors of one particle only.  This never touches the global space.

    Memoized on the only three fields it reads.  Without the cache the typed
    arms spent 72-86% of their wall clock rebuilding the same ~990 dataclasses:
    the adaptive arm calls this once per radius, and at G=1 every particle sits
    on the same regime state, so 1152 calls returned identical results.  That
    waste is invisible to every counter, so it silently contaminated any
    matched-compute comparison.
    """

    key = (particle.current, particle.retired, particle.created)
    cached = _LEGAL_GAP_CACHE.get(key)
    if cached is not None:
        return cached
    successors: list[tuple[GapHypothesis, str | None, tuple[str, ...], int]] = []
    for mechanism, giver, receiver in ACTOR_PAIRS:
        for instance in INSTANCES:
            for cause in CAUSES:
                for move, target, regime, retired, created in _regime_successors(
                    cause, particle.current, particle.retired, particle.created
                ):
                    gap = GapHypothesis(
                        mechanism=mechanism,
                        giver=giver,
                        receiver=receiver,
                        instance=instance,
                        cause=cause,
                        regime_move=move,
                        regime_target=target,
                    )
                    if gap_is_admissible(gap):
                        successors.append((gap, regime, retired, created))
    result = tuple(successors)
    _LEGAL_GAP_CACHE[key] = result
    return result


def _axis_deviations(gap: GapHypothesis, observation: GapObservation) -> int:
    """Axis disagreements between a hypothesis and the reading.

    The regime axis is counted here because it is counted in
    ``_perfect_match_log_likelihood``: a deficit that appears in the numerator
    must be removable by widening, or the deficit is not a deficit in axes.

    Two honesty notes.  Counting it can only shrink the radius-1 set, never grow
    it, so it can only make the adaptive arm widen MORE — an earlier version of
    this docstring claimed the opposite.  And the registered scenarios never
    corrupt ``observed_regime_change``, so this axis has not yet been exercised;
    measured end to end the change moved total variation by 0.0012, a tenth of
    one standard error.
    """

    changed = gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}
    return sum(
        (
            gap.mechanism is not observation.observed_mechanism,
            gap.giver is not observation.observed_giver,
            gap.receiver is not observation.observed_receiver,
            gap.instance is not observation.observed_instance,
            gap.cause is not observation.observed_cause,
            changed is not observation.observed_regime_change,
        )
    )


def _typed_candidates(
    particle: Particle, observation: GapObservation, radius: int = 1
) -> tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...]:
    """Observation-anchored local candidates within ``radius`` axis deviations.

    Radius 1 is the frozen v0.1 behaviour.  It is a hard coverage ceiling: when
    the reading itself is corrupted on two axes (or is inadmissible), the truth
    can never enter the candidate set, and the 2026-09-02 budget sweep showed the
    resulting arm being overtaken by plain RBPF once the budget is large enough
    for a bootstrap proposal to find the mass on its own.
    """

    return tuple(
        candidate
        for candidate in _legal_gaps(particle)
        if _axis_deviations(candidate[0], observation) <= radius
    )


def _perfect_match_log_likelihood(observation: GapObservation) -> float:
    """Log-likelihood a hypothesis would get by matching the reading on every axis."""

    return (
        math.log(observation.mechanism_reliability)
        + 2.0 * math.log(observation.actor_reliability)
        + math.log(observation.instance_reliability)
        + math.log(observation.cause_reliability)
        + math.log(observation.regime_reliability)
    )


def _cheapest_axis_mismatch_cost(observation: GapObservation) -> float:
    """Nats paid for the least expensive single-axis disagreement with the reading.

    This is the unit the deficit below is measured in.  Measuring the deficit in
    raw nats was wrong: the penalty for a mismatch shrinks as reliability falls,
    so a high-ambiguity reading produced a SMALL nat gap for the SAME structural
    failure and the neighbourhood refused to widen exactly where it had to.
    """

    costs = (
        math.log(observation.mechanism_reliability)
        - _log_match(False, observation.mechanism_reliability, len(MECHANISMS)),
        math.log(observation.actor_reliability)
        - _log_match(False, observation.actor_reliability, len(ACTORS)),
        math.log(observation.instance_reliability)
        - _log_match(False, observation.instance_reliability, len(INSTANCES)),
        math.log(observation.cause_reliability)
        - _log_match(False, observation.cause_reliability, len(CAUSES)),
        math.log(observation.regime_reliability)
        - _log_match(False, observation.regime_reliability, 2),
    )
    # Only axes that actually carry information define the unit.  An axis at or
    # below its uniform baseline has a non-positive mismatch cost; letting it set
    # the unit drove the deficit to 1e9 (radius pinned at 3 forever) just below
    # the baseline, and to 0 (radius pinned at 1) just above it.
    informative = [cost for cost in costs if cost > MINIMUM_AXIS_INFORMATION]
    return min(informative) if informative else MINIMUM_AXIS_INFORMATION


def _adaptive_candidates(
    particle: Particle,
    observation: GapObservation,
    meter: CostMeter,
    *,
    relative_probability_coupling_nats: float = 0.0,
) -> tuple[
    tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...], list[float], float, int
]:
    """Widen the neighbourhood until the reading is actually explainable.

    ``unexplained`` is how far the best admissible candidate falls short of a
    hypothesis matching the reading on every axis, measured in units of the
    cheapest single-axis disagreement.  It is scale free, so a corrupted reading
    widens the neighbourhood whether or not the scenario is also ambiguous.
    """

    perfect = _perfect_match_log_likelihood(observation)
    unit = _cheapest_axis_mismatch_cost(observation)
    candidates: tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...] = ()
    scores: list[float] = []
    unexplained = 0.0
    radius = 1
    for radius in range(1, ADAPTIVE_MAX_RADIUS + 1):
        candidates = _typed_candidates(particle, observation, radius)
        if not candidates:
            continue
        scores = []
        best_likelihood = -math.inf
        for candidate in candidates:
            meter.proposal()
            likelihood = gap_log_likelihood(candidate[0], observation, meter)
            best_likelihood = max(best_likelihood, likelihood)
            scores.append(
                gap_log_prior(
                    candidate[0],
                    relative_probability_coupling_nats=(relative_probability_coupling_nats),
                )
                + likelihood
            )
        unexplained = max(0.0, perfect - best_likelihood) / unit
        if unexplained <= ADAPTIVE_UNEXPLAINED_TARGET:
            break
    return candidates, scores, unexplained, radius


def _adaptive_escape(unexplained: float) -> float:
    """Escape probability grows with the unexplained-axis deficit, and is bounded."""

    weight = min(1.0, unexplained / ADAPTIVE_ESCAPE_SATURATION)
    return ADAPTIVE_ESCAPE_MIN + (ADAPTIVE_ESCAPE_MAX - ADAPTIVE_ESCAPE_MIN) * weight


def _incremental_log_evidence(
    particle: Particle,
    gap: GapHypothesis,
    regime: str | None,
    observation: GapObservation,
    meter: CostMeter,
    *,
    rao_blackwellized: bool,
    rng: random.Random,
) -> tuple[
    float,
    dict[tuple[str, str], AnalyticBlock] | None,
    tuple[tuple[float, ...], tuple[float, ...]] | None,
]:
    cell = (gap.receiver.value, regime or "unresolved_regime")
    if rao_blackwellized:
        block = particle.blocks.get(cell, AnalyticBlock()).clone()
        before = block.log_marginal()
        block.update(gap_features(gap), observation.placement_value, observation.placement_bin)
        meter.analytic()
        return block.log_marginal() - before, {cell: block}, None
    parameters = particle.thetas.get(cell)
    if parameters is None:
        scale = 1.0 / math.sqrt(RIDGE_LAMBDA)
        theta = tuple(rng.gauss(0.0, scale) for _ in range(FEATURE_DIM))
        weights = [rng.gammavariate(DIRICHLET_PRIOR, 1.0) for _ in range(PLACEMENT_BINS)]
        denominator = sum(weights) or 1.0
        parameters = (theta, tuple(value / denominator for value in weights))
        meter.analytic()
    theta, categorical = parameters
    x = gap_features(gap)
    mean = sum(theta[index] * x[index] for index in range(FEATURE_DIM))
    residual = observation.placement_value - mean
    meter.elementary(2)
    value = (
        -0.5 * math.log(2.0 * math.pi * NOISE_VARIANCE)
        - residual * residual / (2.0 * NOISE_VARIANCE)
        + math.log(max(categorical[observation.placement_bin], 1e-12))
    )
    return value, None, parameters


def _effective_sample_size(weights: Sequence[float]) -> float:
    total = sum(weights)
    if total <= 0.0:
        return 0.0
    squared = sum((weight / total) ** 2 for weight in weights)
    return 1.0 / squared if squared > 0.0 else 0.0


def _systematic_resample(
    particles: list[Particle],
    weights: list[float],
    rng: random.Random,
    *,
    share_history: bool = False,
) -> list[Particle]:
    size = len(particles)
    total = sum(weights)
    step = total / size
    pointer = rng.uniform(0.0, step)
    cumulative = 0.0
    index = 0
    resampled: list[Particle] = []
    for _ in range(size):
        while cumulative + weights[index] < pointer and index < size - 1:
            cumulative += weights[index]
            index += 1
        clone = (
            particles[index].clone_sharing_history() if share_history else particles[index].clone()
        )
        clone.log_weight = 0.0
        resampled.append(clone)
        pointer += step
    return resampled


TYPED_ESCAPE_PROBABILITY: Final = 0.10
TYPED_FIXED_RADIUS: Final = 1
ADAPTIVE_MAX_RADIUS: Final = 3
ADAPTIVE_UNEXPLAINED_TARGET: Final = 0.5
ADAPTIVE_ESCAPE_SATURATION: Final = 2.0
MINIMUM_AXIS_INFORMATION: Final = 0.05
FACTORIZATION_FITTING_ROUNDS: Final = 200
FACTORIZATION_TOLERANCE: Final = 1e-12
ADAPTIVE_ESCAPE_MIN: Final = 0.05
ADAPTIVE_ESCAPE_MAX: Final = 0.60


def _prior_move_options(
    gap_axes: tuple[Mechanism, Actor, Actor, Instance, Cause], particle: Particle
) -> tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int, float], ...]:
    mechanism, giver, receiver, instance, cause = gap_axes
    options: list[tuple[GapHypothesis, str | None, tuple[str, ...], int, float]] = []
    for move, target, regime, retired, created in _regime_successors(
        cause, particle.current, particle.retired, particle.created
    ):
        gap = GapHypothesis(
            mechanism=mechanism,
            giver=giver,
            receiver=receiver,
            instance=instance,
            cause=cause,
            regime_move=move,
            regime_target=target,
        )
        if gap_is_admissible(gap):
            options.append((gap, regime, retired, created, _AXIS_PRIOR[move.value]))
    return tuple(options)


def _sample_prior_gap(
    particle: Particle, rng: random.Random, meter: CostMeter
) -> tuple[GapHypothesis, str | None, tuple[str, ...], int, float]:
    """Bootstrap proposal: the transition prior restricted to admissible moves."""

    for _ in range(32):
        mechanism = _weighted_choice(MECHANISMS, rng)
        giver = _weighted_choice(ACTORS, rng)
        receiver = giver if mechanism is Mechanism.DIRECT else _weighted_choice(ACTORS, rng)
        instance = _weighted_choice(INSTANCES, rng)
        cause = _weighted_choice(CAUSES, rng)
        options = _prior_move_options((mechanism, giver, receiver, instance, cause), particle)
        meter.proposal()
        if not options:
            continue
        normalizer = sum(option[4] for option in options)
        pick = rng.uniform(0.0, normalizer)
        running = 0.0
        for gap, regime, retired, created, weight in options:
            running += weight
            if pick <= running:
                return gap, regime, retired, created, math.log(weight / normalizer)
    raise RuntimeError("bootstrap proposal failed to find an admissible successor")


def _weighted_choice[T: StrEnum](values: Sequence[T], rng: random.Random) -> T:
    total = sum(_AXIS_PRIOR[value.value] for value in values)
    pick = rng.uniform(0.0, total)
    running = 0.0
    for value in values:
        running += _AXIS_PRIOR[value.value]
        if pick <= running:
            return value
    return values[-1]


def _prior_log_density(
    gap: GapHypothesis, particle: Particle, move_log_density: float | None = None
) -> float:
    """log q_prior(gap) for the bootstrap proposal, used by the typed mixture."""

    if move_log_density is None:
        options = _prior_move_options(
            (gap.mechanism, gap.giver, gap.receiver, gap.instance, gap.cause), particle
        )
        normalizer = sum(option[4] for option in options)
        if normalizer <= 0.0:
            return -math.inf
        move_log_density = math.log(_AXIS_PRIOR[gap.regime_move.value] / normalizer)
    axes = (
        math.log(_AXIS_PRIOR[gap.mechanism.value])
        + math.log(_AXIS_PRIOR[gap.giver.value])
        + (0.0 if gap.mechanism is Mechanism.DIRECT else math.log(_AXIS_PRIOR[gap.receiver.value]))
        + math.log(_AXIS_PRIOR[gap.instance.value])
        + math.log(_AXIS_PRIOR[gap.cause.value])
    )
    return axes + move_log_density


@dataclass(frozen=True, slots=True)
class ArmResult:
    """One particle arm's estimate.

    ``posterior`` is the arm's OWN estimator: self-normalized particle weights
    for the chains, blended with the unresolved hypothesis through the SMC
    evidence estimate.  An earlier version of this module discarded the particle
    weights and re-scored the discovered support with the exact target, which
    made the reported total variation identically ``1 - P_exact(support)`` — a
    proposal-coverage measure wearing a posterior-quality name, i.e. the same
    defect that retired the previous instrument.  Coverage is still reported,
    but as its own number by the evaluator, never as total variation.
    """

    arm: ArmName
    posterior: dict[str, float]
    support: frozenset[str]
    support_chains: dict[str, ChainHypothesis]
    effective_sample_size: float
    log_evidence: float
    cost: dict[str, float | int | str]
    embodied_action_posterior_cache: dict[str, float] | None = None


def _logsumexp(values: Sequence[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return -math.inf
    maximum = max(finite)
    return maximum + math.log(
        sum(math.exp(value - maximum) for value in values if math.isfinite(value))
    )


@dataclass(frozen=True, slots=True)
class ArmConfiguration:
    """The three switches that distinguish arms B/C/D/D'."""

    rao_blackwellized: bool
    typed: bool
    adaptive: bool

    @classmethod
    def of(cls, arm: ArmName) -> ArmConfiguration:
        return cls(
            rao_blackwellized=arm is not ArmName.SAMPLED_THETA_PF,
            typed=arm in TYPED_ARMS,
            adaptive=arm is ArmName.ADAPTIVE_TYPED_RBPF,
        )


def _step_particles(
    particles: list[Particle],
    observation: GapObservation,
    index: int,
    *,
    config: ArmConfiguration,
    rng: random.Random,
    meter: CostMeter,
    relative_probability_coupling_nats: float = 0.0,
) -> None:
    """Advance every particle across one observation gap, in place."""

    typed = config.typed
    adaptive = config.adaptive
    rao_blackwellized = config.rao_blackwellized
    for particle in particles:
        if not particle.boundary_states:
            particle.boundary_states = (
                LatentBoundary(
                    current=particle.current,
                    retired=particle.retired,
                    created=particle.created,
                    run_length=particle.runs[-1] if particle.runs else 0,
                ),
            )
        candidates: tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...] = ()
        scores: list[float] = []
        escape = TYPED_ESCAPE_PROBABILITY
        if typed and adaptive:
            candidates, scores, fit, radius = _adaptive_candidates(
                particle,
                observation,
                meter,
                relative_probability_coupling_nats=(relative_probability_coupling_nats),
            )
            escape = _adaptive_escape(fit)
            meter.note_radius(radius)
        elif typed:
            candidates = _typed_candidates(particle, observation, TYPED_FIXED_RADIUS)
            for candidate in candidates:
                meter.proposal()
                scores.append(
                    gap_log_prior(
                        candidate[0],
                        relative_probability_coupling_nats=(relative_probability_coupling_nats),
                    )
                    + gap_log_likelihood(candidate[0], observation, meter)
                )
            meter.note_radius(TYPED_FIXED_RADIUS)

        if typed and candidates and rng.random() >= escape:
            maximum = max(scores)
            masses = [math.exp(value - maximum) for value in scores]
            normalizer = sum(masses)
            pick = rng.uniform(0.0, normalizer)
            running = 0.0
            selected = 0
            for position, mass in enumerate(masses):
                running += mass
                if pick <= running:
                    selected = position
                    break
            gap, regime, retired, created = candidates[selected]
            typed_log_q = scores[selected] - maximum - math.log(normalizer)
            log_q = _logsumexp(
                (
                    math.log1p(-escape) + typed_log_q,
                    math.log(escape) + _prior_log_density(gap, particle),
                )
            )
        else:
            gap, regime, retired, created, move_log_q = _sample_prior_gap(particle, rng, meter)
            prior_log_q = _prior_log_density(gap, particle, move_log_q)
            log_q = prior_log_q
            if typed and candidates:
                typed_log_q = _typed_log_density_from_scores(gap, candidates, scores)
                if math.isfinite(typed_log_q):
                    log_q = _logsumexp(
                        (
                            math.log(escape) + prior_log_q,
                            math.log1p(-escape) + typed_log_q,
                        )
                    )
                else:
                    # Reachable ONLY through the escape branch, so its proposal
                    # density carries the escape factor.  Omitting it made every
                    # such weight 1/escape too small and biased the evidence low.
                    log_q = math.log(escape) + prior_log_q

        evidence, blocks, parameters = _incremental_log_evidence(
            particle,
            gap,
            regime,
            observation,
            meter,
            rao_blackwellized=rao_blackwellized,
            rng=rng,
        )
        particle.log_weight += (
            gap_log_prior(
                gap,
                relative_probability_coupling_nats=relative_probability_coupling_nats,
            )
            + gap_log_likelihood(gap, observation, meter)
            + evidence
            - log_q
        )
        particle.gaps = (*particle.gaps, gap)
        particle.timeline = (*particle.timeline, regime)
        run_so_far = particle.runs[-1] if particle.runs else 0
        next_run = (
            0 if gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE} else run_so_far + 1
        )
        particle.runs = (*particle.runs, next_run)
        particle.current = regime
        particle.retired = retired
        particle.created = created
        particle.terminal_responsible_actor = gap.receiver
        particle.boundary_states = (
            *particle.boundary_states,
            LatentBoundary(
                current=regime,
                retired=retired,
                created=created,
                run_length=next_run,
            ),
        )
        particle.ancestry = (*particle.ancestry, f"g{index}:{gap.regime_move.value}")
        if blocks is not None:
            if not isinstance(particle.blocks, dict):
                raise TypeError("forward filtering requires mutable analytic blocks")
            particle.blocks.update(blocks)
        if parameters is not None:
            particle.thetas[(gap.receiver.value, regime or "unresolved_regime")] = parameters
        meter.score_state("|".join(item.key for item in particle.gaps))


def run_particle_arm(
    scenario: BackboneScenario,
    *,
    arm: ArmName,
    budget: int,
    seed: int,
) -> ArmResult:
    """Arms B/C/D.  None of them may reach the exact enumerator."""

    if arm not in APPROXIMATE_ARMS:
        raise ValueError(f"{arm.value} is not a particle arm")
    meter = CostMeter(arm=arm, particle_count=budget)
    meter.start()
    rng = random.Random(f"{PROTOCOL_ID}:{scenario.scenario_id}:{arm.value}:{seed}")

    particles = [
        Particle(
            gaps=(),
            timeline=(),
            runs=(),
            current="R0",
            retired=(),
            created=0,
            log_weight=0.0,
            blocks={},
            thetas={},
            ancestry=("root",),
        )
        for _ in range(budget)
    ]

    log_evidence = 0.0
    last_index = len(scenario.observations) - 1
    config = ArmConfiguration.of(arm)
    for index, observation in enumerate(scenario.observations):
        _step_particles(
            particles,
            observation,
            index,
            config=config,
            rng=rng,
            meter=meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        meter.track_live(len(particles))
        log_weights = [particle.log_weight for particle in particles]
        weights = _normalized_masses(log_weights)
        # Never resample on the final step: doing so resets every weight to zero,
        # which reported a perfect effective sample size for exactly the arms that
        # had just degenerated, and discarded support before it was read out.
        if index < last_index and _effective_sample_size(weights) < len(particles) / 2.0:
            log_evidence += _logsumexp(log_weights) - math.log(len(particles))
            particles = _systematic_resample(particles, weights, rng)
            meter.resample()

    meter.ancestry_window_length = max(len(particle.ancestry) for particle in particles)
    final_log_weights = [particle.log_weight for particle in particles]
    final_masses = _normalized_masses(final_log_weights)
    ess = _effective_sample_size(final_masses)
    log_evidence += _logsumexp(final_log_weights) - math.log(len(particles))

    support: dict[str, ChainHypothesis] = {}
    chain_mass: dict[str, float] = {}
    for particle, mass in zip(particles, final_masses, strict=True):
        chain = particle.chain()
        support.setdefault(chain.key, chain)
        chain_mass[chain.key] = chain_mass.get(chain.key, 0.0) + mass

    log_unresolved = unresolved_log_target(scenario.observations)
    total_mass = sum(chain_mass.values())
    if total_mass <= 0.0 or not math.isfinite(log_evidence):
        posterior = {key: 0.0 for key in chain_mass}
        posterior[UNRESOLVED_KEY] = 1.0
    else:
        pivot = max(log_evidence, log_unresolved)
        evidence_mass = math.exp(log_evidence - pivot)
        unresolved_mass = math.exp(log_unresolved - pivot)
        unresolved_probability = unresolved_mass / (evidence_mass + unresolved_mass)
        posterior = {
            key: (1.0 - unresolved_probability) * mass / total_mass
            for key, mass in chain_mass.items()
        }
        posterior[UNRESOLVED_KEY] = unresolved_probability
    meter.stop()
    return ArmResult(
        arm=arm,
        posterior=posterior,
        support=frozenset(support),
        support_chains=dict(support),
        effective_sample_size=ess,
        log_evidence=log_evidence,
        cost=meter.as_dict(),
    )


def _typed_log_density_from_scores(
    gap: GapHypothesis,
    candidates: Sequence[tuple[GapHypothesis, str | None, tuple[str, ...], int]],
    scores: Sequence[float],
) -> float:
    maximum = max(scores)
    normalizer = sum(math.exp(value - maximum) for value in scores)
    for candidate, score in zip(candidates, scores, strict=True):
        if candidate[0].key == gap.key:
            return score - maximum - math.log(normalizer)
    return -math.inf


def _typed_log_density(
    gap: GapHypothesis,
    candidates: Sequence[tuple[GapHypothesis, str | None, tuple[str, ...], int]],
    observation: GapObservation,
    meter: CostMeter,
) -> float:
    scores = [
        gap_log_prior(candidate[0]) + gap_log_likelihood(candidate[0], observation, meter)
        for candidate in candidates
    ]
    maximum = max(scores)
    normalizer = sum(math.exp(value - maximum) for value in scores)
    for candidate, score in zip(candidates, scores, strict=True):
        if candidate[0].key == gap.key:
            return score - maximum - math.log(normalizer)
    return -math.inf


def _normalized_masses(log_weights: Sequence[float]) -> list[float]:
    finite = [value for value in log_weights if math.isfinite(value)]
    if not finite:
        return [0.0 for _ in log_weights]
    maximum = max(finite)
    return [math.exp(value - maximum) if math.isfinite(value) else 0.0 for value in log_weights]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def total_variation(exact: Mapping[str, float], approximate: Mapping[str, float]) -> float:
    keys = set(exact) | set(approximate)
    return 0.5 * sum(abs(exact.get(key, 0.0) - approximate.get(key, 0.0)) for key in keys)


def chain_action(chain: ChainHypothesis, observations: Sequence[GapObservation]) -> int:
    """The embodied readout: where the robot would put the owner's object next."""

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    blocks = analytic_blocks_for(chain, observations, meter)
    cell = (Actor.OWNER.value, chain.final_regime or "unresolved_regime")
    block = blocks.get(cell)
    if block is None:
        block = AnalyticBlock()
    scores = block.action_log_scores(ACTION_QUERY_FEATURES)
    return max(range(PLACEMENT_BINS), key=lambda index: scores[index])


def action_marginal(
    posterior: Mapping[str, float],
    chains: Mapping[str, ChainHypothesis],
    observations: Sequence[GapObservation],
) -> dict[int, float]:
    marginal: dict[int, float] = {index: 0.0 for index in range(PLACEMENT_BINS)}
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        chain = chains.get(key)
        if chain is None:
            continue
        marginal[chain_action(chain, observations)] += probability
    return marginal


def action_regret(exact: Mapping[int, float], approximate: Mapping[int, float]) -> float | None:
    """Exact-Bayes action regret, or ``None`` when the arm proposes no action.

    An arm that puts all of its mass on ``unresolved`` has an all-zero action
    marginal.  Taking ``argmax`` of that silently returned bin 0 and scored the
    arm as if it had chosen — which handed a perfect regret to an arm that
    predicted nothing whenever bin 0 happened to be exact-optimal.  Declining to
    score is the honest answer; the caller records the abstention rate.
    """

    if not exact:
        return None
    if not approximate or all(value <= 0.0 for value in approximate.values()):
        return None
    best = max(exact.values())
    chosen = max(approximate, key=lambda index: approximate[index])
    return best - exact.get(chosen, 0.0)


def proposal_coverage(exact: Mapping[str, float], support: frozenset[str]) -> float:
    """Exact posterior mass the arm's support reached, unresolved included.

    This is a property of the PROPOSAL, computed by the evaluator (which is
    allowed to enumerate) and never by the arm.  It is reported next to total
    variation, never as total variation: an arm can cover the mass and still
    weight it wrongly, and the instrument has to be able to say so.
    """

    return sum(exact.get(key, 0.0) for key in support) + exact.get(UNRESOLVED_KEY, 0.0)


# ---------------------------------------------------------------------------
# Scenario generation
# ---------------------------------------------------------------------------


def _truth_chain(
    gaps: int,
    rng: random.Random,
    *,
    open_world: bool,
    short_regime: bool,
    relative_probability_coupling_nats: float = 0.0,
    relative_probability_truth_model: bool = False,
) -> ChainHypothesis:
    current: str | None = "R0"
    retired: tuple[str, ...] = ()
    created = 0
    built: list[GapHypothesis] = []
    timeline: list[str | None] = []
    runs: list[int] = []
    for index in range(gaps):
        state = Particle(
            gaps=(),
            timeline=(),
            runs=(),
            current=current,
            retired=retired,
            created=created,
            log_weight=0.0,
            blocks={},
            thetas={},
            ancestry=(),
        )
        if relative_probability_truth_model:
            # Task 8 uses the same interaction in the data-generating truth and
            # the inference target.  Sampling the complete admissible successor
            # set keeps both direct and handoff support alive; the cause changes
            # only their relative odds.
            candidates = list(_legal_gaps(state))
            if index == 0:
                candidates = [
                    candidate
                    for candidate in candidates
                    if (
                        candidate[0].giver is Actor.UNKNOWN
                        or candidate[0].receiver is Actor.UNKNOWN
                    )
                    == open_world
                ]
            log_masses = [
                gap_log_prior(
                    candidate[0],
                    relative_probability_coupling_nats=(relative_probability_coupling_nats),
                )
                + (
                    0.35
                    if short_regime
                    and candidate[0].regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}
                    else 0.0
                )
                for candidate in candidates
            ]
            pivot = max(log_masses)
            masses = [math.exp(value - pivot) for value in log_masses]
            pick = rng.uniform(0.0, sum(masses))
            running = 0.0
            selected = len(candidates) - 1
            for position, mass in enumerate(masses):
                running += mass
                if pick <= running:
                    selected = position
                    break
            gap, regime, retired, created = candidates[selected]
        else:
            mechanism = Mechanism.HANDOFF if index % 2 == 1 else Mechanism.DIRECT
            giver = Actor.UNKNOWN if open_world and index == 0 else Actor.OWNER
            receiver = giver if mechanism is Mechanism.DIRECT else Actor.OWNER
            instance = Instance.TARGET if index % 3 != 2 else Instance.DECOY
            cause = Cause.HABIT if (short_regime and index % 2 == 0) else Cause.OBSERVATION
            options = _prior_move_options((mechanism, giver, receiver, instance, cause), state)
            gap, regime, retired, created, _weight = options[rng.randrange(len(options))]
        built.append(gap)
        timeline.append(regime)
        previous = runs[-1] if runs else 0
        runs.append(
            0 if gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE} else previous + 1
        )
        current = regime
    return ChainHypothesis(
        gaps=tuple(built), regime_timeline=tuple(timeline), run_lengths=tuple(runs)
    )


def build_scenario(
    *,
    gaps: int,
    seed: int,
    high_attribution_ambiguity: bool,
    adverse_delayed_feedback: bool,
    open_world_actor: bool,
    short_regime: bool,
    corrupt_index: int = 0,
    relative_probability_coupling_nats: float = 0.0,
    relative_probability_truth_model: bool = False,
) -> BackboneScenario:
    if relative_probability_coupling_nats < 0.0:
        raise ValueError("relative-probability coupling strength cannot be negative")
    rng = random.Random(f"{PROTOCOL_ID}:scenario:{gaps}:{seed}")
    truth = _truth_chain(
        gaps,
        rng,
        open_world=open_world_actor,
        short_regime=short_regime,
        relative_probability_coupling_nats=relative_probability_coupling_nats,
        relative_probability_truth_model=relative_probability_truth_model,
    )
    strong, weak = (0.62, 0.45) if high_attribution_ambiguity else (0.88, 0.74)
    observations: list[GapObservation] = []
    for index, gap in enumerate(truth.gaps):
        corrupt = adverse_delayed_feedback and index == corrupt_index
        observed_receiver = (
            Actor.GUEST if corrupt and gap.receiver is not Actor.GUEST else gap.receiver
        )
        observed_cause = Cause.ACTOR if corrupt else gap.cause
        x = gap_features(gap)
        theta_truth = (0.4, -0.6, 0.9)
        mean = sum(theta_truth[axis] * x[axis] for axis in range(FEATURE_DIM))
        observations.append(
            GapObservation(
                observed_mechanism=gap.mechanism,
                observed_giver=gap.giver,
                observed_receiver=observed_receiver,
                observed_instance=gap.instance,
                observed_cause=observed_cause,
                observed_regime_change=gap.regime_move
                in {RegimeMove.CREATE, RegimeMove.REACTIVATE},
                placement_bin=index % PLACEMENT_BINS,
                placement_value=mean + rng.gauss(0.0, math.sqrt(NOISE_VARIANCE)),
                mechanism_reliability=strong,
                actor_reliability=weak if corrupt else strong,
                instance_reliability=strong,
                cause_reliability=weak,
                regime_reliability=strong,
            )
        )
    flags = (
        f"{int(high_attribution_ambiguity)}{int(adverse_delayed_feedback)}"
        f"{int(open_world_actor)}{int(short_regime)}"
    )
    coupling_suffix = (
        f"-RPC{relative_probability_coupling_nats:g}" if relative_probability_truth_model else ""
    )
    return BackboneScenario(
        scenario_id=f"G{gaps}-S{seed}-{flags}{coupling_suffix}",
        gaps=gaps,
        high_attribution_ambiguity=high_attribution_ambiguity,
        adverse_delayed_feedback=adverse_delayed_feedback,
        open_world_actor=open_world_actor,
        short_regime=short_regime,
        truth=truth,
        observations=tuple(observations),
        corrupt_index=corrupt_index,
        relative_probability_coupling_nats=relative_probability_coupling_nats,
        relative_probability_truth_model=relative_probability_truth_model,
    )


def registered_scenarios(
    gaps: int,
    seeds: Sequence[int],
    *,
    relative_probability_coupling_nats: float = 0.0,
    relative_probability_truth_model: bool = False,
) -> tuple[BackboneScenario, ...]:
    """The 2x2x2 cell design: ambiguity x delayed feedback x open-world actor.

    ``open_world_actor`` used to be bound to seed parity, and every run so far
    used odd seeds, so the factor was pinned to True and never controlled.  That
    also pinned the truth's actor away from the owner, which silently made the
    consolidation readout unable to fire either of its two errors.
    """

    return tuple(
        build_scenario(
            gaps=gaps,
            seed=seed,
            high_attribution_ambiguity=ambiguity,
            adverse_delayed_feedback=delayed,
            open_world_actor=open_world,
            short_regime=True,
            relative_probability_coupling_nats=relative_probability_coupling_nats,
            relative_probability_truth_model=relative_probability_truth_model,
        )
        for seed in seeds
        for ambiguity in (False, True)
        for delayed in (False, True)
        for open_world in (False, True)
    )


# ---------------------------------------------------------------------------
# Ladder runner
# ---------------------------------------------------------------------------


def measure_enumeration_boundary(gaps: int, *, budget: int) -> dict[str, Any]:
    """Protocol section 1.2: the boundary is measured, never assumed."""

    started = time.perf_counter()
    try:
        total = count_chains(gaps, budget=budget)
    except ExactEnumerationBudgetExceeded as error:
        return {
            "gaps": gaps,
            "enumerable_within_budget": False,
            "state_budget": budget,
            "states_reached": error.reached,
            "seconds": round(time.perf_counter() - started, 6),
        }
    return {
        "gaps": gaps,
        "enumerable_within_budget": True,
        "state_budget": budget,
        "admissible_and_inadmissible_states": total,
        "seconds": round(time.perf_counter() - started, 6),
    }


def run_ladder(
    *,
    gaps_values: Sequence[int],
    seeds: Sequence[int],
    particle_budget: int,
    state_budget: int = 2_000_000,
) -> dict[str, Any]:
    ladder: list[dict[str, Any]] = []
    for gaps in gaps_values:
        boundary = measure_enumeration_boundary(gaps, budget=state_budget)
        entry: dict[str, Any] = {"boundary": boundary, "scenarios": []}
        for scenario in registered_scenarios(gaps, seeds):
            exact_meter = CostMeter(arm=ArmName.EXACT_ORACLE)
            exact_meter.start()
            exact, exact_actions = exact_posterior_with_actions(
                scenario,
                exact_meter,
                caller_role=CallerRole.EXACT_ORACLE,
                state_budget=state_budget,
            )
            exact_meter.stop()
            readings: list[dict[str, Any]] = [
                {
                    "arm": ArmName.EXACT_ORACLE.value,
                    "total_variation": 0.0,
                    "proposal_coverage": 1.0,
                    "log_evidence": None,
                    "truth_in_support": scenario.truth.key in exact,
                    "unresolved_mass": exact[UNRESOLVED_KEY],
                    "effective_sample_size": None,
                    "action_regret": 0.0,
                    "cost": exact_meter.as_dict(),
                }
            ]
            for arm in (
                ArmName.SAMPLED_THETA_PF,
                ArmName.RBPF,
                ArmName.TYPED_RBPF,
                ArmName.ADAPTIVE_TYPED_RBPF,
            ):
                result = run_particle_arm(scenario, arm=arm, budget=particle_budget, seed=seeds[0])
                readings.append(
                    {
                        "arm": arm.value,
                        "total_variation": total_variation(exact, result.posterior),
                        "truth_in_support": scenario.truth.key in result.support,
                        "unresolved_mass": result.posterior[UNRESOLVED_KEY],
                        "effective_sample_size": result.effective_sample_size,
                        "proposal_coverage": proposal_coverage(exact, result.support),
                        "log_evidence": result.log_evidence,
                        "action_regret": action_regret(
                            exact_actions,
                            action_marginal(
                                result.posterior, result.support_chains, scenario.observations
                            ),
                        ),
                        "cost": result.cost,
                    }
                )
            entry["scenarios"].append({"scenario_id": scenario.scenario_id, "readings": readings})
        ladder.append(entry)
    return {
        "protocol_id": PROTOCOL_ID,
        "evidence_status": "development instrument bring-up; no method benefit is claimed",
        "particle_budget": particle_budget,
        "seeds": list(seeds),
        "ladder": ladder,
    }


# ---------------------------------------------------------------------------
# Task 10: particle-budget sweep and the accuracy-compute curve
# ---------------------------------------------------------------------------


DEFAULT_BUDGETS: Final = (8, 16, 24, 48, 96)


@dataclass(frozen=True, slots=True)
class SweepCell:
    """One (gaps, budget, arm) point on the accuracy-compute curve."""

    gaps: int
    budget: int
    arm: str
    replicates: int
    mean_total_variation: float
    stdev_total_variation: float
    mean_proposal_coverage: float
    mean_owner_calibration_error: float
    stdev_owner_calibration_error: float
    mean_action_posterior_distance: float
    mean_decision_regret: float
    truth_coverage: float
    action_abstention_rate: float
    mean_action_regret: float
    mean_effective_sample_size: float
    mean_unique_state_evaluations: float
    mean_proposal_evaluations: float
    mean_elementary_evaluations: float
    mean_wall_clock_seconds: float
    truth_loss_cases: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "gaps": self.gaps,
            "budget": self.budget,
            "arm": self.arm,
            "replicates": self.replicates,
            "mean_total_variation": self.mean_total_variation,
            "stdev_total_variation": self.stdev_total_variation,
            "mean_proposal_coverage": self.mean_proposal_coverage,
            "mean_owner_calibration_error": self.mean_owner_calibration_error,
            "stdev_owner_calibration_error": self.stdev_owner_calibration_error,
            "mean_action_posterior_distance": self.mean_action_posterior_distance,
            "mean_decision_regret": self.mean_decision_regret,
            "truth_coverage": self.truth_coverage,
            "action_abstention_rate": self.action_abstention_rate,
            "mean_action_regret": self.mean_action_regret,
            "mean_effective_sample_size": self.mean_effective_sample_size,
            "mean_unique_state_evaluations": self.mean_unique_state_evaluations,
            "mean_proposal_evaluations": self.mean_proposal_evaluations,
            "mean_elementary_evaluations": self.mean_elementary_evaluations,
            "mean_wall_clock_seconds": self.mean_wall_clock_seconds,
            "truth_loss_cases": list(self.truth_loss_cases),
        }


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def run_budget_sweep(
    *,
    gaps: int,
    scenario_seeds: Sequence[int],
    budgets: Sequence[int] = DEFAULT_BUDGETS,
    replicate_seeds: Sequence[int] = (101, 202, 303),
    state_budget: int = 2_000_000,
) -> dict[str, Any]:
    """Protocol task 10.

    The exact posterior does not depend on the particle budget, so it is
    computed once per scenario and reused across every budget and arm.  Each
    (budget, arm) cell is replicated over independent arm seeds so that mean,
    spread and the seeds that lost the truth are all reported, as protocol
    section 4 requires.
    """

    scenarios = registered_scenarios(gaps, scenario_seeds)
    arms = (
        ArmName.SAMPLED_THETA_PF,
        ArmName.RBPF,
        ArmName.TYPED_RBPF,
        ArmName.ADAPTIVE_TYPED_RBPF,
    )
    references: list[dict[str, Any]] = []
    samples: dict[tuple[int, str], dict[str, list[float]]] = {
        (budget, arm.value): {
            "tv": [],
            "coverage": [],
            "calibration": [],
            "action_distance": [],
            "decision_regret": [],
            "regret": [],
            "ess": [],
            "states": [],
            "proposals": [],
            "elementary": [],
            "wall": [],
        }
        for budget in budgets
        for arm in arms
    }
    covered: dict[tuple[int, str], int] = {key: 0 for key in samples}
    losses: dict[tuple[int, str], list[str]] = {key: [] for key in samples}

    # One scenario's exact posterior at a time.  Holding all of them at once is
    # what turned a G=2 sweep into a multi-gigabyte run: at G=2 a single exact
    # posterior has ~9e5 entries, so caching twenty of them is not a cache.
    for scenario in scenarios:
        meter = CostMeter(arm=ArmName.EXACT_ORACLE)
        meter.start()
        summary = exact_decision_summary(
            scenario,
            meter,
            caller_role=CallerRole.EXACT_ORACLE,
            state_budget=state_budget,
        )
        exact = summary.posterior
        exact_actions = summary.legacy_action_marginal
        meter.stop()
        references.append(
            {
                "scenario_id": scenario.scenario_id,
                "unresolved_mass": exact[UNRESOLVED_KEY],
                "truth_in_exact_support": scenario.truth.key in exact,
                "cost": meter.as_dict(),
            }
        )
        for budget in budgets:
            for arm in arms:
                key = (budget, arm.value)
                bucket = samples[key]
                for seed in replicate_seeds:
                    result = run_particle_arm(scenario, arm=arm, budget=budget, seed=seed)
                    bucket["tv"].append(total_variation(exact, result.posterior))
                    bucket["coverage"].append(proposal_coverage(exact, result.support))
                    arm_actions = embodied_action_posterior(
                        result.posterior, result.support_chains, scenario.observations
                    )
                    bucket["action_distance"].append(
                        action_posterior_distance(summary.embodied_action_posterior, arm_actions)
                    )
                    bucket["calibration"].append(
                        abs(
                            owner_responsibility_mass(
                                result.posterior,
                                result.support_chains,
                                scenario.corrupt_index,
                            )
                            - summary.owner_responsibility
                        )
                    )
                    joint = decision_regret(summary.embodied_action_posterior, arm_actions)
                    if joint is not None:
                        bucket["decision_regret"].append(joint)
                    regret = action_regret(
                        exact_actions,
                        action_marginal(
                            result.posterior, result.support_chains, scenario.observations
                        ),
                    )
                    if regret is not None:
                        bucket["regret"].append(regret)
                    bucket["ess"].append(result.effective_sample_size)
                    bucket["states"].append(float(result.cost["unique_state_target_evaluations"]))
                    bucket["proposals"].append(
                        float(result.cost["proposal_generation_evaluations"])
                    )
                    bucket["elementary"].append(
                        float(result.cost["elementary_likelihood_evaluations"])
                    )
                    bucket["wall"].append(float(result.cost["wall_clock_seconds"]))
                    if scenario.truth.key in result.support:
                        covered[key] += 1
                    else:
                        losses[key].append(f"{scenario.scenario_id}@seed{seed}")
        del exact, exact_actions

    cells: list[dict[str, Any]] = []
    for budget in budgets:
        for arm in arms:
            key = (budget, arm.value)
            bucket = samples[key]
            replicates = len(bucket["tv"])
            cells.append(
                SweepCell(
                    gaps=gaps,
                    budget=budget,
                    arm=arm.value,
                    replicates=replicates,
                    mean_total_variation=sum(bucket["tv"]) / replicates,
                    stdev_total_variation=_stdev(bucket["tv"]),
                    mean_proposal_coverage=sum(bucket["coverage"]) / replicates,
                    mean_owner_calibration_error=sum(bucket["calibration"]) / replicates,
                    stdev_owner_calibration_error=_stdev(bucket["calibration"]),
                    mean_action_posterior_distance=sum(bucket["action_distance"]) / replicates,
                    mean_decision_regret=(
                        sum(bucket["decision_regret"]) / len(bucket["decision_regret"])
                        if bucket["decision_regret"]
                        else 0.0
                    ),
                    truth_coverage=covered[key] / replicates,
                    action_abstention_rate=1.0 - len(bucket["regret"]) / replicates,
                    mean_action_regret=(
                        sum(bucket["regret"]) / len(bucket["regret"]) if bucket["regret"] else 0.0
                    ),
                    mean_effective_sample_size=sum(bucket["ess"]) / replicates,
                    mean_unique_state_evaluations=sum(bucket["states"]) / replicates,
                    mean_proposal_evaluations=sum(bucket["proposals"]) / replicates,
                    mean_elementary_evaluations=sum(bucket["elementary"]) / replicates,
                    mean_wall_clock_seconds=sum(bucket["wall"]) / replicates,
                    truth_loss_cases=tuple(losses[key]),
                ).as_dict()
            )
    return {
        "protocol_id": PROTOCOL_ID,
        "evidence_status": "development instrument sweep; no method benefit is claimed",
        "gaps": gaps,
        "scenario_seeds": list(scenario_seeds),
        "replicate_seeds": list(replicate_seeds),
        "budgets": list(budgets),
        "exact_reference": references,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Task 7: late correction at t-k
# ---------------------------------------------------------------------------


class CorrectionTreatment(StrEnum):
    """How a system may respond to evidence that arrives after the fact."""

    FULL_RERUN = "full_rerun"
    LOCAL_REJUVENATION = "local_rejuvenation"
    REWEIGHT_ONLY = "reweight_only"
    APPEND_ONLY = "append_only"


def repair_observation(scenario: BackboneScenario, index: int) -> BackboneScenario:
    """The late correction: the reading at ``index`` is revised to the truth.

    This is the evidence a household system actually receives late — the owner
    says "that was me, not the guest" — not a new observation of a new event.
    """

    gap = scenario.truth.gaps[index]
    original = scenario.observations[index]
    repaired = GapObservation(
        observed_mechanism=gap.mechanism,
        observed_giver=gap.giver,
        observed_receiver=gap.receiver,
        observed_instance=gap.instance,
        observed_cause=gap.cause,
        observed_regime_change=gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE},
        placement_bin=original.placement_bin,
        placement_value=original.placement_value,
        mechanism_reliability=original.mechanism_reliability,
        actor_reliability=max(original.actor_reliability, 0.88),
        instance_reliability=original.instance_reliability,
        cause_reliability=max(original.cause_reliability, 0.88),
        regime_reliability=original.regime_reliability,
    )
    observations = list(scenario.observations)
    observations[index] = repaired
    return BackboneScenario(
        scenario_id=f"{scenario.scenario_id}+corrected@{index}",
        gaps=scenario.gaps,
        high_attribution_ambiguity=scenario.high_attribution_ambiguity,
        adverse_delayed_feedback=scenario.adverse_delayed_feedback,
        open_world_actor=scenario.open_world_actor,
        short_regime=scenario.short_regime,
        truth=scenario.truth,
        observations=tuple(observations),
        corrupt_index=scenario.corrupt_index,
        relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        relative_probability_truth_model=scenario.relative_probability_truth_model,
    )


def _analytic_total(
    chain: ChainHypothesis, observations: Sequence[GapObservation], meter: CostMeter
) -> float:
    return sum(
        block.log_marginal() for block in analytic_blocks_for(chain, observations, meter).values()
    )


def _finalize(
    particles: list[Particle],
    log_evidence: float,
    observations: Sequence[GapObservation],
    meter: CostMeter,
    *,
    unresolved_log_weight: float | None = None,
) -> ArmResult:
    meter.ancestry_window_length = max(len(particle.ancestry) for particle in particles)
    final_log_weights = [particle.log_weight for particle in particles]
    final_masses = _normalized_masses(final_log_weights)
    ess = _effective_sample_size(final_masses)
    log_evidence += _logsumexp(final_log_weights) - math.log(len(particles))
    support: dict[str, ChainHypothesis] = {}
    chain_mass: dict[str, float] = {}
    embodied_action_mass: dict[str, float] = {}
    for particle, mass in zip(particles, final_masses, strict=True):
        chain = particle.chain()
        key = particle.persistent_chain_key or chain.key
        support.setdefault(key, chain)
        chain_mass[key] = chain_mass.get(key, 0.0) + mass
        action_key = _particle_embodied_action(particle).key
        embodied_action_mass[action_key] = embodied_action_mass.get(action_key, 0.0) + mass
    log_unresolved = (
        unresolved_log_target(observations)
        if unresolved_log_weight is None
        else unresolved_log_weight
    )
    total_mass = sum(chain_mass.values())
    if total_mass <= 0.0 or not math.isfinite(log_evidence):
        posterior = dict.fromkeys(chain_mass, 0.0)
        posterior[UNRESOLVED_KEY] = 1.0
    else:
        pivot = max(log_evidence, log_unresolved)
        evidence_mass = math.exp(log_evidence - pivot)
        unresolved_mass = math.exp(log_unresolved - pivot)
        unresolved_probability = unresolved_mass / (evidence_mass + unresolved_mass)
        posterior = {
            key: (1.0 - unresolved_probability) * mass / total_mass
            for key, mass in chain_mass.items()
        }
        posterior[UNRESOLVED_KEY] = unresolved_probability
    meter.stop()
    return ArmResult(
        arm=meter.arm,
        posterior=posterior,
        support=frozenset(support),
        support_chains=dict(support),
        effective_sample_size=ess,
        log_evidence=log_evidence,
        cost=meter.as_dict(),
        embodied_action_posterior_cache=embodied_action_mass,
    )


def _run_stream(
    scenario: BackboneScenario,
    observations: Sequence[GapObservation],
    *,
    arm: ArmName,
    budget: int,
    seed: int,
    stop: int | None = None,
) -> tuple[list[Particle], float, random.Random, CostMeter]:
    meter = CostMeter(arm=arm, particle_count=budget)
    meter.start()
    rng = random.Random(f"{PROTOCOL_ID}:{scenario.scenario_id}:{arm.value}:{seed}")
    config = ArmConfiguration.of(arm)
    particles = [
        Particle(
            gaps=(),
            timeline=(),
            runs=(),
            current="R0",
            retired=(),
            created=0,
            log_weight=0.0,
            blocks={},
            thetas={},
            ancestry=("root",),
        )
        for _ in range(budget)
    ]
    log_evidence = 0.0
    limit = len(observations) if stop is None else stop
    for index in range(limit):
        _step_particles(
            particles,
            observations[index],
            index,
            config=config,
            rng=rng,
            meter=meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        meter.track_live(len(particles))
        log_weights = [particle.log_weight for particle in particles]
        weights = _normalized_masses(log_weights)
        if index < len(observations) - 1 and _effective_sample_size(weights) < len(particles) / 2.0:
            log_evidence += _logsumexp(log_weights) - math.log(len(particles))
            particles = _systematic_resample(particles, weights, rng)
            meter.resample()
    return particles, log_evidence, rng, meter


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _observation_payload(observations: Sequence[GapObservation]) -> list[dict[str, Any]]:
    return [
        {
            "observed_mechanism": observation.observed_mechanism.value,
            "observed_giver": observation.observed_giver.value,
            "observed_receiver": observation.observed_receiver.value,
            "observed_instance": observation.observed_instance.value,
            "observed_cause": observation.observed_cause.value,
            "observed_regime_change": observation.observed_regime_change,
            "placement_bin": observation.placement_bin,
            "placement_value": observation.placement_value,
            "mechanism_reliability": observation.mechanism_reliability,
            "actor_reliability": observation.actor_reliability,
            "instance_reliability": observation.instance_reliability,
            "cause_reliability": observation.cause_reliability,
            "regime_reliability": observation.regime_reliability,
        }
        for observation in observations
    ]


def _boundary_payload(boundaries: Sequence[LatentBoundary]) -> list[dict[str, Any]]:
    return [
        {
            "current": boundary.current,
            "retired": list(boundary.retired),
            "created": boundary.created,
            "run_length": boundary.run_length,
        }
        for boundary in boundaries
    ]


def _analytic_blocks_payload(
    blocks: Mapping[tuple[str, str], AnalyticBlock],
) -> list[dict[str, Any]]:
    return [
        {
            "cell": list(cell),
            "alpha": list(block.alpha),
            "a_matrix": [list(row) for row in block.a_matrix],
            "b_vector": list(block.b_vector),
            "precision": block.precision,
            "xi": block.xi,
            "count": block.count,
        }
        for cell, block in sorted(blocks.items())
    ]


def _position_token(index: int, gap: GapHypothesis) -> int:
    payload = f"{index}:{gap.key}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _position_xor_sha256(gaps: Sequence[GapHypothesis]) -> str:
    """One-pass source identity prepared before a correction arrives."""

    value = 0
    for index, gap in enumerate(gaps):
        value ^= _position_token(index, gap)
    return f"{value:064x}"


def _updated_position_xor_sha256(
    source_digest: str,
    old_window: Sequence[GapHypothesis],
    new_window: Sequence[GapHypothesis],
    *,
    window_start: int,
) -> str:
    """Update a position-bound chain identity by hashing exactly the window."""

    if len(old_window) != len(new_window):
        raise ValueError("Task-7 window identity update must preserve length")
    value = int(source_digest, 16)
    for offset, (before, after) in enumerate(zip(old_window, new_window, strict=True)):
        if before == after:
            continue
        index = window_start + offset
        value ^= _position_token(index, before)
        value ^= _position_token(index, after)
    return f"{value:064x}"


def _checkpoint_unsigned_payload(
    *,
    source_chain_sha256: str,
    source_position_xor_sha256: str,
    source_observations_sha256: str,
    analytic_blocks_sha256: str,
    boundary_states: Sequence[LatentBoundary],
) -> dict[str, Any]:
    return {
        "format_id": TASK7_CHECKPOINT_FORMAT_ID,
        "source_chain_sha256": source_chain_sha256,
        "source_position_xor_sha256": source_position_xor_sha256,
        "source_observations_sha256": source_observations_sha256,
        "analytic_blocks_sha256": analytic_blocks_sha256,
        "boundary_states": _boundary_payload(boundary_states),
    }


def _seal_window_checkpoint(
    particle: Particle, observations: Sequence[GapObservation]
) -> WindowCheckpoint:
    """Seal the boundary summaries produced during the original forward pass."""

    if len(particle.boundary_states) != len(particle.gaps) + 1:
        raise CheckpointIntegrityError("checkpoint must contain one boundary per gap plus root")
    expected_terminal_actor = particle.gaps[-1].receiver if particle.gaps else None
    if particle.terminal_responsible_actor is not expected_terminal_actor:
        raise CheckpointIntegrityError("terminal responsible-actor cache disagrees with history")
    source_chain_sha256 = _sha256_json(
        {
            "key": particle.chain().key,
            "timeline": list(particle.timeline),
            "runs": list(particle.runs),
        }
    )
    source_position_xor_sha256 = _position_xor_sha256(particle.gaps)
    source_observations_sha256 = _sha256_json(_observation_payload(observations))
    analytic_blocks_sha256 = _sha256_json(_analytic_blocks_payload(particle.blocks))
    unsigned = _checkpoint_unsigned_payload(
        source_chain_sha256=source_chain_sha256,
        source_position_xor_sha256=source_position_xor_sha256,
        source_observations_sha256=source_observations_sha256,
        analytic_blocks_sha256=analytic_blocks_sha256,
        boundary_states=particle.boundary_states,
    )
    content_sha256 = _sha256_json(unsigned)
    checkpoint = WindowCheckpoint(
        format_id=TASK7_CHECKPOINT_FORMAT_ID,
        source_chain_sha256=source_chain_sha256,
        source_position_xor_sha256=source_position_xor_sha256,
        source_observations_sha256=source_observations_sha256,
        analytic_blocks_sha256=analytic_blocks_sha256,
        boundary_states=particle.boundary_states,
        content_sha256=content_sha256,
        serialized_bytes=len(_canonical_json_bytes({**unsigned, "content_sha256": content_sha256})),
    )
    particle.checkpoint = checkpoint
    return checkpoint


def _verify_window_checkpoint(
    particle: Particle, source_observations: Sequence[GapObservation]
) -> WindowCheckpoint:
    checkpoint = particle.checkpoint
    if checkpoint is None or checkpoint.format_id != TASK7_CHECKPOINT_FORMAT_ID:
        raise CheckpointIntegrityError("missing or unsupported Task-7 checkpoint")
    unsigned = _checkpoint_unsigned_payload(
        source_chain_sha256=checkpoint.source_chain_sha256,
        source_position_xor_sha256=checkpoint.source_position_xor_sha256,
        source_observations_sha256=checkpoint.source_observations_sha256,
        analytic_blocks_sha256=checkpoint.analytic_blocks_sha256,
        boundary_states=checkpoint.boundary_states,
    )
    if _sha256_json(unsigned) != checkpoint.content_sha256:
        raise CheckpointIntegrityError("Task-7 checkpoint content hash mismatch")
    expected_chain = _sha256_json(
        {
            "key": particle.chain().key,
            "timeline": list(particle.timeline),
            "runs": list(particle.runs),
        }
    )
    if checkpoint.source_chain_sha256 != expected_chain:
        raise CheckpointIntegrityError("Task-7 checkpoint does not bind this particle")
    if checkpoint.source_position_xor_sha256 != _position_xor_sha256(particle.gaps):
        raise CheckpointIntegrityError("Task-7 checkpoint position identity mismatch")
    if checkpoint.source_observations_sha256 != _sha256_json(
        _observation_payload(source_observations)
    ):
        raise CheckpointIntegrityError("Task-7 checkpoint source stream mismatch")
    if checkpoint.analytic_blocks_sha256 != _sha256_json(_analytic_blocks_payload(particle.blocks)):
        raise CheckpointIntegrityError("Task-7 checkpoint analytic-state mismatch")
    if particle.boundary_states != checkpoint.boundary_states:
        raise CheckpointIntegrityError("Task-7 checkpoint boundary-state mismatch")
    if len(checkpoint.boundary_states) != len(particle.gaps) + 1:
        raise CheckpointIntegrityError("Task-7 checkpoint boundary count mismatch")
    return checkpoint


@dataclass(frozen=True, slots=True)
class _ReplayedLatentState:
    """A gap sequence replayed through the typed regime transition system."""

    chain: ChainHypothesis
    current: str | None
    retired: tuple[str, ...]
    created: int


@dataclass(frozen=True, slots=True)
class _WindowReplay:
    """Only the latent states materialized inside one repair window."""

    timeline: tuple[str | None, ...]
    runs: tuple[int, ...]
    boundaries: tuple[LatentBoundary, ...]


def _replay_gap_sequence(gaps: Sequence[GapHypothesis]) -> _ReplayedLatentState | None:
    """Rebuild dependent regime state, rejecting an impossible edited chain.

    A local edit cannot copy the old timeline blindly: changing a CREATE or
    REACTIVATE move can make a later target unreachable.  Replaying the fixed
    suffix is therefore both the state-machine check and the definition of
    "keep outside the window" used by the rejuvenation kernel.
    """

    current: str | None = "R0"
    retired: tuple[str, ...] = ()
    created = 0
    timeline: list[str | None] = []
    runs: list[int] = []
    for gap in gaps:
        if not gap_is_admissible(gap):
            return None
        successor = next(
            (
                (next_regime, next_retired, next_created)
                for move, target, next_regime, next_retired, next_created in _regime_successors(
                    gap.cause, current, retired, created
                )
                if move is gap.regime_move and target == gap.regime_target
            ),
            None,
        )
        if successor is None:
            return None
        next_regime, retired, created = successor
        previous = runs[-1] if runs else 0
        runs.append(
            0 if gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE} else previous + 1
        )
        timeline.append(next_regime)
        current = next_regime
    return _ReplayedLatentState(
        chain=ChainHypothesis(
            gaps=tuple(gaps), regime_timeline=tuple(timeline), run_lengths=tuple(runs)
        ),
        current=current,
        retired=retired,
        created=created,
    )


def _replay_window_from_boundary(
    gaps: Sequence[GapHypothesis], left: LatentBoundary
) -> _WindowReplay | None:
    """Replay exactly ``len(gaps)`` transitions from a sealed left boundary."""

    current = left.current
    retired = left.retired
    created = left.created
    run_length = left.run_length
    timeline: list[str | None] = []
    runs: list[int] = []
    boundaries: list[LatentBoundary] = [left]
    for gap in gaps:
        if not gap_is_admissible(gap):
            return None
        successor = next(
            (
                (next_regime, next_retired, next_created)
                for move, target, next_regime, next_retired, next_created in _regime_successors(
                    gap.cause, current, retired, created
                )
                if move is gap.regime_move and target == gap.regime_target
            ),
            None,
        )
        if successor is None:
            return None
        current, retired, created = successor
        run_length = (
            0 if gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE} else run_length + 1
        )
        timeline.append(current)
        runs.append(run_length)
        boundaries.append(
            LatentBoundary(
                current=current,
                retired=retired,
                created=created,
                run_length=run_length,
            )
        )
    return _WindowReplay(
        timeline=tuple(timeline),
        runs=tuple(runs),
        boundaries=tuple(boundaries),
    )


def _proposal_particle(boundary: LatentBoundary) -> Particle:
    """Minimal state consumed by the one-gap proposal; no history is scanned."""

    return Particle(
        gaps=(),
        timeline=(),
        runs=(boundary.run_length,),
        current=boundary.current,
        retired=boundary.retired,
        created=boundary.created,
        log_weight=0.0,
        blocks={},
        thetas={},
        ancestry=("rejuvenation-window-boundary",),
        boundary_states=(boundary,),
    )


def _prefix_particle(chain: ChainHypothesis, stop: int) -> Particle:
    replayed = _replay_gap_sequence(chain.gaps[:stop])
    if replayed is None:  # pragma: no cover - a stored particle must already be valid
        raise ValueError("stored particle contains an unreachable prefix")
    return Particle(
        gaps=replayed.chain.gaps,
        timeline=replayed.chain.regime_timeline,
        runs=replayed.chain.run_lengths,
        current=replayed.current,
        retired=replayed.retired,
        created=replayed.created,
        log_weight=0.0,
        blocks={},
        thetas={},
        ancestry=("rejuvenation-prefix",),
    )


def _local_proposal_context(
    prefix: Particle,
    observation: GapObservation,
    *,
    config: ArmConfiguration,
    meter: CostMeter,
    relative_probability_coupling_nats: float = 0.0,
) -> tuple[
    tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...],
    list[float],
    float,
]:
    if not config.typed:
        return (), [], 1.0
    if config.adaptive:
        candidates, scores, fit, radius = _adaptive_candidates(
            prefix,
            observation,
            meter,
            relative_probability_coupling_nats=relative_probability_coupling_nats,
        )
        meter.note_radius(radius)
        return candidates, scores, _adaptive_escape(fit)
    candidates = _typed_candidates(prefix, observation, TYPED_FIXED_RADIUS)
    fixed_scores: list[float] = []
    for candidate in candidates:
        meter.proposal()
        fixed_scores.append(
            gap_log_prior(
                candidate[0],
                relative_probability_coupling_nats=(relative_probability_coupling_nats),
            )
            + gap_log_likelihood(candidate[0], observation, meter)
        )
    meter.note_radius(TYPED_FIXED_RADIUS)
    return candidates, fixed_scores, TYPED_ESCAPE_PROBABILITY


def _local_mixture_log_density(
    gap: GapHypothesis,
    prefix: Particle,
    candidates: Sequence[tuple[GapHypothesis, str | None, tuple[str, ...], int]],
    scores: Sequence[float],
    escape: float,
) -> float:
    prior = _prior_log_density(gap, prefix)
    if not candidates or escape >= 1.0:
        return prior
    typed = _typed_log_density_from_scores(gap, candidates, scores)
    terms = [math.log(escape) + prior]
    if math.isfinite(typed):
        terms.append(math.log1p(-escape) + typed)
    return _logsumexp(terms)


def _conditional_nonself_log_density(
    target: GapHypothesis,
    excluded: GapHypothesis,
    prefix: Particle,
    candidates: Sequence[tuple[GapHypothesis, str | None, tuple[str, ...], int]],
    scores: Sequence[float],
    escape: float,
) -> float:
    """Exact density after conditioning the local mixture on a non-self move."""

    target_log_q = _local_mixture_log_density(target, prefix, candidates, scores, escape)
    excluded_log_q = _local_mixture_log_density(excluded, prefix, candidates, scores, escape)
    excluded_probability = math.exp(excluded_log_q) if math.isfinite(excluded_log_q) else 0.0
    if excluded_probability >= 1.0 - 1e-15:
        raise NonSelfProposalUnavailableError("local mixture has no non-self probability mass")
    return target_log_q - math.log1p(-excluded_probability)


def _draw_local_gap(
    prefix: Particle,
    observation: GapObservation,
    *,
    config: ArmConfiguration,
    rng: random.Random,
    meter: CostMeter,
    relative_probability_coupling_nats: float = 0.0,
    context: tuple[
        tuple[tuple[GapHypothesis, str | None, tuple[str, ...], int], ...],
        list[float],
        float,
    ]
    | None = None,
    exclude_gap: GapHypothesis | None = None,
) -> tuple[GapHypothesis, float]:
    """Draw one full-support non-self proposal and return its exact density."""

    candidates, scores, escape = context or _local_proposal_context(
        prefix,
        observation,
        config=config,
        meter=meter,
        relative_probability_coupling_nats=relative_probability_coupling_nats,
    )
    for _attempt in range(64):
        if candidates and rng.random() >= escape:
            maximum = max(scores)
            masses = [math.exp(value - maximum) for value in scores]
            pick = rng.uniform(0.0, sum(masses))
            running = 0.0
            selected = len(candidates) - 1
            for index, mass in enumerate(masses):
                running += mass
                if pick <= running:
                    selected = index
                    break
            gap = candidates[selected][0]
        else:
            gap, _regime, _retired, _created, _move_log_q = _sample_prior_gap(prefix, rng, meter)
        if exclude_gap is None:
            return gap, _local_mixture_log_density(gap, prefix, candidates, scores, escape)
        if gap == exclude_gap:
            meter.self_draw_rejections += 1
            continue
        return gap, _conditional_nonself_log_density(
            gap, exclude_gap, prefix, candidates, scores, escape
        )
    raise NonSelfProposalUnavailableError("failed to draw a non-self gap in 64 attempts")


def _correction_log_ratio(
    chain: ChainHypothesis,
    original: Sequence[GapObservation],
    corrected: Sequence[GapObservation],
    correction_index: int,
    meter: CostMeter,
) -> float:
    gap = chain.gaps[correction_index]
    ratio = gap_log_likelihood(gap, corrected[correction_index], meter) - gap_log_likelihood(
        gap, original[correction_index], meter
    )
    before = original[correction_index]
    after = corrected[correction_index]
    if (before.placement_bin, before.placement_value) != (
        after.placement_bin,
        after.placement_value,
    ):
        ratio += _analytic_total(chain, corrected, meter) - _analytic_total(chain, original, meter)
    return ratio


def _apply_fixed_observation_correction(
    particle: Particle,
    original_observation: GapObservation,
    corrected_observation: GapObservation,
    correction_index: int,
    meter: CostMeter,
) -> float:
    """Move one particle and its analytic checkpoint to the corrected target in O(1).

    The likelihood-ratio reweight and the sufficient-statistic mutation must be
    performed together.  Reweighting alone leaves ``particle.blocks`` on the old
    observation, after which a local MH proposal would downdate a contribution
    that was never inserted.  Only the corrected gap's cell is touched here.
    """

    gap = particle.gaps[correction_index]
    ratio = gap_log_likelihood(gap, corrected_observation, meter) - gap_log_likelihood(
        gap, original_observation, meter
    )
    if (original_observation.placement_bin, original_observation.placement_value) == (
        corrected_observation.placement_bin,
        corrected_observation.placement_value,
    ):
        return ratio

    cell = particle.chain().cell_of(correction_index)
    block = particle.blocks.get(cell)
    if block is None:
        raise CheckpointIntegrityError("corrected analytic cell is absent from the checkpoint")
    changed = block.clone()
    before = changed.log_marginal()
    try:
        changed.downdate(
            gap_features(gap),
            original_observation.placement_value,
            original_observation.placement_bin,
        )
    except ValueError as error:
        raise CheckpointIntegrityError(
            "analytic checkpoint cannot retract the original corrected contribution"
        ) from error
    meter.analytic()
    changed.update(
        gap_features(gap),
        corrected_observation.placement_value,
        corrected_observation.placement_bin,
    )
    meter.analytic()
    ratio += changed.log_marginal() - before
    particle.blocks = _persistent_blocks_with_changes(particle.blocks, {cell: changed})
    return ratio


@dataclass(frozen=True, slots=True)
class WindowRejuvenationReceipt:
    """Machine-readable outcome of the local kernel before any fallback."""

    window_start: int
    window_stop: int
    valid_bridge_proposals: int
    fallback_required: bool
    fallback_reasons: tuple[str, ...]


def _window_chain(
    current: ChainHypothesis,
    window_gaps: Sequence[GapHypothesis],
    replay: _WindowReplay,
    *,
    window_start: int,
    window_stop: int,
    meter: CostMeter,
) -> ChainHypothesis:
    window_length = window_stop - window_start
    meter.persistent_sequence_nodes_created += 3
    meter.persistent_window_items_written += 3 * window_length
    meter.track_repair_window(TASK7_MAX_LIVE_ITEMS_PER_WINDOW_UNIT * window_length + 1)
    return ChainHypothesis(
        gaps=_persistent_replace(current.gaps, window_start, window_stop, window_gaps),
        regime_timeline=_persistent_replace(
            current.regime_timeline, window_start, window_stop, replay.timeline
        ),
        run_lengths=_persistent_replace(
            current.run_lengths, window_start, window_stop, replay.runs
        ),
    )


def _window_analytic_delta(
    current: ChainHypothesis,
    proposed: ChainHypothesis,
    observations: Sequence[GapObservation],
    blocks: Mapping[tuple[str, str], AnalyticBlock],
    *,
    window_start: int,
    window_stop: int,
    meter: CostMeter,
) -> tuple[float, dict[tuple[str, str], AnalyticBlock]]:
    """Return an exact affected-cell marginal delta without scanning the suffix."""

    affected = {
        *(current.cell_of(index) for index in range(window_start, window_stop)),
        *(proposed.cell_of(index) for index in range(window_start, window_stop)),
    }
    changed = {cell: blocks.get(cell, AnalyticBlock()).clone() for cell in affected}
    before = sum(blocks.get(cell, AnalyticBlock()).log_marginal() for cell in affected)
    for index in range(window_start, window_stop):
        gap = current.gaps[index]
        observation = observations[index]
        try:
            changed[current.cell_of(index)].downdate(
                gap_features(gap), observation.placement_value, observation.placement_bin
            )
        except ValueError as error:
            raise CheckpointIntegrityError(
                "analytic checkpoint cannot remove a recorded window contribution"
            ) from error
        meter.analytic()
        meter.window_gap_target_evaluations += 1
    for index in range(window_start, window_stop):
        gap = proposed.gaps[index]
        observation = observations[index]
        changed[proposed.cell_of(index)].update(
            gap_features(gap), observation.placement_value, observation.placement_bin
        )
        meter.analytic()
        meter.window_gap_target_evaluations += 1
    after = sum(block.log_marginal() for block in changed.values())
    return after - before, changed


def _window_conditional_target_delta(
    current: ChainHypothesis,
    proposed: ChainHypothesis,
    observations: Sequence[GapObservation],
    blocks: Mapping[tuple[str, str], AnalyticBlock],
    *,
    window_start: int,
    window_stop: int,
    meter: CostMeter,
    relative_probability_coupling_nats: float = 0.0,
) -> tuple[float, float, dict[tuple[str, str], AnalyticBlock]]:
    """Exact conditional-target change with the outside chain held fixed.

    The local kernel and the full rerun target must not differ by an implicit
    objective.  Boundary preservation fixes the prefix and suffix; this routine
    therefore evaluates every discrete and analytic term whose value may change
    inside the declared window.  Its work is strictly ``O(window)`` and never
    reads an untouched suffix item.
    """

    analytic_delta, changed = _window_analytic_delta(
        current,
        proposed,
        observations,
        blocks,
        window_start=window_start,
        window_stop=window_stop,
        meter=meter,
    )
    discrete_delta = 0.0
    for index in range(window_start, window_stop):
        before = current.gaps[index]
        after = proposed.gaps[index]
        discrete_delta += gap_log_prior(
            after,
            relative_probability_coupling_nats=relative_probability_coupling_nats,
        ) - gap_log_prior(
            before,
            relative_probability_coupling_nats=relative_probability_coupling_nats,
        )
        discrete_delta += gap_log_likelihood(after, observations[index], meter)
        discrete_delta -= gap_log_likelihood(before, observations[index], meter)
        meter.window_gap_target_evaluations += 1
    return discrete_delta + analytic_delta, analytic_delta, changed


def _commit_changed_blocks(
    blocks: Mapping[tuple[str, str], AnalyticBlock],
    changed: Mapping[tuple[str, str], AnalyticBlock],
) -> PersistentBlockMap:
    return _persistent_blocks_with_changes(blocks, changed)


def _window_rejuvenate(
    particles: list[Particle],
    observations: Sequence[GapObservation],
    *,
    window_start: int,
    window_stop: int,
    sweeps: int,
    config: ArmConfiguration,
    rng: random.Random,
    meter: CostMeter,
    relative_probability_coupling_nats: float = 0.0,
    source_observations: Sequence[GapObservation] | None = None,
    checkpoints_preverified: bool = False,
) -> WindowRejuvenationReceipt:
    """Metropolis-within-Gibbs repair of only the declared gap window.

    Every proposal changes exactly one gap in ``[window_start, window_stop)``.
    The prefix and suffix are copied byte-for-byte.  Only the declared window is
    replayed, and its final sufficient state must equal the sealed right boundary;
    an incompatible bridge is rejected without visiting the suffix.
    The proposal is a typed/prior mixture with a non-zero prior escape, and the
    Hastings ratio uses that same mixture in both directions.  Consequently the
    kernel is not a suffix rerun and does not smuggle an oracle enumerator into
    an approximate arm.
    """

    if not 0 <= window_start < window_stop <= len(observations):
        raise ValueError("invalid Task-7 rejuvenation window")
    if sweeps <= 0:
        raise ValueError("Task-7 rejuvenation sweeps must be positive")
    checkpoint_source = observations if source_observations is None else source_observations
    if checkpoints_preverified and any(particle.checkpoint is None for particle in particles):
        raise CheckpointIntegrityError("preverified Task-7 checkpoint is missing")
    if not checkpoints_preverified:
        for particle in particles:
            if particle.checkpoint is None:
                sealed_checkpoint = _seal_window_checkpoint(particle, checkpoint_source)
                meter.checkpoint_bytes += sealed_checkpoint.serialized_bytes
            _verify_window_checkpoint(particle, checkpoint_source)

    fallback_reasons: set[str] = set()
    valid_bridge_proposals = 0
    for particle in particles:
        particle_checkpoint = particle.checkpoint
        if particle_checkpoint is None:  # guarded above, retained for type narrowing
            raise CheckpointIntegrityError("Task-7 checkpoint missing after validation")
        left = particle_checkpoint.boundary_states[window_start]
        right = particle_checkpoint.boundary_states[window_stop]
        meter.checkpoint_boundary_reads += 2
        current = particle.chain()
        original_window_gaps = tuple(
            current.gaps[index] for index in range(window_start, window_stop)
        )
        current_window = _replay_window_from_boundary(original_window_gaps, left)
        if current_window is None or current_window.boundaries[-1] != right:
            raise CheckpointIntegrityError("stored Task-7 window does not join its boundaries")
        # Copy-on-write is confined to the affected cells in
        # ``_window_analytic_delta``.  Cloning the whole dictionary here would
        # make repair memory and work grow with an untouched long suffix.
        current_blocks = particle.blocks
        for _ in range(sweeps):
            for gap_index in range(window_start, window_stop):
                offset = gap_index - window_start
                prefix = _proposal_particle(current_window.boundaries[offset])
                candidates, scores, escape = _local_proposal_context(
                    prefix,
                    observations[gap_index],
                    config=config,
                    meter=meter,
                    relative_probability_coupling_nats=(relative_probability_coupling_nats),
                )
                current_gap = current.gaps[gap_index]
                try:
                    proposed_gap, forward_log_q = _draw_local_gap(
                        prefix,
                        observations[gap_index],
                        config=config,
                        rng=rng,
                        meter=meter,
                        relative_probability_coupling_nats=(relative_probability_coupling_nats),
                        context=(candidates, scores, escape),
                        exclude_gap=current_gap,
                    )
                    reverse_log_q = _conditional_nonself_log_density(
                        current_gap,
                        proposed_gap,
                        prefix,
                        candidates,
                        scores,
                        escape,
                    )
                except NonSelfProposalUnavailableError:
                    fallback_reasons.add("nonself_proposal_unavailable")
                    continue
                meter.rejuvenation_proposals += 1
                if proposed_gap == current_gap:
                    meter.self_draw_rejections += 1
                    fallback_reasons.add("self_proposal_returned")
                    continue
                meter.nonself_rejuvenation_proposals += 1
                edited_window = [current.gaps[index] for index in range(window_start, window_stop)]
                edited_window[offset] = proposed_gap
                replayed_window = _replay_window_from_boundary(edited_window, left)
                if replayed_window is None or replayed_window.boundaries[-1] != right:
                    meter.invalid_bridge_proposals += 1
                    continue
                if not math.isfinite(forward_log_q) or not math.isfinite(reverse_log_q):
                    fallback_reasons.add("nonfinite_proposal_density")
                    continue
                valid_bridge_proposals += 1
                proposed = _window_chain(
                    current,
                    edited_window,
                    replayed_window,
                    window_start=window_start,
                    window_stop=window_stop,
                    meter=meter,
                )
                (
                    conditional_target_delta,
                    analytic_delta,
                    proposed_blocks,
                ) = _window_conditional_target_delta(
                    current,
                    proposed,
                    observations,
                    current_blocks,
                    window_start=window_start,
                    window_stop=window_stop,
                    meter=meter,
                    relative_probability_coupling_nats=(relative_probability_coupling_nats),
                )
                optimized_single_gap_delta = (
                    gap_log_prior(
                        proposed_gap,
                        relative_probability_coupling_nats=(relative_probability_coupling_nats),
                    )
                    - gap_log_prior(
                        current_gap,
                        relative_probability_coupling_nats=(relative_probability_coupling_nats),
                    )
                    + gap_log_likelihood(proposed_gap, observations[gap_index], meter)
                    - gap_log_likelihood(current_gap, observations[gap_index], meter)
                    + analytic_delta
                )
                meter.conditional_target_checks += 1
                if not math.isclose(
                    conditional_target_delta,
                    optimized_single_gap_delta,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    meter.conditional_target_mismatches += 1
                    fallback_reasons.add("conditional_target_mismatch")
                    return WindowRejuvenationReceipt(
                        window_start=window_start,
                        window_stop=window_stop,
                        valid_bridge_proposals=valid_bridge_proposals,
                        fallback_required=True,
                        fallback_reasons=tuple(sorted(fallback_reasons)),
                    )
                log_target_ratio = conditional_target_delta
                log_acceptance = log_target_ratio + reverse_log_q - forward_log_q
                if not math.isfinite(log_acceptance):
                    fallback_reasons.add("nonfinite_local_acceptance_ratio")
                    continue
                if math.log(max(rng.random(), 1e-300)) <= min(0.0, log_acceptance):
                    current = proposed
                    current_window = replayed_window
                    current_blocks = _commit_changed_blocks(current_blocks, proposed_blocks)
                    meter.rejuvenation_accepts += 1
        particle.gaps = current.gaps
        particle.timeline = current.regime_timeline
        particle.runs = current.run_lengths
        particle.blocks = current_blocks
        particle.boundary_states = _persistent_replace(
            particle_checkpoint.boundary_states,
            window_start,
            window_stop + 1,
            current_window.boundaries,
        )
        meter.persistent_sequence_nodes_created += 1
        meter.persistent_window_items_written += window_stop - window_start + 1
        terminal = particle_checkpoint.boundary_states[-1]
        particle.current = terminal.current
        particle.retired = terminal.retired
        particle.created = terminal.created
        current_window_gaps = tuple(
            current.gaps[index] for index in range(window_start, window_stop)
        )
        if window_stop == len(current.gaps):
            particle.terminal_responsible_actor = current_window_gaps[-1].receiver
        particle.persistent_chain_key = (
            f"position-xor-v1:{len(current.gaps):016x}:"
            + _updated_position_xor_sha256(
                particle_checkpoint.source_position_xor_sha256,
                original_window_gaps,
                current_window_gaps,
                window_start=window_start,
            )
        )
        # The source-bound checkpoint has served its purpose.  It must not be
        # silently reused for a later correction against the revised particle.
        particle.checkpoint = None
        particle.log_weight = 0.0
        particle.repair_lineage = (
            *particle.repair_lineage,
            f"window-rejuvenation:{window_start}:{window_stop}",
        )
    if valid_bridge_proposals == 0:
        fallback_reasons.add("no_valid_boundary_preserving_proposal")
    return WindowRejuvenationReceipt(
        window_start=window_start,
        window_stop=window_stop,
        valid_bridge_proposals=valid_bridge_proposals,
        fallback_required=bool(fallback_reasons),
        fallback_reasons=tuple(sorted(fallback_reasons)),
    )


_ADDITIVE_COST_FIELDS: Final = (
    "elementary_likelihood_evaluations",
    "proposal_generation_evaluations",
    "analytic_block_updates",
    "resampling_events",
    "rejuvenation_proposals",
    "rejuvenation_accepts",
    "fixed_gap_reweight_evaluations",
    "invalid_bridge_proposals",
    "window_gap_target_evaluations",
    "checkpoint_boundary_reads",
    "checkpoint_bytes",
    "replay_fallbacks",
    "nonself_rejuvenation_proposals",
    "self_draw_rejections",
    "persistent_sequence_nodes_created",
    "persistent_window_items_written",
    "untouched_suffix_items_read",
    "untouched_suffix_items_copied",
    "untouched_suffix_items_rehashed",
    "conditional_target_checks",
    "conditional_target_mismatches",
)


def _combine_cost_meters(*meters: CostMeter) -> CostMeter:
    if not meters:
        raise ValueError("at least one cost meter is required")
    combined = CostMeter(
        arm=meters[0].arm,
        particle_count=max(meter.particle_count for meter in meters),
    )
    for name in _ADDITIVE_COST_FIELDS:
        setattr(combined, name, sum(int(getattr(meter, name)) for meter in meters))
    combined._scored_keys = set().union(*(meter._scored_keys for meter in meters))
    combined.ancestry_window_length = max(meter.ancestry_window_length for meter in meters)
    combined.proposal_radius_sum = sum(meter.proposal_radius_sum for meter in meters)
    combined.proposal_radius_count = sum(meter.proposal_radius_count for meter in meters)
    combined.wall_clock_seconds = sum(meter.wall_clock_seconds for meter in meters)
    combined.peak_tracked_objects = max(meter.peak_tracked_objects for meter in meters)
    combined.max_repair_live_window_items = max(
        meter.max_repair_live_window_items for meter in meters
    )
    return combined


def _with_lifecycle_cost(
    result: ArmResult,
    *,
    initial_meter: CostMeter,
    repair_meter: CostMeter,
    ancestry_window_length: int,
) -> ArmResult:
    """Report common initial processing separately from marginal repair cost."""

    initial = initial_meter.as_dict()
    repair = repair_meter.as_dict()
    cost = dict(result.cost)
    for name in _ADDITIVE_COST_FIELDS:
        initial_value = int(initial[name])
        marginal_value = int(repair[name])
        cost[f"initial_{name}"] = initial_value
        cost[f"marginal_{name}"] = marginal_value
        cost[name] = initial_value + marginal_value
    cost["rejuvenation_acceptance_rate"] = (
        float(cost["rejuvenation_accepts"]) / float(cost["rejuvenation_proposals"])
        if int(cost["rejuvenation_proposals"])
        else 0.0
    )
    cost["unique_state_target_evaluations"] = len(
        initial_meter._scored_keys | repair_meter._scored_keys
    )
    cost["initial_unique_state_target_evaluations"] = int(
        initial["unique_state_target_evaluations"]
    )
    cost["marginal_unique_state_target_evaluations"] = int(
        repair["unique_state_target_evaluations"]
    )
    cost["particle_count"] = max(int(initial["particle_count"]), int(repair["particle_count"]))
    cost["peak_tracked_objects"] = max(
        int(initial["peak_tracked_objects"]), int(repair["peak_tracked_objects"])
    )
    cost["max_repair_live_window_items"] = max(
        int(initial["max_repair_live_window_items"]),
        int(repair["max_repair_live_window_items"]),
    )
    cost["initial_max_repair_live_window_items"] = int(initial["max_repair_live_window_items"])
    cost["marginal_max_repair_live_window_items"] = int(repair["max_repair_live_window_items"])
    cost["initial_wall_clock_seconds"] = float(initial["wall_clock_seconds"])
    cost["marginal_wall_clock_seconds"] = float(repair["wall_clock_seconds"])
    cost["wall_clock_seconds"] = round(
        float(initial["wall_clock_seconds"]) + float(repair["wall_clock_seconds"]), 6
    )
    cost["ancestry_window_length"] = ancestry_window_length
    cost["cost_scope"] = "full late-correction lifecycle"
    cost["marginal_cost_scope"] = "work triggered after correction arrival"
    return ArmResult(
        arm=result.arm,
        posterior=result.posterior,
        support=result.support,
        support_chains=result.support_chains,
        effective_sample_size=result.effective_sample_size,
        log_evidence=result.log_evidence,
        cost=cost,
        embodied_action_posterior_cache=result.embodied_action_posterior_cache,
    )


def run_late_correction(
    scenario: BackboneScenario,
    *,
    treatment: CorrectionTreatment,
    correction_index: int,
    arm: ArmName,
    budget: int,
    seed: int,
    rejuvenation_window_length: int = 1,
    rejuvenation_sweeps: int = 1,
) -> ArmResult:
    """Protocol task 7.

    ``append_only`` is the falsifiable form of the reversible-consolidation
    claim: a ledger that may only append cannot retract the contribution the
    corrupted reading already made, so it should fail to recover where the other
    three succeed.  Restricted to the Rao-Blackwellized arms, because the
    reweighting identity below integrates the analytic block rather than a
    sampled one.
    """

    if arm is ArmName.SAMPLED_THETA_PF:
        raise ValueError("the late-correction study is defined for the RB arms")
    if not 0 <= correction_index < len(scenario.observations):
        raise ValueError("correction index lies outside the observed stream")
    if rejuvenation_window_length <= 0:
        raise ValueError("rejuvenation window length must be positive")
    if rejuvenation_sweeps <= 0:
        raise ValueError("rejuvenation sweeps must be positive")
    corrected = repair_observation(scenario, correction_index)
    original_stream = scenario.observations
    corrected_stream = corrected.observations

    # A late correction arrives only after the original stream has run.  This
    # common initial cost is retained for lifecycle accounting and separated
    # from the marginal repair cost below.
    particles, evidence, rng, initial_meter = _run_stream(
        scenario, original_stream, arm=arm, budget=budget, seed=seed
    )
    source_unresolved_log_weight = unresolved_log_target(original_stream)
    corrected_unresolved_log_weight = (
        source_unresolved_log_weight
        - _unresolved_observation_log_term(original_stream[correction_index])
        + _unresolved_observation_log_term(corrected_stream[correction_index])
    )
    for particle in particles:
        checkpoint = _seal_window_checkpoint(particle, original_stream)
        # Checkpoint construction and integrity validation belong to the common
        # forward phase, before the late correction arrives.
        _verify_window_checkpoint(particle, original_stream)
        initial_meter.checkpoint_bytes += checkpoint.serialized_bytes
    initial_meter.ancestry_window_length = len(original_stream)
    initial_meter.stop()

    if treatment is CorrectionTreatment.FULL_RERUN:
        repaired_particles, repaired_evidence, _rng, repair_meter = _run_stream(
            scenario, corrected_stream, arm=arm, budget=budget, seed=seed
        )
        repaired = _finalize(repaired_particles, repaired_evidence, corrected_stream, repair_meter)
        return _with_lifecycle_cost(
            repaired,
            initial_meter=initial_meter,
            repair_meter=repair_meter,
            ancestry_window_length=len(corrected_stream),
        )

    if treatment is CorrectionTreatment.LOCAL_REJUVENATION:
        window_start = correction_index
        window_stop = min(len(corrected_stream), window_start + rejuvenation_window_length)
        repair_meter = CostMeter(arm=arm, particle_count=budget)
        repair_meter.start()
        corrected_log_weights: list[float] = []
        for particle in particles:
            ratio = _apply_fixed_observation_correction(
                particle,
                original_stream[correction_index],
                corrected_stream[correction_index],
                correction_index,
                repair_meter,
            )
            corrected_log_weights.append(particle.log_weight + ratio)
        repair_meter.fixed_gap_reweight_evaluations += budget
        corrected_evidence = evidence + _logsumexp(corrected_log_weights) - math.log(len(particles))
        masses = _normalized_masses(corrected_log_weights)
        particles = _systematic_resample(particles, masses, rng, share_history=True)
        repair_meter.resample()
        config = ArmConfiguration.of(arm)
        receipt = _window_rejuvenate(
            particles,
            corrected_stream,
            window_start=window_start,
            window_stop=window_stop,
            sweeps=rejuvenation_sweeps,
            config=config,
            rng=rng,
            meter=repair_meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
            source_observations=original_stream,
            checkpoints_preverified=True,
        )
        if receipt.fallback_required:
            repair_meter.replay_fallbacks += 1
            repair_meter.stop()
            fallback_particles, fallback_evidence, _rng, fallback_meter = _run_stream(
                scenario, corrected_stream, arm=arm, budget=budget, seed=seed
            )
            fallback = _finalize(
                fallback_particles, fallback_evidence, corrected_stream, fallback_meter
            )
            combined_meter = _combine_cost_meters(repair_meter, fallback_meter)
            repaired = _with_lifecycle_cost(
                fallback,
                initial_meter=initial_meter,
                repair_meter=combined_meter,
                ancestry_window_length=len(corrected_stream),
            )
            repaired.cost.update(
                {
                    "repair_mode": "replay_fallback",
                    "fallback_required": True,
                    "fallback_reasons": ",".join(receipt.fallback_reasons),
                    "proposal_window_length": window_stop - window_start,
                    "full_suffix_replayed_by_local_kernel": False,
                }
            )
            return repaired
        repair_meter.track_live(len(particles))
        local = _finalize(
            particles,
            corrected_evidence,
            corrected_stream,
            repair_meter,
            unresolved_log_weight=corrected_unresolved_log_weight,
        )
        repaired = _with_lifecycle_cost(
            local,
            initial_meter=initial_meter,
            repair_meter=repair_meter,
            ancestry_window_length=window_stop - window_start,
        )
        repaired.cost.update(
            {
                "repair_mode": "window_local",
                "fallback_required": False,
                "fallback_reasons": "",
                "proposal_window_length": window_stop - window_start,
                "max_history_transitions_read_per_local_proposal": (window_stop - window_start),
                "full_suffix_replayed_by_local_kernel": False,
                "checkpoint_format_id": TASK7_CHECKPOINT_FORMAT_ID,
                "checkpoint_claim_boundary": (
                    "runtime source binding only; external evidence authenticity is separate"
                ),
            }
        )
        return repaired

    repair_meter = CostMeter(arm=arm, particle_count=budget)
    repair_meter.start()
    for particle in particles:
        chain = particle.chain()
        gap = chain.gaps[correction_index]
        if treatment is CorrectionTreatment.REWEIGHT_ONLY:
            # Chains are frozen; only the target changes, so the exact weight
            # correction is the difference of the discrete and analytic terms.
            particle.log_weight += _correction_log_ratio(
                chain,
                original_stream,
                corrected_stream,
                correction_index,
                repair_meter,
            )
        else:
            # Append-only: the correction is recorded as one more piece of
            # evidence, and the corrupted reading's contribution stays.
            particle.log_weight += gap_log_likelihood(
                gap, corrected_stream[correction_index], repair_meter
            )
            cell = chain.cell_of(correction_index)
            block = particle.blocks.get(cell, AnalyticBlock()).clone()
            before = block.log_marginal()
            corrected_observation = corrected_stream[correction_index]
            block.update(
                gap_features(gap),
                corrected_observation.placement_value,
                corrected_observation.placement_bin,
            )
            repair_meter.analytic()
            particle.log_weight += block.log_marginal() - before
            particle.blocks = _persistent_blocks_with_changes(particle.blocks, {cell: block})
    result = _finalize(
        particles,
        evidence,
        corrected_stream,
        repair_meter,
        unresolved_log_weight=corrected_unresolved_log_weight,
    )
    return _with_lifecycle_cost(
        result,
        initial_meter=initial_meter,
        repair_meter=repair_meter,
        ancestry_window_length=0,
    )


def actor_marginal(result: ArmResult, index: int) -> dict[str, float]:
    """Posterior over who placed the object at gap ``index``, plus unresolved.

    Comparing two runs by the total variation of their FULL-CHAIN posteriors is
    degenerate once the chain space is large: two runs of the same correct
    algorithm on different seeds share no chains at all and score TV ~ 1.  A
    low-dimensional marginal is comparable; the chain posterior is not.
    """

    marginal: dict[str, float] = {actor.value: 0.0 for actor in ACTORS}
    marginal[UNRESOLVED_KEY] = 0.0
    for key, probability in result.posterior.items():
        if key == UNRESOLVED_KEY:
            marginal[UNRESOLVED_KEY] += probability
            continue
        chain = result.support_chains.get(key)
        if chain is not None and index < len(chain.gaps):
            marginal[chain.gaps[index].receiver.value] += probability
    return marginal


def marginal_distance(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def owner_contamination(result: ArmResult, truth: ChainHypothesis, correction_index: int) -> float:
    """Posterior mass still attributing the corrected gap to the wrong actor."""

    expected = truth.gaps[correction_index].receiver
    contaminated = 0.0
    resolved = 0.0
    for key, probability in result.posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        chain = result.support_chains.get(key)
        if chain is None:
            continue
        resolved += probability
        if chain.gaps[correction_index].receiver is not expected:
            contaminated += probability
    # Conditioned on the resolved mass.  Raw contamination is bounded by
    # 1 - P(unresolved), so a treatment that dumps its mass into `unresolved`
    # scored the LOWEST contamination — the metric's sign inverted for exactly
    # the treatment it was built to convict.
    return contaminated / resolved if resolved > 0.0 else 0.0


TASK7_BELIEF_AXES: Final = (
    "mechanism",
    "giver",
    "receiver",
    "instance",
    "cause",
    "regime_move",
    "regime_target",
    "regime_state",
    "run_length",
)


def task7_belief_marginals(result: ArmResult, index: int) -> dict[str, dict[str, float]]:
    """Frozen multi-axis marginals at the corrected episode."""

    marginals: dict[str, dict[str, float]] = {axis: {} for axis in TASK7_BELIEF_AXES}
    for key, probability in result.posterior.items():
        if key == UNRESOLVED_KEY:
            for marginal in marginals.values():
                marginal[UNRESOLVED_KEY] = marginal.get(UNRESOLVED_KEY, 0.0) + probability
            continue
        chain = result.support_chains.get(key)
        if chain is None or index >= len(chain.gaps):
            continue
        gap = chain.gaps[index]
        values = {
            "mechanism": gap.mechanism.value,
            "giver": gap.giver.value,
            "receiver": gap.receiver.value,
            "instance": gap.instance.value,
            "cause": gap.cause.value,
            "regime_move": gap.regime_move.value,
            "regime_target": gap.regime_target or "-",
            "regime_state": chain.regime_timeline[index] or "unresolved_regime",
            "run_length": str(chain.run_lengths[index]),
        }
        for axis, value in values.items():
            marginal = marginals[axis]
            marginal[value] = marginal.get(value, 0.0) + probability
    return marginals


def _task7_bayes_action_key(actions: Mapping[str, float]) -> str | None:
    if not actions:
        return None
    candidates = sorted(actions)
    return min(candidates, key=lambda key: (_expected_cost(_action_of(key), actions), key))


def _window_truth_recovered(
    result: ArmResult, truth: ChainHypothesis, window_start: int, window_stop: int
) -> bool:
    """Window-local recovery criterion that never traverses an untouched suffix."""

    return any(
        all(chain.gaps[index] == truth.gaps[index] for index in range(window_start, window_stop))
        for chain in result.support_chains.values()
    )


def _task7_probe_gap(actor: Actor) -> GapHypothesis:
    return GapHypothesis(
        mechanism=Mechanism.DIRECT,
        giver=actor,
        receiver=actor,
        instance=Instance.TARGET,
        cause=Cause.OBSERVATION,
        regime_move=RegimeMove.STAY,
        regime_target="R0",
    )


def _task7_probe_observation(gap: GapHypothesis, index: int) -> GapObservation:
    return GapObservation(
        observed_mechanism=gap.mechanism,
        observed_giver=gap.giver,
        observed_receiver=gap.receiver,
        observed_instance=gap.instance,
        observed_cause=gap.cause,
        observed_regime_change=False,
        placement_bin=index % PLACEMENT_BINS,
        placement_value=0.25 + 0.01 * (index % PLACEMENT_BINS),
        mechanism_reliability=0.88,
        actor_reliability=0.88,
        instance_reliability=0.88,
        cause_reliability=0.74,
        regime_reliability=0.88,
    )


def _task7_reachable_overlay_bytes(particle: Particle) -> int:
    """Direct size of post-correction objects, excluding retained base history."""

    total = sys.getsizeof(particle.persistent_chain_key) + sys.getsizeof(particle.repair_lineage)
    for sequence in (
        particle.gaps,
        particle.timeline,
        particle.runs,
        particle.boundary_states,
    ):
        if isinstance(sequence, PersistentWindowSequence):
            total += sys.getsizeof(sequence) + sys.getsizeof(sequence.replacement)
    if isinstance(particle.blocks, PersistentBlockMap):
        total += (
            sys.getsizeof(particle.blocks)
            + sys.getsizeof(particle.blocks.overrides)
            + sys.getsizeof(particle.blocks.removed)
        )
        for block in particle.blocks.overrides.values():
            total += (
                sys.getsizeof(block)
                + sys.getsizeof(block.alpha)
                + sys.getsizeof(block.a_matrix)
                + sum(sys.getsizeof(row) for row in block.a_matrix)
                + sys.getsizeof(block.b_vector)
            )
    return total


def run_task7_window_complexity_probe(
    *, window_length: int, sweeps: int, suffix_lengths: Sequence[int]
) -> dict[str, Any]:
    """Measure correction-only state/work while varying an untouched suffix.

    Checkpoint construction and the base history are prepared before the meter
    starts.  The suffix uses a different analytic cell, so every probe presents
    exactly the same window state, proposal stream, and window sufficient
    statistics; only the retained-by-reference suffix length changes.
    """

    if window_length <= 1:
        raise ValueError("Task-7 registered complexity probe requires W > 1")
    lengths = tuple(int(value) for value in suffix_lengths)
    if not lengths or any(value < 0 for value in lengths) or len(set(lengths)) != len(lengths):
        raise ValueError("Task-7 suffix probe lengths must be unique non-negative integers")
    rows: list[dict[str, Any]] = []
    window_start = 1
    window_stop = window_start + window_length
    for suffix_length in lengths:
        owner_gap = _task7_probe_gap(Actor.OWNER)
        suffix_gap = _task7_probe_gap(Actor.FAMILY)
        gaps = (
            *(owner_gap for _ in range(window_stop)),
            *(suffix_gap for _ in range(suffix_length)),
        )
        observations = tuple(_task7_probe_observation(gap, index) for index, gap in enumerate(gaps))
        timeline = tuple("R0" for _ in gaps)
        runs = tuple(index + 1 for index in range(len(gaps)))
        boundaries = (
            LatentBoundary(current="R0", retired=(), created=0, run_length=0),
            *(
                LatentBoundary(current="R0", retired=(), created=0, run_length=index + 1)
                for index in range(len(gaps))
            ),
        )
        chain = ChainHypothesis(gaps=gaps, regime_timeline=timeline, run_lengths=runs)
        blocks = analytic_blocks_for(chain, observations, CostMeter(arm=ArmName.EXACT_ORACLE))
        particle = Particle(
            gaps=gaps,
            timeline=timeline,
            runs=runs,
            current="R0",
            retired=(),
            created=0,
            log_weight=0.0,
            blocks=blocks,
            thetas={},
            ancestry=("probe-root",),
            boundary_states=boundaries,
            terminal_responsible_actor=gaps[-1].receiver,
        )
        checkpoint = _seal_window_checkpoint(particle, observations)
        _verify_window_checkpoint(particle, observations)
        meter = CostMeter(arm=ArmName.RBPF, particle_count=1)
        meter.start()
        receipt = _window_rejuvenate(
            [particle],
            observations,
            window_start=window_start,
            window_stop=window_stop,
            sweeps=sweeps,
            config=ArmConfiguration.of(ArmName.RBPF),
            rng=random.Random(f"{TASK7_PROTOCOL_ID}:complexity-probe"),
            meter=meter,
            source_observations=observations,
            checkpoints_preverified=True,
        )
        meter.stop()
        cost = meter.as_dict()
        rows.append(
            {
                "suffix_length": suffix_length,
                "base_checkpoint_bytes_prepared_before_correction": checkpoint.serialized_bytes,
                "fallback_required": receipt.fallback_required,
                "marginal_window_gap_target_evaluations": cost["window_gap_target_evaluations"],
                "marginal_persistent_sequence_nodes_created": cost[
                    "persistent_sequence_nodes_created"
                ],
                "marginal_persistent_window_items_written": cost["persistent_window_items_written"],
                "marginal_max_repair_live_window_items": cost["max_repair_live_window_items"],
                "reachable_persistent_overlay_bytes": _task7_reachable_overlay_bytes(particle),
                "marginal_untouched_suffix_items_read": cost["untouched_suffix_items_read"],
                "marginal_untouched_suffix_items_copied": cost["untouched_suffix_items_copied"],
                "marginal_untouched_suffix_items_rehashed": cost["untouched_suffix_items_rehashed"],
            }
        )
    work_values = {row["marginal_window_gap_target_evaluations"] for row in rows}
    live_values = {row["marginal_max_repair_live_window_items"] for row in rows}
    reachable_byte_values = {row["reachable_persistent_overlay_bytes"] for row in rows}
    zero_suffix_operations = all(
        row[name] == 0
        for row in rows
        for name in (
            "marginal_untouched_suffix_items_read",
            "marginal_untouched_suffix_items_copied",
            "marginal_untouched_suffix_items_rehashed",
        )
    )
    return {
        "probe_id": "task-7-persistent-window-complexity@0.1",
        "window_length": window_length,
        "sweeps": sweeps,
        "suffix_lengths": list(lengths),
        "checkpoint_preparation_excluded_from_marginal_repair_meter": True,
        "window_target_work_invariant_to_suffix_length": len(work_values) == 1,
        "persistent_live_items_invariant_to_suffix_length": len(live_values) == 1,
        "reachable_overlay_bytes_invariant_to_suffix_length": (len(reachable_byte_values) == 1),
        "zero_untouched_suffix_operations": zero_suffix_operations,
        "passed": (
            len(work_values) == 1
            and len(live_values) == 1
            and len(reachable_byte_values) == 1
            and zero_suffix_operations
            and all(not bool(row["fallback_required"]) for row in rows)
        ),
        "rows": rows,
    }


TASK7_SCENARIO_FACTOR_NAMES: Final = (
    "high_attribution_ambiguity",
    "adverse_delayed_feedback",
    "open_world_actor",
    "short_regime",
)


def complete_task7_scenario_factor_matrix(seed: int = 11) -> tuple[dict[str, bool | int], ...]:
    """Return every cell of the registered 2x2x2x2 Task-7 factor design."""

    return tuple(
        {
            "seed": seed,
            "high_attribution_ambiguity": ambiguity,
            "adverse_delayed_feedback": delayed,
            "open_world_actor": open_world,
            "short_regime": short_regime,
        }
        for ambiguity in (False, True)
        for delayed in (False, True)
        for open_world in (False, True)
        for short_regime in (False, True)
    )


def _task7_validation_gap(
    *,
    actor: Actor,
    cause: Cause,
    move: RegimeMove,
    target: str | None,
) -> GapHypothesis:
    return GapHypothesis(
        mechanism=Mechanism.HANDOFF if actor is Actor.GUEST else Mechanism.DIRECT,
        giver=Actor.OWNER if actor is Actor.GUEST else actor,
        receiver=actor,
        instance=Instance.TARGET,
        cause=cause,
        regime_move=move,
        regime_target=target,
    )


def validate_task7_conditional_target_contract() -> dict[str, Any]:
    """Compare the local objective with the full target on frozen small chains.

    This validation deliberately uses a separate exact-oracle meter and is not
    included in the production repair meter.  The second case changes internal
    regime states and analytic cells while rejoining the same right boundary,
    so a single-gap-only pseudo-target cannot pass by coincidence.
    """

    stay_owner = _task7_validation_gap(
        actor=Actor.OWNER,
        cause=Cause.OBSERVATION,
        move=RegimeMove.STAY,
        target="R0",
    )
    stay_guest = _task7_validation_gap(
        actor=Actor.GUEST,
        cause=Cause.ACTOR,
        move=RegimeMove.STAY,
        target="R0",
    )
    create_r1 = _task7_validation_gap(
        actor=Actor.OWNER,
        cause=Cause.HABIT,
        move=RegimeMove.CREATE,
        target="R1",
    )
    reactivate_r0 = _task7_validation_gap(
        actor=Actor.GUEST,
        cause=Cause.HABIT,
        move=RegimeMove.REACTIVATE,
        target="R0",
    )
    reactivate_r1 = _task7_validation_gap(
        actor=Actor.GUEST,
        cause=Cause.HABIT,
        move=RegimeMove.REACTIVATE,
        target="R1",
    )
    stay_r1 = _task7_validation_gap(
        actor=Actor.FAMILY,
        cause=Cause.OBSERVATION,
        move=RegimeMove.STAY,
        target="R1",
    )

    raw_cases = (
        (
            "one_gap_cell_change",
            (stay_owner, stay_owner, stay_owner),
            (stay_owner, stay_guest, stay_owner),
            1,
            2,
        ),
        (
            "internal_regime_and_cell_change",
            (
                stay_owner,
                create_r1,
                reactivate_r0,
                stay_owner,
                reactivate_r1,
                stay_r1,
            ),
            (
                stay_owner,
                stay_owner,
                create_r1,
                reactivate_r0,
                reactivate_r1,
                stay_r1,
            ),
            1,
            5,
        ),
    )
    rows: list[dict[str, Any]] = []
    for case_id, current_gaps, proposed_gaps, window_start, window_stop in raw_cases:
        current_state = _replay_gap_sequence(current_gaps)
        proposed_state = _replay_gap_sequence(proposed_gaps)
        if current_state is None or proposed_state is None:
            raise AssertionError("registered Task-7 conditional validation chain is invalid")
        current = current_state.chain
        proposed = proposed_state.chain
        root = LatentBoundary(current="R0", retired=(), created=0, run_length=0)
        current_replay = _replay_window_from_boundary(current.gaps, root)
        proposed_replay = _replay_window_from_boundary(proposed.gaps, root)
        if current_replay is None or proposed_replay is None:
            raise AssertionError("conditional validation boundary replay failed")
        current_boundaries = current_replay.boundaries
        proposed_boundaries = proposed_replay.boundaries
        if current_boundaries[window_start] != proposed_boundaries[window_start]:
            raise AssertionError("conditional validation left boundaries differ")
        if current_boundaries[window_stop] != proposed_boundaries[window_stop]:
            raise AssertionError("conditional validation right boundaries differ")
        observations = tuple(
            _task7_probe_observation(gap, index) for index, gap in enumerate(current_gaps)
        )
        blocks = analytic_blocks_for(current, observations, CostMeter(arm=ArmName.EXACT_ORACLE))
        local_meter = CostMeter(arm=ArmName.RBPF)
        local_delta, _analytic_delta, _changed = _window_conditional_target_delta(
            current,
            proposed,
            observations,
            blocks,
            window_start=window_start,
            window_stop=window_stop,
            meter=local_meter,
        )
        reference_meter = CostMeter(arm=ArmName.EXACT_ORACLE)
        reference_delta = chain_log_target(proposed, observations, reference_meter) - (
            chain_log_target(current, observations, reference_meter)
        )
        absolute_error = abs(local_delta - reference_delta)
        rows.append(
            {
                "case_id": case_id,
                "window_start": window_start,
                "window_stop": window_stop,
                "same_outside_chain": (
                    current.gaps[:window_start] == proposed.gaps[:window_start]
                    and current.gaps[window_stop:] == proposed.gaps[window_stop:]
                ),
                "same_left_boundary": True,
                "same_right_boundary": True,
                "later_window_regime_or_cell_changed": any(
                    current.regime_timeline[index] != proposed.regime_timeline[index]
                    or current.cell_of(index) != proposed.cell_of(index)
                    for index in range(window_start + 1, window_stop)
                ),
                "local_conditional_target_delta": local_delta,
                "full_target_delta": reference_delta,
                "absolute_error": absolute_error,
                "passed": absolute_error <= 1e-10,
            }
        )
    return {
        "validation_id": "task-7-same-conditional-target@0.1",
        "production_meter_contaminated_by_full_reference": False,
        "absolute_tolerance": 1e-10,
        "covers_one_gap_cell_change": True,
        "covers_later_window_regime_or_cell_change": any(
            row["later_window_regime_or_cell_changed"] for row in rows
        ),
        "passed": all(row["passed"] for row in rows),
        "rows": rows,
    }


def run_late_correction_study(
    *,
    gaps: int,
    correction_index: int,
    scenario_seeds: Sequence[int],
    arm: ArmName = ArmName.ADAPTIVE_TYPED_RBPF,
    budget: int = 384,
    replicate_seeds: Sequence[int] = (101, 202, 303),
    rejuvenation_window_length: int = 1,
    rejuvenation_sweeps: int = 1,
    complexity_probe_suffix_lengths: Sequence[int] = (8, 64, 256),
    scenario_factor_matrix: Sequence[Mapping[str, bool | int]] | None = None,
    protocol_id: str = TASK7_PROTOCOL_ID,
) -> dict[str, Any]:
    if protocol_id not in {TASK7_PROTOCOL_ID, TASK7_CONDITIONAL_PROTOCOL_ID}:
        raise ValueError("unknown Task-7 protocol ID")
    if protocol_id == TASK7_CONDITIONAL_PROTOCOL_ID and scenario_factor_matrix is None:
        raise ValueError("Task-7 v0.4 requires the exact registered 2x2x2x2 factor matrix")
    rows: list[dict[str, Any]] = []
    window_stop = min(gaps, correction_index + rejuvenation_window_length)
    if scenario_factor_matrix is None:
        factor_cells: tuple[dict[str, bool | int], ...] = tuple(
            {
                "seed": int(scenario_seed),
                "high_attribution_ambiguity": True,
                "adverse_delayed_feedback": True,
                "open_world_actor": scenario_seed % 2 == 1,
                "short_regime": True,
            }
            for scenario_seed in scenario_seeds
        )
        complete_factor_matrix = False
    else:
        factor_cells = tuple(
            {str(key): value for key, value in cell.items()} for cell in scenario_factor_matrix
        )
        expected_combinations = {
            (ambiguity, delayed, open_world, short_regime)
            for ambiguity in (False, True)
            for delayed in (False, True)
            for open_world in (False, True)
            for short_regime in (False, True)
        }
        actual_combinations: set[tuple[bool, bool, bool, bool]] = set()
        for cell in factor_cells:
            if set(cell) != {"seed", *TASK7_SCENARIO_FACTOR_NAMES}:
                raise ValueError("Task-7 factor cell has missing or unknown fields")
            if isinstance(cell["seed"], bool) or not isinstance(cell["seed"], int):
                raise ValueError("Task-7 factor-cell seed must be an integer")
            factor_values = tuple(cell[name] for name in TASK7_SCENARIO_FACTOR_NAMES)
            if not all(isinstance(value, bool) for value in factor_values):
                raise ValueError("Task-7 scenario factors must be booleans")
            actual_combinations.add(
                (
                    bool(factor_values[0]),
                    bool(factor_values[1]),
                    bool(factor_values[2]),
                    bool(factor_values[3]),
                )
            )
        if actual_combinations != expected_combinations or len(factor_cells) != 16:
            raise ValueError("Task-7 registered design must cover the exact 2x2x2x2 factor matrix")
        complete_factor_matrix = True

    for factor_cell in factor_cells:
        scenario = build_scenario(
            gaps=gaps,
            seed=int(factor_cell["seed"]),
            high_attribution_ambiguity=bool(factor_cell["high_attribution_ambiguity"]),
            adverse_delayed_feedback=bool(factor_cell["adverse_delayed_feedback"]),
            open_world_actor=bool(factor_cell["open_world_actor"]),
            short_regime=bool(factor_cell["short_regime"]),
            corrupt_index=correction_index,
        )
        for seed in replicate_seeds:
            reference = run_late_correction(
                scenario,
                treatment=CorrectionTreatment.FULL_RERUN,
                correction_index=correction_index,
                arm=arm,
                budget=budget,
                seed=seed,
            )
            corrected_scenario = repair_observation(scenario, correction_index)
            reference_belief = task7_belief_marginals(reference, correction_index)
            reference_actions = result_embodied_action_posterior(
                reference, corrected_scenario.observations
            )
            for treatment in CorrectionTreatment:
                result = (
                    reference
                    if treatment is CorrectionTreatment.FULL_RERUN
                    else run_late_correction(
                        scenario,
                        treatment=treatment,
                        correction_index=correction_index,
                        arm=arm,
                        budget=budget,
                        seed=seed,
                        rejuvenation_window_length=rejuvenation_window_length,
                        rejuvenation_sweeps=rejuvenation_sweeps,
                    )
                )
                treatment_belief = task7_belief_marginals(result, correction_index)
                belief_distances = {
                    axis: marginal_distance(reference_belief[axis], treatment_belief[axis])
                    for axis in TASK7_BELIEF_AXES
                }
                treatment_actions = result_embodied_action_posterior(
                    result, corrected_scenario.observations
                )
                selected_reference = _task7_bayes_action_key(reference_actions)
                selected_treatment = _task7_bayes_action_key(treatment_actions)
                rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "scenario_factors": {
                            name: bool(factor_cell[name]) for name in TASK7_SCENARIO_FACTOR_NAMES
                        },
                        "replicate_seed": seed,
                        "treatment": treatment.value,
                        "belief_axis_distances_to_full_rerun": belief_distances,
                        "max_belief_axis_distance_to_full_rerun": max(belief_distances.values()),
                        "actor_marginal_distance_to_full_rerun": belief_distances["receiver"],
                        "action_distribution_distance_to_full_rerun": (
                            action_posterior_distance(reference_actions, treatment_actions)
                        ),
                        "selected_action_full_rerun": selected_reference,
                        "selected_action_treatment": selected_treatment,
                        "selected_action_matches_full_rerun": (
                            selected_reference is not None
                            and selected_reference == selected_treatment
                        ),
                        "unresolved_mass": result.posterior.get(UNRESOLVED_KEY, 0.0),
                        "revision_recovery": _window_truth_recovered(
                            result, scenario.truth, correction_index, window_stop
                        ),
                        "revision_recovery_scope": "declared_window_only",
                        "owner_contamination": owner_contamination(
                            result, scenario.truth, correction_index
                        ),
                        "effective_sample_size": result.effective_sample_size,
                        "cost": result.cost,
                    }
                )
    summary: dict[str, dict[str, float]] = {}
    for treatment in CorrectionTreatment:
        subset = [row for row in rows if row["treatment"] == treatment.value]
        summary[treatment.value] = {
            "replicates": float(len(subset)),
            "mean_actor_marginal_distance_to_full_rerun": sum(
                row["actor_marginal_distance_to_full_rerun"] for row in subset
            )
            / len(subset),
            "mean_max_belief_axis_distance_to_full_rerun": sum(
                row["max_belief_axis_distance_to_full_rerun"] for row in subset
            )
            / len(subset),
            "max_belief_axis_distance_to_full_rerun": max(
                row["max_belief_axis_distance_to_full_rerun"] for row in subset
            ),
            "mean_action_distribution_distance_to_full_rerun": sum(
                row["action_distribution_distance_to_full_rerun"] for row in subset
            )
            / len(subset),
            "max_action_distribution_distance_to_full_rerun": max(
                row["action_distribution_distance_to_full_rerun"] for row in subset
            ),
            "selected_action_match_rate": sum(
                1.0 for row in subset if row["selected_action_matches_full_rerun"]
            )
            / len(subset),
            "mean_unresolved_mass": sum(row["unresolved_mass"] for row in subset) / len(subset),
            "revision_recovery_rate": sum(1.0 for row in subset if row["revision_recovery"])
            / len(subset),
            "mean_owner_contamination_given_resolved": sum(
                row["owner_contamination"] for row in subset
            )
            / len(subset),
            "mean_effective_sample_size": sum(row["effective_sample_size"] for row in subset)
            / len(subset),
            "mean_elementary_evaluations": sum(
                float(row["cost"]["elementary_likelihood_evaluations"]) for row in subset
            )
            / len(subset),
            "mean_marginal_elementary_evaluations": sum(
                float(row["cost"]["marginal_elementary_likelihood_evaluations"]) for row in subset
            )
            / len(subset),
            "mean_marginal_window_gap_target_evaluations": sum(
                float(row["cost"]["marginal_window_gap_target_evaluations"]) for row in subset
            )
            / len(subset),
            "fallback_rate": sum(
                1.0 for row in subset if bool(row["cost"].get("fallback_required", False))
            )
            / len(subset),
            "mean_wall_clock_seconds": sum(
                float(row["cost"]["wall_clock_seconds"]) for row in subset
            )
            / len(subset),
        }
    local_rows = [row for row in rows if row["treatment"] == CorrectionTreatment.LOCAL_REJUVENATION]
    full_rows = [row for row in rows if row["treatment"] == CorrectionTreatment.FULL_RERUN]
    full_cost_by_unit = {
        (row["scenario_id"], row["replicate_seed"]): int(
            row["cost"]["marginal_elementary_likelihood_evaluations"]
        )
        for row in full_rows
    }
    belief_equivalence_passed = all(
        all(
            float(distance) <= TASK7_BELIEF_AXIS_TV_TOLERANCE
            for distance in row["belief_axis_distances_to_full_rerun"].values()
        )
        for row in local_rows
    )
    action_equivalence_passed = all(
        float(row["action_distribution_distance_to_full_rerun"])
        <= TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        and bool(row["selected_action_matches_full_rerun"])
        for row in local_rows
    )
    equivalence_passed = belief_equivalence_passed and action_equivalence_passed
    local_cost_passed = all(
        row["cost"].get("repair_mode") == "window_local"
        and row["cost"].get("full_suffix_replayed_by_local_kernel") is False
        and int(row["cost"]["marginal_elementary_likelihood_evaluations"])
        < full_cost_by_unit[(row["scenario_id"], row["replicate_seed"])]
        for row in local_rows
    )
    no_fallbacks = all(row["cost"].get("fallback_required") is False for row in local_rows)
    conditional_target_runtime_passed = all(
        int(row["cost"].get("marginal_conditional_target_checks", 0)) > 0
        and int(row["cost"].get("marginal_conditional_target_mismatches", 0)) == 0
        for row in local_rows
    )
    nonself_move_passed = all(
        int(row["cost"]["marginal_rejuvenation_proposals"]) > 0
        and int(row["cost"]["marginal_nonself_rejuvenation_proposals"])
        == int(row["cost"]["marginal_rejuvenation_proposals"])
        for row in local_rows
    )
    local_suffix_operations_zero = all(
        int(row["cost"][name]) == 0
        for row in local_rows
        for name in (
            "marginal_untouched_suffix_items_read",
            "marginal_untouched_suffix_items_copied",
            "marginal_untouched_suffix_items_rehashed",
        )
    )
    complexity_probe = run_task7_window_complexity_probe(
        window_length=rejuvenation_window_length,
        sweeps=rejuvenation_sweeps,
        suffix_lengths=complexity_probe_suffix_lengths,
    )
    strict_window_complexity_passed = bool(complexity_probe["passed"]) and (
        local_suffix_operations_zero
    )
    conditional_target_validation = validate_task7_conditional_target_contract()
    window_implementation_passed = (
        belief_equivalence_passed
        and action_equivalence_passed
        and local_cost_passed
        and no_fallbacks
        and nonself_move_passed
        and rejuvenation_window_length > 1
        and strict_window_complexity_passed
        and conditional_target_runtime_passed
        and bool(conditional_target_validation["passed"])
        and (complete_factor_matrix or protocol_id == TASK7_PROTOCOL_ID)
    )
    local_contamination = summary[CorrectionTreatment.LOCAL_REJUVENATION.value][
        "mean_owner_contamination_given_resolved"
    ]
    full_contamination = summary[CorrectionTreatment.FULL_RERUN.value][
        "mean_owner_contamination_given_resolved"
    ]
    contamination_not_expanded = local_contamination <= full_contamination
    local_recovery = summary[CorrectionTreatment.LOCAL_REJUVENATION.value]["revision_recovery_rate"]
    full_recovery = summary[CorrectionTreatment.FULL_RERUN.value]["revision_recovery_rate"]
    task_7_passed = window_implementation_passed and contamination_not_expanded
    return {
        "protocol_id": protocol_id,
        "backbone_protocol_id": PROTOCOL_ID,
        "task": "task-7-late-correction",
        "evidence_status": "D0 synthetic window-kernel validation; no external benefit is claimed",
        "gaps": gaps,
        "correction_index": correction_index,
        "arm": arm.value,
        "budget": budget,
        "scenario_seeds": list(scenario_seeds),
        "scenario_factor_matrix": [dict(cell) for cell in factor_cells],
        "scenario_factor_names": list(TASK7_SCENARIO_FACTOR_NAMES),
        "complete_2x2x2x2_scenario_factor_matrix": complete_factor_matrix,
        "replicate_seeds": list(replicate_seeds),
        "window_contract": {
            "checkpoint_format_id": TASK7_CHECKPOINT_FORMAT_ID,
            "proposal_window_length": rejuvenation_window_length,
            "rejuvenation_sweeps": rejuvenation_sweeps,
            "full_suffix_replayed_by_local_kernel": False,
            "persistent_window_overlays": True,
            "proposal_is_conditioned_on_non_self_move": True,
            "untouched_suffix_copy_scan_or_rehash": False,
            "affected_cell_delta_updates": True,
            "explicit_replay_fallback": True,
            "belief_axes": list(TASK7_BELIEF_AXES),
            "belief_axis_tv_tolerance": TASK7_BELIEF_AXIS_TV_TOLERANCE,
            "action_distribution_tv_tolerance": (TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE),
            "selected_bayes_action_must_match": True,
            "conditional_target_id": "task-7-same-conditional-target@0.1",
            "terminal_responsible_actor_cached": True,
            "fallback_policy": "explicit_full_replay",
        },
        "belief_equivalence_passed": belief_equivalence_passed,
        "action_equivalence_passed": action_equivalence_passed,
        "equivalence_passed": equivalence_passed,
        "local_cost_passed": local_cost_passed,
        "no_fallbacks_in_registered_run": no_fallbacks,
        "conditional_target_runtime_passed": conditional_target_runtime_passed,
        "conditional_target_validation": conditional_target_validation,
        "explicit_full_replay_fallback_implemented": True,
        "nonself_move_passed": nonself_move_passed,
        "strict_window_complexity_passed": strict_window_complexity_passed,
        "complexity_probe": complexity_probe,
        "window_implementation_passed": window_implementation_passed,
        "task_7_instrument_passed": window_implementation_passed,
        "contamination_not_expanded": contamination_not_expanded,
        "local_minus_full_owner_contamination": local_contamination - full_contamination,
        "local_minus_full_revision_recovery_rate": local_recovery - full_recovery,
        "task_7_passed": task_7_passed,
        "task_7_verdict": "PASS" if task_7_passed else "FAIL",
        "task_7_failure_reason": (
            None
            if task_7_passed
            else (
                "CONTAMINATION_NONINFERIORITY_FAILED"
                if window_implementation_passed
                else "WINDOW_IMPLEMENTATION_FAILED"
            )
        ),
        "seven_operator_efficacy_authorized": False,
        "claim_boundary": (
            "A Task-7 pass validates the window/checkpoint/reweighting instrument on the "
            "registered synthetic design only. It neither selects the Task-12 kernel nor "
            "authorizes a seven-operator efficacy claim."
        ),
        "summary": summary,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Belief-to-utility interface v0.3
# ---------------------------------------------------------------------------
#
# The previous readout could not separate any two arms: it scored the ARGMAX of a
# three-outcome location marginal, so every arm that found any reasonable mass
# landed on the same bin and scored regret 0.  Widening the bins alone does not
# fix that — with nine bins and a non-degenerate exact marginal all four arms
# still scored 0.  What was actually degenerate was the scoring rule, so this
# interface changes three things at once:
#
#   1. the action is joint (where to put it, AND who is held responsible),
#   2. the loss is graded — placement bins are ORDERED, and mis-attributing a
#      visitor's action to the owner costs more than the reverse, because that
#      is the error that contaminates a long-term habit,
#   3. the arm is scored on its own BAYES action under its full posterior, not
#      on its mode, and a continuous companion metric is reported beside it.


@dataclass(frozen=True, slots=True)
class EmbodiedAction:
    """Where the robot would put the object, and who it holds responsible."""

    location_bin: int
    responsible_actor: Actor

    @property
    def key(self) -> str:
        return f"{self.location_bin}|{self.responsible_actor.value}"


def action_cost(predicted: EmbodiedAction, actual: EmbodiedAction) -> float:
    """Graded loss over the joint action.

    Location is ordered, so the loss is a distance, not 0/1.  Actor errors are
    asymmetric: crediting the owner for someone else's placement writes a
    foreign habit into the owner's memory, which is the failure the whole
    reversible-consolidation machinery exists to prevent.
    """

    span = float(PLACEMENT_BINS - 1)
    location = abs(predicted.location_bin - actual.location_bin) / span
    if predicted.responsible_actor is actual.responsible_actor:
        actor = 0.0
    elif predicted.responsible_actor is Actor.OWNER:
        actor = 1.0
    elif actual.responsible_actor is Actor.OWNER:
        actor = 0.6
    else:
        actor = 0.3
    return LOCATION_COST_WEIGHT * location + ACTOR_COST_WEIGHT * actor


def chain_embodied_action(
    chain: ChainHypothesis, observations: Sequence[GapObservation]
) -> EmbodiedAction:
    """Read the action out of the cell this chain actually attributes it to.

    The old readout always queried the OWNER cell, which is empty for 64% of
    admissible chains — those all fell back to a prior block and returned the
    same constant bin regardless of what the chain said.
    """

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    blocks = analytic_blocks_for(chain, observations, meter)
    actor = chain.gaps[-1].receiver
    cell = (actor.value, chain.final_regime or "unresolved_regime")
    block = blocks.get(cell)
    if block is None:
        block = AnalyticBlock()
    scores = block.action_log_scores(ACTION_QUERY_FEATURES)
    best = max(range(PLACEMENT_BINS), key=lambda index: scores[index])
    return EmbodiedAction(location_bin=best, responsible_actor=actor)


def _particle_embodied_action(particle: Particle) -> EmbodiedAction:
    """Terminal action from live sufficient state, with no history traversal."""

    if not particle.gaps:
        return EmbodiedAction(location_bin=0, responsible_actor=Actor.UNKNOWN)
    actor = particle.terminal_responsible_actor
    if actor is None:
        raise CheckpointIntegrityError(
            "terminal responsible actor is absent from the Task-7 sufficient-state cache"
        )
    cell = (actor.value, particle.current or "unresolved_regime")
    block = particle.blocks.get(cell, AnalyticBlock())
    scores = block.action_log_scores(ACTION_QUERY_FEATURES)
    best = max(range(PLACEMENT_BINS), key=lambda index: scores[index])
    return EmbodiedAction(location_bin=best, responsible_actor=actor)


def embodied_action_posterior(
    posterior: Mapping[str, float],
    chains: Mapping[str, ChainHypothesis],
    observations: Sequence[GapObservation],
) -> dict[str, float]:
    """Posterior over joint actions, unresolved mass excluded and renormalized."""

    marginal: dict[str, float] = {}
    total = 0.0
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        chain = chains.get(key)
        if chain is None:
            continue
        action = chain_embodied_action(chain, observations)
        marginal[action.key] = marginal.get(action.key, 0.0) + probability
        total += probability
    if total <= 0.0:
        return {}
    return {key: value / total for key, value in marginal.items()}


def result_embodied_action_posterior(
    result: ArmResult, observations: Sequence[GapObservation]
) -> dict[str, float]:
    """Return the cached O(1)-per-particle Task-7 action readout when available."""

    if result.embodied_action_posterior_cache is not None:
        total = sum(result.embodied_action_posterior_cache.values())
        if total <= 0.0:
            return {}
        return {key: value / total for key, value in result.embodied_action_posterior_cache.items()}
    return embodied_action_posterior(result.posterior, result.support_chains, observations)


def _action_of(key: str) -> EmbodiedAction:
    location, actor = key.split("|", 1)
    return EmbodiedAction(location_bin=int(location), responsible_actor=Actor(actor))


def _expected_cost(candidate: EmbodiedAction, reference: Mapping[str, float]) -> float:
    return sum(
        probability * action_cost(candidate, _action_of(key))
        for key, probability in reference.items()
    )


def decision_regret(
    exact_actions: Mapping[str, float], arm_actions: Mapping[str, float]
) -> float | None:
    """Expected-cost gap of the arm's Bayes action under the exact posterior.

    The arm chooses by minimizing expected cost under ITS OWN posterior, so the
    choice depends on the whole distribution rather than on its mode.  Returns
    ``None`` when the arm has no action to offer.
    """

    if not exact_actions or not arm_actions:
        return None
    candidates = sorted(set(exact_actions) | set(arm_actions))
    chosen = min(candidates, key=lambda key: (_expected_cost(_action_of(key), arm_actions), key))
    best = min(_expected_cost(_action_of(key), exact_actions) for key in candidates)
    return _expected_cost(_action_of(chosen), exact_actions) - best


def action_posterior_distance(
    exact_actions: Mapping[str, float], arm_actions: Mapping[str, float]
) -> float:
    """Continuous companion to ``decision_regret``.

    A decision rule can agree while the beliefs behind it differ a lot; this
    keeps the instrument able to say so even when every arm picks the same
    action.
    """

    keys = set(exact_actions) | set(arm_actions)
    return 0.5 * sum(abs(exact_actions.get(k, 0.0) - arm_actions.get(k, 0.0)) for k in keys)


# ---------------------------------------------------------------------------
# Belief-to-utility interface v0.3, part two: the consolidation decision
# ---------------------------------------------------------------------------
#
# The placement decision turned out to be insensitive: every arm picked the same
# Bayes action as the oracle in every scenario checked, so its regret was zero by
# construction rather than by metric failure.  That is a fact about the decision,
# not about the arms — a graded loss over an ordered location makes the Bayes
# action robust to exactly the posterior differences we are trying to measure.
#
# The decision that IS sensitive is the one Structure Two actually cares about:
# whether to write this evidence into the owner's long-term habit memory.  It is
# a threshold on the tail of the actor posterior, so it reads the calibration of
# the belief rather than its mode, and mis-promoting is far more expensive than
# over-quarantining — which is the asymmetry the whole reversible-consolidation
# machinery exists to serve.

CONSOLIDATION_THRESHOLD: Final = 0.80
FALSE_PROMOTE_COST: Final = 1.0
FALSE_QUARANTINE_COST: Final = 0.15


def owner_responsibility_mass(
    posterior: Mapping[str, float],
    chains: Mapping[str, ChainHypothesis],
    index: int = 0,
) -> float:
    """Posterior probability that the owner is responsible for the placement.

    Unresolved mass counts against promotion: an unresolved belief is precisely
    the state in which the ledger must not write.
    """

    owner = 0.0
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        chain = chains.get(key)
        if chain is not None and chain.gaps[index].receiver is Actor.OWNER:
            owner += probability
    return owner


def consolidation_cost(
    posterior: Mapping[str, float],
    chains: Mapping[str, ChainHypothesis],
    truth: ChainHypothesis,
    *,
    threshold: float = CONSOLIDATION_THRESHOLD,
    index: int = 0,
) -> float:
    """Loss of the promote/quarantine decision this belief would drive.

    ``index`` defaults to the gap the scenario corrupts, not the last one.
    With ``index=-1`` the truth's actor is the owner for every G>=2 scenario, so
    the false-promote branch was unreachable and over-crediting the owner could
    only ever be rewarded — and the readout was pointed at the one gap the
    adverse-feedback factor never touches, making that factor invisible to it.
    """

    promote = owner_responsibility_mass(posterior, chains, index) >= threshold
    owner_did_it = truth.gaps[index].receiver is Actor.OWNER
    if promote and not owner_did_it:
        return FALSE_PROMOTE_COST
    if owner_did_it and not promote:
        return FALSE_QUARANTINE_COST
    return 0.0


CONSOLIDATION_THRESHOLD_SWEEP: Final = (0.50, 0.65, 0.80, 0.90, 0.95)


def owner_mass_calibration_error(
    exact_posterior_map: Mapping[str, float],
    exact_chains: Mapping[str, ChainHypothesis],
    arm: ArmResult,
    index: int = 0,
) -> float:
    """|P_arm(owner responsible) - P_exact(owner responsible)|.

    The promote/quarantine rule is a step function on this one number, so the
    realized decision cost throws away almost everything the posterior knows and
    can even reward a worse belief that happens to land on the right side of the
    threshold — the sampled-theta arm scored BELOW the exact oracle that way.
    This reports the quantity the decision actually rides on, continuously, so a
    step-function tie is never mistaken for equal belief quality.
    """

    reference = owner_responsibility_mass(exact_posterior_map, exact_chains, index)
    estimate = owner_responsibility_mass(arm.posterior, arm.support_chains, index)
    return abs(estimate - reference)


def consolidation_cost_curve(
    posterior: Mapping[str, float],
    chains: Mapping[str, ChainHypothesis],
    truth: ChainHypothesis,
    *,
    thresholds: Sequence[float] = CONSOLIDATION_THRESHOLD_SWEEP,
    index: int = 0,
) -> dict[str, float]:
    """Decision cost at several thresholds, so a single-threshold tie is visible."""

    return {
        f"{threshold:.2f}": consolidation_cost(
            posterior, chains, truth, threshold=threshold, index=index
        )
        for threshold in thresholds
    }


# ---------------------------------------------------------------------------
# Task 8: the H_t x C_t joint-inference death test
# ---------------------------------------------------------------------------
#
# The question is not whether the event chain and the change cause are
# correlated in the posterior — they are, because the same observation informs
# both.  The question the unified paper has to answer is whether keeping them
# coupled buys anything a matched two-stage pipeline cannot get.  So the
# comparison runs at the EXACT posterior first, where there is no approximation
# error to hide behind: the joint arm IS the exact posterior, and the other two
# are that same posterior with the coupling deliberately removed.  If the joint
# arm cannot win here, no particle implementation of it can be defended by
# appeal to inference quality.


class InferenceCoupling(StrEnum):
    JOINT = "joint"
    FACTORIZED = "factorized"
    TWO_STAGE = "two_stage"


class JointConsequenceAction(StrEnum):
    """Discrete action taken before the Task-8 evaluator reveals truth."""

    PROCEED = "proceed"
    VERIFY = "verify"


def _event_key(chain: ChainHypothesis, *, include_regime: bool = False) -> str:
    """H_t: the event chain with its role and instance bindings, cause excluded.

    ``include_regime`` folds the regime destination Z_t into H.  It matters:
    the model's ONLY structural coupling is the deterministic implication
    ``Z in {create, reactivate} => C = habit`` in ``_regime_successors``.  With
    Z excluded from both keys — the literal reading of "H_t x C_t" — that
    coupling is invisible, and the ablation measures 0.0005 nats and concludes
    the generator has no coupling.  It has one; the partition hid it.
    """

    parts = []
    for gap in chain.gaps:
        axes = f"{gap.mechanism.value}/{gap.giver.value}/{gap.receiver.value}/{gap.instance.value}"
        parts.append(f"{axes}/{gap.regime_move.value}" if include_regime else axes)
    return "|".join(parts)


def _cause_key(chain: ChainHypothesis) -> str:
    """C_t: the change-cause sequence."""

    return "|".join(gap.cause.value for gap in chain.gaps)


@dataclass(frozen=True, slots=True)
class _CouplingRow:
    """One admissible chain, reduced to what the coupling ablation needs."""

    key: str
    event: str
    cause: str
    action: str
    owner: bool
    mechanism_at_correction: str = ""
    regime_move_at_correction: str = ""
    cause_at_correction: str = ""


def _coupling_table(
    scenario: BackboneScenario,
    meter: CostMeter,
    state_budget: int,
    *,
    include_regime: bool = False,
) -> tuple[dict[str, float], list[_CouplingRow]]:
    """One enumeration pass, no ChainHypothesis retained.

    Holding the chain objects costs ~1 GB and two passes at G=2 (9e5 chains),
    which is the same materialization mistake the budget sweep had to be fixed
    for.  Everything the ablation needs is five small fields per chain.
    """

    log_targets: dict[str, float] = {}
    rows: list[_CouplingRow] = []
    visited = 0
    for chain in iter_chains(scenario.gaps):
        visited += 1
        if visited > state_budget:
            raise ExactEnumerationBudgetExceeded(scenario.gaps, state_budget, visited)
        if not chain_is_admissible(chain):
            continue
        log_targets[chain.key] = chain_log_target(
            chain,
            scenario.observations,
            meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        rows.append(
            _CouplingRow(
                key=chain.key,
                event=_event_key(chain, include_regime=include_regime),
                cause=_cause_key(chain),
                action=chain_embodied_action(chain, scenario.observations).key,
                owner=chain.gaps[scenario.corrupt_index].receiver is Actor.OWNER,
                mechanism_at_correction=chain.gaps[scenario.corrupt_index].mechanism.value,
                regime_move_at_correction=chain.gaps[scenario.corrupt_index].regime_move.value,
                cause_at_correction=chain.gaps[scenario.corrupt_index].cause.value,
            )
        )
    posterior = normalize_log_targets(log_targets, unresolved_log_target(scenario.observations))
    return posterior, rows


def _aggregate(
    belief: Mapping[str, float], rows: Sequence[_CouplingRow], field: str
) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        probability = belief.get(row.key, 0.0)
        if probability <= 0.0:
            continue
        name = getattr(row, field)
        out[name] = out.get(name, 0.0) + probability
    return out


def _mutual_information(belief: Mapping[str, float], rows: Sequence[_CouplingRow]) -> float:
    joint: dict[tuple[str, str], float] = {}
    events: dict[str, float] = {}
    causes: dict[str, float] = {}
    total = 0.0
    for row in rows:
        probability = belief.get(row.key, 0.0)
        if probability <= 0.0:
            continue
        joint[(row.event, row.cause)] = joint.get((row.event, row.cause), 0.0) + probability
        events[row.event] = events.get(row.event, 0.0) + probability
        causes[row.cause] = causes.get(row.cause, 0.0) + probability
        total += probability
    if total <= 0.0:
        return 0.0
    information = 0.0
    for (event, cause), mass in joint.items():
        p = mass / total
        product = (events[event] / total) * (causes[cause] / total)
        if p > 0.0 and product > 0.0:
            information += p * math.log(p / product)
    return information


def _joint_cross_severity(row: _CouplingRow) -> float:
    """Frozen severity of one resolved ``(H+Z,C)`` cross cell."""

    if (
        row.cause_at_correction == Cause.ACTOR.value
        and row.mechanism_at_correction == Mechanism.HANDOFF.value
        and row.regime_move_at_correction in {RegimeMove.STAY.value, RegimeMove.UNRESOLVED.value}
    ):
        return TASK8_HANDOFF_ACTOR_SEVERITY
    if row.cause_at_correction == Cause.HABIT.value and row.regime_move_at_correction in {
        RegimeMove.CREATE.value,
        RegimeMove.REACTIVATE.value,
    }:
        return TASK8_REGIME_HABIT_SEVERITY
    return 0.0


def consequential_action_policy(
    belief: Mapping[str, float], rows: Sequence[_CouplingRow]
) -> dict[str, float]:
    """A discrete policy driven directly by posterior cross-cell mass.

    The policy receives no truth label.  Its probability of the consequential
    ``verify`` action is the posterior expected frozen cross-cell severity,
    including the frozen unresolved severity.  Thus two beliefs with identical
    H+Z and C marginals but different dependence induce different actions.
    """

    verify_probability = TASK8_UNRESOLVED_SEVERITY * belief.get(UNRESOLVED_KEY, 0.0)
    verify_probability += sum(belief.get(row.key, 0.0) * _joint_cross_severity(row) for row in rows)
    verify_probability = min(1.0, max(0.0, verify_probability))
    return {
        JointConsequenceAction.PROCEED.value: 1.0 - verify_probability,
        JointConsequenceAction.VERIFY.value: verify_probability,
    }


def consequential_expected_cost(policy: Mapping[str, float], truth_severity: float) -> float:
    """Expected realized cost after the frozen discrete action distribution."""

    verify = policy.get(JointConsequenceAction.VERIFY.value, 0.0)
    proceed = policy.get(JointConsequenceAction.PROCEED.value, 0.0)
    return verify * TASK8_VERIFY_COST + proceed * truth_severity


def task8_endpoint_consumes_interaction() -> bool:
    """Constructive equal-marginal check for the registered endpoint."""

    rows = (
        _CouplingRow(
            key="ha",
            event="handoff/stay",
            cause="actor",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.HANDOFF.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.ACTOR.value,
        ),
        _CouplingRow(
            key="ho",
            event="handoff/stay",
            cause="observation",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.HANDOFF.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.OBSERVATION.value,
        ),
        _CouplingRow(
            key="da",
            event="direct/stay",
            cause="actor",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.DIRECT.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.ACTOR.value,
        ),
        _CouplingRow(
            key="do",
            event="direct/stay",
            cause="observation",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.DIRECT.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.OBSERVATION.value,
        ),
    )
    dependent = {"ha": 0.5, "do": 0.5, UNRESOLVED_KEY: 0.0}
    independent = {row.key: 0.25 for row in rows}
    independent[UNRESOLVED_KEY] = 0.0
    same_marginals = all(
        _aggregate(dependent, rows, field) == _aggregate(independent, rows, field)
        for field in ("event", "cause")
    )
    return same_marginals and consequential_action_policy(
        dependent, rows
    ) != consequential_action_policy(independent, rows)


def _decouple(
    belief: Mapping[str, float], rows: Sequence[_CouplingRow], coupling: InferenceCoupling
) -> dict[str, float]:
    if coupling is InferenceCoupling.JOINT:
        return dict(belief)
    unresolved = belief.get(UNRESOLVED_KEY, 0.0)
    resolved = 1.0 - unresolved
    if resolved <= 0.0:
        return dict(belief)
    events = _aggregate(belief, rows, "event")
    causes = _aggregate(belief, rows, "cause")
    live = [row for row in rows if belief.get(row.key, 0.0) > 0.0]
    if not live:
        return dict(belief)
    if coupling is InferenceCoupling.TWO_STAGE:
        decided = max(causes, key=lambda name: (causes[name], name))
        kept = [row.key for row in live if row.cause == decided]
        mass = sum(belief[key] for key in kept)
        if not kept or mass <= 0.0:
            return dict(belief)
        rebuilt = {key: resolved * belief[key] / mass for key in kept}
        rebuilt[UNRESOLVED_KEY] = unresolved
        return rebuilt
    # Iterative proportional fitting.  A plain outer product p(H)p(C) is only
    # correct when every (event, cause) cell is occupied.  Under the honest
    # partition the grid is RAGGED — `create`/`reactivate` exist only under a
    # habit cause — so the outer product puts mass on impossible combinations
    # and silently stops conserving the marginals it is defined to preserve.
    # The I-projection keeps both marginals AND stays on the support, which is
    # the right meaning of "the dependence is removed, nothing else changed".
    cell: dict[tuple[str, str], float] = {}
    for row in live:
        cell[(row.event, row.cause)] = cell.get((row.event, row.cause), 0.0) + belief[row.key]
    fitted = dict.fromkeys(cell, 1.0)
    for _ in range(FACTORIZATION_FITTING_ROUNDS):
        totals: dict[str, float] = {}
        for (event, _cause), value in fitted.items():
            totals[event] = totals.get(event, 0.0) + value
        for key in fitted:
            scale = totals[key[0]]
            fitted[key] = fitted[key] * events[key[0]] / scale if scale > 0.0 else 0.0
        totals = {}
        for (_event, cause), value in fitted.items():
            totals[cause] = totals.get(cause, 0.0) + value
        drift = 0.0
        for key in fitted:
            scale = totals[key[1]]
            fitted[key] = fitted[key] * causes[key[1]] / scale if scale > 0.0 else 0.0
        for name, target in causes.items():
            drift = max(drift, abs(totals.get(name, 0.0) - target))
        if drift < FACTORIZATION_TOLERANCE:
            break
    projected: dict[str, float] = {}
    weight = 0.0
    for row in live:
        pair = (row.event, row.cause)
        share = belief[row.key] / cell[pair] if cell[pair] > 0.0 else 0.0
        value = fitted[pair] * share
        projected[row.key] = value
        weight += value
    if weight <= 0.0:
        return dict(belief)
    normalized = {key: resolved * value / weight for key, value in projected.items()}
    normalized[UNRESOLVED_KEY] = unresolved
    return normalized


def run_joint_coupling_death_test(
    *,
    gaps: int,
    scenario_seeds: Sequence[int],
    scenarios: Sequence[BackboneScenario] | None = None,
    include_regime_in_event: bool = True,
    state_budget: int = 2_000_000,
    relative_probability_coupling_nats: float | None = None,
) -> dict[str, Any]:
    """Protocol task 8, run at the exact posterior.

    ``scenarios`` overrides the registered design, for the G>=2 case where each
    cell costs one exact enumeration of 9e5 chains.
    """

    rows: list[dict[str, Any]] = []
    design: Sequence[BackboneScenario]
    if scenarios is None:
        strength = (
            RELATIVE_PROBABILITY_SOFT_COUPLING_NATS
            if relative_probability_coupling_nats is None
            else relative_probability_coupling_nats
        )
        design = registered_scenarios(
            gaps,
            scenario_seeds,
            relative_probability_coupling_nats=strength,
            relative_probability_truth_model=True,
        )
    else:
        design = scenarios
        if not design:
            raise ValueError("Task 8 requires at least one scenario")
        if any(not scenario.relative_probability_truth_model for scenario in design):
            raise ValueError("Task 8 scenarios must use the relative-probability truth model")
        strengths = {scenario.relative_probability_coupling_nats for scenario in design}
        if len(strengths) != 1:
            raise ValueError("Task 8 scenarios must use one common coupling strength")
        strength = next(iter(strengths))
        if (
            relative_probability_coupling_nats is not None
            and relative_probability_coupling_nats != strength
        ):
            raise ValueError("declared Task 8 coupling differs from the supplied scenarios")
    if strength < 0.0:
        raise ValueError("Task 8 coupling strength cannot be negative")
    for scenario in design:
        meter = CostMeter(arm=ArmName.EXACT_ORACLE)
        exact, table = _coupling_table(
            scenario, meter, state_budget, include_regime=include_regime_in_event
        )
        information = _mutual_information(exact, table)
        reference_actions = _aggregate(exact, table, "action")
        reference_total = sum(reference_actions.values())
        if reference_total > 0.0:
            reference_actions = {
                key: value / reference_total for key, value in reference_actions.items()
            }
        reference_owner = sum(exact.get(row.key, 0.0) for row in table if row.owner)
        reference_consequential_policy = consequential_action_policy(exact, table)
        truth_row = next(row for row in table if row.key == scenario.truth.key)
        truth_consequence_severity = _joint_cross_severity(truth_row)
        truth_event = _event_key(scenario.truth, include_regime=include_regime_in_event)
        truth_cause = _cause_key(scenario.truth)
        owner_did_it = scenario.truth.gaps[scenario.corrupt_index].receiver is Actor.OWNER
        for coupling in InferenceCoupling:
            belief = _decouple(exact, table, coupling)
            arm_information = _mutual_information(belief, table)
            events = _aggregate(belief, table, "event")
            causes = _aggregate(belief, table, "cause")
            actions = _aggregate(belief, table, "action")
            total = sum(actions.values())
            if total > 0.0:
                actions = {key: value / total for key, value in actions.items()}
            owner_mass = sum(belief.get(row.key, 0.0) for row in table if row.owner)
            consequence_policy = consequential_action_policy(belief, table)
            promote = owner_mass >= CONSOLIDATION_THRESHOLD
            if promote and not owner_did_it:
                consolidation = FALSE_PROMOTE_COST
            elif owner_did_it and not promote:
                consolidation = FALSE_QUARANTINE_COST
            else:
                consolidation = 0.0
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "coupling": coupling.value,
                    "mutual_information_nats": information,
                    "arm_mutual_information_nats": arm_information,
                    "total_variation_to_joint": total_variation(exact, belief),
                    "event_truth_mass": events.get(truth_event, 0.0),
                    "cause_truth_mass": causes.get(truth_cause, 0.0),
                    "cause_argmax_correct": bool(
                        causes and max(causes, key=lambda n: (causes[n], n)) == truth_cause
                    ),
                    "owner_calibration_error": abs(owner_mass - reference_owner),
                    "action_posterior_distance": action_posterior_distance(
                        reference_actions, actions
                    ),
                    "decision_regret": decision_regret(reference_actions, actions),
                    "consolidation_cost": consolidation,
                    "consequential_action_policy": consequence_policy,
                    "selected_consequential_action": max(
                        consequence_policy,
                        key=lambda name: (consequence_policy[name], name),
                    ),
                    "consequential_action_distance_to_joint": (
                        action_posterior_distance(
                            reference_consequential_policy, consequence_policy
                        )
                    ),
                    "truth_cross_cell_severity": truth_consequence_severity,
                    "consequential_expected_cost": consequential_expected_cost(
                        consequence_policy, truth_consequence_severity
                    ),
                }
            )
    summaries: dict[str, dict[str, float]] = {}
    for coupling in InferenceCoupling:
        subset = [row for row in rows if row["coupling"] == coupling.value]
        regrets = [row["decision_regret"] for row in subset if row["decision_regret"] is not None]
        summaries[coupling.value] = {
            "cells": float(len(subset)),
            "mean_total_variation_to_joint": sum(row["total_variation_to_joint"] for row in subset)
            / len(subset),
            "mean_arm_mutual_information_nats": sum(
                row["arm_mutual_information_nats"] for row in subset
            )
            / len(subset),
            "mean_event_truth_mass": sum(row["event_truth_mass"] for row in subset) / len(subset),
            "stdev_event_truth_mass": _stdev([row["event_truth_mass"] for row in subset]),
            "mean_cause_truth_mass": sum(row["cause_truth_mass"] for row in subset) / len(subset),
            "stdev_cause_truth_mass": _stdev([row["cause_truth_mass"] for row in subset]),
            # The mass version degenerates to `resolved x 1{argmax correct}` once an
            # arm collapses the cause, so it scores confidence, not recovery.  The
            # 0/1 verdict is the honest comparison.
            "cause_argmax_accuracy": sum(1.0 for row in subset if row["cause_argmax_correct"])
            / len(subset),
            "mean_owner_calibration_error": sum(row["owner_calibration_error"] for row in subset)
            / len(subset),
            "mean_action_posterior_distance": sum(
                row["action_posterior_distance"] for row in subset
            )
            / len(subset),
            "mean_consequential_action_distance_to_joint": sum(
                row["consequential_action_distance_to_joint"] for row in subset
            )
            / len(subset),
            "consequential_action_difference_rate": sum(
                1.0
                for row in subset
                if row["selected_consequential_action"]
                != next(
                    joint_row["selected_consequential_action"]
                    for joint_row in rows
                    if joint_row["scenario_id"] == row["scenario_id"]
                    and joint_row["coupling"] == InferenceCoupling.JOINT.value
                )
            )
            / len(subset),
            "mean_consequential_expected_cost": sum(
                row["consequential_expected_cost"] for row in subset
            )
            / len(subset),
            "mean_decision_regret": sum(regrets) / len(regrets) if regrets else 0.0,
            "mean_consolidation_cost": sum(row["consolidation_cost"] for row in subset)
            / len(subset),
        }
    joint_rows = [row for row in rows if row["coupling"] == "joint"]
    factorized_loss = summaries[InferenceCoupling.FACTORIZED.value]["mean_total_variation_to_joint"]
    return {
        "protocol_id": TASK8_PROTOCOL_ID,
        "backbone_protocol_id": PROTOCOL_ID,
        "task": "task-8-joint-coupling-death-test",
        "evidence_status": (
            "D0 synthetic exact-posterior coupling ablation; no approximation error involved"
        ),
        "gaps": None if scenarios is not None else gaps,
        "scenario_seeds": None if scenarios is not None else list(scenario_seeds),
        "scenario_ids": [scenario.scenario_id for scenario in design],
        "event_partition": "H+Z" if include_regime_in_event else "H",
        "soft_coupling": {
            "type": "full_support_relative_probability",
            "interaction": "cause=actor x mechanism=handoff",
            "strength_nats": strength,
            "relative_odds_multiplier": math.exp(strength),
            "changes_support": False,
            "truth_and_target_share_interaction": True,
            "truth_generation_mode": "shared_stochastic_relative_probability_model",
        },
        "mean_mutual_information_nats": sum(row["mutual_information_nats"] for row in joint_rows)
        / max(1, len(joint_rows)),
        "min_measurable_factorization_tv": MIN_MEASURABLE_FACTORIZATION_TV,
        "factorization_loss_is_measurable": (factorized_loss >= MIN_MEASURABLE_FACTORIZATION_TV),
        "task_8_instrument_passed": (
            strength > 0.0 and factorized_loss >= MIN_MEASURABLE_FACTORIZATION_TV
        ),
        "consequential_endpoint": {
            "endpoint_id": "joint-cross-safety-policy@0.1",
            "partition": "(H+Z,C)",
            "actions": [
                JointConsequenceAction.PROCEED.value,
                JointConsequenceAction.VERIFY.value,
            ],
            "verify_cost": TASK8_VERIFY_COST,
            "unresolved_severity": TASK8_UNRESOLVED_SEVERITY,
            "truth_visible_to_action_policy": False,
            "endpoint_consumes_cross_term": task8_endpoint_consumes_interaction(),
        },
        "claim_boundary": (
            "An instrument pass establishes that the synthetic task contains a measurable "
            "soft HxC dependency. It does not establish that joint inference improves "
            "embodied utility or external validity."
        ),
        "summary": summaries,
        "rows": rows,
    }


def run_relative_probability_soft_coupling_study(
    *,
    gaps: int,
    scenario_seeds: Sequence[int],
    strengths_nats: Sequence[float] = (0.0, 0.5, 1.0, 1.5),
    state_budget: int = 2_000_000,
) -> dict[str, Any]:
    """Paired Task-8 negative control, sensitivity sweep, and primary rerun.

    Every strength uses the same stochastic truth-generator implementation and
    common random seeds.  This prevents the old deterministic generator at
    lambda=0 from being confounded with the soft-coupled generator at lambda>0.
    The predeclared primary strength is 1.5 nats; 0.5 and 1.0 are sensitivity
    points, not post-hoc alternatives allowed to replace a failed primary.
    """

    strengths = tuple(float(value) for value in strengths_nats)
    required = (0.0, RELATIVE_PROBABILITY_SOFT_COUPLING_NATS)
    if any(value < 0.0 for value in strengths):
        raise ValueError("Task 8 sensitivity strengths cannot be negative")
    if len(strengths) != len(set(strengths)):
        raise ValueError("Task 8 sensitivity strengths must be unique")
    if any(value not in strengths for value in required):
        raise ValueError("Task 8 study requires lambda=0 and the frozen lambda=1.5 primary")
    reports = {
        f"{strength:g}": run_joint_coupling_death_test(
            gaps=gaps,
            scenario_seeds=scenario_seeds,
            include_regime_in_event=True,
            state_budget=state_budget,
            relative_probability_coupling_nats=strength,
        )
        for strength in strengths
    }
    control = reports["0"]
    primary = reports[f"{RELATIVE_PROBABILITY_SOFT_COUPLING_NATS:g}"]
    factorized_name = InferenceCoupling.FACTORIZED.value
    control_tv = control["summary"][factorized_name]["mean_total_variation_to_joint"]
    primary_tv = primary["summary"][factorized_name]["mean_total_variation_to_joint"]
    factorized_summary = primary["summary"][factorized_name]
    joint_summary = primary["summary"][InferenceCoupling.JOINT.value]
    consequential_action_distance = factorized_summary[
        "mean_consequential_action_distance_to_joint"
    ]
    mean_factorized_excess_consequential_cost = (
        factorized_summary["mean_consequential_expected_cost"]
        - joint_summary["mean_consequential_expected_cost"]
    )
    belief_instrument_passed = bool(primary["task_8_instrument_passed"]) and (
        primary_tv > control_tv + MIN_MEASURABLE_FACTORIZATION_TV
    )
    endpoint_consumes_interaction = bool(
        primary["consequential_endpoint"]["endpoint_consumes_cross_term"]
    )
    consequential_action_endpoint_passed = (
        consequential_action_distance >= MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE
    )
    consequential_utility_benefit_passed = (
        mean_factorized_excess_consequential_cost
        >= MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE
    )
    joint_action_utility_passed = (
        belief_instrument_passed
        and endpoint_consumes_interaction
        and consequential_action_endpoint_passed
        and consequential_utility_benefit_passed
    )
    return {
        "protocol_id": TASK8_PROTOCOL_ID,
        "task": "task-8-relative-probability-soft-coupling-study",
        "design": {
            "gaps": gaps,
            "scenario_seeds": list(scenario_seeds),
            "state_budget": state_budget,
            "strengths_nats": list(strengths),
            "negative_control_strength_nats": 0.0,
            "primary_strength_nats": RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
            "common_random_numbers": True,
            "shared_truth_generator_implementation": True,
            "event_partition": "(H+Z,C)",
            "truth_visible_to_action_policy": False,
            "future_observations_visible": False,
        },
        "factorized_tv_negative_control": control_tv,
        "factorized_tv_primary": primary_tv,
        "primary_minus_control_factorized_tv": primary_tv - control_tv,
        "belief_coupling_instrument_passed": belief_instrument_passed,
        "consequential_endpoint_id": "joint-cross-safety-policy@0.1",
        "endpoint_consumes_interaction": endpoint_consumes_interaction,
        "consequential_action_distribution_distance_primary": (consequential_action_distance),
        "min_measurable_consequential_action_distribution_distance": (
            MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE
        ),
        "consequential_action_endpoint_passed": consequential_action_endpoint_passed,
        "legacy_embodied_action_posterior_distance_primary": factorized_summary[
            "mean_action_posterior_distance"
        ],
        "mean_factorized_excess_consequential_cost": (mean_factorized_excess_consequential_cost),
        "min_measurable_mean_consequential_cost_advantage": (
            MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE
        ),
        "consequential_utility_benefit_passed": consequential_utility_benefit_passed,
        "joint_action_utility_passed": joint_action_utility_passed,
        "task_8_definition_and_rerun_complete": True,
        "task_8_passed": joint_action_utility_passed,
        "task_8_verdict": (
            "PASS"
            if joint_action_utility_passed
            else (
                (
                    "BELIEF_INSTRUMENT_PASS_CONSEQUENTIAL_ACTION_FAILED"
                    if not consequential_action_endpoint_passed
                    else "BELIEF_AND_ACTION_PASS_CONSEQUENTIAL_UTILITY_FAILED"
                )
                if belief_instrument_passed
                else "BELIEF_INSTRUMENT_FAILED"
            )
        ),
        "seven_operator_efficacy_authorized": False,
        "claim_boundary": (
            "Task 8 overall passes only when the soft belief-coupling instrument, a "
            "constructive cross-term consumption check, measurable consequential-action "
            "change, and positive registered consequential-cost advantage all pass. The "
            "action policy cannot observe truth; distributional change alone is not utility "
            "benefit, and this artifact never authorizes seven-operator efficacy claims."
        ),
        "reports_by_strength": reports,
    }
