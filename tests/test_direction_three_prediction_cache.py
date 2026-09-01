from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import EvidenceChannel
from cpswm.system.attestation import Ed25519AttestationSigner
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
    DirectionThreeFrameContentBinding,
    DirectionThreeFrameContentManifest,
    DirectionThreePredictionCache,
    build_direction_three_prediction_cache,
    issue_direction_three_frame_manifest,
    read_direction_three_prediction_cache,
    write_direction_three_prediction_cache,
)
from cpswm.system.evaluation_operations.raw_data_signatures import sign_raw_data_file
from cpswm.system.reproducibility import content_sha256

FRAME_SIGNER = Ed25519AttestationSigner.generate(key_id="direction-three-frame-test")
FRAME_VERIFIER = FRAME_SIGNER.verifier()
RAW_SIGNER = Ed25519AttestationSigner.generate(key_id="direction-three-raw-test")
RAW_VERIFIER = RAW_SIGNER.verifier()
RAW_FRAME_BYTES = b"encoded-frame"
DECODED_FRAME_BYTES = b"decoded-frame"
RAW_FRAME_HASH = hashlib.sha256(RAW_FRAME_BYTES).hexdigest()
DECODED_FRAME_HASH = hashlib.sha256(DECODED_FRAME_BYTES).hexdigest()


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
        source_name=episode.source_name,
        source_version=episode.source_version,
        split=split,
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
        input_content_hash=DECODED_FRAME_HASH,
    )


def _frame_manifest(dataset, episode, *, frame_index: int = 3):  # type: ignore[no-untyped-def]
    with tempfile.NamedTemporaryFile(suffix=".video", delete=False) as temporary:
        raw_path = Path(temporary.name)
    raw_signature = sign_raw_data_file(
        raw_path,
        dataset_id="fixture",
        dataset_revision="fixture@0.1",
        source_split=episode.split.value,
        media_type="video/mp4",
        signer=RAW_SIGNER,
    )
    try:
        return issue_direction_three_frame_manifest(
            DirectionThreeFrameContentManifest(
                dataset_manifest_hash=content_sha256(dataset.manifest),
                raw_data_signature_sha256=raw_signature.signature_sha256,
                raw_data_content_sha256=raw_signature.content_sha256,
                split=episode.split,
                producer_run_id="fixture-frame-producer",
                bindings=(
                    DirectionThreeFrameContentBinding(
                        episode_id=episode.episode_id,
                        frame_index=frame_index,
                        source_uri=f"{raw_path}#frame={frame_index}",
                        source_artifact_sha256=raw_signature.content_sha256,
                        raw_byte_sha256=RAW_FRAME_HASH,
                        preprocessing_sha256="b" * 64,
                        decoded_input_sha256=DECODED_FRAME_HASH,
                    ),
                ),
            ),
            raw_data_path=raw_path,
            raw_data_signature=raw_signature,
            raw_data_signature_verifier=RAW_VERIFIER,
            materialize_frame=lambda _path, _binding: (
                RAW_FRAME_BYTES,
                DECODED_FRAME_BYTES,
            ),
            signer=FRAME_SIGNER,
        )
    finally:
        raw_path.unlink()


def _cache():
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target)
    frame_manifest = _frame_manifest(dataset, episode)
    cache = build_direction_three_prediction_cache(
        dataset,
        split=DirectionThreeDatasetSplit.TRAIN,
        records=(prediction,),
        model_versions={EvidenceChannel.VISUAL: prediction.model_version},
        calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
        inference_config_hash="config-sha256",
        frame_manifest=frame_manifest,
        frame_manifest_verifier=FRAME_VERIFIER,
    )
    return dataset, episode, prediction, frame_manifest, cache


def test_cache_round_trip_is_content_bound_and_truth_free(tmp_path: Path):
    dataset, _, prediction, frame_manifest, cache = _cache()
    path = tmp_path / "predictions.json"

    write_direction_three_prediction_cache(cache, path)
    loaded = read_direction_three_prediction_cache(
        path,
        dataset=dataset,
        split=DirectionThreeDatasetSplit.TRAIN,
        model_versions={EvidenceChannel.VISUAL: prediction.model_version},
        calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
        inference_config_hash="config-sha256",
        frame_manifest=frame_manifest,
        frame_manifest_verifier=FRAME_VERIFIER,
    )

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
    frame_manifest = _frame_manifest(dataset, episode)
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
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_cache_rejects_model_or_calibration_manifest_drift():
    _, _, _, _, cache = _cache()
    bad_manifest = cache.manifest.model_copy(
        update={"model_versions": {EvidenceChannel.VISUAL: "other-model"}}
    )

    with pytest.raises(ValueError, match="model version"):
        DirectionThreePredictionCache(manifest=bad_manifest, records=cache.records)


