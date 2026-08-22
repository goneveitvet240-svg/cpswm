"""Dual-track fairness and tamper-negative tests for the SHIFT death test."""

from __future__ import annotations

import json
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
CONFIG = ROOT / "benchmarks/project_one_ablation/project_one_shift_action_death_test_v5.json"


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


def test_v5_test_seeds_are_fresh_against_all_prior_protocols():
    current = ProjectOneShiftActionDeathTestConfig.model_validate_json(
        CONFIG.read_text(encoding="utf-8")
    )
    prior_test_seeds: set[int] = set()
    for version in (1, 2, 3, 4):
        filename = f"project_one_shift_action_death_test_v{version}.json"
        prior_config = ROOT / "benchmarks/project_one_ablation" / filename
        payload = json.loads(prior_config.read_text(encoding="utf-8"))
        prior_test_seeds.update(payload["seed_plan"]["test_seeds"])
    assert len(current.seed_plan.test_seeds) == 50
    assert not (set(current.seed_plan.test_seeds) & prior_test_seeds)


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
    assert max(item.required_test_seed_count for item in completed_report.power_analyses) == 50
    assert (
        max(item.required_test_seed_count for item in completed_report.retuned_power_analyses) == 50
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
    with pytest.raises(ValidationError, match=r"required seed count|power analyses"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_pilot_artifacts_bind_exact_config_seed_set(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    payload["config"]["seed_plan"]["pilot_seeds"][0] = 999_999
    payload["config_sha256"] = content_sha256(payload["config"])
    _rehash_report(payload)
    with pytest.raises(ValidationError, match=r"input artifact seeds|pilot artifact seeds"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_shared_and_retuned_tracks_have_declared_fair_search_budgets(completed_report):
    report = completed_report
    assert tuple(item.arm_id for item in report.tuning_records) == SHIFT_THREE_ARMS
    assert tuple(item.arm_id for item in report.retuned_tuning_records) == SHIFT_THREE_ARMS
    assert all(item.evaluated_trial_count == 18 for item in report.tuning_records)
    assert {item.policy_trial_count for item in report.retuned_tuning_records} == {117}
    assert {item.detector_trial_count for item in report.retuned_tuning_records} == {18}
    assert {item.evaluated_candidate_count for item in report.retuned_tuning_records} == {2106}
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
        item.action_sequence
        == (
            "RESET_OLD_REGIME",
            "VERIFY_NEW_EVIDENCE",
            "CONSOLIDATE_NEW_REGIME",
        )
        for item in consolidated
    )
    assert all(
        item.reset_time < item.verification_time < item.consolidation_time for item in consolidated
    )
    assert all(item.change_time_estimate < item.decision_time for item in consolidated)
    assert all(item.reset_time == item.decision_time for item in consolidated)
    assert all(item.posterior_at_decision is not None for item in consolidated)
    assert all(item.verification_evidence is not None for item in consolidated)
    assert all(
        item.verification_evidence.predicate_id == "owner-associated-repeat-object-location@1"
        for item in consolidated
    )
    assert all(hasattr(item, "task_success_proxy") for item in outcomes)
    missed = [
        item for item in outcomes if item.habit_shift_required and not item.consolidation_issued
    ]
    assert missed
    assert all(item.missed_consolidation for item in missed)
    assert all(item.recovery_time_days > 0.0 for item in missed)
    assert all(not item.task_success_proxy for item in missed)


def test_same_timestep_reset_verification_consolidation_tamper_is_rejected(
    completed_report,
):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = payload["test_artifacts"][arm]
    outcome = next(item for item in artifact["outcomes"] if item["consolidation_issued"])
    outcome["consolidation_time"] = outcome["verification_time"]
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="increasing timesteps"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_consolidation_occurs_on_a_real_later_prefix_not_a_synthetic_tick(
    completed_report,
):
    for artifacts in (
        completed_report.test_artifacts,
        completed_report.retuned_test_artifacts,
    ):
        for artifact in artifacts.values():
            prediction_by_id = {item.case_id: item for item in artifact.predictions}
            for outcome in artifact.outcomes:
                if not outcome.consolidation_issued:
                    continue
                assert outcome.consolidation_time in {
                    item.as_of_time for item in prediction_by_id[outcome.case_id].snapshots
                }
                assert (
                    outcome.verification_time == outcome.verification_evidence.second_evidence_time
                )


def test_predictions_intervals_and_cross_track_decision_recompute(completed_report):
    checked = ProjectOneShiftActionDeathTestReport.model_validate_json(
        completed_report.model_dump_json()
    )
    assert len(checked.paired_test_intervals) == 4
    assert len(checked.retuned_paired_test_intervals) == 4
    assert checked.overall_decision.decision in set(ResearchDecision)
    assert len(checked.utility_sensitivity_results) == 8
    assert set(item.value for item in checked.action_policy_baselines) == {
        "never-act",
        "always-reset-verify",
    }
    assert all(
        artifact.metrics.balanced_downstream_action_regret >= 0.0
        for artifact in checked.action_policy_baselines.values()
    )
    assert len(checked.action_baseline_intervals) == 12
    never = checked.action_policy_baselines["never-act"]
    assert all(not item.reset_issued for item in never.outcomes)
    assert all(not item.verification_issued for item in never.outcomes)
    assert all(not item.consolidation_issued for item in never.outcomes)


def test_every_detector_prediction_is_a_monotone_prefix_trajectory(completed_report):
    for ledger in completed_report.validation_prediction_ledgers.values():
        for candidate in ledger.candidates:
            for prediction in candidate.predictions:
                assert len(prediction.snapshots) == 8
                for earlier, later in zip(
                    prediction.snapshots, prediction.snapshots[1:], strict=False
                ):
                    assert earlier.as_of_time < later.as_of_time
                    assert set(earlier.visible_evidence_record_ids) <= set(
                        later.visible_evidence_record_ids
                    )
                assert all(
                    snapshot.change_time_estimate is None
                    or snapshot.change_time_estimate < snapshot.as_of_time
                    for snapshot in prediction.snapshots
                )


def test_validation_candidate_ledger_replays_and_proves_argmin(completed_report):
    report = completed_report
    assert set(report.validation_prediction_ledgers) == set(SHIFT_THREE_ARMS)
    assert all(
        len(ledger.candidates) == 18 for ledger in report.validation_prediction_ledgers.values()
    )
    assert all(item.candidate_ledger_sha256 for item in report.tuning_records)
    assert all(item.candidate_ledger_sha256 for item in report.retuned_tuning_records)

    payload = deepcopy(report.model_dump(mode="json"))
    payload["tuning_records"][0]["selected_candidate_index"] = 1
    _rehash_report(payload)
    with pytest.raises(ValidationError, match=r"argmin|selected candidate"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_input_params_prediction_replay_rejects_self_rehashed_forgery(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    ledger = payload["validation_prediction_ledgers"][arm]
    candidate = ledger["candidates"][0]
    prediction = candidate["predictions"][0]
    snapshot = prediction["snapshots"][0]
    cause = next(iter(snapshot["posterior"]))
    snapshot["posterior"][cause] = 0.0
    candidate["predictions_sha256"] = content_sha256(candidate["predictions"])
    candidate["record_sha256"] = content_sha256(
        {key: value for key, value in candidate.items() if key != "record_sha256"}
    )
    ledger["ledger_sha256"] = content_sha256(
        {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    )
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="do not replay"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_power_uses_frozen_stddev_safety_factor(completed_report):
    for item in (*completed_report.power_analyses, *completed_report.retuned_power_analyses):
        assert item.stddev_safety_factor == 1.5
        assert item.paired_stddev_floor == 0.05
        assert item.powered_paired_stddev == pytest.approx(
            max(item.empirical_paired_stddev * 1.5, 0.05)
        )


def test_action_truth_is_exactly_bound_to_split_input(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = payload["test_artifacts"][arm]
    artifact["case_truths"][0]["model_input_sha256"] = "0" * 64
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    _rehash_report(payload)
    with pytest.raises(ValidationError, match=r"exact input|truth|replay"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_semantic_verification_evidence_forgery_is_rejected_after_rehash(
    completed_report,
):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    artifact, outcome = next(
        (artifact, outcome)
        for artifact in payload["test_artifacts"].values()
        for outcome in artifact["outcomes"]
        if outcome["verification_issued"]
    )
    outcome["verification_evidence"]["location_id"] = "forged-location"
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    _rehash_report(payload)
    with pytest.raises(ValidationError, match=r"exact input|replay"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_utility_sensitivity_tamper_is_rejected(completed_report):
    payload = deepcopy(completed_report.model_dump(mode="json"))
    payload["utility_sensitivity_results"][0]["regret_intervals"][0][
        "difference_joint_minus_reference"
    ] = -0.9
    _rehash_report(payload)
    with pytest.raises(ValidationError, match="utility sensitivity"):
        ProjectOneShiftActionDeathTestReport.model_validate(payload)


def test_prediction_and_interval_tamper_fail_after_rehash(completed_report):
    prediction_payload = deepcopy(completed_report.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = prediction_payload["retuned_test_artifacts"][arm]
    prediction = artifact["predictions"][0]
    snapshot = prediction["snapshots"][0]
    cause = next(iter(snapshot["posterior"]))
    snapshot["posterior"][cause] = 0.0
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


def test_cli_subprocess_writes_a_self_validating_v5_report(tmp_path):
    output = tmp_path / "action-report-v5.json"
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
