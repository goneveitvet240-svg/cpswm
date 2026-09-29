"""Recompute public surface points before comparing separate collider raycasts."""

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from uuid import uuid4

import numpy as np

from cpswm.perception_mapping.unity_rgbd import (
    PROFILE,
    decode_unity_rgbd,
    observations_from_response,
)
from cpswm.system.reproducibility import content_sha256

TRAJECTORY = (
    {"action": "Pass"},
    {"action": "RotateRight", "degrees": 30},
    {"action": "RotateLeft", "degrees": 60},
    {"action": "RotateRight", "degrees": 30},
    {"action": "LookDown", "degrees": 30},
    {"action": "LookUp", "degrees": 60},
)
BINDING_FIELDS = frozenset(
    {
        "schema_id",
        "action_id",
        "capture_time",
        "rgb_sha256",
        "depth_sha256",
        "worker_sha256",
        "unity_sha256",
        "scene_sha256",
        "configuration_sha256",
    }
)


def validate_protocol_frame(camera, row, *, index, initial_camera):
    """A geometrically consistent image cannot substitute for the fixed action trace."""
    if not 0 <= index < len(TRAJECTORY):
        raise ValueError("undeclared geometry frame")
    request = TRAJECTORY[index]
    metadata = row["metadata"]
    if (
        row["index"] != index
        or row["request"] != request
        or metadata["lastAction"] != request["action"]
        or metadata["lastActionSuccess"] is not True
        or metadata["errorMessage"]
    ):
        raise ValueError("geometry action trace differs from fixed protocol")
    if row["camera"] != {k: v for k, v in camera.items() if k not in BINDING_FIELDS}:
        raise ValueError("recorded camera packet differs from public camera")
    yaw = (initial_camera["yaw_degrees"] + (0, 30, -30, 0, 0, 0)[index]) % 360
    pitch = initial_camera["pitch_degrees"] + (0, 0, 0, 0, 30, -30)[index]
    if (
        abs((camera["yaw_degrees"] - yaw + 180) % 360 - 180) > 1e-3
        or abs(camera["pitch_degrees"] - pitch) > 1e-3
        or math.dist(camera["position_m"], initial_camera["position_m"]) > 1e-5
    ):
        raise ValueError("measured camera motion differs from fixed protocol")
    # These are float-renderer execution tolerances, not a noise calibration model.
    if (
        camera["position_m"] != [metadata["cameraPosition"][k] for k in ("x", "y", "z")]
        or camera["pitch_degrees"] != metadata["agent"]["cameraHorizon"]
        or camera["yaw_degrees"] != metadata["agent"]["rotation"]["y"]
        or camera["vertical_fov_degrees"] != metadata["fov"]
        or camera["width"] != metadata["screenWidth"]
        or camera["height"] != metadata["screenHeight"]
        or metadata["depthFormat"] != "Meters"
    ):
        raise ValueError("public camera differs from recorded SDK camera")


