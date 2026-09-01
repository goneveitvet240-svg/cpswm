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
    session: str | None = None,
    object_instance_ids: tuple[str, ...] | None = None,
    source_record_refs: tuple[str, ...] = (),
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
        session_id=session or f"session-{episode_id}",
        trajectory_id=trajectory,
        video_id=video,
        frame_start=frame_start,
        frame_end=frame_start + 20,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        object_instance_ids=object_instance_ids or (str(target),),
        query_text="find the personalized object",
        candidate_ids=(target, unknown),
        unknown_candidate_id=unknown,
        channel_availability=DirectionThreeChannelAvailability(
            available={channel: True for channel in EvidenceChannel}
        ),
        observation_action=ObservationActionType.MICRO_VERIFY,
        observation_outcome="target_signal",
        observation_selection_probability=1.0,
        source_record_refs=source_record_refs,
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
            source_record_refs=episode.source_record_refs,
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


def test_split_gate_rejects_same_session_across_splits():
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
        session="shared-session",
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="trajectory-b",
        video="video-b",
        frame_start=500,
        session="shared-session",
    )

    with pytest.raises(ValueError, match="session_id leakage"):
        _dataset((first, second))


def test_split_gate_rejects_overlapping_object_instances_across_splits():
    shared_object = "object-instance-shared"
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
        object_instance_ids=(shared_object, "object-train"),
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="trajectory-b",
        video="video-b",
        frame_start=500,
        object_instance_ids=(shared_object, "object-test"),
    )

    with pytest.raises(ValueError, match="object_instance_ids leakage"):
        _dataset((first, second))


def test_split_gate_rejects_shared_source_record_across_splits():
    first = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
        source_record_refs=("findingdory:row:41",),
    )
    second = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TEST,
        split_group="test-a",
        trajectory="trajectory-b",
        video="video-b",
        frame_start=500,
        source_record_refs=("findingdory:row:41",),
    )

    with pytest.raises(ValueError, match="source_record_refs leakage"):
        _dataset((first, second))


@pytest.mark.parametrize(
    "field",
    ("source_name", "source_version", "session_id", "object_instance_ids", "source_record_refs"),
)
def test_manifest_lineage_binds_session_objects_and_source(field: str):
    episode = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
        source_record_refs=("findingdory:row:41",),
    )
    dataset = _dataset((episode,))
    entry = dataset.manifest.entries[0]
    replacement: object = (
        ("tampered",) if field.endswith("ids") or field.endswith("refs") else "tampered"
    )
    tampered_entry = entry.model_copy(update={field: replacement})
    tampered_manifest = dataset.manifest.model_copy(update={"entries": (tampered_entry,)})

    with pytest.raises(ValueError, match="manifest lineage"):
        DirectionThreeEpisodeDataset(
            manifest=tampered_manifest,
            episodes=dataset.episodes,
            evaluator_store=dataset.evaluator_store,
        )


@pytest.mark.parametrize("field", ("source_name", "source_version"))
def test_dataset_manifest_binds_declared_source_to_visible_episodes(field: str):
    episode = _visible(
        episode_id=uuid4(),
        split=DirectionThreeDatasetSplit.TRAIN,
        split_group="train-a",
        trajectory="trajectory-a",
        video="video-a",
        frame_start=0,
    )
    dataset = _dataset((episode,))
    tampered_manifest = dataset.manifest.model_copy(update={field: "different-source"})

    with pytest.raises(ValueError, match=f"source {field.removeprefix('source_')}"):
        DirectionThreeEpisodeDataset(
            manifest=tampered_manifest,
            episodes=dataset.episodes,
            evaluator_store=dataset.evaluator_store,
        )


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
