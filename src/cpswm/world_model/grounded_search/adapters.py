"""Replaceable real-system adapters for direction structure three.

Concrete integrations may use an LLM, open-vocabulary perception, VIO/SLAM,
ROS 2 navigation, MPC/MPPI, and tactile hardware. These protocols keep those
products outside the world-model semantics and make symbolic/offline/real
implementations interchangeable.
"""

from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import ObservationOpportunityRecord
from cpswm.contracts.base import ContractModel, EntityRef, EntityType
from cpswm.contracts.grounded_search import (
    ActionOutcomeLikelihoodModel,
    CompiledSemanticQuery,
    ExecutionFeedbackRecord,
    GroundedObjectCandidate,
    GroundedSearchResult,
    IdentityViewEvidence,
    JointCandidateEvidence,
    ObservationActionCandidate,
    RobotActionType,
    VerificationObservation,
)


GROUNDED_SEARCH_SCHEMA_VERSION = "0.1.0"


class GroundedTaskExecution(ContractModel):
    """One executor-returned action and the evidence it actually produced.

    The package is intentionally stricter than a standalone M27 feedback
    record.  It makes the executor state the selected target, realized action,
    target location, and concrete observation opportunities together, so the
    pipeline can reject invented feedback UUIDs before any canonical write.
    """

    selected_target_candidate_id: UUID
    target_entity: EntityRef
    target_location_id: UUID
    executed_action_id: UUID
    executed_action_type: RobotActionType
    action_outcome_model_version: str | None = Field(default=None, min_length=1)
    action_outcome_calibration_domain: str | None = Field(default=None, min_length=1)
    observation_opportunities: tuple[ObservationOpportunityRecord, ...] = ()
    feedback_records: tuple[ExecutionFeedbackRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_execution_bindings(self) -> GroundedTaskExecution:
        if self.target_entity.entity_type != EntityType.OBJECT_INSTANCE:
            raise ValueError("grounded task execution target must be an object instance")
        model_binding = (
            self.action_outcome_model_version,
            self.action_outcome_calibration_domain,
        )
        if (model_binding[0] is None) != (model_binding[1] is None):
            raise ValueError(
                "action outcome model version and calibration domain must appear together"
            )
        if self.executed_action_type == RobotActionType.SEARCH and any(
            value is None for value in model_binding
        ):
            raise ValueError(
                "search execution requires an outcome model version and calibration domain"
            )

        opportunities = self.observation_opportunities
        opportunity_ids = [item.metadata.record_id for item in opportunities]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("execution observation opportunity IDs must be unique")
        for opportunity in opportunities:
            if opportunity.metadata.schema_name != "cpswm.ObservationOpportunityRecord":
                raise ValueError(
                    "execution observation opportunity schema name is invalid"
                )
            if opportunity.metadata.schema_version != GROUNDED_SEARCH_SCHEMA_VERSION:
                raise ValueError(
                    "execution observation opportunity schema version is invalid"
                )
            if opportunity.metadata.recorded_time != opportunity.opportunity_time:
                raise ValueError(
                    "execution observation opportunity recorded time must match "
                    "opportunity time"
                )
            if opportunity.observation_action_id != self.executed_action_id:
                raise ValueError(
                    "execution observation opportunity must bind the executed action"
                )
            if not opportunity.selected:
                raise ValueError(
                    "execution observation opportunity must represent an executed observation"
                )

        opportunity_id_set = set(opportunity_ids)
        if self.executed_action_type == RobotActionType.SEARCH and not opportunities:
            raise ValueError("search execution requires a real observation opportunity")
        if self.executed_action_type != RobotActionType.SEARCH and opportunities:
            raise ValueError(
                "only search execution may declare observation opportunities"
            )
        referenced_opportunity_ids: set[UUID] = set()
        for feedback in self.feedback_records:
            if feedback.metadata.schema_name != "cpswm.ExecutionFeedbackRecord":
                raise ValueError("execution feedback schema name is invalid")
            if feedback.metadata.schema_version != GROUNDED_SEARCH_SCHEMA_VERSION:
                raise ValueError("execution feedback schema version is invalid")
            if not feedback.valid_time.contains(feedback.metadata.recorded_time):
                raise ValueError(
                    "execution feedback recorded time must fall within valid time"
                )
            if feedback.action_id != self.executed_action_id:
                raise ValueError("execution feedback must bind the executed action ID")
            if feedback.action_type != self.executed_action_type:
                raise ValueError("execution feedback must bind the executed action type")
            if feedback.target_entity is None:
                raise ValueError("execution feedback requires the actual target entity")
            if feedback.target_entity != self.target_entity:
                raise ValueError("execution feedback target must match the executed target")
            if feedback.attempted_location_id is None:
                raise ValueError("execution feedback requires the actual target location")
            if feedback.attempted_location_id != self.target_location_id:
                raise ValueError(
                    "execution feedback location must match the executed target location"
                )
            if feedback.observation_opportunity_id is not None:
                if feedback.observation_opportunity_id not in opportunity_id_set:
                    raise ValueError(
                        "execution feedback references an undeclared observation opportunity"
                    )
                referenced_opportunity_ids.add(feedback.observation_opportunity_id)
            if (
                feedback.action_type == RobotActionType.SEARCH
                and feedback.observation_opportunity_id is None
            ):
                raise ValueError(
                    "search feedback requires an execution observation opportunity"
                )
            if (
                feedback.action_type != RobotActionType.SEARCH
                and feedback.observation_opportunity_id is not None
            ):
                raise ValueError(
                    "only search feedback may reference an observation opportunity"
                )

        if referenced_opportunity_ids != opportunity_id_set:
            raise ValueError(
                "every execution observation opportunity must be referenced by feedback"
            )

        records = (*opportunities, *self.feedback_records)
        households = {item.metadata.household_id for item in records}
        sessions = {item.metadata.session_id for item in records}
        traces = {item.metadata.trace_id for item in records}
        if len(households) != 1:
            raise ValueError("one grounded task execution cannot mix households")
        if len(sessions) != 1:
            raise ValueError("one grounded task execution cannot mix sessions")
        if len(traces) != 1:
            raise ValueError("one grounded task execution cannot mix traces")

        opportunity_by_id = {
            item.metadata.record_id: item for item in opportunities
        }
        for feedback in self.feedback_records:
            opportunity_id = feedback.observation_opportunity_id
            if opportunity_id is None:
                continue
            opportunity_time = opportunity_by_id[opportunity_id].opportunity_time
            if feedback.metadata.recorded_time < opportunity_time:
                raise ValueError(
                    "execution feedback cannot precede its observation opportunity"
                )
            if not feedback.valid_time.contains(opportunity_time):
                raise ValueError(
                    "execution observation opportunity must fall within feedback valid time"
                )
        return self


class SemanticQueryCompiler(Protocol):
    def compile(self, utterance: str) -> CompiledSemanticQuery: ...


class GroundedCandidateRetriever(Protocol):
    def retrieve(
        self, query: CompiledSemanticQuery
    ) -> Sequence[JointCandidateEvidence]: ...


class IdentityEvidenceProvider(Protocol):
    def observe(self, action: ObservationActionCandidate) -> IdentityViewEvidence: ...


class ObservationActionProvider(Protocol):
    def propose(
        self, belief: GroundedSearchResult
    ) -> Sequence[ObservationActionCandidate]: ...


class VerificationObservationProvider(Protocol):
    def observe(
        self,
        action: ObservationActionCandidate,
        belief: GroundedSearchResult,
    ) -> VerificationObservation: ...


class GroundedTaskExecutor(Protocol):
    def execute(
        self, target: GroundedObjectCandidate
    ) -> GroundedTaskExecution: ...


class ActionOutcomeModelProvider(Protocol):
    def model_for(
        self, feedback: ExecutionFeedbackRecord
    ) -> ActionOutcomeLikelihoodModel: ...
