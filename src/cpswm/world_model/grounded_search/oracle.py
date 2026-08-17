"""M29-L0 oracle providers for the direction-three complete decision loop.

These providers deliberately live outside the deployed world-model code path.
They expose deterministic ground-truth-backed observations through the same
robot-visible contracts used by later controlled-noise and real adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose
from uuid import UUID

from cpswm.contracts.grounded_search import (
    ActionOutcomeLikelihoodModel,
    CompiledSemanticQuery,
    ExecutionFeedbackRecord,
    GroundedObjectCandidate,
    GroundedSearchResult,
    JointCandidateEvidence,
    ObservationActionCandidate,
    RobotActionType,
    VerificationObservation,
)

from .adapters import GroundedTaskExecution


class OracleSemanticQueryCompiler:
    """Return a frozen oracle parse for one utterance."""

    def __init__(self, query: CompiledSemanticQuery) -> None:
        self._query = query

    def compile(self, utterance: str) -> CompiledSemanticQuery:
        if utterance != self._query.utterance:
            raise LookupError("oracle compiler has no truth parse for this utterance")
        return self._query


class OracleGroundedCandidateRetriever:
    """Return the complete frozen candidate support, including unknown."""

    def __init__(self, candidates: Sequence[JointCandidateEvidence]) -> None:
        self._candidates = tuple(candidates)

    def retrieve(self, query: CompiledSemanticQuery) -> Sequence[JointCandidateEvidence]:
        del query
        return self._candidates


class OracleObservationActionProvider:
    """Offer unused oracle actions without encoding a fixed selection order."""

    def __init__(self, actions: Sequence[ObservationActionCandidate]) -> None:
        self._actions = tuple(actions)
        self._consumed: set[UUID] = set()

    def propose(self, belief: GroundedSearchResult) -> Sequence[ObservationActionCandidate]:
        del belief
        return tuple(action for action in self._actions if action.action_id not in self._consumed)

    def mark_consumed(self, action_id: UUID) -> None:
        self._consumed.add(action_id)


class OracleVerificationObservationProvider:
    """Reveal the configured robot-visible outcome of a selected oracle action."""

    def __init__(self, observations: Mapping[UUID, VerificationObservation]) -> None:
        self._observations = dict(observations)

    def observe(
        self,
        action: ObservationActionCandidate,
        belief: GroundedSearchResult,
    ) -> VerificationObservation:
        observation = self._observations[action.action_id]
        if observation.action_id != action.action_id:
            raise ValueError("oracle observation action binding is inconsistent")
        if observation.observation_likelihood_model_id != action.observation_likelihood_model_id:
            raise ValueError("planned and realized observation models must match")
        if observation.calibration_domain != action.calibration_domain:
            raise ValueError("planned and realized calibration domains must match")
        if set(observation.candidate_likelihoods) != set(belief.posterior_by_candidate_id):
            raise ValueError("oracle observation must cover the current hypothesis set")
        planned_likelihoods = action.outcome_likelihoods.get(observation.outcome_label)
        if planned_likelihoods is None:
            raise ValueError("realized outcome was absent from the planned observation model")
        if any(
            not isclose(
                planned_likelihoods[candidate_id],
                likelihood,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for candidate_id, likelihood in observation.candidate_likelihoods.items()
        ):
            raise ValueError("realized likelihoods differ from the planned observation model")
        return observation


class OracleGroundedTaskExecutor:
    """Return a frozen feedback trace for the selected object instance."""

    def __init__(
        self,
        executions_by_candidate_id: Mapping[UUID, GroundedTaskExecution],
    ) -> None:
        self._executions = dict(executions_by_candidate_id)

    def execute(self, target: GroundedObjectCandidate) -> GroundedTaskExecution:
        return self._executions[target.candidate_id]


class OracleActionOutcomeModelProvider:
    """Return frozen action-outcome models for oracle feedback projection."""

    def __init__(self, models: Mapping[RobotActionType, ActionOutcomeLikelihoodModel]) -> None:
        self._models = dict(models)

    def model_for(self, feedback: ExecutionFeedbackRecord) -> ActionOutcomeLikelihoodModel:
        return self._models[feedback.action_type]
