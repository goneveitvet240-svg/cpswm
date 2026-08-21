"""Project One ablation protocol v0.2: an 11-arm topology adding joint CF-BOCPD.

ATG-1 (Ablation Topology Gate 1) scope is *topology only*.  This module wires
``joint-cause-factorized-bocpd``
as the 11th arm and turns the shift comparison into three arms
(ordinary / legacy independent / joint), but runs no model, loads no TEST data,
does no tuning, and reports ``formal_experiment_ready=False`` /
``claim_scope=ablation_topology_only``.

ATG-1 is intentionally not called "B1": formal Structure One B1 means the
M05--M12 perception stage and remains blocked.  The later ablation gates for
independent tuning/measured budgets and compliant TEST unsealing also remain
blocked.

The v0.2 classes deliberately do **not** inherit the v0.1 pilot classes, so no
v0.1 version validator runs on v0.2 content.  They inherit ``ContractModel`` and
declare fields explicitly; only :class:`ProjectOneFairAblationManifestV2` reuses
the version-neutral :class:`FairAblationManifest`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, PositiveInt
from cpswm.system.reproducibility import content_sha256, content_uuid

from .fair_ablation import (
    PROJECT_ONE_ARMS_V02,
    FairAblationArm,
    FairAblationManifest,
    ModelBudget,
    ObservationBudget,
    ProjectOneAblationArmId,
    TuningBudget,
)
from .sealed_test_split import (
    SealedSplitMetadata,
    split_artifact_manifest_sha256,
)

PROJECT_ONE_PILOT_PROTOCOL_V02: Literal["project-one-ablation-protocol-pilot@0.2"] = (
    "project-one-ablation-protocol-pilot@0.2"
)
PROJECT_ONE_ABLATION_TOPOLOGY_GATE_V1: Literal["project-one-ablation-topology-gate@1"] = (
    "project-one-ablation-topology-gate@1"
)

ATG1_ARM_NOTE_ID: Literal["atg1.arm.topology-binding-validated.no-execution@1"] = (
    "atg1.arm.topology-binding-validated.no-execution@1"
)
ATG1_CAVEAT_IDS = (
    "atg1.no-model-execution-or-test-access@1",
    "formal-structure-one-b1.m05-m12-perception.blocked@1",
    "atg2.independent-tuning-and-measured-budget-ledger.blocked@1",
    "atg3.compliant-receipt-test-unseal.blocked@1",
    "joint-cf-bocpd.topology-only-unbound@1",
)
ATG1_ALLOWED_CLAIMS = (
    "all-eleven-arms-have-validated-topology-bindings",
    "joint-cf-bocpd-is-wired-as-the-eleventh-arm",
)
ATG1_FORBIDDEN_CLAIMS = (
    "formal-structure-one-b1-complete",
    "test-executed",
    "comparative-performance-measured",
    "joint-cf-bocpd-superior",
    "state-of-the-art",
)


class ProjectOneMatchedComparisonId(StrEnum):
    HABIT_OBSERVATION_CORRECTION = "habit-observation-correction"
    HABIT_ACTOR_CONTAMINATION = "habit-actor-contamination"
    SHIFT_CAUSE_FACTORIZATION = "shift-cause-factorization"
    CHEH_SOURCE_ALIGNMENT = "cheh-source-alignment"
    VERIFICATION_DECISION_OBJECTIVE = "verification-decision-objective"


class PilotAdapterStatusV2(StrEnum):
    TOPOLOGY_ONLY = "topology_only"


class PilotTuningStatusV2(StrEnum):
    NOT_RUN = "not_run"


class ProtocolPilotTuningBudgetV2(ContractModel):
    maximum_trials: PositiveInt
    maximum_compute_units: float = Field(gt=0.0)
    objective_name: str = Field(min_length=1)


class ProjectOneComparisonPilotBudgetV2(ContractModel):
    budget_scope: Literal["protocol_placeholder"] = "protocol_placeholder"
    observation_budget: ObservationBudget
    model_budget: ModelBudget
    tuning_budget: ProtocolPilotTuningBudgetV2


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

_VERIFICATION_UTILITY_ADAPTER = "grounded-verification-utility@unbound"

_TASK_ADAPTER_IDS = {
    ProjectOneMatchedComparisonId.HABIT_OBSERVATION_CORRECTION: "habit-observation-stream@unbound",
    ProjectOneMatchedComparisonId.HABIT_ACTOR_CONTAMINATION: "habit-actor-stream@unbound",
    ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION: "online-shift-attribution@0.1",
    ProjectOneMatchedComparisonId.CHEH_SOURCE_ALIGNMENT: "hidden-event-provenance@unbound",
    ProjectOneMatchedComparisonId.VERIFICATION_DECISION_OBJECTIVE: _VERIFICATION_UTILITY_ADAPTER,
}

#: v0.2 comparison topology: the shift comparison becomes three arms; the other
#: four comparisons keep their v0.1 two-arm topology.
_COMPARISON_ARMS_V02: dict[ProjectOneMatchedComparisonId, tuple[ProjectOneAblationArmId, ...]] = {
    **_COMPARISON_ARMS,
    ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION: (
        ProjectOneAblationArmId.ORDINARY_BOCPD,
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,  # legacy independent
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD,  # new joint
    ),
}

#: Declared (not executed) method version per arm, and the semantic tags each
#: arm's components/notes must carry.
_METHOD_SEMANTICS: dict[ProjectOneAblationArmId, tuple[str, ...]] = {
    ProjectOneAblationArmId.HABIT_BASELINE: (
        "hierarchical-dirichlet-habit-baseline",
        "no-observation-process-correction",
    ),
    ProjectOneAblationArmId.HABIT_OBSERVATION_CORRECTED: (
        "hierarchical-dirichlet-habit",
        "observation-propensity-corrected",
    ),
    ProjectOneAblationArmId.HABIT_VISITOR_ISOLATED: (
        "hierarchical-dirichlet-habit",
        "non-resident-household-channel-isolation",
    ),
    ProjectOneAblationArmId.HABIT_ACTOR_RESIDUAL: (
        "hierarchical-dirichlet-habit",
        "shrinkage-actor-residual",
    ),
    ProjectOneAblationArmId.ORDINARY_BOCPD: ("ordinary-bocpd",),
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD: ("legacy-independent-per-cause",),
    ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD: (
        "joint-cause-factorized",
        "selective-reset",
        "transient-noise-state",
    ),
    ProjectOneAblationArmId.CHEH_INTERNAL_CONSISTENCY: (
        "cheh-internal-consistency",
        "no-source-aligned-revision",
    ),
    ProjectOneAblationArmId.CHEH_SOURCE_ALIGNED: (
        "cheh-source-aligned-revision",
        "endpoint-and-evidence-cluster-binding",
    ),
    ProjectOneAblationArmId.THRESHOLD_VERIFICATION: ("retuned-threshold-verification",),
    ProjectOneAblationArmId.UTILITY_VERIFICATION: (
        "expected-action-utility-verification",
        "motion-time-interruption-privacy-safety-costs",
    ),
}


def _declared_model_version(arm_id: ProjectOneAblationArmId) -> str:
    if arm_id == ProjectOneAblationArmId.ORDINARY_BOCPD:
        return "online-ordinary-bocpd@0.1"
    if arm_id == ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD:
        return "online-cause-factorized-bocpd@0.1"
    if arm_id == ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD:
        return "joint-cause-factorized-bocpd@0.3"
    return f"{arm_id.value}@adapter-unbound"


def _method_semantics(arm_id: ProjectOneAblationArmId) -> tuple[str, ...]:
    return _METHOD_SEMANTICS[arm_id]


def _arm_components(arm_id: ProjectOneAblationArmId) -> tuple[str, ...]:
    return tuple(dict.fromkeys((arm_id.value, *_method_semantics(arm_id))))


def _topology_binding_payload(
    comparison: ProjectOneProtocolComparisonV2,
    arm: FairAblationArm,
) -> dict[str, object]:
    arm_id = ProjectOneAblationArmId(arm.arm_id)
    return {
        "gate_id": PROJECT_ONE_ABLATION_TOPOLOGY_GATE_V1,
        "comparison_id": comparison.comparison_id.value,
        "comparison_manifest_id": str(comparison.manifest.experiment_id),
        "comparison_manifest_sha256": content_sha256(comparison.manifest),
        "arm_id": arm.arm_id,
        "manifest_arm_sha256": content_sha256(arm),
        "independent_tuning_run_id": str(arm.independent_tuning_run_id),
        "declared_model_version": arm.model_version,
        "method_semantics": list(_method_semantics(arm_id)),
        "topology_result": "validated_topology_binding",
    }


def _topology_binding_sha256(
    comparison: ProjectOneProtocolComparisonV2,
    arm: FairAblationArm,
) -> str:
    return content_sha256(_topology_binding_payload(comparison, arm))


class ProjectOneProtocolPilotConfigV2(ContractModel):
    protocol_version: Literal["project-one-ablation-protocol-pilot@0.2"] = (
        PROJECT_ONE_PILOT_PROTOCOL_V02
    )
    gate_id: Literal["project-one-ablation-topology-gate@1"] = PROJECT_ONE_ABLATION_TOPOLOGY_GATE_V1
    comparison_budgets: dict[ProjectOneMatchedComparisonId, ProjectOneComparisonPilotBudgetV2]
    split_metadata: SealedSplitMetadata

    @model_validator(mode="after")
    def require_all_comparison_budgets(self) -> ProjectOneProtocolPilotConfigV2:
        if set(self.comparison_budgets) != set(ProjectOneMatchedComparisonId):
            missing = sorted(
                item.value
                for item in set(ProjectOneMatchedComparisonId) - set(self.comparison_budgets)
            )
            raise ValueError(f"v0.2 pilot comparison budgets mismatch; missing={missing}")
        return self


class ProjectOneProtocolComparisonV2(ContractModel):
    comparison_id: ProjectOneMatchedComparisonId
    task_adapter_id: str = Field(min_length=1)
    manifest: FairAblationManifest

    @model_validator(mode="after")
    def validate_topology(self) -> ProjectOneProtocolComparisonV2:
        expected = _COMPARISON_ARMS_V02[self.comparison_id]
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


class ProjectOneProtocolPilotManifestV2(ContractModel):
    experiment_id: str = Field(min_length=1)
    protocol_version: Literal["project-one-ablation-protocol-pilot@0.2"]
    gate_id: Literal["project-one-ablation-topology-gate@1"]
    claim_scope: Literal["ablation_topology_only"] = "ablation_topology_only"
    formal_structure_one_b1_scope: Literal["M05-M12-perception"] = "M05-M12-perception"
    formal_structure_one_b1_status: Literal["BLOCK"] = "BLOCK"
    tuning_measured_budget_gate_status: Literal["BLOCK"] = "BLOCK"
    compliant_test_unseal_gate_status: Literal["BLOCK"] = "BLOCK"
    split_experiment_id: str = Field(min_length=1)
    artifact_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_manifest_case_count: int = Field(ge=0)
    train_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_case_count: int = Field(ge=0)
    validation_case_count: int = Field(ge=0)
    test_case_count: int = Field(ge=0)
    comparisons: tuple[ProjectOneProtocolComparisonV2, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_complete_topology(self) -> ProjectOneProtocolPilotManifestV2:
        # Revalidate nested values from plain data.  This prevents a caller from
        # using Pydantic's model_copy(update=...) to smuggle an invalid comparison
        # or arm instance past its own validator.
        validated_comparisons = tuple(
            ProjectOneProtocolComparisonV2.model_validate(item.model_dump(mode="json"))
            for item in self.comparisons
        )
        comparison_ids = [item.comparison_id for item in self.comparisons]
        if len(comparison_ids) != len(set(comparison_ids)):
            raise ValueError("v0.2 pilot comparison IDs must be unique")
        if set(comparison_ids) != set(ProjectOneMatchedComparisonId):
            raise ValueError("v0.2 pilot must contain all five matched comparisons")
        if (
            self.train_case_count + self.validation_case_count + self.test_case_count
            != self.artifact_manifest_case_count
        ):
            raise ValueError("manifest split counts must equal artifact manifest case count")
        expected_artifact_hash = split_artifact_manifest_sha256(
            experiment_id=self.split_experiment_id,
            train_split_sha256=self.train_split_sha256,
            validation_split_sha256=self.validation_split_sha256,
            test_split_sha256=self.test_split_sha256,
            observation_trace_sha256=self.observation_trace_sha256,
            train_case_count=self.train_case_count,
            validation_case_count=self.validation_case_count,
            test_case_count=self.test_case_count,
        )
        if self.artifact_manifest_sha256 != expected_artifact_hash:
            raise ValueError("manifest artifact hash does not match split identities and counts")
        arms = [
            arm.arm_id for comparison in validated_comparisons for arm in comparison.manifest.arms
        ]
        if set(arms) != set(PROJECT_ONE_ARMS_V02) or any(arms.count(arm) != 1 for arm in arms):
            raise ValueError("v0.2 pilot must cover every v0.2 arm exactly once")
        tuning_run_ids = [
            arm.independent_tuning_run_id
            for comparison in validated_comparisons
            for arm in comparison.manifest.arms
        ]
        if len(tuning_run_ids) != len(set(tuning_run_ids)):
            raise ValueError("all 11 v0.2 arms require globally unique tuning run IDs")
        for comparison in validated_comparisons:
            for arm in comparison.manifest.arms:
                if arm.tuning_budget.validation_split_sha256 != self.validation_split_sha256:
                    raise ValueError("every v0.2 arm must bind the manifest validation split")
                if arm.test_split_sha256 != self.test_split_sha256:
                    raise ValueError("every v0.2 arm must bind the manifest sealed TEST split")
                if arm.observation_trace_sha256 != self.observation_trace_sha256:
                    raise ValueError("every v0.2 arm must bind the manifest observation trace")
        return self


class ProjectOnePilotArmTopologyResultV2(ContractModel):
    comparison_id: ProjectOneMatchedComparisonId
    comparison_manifest_id: UUID
    comparison_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_id: ProjectOneAblationArmId
    manifest_arm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_tuning_run_id: UUID
    adapter_status: Literal[PilotAdapterStatusV2.TOPOLOGY_ONLY] = PilotAdapterStatusV2.TOPOLOGY_ONLY
    tuning_status: Literal[PilotTuningStatusV2.NOT_RUN] = PilotTuningStatusV2.NOT_RUN
    declared_model_version: str = Field(min_length=1)
    executed_model_version: None = None
    evaluation_split: None = None
    online_shift_report: None = None
    method_semantics: tuple[str, ...] = Field(min_length=1)
    topology_result: Literal["validated_topology_binding"] = "validated_topology_binding"
    topology_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: Literal["atg1.arm.topology-binding-validated.no-execution@1"] = ATG1_ARM_NOTE_ID


class ProjectOneProtocolPilotReportV2(ContractModel):
    manifest: ProjectOneProtocolPilotManifestV2
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_results: tuple[ProjectOnePilotArmTopologyResultV2, ...] = Field(
        min_length=11, max_length=11
    )
    protocol_contracts_valid: Literal[True] = True
    all_adapters_bound: Literal[False] = False
    formal_experiment_ready: Literal[False] = False
    claim_scope: Literal["ablation_topology_only"] = "ablation_topology_only"
    artifact_manifest_case_count: int = Field(ge=0)
    train_case_count: int = Field(ge=0)
    validation_case_count: int = Field(ge=0)
    test_case_count: int = Field(ge=0)
    caveat_ids: tuple[str, ...] = ATG1_CAVEAT_IDS
    allowed_claims: tuple[str, ...] = ATG1_ALLOWED_CLAIMS
    forbidden_claims: tuple[str, ...] = ATG1_FORBIDDEN_CLAIMS

    @model_validator(mode="after")
    def validate_report(self) -> ProjectOneProtocolPilotReportV2:
        manifest = ProjectOneProtocolPilotManifestV2.model_validate(
            self.manifest.model_dump(mode="json")
        )
        if self.manifest_sha256 != content_sha256(manifest):
            raise ValueError("v0.2 pilot manifest hash mismatch")
        if self.claim_scope != manifest.claim_scope:
            raise ValueError("v0.2 report claim scope must match its manifest")
        report_counts = (
            self.artifact_manifest_case_count,
            self.train_case_count,
            self.validation_case_count,
            self.test_case_count,
        )
        manifest_counts = (
            manifest.artifact_manifest_case_count,
            manifest.train_case_count,
            manifest.validation_case_count,
            manifest.test_case_count,
        )
        if report_counts != manifest_counts:
            raise ValueError("v0.2 report split counts must match its manifest")
        if self.caveat_ids != ATG1_CAVEAT_IDS:
            raise ValueError("v0.2 report caveat IDs must match the canonical ATG-1 set")
        if self.allowed_claims != ATG1_ALLOWED_CLAIMS:
            raise ValueError("v0.2 report allowed claims must match the ATG-1 policy")
        if self.forbidden_claims != ATG1_FORBIDDEN_CLAIMS:
            raise ValueError("v0.2 report forbidden claims must match the ATG-1 policy")
        results = tuple(
            ProjectOnePilotArmTopologyResultV2.model_validate(result.model_dump(mode="json"))
            for result in self.arm_results
        )
        result_arms = [result.arm_id for result in results]
        if {arm.value for arm in result_arms} != PROJECT_ONE_ARMS_V02 or len(result_arms) != len(
            set(result_arms)
        ):
            raise ValueError("v0.2 pilot report must contain one topology result per v0.2 arm")
        if any(result.adapter_status != PilotAdapterStatusV2.TOPOLOGY_ONLY for result in results):
            raise ValueError("ATG-1 report requires every arm to be topology_only")
        manifest_arm_bindings = {
            ProjectOneAblationArmId(arm.arm_id): (comparison, arm)
            for comparison in manifest.comparisons
            for arm in comparison.manifest.arms
        }
        for result in results:
            comparison, arm = manifest_arm_bindings[result.arm_id]
            expected_semantics = _method_semantics(result.arm_id)
            if result.comparison_id != comparison.comparison_id:
                raise ValueError("arm topology result is bound to the wrong comparison")
            if result.comparison_manifest_id != comparison.manifest.experiment_id:
                raise ValueError("arm topology result comparison manifest ID mismatch")
            if result.comparison_manifest_sha256 != content_sha256(comparison.manifest):
                raise ValueError("arm topology result comparison manifest hash mismatch")
            if result.manifest_arm_sha256 != content_sha256(arm):
                raise ValueError("arm topology result manifest arm hash mismatch")
            if result.independent_tuning_run_id != arm.independent_tuning_run_id:
                raise ValueError("arm topology result tuning run binding mismatch")
            if result.declared_model_version != arm.model_version:
                raise ValueError("arm topology result model version mismatch")
            if result.declared_model_version != _declared_model_version(result.arm_id):
                raise ValueError("arm topology result model version violates method registry")
            if result.method_semantics != expected_semantics:
                raise ValueError("arm topology result method semantics mismatch")
            if arm.components != _arm_components(result.arm_id):
                raise ValueError("manifest arm components violate method semantics registry")
            if result.topology_result != "validated_topology_binding":
                raise ValueError("arm topology result is not a validated binding")
            if result.topology_binding_sha256 != _topology_binding_sha256(comparison, arm):
                raise ValueError("arm topology result binding hash mismatch")
            if result.note != ATG1_ARM_NOTE_ID:
                raise ValueError("arm topology result note must use the canonical ATG-1 ID")
        return self


class ProjectOneProtocolPilotRunnerV2:
    """ATG-1 runner: validates the 11-arm v0.2 protocol and runs nothing.

    It never generates a suite, never unseals a split, never calls a model or an
    evaluator, and never touches any TEST case; it only binds declared budgets
    and split-identity hashes into a topology-only report.
    """

    def run(self, config: ProjectOneProtocolPilotConfigV2) -> ProjectOneProtocolPilotReportV2:
        metadata = config.split_metadata
        experiment_id = str(
            content_uuid(
                "project-one-protocol-pilot-v0.2",
                {
                    "protocol_version": config.protocol_version,
                    "gate_id": config.gate_id,
                    "artifact_manifest_sha256": metadata.artifact_manifest_sha256,
                    "test_split_sha256": metadata.test_split_sha256,
                    "config": config,
                },
            )
        )
        comparisons = tuple(
            self._comparison(comparison_id, config, experiment_id, metadata)
            for comparison_id in ProjectOneMatchedComparisonId
        )
        manifest = ProjectOneProtocolPilotManifestV2(
            experiment_id=experiment_id,
            protocol_version=config.protocol_version,
            gate_id=config.gate_id,
            split_experiment_id=metadata.experiment_id,
            artifact_manifest_sha256=metadata.artifact_manifest_sha256,
            artifact_manifest_case_count=metadata.artifact_manifest_case_count,
            train_split_sha256=metadata.train_split_sha256,
            validation_split_sha256=metadata.validation_split_sha256,
            test_split_sha256=metadata.test_split_sha256,
            observation_trace_sha256=metadata.observation_trace_sha256,
            train_case_count=metadata.train_case_count,
            validation_case_count=metadata.validation_case_count,
            test_case_count=metadata.test_case_count,
            comparisons=comparisons,
        )
        arm_results = tuple(
            self._arm_result(comparison, arm)
            for comparison in comparisons
            for arm in comparison.manifest.arms
        )
        return ProjectOneProtocolPilotReportV2(
            manifest=manifest,
            manifest_sha256=content_sha256(manifest),
            arm_results=arm_results,
            all_adapters_bound=False,
            artifact_manifest_case_count=metadata.artifact_manifest_case_count,
            train_case_count=metadata.train_case_count,
            validation_case_count=metadata.validation_case_count,
            test_case_count=metadata.test_case_count,
        )

    def _comparison(
        self,
        comparison_id: ProjectOneMatchedComparisonId,
        config: ProjectOneProtocolPilotConfigV2,
        experiment_id: str,
        metadata: SealedSplitMetadata,
    ) -> ProjectOneProtocolComparisonV2:
        budget = config.comparison_budgets[comparison_id]
        arm_ids = _COMPARISON_ARMS_V02[comparison_id]
        arms = tuple(
            FairAblationArm(
                arm_id=arm_id.value,
                model_version=_declared_model_version(arm_id),
                components=_arm_components(arm_id),
                observation_budget=budget.observation_budget,
                model_budget=budget.model_budget,
                tuning_budget=TuningBudget(
                    maximum_trials=budget.tuning_budget.maximum_trials,
                    maximum_compute_units=budget.tuning_budget.maximum_compute_units,
                    validation_split_sha256=metadata.validation_split_sha256,
                    objective_name=budget.tuning_budget.objective_name,
                ),
                independent_tuning_run_id=content_uuid(
                    "project-one-protocol-pilot-v0.2-tuning-run",
                    {
                        "experiment_id": experiment_id,
                        "comparison_id": comparison_id,
                        "arm_id": arm_id,
                    },
                ),
                observation_trace_sha256=metadata.observation_trace_sha256,
                test_split_sha256=metadata.test_split_sha256,
            )
            for arm_id in arm_ids
        )
        comparison_manifest = FairAblationManifest(
            experiment_id=content_uuid(
                "project-one-protocol-pilot-v0.2-comparison",
                {"experiment_id": experiment_id, "comparison_id": comparison_id},
            ),
            baseline_arm_id=arm_ids[0].value,
            arms=arms,
        )
        return ProjectOneProtocolComparisonV2(
            comparison_id=comparison_id,
            task_adapter_id=_TASK_ADAPTER_IDS[comparison_id],
            manifest=comparison_manifest,
        )

    @staticmethod
    def _arm_result(
        comparison: ProjectOneProtocolComparisonV2,
        arm: FairAblationArm,
    ) -> ProjectOnePilotArmTopologyResultV2:
        arm_id = ProjectOneAblationArmId(arm.arm_id)
        semantics = _method_semantics(arm_id)
        return ProjectOnePilotArmTopologyResultV2(
            comparison_id=comparison.comparison_id,
            comparison_manifest_id=comparison.manifest.experiment_id,
            comparison_manifest_sha256=content_sha256(comparison.manifest),
            arm_id=arm_id,
            manifest_arm_sha256=content_sha256(arm),
            independent_tuning_run_id=arm.independent_tuning_run_id,
            declared_model_version=arm.model_version,
            method_semantics=semantics,
            topology_binding_sha256=_topology_binding_sha256(comparison, arm),
            note=ATG1_ARM_NOTE_ID,
        )


def select_pilot_runner(
    config: ProjectOneProtocolPilotConfigV2,
) -> ProjectOneProtocolPilotRunnerV2:
    """Strict ATG-1 dispatch: only an exact v0.2 config is accepted."""

    if not isinstance(config, ProjectOneProtocolPilotConfigV2):
        raise TypeError(
            f"ATG-1 requires ProjectOneProtocolPilotConfigV2, got {type(config).__name__}"
        )
    return ProjectOneProtocolPilotRunnerV2()
