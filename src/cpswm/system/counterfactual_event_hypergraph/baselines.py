"""Direct CHEH baselines used to test revision and mutual exclusion claims."""

from __future__ import annotations

from math import isclose
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import ObservationDetectionResult
from cpswm.contracts.base import ContractModel, Probability

from .contracts import EventChainHypothesis, HiddenEventStep
from .engine import CounterfactualEventHypergraphEngine


class Top1EventGraphPrediction(ContractModel):
    """A committed event chain with no alternatives or later revision state."""

    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    source_record_ids: tuple[UUID, ...] = Field(min_length=2)
    model_version: str = Field(min_length=1)


class IndependentEventCandidate(ContractModel):
    """One independently scored chain; scores need not be mutually exclusive."""

    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    independent_confidence: Probability
    source_record_ids: tuple[UUID, ...] = Field(min_length=2)


class IndependentEventCandidatePrediction(ContractModel):
    candidates: tuple[IndependentEventCandidate, ...] = Field(min_length=2)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_independence(self) -> IndependentEventCandidatePrediction:
        total = sum(item.independent_confidence for item in self.candidates)
        if isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(
                "independent baseline confidences must not masquerade as a normalized posterior"
            )
        return self


class Top1EventGraphBaseline:
    """Commit immediately to the MAP chain and discard all alternatives."""

    model_version = "top1-event-graph@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_prior: dict[str, float],
    ) -> Top1EventGraphPrediction:
        history = CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior=actor_prior,
            unresolved_probability=0.0,
            handoff_fraction=0.0,
        )
        selected = history.latest.map_hypothesis
        assert selected is not None
        return Top1EventGraphPrediction(
            responsible_actor_key=selected.responsible_actor_key,
            steps=selected.steps,
            source_record_ids=selected.source_record_ids,
            model_version=self.model_version,
        )


class IndependentEventCandidateBaseline:
    """Keep chains independently but omit exclusivity, revision, and retraction."""

    model_version = "independent-event-candidates@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_confidence: dict[str, float],
    ) -> IndependentEventCandidatePrediction:
        actor_count = len(actor_confidence)
        actor_prior = {actor: 1.0 / actor_count for actor in actor_confidence}
        history = CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior=actor_prior,
            unresolved_probability=0.0,
            handoff_fraction=0.0,
        )
        by_actor: dict[str, EventChainHypothesis] = {
            item.responsible_actor_key: item for item in history.latest.hypotheses
        }
        # Each candidate is scored as a separate binary plausibility.  A 0.2
        # background floor makes the intentional non-normalization explicit.
        candidates = tuple(
            IndependentEventCandidate(
                responsible_actor_key=actor,
                steps=by_actor[actor].steps,
                independent_confidence=0.2 + 0.8 * confidence,
                source_record_ids=by_actor[actor].source_record_ids,
            )
            for actor, confidence in sorted(actor_confidence.items())
        )
        return IndependentEventCandidatePrediction(
            candidates=candidates,
            model_version=self.model_version,
        )
