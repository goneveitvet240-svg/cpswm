"""WP0 baseline harness for the OAM-PHM substructure.

`OAM-PHM §9.1` lists the baselines every OAM-PHM claim must clear before it can
be called a contribution, and `§9.4` fixes the fairness rules.  Without a
runnable floor, `§12.1` completion condition 8 (*"relative to independently
tuned O-STaR and strong combined baselines, produce action- or utility-level
gains"*) cannot be evaluated, and neither can `§12.2` stop condition 1
(*"strong combined baselines match the candidate method after independent
tuning"*).

Two properties are enforced structurally rather than by convention:

* **No truth access.**  A baseline is handed a :class:`SymbolicSimulationResult`
  — the robot-visible stream — and nothing else.  Ground truth lives behind the
  capability gate in the privileged view and is only ever read by the scorer.
* **Identical inputs.**  :func:`compare_baselines` feeds every entry the same
  run and the same query set, so a difference in score cannot come from a
  difference in information (`§9.4` rule 1 and rule 6).

Baselines that depend on capabilities still suspended by the F0 review gate are
registered with an explicit status instead of being silently omitted, so the
registry always shows what is missing rather than only what exists.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from math import log
from typing import Protocol
from uuid import UUID

import numpy as np
from pydantic import Field, model_validator

from cpswm.contracts import ObservationOutcome
from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.continual.rls import RecursiveLeastSquares, RLSConfig
from cpswm.system.world_model_simulator import SymbolicSimulationResult

#: Mass reserved for unseen locations so held-out truth never yields -inf NLL.
DEFAULT_SMOOTHING = 1e-3


class BaselineStatus(StrEnum):
    """Why a `§9.1` baseline is or is not runnable today."""

    IMPLEMENTED = "implemented"
    #: Blocked by the F0 review gate (multi-person / guest / handover / change).
    GATED_BY_REVIEW = "gated_by_review"
    #: Requires a faithful reimplementation of an external published system.
    EXTERNAL_REIMPLEMENTATION_REQUIRED = "external_reimplementation_required"


class LocationQuery(ContractModel):
    """Ask where one object instance is at one point in time."""

    object_instance_id: UUID
    query_time: datetime


class LocationBeliefPrediction(ContractModel):
    """A normalised belief over candidate locations for one query."""

    query: LocationQuery
    location_posterior: dict[UUID, Probability] = Field(min_length=1)
    baseline_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_posterior(self) -> LocationBeliefPrediction:
        total = sum(self.location_posterior.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError("location_posterior must sum to one")
        return self

    def probability_of(self, location_id: UUID) -> float:
        return self.location_posterior.get(location_id, 0.0)

    @property
    def top1_location_id(self) -> UUID:
        # Ties break on UUID so the same input always yields the same ranking.
        return max(
            sorted(self.location_posterior),
            key=lambda location_id: self.location_posterior[location_id],
        )


class LocationBeliefBaseline(Protocol):
    """The complete interface a baseline may use: the visible stream only."""

    baseline_version: str

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction: ...


class BaselineScore(ContractModel):
    """Scores for one baseline over one query set."""

    baseline_version: str = Field(min_length=1)
    top1_accuracy: float | None = Field(ge=0.0, le=1.0)
    mean_negative_log_likelihood: float | None = Field(default=None, ge=0.0)
    sample_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_zero_sample_semantics(self) -> BaselineScore:
        # Mirrors the F0 evaluator: no samples means undefined, not zero.
        if self.sample_count == 0 and (
            self.top1_accuracy is not None or self.mean_negative_log_likelihood is not None
        ):
            raise ValueError("a zero-sample score must leave both metrics undefined")
        if self.sample_count > 0 and self.top1_accuracy is None:
            raise ValueError("a scored baseline must report top-1 accuracy")
        return self


class BaselineRegistryEntry(ContractModel):
    """One `§9.1` row, with its runnable status recorded either way."""

    name: str = Field(min_length=1)
    status: BaselineStatus
    baseline_version: str | None = None
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_version_presence(self) -> BaselineRegistryEntry:
        implemented = self.status == BaselineStatus.IMPLEMENTED
        if implemented and not self.baseline_version:
            raise ValueError("an implemented baseline must declare a version")
        if not implemented and self.baseline_version:
            raise ValueError("a non-implemented baseline must not declare a version")
        return self


def _detected_history(
    run: SymbolicSimulationResult, object_instance_id: UUID, before: datetime
) -> list[tuple[datetime, UUID]]:
    """Return ``(time, location)`` for detections strictly before ``before``.

    Only ``DETECTED`` outcomes carry identity and location, so a missed or
    ambiguous observation cannot contribute a location here by construction.
    """

    history = [
        (result.detection_time, result.detected_location_id)
        for result in run.detection_results
        if result.outcome == ObservationOutcome.DETECTED
        and result.detected_object_instance_id == object_instance_id
        and result.detection_time is not None
        and result.detected_location_id is not None
        and result.detection_time < before
    ]
    return sorted(history)


def _candidate_locations(run: SymbolicSimulationResult) -> tuple[UUID, ...]:
    """Every location the visible stream mentions, plus the known start."""

    seen = {
        result.detected_location_id
        for result in run.detection_results
        if result.detected_location_id is not None
    }
    seen.add(run.initial_target_location_id)
    return tuple(sorted(seen))


def _smoothed(
    weights: dict[UUID, float], candidates: tuple[UUID, ...], smoothing: float
) -> dict[UUID, Probability]:
    total_weight = sum(weights.values())
    uniform = smoothing / len(candidates)
    if total_weight <= 0.0:
        return dict.fromkeys(candidates, 1.0 / len(candidates))
    posterior = {
        location_id: uniform + (1.0 - smoothing) * weights.get(location_id, 0.0) / total_weight
        for location_id in candidates
    }
    normaliser = sum(posterior.values())
    return {location_id: value / normaliser for location_id, value in posterior.items()}


class LastSeenLocationBaseline:
    """`§9.1` *last observation / last seen*: trust the newest detection.

    This is the floor every memory claim must clear.  It has no notion of
    persistence, so it is exactly wrong in the way the substructure is about:
    an object seen once in an anomalous place stays there forever.
    """

    baseline_version = "oam-phm-last-seen@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        weights: dict[UUID, float] = {}
        if history:
            weights[history[-1][1]] = 1.0
        else:
            weights[run.initial_target_location_id] = 1.0
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )


class HouseholdFrequencyPriorBaseline:
    """`§9.1` *household frequency prior*: one pooled distribution, no person.

    Deliberately household-level.  `§2.2` names person conditioning as one of
    the boundaries OAM-PHM must cross, so the pooled version is the comparison
    that makes crossing it measurable.
    """

    baseline_version = "oam-phm-household-frequency@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        counts = Counter(location_id for _, location_id in history)
        weights = {location_id: float(count) for location_id, count in counts.items()}
        if not weights:
            weights = {run.initial_target_location_id: 1.0}
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )


class MarkovTransitionBaseline:
    """`§9.1` *Markov transition model*: propagate from the last detection.

    Transitions are counted between consecutive detections of the same object.
    With a single observed transition the estimate is degenerate; that is the
    point — it shows how little a first-order model extracts from sparse,
    selectively sampled observation streams.
    """

    baseline_version = "oam-phm-markov-transition@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        if not history:
            weights = {run.initial_target_location_id: 1.0}
            return LocationBeliefPrediction(
                query=query,
                location_posterior=_smoothed(weights, candidates, self.smoothing),
                baseline_version=self.baseline_version,
            )
        transitions: dict[UUID, Counter[UUID]] = defaultdict(Counter)
        for (_, source), (_, destination) in pairwise(history):
            transitions[source][destination] += 1
        current = history[-1][1]
        outgoing = transitions.get(current)
        if outgoing:
            weights = {location_id: float(count) for location_id, count in outgoing.items()}
        else:
            # No observed transition out of here: staying put is the only
            # evidence-backed hypothesis, and smoothing carries the rest.
            weights = {current: 1.0}
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )


class RLSDecayedFrequencyBaseline:
    """Prototype: decayed location-frequency baseline driven by RLS updates.

    This is an OAM-PHM-ready experiment baseline. It intentionally keeps the
    same visible-stream only contract as all other WP0 baselines and does not
    access privileged truth.
    """

    baseline_version = "oam-phm-rls-decayed-frequency@0.1"

    def __init__(
        self,
        *,
        smoothing: float = DEFAULT_SMOOTHING,
        forgetting_factor: float = 0.98,
        ridge: float = 1e-6,
        prior_scale: float = 1e4,
    ) -> None:
        self.smoothing = smoothing
        self.forgetting_factor = forgetting_factor
        self.ridge = ridge
        self.prior_scale = prior_scale

        if not (0.0 < self.forgetting_factor <= 1.0):
            raise ValueError("forgetting_factor must be in (0, 1]")

    def _one_hot(self, index: int, size: int) -> np.ndarray:
        vector = np.zeros(size, dtype=float)
        vector[index] = 1.0
        return vector

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)

        if not candidates:
            raise ValueError("no candidate locations available")

        if not history:
            weights = {run.initial_target_location_id: 1.0}
            return LocationBeliefPrediction(
                query=query,
                location_posterior=_smoothed(weights, candidates, self.smoothing),
                baseline_version=self.baseline_version,
            )

        size = len(candidates)
        index_by_location = {location_id: idx for idx, location_id in enumerate(candidates)}
        models = {
            location_id: RecursiveLeastSquares(
                RLSConfig(
                    feature_dim=size,
                    forgetting_factor=self.forgetting_factor,
                    ridge=self.ridge,
                    prior_scale=self.prior_scale,
                )
            )
            for location_id in candidates
        }

        for _, observed_location in history:
            if observed_location not in index_by_location:
                continue
            observed_idx = index_by_location[observed_location]
            for location_id in candidates:
                x = self._one_hot(index_by_location[location_id], size)
                y = 1.0 if index_by_location[location_id] == observed_idx else 0.0
                models[location_id].update(x, y, gate=1.0, forgetting_factor=self.forgetting_factor)

        weights = {}
        for location_id in candidates:
            x = self._one_hot(index_by_location[location_id], size)
            score = models[location_id].predict(x)
            weights[location_id] = float(1.0 / (1.0 + np.exp(-score)))

        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )


#: `§9.1` in full.  Entries that cannot run today say so, so that a reader can
#: never mistake "not compared" for "compared and beaten".
SECTION_9_1_REGISTRY: tuple[BaselineRegistryEntry, ...] = (
    BaselineRegistryEntry(
        name="last observation / last seen",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=LastSeenLocationBaseline.baseline_version,
        note="Visible-stream only; no persistence model.",
    ),
    BaselineRegistryEntry(
        name="household frequency prior",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=HouseholdFrequencyPriorBaseline.baseline_version,
        note="Pooled over the household; deliberately not person-conditioned.",
    ),
    BaselineRegistryEntry(
        name="Markov transition model",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=MarkovTransitionBaseline.baseline_version,
        note="First-order transitions counted between consecutive detections.",
    ),
    BaselineRegistryEntry(
        name="person-conditioned frequency prior",
        status=BaselineStatus.GATED_BY_REVIEW,
        note=(
            "Needs the multi-person track the F0 review gate still suspends; "
            "see f0-evaluation-foundation-blocker-closure.md."
        ),
    ),
    BaselineRegistryEntry(
        name="O-STaR faithful reproduction",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="OAM-PHM §9.4 rule 2 requires independently tuned w_hit/w_miss/gamma.",
    ),
    BaselineRegistryEntry(
        name="O-STaR + independently retuned parameters",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Depends on the faithful reproduction above.",
    ),
    BaselineRegistryEntry(
        name="O-STaR + stronger but matched perception",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Requires the B1 real-perception track.",
    ),
    BaselineRegistryEntry(
        name="STREAK-style continual relocation model",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Continual relocation learning under household context drift.",
    ),
    BaselineRegistryEntry(
        name="full OAM-PHM",
        status=BaselineStatus.GATED_BY_REVIEW,
        note="Requires WP2-WP6; the review gate suspends WP3 and WP5.",
    ),
    BaselineRegistryEntry(
        name="oracle identity / actor / event / location upper bounds",
        status=BaselineStatus.GATED_BY_REVIEW,
        note="Per-dimension oracle tracks are still an open S3-1/F0 deliverable.",
    ),
)


def registry_status_counts() -> dict[BaselineStatus, int]:
    return dict(Counter(entry.status for entry in SECTION_9_1_REGISTRY))


def score_baseline(
    baseline: LocationBeliefBaseline,
    run: SymbolicSimulationResult,
    queries: tuple[LocationQuery, ...],
    truth_locations: tuple[UUID, ...],
) -> BaselineScore:
    """Score one baseline. ``truth_locations`` is evaluator-side only.

    The baseline never receives ``truth_locations``; it only ever sees ``run``.
    """

    if len(queries) != len(truth_locations):
        raise ValueError("each query requires exactly one truth location")
    if not queries:
        return BaselineScore(
            baseline_version=baseline.baseline_version,
            top1_accuracy=None,
            mean_negative_log_likelihood=None,
            sample_count=0,
        )
    hits = 0
    total_negative_log_likelihood = 0.0
    for query, truth_location_id in zip(queries, truth_locations, strict=True):
        prediction = baseline.predict(run, query)
        if prediction.baseline_version != baseline.baseline_version:
            raise ValueError("baseline returned a prediction under a different version")
        if prediction.top1_location_id == truth_location_id:
            hits += 1
        probability = prediction.probability_of(truth_location_id)
        if probability <= 0.0:
            raise ValueError(
                "baseline assigned zero probability to a truth location; "
                "smoothing must keep every candidate reachable"
            )
        total_negative_log_likelihood -= log(probability)
    return BaselineScore(
        baseline_version=baseline.baseline_version,
        top1_accuracy=hits / len(queries),
        mean_negative_log_likelihood=total_negative_log_likelihood / len(queries),
        sample_count=len(queries),
    )


def compare_baselines(
    baselines: tuple[LocationBeliefBaseline, ...],
    run: SymbolicSimulationResult,
    queries: tuple[LocationQuery, ...],
    truth_locations: tuple[UUID, ...],
) -> tuple[BaselineScore, ...]:
    """Score every baseline on identical inputs (`§9.4` rules 1 and 6)."""

    versions = [baseline.baseline_version for baseline in baselines]
    if len(versions) != len(set(versions)):
        raise ValueError("baseline versions must be unique within one comparison")
    return tuple(score_baseline(baseline, run, queries, truth_locations) for baseline in baselines)


def default_baselines() -> tuple[LocationBeliefBaseline, ...]:
    """The `§9.1` entries that are runnable under the current review gate."""

    return (
        LastSeenLocationBaseline(),
        HouseholdFrequencyPriorBaseline(),
        MarkovTransitionBaseline(),
    )


def experimental_baselines() -> tuple[LocationBeliefBaseline, ...]:
    """Research-only baselines that are not part of the mandatory `§9.1` floor."""

    return (RLSDecayedFrequencyBaseline(),)
