"""Public RGB-D/self-pose whitelist for the pinned Unity development renderer.

No object metadata, target IDs, masks or object poses cross this response.
This helper runs in the SDK interpreter and imports no CPSWM model code.
"""

import base64
import io
import math

import numpy as np
from unity_camera_feedback_worker import method_response

NEAR, FAR = 0.1, 20.0
UNITY_COMMIT = "f0825767cd50d69f666c7f282e54abfe58f1e917"


def camera_values(event):
    meta = event.metadata
    h, w = event.frame.shape[:2]
    rotation = meta["agent"]["rotation"]
    if (
        meta["depthFormat"] != "Meters"
        or (meta["screenWidth"], meta["screenHeight"]) != (w, h)
        or abs(rotation["x"]) > 1e-5
        or abs(rotation["z"]) > 1e-5
        or event.depth_frame is None
        or event.depth_frame.shape != (h, w)
        or event.depth_frame.dtype != np.float32
    ):
        raise ValueError("unsupported camera geometry or depth encoding")
    values = dict(
        width=w,
        height=h,
        vertical_fov_degrees=meta["fov"],
        position_m=[meta["cameraPosition"][k] for k in ("x", "y", "z")],
        yaw_degrees=rotation["y"],
        pitch_degrees=meta["agent"]["cameraHorizon"],
        near_plane_m=NEAR,
        far_plane_m=FAR,
        depth_semantics="Linear01Depth_times_far_minus_near",
        depth_unit="m",
        unity_commit=UNITY_COMMIT,
        world_frame="unity-scene-world-x-right-y-up-z-forward",
        localization="AUTHORIZED_IDEAL_SIMULATOR_CAMERA_SELF_POSE",
    )
    if not all(
        math.isfinite(v)
        for v in (
            *values["position_m"],
            values["yaw_degrees"],
            values["pitch_degrees"],
            values["vertical_fov_degrees"],
        )
    ):
        raise ValueError("nonfinite camera geometry")
    return values


def rgbd_response(identity, event):
    response = method_response(identity, event)
    response["camera"] = camera_values(event)
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(event.depth_frame), allow_pickle=False)
    response["depth_npy"] = base64.b64encode(buffer.getvalue()).decode()
    return response
