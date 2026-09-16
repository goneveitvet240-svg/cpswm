from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pytest
from PIL import Image

from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.perception_mapping.natural_geometry import (
    NaturalGeometryProducer,
    PinholeIntrinsics,
    extract_surface_candidates,
)
from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame
from cpswm.system.reproducibility import content_sha256


def fixture(depth=None):
    rgb_wire, depth_wire = io.BytesIO(), io.BytesIO()
    Image.fromarray(np.full((480, 640, 3), 64, np.uint8)).save(rgb_wire, format="JPEG")
    if depth is None:
        depth = np.full((480, 640), 1500, np.uint16)
    Image.fromarray(depth).save(depth_wire, format="PNG")
    b, d = rgb_wire.getvalue(), depth_wire.getvalue()
    source = HOCapFrameSource(
        "subject_5/20231027_112303",
        "105322251564",
        0,
        hashlib.sha256(b).hexdigest(),
        hashlib.sha256(d).hexdigest(),
    )
    when = datetime(2000, 1, 1, tzinfo=UTC)
    rgb, raw_depth = adapt_hocap_rgbd(
        source,
        rgb_bytes=b,
        depth_bytes=d,
        expected_source_sha256=content_sha256(source),
        household_id=UUID(int=1),
        session_id=UUID(int=2),
        trace_id=UUID(int=3),
        capture_time=when,
        arrival_time=when,
    )
    e = rgb.envelope()
    frame = VisualFrame(
        e.identity.observation_id,
        UUID(int=1),
        UUID(int=2),
        UUID(int=3),
        e.sensor.sensor_id,
        e.frame_id,
        when,
        when,
        when,
        e.payload.payload_sha256,
        rgb.capture_receipt_sha256,
        "test-only",
        "a" * 64,
        "none",
        "none",
        0.5,
        640,
        480,
        (DetectionCandidate(UUID(int=9), "bottle", 0.9, (10.0, 10.0, 20.0, 20.0)),),
    )
    intrinsics = PinholeIntrinsics(
        "105322251564", 640, 480, 400, 400, 320, 240, "b" * 64, (0.1, 0, 0, 0, 0)
    )
    return rgb, raw_depth, frame, intrinsics, when


def test_actual_pixel_deprojection_retains_unobserved_orientation_and_background_ambiguity():
    rgb, depth, frame, k, when = fixture()
    (candidate,) = extract_surface_candidates(rgb, depth, frame, k, cutoff=when)
    assert candidate.valid_depth_pixels == 100
    assert candidate.depth_spread_90_m == 0
    for sample in candidate.surface_samples:
        u, v = sample.pixel_uv
        assert sample.nominal_pinhole_xyz_m == ((u - 320) * 1.5 / 400, (v - 240) * 1.5 / 400, 1.5)
    assert candidate.orientation is candidate.instance_id is candidate.likelihood_model is None
    assert "SURFACE_IS_NOT_OBJECT_CENTRE" in candidate.ambiguity
    assert candidate.rgb_observation_id != candidate.depth_observation_id


def test_zero_depth_is_missing_and_two_surfaces_are_not_collapsed_into_object_pose():
    values = np.full((480, 640), 1000, np.uint16)
    values[15:20, 10:20] = 2000
    rgb, depth, frame, k, when = fixture(values)
    (candidate,) = extract_surface_candidates(rgb, depth, frame, k, cutoff=when)
    assert candidate.depth_spread_90_m == 1
    rgb, depth, frame, k, when = fixture(np.zeros((480, 640), np.uint16))
    (candidate,) = extract_surface_candidates(rgb, depth, frame, k, cutoff=when)
    assert candidate.status == "NO_VALID_DEPTH"
    assert candidate.surface_samples == ()


@pytest.mark.parametrize("attack", ["receipt", "prediction", "camera", "future", "box"])
def test_unpaired_or_unobserved_geometry_rejected(attack):
    rgb, depth, frame, k, when = fixture()
    if attack == "receipt":
        depth = replace(depth, capture_receipt_sha256="a" * 64)
    elif attack == "prediction":
        frame = replace(frame, input_sha256="c" * 64)
    elif attack == "camera":
        k = replace(k, camera_id="wrong-camera")
    elif attack == "future":
        when -= timedelta(seconds=1)
    else:
        frame = replace(
            frame, candidates=(replace(frame.candidates[0], box_xyxy=(-1.0, 1.0, 5.0, 5.0)),)
        )
    with pytest.raises(ValueError):
        extract_surface_candidates(rgb, depth, frame, k, cutoff=when)


def test_producer_waits_for_depth_replay_is_idempotent_and_changed_history_rejected():
    rgb, depth, frame, k, when = fixture()
    p = NaturalGeometryProducer((frame,), k)
    assert p.infer((rgb,), cutoff=when) is None
    assert p.records() == ()
    assert p.infer((rgb, depth), cutoff=when) is None
    before = p.records()
    assert len(before) == 1
    p.infer((rgb, depth), cutoff=when)
    assert p.records() == before
    with pytest.raises(ValueError, match="history"):
        p.infer((rgb,), cutoff=when)
    assert p.records() == before


def test_restore_binds_predictions_and_intrinsics():
    rgb, depth, frame, k, when = fixture()
    p = NaturalGeometryProducer((frame,), k)
    p.infer((rgb, depth), cutoff=when)
    q = NaturalGeometryProducer((frame,), k)
    q.restore_state(p.checkpoint_state())
    assert p.records() == q.records()
    changed = NaturalGeometryProducer((frame,), replace(k, fx=500))
    with pytest.raises(ValueError, match="same predictions"):
        changed.restore_state(p.checkpoint_state())
