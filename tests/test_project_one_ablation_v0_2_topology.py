"""ATG-1 tests: v0.2 11-arm topology, v0.1 freeze protection, zero TEST.

Covers the former narrow "B1" plan, now named ATG-1: v0.1 protection,
v0.2 topology, zero-TEST-access,
version/output, and v0.1 authoritative-asset raw-hash protection.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.fair_ablation import (
    PROJECT_ONE_ARMS_V01,
    PROJECT_ONE_ARMS_V01_ORDERED,
    PROJECT_ONE_ARMS_V02,
    FairAblationArm,
    FairAblationManifest,
    ModelBudget,
    ObservationBudget,
    ProjectOneAblationArmId,
    ProjectOneFairAblationManifest,
    ProjectOneFairAblationManifestV2,
    TuningBudget,
)
from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (
    ProjectOneComparisonPilotBudgetV2,
    ProjectOneMatchedComparisonId,
    ProjectOneProtocolComparisonV2,
    ProjectOneProtocolPilotConfigV2,
    ProjectOneProtocolPilotManifestV2,
    ProjectOneProtocolPilotReportV2,
    ProjectOneProtocolPilotRunnerV2,
    ProtocolPilotTuningBudgetV2,
    select_pilot_runner,
)
from cpswm.system.evaluation_operations.sealed_test_split import SealedSplitMetadata

REPO = Path(__file__).resolve().parents[1]
V01_CONFIG = REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.1.json"
V01_REPORT_FIXTURE = (
    REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.1.fixture.json"
)
V02_CONFIG = REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.2.json"
V02_REPORT_FIXTURE = (
    REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.2.fixture.json"
)

V01_CONFIG_SHA256 = "df0f4d19f172da6df790164ac23e7ccddd88c2643dda102e928459570a7fd307"
V01_REPORT_FIXTURE_SHA256 = "93c3f5975340a581d74b5541202dfcf706aeb93bc2c0e50e6df8dc322924c648"
V02_CONFIG_SHA256 = "ffa62c956be0fdda56a6c2d87b0f67e83e4d42c775ccce4b36f607a3c4552b86"
V02_REPORT_FIXTURE_SHA256 = "27e5a896dea69b2d2c9cf4c5333566cc61c8d0e358c02bb8caa14d7fd810a7ed"

HEX = "a" * 64


def _budgets():
    budget = ProjectOneComparisonPilotBudgetV2(
        observation_budget=ObservationBudget(
            maximum_observation_actions=5,
            maximum_user_interruptions=1,
            maximum_observation_cost=1.0,
            maximum_elapsed_time_seconds=60.0,
        ),
        model_budget=ModelBudget(
            maximum_train_compute_units=1.0,
            maximum_inference_compute_units=1.0,
            maximum_persistent_memory_bytes=1024,
            maximum_latency_ms=10.0,
            maximum_parameter_count=1000,
        ),
        tuning_budget=ProtocolPilotTuningBudgetV2(
            maximum_trials=1, maximum_compute_units=1.0, objective_name="utility"
        ),
    )
    return {comparison: budget for comparison in ProjectOneMatchedComparisonId}


def _metadata():
    return SealedSplitMetadata(
        experiment_id="exp",
        artifact_manifest_sha256="a" * 64,
        train_split_sha256="b" * 64,
        validation_split_sha256="c" * 64,
        test_split_sha256="d" * 64,
        observation_trace_sha256="e" * 64,
        train_case_count=10,
        validation_case_count=5,
        test_case_count=5,
    )


def _config_v2():
    return ProjectOneProtocolPilotConfigV2(
        comparison_budgets=_budgets(), split_metadata=_metadata()
    )


def _fair_arm(arm_id: str, tuning_run_id=None) -> FairAblationArm:
    return FairAblationArm(
        arm_id=arm_id,
        model_version="m@1",
        components=(arm_id,),
        observation_budget=ObservationBudget(
            maximum_observation_actions=5,
            maximum_user_interruptions=1,
            maximum_observation_cost=1.0,
            maximum_elapsed_time_seconds=60.0,
        ),
        model_budget=ModelBudget(
            maximum_train_compute_units=1.0,
            maximum_inference_compute_units=1.0,
            maximum_persistent_memory_bytes=1024,
            maximum_latency_ms=10.0,
            maximum_parameter_count=1000,
        ),
        tuning_budget=TuningBudget(
            maximum_trials=1,
            maximum_compute_units=1.0,
            validation_split_sha256=HEX,
            objective_name="u",
        ),
        independent_tuning_run_id=tuning_run_id or uuid4(),
        observation_trace_sha256=HEX,
        test_split_sha256=HEX,
    )


def _fair_manifest(arm_ids, cls=FairAblationManifest):
    return cls(
        experiment_id=uuid4(),
        baseline_arm_id=arm_ids[0],
        arms=tuple(_fair_arm(a) for a in arm_ids),
    )


# --- v0.1 authoritative asset raw-hash protection ----------------------------


def test_v01_config_raw_hash_is_protected():
    assert hashlib.sha256(V01_CONFIG.read_bytes()).hexdigest() == V01_CONFIG_SHA256


def test_v01_report_fixture_raw_hash_is_protected():
    assert hashlib.sha256(V01_REPORT_FIXTURE.read_bytes()).hexdigest() == V01_REPORT_FIXTURE_SHA256


def test_v02_config_and_report_fixture_raw_hashes_are_protected():
    assert hashlib.sha256(V02_CONFIG.read_bytes()).hexdigest() == V02_CONFIG_SHA256
    assert hashlib.sha256(V02_REPORT_FIXTURE.read_bytes()).hexdigest() == V02_REPORT_FIXTURE_SHA256
    report = ProjectOneProtocolPilotReportV2.model_validate_json(
        V02_REPORT_FIXTURE.read_text(encoding="utf-8")
    )
    assert report.manifest.gate_id == "project-one-ablation-topology-gate@1"


# --- v0.1 protection: frozen 10-arm set --------------------------------------


def test_v01_fair_manifest_accepts_exactly_the_ten_arms():
    manifest = _fair_manifest(PROJECT_ONE_ARMS_V01_ORDERED, ProjectOneFairAblationManifest)
    assert {arm.arm_id for arm in manifest.arms} == PROJECT_ONE_ARMS_V01


def test_v01_fair_manifest_rejects_the_joint_eleventh_arm():
    arms = (
        *sorted(PROJECT_ONE_ARMS_V01),
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD.value,
    )
    with pytest.raises(ValidationError, match="exactly the 10 v0"):
        _fair_manifest(arms, ProjectOneFairAblationManifest)


def test_v01_fair_manifest_rejects_a_missing_arm():
    arms = tuple(sorted(PROJECT_ONE_ARMS_V01))[:-1]
    with pytest.raises(ValidationError, match="exactly the 10 v0"):
        _fair_manifest(arms, ProjectOneFairAblationManifest)


# --- v0.2 topology: exactly 11 arms ------------------------------------------


def test_v02_fair_manifest_accepts_exactly_eleven_arms():
    manifest = _fair_manifest(sorted(PROJECT_ONE_ARMS_V02), ProjectOneFairAblationManifestV2)
    assert {arm.arm_id for arm in manifest.arms} == PROJECT_ONE_ARMS_V02


def test_v02_fair_manifest_rejects_missing_joint():
    with pytest.raises(ValidationError, match="exactly the 11 v0"):
        _fair_manifest(sorted(PROJECT_ONE_ARMS_V01), ProjectOneFairAblationManifestV2)


def test_v02_fair_manifest_rejects_a_twelfth_arm():
    arms = (*sorted(PROJECT_ONE_ARMS_V02), "some-extra-twelfth-arm")
    with pytest.raises(ValidationError, match="exactly the 11 v0"):
        _fair_manifest(arms, ProjectOneFairAblationManifestV2)


def test_v02_fair_manifest_rejects_replacing_legacy_with_joint():
    arms = sorted(PROJECT_ONE_ARMS_V02 - {ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value})
    with pytest.raises(ValidationError, match="exactly the 11 v0"):
        _fair_manifest(arms, ProjectOneFairAblationManifestV2)


def _shift_comparison(arm_ids, *, adapter="online-shift-attribution@0.1", baseline=None):
    manifest = FairAblationManifest(
        experiment_id=uuid4(),
        baseline_arm_id=baseline or arm_ids[0],
        arms=tuple(_fair_arm(a) for a in arm_ids),
    )
    return ProjectOneProtocolComparisonV2(
        comparison_id=ProjectOneMatchedComparisonId.SHIFT_CAUSE_FACTORIZATION,
        task_adapter_id=adapter,
        manifest=manifest,
    )


def test_v02_shift_comparison_accepts_three_ordered_arms():
    comparison = _shift_comparison(
        (
            ProjectOneAblationArmId.ORDINARY_BOCPD.value,
            ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value,
            ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD.value,
        )
    )
    assert comparison.manifest.baseline_arm_id == ProjectOneAblationArmId.ORDINARY_BOCPD.value


def test_v02_shift_comparison_rejects_two_arms():
    with pytest.raises(ValidationError, match="requires ordered arms"):
        _shift_comparison(
            (
                ProjectOneAblationArmId.ORDINARY_BOCPD.value,
                ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value,
            )
        )


def test_v02_shift_comparison_rejects_wrong_order():
    with pytest.raises(ValidationError, match="requires ordered arms"):
        _shift_comparison(
            (
                ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD.value,
                ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD.value,
                ProjectOneAblationArmId.ORDINARY_BOCPD.value,
            )
        )


def test_v02_joint_cannot_appear_in_another_comparison():
    manifest = FairAblationManifest(
        experiment_id=uuid4(),
        baseline_arm_id=ProjectOneAblationArmId.HABIT_BASELINE.value,
        arms=(
            _fair_arm(ProjectOneAblationArmId.HABIT_BASELINE.value),
            _fair_arm(ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD.value),
        ),
    )
    with pytest.raises(ValidationError, match="requires ordered arms"):
        ProjectOneProtocolComparisonV2(
            comparison_id=ProjectOneMatchedComparisonId.HABIT_OBSERVATION_CORRECTION,
            task_adapter_id="habit-observation-stream@unbound",
            manifest=manifest,
        )


def test_v02_full_report_has_eleven_topology_only_arms():
    report = ProjectOneProtocolPilotRunnerV2().run(_config_v2())
    assert len(report.arm_results) == 11
    assert {r.arm_id.value for r in report.arm_results} == PROJECT_ONE_ARMS_V02
    assert all(r.adapter_status == "topology_only" for r in report.arm_results)
    assert report.formal_experiment_ready is False
    assert report.claim_scope == "ablation_topology_only"
    assert report.all_adapters_bound is False
    assert report.manifest.gate_id == "project-one-ablation-topology-gate@1"
    assert report.manifest.formal_structure_one_b1_scope == "M05-M12-perception"
    assert report.manifest.formal_structure_one_b1_status == "BLOCK"
    assert report.manifest.tuning_measured_budget_gate_status == "BLOCK"
    assert report.manifest.compliant_test_unseal_gate_status == "BLOCK"


def test_v02_manifest_requires_all_eleven_tuning_run_ids_globally_unique():
    report = ProjectOneProtocolPilotRunnerV2().run(_config_v2())
    payload = report.manifest.model_dump(mode="json")
    first_id = payload["comparisons"][0]["manifest"]["arms"][0]["independent_tuning_run_id"]
    payload["comparisons"][1]["manifest"]["arms"][0]["independent_tuning_run_id"] = first_id

    with pytest.raises(ValidationError, match="globally unique tuning run IDs"):
        ProjectOneProtocolPilotManifestV2.model_validate(payload)


# --- zero TEST access --------------------------------------------------------


def test_split_metadata_carries_no_cases_or_loader():
    forbidden = {"cases", "unseal", "load", "require_unsealed", "model_inputs", "evaluator_truth"}
    assert forbidden.isdisjoint(set(SealedSplitMetadata.__dataclass_fields__))
    assert not any(hasattr(SealedSplitMetadata, name) for name in ("unseal", "load"))


def test_runner_v2_runs_no_model_and_reads_no_test(monkeypatch):
    # The ATG-1 module has no model-baseline dependency at all.  Also trap the
    # legacy suite generator: topology validation must succeed without it.
    import cpswm.system.evaluation_operations.project_one_ablation_v0_2 as atg1
    from cpswm.system.evaluation_operations.online_shift_attribution import (
        OnlineShiftSuiteGenerator,
    )

    def boom(*args, **kwargs):
        raise AssertionError("ATG-1 topology runner must not run models or read TEST")

    source = inspect.getsource(atg1)
    assert "from .shift_baselines import" not in source
    assert "OnlineOrdinaryBOCPDBaseline" not in source
    assert "OnlineCauseFactorizedBOCPDBaseline" not in source
    monkeypatch.setattr(OnlineShiftSuiteGenerator, "generate", boom)
    report = ProjectOneProtocolPilotRunnerV2().run(_config_v2())
    assert all(r.online_shift_report is None for r in report.arm_results)
    assert all(r.evaluation_split is None for r in report.arm_results)
    assert all(r.executed_model_version is None for r in report.arm_results)


# --- version dispatch & output ------------------------------------------------


def test_strict_dispatch_accepts_only_atg1_v0_2_config():
    assert isinstance(select_pilot_runner(_config_v2()), ProjectOneProtocolPilotRunnerV2)


def test_atg1_dispatch_rejects_non_v0_2_config_object():
    with pytest.raises(TypeError, match="ATG-1 requires"):
        select_pilot_runner(object())  # type: ignore[arg-type]


def test_v0_2_config_class_rejects_the_v0_1_config_json():
    with pytest.raises(ValidationError):
        ProjectOneProtocolPilotConfigV2.model_validate_json(V01_CONFIG.read_text())


def test_v0_2_report_forces_protocol_only_and_not_ready():
    report = ProjectOneProtocolPilotRunnerV2().run(_config_v2())
    dumped = ProjectOneProtocolPilotReportV2.model_validate_json(report.model_dump_json())
    assert dumped.formal_experiment_ready is False
    assert dumped.claim_scope == "ablation_topology_only"


# --- report binding tamper-negative tests ------------------------------------


def _tampered_report_payload():
    report = ProjectOneProtocolPilotRunnerV2().run(_config_v2())
    return report.model_dump(mode="json")


def test_report_rejects_tampered_arm_comparison_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["comparison_id"] = "shift-cause-factorization"
    with pytest.raises(ValidationError, match="wrong comparison"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_comparison_manifest_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["comparison_manifest_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="comparison manifest hash mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_manifest_arm_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["manifest_arm_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="manifest arm hash mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_tuning_run_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["independent_tuning_run_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="tuning run binding mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_model_version_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["declared_model_version"] = "forged-model@9"
    with pytest.raises(ValidationError, match="model version mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_method_semantics_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["method_semantics"] = ["forged-semantics"]
    with pytest.raises(ValidationError, match="method semantics mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_topology_result_binding():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["topology_binding_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="binding hash mismatch"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_topology_result_status():
    payload = _tampered_report_payload()
    payload["arm_results"][0]["topology_result"] = "claimed_experiment_success"
    with pytest.raises(ValidationError):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_report_rejects_tampered_manifest_even_when_outer_hash_is_recomputed():
    payload = _tampered_report_payload()
    # Modify the arm's method components, then recompute both enclosing hashes.
    # Per-arm registry binding must still reject the forged semantics.
    payload["manifest"]["comparisons"][0]["manifest"]["arms"][0]["components"] = [
        "habit-baseline",
        "forged-semantics",
    ]
    from cpswm.system.reproducibility import content_sha256

    comparison_manifest = payload["manifest"]["comparisons"][0]["manifest"]
    payload["arm_results"][0]["comparison_manifest_sha256"] = content_sha256(comparison_manifest)
    payload["arm_results"][0]["manifest_arm_sha256"] = content_sha256(
        comparison_manifest["arms"][0]
    )
    payload["manifest_sha256"] = content_sha256(payload["manifest"])

    with pytest.raises(ValidationError, match="method semantics registry"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)
