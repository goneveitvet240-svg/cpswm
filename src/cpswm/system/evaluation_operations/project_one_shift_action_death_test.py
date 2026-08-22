"""Action-level matched death test for the Project One SHIFT detectors.

This is deliberately a research gate, not another authority layer.  The three
detectors are independently tuned on validation data, then connected to one
frozen detector-neutral habit reset/consolidation policy.  Pilot seeds estimate
paired variance before the TEST seed partition is inspected.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from math import ceil
from statistics import NormalDist, fmean, stdev
from typing import Literal

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, Probability
from cpswm.system.reproducibility import content_sha256

from .fair_ablation import ProjectOneAblationArmId
from .online_shift_attribution import (
    OnlineShiftAttributionCase,
    OnlineShiftCaseTruth,
    OnlineShiftEvaluator,
    OnlineShiftGeneratedCase,
    OnlineShiftPrediction,
    OnlineShiftReport,
    OnlineShiftSplit,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from .project_one_shift_gates import _SEARCH_SPACES, SHIFT_THREE_ARMS, _model_factory
from .shift_attribution import ShiftCause

PRIMARY_ENDPOINT_ID = "downstream-action-regret.normalized-per-case@1"
KEY_SECONDARY_ENDPOINT_ID = "corrupted-habit-mass.mean-per-case@1"
ALLOWED_CLAIM_IDS = (
    "claim.synthetic-shift-action-death-test-reported@1",
    "claim.detector-neutral-policy-used@1",
    "claim.validation-retuned-three-arm-comparison@1",
)
FORBIDDEN_CLAIM_IDS = (
    "claim.general-method-superiority.forbidden@3",
    "claim.state-of-the-art.forbidden@3",
    "claim.external-validity.forbidden@1",
    "claim.formal-structure-one-b1-complete.forbidden@3",
    "claim.all-eleven-arms-experimentally-complete.forbidden@3",
)


class ResearchDecision(StrEnum):
    CONTINUE_JOINT = "continue_joint"
    REBUILD_JOINT = "rebuild_joint"
    USE_ORDINARY = "use_ordinary"
    INCONCLUSIVE = "inconclusive"
    BLOCK_UNDERPOWERED = "block_underpowered"


class FrozenActionPolicy(ContractModel):
    policy_id: Literal["detector-neutral-habit-action-policy@1"] = (
        "detector-neutral-habit-action-policy@1"
    )
    reset_probability_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    consolidation_probability_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    attribution_margin: float = Field(default=0.15, ge=0.0, lt=1.0)
    verification_cost: float = Field(default=0.05, ge=0.0)
    false_reset_cost: float = Field(default=0.25, ge=0.0)
    missed_reset_daily_cost: float = Field(default=0.10, ge=0.0)
    corrupted_mass_daily_cost: float = Field(default=0.10, ge=0.0)
    practical_regret_mde: float = Field(default=0.05, gt=0.0, le=1.0)
    practical_corruption_mde: float = Field(default=0.02, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> FrozenActionPolicy:
        if self.consolidation_probability_threshold < self.reset_probability_threshold:
            raise ValueError("consolidation threshold must not be below reset threshold")
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
    test_seeds: tuple[NonNegativeInt, ...] = tuple(range(7101, 7403, 2))

    @model_validator(mode="after")
    def validate_partitions(self) -> ActionSeedPlan:
        if len(self.validation_seeds) < 3 or len(self.pilot_seeds) < 5:
            raise ValueError("validation requires >=3 seeds and pilot requires >=5 seeds")
        flattened = self.validation_seeds + self.pilot_seeds + self.test_seeds
        if len(flattened) != len(set(flattened)):
            raise ValueError("validation, pilot, and TEST seeds must be globally disjoint")
        return self


class ProjectOneShiftActionDeathTestConfig(ContractModel):
    protocol_version: Literal["project-one-shift-action-death-test@1"] = (
        "project-one-shift-action-death-test@1"
    )
    seed_plan: ActionSeedPlan = Field(default_factory=ActionSeedPlan)
    action_policy: FrozenActionPolicy = Field(default_factory=FrozenActionPolicy)
    duration_days: PositiveInt = 10
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    target_power: float = Field(default=0.80, gt=0.0, lt=1.0)
    bootstrap_samples: PositiveInt = 2000

    @model_validator(mode="after")
    def validate_config(self) -> ProjectOneShiftActionDeathTestConfig:
        if self.duration_days < 8:
            raise ValueError("action trajectories require at least eight days")
        if self.bootstrap_samples < 500:
            raise ValueError("paired seed bootstrap requires at least 500 samples")
        return self


class CaseActionOutcome(ContractModel):
    case_id: str = Field(min_length=1)
    scenario_seed: NonNegativeInt
    habit_shift_required: bool
    reset_issued: bool
    consolidation_issued: bool
    verification_issued: bool
    false_reset: bool
    missed_reset: bool
    false_consolidation: bool
    corrupted_habit_mass: Probability
    recovery_time_days: float = Field(ge=0.0)
    unnecessary_verification_cost: float = Field(ge=0.0)
    downstream_action_regret: Probability
    task_success: bool


class ArmActionMetrics(ContractModel):
    sample_count: PositiveInt
    false_reset_rate: Probability
    missed_reset_rate: Probability
    false_consolidation_rate: Probability
    corrupted_habit_mass: Probability
    recovery_time_days: float = Field(ge=0.0)
    unnecessary_verification_cost: float = Field(ge=0.0)
    downstream_action_regret: Probability
    task_success_rate: Probability


class ActionCaseTruth(ContractModel):
    truth: OnlineShiftCaseTruth
    stream_start_time: datetime
    duration_days: PositiveInt

    @model_validator(mode="after")
    def validate_horizon(self) -> ActionCaseTruth:
        horizon_end = self.stream_start_time + timedelta(days=self.duration_days)
        if not self.stream_start_time < self.truth.change_time < horizon_end:
            raise ValueError("action truth change time lies outside its stream horizon")
        return self


class ArmActionArtifact(ContractModel):
    arm_id: ProjectOneAblationArmId
    split_id: Literal["validation", "pilot", "test"]
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: FrozenActionPolicy
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_truths: tuple[ActionCaseTruth, ...] = Field(min_length=1)
    predictions: tuple[OnlineShiftPrediction, ...] = Field(min_length=1)
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
                stream_start_time=truth_by_id[item.case_id].stream_start_time,
                duration_days=truth_by_id[item.case_id].duration_days,
            )
            for item in self.outcomes
        )
        if recomputed_outcomes != self.outcomes:
            raise ValueError("case action outcomes do not recompute from truth and predictions")
        if self.metrics != aggregate_action_metrics(self.outcomes):
            raise ValueError("action metrics do not recompute from case outcomes")
        rebound = tuple(
            OnlineShiftAttributionCase(
                truth=item.truth,
                prediction=prediction_by_id[str(item.truth.case_id)],
            )
            for item in self.case_truths
        )
        if self.mechanism_metrics != OnlineShiftEvaluator().evaluate(rebound):
            raise ValueError("mechanism metrics do not recompute from truth and predictions")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("action artifact hash mismatch")
        return self


class ArmActionTuningRecord(ContractModel):
    arm_id: ProjectOneAblationArmId
    evaluated_trial_count: PositiveInt
    validation_case_count: PositiveInt
    selected_params: dict[str, int | float]
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_validation_regret: Probability
    search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

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
        return self


class MetricPowerAnalysis(ContractModel):
    endpoint_id: Literal[
        "downstream-action-regret.normalized-per-case@1",
        "corrupted-habit-mass.mean-per-case@1",
    ]
    role: Literal["primary", "key_secondary"]
    empirical_paired_stddev: float = Field(ge=0.0)
    minimum_detectable_effect: float = Field(gt=0.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    target_power: float = Field(gt=0.0, lt=1.0)
    pilot_seed_count: PositiveInt
    required_test_seed_count: PositiveInt
    planned_test_seed_count: PositiveInt
    status: Literal["PASS", "BLOCK"]

    @model_validator(mode="after")
    def validate_power(self) -> MetricPowerAnalysis:
        expected = required_paired_seed_count(
            self.empirical_paired_stddev,
            self.minimum_detectable_effect,
            alpha=self.alpha,
            target_power=self.target_power,
        )
        if self.required_test_seed_count != expected:
            raise ValueError("required seed count does not recompute")
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


class PreregisteredDecision(ContractModel):
    decision: ResearchDecision
    primary_joint_minus_ordinary: PairedActionInterval | None
    corruption_joint_minus_ordinary: PairedActionInterval | None
    primary_joint_minus_legacy: PairedActionInterval | None
    corruption_joint_minus_legacy: PairedActionInterval | None
    primary_practical_threshold: float = Field(gt=0.0)
    corruption_practical_threshold: float = Field(gt=0.0)
    rationale_id: str = Field(min_length=1)


class ProjectOneShiftActionDeathTestReport(ContractModel):
    protocol_version: Literal["project-one-shift-action-death-test@1"]
    config: ProjectOneShiftActionDeathTestConfig
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    primary_endpoint_id: Literal["downstream-action-regret.normalized-per-case@1"] = (
        PRIMARY_ENDPOINT_ID
    )
    key_secondary_endpoint_id: Literal["corrupted-habit-mass.mean-per-case@1"] = (
        KEY_SECONDARY_ENDPOINT_ID
    )
    multiple_comparisons_policy: Literal[
        "primary-alpha-0.05-key-secondary-holm-mechanisms-descriptive@1"
    ] = "primary-alpha-0.05-key-secondary-holm-mechanisms-descriptive@1"
    policy: FrozenActionPolicy
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tuning_records: tuple[ArmActionTuningRecord, ...]
    pilot_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    power_analyses: tuple[MetricPowerAnalysis, ...]
    test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact]
    paired_test_intervals: tuple[PairedActionInterval, ...]
    decision: PreregisteredDecision
    allowed_claims: tuple[str, ...] = ALLOWED_CLAIM_IDS
    forbidden_claims: tuple[str, ...] = FORBIDDEN_CLAIM_IDS
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ProjectOneShiftActionDeathTestReport:
        if self.config_sha256 != content_sha256(self.config):
            raise ValueError("death-test config hash mismatch")
        if self.policy != self.config.action_policy:
            raise ValueError("report policy differs from the frozen config")
        if self.policy_sha256 != content_sha256(self.policy):
            raise ValueError("frozen action policy hash mismatch")
        if tuple(item.arm_id for item in self.tuning_records) != SHIFT_THREE_ARMS:
            raise ValueError("tuning records must cover the ordered SHIFT three arms")
        if set(self.pilot_artifacts) != set(SHIFT_THREE_ARMS):
            raise ValueError("pilot artifacts must cover all three arms")
        selected_hashes = {item.arm_id: item.selected_params_sha256 for item in self.tuning_records}
        for arm, artifact in (*self.pilot_artifacts.items(), *self.test_artifacts.items()):
            if artifact.arm_id != arm:
                raise ValueError("artifact dictionary key does not match arm")
            if artifact.policy_sha256 != self.policy_sha256 or artifact.policy != self.policy:
                raise ValueError("all arms must use the identical frozen action policy")
            if artifact.selected_params_sha256 != selected_hashes[arm]:
                raise ValueError("artifact parameters differ from validation selection")
        if self.allowed_claims != ALLOWED_CLAIM_IDS or self.forbidden_claims != FORBIDDEN_CLAIM_IDS:
            raise ValueError("claim IDs must equal the canonical sets")
        power_pass = all(item.status == "PASS" for item in self.power_analyses)
        if power_pass and set(self.test_artifacts) != set(SHIFT_THREE_ARMS):
            raise ValueError("powered report requires all three TEST artifacts")
        if not power_pass and (self.test_artifacts or self.paired_test_intervals):
            raise ValueError("underpowered report must not inspect or report TEST")
        if power_pass:
            expected_intervals = tuple(
                _paired_interval(
                    self.test_artifacts[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD],
                    self.test_artifacts[reference],
                    metric,
                    endpoint_id,
                    bootstrap_samples=self.config.bootstrap_samples,
                )
                for reference in (
                    ProjectOneAblationArmId.ORDINARY_BOCPD,
                    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
                )
                for endpoint_id, metric in (
                    (PRIMARY_ENDPOINT_ID, "downstream_action_regret"),
                    (KEY_SECONDARY_ENDPOINT_ID, "corrupted_habit_mass"),
                )
            )
            if expected_intervals != self.paired_test_intervals:
                raise ValueError("paired intervals do not recompute from TEST artifacts")
        expected_decision = decide_research_route(
            self.power_analyses,
            self.paired_test_intervals,
            self.policy,
        )
        if self.decision != expected_decision:
            raise ValueError("research decision does not follow preregistered rule")
        payload = self.model_dump(mode="json", exclude={"report_sha256"})
        if self.report_sha256 != content_sha256(payload):
            raise ValueError("action death-test report hash mismatch")
        return self


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


def _case_outcome(
    truth: OnlineShiftCaseTruth,
    prediction: OnlineShiftPrediction,
    policy: FrozenActionPolicy,
    *,
    stream_start_time: datetime,
    duration_days: int,
) -> CaseActionOutcome:
    probabilities = prediction.cause_probabilities
    habit_probability = float(probabilities.get(ShiftCause.OWNER_HABIT_REGIME, 0.0))
    ranked = sorted((float(value) for value in probabilities.values()), reverse=True)
    margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
    detected = prediction.predicted_change_time is not None
    reset = detected and habit_probability >= policy.reset_probability_threshold
    consolidate = (
        detected
        and habit_probability >= policy.consolidation_probability_threshold
        and margin >= policy.attribution_margin
    )
    verify = (
        detected
        and not consolidate
        and (
            habit_probability >= policy.reset_probability_threshold
            or margin < policy.attribution_margin
        )
    )
    true_habit = ShiftCause.OWNER_HABIT_REGIME in truth.true_causes
    false_reset = reset and not true_habit
    missed_reset = true_habit and not reset
    false_consolidation = consolidate and not true_habit
    horizon_end = stream_start_time + timedelta(days=duration_days)
    remaining_days = max(0.0, (horizon_end - truth.change_time).total_seconds() / 86400.0)
    if true_habit and reset and prediction.predicted_change_time is not None:
        recovery_days = max(
            0.0,
            (prediction.predicted_change_time - truth.change_time).total_seconds() / 86400.0,
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
    success = not false_reset and not missed_reset and not false_consolidation
    return CaseActionOutcome(
        case_id=str(truth.case_id),
        scenario_seed=truth.scenario_seed,
        habit_shift_required=true_habit,
        reset_issued=reset,
        consolidation_issued=consolidate,
        verification_issued=verify,
        false_reset=false_reset,
        missed_reset=missed_reset,
        false_consolidation=false_consolidation,
        corrupted_habit_mass=corrupted_mass,
        recovery_time_days=recovery_days,
        unnecessary_verification_cost=policy.verification_cost
        if verify and not true_habit
        else 0.0,
        downstream_action_regret=regret,
        task_success=success,
    )


def aggregate_action_metrics(outcomes: Sequence[CaseActionOutcome]) -> ArmActionMetrics:
    if not outcomes:
        raise ValueError("action evaluation requires outcomes")
    habit = [item for item in outcomes if item.habit_shift_required]
    non_habit = [item for item in outcomes if not item.habit_shift_required]
    return ArmActionMetrics(
        sample_count=len(outcomes),
        false_reset_rate=fmean(float(item.false_reset) for item in non_habit) if non_habit else 0.0,
        missed_reset_rate=fmean(float(item.missed_reset) for item in habit) if habit else 0.0,
        false_consolidation_rate=(
            fmean(float(item.false_consolidation) for item in non_habit) if non_habit else 0.0
        ),
        corrupted_habit_mass=fmean(item.corrupted_habit_mass for item in outcomes),
        recovery_time_days=fmean(item.recovery_time_days for item in habit) if habit else 0.0,
        unnecessary_verification_cost=fmean(
            item.unnecessary_verification_cost for item in outcomes
        ),
        downstream_action_regret=fmean(item.downstream_action_regret for item in outcomes),
        task_success_rate=fmean(float(item.task_success) for item in outcomes),
    )


def _evaluate_arm(
    arm: ProjectOneAblationArmId,
    params: dict[str, int | float],
    cases: Sequence[OnlineShiftGeneratedCase],
    policy: FrozenActionPolicy,
    split_id: Literal["validation", "pilot", "test"],
) -> ArmActionArtifact:
    model = _model_factory(arm, params)
    predictions = tuple(model.predict(case.model_input) for case in cases)  # type: ignore[attr-defined]
    case_truths = tuple(
        ActionCaseTruth(
            truth=case.evaluator_truth,
            stream_start_time=case.model_input.observation_stream.start_time,
            duration_days=case.model_input.observation_stream.duration_days,
        )
        for case in cases
    )
    outcomes = tuple(
        _case_outcome(
            case.evaluator_truth,
            prediction,
            policy,
            stream_start_time=case.model_input.observation_stream.start_time,
            duration_days=case.model_input.observation_stream.duration_days,
        )
        for case, prediction in zip(cases, predictions, strict=True)
    )
    bound = tuple(
        OnlineShiftAttributionCase(truth=case.evaluator_truth, prediction=prediction)
        for case, prediction in zip(cases, predictions, strict=True)
    )
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


def _seed_metric(artifact: ArmActionArtifact, metric: str) -> dict[int, float]:
    by_seed: dict[int, list[CaseActionOutcome]] = {}
    for outcome in artifact.outcomes:
        by_seed.setdefault(outcome.scenario_seed, []).append(outcome)
    return {
        seed: float(getattr(aggregate_action_metrics(items), metric))
        for seed, items in by_seed.items()
    }


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
                case_id_salt="project-one-action-death-test-nontest@1",
                shuffle_seed=20260822,
            )
        )
        by_seed = {seed: [] for seed in non_test_seeds}
        for case in non_test_suite.cases:
            by_seed[case.evaluator_truth.scenario_seed].append(
                OnlineShiftGeneratedCase(
                    model_input=case.model_input,
                    evaluator_truth=case.evaluator_truth.model_copy(
                        update={"split": OnlineShiftSplit.VALIDATION}
                    ),
                )
            )
        validation = tuple(case for seed in plan.validation_seeds for case in by_seed[seed])
        pilot = tuple(case for seed in plan.pilot_seeds for case in by_seed[seed])

        tuning = []
        selected: dict[ProjectOneAblationArmId, dict[str, int | float]] = {}
        for arm in SHIFT_THREE_ARMS:
            trials = [
                (
                    _evaluate_arm(arm, params, validation, checked.action_policy, "validation"),
                    params,
                )
                for params in _SEARCH_SPACES[arm]
            ]
            artifact, params = min(
                trials,
                key=lambda item: (
                    item[0].metrics.downstream_action_regret,
                    item[0].metrics.corrupted_habit_mass,
                    -item[0].metrics.task_success_rate,
                    item[0].mechanism_metrics.cause_negative_log_likelihood,
                    content_sha256(item[1]),
                ),
            )
            selected[arm] = params
            tuning.append(
                ArmActionTuningRecord(
                    arm_id=arm,
                    evaluated_trial_count=len(trials),
                    validation_case_count=len(validation),
                    selected_params=params,
                    selected_params_sha256=content_sha256(params),
                    selected_validation_regret=artifact.metrics.downstream_action_regret,
                    search_space_sha256=content_sha256(_SEARCH_SPACES[arm]),
                )
            )

        pilot_artifacts = {
            arm: _evaluate_arm(arm, selected[arm], pilot, checked.action_policy, "pilot")
            for arm in SHIFT_THREE_ARMS
        }
        joint = pilot_artifacts[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD]
        ordinary = pilot_artifacts[ProjectOneAblationArmId.ORDINARY_BOCPD]
        analyses = []
        for endpoint_id, role, metric, mde in (
            (
                PRIMARY_ENDPOINT_ID,
                "primary",
                "downstream_action_regret",
                checked.action_policy.practical_regret_mde,
            ),
            (
                KEY_SECONDARY_ENDPOINT_ID,
                "key_secondary",
                "corrupted_habit_mass",
                checked.action_policy.practical_corruption_mde,
            ),
        ):
            joint_by_seed = _seed_metric(joint, metric)
            ordinary_by_seed = _seed_metric(ordinary, metric)
            differences = [
                joint_by_seed[seed] - ordinary_by_seed[seed] for seed in plan.pilot_seeds
            ]
            empirical = stdev(differences) if len(differences) > 1 else 0.0
            required = required_paired_seed_count(
                empirical, mde, alpha=checked.alpha, target_power=checked.target_power
            )
            analyses.append(
                MetricPowerAnalysis(
                    endpoint_id=endpoint_id,
                    role=role,
                    empirical_paired_stddev=empirical,
                    minimum_detectable_effect=mde,
                    alpha=checked.alpha,
                    target_power=checked.target_power,
                    pilot_seed_count=len(plan.pilot_seeds),
                    required_test_seed_count=required,
                    planned_test_seed_count=len(plan.test_seeds),
                    status="PASS" if len(plan.test_seeds) >= required else "BLOCK",
                )
            )

        test_artifacts: dict[ProjectOneAblationArmId, ArmActionArtifact] = {}
        intervals: tuple[PairedActionInterval, ...] = ()
        if all(item.status == "PASS" for item in analyses):
            # This is intentionally below the power gate: no TEST inputs or
            # evaluator truths exist in this process before pilot power passes.
            test_suite = OnlineShiftSuiteGenerator().generate(
                OnlineShiftSuiteConfig(
                    duration_days=checked.duration_days,
                    seeds=plan.test_seeds,
                    case_id_salt="project-one-action-death-test-test@1",
                    shuffle_seed=20260823,
                )
            )
            test_by_seed = {seed: [] for seed in plan.test_seeds}
            for case in test_suite.cases:
                test_by_seed[case.evaluator_truth.scenario_seed].append(
                    OnlineShiftGeneratedCase(
                        model_input=case.model_input,
                        evaluator_truth=case.evaluator_truth.model_copy(
                            update={"split": OnlineShiftSplit.TEST}
                        ),
                    )
                )
            test = tuple(case for seed in plan.test_seeds for case in test_by_seed[seed])
            test_artifacts = {
                arm: _evaluate_arm(arm, selected[arm], test, checked.action_policy, "test")
                for arm in SHIFT_THREE_ARMS
            }
            joint_test = test_artifacts[ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD]
            intervals = tuple(
                _paired_interval(
                    joint_test,
                    test_artifacts[reference],
                    metric,
                    endpoint_id,
                    bootstrap_samples=checked.bootstrap_samples,
                )
                for reference in (
                    ProjectOneAblationArmId.ORDINARY_BOCPD,
                    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
                )
                for endpoint_id, metric in (
                    (PRIMARY_ENDPOINT_ID, "downstream_action_regret"),
                    (KEY_SECONDARY_ENDPOINT_ID, "corrupted_habit_mass"),
                )
            )

        payload = {
            "protocol_version": checked.protocol_version,
            "config": checked,
            "config_sha256": content_sha256(checked),
            "code_snapshot_sha256": code_snapshot_sha256,
            "git_commit_sha": git_commit_sha,
            "policy": checked.action_policy,
            "policy_sha256": content_sha256(checked.action_policy),
            "tuning_records": tuple(tuning),
            "pilot_artifacts": pilot_artifacts,
            "power_analyses": tuple(analyses),
            "test_artifacts": test_artifacts,
            "paired_test_intervals": intervals,
            "decision": decide_research_route(analyses, intervals, checked.action_policy),
        }
        full_payload = {
            **payload,
            "primary_endpoint_id": PRIMARY_ENDPOINT_ID,
            "key_secondary_endpoint_id": KEY_SECONDARY_ENDPOINT_ID,
            "multiple_comparisons_policy": (
                "primary-alpha-0.05-key-secondary-holm-mechanisms-descriptive@1"
            ),
            "allowed_claims": ALLOWED_CLAIM_IDS,
            "forbidden_claims": FORBIDDEN_CLAIM_IDS,
        }
        return ProjectOneShiftActionDeathTestReport(
            **full_payload,
            report_sha256=content_sha256(full_payload),
        )
