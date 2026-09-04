"""Independent protocol contracts for Structure Two Tasks 11--13 and P5.

These contracts define work that has not yet been run.  They deliberately do
not implement an SMC method, select a binding, or authorize a positive claim.
Each task owns a different estimand, nuisance-binding schema, result schema,
and claim boundary so evidence from one task cannot be relabelled as another.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, Probability
from cpswm.system.reproducibility import content_sha256

SCHEMA_VERSION = "0.1.0"
PROTOCOL_PACK_ID = "structure-two-backbone-open-tasks@0.1"
SELECTED_METHOD_ID = "structure-two-nap-rbtpr-rc@0.1"
SELECTED_METHOD_RECEIPT_CONTENT_SHA256 = (
    "a3ccafd6612a6ee57a855e82572524622b6f15f305924b3de99bd3e94e17ed2f"
)

TASK11_PROTOCOL_ID = "structure-two-backbone-resampling-task-11@0.1"
TASK12_PROTOCOL_ID = "structure-two-backbone-rejuvenation-task-12@0.1"
TASK13_PROTOCOL_ID = "structure-two-backbone-differentiability-task-13@0.1"
P5_PROTOCOL_ID = "structure-two-backbone-proposal-headroom-p5@0.1"

TASK11_ESTIMAND = (
    "paired_delta_action_loss_per_elementary_evaluation_with_exact_posterior_fidelity_guardrail"
)
TASK12_ESTIMAND = (
    "conditional_window_kernel_effective_sample_size_per_elementary_evaluation_"
    "with_invariance_guardrail"
)
TASK13_ESTIMAND = (
    "sealed_holdout_action_loss_delta_per_training_compute_with_gradient_validity_guardrail"
)
P5_ESTIMAND = (
    "oracle_minus_deployable_full_chain_truth_compatible_recall_decomposed_by_pipeline_stage"
)

TASK11_CLAIM_BOUNDARY = (
    "Task 11 may locally nominate only a diagnostic resampling_policy candidate; formal "
    "resolution requires an enrolled independent outer authority with custody, freshness, "
    "and replay verification. It does not validate Gate B, seven-operator benefit, or "
    "paper-level superiority."
)
TASK12_CLAIM_BOUNDARY = (
    "Task 12 may locally nominate only a diagnostic rejuvenation_kernel candidate; formal "
    "resolution requires an enrolled independent outer authority with custody, freshness, "
    "and replay verification. Task 7 supplies window, checkpoint, outside-window, and "
    "fallback semantics only and cannot select this kernel."
)
TASK13_CLAIM_BOUNDARY = (
    "Task 13 may locally nominate only a diagnostic differentiability_strategy candidate; "
    "formal resolution requires an enrolled independent outer authority with custody, "
    "freshness, and replay verification. It cannot resolve training_schedule or proposer "
    "architecture, validate Gate B, or authorize paper-level superiority."
)
P5_CLAIM_BOUNDARY = (
    "P5 is evaluator-only proposal-headroom diagnosis; it cannot resolve a method binding, "
    "select a neural architecture, validate Gate B or seven-operator benefit, or authorize "
    "deployable or paper-level claims."
)
LOCAL_BINDING_DIAGNOSTIC_CLAIM_BOUNDARY = (
    "Caller-supplied result agreement is diagnostic only. No local object resolves a "
    "binding. Formal resolution requires a future enrolled independent outer authority "
    "with custody, freshness, and replay verification."
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
FiniteNonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key in open-task config: {key}")
        payload[key] = value
    return payload


class DefinitionStatus(StrEnum):
    DEFINED_NOT_RUN = "DEFINED_NOT_RUN"


class ResolvableTaskId(StrEnum):
    TASK_11 = "TASK_11"
    TASK_12 = "TASK_12"
    TASK_13 = "TASK_13"


class RuntimeTaskId(StrEnum):
    TASK_11 = "TASK_11"
    TASK_12 = "TASK_12"
    TASK_13 = "TASK_13"
    PROPOSAL_P5 = "backbone.proposal.P5"


class ResolvableBinding(StrEnum):
    RESAMPLING_POLICY = "resampling_policy"
    REJUVENATION_KERNEL = "rejuvenation_kernel"
    DIFFERENTIABILITY_STRATEGY = "differentiability_strategy"


class BindingRunDisposition(StrEnum):
    RAN_INELIGIBLE = "RAN_INELIGIBLE"
    RAN_ELIGIBLE_NO_SELECTION = "RAN_ELIGIBLE_NO_SELECTION"
    RAN_ELIGIBLE_SELECTION = "RAN_ELIGIBLE_SELECTION"


class ResamplingAlgorithm(StrEnum):
    NONE = "no_resampling"
    SYSTEMATIC = "systematic"
    STRATIFIED = "stratified"
    RESIDUAL = "residual"
    MULTINOMIAL_NEGATIVE_CONTROL = "multinomial_negative_control"


class Task11Metric(StrEnum):
    PRIMARY_ACTION_LOSS_DELTA_PER_EVALUATION = "paired_action_loss_delta_per_elementary_evaluation"
    ESS_TRAJECTORY = "ess_trajectory"
    RESAMPLING_EVENT_INDICES = "resampling_event_indices"
    UNIQUE_PARENT_COUNT = "unique_parent_count"
    UNIQUE_ROOT_ANCESTOR_COUNT = "unique_root_ancestor_count"
    UNKNOWN_SUPPORT_BEFORE_AFTER = "unknown_support_before_after"
    UNRESOLVED_MASS_BEFORE_AFTER = "unresolved_mass_before_after"
    LOG_NORMALIZER_BIAS = "log_normalizer_bias"
    POSTERIOR_TOTAL_VARIATION = "posterior_total_variation"
    ACTION_POSTERIOR_DISTANCE = "action_posterior_distance"
    OWNER_CONTAMINATION = "owner_contamination"
    ELEMENTARY_EVALUATIONS = "elementary_evaluations"
    WALL_CLOCK_SECONDS = "wall_clock_seconds"


class Task11CorrectnessGate(StrEnum):
    FINITE_NORMALIZED_WEIGHTS = "finite_normalized_weights"
    TOY_DISTRIBUTION_FREQUENCY = "toy_distribution_frequency"
    LINEAGE_PARENT_RECORDED = "lineage_parent_recorded"
    FINAL_STEP_NOT_RESAMPLED = "final_step_not_resampled"
    UNKNOWN_UNRESOLVED_SUPPORT_REPORTED = "unknown_unresolved_support_reported"
    RUNTIME_POLICY_TRACE_CHANGES = "runtime_policy_trace_changes"
    NO_ORACLE_ACCESS = "no_oracle_access"


TASK11_ALGORITHMS = tuple(ResamplingAlgorithm)
TASK11_METRICS = tuple(Task11Metric)
TASK11_GATES = tuple(Task11CorrectnessGate)
TASK11_NUISANCE_FIELDS = (
    "particle_budget",
    "proposal_kernel",
    "rejuvenation_kernel",
    "differentiability_strategy",
    "training_schedule",
)


class Task11NuisanceBindings(ContractModel):
    particle_budget: Literal["task_10_resolution_receipt"]
    proposal_kernel: Literal["frozen_backbone_proposal_held_constant"]
    rejuvenation_kernel: Literal["disabled_for_task_11"]
    differentiability_strategy: Literal["not_applicable_inference_only"]
    training_schedule: Literal["not_applicable_inference_only"]


class Task11SelectionRule(ContractModel):
    objective: Literal["minimize_primary_estimand"]
    max_posterior_total_variation: FiniteNonNegativeFloat
    max_owner_contamination: FiniteNonNegativeFloat
    max_absolute_log_normalizer_bias: FiniteNonNegativeFloat
    tie_tolerance: FiniteNonNegativeFloat
    negative_control_selectable: Literal[False]

    @model_validator(mode="after")
    def _freeze_thresholds(self) -> Self:
        if (
            self.max_posterior_total_variation,
            self.max_owner_contamination,
            self.max_absolute_log_normalizer_bias,
            self.tie_tolerance,
        ) != (0.05, 0.05, 0.05, 1e-12):
            raise ValueError("Task 11 selection thresholds are frozen")
        return self


class Task11ResamplingSpec(ContractModel):
    schema_version: Literal["0.1.0"]
    task_id: Literal["TASK_11"]
    protocol_id: Literal["structure-two-backbone-resampling-task-11@0.1"]
    definition_status: Literal["DEFINED_NOT_RUN"]
    target_binding: Literal["resampling_policy"]
    scientific_question: str = Field(min_length=24)
    primary_estimand: Literal[
        "paired_delta_action_loss_per_elementary_evaluation_with_exact_posterior_fidelity_guardrail"
    ]
    algorithms: tuple[ResamplingAlgorithm, ...] = Field(min_length=1)
    validation_only_ess_thresholds: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    never_resample_final_step: Literal[True]
    support_handling: Literal["measure_only_unless_importance_corrected"]
    evaluation_unit: Literal["scenario_seed_cluster"]
    nuisance_bindings: Task11NuisanceBindings
    selection_rule: Task11SelectionRule
    required_outputs: tuple[Task11Metric, ...] = Field(min_length=1)
    correctness_gates: tuple[Task11CorrectnessGate, ...] = Field(min_length=1)
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _freeze_task_11(self) -> Self:
        if self.algorithms != TASK11_ALGORITHMS:
            raise ValueError("Task 11 must retain every preregistered resampling arm in order")
        thresholds = self.validation_only_ess_thresholds
        if thresholds != (0.25, 0.5, 0.75):
            raise ValueError("Task 11 ESS thresholds are frozen")
        if thresholds != tuple(sorted(set(thresholds))):
            raise ValueError("Task 11 ESS thresholds must be unique and increasing")
        if any(value <= 0.0 or value >= 1.0 for value in thresholds):
            raise ValueError("Task 11 ESS thresholds must lie strictly inside (0, 1)")
        if self.required_outputs != TASK11_METRICS:
            raise ValueError("Task 11 required outputs cannot be narrowed or reordered")
        if self.correctness_gates != TASK11_GATES:
            raise ValueError("Task 11 correctness gates cannot be narrowed or reordered")
        if self.claim_boundary != TASK11_CLAIM_BOUNDARY:
            raise ValueError("Task 11 claim boundary is frozen")
        return self


class RejuvenationKernelCandidate(StrEnum):
    NONE = "no_rejuvenation"
    SINGLE_SITE_TYPED_MH = "single_site_typed_metropolis_hastings"
    BLOCKED_TYPED_MH = "blocked_typed_metropolis_hastings"
    EXACT_CONDITIONAL_GIBBS_EVALUATOR_ONLY = "exact_conditional_gibbs_evaluator_only"


class Task12Metric(StrEnum):
    DETAILED_BALANCE_ERROR = "detailed_balance_error"
    STATIONARY_DISTRIBUTION_ERROR = "stationary_distribution_error"
    PROPOSAL_COUNT = "proposal_count"
    ACCEPTANCE_COUNT = "acceptance_count"
    ACCEPTANCE_RATE = "acceptance_rate"
    AXIS_JUMP_DISTANCE = "axis_jump_distance_H_R_I_C_Z"
    AUTOCORRELATION = "autocorrelation"
    EFFECTIVE_SAMPLE_SIZE_PER_EVALUATION = "effective_sample_size_per_elementary_evaluation"
    UNIQUE_ANCESTRY = "unique_ancestry"
    FULL_RERUN_ACTOR_MARGINAL_DISTANCE = "full_rerun_actor_marginal_distance"
    RECOVERY = "late_correction_recovery"
    OWNER_CONTAMINATION = "owner_contamination"
    UNRESOLVED_MASS = "unresolved_mass"
    FALLBACK_COUNT_AND_REASONS = "fallback_count_and_reasons"
    WINDOW_TOUCHED_INDICES = "window_touched_indices"


class Task12CorrectnessGate(StrEnum):
    CONDITIONAL_TARGET_INVARIANCE = "conditional_target_invariance"
    FORWARD_REVERSE_DENSITIES = "forward_reverse_proposal_densities"
    STATE_MACHINE_REACHABILITY = "state_machine_reachability"
    OUTSIDE_WINDOW_BYTE_EQUALITY = "outside_window_byte_equality"
    ANALYTIC_BLOCK_REBUILT = "analytic_block_rebuilt"
    ORACLE_CONFINED_TO_EVALUATOR = "oracle_confined_to_evaluator"
    ZERO_AND_FULL_ACCEPT_PATHS = "zero_and_full_accept_paths"


TASK12_KERNELS = tuple(RejuvenationKernelCandidate)
TASK12_METRICS = tuple(Task12Metric)
TASK12_GATES = tuple(Task12CorrectnessGate)
TASK12_FORBIDDEN_SUBSTITUTES = (
    "task_7_window_semantics",
    "full_suffix_rerun",
)
TASK12_NUISANCE_FIELDS = (
    "particle_budget",
    "resampling_policy",
    "proposal_kernel",
    "late_correction_window_semantics",
    "differentiability_strategy",
    "training_schedule",
)


class Task12NuisanceBindings(ContractModel):
    particle_budget: Literal["task_10_resolution_receipt"]
    resampling_policy: Literal["task_11_resolution_receipt"]
    proposal_kernel: Literal["frozen_backbone_proposal_held_constant"]
    late_correction_window_semantics: Literal[
        "task_7_defines_window_checkpoint_outside_window_and_fallback_only"
    ]
    differentiability_strategy: Literal["not_applicable_inference_only"]
    training_schedule: Literal["not_applicable_inference_only"]


class Task12SelectionRule(ContractModel):
    objective: Literal["maximize_primary_estimand"]
    max_detailed_balance_error: FiniteNonNegativeFloat
    max_stationary_distribution_error: FiniteNonNegativeFloat
    max_full_rerun_actor_marginal_distance: FiniteNonNegativeFloat
    max_owner_contamination: FiniteNonNegativeFloat
    tie_tolerance: FiniteNonNegativeFloat
    evaluator_oracle_selectable: Literal[False]

    @model_validator(mode="after")
    def _freeze_thresholds(self) -> Self:
        if (
            self.max_detailed_balance_error,
            self.max_stationary_distribution_error,
            self.max_full_rerun_actor_marginal_distance,
            self.max_owner_contamination,
            self.tie_tolerance,
        ) != (1e-9, 1e-6, 0.05, 0.05, 1e-12):
            raise ValueError("Task 12 selection thresholds are frozen")
        return self


class Task12RejuvenationSpec(ContractModel):
    schema_version: Literal["0.1.0"]
    task_id: Literal["TASK_12"]
    protocol_id: Literal["structure-two-backbone-rejuvenation-task-12@0.1"]
    definition_status: Literal["DEFINED_NOT_RUN"]
    target_binding: Literal["rejuvenation_kernel"]
    scientific_question: str = Field(min_length=24)
    primary_estimand: Literal[
        "conditional_window_kernel_effective_sample_size_per_elementary_evaluation_"
        "with_invariance_guardrail"
    ]
    conditional_target: Literal["full_chain_posterior_conditioned_on_outside_window"]
    candidate_kernels: tuple[RejuvenationKernelCandidate, ...] = Field(min_length=1)
    exact_oracle_max_gaps: Literal[2]
    task_7_boundary: Literal["task_7_defines_window_checkpoint_outside_window_and_fallback_only"]
    kernel_selection_authority: Literal["task_12_only"]
    forbidden_evidence_substitutes: tuple[str, ...] = Field(min_length=1)
    nuisance_bindings: Task12NuisanceBindings
    selection_rule: Task12SelectionRule
    required_outputs: tuple[Task12Metric, ...] = Field(min_length=1)
    correctness_gates: tuple[Task12CorrectnessGate, ...] = Field(min_length=1)
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _freeze_task_12(self) -> Self:
        if self.candidate_kernels != TASK12_KERNELS:
            raise ValueError("Task 12 must retain every preregistered kernel in order")
        if self.forbidden_evidence_substitutes != TASK12_FORBIDDEN_SUBSTITUTES:
            raise ValueError(
                "Task 7 semantics and full rerun must remain Task 12 non-kernel controls"
            )
        if self.required_outputs != TASK12_METRICS:
            raise ValueError("Task 12 required outputs cannot be narrowed or reordered")
        if self.correctness_gates != TASK12_GATES:
            raise ValueError("Task 12 correctness gates cannot be narrowed or reordered")
        if self.claim_boundary != TASK12_CLAIM_BOUNDARY:
            raise ValueError("Task 12 claim boundary is frozen")
        return self


class DifferentiabilityStrategy(StrEnum):
    STOP_GRADIENT_SUPERVISED = "stop_gradient_supervised_proposal"
    SCORE_FUNCTION_UNBIASED = "score_function_unbiased_estimator"
    RELAXED_PATHWISE_BIASED = "relaxed_pathwise_resampling_biased"


class Task13Metric(StrEnum):
    PRIMARY_ACTION_LOSS_DELTA_PER_TRAINING_COMPUTE = "paired_action_loss_delta_per_training_compute"
    FINITE_DIFFERENCE_GRADIENT_ERROR = "finite_difference_gradient_error"
    EXPECTATION_GRADIENT_ERROR = "exact_expectation_gradient_error"
    GRADIENT_BIAS = "gradient_bias"
    GRADIENT_VARIANCE = "gradient_variance"
    GRADIENT_NORM = "gradient_norm"
    NONFINITE_GRADIENT_COUNT = "nonfinite_gradient_count"
    HARD_CONSTRAINT_VIOLATIONS = "hard_constraint_violations"
    UNKNOWN_SUPPORT_RETENTION = "unknown_support_retention"
    UNRESOLVED_MASS_RETENTION = "unresolved_mass_retention"
    INFERENCE_TARGET_HASH_EQUALITY = "inference_target_hash_equality"
    LEARNING_CURVE_PER_COMPUTE = "learning_curve_per_training_compute"
    HOLDOUT_PROPOSAL_RECALL = "holdout_truth_compatible_proposal_recall"
    POSTERIOR_TOTAL_VARIATION = "posterior_total_variation"
    ACTION_LOSS = "action_loss"


class Task13CorrectnessGate(StrEnum):
    TINY_EXACT_GRADIENT_CHECK = "tiny_exact_gradient_check"
    FINITE_GRADIENTS = "finite_gradients"
    HARD_CONSTRAINTS_PRESERVED = "hard_constraints_preserved"
    INFERENCE_SEMANTICS_UNCHANGED = "inference_semantics_unchanged"
    SEALED_HOLDOUT_UNSEEN_DURING_SELECTION = "sealed_holdout_unseen_during_selection"
    PROPOSER_HAS_NO_COMMIT_AUTHORITY = "proposer_has_no_commit_authority"
    RUNTIME_STRATEGY_TRACE_CHANGES = "runtime_strategy_trace_changes"


TASK13_STRATEGIES = tuple(DifferentiabilityStrategy)
TASK13_METRICS = tuple(Task13Metric)
TASK13_GATES = tuple(Task13CorrectnessGate)
TASK13_EXCLUDED_BINDINGS = (
    "training_schedule",
    "neural_proposer_architecture",
)
TASK13_NUISANCE_FIELDS = (
    "particle_budget",
    "resampling_policy",
    "rejuvenation_kernel",
    "proposal_architecture",
    "training_schedule",
    "optimizer",
    "training_compute_budget",
)


class Task13NuisanceBindings(ContractModel):
    particle_budget: Literal["task_10_resolution_receipt"]
    resampling_policy: Literal["task_11_resolution_receipt"]
    rejuvenation_kernel: Literal["task_12_resolution_receipt"]
    proposal_architecture: Literal["preregistered_fixed_architecture_receipt"]
    training_schedule: Literal["fixed_nuisance_not_a_task_13_arm"]
    optimizer: Literal["fixed_nuisance_not_a_task_13_arm"]
    training_compute_budget: Literal["equal_across_task_13_arms"]


class Task13SelectionRule(ContractModel):
    objective: Literal["minimize_primary_estimand"]
    maximum_primary_estimand_for_improvement: FiniteFloat
    max_finite_difference_gradient_error: FiniteNonNegativeFloat
    max_exact_expectation_gradient_error: FiniteNonNegativeFloat
    max_posterior_total_variation: FiniteNonNegativeFloat
    tie_tolerance: FiniteNonNegativeFloat

    @model_validator(mode="after")
    def _freeze_thresholds(self) -> Self:
        if (
            self.maximum_primary_estimand_for_improvement,
            self.max_finite_difference_gradient_error,
            self.max_exact_expectation_gradient_error,
            self.max_posterior_total_variation,
            self.tie_tolerance,
        ) != (0.0, 0.05, 0.05, 0.10, 1e-12):
            raise ValueError("Task 13 selection thresholds are frozen")
        return self


class Task13DifferentiabilitySpec(ContractModel):
    schema_version: Literal["0.1.0"]
    task_id: Literal["TASK_13"]
    protocol_id: Literal["structure-two-backbone-differentiability-task-13@0.1"]
    definition_status: Literal["DEFINED_NOT_RUN"]
    target_binding: Literal["differentiability_strategy"]
    scientific_question: str = Field(min_length=24)
    primary_estimand: Literal[
        "sealed_holdout_action_loss_delta_per_training_compute_with_gradient_validity_guardrail"
    ]
    strategies: tuple[DifferentiabilityStrategy, ...] = Field(min_length=1)
    controlled_variable: Literal["gradient_estimator_only"]
    explicitly_excluded_bindings: tuple[str, ...] = Field(min_length=1)
    nuisance_bindings: Task13NuisanceBindings
    selection_rule: Task13SelectionRule
    required_outputs: tuple[Task13Metric, ...] = Field(min_length=1)
    correctness_gates: tuple[Task13CorrectnessGate, ...] = Field(min_length=1)
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _freeze_task_13(self) -> Self:
        if self.strategies != TASK13_STRATEGIES:
            raise ValueError("Task 13 must retain every preregistered gradient strategy in order")
        if self.explicitly_excluded_bindings != TASK13_EXCLUDED_BINDINGS:
            raise ValueError("Task 13 cannot absorb training schedule or proposer architecture")
        if self.required_outputs != TASK13_METRICS:
            raise ValueError("Task 13 required outputs cannot be narrowed or reordered")
        if self.correctness_gates != TASK13_GATES:
            raise ValueError("Task 13 correctness gates cannot be narrowed or reordered")
        if self.claim_boundary != TASK13_CLAIM_BOUNDARY:
            raise ValueError("Task 13 claim boundary is frozen")
        return self


class ProposalHeadroomArm(StrEnum):
    BOOTSTRAP = "bootstrap_proposal"
    DETERMINISTIC_TYPED = "deterministic_adaptive_typed_proposal"
    LOCAL_CONDITIONAL_ORACLE = "local_conditional_posterior_oracle_evaluator_only"
    TRUTH_INCLUSION_ORACLE = "truth_inclusion_top_k_oracle_evaluator_only"


class ProposalPipelineStage(StrEnum):
    RAW_CANDIDATE = "raw_candidate_generation"
    HARD_CONSTRAINT_SURVIVAL = "hard_constraint_survival"
    WEIGHTED_SUPPORT = "weighted_support"
    RESAMPLING_SURVIVAL = "resampling_survival"
    FINAL_CHAIN_SUPPORT = "final_chain_support"


class P5Diagnosis(StrEnum):
    NO_PROPOSAL_HEADROOM = "NO_PROPOSAL_HEADROOM"
    PROPOSAL_BOTTLENECK = "PROPOSAL_BOTTLENECK"
    DOWNSTREAM_WEIGHTING_OR_RESAMPLING_BOTTLENECK = "DOWNSTREAM_WEIGHTING_OR_RESAMPLING_BOTTLENECK"
    MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK = "MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK"
    READOUT_INCONCLUSIVE = "READOUT_INCONCLUSIVE"


class ParticleAxis(StrEnum):
    EVENT_CHAIN = "H"
    ACTOR_ROLE = "R"
    INSTANCE = "I"
    CHANGE_CAUSE = "C"
    REGIME = "Z"


class ProposalOperation(StrEnum):
    BRANCH = "branch"
    REVISE = "revise"
    RETRACT = "retract"
    REACTIVATE = "reactivate"
    REJUVENATE = "rejuvenate"
    PRESERVE_UNRESOLVED = "preserve_unresolved"


class P5Metric(StrEnum):
    RECOMPUTED_STAGE_HEADROOM = "recomputed_stage_headroom"
    RECOMPUTED_DIAGNOSIS = "recomputed_diagnosis"
    FULL_CHAIN_TOP_K_RECALL = "full_chain_truth_compatible_top_k_recall"
    POSTERIOR_MASS_COVERAGE = "posterior_mass_coverage"
    AXIS_RECALL = "axis_recall_H_R_I_C_Z"
    OPERATION_RECALL = "proposal_operation_recall"
    UNKNOWN_SUPPORT_RETENTION = "unknown_support_retention"
    UNRESOLVED_MASS_RETENTION = "unresolved_mass_retention"
    ACTION_CONSEQUENCE = "action_consequence"
    ELEMENTARY_EVALUATIONS = "elementary_evaluations"
    TRUTH_READ_COUNT = "truth_read_count"
    EXACT_ENUMERATION_COUNT = "exact_enumeration_count"


P5_ARMS = tuple(ProposalHeadroomArm)
P5_STAGES = tuple(ProposalPipelineStage)
P5_DIAGNOSES = tuple(P5Diagnosis)
P5_METRICS = tuple(P5Metric)
P5_FORBIDDEN_OUTPUTS = (
    "passed",
    "binding_resolution",
    "paper_claim_authorization",
    "architecture_selection",
)
P5_NUISANCE_FIELDS = (
    "particle_budget",
    "resampling_policy",
    "rejuvenation_kernel",
    "structured_weighting",
    "action_readout",
    "differentiability_strategy",
    "training_schedule",
)


class P5NuisanceBindings(ContractModel):
    particle_budget: Literal["task_10_resolution_receipt"]
    resampling_policy: Literal["task_11_resolution_receipt"]
    rejuvenation_kernel: Literal["task_12_resolution_receipt"]
    structured_weighting: Literal["frozen_identical_across_p5_arms"]
    action_readout: Literal["frozen_identical_across_p5_arms"]
    differentiability_strategy: Literal["not_applicable_diagnostic_only"]
    training_schedule: Literal["not_applicable_diagnostic_only"]


class P5DiagnosisRule(ContractModel):
    recall_headroom_epsilon: FiniteNonNegativeFloat
    action_gain_epsilon: FiniteNonNegativeFloat
    decision_order: tuple[
        Literal["no_headroom"],
        Literal["readout_inconclusive"],
        Literal["raw_proposal_gap"],
        Literal["downstream_gap"],
    ]

    @model_validator(mode="after")
    def _freeze_thresholds(self) -> Self:
        if (self.recall_headroom_epsilon, self.action_gain_epsilon) != (0.01, 0.0):
            raise ValueError("P5 diagnosis thresholds are frozen")
        return self


class TaskP5ProposalHeadroomSpec(ContractModel):
    schema_version: Literal["0.1.0"]
    task_id: Literal["backbone.proposal.P5"]
    protocol_id: Literal["structure-two-backbone-proposal-headroom-p5@0.1"]
    definition_status: Literal["DEFINED_NOT_RUN"]
    authority: Literal["diagnosis_only_no_binding_resolution"]
    scientific_question: str = Field(min_length=24)
    primary_estimand: Literal[
        "oracle_minus_deployable_full_chain_truth_compatible_recall_decomposed_by_pipeline_stage"
    ]
    arms: tuple[ProposalHeadroomArm, ...] = Field(min_length=1)
    pipeline_stages: tuple[ProposalPipelineStage, ...] = Field(min_length=1)
    verdict_space: tuple[P5Diagnosis, ...] = Field(min_length=1)
    forbidden_outputs: tuple[str, ...] = Field(min_length=1)
    nuisance_bindings: P5NuisanceBindings
    diagnosis_rule: P5DiagnosisRule
    required_outputs: tuple[P5Metric, ...] = Field(min_length=1)
    oracle_access: Literal["evaluator_only_logged_and_counted"]
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _freeze_p5(self) -> Self:
        if self.arms != P5_ARMS:
            raise ValueError("P5 must retain every preregistered proposal arm in order")
        if self.pipeline_stages != P5_STAGES:
            raise ValueError("P5 recall decomposition must cover every pipeline stage in order")
        if self.verdict_space != P5_DIAGNOSES:
            raise ValueError("P5 verdicts must remain exhaustive and mutually exclusive")
        if self.forbidden_outputs != P5_FORBIDDEN_OUTPUTS:
            raise ValueError("P5 may not expose pass, resolution, claim, or architecture authority")
        if self.required_outputs != P5_METRICS:
            raise ValueError("P5 required outputs cannot be narrowed or reordered")
        if self.claim_boundary != P5_CLAIM_BOUNDARY:
            raise ValueError("P5 claim boundary is frozen")
        return self


class BindingResolutionAuthoritySpec(ContractModel):
    """Frozen absence of the authority needed to resolve a formal binding."""

    required: Literal[True]
    authority_role: Literal["independent_binding_resolution_custodian"]
    attestation_domain: Literal["cpswm.structure_two.backbone_binding_resolution.v1"]
    trust_anchor_status: Literal["NOT_ENROLLED"]
    trust_anchor_manifest_sha256: None = None
    outer_verifier_handle_schema: Literal["UNAVAILABLE_NOT_IMPLEMENTED"]
    local_verifier_may_issue_formal_resolution: Literal[False]
    external_freshness_and_replay_registry_required: Literal[True]


class StructureTwoBackboneOpenTaskProtocols(ContractModel):
    schema_version: Literal["0.1.0"]
    protocol_pack_id: Literal["structure-two-backbone-open-tasks@0.1"]
    selected_method_id: Literal["structure-two-nap-rbtpr-rc@0.1"]
    selected_method_receipt_content_sha256: Literal[
        "a3ccafd6612a6ee57a855e82572524622b6f15f305924b3de99bd3e94e17ed2f"
    ]
    definition_status: Literal["DEFINED_NOT_RUN"]
    seven_operator_ablation_authorized: Literal[False]
    binding_resolution_authority: BindingResolutionAuthoritySpec
    task_11: Task11ResamplingSpec
    task_12: Task12RejuvenationSpec
    task_13: Task13DifferentiabilitySpec
    proposal_p5: TaskP5ProposalHeadroomSpec

    @model_validator(mode="after")
    def _independent_protocols(self) -> Self:
        tasks = (self.task_11, self.task_12, self.task_13, self.proposal_p5)
        if any(item.definition_status != DefinitionStatus.DEFINED_NOT_RUN for item in tasks):
            raise ValueError("every open task must begin DEFINED_NOT_RUN")
        protocol_ids = tuple(item.protocol_id for item in tasks)
        if len(protocol_ids) != len(set(protocol_ids)):
            raise ValueError("open tasks require independent protocol ids")
        estimands = tuple(item.primary_estimand for item in tasks)
        if len(estimands) != len(set(estimands)):
            raise ValueError("open tasks require independent primary estimands")
        boundaries = tuple(item.claim_boundary for item in tasks)
        if len(boundaries) != len(set(boundaries)):
            raise ValueError("open tasks require independent claim boundaries")
        return self

    @classmethod
    def load(cls, path: Path) -> StructureTwoBackboneOpenTaskProtocols:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        if not isinstance(payload, dict):
            raise ValueError("open-task config must be a JSON object")
        return cls.model_validate(payload)

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class RuntimeBindingObservation(ContractModel):
    """One configured nuisance value observed at its actual runtime boundary."""

    binding: str = Field(min_length=1)
    configured_value: str = Field(min_length=1)
    observed_runtime_value: str = Field(min_length=1)
    runtime_trace_payload_sha256: Sha256

    @model_validator(mode="after")
    def _configured_value_reached_runtime(self) -> Self:
        if self.configured_value != self.observed_runtime_value:
            raise ValueError("configured nuisance value differs from observed runtime value")
        return self


class RuntimeBindingReceipt(ContractModel):
    """Verifier input bound to a spec/config/source tuple, never authority alone."""

    schema_version: Literal["0.2.0"]
    task_id: RuntimeTaskId
    protocol_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    observations: tuple[RuntimeBindingObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_complete_names(self) -> Self:
        required = {
            RuntimeTaskId.TASK_11: TASK11_NUISANCE_FIELDS,
            RuntimeTaskId.TASK_12: TASK12_NUISANCE_FIELDS,
            RuntimeTaskId.TASK_13: TASK13_NUISANCE_FIELDS,
            RuntimeTaskId.PROPOSAL_P5: P5_NUISANCE_FIELDS,
        }[self.task_id]
        supplied = tuple(item.binding for item in self.observations)
        if len(supplied) != len(set(supplied)) or set(supplied) != set(required):
            raise ValueError(
                f"{self.task_id.value} runtime nuisance coverage mismatch: "
                f"required={required}, supplied={supplied}"
            )
        return self


class Task11ArmPolicy(ContractModel):
    algorithm: ResamplingAlgorithm
    ess_fraction: float | None = Field(default=None, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _threshold_semantics(self) -> Self:
        if self.algorithm is ResamplingAlgorithm.NONE:
            if self.ess_fraction is not None:
                raise ValueError("no-resampling arm cannot carry an ESS threshold")
        elif self.ess_fraction is None:
            raise ValueError("a resampling arm requires an ESS fraction")
        return self

    @property
    def arm_key(self) -> str:
        if self.ess_fraction is None:
            return self.algorithm.value
        return f"{self.algorithm.value}@ess={self.ess_fraction:g}"


class Task11PolicySelection(Task11ArmPolicy):
    @model_validator(mode="after")
    def _deployable(self) -> Self:
        if self.algorithm is ResamplingAlgorithm.MULTINOMIAL_NEGATIVE_CONTROL:
            raise ValueError("the multinomial negative control cannot be selected for deployment")
        return self


class Task11GateOutcomes(ContractModel):
    finite_normalized_weights: bool
    toy_distribution_frequency: bool
    lineage_parent_recorded: bool
    final_step_not_resampled: bool
    unknown_unresolved_support_reported: bool
    runtime_policy_trace_changes: bool
    no_oracle_access: bool

    @property
    def all_passed(self) -> bool:
        return all(self.model_dump(mode="python").values())


class Task11ArmResult(ContractModel):
    policy: Task11ArmPolicy
    paired_action_loss_delta_per_elementary_evaluation: float = Field(allow_inf_nan=False)
    ess_trajectory: tuple[float, ...] = Field(min_length=1)
    resampling_event_indices: tuple[NonNegativeInt, ...]
    unique_parent_count: PositiveInt
    unique_root_ancestor_count: PositiveInt
    unknown_support_before: Probability
    unknown_support_after: Probability
    unresolved_mass_before: Probability
    unresolved_mass_after: Probability
    log_normalizer_bias: float = Field(allow_inf_nan=False)
    posterior_total_variation: Probability
    action_posterior_distance: Probability
    owner_contamination: Probability
    elementary_evaluations: PositiveInt
    wall_clock_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    gates: Task11GateOutcomes

    @model_validator(mode="after")
    def _metric_semantics(self) -> Self:
        if any(not 0.0 < value < float("inf") for value in self.ess_trajectory):
            raise ValueError("Task 11 ESS trajectory must be finite and positive")
        if self.policy.algorithm is ResamplingAlgorithm.NONE and self.resampling_event_indices:
            raise ValueError("no-resampling arm cannot report resampling events")
        return self


class Task11RunResult(ContractModel):
    schema_version: Literal["0.2.0"]
    protocol_id: Literal["structure-two-backbone-resampling-task-11@0.1"]
    primary_estimand: Literal[
        "paired_delta_action_loss_per_elementary_evaluation_with_exact_posterior_fidelity_guardrail"
    ]
    execution_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    runtime_binding_receipt: RuntimeBindingReceipt
    arm_results: tuple[Task11ArmResult, ...] = Field(min_length=1)
    disposition: BindingRunDisposition
    selected_policy: Task11PolicySelection | None = None
    authority: Literal["local_diagnostic_only_no_binding_resolution"]
    formal_binding_resolved: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: str

    @model_validator(mode="after")
    def _structural_completeness(self) -> Self:
        keys = tuple(item.policy.arm_key for item in self.arm_results)
        if len(keys) != len(set(keys)):
            raise ValueError("Task 11 arm results must have unique policy keys")
        expected_keys = [ResamplingAlgorithm.NONE.value]
        for algorithm in TASK11_ALGORITHMS:
            if algorithm is ResamplingAlgorithm.NONE:
                continue
            expected_keys.extend(
                Task11ArmPolicy(algorithm=algorithm, ess_fraction=threshold).arm_key
                for threshold in (0.25, 0.5, 0.75)
            )
        if keys != tuple(expected_keys):
            raise ValueError("Task 11 result must contain every preregistered arm in order")
        if self.runtime_binding_receipt.task_id is not RuntimeTaskId.TASK_11:
            raise ValueError("Task 11 result requires a Task 11 runtime receipt")
        if (
            self.execution_id,
            self.producer_id,
        ) != (
            self.runtime_binding_receipt.execution_id,
            self.runtime_binding_receipt.producer_id,
        ):
            raise ValueError("Task 11 result and runtime receipt execution identity differ")
        if self.claim_boundary != TASK11_CLAIM_BOUNDARY:
            raise ValueError("Task 11 result cannot widen its claim boundary")
        return self


class Task12GateOutcomes(ContractModel):
    conditional_target_invariance: bool
    forward_reverse_proposal_densities: bool
    state_machine_reachability: bool
    outside_window_byte_equality: bool
    analytic_block_rebuilt: bool
    oracle_confined_to_evaluator: bool
    zero_and_full_accept_paths: bool

    @property
    def all_passed(self) -> bool:
        return all(self.model_dump(mode="python").values())


class AxisJumpDistance(ContractModel):
    h: float = Field(ge=0.0, allow_inf_nan=False)
    r: float = Field(ge=0.0, allow_inf_nan=False)
    i: float = Field(ge=0.0, allow_inf_nan=False)
    c: float = Field(ge=0.0, allow_inf_nan=False)
    z: float = Field(ge=0.0, allow_inf_nan=False)


class Task12ArmResult(ContractModel):
    kernel: RejuvenationKernelCandidate
    detailed_balance_error: float = Field(ge=0.0, allow_inf_nan=False)
    stationary_distribution_error: float = Field(ge=0.0, allow_inf_nan=False)
    proposal_count: NonNegativeInt
    acceptance_count: NonNegativeInt
    acceptance_rate: Probability
    axis_jump_distance: AxisJumpDistance
    autocorrelation: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    effective_sample_size_per_elementary_evaluation: float = Field(ge=0.0, allow_inf_nan=False)
    unique_ancestry: PositiveInt
    full_rerun_actor_marginal_distance: Probability
    late_correction_recovery: Probability
    owner_contamination: Probability
    unresolved_mass: Probability
    fallback_count: NonNegativeInt
    fallback_reasons: tuple[str, ...]
    window_touched_indices: tuple[NonNegativeInt, ...]
    wall_clock_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    gates: Task12GateOutcomes

    @model_validator(mode="after")
    def _count_semantics(self) -> Self:
        if self.acceptance_count > self.proposal_count:
            raise ValueError("Task 12 acceptance count cannot exceed proposal count")
        expected_rate = self.acceptance_count / self.proposal_count if self.proposal_count else 0.0
        if abs(self.acceptance_rate - expected_rate) > 1e-12:
            raise ValueError("Task 12 acceptance rate must be derived from proposal counts")
        if self.kernel is RejuvenationKernelCandidate.NONE and (
            self.proposal_count or self.acceptance_count
        ):
            raise ValueError("no-rejuvenation arm cannot report Markov proposals")
        if self.fallback_count != len(self.fallback_reasons):
            raise ValueError("Task 12 fallback reasons must account for every fallback")
        return self


class Task12RunResult(ContractModel):
    schema_version: Literal["0.2.0"]
    protocol_id: Literal["structure-two-backbone-rejuvenation-task-12@0.1"]
    primary_estimand: Literal[
        "conditional_window_kernel_effective_sample_size_per_elementary_evaluation_"
        "with_invariance_guardrail"
    ]
    execution_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    runtime_binding_receipt: RuntimeBindingReceipt
    arm_results: tuple[Task12ArmResult, ...] = Field(min_length=1)
    disposition: BindingRunDisposition
    selected_kernel: RejuvenationKernelCandidate | None = None
    authority: Literal["local_diagnostic_only_no_binding_resolution"]
    formal_binding_resolved: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: str

    @model_validator(mode="after")
    def _structural_completeness(self) -> Self:
        kernels = tuple(item.kernel for item in self.arm_results)
        if len(kernels) != len(set(kernels)):
            raise ValueError("Task 12 arm results must have unique kernels")
        if kernels != TASK12_KERNELS:
            raise ValueError("Task 12 result must contain every preregistered kernel in order")
        if (
            self.selected_kernel
            is RejuvenationKernelCandidate.EXACT_CONDITIONAL_GIBBS_EVALUATOR_ONLY
        ):
            raise ValueError("Task 12 evaluator oracle cannot be selected as a deployable kernel")
        if self.runtime_binding_receipt.task_id is not RuntimeTaskId.TASK_12:
            raise ValueError("Task 12 result requires a Task 12 runtime receipt")
        if (
            self.execution_id,
            self.producer_id,
        ) != (
            self.runtime_binding_receipt.execution_id,
            self.runtime_binding_receipt.producer_id,
        ):
            raise ValueError("Task 12 result and runtime receipt execution identity differ")
        if self.claim_boundary != TASK12_CLAIM_BOUNDARY:
            raise ValueError("Task 12 result cannot widen its claim boundary")
        return self


class Task13GateOutcomes(ContractModel):
    tiny_exact_gradient_check: bool
    finite_gradients: bool
    hard_constraints_preserved: bool
    inference_semantics_unchanged: bool
    sealed_holdout_unseen_during_selection: bool
    proposer_has_no_commit_authority: bool
    runtime_strategy_trace_changes: bool

    @property
    def all_passed(self) -> bool:
        return all(self.model_dump(mode="python").values())


class Task13ArmResult(ContractModel):
    strategy: DifferentiabilityStrategy
    paired_action_loss_delta_per_training_compute: float = Field(allow_inf_nan=False)
    finite_difference_gradient_error: float = Field(ge=0.0, allow_inf_nan=False)
    exact_expectation_gradient_error: float = Field(ge=0.0, allow_inf_nan=False)
    gradient_bias: float = Field(allow_inf_nan=False)
    gradient_variance: float = Field(ge=0.0, allow_inf_nan=False)
    gradient_norm: float = Field(ge=0.0, allow_inf_nan=False)
    nonfinite_gradient_count: NonNegativeInt
    hard_constraint_violations: NonNegativeInt
    unknown_support_retention: Probability
    unresolved_mass_retention: Probability
    inference_target_sha256_before: Sha256
    inference_target_sha256_after: Sha256
    learning_curve_per_training_compute: tuple[float, ...] = Field(min_length=1)
    holdout_truth_compatible_proposal_recall: Probability
    posterior_total_variation: Probability
    action_loss: float = Field(ge=0.0, allow_inf_nan=False)
    wall_clock_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    gates: Task13GateOutcomes

    @model_validator(mode="after")
    def _trace_semantics(self) -> Self:
        if any(
            not float("-inf") < value < float("inf")
            for value in self.learning_curve_per_training_compute
        ):
            raise ValueError("Task 13 learning curve values must be finite")
        target_equal = self.inference_target_sha256_before == self.inference_target_sha256_after
        if target_equal != self.gates.inference_semantics_unchanged:
            raise ValueError("Task 13 inference target hashes must agree with the semantics gate")
        if (self.nonfinite_gradient_count == 0) != self.gates.finite_gradients:
            raise ValueError("Task 13 nonfinite count must agree with the finite-gradient gate")
        if (self.hard_constraint_violations == 0) != self.gates.hard_constraints_preserved:
            raise ValueError("Task 13 constraint count must agree with the constraint gate")
        return self


class Task13RunResult(ContractModel):
    schema_version: Literal["0.2.0"]
    protocol_id: Literal["structure-two-backbone-differentiability-task-13@0.1"]
    primary_estimand: Literal[
        "sealed_holdout_action_loss_delta_per_training_compute_with_gradient_validity_guardrail"
    ]
    execution_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    runtime_binding_receipt: RuntimeBindingReceipt
    arm_results: tuple[Task13ArmResult, ...] = Field(min_length=1)
    disposition: BindingRunDisposition
    selected_strategy: DifferentiabilityStrategy | None = None
    authority: Literal["local_diagnostic_only_no_binding_resolution"]
    formal_binding_resolved: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: str

    @model_validator(mode="after")
    def _structural_completeness(self) -> Self:
        strategies = tuple(item.strategy for item in self.arm_results)
        if len(strategies) != len(set(strategies)):
            raise ValueError("Task 13 arm results must have unique strategies")
        if strategies != TASK13_STRATEGIES:
            raise ValueError("Task 13 result must contain every preregistered strategy in order")
        if self.runtime_binding_receipt.task_id is not RuntimeTaskId.TASK_13:
            raise ValueError("Task 13 result requires a Task 13 runtime receipt")
        if (
            self.execution_id,
            self.producer_id,
        ) != (
            self.runtime_binding_receipt.execution_id,
            self.runtime_binding_receipt.producer_id,
        ):
            raise ValueError("Task 13 result and runtime receipt execution identity differ")
        if self.claim_boundary != TASK13_CLAIM_BOUNDARY:
            raise ValueError("Task 13 result cannot widen its claim boundary")
        return self


class BindingCandidateDiagnostic(ContractModel):
    """Non-authoritative local comparison; intentionally cannot resolve a binding."""

    schema_version: Literal["0.3.0"]
    source_task: ResolvableTaskId
    source_protocol_id: str
    source_result_status: Literal["RAN_ELIGIBLE_SELECTION"]
    candidate_binding: ResolvableBinding
    diagnostic_resampling_policy: Task11PolicySelection | None = None
    diagnostic_rejuvenation_kernel: RejuvenationKernelCandidate | None = None
    diagnostic_differentiability_strategy: DifferentiabilityStrategy | None = None
    reported_result_content_sha256: Sha256
    comparison_result_deterministic_sha256: Sha256
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    evidence_status: Literal["LOCAL_CALLER_PAIR_DIAGNOSTIC_ONLY"]
    enrolled_independent_authority_verified: Literal[False]
    custody_verified: Literal[False]
    freshness_verified: Literal[False]
    replay_registry_checked: Literal[False]
    formal_binding_resolved: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    authority: Literal["diagnostic_only_no_binding_resolution"]
    claim_boundary: str
    diagnostic_sha256: Sha256

    @model_validator(mode="after")
    def _one_task_one_diagnostic_candidate(self) -> Self:
        expected = {
            ResolvableTaskId.TASK_11: (TASK11_PROTOCOL_ID, ResolvableBinding.RESAMPLING_POLICY),
            ResolvableTaskId.TASK_12: (TASK12_PROTOCOL_ID, ResolvableBinding.REJUVENATION_KERNEL),
            ResolvableTaskId.TASK_13: (
                TASK13_PROTOCOL_ID,
                ResolvableBinding.DIFFERENTIABILITY_STRATEGY,
            ),
        }[self.source_task]
        if (self.source_protocol_id, self.candidate_binding) != expected:
            raise ValueError("source task may diagnose only its declared binding and protocol")
        candidates = (
            self.diagnostic_resampling_policy,
            self.diagnostic_rejuvenation_kernel,
            self.diagnostic_differentiability_strategy,
        )
        expected_index = {
            ResolvableTaskId.TASK_11: 0,
            ResolvableTaskId.TASK_12: 1,
            ResolvableTaskId.TASK_13: 2,
        }[self.source_task]
        if tuple(item is not None for item in candidates) != tuple(
            index == expected_index for index in range(3)
        ):
            raise ValueError("diagnostic must carry exactly the source task's typed candidate")
        if self.claim_boundary != LOCAL_BINDING_DIAGNOSTIC_CLAIM_BOUNDARY:
            raise ValueError("local binding diagnostic cannot widen its claim boundary")
        unsigned = self.model_dump(mode="python", exclude={"diagnostic_sha256"})
        if self.diagnostic_sha256 != content_sha256(unsigned):
            raise ValueError("binding diagnostic hash mismatch")
        return self


class P5StageRecall(ContractModel):
    stage: ProposalPipelineStage
    full_chain_truth_compatible_recall: Probability


class P5ArmGateOutcomes(ContractModel):
    same_visible_input: bool
    fixed_nuisance_bindings: bool
    stage_accounting_complete: bool
    oracle_access_role_enforced: bool
    truth_reads_logged: bool

    @property
    def all_passed(self) -> bool:
        return all(self.model_dump(mode="python").values())


class P5ArmResult(ContractModel):
    arm: ProposalHeadroomArm
    stage_recall: tuple[P5StageRecall, ...] = Field(min_length=1)
    posterior_mass_coverage: Probability
    axis_recall: dict[ParticleAxis, Probability]
    operation_recall: dict[ProposalOperation, Probability]
    unknown_support_retention: Probability
    unresolved_mass_retention: Probability
    action_loss: float = Field(ge=0.0, allow_inf_nan=False)
    elementary_evaluations: PositiveInt
    truth_read_count: NonNegativeInt
    exact_enumeration_count: NonNegativeInt
    oracle_used: bool
    wall_clock_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    gates: P5ArmGateOutcomes

    @model_validator(mode="after")
    def _complete_arm_evidence(self) -> Self:
        if tuple(item.stage for item in self.stage_recall) != P5_STAGES:
            raise ValueError("every P5 arm must report every pipeline stage exactly once in order")
        recalls = tuple(item.full_chain_truth_compatible_recall for item in self.stage_recall)
        if any(later > earlier + 1e-12 for earlier, later in pairwise(recalls)):
            raise ValueError("P5 recall cannot increase after a support-removing pipeline stage")
        if set(self.axis_recall) != set(ParticleAxis):
            raise ValueError("every P5 arm must report every particle axis")
        if set(self.operation_recall) != set(ProposalOperation):
            raise ValueError("every P5 arm must report every proposal operation")
        oracle_arm = self.arm in {
            ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE,
            ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE,
        }
        if self.oracle_used != oracle_arm:
            raise ValueError("P5 oracle-use flag must agree with the arm role")
        if oracle_arm:
            if self.truth_read_count <= 0 or self.exact_enumeration_count <= 0:
                raise ValueError("P5 oracle arms must log truth reads and exact enumeration")
        elif self.truth_read_count != 0 or self.exact_enumeration_count != 0:
            raise ValueError("P5 deployable arms cannot read truth or exact-enumerate")
        return self


class P5StageHeadroom(ContractModel):
    stage: ProposalPipelineStage
    best_deployable_recall: Probability
    best_oracle_recall: Probability
    headroom: Probability

    @model_validator(mode="after")
    def _derived_difference(self) -> Self:
        expected = max(0.0, self.best_oracle_recall - self.best_deployable_recall)
        if abs(self.headroom - expected) > 1e-12:
            raise ValueError("P5 stage headroom must be recomputed from arm recalls")
        return self


def _compute_p5_summary(
    arm_results: Sequence[P5ArmResult],
) -> tuple[tuple[P5StageHeadroom, ...], float, float, P5Diagnosis]:
    by_arm = {item.arm: item for item in arm_results}
    if tuple(by_arm) != P5_ARMS or len(by_arm) != len(P5_ARMS):
        raise ValueError("P5 result must contain all four preregistered arms exactly once in order")
    deployable = (
        by_arm[ProposalHeadroomArm.BOOTSTRAP],
        by_arm[ProposalHeadroomArm.DETERMINISTIC_TYPED],
    )
    oracles = (
        by_arm[ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE],
        by_arm[ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE],
    )
    stage_headroom: list[P5StageHeadroom] = []
    for index, stage in enumerate(P5_STAGES):
        deployable_recall = max(
            item.stage_recall[index].full_chain_truth_compatible_recall for item in deployable
        )
        oracle_recall = max(
            item.stage_recall[index].full_chain_truth_compatible_recall for item in oracles
        )
        stage_headroom.append(
            P5StageHeadroom(
                stage=stage,
                best_deployable_recall=deployable_recall,
                best_oracle_recall=oracle_recall,
                headroom=max(0.0, oracle_recall - deployable_recall),
            )
        )
    final_headroom = stage_headroom[-1].headroom
    action_gain = min(item.action_loss for item in deployable) - min(
        item.action_loss for item in oracles
    )
    raw_headroom = stage_headroom[0].headroom
    deployable_recalls = tuple(
        max(item.stage_recall[index].full_chain_truth_compatible_recall for item in deployable)
        for index in range(len(P5_STAGES))
    )
    oracle_recalls = tuple(
        max(item.stage_recall[index].full_chain_truth_compatible_recall for item in oracles)
        for index in range(len(P5_STAGES))
    )
    downstream_excess_loss = max(
        (
            max(0.0, deployable_recalls[index - 1] - deployable_recalls[index])
            - max(0.0, oracle_recalls[index - 1] - oracle_recalls[index])
        )
        for index in range(1, len(P5_STAGES))
    )
    proposal_bottleneck = raw_headroom > 0.01
    downstream_bottleneck = downstream_excess_loss > 0.01
    if final_headroom <= 0.01:
        diagnosis = P5Diagnosis.NO_PROPOSAL_HEADROOM
    elif action_gain <= 0.0:
        diagnosis = P5Diagnosis.READOUT_INCONCLUSIVE
    elif proposal_bottleneck and downstream_bottleneck:
        diagnosis = P5Diagnosis.MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK
    elif proposal_bottleneck:
        diagnosis = P5Diagnosis.PROPOSAL_BOTTLENECK
    elif downstream_bottleneck:
        diagnosis = P5Diagnosis.DOWNSTREAM_WEIGHTING_OR_RESAMPLING_BOTTLENECK
    else:
        diagnosis = P5Diagnosis.READOUT_INCONCLUSIVE
    return tuple(stage_headroom), final_headroom, action_gain, diagnosis


class TaskP5DiagnosticResult(ContractModel):
    """Four-arm P5 matrix with a diagnosis recomputed from typed evidence."""

    schema_version: Literal["0.2.0"]
    protocol_id: Literal["structure-two-backbone-proposal-headroom-p5@0.1"]
    result_status: Literal["COMPLETED_DIAGNOSTIC"]
    primary_estimand: Literal[
        "oracle_minus_deployable_full_chain_truth_compatible_recall_decomposed_by_pipeline_stage"
    ]
    execution_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    spec_content_sha256: Sha256
    config_content_sha256: Sha256
    source_bundle_sha256: Sha256
    runtime_binding_receipt: RuntimeBindingReceipt
    arm_results: tuple[P5ArmResult, ...] = Field(min_length=1)
    stage_headroom: tuple[P5StageHeadroom, ...] = Field(min_length=1)
    primary_estimand_value: Probability
    oracle_action_gain: float = Field(allow_inf_nan=False)
    diagnosis: P5Diagnosis
    authority: Literal["diagnosis_only_no_binding_resolution"]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: str

    @model_validator(mode="after")
    def _diagnostic_only(self) -> Self:
        expected = _compute_p5_summary(self.arm_results)
        actual = (
            self.stage_headroom,
            self.primary_estimand_value,
            self.oracle_action_gain,
            self.diagnosis,
        )
        if actual != expected:
            raise ValueError(
                "P5 headroom and diagnosis must be recomputed from the four-arm matrix"
            )
        if not all(item.gates.all_passed for item in self.arm_results):
            raise ValueError("P5 diagnostic requires every per-arm integrity gate")
        if self.runtime_binding_receipt.task_id is not RuntimeTaskId.PROPOSAL_P5:
            raise ValueError("P5 result requires a P5 runtime receipt")
        if (
            self.execution_id,
            self.producer_id,
        ) != (
            self.runtime_binding_receipt.execution_id,
            self.runtime_binding_receipt.producer_id,
        ):
            raise ValueError("P5 result and runtime receipt execution identity differ")
        if self.claim_boundary != P5_CLAIM_BOUNDARY:
            raise ValueError("P5 result cannot widen its diagnostic claim boundary")
        return self


def _spec_for_runtime_task(
    protocols: StructureTwoBackboneOpenTaskProtocols, task_id: RuntimeTaskId
) -> (
    Task11ResamplingSpec
    | Task12RejuvenationSpec
    | Task13DifferentiabilitySpec
    | TaskP5ProposalHeadroomSpec
):
    if task_id is RuntimeTaskId.TASK_11:
        return protocols.task_11
    if task_id is RuntimeTaskId.TASK_12:
        return protocols.task_12
    if task_id is RuntimeTaskId.TASK_13:
        return protocols.task_13
    return protocols.proposal_p5


def build_runtime_binding_receipt(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    task_id: RuntimeTaskId,
    execution_id: str,
    producer_id: str,
    observed_runtime_values: Mapping[str, str],
    runtime_trace_payload_sha256_by_binding: Mapping[str, str],
    source_bundle_sha256: str,
) -> RuntimeBindingReceipt:
    """Build a complete runtime receipt from the frozen spec and observed values."""

    spec = _spec_for_runtime_task(protocols, task_id)
    configured = spec.nuisance_bindings.model_dump(mode="json")
    if set(observed_runtime_values) != set(configured):
        raise ValueError("observed runtime values do not cover the frozen nuisance bindings")
    if set(runtime_trace_payload_sha256_by_binding) != set(configured):
        raise ValueError("runtime trace payloads do not cover the frozen nuisance bindings")
    return RuntimeBindingReceipt(
        schema_version="0.2.0",
        task_id=task_id,
        protocol_id=spec.protocol_id,
        execution_id=execution_id,
        producer_id=producer_id,
        spec_content_sha256=content_sha256(spec),
        config_content_sha256=protocols.content_sha256,
        source_bundle_sha256=source_bundle_sha256,
        observations=tuple(
            RuntimeBindingObservation(
                binding=name,
                configured_value=str(configured[name]),
                observed_runtime_value=observed_runtime_values[name],
                runtime_trace_payload_sha256=runtime_trace_payload_sha256_by_binding[name],
            )
            for name in configured
        ),
    )


def verify_runtime_binding_receipt(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    task_id: RuntimeTaskId,
    receipt: RuntimeBindingReceipt,
    expected_source_bundle_sha256: str,
) -> None:
    """Reject key-complete but spec-drifted or source-drifted runtime receipts."""

    receipt = RuntimeBindingReceipt.model_validate(receipt.model_dump(mode="python"))
    spec = _spec_for_runtime_task(protocols, task_id)
    configured = spec.nuisance_bindings.model_dump(mode="json")
    expected_header = (
        task_id,
        spec.protocol_id,
        content_sha256(spec),
        protocols.content_sha256,
        expected_source_bundle_sha256,
    )
    actual_header = (
        receipt.task_id,
        receipt.protocol_id,
        receipt.spec_content_sha256,
        receipt.config_content_sha256,
        receipt.source_bundle_sha256,
    )
    if actual_header != expected_header:
        raise ValueError("runtime receipt spec/config/source binding drift")
    observed = {item.binding: item for item in receipt.observations}
    if set(observed) != set(configured):
        raise ValueError("runtime receipt nuisance coverage drift")
    for name, expected_value in configured.items():
        item = observed[name]
        if (item.configured_value, item.observed_runtime_value) != (
            str(expected_value),
            str(expected_value),
        ):
            raise ValueError(f"runtime receipt value drift for {name}")


_NONDETERMINISTIC_RESULT_FIELDS = frozenset({"wall_clock_seconds", "execution_id", "producer_id"})


def _deterministic_projection(value: Any) -> Any:
    if isinstance(value, ContractModel):
        return _deterministic_projection(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {
            key: _deterministic_projection(item)
            for key, item in value.items()
            if key not in _NONDETERMINISTIC_RESULT_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_deterministic_projection(item) for item in value]
    return value


def deterministic_result_sha256(
    result: Task11RunResult | Task12RunResult | Task13RunResult | TaskP5DiagnosticResult,
) -> str:
    return content_sha256(_deterministic_projection(result))


def _verify_caller_pair_deterministic_agreement(
    reported: Task11RunResult | Task12RunResult | Task13RunResult | TaskP5DiagnosticResult,
    recomputed: Task11RunResult | Task12RunResult | Task13RunResult | TaskP5DiagnosticResult,
) -> None:
    if type(reported) is not type(recomputed):
        raise ValueError("reported and recomputed results use different task schemas")
    if reported.execution_id == recomputed.execution_id:
        raise ValueError("caller comparison requires distinct claimed execution ids")
    if reported.producer_id == recomputed.producer_id:
        raise ValueError("caller comparison requires distinct claimed producer ids")
    if deterministic_result_sha256(reported) != deterministic_result_sha256(recomputed):
        raise ValueError("caller-pair deterministic comparison mismatch")


def _verify_result_header(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    spec: Task11ResamplingSpec
    | Task12RejuvenationSpec
    | Task13DifferentiabilitySpec
    | TaskP5ProposalHeadroomSpec,
    task_id: RuntimeTaskId,
    reported: Task11RunResult | Task12RunResult | Task13RunResult | TaskP5DiagnosticResult,
    recomputed: Task11RunResult | Task12RunResult | Task13RunResult | TaskP5DiagnosticResult,
    expected_source_bundle_sha256: str,
) -> None:
    result_type = type(reported)
    if result_type not in {
        Task11RunResult,
        Task12RunResult,
        Task13RunResult,
        TaskP5DiagnosticResult,
    }:
        raise ValueError("unsupported task result schema")
    result_type.model_validate(reported.model_dump(mode="python"))
    result_type.model_validate(recomputed.model_dump(mode="python"))
    _verify_caller_pair_deterministic_agreement(reported, recomputed)
    for result in (reported, recomputed):
        expected = (
            spec.protocol_id,
            content_sha256(spec),
            protocols.content_sha256,
            expected_source_bundle_sha256,
        )
        actual = (
            result.protocol_id,
            result.spec_content_sha256,
            result.config_content_sha256,
            result.source_bundle_sha256,
        )
        if actual != expected:
            raise ValueError("task result protocol/spec/config/source binding drift")
        verify_runtime_binding_receipt(
            protocols,
            task_id=task_id,
            receipt=result.runtime_binding_receipt,
            expected_source_bundle_sha256=expected_source_bundle_sha256,
        )


def _expected_task11_arm_keys(spec: Task11ResamplingSpec) -> tuple[str, ...]:
    keys = [ResamplingAlgorithm.NONE.value]
    for algorithm in spec.algorithms:
        if algorithm is ResamplingAlgorithm.NONE:
            continue
        keys.extend(
            Task11ArmPolicy(algorithm=algorithm, ess_fraction=threshold).arm_key
            for threshold in spec.validation_only_ess_thresholds
        )
    return tuple(keys)


def _choose_task11_policy(
    spec: Task11ResamplingSpec, arm_results: Sequence[Task11ArmResult]
) -> Task11PolicySelection | None:
    rule = spec.selection_rule
    candidates = [
        item
        for item in arm_results
        if item.policy.algorithm is not ResamplingAlgorithm.MULTINOMIAL_NEGATIVE_CONTROL
        and item.posterior_total_variation <= rule.max_posterior_total_variation
        and item.owner_contamination <= rule.max_owner_contamination
        and abs(item.log_normalizer_bias) <= rule.max_absolute_log_normalizer_bias
    ]
    if not candidates:
        return None
    best_value = min(item.paired_action_loss_delta_per_elementary_evaluation for item in candidates)
    tied = [
        item
        for item in candidates
        if item.paired_action_loss_delta_per_elementary_evaluation
        <= best_value + rule.tie_tolerance
    ]
    selected = min(tied, key=lambda item: item.policy.arm_key).policy
    return Task11PolicySelection.model_validate(selected.model_dump(mode="python"))


def verify_task11_result(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task11RunResult,
    recomputed: Task11RunResult,
    expected_source_bundle_sha256: str,
) -> Task11PolicySelection | None:
    spec = protocols.task_11
    _verify_result_header(
        protocols,
        spec=spec,
        task_id=RuntimeTaskId.TASK_11,
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=expected_source_bundle_sha256,
    )
    keys = tuple(item.policy.arm_key for item in reported.arm_results)
    if keys != _expected_task11_arm_keys(spec):
        raise ValueError("Task 11 result is missing, reordering, or substituting an arm")
    integrity = all(item.gates.all_passed for item in reported.arm_results)
    selected = _choose_task11_policy(spec, reported.arm_results) if integrity else None
    expected_disposition = (
        BindingRunDisposition.RAN_INELIGIBLE
        if not integrity
        else (
            BindingRunDisposition.RAN_ELIGIBLE_SELECTION
            if selected is not None
            else BindingRunDisposition.RAN_ELIGIBLE_NO_SELECTION
        )
    )
    if (reported.disposition, reported.selected_policy) != (expected_disposition, selected):
        raise ValueError("Task 11 disposition/selection was not verifier-derived from arm evidence")
    return selected


def _choose_task12_kernel(
    spec: Task12RejuvenationSpec, arm_results: Sequence[Task12ArmResult]
) -> RejuvenationKernelCandidate | None:
    rule = spec.selection_rule
    candidates = [
        item
        for item in arm_results
        if item.kernel is not RejuvenationKernelCandidate.EXACT_CONDITIONAL_GIBBS_EVALUATOR_ONLY
        and item.detailed_balance_error <= rule.max_detailed_balance_error
        and item.stationary_distribution_error <= rule.max_stationary_distribution_error
        and item.full_rerun_actor_marginal_distance <= rule.max_full_rerun_actor_marginal_distance
        and item.owner_contamination <= rule.max_owner_contamination
    ]
    if not candidates:
        return None
    best_value = max(item.effective_sample_size_per_elementary_evaluation for item in candidates)
    tied = [
        item
        for item in candidates
        if item.effective_sample_size_per_elementary_evaluation >= best_value - rule.tie_tolerance
    ]
    return min(tied, key=lambda item: item.kernel.value).kernel


def verify_task12_result(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task12RunResult,
    recomputed: Task12RunResult,
    expected_source_bundle_sha256: str,
) -> RejuvenationKernelCandidate | None:
    spec = protocols.task_12
    _verify_result_header(
        protocols,
        spec=spec,
        task_id=RuntimeTaskId.TASK_12,
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=expected_source_bundle_sha256,
    )
    kernels = tuple(item.kernel for item in reported.arm_results)
    if kernels != spec.candidate_kernels:
        raise ValueError("Task 12 result is missing, reordering, or substituting a kernel arm")
    integrity = all(item.gates.all_passed for item in reported.arm_results)
    selected = _choose_task12_kernel(spec, reported.arm_results) if integrity else None
    expected_disposition = (
        BindingRunDisposition.RAN_INELIGIBLE
        if not integrity
        else (
            BindingRunDisposition.RAN_ELIGIBLE_SELECTION
            if selected is not None
            else BindingRunDisposition.RAN_ELIGIBLE_NO_SELECTION
        )
    )
    if (reported.disposition, reported.selected_kernel) != (expected_disposition, selected):
        raise ValueError("Task 12 disposition/selection was not verifier-derived from arm evidence")
    return selected


def _choose_task13_strategy(
    spec: Task13DifferentiabilitySpec, arm_results: Sequence[Task13ArmResult]
) -> DifferentiabilityStrategy | None:
    rule = spec.selection_rule
    candidates = [
        item
        for item in arm_results
        if item.finite_difference_gradient_error <= rule.max_finite_difference_gradient_error
        and item.exact_expectation_gradient_error <= rule.max_exact_expectation_gradient_error
        and item.posterior_total_variation <= rule.max_posterior_total_variation
        and item.paired_action_loss_delta_per_training_compute
        < rule.maximum_primary_estimand_for_improvement
    ]
    if not candidates:
        return None
    best_value = min(item.paired_action_loss_delta_per_training_compute for item in candidates)
    tied = [
        item
        for item in candidates
        if item.paired_action_loss_delta_per_training_compute <= best_value + rule.tie_tolerance
    ]
    return min(tied, key=lambda item: item.strategy.value).strategy


def verify_task13_result(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task13RunResult,
    recomputed: Task13RunResult,
    expected_source_bundle_sha256: str,
) -> DifferentiabilityStrategy | None:
    spec = protocols.task_13
    _verify_result_header(
        protocols,
        spec=spec,
        task_id=RuntimeTaskId.TASK_13,
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=expected_source_bundle_sha256,
    )
    strategies = tuple(item.strategy for item in reported.arm_results)
    if strategies != spec.strategies:
        raise ValueError("Task 13 result is missing, reordering, or substituting a strategy arm")
    integrity = all(item.gates.all_passed for item in reported.arm_results)
    selected = _choose_task13_strategy(spec, reported.arm_results) if integrity else None
    expected_disposition = (
        BindingRunDisposition.RAN_INELIGIBLE
        if not integrity
        else (
            BindingRunDisposition.RAN_ELIGIBLE_SELECTION
            if selected is not None
            else BindingRunDisposition.RAN_ELIGIBLE_NO_SELECTION
        )
    )
    if (reported.disposition, reported.selected_strategy) != (expected_disposition, selected):
        raise ValueError("Task 13 disposition/selection was not verifier-derived from arm evidence")
    return selected


def build_p5_diagnostic_result(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    execution_id: str,
    producer_id: str,
    source_bundle_sha256: str,
    runtime_binding_receipt: RuntimeBindingReceipt,
    arm_results: Sequence[P5ArmResult],
) -> TaskP5DiagnosticResult:
    verify_runtime_binding_receipt(
        protocols,
        task_id=RuntimeTaskId.PROPOSAL_P5,
        receipt=runtime_binding_receipt,
        expected_source_bundle_sha256=source_bundle_sha256,
    )
    summary = _compute_p5_summary(arm_results)
    return TaskP5DiagnosticResult(
        schema_version="0.2.0",
        protocol_id=P5_PROTOCOL_ID,
        result_status="COMPLETED_DIAGNOSTIC",
        primary_estimand=P5_ESTIMAND,
        execution_id=execution_id,
        producer_id=producer_id,
        spec_content_sha256=content_sha256(protocols.proposal_p5),
        config_content_sha256=protocols.content_sha256,
        source_bundle_sha256=source_bundle_sha256,
        runtime_binding_receipt=runtime_binding_receipt,
        arm_results=tuple(arm_results),
        stage_headroom=summary[0],
        primary_estimand_value=summary[1],
        oracle_action_gain=summary[2],
        diagnosis=summary[3],
        authority="diagnosis_only_no_binding_resolution",
        seven_operator_ablation_authorized=False,
        claim_boundary=P5_CLAIM_BOUNDARY,
    )


def verify_p5_result(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: TaskP5DiagnosticResult,
    recomputed: TaskP5DiagnosticResult,
    expected_source_bundle_sha256: str,
) -> P5Diagnosis:
    _verify_result_header(
        protocols,
        spec=protocols.proposal_p5,
        task_id=RuntimeTaskId.PROPOSAL_P5,
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=expected_source_bundle_sha256,
    )
    return reported.diagnosis


def diagnose_binding_candidate(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task11RunResult | Task12RunResult | Task13RunResult,
    recomputed: Task11RunResult | Task12RunResult | Task13RunResult,
    expected_source_bundle_sha256: str,
) -> BindingCandidateDiagnostic:
    """Compare two caller-supplied results without granting resolution authority."""

    selected_policy: Task11PolicySelection | None = None
    selected_kernel: RejuvenationKernelCandidate | None = None
    selected_strategy: DifferentiabilityStrategy | None = None
    if isinstance(reported, Task11RunResult) and isinstance(recomputed, Task11RunResult):
        selected_policy = verify_task11_result(
            protocols,
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=expected_source_bundle_sha256,
        )
        source_task = ResolvableTaskId.TASK_11
        protocol_id = TASK11_PROTOCOL_ID
        binding = ResolvableBinding.RESAMPLING_POLICY
        spec_hash = content_sha256(protocols.task_11)
    elif isinstance(reported, Task12RunResult) and isinstance(recomputed, Task12RunResult):
        selected_kernel = verify_task12_result(
            protocols,
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=expected_source_bundle_sha256,
        )
        source_task = ResolvableTaskId.TASK_12
        protocol_id = TASK12_PROTOCOL_ID
        binding = ResolvableBinding.REJUVENATION_KERNEL
        spec_hash = content_sha256(protocols.task_12)
    elif isinstance(reported, Task13RunResult) and isinstance(recomputed, Task13RunResult):
        selected_strategy = verify_task13_result(
            protocols,
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=expected_source_bundle_sha256,
        )
        source_task = ResolvableTaskId.TASK_13
        protocol_id = TASK13_PROTOCOL_ID
        binding = ResolvableBinding.DIFFERENTIABILITY_STRATEGY
        spec_hash = content_sha256(protocols.task_13)
    else:
        raise ValueError("reported and recomputed results must use one matching resolvable schema")
    if selected_policy is None and selected_kernel is None and selected_strategy is None:
        raise ValueError("no eligible local diagnostic binding candidate was found")
    payload: dict[str, Any] = {
        "schema_version": "0.3.0",
        "source_task": source_task,
        "source_protocol_id": protocol_id,
        "source_result_status": "RAN_ELIGIBLE_SELECTION",
        "candidate_binding": binding,
        "diagnostic_resampling_policy": selected_policy,
        "diagnostic_rejuvenation_kernel": selected_kernel,
        "diagnostic_differentiability_strategy": selected_strategy,
        "reported_result_content_sha256": content_sha256(reported),
        "comparison_result_deterministic_sha256": deterministic_result_sha256(recomputed),
        "spec_content_sha256": spec_hash,
        "config_content_sha256": protocols.content_sha256,
        "source_bundle_sha256": expected_source_bundle_sha256,
        "evidence_status": "LOCAL_CALLER_PAIR_DIAGNOSTIC_ONLY",
        "enrolled_independent_authority_verified": False,
        "custody_verified": False,
        "freshness_verified": False,
        "replay_registry_checked": False,
        "formal_binding_resolved": False,
        "seven_operator_ablation_authorized": False,
        "authority": "diagnostic_only_no_binding_resolution",
        "claim_boundary": LOCAL_BINDING_DIAGNOSTIC_CLAIM_BOUNDARY,
    }
    payload["diagnostic_sha256"] = content_sha256(payload)
    return BindingCandidateDiagnostic.model_validate(payload)


def derive_binding_resolution(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task11RunResult | Task12RunResult | Task13RunResult,
    recomputed: Task11RunResult | Task12RunResult | Task13RunResult,
    expected_source_bundle_sha256: str,
) -> NoReturn:
    """Fail closed until a non-caller-controlled outer authority is enrolled."""

    diagnose_binding_candidate(
        protocols,
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=expected_source_bundle_sha256,
    )
    raise ValueError(
        "local verifier cannot issue a formal binding resolution: an enrolled independent "
        "outer-authority handle with custody, freshness, and replay verification is required"
    )


def verify_binding_resolution(
    protocols: StructureTwoBackboneOpenTaskProtocols,
    *,
    reported: Task11RunResult | Task12RunResult | Task13RunResult,
    recomputed: Task11RunResult | Task12RunResult | Task13RunResult,
    receipt: object,
    expected_source_bundle_sha256: str,
) -> NoReturn:
    del protocols, reported, recomputed, receipt, expected_source_bundle_sha256
    raise ValueError(
        "local verifier cannot accept a binding resolution receipt; only a future enrolled "
        "independent outer verifier may validate its own opaque authority handle"
    )


__all__ = [
    "AxisJumpDistance",
    "BindingCandidateDiagnostic",
    "BindingResolutionAuthoritySpec",
    "BindingRunDisposition",
    "DefinitionStatus",
    "DifferentiabilityStrategy",
    "P5ArmGateOutcomes",
    "P5ArmResult",
    "P5Diagnosis",
    "P5StageHeadroom",
    "P5StageRecall",
    "ParticleAxis",
    "ProposalHeadroomArm",
    "ProposalOperation",
    "ProposalPipelineStage",
    "RejuvenationKernelCandidate",
    "ResamplingAlgorithm",
    "ResolvableBinding",
    "ResolvableTaskId",
    "RuntimeBindingObservation",
    "RuntimeBindingReceipt",
    "RuntimeTaskId",
    "StructureTwoBackboneOpenTaskProtocols",
    "Task11ArmPolicy",
    "Task11ArmResult",
    "Task11GateOutcomes",
    "Task11PolicySelection",
    "Task11ResamplingSpec",
    "Task11RunResult",
    "Task12ArmResult",
    "Task12GateOutcomes",
    "Task12RejuvenationSpec",
    "Task12RunResult",
    "Task13ArmResult",
    "Task13DifferentiabilitySpec",
    "Task13GateOutcomes",
    "Task13RunResult",
    "TaskP5DiagnosticResult",
    "TaskP5ProposalHeadroomSpec",
    "build_p5_diagnostic_result",
    "build_runtime_binding_receipt",
    "derive_binding_resolution",
    "deterministic_result_sha256",
    "diagnose_binding_candidate",
    "verify_binding_resolution",
    "verify_p5_result",
    "verify_runtime_binding_receipt",
    "verify_task11_result",
    "verify_task12_result",
    "verify_task13_result",
]
