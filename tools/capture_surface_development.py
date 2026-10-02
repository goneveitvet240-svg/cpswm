"""Fixed public calibration capture; SDK masks go only to the separate evaluator."""

import argparse
import base64
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import torch

from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand
from cpswm.system.surface_episode import report_from_surface_state
from cpswm.system.unity_observation import UnityObservationExecutor


def save(p, v):
    p.write_text(json.dumps(v, sort_keys=True, indent=2, allow_nan=False) + "\n")


def run(args):
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    scope = [uuid4() for _ in range(3)]
    seq = MaskSurfaceSequence(
        NaturalMaskSurfaceDetector(
            weights_path=args.mask_weights,
            household_id=scope[0],
            session_id=scope[1],
            trace_id=scope[2],
        )
    )
    queries = [
        dict(category=s.rsplit(":", 1)[0], ordinal=int(s.rsplit(":", 1)[1])) for s in args.target
    ]
    schedule = [
        dict(action="Pass" if d == 0 else "RotateRight" if d > 0 else "RotateLeft", degrees=abs(d))
        for d in args.degrees
    ]
    state = dict(records=[], action_ids=[])
    result = dict(
        status="RUNNING",
        scope="development capture; no Native transactions",
        queries=queries,
        schedule=schedule,
        budget=len(schedule),
        steps=[],
        failures=[],
    )
    camera = None
    try:
        camera = UnityObservationExecutor(
            python=args.sdk_python,
            worker=Path(__file__).with_name("unity_surface_pipeline_worker.py").resolve(),
            binary=args.binary,
            house=args.house,
            log_dir=root / "transport",
            household_id=scope[0],
            session_id=scope[1],
            trace_id=scope[2],
            image_size=320,
            sensor_profile="rgbd_self_pose",
        )
        for index, action in enumerate(schedule):
            command = ObservationCommand(
                uuid4(),
                uuid4(),
                action["action"],
                action["degrees"],
                "predeclared calibration scan",
                (),
                datetime.now(UTC),
            )
            delivery = camera.execute(command)
            folder = root / "public" / f"{index:03d}"
            folder.mkdir(parents=True)
            save(
                folder / "raw.json",
                dict(
                    action_id=str(command.action_id),
                    **action,
                    decision_time=command.decision_time.isoformat(),
                    received_at=delivery.received_at.isoformat(),
                    success=delivery.success,
                    error=delivery.error,
                    observations=[
                        dict(
                            envelope_json=r.envelope_json,
                            payload_base64=base64.b64encode(r.payload_bytes).decode(),
                            capture_receipt_sha256=r.capture_receipt_sha256,
                            depth_unit=r.depth_unit,
                        )
                        for r in delivery.observations
                    ],
                ),
            )
            if not delivery.success:
                raise RuntimeError(delivery.error)
            record, masks = seq.observe(delivery.observations, cutoff=delivery.received_at)
            save(folder / "prediction.json", record)
            (folder / "masks.npy.gz").write_bytes(gzip.compress(masks, mtime=0))
            state["records"].append(record)
            state["action_ids"].append(str(command.action_id))
            state["view_sha256"] = content_sha256(record)
            report = [
                report_from_surface_state(state, **q, reference_action=state["action_ids"][0])
                for q in queries
            ]
            save(folder / "reports.json", report)
            result["steps"].append(
                dict(index=index, action_id=str(command.action_id), reports=report)
            )
            save(root / "result.json", result)
            print(json.dumps(dict(index=index, status=[r["status"] for r in report])), flush=True)
        result.update(
            status="COMPLETED",
            reference_action=state["action_ids"][0],
            physical_dispatches=len(camera._seen),
            final_reports=report,
        )
    except BaseException as e:
        result["status"] = "FAILED"
        result["failures"].append(dict(type=type(e).__name__, message=str(e)))
        raise
    finally:
        save(root / "result.json", result)
        if camera:
            camera.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("output", "mask-weights", "sdk-python", "binary", "house"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--degrees", nargs="+", type=float, required=True)
    p.add_argument("--target", nargs="+", required=True)
    a = p.parse_args()
    torch.set_num_threads(2)
    run(a)