def verify(directory, *, expected=None):
    manifest = json.loads((directory / "capture.json").read_text())
    if manifest["status"] != "COMPLETE" or (manifest["frames"], manifest["queries"]) != (6, 54):
        raise ValueError("incomplete fixed geometry probe")
    predictions = []
    # No evaluation metadata is opened until all public unprojection is finished.
    for i in range(6):
        response = json.loads((directory / f"{i:03d}-response.json").read_text())
        capture = datetime.fromisoformat(response["capture_time"])
        provenance = dict(
            worker=hashlib.sha256(
                Path(__file__).with_name("unity_rgbd_geometry_probe.py").read_bytes()
            ).hexdigest(),
            unity=manifest["binary_sha256"],
            house=manifest["house_sha256"],
            capture_configuration=content_sha256((PROFILE, 320, 320, 60.0, 0.1, 20.0, False)),
        )
        rows = observations_from_response(
            response,
            action_id=__import__("uuid").UUID(response["action_id"]),
            scope=(uuid4(), uuid4(), uuid4()),
            arrival=capture + timedelta(seconds=1),
            provenance=provenance,
        )
        camera, depth = decode_unity_rgbd(rows, cutoff=capture + timedelta(seconds=1))
        if (
            rows[0].payload_bytes != (directory / f"{i:03d}-rgb.npy").read_bytes()
            or rows[1].payload_bytes != (directory / f"{i:03d}-depth.npy").read_bytes()
        ):
            raise ValueError("probe source arrays differ")
        points = []
        for v in (40, 160, 280):
            for u in (40, 160, 280):
                d = float(depth[v, u])
                corrected = camera.world_point(u, v, d)
                uncorrected = tuple(
                    camera.position_m[k] + (corrected[k] - camera.position_m[k]) * (20 - 0.1) / 20
                    for k in range(3)
                )
                points.append(
                    dict(
                        pixel=[u, v],
                        rendered_depth=d,
                        corrected=list(corrected),
                        uncorrected=list(uncorrected),
                    )
                )
        predictions.append(dict(camera=camera.model_dump(mode="json"), points=points))
    evaluation = json.loads((directory / "evaluator_only.json").read_text())
    if len(evaluation) != 6:
        raise ValueError("incomplete evaluator raycast coverage")
    identities = [p["camera"]["action_id"] for p in predictions]
    captures = [datetime.fromisoformat(p["camera"]["capture_time"]) for p in predictions]
    if len(set(identities)) != len(identities) or any(a >= b for a, b in pairwise(captures)):
        raise ValueError("repeated camera action or noncausal geometry capture")
    residuals = []
    for i, (pred, row) in enumerate(zip(predictions, evaluation, strict=True)):
        if row["index"] != i or len(row["rays"]) != 9:
            raise ValueError("probe frame/query order differs")
        validate_protocol_frame(
            pred["camera"], row, index=i, initial_camera=predictions[0]["camera"]
        )
        meta = row["metadata"]
        camera = pred["camera"]
        if (
            camera["position_m"] != [meta["cameraPosition"][k] for k in ("x", "y", "z")]
            or camera["pitch_degrees"] != meta["agent"]["cameraHorizon"]
            or camera["yaw_degrees"] != meta["agent"]["rotation"]["y"]
        ):
            raise ValueError("public camera differs from recorded SDK camera")
        for point, ray in zip(pred["points"], row["rays"], strict=True):
            u, v = point["pixel"]
            if (
                ray["pixel"] != point["pixel"]
                or ray["rendered_depth"] != point["rendered_depth"]
                or ray["request"]
                != dict(action="GetCoordinateFromRaycast", x=(u + 0.5) / 320, y=(v + 0.5) / 320)
                or ray["success"] is not True
            ):
                raise ValueError("raycast pairing differs")
            truth = [ray["world"][k] for k in ("x", "y", "z")]
            if not all(math.isfinite(x) for x in truth) or truth == [0, 0, 0]:
                raise ValueError("raycast no-hit or invalid result")
            residuals.append(
                dict(
                    frame=i,
                    pixel=point["pixel"],
                    raycast_world=truth,
                    **{k: point[k] for k in ("corrected", "uncorrected")},
                    corrected_error_m=math.dist(point["corrected"], truth),
                    uncorrected_error_m=math.dist(point["uncorrected"], truth),
                )
            )
    result = dict(
        scope="SAME_MACHINE_RENDER_DEPTH_VS_COLLIDER_GEOMETRY_NOT_EMPIRICAL_NOISE_CALIBRATION",
        frames=6,
        rays=54,
        residuals=residuals,
        summary={},
    )
    for key in ("corrected", "uncorrected"):
        errors = np.array([r[key + "_error_m"] for r in residuals])
        result["summary"][key] = dict(
            median_m=float(np.median(errors)),
            p90_m=float(np.quantile(errors, 0.9)),
            max_m=float(errors.max()),
            within_1cm=int((errors <= 0.01).sum()),
            within_5cm=int((errors <= 0.05).sum()),
        )
    if expected is not None and json.loads(expected.read_text()) != result:
        raise ValueError("fresh geometry evaluation differs")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    target = a.directory / "evaluation.json"
    result = verify(a.directory, expected=target if a.verify else None)
    if not a.verify:
        if target.exists():
            raise ValueError("refuse to overwrite evaluation")
        target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"]))
