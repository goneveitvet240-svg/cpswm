"""Fixed geometry trace checks. Fixtures test protocol, not simulator accuracy."""

from copy import deepcopy

import pytest
from test_unity_rgbd import event_for, packet
from unity_rgbd_capture import camera_values
from verify_rgbd_geometry import TRAJECTORY, validate_protocol_frame

from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd


def protocol_frame(index):
    yaw = (270, 300, 240, 270, 270, 270)[index]
    pitch = (30, 30, 30, 30, 60, 0)[index]
    event = event_for(yaw=float(yaw), pitch=float(pitch))
    request = deepcopy(TRAJECTORY[index])
    event.metadata["lastAction"] = request["action"]
    rows, cutoff = packet(event=event)
    camera, _ = decode_unity_rgbd(rows, cutoff=cutoff)
    return camera.model_dump(mode="json"), dict(
        index=index, request=request, metadata=event.metadata, camera=camera_values(event)
    )


@pytest.mark.parametrize("index", range(6))
def test_positive_full_fixed_trajectory(index):
    camera, row = protocol_frame(index)
    initial, _ = protocol_frame(0)
    validate_protocol_frame(camera, row, index=index, initial_camera=initial)


@pytest.mark.parametrize(
    "attack",
    [
        "request",
        "sdk_action",
        "success",
        "error",
        "packet",
        "yaw",
        "pitch",
        "origin",
        "fov",
        "size",
        "unit",
        "index",
    ],
)
def test_reject_protocol_forgery_with_otherwise_complete_camera_fields(attack):
    camera, row = protocol_frame(1)
    initial, _ = protocol_frame(0)
    if attack == "request":
        row["request"] = dict(action="Pass")
        row["metadata"]["lastAction"] = "Pass"
    elif attack == "sdk_action":
        row["metadata"]["lastAction"] = "Pass"
    elif attack == "success":
        row["metadata"]["lastActionSuccess"] = False
    elif attack == "error":
        row["metadata"]["errorMessage"] = "failed"
    elif attack == "packet":
        row["camera"]["yaw_degrees"] += 10
    elif attack in ("yaw", "pitch"):
        key = "yaw_degrees" if attack == "yaw" else "pitch_degrees"
        camera[key] += 10
        row["camera"][key] += 10
        if attack == "yaw":
            row["metadata"]["agent"]["rotation"]["y"] += 10
        else:
            row["metadata"]["agent"]["cameraHorizon"] += 10
    elif attack == "origin":
        camera["position_m"][0] += 1
        row["camera"]["position_m"][0] += 1
        row["metadata"]["cameraPosition"]["x"] += 1
    elif attack == "fov":
        row["metadata"]["fov"] += 1
    elif attack == "size":
        row["metadata"]["screenWidth"] += 1
    elif attack == "unit":
        row["metadata"]["depthFormat"] = "Millimeters"
    else:
        row["index"] = 0
    with pytest.raises(ValueError):
        validate_protocol_frame(camera, row, index=1, initial_camera=initial)


def test_simulator_float_roundoff_allowed_but_not_real_motion_change():
    camera, row = protocol_frame(1)
    initial, _ = protocol_frame(0)
    camera["yaw_degrees"] += 1e-5
    row["camera"]["yaw_degrees"] += 1e-5
    row["metadata"]["agent"]["rotation"]["y"] += 1e-5
    validate_protocol_frame(camera, row, index=1, initial_camera=initial)
