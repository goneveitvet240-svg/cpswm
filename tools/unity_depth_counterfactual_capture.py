"""Live simulator intervention; evaluator controls never enter public observations.

DisableObject is an experiment intervention, not a robot manipulation action.
Pass/Rotate are actual camera observations with recorded success and source IDs.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from unity_rgbd_capture import FAR, NEAR, camera_values, rgbd_response

TARGETS = ("Bowl|surface|2|11", "WineBottle|surface|2|8", "SoapBottle|surface|2|14")


def run(output, binary, house):
    from ai2thor.controller import Controller

    output.mkdir(parents=True, exist_ok=False)
    scene = json.loads(house.read_text())
    scene["metadata"].pop("cpswm_diagnostic_target", None)
    # Match the archived 225 -> 255 degree camera trajectory. The source house
    # defaults to 270 degrees and is not itself the earlier acquisition pose.
    scene["metadata"]["agent"]["rotation"]["y"] = 225
    scene["metadata"]["agentPoses"]["default"]["rotation"]["y"] = 225
    (output / "scene.json").write_text(json.dumps(scene, sort_keys=True) + "\n")

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return str(output)

    c = LocalLogs(
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
        server_timeout=30,
        server_start_timeout=30,
    )
    actions, frames = [], []

    def step(request, kind):
        action_id = str(uuid4())
        started = datetime.now(UTC).isoformat()
        event = c.step(**request)
        actions.append(
            dict(
                action_id=action_id,
                request=request,
                kind=kind,
                started=started,
                finished=datetime.now(UTC).isoformat(),
                success=event.metadata["lastActionSuccess"],
                error=event.metadata["errorMessage"],
            )
        )
        (output / "actions.json").write_text(json.dumps(actions, indent=2) + "\n")
        if not actions[-1]["success"]:
            raise RuntimeError(actions[-1])
        return event, action_id

    def capture(label, event, action_id):
        d = output / label
        d.mkdir()
        response = rgbd_response(action_id, event)
        (d / "public.json").write_text(json.dumps(response) + "\n")
        np.save(d / "depth.npy", event.depth_frame, allow_pickle=False)
        np.save(d / "rgb.npy", event.frame, allow_pickle=False)
        # All private ground truth is physically separate from the public payload.
        (d / "evaluator.json").write_text(json.dumps(event.metadata) + "\n")
        np.savez_compressed(d / "evaluator-masks.npz", **event.instance_masks)
        frames.append(
            dict(
                label=label,
                action_id=action_id,
                camera=camera_values(event),
                public_sha256=hashlib.sha256((d / "public.json").read_bytes()).hexdigest(),
            )
        )

    try:
        for a in ("PausePhysicsAutoSim", "Pass", "Pass"):
            step(dict(action=a), "preparation")
        event, aid = step(dict(action="RotateRight", degrees=30), "camera_observation")
        capture("baseline", event, aid)
        # Fixed evaluator-only raycast coordinates include the archived glass sample.
        rays = []
        for u, v in ((163, 159), (150, 150), (170, 170), (40, 40), (280, 280)):
            e, _ = step(
                dict(action="GetCoordinateFromRaycast", x=(u + 0.5) / 320, y=(v + 0.5) / 320),
                "evaluator_raycast",
            )
            rays.append(dict(pixel=[u, v], world=e.metadata["actionReturn"]))
        (output / "evaluator-rays.json").write_text(json.dumps(rays, indent=2) + "\n")
        for index, target in enumerate(TARGETS):
            step(dict(action="DisableObject", objectId=target), "evaluator_intervention")
            event, aid = step(dict(action="Pass"), "camera_observation")
            capture(f"removed-{index}", event, aid)
        (output / "capture.json").write_text(
            json.dumps(
                dict(
                    status="COMPLETE",
                    frames=frames,
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    house_sha256=hashlib.sha256((output / "scene.json").read_bytes()).hexdigest(),
                    input_house_sha256=hashlib.sha256(house.read_bytes()).hexdigest(),
                    scope="ACTUAL_UNITY_INTERVENTION_DEVELOPMENT_NOT_PHYSICAL_ROBOT_OR_ACTOR_CALIBRATION",
                ),
                indent=2,
            )
            + "\n"
        )
    finally:
        c.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "binary", "house"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.output, a.binary, a.house)
