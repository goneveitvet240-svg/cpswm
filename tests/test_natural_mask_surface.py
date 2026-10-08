"""Controlled boundary tests; real pinned model inference is a separate experiment."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest
from test_unity_rgbd import event_for, packet, rewrite_packet
from unity_rgbd_capture import rgbd_response

from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector, select_surface
from cpswm.perception_mapping.unity_rgbd import (
    PROFILE,
    decode_unity_rgbd,
    observations_from_response,
)
from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker
from cpswm.system.reproducibility import content_sha256

torch = pytest.importorskip("torch")


def model(scope, *, shift=(0, 0), copies=1):
    detector = object.__new__(NaturalMaskSurfaceDetector)
    detector._torch, detector._scope = torch, scope
    detector._versions, detector._minimum_score = ("controlled", "controlled"), 0.5
    detector._categories = ("N/A", "bottle")
    prediction = predictions(shift=shift, copies=copies)
    detector._model = lambda tensors: [prediction]
    return detector, prediction


def predictions(*, shift=(0, 0), copies=1):
    dx, dy = shift
    masks = torch.zeros((copies, 1, 96, 96), dtype=torch.float32)
    masks[:, :, 20 + dy : 60 + dy, 30 + dx : 70 + dx] = 0.9
    return dict(
        boxes=torch.tensor([[30 + dx, 20 + dy, 70 + dx, 60 + dy]] * copies, dtype=torch.float32),
        scores=torch.full((copies,), 0.9),
        labels=torch.ones(copies, dtype=torch.int64),
        masks=masks,
    )


def wires(scope, *, shift=(0, 0), index=0):
    rgb = np.zeros((96, 96, 3), np.uint8)
    rgb[20:60, 30:70] = np.random.default_rng(55).integers(0, 256, (40, 40, 3), dtype=np.uint8)
    rgb = np.roll(rgb, (shift[1], shift[0]), axis=(0, 1))
    event = event_for()
    event.frame, event.depth_frame = rgb, np.full((96, 96), 1.99, dtype=np.float32)
    event.metadata.update(screenWidth=96, screenHeight=96)
    action = uuid4()
    response = rgbd_response(str(action), event)
    capture = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index)
    response["capture_time"] = capture.isoformat()
    cutoff = capture + timedelta(seconds=1)
    provenance = dict(
        worker="a" * 64,
        unity="b" * 64,
        house="c" * 64,
        capture_configuration=content_sha256((PROFILE, 96, 96, 90.0, 0.1, 20.0, False)),
    )
    return observations_from_response(
        response, action_id=action, scope=scope, arrival=cutoff, provenance=provenance
    ), cutoff


def test_positive_surface_point_and_stable_masked_flow_with_duplicate_content_flag():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    assert first["tracks"][0]["status"] == "FLOW_AND_MASK_SUPPORTED"
    detector._model = lambda tensors: [predictions(shift=(3, 2))]
    second_raw, cutoff = wires(scope, shift=(3, 2), index=1)
    second, _ = sequence.observe(second_raw, cutoff=cutoff)
    a, b = first["tracks"][0], second["tracks"][0]
    assert a["anchor_id"] == b["anchor_id"]
    assert set(b["flow_feature_ids"]) <= set(a["flow_feature_ids"])
    assert set(b["selected_feature_ids"]) <= set(b["flow_feature_ids"])
    assert b["status"] == "FLOW_AND_MASK_SUPPORTED"
    assert b["flow"]["box_xyxy"] == pytest.approx((33, 22, 73, 62), abs=0.2)
    assert not second["memory_update_authorized"] and second["identity_status"] == "UNRESOLVED"
    third_raw, cutoff = wires(scope, shift=(3, 2), index=2)
    third, _ = sequence.observe(third_raw, cutoff=cutoff)
    assert third["duplicate_sensor_content"]


def test_mask_cannot_borrow_background_texture_and_loss_never_reinitializes():
    rgb = np.random.default_rng(20).integers(0, 256, (96, 96, 3), dtype=np.uint8)
    rgb[30:50, 40:60] = 0
    initial = np.zeros((96, 96), bool)
    initial[35:45, 45:55] = True
    tracker = InitializedPixelTargetTracker((30, 20, 70, 60), initial_mask=initial)
    initial[:] = True  # Caller cannot expand the stored foreground support.
    assert tracker.update(rgb, frame_index=0).status == "LOST"
    assert tracker.update(np.roll(rgb, 10, axis=0), frame_index=1).status == "LOST"
    assert tracker.points_uv == ()
    assert (
        InitializedPixelTargetTracker((30, 20, 70, 60)).update(rgb, frame_index=0).surviving_points
        >= 4
    )


def test_unique_existing_energy_reidentifies_lost_track_without_changing_anchor():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    anchor = first["tracks"][0]["anchor_id"]
    sequence._tracks[anchor][1]._lost = True

    raw, cutoff = wires(scope, index=1)
    recovered, _ = sequence.observe(raw, cutoff=cutoff)
    track = recovered["tracks"][0]
    assert track["anchor_id"] == anchor
    assert track["status"] == "REIDENTIFIED_FLOW_AND_MASK_SUPPORTED"
    assert track["identity_status"] == "CONDITIONAL_APPEARANCE_GEOMETRY_ASSOCIATION"
    assert track["reidentification"]["status"] == "ACCEPTED_UNIQUE_REIDENTIFICATION"
    assert recovered["accepted_reidentifications"] == [track["current_candidate_id"]]
    assert track["world_point_m"] is not None


def test_lost_track_keeps_unknown_when_two_candidates_pass_existing_gate():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    anchor = first["tracks"][0]["anchor_id"]
    sequence._tracks[anchor][1]._lost = True

    detector._model = lambda tensors: [predictions(copies=2)]
    raw, cutoff = wires(scope, index=1)
    result, _ = sequence.observe(raw, cutoff=cutoff)
    track = result["tracks"][0]
    assert track["status"] == "UNKNOWN_AMBIGUOUS_REIDENTIFICATION"
    assert track["world_point_m"] is None and track["current_candidate_id"] is None
    assert (
        len([row for row in track["reidentification"]["comparisons"] if row["accepted_energy"]])
        == 2
    )
    assert result["accepted_reidentifications"] == []


def test_lost_track_keeps_unknown_without_compatible_candidate_then_can_recover():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    anchor = first["tracks"][0]["anchor_id"]
    sequence._tracks[anchor][1]._lost = True
    empty = dict(
        boxes=torch.empty((0, 4)),
        scores=torch.empty((0,)),
        labels=torch.empty((0,), dtype=torch.int64),
        masks=torch.empty((0, 1, 96, 96)),
    )
    detector._model = lambda tensors: [empty]
    raw, cutoff = wires(scope, index=1)
    unknown, _ = sequence.observe(raw, cutoff=cutoff)
    assert unknown["tracks"][0]["status"] == "UNKNOWN_NO_REIDENTIFICATION_SUPPORT"
    assert unknown["accepted_reidentifications"] == []

    detector._model = lambda tensors: [predictions()]
    raw, cutoff = wires(scope, index=2)
    recovered, _ = sequence.observe(raw, cutoff=cutoff)
    assert recovered["tracks"][0]["anchor_id"] == anchor
    assert recovered["tracks"][0]["status"] == "REIDENTIFIED_FLOW_AND_MASK_SUPPORTED"


def test_two_lost_anchors_cannot_share_one_reidentification_candidate():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope, copies=2)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    for anchor in [track["anchor_id"] for track in first["tracks"]]:
        sequence._tracks[anchor][1]._lost = True

    detector._model = lambda tensors: [predictions()]
    raw, cutoff = wires(scope, index=1)
    result, _ = sequence.observe(raw, cutoff=cutoff)
    assert len(result["tracks"]) == 2
    assert all(
        track["status"] == "UNKNOWN_SHARED_REIDENTIFICATION_CANDIDATE" for track in result["tracks"]
    )
    assert all(track["current_candidate_id"] is None for track in result["tracks"])
    assert result["accepted_reidentifications"] == []


def test_late_category_birth_is_tracked_but_cannot_replace_first_frame_query():
    from cpswm.system.surface_episode import report_from_surface_state

    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    empty = dict(
        boxes=torch.empty((0, 4)),
        scores=torch.empty((0,)),
        labels=torch.empty((0,), dtype=torch.int64),
        masks=torch.empty((0, 1, 96, 96)),
    )
    detector._model = lambda tensors: [empty]
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    assert first["tracks"] == []

    detector._model = lambda tensors: [predictions()]
    raw, cutoff = wires(scope, index=1)
    second, _ = sequence.observe(raw, cutoff=cutoff)
    assert len(second["tracks"]) == 1 and len(second["late_births"]) == 1
    track = second["tracks"][0]
    assert track["status"] == "LATE_BIRTH_FLOW_AND_MASK_SUPPORTED"
    assert track["birth_frame"] == 1 and not track["query_eligible"]
    report = report_from_surface_state(
        dict(view_sha256="view", records=[first, second], history={}, action_ids=["a", "b"]),
        category="bottle",
        ordinal=0,
        reference_action="a",
    )
    assert report["status"] == "unknown"
    assert report["reason"] == "initial_query_unresolved"


def test_public_point_rule_tie_depth_and_unknown_no_fabrication():
    rows, cutoff = packet()
    camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
    p = np.zeros((4, 4), np.float32)
    assert select_surface(camera, depth, p)["status"] == "UNKNOWN_NO_MASK"
    p[3, 1] = p[0, 2] = 0.9
    point = select_surface(camera, depth, p)
    assert point["selected_pixel_uv"] == [1, 3]  # u first, not row-major v first.
    assert point["world_point_m"] == pytest.approx(camera.world_point(1, 3, float(depth[3, 1])))
    assert select_surface(camera, np.zeros_like(depth), p)["world_point_m"] is None
    assert select_surface(camera, depth, p, support_uv=())["world_point_m"] is None
    point = select_surface(camera, depth, p, support_uv=((2, 0),))
    assert point["selected_pixel_uv"] == [2, 0]


@pytest.mark.parametrize("attack", ["nan", "range", "dtype", "shape"])
def test_complete_malformed_native_masks_rejected_then_legal_retry(attack):
    scope = tuple(uuid4() for _ in range(3))
    detector, prediction = model(scope)
    raw, cutoff = wires(scope)
    if attack == "nan":
        prediction["masks"][0, 0, 0, 0] = float("nan")
    elif attack == "range":
        prediction["masks"][0, 0, 0, 0] = 1.01
    elif attack == "dtype":
        prediction["masks"] = prediction["masks"].double()
    else:
        prediction["masks"] = prediction["masks"][:, :, :95]
    sequence = MaskSurfaceSequence(detector)
    with pytest.raises(ValueError):
        sequence.observe(raw, cutoff=cutoff)
    assert sequence._index == 0 and not sequence._tracks and not sequence._observations
    detector._model = lambda tensors: [predictions()]
    assert (
        sequence.observe(raw, cutoff=cutoff)[0]["tracks"][0]["status"] == "FLOW_AND_MASK_SUPPORTED"
    )


def test_ambiguous_current_masks_do_not_force_a_match_or_replace_anchor():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    first, _ = sequence.observe(raw, cutoff=cutoff)
    detector._model = lambda tensors: [predictions(copies=2)]
    raw, cutoff = wires(scope, index=1)
    second, _ = sequence.observe(raw, cutoff=cutoff)
    track = second["tracks"][0]
    assert track["anchor_id"] == first["tracks"][0]["anchor_id"]
    assert track["status"] == "UNKNOWN_AMBIGUOUS_CURRENT_MASK_SUPPORT"
    assert track["world_point_m"] is None and track["current_candidate_id"] is None
    assert len(track["mask_support"]) == 2


def test_shared_current_mask_missing_mask_and_provisional_late_initialization():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope, copies=2)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    sequence.observe(raw, cutoff=cutoff)
    detector._model = lambda tensors: [predictions()]
    raw, cutoff = wires(scope, index=1)
    result, _ = sequence.observe(raw, cutoff=cutoff)
    assert all(t["status"] == "UNKNOWN_SHARED_CURRENT_MASK" for t in result["tracks"])
    assert all(
        t["world_point_m"] is None and t["current_candidate_id"] is None for t in result["tracks"]
    )
    empty = dict(
        boxes=torch.empty((0, 4)),
        scores=torch.empty((0,)),
        labels=torch.empty((0,), dtype=torch.int64),
        masks=torch.empty((0, 1, 96, 96)),
    )
    detector._model = lambda tensors: [empty]
    raw, cutoff = wires(scope, index=2)
    result, _ = sequence.observe(raw, cutoff=cutoff)
    assert all(t["status"] == "UNKNOWN_NO_CURRENT_MASK_SUPPORT" for t in result["tracks"])
    fresh = MaskSurfaceSequence(detector)
    fresh.observe(raw, cutoff=cutoff)
    detector._model = lambda tensors: [predictions()]
    raw, cutoff = wires(scope, index=3)
    late = fresh.observe(raw, cutoff=cutoff)[0]
    assert len(late["tracks"]) == 1
    assert late["tracks"][0]["status"] == "LATE_BIRTH_FLOW_AND_MASK_SUPPORTED"
    assert not late["tracks"][0]["query_eligible"]


def test_scope_time_duplicate_receipt_and_calibration_attacks_preserve_flow_state():
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    sequence.observe(raw, cutoff=cutoff)
    snapshot = deepcopy(sequence._tracks)
    before = sequence._index, set(sequence._observations)
    other, later = wires(scope, index=1)
    bad = rewrite_packet(other, pose_changes={"width": 95})
    for rows, when in (
        (raw, cutoff),
        (other, later - timedelta(days=1)),
        (bad, later),
        (wires(tuple(uuid4() for _ in range(3)), index=1)[0], later),
    ):
        with pytest.raises(ValueError):
            sequence.observe(rows, cutoff=when)
        assert (sequence._index, sequence._observations) == before
        for key in snapshot:
            assert sequence._tracks[key][1].points_uv == snapshot[key][1].points_uv
    assert sequence.observe(other, cutoff=later)[0]["frame_index"] == 1


def test_low_score_retained_without_position_and_wrong_weight_rejected(tmp_path):
    scope = tuple(uuid4() for _ in range(3))
    detector, p = model(scope)
    p["scores"][0] = 0.49
    raw, cutoff = wires(scope)
    result = detector.infer_surface(raw, cutoff=cutoff)
    assert len(result.record["candidates"]) == 1
    assert result.record["candidates"][0]["status"] == "BELOW_DETECTOR_THRESHOLD"
    assert result.record["candidates"][0]["world_point_m"] is None
    weights = tmp_path / "forged.pth"
    weights.write_bytes(b"forged complete model")
    with pytest.raises(ValueError, match="pinned"):
        NaturalMaskSurfaceDetector(
            weights_path=weights, household_id=scope[0], session_id=scope[1], trace_id=scope[2]
        )


def test_late_track_failure_rolls_back_all_staged_flows_then_retry(monkeypatch):
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope, copies=2)
    sequence = MaskSurfaceSequence(detector)
    raw, cutoff = wires(scope)
    sequence.observe(raw, cutoff=cutoff)
    before = {k: t.points_uv for k, (_, t) in sequence._tracks.items()}
    evidence_before = deepcopy(sequence._evidence)
    real = InitializedPixelTargetTracker.update
    count = 0

    def interrupted(self, *args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("injected second-track failure")
        return real(self, *args, **kwargs)

    detector._model = lambda tensors: [predictions(shift=(3, 2), copies=2)]
    raw, cutoff = wires(scope, shift=(3, 2), index=1)
    with monkeypatch.context() as m:
        m.setattr(InitializedPixelTargetTracker, "update", interrupted)
        with pytest.raises(RuntimeError, match="second-track"):
            sequence.observe(raw, cutoff=cutoff)
    assert sequence._index == 1
    assert {k: t.points_uv for k, (_, t) in sequence._tracks.items()} == before
    assert sequence._evidence == evidence_before
    assert sequence.observe(raw, cutoff=cutoff)[0]["frame_index"] == 1
