from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import EvidenceChannel
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
from cpswm.system.evaluation_operations.direction_three_prediction_cache import (
    DirectionThreeCachedPrediction,
    DirectionThreePredictionCache,
    build_direction_three_prediction_cache,
    read_direction_three_prediction_cache,
    write_direction_three_prediction_cache,
)
from cpswm.system.reproducibility import content_sha256


def _dataset(split: DirectionThreeDatasetSplit = DirectionThreeDatasetSplit.TRAIN):
    episode_id = uuid4()
    target = uuid4()
    unknown = uuid4()
    episode = DirectionThreeVisibleEpisode(
        episode_id=episode_id,
        source_name="fixture",
        source_version="fixture@0.1",
        split=split,
        split_group_id=f"group-{split.value}",
        scene_id=f"scene-{split.value}",
        household_id=f"household-{split.value}",
        session_id=f"session-{split.value}",
        trajectory_id=f"trajectory-{split.value}",
        video_id=f"video-{split.value}",
        frame_start=0,
        frame_end=20,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        object_instance_ids=(str(target),),
        query_text="find it",
        candidate_ids=(target, unknown),
        unknown_candidate_id=unknown,
        channel_availability=DirectionThreeChannelAvailability(
            available={channel: True for channel in EvidenceChannel}
        ),
    )
    truth = DirectionThreeEvaluatorTruth(
        episode_id=episode_id,
        source_hash="source-hash",
        true_target_candidate_id=target,
        truth_by_dimension={dimension: "fixture" for dimension in DirectionThreeTruthDimension},
    )
    entry = DirectionThreeDatasetEntry(
        episode_id=episode_id,
        split=split,
        split_group_id=episode.split_group_id,
        scene_id=episode.scene_id,
        household_id=episode.household_id,
        trajectory_id=episode.trajectory_id,
        video_id=episode.video_id,
        frame_start=episode.frame_start,
        frame_end=episode.frame_end,
        source_hash=truth.source_hash,
        visible_content_hash=content_sha256(episode),
        evaluator_content_hash=content_sha256(truth.model_dump(mode="python")),
    )
    dataset = DirectionThreeEpisodeDataset(
        manifest=DirectionThreeDatasetManifest(
            dataset_name="fixture",
            source_name="fixture",
            source_version="fixture@0.1",
            entries=(entry,),
        ),
        episodes=(episode,),
        evaluator_store=(truth,),
    )
    return dataset, episode, target


def _prediction(
    episode: DirectionThreeVisibleEpisode,
    candidate_id: UUID,
) -> DirectionThreeCachedPrediction:
    return DirectionThreeCachedPrediction(
        episode_id=episode.episode_id,
        split=episode.split,
        visible_content_hash=content_sha256(episode),
        frame_index=3,
        candidate_id=candidate_id,
        channel=EvidenceChannel.VISUAL,
        likelihood_given_candidate=0.8,
        reliability=0.9,
        availability=1.0,
        identity_embedding=(0.1, 0.2),
        reid_score=0.85,
        visibility=0.7,
        miss_likelihood=0.1,
        evidence_refs=("video:frame:3",),
        model_version="visual-fixture@0.1",
        calibration_domain="fixture-household",
        input_content_hash="frame-sha256",
    )


def _cache():
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target)
    cache = build_direction_three_prediction_cache(
        dataset,
        split=DirectionThreeDatasetSplit.TRAIN,
        records=(prediction,),
        model_versions={EvidenceChannel.VISUAL: prediction.model_version},
        calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
        inference_config_hash="config-sha256",
    )
    return dataset, episode, prediction, cache


def test_cache_round_trip_is_content_bound_and_truth_free(tmp_path: Path):
    _, _, prediction, cache = _cache()
    path = tmp_path / "predictions.json"

    write_direction_three_prediction_cache(cache, path)
    loaded = read_direction_three_prediction_cache(path)

    assert loaded == cache
    assert loaded.records == (prediction,)
    assert "true_target_candidate_id" not in path.read_text(encoding="utf-8")


def test_cache_rejects_truth_fields_at_the_public_boundary():
    _, episode, target = _dataset()
    payload = _prediction(episode, target).model_dump(mode="python")
    payload["true_target_candidate_id"] = target

    with pytest.raises(ValueError, match="Extra inputs"):
        DirectionThreeCachedPrediction.model_validate(payload)


def test_cache_rejects_cross_split_prediction():
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target).model_copy(
        update={"split": DirectionThreeDatasetSplit.TEST}
    )

    with pytest.raises(ValueError, match="crosses the cache split boundary"):
        build_direction_three_prediction_cache(
            dataset,
            split=DirectionThreeDatasetSplit.TRAIN,
            records=(prediction,),
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
        )


def test_cache_rejects_model_or_calibration_manifest_drift():
    _, _, _, cache = _cache()
    bad_manifest = cache.manifest.model_copy(
        update={"model_versions": {EvidenceChannel.VISUAL: "other-model"}}
    )

    with pytest.raises(ValueError, match="model version"):
        DirectionThreePredictionCache(manifest=bad_manifest, records=cache.records)


def test_cache_rejects_record_tampering():
    _, _, prediction, cache = _cache()
    tampered = prediction.model_copy(update={"likelihood_given_candidate": 0.2})

    with pytest.raises(ValueError, match="content hash"):
        DirectionThreePredictionCache(manifest=cache.manifest, records=(tampered,))


def test_identity_outputs_are_restricted_to_visual_channel():
    _, episode, target = _dataset()
    payload = _prediction(episode, target).model_dump(mode="python")
    payload["channel"] = EvidenceChannel.GEOMETRY

    with pytest.raises(ValueError, match="visual evidence only"):
        DirectionThreeCachedPrediction.model_validate(payload)


def test_cache_refuses_overwrite_without_force(tmp_path: Path):
    _, _, _, cache = _cache()
    path = tmp_path / "predictions.json"
    write_direction_three_prediction_cache(cache, path)

    with pytest.raises(FileExistsError, match="--force"):
        write_direction_three_prediction_cache(cache, path)
