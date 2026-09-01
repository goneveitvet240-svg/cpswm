"""Additive v0.3 Gate A: reachability references and a finite-sample estimator.

v0.2's Gate A asks only whether trivial rules are *bad enough*.  Every one of its
criteria has the form "this error must exceed a floor", so a target made of pure
noise would pass almost all of them.  This module adds the missing symmetric
side: how much of the remaining error is reachable at all.

Nothing here modifies the v0.2 world generator, manifest, gate module, artifact,
or verdict.  The generator is imported unchanged and its outputs are read-only.

Three references and one executable estimator:

``observable_parameter_oracle``
    Knows the world's parameters (and therefore the regime schedule, which is a
    deterministic function of them) but not the latent actor.  It must condition
    on ``observed = False``, because the generator's visibility depends on
    location, actor class, and calendar context: the unobserved subpopulation is
    not a uniform sample of the world.  This is a *privileged upper bound* on
    available headroom, never a floor a method is expected to reach -- a method
    must additionally infer change points and habit parameters from data.

``unconditional_parameter_reference``
    The same computation with the MNAR correction removed.  It exists only so a
    test can assert the correction has the right sign; it is never a gate input.

``true_actor_parameter_oracle``
    Additionally given the latent actor.  Report-only, and excluded from every
    verdict: the generator emits no actor evidence on unobserved steps, so the
    gap it opens is provably unreachable from visible data.

``shrunk_context_estimator``
    An executable, method-free rule.  v0.2's frozen estimator partitions a
    35-day window by calendar context, which leaves the weekend cell with a
    couple of samples to locate a mode over eight to twelve locations.  This one
    shrinks the context counts toward the pooled counts with a pseudo-count
    strength, so a thin cell degrades to the pooled estimate instead of to
    noise.  Its window and strength are selected on TRAIN worlds only and then
    frozen into the v0.3 manifest.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass

from .structure_two_world_generator_v0_2 import (
    StructureTwoWorld,
    StructureTwoWorldRollout,
    StructureTwoWorldStep,
    WorldDistributionConfig,
)

PROTOCOL_ID = "structure-two-world-generator-gate-a@0.3"
CONTEXTS = ("weekday", "weekend")


def _normalise(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0.0:
        uniform = 1.0 / max(1, len(values))
        return {key: uniform for key in values}
    return {key: value / total for key, value in values.items()}


def encounter_order(
    locations: tuple[str, ...],
    visible_encounters: tuple[str, ...] = (),
) -> dict[str, int]:
    """Return the formal robot-visible first-encounter tie-break order.

    ``project_two_action_benchmark._locations`` scans the visible episode and
    de-duplicates locations in first-encounter order.  ``rollout.locations`` is
    instead the generator's candidate catalogue, so treating its order as an
    encounter order silently re-introduces an identifier-derived tie-break.

    Gate A first orders candidates by their first *visible* observed-location
    occurrence.  A location that is never visible still has to be represented
    because evaluator truth may place the object there; those candidates are
    appended in the frozen catalogue order.  Location strings themselves are
    never sorted or used as features.
    """

    candidates = set(locations)
    ordered = list(dict.fromkeys(item for item in visible_encounters if item in candidates))
    ordered.extend(item for item in locations if item not in ordered)
    return {location: index for index, location in enumerate(ordered)}


def _argmax(values: dict[str, float], order: dict[str, int] | None = None) -> str:
    if order is None:
        return min(values.items(), key=lambda item: (-item[1], item[0]))[0]
    return min(values.items(), key=lambda item: (-item[1], order.get(item[0], len(order))))[0]


def observation_propensity(
    world: StructureTwoWorld,
    config: WorldDistributionConfig,
    *,
    location: str,
    actor_class: str,
    context: str,
) -> float:
    """Mirror of the generator's visibility computation, including its clamp."""

    propensity = world.base_observation_probability * world.location_visibility[location]
    if actor_class == "unknown":
        propensity *= config.unknown_visibility_multiplier
    elif actor_class == "guest":
        propensity *= config.guest_visibility_multiplier
    if context == "weekend":
        propensity *= config.weekend_visibility_multiplier
    return max(0.05, min(0.98, propensity))


