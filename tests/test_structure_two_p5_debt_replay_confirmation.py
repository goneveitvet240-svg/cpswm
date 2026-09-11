from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations import (
    structure_two_p5_debt_replay_confirmation as replay_module,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_debt_replay_confirmation import (
    CLAIM_BOUNDARY,
    PROTOCOL_ID,
    _load_config,
    _new_system,
    compare_positive_transition,
    verify_p5_debt_replay_confirmation,
)
from cpswm.system.evaluation_operations.structure_two_p5_direct_trace_probe import (
    _ProbeTraceSink,
    _router_features,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _ciav_input,
    _episode_schedule_commitment,
    _packet_for_step,
    _transition,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _load_config as _load_retained_config,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext

ROOT = Path(__file__).resolve().parents[1]


def test_replay_config_is_engineering_only_and_keeps_coverage_limits_explicit() -> None:
    config = _load_config(ROOT)
    assert config["protocol_id"] == PROTOCOL_ID
    assert config["claim_boundary"] == CLAIM_BOUNDARY
    assert config["test_reuse_disclosure"] == {
        "engineering_confirmation_only": True,
        "confirmatory": False,
        "fresh_preregistered_death_test": False,
        "may_issue_positive_scientific_receipt": False,
    }
    assert all(value is False for value in config["coverage_limits"].values())
    assert config["execution"]["evaluator_truth_accessed"] is False


def test_one_positive_transition_matches_direct_and_production_debt_replay() -> None:
    retained = _load_retained_config(ROOT)
    dataset = (
        D0SyntheticReplayExperimentConfig.load(ROOT / Path(retained["dataset_source"]))
        .build_adapter()
        .build()
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    index, step = next(
        (index, step) for index, step in enumerate(episode.steps) if step.after is not None
    )
    packet = _packet_for_step(
        episode,
        step,
        schedule_commitment_sha256=_episode_schedule_commitment(episode),
    )
    row = compare_positive_transition(
        direct_system=_new_system(episode),
        replay_system=_new_system(episode),
        episode=episode,
        step=step,
        original_step_index=index,
        packet=packet,
        absolute_tolerance=1e-12,
    )

    assert all(row["checks"].values())
    assert row["direct_put_back_location_id"] == row["replay_put_back_location_id"]
    assert (
        row["direct_owner_habit_location_distribution"]
        == row["replay_owner_habit_location_distribution"]
    )


def test_different_location_feedback_has_representable_time_and_replays() -> None:
    retained = _load_retained_config(ROOT)
    dataset = (
        D0SyntheticReplayExperimentConfig.load(ROOT / Path(retained["dataset_source"]))
        .build_adapter()
        .build()
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    index, step = next(
        (index, step) for index, step in enumerate(episode.steps) if step.after is not None
    )
    packet = _packet_for_step(
        episode,
        step,
        schedule_commitment_sha256=_episode_schedule_commitment(episode),
    )
    transition = _transition(episode, step, index)
    locations = _locations(episode)
    base = _ciav_input(packet, episode, step, locations)
    different_location = next(
        location for location in locations if location != base.expected_detected_location_id
    )
    ciav_input = replace(base, expected_detected_location_id=different_location)

    direct = _new_system(episode)
    direct_sink = _ProbeTraceSink()
    direct_result = direct.process_evaluation_direct_p5_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_router_features(direct),
            step_index=index,
            debt_expiry_steps=1,
            ciav_input=ciav_input,
        ),
        trace_sink=direct_sink,
    )

    replay = _new_system(episode)
    p0_result = replay.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_router_features(replay),
            step_index=2 * index,
            debt_expiry_steps=1,
            ciav_input=ciav_input,
        ),
        trace_sink=_ProbeTraceSink(),
    )
    debt = p0_result.debt_certificates[0]
    replay_sink = _ProbeTraceSink()
    replay_result = replay.replay_adaptive_debt(
        debt.debt_id,
        step_index=2 * index + 1,
        ciav_input=ciav_input,
        trace_sink=replay_sink,
    )

    assert direct_sink.trace is not None
    assert replay_sink.trace is not None
    assert direct_sink.trace.feedback_closure_kind == "full_transition"
    assert replay_sink.trace.feedback_closure_kind == "full_transition"
    assert direct_result.feedback_result is not None
    assert replay_result.feedback_result is not None
    assert replay_result.ciav_receipt is not None
    assert replay_result.ciav_receipt.detection.detected_location_id == different_location
    assert replay.pending_adaptive_debts() == ()


def test_artifact_numeric_forgery_fails_fresh_recomputation(monkeypatch) -> None:
    retained = {
        "schema_version": replay_module.SCHEMA_VERSION,
        "evidence_context": replay_module.current_evidence_context(),
        "protocol_id": PROTOCOL_ID,
        "status": "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_binding": replay_module._source_binding(
            ROOT,
            replay_module._load_config(ROOT),
        ),
        "data_scope": {
            "evaluator_truth_access_count": 0,
            "positive_transition_count": 1,
        },
        "equivalence_audit": {
            "all_required_checks_passed": True,
            "failed_transition_count": 0,
        },
        "search_or_put_back_scientific_signal_retested": False,
        "retained_v0_1_failure_overwritten": False,
        "positive_scientific_receipt_issued": False,
        "adaptive_router_calibration_validated": False,
        "task_7_8_9_passed": False,
        "external_validity_established": False,
    }
    retained["content_sha256"] = content_sha256(retained)
    forged = copy.deepcopy(retained)
    forged["data_scope"]["positive_transition_count"] += 1
    forged["content_sha256"] = content_sha256(
        {key: value for key, value in forged.items() if key != "content_sha256"}
    )
    monkeypatch.setattr(
        replay_module,
        "run_p5_debt_replay_confirmation",
        lambda *, repository_root: retained,
    )

    with pytest.raises(ValueError, match="fresh P5 debt-replay recomputation disagrees"):
        verify_p5_debt_replay_confirmation(
            forged,
            repository_root=ROOT,
            fresh_recompute=True,
        )


def test_artifact_verifier_rejects_hash_only_verification() -> None:
    with pytest.raises(ValueError, match="requires fresh recomputation"):
        verify_p5_debt_replay_confirmation(
            {},
            repository_root=ROOT,
            fresh_recompute=False,
        )
