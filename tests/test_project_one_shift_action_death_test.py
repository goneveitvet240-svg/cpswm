"""Research and tamper-negative tests for the SHIFT action death test."""

from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.project_one_shift_action_death_test import (
    ALLOWED_CLAIM_IDS,
    FORBIDDEN_CLAIM_IDS,
    KEY_SECONDARY_ENDPOINT_ID,
    PRIMARY_ENDPOINT_ID,
    ProjectOneShiftActionDeathTestConfig,
    ProjectOneShiftActionDeathTestReport,
    ProjectOneShiftActionDeathTestRunner,
    ResearchDecision,
    required_paired_seed_count,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import SHIFT_THREE_ARMS
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks/project_one_ablation/project_one_shift_action_death_test_v1.json"


@pytest.fixture(scope="module")
def completed_report():
    config = ProjectOneShiftActionDeathTestConfig.model_validate_json(
        CONFIG.read_text(encoding="utf-8")
    )
    return ProjectOneShiftActionDeathTestRunner().run(
        config,
        code_snapshot_sha256="a" * 64,
        git_commit_sha="b" * 40,
    )


def _rehash_report(payload: dict) -> None:
    payload["report_sha256"] = content_sha256(
        {key: value for key, value in payload.items() if key != "report_sha256"}
    )


def test_seed_partitions_are_independent_and_empirical_power_opens_test(completed_report):
    report = completed_report
    plan = report.config.seed_plan
    flattened = plan.validation_seeds + plan.pilot_seeds + plan.test_seeds
    assert len(flattened) == len(set(flattened))
    assert len(plan.test_seeds) == 151
    assert [
        (item.endpoint_id, item.required_test_seed_count, item.status)
        for item in report.power_analyses
    ] == [
        (PRIMARY_ENDPOINT_ID, 11, "PASS"),
        (KEY_SECONDARY_ENDPOINT_ID, 151, "PASS"),
    ]
    assert all(item.empirical_paired_stddev != 0.1 for item in report.power_analyses)
    assert set(report.test_artifacts) == set(SHIFT_THREE_ARMS)


def test_three_arms_are_independently_retuned_but_share_one_policy(completed_report):
    report = completed_report
    assert tuple(item.arm_id for item in report.tuning_records) == SHIFT_THREE_ARMS
    assert len({item.selected_params_sha256 for item in report.tuning_records}) == 3
    assert all(
        artifact.policy_sha256 == report.policy_sha256 and artifact.policy == report.policy
        for artifact in (*report.pilot_artifacts.values(), *report.test_artifacts.values())
    )
    assert all(item.evaluated_trial_count == 18 for item in report.tuning_records)


def test_preregistered_decision_uses_ordinary_and_legacy(completed_report):
    report = completed_report
    decision = report.decision
    assert decision.decision in set(ResearchDecision)
    assert decision.primary_joint_minus_ordinary.reference_arm_id == (
        ProjectOneAblationArmId.ORDINARY_BOCPD
    )
    assert decision.primary_joint_minus_legacy.reference_arm_id == (
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD
    )
    assert decision.corruption_joint_minus_ordinary.endpoint_id == KEY_SECONDARY_ENDPOINT_ID
    assert decision.corruption_joint_minus_legacy.endpoint_id == KEY_SECONDARY_ENDPOINT_ID


def test_report_round_trip_recomputes_every_aggregate(completed_report):
    checked = ProjectOneShiftActionDeathTestReport.model_validate_json(
        completed_report.model_dump_json()
    )
    assert checked.report_sha256 == completed_report.report_sha256
    assert checked.allowed_claims == ALLOWED_CLAIM_IDS
    assert checked.forbidden_claims == FORBIDDEN_CLAIM_IDS


def test_prediction_tamper_fails_after_inner_and_outer_rehash(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = payload["test_artifacts"][arm]
    prediction = artifact["predictions"][0]
    cause = next(iter(prediction["cause_probabilities"]))
    prediction["cause_probabilities"][cause] = 0.0
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="recompute"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_interval_tamper_fails_after_outer_rehash(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    payload["paired_test_intervals"][0]["difference_joint_minus_reference"] = -0.9
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="paired intervals"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_claim_and_policy_tamper_are_rejected(completed_report):
    claims = deepcopy(completed_report.model_dump(mode="json"))
    claims["allowed_claims"].append("claim.joint-superior@9")
    _rehash_report(claims)
    with pytest.raises(ValidationError, match="claim IDs"):
        ProjectOneShiftActionDeathTestReport.model_validate(claims)

    policy = deepcopy(completed_report.model_dump(mode="json"))
    policy["test_artifacts"][ProjectOneAblationArmId.ORDINARY_BOCPD.value]["policy"][
        "reset_probability_threshold"
    ] = 0.1
    _rehash_report(policy)
    with pytest.raises(ValidationError):
        ProjectOneShiftActionDeathTestReport.model_validate(policy)


def test_power_calculation_uses_metric_specific_empirical_variance():
    assert (
        required_paired_seed_count(0.057924241575318246, 0.05, alpha=0.05, target_power=0.8) == 11
    )
    assert (
        required_paired_seed_count(0.08764118476161362, 0.02, alpha=0.05, target_power=0.8) == 151
    )


def test_cli_subprocess_writes_a_self_validating_report(tmp_path):
    output = tmp_path / "action-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps/evaluation_runner/run_project_one_shift_action_death_test.py"),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "decision=" in completed.stdout
    report = ProjectOneShiftActionDeathTestReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert report.git_commit_sha
    assert report.code_snapshot_sha256