def _actor_components(
    world: StructureTwoWorld, *, regime: str, context: str
) -> list[tuple[str, float, dict[str, float]]]:
    """(actor_class, prior, location distribution) for every actor class."""

    habit = world.habit_distribution(regime, context)
    uniform = {location: 1.0 / len(world.locations) for location in world.locations}
    guest_prior = max(0.0, 1.0 - world.owner_event_probability - world.unknown_event_probability)
    components: list[tuple[str, float, dict[str, float]]] = [
        ("owner", world.owner_event_probability, habit),
        ("unknown", world.unknown_event_probability, uniform),
    ]
    if world.guest_actors:
        share = guest_prior / len(world.guest_actors)
        for guest in world.guest_actors:
            components.append(("guest", share, world.guest_distributions[guest]))
    return components


def unobserved_location_posterior(
    world: StructureTwoWorld,
    config: WorldDistributionConfig,
    *,
    regime: str,
    context: str,
    apply_mnar_correction: bool = True,
) -> dict[str, float]:
    """P(location | observed = False, world parameters, regime, context).

    With ``apply_mnar_correction`` disabled this returns the plain actor-marginal
    P(location), which ignores that low-visibility locations and low-visibility
    actor classes are over-represented among unobserved steps.
    """

    components = _actor_components(world, regime=regime, context=context)
    mass: dict[str, float] = {}
    for location in world.locations:
        total = 0.0
        for actor_class, prior, distribution in components:
            weight = prior * distribution.get(location, 0.0)
            if apply_mnar_correction:
                weight *= 1.0 - observation_propensity(
                    world,
                    config,
                    location=location,
                    actor_class=actor_class,
                    context=context,
                )
            total += weight
        mass[location] = total
    return _normalise(mass)


def true_actor_location_posterior(
    world: StructureTwoWorld,
    config: WorldDistributionConfig,
    *,
    step: StructureTwoWorldStep,
    apply_mnar_correction: bool = True,
) -> dict[str, float]:
    """Report-only reference that is additionally given the latent actor."""

    if step.true_actor == world.owner_actor:
        actor_class = "owner"
        distribution = world.habit_distribution(step.regime, step.context)
    elif step.true_actor == "unknown_actor":
        actor_class = "unknown"
        distribution = {item: 1.0 / len(world.locations) for item in world.locations}
    else:
        actor_class = "guest"
        distribution = world.guest_distributions[step.true_actor]
    if not apply_mnar_correction:
        return _normalise(dict(distribution))
    mass = {
        location: distribution.get(location, 0.0)
        * (
            1.0
            - observation_propensity(
                world,
                config,
                location=location,
                actor_class=actor_class,
                context=step.context,
            )
        )
        for location in world.locations
    }
    return _normalise(mass)


@dataclass(frozen=True, slots=True)
class ShrunkEstimatorConfig:
    """Rolling-count estimator settings; selected on train worlds, then frozen.

    ``owner_probability_threshold`` is carried per estimator on purpose.  An
    earlier draft declared it here but read the frozen v0.2 value for both
    estimators, so the field looked configurable while silently doing nothing --
    the same class of defect this whole line of work exists to catch.
    """

    window_days: int
    context_shrinkage_pseudocounts: float
    owner_probability_threshold: float


@dataclass(frozen=True, slots=True)
class RegimeAdaptiveWitnessConfig:
    """Minimal learnability witness: standard CUSUM over visible history only.

    It reads observed locations, the visible owner probability, and the calendar
    context.  It never reads the latent actor, the true change points, the true
    regime label, or any CPSWM internal state.

    Detection is a two-window total-variation test, not an accumulating CUSUM.
    The reference window and the recent window are disjoint: an observation sits
    in the recent window until it is evicted, and only then joins the reference.
    Letting recent samples also count inside the reference pulls the two
    distributions together and biases the statistic against firing.
    A CUSUM of the form ``I[mispredicted] - delta`` is not centered under the
    null here: a stable habit has mode mass 0.42-0.58, so the mispredict rate is
    already 0.42-0.58 and any fixed ``delta`` below that makes the statistic
    drift upward with no change present.  Such a rule is a timer that resets on
    a schedule, and its reset count carries no evidence about detection.  Total
    variation between a reference window and a recent window has a null
    expectation set by window size rather than by elapsed time, so it does not
    drift.  If this witness clears the
    frozen search bar, the target is finite-sample recoverable; if it also
    absorbs most of a proposed operator's benefit, that is worth discovering now
    rather than in review, and it must then be carried as a formal baseline.
    """

    recent_window: int
    divergence_threshold: float
    minimum_reference_observations: int
    context_shrinkage_pseudocounts: float
    owner_probability_threshold: float


