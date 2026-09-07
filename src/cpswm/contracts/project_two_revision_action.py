"""Immutable audit contracts for Project Two revision-to-next-action causality."""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import Any
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


class ActionKind(StrEnum):
    """Closed action vocabulary used by the audited planner distribution."""

    PUT_BACK = "put_back"
    SEARCH = "search"
    DELIVER = "deliver"
    ASK = "ask"


class ProbabilityMass(ContractModel):
    key: str = Field(min_length=1)
    probability: Probability


class UUIDProbabilityMass(ContractModel):
    key: UUID
    probability: Probability


class ActionProbability(ContractModel):
    action: ActionKind
    location_id: UUID | None = None
    probability: Probability

    @model_validator(mode="after")
    def _location_semantics(self) -> ActionProbability:
        if self.action in {ActionKind.PUT_BACK, ActionKind.SEARCH, ActionKind.DELIVER} and (
            self.location_id is None
        ):
            raise ValueError(f"{self.action} action requires a location_id")
        if self.action is ActionKind.ASK and self.location_id is not None:
            raise ValueError("ask action cannot name a location_id")
        return self


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

    @model_validator(mode="after")
    def _owner_delta_is_derived(self) -> ProjectOneStatRequestTrace:
        if not isclose(
            self.owner_mass_delta,
            self.owner_mass_after - self.owner_mass_before,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("owner_mass_delta must equal owner_mass_after - owner_mass_before")
        return self


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

    @model_validator(mode="after")
    def _state_change_requires_execution(self) -> OperatorDiagnostic:
        if self.changed_state and not self.executed:
            raise ValueError("operator cannot change state when it was not executed")
        return self


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
    owner_key: str = Field(min_length=1)
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
    planner_prediction_count: int | None = Field(default=None, ge=1)
    next_action_distribution: tuple[ActionProbability, ...] = ()
    evaluator_utility: float | None = None
    evaluator_regret: float | None = None
    evaluator_prediction_count: int | None = Field(default=None, ge=1)
    evaluator_true_location_id: UUID | None = None
    evaluator_true_owner_habit_location_id: UUID | None = None
    evaluator_registered_location_count: int | None = Field(default=None, ge=1)
    attempted_location_id: UUID | None = None
    observed_destination_location_id: UUID | None = None
    confirmed_location_evidence_id: UUID | None = None
    operator_diagnostics: tuple[OperatorDiagnostic, ...] = ()

    def validated_update(self, **update: Any) -> ProjectTwoRevisionActionTrace:
        """Return an immutable update with every cross-field invariant rechecked.

        Pydantic's ``model_copy(update=...)`` deliberately skips validation.  A
        trace is an audit artifact, so runtime evolution must use this method
        instead of creating a temporarily or permanently contradictory object.
        """

        values = self.model_dump(mode="python")
        values.update(update)
        return type(self).model_validate(values)

    @staticmethod
    def _require_unique_keys(name: str, items: tuple[ProbabilityMass, ...]) -> None:
        keys = [item.key for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{name} contains duplicate keys")

    @staticmethod
    def _require_unit_mass(name: str, total: float) -> None:
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError(f"{name} probability mass must sum to one")

    @model_validator(mode="after")
    def _causal_and_probability_invariants(self) -> ProjectTwoRevisionActionTrace:
        if self.feedback_record_id not in self.evidence_source_record_ids:
            raise ValueError("feedback_record_id must be part of the evidence source chain")
        if len(self.evidence_source_record_ids) != len(set(self.evidence_source_record_ids)):
            raise ValueError("evidence source chain contains duplicate record ids")

        named_masses = {
            "actor_posterior_before": self.actor_posterior_before,
            "actor_posterior_after": self.actor_posterior_after,
            "known_mechanism_actor_mass_before": self.known_mechanism_actor_mass_before,
            "known_mechanism_actor_mass_after": self.known_mechanism_actor_mass_after,
            "mechanism_posterior_before": self.mechanism_posterior_before,
            "mechanism_posterior_after": self.mechanism_posterior_after,
            "role_posterior_before": self.role_posterior_before,
            "role_posterior_after": self.role_posterior_after,
            "location_posterior_before": self.location_posterior_before,
            "location_posterior_after": self.location_posterior_after,
            "unknown_mechanism_actor_mass_before": self.unknown_mechanism_actor_mass_before,
            "unknown_mechanism_actor_mass_after": self.unknown_mechanism_actor_mass_after,
        }
        for name, items in named_masses.items():
            self._require_unique_keys(name, items)
        for name, uuid_items in {
            "hypothesis_posterior_before": self.hypothesis_posterior_before,
            "hypothesis_posterior_after": self.hypothesis_posterior_after,
        }.items():
            keys = [item.key for item in uuid_items]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} contains duplicate keys")

        before_actor = dict((item.key, item.probability) for item in self.actor_posterior_before)
        after_actor = dict((item.key, item.probability) for item in self.actor_posterior_after)
        if not isclose(
            before_actor.get("unknown_actor", 0.0),
            self.unknown_actor_before,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ValueError("unknown_actor_before disagrees with actor posterior")
        if not isclose(
            after_actor.get("unknown_actor", 0.0),
            self.unknown_actor_after,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ValueError("unknown_actor_after disagrees with actor posterior")

        self._require_unit_mass("actor_posterior_before", sum(before_actor.values()))
        self._require_unit_mass("actor_posterior_after", sum(after_actor.values()))
        if self.owner_key not in before_actor or self.owner_key not in after_actor:
            raise ValueError("owner_key must exist in both actor posteriors")
        if not isclose(
            before_actor[self.owner_key], self.owner_mass_before, rel_tol=0.0, abs_tol=1e-8
        ):
            raise ValueError("owner_mass_before disagrees with owner actor posterior")
        if not isclose(
            after_actor[self.owner_key], self.owner_mass_after, rel_tol=0.0, abs_tol=1e-8
        ):
            raise ValueError("owner_mass_after disagrees with owner actor posterior")
        self._require_unit_mass(
            "location_posterior_before",
            sum(item.probability for item in self.location_posterior_before),
        )
        self._require_unit_mass(
            "location_posterior_after",
            sum(item.probability for item in self.location_posterior_after),
        )
        for suffix in ("before", "after"):
            unresolved = getattr(self, f"unresolved_{suffix}")
            unknown_mechanism = getattr(self, f"unknown_mechanism_{suffix}")
            hypothesis = getattr(self, f"hypothesis_posterior_{suffix}")
            mechanism = getattr(self, f"mechanism_posterior_{suffix}")
            roles = getattr(self, f"role_posterior_{suffix}")
            known_actor = getattr(self, f"known_mechanism_actor_mass_{suffix}")
            unknown_actor = getattr(self, f"unknown_mechanism_actor_mass_{suffix}")
            mechanism_by_key = {item.key: item.probability for item in mechanism}
            if not isclose(
                mechanism_by_key.get("unknown_mechanism", 0.0),
                unknown_mechanism,
                rel_tol=0.0,
                abs_tol=1e-8,
            ):
                raise ValueError(f"unknown_mechanism_{suffix} disagrees with mechanism posterior")
            self._require_unit_mass(
                f"hypothesis decomposition {suffix}",
                sum(item.probability for item in hypothesis) + unknown_mechanism + unresolved,
            )
            self._require_unit_mass(
                f"mechanism decomposition {suffix}",
                sum(item.probability for item in mechanism) + unresolved,
            )
            self._require_unit_mass(
                f"role decomposition {suffix}",
                sum(item.probability for item in roles) + unknown_mechanism + unresolved,
            )
            self._require_unit_mass(
                f"actor mechanism decomposition {suffix}",
                sum(item.probability for item in known_actor)
                + sum(item.probability for item in unknown_actor)
                + unresolved,
            )

        request = self.project_one_request
        has_application_fields = any(
            (
                self.request_application_status is not None,
                self.application_receipt_id is not None,
                bool(self.dirichlet_deltas),
                bool(self.rls_deltas),
                bool(self.hybrid_rgrc_deltas),
                self.ccrr_decision != "not_requested",
            )
        )
        if request is None and has_application_fields:
            raise ValueError("application result cannot exist without a Project One request")
        if request is not None:
            if request.source_feedback_record_id != self.feedback_record_id:
                raise ValueError("Project One request is bound to another feedback record")
            if request.superseded_revision_id != self.superseded_revision_id:
                raise ValueError("Project One request superseded revision mismatch")
            if request.corrected_revision_id != self.corrected_revision_id:
                raise ValueError("Project One request corrected revision mismatch")
            if request.owner_key != self.owner_key:
                raise ValueError("Project One request owner mismatch")
            if not isclose(
                request.owner_mass_before,
                self.owner_mass_before,
                rel_tol=0.0,
                abs_tol=1e-8,
            ) or not isclose(
                request.owner_mass_after,
                self.owner_mass_after,
                rel_tol=0.0,
                abs_tol=1e-8,
            ):
                raise ValueError("Project One request owner masses disagree with trace")
        if self.request_application_status is None:
            if self.application_receipt_id is not None:
                raise ValueError("application receipt cannot exist without application status")
            if self.dirichlet_deltas or self.rls_deltas or self.hybrid_rgrc_deltas:
                raise ValueError("statistic deltas cannot exist without application status")
            if self.ccrr_decision != "not_requested":
                raise ValueError("CCRR decision cannot exist without application status")
        elif self.application_receipt_id is None:
            raise ValueError("application status requires an application receipt")

        planner_fields = (
            self.planner_read_snapshot_id,
            self.planner_prediction_index,
            self.planner_prediction_count,
            self.next_action_distribution or None,
        )
        if any(item is not None for item in planner_fields) and not all(
            item is not None for item in planner_fields
        ):
            raise ValueError(
                "planner read, index, count, and action distribution must be all present or absent"
            )
        if self.planner_read_snapshot_id is not None:
            if self.planner_read_snapshot_id != self.new_belief_snapshot_id:
                raise ValueError("planner must read the corrected new belief snapshot")
            action_keys = [
                (item.action, item.location_id) for item in self.next_action_distribution
            ]
            if len(action_keys) != len(set(action_keys)):
                raise ValueError("next action distribution contains duplicate action keys")
            self._require_unit_mass(
                "next_action_distribution",
                sum(item.probability for item in self.next_action_distribution),
            )
            assert self.planner_prediction_index is not None
            assert self.planner_prediction_count is not None
            if self.planner_prediction_index != self.planner_prediction_count - 1:
                raise ValueError("planner prediction index must bind the emitted prediction count")

        if (self.evaluator_utility is None) != (self.evaluator_regret is None):
            raise ValueError("evaluator utility and regret must be recorded together")
        if self.evaluator_regret is not None and self.evaluator_regret < 0.0:
            raise ValueError("evaluator regret must be non-negative")
        evaluator_context = (
            self.evaluator_prediction_count,
            self.evaluator_true_location_id,
            self.evaluator_true_owner_habit_location_id,
            self.evaluator_registered_location_count,
        )
        if self.evaluator_utility is None:
            if any(item is not None for item in evaluator_context):
                raise ValueError("evaluator derivation context cannot exist before scoring")
        else:
            if any(item is None for item in evaluator_context):
                raise ValueError("evaluator scoring requires complete derivation context")
            if self.planner_prediction_index is None or not self.next_action_distribution:
                raise ValueError("evaluator scoring requires a planner action distribution")
            assert self.evaluator_prediction_count is not None
            assert self.evaluator_true_location_id is not None
            assert self.evaluator_true_owner_habit_location_id is not None
            assert self.evaluator_registered_location_count is not None
            assert self.evaluator_regret is not None
            assert self.evaluator_utility is not None
            if self.planner_prediction_index >= self.evaluator_prediction_count:
                raise ValueError(
                    "planner prediction index exceeds the evaluated prediction sequence"
                )
            put_candidates = tuple(
                item for item in self.next_action_distribution if item.action is ActionKind.PUT_BACK
            )
            search_candidates = tuple(
                item for item in self.next_action_distribution if item.action is ActionKind.SEARCH
            )
            if not put_candidates or not search_candidates:
                raise ValueError("evaluator scoring requires put-back and search action support")
            selected_put = max(
                enumerate(put_candidates),
                key=lambda pair: (pair[1].probability, -pair[0]),
            )[1].location_id
            ranked_search = tuple(
                item.location_id
                for _, item in sorted(
                    enumerate(search_candidates),
                    key=lambda pair: (-pair[1].probability, pair[0]),
                )
            )
            try:
                inspected = ranked_search.index(self.evaluator_true_location_id) + 1
                search_regret = (
                    0.0
                    if self.evaluator_registered_location_count == 1
                    else (inspected - 1) / (self.evaluator_registered_location_count - 1)
                )
            except ValueError:
                search_regret = 1.0
            derived_regret = (
                float(selected_put != self.evaluator_true_owner_habit_location_id) + search_regret
            )
            if not isclose(
                self.evaluator_regret, derived_regret, rel_tol=0.0, abs_tol=1e-9
            ) or not isclose(
                self.evaluator_utility, 2.0 - derived_regret, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(
                    "evaluator utility/regret are not derived from the action distribution"
                )
        if self.confirmed_location_evidence_id is not None and (
            self.observed_destination_location_id is None
        ):
            raise ValueError("confirmed location evidence requires an observed destination")

        operators = [item.operator for item in self.operator_diagnostics]
        if len(operators) != len(set(operators)):
            raise ValueError("operator diagnostics contain duplicate operators")
        required = {
            RevisionActionOperator.CHEH_HYPOTHESIS_SUPPORT,
            RevisionActionOperator.PCHMP_REPROPAGATION,
            RevisionActionOperator.ORRER_REVISION,
            RevisionActionOperator.PROJECT_ONE_REQUEST_GENERATION,
            RevisionActionOperator.QUARANTINE_HANDOFF,
            RevisionActionOperator.DIRICHLET_RLS_APPLICATION,
            RevisionActionOperator.CCRR_REGIME_DECISION,
        }
        if not required <= set(operators):
            raise ValueError("operator diagnostics omit a required revision operator")
        planner_diagnostics = operators.count(RevisionActionOperator.PLANNER_BELIEF_READ)
        if planner_diagnostics != int(self.planner_read_snapshot_id is not None):
            raise ValueError("planner diagnostic must exactly match the planner read edge")
        utility_diagnostics = operators.count(RevisionActionOperator.UTILITY_ACTION_SELECTION)
        if utility_diagnostics != int(self.evaluator_utility is not None):
            raise ValueError("utility diagnostic must exactly match evaluator scoring")
        return self


__all__ = [
    "ActionKind",
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
