"""Evaluator-only actual Unity replay; segmentation never enters method inputs.

Replays original successful requests with identical 96x96 RGB-D settings, adding
instance segmentation for measurement. Checks target poses against original receipts.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import ai2thor
import numpy as np
from ai2thor.controller import Controller

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07"
OUT = ROOT / "docs/reviews/pc_a/proposal_two_round_audit_2026-09-13" / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)
binary = Path(sys.argv[2])


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    with (OUT / name).open("x") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)


private = BASE / "schedule_run/evaluator_only"
bindings = read(private / "binding.json")
schedule = read(private / "schedule.json")
execution = read(private / "execution.json")
by_step = {r["actual_steps"][-1]: e for e, r in zip(schedule["events"], execution, strict=True)}
controller = None
rows = []
started = time.monotonic()
source_before = sha(Path(__file__))
receipt = {
    "scope": "evaluator-only actual Unity replay, not additional training examples",
    "tested_base": "5ec6204dfecc9137523b6c0e5dfb66658e574d41",
    "python": sys.version,
    "sdk_version": ai2thor.__version__,
    "sdk_controller_sha256": sha(Path(ai2thor.__file__).parent / "controller.py"),
    "unity_sha256": sha(binary),
    "house_sha256": sha(BASE / "train_house.json"),
    "original_receipt_sha256": sha(BASE / "receipt.json"),
    "source_before": source_before,
    "complete": False,
    "changed_configuration": {"renderInstanceSegmentation": True},
    "training_started": False,
}


class LocalLogs(Controller):
    @property
    def log_dir(self):
        return str(OUT / "unity_logs")


try:
    controller = LocalLogs(
        local_executable_path=str(binary),
        scene=read(BASE / "train_house.json"),
        width=96,
        height=96,
        renderDepthImage=True,
        renderInstanceSegmentation=True,
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    if controller.last_event.metadata.get("lastActionSuccess") is not True:
        raise RuntimeError("house initialization failed")
    for record in read(BASE / "initialization.json"):
        event = controller.step(**record["request"])
        if not event.metadata["lastActionSuccess"]:
            raise RuntimeError("original clearance initialization failed")
    controller.step(action="GetReachablePositions")
    for path in sorted((private / "raw/observations").glob("*.json")):
        record = read(path)
        event = controller.step(**record["request"])
        step = record["step_index"]
        metadata = event.metadata
        objects = {o["objectId"]: o for o in metadata["objects"]}
        original_metadata = read(private / "raw/evaluator_only" / path.name)
        original = {o["objectId"]: o for o in original_metadata["objects"]}
        camera_error = max(
            abs(metadata["cameraPosition"][k] - original_metadata["cameraPosition"][k])
            for k in ("x", "y", "z")
        )
        view_error = max(
            abs(metadata["agent"]["rotation"][k] - original_metadata["agent"]["rotation"][k])
            for k in ("x", "y", "z")
        )
        view_error = max(
            view_error,
            abs(metadata["agent"]["cameraHorizon"] - original_metadata["agent"]["cameraHorizon"]),
        )
        errors = {
            key: max(
                abs(objects[oid]["position"][axis] - original[oid]["position"][axis])
                for axis in ("x", "y", "z")
            )
            for key, oid in bindings["object_ids"].items()
        }
        row = {
            "step": step,
            "request": record["request"],
            "success": metadata["lastActionSuccess"],
            "pose_max_error_m": errors,
            "camera_position_error_m": camera_error,
            "view_angle_error_degrees": view_error,
            "objects": {
                key: {
                    "metadata_visible": objects[oid]["visible"],
                    "distance_m": objects[oid]["distance"],
                    "mask_pixels": int(event.instance_masks[oid].sum())
                    if oid in event.instance_masks
                    else 0,
                }
                for key, oid in bindings["object_ids"].items()
            },
        }
        if step in by_step:
            planned = by_step[step]
            row.update(
                event_tick=planned["tick"],
                selected=planned["observation_selected"],
                target=planned["instance_key"],
                kind=planned["kind"],
            )
            if planned["observation_selected"]:
                oid = bindings["object_ids"][planned["instance_key"]]
                mask = event.instance_masks.get(oid, np.zeros((96, 96), dtype=bool))
                sensor = OUT / f"evaluator_pixels_{step:06d}.npz"
                with sensor.open("xb") as stream:
                    np.savez(stream, rgb=event.frame, depth=event.depth_frame, target_mask=mask)
                row.update(evaluator_sensor_file=sensor.name, evaluator_sensor_sha256=sha(sensor))
        rows.append(row)
        if (
            not row["success"]
            or max(errors.values()) > 0.002
            or camera_error > 0.002
            or view_error > 0.01
        ):
            raise RuntimeError(f"replay mismatch at {step}")
    selected = [r for r in rows if r.get("selected")]
    summary = {
        "events": len(by_step),
        "released": len(selected),
        "released_metadata_visible": sum(
            r["objects"][r["target"]]["metadata_visible"] for r in selected
        ),
        "released_positive_mask": sum(
            r["objects"][r["target"]]["mask_pixels"] > 0 for r in selected
        ),
        "released_mask_pixels": [r["objects"][r["target"]]["mask_pixels"] for r in selected],
        "released_nonzero_mask_metadata_false": sum(
            r["objects"][r["target"]]["mask_pixels"] > 0
            and not r["objects"][r["target"]]["metadata_visible"]
            for r in selected
        ),
        "all_tracked_pose_errors_within_2mm": True,
        "all_camera_positions_within_2mm_and_angles_within_0_01deg": True,
        "rendered_human_roles_verified": False,
        "perception_or_negative_labels_authorized": False,
    }
    save("summary.json", summary)
    receipt["complete"] = True
    print(json.dumps(summary), flush=True)
except BaseException as error:
    receipt.update(error_type=type(error).__name__, error=str(error))
    raise
finally:
    if controller is not None:
        controller.stop()
    save("steps.json", rows)
    receipt.update(
        seconds=time.monotonic() - started,
        source_after=sha(Path(__file__)),
        source_unchanged=source_before == sha(Path(__file__)),
    )
    save("receipt.json", receipt)
