from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import EvidenceChannel, ObservationActionType, RobotActionOutcome
from cpswm.system.evaluation_operations.direction_three_dataset import (
    DIRECTION_THREE_DATASET_VERSION,
    DirectionThreeChannelAvailability,
    DirectionThreeDatasetEntry,
    DirectionThreeDatasetManifest,
    DirectionThreeDatasetSplit,
    DirectionThreeEpisodeDataset,
    DirectionThreeEvaluatorTruth,
    DirectionThreeTruthDimension,
    DirectionThreeVisibleEpisode,
    audit_direction_three_dataset,
)
from cpswm.system.reproducibility import content_sha256


def _visible(
    *,
    episode_id: UUID,
    split: DirectionThreeDatasetSplit,
    split_group: str,
    trajectory: str,
    video: str,
    frame_start: int,
) -> DirectionThreeVisibleEpisode:
    unknown = uuid4()
    target = uuid4()
    return DirectionThreeVisibleEpisode(
        episode_id=episode_id,
        source_name="fixture",
        source_version="fixture@0.1",
        split=split,
        split_group_id=split_group,
        scene_id=f"scene-{split_group}",
        household_id=f"household-{split_group}",
        session_id=f"session-{episode_id}",
        trajectory_id=trajectory,
        video_id=video,
        frame_start=frame_start,
        frame_end=frame_start + 20,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        object_instance_ids=(str(target),),
        query_text="find the personalized object",
        candidate_ids=(target, unknown),
        unknown_candidate_id=unknown,
        channel_availability=DirectionThreeChannelAvailability(
            available={channel: True for channel in EvidenceChannel}
        ),
        observation_action=ObservationActionType.MICRO_VERIFY,
        observation_outcome="target_signal",
        observation_selection_probability=1.0,
    )


def _truth(episode: DirectionThreeVisibleEpisode) -> DirectionThreeEvaluatorTruth:
    target = next(
        candidate
        for candidate in episode.candidate_ids
        if candidate != episode.unknown_candidate_id
    )
    return DirectionThreeEvaluatorTruth(
        episode_id=episode.episode_id,
        source_hash=f"source:{episode.episode_id}",
        true_target_candidate_id=target,
        truth_by_dimension={
            dimension: f"{dimension.value}:{target}" for dimension in DirectionThreeTruthDimension
        },
        expected_terminal_outcome=RobotActionOutcome.SUCCESS,
    )


def _dataset(episodes: tuple[DirectionThreeVisibleEpisode, ...]) -> DirectionThreeEpisodeDataset:
    truths = tuple(_truth(episode) for episode in episodes)
    truth_by_id = {truth.episode_id: truth for truth in truths}
    entries = tuple(
        DirectionThreeDatasetEntry(
            episode_id=episode.episode_id,
            split=episode.split,
            split_group_id=episode.split_group_id,
            scene_id=episode.scene_id,
            household_id=episode.household_id,
            trajectory_id=episode.trajectory_id,
            video_id=episode.video_id,
            frame_start=episode.frame_start,
            frame_end=episode.frame_end,
            source_hash=truth_by_id[episode.episode_id].source_hash,
            visible_content_hash=content_sha256(episode),
            evaluator_content_hash=content_sha256(
                truth_by_id[episode.episode_id].model_dump(mode="python")
            ),
        )
        for episode in episodes
    )
    return DirectionThreeEpisodeDataset(
        manifest=DirectionThreeDatasetManifest(
            dataset_name="direction-three-fixture",
            source_name="fixture",
            source_version="fixture@0.1",
            entries=entries,
        ),
        episodes=episodes,
        evaluator_store=truths,
    )


def test_direction_three_dataset_separates_visible_data_from_evaluator_truth():
    episode = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    dataset = _dataset((episode,))

    forbidden = {
        "true_target_candidate_id",
        "target_is_unknown",
        "truth_by_dimension",
        "expected_terminal_outcome",
    }
    assert forbidden.isdisjoint(DirectionThreeVisibleEpisode.model_fields)
    assert dataset.visible_episodes(DirectionThreeDatasetSplit.TRAIN) == (episode,)
    assert dataset.truth_for(episode.episode_id).true_target_candidate_id is not None


def test_direction_three_episode_requires_all_six_channel_availability_flags():
    with pytest.raises(ValueError, match="all six channels"):
        DirectionThreeChannelAvailability(available={EvidenceChannel.VISUAL: True})


def test_direction_three_episode_requires_explicit_unknown_candidate():
    episode = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    with pytest.raises(ValueError, match="explicit unknown"):
        DirectionThreeVisibleEpisode.model_validate(
            episode.model_copy(update={"candidate_ids": (uuid4(), uuid4())}).model_dump()
        )


def test_observation_logging_requires_selection_probability():
    episode = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    with pytest.raises(ValueError, match="selection probability"):
        DirectionThreeVisibleEpisode.model_validate(
            episode.model_copy(update={"observation_selection_probability": None}).model_dump()
        )


def test_direction_three_truth_requires_all_five_dimensions():
    with pytest.raises(ValueError, match="all five"):
        DirectionThreeEvaluatorTruth(
            episode_id=uuid4(),
            source_hash="source",
            target_is_unknown=True,
            truth_by_dimension={DirectionThreeTruthDimension.IDENTITY: "object-a"},
        )


def test_split_gate_rejects_same_household_scene_time_group_across_splits():
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="shared",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="shared",
        trajectory="trajectory-b",
        video="video-b",
        frame_start=500,
    )
    with pytest.raises(ValueError, match="household_id leakage"):
        _dataset((first, second))


def test_split_gate_rejects_same_object_trajectory_across_splits():
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="shared-trajectory",
        video="video-a",
        frame_start=0,
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="shared-trajectory",
        video="video-b",
        frame_start=500,
    )
    with pytest.raises(ValueError, match="trajectory_id leakage"):
        _dataset((first, second))


def test_split_gate_rejects_adjacent_video_segments_across_splits():
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="shared-video",
        frame_start=0,
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="trajectory-b",
        video="shared-video",
        frame_start=100,
    )
    with pytest.raises(ValueError, match="adjacent video leakage"):
        _dataset((first, second))


def test_split_gate_allows_isolated_sources_and_audit_reports_coverage():
    train = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    test = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="trajectory-b",
        video="video-b",
        frame_start=500,
    )
    dataset = _dataset((train, test))
    audit = audit_direction_three_dataset(dataset)

    assert audit.dataset_version == DIRECTION_THREE_DATASET_VERSION
    assert audit.episode_count == 2
    assert audit.split_counts == {
        DirectionThreeDatasetSplit.TRAIN: 1,
        DirectionThreeDatasetSplit.TEST: 1,
    }
    assert all(value == 2 for value in audit.channel_available_counts.values())
    assert audit.ready
