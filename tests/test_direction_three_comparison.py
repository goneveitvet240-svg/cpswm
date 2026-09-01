from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import EvidenceChannel, ResolutionStatus
from cpswm.system.evaluation_operations.direction_three_comparison import (
    DirectionThreeComparisonBudget,
    DirectionThreeMethodDeclaration,
    DirectionThreeMethodEpisodeOutput,
    DirectionThreeMethodRun,
    validate_matched_direction_three_runs,
)
from cpswm.system.evaluation_operations.direction_three_dataset import (
    DirectionThreeChannelAvailability,
    DirectionThreeDatasetEntry,
    DirectionThreeDatasetManifest,
    DirectionThreeDatasetSplit,
    DirectionThreeEpisodeDataset,
    DirectionThreeEvaluatorTruth,
    DirectionThreeTruthDimension,
    DirectionThreeVisibleEpisode,
)
from cpswm.system.reproducibility import content_sha256


def _dataset():
    target, unknown = uuid4(), uuid4()
    episode = DirectionThreeVisibleEpisode(
        episode_id=uuid4(),
        source_name="shared-evaluation-fixture",
        source_version="fixture@0.1",
        split=DirectionThreeDatasetSplit.TEST,
        split_group_id="test-group",
        scene_id="test-scene",
        household_id="test-household",
        session_id="test-session",
        trajectory_id="test-trajectory",
        video_id="test-video",
        frame_start=0,
        frame_end=20,
        timestamp=datetime(2026, 8, 26, tzinfo=UTC),
        object_instance_ids=(str(target),),
        query_text="find my usual bedside object",
        candidate_ids=(target, unknown),
        unknown_candidate_id=unknown,
        channel_availability=DirectionThreeChannelAvailability(
            available={channel: True for channel in EvidenceChannel}
        ),
    )
    truth = DirectionThreeEvaluatorTruth(
        episode_id=episode.episode_id,
        source_hash="shared-source-hash",
        true_target_candidate_id=target,
        truth_by_dimension={
            dimension: f"{dimension.value}:{target}" for dimension in DirectionThreeTruthDimension
        },
    )
    entry = DirectionThreeDatasetEntry(
        episode_id=episode.episode_id,
        source_name=episode.source_name,
        source_version=episode.source_version,
        split=episode.split,
        split_group_id=episode.split_group_id,
        scene_id=episode.scene_id,
        household_id=episode.household_id,
        session_id=episode.session_id,
        trajectory_id=episode.trajectory_id,
        video_id=episode.video_id,
        frame_start=episode.frame_start,
        frame_end=episode.frame_end,
        object_instance_ids=episode.object_instance_ids,
        source_hash=truth.source_hash,
        visible_content_hash=content_sha256(episode),
        evaluator_content_hash=content_sha256(truth.model_dump(mode="python")),
    )
    dataset = DirectionThreeEpisodeDataset(
        manifest=DirectionThreeDatasetManifest(
            dataset_name="shared-evaluation-fixture",
            source_name=episode.source_name,
            source_version=episode.source_version,
            entries=(entry,),
        ),
        episodes=(episode,),
        evaluator_store=(truth,),
    )
    return dataset, episode, target, unknown


def _budget() -> DirectionThreeComparisonBudget:
    return DirectionThreeComparisonBudget(
        max_observation_actions=4,
        max_execution_actions=2,
        max_path_length_m=20.0,
        max_elapsed_seconds=120.0,
        allowed_observation_actions=(),
        cost_weights={
            "motion": 1.0,
            "time": 1.0,
            "interruption": 1.0,
            "privacy": 1.0,
            "safety": 1.0,
        },
    )


def _run(method_id: str, *, probabilistic: bool) -> DirectionThreeMethodRun:
    dataset, episode, target, unknown = _dataset_for_runs
    posterior = {target: 0.8, unknown: 0.2} if probabilistic else None
    return DirectionThreeMethodRun(
        dataset_manifest_hash=content_sha256(dataset.manifest),
        evaluation_split=DirectionThreeDatasetSplit.TEST,
        method=DirectionThreeMethodDeclaration(
            method_id=method_id,
            method_family="external-memory" if not probabilistic else "six-channel-fusion",
            external_system=not probabilistic,
            code_version=f"{method_id}@0.1",
            input_channels=tuple(EvidenceChannel),
            model_versions={"method": f"{method_id}@0.1"},
            supports_active_verification=True,
            produces_normalized_posterior=probabilistic,
            tuning_splits=(DirectionThreeDatasetSplit.CALIBRATION,),
        ),
        budget=_budget(),
        outputs=(
            DirectionThreeMethodEpisodeOutput(
                episode_id=episode.episode_id,
                visible_content_hash=content_sha256(episode),
                candidate_ranking=(target, unknown),
                posterior_by_candidate_id=posterior,
                resolution_status=ResolutionStatus.RESOLVED,
                selected_target_candidate_id=target,
                observation_actions_used=1,
                execution_actions_used=1,
                path_length_m=3.0,
                elapsed_seconds=12.0,
                costs={
                    "motion": 3.0,
                    "time": 12.0,
                    "interruption": 0.0,
                    "privacy": 0.0,
                    "safety": 0.0,
                },
                source_output_sha256=("a" if probabilistic else "b") * 64,
            ),
        ),
    )


_dataset_for_runs = _dataset()


def test_matched_comparison_accepts_internal_and_external_outputs_on_one_surface():
    dataset, episode, _target, _unknown = _dataset_for_runs
    audit = validate_matched_direction_three_runs(
        dataset,
        (_run("full-s3", probabilistic=True), _run("external-a", probabilistic=False)),
    )

    assert audit.comparable
    assert audit.episode_ids == (episode.episode_id,)
    assert audit.posterior_metric_eligible_method_ids == ("full-s3",)
    assert "same_action_and_cost_budget" in audit.checks_passed


def test_comparison_rejects_unequal_budget():
    dataset, _episode, _target, _unknown = _dataset_for_runs
    external = _run("external-a", probabilistic=False)
    external = external.model_copy(
        update={"budget": external.budget.model_copy(update={"max_observation_actions": 5})}
    )

    with pytest.raises(ValueError, match="identical action and cost budget"):
        validate_matched_direction_three_runs(
            dataset, (_run("full-s3", probabilistic=True), external)
        )


def test_comparison_rejects_candidate_support_injection():
    dataset, _episode, _target, _unknown = _dataset_for_runs
    external = _run("external-a", probabilistic=False)
    forged_output = external.outputs[0].model_copy(
        update={"candidate_ranking": (*external.outputs[0].candidate_ranking, uuid4())}
    )
    external = external.model_copy(update={"outputs": (forged_output,)})

    with pytest.raises(ValueError, match="outside shared support"):
        validate_matched_direction_three_runs(
            dataset, (_run("full-s3", probabilistic=True), external)
        )


def test_method_contract_forbids_evaluator_truth_access_and_test_tuning():
    common = dict(
        method_id="leaky",
        method_family="invalid",
        external_system=True,
        code_version="leaky@0.1",
        input_channels=(),
        model_versions={},
        supports_active_verification=False,
        produces_normalized_posterior=False,
    )
    with pytest.raises(ValidationError, match="evaluator-only truth"):
        DirectionThreeMethodDeclaration(
            **common,
            tuning_splits=(DirectionThreeDatasetSplit.CALIBRATION,),
            evaluator_truth_accessed=True,
        )
    with pytest.raises(ValidationError, match="sealed test"):
        DirectionThreeMethodDeclaration(
            **common,
            tuning_splits=(DirectionThreeDatasetSplit.TEST,),
        )
