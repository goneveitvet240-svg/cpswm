"""Adversarial source/replay checks; synthetic pixels have no semantic authority."""

import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_initialized_target_tracking as tracking


def encoded(rgb):
    buffer = io.BytesIO()
    np.save(buffer, rgb, allow_pickle=False)
    return buffer.getvalue()


def sample(tmp_path):
    directory = tmp_path / "pixels" / "clip-0001"
    directory.mkdir(parents=True)
    random = np.random.default_rng(4)
    rgb = random.integers(0, 255, (80, 80, 3), dtype=np.uint8)
    rows, records = [], []
    for index in range(3):
        raw = encoded(np.roll(rgb, index, axis=1))
        digest = hashlib.sha256(raw).hexdigest()
        (directory / f"{index:04d}.npy").write_bytes(raw)
        rows.append(
            {"frame_index": index, "payload_sha256": digest, "visible_support_proxy": "unknown"}
        )
        records.append({"visual": {"input_sha256": digest}})
    result = json.dumps({"frames": 3, "records": records}).encode()
    (directory / "result.json").write_bytes(result)
    annotation = {
        "clips": [
            {
                "clip_id": "clip-0001",
                "input_result_sha256": hashlib.sha256(result).hexdigest(),
                "first_frame_initialization_xyxy": [15, 15, 60, 60],
                "rows": rows,
            }
        ]
    }
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps(annotation))
    return directory.parent, path, annotation


def test_legal_tracking_positive_path_does_not_authorize_semantic_memory(tmp_path):
    pixels, path, _ = sample(tmp_path)
    result = tracking.run(pixels, path, tmp_path / "out")
    assert len(result["clips"][0]["measurements"]) == 3
    assert all(row["box_xyxy"] for row in result["clips"][0]["measurements"])
    assert result["natural_grounded_transition_authorized"] is False


def test_changed_annotation_mid_run_cannot_claim_new_annotation_hash(tmp_path, monkeypatch):
    pixels, path, original = sample(tmp_path)
    update = tracking.InitializedPixelTargetTracker.update

    def mutate(self, rgb, *, frame_index):
        if frame_index == 0:
            original["clips"][0]["first_frame_initialization_xyxy"] = [1, 1, 10, 10]
            path.write_text(json.dumps(original))
        return update(self, rgb, frame_index=frame_index)

    monkeypatch.setattr(tracking.InitializedPixelTargetTracker, "update", mutate)
    with pytest.raises(ValueError, match=r"annotation.*changed"):
        tracking.run(pixels, path, tmp_path / "out")
    assert not (tmp_path / "out/result.json").exists()


def test_forged_payload_and_annotation_digest_cannot_rebind_original_pixel_run(tmp_path):
    pixels, path, annotation = sample(tmp_path)
    payload = encoded(np.full((80, 80, 3), 127, dtype=np.uint8))
    (pixels / "clip-0001/0000.npy").write_bytes(payload)
    annotation["clips"][0]["rows"][0]["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    path.write_text(json.dumps(annotation))
    with pytest.raises(ValueError, match=r"archive|original"):
        tracking.run(pixels, path, tmp_path / "out")
    assert not (tmp_path / "out/result.json").exists()


def test_truncating_failure_suffix_cannot_report_complete_reviewed_clip(tmp_path):
    pixels, path, annotation = sample(tmp_path)
    annotation["clips"][0]["rows"] = annotation["clips"][0]["rows"][:1]
    path.write_text(json.dumps(annotation))
    with pytest.raises(ValueError, match=r"complete|coverage|frame count"):
        tracking.run(pixels, path, tmp_path / "out")


@pytest.mark.parametrize(
    "attack", ["duplicate_clip", "empty_clips", "escape_path", "reverse_frames", "bool_index"]
)
def test_round2_closure_attacks(tmp_path, attack):
    pixels, path, annotation = sample(tmp_path)
    if attack == "duplicate_clip":
        annotation["clips"] *= 2
    elif attack == "empty_clips":
        annotation["clips"] = []
    elif attack == "escape_path":
        annotation["clips"][0]["clip_id"] = "../outside"
    elif attack == "reverse_frames":
        annotation["clips"][0]["rows"].reverse()
    else:
        annotation["clips"][0]["rows"][0]["frame_index"] = False
    path.write_text(json.dumps(annotation))
    with pytest.raises(ValueError):
        tracking.run(pixels, path, tmp_path / "out")
    assert not (tmp_path / "out/result.json").exists()


def test_round2_later_labels_do_not_change_causal_measurements(tmp_path):
    pixels, path, annotation = sample(tmp_path)
    first = tracking.run(pixels, path, tmp_path / "first")
    for row in annotation["clips"][0]["rows"]:
        row["visible_support_proxy"] = "FORGED_OWNER_CONTACT"
        row["world_pose"] = [999, 999, 999]
    path.write_text(json.dumps(annotation))
    second = tracking.run(pixels, path, tmp_path / "second")
    assert first["clips"] == second["clips"]
    assert second["natural_grounded_transition_authorized"] is False


def test_round2_fully_coherent_forgery_remains_only_a_measurement(tmp_path):
    pixels, path, annotation = sample(tmp_path)
    raw = encoded(np.random.default_rng(20).integers(0, 255, (80, 80, 3), dtype=np.uint8))
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    for row in annotation["clips"][0]["rows"]:
        (pixels / "clip-0001" / f"{row['frame_index']:04d}.npy").write_bytes(raw)
        row["payload_sha256"] = digest
        row["physical_contact_truth"] = "FORGED_CERTAIN_OWNER"
        records.append({"visual": {"input_sha256": digest}})
    archive = json.dumps({"frames": 3, "records": records}).encode()
    (pixels / "clip-0001/result.json").write_bytes(archive)
    annotation["clips"][0]["input_result_sha256"] = hashlib.sha256(archive).hexdigest()
    annotation["independent_human_annotation"] = True
    annotation["scientific_confirmation"] = True
    path.write_text(json.dumps(annotation))
    result = tracking.run(pixels, path, tmp_path / "out")
    assert all(m["box_xyxy"] is not None for m in result["clips"][0]["measurements"])
    assert not result["independent_contact_calibration"]
    assert not result["world_instance_or_pose_established"]
    assert not result["natural_grounded_transition_authorized"]
