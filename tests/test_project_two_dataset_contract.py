from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayStep
from cpswm.system.evaluation_operations.project_two_dataset import (
    ProjectTwoReplayGateError,
    audit_project_two_replay,
    enforce_project_two_replay_gate,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)


def _dataset():
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=5
    ).build()


def test_d0_contract_keeps_truth_in_separate_store():
    dataset = _dataset()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    assert not hasattr(episode, "truth_by_step")
    assert dataset.truth_for(episode.episode_id).truth_by_step
    assert "true_actor" not in episode.model_dump_json()


def test_attempted_and_observed_destination_are_not_interchangeable():
    step = _dataset().episodes[0].steps[0]
    other = uuid4()
    with pytest.raises(ValidationError, match="observed destination"):
        ProjectTwoReplayStep.model_validate(
            {**step.model_dump(), "observed_destination_location_id": other}
        )


def test_duplicate_feedback_record_is_rejected():
    dataset = _dataset()
    episode = dataset.episodes[0]
    source = next(step for step in episode.steps if step.execution_feedback)
    duplicate = source.model_copy(
        update={
            "step_id": episode.steps[-1].step_id,
            "timestamp": episode.steps[-1].timestamp,
            "valid_time": episode.steps[-1].valid_time,
        }
    )
    with pytest.raises(ValidationError, match="duplicate execution feedback"):
        type(episode).model_validate(
            {**episode.model_dump(), "steps": (*episode.steps[:-1], duplicate)}
        )


def test_delayed_feedback_keeps_original_time_order():
    dataset = _dataset()
    episode = dataset.episodes[0]
    timestamps = [step.timestamp for step in episode.steps]
    assert timestamps == sorted(timestamps)
    assert any(
        feedback.metadata.recorded_time > step.timestamp
        for step in episode.steps
        for feedback in step.execution_feedback
    )


def test_quality_report_declares_missing_real_fields_without_deleting_capability():
    report = audit_project_two_replay(_dataset())
    assert report.missingness_counts["real_sensor_calibration"] > 0
    assert report.delayed_feedback_count > 0
    assert "source_label_leakage" in report.checks_passed


def test_d0_replay_passes_hard_safety_and_content_gate():
    report = enforce_project_two_replay_gate(_dataset())
    assert report.ready
    assert not report.failures
    assert "visible_content_integrity" in report.checks_passed
    assert "evaluator_content_integrity" in report.checks_passed


def test_quality_gate_is_not_a_cosmetic_list_of_check_names():
    dataset = _dataset()
    episode = dataset.episodes[0]
    broken = episode.model_copy(update={"field_availability": {}})
    tampered = dataset.model_copy(update={"episodes": (broken, *dataset.episodes[1:])})
    with pytest.raises(ProjectTwoReplayGateError, match="missingness declaration"):
        enforce_project_two_replay_gate(tampered)