def _prune(rows: deque[tuple[int, str]], counts: Counter[str], *, minimum_day: int) -> None:
    while rows and rows[0][0] < minimum_day:
        _, location = rows.popleft()
        counts[location] -= 1
        if counts[location] <= 0:
            del counts[location]


@dataclass(frozen=True, slots=True)
class RolloutV03Reading:
    """One rollout's readings.

    Analytic and empirical oracle errors are separate fields and must stay that
    way.  The analytic value is a property of the world; the empirical value is
    what a predictor holding that same posterior actually scored on this finite
    rollout.  They differ systematically, so only the empirical field may be
    subtracted from an empirical estimator's error.
    """

    world_seed: int
    rollout_id: str
    step_count: int
    unobserved_step_count: int
    search_last_observed_error: float
    search_frozen_context_error: float
    search_witness_error: float
    search_observable_oracle_error_empirical: float
    search_observable_oracle_unobserved_error_empirical: float
    search_observable_oracle_unobserved_error_analytic: float
    search_unconditional_reference_error_empirical: float
    search_true_actor_oracle_error_empirical: float
    search_last_observed_normalised_path_cost: float
    search_frozen_context_normalised_path_cost: float
    search_witness_normalised_path_cost: float
    put_back_frozen_context_error: float
    put_back_witness_error: float
    witness_reset_count: int
    witness_reset_days: tuple[int, ...]
    witness_admitted_weekday_count: int
    witness_admitted_weekend_count: int


def analytic_unobserved_accuracy(
    world: StructureTwoWorld, config: WorldDistributionConfig, *, regime: str, context: str
) -> float:
    """max_l P(l | unobserved, world, regime, context) -- a property of the world."""

    posterior = unobserved_location_posterior(world, config, regime=regime, context=context)
    return max(posterior.values())


def day_regime(world: StructureTwoWorld, day: int) -> str:
    if day < world.abrupt_day:
        return "baseline"
    return "shifted" if day < world.recurrence_day else "recurrent"


def day_context(day: int) -> str:
    return "weekday" if day % 7 < 5 else "weekend"


def analytic_world_unobserved_error(
    world: StructureTwoWorld, config: WorldDistributionConfig
) -> float:
    """1 - E[max_l P(l | unobserved)] integrated over P(unobserved) for every day.

    This reads only world parameters and the deterministic day -> (regime,
    context) map.  It never touches a trajectory seed, an observation seed, or
    the realised observation mask, so it is a property of the world alone.  The
    earlier field averaged over whichever days happened to be unobserved in one
    rollout and therefore moved with the observation seed.
    """

    numerator = denominator = 0.0
    for day in range(world.duration_days):
        context = day_context(day)
        components = _actor_components(world, regime=day_regime(world, day), context=context)
        joint: dict[str, float] = {}
        for actor_class, prior, distribution in components:
            for location in world.locations:
                weight = (
                    prior
                    * distribution.get(location, 0.0)
                    * (
                        1.0
                        - observation_propensity(
                            world,
                            config,
                            location=location,
                            actor_class=actor_class,
                            context=context,
                        )
                    )
                )
                joint[location] = joint.get(location, 0.0) + weight
        numerator += max(joint.values())
        denominator += sum(joint.values())
    return 1.0 - numerator / denominator if denominator else 0.0


def _ranked(
    scores: dict[str, float],
    locations: tuple[str, ...],
    first: str | None,
    positions: dict[str, int] | None = None,
) -> list[str]:
    index = positions if positions is not None else encounter_order(locations)
    order = sorted(locations, key=lambda item: (-scores.get(item, 0.0), index[item]))
    if first is not None and first in order:
        order.remove(first)
        order.insert(0, first)
    return order


