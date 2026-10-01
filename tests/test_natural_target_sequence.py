"""Real fixed detector, natural archived RGB, controlled sequence perturbations."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from test_natural_candidate_position import public_image
from test_unity_rgbd import event_for
from unity_rgbd_capture import rgbd_response

from cpswm.perception_mapping.natural_target_sequence import NaturalTargetSequence
from cpswm.perception_mapping.unity_rgbd import PROFILE, observations_from_response
from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker
from cpswm.system.reproducibility import content_sha256


@pytest.fixture(scope="module")
def weights():
    import torch

    torch.set_num_threads(2)
    path = Path(os.environ["CPSWM_SSDLITE_WEIGHTS"])
    assert path.is_file()
    return path


def observation(image, index, *, scope=None):
    event = event_for()
    h, w = image.shape[:2]
    event.frame = image
    event.depth_frame = np.full((h, w), 1.99, dtype=np.float32)
    event.metadata.update(screenWidth=w, screenHeight=h)
    action = uuid4()
    capture = datetime(2026, 10, 2, tzinfo=UTC) + timedelta(seconds=index * 2)
    cutoff = capture + timedelta(seconds=1)
    response = rgbd_response(str(action), event)
    response["capture_time"] = capture.isoformat()
    rows = observations_from_response(
        response,
        action_id=action,
        scope=scope or (UUID(int=1), UUID(int=2), UUID(int=3)),
        arrival=cutoff,
        provenance=dict(
            worker="a" * 64,
            unity="b" * 64,
            house="c" * 64,
            capture_configuration=content_sha256((PROFILE, w, h, 90.0, 0.1, 20.0, False)),
        ),
    )
    return rows[0], cutoff


def test_natural_initialization_translation_duplicate_and_replay(weights):
    image = public_image()
    inputs = [
        observation(image, 0),
        observation(np.roll(image, 2, axis=1), 1),
        observation(np.roll(image, 2, axis=1), 2),
    ]
    sequence = NaturalTargetSequence(weights_path=weights)
    records = [sequence.observe(raw, cutoff=cutoff) for raw, cutoff in inputs]
    assert records[0]["tracks"]
    assert records[1]["tracks"][0]["status"] == "PIXEL_SUPPORTED"
    assert records[1]["tracks"][0]["box_xyxy"][0] == pytest.approx(
        records[0]["tracks"][0]["box_xyxy"][0] + 2, abs=0.3
    )
    assert records[2]["duplicate_pixels"]
    assert all(r["identity_status"] == "UNRESOLVED" for r in records)
    before = sequence.records
    assert sequence.observe(inputs[-1][0], cutoff=inputs[-1][1]) == records[-1]
    assert sequence.records == before
    fresh = NaturalTargetSequence(weights_path=weights)
    assert content_sha256([fresh.observe(r, cutoff=c) for r, c in inputs]) == content_sha256(
        records
    )


def test_unknown_is_retained_and_not_forcibly_reacquired(weights):
    image = public_image()
    seq = NaturalTargetSequence(weights_path=weights)
    records = [
        seq.observe(r, cutoff=c)
        for r, c in (
            observation(image, 0),
            observation(np.zeros_like(image), 1),
            observation(image, 2),
        )
    ]
    assert records[0]["status"] == "PIXEL_SUPPORT_AVAILABLE"
    assert records[1]["status"] == records[2]["status"] == "UNKNOWN"
    assert len(seq.records) == 3
    assert records[2]["detector"]["candidates"]  # detector reappearance is not target authority
    assert not records[1]["negative_observation_authorized"]


def test_empty_initial_frame_stays_unknown(weights):
    image = public_image()
    seq = NaturalTargetSequence(weights_path=weights)
    records = [
        seq.observe(r, cutoff=c)
        for r, c in (observation(np.zeros_like(image), 0), observation(image, 1))
    ]
    assert all(r["status"] == "UNKNOWN" for r in records)
    assert len(seq.records) == 2


def test_wrong_scope_order_shape_and_forged_bytes_do_not_advance(weights):
    image = public_image()
    seq = NaturalTargetSequence(weights_path=weights)
    raw, cutoff = observation(image, 0)
    seq.observe(raw, cutoff=cutoff)
    before = seq.records
    bad = [
        observation(image, 0),
        observation(image[:200], 1),
        observation(image, 1, scope=(UUID(int=4), UUID(int=2), UUID(int=3))),
        (replace(raw, payload_bytes=raw.payload_bytes[:-1] + b"x"), cutoff),
        (raw, cutoff + timedelta(seconds=1)),
    ]
    for r, c in bad:
        with pytest.raises(ValueError):
            seq.observe(r, cutoff=c)
        assert seq.records == before
    good, when = observation(image, 1)
    assert seq.observe(good, cutoff=when)["frame_index"] == 1


def test_tracker_fault_rolls_back_all_candidates(weights, monkeypatch):
    image = public_image()
    seq = NaturalTargetSequence(weights_path=weights)
    r, c = observation(image, 0)
    seq.observe(r, cutoff=c)
    before = seq.records
    original = InitializedPixelTargetTracker.update

    def fail_after_update(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected failure after optical flow state mutation")

    r, c = observation(image, 1)
    with monkeypatch.context() as m:
        m.setattr(InitializedPixelTargetTracker, "update", fail_after_update)
        with pytest.raises(RuntimeError, match="injected"):
            seq.observe(r, cutoff=c)
    assert seq.records == before
    assert seq.observe(r, cutoff=c)["frame_index"] == 1


def test_multiple_natural_anchors_remain_separate(weights):
    image = public_image().copy()
    crop = image[80:175, 62:110].copy()
    for x in (15, 180):
        image[60:155, x : x + 48] = crop
    seq = NaturalTargetSequence(weights_path=weights)
    raw, cutoff = observation(image, 0)
    first = seq.observe(raw, cutoff=cutoff)
    assert len(first["tracks"]) >= 2
    assert {t["anchor_id"] for t in first["tracks"]} == {
        str(c["candidate_id"]) for c in first["detector"]["candidates"]
    }
    raw, cutoff = observation(np.roll(image, 2, axis=1), 1)
    second = seq.observe(raw, cutoff=cutoff)
    assert {t["anchor_id"] for t in first["tracks"]} == {t["anchor_id"] for t in second["tracks"]}
    assert second["identity_status"] == "UNRESOLVED"


def test_optical_flow_alone_cannot_force_match_on_blank_image(weights, monkeypatch):
    from dataclasses import replace

    image = public_image()
    seq = NaturalTargetSequence(weights_path=weights)
    raw, cutoff = observation(image, 0)
    first = seq.observe(raw, cutoff=cutoff)
    original = InitializedPixelTargetTracker.update

    def forged_flow(self, rgb, *, frame_index):
        result = original(self, rgb, frame_index=frame_index)
        return replace(
            result,
            box_xyxy=tuple(first["tracks"][0]["box_xyxy"]),
            surviving_points=80,
            forward_backward_error_px=0.0,
        )

    raw, cutoff = observation(np.zeros_like(image), 1)
    with monkeypatch.context() as m:
        m.setattr(InitializedPixelTargetTracker, "update", forged_flow)
        result = seq.observe(raw, cutoff=cutoff)
    assert result["status"] == "UNKNOWN"
    assert result["tracks"][0]["reason"] == "initial_appearance_not_supported"
