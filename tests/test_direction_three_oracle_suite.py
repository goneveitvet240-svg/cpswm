from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cpswm.contracts import ObservationActionType, RobotActionOutcome
from cpswm.system.evaluation_operations.direction_three_oracle_suite import (
    OracleTruthDimension,
    combination_oracle_scenarios,
    default_oracle_scenarios,
    load_oracle_scenario_manifest,
    oracle_scenario_manifest_payload,
    run_oracle_suite,
)


def test_oracle_suite_covers_complete_s3_1_scenario_semantics():
    report = run_oracle_suite()

    assert report["scenario_count"] == 17
    assert report["summary"]["expected_behavior_met_rate"] == 1.0
    tags = {tag for scenario in report["scenarios"] for tag in scenario["semantic_tags"]}
    assert {
        "multi_person",
        "similar_instances",
        "hidden_event",
        "closed_container",
        "cross_time",
        "unknown",
        "grasp_failed",
        "object_slipped",
        "partial",
        "unknown_outcome",
    } <= tags


def test_oracle_suite_covers_every_verification_action_and_stop():
    report = run_oracle_suite()

    assert set(report["summary"]["action_coverage"]) == {
        *(action.value for action in ObservationActionType),
        "stop_or_abstain",
    }
    stopped = next(
        scenario
        for scenario in report["scenarios"]
        if scenario["scenario_id"] == "stop_without_positive_value"
    )
    assert stopped["termination_reason"] == "no_candidate_observation_action"
    assert stopped["canonical_log_watermark"] == 0


def test_oracle_suite_covers_every_execution_outcome():
    report = run_oracle_suite()

    assert set(report["summary"]["execution_outcome_coverage"]) == {
        outcome.value for outcome in RobotActionOutcome
    }


def test_oracle_suite_injects_each_truth_dimension_independently():
    report = run_oracle_suite()

    assert report["summary"]["oracle_dimension_coverage"] == {
        dimension.value: 1 for dimension in OracleTruthDimension
    }
    probes = [
        scenario
        for scenario in report["scenarios"]
        if scenario["scenario_id"].endswith("_truth_probe")
    ]
    assert len(probes) == 5
    assert all(
        sum(
            dimension["injected_as_decisive_evidence"]
            for dimension in scenario["oracle_truth"].values()
        )
        == 1
        for scenario in probes
    )


def test_not_found_scenario_replans_to_true_target_without_wrong_pickup():
    report = run_oracle_suite()
    scenario = next(
        item
        for item in report["scenarios"]
        if item["scenario_id"] == "not_found_hidden_move_replan"
    )

    assert scenario["execution_outcomes"] == ["not_found", "unknown", "success"]
    assert scenario["selected_target_candidate_id"] == scenario["true_target_candidate_id"]
    assert scenario["task_success"]
    assert not scenario["wrong_object_pickup"]
    # Each grounded execution appends its opportunity and feedback atomically
    # as one transaction, so two search attempts advance the watermark twice.
    assert scenario["canonical_log_watermark"] == 2


def test_unknown_target_abstains_without_canonical_write():
    report = run_oracle_suite()
    scenario = next(
        item for item in report["scenarios"] if item["scenario_id"] == "unknown_unmapped_target"
    )

    assert scenario["resolution_sequence"] == ["unknown"]
    assert scenario["termination_reason"] == "abstained_with_unknown_target"
    assert scenario["selected_target_candidate_id"] is None
    assert scenario["canonical_log_watermark"] == 0


def test_failure_feedback_never_claims_task_success():
    report = run_oracle_suite()
    failures = [
        scenario
        for scenario in report["scenarios"]
        if "failure_feedback" in scenario["semantic_tags"]
    ]

    assert {scenario["scenario_id"] for scenario in failures} == {
        "grasp_failed_feedback",
        "object_slipped_feedback",
        "partial_execution_feedback",
        "unknown_execution_feedback",
    }
    assert all(not scenario["task_success"] for scenario in failures)
    assert all(
        scenario["termination_reason"] == "task_incomplete_feedback_committed"
        for scenario in failures
    )
    assert all(scenario["canonical_log_watermark"] == 1 for scenario in failures)


def test_oracle_scenario_ids_are_frozen_and_unique():
    scenarios = default_oracle_scenarios()
    assert len({scenario.scenario_id for scenario in scenarios}) == len(scenarios)


def test_frozen_manifest_round_trips_the_default_suite(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(oracle_scenario_manifest_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_oracle_scenario_manifest(manifest)
    assert loaded == default_oracle_scenarios()
    assert run_oracle_suite(loaded)["summary"] == run_oracle_suite()["summary"]


def test_repository_manifest_is_the_frozen_default_suite():
    repository = Path(__file__).resolve().parents[1]
    manifest = repository / "configs/direction_three/s3_1_oracle_suite_v0_1.json"

    assert load_oracle_scenario_manifest(manifest) == default_oracle_scenarios()


def test_oracle_suite_cli_runs_directly_and_emits_json():
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            str(repository / ".venv/bin/python"),
            str(repository / "apps/evaluation_runner/run_direction_three_oracle_suite.py"),
        ],
        cwd="/tmp",
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["schema_name"] == "cpswm.DirectionThreeOracleSuiteReport"
    assert report["scenario_count"] == 17


def test_combination_suite_injects_two_three_and_five_truth_dimensions():
    report = run_oracle_suite(combination_oracle_scenarios())

    assert report["scenario_count"] == 3
    injected_counts = [
        sum(truth["injected_as_decisive_evidence"] for truth in scenario["oracle_truth"].values())
        for scenario in report["scenarios"]
    ]
    assert injected_counts == [2, 3, 5]
    assert report["summary"]["expected_behavior_met_rate"] == 1.0
    assert report["summary"]["wrong_object_pickup_rate"] == 0.0


def test_combination_suite_covers_joint_semantic_axes_and_cli():
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            str(repository / ".venv/bin/python"),
            str(repository / "apps/evaluation_runner/run_direction_three_oracle_suite.py"),
            "--combinations",
        ],
        cwd="/tmp",
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    tags = {tag for scenario in report["scenarios"] for tag in scenario["semantic_tags"]}
    assert report["scenario_count"] == 3
    assert {
        "multi_person",
        "similar_instances",
        "hidden_event",
        "closed_container",
        "cross_time",
    } <= tags