def _normalised_path_cost(order: list[str], truth: str, location_count: int) -> float:
    if location_count <= 1:
        return 0.0
    rank = order.index(truth) if truth in order else location_count - 1
    return rank / (location_count - 1)


class _CountingEstimator:
    """Shared count bookkeeping for the rolling and witness estimators."""

    def __init__(self, fallback: str, *, threshold: float, shrinkage: float) -> None:
        self.sticky = fallback
        self.threshold = threshold
        self.shrinkage = shrinkage
        self.pooled: Counter[str] = Counter()
        self.by_context: dict[str, Counter[str]] = {item: Counter() for item in CONTEXTS}

    def scores(self, context: str) -> dict[str, float]:
        pooled_total = sum(self.pooled.values())
        cell = self.by_context[context]
        if not cell:
            # v0.2's frozen chain is context cell -> pooled mode -> sticky.  With
            # zero shrinkage the blend below would score every candidate 0 and
            # fall through to a lexicographic tie-break, which is not the same
            # rule, so the empty cell is handled explicitly.
            if self.pooled:
                return {location: float(count) for location, count in self.pooled.items()}
            return {self.sticky: 1.0}
        candidates = set(self.pooled) | set(cell)
        return {
            location: cell.get(location, 0)
            + (
                self.shrinkage * self.pooled.get(location, 0) / pooled_total
                if pooled_total
                else 0.0
            )
            for location in candidates
        }

    def mode(self, context: str, order: dict[str, int] | None = None) -> str:
        return _argmax(self.scores(context), order)

    def admit(self, step: StructureTwoWorldStep) -> bool:
        return (
            step.visible_owner_probability is not None
            and step.visible_owner_probability >= self.threshold
        )


class _RollingEstimator(_CountingEstimator):
    def __init__(self, fallback: str, config: ShrunkEstimatorConfig) -> None:
        super().__init__(
            fallback,
            threshold=config.owner_probability_threshold,
            shrinkage=config.context_shrinkage_pseudocounts,
        )
        self.window = config.window_days
        self.pooled_rows: deque[tuple[int, str]] = deque()
        self.context_rows: dict[str, deque[tuple[int, str]]] = {item: deque() for item in CONTEXTS}

    def advance(self, step: StructureTwoWorldStep) -> None:
        minimum_day = step.day - self.window + 1
        _prune(self.pooled_rows, self.pooled, minimum_day=minimum_day)
        for context in CONTEXTS:
            _prune(self.context_rows[context], self.by_context[context], minimum_day=minimum_day)

    def observe(self, step: StructureTwoWorldStep, location: str) -> None:
        self.sticky = location
        self.pooled_rows.append((step.day, location))
        self.pooled[location] += 1
        self.context_rows[step.context].append((step.day, location))
        self.by_context[step.context][location] += 1


