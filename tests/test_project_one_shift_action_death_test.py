"""Dual-track fairness and tamper-negative tests for the SHIFT death test."""

from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.project_one_shift_action_death_test import (
    POWER_ENDPOINTS,
    POWER_REFERENCES,
    ProjectOneShiftActionDeathTestConfig,
    ProjectOneShiftActionDeathTestReport,
    ProjectOneShiftActionDeathTestRunner,
    ResearchDecision,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import SHIFT_THREE_ARMS
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks/project_one_ablation/project_one_shift_action_death_test_v2.json"


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


def _power_topology(items) -> tuple[tuple[str, ProjectOneAblationArmId], ...]:
    return tuple((item.endpoint_id, item.reference_arm_id) for item in items)


def test_power_topology_is_exact_nonempty_ordered_and_covers_both_references(
    completed_report,
):
    expected = tuple(
        (endpoint_id, reference)
        for reference in POWER_REFERENCES
        for endpoint_id, _role, _metric, _mde in POWER_ENDPOINTS
    )
    assert _power_topology(completed_report.power_analyses) == expected
    assert _power_topology(completed_report.retuned_power_analyses) == expected
    assert len(expected) == 4
    assert max(item.required_test_seed_count for item in completed_report.power_analyses) == 151
    assert (
        max(item.required_test_seed_count for item in completed_report.retuned_power_analyses)
        == 101
    )


def test_empty_power_cannot_coexist_with_test_even_after_decision_and_outer_rehash(
    completed_report,
):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    payload["power_analyses"] = []
    payload["decision"] = {
        "decision": "block_underpowered",
        "primary_joint_minus_ordinary": None,
        "corruption_joint_minus_ordinary": None,
        "primary_joint_minus_legacy": None,
        "corruption_joint_minus_legacy": None,
        "primary_practical_threshold": 0.05,
        "corruption_practical_threshold": 0.02,
        "rationale_id": "decision.test-not-opened-power-block@1",
    }
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="power analyses"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


@pytest.mark.parametrize("track_field", ["power_analyses", "retuned_power_analyses"])
def test_power_omission_duplication_and_reordering_are_rejected(completed_report, track_field):
    for mutation in ("omit", "duplicate", "reverse"):
        payload = deepcopy(completed_report.model_dump(mode="json"))
        items = payload[track_field]
        if mutation == "omit":
            items.pop()
        elif mutation == "duplicate":
            items[-1] = deepcopy(items[0])
        else:
            items.reverse()
        _rehash_report(payload)
        with pytest.raises(ValidationError, match="power analyses"):
            ProjectOneShiftActionDeathTestReport.model_validate(payload)


@pytest.mark.parametrize("track_field", ["power_analyses", "retuned_power_analyses"])
def test_empirical_stddev_must_recompute_from_pilot_artifacts(completed_report, track_field):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    item = payload[track_field][0]
    item["empirical_paired_stddev"] = 0.0
    item["required_test_seed_count"] = 2
    item["status"] = "PASS"
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="power analyses"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_pilot_artifacts_bind_exact_config_seed_set(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    payload["config"]["seed_plan"]["pilot_seeds"][0] = 999_999
    payload["config_sha256"] = content_sha256(payload["config"])
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="pilot artifact seeds"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_shared_and_retuned_tracks_have_declared_fair_search_budgets(completed_report):
    report = completed_report
    assert tuple(item.arm_id for item in report.tuning_records) == SHIFT_THREE_ARMS
    assert tuple(item.arm_id for item in report.retuned_tuning_records) == SHIFT_THREE_ARMS
    assert all(item.evaluated_trial_count == 18 for item in report.tuning_records)
    assert {item.policy_trial_count for item in report.retuned_tuning_records} == {117}
    assert {item.detector_trial_count for item in report.retuned_tuning_records} == {18}
    assert {item.evaluated_candidate_count for item in report.retuned_tuning_records} == {2106}
    assert len({item.selected_policy_sha256 for item in report.retuned_tuning_records}) > 1
    assert all(artifact.policy == report.policy for artifact in report.test_artifacts.values())
    assert all(
        report.retuned_test_artifacts[item.arm_id].policy == item.selected_policy
        for item in report.retuned_tuning_records
    )


def test_reset_then_consolidate_is_an_explicit_ordered_transition(completed_report):
    outcomes = tuple(
        outcome
        for artifacts in (
            completed_report.test_artifacts,
            completed_report.retuned_test_artifacts,
        )
        for artifact in artifacts.values()
        for outcome in artifact.outcomes
    )
    consolidated = [item for item in outcomes if item.consolidation_issued]
    assert consolidated
    assert all(item.reset_issued for item in consolidated)
    assert all(
        item.action_sequence == ("RESET_OLD_REGIME", "CONSOLIDATE_NEW_REGIME")
        for item in consolidated
    )
    assert all(hasattr(item, "task_success_proxy") for item in outcomes)


def test_predictions_intervals_and_cross_track_decision_recompute(completed_report):
    checked = ProjectOneShiftActionDeathTestReport.model_validate_json(
        completed_report.model_dump_json()
    )
    assert len(checked.paired_test_intervals) == 4
    assert len(checked.retuned_paired_test_intervals) == 4
    assert checked.overall_decision.decision in set(ResearchDecision)


def test_prediction_and_interval_tamper_fail_after_rehash(completed_report):
    prediction_payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = prediction_payload["retuned_test_artifacts"][arm]
    prediction = artifact["predictions"][0]
    cause = next(iter(prediction["cause_probabilities"]))
    prediction["cause_probabilities"][cause] = 0.0
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    _rehash_report(prediction_payload)
    with pytest.raises(ValidationError, match="recompute"):
        ProjectOneShiftActionDeathTestReport.model_validate(prediction_payload)

    interval_payload = deepcopy(completed_report.model_dump(mode="json"))
    interval_payload["retuned_paired_test_intervals"][0]["difference_joint_minus_reference"] = -0.9
    _rehash_report(interval_payload)
    with pytest.raises(ValidationError, match="retuned paired intervals"):
        ProjectOneShiftActionDeathTestReport.model_validate(interval_payload)


def test_cli_subprocess_writes_a_self_validating_v2_report(tmp_path):
    output = tmp_path / "action-report-v2.json"
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
    assert completed.returncode == 0, completed.stderr
    assert "overall_decision=" in completed.stdout
    ProjectOneShiftActionDeathTestReport.model_validate_json(output.read_text(encoding="utf-8"))
