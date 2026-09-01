"""ATG-2/ATG-3 for the executable Project One SHIFT three-arm comparison.

The global 11-arm topology remains broader than this experiment: eight arms are
still adapter-unbound.  This module therefore advances only the SHIFT
comparison (ordinary / legacy independent / joint CF-BOCPD) and encodes that
scope explicitly in every report and claim policy.
"""

from __future__ import annotations

import random
import tracemalloc
from collections.abc import Callable, Sequence
from math import ceil, isfinite
from statistics import NormalDist
from time import perf_counter_ns
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt
from cpswm.system.reproducibility import canonical_json, content_sha256, content_uuid

from .fair_ablation import ProjectOneAblationArmId
from .online_shift_attribution import (
    OnlineShiftAttributionCase,
    OnlineShiftCaseTruth,
    OnlineShiftEvaluator,
    OnlineShiftGeneratedCase,
    OnlineShiftPrediction,
    OnlineShiftReport,
    OnlineShiftSplit,
    OnlineShiftSuite,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from .project_one_ablation_v0_2 import (
    ProjectOneMatchedComparisonId,
    ProjectOneProtocolPilotReportV2,
)
from .sealed_test_split import ExternalSealedTestSplit, ExternalTestUnsealGrant
from .shift_baselines import (
    OnlineBOCPDMSBaseline,
    OnlineCauseFactorizedBOCPDBaseline,
    OnlineJointCauseFactorizedBOCPDBaseline,
    OnlineOrdinaryBOCPDBaseline,
)

SHIFT_THREE_ARMS: tuple[ProjectOneAblationArmId, ...] = (
    ProjectOneAblationArmId.ORDINARY_BOCPD,
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
    ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,
)

#: Frozen three-arm scope above stays byte-identical so existing ATG2/ATG3
#: artifacts keep validating.  The four-arm scope adds the BOCPDMS matched
#: adaptation, which is the arm that can actually disconfirm the CF-BOCPD
#: cause-factorization claim.
SHIFT_FOUR_ARMS: tuple[ProjectOneAblationArmId, ...] = (
    *SHIFT_THREE_ARMS,
    ProjectOneAblationArmId.BOCPDMS_MODEL_SELECTION,
)
ATG2_SCOPE: Literal["project-one-shift-three-arm-tuning@1"] = "project-one-shift-three-arm-tuning@1"
ATG3_SCOPE: Literal["project-one-shift-three-arm-test@1"] = "project-one-shift-three-arm-test@1"

ATG3_ALLOWED_CLAIM_IDS = (
    "atg3.frozen-synthetic-shift-suite-metrics-reported@2",
    "atg3.paired-scenario-seed-trajectory-bootstrap-intervals-reported@2",
)
ATG3_FORBIDDEN_CLAIM_IDS = (
    "claim.general-method-superiority.forbidden@2",
    "claim.state-of-the-art.forbidden@2",
    "claim.formal-structure-one-b1-complete.forbidden@2",
    "claim.all-eleven-arms-experimentally-complete.forbidden@2",
)

_SEARCH_SPACES: dict[ProjectOneAblationArmId, tuple[dict[str, int | float], ...]] = {
    ProjectOneAblationArmId.ORDINARY_BOCPD: tuple(
        {
            "warmup_days": warmup,
            "hazard_probability": hazard,
            "detection_threshold": threshold,
        }
        for warmup in (1, 2)
        for hazard in (0.01, 0.05, 0.1)
        for threshold in (0.2, 0.35, 0.5)
    ),
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD: tuple(
        {
            "warmup_days": warmup,
            "hazard_probability": hazard,
            "detection_threshold": threshold,
        }
        for warmup in (1, 2)
        for hazard in (0.01, 0.05, 0.1)
        for threshold in (0.2, 0.35, 0.5)
    ),
    ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD: tuple(
        {
            "warmup_days": 2,
            "hazard_probability": hazard,
            "detection_threshold": threshold,
            "beam_width": beam,
            # Backward-compatible SHIFT arm: the pre-joint-event benchmark
            # allowed one cause per changepoint.  Carry that choice explicitly
            # now that the detector exposes multi-cause event regimes.
            "maximum_simultaneous_causes": 1,
            "simultaneous_hazard_scale": 0.25,
        }
        for hazard in (0.01, 0.05, 0.1)
        for threshold in (0.2, 0.35, 0.5)
        for beam in (12, 24)
    ),
    # Same 18-trial budget as every other arm.  The third dimension is the model
    # prior concentration -- BOCPDMS's own knob -- rather than a second copy of a
    # dimension the CF-BOCPD arms already search, so the budget buys this arm the
    # same amount of real freedom.
    ProjectOneAblationArmId.BOCPDMS_MODEL_SELECTION: tuple(
        {
            "warmup_days": 2,
            "hazard_probability": hazard,
            "detection_threshold_hazard_fraction": fraction,
            "model_switch_weight": switch,
        }
        for hazard in (0.01, 0.05, 0.1)
        for fraction in (0.05, 0.2, 0.5)
        for switch in (0.0, 0.25)
    ),
}


class MeasuredTuningBudget(ContractModel):
    maximum_trials_per_arm: PositiveInt = 18
    maximum_validation_predictions_per_arm: PositiveInt = 108
    maximum_elapsed_ns_per_arm: PositiveInt = 30_000_000_000
    maximum_peak_tracemalloc_bytes_per_arm: PositiveInt = 100_000_000
    maximum_p95_prediction_latency_ns: PositiveInt = 1_000_000_000
    maximum_hyperparameter_json_bytes_per_arm: PositiveInt = 4096
    maximum_hyperparameter_field_count_per_arm: PositiveInt = 8


class FrozenShiftSuiteConfig(ContractModel):
    """Explicit disjoint seed partitions for the authority-owned suite."""

    train_seeds: tuple[NonNegativeInt, ...] = (1103, 2207, 3301)
    validation_seeds: tuple[NonNegativeInt, ...] = (4409, 5519, 6619)
    test_seeds: tuple[NonNegativeInt, ...] = (7727, 8837, 9949)
    base: OnlineShiftSuiteConfig = Field(
        default_factory=lambda: OnlineShiftSuiteConfig(
            seeds=(1103, 2207, 3301, 4409, 5519, 6619, 7727, 8837, 9949)
        )
    )

    @model_validator(mode="after")
    def validate_seed_partitions(self) -> FrozenShiftSuiteConfig:
        partitions = (self.train_seeds, self.validation_seeds, self.test_seeds)
        if any(len(partition) < 2 for partition in partitions):
            raise ValueError("each frozen split requires at least two independent seeds")
        flattened = tuple(seed for partition in partitions for seed in partition)
        if len(flattened) != len(set(flattened)):
            raise ValueError("train/validation/TEST seeds must be globally disjoint")
        if flattened != self.base.seeds:
            raise ValueError("base generator seeds must equal the ordered explicit partitions")
        return self


class ShiftPowerAnalysis(ContractModel):
    analysis_id: Literal["paired-seed-normal-approximation@1"] = (
        "paired-seed-normal-approximation@1"
    )
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    target_power: float = Field(default=0.8, gt=0.0, lt=1.0)
    minimum_detectable_effect: float = Field(default=0.2, gt=0.0)
    assumed_paired_difference_stddev: float = Field(default=0.1, gt=0.0)
    required_independent_test_seeds: PositiveInt = 2
    planned_independent_test_seeds: PositiveInt = 3
    status: Literal["PASS"] = "PASS"
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def calculate(
        cls,
        *,
        planned_independent_test_seeds: int,
        alpha: float = 0.05,
        target_power: float = 0.8,
        minimum_detectable_effect: float = 0.2,
        assumed_paired_difference_stddev: float = 0.1,
    ) -> ShiftPowerAnalysis:
        normal = NormalDist()
        required = ceil(
            (
                (normal.inv_cdf(1.0 - alpha / 2.0) + normal.inv_cdf(target_power))
                * assumed_paired_difference_stddev
                / minimum_detectable_effect
            )
            ** 2
        )
        payload = {
            "analysis_id": "paired-seed-normal-approximation@1",
            "alpha": alpha,
            "target_power": target_power,
            "minimum_detectable_effect": minimum_detectable_effect,
            "assumed_paired_difference_stddev": assumed_paired_difference_stddev,
            "required_independent_test_seeds": max(2, required),
            "planned_independent_test_seeds": planned_independent_test_seeds,
            "status": "PASS",
        }
        return cls.model_validate({**payload, "analysis_sha256": content_sha256(payload)})

    @model_validator(mode="after")
    def validate_power(self) -> ShiftPowerAnalysis:
        normal = NormalDist()
        expected_required = max(
            2,
            ceil(
                (
                    (normal.inv_cdf(1.0 - self.alpha / 2.0) + normal.inv_cdf(self.target_power))
                    * self.assumed_paired_difference_stddev
                    / self.minimum_detectable_effect
                )
                ** 2
            ),
        )
        if self.required_independent_test_seeds != expected_required:
            raise ValueError("power-analysis required seed count is not reproducible")
        if self.planned_independent_test_seeds < self.required_independent_test_seeds:
            raise ValueError("planned TEST seeds do not satisfy frozen power analysis")
        payload = self.model_dump(mode="json", exclude={"analysis_sha256"})
        if self.analysis_sha256 != content_sha256(payload):
            raise ValueError("power-analysis hash mismatch")
        return self


def generate_frozen_shift_suite(config: FrozenShiftSuiteConfig) -> OnlineShiftSuite:
    generated = OnlineShiftSuiteGenerator().generate(config.base)
    split_by_seed = {
        **dict.fromkeys(config.train_seeds, OnlineShiftSplit.TRAIN),
        **dict.fromkeys(config.validation_seeds, OnlineShiftSplit.VALIDATION),
        **dict.fromkeys(config.test_seeds, OnlineShiftSplit.TEST),
    }
    cases = tuple(
        OnlineShiftGeneratedCase.model_validate(
            {
                **case.model_dump(mode="json"),
                "evaluator_truth": {
                    **case.evaluator_truth.model_dump(mode="json"),
                    "split": split_by_seed[case.evaluator_truth.scenario_seed],
                },
            }
        )
        for case in generated.cases
    )
    payload = {
        "generator_version": "online-shift-suite@0.2-explicit-disjoint-seeds",
        "config_sha256": content_sha256(config),
        "cases": cases,
    }
    return OnlineShiftSuite.model_validate(
        {
            **payload,
            "suite_id": content_uuid("online-shift-suite", payload),
            "suite_content_sha256": content_sha256(payload),
        }
    )


class ProjectOneShiftGateConfig(ContractModel):
    protocol_version: Literal["project-one-shift-gates@2"] = "project-one-shift-gates@2"
    base_atg1_config_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite: FrozenShiftSuiteConfig = Field(default_factory=FrozenShiftSuiteConfig)
    power_analysis: ShiftPowerAnalysis
    authority_key_id: str = Field(min_length=1)
    tuning_budget: MeasuredTuningBudget = Field(default_factory=MeasuredTuningBudget)
    bootstrap_samples: PositiveInt = 500

    @model_validator(mode="after")
    def validate_bootstrap_budget(self) -> ProjectOneShiftGateConfig:
        if self.bootstrap_samples < 100:
            raise ValueError("ATG-3 paired bootstrap requires at least 100 samples")
        if self.power_analysis.planned_independent_test_seeds != len(self.suite.test_seeds):
            raise ValueError("power analysis must bind the frozen TEST seed count")
        return self


class TuningTrialRecord(ContractModel):
    record_index: NonNegativeInt
    previous_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_id: ProjectOneAblationArmId
    tuning_run_id: UUID
    trial_id: UUID
    params: dict[str, int | float]
    params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_version: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_report: OnlineShiftReport
    elapsed_ns: PositiveInt
    peak_tracemalloc_bytes: NonNegativeInt
    p95_prediction_latency_ns: PositiveInt
    hyperparameter_json_bytes: PositiveInt
    hyperparameter_field_count: PositiveInt
    validation_prediction_count: PositiveInt
    status: Literal["COMPLETED"] = "COMPLETED"
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_hashes(self) -> TuningTrialRecord:
        if self.params_sha256 != content_sha256(self.params):
            raise ValueError("trial params hash mismatch")
        payload = self.model_dump(mode="json", exclude={"record_sha256"})
        if self.record_sha256 != content_sha256(payload):
            raise ValueError("tuning trial record hash mismatch")
        return self


class ArmMeasuredBudgetLedger(ContractModel):
    arm_id: ProjectOneAblationArmId
    tuning_run_id: UUID
    search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_version: str = Field(min_length=1)
    trials: tuple[TuningTrialRecord, ...] = Field(min_length=1)
    selected_params: dict[str, int | float]
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_elapsed_ns: PositiveInt
    total_validation_predictions: PositiveInt
    peak_tracemalloc_bytes: NonNegativeInt
    p95_prediction_latency_ns: PositiveInt
    hyperparameter_json_bytes: PositiveInt
    hyperparameter_field_count: PositiveInt
    budget: MeasuredTuningBudget
    within_budget: Literal[True] = True
    canonical_log_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_ledger(self) -> ArmMeasuredBudgetLedger:
        if self.arm_id not in SHIFT_THREE_ARMS:
            raise ValueError("ATG-2 ledger arm is outside the SHIFT three-arm scope")
        if len(self.trials) != len(_SEARCH_SPACES[self.arm_id]):
            raise ValueError("ATG-2 ledger must execute the complete declared search space")
        previous = "0" * 64
        expected_space = _SEARCH_SPACES[self.arm_id]
        if self.search_space_sha256 != content_sha256(expected_space):
            raise ValueError("ATG-2 declared search-space hash mismatch")
        for index, (trial, expected_params) in enumerate(
            zip(self.trials, expected_space, strict=True)
        ):
            checked = TuningTrialRecord.model_validate(trial.model_dump(mode="json"))
            if checked.record_index != index or checked.previous_record_sha256 != previous:
                raise ValueError("tuning trial canonical hash chain is broken")
            if checked.arm_id != self.arm_id or checked.tuning_run_id != self.tuning_run_id:
                raise ValueError("tuning trial is bound to the wrong arm or run")
            if checked.params != expected_params:
                raise ValueError("tuning trial order does not cover the declared search space")
            expected_trial_id = content_uuid(
                "project-one-shift-tuning-trial",
                {"run_id": self.tuning_run_id, "index": index, "params": expected_params},
            )
            if checked.trial_id != expected_trial_id:
                raise ValueError("tuning trial ID is not bound to run, index, and params")
            if (
                checked.model_version != self.model_version
                or checked.validation_split_sha256 != self.validation_split_sha256
            ):
                raise ValueError("tuning trial model or validation binding mismatch")
            previous = checked.record_sha256
        if self.canonical_log_head_sha256 != previous:
            raise ValueError("tuning ledger log-head hash mismatch")
        if self.selected_params_sha256 != content_sha256(self.selected_params):
            raise ValueError("selected tuning params hash mismatch")
        if self.selected_params not in [trial.params for trial in self.trials]:
            raise ValueError("selected params must come from a completed trial")
        if self.total_elapsed_ns != sum(trial.elapsed_ns for trial in self.trials):
            raise ValueError("measured tuning elapsed ledger mismatch")
        if self.total_validation_predictions != sum(
            trial.validation_prediction_count for trial in self.trials
        ):
            raise ValueError("measured tuning prediction ledger mismatch")
        if self.peak_tracemalloc_bytes != max(
            trial.peak_tracemalloc_bytes for trial in self.trials
        ):
            raise ValueError("measured tuning tracemalloc-peak ledger mismatch")
        selected_trial = next(
            trial for trial in self.trials if trial.params == self.selected_params
        )
        if (
            self.hyperparameter_json_bytes != selected_trial.hyperparameter_json_bytes
            or self.hyperparameter_field_count != selected_trial.hyperparameter_field_count
        ):
            raise ValueError("selected hyperparameter serialization ledger mismatch")
        if self.p95_prediction_latency_ns != max(
            trial.p95_prediction_latency_ns for trial in self.trials
        ):
            raise ValueError("ledger latency must conservatively bind the worst trial p95")
        if self.total_elapsed_ns > self.budget.maximum_elapsed_ns_per_arm:
            raise ValueError("ATG-2 measured elapsed budget exceeded")
        if len(self.trials) > self.budget.maximum_trials_per_arm:
            raise ValueError("ATG-2 trial budget exceeded")
        if self.total_validation_predictions > self.budget.maximum_validation_predictions_per_arm:
            raise ValueError("ATG-2 validation compute budget exceeded")
        if self.peak_tracemalloc_bytes > self.budget.maximum_peak_tracemalloc_bytes_per_arm:
            raise ValueError("ATG-2 tracemalloc-peak budget exceeded")
        if self.p95_prediction_latency_ns > self.budget.maximum_p95_prediction_latency_ns:
            raise ValueError("ATG-2 latency budget exceeded")
        if self.hyperparameter_json_bytes > self.budget.maximum_hyperparameter_json_bytes_per_arm:
            raise ValueError("ATG-2 hyperparameter JSON-byte budget exceeded")
        if self.hyperparameter_field_count > self.budget.maximum_hyperparameter_field_count_per_arm:
            raise ValueError("ATG-2 hyperparameter-field budget exceeded")
        payload = self.model_dump(mode="json", exclude={"ledger_sha256"})
        if self.ledger_sha256 != content_sha256(payload):
            raise ValueError("ATG-2 measured-budget ledger hash mismatch")
        return self


class TuningArmReceiptBinding(ContractModel):
    arm_id: ProjectOneAblationArmId
    tuning_run_id: UUID
    trial_count: PositiveInt
    search_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_params_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    measured_budget_ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_version: str = Field(min_length=1)
    completion_status: Literal["COMPLETED_WITHIN_BUDGET"]
    canonical_log_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShiftTuningCompletionReceipt(ContractModel):
    receipt_scope: Literal["project-one-shift-atg3"] = "project-one-shift-atg3"
    protocol_version: Literal["project-one-shift-gates@2"] = "project-one-shift-gates@2"
    topology_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_arm_ids: tuple[ProjectOneAblationArmId, ...]
    arm_bindings: tuple[TuningArmReceiptBinding, ...]
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completion_status: Literal["COMPLETED_WITHIN_BUDGET"]
    authority_key_id: str = Field(min_length=1)
    registration_transaction_id: UUID
    registration_global_commit_seq: PositiveInt
    registration_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_log_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ShiftTuningCompletionReceipt:
        if self.required_arm_ids != SHIFT_THREE_ARMS:
            raise ValueError("receipt must name the ordered SHIFT three-arm scope")
        if tuple(item.arm_id for item in self.arm_bindings) != SHIFT_THREE_ARMS:
            raise ValueError("receipt requires one ordered binding per SHIFT arm")
        if len({item.tuning_run_id for item in self.arm_bindings}) != 3:
            raise ValueError("receipt tuning run IDs must be independent")
        return self

    @property
    def authority_receipt_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def _validate_atg2_ledgers(
    ledgers: tuple[ArmMeasuredBudgetLedger, ...],
    *,
    validation_split_sha256: str,
) -> tuple[ArmMeasuredBudgetLedger, ...]:
    checked = tuple(
        ArmMeasuredBudgetLedger.model_validate(item.model_dump(mode="json")) for item in ledgers
    )
    if tuple(item.arm_id for item in checked) != SHIFT_THREE_ARMS:
        raise ValueError("ATG-2 requires the ordered SHIFT three-arm ledgers")
    if len({item.tuning_run_id for item in checked}) != len(SHIFT_THREE_ARMS):
        raise ValueError("ATG-2 requires independent tuning run IDs")
    if any(item.validation_split_sha256 != validation_split_sha256 for item in checked):
        raise ValueError("ATG-2 ledgers must bind the report validation split")
    return checked


class ShiftATG2Draft(ContractModel):
    """Validation-only worker output; it has no authority to unlock TEST."""

    gate_id: Literal["ATG-2-DRAFT"] = "ATG-2-DRAFT"
    scope: Literal["project-one-shift-three-arm-tuning@1"] = ATG2_SCOPE
    topology_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_accessed: Literal[False] = False
    ledgers: tuple[ArmMeasuredBudgetLedger, ...]
    worker_input_kind: Literal["validation-cases-only"] = "validation-cases-only"
    draft_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_draft(self) -> ShiftATG2Draft:
        _validate_atg2_ledgers(
            self.ledgers,
            validation_split_sha256=self.validation_split_sha256,
        )
        payload = self.model_dump(mode="json", exclude={"draft_sha256"})
        if self.draft_sha256 != content_sha256(payload):
            raise ValueError("ATG-2 validation-only draft hash mismatch")
        return self


class ShiftATG2Report(ContractModel):
    gate_id: Literal["ATG-2"] = "ATG-2"
    scope: Literal["project-one-shift-three-arm-tuning@1"] = ATG2_SCOPE
    topology_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_accessed: Literal[False] = False
    ledgers: tuple[ArmMeasuredBudgetLedger, ...]
    worker_draft_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: ShiftTuningCompletionReceipt
    gate_status: Literal["PASS"] = "PASS"
    global_eleven_arm_tuning_status: Literal["BLOCK"] = "BLOCK"

    @model_validator(mode="after")
    def validate_report(self) -> ShiftATG2Report:
        ledgers = _validate_atg2_ledgers(
            self.ledgers,
            validation_split_sha256=self.validation_split_sha256,
        )
        receipt = ShiftTuningCompletionReceipt.model_validate(self.receipt.model_dump(mode="json"))
        report_bindings = (
            receipt.topology_manifest_sha256,
            receipt.experiment_id,
            receipt.validation_split_sha256,
            receipt.test_split_sha256,
            receipt.code_snapshot_sha256,
        )
        expected_bindings = (
            self.topology_manifest_sha256,
            self.experiment_id,
            self.validation_split_sha256,
            self.test_split_sha256,
            self.code_snapshot_sha256,
        )
        if report_bindings != expected_bindings:
            raise ValueError("ATG-2 receipt report binding mismatch")
        for ledger, binding in zip(ledgers, receipt.arm_bindings, strict=True):
            expected = {
                "arm_id": ledger.arm_id,
                "tuning_run_id": ledger.tuning_run_id,
                "trial_count": len(ledger.trials),
                "search_space_sha256": ledger.search_space_sha256,
                "selected_params_sha256": ledger.selected_params_sha256,
                "measured_budget_ledger_sha256": ledger.ledger_sha256,
                "model_version": ledger.model_version,
                "completion_status": "COMPLETED_WITHIN_BUDGET",
                "canonical_log_head_sha256": ledger.canonical_log_head_sha256,
            }
            if binding.model_dump(mode="json") != TuningArmReceiptBinding.model_validate(
                expected
            ).model_dump(mode="json"):
                raise ValueError("ATG-2 receipt arm binding mismatch")
        return self


class PairedBootstrapInterval(ContractModel):
    metric_name: str = Field(min_length=1)
    candidate_arm_id: ProjectOneAblationArmId
    reference_arm_id: ProjectOneAblationArmId
    difference: float
    lower_95: float
    upper_95: float
    resampling_unit: Literal["scenario_seed_trajectory"] = "scenario_seed_trajectory"
    bootstrap_samples: PositiveInt


class TestTruthArtifact(ContractModel):
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truths: tuple[OnlineShiftCaseTruth, ...] = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_artifact(self) -> TestTruthArtifact:
        if any(item.split != OnlineShiftSplit.TEST for item in self.truths):
            raise ValueError("TEST truth artifact may contain only TEST truths")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("TEST truth artifact hash mismatch")
        return self


class ArmPredictionArtifact(ContractModel):
    arm_id: ProjectOneAblationArmId
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions: tuple[OnlineShiftPrediction, ...] = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_artifact(self) -> ArmPredictionArtifact:
        if len({item.case_id for item in self.predictions}) != len(self.predictions):
            raise ValueError("prediction artifact case IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != content_sha256(payload):
            raise ValueError("prediction artifact hash mismatch")
        return self


class GateStateCommitProof(ContractModel):
    event_type: Literal["ATG2_COMPLETED", "TEST_UNSEALED", "ATG3_COMPLETED"]
    transaction_id: UUID
    global_commit_seq: PositiveInt
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    log_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShiftATG3Report(ContractModel):
    gate_id: Literal["ATG-3"] = "ATG-3"
    scope: Literal["project-one-shift-three-arm-test@1"] = ATG3_SCOPE
    topology_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: ShiftTuningCompletionReceipt
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_case_count: PositiveInt
    power_analysis: ShiftPowerAnalysis
    test_truth_artifact: TestTruthArtifact
    prediction_artifacts_by_arm: dict[ProjectOneAblationArmId, ArmPredictionArtifact]
    selected_params_sha256_by_arm: dict[ProjectOneAblationArmId, str]
    reports_by_arm: dict[ProjectOneAblationArmId, OnlineShiftReport]
    paired_intervals: tuple[PairedBootstrapInterval, ...]
    test_unseal_commit: GateStateCommitProof
    test_unseal_audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_status: Literal["PASS"] = "PASS"
    formal_structure_one_b1_status: Literal["BLOCK"] = "BLOCK"
    global_eleven_arm_experiment_status: Literal["BLOCK"] = "BLOCK"
    allowed_claims: tuple[str, ...] = ATG3_ALLOWED_CLAIM_IDS
    forbidden_claims: tuple[str, ...] = ATG3_FORBIDDEN_CLAIM_IDS

    @model_validator(mode="after")
    def validate_report(self) -> ShiftATG3Report:
        receipt = ShiftTuningCompletionReceipt.model_validate(self.receipt.model_dump(mode="json"))
        if receipt.topology_manifest_sha256 != self.topology_manifest_sha256:
            raise ValueError("ATG-3 receipt topology binding mismatch")
        if receipt.test_split_sha256 != self.test_split_sha256:
            raise ValueError("ATG-3 receipt TEST binding mismatch")
        if self.test_unseal_commit.event_type != "TEST_UNSEALED":
            raise ValueError("ATG-3 requires a committed TEST_UNSEALED event")
        if self.test_unseal_commit.global_commit_seq <= receipt.registration_global_commit_seq:
            raise ValueError("TEST_UNSEALED must follow ATG2_COMPLETED")
        if set(self.reports_by_arm) != set(SHIFT_THREE_ARMS):
            raise ValueError("ATG-3 requires one report per SHIFT arm")
        if set(self.prediction_artifacts_by_arm) != set(SHIFT_THREE_ARMS):
            raise ValueError("ATG-3 requires one prediction artifact per SHIFT arm")
        if set(self.selected_params_sha256_by_arm) != set(SHIFT_THREE_ARMS):
            raise ValueError("ATG-3 requires frozen params for every SHIFT arm")
        if any(
            report.sample_count != self.test_case_count for report in self.reports_by_arm.values()
        ):
            raise ValueError("ATG-3 report sample counts must equal the frozen TEST count")
        if len(self.test_truth_artifact.truths) != self.test_case_count:
            raise ValueError("ATG-3 TEST truth artifact count mismatch")
        if (
            len({item.scenario_seed for item in self.test_truth_artifact.truths})
            != self.power_analysis.planned_independent_test_seeds
        ):
            raise ValueError("ATG-3 TEST truths do not satisfy the powered seed count")
        if self.test_truth_artifact.test_split_sha256 != self.test_split_sha256:
            raise ValueError("ATG-3 TEST truth artifact split binding mismatch")
        receipt_params = {
            binding.arm_id: binding.selected_params_sha256 for binding in receipt.arm_bindings
        }
        if self.selected_params_sha256_by_arm != receipt_params:
            raise ValueError("ATG-3 selected params do not match the tuning receipt")
        expected_audit = content_sha256(
            {
                "event": "TEST_UNSEALED_FOR_ATG3",
                "authority_receipt_sha256": receipt.authority_receipt_sha256,
                "test_unseal_transaction_id": str(self.test_unseal_commit.transaction_id),
                "test_unseal_log_head_sha256": self.test_unseal_commit.log_head_sha256,
                "test_split_sha256": receipt.test_split_sha256,
                "test_case_count": self.test_case_count,
                "selected_params": {
                    arm.value: self.selected_params_sha256_by_arm[arm] for arm in SHIFT_THREE_ARMS
                },
            }
        )
        if self.test_unseal_audit_sha256 != expected_audit:
            raise ValueError("ATG-3 TEST-unseal audit hash mismatch")
        if self.allowed_claims != ATG3_ALLOWED_CLAIM_IDS:
            raise ValueError("ATG-3 allowed claim IDs must equal the canonical set")
        if self.forbidden_claims != ATG3_FORBIDDEN_CLAIM_IDS:
            raise ValueError("ATG-3 forbidden claim IDs must equal the canonical set")
        truth_by_id = {item.case_id: item for item in self.test_truth_artifact.truths}
        rebound_by_arm: dict[ProjectOneAblationArmId, tuple[OnlineShiftAttributionCase, ...]] = {}
        for arm in SHIFT_THREE_ARMS:
            artifact = ArmPredictionArtifact.model_validate(
                self.prediction_artifacts_by_arm[arm].model_dump(mode="json")
            )
            if artifact.arm_id != arm or artifact.test_split_sha256 != self.test_split_sha256:
                raise ValueError("ATG-3 prediction artifact arm or split binding mismatch")
            if set(item.case_id for item in artifact.predictions) != set(truth_by_id):
                raise ValueError("ATG-3 prediction artifact case coverage mismatch")
            rebound = tuple(
                OnlineShiftAttributionCase(
                    truth=truth_by_id[prediction.case_id],
                    prediction=prediction,
                )
                for prediction in artifact.predictions
            )
            rebound_by_arm[arm] = rebound
            recomputed = OnlineShiftEvaluator().evaluate(rebound)
            if recomputed != self.reports_by_arm[arm]:
                raise ValueError("ATG-3 aggregate metrics do not recompute from artifacts")
        metrics = set(OnlineShiftReport.model_fields) - {"sample_count"}
        expected_pairs = {
            (
                metric,
                ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,
                reference,
            )
            for reference in (
                ProjectOneAblationArmId.ORDINARY_BOCPD,
                ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
            )
            for metric in metrics
        }
        actual_pairs = {
            (item.metric_name, item.candidate_arm_id, item.reference_arm_id)
            for item in self.paired_intervals
        }
        if actual_pairs != expected_pairs or len(self.paired_intervals) != len(expected_pairs):
            raise ValueError("ATG-3 paired intervals are incomplete or duplicated")
        if any(
            not all(isfinite(value) for value in (item.difference, item.lower_95, item.upper_95))
            or item.lower_95 > item.upper_95
            or item.bootstrap_samples < 100
            for item in self.paired_intervals
        ):
            raise ValueError("ATG-3 paired interval values are invalid")
        bootstrap_samples = self.paired_intervals[0].bootstrap_samples
        if any(item.bootstrap_samples != bootstrap_samples for item in self.paired_intervals):
            raise ValueError("ATG-3 paired intervals use inconsistent sample counts")
        recomputed_intervals = ProjectOneShiftGateRunner._paired_intervals(
            rebound_by_arm,
            bootstrap_samples=bootstrap_samples,
        )
        if tuple(item.model_dump(mode="json") for item in recomputed_intervals) != tuple(
            item.model_dump(mode="json") for item in self.paired_intervals
        ):
            raise ValueError("ATG-3 paired intervals do not recompute from artifacts")
        return self


class ProjectOneShiftGateReport(ContractModel):
    """One self-validating snapshot joining ATG-1 evidence to ATG-2/ATG-3."""

    protocol_version: Literal["project-one-shift-gates@2"] = "project-one-shift-gates@2"
    frozen_suite_config: FrozenShiftSuiteConfig
    atg1_topology_report: ProjectOneProtocolPilotReportV2
    atg2: ShiftATG2Report
    atg3: ShiftATG3Report
    atg3_completion_commit: GateStateCommitProof
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_gate_chain(self) -> ProjectOneShiftGateReport:
        topology = ProjectOneProtocolPilotReportV2.model_validate(
            self.atg1_topology_report.model_dump(mode="json")
        )
        tuning = ShiftATG2Report.model_validate(self.atg2.model_dump(mode="json"))
        test = ShiftATG3Report.model_validate(self.atg3.model_dump(mode="json"))
        truth_seeds = {item.scenario_seed for item in test.test_truth_artifact.truths}
        if truth_seeds != set(self.frozen_suite_config.test_seeds):
            raise ValueError("ATG-3 truth artifact does not bind the frozen TEST seeds")
        if not (
            topology.manifest_sha256
            == tuning.topology_manifest_sha256
            == test.topology_manifest_sha256
        ):
            raise ValueError("ATG-1/ATG-2/ATG-3 topology hash chain mismatch")
        if tuning.receipt != test.receipt:
            raise ValueError("ATG-2 receipt and ATG-3 unlock receipt differ")
        if self.atg3_completion_commit.event_type != "ATG3_COMPLETED":
            raise ValueError("combined report requires committed ATG3_COMPLETED state")
        if (
            self.atg3_completion_commit.global_commit_seq
            <= test.test_unseal_commit.global_commit_seq
        ):
            raise ValueError("ATG3_COMPLETED must follow TEST_UNSEALED")
        payload = self.model_dump(mode="json", exclude={"report_sha256"})
        if self.report_sha256 != content_sha256(payload):
            raise ValueError("Project One SHIFT gate report hash mismatch")
        return self


def _model_factory(arm_id: ProjectOneAblationArmId, params: dict[str, int | float]) -> object:
    factories: dict[ProjectOneAblationArmId, Callable[..., object]] = {
        ProjectOneAblationArmId.ORDINARY_BOCPD: OnlineOrdinaryBOCPDBaseline,
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD: (OnlineCauseFactorizedBOCPDBaseline),
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD: (
            OnlineJointCauseFactorizedBOCPDBaseline
        ),
        ProjectOneAblationArmId.BOCPDMS_MODEL_SELECTION: OnlineBOCPDMSBaseline,
    }
    return factories[arm_id](**params)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, ceil(fraction * len(ordered)) - 1))]