class _WitnessEstimator(_CountingEstimator):
    """Counts since the last TV-detected change.

    Detection uses two explicit, disjoint windows cut from ``detector_history``:
    an older reference window and a newer recent window.  The prediction counts
    are separate from those detector windows.  A reset seeds the new prediction
    state from the recent window and retains only that recent window as detector
    warm-up, preventing a small post-reset reference from making another reset
    artificially easier.
    """

    def __init__(self, fallback: str, config: RegimeAdaptiveWitnessConfig) -> None:
        super().__init__(
            fallback,
            threshold=config.owner_probability_threshold,
            shrinkage=config.context_shrinkage_pseudocounts,
        )
        self.config = config
        self.detector_history: deque[tuple[int, str, str]] = deque(
            maxlen=(max(1, config.minimum_reference_observations) + max(1, config.recent_window))
        )
        self.reset_count = 0
        self.reset_days: list[int] = []
        self.observation_count = 0

    def advance(self, step: StructureTwoWorldStep) -> None:
        del step

    def detector_windows(
        self,
    ) -> tuple[tuple[tuple[int, str, str], ...], tuple[tuple[int, str, str], ...]] | None:
        required = self.config.minimum_reference_observations + self.config.recent_window
        if len(self.detector_history) < required:
            return None
        rows = tuple(self.detector_history)
        return rows[: self.config.minimum_reference_observations], rows[
            -self.config.recent_window :
        ]

    def _total_variation(self) -> float:
        windows = self.detector_windows()
        if windows is None:
            return 0.0
        reference_rows, recent_rows = windows
        reference_by_context = {item: Counter() for item in CONTEXTS}
        recent_by_context = {item: Counter() for item in CONTEXTS}
        for _day, context, location in reference_rows:
            reference_by_context[context][location] += 1
        for _day, context, location in recent_rows:
            recent_by_context[context][location] += 1
        weighted_distance = 0.0
        included_recent = 0
        for context in CONTEXTS:
            reference = reference_by_context[context]
            recent = recent_by_context[context]
            reference_total = sum(reference.values())
            recent_total = sum(recent.values())
            if reference_total == 0 or recent_total == 0:
                continue
            keys = set(reference) | set(recent)
            distance = 0.5 * sum(
                abs(recent.get(key, 0) / recent_total - reference.get(key, 0) / reference_total)
                for key in keys
            )
            weighted_distance += recent_total * distance
            included_recent += recent_total
        return weighted_distance / included_recent if included_recent else 0.0

    def observe(self, step: StructureTwoWorldStep, location: str) -> None:
        self.sticky = location
        self.observation_count += 1
        self.pooled[location] += 1
        self.by_context[step.context][location] += 1
        self.detector_history.append((step.day, step.context, location))
        if self._total_variation() > self.config.divergence_threshold:
            windows = self.detector_windows()
            assert windows is not None
            _reference_rows, recent_rows = windows
            self.pooled = Counter()
            self.by_context = {item: Counter() for item in CONTEXTS}
            for _day, recent_context, recent_location in recent_rows:
                self.pooled[recent_location] += 1
                self.by_context[recent_context][recent_location] += 1
            self.detector_history = deque(
                recent_rows,
                maxlen=(
                    max(1, self.config.minimum_reference_observations)
                    + max(1, self.config.recent_window)
                ),
            )
            self.reset_count += 1
            self.reset_days.append(step.day)

    @property
    def false_reset_rate_per_observation(self) -> float:
        return self.reset_count / self.observation_count if self.observation_count else 0.0


