from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cpswm.contracts import CandidateKind, EvidenceChannel
from cpswm.system.evaluation_operations.direction_three_controlled_noise import (
    DirectionThreeNoiseConfig,
    apply_direction_three_controlled_noise,
    default_controlled_noise_matrix,
    default_controlled_noise_study,
    run_controlled_noise_benchmark,
    run_controlled_noise_study,
)
from cpswm.system.evaluation_operations.direction_three_oracle_suite import (
    build_oracle_request,
    default_oracle_scenarios,
)


def _identity_probe():
    scenario = next(
        item for item in default_oracle_scenarios() if item.scenario_id == "identity_truth_probe"
    )
    return build_oracle_request(scenario)


def test_controlled_noise_matrix_covers_declared_s3_2_factors():
    ids = {config.condition_id for config in default_controlled_noise_matrix()}
    assert ids == {
        "clean",
        "visual_missing",
        "six_channel_miscalibration",
        "visual_geometry_correlation_discount",
        "identity_noise",
        "actor_noise",
        "event_noise",
        "habit_noise",
        "retrieval_miss_open_set",
        "occlusion_distance_proxy",
    }


def test_missing_channel_becomes_unavailable_not_negative_evidence():
    request, _, target, distractor = _identity_probe()
    noisy = apply_direction_three_controlled_noise(
        request,
        true_target_candidate_id=target,
        distractor_candidate_id=distractor,
        config=DirectionThreeNoiseConfig(
            "visual-missing",
            channel_missing_probability=((EvidenceChannel.VISUAL, 1.0),),
        ),
    )

    assert all(
        candidate.channel_evidence[EvidenceChannel.VISUAL].availability == 0.0
        for candidate in noisy.request.candidates
    )
    assert any(item["operation"] == "channel_missing" for item in noisy.operations)


def test_retrieval_miss_removes_truth_but_retains_explicit_unknown():
    request, _, target, distractor = _identity_probe()
    noisy = apply_direction_three_controlled_noise(
        request,
        true_target_candidate_id=target,
        distractor_candidate_id=distractor,
        config=DirectionThreeNoiseConfig(
            "retrieval-miss",
            retrieval_miss=True,
            unknown_likelihood_scale=10.0,
        ),
    )

    assert target not in {candidate.candidate_id for candidate in noisy.request.candidates}
    assert (
        sum(candidate.kind == CandidateKind.UNKNOWN for candidate in noisy.request.candidates) == 1
    )
    assert not noisy.true_target_was_retrieved


def test_noise_is_deterministic_for_a_fixed_seed():
    request, _, target, distractor = _identity_probe()
    config = DirectionThreeNoiseConfig(
        "stochastic-missing",
        seed=73,
        channel_missing_probability=((EvidenceChannel.VISUAL, 0.5),),
    )

    first = apply_direction_three_controlled_noise(
        request,
        true_target_candidate_id=target,
        distractor_candidate_id=distractor,
        config=config,
    )
    second = apply_direction_three_controlled_noise(
        request,
        true_target_candidate_id=target,
        distractor_candidate_id=distractor,
        config=config,
    )
    assert first == second


def test_controlled_noise_benchmark_reports_calibration_and_support_metrics():
    report = run_controlled_noise_benchmark()

    assert report["condition_count"] == 10
    assert report["case_count"] == 60
    assert all(
        {
            "top1_accuracy",
            "mean_nll",
            "mean_brier",
            "mean_unknown_probability",
            "unified_metrics",
        }
        <= set(condition)
        for condition in report["conditions"]
    )
    clean = next(
        condition for condition in report["conditions"] if condition["condition_id"] == "clean"
    )
    assert clean["unified_metrics"]["retrieval"]["recall_at_1"] == 1.0
    assert clean["unified_metrics"]["open_set"]["unknown_auroc"] == 1.0
    retrieval = next(
        condition
        for condition in report["conditions"]
        if condition["condition_id"] == "retrieval_miss_open_set"
    )
    assert retrieval["support_miss_count"] == 6
    assert report["decision_gates"][0]["status"] == "user_decision_deferred"


def test_controlled_noise_cli_runs_directly():
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            str(repository / ".venv/bin/python"),
            str(repository / "apps/evaluation_runner/run_direction_three_controlled_noise.py"),
        ],
        cwd="/tmp",
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["schema_name"] == "cpswm.DirectionThreeControlledNoiseReport"
    assert report["case_count"] == 60


def test_expanded_study_crosses_severity_seed_and_combination_axes():
    study = default_controlled_noise_study()

    assert len(study) == 63
    assert {condition.severity for condition in study} == {0.25, 0.5, 0.75}
    assert {condition.seed for condition in study} == {11, 29, 47}
    assert "combined_sensing_noise" in {condition.arm_id for condition in study}
    assert "combined_context_noise" in {condition.arm_id for condition in study}


def test_expanded_study_reports_multiseed_intervals_and_probe_strata():
    report = run_controlled_noise_study()

    assert report["condition_count"] == 63
    assert report["case_count"] == 378
    assert report["arm_count"] == 7
    assert len(report["aggregates"]) == 21
    assert len(report["scenario_strata"]) == 126
    assert all(item["seed_count"] == 3 for item in report["aggregates"])
    assert all("top1_accuracy_t95" in item for item in report["aggregates"])
    assert report["decision_gates"][0]["status"] == "user_decision_deferred"


def test_expanded_study_cli_mode_runs_directly():
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            str(repository / ".venv/bin/python"),
            str(repository / "apps/evaluation_runner/run_direction_three_controlled_noise.py"),
            "--expanded-study",
        ],
        cwd="/tmp",
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["schema_name"] == "cpswm.DirectionThreeControlledNoiseStudyReport"
    assert report["case_count"] == 378
