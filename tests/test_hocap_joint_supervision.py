"""Pose correspondence and truth-lane tests on independent synthetic arrays."""

import io
from copy import deepcopy

import numpy as np
import pytest

from cpswm.data_preflight.hocap_joint_supervision import pose_supervision, strict_json


def fixture():
    camera = "105322251564"
    meta = {"num_frames": 2, "object_ids": ["a", "b"], "realsense": {"serials": [camera]}}
    intr = {
        "serial": camera,
        "color": {"height": 3, "width": 4, "fx": 2.0, "fy": 2.0, "ppx": 2.0, "ppy": 1.0},
    }
    extr = {
        "extrinsics": {
            camera: np.eye(4)[:3].flatten().tolist(),
            "tag_1": np.eye(4)[:3].flatten().tolist(),
        }
    }
    seq = np.zeros((2, 2, 7))
    seq[:, :, 3] = 1
    seq[0, :, 4] = 0.25
    seq[1, :, 4] = 0.5
    poses = np.tile(np.eye(4), (2, 1, 1))
    poses[:, 0, 3] = [0.25, 0.5]
    arrays = {
        "obj_poses": poses,
        "obj_class_names": np.array(["a", "b", "RIGHT_HAND"]),
        "obj_class_inds": np.array([4, 5, 64]),
        "seg_mask": np.ones((3, 4), dtype=np.uint8),
        "cam_K": np.array([[2.0, 0, 2.0], [0, 2.0, 1.0], [0, 0, 1.0]]),
    }
    return arrays, dict(
        metadata=meta, intrinsics=intr, extrinsics=extr, sequence_poses=seq, frame=0, camera=camera
    )


def encode(arrays):
    blob = io.BytesIO()
    np.savez(blob, **arrays)
    return blob.getvalue()


def test_pose_rows_bind_correct_object_camera_and_sequence_without_noise_or_contact():
    arrays, kwargs = fixture()
    result = pose_supervision(encode(arrays), **kwargs)
    assert len(result["objects"]) == 2
    assert result["objects"][1]["visible_mask_pixels"] == 0
    assert not result["contact_gold"] and not result["measurement_noise_calibrated"]
    assert result["objects"][0]["cross_file_max_abs"] == 0


@pytest.mark.parametrize(
    "attack",
    ["object_order", "frame", "pose", "reflection", "quaternion", "intrinsics", "bool_frame"],
)
def test_resealed_semantically_wrong_pose_labels_rejected(attack):
    arrays, kwargs = fixture()
    arrays, kwargs = deepcopy(arrays), deepcopy(kwargs)
    if attack == "object_order":
        arrays["obj_class_names"] = np.array(["b", "a", "RIGHT_HAND"])
    if attack == "frame":
        kwargs["sequence_poses"][:, 1, 4] += 1
        kwargs["frame"] = 1
    if attack == "pose":
        arrays["obj_poses"][0, 0, 3] += 1
    if attack == "reflection":
        arrays["obj_poses"][0, 0, 0] = -1
    if attack == "quaternion":
        kwargs["sequence_poses"][0, 0, 3] = 2
    if attack == "intrinsics":
        arrays["cam_K"][0, 0] = 99
    if attack == "bool_frame":
        kwargs["frame"] = True
    with pytest.raises(ValueError):
        pose_supervision(encode(arrays), **kwargs)


def test_duplicate_json_cannot_hide_source_identity():
    with pytest.raises(ValueError, match="duplicate"):
        strict_json(b'{"sha256":"a","sha256":"b"}')
