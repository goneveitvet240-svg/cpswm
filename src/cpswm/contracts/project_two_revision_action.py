"""Immutable audit contracts for Project Two revision-to-next-action causality."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel, Probability


class ProjectOneRequestApplicationStatus(StrEnum):
    """Exhaustive state of one Project Two -> Project One request attempt."""

    APPLIED = "applied"
    DEFERRED_DUE_TO_QUARANTINE = "deferred_due_to_quarantine"
    REJECTED = "rejected"
    REPLAY_NOOP = "replay_noop"


class RevisionActionOperator(StrEnum):
    CHEH_HYPOTHESIS_SUPPORT = "cheh_hypothesis_support"
    PCHMP_REPROPAGATION = "pchmp_repropagation"
    ORRER_REVISION = "orrer_revision"
    PROJECT_ONE_REQUEST_GENERATION = "project_one_request_generation"
    QUARANTINE_HANDOFF = "quarantine_handoff"
    DIRICHLET_RLS_APPLICATION = "dirichlet_rls_application"
    CCRR_REGIME_DECISION = "ccrr_regime_decision"
    PLANNER_BELIEF_READ = "planner_belief_read"
    UTILITY_ACTION_SELECTION = "utility_action_selection"


class ProbabilityMass(ContractModel):
    key: str = Field(min_length=1)
    probability: Probability


class UUIDProbabilityMass(ContractModel):
    key: UUID
    probability: Probability


class ActionProbability(ContractModel):
    action: str = Field(min_length=1)
    location_id: UUID | None = None
    probability: Probability


class StatisticDelta(ContractModel):
    statistic: str = Field(min_length=1)
    before: float
    after: float
    delta: float

    @model_validator(mode="after")
    def _consistent(self) -> StatisticDelta:
        if abs((self.after - self.before) - self.delta) > 1e-9:
            raise ValueError("statistic delta must equal after - before")
        return self


class ProjectOneStatRequestTrace(ContractModel):
    kind: str = Field(min_length=1)
    superseded_revision_id: UUID
    corrected_revision_id: UUID
    event_hypothesis_id: UUID
    owner_key: str = Field(min_length=1)
    object_instance_id: UUID
    location_id: UUID
    owner_mass_before: Probability
    owner_mass_after: Probability
    owner_mass_delta: float
    source_feedback_record_id: UUID


class ProjectOneRequestApplicationReceipt(ContractModel):
    receipt_id: UUID
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ProjectOneRequestApplicationStatus
    superseded_revision_id: UUID
    corrected_revision_id: UUID
    source_feedback_record_id: UUID
    evidence_source_record_ids: tuple[UUID, ...]
    attempt_number: int = Field(ge=1)
    old_belief_snapshot_id: UUID
    new_belief_snapshot_id: UUID
    dirichlet_deltas: tuple[StatisticDelta, ...] = ()
    rls_deltas: tuple[StatisticDelta, ...] = ()
    hybrid_rgrc_deltas: tuple[StatisticDelta, ...] = ()
    ccrr_decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class OperatorDiagnostic(ContractModel):
    operator: RevisionActionOperator
    executed: bool
    changed_state: bool
    detail: str = Field(min_length=1)


class ProjectTwoRevisionActionTrace(ContractModel):
    """One source-feedback-to-next-action proof, frozen for audit and scoring."""

    feedback_record_id: UUID
    evidence_source_record_ids: tuple[UUID, ...]
    superseded_revision_id: UUID
    corrected_revision_id: UUID
    hypothesis_posterior_before: tuple[UUIDProbabilityMass, ...]
    hypothesis_posterior_after: tuple[UUIDProbabilityMass, ...]
    actor_posterior_before: tuple[ProbabilityMass, ...]
    actor_posterior_after: tuple[ProbabilityMass, ...]
    known_mechanism_actor_mass_before: tuple[ProbabilityMass, ...]
    known_mechanism_actor_mass_after: tuple[ProbabilityMass, ...]
    mechanism_posterior_before: tuple[ProbabilityMass, ...]
    mechanism_posterior_after: tuple[ProbabilityMass, ...]
    role_posterior_before: tuple[ProbabilityMass, ...]
    role_posterior_after: tuple[ProbabilityMass, ...]
    location_posterior_before: tuple[ProbabilityMass, ...]
    location_posterior_after: tuple[ProbabilityMass, ...]
    unknown_actor_before: Probability
    unknown_actor_after: Probability
    unknown_mechanism_before: Probability
    unknown_mechanism_after: Probability
    unresolved_before: Probability
    unresolved_after: Probability
    unknown_mechanism_actor_mass_before: tuple[ProbabilityMass, ...]
    unknown_mechanism_actor_mass_after: tuple[ProbabilityMass, ...]
    owner_mass_before: Probability
    owner_mass_after: Probability
    project_one_request: ProjectOneStatRequestTrace | None = None
    request_application_status: ProjectOneRequestApplicationStatus | None = None
    application_receipt_id: UUID | None = None
    dirichlet_deltas: tuple[StatisticDelta, ...] = ()
    rls_deltas: tuple[StatisticDelta, ...] = ()
    hybrid_rgrc_deltas: tuple[StatisticDelta, ...] = ()
    ccrr_decision: str = "not_requested"
    old_belief_snapshot_id: UUID
    new_belief_snapshot_id: UUID
    planner_read_snapshot_id: UUID | None = None
    planner_prediction_index: int | None = Field(default=None, ge=0)
    next_action_distribution: tuple[ActionProbability, ...] = ()
    evaluator_utility: float | None = None
    evaluator_regret: float | None = None
    attempted_location_id: UUID | None = None
    observed_destination_location_id: UUID | None = None
    confirmed_location_evidence_id: UUID | None = None
    operator_diagnostics: tuple[OperatorDiagnostic, ...] = ()


__all__ = [
    "ActionProbability",
    "OperatorDiagnostic",
    "ProbabilityMass",
    "ProjectOneRequestApplicationReceipt",
    "ProjectOneRequestApplicationStatus",
    "ProjectOneStatRequestTrace",
    "ProjectTwoRevisionActionTrace",
    "RevisionActionOperator",
    "StatisticDelta",
    "UUIDProbabilityMass",
]
