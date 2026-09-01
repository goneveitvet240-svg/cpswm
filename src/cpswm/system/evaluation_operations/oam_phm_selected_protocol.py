"""Frozen route choices and fail-closed contracts for the OAM-PHM strong comparison.

The user selected the protocol shape on 2026-08-27.  A selected route is not
evidence that its datasets, implementations, thresholds, or results exist.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

from .oam_phm_external_evidence import (
    AntiContaminationBootstrapReport,
    ClusterAxis,
)


class SelectedProtocolStatus(StrEnum):
    ROUTE_FROZEN_PARAMETERS_PENDING = "route_frozen_parameters_pending"
    EXECUTABLE_PROTOCOL_COMPLETE = "executable_protocol_complete"


class OStarInputTrack(StrEnum):
    RECORDED_3D_REPLAY = "recorded-3d-replay"


class OStarPriorTrack(StrEnum):
    FROZEN_RESPONSE_TABLE = "frozen-response-table"


class StreakReproductionTrack(StrEnum):
    COMPONENT_FACTORED_REPRODUCTION = "component-factored-reproduction"


class OAMFullArmTrack(StrEnum):
    GOVERNED_MAIN_LEARNED_SENSITIVITY = "governed-main+learned-sensitivity"


class ComplexityDecisionTrack(StrEnum):
    NONINFERIORITY_PLUS_SUPERIORITY = "non-inferiority-plus-superiority"


class ExecutionIsolationTrack(StrEnum):
    LOCAL_PROCESS_DEV_CONTAINER_FORMAL = "local-process-dev+container-formal"


class ComputeBudgetTrack(StrEnum):
    BUDGET_VECTOR = "budget-vector"


DOMAIN_OAM_FORMAL_EVIDENCE = "cpswm.oam_phm.formal_evidence.v1"


class OAMFormalEvidenceKind(StrEnum):
    RECORDED_REPLAY = "recorded_replay"
    FROZEN_RESPONSE_TABLE = "frozen_response_table"
    STREAK_MANIFEST = "streak_manifest"
    BUDGET_RECEIPT = "budget_receipt"
    BOOTSTRAP_REPORT = "bootstrap_report"
    DECISION_CRITERION = "decision_criterion"


class OAMFormalEvidenceReceipt(ContractModel):
    evidence_kind: OAMFormalEvidenceKind
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_run_id: str = Field(min_length=1)
    attestation: Attestation | None = None


def issue_oam_formal_evidence_receipt(
    subject: ContractModel,
    *,
    evidence_kind: OAMFormalEvidenceKind,
    custodian_run_id: str,
    signer: Ed25519AttestationSigner,
) -> OAMFormalEvidenceReceipt:
    unsigned = OAMFormalEvidenceReceipt(
        evidence_kind=evidence_kind,
        subject_sha256=content_sha256(subject),
        custodian_run_id=custodian_run_id,
    )
    return unsigned.model_copy(
        update={
            "attestation": signer.sign(
                DOMAIN_OAM_FORMAL_EVIDENCE,
                attested_payload(unsigned),
            )
        }
    )


def verify_oam_formal_evidence_receipt(
    subject: ContractModel,
    receipt: OAMFormalEvidenceReceipt,
    *,
    evidence_kind: OAMFormalEvidenceKind,
    verifier: Ed25519AttestationVerifier,
) -> None:
    if receipt.evidence_kind is not evidence_kind:
        raise AttestationError("OAM evidence receipt has the wrong evidence kind")
    if receipt.subject_sha256 != content_sha256(subject):
        raise AttestationError("OAM evidence receipt does not bind this subject")
    verifier.verify(
        DOMAIN_OAM_FORMAL_EVIDENCE,
        attested_payload(receipt),
        receipt.attestation,
    )


class SelectedOAMProtocol(ContractModel):
    selection_id: str = Field(min_length=1)
    selected_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    o_star_input: OStarInputTrack
    o_star_prior: OStarPriorTrack
    streak_reproduction: StreakReproductionTrack
    full_arm: OAMFullArmTrack
    complexity_decision: ComplexityDecisionTrack
    execution_isolation: ExecutionIsolationTrack
    compute_budget: ComputeBudgetTrack
    status: SelectedProtocolStatus
    unresolved_parameters: tuple[str, ...] = Field(min_length=1)

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def current_selected_oam_protocol() -> SelectedOAMProtocol:
    """Return the route selected by the user without inventing missing thresholds."""

    return SelectedOAMProtocol(
        selection_id="oam-phm-strong-comparison-route@2026-08-27",
        selected_on="2026-08-27",
        o_star_input=OStarInputTrack.RECORDED_3D_REPLAY,
        o_star_prior=OStarPriorTrack.FROZEN_RESPONSE_TABLE,
        streak_reproduction=StreakReproductionTrack.COMPONENT_FACTORED_REPRODUCTION,
        full_arm=OAMFullArmTrack.GOVERNED_MAIN_LEARNED_SENSITIVITY,
        complexity_decision=ComplexityDecisionTrack.NONINFERIORITY_PLUS_SUPERIORITY,
        execution_isolation=ExecutionIsolationTrack.LOCAL_PROCESS_DEV_CONTAINER_FORMAL,
        compute_budget=ComputeBudgetTrack.BUDGET_VECTOR,
        status=SelectedProtocolStatus.ROUTE_FROZEN_PARAMETERS_PENDING,
        unresolved_parameters=(
            "recorded-3d replay dataset and producer hashes",
            "frozen-response table and generation-protocol hashes",
            "STREAK stage acceptance tolerances",
            "governed and learned arm composition hashes",
            "non-inferiority margins and superiority threshold",
            "development and formal hard-timeout values",
            "formal OCI image digest and hardware profile",
            "budget-vector caps",
        ),
    )


class Recorded3DReplayContract(ContractModel):
    replay_id: str = Field(min_length=1)
    replay_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scene_graph_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    perception_producer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    search_cost_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_group_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable: bool
    evaluator_truth_fields_present: bool

    @model_validator(mode="after")
    def validate_replay(self) -> Self:
        if not self.immutable:
            raise ValueError("recorded 3D replay must be immutable")
        if self.evaluator_truth_fields_present:
            raise ValueError("recorded 3D baseline input cannot expose evaluator truth")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class FrozenResponseTableContract(ContractModel):
    table_id: str = Field(min_length=1)
    response_table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_vocabulary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rank_to_probability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_key_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_count: int = Field(gt=0)
    generated_before_sealed_test_access: bool

    @model_validator(mode="after")
    def validate_freeze(self) -> Self:
        if not self.generated_before_sealed_test_access:
            raise ValueError("LLM response table must be frozen before sealed-test access")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class StreakReproductionStage(StrEnum):
    STATIC_GTM = "static-gtm"
    SEQUENTIAL_FINETUNING_LOWER_BOUND = "sequential-finetuning-lower-bound"
    JOINT_TRAINING_UPPER_BOUND = "joint-training-upper-bound"
    FISHER_ONLY = "fisher-only"
    REHEARSAL_ONLY = "rehearsal-only"
    FULL_STREAK = "full-streak"


REQUIRED_STREAK_STAGE_ORDER = (
    StreakReproductionStage.STATIC_GTM,
    StreakReproductionStage.SEQUENTIAL_FINETUNING_LOWER_BOUND,
    StreakReproductionStage.JOINT_TRAINING_UPPER_BOUND,
    StreakReproductionStage.FISHER_ONLY,
    StreakReproductionStage.REHEARSAL_ONLY,
    StreakReproductionStage.FULL_STREAK,
)


class StreakComponentStageRecord(ContractModel):
    stage: StreakReproductionStage
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: bool


class StreakComponentFactoredManifest(ContractModel):
    reproduction_id: str = Field(min_length=1)
    stages: tuple[StreakComponentStageRecord, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_stages(self) -> Self:
        if tuple(record.stage for record in self.stages) != REQUIRED_STREAK_STAGE_ORDER:
            raise ValueError("STREAK component stages must use the frozen order")
        if any(
            record.accepted and not all(previous.accepted for previous in self.stages[:index])
            for index, record in enumerate(self.stages)
        ):
            raise ValueError("a STREAK stage cannot pass before every prerequisite stage")
        return self

    @property
    def reproduction_complete(self) -> bool:
        # Caller-declared acceptance is never a formal completion decision.
        return False

    @property
    def declared_reproduction_complete(self) -> bool:
        return all(record.accepted for record in self.stages)

    def verified_reproduction_complete(
        self,
        receipt: OAMFormalEvidenceReceipt,
        *,
        verifier: Ed25519AttestationVerifier,
    ) -> bool:
        if not self.declared_reproduction_complete:
            return False
        verify_oam_formal_evidence_receipt(
            self,
            receipt,
            evidence_kind=OAMFormalEvidenceKind.STREAK_MANIFEST,
            verifier=verifier,
        )
        return True


class GovernedLearnedSensitivityPair(ContractModel):
    governed_main_arm_id: str = Field(min_length=1)
    learned_sensitivity_arm_id: str = Field(min_length=1)
    governed_wp2_wp6_composition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_and_write_authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    learned_variant_composition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_difference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_non_target_components_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    learned_variant_is_formal_full_method: bool = False

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        if self.governed_main_arm_id == self.learned_sensitivity_arm_id:
            raise ValueError("governed main and learned sensitivity need distinct arm ids")
        if self.learned_variant_is_formal_full_method:
            raise ValueError("learned sensitivity cannot be labeled as the governed full method")
        return self


class TuningBudgetVector(ContractModel):
    gpu_hours: float = Field(gt=0.0)
    candidate_trials: int = Field(gt=0)
    training_samples: int = Field(gt=0)


class OnlineInferenceBudgetVector(ContractModel):
    wall_clock_p50_ms: float = Field(gt=0.0)
    wall_clock_p95_ms: float = Field(gt=0.0)
    model_forwards: int = Field(gt=0)
    processed_graph_edges: int = Field(gt=0)
    llm_tokens: int = Field(ge=0)
    peak_memory_mb: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_percentiles(self) -> Self:
        if self.wall_clock_p95_ms < self.wall_clock_p50_ms:
            raise ValueError("wall-clock p95 cannot be below p50")
        return self


class EmbodiedActionBudgetVector(ContractModel):
    navigation_distance_m: float = Field(ge=0.0)
    container_interactions: int = Field(ge=0)
    additional_observations: int = Field(ge=0)
    user_interruptions: int = Field(ge=0)


class OAMBudgetVector(ContractModel):
    budget_id: str = Field(min_length=1)
    tuning: TuningBudgetVector
    online_inference: OnlineInferenceBudgetVector
    embodied_action: EmbodiedActionBudgetVector

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class TuningUsageVector(ContractModel):
    gpu_hours: float = Field(ge=0.0)
    candidate_trials: int = Field(ge=0)
    training_samples: int = Field(ge=0)


class OnlineInferenceUsageVector(ContractModel):
    wall_clock_p50_ms: float = Field(ge=0.0)
    wall_clock_p95_ms: float = Field(ge=0.0)
    model_forwards: int = Field(ge=0)
    processed_graph_edges: int = Field(ge=0)
    llm_tokens: int = Field(ge=0)
    peak_memory_mb: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_percentiles(self) -> Self:
        if self.wall_clock_p95_ms < self.wall_clock_p50_ms:
            raise ValueError("wall-clock usage p95 cannot be below p50")
        return self


class EmbodiedActionUsageVector(ContractModel):
    navigation_distance_m: float = Field(ge=0.0)
    container_interactions: int = Field(ge=0)
    additional_observations: int = Field(ge=0)
    user_interruptions: int = Field(ge=0)


class OAMBudgetUsage(ContractModel):
    tuning: TuningUsageVector
    online_inference: OnlineInferenceUsageVector
    embodied_action: EmbodiedActionUsageVector


BUDGET_DIMENSIONS = (
    "tuning.gpu_hours",
    "tuning.candidate_trials",
    "tuning.training_samples",
    "online_inference.wall_clock_p50_ms",
    "online_inference.wall_clock_p95_ms",
    "online_inference.model_forwards",
    "online_inference.processed_graph_edges",
    "online_inference.llm_tokens",
    "online_inference.peak_memory_mb",
    "embodied_action.navigation_distance_m",
    "embodied_action.container_interactions",
    "embodied_action.additional_observations",
    "embodied_action.user_interruptions",
)


class BudgetVectorComplianceReceipt(ContractModel):
    budget_vector_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: OAMBudgetUsage
    compliant_dimensions: tuple[str, ...]
    exceeded_dimensions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_partition(self) -> Self:
        combined = (*self.compliant_dimensions, *self.exceeded_dimensions)
        if len(combined) != len(set(combined)) or set(combined) != set(BUDGET_DIMENSIONS):
            raise ValueError("budget receipt dimensions must form an exact partition")
        return self

    @property
    def compliant(self) -> bool:
        return not self.exceeded_dimensions


def assess_budget_vector(
    budget: OAMBudgetVector, usage: OAMBudgetUsage
) -> BudgetVectorComplianceReceipt:
    """Compare every selected budget dimension without scalarizing the vector."""

    caps = {
        "tuning.gpu_hours": budget.tuning.gpu_hours,
        "tuning.candidate_trials": budget.tuning.candidate_trials,
        "tuning.training_samples": budget.tuning.training_samples,
        "online_inference.wall_clock_p50_ms": budget.online_inference.wall_clock_p50_ms,
        "online_inference.wall_clock_p95_ms": budget.online_inference.wall_clock_p95_ms,
        "online_inference.model_forwards": budget.online_inference.model_forwards,
        "online_inference.processed_graph_edges": (budget.online_inference.processed_graph_edges),
        "online_inference.llm_tokens": budget.online_inference.llm_tokens,
        "online_inference.peak_memory_mb": budget.online_inference.peak_memory_mb,
        "embodied_action.navigation_distance_m": (budget.embodied_action.navigation_distance_m),
        "embodied_action.container_interactions": (budget.embodied_action.container_interactions),
        "embodied_action.additional_observations": (budget.embodied_action.additional_observations),
        "embodied_action.user_interruptions": budget.embodied_action.user_interruptions,
    }
    values = {
        "tuning.gpu_hours": usage.tuning.gpu_hours,
        "tuning.candidate_trials": usage.tuning.candidate_trials,
        "tuning.training_samples": usage.tuning.training_samples,
        "online_inference.wall_clock_p50_ms": usage.online_inference.wall_clock_p50_ms,
        "online_inference.wall_clock_p95_ms": usage.online_inference.wall_clock_p95_ms,
        "online_inference.model_forwards": usage.online_inference.model_forwards,
        "online_inference.processed_graph_edges": (usage.online_inference.processed_graph_edges),
        "online_inference.llm_tokens": usage.online_inference.llm_tokens,
        "online_inference.peak_memory_mb": usage.online_inference.peak_memory_mb,
        "embodied_action.navigation_distance_m": usage.embodied_action.navigation_distance_m,
        "embodied_action.container_interactions": usage.embodied_action.container_interactions,
        "embodied_action.additional_observations": usage.embodied_action.additional_observations,
        "embodied_action.user_interruptions": usage.embodied_action.user_interruptions,
    }
    exceeded = tuple(name for name in BUDGET_DIMENSIONS if values[name] > caps[name])
    return BudgetVectorComplianceReceipt(
        budget_vector_sha256=budget.content_sha256,
        usage=usage,
        compliant_dimensions=tuple(name for name in BUDGET_DIMENSIONS if name not in exceeded),
        exceeded_dimensions=exceeded,
    )


class DevelopmentProcessIsolation(ContractModel):
    subprocess_per_arm_seed_split: bool
    hard_timeout_seconds: float = Field(gt=0.0)
    termination_grace_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_isolation(self) -> Self:
        if not self.subprocess_per_arm_seed_split:
            raise ValueError("development isolation requires one subprocess per arm/seed/split")
        return self


class FormalContainerIsolation(ContractModel):
    oci_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    hardware_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    network_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hard_timeout_seconds: float = Field(gt=0.0)
    termination_grace_seconds: float = Field(ge=0.0)
    read_only_root_filesystem: bool

    @model_validator(mode="after")
    def validate_isolation(self) -> Self:
        if not self.read_only_root_filesystem:
            raise ValueError("formal container root filesystem must be read-only")
        return self


class HybridExecutionIsolationProtocol(ContractModel):
    protocol_id: str = Field(min_length=1)
    development: DevelopmentProcessIsolation
    formal: FormalContainerIsolation

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class NonInferioritySuperiorityCriterion(ContractModel):
    criterion_id: str = Field(min_length=1)
    cluster_axis: ClusterAxis
    confidence_level: Probability
    minimum_contamination_reduction: float = Field(ge=0.0)
    maximum_recovery_latency_increase: float = Field(ge=0.0)
    maximum_action_utility_loss: float = Field(ge=0.0)
    budget_vector_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "minimum_contamination_reduction",
        "maximum_recovery_latency_increase",
        "maximum_action_utility_loss",
    )
    @classmethod
    def finite_thresholds(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("non-inferiority and superiority thresholds must be finite")
        return value

    @model_validator(mode="after")
    def validate_confidence(self) -> Self:
        if self.confidence_level != 0.95:
            raise ValueError("current bootstrap report supports only 0.95 confidence")
        return self


class NonInferioritySuperiorityDecision(ContractModel):
    criterion_id: str
    contamination_superiority_passed: bool
    recovery_noninferiority_passed: bool
    action_utility_noninferiority_passed: bool
    budget_compliance_passed: bool

    @property
    def criterion_satisfied(self) -> bool:
        return all(
            (
                self.contamination_superiority_passed,
                self.recovery_noninferiority_passed,
                self.action_utility_noninferiority_passed,
                self.budget_compliance_passed,
            )
        )


def evaluate_noninferiority_superiority(
    report: AntiContaminationBootstrapReport,
    *,
    criterion: NonInferioritySuperiorityCriterion,
    budget_receipt: BudgetVectorComplianceReceipt,
    report_receipt: OAMFormalEvidenceReceipt,
    criterion_receipt: OAMFormalEvidenceReceipt,
    budget_attestation: OAMFormalEvidenceReceipt,
    verifier: Ed25519AttestationVerifier,
) -> NonInferioritySuperiorityDecision:
    """Apply the frozen one-sided decision gates to clustered interval evidence."""

    if report.cluster_axis != criterion.cluster_axis:
        raise ValueError("criterion and bootstrap report use different cluster axes")
    if budget_receipt.budget_vector_sha256 != criterion.budget_vector_sha256:
        raise ValueError("criterion and compliance receipt use different budget vectors")
    verify_oam_formal_evidence_receipt(
        report,
        report_receipt,
        evidence_kind=OAMFormalEvidenceKind.BOOTSTRAP_REPORT,
        verifier=verifier,
    )
    verify_oam_formal_evidence_receipt(
        criterion,
        criterion_receipt,
        evidence_kind=OAMFormalEvidenceKind.DECISION_CRITERION,
        verifier=verifier,
    )
    verify_oam_formal_evidence_receipt(
        budget_receipt,
        budget_attestation,
        evidence_kind=OAMFormalEvidenceKind.BUDGET_RECEIPT,
        verifier=verifier,
    )
    return NonInferioritySuperiorityDecision(
        criterion_id=criterion.criterion_id,
        contamination_superiority_passed=(
            report.contamination_reduction.confidence_interval_95[0]
            > criterion.minimum_contamination_reduction
        ),
        recovery_noninferiority_passed=(
            report.recovery_latency_reduction.confidence_interval_95[0]
            >= -criterion.maximum_recovery_latency_increase
        ),
        action_utility_noninferiority_passed=(
            report.action_utility_gain.confidence_interval_95[0]
            >= -criterion.maximum_action_utility_loss
        ),
        budget_compliance_passed=budget_receipt.compliant,
    )