def test_cache_rejects_record_tampering():
    _, _, prediction, _, cache = _cache()
    tampered = prediction.model_copy(update={"likelihood_given_candidate": 0.2})

    with pytest.raises(ValueError, match="content hash"):
        DirectionThreePredictionCache(manifest=cache.manifest, records=(tampered,))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_name", "tampered-source"),
        ("source_version", "tampered@9"),
        ("session_id", "tampered-session"),
        ("object_instance_ids", ("tampered-object",)),
        ("source_record_refs", ("tampered-record",)),
    ],
)
def test_cache_read_rejects_tampered_episode_lineage_binding(
    tmp_path: Path, field: str, replacement: object
):
    dataset, _, prediction, frame_manifest, cache = _cache()
    binding = cache.manifest.episode_bindings[0].model_copy(update={field: replacement})
    tampered_manifest = cache.manifest.model_copy(update={"episode_bindings": (binding,)})
    tampered_cache = cache.model_copy(update={"manifest": tampered_manifest})
    path = tmp_path / "predictions.json"
    write_direction_three_prediction_cache(tampered_cache, path)

    with pytest.raises(ValueError, match="episode bindings"):
        read_direction_three_prediction_cache(
            path,
            dataset=dataset,
            split=DirectionThreeDatasetSplit.TRAIN,
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_cache_rejects_candidate_outside_episode_support():
    dataset, episode, _ = _dataset()
    prediction = _prediction(episode, uuid4())
    frame_manifest = _frame_manifest(dataset, episode)

    with pytest.raises(ValueError, match="candidate support"):
        build_direction_three_prediction_cache(
            dataset,
            split=episode.split,
            records=(prediction,),
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_cache_rejects_frame_outside_episode_interval():
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target).model_copy(update={"frame_index": 21})
    frame_manifest = _frame_manifest(dataset, episode)

    with pytest.raises(ValueError, match="frame interval"):
        build_direction_three_prediction_cache(
            dataset,
            split=episode.split,
            records=(prediction,),
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_cache_rejects_prediction_from_different_frame_bytes() -> None:
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target).model_copy(update={"input_content_hash": "e" * 64})
    frame_manifest = _frame_manifest(dataset, episode)

    with pytest.raises(ValueError, match="signed frame content"):
        build_direction_three_prediction_cache(
            dataset,
            split=episode.split,
            records=(prediction,),
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_cache_rejects_frame_manifest_tampered_after_custodian_signature() -> None:
    dataset, episode, target = _dataset()
    prediction = _prediction(episode, target)
    frame_manifest = _frame_manifest(dataset, episode)
    tampered_binding = frame_manifest.bindings[0].model_copy(update={"raw_byte_sha256": "f" * 64})
    tampered = frame_manifest.model_copy(update={"bindings": (tampered_binding,)})

    with pytest.raises(ValueError, match="signature"):
        build_direction_three_prediction_cache(
            dataset,
            split=episode.split,
            records=(prediction,),
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=tampered,
            frame_manifest_verifier=FRAME_VERIFIER,
        )


def test_identity_outputs_are_restricted_to_visual_channel():
    _, episode, target = _dataset()
    payload = _prediction(episode, target).model_dump(mode="python")
    payload["channel"] = EvidenceChannel.GEOMETRY

    with pytest.raises(ValueError, match="visual evidence only"):
        DirectionThreeCachedPrediction.model_validate(payload)


def test_cache_refuses_overwrite_without_force(tmp_path: Path):
    _, _, _, _, cache = _cache()
    path = tmp_path / "predictions.json"
    write_direction_three_prediction_cache(cache, path)

    with pytest.raises(FileExistsError, match="--force"):
        write_direction_three_prediction_cache(cache, path)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"split": DirectionThreeDatasetSplit.TEST}, "requested split"),
        (
            {"model_versions": {EvidenceChannel.VISUAL: "wrong-model"}},
            "external expectations",
        ),
        (
            {"calibration_domains": {EvidenceChannel.VISUAL: "wrong-domain"}},
            "external expectations",
        ),
        ({"inference_config_hash": "wrong-config"}, "inference config"),
    ],
)
def test_cache_read_rejects_external_expectation_mismatch(
    tmp_path: Path, override: dict[str, object], message: str
):
    dataset, _, prediction, frame_manifest, cache = _cache()
    path = tmp_path / "predictions.json"
    write_direction_three_prediction_cache(cache, path)
    expectations = {
        "dataset": dataset,
        "split": DirectionThreeDatasetSplit.TRAIN,
        "model_versions": {EvidenceChannel.VISUAL: prediction.model_version},
        "calibration_domains": {EvidenceChannel.VISUAL: prediction.calibration_domain},
        "inference_config_hash": "config-sha256",
        "frame_manifest": frame_manifest,
        "frame_manifest_verifier": FRAME_VERIFIER,
    }
    expectations.update(override)

    with pytest.raises(ValueError, match=message):
        read_direction_three_prediction_cache(path, **expectations)


def test_cache_read_rejects_whole_valid_cache_from_another_dataset(tmp_path: Path):
    _, _, prediction, frame_manifest, cache = _cache()
    other_dataset, _, _ = _dataset()
    path = tmp_path / "predictions.json"
    write_direction_three_prediction_cache(cache, path)

    with pytest.raises(ValueError, match="different dataset manifest"):
        read_direction_three_prediction_cache(
            path,
            dataset=other_dataset,
            split=DirectionThreeDatasetSplit.TRAIN,
            model_versions={EvidenceChannel.VISUAL: prediction.model_version},
            calibration_domains={EvidenceChannel.VISUAL: prediction.calibration_domain},
            inference_config_hash="config-sha256",
            frame_manifest=frame_manifest,
            frame_manifest_verifier=FRAME_VERIFIER,
        )
