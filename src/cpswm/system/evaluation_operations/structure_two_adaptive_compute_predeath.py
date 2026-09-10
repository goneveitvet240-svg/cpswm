"""Fail-closed pre-death test for adaptive Structure-Two computation.

This module deliberately separates three claims:

* a frozen library of legal seven-operator compute paths exists;
* a counterfactual shadow matrix can reveal hindsight routing headroom; and
* a deployable router is scientifically supported.

Only the first claim is established by the checked-in v0.1 protocol.  The
second requires a source-bound production-runtime executor and complete
branching evidence.  The third additionally requires a later observable-only
policy gate.  No caller-provided hash or synthetic fixture can promote either
of those claims.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import random
import textwrap
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from statistics import mean
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, NamedTuple, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, Probability
from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    DEFAULT_CONFIG as ACTION_UTILITY_GATE_CONFIG,
)
from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    run_action_utility_construct_gate,
)
from cpswm.system.evaluation_operations.structure_two_runtime_identity_gate import (
    DEFAULT_CONFIG as RUNTIME_IDENTITY_GATE_CONFIG,
)
from cpswm.system.evaluation_operations.structure_two_runtime_identity_gate import (
    run_runtime_identity_gate_audit,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    StructureTwoOperator,
    StructureTwoSelectedMethod,
)
from cpswm.system.evaluation_operations.structure_two_task9_protocol import (
    load_task9_protocol,
)
from cpswm.system.prototype_spine import CorePrototypeSpine
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveExecutionContext,
    AdaptiveRouterFeatures,
    AdaptiveStepResult,
    select_adaptive_path,
)
from cpswm.system.structure_two_execution import (
    ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH,
    ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS,
    LEGACY_CONSUMPTION_GRAPH,
    LEGACY_PLAN_ID,
    REGISTERED_ADAPTIVE_PATH_MODES,
    StructureTwoExecutionPlan,
    StructureTwoExecutionTrace,
    TraceAbortAck,
    TraceCommitAck,
    TraceSink,
    canonical_legacy_ordinary_transition_plan,
    registered_adaptive_execution_plan,
)
from cpswm.system.structure_two_execution import (
    OperatorInvocationReceipt as RuntimeOperatorInvocationReceipt,
)
from cpswm.system.structure_two_production_system import (
    PRODUCTION_OPERATOR_ORDER,
    StructureTwoProductionSystem,
)

SCHEMA_VERSION: Final = "1.0.0"
PROTOCOL_ID: Final = "structure-two-adaptive-computation-pre-death-test@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json"
)
DEFAULT_RUNNER: Final = Path(
    "apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_adaptive_compute_predeath_readiness_v0_1.json"
)
REQUIRED_PATH_IDS: Final = (
    "P0_SAFE_DEFERRED",
    "P1_EVENT_ACTOR_LOCAL",
    "P2_REGIME_RECOVERY_LOCAL",
    "P3_ACTIVE_VERIFY",
    "P4_EVENT_ACTOR_PLUS_REGIME",
    "P5_FULL_EAGER",
)
FULL_EAGER_PATH_ID: Final = "P5_FULL_EAGER"
SAFE_ABSTAIN_PATH_ID: Final = "SAFE_ABSTAIN"
CIAV_FEEDBACK_REPLAY_ORDER: Final = tuple(
    StructureTwoOperator(value)
    for value in (
        "ciav",
        "opceu",
        "orrer_cheh",
        "pchmp",
        "cf_bocpd",
        "ccrr",
        "rgrc",
    )
)
REQUIRED_DEBT_TRIGGERS: Final = frozenset(
    {
        "late_contradictory_evidence",
        "before_long_term_commit",
        "risk_bound_exceeded",
        "debt_expiry",
    }
)
REQUIRED_FLIP_RISK_BLOCKED_TRANSITIONS: Final = frozenset(
    {
        "long_term_memory_write",
        "permanent_attribution_commit",
        "permanent_identity_commit",
        "irreversible_memory_retraction",
    }
)
REQUIRED_PATH_ESCALATION_CONDITIONS: Final = frozenset(
    {
        "invalid_router_input",
        "expired_debt",
        "risk_bound_exceeded",
        "unsafe_or_unauthorized_memory_transition",
        "privacy_policy_violation",
    }
)
CLAIM_BOUNDARY: Final = (
    "This pure D0 evaluator accepts caller-controlled development evidence and cannot establish "
    "or kill hindsight headroom. Hindsight selection uses post-outcome information and is not "
    "deployable. Only a future source-bound production execution may establish the pre-death "
    "result and, if positive, authorize the next observable-information gate. Nothing here "
    "establishes a learned router, production benefit, external validity, scientific superiority, "
    "novelty, or permission to remove any Structure-Two operator or capability."
)


class ReadinessRequirement(NamedTuple):
    gate_key: str
    blocking_reason: str
    next_required_work: str


READINESS_REQUIREMENTS: Final[tuple[ReadinessRequirement, ...]] = (
    ReadinessRequirement(
        "selected_method_operator_inventory_covers_production_registry",
        "selected_method_does_not_retain_complete_seven_operator_scope",
        "restore the complete seven-operator selected-method inventory",
    ),
    ReadinessRequirement(
        "protocol_operator_order_matches_production_dag",
        "protocol_operator_order_differs_from_production_dag",
        "align the registered protocol order with the production dependency DAG",
    ),
    ReadinessRequirement(
        "fresh_typed_action_utility_construct_gate_passed",
        "typed_action_utility_construct_gate_failed",
        "repair and freshly verify the typed SEARCH/PUT_BACK construct gate",
    ),
    ReadinessRequirement(
        "population_seed_split_binding_matches_task9",
        "population_seed_or_split_binding_drifted_from_task9",
        "restore the frozen Task-9 population, seed, and split binding",
    ),
    ReadinessRequirement(
        "task9_remains_definition_only",
        "task9_confirmatory_status_not_sealed_definition_only",
        "restore the sealed Task-9 definition-only status before shadow execution",
    ),
    ReadinessRequirement(
        "production_execution_plan_interface_selected",
        "production_execution_plan_interface_unresolved",
        "select and source-bind the production execution-plan interface",
    ),
    ReadinessRequirement(
        "immutable_execution_plan_contract_source_bound",
        "immutable_execution_plan_contract_not_source_bound",
        "source-bind the immutable execution-plan contract",
    ),
    ReadinessRequirement(
        "trace_sink_contract_source_bound",
        "trace_sink_contract_not_source_bound",
        "source-bind the trace-sink contract",
    ),
    ReadinessRequirement(
        "legacy_no_plan_no_trace_call_shape_preserved",
        "legacy_no_plan_no_trace_call_shape_not_preserved",
        "restore the legacy no-plan/no-trace call shape without claiming behavioral equivalence",
    ),
    ReadinessRequirement(
        "cross_system_trace_state_atomicity_established",
        "cross_system_trace_state_atomicity_not_established",
        "establish durable cross-system atomic commit across runtime state and trace storage",
    ),
    ReadinessRequirement(
        "path_specific_operator_budgets_bound",
        "path_specific_operator_budgets_unbound",
        "project-owner freeze of path-specific operator budgets",
    ),
    ReadinessRequirement(
        "frozen_branch_point_manifest_bound",
        "frozen_branch_point_manifest_unbound",
        "bind a frozen exhaustive branch-point manifest before confirmatory opening",
    ),
    ReadinessRequirement(
        "path_eligibility_policy_bound_to_production_state",
        "production_router_feature_extractor_not_bound",
        "project-owner freeze of each observable router-feature definition, followed by a "
        "runtime-owned source-bound extractor and provenance checks",
    ),
    ReadinessRequirement(
        "debt_replay_verifier_bound_to_production_replay",
        "debt_replay_verifier_not_bound_to_production_replay",
        "bind debt replay and eager-reference reconstruction to production replay",
    ),
    ReadinessRequirement(
        "power_analysis_bound_to_empirical_variance_and_icc",
        "power_analysis_not_bound_to_empirical_variance_and_icc",
        "bind power analysis to pilot variance and household intraclass correlation",
    ),
    ReadinessRequirement(
        "confirmatory_access_custody_bound",
        "confirmatory_access_custody_unbound",
        "establish independently controlled confirmatory access and freeze custody",
    ),
    ReadinessRequirement(
        "exogenous_rng_source_bound_to_production_execution",
        "exogenous_rng_source_not_bound_to_production_execution",
        "bind the exogenous RNG source to production execution",
    ),
    ReadinessRequirement(
        "legal_path_executor_bound_to_production_runtime",
        "legal_path_executor_not_bound_to_production_runtime",
        "project-owner freeze and implementation of path-specific production kernels, complete "
        "CIAV outcome closure, debt-period wrapper-rebinding semantics, the registered P0--P4 "
        "to P5 failure/timeout fallback, and the P5 safe-abstain receipt",
    ),
    ReadinessRequirement(
        "p0_p5_consequential_runtime_identity_established",
        "p0_p5_consequential_runtime_identity_not_established",
        "establish current state-derived selection through distinct P0--P5 execution, action, "
        "and next-state identity",
    ),
    ReadinessRequirement(
        "resource_accountant_bound_to_production_execution",
        "full_adaptive_resource_accounting_not_bound",
        "measure and bind feature extraction and router-selection overhead in addition to "
        "operator elapsed time and the remaining registered resource axes",
    ),
    ReadinessRequirement(
        "long_horizon_loss_bound_to_production_actions",
        "long_horizon_loss_not_bound_to_production_action_consequences",
        "bind long-horizon task-memory-recovery loss to true action consequences",
    ),
)


def evaluate_readiness_requirements(
    gate_results: Mapping[str, bool],
) -> tuple[list[str], list[str]]:
    """Map every current gate to exactly one blocker and repair action.

    The historical Route-C diagnostic is deliberately absent: it describes an
    immutable old execution route and cannot make a future Architecture-A
    P0--P5 shadow lane unreachable.
    """

    expected = {requirement.gate_key for requirement in READINESS_REQUIREMENTS}
    if set(gate_results) != expected:
        missing = sorted(expected - set(gate_results))
        extra = sorted(set(gate_results) - expected)
        raise ValueError(f"readiness gate coverage mismatch: missing={missing}, extra={extra}")
    blockers: list[str] = []
    next_required_work: list[str] = []
    for requirement in READINESS_REQUIREMENTS:
        if not gate_results[requirement.gate_key]:
            blockers.append(requirement.blocking_reason)
            next_required_work.append(requirement.next_required_work)
    return blockers, next_required_work


def _readiness_outcome(
    gate_results: Mapping[str, bool],
) -> tuple[bool, str, list[str], list[str]]:
    blockers, next_required_work = evaluate_readiness_requirements(gate_results)
    ready = not blockers
    status = "READY_FOR_D0_SHADOW_EXECUTION" if ready else "PROTOCOL_IMPLEMENTED_EXECUTION_BLOCKED"
    return ready, status, blockers, next_required_work


SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FiniteNonNegative = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
FinitePositive = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class OperatorExecutionMode(StrEnum):
    MANDATORY_MAINTENANCE_EXECUTED = "mandatory_maintenance_executed"
    REFINEMENT_EXECUTED = "refinement_executed"
    DEFERRED_WITH_VALID_DEBT_CERTIFICATE = "deferred_with_valid_debt_certificate"
    NOT_APPLICABLE_WITH_RECOMPUTED_REASON = "not_applicable_with_recomputed_reason"


EXPECTED_PATH_MODES: Final = {
    "P0_SAFE_DEFERRED": (
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
    ),
    "P1_EVENT_ACTOR_LOCAL": (
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
    ),
    "P2_REGIME_RECOVERY_LOCAL": (
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
    ),
    "P3_ACTIVE_VERIFY": (
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.MANDATORY_MAINTENANCE_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
    ),
    "P4_EVENT_ACTOR_PLUS_REGIME": (
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.REFINEMENT_EXECUTED,
        OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
    ),
    "P5_FULL_EAGER": (OperatorExecutionMode.REFINEMENT_EXECUTED,) * 7,
}


class QualityAxis(StrEnum):
    TASK_LOSS = "task_loss"
    MEMORY_LOSS = "memory_loss"
    RECOVERY_LOSS = "recovery_loss"


class EvidenceSplit(StrEnum):
    VALIDATION = "validation"
    CONFIRMATORY = "confirmatory"


class DebtStatus(StrEnum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"


class PreResolutionAction(StrEnum):
    SAFE_READ_ONLY_QUERY = "safe_read_only_query"
    REQUEST_PHYSICAL_VERIFICATION = "request_physical_verification"
    SAFE_ABSTAIN = "safe_abstain"
    LONG_TERM_MEMORY_WRITE = "long_term_memory_write"
    PERMANENT_ATTRIBUTION_COMMIT = "permanent_attribution_commit"
    PERMANENT_IDENTITY_COMMIT = "permanent_identity_commit"
    IRREVERSIBLE_MEMORY_RETRACTION = "irreversible_memory_retraction"


class MemoryTransitionKind(StrEnum):
    EPHEMERAL_BELIEF_UPDATE = "ephemeral_belief_update"
    DEBT_LEDGER_APPEND = "debt_ledger_append"
    LONG_TERM_MEMORY_WRITE = "long_term_memory_write"
    PERMANENT_ATTRIBUTION_COMMIT = "permanent_attribution_commit"
    PERMANENT_IDENTITY_COMMIT = "permanent_identity_commit"
    IRREVERSIBLE_MEMORY_RETRACTION = "irreversible_memory_retraction"


class ForcedEscalationCause(StrEnum):
    INVALID_ROUTER_INPUT = "invalid_router_input"
    EXPIRED_DEBT = "expired_debt"
    RISK_BOUND_EXCEEDED = "risk_bound_exceeded"
    UNSAFE_OR_UNAUTHORIZED_MEMORY_TRANSITION = "unsafe_or_unauthorized_memory_transition"
    PRIVACY_POLICY_VIOLATION = "privacy_policy_violation"


class ForcedEscalationStage(StrEnum):
    PRE_ROUTE = "PRE_ROUTE"
    MID_SELECTED_PATH = "MID_SELECTED_PATH"


class PreDeathDisposition(StrEnum):
    INVALID_NO_SCIENTIFIC_CONCLUSION = "INVALID_NO_SCIENTIFIC_CONCLUSION"
    KILL_ADAPTIVE_ROUTING_FOR_REGISTERED_LIBRARY = "KILL_ADAPTIVE_ROUTING_FOR_REGISTERED_LIBRARY"
    HINDSIGHT_HEADROOM_PRESENT_OBSERVABLE_GATE_REQUIRED = (
        "HINDSIGHT_HEADROOM_PRESENT_OBSERVABLE_GATE_REQUIRED"
    )
    CALLER_CONTROLLED_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING = (
        "CALLER_CONTROLLED_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING"
    )
    CALLER_CONTROLLED_NO_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING = (
        "CALLER_CONTROLLED_NO_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING"
    )


class ScopePolicy(ContractModel):
    unified_seven_operator_framework_retained: Literal[True]
    operators: tuple[StructureTwoOperator, ...]
    hidden_event_inference_retained: Literal[True]
    multi_actor_reasoning_retained: Literal[True]
    open_world_unknowns_retained: Literal[True]
    reversible_attribution_retained: Literal[True]
    embodied_feedback_loop_retained: Literal[True]
    arbitrary_operator_bitmask_forbidden: Literal[True]


class HardSafetyKernel(ContractModel):
    router_may_grant_long_term_write: Literal[False]
    rgrc_is_only_long_term_write_retract_authority: Literal[True]
    ccrr_promotion_required_before_eligible_write: Literal[True]
    unexecuted_inference_may_not_be_encoded_as_negative_evidence: Literal[True]
    unknown_actor_support_must_be_preserved: Literal[True]
    provenance_and_dependency_checks_always_executed: Literal[True]
    atomic_evidence_bundle_commit_or_retract: Literal[True]
    pending_debt_that_can_flip_attribution_blocks_permanent_write: Literal[True]
    invalid_router_input_action: Literal["SAFE_ABSTAIN_OR_FULL_FALLBACK"]
    expired_debt_action: Literal["MANDATORY_ESCALATION"]
    maximum_safety_violations: Literal[0]
    maximum_unauthorized_long_term_commits: Literal[0]
    maximum_provenance_violations: Literal[0]
    maximum_unresolved_as_negative_events: Literal[0]
    maximum_discarded_required_evidence_events: Literal[0]
    maximum_unauthorized_identity_disclosures: Literal[0]
    maximum_unauthorized_person_data_egress_events: Literal[0]


class RouterFeatureContract(ContractModel):
    pre_path_only: Literal[True]
    latent_truth_forbidden: Literal[True]
    future_feedback_forbidden: Literal[True]
    other_path_outputs_forbidden: Literal[True]
    full_inference_output_as_feature_forbidden: Literal[True]
    feature_source_hashes_required: Literal[True]
    feature_extraction_cost_counted: Literal[True]
    allowed_feature_names: tuple[str, ...]

    @model_validator(mode="after")
    def unique_features(self) -> Self:
        if not self.allowed_feature_names or len(set(self.allowed_feature_names)) != len(
            self.allowed_feature_names
        ):
            raise ValueError("router feature allowlist must be non-empty and unique")
        return self


class OperatorModeSpec(ContractModel):
    operator: StructureTwoOperator
    mode: OperatorExecutionMode
    contract_guard_active: Literal[True]


class LegalPathSpec(ContractModel):
    path_id: str = Field(pattern=r"^P[0-9]+_[A-Z0-9_]+$")
    semantic_purpose: str = Field(min_length=1)
    operator_modes: tuple[OperatorModeSpec, ...]
    feedback_closure_operator_order: tuple[StructureTwoOperator, ...]
    dependency_closure_complete: Literal[True]
    all_seven_operator_receipts_required: Literal[True]
    eligibility_preconditions: tuple[str, ...]
    forced_escalation_conditions: tuple[str, ...]
    forced_escalation_target_by_condition: dict[ForcedEscalationCause, str]
    rgrc_remains_only_long_term_write_authority: Literal[True]
    fallback_path_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def complete_ordered_operator_path(self) -> Self:
        observed = tuple(item.operator.value for item in self.operator_modes)
        if observed != PRODUCTION_OPERATOR_ORDER:
            raise ValueError("legal path must retain the exact production seven-operator order")
        ciav_mode = self.operator_modes[-1].mode
        required_feedback = tuple(
            StructureTwoOperator(value)
            for value in (
                "ciav",
                "opceu",
                "orrer_cheh",
                "pchmp",
                "cf_bocpd",
                "ccrr",
                "rgrc",
            )
        )
        if ciav_mode is OperatorExecutionMode.REFINEMENT_EXECUTED:
            if self.feedback_closure_operator_order != required_feedback:
                raise ValueError("CIAV refinement path must freeze the complete feedback closure")
        elif self.feedback_closure_operator_order:
            raise ValueError("a path without CIAV refinement cannot claim a feedback closure")
        if not self.eligibility_preconditions:
            raise ValueError("each legal path must freeze non-empty eligibility preconditions")
        if not REQUIRED_PATH_ESCALATION_CONDITIONS.issubset(self.forced_escalation_conditions):
            raise ValueError("legal path is missing a mandatory forced-escalation condition")
        if set(self.forced_escalation_target_by_condition) != set(ForcedEscalationCause):
            raise ValueError("legal path must freeze one target for every escalation cause")
        expected_targets = {
            cause: (
                SAFE_ABSTAIN_PATH_ID
                if self.path_id == FULL_EAGER_PATH_ID
                or cause
                in {
                    ForcedEscalationCause.UNSAFE_OR_UNAUTHORIZED_MEMORY_TRANSITION,
                    ForcedEscalationCause.PRIVACY_POLICY_VIOLATION,
                }
                else FULL_EAGER_PATH_ID
            )
            for cause in ForcedEscalationCause
        }
        if self.forced_escalation_target_by_condition != expected_targets:
            raise ValueError("forced-escalation target mapping is not fail closed")
        return self

    @property
    def deferred_operators(self) -> frozenset[StructureTwoOperator]:
        return frozenset(
            item.operator
            for item in self.operator_modes
            if item.mode is OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE
        )


class CounterfactualBranchingSpec(ContractModel):
    branch_point: Literal["BEFORE_ROUTER_AND_ANY_PATH_DEPENDENT_FEATURE"]
    exact_initial_state_hash_required: Literal[True]
    same_robot_visible_input: Literal[True]
    same_model_weights: Literal[True]
    same_candidate_support: Literal[True]
    same_exogenous_event_schedule: Literal[True]
    exogenous_rng_algorithm: Literal["SOURCE_BOUND_COMMON_RANDOM_NUMBER_STREAM"]
    exogenous_rng_version: Literal["0.1-development"]
    exogenous_rng_seed_binding: Literal["REPLICATE_SEED_EXACT"]
    exogenous_rng_initial_state_hash_required: Literal[True]
    canonical_schedule_payload_hash_required: Literal[True]
    truth_visible_to_router_or_path: Literal[False]
    truth_visible_to_evaluator_only: Literal[True]
    cross_branch_state_leakage_forbidden: Literal[True]
    post_action_observations_regenerated_inside_branch: Literal[True]
    all_registered_legal_paths_required_per_branch_point: Literal[True]
    horizon_must_cover_late_correction_and_recovery: Literal[True]
    terminal_pending_debt_is_infeasible: Literal[True]


class Gate1OracleAccountingSpec(ContractModel):
    hindsight_uses_post_outcome_information: Literal[True]
    hindsight_decision_overhead_ratio: Annotated[float, Field(ge=0.0, le=0.0)]
    best_fixed_router_overhead_ratio: Annotated[float, Field(ge=0.0, le=0.0)]
    path_execution_storage_replay_sensing_costs_unchanged: Literal[True]
    router_feature_and_inference_costs_must_be_counted_in_observable_gate: Literal[True]


class ResourceVector(ContractModel):
    online_compute_ratio: FiniteNonNegative
    latency_ratio: FiniteNonNegative
    energy_ratio: FiniteNonNegative
    peak_memory_ratio: FiniteNonNegative
    persistent_storage_ratio: FiniteNonNegative
    replay_compute_ratio: FiniteNonNegative
    embodied_sensing_ratio: FiniteNonNegative
    router_overhead_ratio: FiniteNonNegative


class ResourceBudgetPoint(ResourceVector):
    budget_id: str = Field(pattern=r"^[A-Z0-9_]+$")


class RecoveryEquivalenceSpec(ContractModel):
    belief_tv_p95_maximum: Probability
    belief_tv_maximum: Probability
    action_top1_agreement_minimum: Probability
    consequential_action_exact_match_required: Literal[True]
    actor_identity_state_exact_match_required: Literal[True]
    commit_retract_state_exact_match_required: Literal[True]
    authority_state_exact_match_required: Literal[True]
    privacy_state_exact_match_required: Literal[True]
    utility_relative_delta_maximum: FiniteNonNegative
    utility_absolute_delta_maximum: FiniteNonNegative


class StatisticalPolicy(ContractModel):
    minimum_validation_households: Annotated[int, Field(gt=1)]
    minimum_confirmatory_households: Annotated[int, Field(gt=1)]
    cluster_key: Literal["household_id"]
    familywise_alpha: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]
    multiplicity_correction: Literal[
        "BONFERRONI_OVER_BUDGET_ALL_EFFECT_NONINFERIORITY_AND_DIVERSITY_BOUNDS"
    ]
    bootstrap_resamples: Annotated[int, Field(ge=100)]
    minimum_bootstrap_tail_draws: Annotated[int, Field(ge=20)]
    bootstrap_seed: int
    minimum_absolute_improvement: FinitePositive
    minimum_relative_improvement: FinitePositive
    other_axis_noninferiority_margin: FiniteNonNegative
    minimum_strict_winner_absolute_gap: FinitePositive
    minimum_distinct_winning_paths: Annotated[int, Field(ge=2)]
    minimum_winning_path_share: Annotated[float, Field(gt=0.0, le=0.5, allow_inf_nan=False)]


class PopulationBinding(ContractModel):
    source_protocol_id: Literal["structure-two-task9-four-coupling-protocol@1.1"]
    validation_household_ids: tuple[str, ...]
    confirmatory_household_ids: tuple[str, ...]
    replicate_seeds: tuple[int, ...]

    @model_validator(mode="after")
    def disjoint_complete_population(self) -> Self:
        validation = set(self.validation_household_ids)
        confirmatory = set(self.confirmatory_household_ids)
        if (
            not validation
            or not confirmatory
            or len(validation) != len(self.validation_household_ids)
            or len(confirmatory) != len(self.confirmatory_household_ids)
        ):
            raise ValueError("population household identifiers must be non-empty and unique")
        if validation & confirmatory:
            raise ValueError("validation and confirmatory population bindings must be disjoint")
        if len(self.replicate_seeds) < 2 or len(set(self.replicate_seeds)) != len(
            self.replicate_seeds
        ):
            raise ValueError("population requires at least two unique replicate seeds")
        return self


class ExecutionBindingStatus(ContractModel):
    production_execution_plan_interface: Literal["SELECTED_A_IMMUTABLE_PLAN_AND_TRACE_SINK"]
    path_specific_operator_budgets: Literal["UNBOUND"]
    branch_point_manifest: Literal["UNBOUND"]
    path_eligibility_policy: Literal[
        "ROUTER_POLICY_BOUND_FEATURE_EXTRACTION_UNBOUND",
        "BOUND_TO_LOCAL_PRODUCTION_STATE",
    ]
    debt_replay_verifier: Literal["UNBOUND_TO_PRODUCTION_REPLAY"]
    power_analysis: Literal["UNBOUND_TO_EMPIRICAL_VARIANCE_AND_ICC"]
    confirmatory_access_custody: Literal["UNBOUND"]
    exogenous_rng_source: Literal["UNBOUND_TO_PRODUCTION_EXECUTION"]
    legal_path_executor: Literal[
        "PLAN_REGISTRY_AND_PARTIAL_KERNELS_BOUND_FULL_EXECUTOR_UNBOUND",
        "BOUND_TO_PRODUCTION_RUNTIME",
    ]
    p0_p5_consequential_runtime_identity: Literal[
        "PARTIAL_TRACE_IDENTITY_FULL_CONSEQUENTIAL_IDENTITY_UNBOUND",
        "ESTABLISHED_D0_LOCAL_RUNTIME",
    ]
    resource_accountant: Literal[
        "OPERATOR_ELAPSED_BOUND_ROUTER_FEATURE_COST_UNBOUND",
        "BOUND_TO_LOCAL_PRODUCTION_EXECUTION",
    ]
    long_horizon_loss_adapter: Literal["UNBOUND_TO_PRODUCTION_ACTION_CONSEQUENCES"]


class PrerequisiteSources(ContractModel):
    selected_method_receipt: Path
    action_utility_construct_gate_config: Path
    runtime_identity_gate_config: Path
    production_execution_contract: Path
    adaptive_runtime: Path
    production_system: Path
    prototype_spine: Path
    regime_loop: Path
    task9_protocol: Path


class AdaptiveComputePreDeathProtocol(ContractModel):
    schema_version: Literal["1.0.0"]
    protocol_id: Literal["structure-two-adaptive-computation-pre-death-test@0.1-development"]
    status: Literal[
        "PROTOCOL_SCHEMA_FROZEN_LOCAL_ADAPTIVE_RUNTIME_BOUND_REMAINING_GATES_UNRESOLVED"
    ]
    evidence_level: Literal["D0_COUNTERFACTUAL_BRANCHING_DEVELOPMENT_ONLY"]
    frozen_on: Literal["2026-09-09"]
    historical_task8_status: Literal["IMMUTABLE_FAIL"]
    frozen_before_confirmatory_opening: Literal[True]
    primary_question: str = Field(min_length=1)
    scope_policy: ScopePolicy
    hard_safety_kernel: HardSafetyKernel
    router_feature_contract: RouterFeatureContract
    operator_order: tuple[StructureTwoOperator, ...]
    legal_paths: tuple[LegalPathSpec, ...]
    counterfactual_branching: CounterfactualBranchingSpec
    gate1_oracle_accounting: Gate1OracleAccountingSpec
    quality_axes: tuple[QualityAxis, ...]
    resource_budget_points: tuple[ResourceBudgetPoint, ...]
    recovery_equivalence: RecoveryEquivalenceSpec
    statistical_policy: StatisticalPolicy
    population_binding: PopulationBinding
    execution_binding_status: ExecutionBindingStatus
    prerequisite_sources: PrerequisiteSources
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def frozen_complete_protocol(self) -> Self:
        expected_operators = tuple(
            StructureTwoOperator(value) for value in PRODUCTION_OPERATOR_ORDER
        )
        if self.operator_order != expected_operators:
            raise ValueError("protocol operator order drifted from production order")
        if self.scope_policy.operators != expected_operators:
            raise ValueError("scope policy must retain all seven production operators")
        path_ids = tuple(path.path_id for path in self.legal_paths)
        if path_ids != REQUIRED_PATH_IDS:
            raise ValueError("pre-death test requires the exact ordered six-path registry")
        for path in self.legal_paths:
            observed_modes = tuple(item.mode for item in path.operator_modes)
            if observed_modes != EXPECTED_PATH_MODES[path.path_id]:
                raise ValueError(
                    f"legal path operator modes drifted from frozen registry: {path.path_id}"
                )
        if any(
            path.fallback_path_id != FULL_EAGER_PATH_ID
            for path in self.legal_paths
            if path.path_id != FULL_EAGER_PATH_ID
        ):
            raise ValueError("every non-full path must fail closed to the full-eager path")
        full = self.path_by_id[FULL_EAGER_PATH_ID]
        if full.fallback_path_id != "SAFE_ABSTAIN":
            raise ValueError("full-eager failure must terminate in safe abstention")
        if any(
            item.mode is not OperatorExecutionMode.REFINEMENT_EXECUTED
            for item in full.operator_modes
        ):
            raise ValueError("full-eager path may not defer or weaken an operator")
        if self.quality_axes != tuple(QualityAxis):
            raise ValueError("all three long-horizon quality axes must remain explicit")
        budget_ids = tuple(point.budget_id for point in self.resource_budget_points)
        if not budget_ids or len(budget_ids) != len(set(budget_ids)):
            raise ValueError("resource budget identifiers must be non-empty and unique")
        if self.statistical_policy.minimum_distinct_winning_paths > len(self.legal_paths):
            raise ValueError("winning-path diversity threshold exceeds registered paths")
        bounds_per_comparison = 2 + (len(self.quality_axes) - 1) + len(self.legal_paths)
        family_size = (
            len(self.resource_budget_points) * len(self.quality_axes) * bounds_per_comparison
        )
        corrected_alpha = self.statistical_policy.familywise_alpha / family_size
        if math.floor(self.statistical_policy.bootstrap_resamples * corrected_alpha) < (
            self.statistical_policy.minimum_bootstrap_tail_draws
        ):
            raise ValueError("bootstrap has too few draws in each corrected extreme tail")
        if len(self.population_binding.validation_household_ids) < (
            self.statistical_policy.minimum_validation_households
        ):
            raise ValueError("frozen validation population is smaller than the statistical gate")
        if len(self.population_binding.confirmatory_household_ids) < (
            self.statistical_policy.minimum_confirmatory_households
        ):
            raise ValueError("frozen confirmatory population is smaller than the statistical gate")
        if self.prerequisite_sources.action_utility_construct_gate_config != (
            ACTION_UTILITY_GATE_CONFIG
        ):
            raise ValueError("action/utility prerequisite must bind the audited default config")
        if self.prerequisite_sources.runtime_identity_gate_config != (RUNTIME_IDENTITY_GATE_CONFIG):
            raise ValueError("runtime-identity prerequisite must bind the audited default config")
        return self

    @property
    def path_by_id(self) -> dict[str, LegalPathSpec]:
        return {path.path_id: path for path in self.legal_paths}


def _strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-standard JSON numeric constant in {path}: {value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _repository_file(repository_root: Path, relative_path: Path) -> Path:
    root = repository_root.resolve()
    resolved = (root / relative_path).resolve()
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or not resolved.is_relative_to(root)
        or not resolved.is_file()
    ):
        raise ValueError(f"pre-death-test source is not a repository file: {relative_path}")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_adaptive_compute_predeath_protocol(
    repository_root: Path,
    path: Path = DEFAULT_CONFIG,
) -> AdaptiveComputePreDeathProtocol:
    config_path = _repository_file(repository_root, path)
    return AdaptiveComputePreDeathProtocol.model_validate(_strict_json(config_path))


def required_debt_replay_order(
    deferred_operators: frozenset[StructureTwoOperator],
) -> tuple[StructureTwoOperator, ...]:
    """Return the frozen replay closure needed to settle an inference debt."""

    if not deferred_operators:
        raise ValueError("a debt replay closure requires at least one deferred operator")
    earliest = min(
        PRODUCTION_OPERATOR_ORDER.index(operator.value) for operator in deferred_operators
    )
    forward_rebuild_through_ciav = tuple(
        StructureTwoOperator(value) for value in PRODUCTION_OPERATOR_ORDER[earliest:]
    )
    return forward_rebuild_through_ciav + CIAV_FEEDBACK_REPLAY_ORDER[1:]


class DebtResolutionReceipt(ContractModel):
    settled_at_step: NonNegativeInt
    replay_trace_sha256: SHA256
    recovered_state_sha256: SHA256
    eager_reference_state_sha256: SHA256
    belief_tv: Probability
    action_top1_agreement: Probability
    consequential_action_exact_match: bool
    actor_identity_state_exact_match: bool
    commit_retract_state_exact_match: bool
    authority_state_exact_match: bool
    privacy_state_exact_match: bool
    utility_relative_delta: FiniteNonNegative
    utility_absolute_delta: FiniteNonNegative


class InferenceDebtCertificate(ContractModel):
    debt_schema_version: Literal["1.0.0"]
    debt_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    route_id: str = Field(min_length=1)
    origin_checkpoint_sha256: SHA256
    created_at_step: NonNegativeInt
    deferred_operators: tuple[StructureTwoOperator, ...]
    raw_evidence_content_hashes: tuple[SHA256, ...]
    operator_version_hashes: dict[str, SHA256]
    sufficient_state_snapshot_sha256: SHA256
    unresolved_hypothesis_ids: tuple[str, ...]
    skipped_as_negative: Literal[False]
    decision_flip_upper_bound: Probability
    decision_flip_bound_derivation_sha256: SHA256
    attribution_flip_upper_bound: Probability
    attribution_flip_bound_derivation_sha256: SHA256
    allowed_actions_before_resolution: tuple[PreResolutionAction, ...]
    forbidden_memory_transitions_before_resolution: tuple[MemoryTransitionKind, ...]
    observed_actions_before_resolution: tuple[PreResolutionAction, ...]
    observed_memory_transitions_before_resolution: tuple[MemoryTransitionKind, ...]
    escalation_triggers: tuple[str, ...]
    expiry_step: Annotated[int, Field(gt=0)]
    replay_operator_order: tuple[StructureTwoOperator, ...]
    replay_scope_ids: tuple[str, ...]
    status: DebtStatus
    resolution: DebtResolutionReceipt | None

    @model_validator(mode="after")
    def complete_recoverable_debt(self) -> Self:
        if not self.deferred_operators or len(set(self.deferred_operators)) != len(
            self.deferred_operators
        ):
            raise ValueError("inference debt must name unique deferred operators")
        if (
            not self.raw_evidence_content_hashes
            or len(set(self.raw_evidence_content_hashes)) != len(self.raw_evidence_content_hashes)
            or not self.unresolved_hypothesis_ids
        ):
            raise ValueError("inference debt must retain evidence and unresolved hypotheses")
        if set(self.operator_version_hashes) != set(PRODUCTION_OPERATOR_ORDER):
            raise ValueError("inference debt must bind all seven operator versions")
        if not self.allowed_actions_before_resolution or len(
            set(self.allowed_actions_before_resolution)
        ) != len(self.allowed_actions_before_resolution):
            raise ValueError("inference debt must freeze unique allowed pre-resolution actions")
        if len(set(self.forbidden_memory_transitions_before_resolution)) != len(
            self.forbidden_memory_transitions_before_resolution
        ):
            raise ValueError("inference debt must freeze unique blocked memory transitions")
        frozen_forbidden = {
            transition.value for transition in self.forbidden_memory_transitions_before_resolution
        }
        if (
            self.decision_flip_upper_bound > 0.0 or self.attribution_flip_upper_bound > 0.0
        ) and not REQUIRED_FLIP_RISK_BLOCKED_TRANSITIONS.issubset(frozen_forbidden):
            raise ValueError("positive flip risk must block every permanent memory transition")
        if {
            action.value for action in self.allowed_actions_before_resolution
        } & REQUIRED_FLIP_RISK_BLOCKED_TRANSITIONS:
            raise ValueError("a blocked permanent transition cannot be an allowed action")
        if not set(self.observed_actions_before_resolution).issubset(
            self.allowed_actions_before_resolution
        ):
            raise ValueError("observed pre-resolution action was not authorized by the debt")
        if set(self.observed_memory_transitions_before_resolution) & set(
            self.forbidden_memory_transitions_before_resolution
        ):
            raise ValueError("a forbidden memory transition occurred before debt resolution")
        if not self.replay_scope_ids or self.replay_operator_order != required_debt_replay_order(
            frozenset(self.deferred_operators)
        ):
            raise ValueError(
                "inference debt replay must exactly cover the frozen downstream/feedback closure"
            )
        if not REQUIRED_DEBT_TRIGGERS.issubset(self.escalation_triggers):
            raise ValueError("inference debt is missing a mandatory escalation trigger")
        if self.expiry_step <= self.created_at_step:
            raise ValueError("inference debt must expire after it is created")
        if self.status is DebtStatus.PENDING and self.resolution is not None:
            raise ValueError("pending inference debt cannot carry a resolution receipt")
        if self.status is DebtStatus.SETTLED and self.resolution is None:
            raise ValueError("settled inference debt requires a resolution receipt")
        if self.resolution is not None and self.resolution.settled_at_step < self.created_at_step:
            raise ValueError("inference debt cannot settle before creation")
        if self.resolution is not None and self.resolution.settled_at_step > self.expiry_step:
            raise ValueError("inference debt cannot settle after its frozen expiry")
        return self


class QualityLossVector(ContractModel):
    task_loss: FiniteNonNegative
    memory_loss: FiniteNonNegative
    recovery_loss: FiniteNonNegative

    def value(self, axis: QualityAxis) -> float:
        return float(getattr(self, axis.value))


class HardConstraintOutcome(ContractModel):
    safety_violations: NonNegativeInt
    unauthorized_long_term_commits: NonNegativeInt
    provenance_violations: NonNegativeInt
    unresolved_as_negative_events: NonNegativeInt
    discarded_required_evidence_events: NonNegativeInt
    unauthorized_identity_disclosures: NonNegativeInt
    unauthorized_person_data_egress_events: NonNegativeInt
    pending_debt_at_horizon: NonNegativeInt


class PathEligibilityOutcome(ContractModel):
    policy_id: Literal["structure-two-path-eligibility@0.1-development"]
    eligibility_evidence_sha256: SHA256
    preconditions_satisfied: bool
    forced_escalation_triggered: bool
    forced_escalation_honored: bool
    escalation_target_path_id: str | None
    escalation_cause: ForcedEscalationCause | None
    escalation_stage: ForcedEscalationStage | None
    long_term_write_requested: bool
    rgrc_write_authorized: bool

    @model_validator(mode="after")
    def coherent_outcome(self) -> Self:
        escalation_fields_present = (
            self.escalation_target_path_id is not None
            and self.escalation_cause is not None
            and self.escalation_stage is not None
        )
        if self.forced_escalation_triggered != escalation_fields_present:
            raise ValueError("forced escalation must name exactly one target, cause, and stage")
        if not self.forced_escalation_triggered and any(
            value is not None
            for value in (
                self.escalation_target_path_id,
                self.escalation_cause,
                self.escalation_stage,
            )
        ):
            raise ValueError("untriggered escalation cannot carry target, cause, or stage")
        if self.forced_escalation_honored and not self.forced_escalation_triggered:
            raise ValueError("an untriggered escalation cannot be marked honored")
        if self.forced_escalation_triggered and not self.forced_escalation_honored:
            raise ValueError("a triggered forced escalation must be honored")
        if not self.preconditions_satisfied and self.escalation_stage is not (
            ForcedEscalationStage.PRE_ROUTE
        ):
            raise ValueError("failed path preconditions require a pre-route escalation")
        if self.preconditions_satisfied and self.escalation_stage is (
            ForcedEscalationStage.PRE_ROUTE
        ):
            raise ValueError("pre-route escalation requires failed path preconditions")
        pre_route_only_causes = {
            ForcedEscalationCause.INVALID_ROUTER_INPUT,
            ForcedEscalationCause.EXPIRED_DEBT,
            ForcedEscalationCause.UNSAFE_OR_UNAUTHORIZED_MEMORY_TRANSITION,
            ForcedEscalationCause.PRIVACY_POLICY_VIOLATION,
        }
        if (
            self.escalation_cause in pre_route_only_causes
            and self.escalation_stage is not ForcedEscalationStage.PRE_ROUTE
        ):
            raise ValueError("this escalation cause must be detected before path execution")
        if self.long_term_write_requested and not self.rgrc_write_authorized:
            raise ValueError("long-term writes require explicit RGRC authorization")
        return self


class OperatorInvocationReceipt(ContractModel):
    invocation_id: str = Field(min_length=1)
    sequence_index: NonNegativeInt
    operator: StructureTwoOperator
    execution_mode: OperatorExecutionMode
    phase: Literal[
        "SELECTED_PATH",
        "SELECTED_FEEDBACK_CLOSURE",
        "FALLBACK_PATH",
        "FALLBACK_FEEDBACK_CLOSURE",
        "DEBT_REPLAY",
    ]
    path_id: str = Field(min_length=1)
    debt_id: str | None
    consumes_state_sha256: SHA256
    produces_state_sha256: SHA256
    receipt_sha256: SHA256


class ShadowRunRecord(ContractModel):
    split: EvidenceSplit
    household_id: str = Field(min_length=1)
    replicate_seed: int
    trajectory_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    route_id: str = Field(min_length=1)
    predecision_checkpoint_sha256: SHA256
    robot_visible_input_sha256: SHA256
    model_weights_sha256: SHA256
    candidate_support_sha256: SHA256
    exogenous_event_schedule_sha256: SHA256
    exogenous_rng_algorithm: str = Field(min_length=1)
    exogenous_rng_version: str = Field(min_length=1)
    exogenous_rng_seed: int
    exogenous_rng_initial_state_sha256: SHA256
    exogenous_rng_source_sha256: SHA256
    exogenous_rng_binding_sha256: SHA256
    route_feature_source_sha256: SHA256
    route_features: dict[str, float]
    truth_read_before_route_selection: Literal[False]
    future_feedback_read_before_route_selection: Literal[False]
    other_path_output_read_before_route_selection: Literal[False]
    runtime_execution_id: str = Field(min_length=1)
    runtime_symbol: str = Field(min_length=1)
    runtime_binding_evidence_sha256: SHA256
    path_eligibility: PathEligibilityOutcome
    operator_receipt_sha256: dict[str, SHA256]
    operator_invocation_receipts: tuple[OperatorInvocationReceipt, ...]
    losses: QualityLossVector
    costs: ResourceVector
    hard_constraints: HardConstraintOutcome
    debt_certificates: tuple[InferenceDebtCertificate, ...]
    fallback_used: bool
    executed_path_sequence: tuple[str, ...]
    branch_timed_out: bool
    branch_failed: bool
    failure_or_timeout_receipt_sha256: SHA256 | None
    failure_or_timeout_cost_charged: bool
    fallback_path_timed_out: bool
    fallback_path_failed: bool
    fallback_failure_or_timeout_receipt_sha256: SHA256 | None
    fallback_failure_or_timeout_cost_charged: bool
    safe_abstention_executed: bool
    safe_abstention_receipt_sha256: SHA256 | None
    selected_path_observation_acquired: bool
    fallback_path_observation_acquired: bool
    physical_verification_executed: bool
    feedback_closure_receipt_sha256: SHA256 | None
    late_correction_present: bool
    late_correction_step: NonNegativeInt | None
    horizon_end_step: NonNegativeInt
    horizon_complete: Literal[True]

    @model_validator(mode="after")
    def finite_features(self) -> Self:
        if any(not math.isfinite(value) for value in self.route_features.values()):
            raise ValueError("route features must be finite")
        if self.exogenous_rng_seed != self.replicate_seed:
            raise ValueError("exogenous RNG seed must equal the frozen replicate seed")
        expected_rng_binding = content_sha256(
            {
                "algorithm": self.exogenous_rng_algorithm,
                "version": self.exogenous_rng_version,
                "seed": self.exogenous_rng_seed,
                "initial_state_sha256": self.exogenous_rng_initial_state_sha256,
                "source_sha256": self.exogenous_rng_source_sha256,
                "canonical_schedule_payload_sha256": (self.exogenous_event_schedule_sha256),
            }
        )
        if self.exogenous_rng_binding_sha256 != expected_rng_binding:
            raise ValueError("exogenous RNG binding hash does not bind its canonical fields")
        if set(self.operator_receipt_sha256) != set(PRODUCTION_OPERATOR_ORDER):
            raise ValueError("every shadow branch requires all seven operator receipts")
        invocation_indices = tuple(
            receipt.sequence_index for receipt in self.operator_invocation_receipts
        )
        if invocation_indices != tuple(range(len(invocation_indices))):
            raise ValueError("operator invocation receipts must have consecutive sequence indices")
        if len({item.invocation_id for item in self.operator_invocation_receipts}) != len(
            self.operator_invocation_receipts
        ):
            raise ValueError("operator invocation identifiers must be unique within a branch")
        if self.operator_invocation_receipts:
            if (
                self.operator_invocation_receipts[0].consumes_state_sha256
                != self.predecision_checkpoint_sha256
            ):
                raise ValueError("first operator invocation must consume the branch checkpoint")
            for previous, current in pairwise(self.operator_invocation_receipts):
                if current.consumes_state_sha256 != previous.produces_state_sha256:
                    raise ValueError("operator invocation receipts must form a state-hash chain")
        if self.physical_verification_executed != (
            self.feedback_closure_receipt_sha256 is not None
        ):
            raise ValueError("physical verification requires exactly one feedback-closure receipt")
        if self.fallback_path_observation_acquired and not self.fallback_used:
            raise ValueError("fallback observation cannot exist without fallback execution")
        if self.physical_verification_executed != (
            self.selected_path_observation_acquired or self.fallback_path_observation_acquired
        ):
            raise ValueError("physical verification must equal observed selected/fallback action")
        feedback_receipts = [
            receipt.model_dump(mode="json")
            for receipt in self.operator_invocation_receipts
            if "FEEDBACK_CLOSURE" in receipt.phase
        ]
        if self.physical_verification_executed != bool(feedback_receipts):
            raise ValueError("physical verification must match executed feedback-closure calls")
        if feedback_receipts and self.feedback_closure_receipt_sha256 != content_sha256(
            {"operator_invocation_receipts": feedback_receipts}
        ):
            raise ValueError("feedback-closure aggregate hash does not bind its invocations")
        if not self.executed_path_sequence or self.executed_path_sequence[0] != self.route_id:
            raise ValueError("executed path sequence must begin with the selected route")
        if self.branch_timed_out and not self.fallback_used:
            raise ValueError("a timed-out branch must execute its frozen fallback")
        if self.branch_failed and not self.fallback_used:
            raise ValueError("a failed branch must execute its frozen fallback")
        if (self.branch_timed_out or self.branch_failed) != (
            self.failure_or_timeout_receipt_sha256 is not None
        ):
            raise ValueError("failure or timeout requires exactly one source receipt")
        if self.fallback_used and not self.failure_or_timeout_cost_charged:
            raise ValueError("fallback execution must charge failure or timeout cost")
        secondary_failure = self.fallback_path_timed_out or self.fallback_path_failed
        if secondary_failure and not self.fallback_used:
            raise ValueError("a fallback path cannot fail unless it was executed")
        if secondary_failure != (self.fallback_failure_or_timeout_receipt_sha256 is not None):
            raise ValueError("fallback failure or timeout requires exactly one source receipt")
        if secondary_failure and not self.fallback_failure_or_timeout_cost_charged:
            raise ValueError("fallback failure or timeout cost must be charged")
        if not secondary_failure and self.fallback_failure_or_timeout_cost_charged:
            raise ValueError("fallback failure cost cannot be charged without a failure")
        if self.safe_abstention_executed != (self.safe_abstention_receipt_sha256 is not None):
            raise ValueError("safe abstention requires exactly one action receipt")
        if not self.fallback_used and self.safe_abstention_executed:
            raise ValueError("safe abstention cannot occur without a frozen fallback")
        if self.late_correction_present != (self.late_correction_step is not None):
            raise ValueError("late-correction presence requires exactly one event step")
        if (
            self.late_correction_step is not None
            and self.late_correction_step >= self.horizon_end_step
        ):
            raise ValueError("late correction must occur before the scoring horizon ends")
        return self


class ShadowMatrixEvidence(ContractModel):
    schema_version: Literal["1.0.0"]
    protocol_id: Literal["structure-two-adaptive-computation-pre-death-test@0.1-development"]
    protocol_content_sha256: SHA256
    evidence_level: Literal["D0_COUNTERFACTUAL_BRANCHING_DEVELOPMENT_ONLY"]
    executor_source_sha256: SHA256
    resource_accountant_source_sha256: SHA256
    long_horizon_loss_contract_sha256: SHA256
    records: tuple[ShadowRunRecord, ...]


BranchKey = tuple[EvidenceSplit, str, int, str, str]
ContextKey = tuple[EvidenceSplit, str, str, str]


def _group_key(record: ShadowRunRecord) -> BranchKey:
    return (
        record.split,
        record.household_id,
        record.replicate_seed,
        record.trajectory_id,
        record.decision_id,
    )


def _context_key(record: ShadowRunRecord) -> ContextKey:
    return (
        record.split,
        record.household_id,
        record.trajectory_id,
        record.decision_id,
    )


def _path_invocation_signature(
    route: LegalPathSpec,
    *,
    primary_phase: str,
    feedback_phase: str,
    include_feedback: bool,
) -> tuple[tuple[StructureTwoOperator, OperatorExecutionMode, str, str, None], ...]:
    primary = tuple(
        (item.operator, item.mode, primary_phase, route.path_id, None)
        for item in route.operator_modes
        if item.mode
        not in {
            OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
            OperatorExecutionMode.NOT_APPLICABLE_WITH_RECOMPUTED_REASON,
        }
    )
    feedback = (
        tuple(
            (
                operator,
                OperatorExecutionMode.REFINEMENT_EXECUTED,
                feedback_phase,
                route.path_id,
                None,
            )
            for operator in route.feedback_closure_operator_order[1:]
        )
        if include_feedback
        else ()
    )
    return primary + feedback


def _validate_operator_invocations(
    record: ShadowRunRecord,
    protocol: AdaptiveComputePreDeathProtocol,
) -> None:
    route = protocol.path_by_id[record.route_id]
    selected = _path_invocation_signature(
        route,
        primary_phase="SELECTED_PATH",
        feedback_phase="SELECTED_FEEDBACK_CLOSURE",
        include_feedback=record.selected_path_observation_acquired,
    )
    fallback: tuple[tuple[StructureTwoOperator, OperatorExecutionMode, str, str, None], ...] = ()
    fallback_path_id = (
        record.path_eligibility.escalation_target_path_id
        if record.path_eligibility.forced_escalation_triggered
        else route.fallback_path_id
    )
    if record.fallback_used and fallback_path_id in protocol.path_by_id:
        fallback = _path_invocation_signature(
            protocol.path_by_id[fallback_path_id],
            primary_phase="FALLBACK_PATH",
            feedback_phase="FALLBACK_FEEDBACK_CLOSURE",
            include_feedback=record.fallback_path_observation_acquired,
        )
    debt_replay = tuple(
        (
            operator,
            OperatorExecutionMode.REFINEMENT_EXECUTED,
            "DEBT_REPLAY",
            record.route_id,
            certificate.debt_id,
        )
        for certificate in record.debt_certificates
        for operator in certificate.replay_operator_order
    )
    actual = tuple(
        (
            receipt.operator,
            receipt.execution_mode,
            receipt.phase,
            receipt.path_id,
            receipt.debt_id,
        )
        for receipt in record.operator_invocation_receipts
    )
    if not record.fallback_used:
        if actual != selected + debt_replay:
            raise ValueError("operator invocation trace differs from selected path and debt replay")
        return
    fallback_start = next(
        (index for index, item in enumerate(actual) if item[2].startswith("FALLBACK")),
        len(actual) - len(debt_replay),
    )
    selected_actual = actual[:fallback_start]
    remainder = actual[fallback_start:]
    if selected_actual != selected[: len(selected_actual)]:
        raise ValueError("failed selected-path invocation trace is not a legal prefix")
    escalation_stage = record.path_eligibility.escalation_stage
    if escalation_stage is ForcedEscalationStage.PRE_ROUTE and selected_actual:
        raise ValueError("pre-route escalation must occur before every selected-path invocation")
    if escalation_stage is ForcedEscalationStage.MID_SELECTED_PATH and (
        not selected_actual or len(selected_actual) >= len(selected)
    ):
        raise ValueError("mid-path escalation requires a non-empty strict selected-path prefix")
    debt_start = next(
        (index for index, item in enumerate(remainder) if item[2] == "DEBT_REPLAY"),
        len(remainder),
    )
    fallback_actual = remainder[:debt_start]
    debt_actual = remainder[debt_start:]
    if record.fallback_path_timed_out or record.fallback_path_failed:
        if fallback_actual != fallback[: len(fallback_actual)]:
            raise ValueError("failed fallback-path invocation trace is not a legal prefix")
    elif fallback_actual != fallback:
        raise ValueError("fallback invocation trace differs from frozen contract")
    if debt_actual != debt_replay:
        raise ValueError("debt-replay invocation trace differs from frozen contract")


def _record_path_is_eligible(record: ShadowRunRecord) -> bool:
    eligibility = record.path_eligibility
    return bool(
        eligibility.preconditions_satisfied
        and not eligibility.forced_escalation_triggered
        and not record.fallback_used
        and not record.branch_timed_out
    )


def _record_is_within_budget(
    record: ShadowRunRecord,
    budget: ResourceBudgetPoint,
    *,
    include_router_overhead: bool,
) -> bool:
    return all(
        float(getattr(record.costs, field)) <= float(getattr(budget, field))
        for field in ResourceVector.model_fields
        if include_router_overhead or field != "router_overhead_ratio"
    )


def _debt_guardrail_reasons(
    record: ShadowRunRecord,
    route: LegalPathSpec,
    recovery: RecoveryEquivalenceSpec,
) -> list[str]:
    reasons: list[str] = []
    deferred = (
        frozenset()
        if record.path_eligibility.escalation_stage is ForcedEscalationStage.PRE_ROUTE
        else route.deferred_operators
    )
    certificates = record.debt_certificates
    covered = frozenset(
        operator for certificate in certificates for operator in certificate.deferred_operators
    )
    coverage_counts = Counter(
        operator for certificate in certificates for operator in certificate.deferred_operators
    )
    if deferred != covered:
        reasons.append("deferred_operator_debt_coverage_mismatch")
    if any(count != 1 for count in coverage_counts.values()):
        reasons.append("deferred_operator_has_multiple_debt_owners")
    if not deferred and certificates:
        reasons.append("non_deferred_path_created_inference_debt")
    for certificate in certificates:
        if certificate.route_id != record.route_id or certificate.decision_id != record.decision_id:
            reasons.append("inference_debt_identity_mismatch")
        if certificate.origin_checkpoint_sha256 != record.predecision_checkpoint_sha256:
            reasons.append("inference_debt_checkpoint_mismatch")
        if certificate.status is not DebtStatus.SETTLED or certificate.resolution is None:
            reasons.append("terminal_inference_debt_not_settled")
            continue
        resolution = certificate.resolution
        if resolution.settled_at_step > record.horizon_end_step:
            reasons.append("debt_settled_after_scoring_horizon")
        if (
            record.late_correction_step is not None
            and resolution.settled_at_step < record.late_correction_step
        ):
            reasons.append("debt_settled_before_late_correction")
        if resolution.belief_tv > recovery.belief_tv_maximum:
            reasons.append("debt_recovery_belief_tv_exceeded")
        if resolution.action_top1_agreement < recovery.action_top1_agreement_minimum:
            reasons.append("debt_recovery_action_agreement_failed")
        if not resolution.consequential_action_exact_match:
            reasons.append("debt_recovery_consequential_action_mismatch")
        if not resolution.actor_identity_state_exact_match:
            reasons.append("debt_recovery_actor_identity_state_mismatch")
        if not resolution.commit_retract_state_exact_match:
            reasons.append("debt_recovery_commit_retract_state_mismatch")
        if not resolution.authority_state_exact_match:
            reasons.append("debt_recovery_authority_state_mismatch")
        if not resolution.privacy_state_exact_match:
            reasons.append("debt_recovery_privacy_state_mismatch")
        if resolution.utility_relative_delta > recovery.utility_relative_delta_maximum:
            reasons.append("debt_recovery_relative_utility_delta_exceeded")
        if resolution.utility_absolute_delta > recovery.utility_absolute_delta_maximum:
            reasons.append("debt_recovery_absolute_utility_delta_exceeded")
    return reasons


def _hard_guardrail_reasons(
    record: ShadowRunRecord,
    protocol: AdaptiveComputePreDeathProtocol,
) -> list[str]:
    hard = record.hard_constraints
    kernel = protocol.hard_safety_kernel
    reasons: list[str] = []
    checks = (
        (hard.safety_violations, kernel.maximum_safety_violations, "safety_violation"),
        (
            hard.unauthorized_long_term_commits,
            kernel.maximum_unauthorized_long_term_commits,
            "unauthorized_long_term_commit",
        ),
        (
            hard.provenance_violations,
            kernel.maximum_provenance_violations,
            "provenance_violation",
        ),
        (
            hard.unresolved_as_negative_events,
            kernel.maximum_unresolved_as_negative_events,
            "unresolved_encoded_as_negative",
        ),
        (
            hard.discarded_required_evidence_events,
            kernel.maximum_discarded_required_evidence_events,
            "required_evidence_discarded",
        ),
        (
            hard.unauthorized_identity_disclosures,
            kernel.maximum_unauthorized_identity_disclosures,
            "unauthorized_identity_disclosure",
        ),
        (
            hard.unauthorized_person_data_egress_events,
            kernel.maximum_unauthorized_person_data_egress_events,
            "unauthorized_person_data_egress",
        ),
        (hard.pending_debt_at_horizon, 0, "pending_debt_at_horizon"),
    )
    reasons.extend(label for actual, maximum, label in checks if actual > maximum)
    reasons.extend(
        _debt_guardrail_reasons(
            record,
            protocol.path_by_id[record.route_id],
            protocol.recovery_equivalence,
        )
    )
    return reasons


def validate_shadow_matrix(
    evidence: ShadowMatrixEvidence,
    protocol: AdaptiveComputePreDeathProtocol,
) -> dict[BranchKey, tuple[ShadowRunRecord, ...]]:
    """Validate complete, leak-free, common-random-number branch coverage."""

    # Reconstruct from serialized values so model_copy(update=...) and mutable
    # nested dictionaries cannot bypass Pydantic field or model validators.
    protocol = AdaptiveComputePreDeathProtocol.model_validate(
        protocol.model_dump(mode="python", warnings=False)
    )
    evidence = ShadowMatrixEvidence.model_validate(
        evidence.model_dump(mode="python", warnings=False)
    )
    if evidence.protocol_id != protocol.protocol_id:
        raise ValueError("shadow evidence protocol mismatch")
    protocol_hash = content_sha256(protocol.model_dump(mode="json"))
    if evidence.protocol_content_sha256 != protocol_hash:
        raise ValueError("shadow evidence is not bound to the supplied protocol content")
    if not evidence.records:
        raise ValueError("shadow evidence contains no records")
    allowed_features = set(protocol.router_feature_contract.allowed_feature_names)
    groups: dict[BranchKey, list[ShadowRunRecord]] = defaultdict(list)
    decision_contexts: dict[str, ContextKey] = {}
    checkpoint_contexts: dict[str, ContextKey] = {}
    runtime_execution_ids: set[str] = set()
    invocation_ids: set[str] = set()
    debt_ids: set[str] = set()
    for record in evidence.records:
        if record.route_id not in protocol.path_by_id:
            raise ValueError(f"unregistered path in shadow evidence: {record.route_id}")
        if not set(record.route_features).issubset(allowed_features):
            raise ValueError("shadow record contains a forbidden or unregistered route feature")
        if record.runtime_symbol != (
            "cpswm.system.structure_two_production_system.StructureTwoProductionSystem"
        ):
            raise ValueError("shadow record is not bound to the production runtime symbol")
        context_key = _context_key(record)
        prior_context = decision_contexts.setdefault(record.decision_id, context_key)
        if prior_context != context_key:
            raise ValueError("decision identifier was reused across branch-point contexts")
        prior_checkpoint_context = checkpoint_contexts.setdefault(
            record.predecision_checkpoint_sha256, context_key
        )
        if prior_checkpoint_context != context_key:
            raise ValueError("predecision checkpoint was reused across branch-point contexts")
        if record.runtime_execution_id in runtime_execution_ids:
            raise ValueError("runtime execution identifiers must be globally unique")
        runtime_execution_ids.add(record.runtime_execution_id)
        for receipt in record.operator_invocation_receipts:
            if receipt.invocation_id in invocation_ids:
                raise ValueError("operator invocation identifiers must be globally unique")
            invocation_ids.add(receipt.invocation_id)
        for certificate in record.debt_certificates:
            if certificate.debt_id in debt_ids:
                raise ValueError("inference debt identifiers must be globally unique")
            debt_ids.add(certificate.debt_id)
        groups[_group_key(record)].append(record)

    expected_routes = tuple(protocol.path_by_id)
    normalized: dict[BranchKey, tuple[ShadowRunRecord, ...]] = {}
    for key, values in groups.items():
        by_route = {record.route_id: record for record in values}
        if len(values) != len(by_route) or tuple(sorted(by_route, key=expected_routes.index)) != (
            expected_routes
        ):
            raise ValueError("every branch point must contain each legal path exactly once")
        ordered = tuple(by_route[route_id] for route_id in expected_routes)
        invariants = (
            "predecision_checkpoint_sha256",
            "robot_visible_input_sha256",
            "model_weights_sha256",
            "candidate_support_sha256",
            "exogenous_event_schedule_sha256",
            "exogenous_rng_algorithm",
            "exogenous_rng_version",
            "exogenous_rng_seed",
            "exogenous_rng_initial_state_sha256",
            "exogenous_rng_source_sha256",
            "exogenous_rng_binding_sha256",
            "route_feature_source_sha256",
            "route_features",
            "late_correction_present",
            "late_correction_step",
            "horizon_end_step",
        )
        for field in invariants:
            if len({json.dumps(getattr(item, field), sort_keys=True) for item in ordered}) != 1:
                raise ValueError(
                    f"counterfactual branches disagree on pre-route invariant: {field}"
                )
        if len({record.runtime_execution_id for record in ordered}) != len(ordered):
            raise ValueError("each counterfactual branch requires a fresh runtime execution")
        for record in ordered:
            route = protocol.path_by_id[record.route_id]
            eligibility = record.path_eligibility
            expected_sequence: tuple[str, ...]
            if not record.fallback_used:
                expected_sequence = (record.route_id,)
            elif record.fallback_path_timed_out or record.fallback_path_failed:
                expected_sequence = (
                    record.route_id,
                    route.fallback_path_id,
                    SAFE_ABSTAIN_PATH_ID,
                )
            elif eligibility.forced_escalation_triggered:
                escalation_target = eligibility.escalation_target_path_id
                if escalation_target is None:
                    raise ValueError("triggered forced escalation is missing its target")
                expected_sequence = (
                    record.route_id,
                    escalation_target,
                )
            else:
                expected_sequence = (record.route_id, route.fallback_path_id)
            if record.executed_path_sequence != expected_sequence:
                raise ValueError("executed path sequence differs from the frozen fallback contract")
            if not eligibility.preconditions_satisfied and not (
                eligibility.forced_escalation_triggered and eligibility.forced_escalation_honored
            ):
                raise ValueError("failed path preconditions require an honored forced escalation")
            if eligibility.forced_escalation_triggered and (
                not record.fallback_used
                or eligibility.escalation_cause is None
                or eligibility.escalation_target_path_id
                != route.forced_escalation_target_by_condition[eligibility.escalation_cause]
            ):
                raise ValueError("forced escalation did not execute its cause-specific target")
            if eligibility.escalation_cause is not None and (
                eligibility.escalation_cause.value not in route.forced_escalation_conditions
            ):
                raise ValueError("forced-escalation cause is not registered for the selected path")
            if record.fallback_used and not (
                record.branch_timed_out
                or record.branch_failed
                or eligibility.forced_escalation_triggered
            ):
                raise ValueError("fallback execution has no frozen trigger receipt")
            terminal_safe_abstention_required = bool(
                record.fallback_used
                and (
                    route.fallback_path_id == SAFE_ABSTAIN_PATH_ID
                    or eligibility.escalation_target_path_id == SAFE_ABSTAIN_PATH_ID
                    or record.fallback_path_timed_out
                    or record.fallback_path_failed
                )
            )
            if terminal_safe_abstention_required:
                if not record.safe_abstention_executed:
                    raise ValueError("terminal full-eager failure must execute safe abstention")
            elif record.safe_abstention_executed:
                raise ValueError("safe abstention is not the registered fallback for this path")
            if record.physical_verification_executed and not (
                any(
                    "FEEDBACK_CLOSURE" in item.phase for item in record.operator_invocation_receipts
                )
            ):
                raise ValueError(
                    "physical verification occurred on a path without feedback closure"
                )
            deferred = (
                frozenset()
                if eligibility.escalation_stage is ForcedEscalationStage.PRE_ROUTE
                else route.deferred_operators
            )
            covered = frozenset(
                operator
                for certificate in record.debt_certificates
                for operator in certificate.deferred_operators
            )
            if deferred != covered:
                raise ValueError("deferred operators are not exactly covered by inference debt")
            if any(
                certificate.status is DebtStatus.PENDING for certificate in record.debt_certificates
            ):
                raise ValueError("a completed scoring horizon cannot end with pending debt")
            _validate_operator_invocations(record, protocol)
        normalized[key] = ordered

    households = {
        split: {key[1] for key in normalized if key[0] is split} for split in EvidenceSplit
    }
    expected_households = {
        EvidenceSplit.VALIDATION: set(protocol.population_binding.validation_household_ids),
        EvidenceSplit.CONFIRMATORY: set(protocol.population_binding.confirmatory_household_ids),
    }
    if households != expected_households:
        raise ValueError("shadow evidence household population differs from the frozen binding")
    expected_seeds = set(protocol.population_binding.replicate_seeds)
    expected_rng_algorithm = protocol.counterfactual_branching.exogenous_rng_algorithm
    expected_rng_version = protocol.counterfactual_branching.exogenous_rng_version
    observed_rng_sources = {record.exogenous_rng_source_sha256 for record in evidence.records}
    if len(observed_rng_sources) != 1:
        raise ValueError("shadow evidence must use one frozen exogenous RNG source digest")
    if any(
        record.exogenous_rng_algorithm != expected_rng_algorithm
        or record.exogenous_rng_version != expected_rng_version
        for record in evidence.records
    ):
        raise ValueError("shadow evidence RNG implementation differs from the frozen protocol")
    context_groups: dict[ContextKey, list[tuple[BranchKey, tuple[ShadowRunRecord, ...]]]] = (
        defaultdict(list)
    )
    for key, records in normalized.items():
        context_groups[(key[0], key[1], key[3], key[4])].append((key, records))
    cross_seed_invariants = (
        "predecision_checkpoint_sha256",
        "robot_visible_input_sha256",
        "model_weights_sha256",
        "candidate_support_sha256",
        "route_feature_source_sha256",
        "route_features",
        "late_correction_present",
        "late_correction_step",
        "horizon_end_step",
    )
    for context_rows in context_groups.values():
        observed_seeds = {key[2] for key, _ in context_rows}
        if observed_seeds != expected_seeds:
            raise ValueError("each branch-point context must cover every frozen replicate seed")
        flattened = [record for _, records in context_rows for record in records]
        for field in cross_seed_invariants:
            if len({json.dumps(getattr(item, field), sort_keys=True) for item in flattened}) != 1:
                raise ValueError(
                    f"replicate seeds disagree on pre-route context invariant: {field}"
                )
        for route_id in protocol.path_by_id:
            route_records = [record for record in flattened if record.route_id == route_id]
            eligibility_states = {
                (
                    record.path_eligibility.policy_id,
                    record.path_eligibility.preconditions_satisfied,
                    record.path_eligibility.forced_escalation_triggered,
                    record.path_eligibility.escalation_target_path_id,
                    record.path_eligibility.escalation_cause,
                    record.path_eligibility.escalation_stage,
                )
                for record in route_records
            }
            if len(eligibility_states) != 1:
                raise ValueError("replicate seeds disagree on pre-route path eligibility")
    policy = protocol.statistical_policy
    if len(households[EvidenceSplit.VALIDATION]) < policy.minimum_validation_households:
        raise ValueError("insufficient validation household clusters")
    if len(households[EvidenceSplit.CONFIRMATORY]) < policy.minimum_confirmatory_households:
        raise ValueError("insufficient confirmatory household clusters")
    if any(
        not records[0].late_correction_present
        for key, records in normalized.items()
        if key[0] is EvidenceSplit.CONFIRMATORY
    ):
        raise ValueError("every confirmatory branch-point horizon must cover a late correction")
    return normalized


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot compute a quantile from no values")
    ordered = sorted(values)
    # Nearest-rank empirical quantile.  Subtracting one after ceil avoids the
    # optimistic (k + 1)-th order statistic when probability * n is integral.
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return float(ordered[index])


def _cluster_bootstrap_bound(
    differences: Sequence[tuple[str, float]],
    *,
    probability: float,
    resamples: int,
    seed: int,
) -> float:
    grouped: dict[str, list[float]] = defaultdict(list)
    for household_id, difference in differences:
        grouped[household_id].append(difference)
    cluster_means = {key: mean(values) for key, values in grouped.items()}
    cluster_ids = tuple(sorted(cluster_means))
    if len(cluster_ids) < 2:
        raise ValueError("cluster bootstrap requires at least two households")
    rng = random.Random(seed)
    draws = [
        mean(cluster_means[rng.choice(cluster_ids)] for _ in cluster_ids) for _ in range(resamples)
    ]
    return _quantile(draws, probability)


def _cluster_bootstrap_relative_improvement_lower_bound(
    paired_losses: Sequence[tuple[str, float, float]],
    *,
    alpha: float,
    resamples: int,
    seed: int,
) -> float:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for household_id, fixed_loss, oracle_loss in paired_losses:
        grouped[household_id].append((fixed_loss, oracle_loss))
    cluster_means = {
        household_id: (
            mean(fixed for fixed, _ in values),
            mean(oracle for _, oracle in values),
        )
        for household_id, values in grouped.items()
    }
    cluster_ids = tuple(sorted(cluster_means))
    if len(cluster_ids) < 2:
        raise ValueError("cluster bootstrap requires at least two households")
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        sampled = [cluster_means[rng.choice(cluster_ids)] for _ in cluster_ids]
        fixed_mean = mean(fixed for fixed, _ in sampled)
        oracle_mean = mean(oracle for _, oracle in sampled)
        draws.append((fixed_mean - oracle_mean) / fixed_mean if fixed_mean > 0.0 else 0.0)
    return _quantile(draws, alpha)


def _household_equal_mean(rows: Sequence[ShadowRunRecord], axis: QualityAxis) -> float:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row.household_id].append(row.losses.value(axis))
    if not grouped:
        raise ValueError("household-equal mean requires at least one record")
    return mean(mean(values) for values in grouped.values())


def _household_equal_winner_shares(
    winners: Sequence[tuple[str, str | None]],
    *,
    context_household_ids: Sequence[str],
    route_ids: Sequence[str],
) -> dict[str, float]:
    context_counts = Counter(context_household_ids)
    win_counts: Counter[tuple[str, str]] = Counter()
    for household_id, route_id in winners:
        if route_id is not None:
            win_counts[(household_id, route_id)] += 1
    if not context_counts:
        raise ValueError("winner shares require at least one context per household")
    return {
        route_id: mean(
            win_counts[(household_id, route_id)] / count
            for household_id, count in context_counts.items()
        )
        for route_id in route_ids
    }


def evaluate_hindsight_headroom(
    evidence: ShadowMatrixEvidence,
    protocol: AdaptiveComputePreDeathProtocol,
) -> dict[str, Any]:
    """Compare a validation-selected fixed route with a confirmatory hindsight oracle.

    This pure evaluator does not authenticate the evidence source.  Its result is
    development-only and must be paired with the source-bound readiness gate.
    """

    protocol = AdaptiveComputePreDeathProtocol.model_validate(
        protocol.model_dump(mode="python", warnings=False)
    )
    evidence = ShadowMatrixEvidence.model_validate(
        evidence.model_dump(mode="python", warnings=False)
    )
    groups = validate_shadow_matrix(evidence, protocol)
    violations: list[dict[str, Any]] = []
    recovered_belief_tvs: dict[tuple[EvidenceSplit, str], list[float]] = defaultdict(list)
    for key, records in groups.items():
        for record in records:
            recovered_belief_tvs[(key[0], key[1])].extend(
                certificate.resolution.belief_tv
                for certificate in record.debt_certificates
                if certificate.resolution is not None
            )
            reasons = _hard_guardrail_reasons(record, protocol)
            if reasons:
                violations.append(
                    {
                        "split": key[0].value,
                        "household_id": key[1],
                        "replicate_seed": key[2],
                        "trajectory_id": key[3],
                        "decision_id": key[4],
                        "route_id": record.route_id,
                        "reasons": sorted(set(reasons)),
                    }
                )
    for split in EvidenceSplit:
        household_maxima = [
            max(values)
            for (observed_split, _), values in recovered_belief_tvs.items()
            if observed_split is split and values
        ]
        if household_maxima and _quantile(household_maxima, 0.95) > (
            protocol.recovery_equivalence.belief_tv_p95_maximum
        ):
            violations.append(
                {
                    "split": split.value,
                    "household_id": "household_equal_p95",
                    "trajectory_id": "all",
                    "decision_id": "all",
                    "route_id": "all_deferred_paths",
                    "reasons": ["debt_recovery_household_max_belief_tv_p95_exceeded"],
                }
            )
    if violations:
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "protocol_content_sha256": evidence.protocol_content_sha256,
            "evidence_content_sha256": content_sha256(evidence.model_dump(mode="json")),
            "evidence_status": "CALLER_CONTROLLED_DEVELOPMENT_MATRIX",
            "disposition": PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION.value,
            "hard_guardrail_violations": violations,
            "comparisons": [],
            "caller_controlled_hindsight_headroom_candidate": False,
            "source_bound_hindsight_headroom_established": False,
            "hindsight_headroom_present": False,
            "observable_policy_gate_candidate": False,
            "hindsight_headroom_claim_authorized": False,
            "adaptive_routing_kill_authorized": False,
            "observable_policy_training_authorized": False,
            "recovery_p95_estimand": "WITHIN_HOUSEHOLD_MAX_THEN_HOUSEHOLD_EQUAL_P95_BY_SPLIT",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        report["content_sha256"] = content_sha256(report)
        return report

    validation_groups = {
        key: rows for key, rows in groups.items() if key[0] is EvidenceSplit.VALIDATION
    }
    confirmatory_groups = {
        key: rows for key, rows in groups.items() if key[0] is EvidenceSplit.CONFIRMATORY
    }
    confirmatory_contexts: dict[ContextKey, dict[int, tuple[ShadowRunRecord, ...]]] = defaultdict(
        dict
    )
    for key, rows in confirmatory_groups.items():
        confirmatory_contexts[(key[0], key[1], key[3], key[4])][key[2]] = rows
    route_priority = {route_id: index for index, route_id in enumerate(protocol.path_by_id)}
    comparisons: list[dict[str, Any]] = []
    diagnostic_positive_comparisons = 0
    evaluated_comparisons = 0
    bounds_per_comparison = 2 + (len(protocol.quality_axes) - 1) + len(protocol.legal_paths)
    family_count = (
        len(protocol.resource_budget_points) * len(protocol.quality_axes) * bounds_per_comparison
    )
    corrected_alpha = protocol.statistical_policy.familywise_alpha / family_count

    for budget_index, budget in enumerate(protocol.resource_budget_points):
        for axis_index, axis in enumerate(protocol.quality_axes):
            validation_scores: dict[str, float] = {}
            for route_id in protocol.path_by_id:
                validation_route_rows = [
                    next(record for record in records if record.route_id == route_id)
                    for records in validation_groups.values()
                ]
                if validation_route_rows and all(
                    _record_path_is_eligible(row)
                    and _record_is_within_budget(
                        row,
                        budget,
                        include_router_overhead=False,
                    )
                    for row in validation_route_rows
                ):
                    validation_scores[route_id] = _household_equal_mean(validation_route_rows, axis)
            if not validation_scores:
                comparisons.append(
                    {
                        "budget_id": budget.budget_id,
                        "quality_axis": axis.value,
                        "status": "NO_VALIDATION_FIXED_PATH_WITHIN_BUDGET",
                        "caller_controlled_positive_headroom_candidate": False,
                        "source_bound_positive_headroom": False,
                    }
                )
                continue
            best_fixed = min(
                validation_scores,
                key=lambda route_id: (validation_scores[route_id], route_priority[route_id]),
            )
            fixed_rows: list[ShadowRunRecord] = []
            oracle_rows: list[ShadowRunRecord] = []
            winner_counts: Counter[str] = Counter()
            strict_winners: list[tuple[str, str | None]] = []
            context_household_ids: list[str] = []
            confirmatory_budget_breach = False
            for context_key in sorted(
                confirmatory_contexts,
                key=lambda item: tuple(str(value) for value in item),
            ):
                seed_groups = confirmatory_contexts[context_key]
                by_seed_route = {
                    seed: {record.route_id: record for record in records}
                    for seed, records in seed_groups.items()
                }
                for held_out_seed in protocol.population_binding.replicate_seeds:
                    selection_seeds = tuple(
                        seed
                        for seed in protocol.population_binding.replicate_seeds
                        if seed != held_out_seed
                    )
                    if not selection_seeds:
                        raise ValueError(
                            "cross-fitted oracle requires at least two replicate seeds"
                        )
                    eligible_routes = [
                        route_id
                        for route_id in protocol.path_by_id
                        if all(
                            _record_path_is_eligible(by_seed_route[seed][route_id])
                            and _record_is_within_budget(
                                by_seed_route[seed][route_id],
                                budget,
                                include_router_overhead=False,
                            )
                            for seed in selection_seeds
                        )
                    ]
                    fixed = by_seed_route[held_out_seed][best_fixed]
                    if (
                        not eligible_routes
                        or not _record_path_is_eligible(fixed)
                        or not _record_is_within_budget(
                            fixed,
                            budget,
                            include_router_overhead=False,
                        )
                    ):
                        confirmatory_budget_breach = True
                        break
                    selection_scores = {
                        route_id: mean(
                            by_seed_route[seed][route_id].losses.value(axis)
                            for seed in selection_seeds
                        )
                        for route_id in eligible_routes
                    }
                    oracle_route = min(
                        selection_scores,
                        key=lambda route_id: (
                            selection_scores[route_id],
                            route_priority[route_id],
                        ),
                    )
                    oracle = by_seed_route[held_out_seed][oracle_route]
                    if not _record_path_is_eligible(oracle) or not _record_is_within_budget(
                        oracle,
                        budget,
                        include_router_overhead=False,
                    ):
                        confirmatory_budget_breach = True
                        break
                    fixed_rows.append(fixed)
                    oracle_rows.append(oracle)
                    context_household_ids.append(context_key[1])
                    held_out_feasible_routes = [
                        route_id
                        for route_id in eligible_routes
                        if _record_path_is_eligible(by_seed_route[held_out_seed][route_id])
                        and _record_is_within_budget(
                            by_seed_route[held_out_seed][route_id],
                            budget,
                            include_router_overhead=False,
                        )
                    ]
                    held_out_scores = sorted(
                        by_seed_route[held_out_seed][route_id].losses.value(axis)
                        for route_id in held_out_feasible_routes
                    )
                    if (
                        len(held_out_scores) >= 2
                        and oracle.losses.value(axis) == held_out_scores[0]
                        and held_out_scores[1] - held_out_scores[0]
                        >= protocol.statistical_policy.minimum_strict_winner_absolute_gap
                    ):
                        winner_counts[oracle_route] += 1
                        strict_winners.append((context_key[1], oracle_route))
                    else:
                        strict_winners.append((context_key[1], None))
                if confirmatory_budget_breach:
                    break
            if confirmatory_budget_breach:
                comparisons.append(
                    {
                        "budget_id": budget.budget_id,
                        "quality_axis": axis.value,
                        "status": "CONFIRMATORY_INELIGIBLE_FAILURE_OR_BUDGET_BREACH",
                        "validation_selected_best_fixed_path": best_fixed,
                        "caller_controlled_positive_headroom_candidate": False,
                        "source_bound_positive_headroom": False,
                    }
                )
                continue

            evaluated_comparisons += 1
            fixed_mean = _household_equal_mean(fixed_rows, axis)
            oracle_mean = _household_equal_mean(oracle_rows, axis)
            improvement = fixed_mean - oracle_mean
            relative_improvement = improvement / fixed_mean if fixed_mean > 0.0 else 0.0
            paired = [
                (fixed.household_id, fixed.losses.value(axis) - oracle.losses.value(axis))
                for fixed, oracle in zip(fixed_rows, oracle_rows, strict=True)
            ]
            paired_levels = [
                (
                    fixed.household_id,
                    fixed.losses.value(axis),
                    oracle.losses.value(axis),
                )
                for fixed, oracle in zip(fixed_rows, oracle_rows, strict=True)
            ]
            lower_bound = _cluster_bootstrap_bound(
                paired,
                probability=corrected_alpha,
                resamples=protocol.statistical_policy.bootstrap_resamples,
                seed=(
                    protocol.statistical_policy.bootstrap_seed
                    + budget_index * len(protocol.quality_axes)
                    + axis_index
                ),
            )
            relative_lower_bound = _cluster_bootstrap_relative_improvement_lower_bound(
                paired_levels,
                alpha=corrected_alpha,
                resamples=protocol.statistical_policy.bootstrap_resamples,
                seed=(
                    protocol.statistical_policy.bootstrap_seed
                    + 5_000
                    + budget_index * len(protocol.quality_axes)
                    + axis_index
                ),
            )
            other_axis_deltas: dict[str, float] = {}
            other_axis_upper_bounds: dict[str, float] = {}
            for other_index, other in enumerate(protocol.quality_axes):
                if other is axis:
                    continue
                other_axis_deltas[other.value] = _household_equal_mean(
                    oracle_rows, other
                ) - _household_equal_mean(fixed_rows, other)
                other_pairs = [
                    (
                        fixed.household_id,
                        oracle.losses.value(other) - fixed.losses.value(other),
                    )
                    for fixed, oracle in zip(fixed_rows, oracle_rows, strict=True)
                ]
                other_axis_upper_bounds[other.value] = _cluster_bootstrap_bound(
                    other_pairs,
                    probability=1.0 - corrected_alpha,
                    resamples=protocol.statistical_policy.bootstrap_resamples,
                    seed=(
                        protocol.statistical_policy.bootstrap_seed
                        + 10_000
                        + budget_index * len(protocol.quality_axes) ** 2
                        + axis_index * len(protocol.quality_axes)
                        + other_index
                    ),
                )
            noninferior = all(
                upper_bound <= protocol.statistical_policy.other_axis_noninferiority_margin
                for upper_bound in other_axis_upper_bounds.values()
            )
            household_equal_winner_shares = _household_equal_winner_shares(
                strict_winners,
                context_household_ids=context_household_ids,
                route_ids=tuple(protocol.path_by_id),
            )
            winner_share_lower_bounds = {
                route_id: _cluster_bootstrap_bound(
                    [
                        (household_id, float(winner == route_id))
                        for household_id, winner in strict_winners
                    ],
                    probability=corrected_alpha,
                    resamples=protocol.statistical_policy.bootstrap_resamples,
                    seed=(
                        protocol.statistical_policy.bootstrap_seed
                        + 20_000
                        + budget_index * len(protocol.quality_axes) * len(protocol.legal_paths)
                        + axis_index * len(protocol.legal_paths)
                        + route_priority[route_id]
                    ),
                )
                for route_id in protocol.path_by_id
            }
            qualifying_winners = sorted(
                route_id
                for route_id, share in household_equal_winner_shares.items()
                if share >= protocol.statistical_policy.minimum_winning_path_share
                and winner_share_lower_bounds[route_id]
                >= protocol.statistical_policy.minimum_winning_path_share
            )
            diverse = (
                len(qualifying_winners)
                >= protocol.statistical_policy.minimum_distinct_winning_paths
            )
            diagnostic_positive = bool(
                improvement >= protocol.statistical_policy.minimum_absolute_improvement
                and relative_improvement >= protocol.statistical_policy.minimum_relative_improvement
                and lower_bound >= protocol.statistical_policy.minimum_absolute_improvement
                and relative_lower_bound >= protocol.statistical_policy.minimum_relative_improvement
                and noninferior
                and diverse
            )
            diagnostic_positive_comparisons += int(diagnostic_positive)
            comparisons.append(
                {
                    "budget_id": budget.budget_id,
                    "quality_axis": axis.value,
                    "status": "EVALUATED",
                    "validation_selected_best_fixed_path": best_fixed,
                    "validation_best_fixed_mean_loss": validation_scores[best_fixed],
                    "confirmatory_best_fixed_mean_loss": fixed_mean,
                    "confirmatory_hindsight_oracle_mean_loss": oracle_mean,
                    "absolute_improvement": improvement,
                    "relative_improvement": relative_improvement,
                    "bonferroni_one_sided_bootstrap_lower_bound": lower_bound,
                    "relative_improvement_bonferroni_one_sided_lower_bound": (relative_lower_bound),
                    "other_axis_oracle_minus_fixed": other_axis_deltas,
                    "other_axis_bonferroni_one_sided_upper_bounds": (other_axis_upper_bounds),
                    "other_axis_noninferior": noninferior,
                    "oracle_winner_counts": dict(sorted(winner_counts.items())),
                    "oracle_household_equal_strict_winner_shares": (household_equal_winner_shares),
                    "oracle_strict_winner_share_bonferroni_lower_bounds": (
                        winner_share_lower_bounds
                    ),
                    "qualifying_distinct_winning_paths": qualifying_winners,
                    "winner_diversity_passed": diverse,
                    "caller_controlled_positive_headroom_candidate": diagnostic_positive,
                    "source_bound_positive_headroom": False,
                }
            )

    diagnostic_headroom = diagnostic_positive_comparisons > 0
    expected_comparisons = len(protocol.resource_budget_points) * len(protocol.quality_axes)
    all_comparisons_evaluable = evaluated_comparisons == expected_comparisons
    if not evaluated_comparisons:
        disposition = PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    elif diagnostic_headroom:
        disposition = (
            PreDeathDisposition.CALLER_CONTROLLED_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING
        )
    elif not all_comparisons_evaluable:
        disposition = PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    else:
        disposition = (
            PreDeathDisposition.CALLER_CONTROLLED_NO_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_content_sha256": evidence.protocol_content_sha256,
        "evidence_content_sha256": content_sha256(evidence.model_dump(mode="json")),
        "evidence_status": "CALLER_CONTROLLED_DEVELOPMENT_MATRIX",
        "disposition": disposition.value,
        "hard_guardrail_violations": [],
        "validation_household_count": len({key[1] for key in validation_groups}),
        "confirmatory_household_count": len({key[1] for key in confirmatory_groups}),
        "registered_path_ids": list(protocol.path_by_id),
        "quality_axes": [axis.value for axis in protocol.quality_axes],
        "resource_budget_ids": [budget.budget_id for budget in protocol.resource_budget_points],
        "multiplicity_family_size": family_count,
        "multiplicity_adjusted_one_sided_alpha": corrected_alpha,
        "bootstrap_tail_draw_count": math.floor(
            protocol.statistical_policy.bootstrap_resamples * corrected_alpha
        ),
        "gate1_router_overhead_accounting": {
            "hindsight_oracle_router_overhead_ratio": 0.0,
            "best_fixed_router_overhead_ratio": 0.0,
            "observable_gate_must_charge_recorded_router_overhead": True,
        },
        "confirmatory_oracle_estimator": "LEAVE_ONE_REPLICATE_SEED_OUT_CROSS_FIT",
        "recovery_p95_estimand": "WITHIN_HOUSEHOLD_MAX_THEN_HOUSEHOLD_EQUAL_P95_BY_SPLIT",
        "comparisons": comparisons,
        "expected_comparison_count": expected_comparisons,
        "evaluated_comparison_count": evaluated_comparisons,
        "all_comparisons_evaluable": all_comparisons_evaluable,
        "diagnostic_positive_comparison_count": diagnostic_positive_comparisons,
        "positive_comparison_count": 0,
        "caller_controlled_hindsight_headroom_candidate": diagnostic_headroom,
        "source_bound_hindsight_headroom_established": False,
        "hindsight_headroom_present": False,
        "hindsight_headroom_claim_authorized": False,
        "adaptive_routing_kill_authorized": False,
        "observable_policy_gate_candidate": False,
        "observable_policy_training_authorized": False,
        "seven_operator_scope_retained": True,
        "seven_operator_ablation_authorized": False,
        "deployable_router_established": False,
        "scientific_superiority_established": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    report["content_sha256"] = content_sha256(report)
    return report


def _architecture_a_interface_selection_is_declared(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    del repository_root
    return bool(
        protocol.execution_binding_status.production_execution_plan_interface
        == "SELECTED_A_IMMUTABLE_PLAN_AND_TRACE_SINK"
    )


def _symbol_source_matches_repository_file(
    symbol: Any,
    *,
    repository_root: Path,
    expected_source: Path,
) -> bool:
    try:
        loaded_source = inspect.getsourcefile(symbol)
        repository_source = _repository_file(repository_root, expected_source)
    except (OSError, TypeError, ValueError):
        return False
    return loaded_source is not None and Path(loaded_source).resolve() == repository_source


def _optional_keyword_parameter_is_bound(
    entrypoint: Any,
    *,
    name: str,
    annotation_symbol: str,
) -> bool:
    try:
        parameter = inspect.signature(entrypoint).parameters.get(name)
    except (TypeError, ValueError):
        return False
    return bool(
        parameter is not None
        and parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is None
        and annotation_symbol in str(parameter.annotation)
        and "None" in str(parameter.annotation)
    )


def _immutable_execution_plan_contract_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    expected_source = Path("src/cpswm/system/structure_two_execution.py")
    if (
        protocol.prerequisite_sources.production_execution_contract != expected_source
        or not _symbol_source_matches_repository_file(
            StructureTwoExecutionPlan,
            repository_root=repository_root,
            expected_source=expected_source,
        )
    ):
        return False
    if StructureTwoExecutionPlan.model_config.get("frozen") is not True:
        return False
    legacy = canonical_legacy_ordinary_transition_plan()
    if (
        legacy.plan_id != LEGACY_PLAN_ID
        or legacy.lane != "legacy_ordinary_transition"
        or legacy.scientific_evidence_authorized is not False
    ):
        return False
    for entrypoint in (
        StructureTwoProductionSystem.process_transition,
        CorePrototypeSpine.process_transition,
    ):
        if not _optional_keyword_parameter_is_bound(
            entrypoint,
            name="execution_plan",
            annotation_symbol="StructureTwoExecutionPlan",
        ):
            return False
    return True


def _trace_sink_contract_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    expected_source = Path("src/cpswm/system/structure_two_execution.py")
    source_bound_symbols = (TraceSink, TraceCommitAck, TraceAbortAck)
    if (
        protocol.prerequisite_sources.production_execution_contract != expected_source
        or not all(
            _symbol_source_matches_repository_file(
                symbol,
                repository_root=repository_root,
                expected_source=expected_source,
            )
            for symbol in source_bound_symbols
        )
        or getattr(TraceSink, "_is_runtime_protocol", False) is not True
        or TraceCommitAck.model_config.get("frozen") is not True
        or TraceAbortAck.model_config.get("frozen") is not True
    ):
        return False
    try:
        commit = inspect.signature(TraceSink.commit)
        abort = inspect.signature(TraceSink.abort)
    except (TypeError, ValueError):
        return False
    commit_parameters = tuple(commit.parameters.values())
    abort_parameters = tuple(abort.parameters.values())
    if (
        len(commit_parameters) != 2
        or commit_parameters[1].name != "trace"
        or commit_parameters[1].kind is not inspect.Parameter.POSITIONAL_ONLY
        or str(commit.return_annotation) != "TraceCommitAck"
        or len(abort_parameters) != 3
        or abort_parameters[1].name != "trace"
        or abort_parameters[1].kind is not inspect.Parameter.POSITIONAL_ONLY
        or abort_parameters[2].name != "reason"
        or abort_parameters[2].kind is not inspect.Parameter.KEYWORD_ONLY
        or str(abort.return_annotation) != "TraceAbortAck"
    ):
        return False
    return all(
        _optional_keyword_parameter_is_bound(
            entrypoint,
            name="trace_sink",
            annotation_symbol="TraceSink",
        )
        for entrypoint in (
            StructureTwoProductionSystem.process_transition,
            CorePrototypeSpine.process_transition,
        )
    )


def _attribute_chain(node: ast.expr) -> tuple[str, ...] | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def _is_none_identity_check(node: ast.expr, name: str) -> bool:
    return bool(
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == name
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Is)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _is_both_execution_arguments_omitted(node: ast.expr) -> bool:
    if (
        not isinstance(node, ast.BoolOp)
        or not isinstance(node.op, ast.And)
        or len(node.values) != 2
    ):
        return False
    return {
        name
        for name in ("execution_plan", "trace_sink")
        if any(_is_none_identity_check(value, name) for value in node.values)
    } == {"execution_plan", "trace_sink"}


def _method_has_legacy_return(
    method: Any,
    *,
    target: tuple[str, ...],
) -> bool:
    try:
        module = ast.parse(textwrap.dedent(inspect.getsource(method)))
    except (IndentationError, OSError, SyntaxError, TypeError):
        return False

    def is_target_return(statement: ast.stmt) -> bool:
        if isinstance(statement, ast.Try):
            return any(is_target_return(child) for child in statement.body)
        if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
            return False
        call = statement.value
        return bool(
            _attribute_chain(call.func) == target
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "transition"
            and not call.keywords
        )

    for node in ast.walk(module):
        if not isinstance(node, ast.If) or not _is_both_execution_arguments_omitted(node.test):
            continue
        if any(is_target_return(statement) for statement in node.body):
            return True
    return False


def _legacy_no_plan_no_trace_call_shape_is_preserved(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    if (
        not _symbol_source_matches_repository_file(
            StructureTwoProductionSystem.process_transition,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
        or not _symbol_source_matches_repository_file(
            CorePrototypeSpine.process_transition,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.prototype_spine,
        )
        or not _symbol_source_matches_repository_file(
            CorePrototypeSpine._process_transition_with_runtime_binding,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.prototype_spine,
        )
        or not _symbol_source_matches_repository_file(
            CorePrototypeSpine._process_transition_with_runtime_binding_locked,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.prototype_spine,
        )
    ):
        return False
    for entrypoint in (
        StructureTwoProductionSystem.process_transition,
        CorePrototypeSpine.process_transition,
    ):
        if not all(
            _optional_keyword_parameter_is_bound(
                entrypoint,
                name=name,
                annotation_symbol=annotation,
            )
            for name, annotation in (
                ("execution_plan", "StructureTwoExecutionPlan"),
                ("trace_sink", "TraceSink"),
            )
        ):
            return False
    return bool(
        _method_has_legacy_return(
            StructureTwoProductionSystem.process_transition,
            target=("self", "core", "process_transition"),
        )
        and _method_has_legacy_return(
            CorePrototypeSpine._process_transition_with_runtime_binding_locked,
            target=("self", "_process_transition"),
        )
    )


def _required_keyword_parameter_is_bound(
    entrypoint: Any,
    *,
    name: str,
    annotation_symbol: str,
) -> bool:
    try:
        parameter = inspect.signature(entrypoint).parameters.get(name)
    except (TypeError, ValueError):
        return False
    return bool(
        parameter is not None
        and parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        and annotation_symbol in str(parameter.annotation)
    )


def _adaptive_runtime_bindings_are_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    adaptive_source = Path("src/cpswm/system/structure_two_adaptive_runtime.py")
    if protocol.prerequisite_sources.adaptive_runtime != adaptive_source:
        return False
    if not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=adaptive_source,
        )
        for symbol in (
            AdaptiveAuthorizationPolicy,
            AdaptiveExecutionContext,
            AdaptiveRouterFeatures,
            select_adaptive_path,
        )
    ):
        return False
    if not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
        for symbol in (
            StructureTwoProductionSystem.process_adaptive_transition,
            StructureTwoProductionSystem.replay_adaptive_debt,
        )
    ):
        return False
    if AdaptiveAuthorizationPolicy.model_config.get("frozen") is not True:
        return False
    if not all(
        isinstance(registry, MappingProxyType)
        for registry in (
            REGISTERED_ADAPTIVE_PATH_MODES,
            LEGACY_CONSUMPTION_GRAPH,
            ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS,
            ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH,
        )
    ) or not all(
        isinstance(graph, MappingProxyType)
        for graph in ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS.values()
    ):
        return False
    if not all(
        _required_keyword_parameter_is_bound(
            StructureTwoProductionSystem.process_adaptive_transition,
            name=name,
            annotation_symbol=annotation,
        )
        for name, annotation in (
            ("context", "AdaptiveExecutionContext"),
            ("trace_sink", "TraceSink"),
        )
    ):
        return False
    if not _required_keyword_parameter_is_bound(
        StructureTwoProductionSystem.replay_adaptive_debt,
        name="trace_sink",
        annotation_symbol="TraceSink",
    ):
        return False
    for path_id in REQUIRED_PATH_IDS:
        plan = registered_adaptive_execution_plan(path_id)
        expected_modes = tuple(mode.value for mode in EXPECTED_PATH_MODES[path_id])
        if (
            plan.plan_id != path_id
            or plan.lane != "registered_adaptive_path"
            or tuple(item.mode for item in plan.operator_directives) != expected_modes
            or REGISTERED_ADAPTIVE_PATH_MODES.get(path_id) != expected_modes
        ):
            return False
    return True


def _production_router_feature_extractor_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    """Require a production-owned extractor, not only caller feature hashes."""

    if (
        protocol.execution_binding_status.path_eligibility_policy
        != "BOUND_TO_LOCAL_PRODUCTION_STATE"
    ):
        return False
    extractor = getattr(
        StructureTwoProductionSystem,
        "build_adaptive_router_features",
        None,
    )
    return bool(
        extractor is not None
        and _symbol_source_matches_repository_file(
            extractor,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
    )


def _adaptive_operator_elapsed_accounting_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    if not _symbol_source_matches_repository_file(
        RuntimeOperatorInvocationReceipt,
        repository_root=repository_root,
        expected_source=protocol.prerequisite_sources.production_execution_contract,
    ):
        return False
    if "elapsed_ns" not in RuntimeOperatorInvocationReceipt.model_fields:
        return False
    if not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
        for symbol in (
            StructureTwoProductionSystem._execute_adaptive_plan,
            StructureTwoProductionSystem._execute_p0_safe_deferred,
            StructureTwoProductionSystem._adaptive_step_result,
        )
    ):
        return False
    try:
        core_source = inspect.getsource(CorePrototypeSpine._process_transition)
        adaptive_source = inspect.getsource(StructureTwoProductionSystem._execute_adaptive_plan)
        p0_source = inspect.getsource(StructureTwoProductionSystem._execute_p0_safe_deferred)
        result_source = inspect.getsource(StructureTwoProductionSystem._adaptive_step_result)
    except (OSError, TypeError):
        return False
    return bool(
        "perf_counter_ns" in core_source
        and "elapsed_ns=" in core_source
        and adaptive_source.count("elapsed_ns=perf_counter_ns() - started_ns") >= 2
        and p0_source.count("elapsed_ns=perf_counter_ns() - started_ns") >= 2
        and "receipt.elapsed_ns" in result_source
        and "elapsed_ns_by_operator=elapsed" in result_source
    )


def _adaptive_resource_accounting_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
    production_router_feature_extractor_bound: bool,
) -> bool:
    """Require full pre-path overhead, not only per-operator wall-clock receipts."""

    return bool(
        protocol.execution_binding_status.resource_accountant
        == "BOUND_TO_LOCAL_PRODUCTION_EXECUTION"
        and production_router_feature_extractor_bound
        and _adaptive_operator_elapsed_accounting_is_source_bound(
            protocol=protocol,
            repository_root=repository_root,
        )
        and {
            "feature_extraction_elapsed_ns",
            "router_selection_elapsed_ns",
        }
        <= set(AdaptiveStepResult.__dataclass_fields__)
        and {
            "adaptive_feature_extraction_elapsed_ns",
            "adaptive_router_selection_elapsed_ns",
        }
        <= set(StructureTwoExecutionTrace.model_fields)
    )


def _adaptive_caller_context_snapshot_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    """Require both public adaptive entrypoints to detach caller-owned context."""

    expected_source = protocol.prerequisite_sources.production_system
    methods_and_tokens = (
        (
            StructureTwoProductionSystem.process_adaptive_transition,
            "_snapshot_adaptive_context(context)",
        ),
        (
            StructureTwoProductionSystem.process_transition,
            "_snapshot_adaptive_context(adaptive_context)",
        ),
        (
            StructureTwoProductionSystem.replay_adaptive_debt,
            "_snapshot_adaptive_ciav_input(ciav_input)",
        ),
    )
    try:
        return all(
            _symbol_source_matches_repository_file(
                method,
                repository_root=repository_root,
                expected_source=expected_source,
            )
            and token in inspect.getsource(method)
            for method, token in methods_and_tokens
        )
    except (OSError, TypeError):
        return False


def _pending_debt_core_transition_barrier_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    """Bind the narrow core-transition barrier without claiming wrapper freeze."""

    production_symbols = (
        StructureTwoProductionSystem.__init__,
        StructureTwoProductionSystem._require_core_public_mutation_permission,
    )
    core_symbols = (
        CorePrototypeSpine._require_external_mutation_permission,
        CorePrototypeSpine._process_transition_with_runtime_binding_locked,
        CorePrototypeSpine.apply_fast_action_verification,
    )
    if not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
        for symbol in production_symbols
    ) or not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.prototype_spine,
        )
        for symbol in core_symbols
    ):
        return False
    try:
        init_source = inspect.getsource(StructureTwoProductionSystem.__init__)
        guard_source = inspect.getsource(
            StructureTwoProductionSystem._require_core_public_mutation_permission
        )
        core_entry_source = inspect.getsource(
            CorePrototypeSpine._process_transition_with_runtime_binding_locked
        )
        public_mutator_source = inspect.getsource(CorePrototypeSpine.apply_fast_action_verification)
    except (OSError, TypeError):
        return False
    return bool(
        "_external_mutation_guard" in init_source
        and "AdaptiveDebtStatus.PENDING" in guard_source
        and "pending adaptive debt blocks" in guard_source
        and "_require_external_mutation_permission()" in core_entry_source
        and "@_serialized_core_mutation" in public_mutator_source
    )


def _isolated_adaptive_replay_entrypoint_is_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    """Bind the narrow replay entrypoint, not recovery or origin-policy equivalence."""

    method = StructureTwoProductionSystem.replay_adaptive_debt
    if not _symbol_source_matches_repository_file(
        method,
        repository_root=repository_root,
        expected_source=protocol.prerequisite_sources.production_system,
    ):
        return False
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    return bool(
        "AdaptiveDebtStatus.PENDING" in source
        and "post_origin_core_state_sha256" in source
        and "P5_FULL_EAGER" in source
        and "_adaptive_replay_authorized_debt_ids" in source
        and _required_keyword_parameter_is_bound(
            method,
            name="trace_sink",
            annotation_symbol="TraceSink",
        )
    )


def _ciav_detected_feedback_branches_are_source_bound(
    *,
    protocol: AdaptiveComputePreDeathProtocol,
    repository_root: Path,
) -> bool:
    """Recognize only the implemented detected-observation closure branches."""

    production_symbols = (
        StructureTwoProductionSystem._execute_adaptive_plan,
        StructureTwoProductionSystem._ciav_feedback_transition,
    )
    if not all(
        _symbol_source_matches_repository_file(
            symbol,
            repository_root=repository_root,
            expected_source=protocol.prerequisite_sources.production_system,
        )
        for symbol in production_symbols
    ) or not _symbol_source_matches_repository_file(
        StructureTwoExecutionTrace._validate_adaptive_trace,
        repository_root=repository_root,
        expected_source=protocol.prerequisite_sources.production_execution_contract,
    ):
        return False
    try:
        execution_source = inspect.getsource(StructureTwoProductionSystem._execute_adaptive_plan)
        feedback_source = inspect.getsource(StructureTwoProductionSystem._ciav_feedback_transition)
        trace_source = inspect.getsource(StructureTwoExecutionTrace._validate_adaptive_trace)
    except (OSError, TypeError):
        return False
    return bool(
        "ObservationOutcome.DETECTED" in execution_source
        and "same_location_fast_verification" in execution_source
        and "_ciav_feedback_transition" in execution_source
        and "feedback_result = self.core._process_transition" in execution_source
        and "only a detected CIAV observation" in feedback_source
        and "full_transition" in trace_source
        and "same_location_fast_verification" in trace_source
        and "adaptive feedback closure operator order drifted" in trace_source
    )


def run_adaptive_compute_predeath_readiness(*, repository_root: Path) -> dict[str, Any]:
    """Freshly audit whether real production shadow execution may begin."""

    root = repository_root.resolve()
    protocol = load_adaptive_compute_predeath_protocol(root)
    selected_path = _repository_file(root, protocol.prerequisite_sources.selected_method_receipt)
    selected = StructureTwoSelectedMethod.load(selected_path)
    selected_operators = tuple(operator.value for operator in selected.operators)
    complete_selected_scope = bool(
        len(selected_operators) == len(PRODUCTION_OPERATOR_ORDER)
        and set(selected_operators) == set(PRODUCTION_OPERATOR_ORDER)
    )
    protocol_operator_order = tuple(operator.value for operator in protocol.operator_order)
    protocol_order_matches_production = protocol_operator_order == PRODUCTION_OPERATOR_ORDER

    # Recompute both local validity gates from current sources.  The saved
    # action artifact is intentionally not trusted because source-bound claim
    # text can drift while an old JSON remains internally self-consistent.
    action_gate = run_action_utility_construct_gate(repository_root=root)
    runtime_gate = run_runtime_identity_gate_audit(repository_root=root)
    task9 = load_task9_protocol(root, protocol.prerequisite_sources.task9_protocol)

    action_construct_passed = bool(action_gate["action_utility_construct_gate_passed"])
    historical_route_c_runtime_identity_passed = bool(runtime_gate["runtime_identity_gate_passed"])
    task9_still_definition_only = bool(
        task9.definition_status.value == "DEFINED_NOT_RUN" and not task9.task9_result_available
    )
    population_binding_matches_task9 = bool(
        protocol.population_binding.validation_household_ids
        == task9.population_commitment.validation_household_ids
        and protocol.population_binding.confirmatory_household_ids
        == task9.population_commitment.confirmatory_household_ids
        and protocol.population_binding.replicate_seeds
        == task9.population_commitment.replicate_seeds
    )

    # Architecture A now has a local production host for the exact P0--P5 plan
    # registry and partial kernels.  Registry/source binding alone does not
    # establish distinct path semantics or the full legal executor.
    adaptive_runtime_bindings_source_bound = _adaptive_runtime_bindings_are_source_bound(
        protocol=protocol,
        repository_root=root,
    )
    legal_path_executor_bound_to_production_runtime = bool(
        adaptive_runtime_bindings_source_bound
        and protocol.execution_binding_status.legal_path_executor == "BOUND_TO_PRODUCTION_RUNTIME"
    )
    production_execution_plan_interface_selected = _architecture_a_interface_selection_is_declared(
        protocol=protocol,
        repository_root=root,
    )
    immutable_execution_plan_contract_source_bound = (
        _immutable_execution_plan_contract_is_source_bound(
            protocol=protocol,
            repository_root=root,
        )
    )
    trace_sink_contract_source_bound = _trace_sink_contract_is_source_bound(
        protocol=protocol,
        repository_root=root,
    )
    legacy_no_plan_no_trace_call_shape_preserved = _legacy_no_plan_no_trace_call_shape_is_preserved(
        protocol=protocol,
        repository_root=root,
    )
    caller_context_snapshot_source_bound = _adaptive_caller_context_snapshot_is_source_bound(
        protocol=protocol,
        repository_root=root,
    )
    pending_debt_core_transition_barrier_source_bound = (
        _pending_debt_core_transition_barrier_is_source_bound(
            protocol=protocol,
            repository_root=root,
        )
    )
    isolated_replay_entrypoint_source_bound = _isolated_adaptive_replay_entrypoint_is_source_bound(
        protocol=protocol,
        repository_root=root,
    )
    detected_ciav_feedback_branches_source_bound = (
        _ciav_detected_feedback_branches_are_source_bound(
            protocol=protocol,
            repository_root=root,
        )
    )
    # A typed sink acknowledgement and compensating abort protocol do not prove
    # one durable transaction across runtime state and an external trace store.
    cross_system_trace_state_atomicity_established = False
    # This is the consequential runtime-identity gate for the *new* P0--P5
    # execution lane.  It is intentionally distinct from the retained Route-C
    # v0.2 diagnostic above: the historical artifact is expected to remain
    # stale and must not make future Architecture-A shadow readiness
    # unreachable forever.
    production_router_feature_extractor_bound = (
        _production_router_feature_extractor_is_source_bound(
            protocol=protocol,
            repository_root=root,
        )
    )
    p0_p5_consequential_runtime_identity_established = bool(
        legal_path_executor_bound_to_production_runtime
        and production_router_feature_extractor_bound
        and protocol.execution_binding_status.p0_p5_consequential_runtime_identity
        == "ESTABLISHED_D0_LOCAL_RUNTIME"
        and {
            "adaptive_router_feature_sha256",
            "adaptive_authorization_policy_sha256",
            "adaptive_path_selection_receipt_sha256",
            "adaptive_ciav_input_sha256",
            "feedback_closure_kind",
        }
        <= set(StructureTwoExecutionTrace.model_fields)
    )
    path_specific_operator_budgets_bound = False
    branch_point_manifest_bound = False
    path_eligibility_policy_bound_to_production_state = bool(
        production_router_feature_extractor_bound
        and "authorization_policy_sha256" in AdaptiveRouterFeatures.model_fields
        and hasattr(StructureTwoProductionSystem, "bind_adaptive_authorization_policy")
    )
    debt_replay_verifier_bound_to_production_replay = False
    power_analysis_bound_to_empirical_variance_and_icc = False
    confirmatory_access_custody_bound = False
    exogenous_rng_source_bound_to_production_execution = False
    resource_accountant_bound_to_production_execution = (
        _adaptive_resource_accounting_is_source_bound(
            protocol=protocol,
            repository_root=root,
            production_router_feature_extractor_bound=(production_router_feature_extractor_bound),
        )
    )
    long_horizon_loss_bound_to_production_actions = False
    readiness_requirement_results = {
        "selected_method_operator_inventory_covers_production_registry": (complete_selected_scope),
        "protocol_operator_order_matches_production_dag": protocol_order_matches_production,
        "fresh_typed_action_utility_construct_gate_passed": action_construct_passed,
        "population_seed_split_binding_matches_task9": population_binding_matches_task9,
        "task9_remains_definition_only": task9_still_definition_only,
        "production_execution_plan_interface_selected": (
            production_execution_plan_interface_selected
        ),
        "immutable_execution_plan_contract_source_bound": (
            immutable_execution_plan_contract_source_bound
        ),
        "trace_sink_contract_source_bound": trace_sink_contract_source_bound,
        "legacy_no_plan_no_trace_call_shape_preserved": (
            legacy_no_plan_no_trace_call_shape_preserved
        ),
        "cross_system_trace_state_atomicity_established": (
            cross_system_trace_state_atomicity_established
        ),
        "path_specific_operator_budgets_bound": path_specific_operator_budgets_bound,
        "frozen_branch_point_manifest_bound": branch_point_manifest_bound,
        "path_eligibility_policy_bound_to_production_state": (
            path_eligibility_policy_bound_to_production_state
        ),
        "debt_replay_verifier_bound_to_production_replay": (
            debt_replay_verifier_bound_to_production_replay
        ),
        "power_analysis_bound_to_empirical_variance_and_icc": (
            power_analysis_bound_to_empirical_variance_and_icc
        ),
        "confirmatory_access_custody_bound": confirmatory_access_custody_bound,
        "exogenous_rng_source_bound_to_production_execution": (
            exogenous_rng_source_bound_to_production_execution
        ),
        "legal_path_executor_bound_to_production_runtime": (
            legal_path_executor_bound_to_production_runtime
        ),
        "p0_p5_consequential_runtime_identity_established": (
            p0_p5_consequential_runtime_identity_established
        ),
        "resource_accountant_bound_to_production_execution": (
            resource_accountant_bound_to_production_execution
        ),
        "long_horizon_loss_bound_to_production_actions": (
            long_horizon_loss_bound_to_production_actions
        ),
    }
    ready, status, blockers, next_required_work = _readiness_outcome(readiness_requirement_results)
    config_path = _repository_file(root, DEFAULT_CONFIG)
    runner_path = _repository_file(root, DEFAULT_RUNNER)
    implementation_path = Path(__file__).resolve()
    execution_contract_path = _repository_file(
        root, protocol.prerequisite_sources.production_execution_contract
    )
    adaptive_runtime_path = _repository_file(root, protocol.prerequisite_sources.adaptive_runtime)
    production_system_path = _repository_file(root, protocol.prerequisite_sources.production_system)
    prototype_spine_path = _repository_file(root, protocol.prerequisite_sources.prototype_spine)
    regime_loop_path = _repository_file(root, protocol.prerequisite_sources.regime_loop)
    source_bindings = {
        "protocol_config": {
            "path": str(DEFAULT_CONFIG),
            "sha256": _file_sha256(config_path),
        },
        "implementation": {
            "path": str(implementation_path.relative_to(root)),
            "sha256": _file_sha256(implementation_path),
        },
        "runner": {
            "path": str(DEFAULT_RUNNER),
            "sha256": _file_sha256(runner_path),
        },
        "production_execution_contract": {
            "path": str(protocol.prerequisite_sources.production_execution_contract),
            "sha256": _file_sha256(execution_contract_path),
        },
        "adaptive_runtime": {
            "path": str(protocol.prerequisite_sources.adaptive_runtime),
            "sha256": _file_sha256(adaptive_runtime_path),
        },
        "production_system": {
            "path": str(protocol.prerequisite_sources.production_system),
            "sha256": _file_sha256(production_system_path),
        },
        "prototype_spine": {
            "path": str(protocol.prerequisite_sources.prototype_spine),
            "sha256": _file_sha256(prototype_spine_path),
        },
        "regime_loop": {
            "path": str(protocol.prerequisite_sources.regime_loop),
            "sha256": _file_sha256(regime_loop_path),
        },
        "selected_method_receipt": {
            "path": str(protocol.prerequisite_sources.selected_method_receipt),
            "file_sha256": _file_sha256(selected_path),
            "content_sha256": selected.content_sha256,
        },
        "fresh_action_construct_gate": {
            "config_path": str(protocol.prerequisite_sources.action_utility_construct_gate_config),
            "config_file_sha256": _file_sha256(
                _repository_file(
                    root,
                    protocol.prerequisite_sources.action_utility_construct_gate_config,
                )
            ),
            "protocol_id": action_gate["protocol_id"],
            "content_sha256": action_gate["content_sha256"],
        },
        "fresh_runtime_identity_gate": {
            "config_path": str(protocol.prerequisite_sources.runtime_identity_gate_config),
            "config_file_sha256": _file_sha256(
                _repository_file(
                    root,
                    protocol.prerequisite_sources.runtime_identity_gate_config,
                )
            ),
            "protocol_id": runtime_gate["protocol_id"],
            "content_sha256": runtime_gate["content_sha256"],
        },
        "task9_protocol": {
            "path": str(protocol.prerequisite_sources.task9_protocol),
            "file_sha256": _file_sha256(
                _repository_file(root, protocol.prerequisite_sources.task9_protocol)
            ),
        },
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": status,
        "evidence_level": protocol.evidence_level,
        "source_bindings": source_bindings,
        "scope_audit": {
            "selected_method_id": selected.method_id,
            "selected_method_operators": list(selected_operators),
            "selected_method_operator_inventory_covers_production_registry": (
                complete_selected_scope
            ),
            "protocol_operator_order": list(protocol_operator_order),
            "protocol_operator_order_matches_production_dag": (protocol_order_matches_production),
            "registered_path_ids": list(protocol.path_by_id),
            "all_registered_path_specs_require_seven_operator_dispositions": all(
                path.all_seven_operator_receipts_required for path in protocol.legal_paths
            ),
            "complete_selected_scope_retained": complete_selected_scope,
            "seven_operator_ablation_authorized": False,
        },
        "retained_historical_diagnostics": {
            "fresh_historical_route_c_runtime_identity_gate_passed": (
                historical_route_c_runtime_identity_passed
            ),
            "used_as_current_shadow_readiness_blocker": False,
            "interpretation": (
                "Route-C v0.2 remains a retained historical identity diagnostic. "
                "Its expected failure does not negate the selected Architecture-A "
                "interface or the current partial P0--P5 control-flow lane. The current "
                "lane has its own failed consequential-identity requirement."
            ),
        },
        "local_adaptive_runtime_diagnostics": {
            "transitively_immutable_six_plan_registry_bound": (
                adaptive_runtime_bindings_source_bound
            ),
            "production_router_feature_extractor_bound": (
                production_router_feature_extractor_bound
            ),
            "path_specific_compute_kernels_bound": False,
            "registered_failure_fallback_state_machine_bound": False,
            "executed_operator_wallclock_receipts_bound": (
                _adaptive_operator_elapsed_accounting_is_source_bound(
                    protocol=protocol,
                    repository_root=root,
                )
            ),
            "full_adaptive_resource_accounting_bound": (
                resource_accountant_bound_to_production_execution
            ),
            "caller_context_snapshot_source_bound": caller_context_snapshot_source_bound,
            "pending_debt_core_transition_barrier_source_bound": (
                pending_debt_core_transition_barrier_source_bound
            ),
            "pending_debt_all_wrapper_mutations_barrier_bound": False,
            "isolated_replay_entrypoint_source_bound": isolated_replay_entrypoint_source_bound,
            "different_location_detected_full_ciav_closure_source_bound": (
                detected_ciav_feedback_branches_source_bound
            ),
            "same_location_detected_fast_verification_source_bound": (
                detected_ciav_feedback_branches_source_bound
            ),
            "negative_observation_full_ciav_closure_source_bound": False,
            "full_ciav_outcome_closure_bound": False,
            "recovery_equivalence_established": False,
            "independent_authorization_custody_established": False,
            "interpretation": (
                "The immutable P0--P5 plan registry, partial control-flow kernels, local "
                "authorization policy, different-location detected full CIAV closure, "
                "same-location detected fast verification, isolated debt-replay entrypoint, "
                "caller-context snapshot, pending-debt core-transition barrier, and executed "
                "operator wall-clock receipts are source-bound. The barrier does not freeze all "
                "wrapper rebindings, replay does not bind origin policy/trace, and a negative "
                "CIAV observation has no complete downstream closure. Production-owned "
                "router-feature extraction, six distinct path kernels, registered failure "
                "fallback, full resource accounting, eager-reference recovery equivalence, "
                "independent custody, and scientific benefit are not."
            ),
        },
        "prerequisite_gates": {
            "fresh_typed_action_utility_construct_gate_passed": action_construct_passed,
            "task9_remains_definition_only": task9_still_definition_only,
            "population_seed_split_binding_matches_task9": population_binding_matches_task9,
            "production_execution_plan_interface_selected": (
                production_execution_plan_interface_selected
            ),
            "immutable_execution_plan_contract_source_bound": (
                immutable_execution_plan_contract_source_bound
            ),
            "trace_sink_contract_source_bound": trace_sink_contract_source_bound,
            "legacy_no_plan_no_trace_call_shape_preserved": (
                legacy_no_plan_no_trace_call_shape_preserved
            ),
            "cross_system_trace_state_atomicity_established": (
                cross_system_trace_state_atomicity_established
            ),
            "path_specific_operator_budgets_bound": path_specific_operator_budgets_bound,
            "frozen_branch_point_manifest_bound": branch_point_manifest_bound,
            "path_eligibility_policy_bound_to_production_state": (
                path_eligibility_policy_bound_to_production_state
            ),
            "debt_replay_verifier_bound_to_production_replay": (
                debt_replay_verifier_bound_to_production_replay
            ),
            "power_analysis_bound_to_empirical_variance_and_icc": (
                power_analysis_bound_to_empirical_variance_and_icc
            ),
            "confirmatory_access_custody_bound": confirmatory_access_custody_bound,
            "exogenous_rng_source_bound_to_production_execution": (
                exogenous_rng_source_bound_to_production_execution
            ),
            "legal_path_executor_bound_to_production_runtime": (
                legal_path_executor_bound_to_production_runtime
            ),
            "p0_p5_consequential_runtime_identity_established": (
                p0_p5_consequential_runtime_identity_established
            ),
            "resource_accountant_bound_to_production_execution": (
                resource_accountant_bound_to_production_execution
            ),
            "long_horizon_loss_bound_to_production_actions": (
                long_horizon_loss_bound_to_production_actions
            ),
        },
        "readiness_requirement_results": readiness_requirement_results,
        "blocking_reasons": blockers,
        "shadow_execution_authorized": ready,
        "caller_controlled_evaluator_can_promote_or_kill": False,
        "hindsight_headroom_claim_authorized": False,
        "observable_policy_training_authorized": False,
        "deployable_router_established": False,
        "scientific_superiority_established": False,
        "independent_custody_established": False,
        "next_required_work": next_required_work,
        "post_shadow_requirements_before_router_training": [
            "complete common-random-number shadow matrix",
            "pass the registered observable-policy gate with full router overhead",
        ],
        "claim_boundary": protocol.claim_boundary,
    }
    report["content_sha256"] = content_sha256(report)
    return report


def verify_adaptive_compute_predeath_readiness(
    report: Mapping[str, Any],
    *,
    repository_root: Path,
) -> None:
    """Regenerate the readiness report; self-consistent caller rehashing is insufficient."""

    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or stored != content_sha256(unsigned):
        raise ValueError("adaptive-compute readiness content hash mismatch")
    expected = run_adaptive_compute_predeath_readiness(repository_root=repository_root)
    if dict(report) != expected:
        raise ValueError("adaptive-compute readiness differs from fresh source-bound audit")


def verify_hindsight_headroom_report(
    report: Mapping[str, Any],
    *,
    evidence: ShadowMatrixEvidence,
    protocol: AdaptiveComputePreDeathProtocol,
) -> None:
    """Re-evaluate a caller-controlled shadow matrix and reject report rewriting."""

    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or stored != content_sha256(unsigned):
        raise ValueError("adaptive-compute headroom report content hash mismatch")
    expected = evaluate_hindsight_headroom(evidence, protocol)
    if dict(report) != expected:
        raise ValueError("adaptive-compute headroom report differs from fresh evaluation")


__all__ = [
    "FULL_EAGER_PATH_ID",
    "AdaptiveComputePreDeathProtocol",
    "DebtResolutionReceipt",
    "DebtStatus",
    "EvidenceSplit",
    "ForcedEscalationCause",
    "ForcedEscalationStage",
    "HardConstraintOutcome",
    "InferenceDebtCertificate",
    "LegalPathSpec",
    "MemoryTransitionKind",
    "OperatorExecutionMode",
    "OperatorInvocationReceipt",
    "PathEligibilityOutcome",
    "PreDeathDisposition",
    "PreResolutionAction",
    "QualityAxis",
    "QualityLossVector",
    "ResourceVector",
    "ShadowMatrixEvidence",
    "ShadowRunRecord",
    "evaluate_hindsight_headroom",
    "load_adaptive_compute_predeath_protocol",
    "required_debt_replay_order",
    "run_adaptive_compute_predeath_readiness",
    "validate_shadow_matrix",
    "verify_adaptive_compute_predeath_readiness",
    "verify_hindsight_headroom_report",
]