def evaluate_rollout_v0_3(
    rollout: StructureTwoWorldRollout,
    world: StructureTwoWorld,
    config: WorldDistributionConfig,
    *,
    frozen: ShrunkEstimatorConfig,
    witness: RegimeAdaptiveWitnessConfig,
) -> RolloutV03Reading:
    """Score the rolling estimator, the reachability references, and the witness.

    The witness is retained so its failure stays reproducible, but it is NOT on
    the Gate A decision path: at a horizon where the window is short relative to
    a regime, resetting on a detected change only discards samples, and the
    plain window plus shrinkage rule dominates it.  Dropping the detector from
    the gate says nothing about CF-BOCPD, which must still beat fixed-window,
    multi-window and simple-change-detector baselines when method comparison
    resumes.

    Each estimator advances its own history with its own admission threshold, so
    no parameter is shared between them by accident.
    """

    locations = tuple(rollout.locations)
    positions = encounter_order(
        locations,
        tuple(
            step.observed_location
            for step in rollout.steps
            if step.observed and step.observed_location is not None
        ),
    )
    fallback = min(locations, key=positions.__getitem__)
    rolling = _RollingEstimator(fallback, frozen)
    adaptive = _WitnessEstimator(fallback, witness)
    last_observed = fallback
    last_observed_tail_counts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    path: Counter[str] = Counter()
    witness_admissions: Counter[str] = Counter()
    unobserved = 0
    cache: dict[tuple[str, str], dict[str, float]] = {}

    for step in rollout.steps:
        rolling.advance(step)
        adaptive.advance(step)
        visible_now = step.observed and step.observed_location is not None
        if visible_now:
            assert step.observed_location is not None
            last_observed = step.observed_location
            # Match the formal action evaluator: last observed is pinned first,
            # while every remaining location is ranked by cumulative observed
            # counts.  This tail is not owner-filtered and does not use the
            # rolling estimator's 35-day window.
            last_observed_tail_counts[step.observed_location] += 1
            if rolling.admit(step):
                rolling.observe(step, step.observed_location)
            if adaptive.admit(step):
                witness_admissions[step.context] += 1
                adaptive.observe(step, step.observed_location)

        key = (step.regime, step.context)
        if key not in cache:
            cache[key] = unobserved_location_posterior(
                world, config, regime=step.regime, context=step.context
            )
        posterior = cache[key]
        frozen_scores = rolling.scores(step.context)
        witness_scores = adaptive.scores(step.context)
        frozen_mode = _argmax(frozen_scores, positions)
        witness_mode = _argmax(witness_scores, positions)

        head = step.observed_location if visible_now else None
        orders = {
            "last": _ranked(
                {loc: float(last_observed_tail_counts.get(loc, 0)) for loc in locations},
                locations,
                head or last_observed,
                positions,
            ),
            "frozen": _ranked(
                frozen_scores,
                locations,
                head or frozen_mode,
                positions,
            ),
            "witness": _ranked(
                witness_scores,
                locations,
                head or witness_mode,
                positions,
            ),
        }
        for name, order in orders.items():
            errors[f"search_{name}"] += order[0] != step.true_location
            path[name] += _normalised_path_cost(order, step.true_location, len(locations))

        oracle_head = head or _argmax(posterior, positions)
        uncond = unobserved_location_posterior(
            world, config, regime=step.regime, context=step.context, apply_mnar_correction=False
        )
        actor_posterior = true_actor_location_posterior(world, config, step=step)
        errors["search_oracle"] += oracle_head != step.true_location
        if not visible_now:
            errors["search_oracle_unobserved"] += oracle_head != step.true_location
        errors["search_uncond"] += (head or _argmax(uncond, positions)) != step.true_location
        errors["search_actor"] += (
            head or _argmax(actor_posterior, positions)
        ) != step.true_location

        errors["put_frozen"] += frozen_mode != step.true_owner_habit_location
        errors["put_witness"] += witness_mode != step.true_owner_habit_location
        unobserved += not step.observed

    total = len(rollout.steps)
    return RolloutV03Reading(
        world_seed=rollout.world_seed,
        rollout_id=rollout.rollout_id,
        step_count=total,
        unobserved_step_count=unobserved,
        search_last_observed_error=errors["search_last"] / total,
        search_frozen_context_error=errors["search_frozen"] / total,
        search_witness_error=errors["search_witness"] / total,
        search_observable_oracle_error_empirical=errors["search_oracle"] / total,
        search_observable_oracle_unobserved_error_empirical=(
            errors["search_oracle_unobserved"] / unobserved if unobserved else 0.0
        ),
        # World-level: integrated over P(unobserved) for every day, never over the
        # observation mask this rollout happened to draw.
        search_observable_oracle_unobserved_error_analytic=analytic_world_unobserved_error(
            world, config
        ),
        search_unconditional_reference_error_empirical=errors["search_uncond"] / total,
        search_true_actor_oracle_error_empirical=errors["search_actor"] / total,
        search_last_observed_normalised_path_cost=path["last"] / total,
        search_frozen_context_normalised_path_cost=path["frozen"] / total,
        search_witness_normalised_path_cost=path["witness"] / total,
        put_back_frozen_context_error=errors["put_frozen"] / total,
        put_back_witness_error=errors["put_witness"] / total,
        witness_reset_count=adaptive.reset_count,
        witness_reset_days=tuple(adaptive.reset_days),
        witness_admitted_weekday_count=witness_admissions["weekday"],
        witness_admitted_weekend_count=witness_admissions["weekend"],
    )


__all__ = [
    "CONTEXTS",
    "PROTOCOL_ID",
    "RegimeAdaptiveWitnessConfig",
    "RolloutV03Reading",
    "ShrunkEstimatorConfig",
    "analytic_unobserved_accuracy",
    "analytic_world_unobserved_error",
    "day_context",
    "day_regime",
    "encounter_order",
    "evaluate_rollout_v0_3",
    "observation_propensity",
    "true_actor_location_posterior",
    "unobserved_location_posterior",
]
