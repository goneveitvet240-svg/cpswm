"""Structural gates must not promote matching dimensions or edge scores to truth."""

import io
import sys
from pathlib import Path

import numpy as np
import pytest

from cpswm.data_preflight.supervision_alignment import (
    alignment_inventory,
    boundary_support,
    pose_audit,
    timestamp_audit,
)


def test_integer_epoch_precision_and_nonuniform_time():
    start = 1_700_000_000_000_000_000
    result = timestamp_audit((start, start + 1, start + 70_000_001), 3)
    assert result["relative_seconds"] == [0.0, 1e-9, 0.070000001]
    assert result["cross_stream_alignment_verified"] is False


@pytest.mark.parametrize(
    "ts,count", [((1, 1), 2), ((2, 1), 2), ((1,), 2), ((True,), 1), ((-1,), 1), ((), 0)]
)
def test_invalid_frame_clock_rejected(ts, count):
    with pytest.raises(ValueError):
        timestamp_audit(ts, count)


def test_pose_defects_preserved_and_not_repaired():
    poses = np.repeat(np.eye(4)[None], 5, axis=0)
    poses[0, :3, 3] = [2.0, -3.0, 7.0]
    poses[1, 0, 0] = -1
    poses[2, 1, 1] = 0.5
    poses[3, 3, 0] = 1
    poses[4, 0, 0] = np.nan
    before = poses.copy()
    result = pose_audit(poses)
    assert result["invalid_rows"] == [1, 2, 3, 4]
    assert result["repaired"] is False
    np.testing.assert_equal(poses, before)


def test_structural_match_and_missing_value_never_authorize_alignment():
    masks = np.ones((3, 8, 8), np.uint8)
    masks[0, 3:5, 3:5] = 3
    aligned = np.repeat(np.arange(9)[:, None], 7, axis=1)
    r = alignment_inventory(masks, aligned, video_frames=9, pose_rows=9)
    assert r["published_table_matches_current_generator_width"]
    assert r["value_present_rows"]["3"] == [0]
    assert r["accepted_frame_links"] == []
    assert not r["absent_value_means_absent_object"]
    assert not r["usable_for_role_or_contact_calibration"]
    assert all(not h["accepted"] for h in r["hypotheses"].values())


def test_out_of_range_candidate_is_retained_but_flagged():
    r = alignment_inventory(
        np.ones((3, 8, 8), np.uint8), np.ones((2, 6), int), video_frames=2, pose_rows=2
    )
    assert not r["hypotheses"]["three_times_mask_row"]["all_in_range"]
    assert not r["published_table_matches_current_generator_width"]
    assert "every_third_table_row_first_column" not in r["hypotheses"]


def test_edge_evidence_scores_translation_but_does_not_label_it():
    masks = np.zeros((1, 24, 24), np.uint8)
    masks[0, 6:18, 6:18] = 1
    rgb = np.zeros((2, 24, 24, 3), np.uint8)
    rgb[0, 6:18, 6:18] = 255
    rgb[1, 1:5, 1:5] = 255
    scores = boundary_support(rgb, masks)
    assert scores.shape == (1, 2)
    assert scores[0, 0] > scores[0, 1]
    assert np.all(boundary_support(np.zeros_like(rgb), masks) == 0)
    assert np.all(boundary_support(rgb, np.zeros_like(masks)) == 0)


def test_pinned_bytes_and_array_allocation(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from audit_core4d_supervision_alignment import array_bytes, pinned

    stream = io.BytesIO()
    np.save(stream, np.eye(4), allow_pickle=False)
    data = stream.getvalue()
    assert array_bytes(data, 1000).shape == (4, 4)
    with pytest.raises(ValueError):
        array_bytes(data, 1)
    with pytest.raises(ValueError):
        array_bytes(data + b"x", 1000)
    stream = io.BytesIO()
    np.save(stream, np.array([{}], dtype=object), allow_pickle=True)
    with pytest.raises(ValueError):
        array_bytes(stream.getvalue(), 1000)
    p = tmp_path / "input"
    p.write_bytes(b"abc")
    with pytest.raises(ValueError):
        pinned(p, "a" * 64, 100)
    with pytest.raises(ValueError):
        pinned(p, "a" * 64, 1)


@pytest.mark.parametrize("dtype", [np.float16, np.float32, np.float64, np.longdouble])
def test_supported_floating_identity_is_auditable(dtype):
    import json

    result = pose_audit(np.eye(4, dtype=dtype)[None])
    assert result["invalid_rows"] == []
    json.dumps(result, allow_nan=False)


def test_pose_computation_overflow_is_serializable_defect():
    import json

    poses = np.eye(4)[None]
    poses[0, 0, 0] = 1e308
    result = pose_audit(poses)
    assert result["invalid_rows"] == [0]
    json.dumps(result, allow_nan=False)


def test_each_edge_score_depends_only_on_its_own_rgb_frame():
    masks = np.zeros((1, 24, 24), np.uint8)
    masks[0, 6:18, 6:18] = 1
    rgb = np.zeros((3, 24, 24, 3), np.uint8)
    before = boundary_support(rgb, masks)
    rgb[0, 6:18, 6:18] = 255
    after = boundary_support(rgb, masks)
    np.testing.assert_array_equal(after[:, 1:], before[:, 1:])
    assert after[0, 0] > 0
