from __future__ import annotations

import hashlib
import io

import numpy as np
import pytest

from cpswm.data_preflight.natural_event_coverage import inspect_annotation, pose_pair_diagnostic


def annotation(**changes):
    values = dict(
        cam_K=np.diag([300.0, 300.0, 1.0]),
        obj_poses=np.eye(4)[None, ...],
        hand_joints_3d=np.full((2, 21, 3), -1.0),
        hand_joints_2d=np.full((2, 21, 2), -1),
        seg_mask=np.zeros((480, 640), dtype=np.uint8),
        obj_class_inds=np.array([0]),
        obj_class_names=np.array(["test-object"]),
    )
    values.update(changes)
    stream = io.BytesIO()
    np.savez_compressed(stream, **values)
    return stream.getvalue()


def inspect(payload):
    return inspect_annotation(payload, expected_sha256=hashlib.sha256(payload).hexdigest())


def test_absent_hands_are_not_two_actors_or_contact_supervision():
    result = inspect(annotation())
    assert [h["valid_3d_joints"] for h in result["hands"]] == [0, 0]
    assert set(result["semantic_event_labels"].values()) == {"NOT_PROVIDED"}
    assert result["evidence_lane"] == "EVALUATOR_ONLY_NO_RUNTIME_AUTHORITY"


def test_valid_two_hands_do_not_establish_people_or_contact():
    result = inspect(
        annotation(hand_joints_3d=np.ones((2, 21, 3)), hand_joints_2d=np.full((2, 21, 2), 100))
    )
    assert [h["valid_3d_joints"] for h in result["hands"]] == [21, 21]
    assert all(h["person_identity"] == "NOT_PROVIDED_BY_HAND_SIDE" for h in result["hands"])


def test_nonfinite_hand_joints_are_missing_not_valid_labels():
    result = inspect(annotation(hand_joints_3d=np.full((2, 21, 3), np.nan)))
    assert not any(h["valid_3d_joints"] for h in result["hands"])


def test_missing_pose_is_not_zero_displacement():
    a = inspect(annotation())
    b = inspect(annotation(obj_poses=np.full((1, 4, 4), -1.0)))
    result = pose_pair_diagnostic(a, b, frame_gap=1)
    assert result["objects"][0]["endpoint_distance_m"] is None


def test_translation_across_gap_is_not_pickup_or_contact_label():
    a = inspect(annotation())
    pose = np.eye(4)[None, ...]
    pose[0, 0, 3] = 0.2
    b = inspect(annotation(obj_poses=pose))
    result = pose_pair_diagnostic(a, b, frame_gap=100)
    assert result["objects"][0]["endpoint_distance_m"] == pytest.approx(0.2)
    assert result["event_classification"] == "UNRESOLVED"
    assert not result["contiguous"] and result["physical_duration_seconds"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"obj_poses": np.zeros((1, 4, 4))},
        {"obj_poses": np.full((1, 4, 4), np.nan)},
        {"obj_class_names": np.array(["test-object", "test-object"])},
        {"hand_joints_3d": np.zeros((3, 21, 3))},
    ],
)
def test_invalid_supervision_rejected(change):
    with pytest.raises(ValueError):
        inspect(annotation(**change))


def test_changed_source_pin_is_rejected():
    with pytest.raises(ValueError, match="SHA256"):
        inspect_annotation(annotation(), expected_sha256="0" * 64)
