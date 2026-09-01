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
        "retrieval_miss_known_out_of_support",
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
    missing_operations = [
        item for item in noisy.operations if item["operation"] == "channel_missing"
    ]
    assert missing_operations == [
        {
            "operation": "channel_missing",
            "scope": "episode_channel",
            "channel": "visual",
        }
    ]


def test_stochastic_channel_missingness_is_shared_by_every_candidate():
    request, _, target, distractor = _identity_probe()
    noisy = apply_direction_three_controlled_noise(
        request,
        true_target_candidate_id=target,
        distractor_candidate_id=distractor,
        config=DirectionThreeNoiseConfig(
            "episode-channel-missing",
            seed=73,
            channel_missing_probability=((EvidenceChannel.VISUAL, 0.5),),
        ),
    )

    availability = {
        candidate.channel_evidence[EvidenceChannel.VISUAL].availability
        for candidate in noisy.request.candidates
    }
    assert len(availability) == 1


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
            "conditional_top1_accuracy",
            "conditional_mean_nll",
            "conditional_mean_brier",
            "known_target_retrieval_recall",
            "mean_unknown_probability_diagnostic",
            "unified_metrics",
        }
        <= set(condition)
        for condition in report["conditions"]
    )
    clean = next(
        condition for condition in report["conditions"] if condition["condition_id"] == "clean"
    )
    assert clean["unified_metrics"]["conditional_fusion"]["recall_at_1"] == 1.0
    assert clean["unified_metrics"]["open_set"]["unknown_auroc"] == 1.0
    retrieval = next(
        condition
        for condition in report["conditions"]
        if condition["condition_id"] == "retrieval_miss_known_out_of_support"
    )
    assert retrieval["support_miss_count"] == 5
    assert retrieval["known_target_retrieval_recall"] == 0.0
    assert retrieval["conditional_fusion_case_count"] == 1
    assert retrieval["unified_metrics"]["open_set"] == {
        "unknown_auroc": None,
        "unknown_auprc": None,
    }
    support_misses = [
        case
        for case in report["cases"]
        if case["condition_id"] == "retrieval_miss_known_out_of_support"
        and case["support_status"] == "known_out_of_support"
    ]
    assert len(support_misses) == 5
    assert all(case["top1_correct"] is None for case in support_misses)
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

    assert len(study) == 33
    assert {condition.severity for condition in study} == {0.25, 0.5, 0.75}
    assert {
        condition.seed
        for condition in study
        if condition.replication_kind == "stochastic_seed_replicate"
    } == {11, 29, 47}
    assert all(
        condition.seed == 0
        for condition in study
        if condition.replication_kind == "deterministic_sensitivity"
    )
    assert "combined_sensing_noise" in {condition.arm_id for condition in study}
    assert "combined_context_noise" in {condition.arm_id for condition in study}


def test_expanded_study_reports_multiseed_intervals_and_probe_strata():
    report = run_controlled_noise_study()

    assert report["condition_count"] == 33
    assert report["case_count"] == 198
    assert report["arm_count"] == 7
    assert len(report["aggregates"]) == 21
    assert len(report["scenario_strata"]) == 126
    assert report["stochastic_configuration_count"] == 18
    assert report["deterministic_configuration_count"] == 15
    stochastic = [
        item
        for item in report["aggregates"]
        if item["replication_kind"] == "stochastic_seed_replicate"
    ]
    deterministic = [
        item
        for item in report["aggregates"]
        if item["replication_kind"] == "deterministic_sensitivity"
    ]
    assert all(item["run_count"] == 3 for item in stochastic)
    assert all(item["run_count"] == 1 for item in deterministic)
    assert all(item["top1_accuracy"]["upper"] <= 1.0 for item in stochastic)
    assert all(item["top1_accuracy"]["lower"] >= 0.0 for item in stochastic)
    assert all(item["top1_accuracy"]["lower"] is None for item in deterministic)
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
    assert report["case_count"] == 198