def _evaluate_model(
    model: object, cases: Sequence[OnlineShiftGeneratedCase]
) -> tuple[OnlineShiftReport, tuple[OnlineShiftAttributionCase, ...], tuple[int, ...]]:
    bound = []
    latencies = []
    for case in cases:
        started = perf_counter_ns()
        prediction = model.predict(case.model_input)  # type: ignore[attr-defined]
        latencies.append(max(1, perf_counter_ns() - started))
        bound.append(OnlineShiftAttributionCase(truth=case.evaluator_truth, prediction=prediction))
    bound_cases = tuple(bound)
    return OnlineShiftEvaluator().evaluate(bound_cases), bound_cases, tuple(latencies)


def _selection_key(trial: TuningTrialRecord) -> tuple[float, ...]:
    report = trial.validation_report
    return (
        report.cause_micro_f1,
        report.exact_cause_set_accuracy,
        -report.false_owner_habit_change_rate,
        -report.cause_brier_score,
        -report.cause_negative_log_likelihood,
    )


class ProjectOneShiftGateRunner:
    """Sequential state machine: ATG-2 tunes, then its receipt unlocks ATG-3."""

    def __init__(self) -> None:
        self._test_unsealed = False

    def run_atg2(
        self,
        topology_report: ProjectOneProtocolPilotReportV2,
        validation_cases: Sequence[OnlineShiftGeneratedCase],
        *,
        code_snapshot_sha256: str,
        budget: MeasuredTuningBudget | None = None,
    ) -> ShiftATG2Draft:
        if self._test_unsealed:
            raise RuntimeError("ATG-2 retuning is forbidden after TEST has been unsealed")
        topology = ProjectOneProtocolPilotReportV2.model_validate(
            topology_report.model_dump(mode="json")
        )
        if not validation_cases or any(
            case.evaluator_truth.split != OnlineShiftSplit.VALIDATION for case in validation_cases
        ):
            raise ValueError("ATG-2 may receive only non-empty VALIDATION cases")
        validation_hash = content_sha256(tuple(validation_cases))
        if validation_hash != topology.manifest.validation_split_sha256:
            raise ValueError("ATG-2 validation cases do not match the frozen split")
        measured_budget = budget or MeasuredTuningBudget()
        shift_comparison = next(
            item
            for item in topology.manifest.comparisons
            if item.comparison_id == ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION
        )
        manifest_arms = {
            ProjectOneAblationArmId(item.arm_id): item for item in shift_comparison.manifest.arms
        }
        ledgers = tuple(
            self._tune_arm(
                arm_id,
                manifest_arms[arm_id].independent_tuning_run_id,
                validation_cases,
                validation_hash,
                measured_budget,
            )
            for arm_id in SHIFT_THREE_ARMS
        )
        draft_payload = {
            "topology_manifest_sha256": topology.manifest_sha256,
            "experiment_id": topology.manifest.experiment_id,
            "validation_split_sha256": validation_hash,
            "test_split_sha256": topology.manifest.test_split_sha256,
            "code_snapshot_sha256": code_snapshot_sha256,
            "ledgers": ledgers,
        }
        return ShiftATG2Draft.model_validate(
            {
                **draft_payload,
                "draft_sha256": content_sha256(
                    {
                        "gate_id": "ATG-2-DRAFT",
                        "scope": ATG2_SCOPE,
                        **draft_payload,
                        "test_split_accessed": False,
                        "worker_input_kind": "validation-cases-only",
                    }
                ),
            }
        )

    def _tune_arm(
        self,
        arm_id: ProjectOneAblationArmId,
        tuning_run_id: UUID,
        validation_cases: Sequence[OnlineShiftGeneratedCase],
        validation_hash: str,
        budget: MeasuredTuningBudget,
    ) -> ArmMeasuredBudgetLedger:
        records = []
        previous = "0" * 64
        for index, params in enumerate(_SEARCH_SPACES[arm_id]):
            tracemalloc.start()
            started = perf_counter_ns()
            model = _model_factory(arm_id, params)
            report, _bound, latencies = _evaluate_model(model, validation_cases)
            elapsed = max(1, perf_counter_ns() - started)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            params_hash = content_sha256(params)
            payload = {
                "record_index": index,
                "previous_record_sha256": previous,
                "arm_id": arm_id,
                "tuning_run_id": tuning_run_id,
                "trial_id": content_uuid(
                    "project-one-shift-tuning-trial",
                    {"run_id": tuning_run_id, "index": index, "params": params},
                ),
                "params": params,
                "params_sha256": params_hash,
                "model_version": model.model_version,  # type: ignore[attr-defined]
                "validation_split_sha256": validation_hash,
                "validation_report": report,
                "elapsed_ns": elapsed,
                "peak_tracemalloc_bytes": peak,
                "p95_prediction_latency_ns": int(_percentile(latencies, 0.95)),
                "hyperparameter_json_bytes": len(canonical_json(params).encode("utf-8")),
                "hyperparameter_field_count": len(params),
                "validation_prediction_count": len(validation_cases),
                "status": "COMPLETED",
            }
            record = TuningTrialRecord(
                **payload,
                record_sha256=content_sha256(payload),
            )
            records.append(record)
            previous = record.record_sha256
        selected = max(records, key=lambda item: (_selection_key(item), item.params_sha256))
        ledger_payload = {
            "arm_id": arm_id,
            "tuning_run_id": tuning_run_id,
            "search_space_sha256": content_sha256(_SEARCH_SPACES[arm_id]),
            "validation_split_sha256": validation_hash,
            "model_version": selected.model_version,
            "trials": tuple(records),
            "selected_params": selected.params,
            "selected_params_sha256": selected.params_sha256,
            "total_elapsed_ns": sum(item.elapsed_ns for item in records),
            "total_validation_predictions": sum(
                item.validation_prediction_count for item in records
            ),
            "peak_tracemalloc_bytes": max(item.peak_tracemalloc_bytes for item in records),
            "p95_prediction_latency_ns": max(item.p95_prediction_latency_ns for item in records),
            "hyperparameter_json_bytes": selected.hyperparameter_json_bytes,
            "hyperparameter_field_count": selected.hyperparameter_field_count,
            "budget": budget,
            "within_budget": True,
            "canonical_log_head_sha256": previous,
        }
        return ArmMeasuredBudgetLedger.model_validate(
            {
                **ledger_payload,
                "ledger_sha256": content_sha256(ledger_payload),
            }
        )

    def run_atg3(
        self,
        topology_report: ProjectOneProtocolPilotReportV2,
        atg2_report: ShiftATG2Report,
        sealed_test: ExternalSealedTestSplit[OnlineShiftGeneratedCase],
        *,
        authority: object,
        unseal_grant: ExternalTestUnsealGrant,
        expected_code_snapshot_sha256: str,
        power_analysis: ShiftPowerAnalysis,
        bootstrap_samples: int = 500,
    ) -> ShiftATG3Report:
        topology = ProjectOneProtocolPilotReportV2.model_validate(
            topology_report.model_dump(mode="json")
        )
        tuning = ShiftATG2Report.model_validate(atg2_report.model_dump(mode="json"))
        receipt = tuning.receipt
        if self._test_unsealed:
            raise RuntimeError("ATG-3 TEST may be unsealed only once per runner")
        if tuning.topology_manifest_sha256 != topology.manifest_sha256:
            raise ValueError("ATG-3 tuning report is bound to a different topology")
        if receipt.code_snapshot_sha256 != expected_code_snapshot_sha256:
            raise ValueError("ATG-3 code snapshot does not match the tuning receipt")
        if not sealed_test.formal_isolation:
            raise ValueError("ATG-3 requires external TEST process isolation")
        if sealed_test.test_split_sha256 != topology.manifest.test_split_sha256:
            raise ValueError("ATG-3 sealed TEST hash does not match topology")
        if unseal_grant.authority_receipt_sha256 != receipt.authority_receipt_sha256:
            raise ValueError("external unseal grant does not bind the ATG-2 authority receipt")
        if not hasattr(authority, "authorize_test_unseal"):
            raise ValueError("ATG-3 requires an independent gate-state authority")
        unseal_commit = GateStateCommitProof.model_validate(
            authority.authorize_test_unseal(
                tuning,
                experiment_id=receipt.experiment_id,
                validation_split_sha256=receipt.validation_split_sha256,
                test_split_sha256=receipt.test_split_sha256,
            )
        )
        test_cases = sealed_test.unseal(unseal_grant)
        self._test_unsealed = True
        if content_sha256(test_cases) != topology.manifest.test_split_sha256:
            raise ValueError("ATG-3 unsealed TEST content hash mismatch")
        ledgers = {item.arm_id: item for item in tuning.ledgers}
        reports = {}
        bound_by_arm = {}
        for arm_id in SHIFT_THREE_ARMS:
            model = _model_factory(arm_id, ledgers[arm_id].selected_params)
            report, bound, _latencies = _evaluate_model(model, test_cases)
            reports[arm_id] = report
            bound_by_arm[arm_id] = bound
        intervals = self._paired_intervals(
            bound_by_arm,
            bootstrap_samples=bootstrap_samples,
        )
        unseal_audit = content_sha256(
            {
                "event": "TEST_UNSEALED_FOR_ATG3",
                "authority_receipt_sha256": receipt.authority_receipt_sha256,
                "test_unseal_transaction_id": str(unseal_commit.transaction_id),
                "test_unseal_log_head_sha256": unseal_commit.log_head_sha256,
                "test_split_sha256": receipt.test_split_sha256,
                "test_case_count": len(test_cases),
                "selected_params": {
                    arm.value: ledgers[arm].selected_params_sha256 for arm in SHIFT_THREE_ARMS
                },
            }
        )
        truth_payload = {
            "test_split_sha256": topology.manifest.test_split_sha256,
            "truths": tuple(case.evaluator_truth for case in test_cases),
        }
        truth_artifact = TestTruthArtifact.model_validate(
            {
                **truth_payload,
                "artifact_sha256": content_sha256(truth_payload),
            }
        )
        prediction_artifacts = {}
        for arm, bound in bound_by_arm.items():
            artifact_payload = {
                "arm_id": arm,
                "test_split_sha256": topology.manifest.test_split_sha256,
                "predictions": tuple(item.prediction for item in bound),
            }
            prediction_artifacts[arm] = ArmPredictionArtifact.model_validate(
                {
                    **artifact_payload,
                    "artifact_sha256": content_sha256(artifact_payload),
                }
            )
        return ShiftATG3Report(
            topology_manifest_sha256=topology.manifest_sha256,
            receipt=receipt,
            test_split_sha256=topology.manifest.test_split_sha256,
            test_case_count=len(test_cases),
            power_analysis=power_analysis,
            test_truth_artifact=truth_artifact,
            prediction_artifacts_by_arm=prediction_artifacts,
            selected_params_sha256_by_arm={
                arm: ledgers[arm].selected_params_sha256 for arm in SHIFT_THREE_ARMS
            },
            reports_by_arm=reports,
            paired_intervals=intervals,
            test_unseal_commit=unseal_commit,
            test_unseal_audit_sha256=unseal_audit,
        )

    @staticmethod
    def _paired_intervals(
        bound_by_arm: dict[ProjectOneAblationArmId, tuple[OnlineShiftAttributionCase, ...]],
        *,
        bootstrap_samples: int,
    ) -> tuple[PairedBootstrapInterval, ...]:
        if bootstrap_samples < 100:
            raise ValueError("paired bootstrap requires at least 100 samples")
        reference_pairs = (
            (
                ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,
                ProjectOneAblationArmId.ORDINARY_BOCPD,
            ),
            (
                ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,
                ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
            ),
        )
        metrics = tuple(OnlineShiftReport.model_fields)
        cases_by_seed_by_arm = {
            arm: {
                seed: tuple(case for case in cases if case.truth.scenario_seed == seed)
                for seed in sorted({case.truth.scenario_seed for case in cases})
            }
            for arm, cases in bound_by_arm.items()
        }
        seeds = tuple(cases_by_seed_by_arm[SHIFT_THREE_ARMS[0]])
        rng = random.Random(20260822)
        output = []
        evaluator = OnlineShiftEvaluator()
        for candidate, reference in reference_pairs:
            candidate_report = evaluator.evaluate(bound_by_arm[candidate])
            reference_report = evaluator.evaluate(bound_by_arm[reference])
            draws: dict[str, list[float]] = {metric: [] for metric in metrics}
            for _ in range(bootstrap_samples):
                sampled = tuple(rng.choice(seeds) for _seed in seeds)
                candidate_cases = tuple(
                    case for seed in sampled for case in cases_by_seed_by_arm[candidate][seed]
                )
                reference_cases = tuple(
                    case for seed in sampled for case in cases_by_seed_by_arm[reference][seed]
                )
                candidate_draw = evaluator.evaluate(candidate_cases)
                reference_draw = evaluator.evaluate(reference_cases)
                for metric in metrics:
                    if metric == "sample_count":
                        continue
                    draws[metric].append(
                        float(getattr(candidate_draw, metric))
                        - float(getattr(reference_draw, metric))
                    )
            for metric in metrics:
                if metric == "sample_count":
                    continue
                values = draws[metric]
                output.append(
                    PairedBootstrapInterval(
                        metric_name=metric,
                        candidate_arm_id=candidate,
                        reference_arm_id=reference,
                        difference=float(getattr(candidate_report, metric))
                        - float(getattr(reference_report, metric)),
                        lower_95=_percentile(values, 0.025),
                        upper_95=_percentile(values, 0.975),
                        bootstrap_samples=bootstrap_samples,
                    )
                )
        return tuple(output)
