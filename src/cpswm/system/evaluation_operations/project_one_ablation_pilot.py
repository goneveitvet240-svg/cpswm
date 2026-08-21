"""Protocol-only pilot for the five matched Project One ablations.

The pilot validates experiment topology, split identities, matched budgets, and
adapter coverage.  It deliberately does not convert unbound task adapters into
synthetic scores or claim that independent tuning has taken place.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, PositiveInt
from cpswm.system.reproducibility import content_sha256, content_uuid

from .fair_ablation import (
    PROJECT_ONE_ARMS_V01,
    FairAblationArm,
    FairAblationManifest,
    ModelBudget,
    ObservationBudget,
    ProjectOneAblationArmId,
    TuningBudget,
)
from .online_shift_attribution import (
    OnlineShiftAttributionCase,
    OnlineShiftEvaluator,
    OnlineShiftGeneratedCase,
    OnlineShiftReport,
    OnlineShiftSplit,
    OnlineShiftSuite,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from .shift_baselines import (
    OnlineCauseFactorizedBOCPDBaseline,
    OnlineOrdinaryBOCPDBaseline,
)

#: The exact v0.1 protocol version string; v0.1 classes accept only this.
PROJECT_ONE_PILOT_PROTOCOL_V01 = "project-one-ablation-protocol-pilot@0.1"


class ProjectOneMatchedComparisonId(StrEnum):
    HABIT_OBSERVATION_CORRECTION = "habit-observation-correction"
    HABIT_ACTOR_CONTAMINATION = "habit-actor-contamination"
    SHIFT_CAUSE_FACTORIZATION = "shift-cause-factorization"
    CHEH_SOURCE_ALIGNMENT = "cheh-source-alignment"
    VERIFICATION_DECISION_OBJECTIVE = "verification-decision-objective"


_COMPARISON_ARMS = {
    ProjectOneMatchedComparisonId.HABIT_OBSERVATION_CORRECTION: (
        ProjectOneAblationArmId.HABIT_BASELINE,
        ProjectOneAblationArmId.HABIT_OBSERVATION_CORRECTED,
    ),
    ProjectOneMatchedComparisonId.HABIT_ACTOR_CONTAMINATION: (
        ProjectOneAblationArmId.HABIT_VISITOR_ISOLATED,
        ProjectOneAblationArmId.HABIT_ACTOR_RESIDUAL,
    ),
    ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION: (
        ProjectOneAblationArmId.ORDINARY_BOCPD,
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
    ),
    ProjectOneMatchedComparisonId.CHEH_SOURCE_ALIGNMENT: (
        ProjectOneAblationArmId.CHEH_INTERNAL_CONSISTENCY,
        ProjectOneAblationArmId.CHEH_SOURCE_ALIGNED,
    ),
    ProjectOneMatchedComparisonId.VERIFICATION_DECISION_OBJECTIVE: (
        ProjectOneAblationArmId.THRESHOLD_VERIFICATION,
        ProjectOneAblationArmId.UTILITY_VERIFICATION,
    ),
}

_TASK_ADAPTER_IDS = {
    ProjectOneMatchedComparisonId.HABIT_OBSERVATION_CORRECTION: "habit-observation-stream@unbound",
    ProjectOneMatchedComparisonId.HABIT_ACTOR_CONTAMINATION: "habit-actor-stream@unbound",
    ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION: "online-shift-attribution@0.1",
    ProjectOneMatchedComparisonId.CHEH_SOURCE_ALIGNMENT: "hidden-event-provenance@unbound",
    ProjectOneMatchedComparisonId.VERIFICATION_DECISION_OBJECTIVE: (
        "grounded-verification-utility@unbound"
    ),
}


class ProtocolPilotTuningBudget(ContractModel):
    maximum_trials: PositiveInt
    maximum_compute_units: float = Field(gt=0.0)
    objective_name: str = Field(min_length=1)


class ProjectOneComparisonPilotBudget(ContractModel):
    budget_scope: Literal["protocol_placeholder"] = "protocol_placeholder"
    observation_budget: ObservationBudget
    model_budget: ModelBudget
    tuning_budget: ProtocolPilotTuningBudget


class ProjectOneProtocolPilotConfig(ContractModel):
    # Frozen v0.1: this class accepts only the exact @0.1 protocol version.
    protocol_version: Literal["project-one-ablation-protocol-pilot@0.1"] = (
        "project-one-ablation-protocol-pilot@0.1"
    )
    online_shift_suite: OnlineShiftSuiteConfig = Field(default_factory=OnlineShiftSuiteConfig)
    comparison_budgets: dict[ProjectOneMatchedComparisonId, ProjectOneComparisonPilotBudget]

    @model_validator(mode="after")
    def require_all_comparison_budgets(self) -> ProjectOneProtocolPilotConfig:
        declared = set(self.comparison_budgets)
        required = set(ProjectOneMatchedComparisonId)
        if declared != required:
            missing = sorted(item.value for item in required - declared)
            extra = sorted(str(item) for item in declared - required)
            raise ValueError(f"pilot comparison budgets mismatch; missing={missing}, extra={extra}")
        return self


class ProjectOneProtocolComparison(ContractModel):
    comparison_id: ProjectOneMatchedComparisonId
    task_adapter_id: str = Field(min_length=1)
    manifest: FairAblationManifest

    @model_validator(mode="after")
    def validate_pair_topology(self) -> ProjectOneProtocolComparison:
        expected = _COMPARISON_ARMS[self.comparison_id]
        actual = tuple(ProjectOneAblationArmId(arm.arm_id) for arm in self.manifest.arms)
        if actual != expected:
            raise ValueError(
                f"{self.comparison_id.value} requires ordered arms "
                f"{tuple(item.value for item in expected)}"
            )
        if self.manifest.baseline_arm_id != expected[0].value:
            raise ValueError("matched comparison must identify its control arm as baseline")
        if self.task_adapter_id != _TASK_ADAPTER_IDS[self.comparison_id]:
            raise ValueError("matched comparison task adapter does not match protocol")
        return self


class ProjectOneProtocolPilotManifest(ContractModel):
    experiment_id: str = Field(min_length=1)
    # Frozen v0.1: a v0.1 manifest carries only the @0.1 protocol version.
    protocol_version: Literal["project-one-ablation-protocol-pilot@0.1"]
    claim_scope: Literal["protocol_only"] = "protocol_only"
    online_shift_suite_id: str = Field(min_length=1)
    online_shift_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparisons: tuple[ProjectOneProtocolComparison, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_complete_topology(self) -> ProjectOneProtocolPilotManifest:
        comparison_ids = [item.comparison_id for item in self.comparisons]
        if len(comparison_ids) != len(set(comparison_ids)):
            raise ValueError("pilot comparison IDs must be unique")
        if set(comparison_ids) != set(ProjectOneMatchedComparisonId):
            raise ValueError("pilot must contain all five matched comparisons")
        arms = [arm.arm_id for comparison in self.comparisons for arm in comparison.manifest.arms]
        expected = set(PROJECT_ONE_ARMS_V01)
        if set(arms) != expected or any(count != 1 for count in Counter(arms).values()):
            raise ValueError("pilot must cover every v0.1 Project One arm exactly once")
        return self


class PilotAdapterStatus(StrEnum):
    EXECUTED = "executed"
    ADAPTER_UNBOUND = "adapter_unbound"
    #: B1 pure-topology: the arm is wired but nothing is run or loaded.
    TOPOLOGY_ONLY = "topology_only"


class PilotTuningStatus(StrEnum):
    NOT_RUN = "not_run"


class ProjectOnePilotArmResult(ContractModel):
    comparison_id: ProjectOneMatchedComparisonId
    arm_id: ProjectOneAblationArmId
    adapter_status: PilotAdapterStatus
    tuning_status: PilotTuningStatus = PilotTuningStatus.NOT_RUN
    model_version: str | None = None
    evaluation_split: OnlineShiftSplit | None = None
    online_shift_report: OnlineShiftReport | None = None
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result_scope(self) -> ProjectOnePilotArmResult:
        if self.adapter_status == PilotAdapterStatus.EXECUTED:
            if (
                self.model_version is None
                or self.evaluation_split is None
                or self.online_shift_report is None
            ):
                raise ValueError("executed pilot arms require a bound report and model")
        elif any(
            value is not None
            for value in (
                self.model_version,
                self.evaluation_split,
                self.online_shift_report,
            )
        ):
            raise ValueError("unbound pilot arms cannot publish evaluation results")
        return self


class ProjectOneProtocolPilotReport(ContractModel):
    manifest: ProjectOneProtocolPilotManifest
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_case_count: PositiveInt
    split_case_counts: dict[OnlineShiftSplit, int]
    arm_results: tuple[ProjectOnePilotArmResult, ...] = Field(min_length=10, max_length=10)
    protocol_contracts_valid: Literal[True] = True
    all_adapters_bound: bool
    formal_experiment_ready: Literal[False] = False
    claim_scope: Literal["protocol_only"] = "protocol_only"
    caveats: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_report(self) -> ProjectOneProtocolPilotReport:
        if self.manifest_sha256 != content_sha256(self.manifest):
            raise ValueError("pilot manifest hash mismatch")
        if sum(self.split_case_counts.values()) != self.suite_case_count:
            raise ValueError("pilot split counts do not cover the suite")
        if set(self.split_case_counts) != set(OnlineShiftSplit):
            raise ValueError("pilot report must identify all suite splits")
        result_arms = [result.arm_id for result in self.arm_results]
        if {arm.value for arm in result_arms} != PROJECT_ONE_ARMS_V01 or len(result_arms) != len(
            set(result_arms)
        ):
            raise ValueError("pilot report must contain one result per v0.1 arm")
        computed_all_bound = all(
            result.adapter_status == PilotAdapterStatus.EXECUTED for result in self.arm_results
        )
        if self.all_adapters_bound != computed_all_bound:
            raise ValueError("all_adapters_bound disagrees with arm results")
        return self


class ProjectOneProtocolPilotRunner:
    """Run available adapters while preserving explicit gaps for the others."""

    def run(self, config: ProjectOneProtocolPilotConfig) -> ProjectOneProtocolPilotReport:
        suite = OnlineShiftSuiteGenerator().generate(config.online_shift_suite)
        manifest = self._manifest(config, suite)
        test_cases = tuple(
            case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
        )
        arm_results = tuple(
            self._arm_result(
                comparison.comparison_id, ProjectOneAblationArmId(arm.arm_id), test_cases
            )
            for comparison in manifest.comparisons
            for arm in comparison.manifest.arms
        )
        split_counts = Counter(case.evaluator_truth.split for case in suite.cases)
        return ProjectOneProtocolPilotReport(
            manifest=manifest,
            manifest_sha256=content_sha256(manifest),
            suite_case_count=len(suite.cases),
            split_case_counts={split: split_counts[split] for split in OnlineShiftSplit},
            arm_results=arm_results,
            all_adapters_bound=all(
                result.adapter_status == PilotAdapterStatus.EXECUTED for result in arm_results
            ),
            caveats=(
                "This dry run validates protocol wiring, not comparative method efficacy.",
                "Independent hyperparameter tuning was not run.",
                "Only the two BOCPD arms have online-shift task adapters.",
                "Unbound arms publish no synthetic or proxy scores.",
            ),
        )

    @staticmethod
    def _manifest(
        config: ProjectOneProtocolPilotConfig, suite: OnlineShiftSuite
    ) -> ProjectOneProtocolPilotManifest:
        validation_cases = tuple(
            case
            for case in suite.cases
            if case.evaluator_truth.split == OnlineShiftSplit.VALIDATION
        )
        test_cases = tuple(
            case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
        )
        validation_sha256 = content_sha256(validation_cases)
        test_sha256 = content_sha256(test_cases)
        trace_sha256 = content_sha256(tuple(case.model_input for case in suite.cases))
        experiment_payload = {
            "protocol_version": config.protocol_version,
            "suite_id": suite.suite_id,
            "suite_sha256": suite.suite_content_sha256,
            "config": config,
        }
        experiment_id = str(content_uuid("project-one-protocol-pilot", experiment_payload))
        comparisons = []
        for comparison_id in ProjectOneMatchedComparisonId:
            budget = config.comparison_budgets[comparison_id]
            arm_ids = _COMPARISON_ARMS[comparison_id]
            arms = tuple(
                FairAblationArm(
                    arm_id=arm_id.value,
                    model_version=ProjectOneProtocolPilotRunner._model_version(arm_id),
                    components=(arm_id.value, _TASK_ADAPTER_IDS[comparison_id]),
                    observation_budget=budget.observation_budget,
                    model_budget=budget.model_budget,
                    tuning_budget=TuningBudget(
                        maximum_trials=budget.tuning_budget.maximum_trials,
                        maximum_compute_units=budget.tuning_budget.maximum_compute_units,
                        validation_split_sha256=validation_sha256,
                        objective_name=budget.tuning_budget.objective_name,
                    ),
                    independent_tuning_run_id=content_uuid(
                        "project-one-protocol-pilot-tuning-run",
                        {
                            "experiment_id": experiment_id,
                            "comparison_id": comparison_id,
                            "arm_id": arm_id,
                        },
                    ),
                    observation_trace_sha256=trace_sha256,
                    test_split_sha256=test_sha256,
                )
                for arm_id in arm_ids
            )
            comparison_manifest = FairAblationManifest(
                experiment_id=content_uuid(
                    "project-one-protocol-pilot-comparison",
                    {"experiment_id": experiment_id, "comparison_id": comparison_id},
                ),
                baseline_arm_id=arm_ids[0].value,
                arms=arms,
            )
            comparisons.append(
                ProjectOneProtocolComparison(
                    comparison_id=comparison_id,
                    task_adapter_id=_TASK_ADAPTER_IDS[comparison_id],
                    manifest=comparison_manifest,
                )
            )
        return ProjectOneProtocolPilotManifest(
            experiment_id=experiment_id,
            protocol_version=config.protocol_version,
            online_shift_suite_id=str(suite.suite_id),
            online_shift_suite_sha256=suite.suite_content_sha256,
            validation_split_sha256=validation_sha256,
            test_split_sha256=test_sha256,
            observation_trace_sha256=trace_sha256,
            comparisons=tuple(comparisons),
        )

    @staticmethod
    def _model_version(arm_id: ProjectOneAblationArmId) -> str:
        if arm_id == ProjectOneAblationArmId.ORDINARY_BOCPD:
            return OnlineOrdinaryBOCPDBaseline.model_version
        if arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD:
            return OnlineCauseFactorizedBOCPDBaseline.model_version
        return f"{arm_id.value}@adapter-unbound"

    @staticmethod
    def _arm_result(
        comparison_id: ProjectOneMatchedComparisonId,
        arm_id: ProjectOneAblationArmId,
        test_cases: tuple[OnlineShiftGeneratedCase, ...],
    ) -> ProjectOnePilotArmResult:
        models = {
            ProjectOneAblationArmId.ORDINARY_BOCPD: OnlineOrdinaryBOCPDBaseline,
            ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD: OnlineCauseFactorizedBOCPDBaseline,
        }
        model_factory = models.get(arm_id)
        if model_factory is None:
            return ProjectOnePilotArmResult(
                comparison_id=comparison_id,
                arm_id=arm_id,
                adapter_status=PilotAdapterStatus.ADAPTER_UNBOUND,
                note="No task-valid protocol pilot adapter is bound for this arm.",
            )
        model = model_factory()
        bound = tuple(
            OnlineShiftAttributionCase(
                truth=case.evaluator_truth,
                prediction=model.predict(case.model_input),
            )
            for case in test_cases
        )
        report = OnlineShiftEvaluator().evaluate(bound)
        return ProjectOnePilotArmResult(
            comparison_id=comparison_id,
            arm_id=arm_id,
            adapter_status=PilotAdapterStatus.EXECUTED,
            model_version=model.model_version,
            evaluation_split=OnlineShiftSplit.TEST,
            online_shift_report=report,
            note="Executed as an adapter smoke test without hyperparameter tuning.",
        )
