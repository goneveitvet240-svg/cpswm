"""Paired sensor geometry contract; analytic scenes are controlled fixtures.
PYTEST_DONT_REWRITE: decoder code is bound by the owner.
"""

import base64
import io
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from test_owned_visual_support import SupportDecoder
from unity_rgbd_capture import camera_values, rgbd_response

from cpswm.perception_mapping.unity_rgbd import (
    PROFILE,
    decode_unity_rgbd,
    observations_from_response,
    packet_receipt,
    public_rgb_observations,
    surface_support,
)
from cpswm.system.reproducibility import content_sha256


def event_for(*, yaw=0.0, pitch=0.0, depth=None):
    return SimpleNamespace(
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
        depth_frame=np.full((4, 4), 1.99, dtype=np.float32) if depth is None else depth,
        metadata=dict(
            lastActionSuccess=True,
            errorMessage="",
            depthFormat="Meters",
            screenWidth=4,
            screenHeight=4,
            fov=90.0,
            cameraPosition=dict(x=1.0, y=2.0, z=3.0),
            agent=dict(rotation=dict(x=0.0, y=yaw, z=0.0), cameraHorizon=pitch),
            objects=[dict(objectId="EVALUATOR_ONLY", position=dict(x=42))],
            colors=["FORBIDDEN"],
        ),
    )


def packet(*, event=None, action=None, scope=None, capture=None):
    event = event or event_for()
    action = action or uuid4()
    response = rgbd_response(str(action), event)
    capture = capture or datetime.now(UTC)
    response["capture_time"] = capture.isoformat()
    scope = scope or (uuid4(), uuid4(), uuid4())
    provenance = dict(
        worker="a" * 64,
        unity="b" * 64,
        house="c" * 64,
        capture_configuration=content_sha256((PROFILE, 4, 4, 90.0, 0.1, 20.0, False)),
    )
    cutoff = capture + timedelta(seconds=1)
    return observations_from_response(
        response, action_id=action, scope=scope, arrival=cutoff, provenance=provenance
    ), cutoff


def rewrite_packet(rows, *, pose_changes=None, depth=None):
    """Coherently rebuild all channel hashes and receipt (not a broken-hash strawman)."""
    payloads = [r.payload_bytes for r in rows]
    if depth is not None:
        b = io.BytesIO()
        np.save(b, depth, allow_pickle=False)
        payloads[1] = b.getvalue()
    pose = json.loads(payloads[2])
    pose.update(pose_changes or {})
    pose["depth_sha256"] = sha256(payloads[1]).hexdigest()
    payloads[2] = json.dumps(pose).encode()
    receipt = packet_receipt(tuple(payloads))
    updated = []
    for r, data in zip(rows, payloads, strict=True):
        e = r.envelope()
        e = e.model_copy(
            update={
                "payload": e.payload.model_copy(
                    update={"payload_sha256": sha256(data).hexdigest(), "size_bytes": len(data)}
                )
            }
        )
        updated.append(
            replace(
                r,
                payload_bytes=data,
                envelope_json=e.model_dump_json(),
                capture_receipt_sha256=receipt,
            )
        )
    return tuple(updated)


@pytest.mark.parametrize(
    "yaw,pitch,expected",
    [
        (0.0, 0.0, (1.5, 1.5, 5.0)),
        (90.0, 0.0, (3.0, 1.5, 2.5)),
        (180.0, 0.0, (0.5, 1.5, 1.0)),
        (270.0, 0.0, (-1.0, 1.5, 3.5)),
        (0.0, 90.0, (1.5, 0.0, 2.5)),
        (90.0, 90.0, (0.5, 0.0, 2.5)),
    ],
)
def test_unprojection_axis_scale_pitch_pixel_centre(yaw, pitch, expected):
    rows, cutoff = packet(event=event_for(yaw=yaw, pitch=pitch))
    camera, z = decode_unity_rgbd(rows, cutoff=cutoff)
    assert camera.world_point(2, 2, float(z[2, 2])) == pytest.approx(expected, abs=1e-6)
    assert not z.flags.writeable
    assert public_rgb_observations(rows, cutoff=cutoff) == rows[:1]


def test_world_surfaces_keep_raw_sources_and_do_not_gain_identity_or_density():
    rows, cutoff = packet()
    frame = SupportDecoder().measurements(rows[:1], cutoff=cutoff)[0]
    support = surface_support(rows, frame, cutoff=cutoff)
    assert len(support.candidates) == 3
    assert [c.box_pixel_count for c in support.candidates] == [16, 4, 4]
    assert all(
        c.samples and c.object_instance_id is c.object_centre_m is c.probability is None
        for c in support.candidates
    )
    assert support.identity_association is support.likelihood_model is None
    assert support.memory_write_authorized is False
    assert support.observation_ids == tuple(r.envelope().identity.observation_id for r in rows)


