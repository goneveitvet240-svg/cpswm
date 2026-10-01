"""Collect a declared camera sequence; evaluate separately from public inference.

This is a visual-support diagnostic, not an active policy or task-success test.
"""

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import torch

from cpswm.perception_mapping.natural_target_sequence import NaturalTargetSequence
from cpswm.system.structure_two_continuous_input import ObservationCommand
from cpswm.system.unity_observation import UnityObservationExecutor


def run(args):
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    sequence = NaturalTargetSequence(weights_path=Path(args.weights))
    result = dict(
        status="RUNNING",
        scope="fixed-scan visual support only",
        schedule=args.degrees,
        frames=[],
        failures=[],
        identity_status="UNRESOLVED",
    )
    camera = None
    try:
        scope = tuple(uuid4() for _ in range(3))
        camera = UnityObservationExecutor(
            python=Path(args.sdk_python),
            worker=Path(__file__).with_name("unity_target_sequence_worker.py"),
            binary=Path(args.binary),
            house=Path(args.house),
            log_dir=root / "transport",
            household_id=scope[0],
            session_id=scope[1],
            trace_id=scope[2],
            image_size=320,
            sensor_profile="rgbd_self_pose",
        )
        for index, degrees in enumerate(args.degrees):
            now = datetime.now(UTC)
            command = ObservationCommand(
                uuid4(),
                uuid4(),
                "RotateRight",
                degrees,
                "declared visual-support diagnostic",
                (),
                now,
            )
            delivery = camera.execute(command)
            frame_dir = root / "public" / f"{index:03d}"
            frame_dir.mkdir(parents=True)
            wires = []
            for raw in delivery.observations:
                wires.append(
                    dict(
                        envelope_json=raw.envelope_json,
                        payload_base64=base64.b64encode(raw.payload_bytes).decode(),
                        capture_receipt_sha256=raw.capture_receipt_sha256,
                        depth_unit=raw.depth_unit,
                    )
                )
            (frame_dir / "raw.json").write_text(
                json.dumps(
                    dict(
                        action_id=str(command.action_id),
                        action=command.action,
                        degrees=degrees,
                        decision_time=now.isoformat(),
                        received_at=delivery.received_at.isoformat(),
                        success=delivery.success,
                        error=delivery.error,
                        observations=wires,
                    )
                )
            )
            if not delivery.success:
                raise RuntimeError(delivery.error)
            record = sequence.observe(delivery.observations[0], cutoff=delivery.received_at)
            result["frames"].append(record)
            (root / "result.json").write_text(json.dumps(result, default=str, indent=2))
            print(
                json.dumps(
                    dict(
                        index=index,
                        status=record["status"],
                        detections=len(record["detector"]["candidates"]),
                        supported=sum(t["status"] == "PIXEL_SUPPORTED" for t in record["tracks"]),
                    )
                ),
                flush=True,
            )
        result["status"] = "CAPTURE_COMPLETED"
    except BaseException as exc:
        result["status"] = "FAILED"
        result["failures"].append(dict(type=type(exc).__name__, message=str(exc)))
        raise
    finally:
        (root / "result.json").write_text(json.dumps(result, default=str, indent=2))
        if camera is not None:
            camera.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "weights", "sdk-python", "binary", "house"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--degrees", nargs="+", type=float, required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    run(args)
