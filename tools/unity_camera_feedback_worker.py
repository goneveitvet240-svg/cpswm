"""Pixel-only live camera transport with a separate evaluator-only visibility log.

Scene placement is exogenous initialization. Object/agent metadata and masks are
written solely to the evaluator directory; the method response contains RGB and
execution status. No robot manipulation or navigation is asserted.
"""

import argparse
import base64
import io
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import numpy as np


def validate_request(request, seen):
    if set(request) != {"action_id", "action", "degrees"}:
        raise ValueError("camera request must contain only its bounded command")
    identity = request["action_id"]
    UUID(identity)
    if identity in seen:
        raise ValueError("worker will not redispatch an action ID")
    action, degrees = request["action"], request["degrees"]
    if (
        action not in {"Pass", "RotateRight", "RotateLeft"}
        or type(degrees) not in (int, float)
        or not math.isfinite(degrees)
        or not 0 <= degrees <= 90
        or (action == "Pass") != (degrees == 0)
    ):
        raise ValueError("unsupported or unbounded camera request")
    return identity, action, {} if action == "Pass" else {"degrees": degrees}


def method_response(identity, event):
    buffer = io.BytesIO()
    np.save(buffer, event.frame, allow_pickle=False)
    return {
        "action_id": identity,
        "capture_time": datetime.now(UTC).isoformat(),
        "success": event.metadata.get("lastActionSuccess") is True,
        "error": event.metadata.get("errorMessage", ""),
        "rgb_npy": base64.b64encode(buffer.getvalue()).decode(),
    }


def main():
    from ai2thor.controller import Controller

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--house", required=True)
    parser.add_argument("--log-dir", required=True)
    args = parser.parse_args()
    house = json.loads(Path(args.house).read_text())
    target = house["metadata"].pop("cpswm_diagnostic_target")
    private = Path(args.log_dir) / "evaluator_only"
    private.mkdir()

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return args.log_dir

    controller = LocalLogs(
        local_executable_path=args.binary,
        scene=house,
        width=320,
        height=320,
        fieldOfView=60,
        renderInstanceSegmentation=True,
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    seen = set()
    rows = []
    try:
        initial = controller.last_event.metadata
        (private / "initial.json").write_text(json.dumps(initial, indent=2) + "\n")
        objects = {o["objectId"]: o for o in initial["objects"]}
        if target not in objects or objects[target]["objectType"] != "Apple":
            raise ValueError("explicit diagnostic target missing from actual Unity house")
        print("CPSWM_RESPONSE " + json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request == {"stop": True}:
                break
            identity, action, kwargs = validate_request(request, seen)
            seen.add(identity)
            event = controller.step(action=action, **kwargs)
            response = method_response(identity, event)
            mask = event.instance_masks.get(target, np.zeros(event.frame.shape[:2], dtype=bool))
            indices = np.argwhere(mask)
            bbox = (
                None
                if len(indices) == 0
                else [
                    int(indices[:, 1].min()),
                    int(indices[:, 0].min()),
                    int(indices[:, 1].max() + 1),
                    int(indices[:, 0].max() + 1),
                ]
            )
            obj = next(x for x in event.metadata["objects"] if x["objectId"] == target)
            index = len(rows)
            np.save(private / f"{index:03d}-rgb.npy", event.frame, allow_pickle=False)
            np.save(private / f"{index:03d}-mask.npy", mask, allow_pickle=False)
            rows.append(
                {
                    "index": index,
                    "request": request,
                    "success": response["success"],
                    "error": response["error"],
                    "capture_time": response["capture_time"],
                    "target_pixels": int(mask.sum()),
                    "target_bbox": bbox,
                    "target_sdk_visible": obj["visible"],
                    "target_position": obj["position"],
                    "agent": event.metadata["agent"],
                    "camera_position": event.metadata["cameraPosition"],
                    "fov": event.metadata["fov"],
                }
            )
            (private / "actions.json").write_text(json.dumps(rows, indent=2) + "\n")
            print("CPSWM_RESPONSE " + json.dumps(response), flush=True)
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