@pytest.mark.parametrize(
    "depth", [np.zeros((4, 4), dtype=np.float32), np.full((4, 4), 19.9, dtype=np.float32)]
)
def test_zero_and_far_plane_are_not_surfaces(depth):
    rows, cutoff = packet(event=event_for(depth=depth))
    f = SupportDecoder().measurements(rows[:1], cutoff=cutoff)[0]
    support = surface_support(rows, f, cutoff=cutoff)
    assert all(c.valid_depth_pixel_count == 0 and c.samples == () for c in support.candidates)


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "reorder",
        "duplicate",
        "receipt",
        "unit",
        "clock",
        "frame",
        "source",
        "scope",
        "time",
        "sensor",
        "archive",
    ],
)
def test_cross_channel_pairing_attacks(attack):
    rows, cutoff = packet()
    rows = list(rows)
    if attack == "missing":
        rows.pop()
    elif attack == "reorder":
        rows.reverse()
    elif attack == "duplicate":
        rows[1] = rows[0]
    elif attack in ("receipt", "unit", "archive"):
        field = {
            "receipt": "capture_receipt_sha256",
            "unit": "depth_unit",
            "archive": "archive_sampling_json",
        }[attack]
        rows[1] = replace(rows[1], **{field: "0" * 64 if attack == "receipt" else "mm"})
    else:
        e = rows[1].envelope()
        if attack == "clock":
            e = e.model_copy(update={"clock_domain": "other"})
        if attack == "frame":
            e = e.model_copy(update={"frame_id": "other"})
        if attack == "source":
            e = e.model_copy(
                update={"metadata": e.metadata.model_copy(update={"source_id": str(uuid4())})}
            )
        if attack == "scope":
            key = uuid4()
            e = e.model_copy(
                update={
                    "metadata": e.metadata.model_copy(update={"trace_id": key}),
                    "identity": e.identity.model_copy(update={"trace_id": key}),
                }
            )
        if attack == "time":
            e = e.model_copy(update={"capture_time": e.capture_time - timedelta(seconds=1)})
        if attack == "sensor":
            e = e.model_copy(update={"sensor": e.sensor.model_copy(update={"sensor_id": "wrong"})})
        rows[1] = replace(rows[1], envelope_json=e.model_dump_json())
    with pytest.raises(ValueError):
        public_rgb_observations(tuple(rows), cutoff=cutoff)


@pytest.mark.parametrize(
    "change",
    [
        {"objects": []},
        {"object_position": [1, 2, 3]},
        {"pitch_degrees": float("nan")},
        {"depth_unit": "mm"},
        {"near_plane_m": 0.2},
        {"width": True},
        {"vertical_fov_degrees": 90.1},
        {"unity_commit": "fake"},
    ],
)
def test_complete_hash_valid_forbidden_or_changed_camera_packet(change):
    rows, cutoff = packet()
    forged = rewrite_packet(rows, pose_changes=change)
    with pytest.raises(ValueError):
        decode_unity_rgbd(forged, cutoff=cutoff)


@pytest.mark.parametrize(
    "depth",
    [
        np.ones((3, 4), dtype=np.float32),
        np.ones((4, 4), dtype=np.float64),
        np.full((4, 4), np.nan, dtype=np.float32),
        np.full((4, 4), -1, dtype=np.float32),
        np.full((4, 4), 200, dtype=np.float32),
    ],
)
def test_complete_hash_valid_bad_depth(depth):
    rows, cutoff = packet()
    forged = rewrite_packet(rows, depth=depth)
    with pytest.raises(ValueError):
        decode_unity_rgbd(forged, cutoff=cutoff)


def test_worker_whitelist_and_camera_origin_is_not_agent_origin():
    e = event_for()
    e.metadata["agent"]["position"] = dict(x=8, y=9, z=10)
    values = camera_values(e)
    assert values["position_m"] == [1.0, 2.0, 3.0]
    response = rgbd_response(str(uuid4()), e)
    assert set(response) == {
        "action_id",
        "capture_time",
        "success",
        "error",
        "rgb_npy",
        "depth_npy",
        "camera",
    }
    assert "EVALUATOR_ONLY" not in json.dumps(response)
    assert np.array_equal(
        np.load(io.BytesIO(base64.b64decode(response["depth_npy"]))), e.depth_frame
    )
    e.metadata["agent"]["rotation"]["z"] = 1
    with pytest.raises(ValueError):
        camera_values(e)


def test_no_future_observation_or_wrong_frame_can_supply_surfaces():
    rows, cutoff = packet()
    f = SupportDecoder().measurements(rows[:1], cutoff=cutoff)[0]
    with pytest.raises(ValueError):
        decode_unity_rgbd(rows, cutoff=cutoff - timedelta(seconds=2))
    with pytest.raises(ValueError):
        surface_support(rows, replace(f, observation_id=uuid4()), cutoff=cutoff)


def test_retained_geometry_float_constants_do_not_change_implementation_binding():
    from cpswm.perception_mapping.unity_rgbd import implementation_binding

    rows, cutoff = packet()
    frame = SupportDecoder().measurements(rows[:1], cutoff=cutoff)[0]
    before = implementation_binding()
    support = surface_support(rows, frame, cutoff=cutoff)
    assert support.candidates[0].samples
    assert implementation_binding() == before
    retained = tuple(surface_support(rows, frame, cutoff=cutoff) for _ in range(10))
    assert len(retained) == 10 and implementation_binding() == before
