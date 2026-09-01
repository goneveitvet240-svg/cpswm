"""Action-level matched death test for the Project One SHIFT detectors.

This is deliberately a research gate, not another authority layer.  The three
detectors are independently tuned on validation data, then connected to one
frozen detector-neutral habit reset/consolidation policy.  Pilot seeds estimate
paired variance before the TEST seed partition is inspected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from math import ceil, exp, log
from statistics import NormalDist, fmean, stdev
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import ObservationDetectionResult, ObservationOutcome
from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, Probability
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions.cause_factorized_bocpd import (
    CauseFactorizedBOCPD,
    ChangeCause,
)
from cpswm.world_model.habits_transitions.joint_cause_bocpd import (
    CauseSignalFrame,
    JointCauseFactorizedBOCPD,
)

from .d0_shift_scenarios import D0VisibleSimulationRun
from .fair_ablation import ProjectOneAblationArmId
from .online_shift_attribution import (
    OnlineShiftAttributionCase,
    OnlineShiftCaseInput,
    OnlineShiftCaseTruth,
    OnlineShiftEvaluator,
    OnlineShiftGeneratedCase,
    OnlineShiftPrediction,
    OnlineShiftReport,
    OnlineShiftSplit,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from .project_one_shift_gates import _SEARCH_SPACES, SHIFT_THREE_ARMS
from .shift_attribution import ShiftCause
from .shift_baselines import OnlineCauseFactorizedBOCPDBaseline

PRIMARY_ENDPOINT_ID: Literal["downstream-action-regret.balanced-habit-vs-nonhabit@1"] = (
    "downstream-action-regret.balanced-habit-vs-nonhabit@1"
)
KEY_SECONDARY_ENDPOINT_ID: Literal["corrupted-habit-mass.mean-per-case@1"] = (
    "corrupted-habit-mass.mean-per-case@1"
)
ALLOWED_CLAIM_IDS = (
    "claim.synthetic-prefix-online-shift-action-death-test-reported@5",
    "claim.shared-policy-track-reported@1",
    "claim.independently-retuned-policy-track-reported@1",
)
ALLOWED_CLAIM_IDS_V6 = (
    "claim.synthetic-prefix-online-shift-action-death-test-reported@6",
    "claim.shared-policy-track-reported@1",
    "claim.independently-retuned-policy-track-reported@1",
    "claim.active-verification-and-multilabel-policy-reported@1",
)
FORBIDDEN_CLAIM_IDS = (
    "claim.general-method-superiority.forbidden@3",
    "claim.state-of-the-art.forbidden@3",
    "claim.external-validity.forbidden@1",
    "claim.formal-structure-one-b1-complete.forbidden@3",
    "claim.all-eleven-arms-experimentally-complete.forbidden@3",
    "claim.v4-confirmatory-rebuild-joint.forbidden@1",
    "claim.v4-confirmatory-legacy-advantage.forbidden@1",
)


def _claim_ids(protocol_version: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    allowed = ALLOWED_CLAIM_IDS_V6 if protocol_version.endswith("@6") else ALLOWED_CLAIM_IDS
    return allowed, FORBIDDEN_CLAIM_IDS


POWER_REFERENCES = (
    ProjectOneAblationArmId.ORDINARY_BOCPD,
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
)
POWER_ENDPOINTS = (
    (
        PRIMARY_ENDPOINT_ID,
        "primary",
        "balanced_downstream_action_regret",
        "practical_regret_mde",
    ),
    (
        KEY_SECONDARY_ENDPOINT_ID,
        "key_secondary",
        "corrupted_habit_mass",
        "practical_corruption_mde",
    ),
)


class ResearchDecision(StrEnum):
    CONTINUE_JOINT = "continue_joint"
    REBUILD_JOINT = "rebuild_joint"
    USE_ORDINARY = "use_ordinary"
    INCONCLUSIVE = "inconclusive"
    BLOCK_UNDERPOWERED = "block_underpowered"


class EvaluationTrack(StrEnum):
    SHARED_POLICY = "shared_policy"
    INDEPENDENTLY_RETUNED_POLICY = "independently_retuned_policy"


class FrozenActionPolicy(ContractModel):
    policy_id: Literal[
        "habit-reset-consolidation-policy@5",
        "habit-reset-consolidation-policy@6",
    ] = "habit-reset-consolidation-policy@5"
    probability_temperature: float = Field(default=1.0, gt=0.0)
    reset_probability_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    consolidation_probability_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    attribution_margin: float = Field(default=0.15, ge=0.0, lt=1.0)
    verification_cost: float = Field(default=0.05, ge=0.0)
    false_reset_cost: float = Field(default=0.25, ge=0.0)
    missed_reset_daily_cost: float = Field(default=0.10, ge=0.0)
    corrupted_mass_daily_cost: float = Field(default=0.10, ge=0.0)
    practical_regret_mde: float = Field(default=0.05, gt=0.0, le=1.0)
    practical_corruption_mde: float = Field(default=0.02, gt=0.0, le=1.0)
    verification_owner_probability_threshold: float = Field(default=0.60, gt=0.5, le=1.0)
    verification_required_matching_detections: Literal[2] = 2
    active_verification_enabled: bool = False
    active_verification_latency_hours: PositiveInt = 12
    active_verification_positive_owner_probability: float = Field(default=0.98, gt=0.5, le=1.0)
    active_verification_negative_owner_probability: float = Field(default=0.02, ge=0.0, lt=0.5)
    multi_label_consolidation: bool = False

    @model_validator(mode="after")
    def validate_threshold_order(self) -> FrozenActionPolicy:
        if self.consolidation_probability_threshold < self.reset_probability_threshold:
            raise ValueError("consolidation threshold must not be below reset threshold")
        if self.policy_id.endswith("@6") and not (
            self.active_verification_enabled and self.multi_label_consolidation
        ):
            raise ValueError("policy@6 requires active verification and multi-label consolidation")
        return self


class ActionSeedPlan(ContractModel):
    validation_seeds: tuple[NonNegativeInt, ...] = (4101, 4111, 4127, 4133, 4139)
    pilot_seeds: tuple[NonNegativeInt, ...] = (
        5101,
        5107,
        5113,
        5119,
        5147,
        5153,
        5167,
        5171,
    )
    test_seeds: tuple[NonNegativeInt, ...] = tuple(range(15101, 15201, 2))

    @model_validator(mode="after")
    def validate_partitions(self) -> ActionSeedPlan:
        if len(self.validation_seeds) < 3 or len(self.pilot_seeds) < 5:
            raise ValueError("validation requires >=3 seeds and pilot requires >=5 seeds")
        flattened = self.validation_seeds + self.pilot_seeds + self.test_seeds
        if len(flattened) != len(set(flattened)):
            raise ValueError("validation, pilot, and TEST seeds must be globally disjoint")
        return self


class UtilitySensitivityScenario(ContractModel):
    scenario_id: Literal[
        "base@1",
        "false-action-cost-x1.5@1",
        "unrecovered-habit-cost-x1.5@1",
        "verification-cost-x2@1",
    ]
    false_reset_multiplier: float = Field(default=1.0, gt=0.0)
    unrecovered_habit_multiplier: float = Field(default=1.0, gt=0.0)
    corrupted_mass_multiplier: float = Field(default=1.0, gt=0.0)
    verification_multiplier: float = Field(default=1.0, gt=0.0)


def _canonical_utility_scenarios() -> tuple[UtilitySensitivityScenario, ...]:
    return (
        UtilitySensitivityScenario(scenario_id="base@1"),
        UtilitySensitivityScenario(
            scenario_id="false-action-cost-x1.5@1",
            false_reset_multiplier=1.5,
            corrupted_mass_multiplier=1.5,
        ),
        UtilitySensitivityScenario(
            scenario_id="unrecovered-habit-cost-x1.5@1",
            unrecovered_habit_multiplier=1.5,
        ),
        UtilitySensitivityScenario(
            scenario_id="verification-cost-x2@1",
            verification_multiplier=2.0,
        ),
    )


class ProjectOneShiftActionDeathTestConfig(ContractModel):
    protocol_version: Literal[
        "project-one-shift-action-death-test@5",
        "project-one-shift-action-death-test@6",
    ] = "project-one-shift-action-death-test@5"
    seed_plan: ActionSeedPlan = Field(default_factory=ActionSeedPlan)
    action_policy: FrozenActionPolicy = Field(default_factory=FrozenActionPolicy)
    duration_days: PositiveInt = 10
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    target_power: float = Field(default=0.80, gt=0.0, lt=1.0)
    power_stddev_safety_factor: float = Field(default=1.5, ge=1.0)
    power_paired_stddev_floor: float = Field(default=0.05, gt=0.0)
    bootstrap_samples: PositiveInt = 2000
    utility_sensitivity_scenarios: tuple[UtilitySensitivityScenario, ...] = Field(
        default_factory=_canonical_utility_scenarios
    )

    @model_validator(mode="after")
    def validate_config(self) -> ProjectOneShiftActionDeathTestConfig:
        if self.duration_days < 8:
            raise ValueError("action trajectories require at least eight days")
        if self.bootstrap_samples < 500:
            raise ValueError("paired seed bootstrap requires at least 500 samples")
        if self.utility_sensitivity_scenarios != _canonical_utility_scenarios():
            raise ValueError("utility sensitivity scenarios must equal the canonical set")
        if self.protocol_version.endswith("@6"):
            legacy_test_seeds = set(range(15101, 15201, 2))
            if len(self.seed_plan.test_seeds) < 152:
                raise ValueError("protocol@6 requires at least 152 preregistered TEST seeds")
            if legacy_test_seeds.intersection(self.seed_plan.test_seeds):
                raise ValueError("protocol@6 TEST seeds must be fresh against protocol@5")
            if not self.action_policy.policy_id.endswith("@6"):
                raise ValueError("protocol@6 requires policy@6")
        return self


class PrefixPosteriorSnapshot(ContractModel):
    as_of_time: datetime
    change_time_estimate: datetime | None
    posterior: dict[ShiftCause, Probability] = Field(min_length=1)
    prefix_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_evidence_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_prefix_snapshot(self) -> PrefixPosteriorSnapshot:
        if self.change_time_estimate is not None and self.change_time_estimate >= self.as_of_time:
            raise ValueError("change-time estimate must precede the prefix decision cutoff")
        if len(self.visible_evidence_record_ids) != len(set(self.visible_evidence_record_ids)):
            raise ValueError("prefix evidence IDs must be unique")
        return self


class PrefixOnlinePrediction(ContractModel):
    case_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    snapshots: tuple[PrefixPosteriorSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trajectory(self) -> PrefixOnlinePrediction:
        cutoffs = tuple(item.as_of_time for item in self.snapshots)
        if cutoffs != tuple(sorted(set(cutoffs))):
            raise ValueError("prefix prediction cutoffs must be unique and increasing")
        estimates = tuple(
            item.change_time_estimate
            for item in self.snapshots
            if item.change_time_estimate is not None
        )
        if estimates and len(set(estimates)) != 1:
            raise ValueError("first online change-time estimate must remain frozen")
        for earlier, later in zip(self.snapshots, self.snapshots[1:], strict=False):
            if not set(earlier.visible_evidence_record_ids).issubset(
                later.visible_evidence_record_ids
            ):
                raise ValueError("visible evidence must grow monotonically across prefixes")
        return self


class VerificationEvidence(ContractModel):
    predicate_id: Literal[
        "owner-associated-repeat-object-location@1",
        "active-owner-confirmation-across-observations@1",
    ] = "owner-associated-repeat-object-location@1"
    object_instance_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    first_detection_result_id: str = Field(min_length=1)
    second_detection_result_id: str = Field(min_length=1)
    first_evidence_time: datetime
    second_evidence_time: datetime
    minimum_owner_posterior: Probability

    @model_validator(mode="after")
    def validate_evidence(self) -> VerificationEvidence:
        if self.first_detection_result_id == self.second_detection_result_id:
            raise ValueError("verification requires two distinct detection results")
        if not self.first_evidence_time < self.second_evidence_time:
            raise ValueError("verification detections must occur at increasing times")
        return self


class CaseActionOutcome(ContractModel):
    case_id: str = Field(min_length=1)
    scenario_seed: NonNegativeInt
    habit_shift_required: bool
    reset_issued: bool
    consolidation_issued: bool
    verification_issued: bool
    action_sequence: tuple[
        Literal["RESET_OLD_REGIME", "VERIFY_NEW_EVIDENCE", "CONSOLIDATE_NEW_REGIME"], ...
    ]
    change_time_estimate: datetime | None
    decision_time: datetime | None
    posterior_at_decision: dict[ShiftCause, Probability] | None
    reset_time: datetime | None
    verification_time: datetime | None
    consolidation_time: datetime | None
    verification_evidence: VerificationEvidence | None
    false_reset: bool
    missed_reset: bool
    missed_consolidation: bool
    false_consolidation: bool
    corrupted_habit_mass: Probability
    recovery_time_days: float = Field(ge=0.0)
    unnecessary_verification_cost: float = Field(ge=0.0)
    downstream_action_regret: Probability
    task_success_proxy: bool

    @model_validator(mode="after")
    def validate_action_sequence(self) -> CaseActionOutcome:
        if self.consolidation_issued and not self.reset_issued:
            raise ValueError("consolidation requires a preceding reset")
        if self.consolidation_issued:
            expected: tuple[str, ...] = (
                "RESET_OLD_REGIME",
                "VERIFY_NEW_EVIDENCE",
                "CONSOLIDATE_NEW_REGIME",
            )
        elif self.reset_issued and self.verification_issued:
            expected = ("RESET_OLD_REGIME", "VERIFY_NEW_EVIDENCE")
        elif self.reset_issued:
            expected = ("RESET_OLD_REGIME",)
        elif self.verification_issued:
            expected = ("VERIFY_NEW_EVIDENCE",)
        else:
            expected = ()
        if self.action_sequence != expected:
            raise ValueError("action sequence does not encode the declared two-phase transition")
        if self.reset_issued != (self.reset_time is not None):
            raise ValueError("reset timestamp does not match reset state")
        if self.reset_issued != (self.decision_time is not None):
            raise ValueError("reset state must bind an explicit decision time")
        if self.reset_issued != (self.posterior_at_decision is not None):
            raise ValueError("reset state must bind the posterior at decision")
        if self.reset_time != self.decision_time:
            raise ValueError("reset executes at decision time, not at estimated change time")
        if (
            self.change_time_estimate is not None
            and self.decision_time is not None
            and self.change_time_estimate >= self.decision_time
        ):
            raise ValueError("change-time estimate must precede decision time")
        if self.verification_issued != (self.verification_time is not None):
            raise ValueError("verification timestamp does not match verification state")
        if self.verification_issued != (self.verification_evidence is not None):
            raise ValueError("verification state must bind semantic evidence")
        if self.verification_evidence is not None and (
            self.verification_time != self.verification_evidence.second_evidence_time
        ):
            raise ValueError("verification time must equal the predicate satisfaction time")
        if self.consolidation_issued != (self.consolidation_time is not None):
            raise ValueError("consolidation timestamp does not match consolidation state")
        if self.consolidation_issued and (
            self.reset_time is None
            or self.verification_time is None
            or self.consolidation_time is None
            or not self.reset_time < self.verification_time < self.consolidation_time
        ):
            raise ValueError("consolidation state transitions must cross increasing timesteps")
        return self


class ArmActionMetrics(ContractModel):
    sample_count: PositiveInt
    false_reset_rate: Probability
    missed_reset_rate: Probability
    missed_consolidation_rate: Probability
    false_consolidation_rate: Probability
    corrupted_habit_mass: Probability
    recovery_time_days: float = Field(ge=0.0)
    unnecessary_verification_cost: float = Field(ge=0.0)
    downstream_action_regret: Probability
    balanced_downstream_action_regret: Probability
    task_success_proxy_rate: Probability


class ActionCaseTruth(ContractModel):
    truth: OnlineShiftCaseTruth
    stream_start_time: datetime
    duration_days: PositiveInt
    model_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_horizon(self) -> ActionCaseTruth:
        horizon_end = self.stream_start_time + timedelta(days=self.duration_days)
        if not self.stream_start_time < self.truth.change_time < horizon_end:
            raise ValueError("action truth change time lies outside its stream horizon")
        if self.evaluator_truth_sha256 != content_sha256(self.truth):
            raise ValueError("action truth hash mismatch")
        return self


class SplitInputArtifact(ContractModel):
    split_id: Literal["validation", "pilot", "test"]
    cases: tuple[OnlineShiftGeneratedCase, ...] = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_artifact(self) -> SplitInputArtifact:
        expected = OnlineShiftSplit.TEST if self.split_id == "test" else OnlineShiftSplit.VALIDATION
        if any(item.evaluator_truth.split != expected for item in self.cases):
            raise ValueError("input artifact carries the wrong split")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("input artifact hash mismatch")
        return self


class ShiftRuntimeParameterBinding(ContractModel):
    """One declared SHIFT parameter bound to the component that consumed it."""

    parameter: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    configured_value: int | float
    runtime_value: int | float
    component_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShiftRuntimeParameterReceipt(ContractModel):
    arm_id: ProjectOneAblationArmId
    params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bindings: tuple[ShiftRuntimeParameterBinding, ...] = Field(min_length=1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ShiftRuntimeParameterReceipt:
        names = tuple(item.parameter for item in self.bindings)
        if len(names) != len(set(names)):
            raise ValueError("runtime parameter receipt contains duplicate bindings")
        if any(item.configured_value != item.runtime_value for item in self.bindings):
            raise ValueError("configured SHIFT parameter did not reach its runtime component")
        payload = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != content_sha256(payload):
            raise ValueError("runtime parameter receipt hash mismatch")
        return self


class UnusedShiftParameterError(ValueError):
    """A declared parameter was not consumed, or a mutation had no runtime effect."""


def build_shift_runtime_parameter_receipt(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
) -> ShiftRuntimeParameterReceipt:
    """Bind every candidate field to an actual constructor/run argument.

    The allow-list is intentionally arm-specific.  Adding a field to a search
    space without wiring it below fails immediately instead of producing a
    tuning result for a knob the detector never read.
    """

    common = {
        "warmup_days": "evidence_frame_adapter+detector.run",
        "hazard_probability": "bocpd.detector",
        "detection_threshold": "bocpd.detector.run",
    }
    targets = dict(common)
    if arm is ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD:
        targets.update(
            {
                "beam_width": "joint_cf_bocpd.detector",
                "maximum_simultaneous_causes": "joint_cf_bocpd.detector",
                "simultaneous_hazard_scale": "joint_cf_bocpd.detector",
            }
        )
    missing = set(params) - set(targets)
    unused = set(targets) - set(params)
    if missing or unused:
        raise UnusedShiftParameterError(
            f"SHIFT runtime parameter coverage mismatch: "
            f"unbound={sorted(missing)}, missing={sorted(unused)}"
        )
    bindings = tuple(
        ShiftRuntimeParameterBinding(
            parameter=name,
            target_component=targets[name],
            configured_value=value,
            runtime_value=value,
            component_config_sha256=content_sha256(
                {"component": targets[name], "parameter": name, "value": value}
            ),
            runtime_trace_sha256=content_sha256(
                {"arm": arm, "component": targets[name], "observed": value}
            ),
        )
        for name, value in sorted(params.items())
    )
    payload = {
        "arm_id": arm,
        "params_sha256": content_sha256(params),
        "bindings": bindings,
    }
    return ShiftRuntimeParameterReceipt(**payload, receipt_sha256=content_sha256(payload))


def reject_unused_shift_parameter_change(
    arm: ProjectOneAblationArmId,
    before: dict[str, int | float],
    after: dict[str, int | float],
) -> None:
    """Reject a changed knob unless its component config or trace also changes."""

    before_receipt = build_shift_runtime_parameter_receipt(arm, before)
    after_receipt = build_shift_runtime_parameter_receipt(arm, after)
    before_by_name = {item.parameter: item for item in before_receipt.bindings}
    after_by_name = {item.parameter: item for item in after_receipt.bindings}
    for name in set(before) | set(after):
        if before.get(name) == after.get(name):
            continue
        if name not in before_by_name or name not in after_by_name:
            raise UnusedShiftParameterError(f"changed parameter {name!r} is not injected")
        if (
            before_by_name[name].component_config_sha256
            == after_by_name[name].component_config_sha256
            and before_by_name[name].runtime_trace_sha256
            == after_by_name[name].runtime_trace_sha256
        ):
            raise UnusedShiftParameterError(
                f"changed parameter {name!r} altered no runtime component"
            )


class ValidationPredictionCandidate(ContractModel):
    arm_id: ProjectOneAblationArmId
    candidate_index: NonNegativeInt
    params: dict[str, int | float]
    params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions: tuple[PrefixOnlinePrediction, ...] = Field(min_length=1)
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_parameter_receipt: ShiftRuntimeParameterReceipt
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_record(self) -> ValidationPredictionCandidate:
        if self.params_sha256 != content_sha256(self.params):
            raise ValueError("candidate params hash mismatch")
        if self.predictions_sha256 != content_sha256(self.predictions):
            raise ValueError("candidate predictions hash mismatch")
        if (
            self.runtime_parameter_receipt.arm_id != self.arm_id
            or self.runtime_parameter_receipt.params_sha256 != self.params_sha256
            or {item.parameter for item in self.runtime_parameter_receipt.bindings}
            != set(self.params)
        ):
            raise ValueError("candidate runtime parameter receipt mismatch")
        payload = self.model_dump(mode="json", exclude={"record_sha256"})
        if self.record_sha256 != content_sha256(payload):
            raise ValueError("candidate record hash mismatch")
        return self


class ArmValidationPredictionLedger(ContractModel):
    arm_id: ProjectOneAblationArmId
    validation_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[ValidationPredictionCandidate, ...] = Field(min_length=1)
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_ledger(self) -> ArmValidationPredictionLedger:
        space = _SEARCH_SPACES[self.arm_id]
        if len(self.candidates) != len(space):
            raise ValueError("validation prediction ledger must cover every detector candidate")
        for index, (candidate, params) in enumerate(zip(self.candidates, space, strict=True)):
            if (
                candidate.arm_id != self.arm_id
                or candidate.candidate_index != index
                or candidate.params != params
                or candidate.validation_input_sha256 != self.validation_input_sha256
            ):
                raise ValueError("validation prediction ledger topology mismatch")
        payload = self.model_dump(mode="json", exclude={"ledger_sha256"})
        if self.ledger_sha256 != content_sha256(payload):
            raise ValueError("validation prediction ledger hash mismatch")
        return self


class ArmActionArtifact(ContractModel):
    arm_id: ProjectOneAblationArmId
    split_id: Literal["validation", "pilot", "test"]
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: FrozenActionPolicy
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_truths: tuple[ActionCaseTruth, ...] = Field(min_length=1)
    predictions: tuple[PrefixOnlinePrediction, ...] = Field(min_length=1)
    outcomes: tuple[CaseActionOutcome, ...] = Field(min_length=1)
    metrics: ArmActionMetrics
    mechanism_metrics: OnlineShiftReport
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_artifact(self) -> ArmActionArtifact:
        if self.policy_sha256 != content_sha256(self.policy):
            raise ValueError("artifact policy hash mismatch")
        expected_truth_split = (
            OnlineShiftSplit.TEST if self.split_id == "test" else OnlineShiftSplit.VALIDATION
        )
        if any(item.truth.split != expected_truth_split for item in self.case_truths):
            raise ValueError("artifact truths carry the wrong split label")
        if len(self.predictions) != len(self.outcomes) or len(self.case_truths) != len(
            self.outcomes
        ):
            raise ValueError("truth/prediction/outcome case counts differ")
        if {str(item.case_id) for item in self.predictions} != {
            item.case_id for item in self.outcomes
        } or {str(item.truth.case_id) for item in self.case_truths} != {
            item.case_id for item in self.outcomes
        }:
            raise ValueError("prediction/outcome case IDs differ")
        prediction_by_id = {str(item.case_id): item for item in self.predictions}
        truth_by_id = {str(item.truth.case_id): item for item in self.case_truths}
        recomputed_outcomes = tuple(
            _case_outcome(
                truth_by_id[item.case_id].truth,
                prediction_by_id[item.case_id],
                self.policy,
                model_input=None,
                stream_start_time=truth_by_id[item.case_id].stream_start_time,
                duration_days=truth_by_id[item.case_id].duration_days,
                verification_evidence=item.verification_evidence,
            )
            for item in self.outcomes
        )
        if recomputed_outcomes != self.outcomes:
            raise ValueError("case action outcomes do not recompute from truth and predictions")
        if self.metrics != aggregate_action_metrics(self.outcomes):
            raise ValueError("action metrics do not recompute from case outcomes")
        rebound = _terminal_attribution_cases(self.case_truths, prediction_by_id)
        if self.mechanism_metrics != OnlineShiftEvaluator().evaluate(rebound):
            raise ValueError("mechanism metrics do not recompute from terminal prefix states")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("action artifact hash mismatch")
        return self


class ActionPolicyBaselineId(StrEnum):
    NEVER_ACT = "never-act"
    ALWAYS_RESET_VERIFY = "always-reset-verify"


class ActionPolicyBaselineArtifact(ContractModel):
    baseline_id: ActionPolicyBaselineId
    split_id: Literal["test"] = "test"
    outcomes: tuple[CaseActionOutcome, ...] = Field(min_length=1)
    metrics: ArmActionMetrics
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_baseline(self) -> ActionPolicyBaselineArtifact:
        if self.metrics != aggregate_action_metrics(self.outcomes):
            raise ValueError("action baseline metrics do not recompute")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("action baseline artifact hash mismatch")
        return self


class ArmActionTuningRecord(ContractModel):
    arm_id: ProjectOneAblationArmId
    evaluated_trial_count: PositiveInt
    validation_case_count: PositiveInt
    selected_params: dict[str, int | float]
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_validation_regret: Probability
    search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_candidate_index: NonNegativeInt

    @model_validator(mode="after")
    def validate_record(self) -> ArmActionTuningRecord:
        space = _SEARCH_SPACES[self.arm_id]
        if self.evaluated_trial_count != len(space):
            raise ValueError("independent tuning must cover the complete declared search space")
        if self.selected_params not in space:
            raise ValueError("selected parameters are outside the arm search space")
        if self.selected_params_sha256 != content_sha256(self.selected_params):
            raise ValueError("selected parameter hash mismatch")
        if self.search_space_sha256 != content_sha256(space):
            raise ValueError("search space hash mismatch")
        if space[self.selected_candidate_index] != self.selected_params:
            raise ValueError("selected candidate index does not bind selected params")
        return self


def _retuned_policy_space(template: FrozenActionPolicy) -> tuple[FrozenActionPolicy, ...]:
    return tuple(
        template.model_copy(
            update={
                "probability_temperature": temperature,
                "reset_probability_threshold": reset,
                "consolidation_probability_threshold": consolidation,
                "attribution_margin": margin,
            }
        )
        for temperature in (0.5, 1.0, 2.0)
        for reset in (0.25, 0.4, 0.55, 0.7)
        for consolidation in (0.4, 0.55, 0.7, 0.85)
        if consolidation >= reset
        for margin in (0.0, 0.1, 0.2)
    )


class ArmRetunedPolicyTuningRecord(ContractModel):
    arm_id: ProjectOneAblationArmId
    detector_trial_count: PositiveInt
    policy_trial_count: PositiveInt
    evaluated_candidate_count: PositiveInt
    validation_case_count: PositiveInt
    selected_params: dict[str, int | float]
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_template: FrozenActionPolicy
    selected_policy: FrozenActionPolicy
    selected_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_validation_regret: Probability
    detector_search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_detector_index: NonNegativeInt
    selected_policy_index: NonNegativeInt

    @model_validator(mode="after")
    def validate_record(self) -> ArmRetunedPolicyTuningRecord:
        detector_space = _SEARCH_SPACES[self.arm_id]
        policy_space = _retuned_policy_space(self.policy_template)
        if self.detector_trial_count != len(detector_space):
            raise ValueError("retuned track detector search is incomplete")
        if self.policy_trial_count != len(policy_space):
            raise ValueError("retuned track policy search is incomplete")
        if self.evaluated_candidate_count != len(detector_space) * len(policy_space):
            raise ValueError("retuned track must evaluate the detector-policy cross product")
        if self.selected_params not in detector_space:
            raise ValueError("retuned detector params are outside the shared search space")
        if self.selected_policy not in policy_space:
            raise ValueError("retuned policy is outside the shared policy search space")
        if self.selected_params_sha256 != content_sha256(self.selected_params):
            raise ValueError("retuned detector parameter hash mismatch")
        if self.selected_policy_sha256 != content_sha256(self.selected_policy):
            raise ValueError("retuned policy hash mismatch")
        if self.detector_search_space_sha256 != content_sha256(detector_space):
            raise ValueError("retuned detector search-space hash mismatch")
        if self.policy_search_space_sha256 != content_sha256(policy_space):
            raise ValueError("retuned policy search-space hash mismatch")
        if detector_space[self.selected_detector_index] != self.selected_params:
            raise ValueError("selected detector index mismatch")
        if policy_space[self.selected_policy_index] != self.selected_policy:
            raise ValueError("selected policy index mismatch")
        return self


class MetricPowerAnalysis(ContractModel):
    endpoint_id: Literal[
        "downstream-action-regret.balanced-habit-vs-nonhabit@1",
        "corrupted-habit-mass.mean-per-case@1",
    ]
    reference_arm_id: Literal[
        ProjectOneAblationArmId.ORDINARY_BOCPD,
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
    ]
    role: Literal["primary", "key_secondary"]
    empirical_paired_stddev: float = Field(ge=0.0)
    stddev_safety_factor: float = Field(ge=1.0)
    paired_stddev_floor: float = Field(gt=0.0)
    powered_paired_stddev: float = Field(ge=0.0)
    minimum_detectable_effect: float = Field(gt=0.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    target_power: float = Field(gt=0.0, lt=1.0)
    pilot_seed_count: PositiveInt
    required_test_seed_count: PositiveInt
    planned_test_seed_count: NonNegativeInt
    status: Literal["PASS", "BLOCK"]

    @model_validator(mode="after")
    def validate_power(self) -> MetricPowerAnalysis:
        expected = required_paired_seed_count(
            self.powered_paired_stddev,
            self.minimum_detectable_effect,
            alpha=self.alpha,
            target_power=self.target_power,
        )
        if self.required_test_seed_count != expected:
            raise ValueError("required seed count does not recompute")
        if self.powered_paired_stddev != max(
            self.empirical_paired_stddev * self.stddev_safety_factor,
            self.paired_stddev_floor,
        ):
            raise ValueError("powered stddev does not apply the frozen factor and floor")
        expected_status = (
            "PASS" if self.planned_test_seed_count >= self.required_test_seed_count else "BLOCK"
        )
        if self.status != expected_status:
            raise ValueError("power status disagrees with the planned TEST count")
        return self


class PairedActionInterval(ContractModel):
    endpoint_id: str = Field(min_length=1)
    candidate_arm_id: Literal[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD]
    reference_arm_id: ProjectOneAblationArmId
    difference_joint_minus_reference: float
    lower_95: float
    upper_95: float
    bootstrap_samples: PositiveInt
    resampling_unit: Literal["scenario_seed"] = "scenario_seed"


class ActionBaselineInterval(ContractModel):
    track: EvaluationTrack
    endpoint_id: Literal["downstream-action-regret.balanced-habit-vs-nonhabit@1"] = (
        PRIMARY_ENDPOINT_ID
    )
    candidate_arm_id: ProjectOneAblationArmId
    reference_baseline_id: ActionPolicyBaselineId
    difference_detector_minus_baseline: float
    lower_95: float
    upper_95: float
    bootstrap_samples: PositiveInt
    resampling_unit: Literal["scenario_seed"] = "scenario_seed"


class UtilitySensitivityResult(ContractModel):
    track: EvaluationTrack
    scenario_id: str = Field(min_length=1)
    metrics_by_arm: dict[ProjectOneAblationArmId, ArmActionMetrics]
    regret_intervals: tuple[PairedActionInterval, ...]


class PreregisteredDecision(ContractModel):
    decision: ResearchDecision
    primary_joint_minus_ordinary: PairedActionInterval | None
    corruption_joint_minus_ordinary: PairedActionInterval | None
    primary_joint_minus_legacy: PairedActionInterval | None
    corruption_joint_minus_legacy: PairedActionInterval | None
    primary_practical_threshold: float = Field(gt=0.0)
    corruption_practical_threshold: float = Field(gt=0.0)
    rationale_id: str = Field(min_length=1)


class CrossTrackDecision(ContractModel):
    decision: ResearchDecision
    shared_policy_decision: ResearchDecision
    independently_retuned_policy_decision: ResearchDecision
    rationale_id: str = Field(min_length=1)


class ProjectOneShiftActionDeathTestReport(ContractModel):
    protocol_version: Literal[
        "project-one-shift-action-death-test@5",
        "project-one-shift-action-death-test@6",
    ]
    config: ProjectOneShiftActionDeathTestConfig
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    primary_endpoint_id: Literal["downstream-action-regret.balanced-habit-vs-nonhabit@1"] = (
        PRIMARY_ENDPOINT_ID
    )
    key_secondary_endpoint_id: Literal["corrupted-habit-mass.mean-per-case@1"] = (
        KEY_SECONDARY_ENDPOINT_ID
    )
    multiple_comparisons_policy: Literal[
        "intersection-union-two-tracks-two-references-utility-sensitivity@5",
        "intersection-union-two-tracks-two-references-utility-sensitivity@6",
    ] = "intersection-union-two-tracks-two-references-utility-sensitivity@5"
    policy: FrozenActionPolicy
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_input_artifact: SplitInputArtifact
    pilot_input_artifact: SplitInputArtifact
    test_input_artifact: SplitInputArtifact | None
    validation_prediction_ledgers: dict[ProjectOneAblationArmId, ArmValidationPredictionLedger]
    tuning_records: tuple[ArmActionTuningRecord, ...]
    pilot_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    power_analyses: tuple[MetricPowerAnalysis, ...]
    test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    paired_test_intervals: tuple[PairedActionInterval, ...]
    decision: PreregisteredDecision
    retuned_tuning_records: tuple[ArmRetunedPolicyTuningRecord, ...]
    retuned_pilot_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    retuned_power_analyses: tuple[MetricPowerAnalysis, ...]
    retuned_test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    retuned_paired_test_intervals: tuple[PairedActionInterval, ...]
    retuned_decision: PreregisteredDecision
    overall_decision: CrossTrackDecision
    utility_sensitivity_results: tuple[UtilitySensitivityResult, ...]
    action_policy_baselines: dict[ActionPolicyBaselineId, ActionPolicyBaselineArtifact]
    action_baseline_intervals: tuple[ActionBaselineInterval, ...]
    allowed_claims: tuple[str, ...] = ALLOWED_CLAIM_IDS
    forbidden_claims: tuple[str, ...] = FORBIDDEN_CLAIM_IDS
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ProjectOneShiftActionDeathTestReport:
        if self.protocol_version != self.config.protocol_version:
            raise ValueError("report protocol version differs from its config")
        expected_comparisons = (
            "intersection-union-two-tracks-two-references-utility-sensitivity@6"
            if self.protocol_version.endswith("@6")
            else "intersection-union-two-tracks-two-references-utility-sensitivity@5"
        )
        if self.multiple_comparisons_policy != expected_comparisons:
            raise ValueError("multiple-comparisons policy version differs from protocol")
        if self.config_sha256 != content_sha256(self.config):
            raise ValueError("death-test config hash mismatch")
        if self.policy != self.config.action_policy:
            raise ValueError("report policy differs from the frozen config")
        if self.policy_sha256 != content_sha256(self.policy):
            raise ValueError("frozen action policy hash mismatch")
        if tuple(item.arm_id for item in self.tuning_records) != SHIFT_THREE_ARMS:
            raise ValueError("tuning records must cover the ordered SHIFT three arms")
        if tuple(item.arm_id for item in self.retuned_tuning_records) != SHIFT_THREE_ARMS:
            raise ValueError("retuned tuning records must cover the ordered SHIFT three arms")
        self._validate_input_seed_binding()
        if set(self.validation_prediction_ledgers) != set(SHIFT_THREE_ARMS):
            raise ValueError("validation prediction ledgers must cover all three arms")
        shared_records = {item.arm_id: item for item in self.tuning_records}
        retuned_records = {item.arm_id: item for item in self.retuned_tuning_records}
        policy_space = _retuned_policy_space(self.policy)
        validation_cases = self.validation_input_artifact.cases
        for arm in SHIFT_THREE_ARMS:
            ledger = self.validation_prediction_ledgers[arm]
            if ledger.arm_id != arm or ledger.validation_input_sha256 != (
                self.validation_input_artifact.artifact_sha256
            ):
                raise ValueError("validation ledger input binding mismatch")
            for candidate in ledger.candidates:
                replayed = tuple(
                    _predict_prefix_online(arm, candidate.params, case.model_input)
                    for case in validation_cases
                )
                if replayed != candidate.predictions:
                    raise ValueError(
                        "validation prefix predictions do not replay from input and params"
                    )
            shared_items, shared_index = _shared_candidate_ledger(
                arm, ledger, validation_cases, self.policy
            )
            shared_record = shared_records[arm]
            if (
                shared_record.candidate_ledger_sha256 != content_sha256(shared_items)
                or shared_record.selected_candidate_index != shared_index
                or shared_record.selected_params != ledger.candidates[shared_index].params
                or shared_record.selected_validation_regret
                != shared_items[shared_index]["metrics"].balanced_downstream_action_regret
            ):
                raise ValueError("shared selected params are not the declared ledger argmin")
            retuned_items, (detector_index, policy_index) = _retuned_candidate_ledger(
                ledger, validation_cases, policy_space
            )
            retuned_record = retuned_records[arm]
            selected_flat = detector_index * len(policy_space) + policy_index
            if (
                retuned_record.candidate_ledger_sha256 != content_sha256(retuned_items)
                or retuned_record.selected_detector_index != detector_index
                or retuned_record.selected_policy_index != policy_index
                or retuned_record.selected_params != ledger.candidates[detector_index].params
                or retuned_record.selected_policy != policy_space[policy_index]
                or retuned_record.selected_validation_regret
                != retuned_items[selected_flat]["metrics"].balanced_downstream_action_regret
            ):
                raise ValueError("retuned selected params are not the declared ledger argmin")
        if set(self.pilot_artifacts) != set(SHIFT_THREE_ARMS):
            raise ValueError("pilot artifacts must cover all three arms")
        if set(self.retuned_pilot_artifacts) != set(SHIFT_THREE_ARMS):
            raise ValueError("retuned pilot artifacts must cover all three arms")
        selected_hashes = {item.arm_id: item.selected_params_sha256 for item in self.tuning_records}
        for arm, artifact in (*self.pilot_artifacts.items(), *self.test_artifacts.items()):
            if artifact.arm_id != arm:
                raise ValueError("artifact dictionary key does not match arm")
            if artifact.policy_sha256 != self.policy_sha256 or artifact.policy != self.policy:
                raise ValueError("all arms must use the identical frozen action policy")
            if artifact.selected_params_sha256 != selected_hashes[arm]:
                raise ValueError("artifact parameters differ from validation selection")
        if any(item.policy_template != self.policy for item in self.retuned_tuning_records):
            raise ValueError("retuned policy search template differs from the frozen config")
        for arm, artifact in (
            *self.retuned_pilot_artifacts.items(),
            *self.retuned_test_artifacts.items(),
        ):
            record = retuned_records[arm]
            if artifact.arm_id != arm:
                raise ValueError("retuned artifact dictionary key does not match arm")
            if artifact.selected_params_sha256 != record.selected_params_sha256:
                raise ValueError("retuned artifact detector params differ from selection")
            if artifact.policy != record.selected_policy:
                raise ValueError("retuned artifact policy differs from validation selection")
            if artifact.policy_sha256 != record.selected_policy_sha256:
                raise ValueError("retuned artifact policy hash differs from selection")
        self._validate_selected_prediction_replay(
            self.pilot_input_artifact,
            self.pilot_artifacts,
            shared_records,
            retuned=False,
        )
        self._validate_selected_prediction_replay(
            self.pilot_input_artifact,
            self.retuned_pilot_artifacts,
            retuned_records,
            retuned=True,
        )
        expected_allowed, expected_forbidden = _claim_ids(self.protocol_version)
        if self.allowed_claims != expected_allowed or self.forbidden_claims != expected_forbidden:
            raise ValueError("claim IDs must equal the canonical sets")
        self._validate_pilot_bindings(self.pilot_artifacts)
        self._validate_pilot_bindings(self.retuned_pilot_artifacts)
        expected_shared_power = _power_analyses_from_pilot(self.pilot_artifacts, self.config)
        expected_retuned_power = _power_analyses_from_pilot(
            self.retuned_pilot_artifacts, self.config
        )
        if self.power_analyses != expected_shared_power:
            raise ValueError("shared power analyses do not recompute from pilot artifacts")
        if self.retuned_power_analyses != expected_retuned_power:
            raise ValueError("retuned power analyses do not recompute from pilot artifacts")
        # Exact non-empty topology has now been established, so all([]) cannot
        # vacuously authorize TEST.
        power_pass = all(
            item.status == "PASS" for item in (*self.power_analyses, *self.retuned_power_analyses)
        )
        if power_pass and (
            set(self.test_artifacts) != set(SHIFT_THREE_ARMS)
            or set(self.retuned_test_artifacts) != set(SHIFT_THREE_ARMS)
        ):
            raise ValueError("powered report requires both three-arm TEST tracks")
        if not power_pass and (
            self.test_artifacts
            or self.paired_test_intervals
            or self.retuned_test_artifacts
            or self.retuned_paired_test_intervals
            or self.action_policy_baselines
            or self.action_baseline_intervals
        ):
            raise ValueError("underpowered report must not inspect or report TEST")
        if power_pass:
            if self.test_input_artifact is None:
                raise ValueError("powered report requires the sealed TEST input artifact")
            self._validate_selected_prediction_replay(
                self.test_input_artifact,
                self.test_artifacts,
                shared_records,
                retuned=False,
            )
            self._validate_selected_prediction_replay(
                self.test_input_artifact,
                self.retuned_test_artifacts,
                retuned_records,
                retuned=True,
            )
            expected_intervals = _paired_intervals_for_artifacts(
                self.test_artifacts, self.config.bootstrap_samples
            )
            if expected_intervals != self.paired_test_intervals:
                raise ValueError("paired intervals do not recompute from TEST artifacts")
            expected_retuned_intervals = _paired_intervals_for_artifacts(
                self.retuned_test_artifacts, self.config.bootstrap_samples
            )
            if expected_retuned_intervals != self.retuned_paired_test_intervals:
                raise ValueError("retuned paired intervals do not recompute from TEST artifacts")
            expected_sensitivity = _utility_sensitivity_results(
                self.config,
                self.test_input_artifact.cases,
                self.test_artifacts,
                self.retuned_test_artifacts,
                shared_records,
                retuned_records,
            )
            if self.utility_sensitivity_results != expected_sensitivity:
                raise ValueError("utility sensitivity does not recompute from TEST artifacts")
            expected_baselines = _action_policy_baselines(
                self.test_input_artifact.cases, self.policy
            )
            if self.action_policy_baselines != expected_baselines:
                raise ValueError("action policy baselines do not recompute from TEST inputs")
            expected_baseline_intervals = _action_baseline_intervals(
                self.test_artifacts,
                self.retuned_test_artifacts,
                self.action_policy_baselines,
                self.config.bootstrap_samples,
            )
            if self.action_baseline_intervals != expected_baseline_intervals:
                raise ValueError("action baseline intervals do not recompute")
        elif self.utility_sensitivity_results:
            raise ValueError("underpowered report must not contain utility sensitivity")
        expected_decision = decide_research_route(
            self.power_analyses,
            self.paired_test_intervals,
            self.policy,
        )
        if self.decision != expected_decision:
            raise ValueError("research decision does not follow preregistered rule")
        expected_retuned_decision = decide_research_route(
            self.retuned_power_analyses,
            self.retuned_paired_test_intervals,
            self.policy,
        )
        if self.retuned_decision != expected_retuned_decision:
            raise ValueError("retuned decision does not follow preregistered rule")
        expected_overall = decide_cross_track_route(
            self.decision, self.retuned_decision, self.policy
        )
        sensitivity_not_robust = bool(self.utility_sensitivity_results) and any(
            next(
                interval
                for interval in result.regret_intervals
                if interval.reference_arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD
            ).lower_95
            < self.policy.practical_regret_mde
            for result in self.utility_sensitivity_results
        )
        if expected_overall.decision == ResearchDecision.REBUILD_JOINT and sensitivity_not_robust:
            expected_overall = CrossTrackDecision(
                decision=ResearchDecision.INCONCLUSIVE,
                shared_policy_decision=self.decision.decision,
                independently_retuned_policy_decision=self.retuned_decision.decision,
                rationale_id="decision.utility-sensitivity-not-robust@5",
            )
        guarded_arm = {
            ResearchDecision.CONTINUE_JOINT: (ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD),
            ResearchDecision.REBUILD_JOINT: (ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD),
            ResearchDecision.USE_ORDINARY: ProjectOneAblationArmId.ORDINARY_BOCPD,
        }.get(expected_overall.decision)
        if guarded_arm is not None and not _beats_never_act_in_both_tracks(
            self.action_baseline_intervals,
            guarded_arm,
            self.policy.practical_regret_mde,
        ):
            expected_overall = CrossTrackDecision(
                decision=ResearchDecision.INCONCLUSIVE,
                shared_policy_decision=self.decision.decision,
                independently_retuned_policy_decision=self.retuned_decision.decision,
                rationale_id="decision.action-winner-does-not-beat-never-act@5",
            )
        if self.overall_decision != expected_overall:
            raise ValueError("overall decision does not follow cross-track sensitivity rules")
        payload = self.model_dump(mode="json", exclude={"report_sha256"})
        if self.report_sha256 != content_sha256(payload):
            raise ValueError("action death-test report hash mismatch")
        return self

    def _validate_input_seed_binding(self) -> None:
        expected = (
            (self.validation_input_artifact, set(self.config.seed_plan.validation_seeds)),
            (self.pilot_input_artifact, set(self.config.seed_plan.pilot_seeds)),
        )
        for artifact, seeds in expected:
            if {item.evaluator_truth.scenario_seed for item in artifact.cases} != seeds:
                raise ValueError("input artifact seeds do not match the config")
        if self.test_input_artifact is not None and {
            item.evaluator_truth.scenario_seed for item in self.test_input_artifact.cases
        } != set(self.config.seed_plan.test_seeds):
            raise ValueError("TEST input artifact seeds do not match the config")

    def _validate_selected_prediction_replay(
        self,
        inputs: SplitInputArtifact | None,
        artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
        records: Mapping[
            ProjectOneAblationArmId,
            ArmActionTuningRecord | ArmRetunedPolicyTuningRecord,
        ],
        *,
        retuned: bool,
    ) -> None:
        if inputs is None:
            raise ValueError("selected prediction replay requires input artifacts")
        for arm in SHIFT_THREE_ARMS:
            record = records[arm]
            replayed = tuple(
                _predict_prefix_online(arm, record.selected_params, case.model_input)
                for case in inputs.cases
            )
            expected = _artifact_from_predictions(
                arm,
                record.selected_params,
                inputs.cases,
                replayed,
                artifacts[arm].policy,
                artifacts[arm].split_id,
            )
            if expected != artifacts[arm]:
                label = "retuned" if retuned else "shared"
                raise ValueError(
                    f"{label} artifact does not replay from exact input, truth, params, and policy"
                )

    def _validate_pilot_bindings(
        self, artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    ) -> None:
        expected_seeds = set(self.config.seed_plan.pilot_seeds)
        case_ids: set[str] | None = None
        for arm in SHIFT_THREE_ARMS:
            artifact = artifacts[arm]
            actual_seeds = {item.scenario_seed for item in artifact.outcomes}
            if actual_seeds != expected_seeds:
                raise ValueError("pilot artifact seeds do not match the config seed plan")
            actual_case_ids = {item.case_id for item in artifact.outcomes}
            if case_ids is None:
                case_ids = actual_case_ids
            elif actual_case_ids != case_ids:
                raise ValueError("pilot arms do not cover identical paired cases")


def required_paired_seed_count(
    empirical_stddev: float,
    minimum_detectable_effect: float,
    *,
    alpha: float,
    target_power: float,
) -> int:
    if empirical_stddev < 0.0 or minimum_detectable_effect <= 0.0:
        raise ValueError("invalid empirical variance or MDE")
    normal = NormalDist()
    value = (
        (normal.inv_cdf(1.0 - alpha / 2.0) + normal.inv_cdf(target_power))
        * empirical_stddev
        / minimum_detectable_effect
    ) ** 2
    return max(2, ceil(value))


def _calibrate_probability(probability: float, temperature: float) -> float:
    epsilon = 1e-12
    clipped = min(1.0 - epsilon, max(epsilon, probability))
    return 1.0 / (1.0 + exp(-log(clipped / (1.0 - clipped)) / temperature))


def _prefix_input(
    model_input: OnlineShiftCaseInput, *, as_of_time: datetime
) -> OnlineShiftCaseInput:
    run = model_input.observation_stream
    prefix_days = int((as_of_time - run.start_time).total_seconds() // 86400)
    result_by_opportunity = {
        item.observation_opportunity_id: item for item in run.detection_results
    }
    opportunities = tuple(
        item
        for item in run.observation_opportunities
        if item.opportunity_time < as_of_time
        and result_by_opportunity[item.metadata.record_id].metadata.recorded_time < as_of_time
    )
    opportunity_ids = {item.metadata.record_id for item in opportunities}
    results = tuple(
        item for item in run.detection_results if item.observation_opportunity_id in opportunity_ids
    )
    result_ids = {item.metadata.record_id for item in results}
    actor_evidence = tuple(
        item
        for item in model_input.actor_evidence
        if item.source_detection_result_id in result_ids and item.evidence_time < as_of_time
    )
    prefix_run = D0VisibleSimulationRun.from_records(
        start_time=run.start_time,
        duration_days=prefix_days,
        random_seed=run.random_seed,
        observation_opportunities=opportunities,
        detection_results=results,
    )
    return model_input.model_copy(
        update={"observation_stream": prefix_run, "actor_evidence": actor_evidence}
    )


def _detector_state_at_prefix(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
    prefix: OnlineShiftCaseInput,
) -> tuple[datetime | None, dict[ShiftCause, float], str]:
    warmup = int(params["warmup_days"])
    hazard = float(params["hazard_probability"])
    threshold = float(params["detection_threshold"])
    frame_adapter = OnlineCauseFactorizedBOCPDBaseline(
        warmup_days=warmup,
        hazard_probability=hazard,
        detection_threshold=threshold,
    )
    frames = frame_adapter.evidence_frames(prefix)
    cause_map = OnlineCauseFactorizedBOCPDBaseline._CAUSE_MAP
    if arm == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD:
        model_version = "online-cause-factorized-bocpd@0.1-prefix@1"
        result = CauseFactorizedBOCPD(
            hazard_probability=hazard,
            model_version=model_version,
        ).run(
            frames,
            detection_threshold=threshold,
            minimum_observations=warmup + 1,
        )
        detected = tuple(
            item for item in result.detected_change_time_by_cause.values() if item is not None
        )
        posterior = {
            cause_map[cause]: probability
            for cause, probability in result.snapshots[-1].changepoint_probability_by_cause.items()
        }
        return (min(detected) if detected else None), posterior, model_version
    if arm == ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD:
        model_version = "joint-cause-factorized-bocpd@0.4-event-regime-multicause-prefix@1"
        signals = tuple(
            CauseSignalFrame(
                timestamp=frame.timestamp,
                signals={
                    cause: min(
                        1.0,
                        max(0.0, (frame.changepoint_likelihoods[cause] - 0.01) / 0.99),
                    )
                    for cause in ChangeCause
                },
            )
            for frame in frames
        )
        joint_result = JointCauseFactorizedBOCPD(
            hazard_probability=hazard,
            beam_width=int(params["beam_width"]),
            maximum_simultaneous_causes=int(params["maximum_simultaneous_causes"]),
            simultaneous_hazard_scale=float(params["simultaneous_hazard_scale"]),
            model_version=model_version,
        ).run(signals, detection_threshold=threshold, warmup_steps=warmup)
        detected = tuple(
            item for item in joint_result.detected_change_time_by_cause.values() if item is not None
        )
        current = joint_result.snapshots[-1]
        posterior = {
            cause_map[cause]: min(
                1.0,
                max(
                    0.0,
                    (
                        current.transient_noise_probability
                        if cause == ChangeCause.NOISE
                        # Action gates need the durable cause of the currently
                        # active regime, not P(a fresh change happened today).
                        # The latter correctly decays after the event and was
                        # the source of systematic missed consolidations.
                        else current.active_regime_cause_posterior.get(cause, 0.0)
                    ),
                ),
            )
            for cause in ChangeCause
        }
        return (min(detected) if detected else None), posterior, model_version
    if arm != ProjectOneAblationArmId.ORDINARY_BOCPD:
        raise ValueError(f"unsupported prefix-online arm: {arm}")
    model_version = "online-ordinary-bocpd@0.1-prefix@1"
    posterior_by_run_length = {0: 1.0}
    snapshots: list[tuple[datetime, float]] = []
    for frame in frames:
        changepoint_likelihood = max(frame.changepoint_likelihoods.values())
        continuation_likelihood = min(frame.continuation_likelihoods.values())
        updated = {0: sum(posterior_by_run_length.values()) * hazard * changepoint_likelihood}
        for run_length, probability in posterior_by_run_length.items():
            next_length = min(run_length + 1, 256)
            updated[next_length] = updated.get(next_length, 0.0) + (
                probability * (1.0 - hazard) * continuation_likelihood
            )
        total = sum(updated.values())
        posterior_by_run_length = {key: value / total for key, value in updated.items()}
        snapshots.append((frame.timestamp, posterior_by_run_length[0]))
    eligible = snapshots[warmup:]
    estimate = next((time for time, probability in eligible if probability >= threshold), None)
    current_frame = frames[-1]
    posterior = {
        cause_map[cause]: (
            current_frame.changepoint_likelihoods[cause]
            / (
                current_frame.changepoint_likelihoods[cause]
                + current_frame.continuation_likelihoods[cause]
            )
        )
        for cause in ChangeCause
    }
    return estimate, posterior, model_version


def _predict_prefix_online(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
    model_input: OnlineShiftCaseInput,
) -> PrefixOnlinePrediction:
    run = model_input.observation_stream
    snapshots = []
    model_version = ""
    for prefix_days in range(3, run.duration_days + 1):
        as_of_time = run.start_time + timedelta(days=prefix_days)
        prefix = _prefix_input(model_input, as_of_time=as_of_time)
        estimate, posterior, model_version = _detector_state_at_prefix(arm, params, prefix)
        evidence_ids = tuple(
            dict.fromkeys(
                tuple(
                    str(item.metadata.record_id)
                    for item in prefix.observation_stream.observation_opportunities
                )
                + tuple(
                    str(item.metadata.record_id)
                    for item in prefix.observation_stream.detection_results
                )
                + tuple(str(item.metadata.record_id) for item in prefix.actor_evidence)
            )
        )
        snapshots.append(
            PrefixPosteriorSnapshot(
                as_of_time=as_of_time,
                change_time_estimate=estimate,
                posterior=posterior,
                prefix_input_sha256=content_sha256(prefix),
                visible_evidence_record_ids=evidence_ids,
            )
        )
    return PrefixOnlinePrediction(
        case_id=str(model_input.case_id),
        model_version=model_version,
        snapshots=tuple(snapshots),
    )


def _verification_evidence(
    model_input: OnlineShiftCaseInput,
    *,
    after_time: datetime,
    policy: FrozenActionPolicy,
) -> VerificationEvidence | None:
    actor_by_result = {item.source_detection_result_id: item for item in model_input.actor_evidence}
    first_by_key: dict[tuple[UUID, UUID], tuple[ObservationDetectionResult, float]] = {}
    results = sorted(
        model_input.observation_stream.detection_results,
        key=lambda item: item.metadata.recorded_time,
    )
    for result in results:
        if (
            result.metadata.recorded_time <= after_time
            or result.outcome != ObservationOutcome.DETECTED
            or result.detected_object_instance_id is None
            or result.detected_location_id is None
        ):
            continue
        actor = actor_by_result.get(result.metadata.record_id)
        if actor is None:
            continue
        owner_probability = float(actor.actor_posterior.get(str(model_input.target_person_id), 0.0))
        if owner_probability < policy.verification_owner_probability_threshold:
            continue
        key = (result.detected_object_instance_id, result.detected_location_id)
        first = first_by_key.get(key)
        if first is None:
            first_by_key[key] = (result, owner_probability)
            continue
        first_result, first_owner = first
        if first_result.metadata.recorded_time >= result.metadata.recorded_time:
            continue
        return VerificationEvidence(
            object_instance_id=str(key[0]),
            location_id=str(key[1]),
            first_detection_result_id=str(first_result.metadata.record_id),
            second_detection_result_id=str(result.metadata.record_id),
            first_evidence_time=first_result.metadata.recorded_time,
            second_evidence_time=result.metadata.recorded_time,
            minimum_owner_posterior=min(first_owner, owner_probability),
        )
    return None


def _active_verification_evidence(
    model_input: OnlineShiftCaseInput,
    truth: OnlineShiftCaseTruth,
    *,
    after_time: datetime,
    policy: FrozenActionPolicy,
) -> VerificationEvidence | None:
    """Simulate the preregistered on-demand identity confirmation intervention.

    The policy may request a confirmation after the same object has been seen
    before and after the decision (locations may differ under a real habit
    change).  The response is generated behind the
    evaluator boundary from the latent scenario and is returned with declared
    latency and cost; it is not inserted into the ordinary model input.
    """

    if not policy.active_verification_enabled or not truth.intervention_available:
        return None
    results = sorted(
        model_input.observation_stream.detection_results,
        key=lambda item: item.metadata.recorded_time,
    )
    valid_results = [
        result
        for result in results
        if (
            result.outcome == ObservationOutcome.DETECTED
            and result.detected_object_instance_id is not None
            and result.detected_location_id is not None
        )
    ]
    for result in valid_results:
        if result.metadata.recorded_time <= after_time:
            continue
        first = next(
            (
                candidate
                for candidate in reversed(valid_results)
                if candidate.metadata.recorded_time < result.metadata.recorded_time
                and candidate.detected_object_instance_id == result.detected_object_instance_id
            ),
            None,
        )
        if first is None:
            continue
        response_time = result.metadata.recorded_time + timedelta(
            hours=policy.active_verification_latency_hours
        )
        true_habit = ShiftCause.OWNER_HABIT_REGIME in truth.true_causes
        owner_probability = (
            policy.active_verification_positive_owner_probability
            if true_habit
            else policy.active_verification_negative_owner_probability
        )
        return VerificationEvidence(
            predicate_id="active-owner-confirmation-across-observations@1",
            object_instance_id=str(result.detected_object_instance_id),
            location_id=str(result.detected_location_id),
            first_detection_result_id=str(first.metadata.record_id),
            second_detection_result_id=str(result.metadata.record_id),
            first_evidence_time=first.metadata.recorded_time,
            second_evidence_time=response_time,
            minimum_owner_posterior=owner_probability,
        )
    return None


def _case_outcome(
    truth: OnlineShiftCaseTruth,
    prediction: PrefixOnlinePrediction | None,
    policy: FrozenActionPolicy,
    *,
    model_input: OnlineShiftCaseInput | None,
    stream_start_time: datetime,
    duration_days: int,
    verification_evidence: VerificationEvidence | None = None,
    action_mode: Literal["detector", "never-act", "always-reset-verify"] = "detector",
) -> CaseActionOutcome:
    snapshots = prediction.snapshots if prediction is not None else ()
    selected: PrefixPosteriorSnapshot | None = None
    calibrated: dict[ShiftCause, float] = {}
    if action_mode == "detector":
        for snapshot in snapshots:
            candidate = {
                cause: _calibrate_probability(float(probability), policy.probability_temperature)
                for cause, probability in snapshot.posterior.items()
            }
            if (
                snapshot.change_time_estimate is not None
                and candidate.get(ShiftCause.OWNER_HABIT_REGIME, 0.0)
                >= policy.reset_probability_threshold
            ):
                selected = snapshot
                calibrated = candidate
                break
    elif action_mode == "always-reset-verify" and snapshots:
        selected = snapshots[0]
        calibrated = {cause: 0.0 for cause in ShiftCause if cause != ShiftCause.UNRESOLVED}
        calibrated[ShiftCause.OWNER_HABIT_REGIME] = 1.0
    reset = selected is not None and action_mode != "never-act"
    decision_time = selected.as_of_time if selected is not None else None
    change_time_estimate = selected.change_time_estimate if selected is not None else None
    posterior_at_decision = selected.posterior if selected is not None else None
    if action_mode == "always-reset-verify" and selected is not None:
        posterior_at_decision = calibrated
    habit_probability = float(calibrated.get(ShiftCause.OWNER_HABIT_REGIME, 0.0))
    if reset and model_input is not None and decision_time is None:
        raise AssertionError("reset decision must carry its decision time")
    if verification_evidence is None and reset and model_input is not None:
        if decision_time is None:
            raise AssertionError("reset decision must carry its decision time")
        verification_evidence = _verification_evidence(
            model_input, after_time=decision_time, policy=policy
        )
    if verification_evidence is None and reset and model_input is not None:
        if decision_time is None:
            raise AssertionError("reset decision must carry its decision time")
        verification_evidence = _active_verification_evidence(
            model_input,
            truth,
            after_time=decision_time,
            policy=policy,
        )
    verify = reset and verification_evidence is not None
    verification_time = (
        verification_evidence.second_evidence_time if verification_evidence is not None else None
    )
    consolidation_time = None
    positive_owner_verification = (
        verification_evidence is not None
        and verification_evidence.minimum_owner_posterior
        >= policy.verification_owner_probability_threshold
    )
    if verify and positive_owner_verification and verification_time is not None:
        for snapshot in snapshots:
            if snapshot.as_of_time <= verification_time:
                continue
            probabilities = {
                cause: _calibrate_probability(float(probability), policy.probability_temperature)
                for cause, probability in snapshot.posterior.items()
            }
            if (
                verification_evidence is not None
                and verification_evidence.predicate_id
                == "active-owner-confirmation-across-observations@1"
            ):
                model_habit = probabilities.get(ShiftCause.OWNER_HABIT_REGIME, 0.0)
                confirmation = float(verification_evidence.minimum_owner_posterior)
                probabilities[ShiftCause.OWNER_HABIT_REGIME] = 1.0 - (
                    (1.0 - model_habit) * (1.0 - confirmation)
                )
            if policy.multi_label_consolidation:
                habit_probability_at_prefix = probabilities.get(ShiftCause.OWNER_HABIT_REGIME, 0.0)
                # Independent/multi-label causes may coexist, so observation
                # mass must not count as evidence against a habit change.
                margin = max(0.0, 2.0 * habit_probability_at_prefix - 1.0)
            else:
                ranked = sorted(probabilities.values(), reverse=True)
                margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
            if action_mode == "always-reset-verify" or (
                probabilities.get(ShiftCause.OWNER_HABIT_REGIME, 0.0)
                >= policy.consolidation_probability_threshold
                and margin >= policy.attribution_margin
            ):
                consolidation_time = snapshot.as_of_time
                break
    consolidate = consolidation_time is not None
    if consolidate:
        action_sequence: tuple[str, ...] = (
            "RESET_OLD_REGIME",
            "VERIFY_NEW_EVIDENCE",
            "CONSOLIDATE_NEW_REGIME",
        )
    elif reset and verify:
        action_sequence = ("RESET_OLD_REGIME", "VERIFY_NEW_EVIDENCE")
    elif reset:
        action_sequence = ("RESET_OLD_REGIME",)
    else:
        action_sequence = ()
    true_habit = ShiftCause.OWNER_HABIT_REGIME in truth.true_causes
    false_reset = reset and not true_habit
    missed_reset = true_habit and not reset
    missed_consolidation = true_habit and not consolidate
    false_consolidation = consolidate and not true_habit
    horizon_end = stream_start_time + timedelta(days=duration_days)
    remaining_days = max(0.0, (horizon_end - truth.change_time).total_seconds() / 86400.0)
    if true_habit and consolidate and consolidation_time is not None:
        recovery_days = max(
            0.0,
            (consolidation_time - truth.change_time).total_seconds() / 86400.0,
        )
    elif true_habit:
        recovery_days = remaining_days
    else:
        recovery_days = 0.0
    corrupted_mass = habit_probability if false_consolidation else 0.0
    raw_regret = (
        policy.false_reset_cost * float(false_reset)
        + policy.missed_reset_daily_cost * recovery_days
        + policy.corrupted_mass_daily_cost * corrupted_mass * remaining_days
        + policy.verification_cost * float(verify)
    )
    regret = min(1.0, raw_regret)
    success = (
        not false_reset
        and not missed_reset
        and not missed_consolidation
        and not false_consolidation
    )
    return CaseActionOutcome(
        case_id=str(truth.case_id),
        scenario_seed=truth.scenario_seed,
        habit_shift_required=true_habit,
        reset_issued=reset,
        consolidation_issued=consolidate,
        verification_issued=verify,
        action_sequence=action_sequence,
        change_time_estimate=change_time_estimate,
        decision_time=decision_time,
        posterior_at_decision=posterior_at_decision,
        reset_time=decision_time,
        verification_time=verification_time,
        consolidation_time=consolidation_time,
        verification_evidence=verification_evidence if verify else None,
        false_reset=false_reset,
        missed_reset=missed_reset,
        missed_consolidation=missed_consolidation,
        false_consolidation=false_consolidation,
        corrupted_habit_mass=corrupted_mass,
        recovery_time_days=recovery_days,
        unnecessary_verification_cost=policy.verification_cost
        if verify and not true_habit
        else 0.0,
        downstream_action_regret=regret,
        task_success_proxy=success,
    )


def aggregate_action_metrics(outcomes: Sequence[CaseActionOutcome]) -> ArmActionMetrics:
    if not outcomes:
        raise ValueError("action evaluation requires outcomes")
    habit = [item for item in outcomes if item.habit_shift_required]
    non_habit = [item for item in outcomes if not item.habit_shift_required]
    habit_regret = fmean(item.downstream_action_regret for item in habit) if habit else 0.0
    non_habit_regret = (
        fmean(item.downstream_action_regret for item in non_habit) if non_habit else 0.0
    )
    balanced_regret = (
        0.5 * habit_regret + 0.5 * non_habit_regret
        if habit and non_habit
        else fmean(item.downstream_action_regret for item in outcomes)
    )
    return ArmActionMetrics(
        sample_count=len(outcomes),
        false_reset_rate=fmean(float(item.false_reset) for item in non_habit) if non_habit else 0.0,
        missed_reset_rate=fmean(float(item.missed_reset) for item in habit) if habit else 0.0,
        missed_consolidation_rate=(
            fmean(float(item.missed_consolidation) for item in habit) if habit else 0.0
        ),
        false_consolidation_rate=(
            fmean(float(item.false_consolidation) for item in non_habit) if non_habit else 0.0
        ),
        corrupted_habit_mass=fmean(item.corrupted_habit_mass for item in outcomes),
        recovery_time_days=fmean(item.recovery_time_days for item in habit) if habit else 0.0,
        unnecessary_verification_cost=fmean(
            item.unnecessary_verification_cost for item in outcomes
        ),
        downstream_action_regret=fmean(item.downstream_action_regret for item in outcomes),
        balanced_downstream_action_regret=balanced_regret,
        task_success_proxy_rate=fmean(float(item.task_success_proxy) for item in outcomes),
    )


def _evaluate_arm(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
    cases: Sequence[OnlineShiftGeneratedCase],
    policy: FrozenActionPolicy,
    split_id: Literal["validation", "pilot", "test"],
) -> ArmActionArtifact:
    predictions = tuple(_predict_prefix_online(arm, params, case.model_input) for case in cases)
    return _artifact_from_predictions(arm, params, cases, predictions, policy, split_id)


def _action_truth(case: OnlineShiftGeneratedCase) -> ActionCaseTruth:
    return ActionCaseTruth(
        truth=case.evaluator_truth,
        stream_start_time=case.model_input.observation_stream.start_time,
        duration_days=case.model_input.observation_stream.duration_days,
        model_input_sha256=content_sha256(case.model_input),
        evaluator_truth_sha256=content_sha256(case.evaluator_truth),
        generated_case_sha256=content_sha256(case),
    )


def _terminal_attribution_cases(
    case_truths: Sequence[ActionCaseTruth],
    predictions_by_id: dict[str, PrefixOnlinePrediction],
) -> tuple[OnlineShiftAttributionCase, ...]:
    output = []
    for item in case_truths:
        trajectory = predictions_by_id[str(item.truth.case_id)]
        terminal = trajectory.snapshots[-1]
        output.append(
            OnlineShiftAttributionCase(
                truth=item.truth,
                prediction=OnlineShiftPrediction(
                    case_id=item.truth.case_id,
                    predicted_change_time=terminal.change_time_estimate,
                    cause_probabilities=terminal.posterior,
                    model_version=trajectory.model_version,
                ),
            )
        )
    return tuple(output)


def _artifact_from_predictions(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
    cases: Sequence[OnlineShiftGeneratedCase],
    predictions: tuple[PrefixOnlinePrediction, ...],
    policy: FrozenActionPolicy,
    split_id: Literal["validation", "pilot", "test"],
) -> ArmActionArtifact:
    case_truths = tuple(_action_truth(case) for case in cases)
    outcomes = tuple(
        _case_outcome(
            case.evaluator_truth,
            prediction,
            policy,
            model_input=case.model_input,
            stream_start_time=case.model_input.observation_stream.start_time,
            duration_days=case.model_input.observation_stream.duration_days,
        )
        for case, prediction in zip(cases, predictions, strict=True)
    )
    bound = _terminal_attribution_cases(case_truths, {item.case_id: item for item in predictions})
    payload = {
        "arm_id": arm,
        "split_id": split_id,
        "policy_sha256": content_sha256(policy),
        "policy": policy,
        "selected_params_sha256": content_sha256(params),
        "case_truths": case_truths,
        "predictions": predictions,
        "outcomes": outcomes,
        "metrics": aggregate_action_metrics(outcomes),
        "mechanism_metrics": OnlineShiftEvaluator().evaluate(bound),
    }
    return ArmActionArtifact(**payload, artifact_sha256=content_sha256(payload))


def _action_metrics_from_predictions(
    cases: Sequence[OnlineShiftGeneratedCase],
    predictions: tuple[PrefixOnlinePrediction, ...],
    policy: FrozenActionPolicy,
) -> ArmActionMetrics:
    outcomes = tuple(
        _case_outcome(
            case.evaluator_truth,
            prediction,
            policy,
            model_input=case.model_input,
            stream_start_time=case.model_input.observation_stream.start_time,
            duration_days=case.model_input.observation_stream.duration_days,
        )
        for case, prediction in zip(cases, predictions, strict=True)
    )
    return aggregate_action_metrics(outcomes)


def _input_artifact(
    cases: Sequence[OnlineShiftGeneratedCase],
    split_id: Literal["validation", "pilot", "test"],
) -> SplitInputArtifact:
    payload = {"split_id": split_id, "cases": tuple(cases)}
    return SplitInputArtifact(**payload, artifact_sha256=content_sha256(payload))


def _policy_baseline_prediction(model_input: OnlineShiftCaseInput) -> PrefixOnlinePrediction:
    run = model_input.observation_stream
    snapshots = []
    for prefix_days in range(3, run.duration_days + 1):
        as_of_time = run.start_time + timedelta(days=prefix_days)
        prefix = _prefix_input(model_input, as_of_time=as_of_time)
        snapshots.append(
            PrefixPosteriorSnapshot(
                as_of_time=as_of_time,
                change_time_estimate=None,
                posterior={
                    cause: (1.0 if cause == ShiftCause.OWNER_HABIT_REGIME else 0.0)
                    for cause in ShiftCause
                    if cause != ShiftCause.UNRESOLVED
                },
                prefix_input_sha256=content_sha256(prefix),
                visible_evidence_record_ids=tuple(
                    dict.fromkeys(
                        tuple(
                            str(item.metadata.record_id)
                            for item in prefix.observation_stream.observation_opportunities
                        )
                        + tuple(
                            str(item.metadata.record_id)
                            for item in prefix.observation_stream.detection_results
                        )
                        + tuple(str(item.metadata.record_id) for item in prefix.actor_evidence)
                    )
                ),
            )
        )
    return PrefixOnlinePrediction(
        case_id=str(model_input.case_id),
        model_version="action-policy-baseline@1",
        snapshots=tuple(snapshots),
    )


def _action_policy_baselines(
    cases: Sequence[OnlineShiftGeneratedCase], policy: FrozenActionPolicy
) -> dict[ActionPolicyBaselineId, ActionPolicyBaselineArtifact]:
    output = {}
    baseline_modes: tuple[
        tuple[
            ActionPolicyBaselineId,
            Literal["never-act", "always-reset-verify"],
        ],
        ...,
    ] = (
        (ActionPolicyBaselineId.NEVER_ACT, "never-act"),
        (ActionPolicyBaselineId.ALWAYS_RESET_VERIFY, "always-reset-verify"),
    )
    for baseline_id, action_mode in baseline_modes:
        outcomes = tuple(
            _case_outcome(
                case.evaluator_truth,
                _policy_baseline_prediction(case.model_input),
                policy,
                model_input=case.model_input,
                stream_start_time=case.model_input.observation_stream.start_time,
                duration_days=case.model_input.observation_stream.duration_days,
                action_mode=action_mode,
            )
            for case in cases
        )
        payload = {
            "baseline_id": baseline_id,
            "split_id": "test",
            "outcomes": outcomes,
            "metrics": aggregate_action_metrics(outcomes),
        }
        output[baseline_id] = ActionPolicyBaselineArtifact(
            **payload, artifact_sha256=content_sha256(payload)
        )
    return output


def _validation_prediction_ledgers(
    validation: Sequence[OnlineShiftGeneratedCase], validation_input_sha256: str
) -> dict[ProjectOneAblationArmId, ArmValidationPredictionLedger]:
    output = {}
    for arm in SHIFT_THREE_ARMS:
        records = []
        for index, params in enumerate(_SEARCH_SPACES[arm]):
            predictions = tuple(
                _predict_prefix_online(arm, params, case.model_input) for case in validation
            )
            payload = {
                "arm_id": arm,
                "candidate_index": index,
                "params": params,
                "params_sha256": content_sha256(params),
                "validation_input_sha256": validation_input_sha256,
                "predictions": predictions,
                "predictions_sha256": content_sha256(predictions),
                "runtime_parameter_receipt": build_shift_runtime_parameter_receipt(arm, params),
            }
            records.append(
                ValidationPredictionCandidate(**payload, record_sha256=content_sha256(payload))
            )
        ledger_payload = {
            "arm_id": arm,
            "validation_input_sha256": validation_input_sha256,
            "candidates": tuple(records),
        }
        output[arm] = ArmValidationPredictionLedger(
            **ledger_payload, ledger_sha256=content_sha256(ledger_payload)
        )
    return output


def _mechanism_metrics_from_predictions(
    cases: Sequence[OnlineShiftGeneratedCase],
    predictions: tuple[PrefixOnlinePrediction, ...],
) -> OnlineShiftReport:
    return OnlineShiftEvaluator().evaluate(
        _terminal_attribution_cases(
            tuple(_action_truth(case) for case in cases),
            {item.case_id: item for item in predictions},
        )
    )


def _shared_candidate_ledger(
    arm: ProjectOneAblationArmId,
    ledger: ArmValidationPredictionLedger,
    validation: Sequence[OnlineShiftGeneratedCase],
    policy: FrozenActionPolicy,
) -> tuple[tuple[dict[str, Any], ...], int]:
    items: tuple[dict[str, Any], ...] = tuple(
        {
            "candidate_index": candidate.candidate_index,
            "params_sha256": candidate.params_sha256,
            "metrics": _action_metrics_from_predictions(validation, candidate.predictions, policy),
            "mechanism_metrics": _mechanism_metrics_from_predictions(
                validation, candidate.predictions
            ),
        }
        for candidate in ledger.candidates
    )
    selected = min(
        range(len(items)),
        key=lambda index: (
            items[index]["metrics"].balanced_downstream_action_regret,
            items[index]["metrics"].corrupted_habit_mass,
            -items[index]["metrics"].task_success_proxy_rate,
            items[index]["mechanism_metrics"].cause_negative_log_likelihood,
            ledger.candidates[index].params_sha256,
        ),
    )
    return items, selected


def _retuned_candidate_ledger(
    ledger: ArmValidationPredictionLedger,
    validation: Sequence[OnlineShiftGeneratedCase],
    policy_space: tuple[FrozenActionPolicy, ...],
) -> tuple[tuple[dict[str, Any], ...], tuple[int, int]]:
    items: tuple[dict[str, Any], ...] = tuple(
        {
            "detector_index": candidate.candidate_index,
            "policy_index": policy_index,
            "params_sha256": candidate.params_sha256,
            "policy_sha256": content_sha256(policy),
            "metrics": _action_metrics_from_predictions(validation, candidate.predictions, policy),
        }
        for candidate in ledger.candidates
        for policy_index, policy in enumerate(policy_space)
    )
    selected_flat = min(
        range(len(items)),
        key=lambda index: (
            items[index]["metrics"].balanced_downstream_action_regret,
            items[index]["metrics"].corrupted_habit_mass,
            -items[index]["metrics"].task_success_proxy_rate,
            items[index]["policy_sha256"],
            items[index]["params_sha256"],
        ),
    )
    selected = items[selected_flat]
    return items, (int(selected["detector_index"]), int(selected["policy_index"]))


def _seed_metric(
    artifact: ArmActionArtifact | ActionPolicyBaselineArtifact, metric: str
) -> dict[int, float]:
    by_seed: dict[int, list[CaseActionOutcome]] = {}
    for outcome in artifact.outcomes:
        by_seed.setdefault(outcome.scenario_seed, []).append(outcome)
    return {
        seed: float(getattr(aggregate_action_metrics(items), metric))
        for seed, items in by_seed.items()
    }


def _power_analyses_from_pilot(
    artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    config: ProjectOneShiftActionDeathTestConfig,
) -> tuple[MetricPowerAnalysis, ...]:
    if set(artifacts) != set(SHIFT_THREE_ARMS):
        raise ValueError("power analysis requires exact three-arm pilot artifacts")
    joint = artifacts[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD]
    output = []
    for reference in POWER_REFERENCES:
        for endpoint_id, role, metric, mde_field in POWER_ENDPOINTS:
            joint_by_seed = _seed_metric(joint, metric)
            reference_by_seed = _seed_metric(artifacts[reference], metric)
            expected_seeds = tuple(config.seed_plan.pilot_seeds)
            if set(joint_by_seed) != set(expected_seeds) or set(reference_by_seed) != set(
                expected_seeds
            ):
                raise ValueError("power analysis pilot seeds do not match the config")
            differences = [joint_by_seed[seed] - reference_by_seed[seed] for seed in expected_seeds]
            empirical = stdev(differences)
            powered = max(
                empirical * config.power_stddev_safety_factor,
                config.power_paired_stddev_floor,
            )
            mde = float(getattr(config.action_policy, mde_field))
            required = required_paired_seed_count(
                powered,
                mde,
                alpha=config.alpha,
                target_power=config.target_power,
            )
            output.append(
                MetricPowerAnalysis(
                    endpoint_id=endpoint_id,
                    reference_arm_id=reference,
                    role=role,
                    empirical_paired_stddev=empirical,
                    stddev_safety_factor=config.power_stddev_safety_factor,
                    paired_stddev_floor=config.power_paired_stddev_floor,
                    powered_paired_stddev=powered,
                    minimum_detectable_effect=mde,
                    alpha=config.alpha,
                    target_power=config.target_power,
                    pilot_seed_count=len(expected_seeds),
                    required_test_seed_count=required,
                    planned_test_seed_count=len(config.seed_plan.test_seeds),
                    status=("PASS" if len(config.seed_plan.test_seeds) >= required else "BLOCK"),
                )
            )
    return tuple(output)


def _paired_interval(
    candidate: ArmActionArtifact,
    reference: ArmActionArtifact,
    metric: str,
    endpoint_id: str,
    *,
    bootstrap_samples: int,
) -> PairedActionInterval:
    import random

    left = _seed_metric(candidate, metric)
    right = _seed_metric(reference, metric)
    if set(left) != set(right):
        raise ValueError("paired artifacts do not cover identical seeds")
    seeds = tuple(sorted(left))
    differences = [left[seed] - right[seed] for seed in seeds]
    rng = random.Random(content_sha256({"metric": metric, "seeds": seeds}))
    draws = sorted(fmean(rng.choice(differences) for _ in seeds) for _ in range(bootstrap_samples))
    lower_index = max(0, ceil(0.025 * len(draws)) - 1)
    upper_index = max(0, ceil(0.975 * len(draws)) - 1)
    return PairedActionInterval(
        endpoint_id=endpoint_id,
        candidate_arm_id=ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,
        reference_arm_id=reference.arm_id,
        difference_joint_minus_reference=fmean(differences),
        lower_95=draws[lower_index],
        upper_95=draws[upper_index],
        bootstrap_samples=bootstrap_samples,
    )


def _paired_intervals_for_artifacts(
    artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    bootstrap_samples: int,
) -> tuple[PairedActionInterval, ...]:
    joint = artifacts[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD]
    return tuple(
        _paired_interval(
            joint,
            artifacts[reference],
            metric,
            endpoint_id,
            bootstrap_samples=bootstrap_samples,
        )
        for reference in POWER_REFERENCES
        for endpoint_id, _role, metric, _mde_field in POWER_ENDPOINTS
    )


def _action_baseline_intervals(
    shared_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    retuned_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    baselines: dict[ActionPolicyBaselineId, ActionPolicyBaselineArtifact],
    bootstrap_samples: int,
) -> tuple[ActionBaselineInterval, ...]:
    import random

    output = []
    for track, artifacts in (
        (EvaluationTrack.SHARED_POLICY, shared_artifacts),
        (EvaluationTrack.INDEPENDENTLY_RETUNED_POLICY, retuned_artifacts),
    ):
        for arm in SHIFT_THREE_ARMS:
            candidate = _seed_metric(artifacts[arm], "balanced_downstream_action_regret")
            for baseline_id in ActionPolicyBaselineId:
                reference = _seed_metric(
                    baselines[baseline_id], "balanced_downstream_action_regret"
                )
                if set(candidate) != set(reference):
                    raise ValueError("action baseline comparison requires identical seeds")
                seeds = tuple(sorted(candidate))
                differences = [candidate[seed] - reference[seed] for seed in seeds]
                rng = random.Random(
                    content_sha256(
                        {
                            "track": track,
                            "arm": arm,
                            "baseline": baseline_id,
                            "seeds": seeds,
                        }
                    )
                )
                draws = sorted(
                    fmean(rng.choice(differences) for _ in seeds) for _ in range(bootstrap_samples)
                )
                lower_index = max(0, ceil(0.025 * len(draws)) - 1)
                upper_index = max(0, ceil(0.975 * len(draws)) - 1)
                output.append(
                    ActionBaselineInterval(
                        track=track,
                        candidate_arm_id=arm,
                        reference_baseline_id=baseline_id,
                        difference_detector_minus_baseline=fmean(differences),
                        lower_95=draws[lower_index],
                        upper_95=draws[upper_index],
                        bootstrap_samples=bootstrap_samples,
                    )
                )
    return tuple(output)


def _scenario_policy(
    policy: FrozenActionPolicy, scenario: UtilitySensitivityScenario
) -> FrozenActionPolicy:
    return policy.model_copy(
        update={
            "false_reset_cost": policy.false_reset_cost * scenario.false_reset_multiplier,
            "missed_reset_daily_cost": policy.missed_reset_daily_cost
            * scenario.unrecovered_habit_multiplier,
            "corrupted_mass_daily_cost": policy.corrupted_mass_daily_cost
            * scenario.corrupted_mass_multiplier,
            "verification_cost": policy.verification_cost * scenario.verification_multiplier,
        }
    )


def _utility_sensitivity_results(
    config: ProjectOneShiftActionDeathTestConfig,
    test_cases: Sequence[OnlineShiftGeneratedCase],
    shared_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    retuned_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact],
    shared_records: dict[ProjectOneAblationArmId, ArmActionTuningRecord],
    retuned_records: dict[ProjectOneAblationArmId, ArmRetunedPolicyTuningRecord],
) -> tuple[UtilitySensitivityResult, ...]:
    output = []
    for track, source, records in (
        (EvaluationTrack.SHARED_POLICY, shared_artifacts, shared_records),
        (
            EvaluationTrack.INDEPENDENTLY_RETUNED_POLICY,
            retuned_artifacts,
            retuned_records,
        ),
    ):
        for scenario in config.utility_sensitivity_scenarios:
            scenario_artifacts = {}
            for arm in SHIFT_THREE_ARMS:
                if track == EvaluationTrack.SHARED_POLICY:
                    base_policy = config.action_policy
                else:
                    retuned_record = records[arm]
                    if not isinstance(retuned_record, ArmRetunedPolicyTuningRecord):
                        raise TypeError("retuned track requires retuned policy records")
                    base_policy = retuned_record.selected_policy
                scenario_artifacts[arm] = _artifact_from_predictions(
                    arm,
                    records[arm].selected_params,
                    test_cases,
                    source[arm].predictions,
                    _scenario_policy(base_policy, scenario),
                    "test",
                )
            intervals = tuple(
                item
                for item in _paired_intervals_for_artifacts(
                    scenario_artifacts, config.bootstrap_samples
                )
                if item.endpoint_id == PRIMARY_ENDPOINT_ID
            )
            output.append(
                UtilitySensitivityResult(
                    track=track,
                    scenario_id=scenario.scenario_id,
                    metrics_by_arm={
                        arm: scenario_artifacts[arm].metrics for arm in SHIFT_THREE_ARMS
                    },
                    regret_intervals=intervals,
                )
            )
    return tuple(output)


def decide_research_route(
    power: Sequence[MetricPowerAnalysis],
    intervals: Sequence[PairedActionInterval],
    policy: FrozenActionPolicy,
) -> PreregisteredDecision:
    if not power or any(item.status != "PASS" for item in power):
        return PreregisteredDecision(
            decision=ResearchDecision.BLOCK_UNDERPOWERED,
            primary_joint_minus_ordinary=None,
            corruption_joint_minus_ordinary=None,
            primary_joint_minus_legacy=None,
            corruption_joint_minus_legacy=None,
            primary_practical_threshold=policy.practical_regret_mde,
            corruption_practical_threshold=policy.practical_corruption_mde,
            rationale_id="decision.test-not-opened-power-block@1",
        )
    primary = next(
        item
        for item in intervals
        if item.endpoint_id == PRIMARY_ENDPOINT_ID
        and item.reference_arm_id == ProjectOneAblationArmId.ORDINARY_BOCPD
    )
    corruption = next(
        item
        for item in intervals
        if item.endpoint_id == KEY_SECONDARY_ENDPOINT_ID
        and item.reference_arm_id == ProjectOneAblationArmId.ORDINARY_BOCPD
    )
    primary_legacy = next(
        item
        for item in intervals
        if item.endpoint_id == PRIMARY_ENDPOINT_ID
        and item.reference_arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD
    )
    corruption_legacy = next(
        item
        for item in intervals
        if item.endpoint_id == KEY_SECONDARY_ENDPOINT_ID
        and item.reference_arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD
    )
    if (
        primary.upper_95 <= -policy.practical_regret_mde
        and corruption.upper_95 <= -policy.practical_corruption_mde
        and primary_legacy.upper_95 <= -policy.practical_regret_mde
        and corruption_legacy.upper_95 <= -policy.practical_corruption_mde
    ):
        decision = ResearchDecision.CONTINUE_JOINT
        rationale = "decision.joint-clears-action-mde-and-corruption-guardrail@1"
    elif primary.lower_95 >= policy.practical_regret_mde:
        decision = ResearchDecision.USE_ORDINARY
        rationale = "decision.ordinary-clears-action-mde-over-joint@1"
    elif (
        primary_legacy.lower_95 >= policy.practical_regret_mde
        or primary.difference_joint_minus_reference >= 0.0
    ):
        decision = ResearchDecision.REBUILD_JOINT
        rationale = "decision.joint-no-positive-action-benefit@1"
    else:
        decision = ResearchDecision.INCONCLUSIVE
        rationale = "decision.action-interval-crosses-practical-threshold@1"
    return PreregisteredDecision(
        decision=decision,
        primary_joint_minus_ordinary=primary,
        corruption_joint_minus_ordinary=corruption,
        primary_joint_minus_legacy=primary_legacy,
        corruption_joint_minus_legacy=corruption_legacy,
        primary_practical_threshold=policy.practical_regret_mde,
        corruption_practical_threshold=policy.practical_corruption_mde,
        rationale_id=rationale,
    )


def decide_cross_track_route(
    shared: PreregisteredDecision,
    retuned: PreregisteredDecision,
    policy: FrozenActionPolicy,
) -> CrossTrackDecision:
    decisions = (shared.decision, retuned.decision)
    if ResearchDecision.BLOCK_UNDERPOWERED in decisions:
        decision = ResearchDecision.BLOCK_UNDERPOWERED
        rationale = "decision.cross-track-test-not-opened-power-block@2"
    else:
        shared_legacy = shared.primary_joint_minus_legacy
        retuned_legacy = retuned.primary_joint_minus_legacy
        if (
            shared_legacy is not None
            and retuned_legacy is not None
            and shared_legacy.lower_95 >= policy.practical_regret_mde
            and retuned_legacy.lower_95 >= policy.practical_regret_mde
        ):
            decision = ResearchDecision.REBUILD_JOINT
            rationale = "decision.both-tracks-legacy-clears-action-mde-over-joint@2"
        elif decisions == (
            ResearchDecision.CONTINUE_JOINT,
            ResearchDecision.CONTINUE_JOINT,
        ):
            decision = ResearchDecision.CONTINUE_JOINT
            rationale = "decision.both-tracks-joint-clears-all-gates@2"
        elif decisions == (ResearchDecision.USE_ORDINARY, ResearchDecision.USE_ORDINARY):
            decision = ResearchDecision.USE_ORDINARY
            rationale = "decision.both-tracks-ordinary-clears-action-mde@2"
        else:
            decision = ResearchDecision.INCONCLUSIVE
            rationale = "decision.cross-track-evidence-disagrees-or-crosses-mde@2"
    return CrossTrackDecision(
        decision=decision,
        shared_policy_decision=shared.decision,
        independently_retuned_policy_decision=retuned.decision,
        rationale_id=rationale,
    )


def _beats_never_act_in_both_tracks(
    intervals: Sequence[ActionBaselineInterval],
    arm: ProjectOneAblationArmId,
    minimum_effect: float,
) -> bool:
    matched = tuple(
        item
        for item in intervals
        if item.candidate_arm_id == arm
        and item.reference_baseline_id == ActionPolicyBaselineId.NEVER_ACT
    )
    return tuple(item.track for item in matched) == (
        EvaluationTrack.SHARED_POLICY,
        EvaluationTrack.INDEPENDENTLY_RETUNED_POLICY,
    ) and all(item.upper_95 <= -minimum_effect for item in matched)


class ProjectOneShiftActionDeathTestRunner:
    def run(
        self,
        config: ProjectOneShiftActionDeathTestConfig,
        *,
        code_snapshot_sha256: str,
        git_commit_sha: str,
    ) -> ProjectOneShiftActionDeathTestReport:
        checked = ProjectOneShiftActionDeathTestConfig.model_validate(
            config.model_dump(mode="json")
        )
        plan = checked.seed_plan
        non_test_seeds = plan.validation_seeds + plan.pilot_seeds
        non_test_suite = OnlineShiftSuiteGenerator().generate(
            OnlineShiftSuiteConfig(
                duration_days=checked.duration_days,
                seeds=non_test_seeds,
                case_id_salt=(
                    "project-one-action-death-test-nontest@2"
                    if checked.protocol_version.endswith("@6")
                    else "project-one-action-death-test-nontest@1"
                ),
                shuffle_seed=(20260826 if checked.protocol_version.endswith("@6") else 20260822),
            )
        )
        by_seed: dict[int, list[OnlineShiftGeneratedCase]] = {seed: [] for seed in non_test_seeds}
        for case in non_test_suite.cases:
            by_seed[case.evaluator_truth.scenario_seed].append(
                OnlineShiftGeneratedCase(
                    model_input=case.model_input,
                    evaluator_truth=case.evaluator_truth.model_copy(
                        update={
                            "split": OnlineShiftSplit.VALIDATION,
                            "intervention_available": (
                                checked.action_policy.active_verification_enabled
                            ),
                        }
                    ),
                )
            )
        validation = tuple(case for seed in plan.validation_seeds for case in by_seed[seed])
        pilot = tuple(case for seed in plan.pilot_seeds for case in by_seed[seed])
        validation_input_artifact = _input_artifact(validation, "validation")
        pilot_input_artifact = _input_artifact(pilot, "pilot")
        validation_ledgers = _validation_prediction_ledgers(
            validation, validation_input_artifact.artifact_sha256
        )

        tuning = []
        selected: dict[ProjectOneAblationArmId, dict[str, int | float]] = {}
        for arm in SHIFT_THREE_ARMS:
            items, selected_index = _shared_candidate_ledger(
                arm, validation_ledgers[arm], validation, checked.action_policy
            )
            params = validation_ledgers[arm].candidates[selected_index].params
            selected[arm] = params
            tuning.append(
                ArmActionTuningRecord(
                    arm_id=arm,
                    evaluated_trial_count=len(items),
                    validation_case_count=len(validation),
                    selected_params=params,
                    selected_params_sha256=content_sha256(params),
                    selected_validation_regret=items[selected_index][
                        "metrics"
                    ].balanced_downstream_action_regret,
                    search_space_sha256=content_sha256(_SEARCH_SPACES[arm]),
                    candidate_ledger_sha256=content_sha256(items),
                    selected_candidate_index=selected_index,
                )
            )

        policy_space = _retuned_policy_space(checked.action_policy)
        retuned_tuning = []
        retuned_selected_params: dict[ProjectOneAblationArmId, dict[str, int | float]] = {}
        retuned_selected_policies: dict[ProjectOneAblationArmId, FrozenActionPolicy] = {}
        for arm in SHIFT_THREE_ARMS:
            items, (detector_index, policy_index) = _retuned_candidate_ledger(
                validation_ledgers[arm], validation, policy_space
            )
            params = validation_ledgers[arm].candidates[detector_index].params
            policy = policy_space[policy_index]
            selected_flat = detector_index * len(policy_space) + policy_index
            retuned_selected_params[arm] = params
            retuned_selected_policies[arm] = policy
            retuned_tuning.append(
                ArmRetunedPolicyTuningRecord(
                    arm_id=arm,
                    detector_trial_count=len(_SEARCH_SPACES[arm]),
                    policy_trial_count=len(policy_space),
                    evaluated_candidate_count=len(items),
                    validation_case_count=len(validation),
                    selected_params=params,
                    selected_params_sha256=content_sha256(params),
                    policy_template=checked.action_policy,
                    selected_policy=policy,
                    selected_policy_sha256=content_sha256(policy),
                    selected_validation_regret=items[selected_flat][
                        "metrics"
                    ].balanced_downstream_action_regret,
                    detector_search_space_sha256=content_sha256(_SEARCH_SPACES[arm]),
                    policy_search_space_sha256=content_sha256(policy_space),
                    candidate_ledger_sha256=content_sha256(items),
                    selected_detector_index=detector_index,
                    selected_policy_index=policy_index,
                )
            )

        pilot_artifacts = {
            arm: _evaluate_arm(arm, selected[arm], pilot, checked.action_policy, "pilot")
            for arm in SHIFT_THREE_ARMS
        }
        retuned_pilot_artifacts = {
            arm: _evaluate_arm(
                arm,
                retuned_selected_params[arm],
                pilot,
                retuned_selected_policies[arm],
                "pilot",
            )
            for arm in SHIFT_THREE_ARMS
        }
        analyses = _power_analyses_from_pilot(pilot_artifacts, checked)
        retuned_analyses = _power_analyses_from_pilot(retuned_pilot_artifacts, checked)

        test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact] = {}
        retuned_test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact] = {}
        test_input_artifact: SplitInputArtifact | None = None
        test: tuple[OnlineShiftGeneratedCase, ...] = ()
        intervals: tuple[PairedActionInterval, ...] = ()
        retuned_intervals: tuple[PairedActionInterval, ...] = ()
        if all(item.status == "PASS" for item in (*analyses, *retuned_analyses)):
            # This is intentionally below the power gate: no TEST inputs or
            # evaluator truths exist in this process before pilot power passes.
            test_suite = OnlineShiftSuiteGenerator().generate(
                OnlineShiftSuiteConfig(
                    duration_days=checked.duration_days,
                    seeds=plan.test_seeds,
                    case_id_salt=(
                        "project-one-action-death-test-test@3"
                        if checked.protocol_version.endswith("@6")
                        else "project-one-action-death-test-test@2"
                    ),
                    shuffle_seed=(
                        20260827 if checked.protocol_version.endswith("@6") else 20260824
                    ),
                )
            )
            test_by_seed: dict[int, list[OnlineShiftGeneratedCase]] = {
                seed: [] for seed in plan.test_seeds
            }
            for case in test_suite.cases:
                test_by_seed[case.evaluator_truth.scenario_seed].append(
                    OnlineShiftGeneratedCase(
                        model_input=case.model_input,
                        evaluator_truth=case.evaluator_truth.model_copy(
                            update={
                                "split": OnlineShiftSplit.TEST,
                                "intervention_available": (
                                    checked.action_policy.active_verification_enabled
                                ),
                            }
                        ),
                    )
                )
            test = tuple(case for seed in plan.test_seeds for case in test_by_seed[seed])
            test_input_artifact = _input_artifact(test, "test")
            test_artifacts = {
                arm: _evaluate_arm(arm, selected[arm], test, checked.action_policy, "test")
                for arm in SHIFT_THREE_ARMS
            }
            retuned_test_artifacts = {
                arm: _evaluate_arm(
                    arm,
                    retuned_selected_params[arm],
                    test,
                    retuned_selected_policies[arm],
                    "test",
                )
                for arm in SHIFT_THREE_ARMS
            }
            intervals = _paired_intervals_for_artifacts(test_artifacts, checked.bootstrap_samples)
            retuned_intervals = _paired_intervals_for_artifacts(
                retuned_test_artifacts, checked.bootstrap_samples
            )

        shared_decision = decide_research_route(analyses, intervals, checked.action_policy)
        retuned_decision = decide_research_route(
            retuned_analyses, retuned_intervals, checked.action_policy
        )
        shared_record_map = {item.arm_id: item for item in tuning}
        retuned_record_map = {item.arm_id: item for item in retuned_tuning}
        sensitivity = (
            _utility_sensitivity_results(
                checked,
                test,
                test_artifacts,
                retuned_test_artifacts,
                shared_record_map,
                retuned_record_map,
            )
            if test
            else ()
        )
        action_policy_baselines = (
            _action_policy_baselines(test, checked.action_policy) if test else {}
        )
        action_baseline_intervals = (
            _action_baseline_intervals(
                test_artifacts,
                retuned_test_artifacts,
                action_policy_baselines,
                checked.bootstrap_samples,
            )
            if test
            else ()
        )
        overall = decide_cross_track_route(shared_decision, retuned_decision, checked.action_policy)
        if overall.decision == ResearchDecision.REBUILD_JOINT and any(
            next(
                interval
                for interval in result.regret_intervals
                if interval.reference_arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD
            ).lower_95
            < checked.action_policy.practical_regret_mde
            for result in sensitivity
        ):
            overall = CrossTrackDecision(
                decision=ResearchDecision.INCONCLUSIVE,
                shared_policy_decision=shared_decision.decision,
                independently_retuned_policy_decision=retuned_decision.decision,
                rationale_id="decision.utility-sensitivity-not-robust@5",
            )
        guarded_arm = {
            ResearchDecision.CONTINUE_JOINT: (ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD),
            ResearchDecision.REBUILD_JOINT: (ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD),
            ResearchDecision.USE_ORDINARY: ProjectOneAblationArmId.ORDINARY_BOCPD,
        }.get(overall.decision)
        if guarded_arm is not None and not _beats_never_act_in_both_tracks(
            action_baseline_intervals,
            guarded_arm,
            checked.action_policy.practical_regret_mde,
        ):
            overall = CrossTrackDecision(
                decision=ResearchDecision.INCONCLUSIVE,
                shared_policy_decision=shared_decision.decision,
                independently_retuned_policy_decision=retuned_decision.decision,
                rationale_id="decision.action-winner-does-not-beat-never-act@5",
            )

        payload = {
            "protocol_version": checked.protocol_version,
            "config": checked,
            "config_sha256": content_sha256(checked),
            "code_snapshot_sha256": code_snapshot_sha256,
            "git_commit_sha": git_commit_sha,
            "policy": checked.action_policy,
            "policy_sha256": content_sha256(checked.action_policy),
            "validation_input_artifact": validation_input_artifact,
            "pilot_input_artifact": pilot_input_artifact,
            "test_input_artifact": test_input_artifact,
            "validation_prediction_ledgers": validation_ledgers,
            "tuning_records": tuple(tuning),
            "pilot_artifacts": pilot_artifacts,
            "power_analyses": tuple(analyses),
            "test_artifacts": test_artifacts,
            "paired_test_intervals": intervals,
            "decision": shared_decision,
            "retuned_tuning_records": tuple(retuned_tuning),
            "retuned_pilot_artifacts": retuned_pilot_artifacts,
            "retuned_power_analyses": retuned_analyses,
            "retuned_test_artifacts": retuned_test_artifacts,
            "retuned_paired_test_intervals": retuned_intervals,
            "retuned_decision": retuned_decision,
            "overall_decision": overall,
            "utility_sensitivity_results": sensitivity,
            "action_policy_baselines": action_policy_baselines,
            "action_baseline_intervals": action_baseline_intervals,
        }
        full_payload = {
            **payload,
            "primary_endpoint_id": PRIMARY_ENDPOINT_ID,
            "key_secondary_endpoint_id": KEY_SECONDARY_ENDPOINT_ID,
            "multiple_comparisons_policy": (
                "intersection-union-two-tracks-two-references-utility-sensitivity@6"
                if checked.protocol_version.endswith("@6")
                else "intersection-union-two-tracks-two-references-utility-sensitivity@5"
            ),
            "allowed_claims": _claim_ids(checked.protocol_version)[0],
            "forbidden_claims": _claim_ids(checked.protocol_version)[1],
        }
        return ProjectOneShiftActionDeathTestReport(
            **full_payload,
            report_sha256=content_sha256(full_payload),
        )
