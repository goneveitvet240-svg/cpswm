from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
import pytest
from PIL import Image

from cpswm.data_preflight.hocap_evaluation import (
    AnnotatedTarget,
    match_targets,
    read_author_targets,
)
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.perception_mapping.natural_vision import DetectionCandidate, decode_rgb
from cpswm.system.reproducibility import content_sha256


def fixture():
    rgb = io.BytesIO()
    Image.fromarray(np.full((480, 640, 3), 64, np.uint8)).save(rgb, format="JPEG")
    depth = io.BytesIO()
    Image.fromarray(np.full((480, 640), 1500, np.uint16)).save(depth, format="PNG")
    b, d = rgb.getvalue(), depth.getvalue()
    s = HOCapFrameSource(
        "subject_5/20231027_112303",
        "105322251564",
        0,
        hashlib.sha256(b).hexdigest(),
        hashlib.sha256(d).hexdigest(),
    )
    return s, b, d


def adapt(s, b, d, **changes):
    when = datetime(2000, 1, 1, tzinfo=UTC)
    values = dict(
        rgb_bytes=b,
        depth_bytes=d,
        expected_source_sha256=content_sha256(s),
        household_id=UUID(int=1),
        session_id=UUID(int=2),
        trace_id=UUID(int=3),
        capture_time=when,
        arrival_time=when,
    )
    values.update(changes)
    return adapt_hocap_rgbd(s, **values)


def test_real_encoding_boundary_preserves_pixels_and_mm_to_m_units():
    s, b, d = fixture()
    rgb, depth = adapt(s, b, d)
    env, pixels = decode_rgb(rgb, cutoff=datetime(2000, 1, 1, tzinfo=UTC))
    assert pixels.shape == (480, 640, 3)
    assert np.all(pixels == 64)
    assert np.all(np.load(io.BytesIO(depth.payload_bytes)) == 1.5)
    assert depth.depth_unit == "m"
    assert env.metadata.source_id == s.member("rgb")
    assert not env.oracle_channel
    assert "ordinal" in env.clock_domain
    assert "pose" not in env.model_dump_json()
    assert adapt(s, b, d) == (rgb, depth)


@pytest.mark.parametrize("change", ("rgb", "depth", "source", "time"))
def test_changed_source_pixels_and_future_time_rejected(change):
    s, b, d = fixture()
    with pytest.raises(ValueError):
        if change == "rgb":
            adapt(s, b + b"corruption", d)
        elif change == "depth":
            adapt(s, b, d + b"corruption")
        elif change == "source":
            adapt(replace(s, frame_index=1), b, d, expected_source_sha256=content_sha256(s))
        else:
            adapt(s, b, d, capture_time=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=1))


def test_raw_source_schema_cannot_carry_author_roles_or_escaping_paths():
    s, _, _ = fixture()
    with pytest.raises(TypeError):
        HOCapFrameSource(**vars(s), object_ids=["G15_1"])
    with pytest.raises(ValueError):
        replace(s, sequence_id="../evaluator")
    with pytest.raises(ValueError):
        s.member("label")


def test_depth_encoding_is_not_silently_coerced_from_8bit():
    s, b, _ = fixture()
    out = io.BytesIO()
    Image.fromarray(np.ones((480, 640), np.uint8)).save(out, format="PNG")
    d = out.getvalue()
    s = replace(s, depth_sha256=hashlib.sha256(d).hexdigest())
    with pytest.raises(ValueError, match="16-bit"):
        adapt(s, b, d)


def annotation():
    mask = np.zeros((480, 640), np.uint8)
    mask[10:20, 30:40] = 1
    mask[30:40, 50:60] = 3
    out = io.BytesIO()
    np.savez_compressed(
        out, seg_mask=mask, obj_class_names=np.array(["G15_1", "G15_2", "RIGHT_HAND"])
    )
    return out.getvalue()


def test_author_masks_keep_invisibility_and_do_not_convert_hands_to_objects():
    targets = read_author_targets(annotation())
    assert targets == (
        AnnotatedTarget("G15_1", (30.0, 10.0, 40.0, 20.0)),
        AnnotatedTarget("G15_2", None),
    )
    rows, missed = match_targets((), targets)
    assert rows == ()
    assert missed == ("G15_1",)


def test_unique_target_matching_keeps_duplicates_and_all_alternatives():
    targets = read_author_targets(annotation())
    a = DetectionCandidate(uuid4(), "bottle", 0.9, (30.0, 10.0, 40.0, 20.0))
    b = DetectionCandidate(uuid4(), "cup", 0.8, (30.0, 10.0, 40.0, 20.0))
    chair = DetectionCandidate(uuid4(), "chair", 0.7, (100.0, 100.0, 200.0, 200.0))
    rows, missed = match_targets((b, chair, a), targets)
    assert missed == ()
    assert [r.matched_target for r in rows] == ["G15_1", None, None]
    assert rows[1].overlaps == (("G15_1", 1.0),)
    assert rows[2].overlaps == (("G15_1", 0.0),)
    with pytest.raises(ValueError, match="duplicate candidate"):
        match_targets((a, a), targets)


def test_ambiguous_targets_are_not_hidden_by_best_match():
    a = DetectionCandidate(uuid4(), "bottle", 0.9, (30.0, 10.0, 40.0, 20.0))
    targets = (AnnotatedTarget("a", a.box_xyxy), AnnotatedTarget("b", a.box_xyxy))
    rows, missed = match_targets((a,), targets)
    assert rows[0].ambiguous
    assert missed == ("b",)


@pytest.mark.parametrize("score", (float("nan"), 1.1, -0.1))
def test_nonfinite_or_invalid_candidate_scores_rejected(score):
    a = DetectionCandidate(uuid4(), "bottle", score, (30.0, 10.0, 40.0, 20.0))
    with pytest.raises(ValueError):
        match_targets((a,), read_author_targets(annotation()))
