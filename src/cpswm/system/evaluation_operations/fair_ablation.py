"""Matched-budget ablation contracts and joint calibration/utility metrics."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from math import log
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, Probability


class ObservationBudget(ContractModel):
    maximum_observation_actions: NonNegativeInt
    maximum_user_interruptions: NonNegativeInt
    maximum_observation_cost: float = Field(ge=0.0)
    maximum_elapsed_time_seconds: float = Field(ge=0.0)


class ModelBudget(ContractModel):
    maximum_train_compute_units: float = Field(ge=0.0)
    maximum_inference_compute_units: float = Field(ge=0.0)
    maximum_persistent_memory_bytes: NonNegativeInt
    maximum_latency_ms: float = Field(ge=0.0)
    maximum_parameter_count: NonNegativeInt


class TuningBudget(ContractModel):
    maximum_trials: PositiveInt
    maximum_compute_units: float = Field(gt=0.0)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective_name: str = Field(min_length=1)


class FairAblationArm(ContractModel):
    arm_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    components: tuple[str, ...] = Field(min_length=1)
    observation_budget: ObservationBudget
    model_budget: ModelBudget
    tuning_budget: TuningBudget
    independent_tuning_run_id: UUID
    observation_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_components(self) -> FairAblationArm:
        if len(self.components) != len(set(self.components)):
            raise ValueError("ablation arm components must be unique")
        return self


class FairAblationManifest(ContractModel):
    experiment_id: UUID
    baseline_arm_id: str = Field(min_length=1)
    arms: tuple[FairAblationArm, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def enforce_matched_budgets(self) -> FairAblationManifest:
        arm_ids = [arm.arm_id for arm in self.arms]
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError("ablation arm IDs must be unique")
        if self.baseline_arm_id not in arm_ids:
            raise ValueError("baseline_arm_id must identify a declared arm")
        reference = self.arms[0]
        for arm in self.arms[1:]:
            if arm.observation_budget != reference.observation_budget:
                raise ValueError("all ablation arms require the same observation budget")
            if arm.model_budget != reference.model_budget:
                raise ValueError("all ablation arms require the same model budget")
            if arm.tuning_budget != reference.tuning_budget:
                raise ValueError("all ablation arms require the same tuning budget")
            if arm.observation_trace_sha256 != reference.observation_trace_sha256:
                raise ValueError("all ablation arms require the same observation trace")
            if arm.test_split_sha256 != reference.test_split_sha256:
                raise ValueError("all ablation arms require the same frozen test split")
        tuning_runs = [arm.independent_tuning_run_id for arm in self.arms]
        if len(tuning_runs) != len(set(tuning_runs)):
            raise ValueError("each ablation arm requires an independent tuning run")
        return self


class ProjectOneAblationArmId(StrEnum):
    HABIT_BASELINE = "habit-baseline"
    HABIT_OBSERVATION_CORRECTED = "habit-observation-corrected"
    HABIT_VISITOR_ISOLATED = "habit-visitor-isolated"
    HABIT_ACTOR_RESIDUAL = "habit-actor-residual"
    ORDINARY_BOCPD = "ordinary-bocpd"
    # Legacy independent-per-cause BOCPD baseline (旧独立原因通道 BOCPD 基线).
    CAUSE_FACTORIZED_BOCPD = "cause-factorized-bocpd"
    # New real joint CF-BOCPD (JointCauseFactorizedBOCPD); added for v0.2 only.
    JOINT_CAUSE_FACTORIZED_BOCPD = "joint-cause-factorized-bocpd"
    # BOCPDMS (Knoblauch & Damoulas 2018) matched adaptation; added for the
    # four-arm scope only.  It is the direct disconfirming control for the claim
    # that joint run-length/cause inference is CF-BOCPD's contribution.
    BOCPDMS_MODEL_SELECTION = "bocpdms-model-selection"
    CHEH_INTERNAL_CONSISTENCY = "cheh-internal-consistency"
    CHEH_SOURCE_ALIGNED = "cheh-source-aligned"
    THRESHOLD_VERIFICATION = "retuned-threshold-verification"
    UTILITY_VERIFICATION = "decision-utility-verification"


#: Frozen v0.1 arm set (exactly 10).  Required-arm validation must use this
#: constant rather than iterating the enum, so adding a v0.2 member cannot
#: retroactively break v0.1 manifests or reports.
PROJECT_ONE_ARMS_V01_ORDERED: tuple[str, ...] = (
    ProjectOneAblationArmId.HABIT_BASELINE.value,
    ProjectOneAblationArmId.HABIT_OBSERVATION_CORRECTED.value,
    ProjectOneAblationArmId.HABIT_VISITOR_ISOLATED.value,
    ProjectOneAblationArmId.HABIT_ACTOR_RESIDUAL.value,
    ProjectOneAblationArmId.ORDINARY_BOCPD.value,
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value,
    ProjectOneAblationArmId.CHEH_INTERNAL_CONSISTENCY.value,
    ProjectOneAblationArmId.CHEH_SOURCE_ALIGNED.value,
    ProjectOneAblationArmId.THRESHOLD_VERIFICATION.value,
    ProjectOneAblationArmId.UTILITY_VERIFICATION.value,
)
PROJECT_ONE_ARMS_V01: frozenset[str] = frozenset(PROJECT_ONE_ARMS_V01_ORDERED)

#: Frozen v0.2 arm set (the 10 plus the joint arm), with the joint arm placed
#: immediately after the legacy independent baseline.
PROJECT_ONE_ARMS_V02_ORDERED: tuple[str, ...] = (
    ProjectOneAblationArmId.HABIT_BASELINE.value,
    ProjectOneAblationArmId.HABIT_OBSERVATION_CORRECTED.value,
    ProjectOneAblationArmId.HABIT_VISITOR_ISOLATED.value,
    ProjectOneAblationArmId.HABIT_ACTOR_RESIDUAL.value,
    ProjectOneAblationArmId.ORDINARY_BOCPD.value,
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value,
    ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD.value,
    ProjectOneAblationArmId.CHEH_INTERNAL_CONSISTENCY.value,
    ProjectOneAblationArmId.CHEH_SOURCE_ALIGNED.value,
    ProjectOneAblationArmId.THRESHOLD_VERIFICATION.value,
    ProjectOneAblationArmId.UTILITY_VERIFICATION.value,
)
PROJECT_ONE_ARMS_V02: frozenset[str] = frozenset(PROJECT_ONE_ARMS_V02_ORDERED)


class ProjectOneFairAblationManifest(FairAblationManifest):
    """Require exactly the frozen v0.1 arm set (10 arms)."""

    @model_validator(mode="after")
    def require_project_one_arms(self) -> ProjectOneFairAblationManifest:
        declared = {arm.arm_id for arm in self.arms}
        if declared != PROJECT_ONE_ARMS_V01:
            missing = sorted(PROJECT_ONE_ARMS_V01 - declared)
            extra = sorted(declared - PROJECT_ONE_ARMS_V01)
            raise ValueError(
                f"project-one v0.1 fair ablation requires exactly the 10 v0.1 arms; "
                f"missing={missing}, extra={extra}"
            )
        return self


class ProjectOneFairAblationManifestV2(FairAblationManifest):
    """Require exactly the frozen v0.2 arm set (11 arms, including the joint arm)."""

    @model_validator(mode="after")
    def require_project_one_v2_arms(self) -> ProjectOneFairAblationManifestV2:
        declared = {arm.arm_id for arm in self.arms}
        if declared != PROJECT_ONE_ARMS_V02:
            missing = sorted(PROJECT_ONE_ARMS_V02 - declared)
            extra = sorted(declared - PROJECT_ONE_ARMS_V02)
            raise ValueError(
                f"project-one v0.2 fair ablation requires exactly the 11 v0.2 arms; "
                f"missing={missing}, extra={extra}"
            )
        return self


class CalibrationUtilityCase(ContractModel):
    case_id: str = Field(min_length=1)
    predicted_success_probability: Probability
    success: bool
    realized_action_utility: float
    oracle_action_utility: float
    elapsed_time_seconds: float = Field(ge=0.0)
    user_interruptions: NonNegativeInt = 0
    observation_actions: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_oracle_bound(self) -> CalibrationUtilityCase:
        if self.realized_action_utility > self.oracle_action_utility:
            raise ValueError("oracle action utility cannot be below realized utility")
        return self


class JointCalibrationUtilityReport(ContractModel):
    sample_count: PositiveInt
    ece: Probability
    brier_score: float = Field(ge=0.0)
    negative_log_likelihood: float = Field(ge=0.0)
    action_success_rate: Probability
    mean_action_utility: float
    mean_true_environment_regret: float = Field(ge=0.0)
    mean_elapsed_time_seconds: float = Field(ge=0.0)
    mean_user_interruptions: float = Field(ge=0.0)
    mean_observation_actions: float = Field(ge=0.0)


class CalibrationUtilityEvaluator:
    """Report proper scoring rules beside realized action-level value."""

    def evaluate(
        self,
        cases: Sequence[CalibrationUtilityCase],
        *,
        ece_bin_count: int = 10,
    ) -> JointCalibrationUtilityReport:
        if not cases:
            raise ValueError("joint calibration/utility evaluation requires cases")
        if ece_bin_count < 2:
            raise ValueError("ece_bin_count must be at least two")
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("calibration/utility case IDs must be unique")
        count = len(cases)
        epsilon = 1e-12
        probabilities = [case.predicted_success_probability for case in cases]
        outcomes = [1.0 if case.success else 0.0 for case in cases]
        brier = (
            sum(
                (probability - outcome) ** 2
                for probability, outcome in zip(probabilities, outcomes, strict=True)
            )
            / count
        )
        nll = (
            -sum(
                outcome * log(max(probability, epsilon))
                + (1.0 - outcome) * log(max(1.0 - probability, epsilon))
                for probability, outcome in zip(probabilities, outcomes, strict=True)
            )
            / count
        )
        return JointCalibrationUtilityReport(
            sample_count=count,
            ece=self._ece(probabilities, outcomes, ece_bin_count),
            brier_score=brier,
            negative_log_likelihood=nll,
            action_success_rate=sum(outcomes) / count,
            mean_action_utility=sum(case.realized_action_utility for case in cases) / count,
            mean_true_environment_regret=sum(
                case.oracle_action_utility - case.realized_action_utility for case in cases
            )
            / count,
            mean_elapsed_time_seconds=sum(case.elapsed_time_seconds for case in cases) / count,
            mean_user_interruptions=sum(case.user_interruptions for case in cases) / count,
            mean_observation_actions=sum(case.observation_actions for case in cases) / count,
        )

    @staticmethod
    def _ece(probabilities: list[float], outcomes: list[float], bin_count: int) -> float:
        error = 0.0
        for bin_index in range(bin_count):
            lower = bin_index / bin_count
            upper = (bin_index + 1) / bin_count
            members = [
                index
                for index, probability in enumerate(probabilities)
                if lower <= probability < upper
                or (bin_index == bin_count - 1 and probability == 1.0)
            ]
            if not members:
                continue
            confidence = sum(probabilities[index] for index in members) / len(members)
            accuracy = sum(outcomes[index] for index in members) / len(members)
            error += len(members) / len(probabilities) * abs(confidence - accuracy)
        return error
