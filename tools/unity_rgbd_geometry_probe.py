"""Fixed evaluator-only raycast geometry probe; no queries feed the policy.

Run with the pinned SDK interpreter. Raw depth/RGB and all raycast results are
retained; collider/render discrepancies are reported rather than erased.
"""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from unity_rgbd_capture import FAR, NEAR, camera_values, rgbd_response


def capture(output, *, binary, house):
    from ai2thor.controller import Controller

    output.mkdir(parents=True, exist_ok=False)
    scene = json.loads(house.read_text())
    scene["metadata"].pop("cpswm_diagnostic_target", None)

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return str(output)

    controller = LocalLogs(
        local_executable_path=str(binary),
        scene=scene,
        width=320,
        height=320,
        fieldOfView=60,
        renderDepthImage=True,
        renderInstanceSegmentation=True,
        cameraNearPlane=NEAR,
        cameraFarPlane=FAR,
        add_depth_noise=False,
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    rows = []
    # Predeclared grid and trajectory, including pitch plus yaw. No selection by results.
    pixels = [(u, v) for v in (40, 160, 280) for u in (40, 160, 280)]
    trajectory = [
        dict(action="Pass"),
        dict(action="RotateRight", degrees=30),
        dict(action="RotateLeft", degrees=60),
        dict(action="RotateRight", degrees=30),
        dict(action="LookDown", degrees=30),
        dict(action="LookUp", degrees=60),
    ]
    try:
        for action in ("PausePhysicsAutoSim", "Pass", "Pass"):
            event = controller.step(action=action)
            if not event.metadata["lastActionSuccess"]:
                raise ValueError("preparation failed")
        for index, request in enumerate(trajectory):
            event = controller.step(**request)
            if not event.metadata["lastActionSuccess"]:
                raise ValueError("probe action failed")
            values = camera_values(event)
            depth = np.array(event.depth_frame)
            np.save(output / f"{index:03d}-depth.npy", depth, allow_pickle=False)
            np.save(output / f"{index:03d}-rgb.npy", event.frame, allow_pickle=False)
            # Sensor response persisted before reading any private raycast evaluation.
            response = rgbd_response(str(uuid4()), event)
            (output / f"{index:03d}-response.json").write_text(json.dumps(response) + "\n")
            metadata = event.metadata
            rays = []
            for u, v in pixels:
                query = dict(
                    action="GetCoordinateFromRaycast", x=(u + 0.5) / 320, y=(v + 0.5) / 320
                )
                reply = controller.step(**query)
                if not reply.metadata["lastActionSuccess"]:
                    raise ValueError("raycast failed")
                if camera_values(reply) != values:
                    raise ValueError("raycast changed camera")
                rays.append(
                    dict(
                        pixel=[u, v],
                        request=query,
                        world=reply.metadata["actionReturn"],
                        rendered_depth=float(depth[v, u]),
                        success=True,
                    )
                )
            rows.append(
                dict(index=index, request=request, camera=values, metadata=metadata, rays=rays)
            )
            (output / "evaluator_only.json").write_text(json.dumps(rows, indent=2) + "\n")
        (output / "capture.json").write_text(
            json.dumps(
                dict(
                    status="COMPLETE",
                    frames=len(rows),
                    queries=sum(len(r["rays"]) for r in rows),
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    house_sha256=hashlib.sha256(house.read_bytes()).hexdigest(),
                    scope="FIXED_DEVELOPMENT_GEOMETRY_NOT_POLICY_OR_INDEPENDENT_ACCEPTANCE",
                ),
                indent=2,
            )
            + "\n"
        )
    finally:
        controller.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "binary", "house"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    capture(a.output, binary=a.binary, house=a.house)
