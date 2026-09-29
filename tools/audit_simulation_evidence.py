"""Recompute archived simulator observations without reusing their summary arithmetic.

A local reproducibility audit, not an independent simulator attestation. Private
masks are read only after the optional fresh public-pixel detector execution.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import numpy as np
import torch
from run_camera_measurement_grid import measure_public

from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
SITES = ("north", "south")
XS = (1.05, 1.25, 1.45)
HEADINGS = tuple(range(195, 346, 15))
FRONTENDS = ("ssdlite", "fasterrcnn")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_source_map(revision):
    data = subprocess.check_output(["git", "archive", revision, "src", "tests", "tools"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return {
            m.name: sha(archive.extractfile(m).read())
            for m in archive.getmembers()
            if m.isfile() and m.name.endswith(".py")
        }


def inventory(root, manifest):
    rows = json.loads(manifest.read_text())["artifacts"]
    require(len({r["path"] for r in rows}) == len(rows), "duplicate inventory path")
    for row in rows:
        path = (root / row["path"]).resolve()
        require(path.is_relative_to(root.resolve()), "inventory escapes root")
        require(
            path.stat().st_size == row["bytes"] and sha(path.read_bytes()) == row["sha256"],
            "artifact changed: " + row["path"],
        )
    return {"verified_files": len(rows), "bytes": sum(r["bytes"] for r in rows)}


def mask_box(mask):
    require(mask.dtype == bool and mask.ndim == 2, "mask must be a 2D boolean array")
    yy, xx = np.where(mask)
    return (
        None
        if not len(xx)
        else [int(xx.min()), int(yy.min()), int(xx.max() + 1), int(yy.max() + 1)]
    )


def overlap(box, truth):
    require(len(box) == 4 and all(np.isfinite(box)), "invalid detector box")
    if truth is None:
        return 0.0
    intersection = max(0, min(box[2], truth[2]) - max(box[0], truth[0])) * max(
        0, min(box[3], truth[3]) - max(box[1], truth[1])
    )
    union = (
        (box[2] - box[0]) * (box[3] - box[1])
        + (truth[2] - truth[0]) * (truth[3] - truth[1])
        - intersection
    )
    return float(intersection / union) if union > 0 else 0.0


def inspect_frame(command, delivery, row, raw_bytes, mask, size, heading, initial):
    require(
        delivery.success is True and len(delivery.observations) == 1, "failed or empty delivery"
    )
    raw = delivery.observations[0]
    envelope = raw.envelope()
    require(
        raw.payload_bytes == raw_bytes and envelope.payload.payload_sha256 == sha(raw_bytes),
        "RGB ownership differs",
    )
    rgb = np.load(io.BytesIO(raw_bytes), allow_pickle=False)
    require(rgb.dtype == np.uint8 and rgb.shape == (size, size, 3), "RGB shape or dtype differs")
    require(mask.shape == rgb.shape[:2], "mask and RGB shape differ")
    box = mask_box(mask)
    require(
        row["target_pixels"] == int(mask.sum()) and row["target_bbox"] == box,
        "mask statistics differ",
    )
    require(
        row["request"]
        == dict(action_id=str(command.action_id), action=command.action, degrees=command.degrees)
        and delivery.action_id == command.action_id
        and row["success"] is True,
        "action ownership differs",
    )
    require(envelope.metadata.source_id == str(command.action_id), "pixel command source differs")
    require(
        command.decision_time
        <= envelope.capture_time
        <= envelope.arrival_time
        <= delivery.received_at,
        "capture chronology differs",
    )
    require(
        row["capture_time"] == envelope.capture_time.isoformat(),
        "private/public capture time differs",
    )
    require(
        row["fov"] == 60
        and row["image_size"] == [size, size]
        and abs(row["agent"]["rotation"]["y"] - heading) < 1e-3
        and abs(row["agent"]["cameraHorizon"] - 30) < 1e-3,
        "actual camera configuration differs",
    )
    require(
        all(
            abs(row["agent"]["position"][k] - initial["agent"]["position"][k]) < 1e-4
            and abs(row["camera_position"][k] - initial["cameraPosition"][k]) < 1e-4
            for k in ("x", "y", "z")
        ),
        "camera translated during static sweep",
    )
    return box


def audit_grid(directory, *, size, historical_sources, weights=None):
    plan = json.loads((directory / "grid.json").read_text())
    expected = [
        dict(site=s, camera_x=x, directory=f"{s}-{x}", status="COMPLETE", image_size=size)
        for s in SITES
        for x in XS
    ]
    require(plan == expected, "full declared grid differs")
    groups, frames = {}, []
    for cell in plan:
        case = directory / cell["directory"]
        capture = json.loads((case / "capture.json").read_text())
        require(
            capture["source_files"] == historical_sources
            and capture["source_sha256"] == content_sha256(historical_sources),
            "historical source map differs from Git",
        )
        document = (case / "capture-state.json").read_bytes()
        require(sha(document) == capture["state_sha256"], "owned state hash differs")
        records = StateCodec().loads(document.decode())
        predictions = json.loads((case / "predictions.json").read_text())
        require(len(records) == 11 and capture["status"] == "COMPLETE", "incomplete capture")
        if weights is not None:
            fresh = measure_public(records, weights=weights)
            require(fresh == predictions, "fresh public pixel predictions differ")
        # Only after inference read private evaluator data.
        private = case / "unity-logs/evaluator_only"
        initial = json.loads((private / "initial.json").read_text())
        truth = json.loads((private / "actions.json").read_text())
        require(len(truth) == 11, "private frame count differs")
        ids = ()
        for i, ((command, delivery), row) in enumerate(zip(records, truth, strict=True)):
            require(
                (command.action, command.degrees)
                == (("Pass", 0.0) if i == 0 else ("RotateRight", 15.0))
                and command.source_ids == ids
                and row["index"] == i,
                "public schedule differs",
            )
            ids += tuple(o.envelope().identity.observation_id for o in delivery.observations)
            mask = np.load(private / f"{i:03d}-mask.npy", allow_pickle=False)
            box = inspect_frame(
                command,
                delivery,
                row,
                (private / f"{i:03d}-rgb.npy").read_bytes(),
                mask,
                size,
                HEADINGS[i],
                initial,
            )
            observations = {}
            for frontend in FRONTENDS:
                all_frames = predictions["measurements"][frontend]
                require(len(all_frames) == 11, "detector frame coverage differs")
                prediction = all_frames[i]
                raw = delivery.observations[0]
                require(
                    prediction["input_sha256"] == sha(raw.payload_bytes)
                    and prediction["observation_id"] == str(raw.envelope().identity.observation_id)
                    and prediction["minimum_score"] == 0.5
                    and prediction["identity_status"] == "UNRESOLVED"
                    and prediction["negative_observation_authorized"] is False,
                    "prediction authority or image differs",
                )
                candidates = [c for c in prediction["candidates"] if c["category"] == "apple"]
                ious = [overlap(c["box_xyxy"], box) for c in candidates]
                key = f"{frontend}:{cell['site']}:{cell['camera_x']}"
                g = groups.setdefault(
                    key,
                    dict(
                        frames=0,
                        visible_frames=0,
                        visible_with_candidate=0,
                        visible_with_overlapping_candidate=0,
                        no_target_pixels_frames=0,
                        candidate_without_target_pixels=0,
                    ),
                )
                g["frames"] += 1
                visible = bool(mask.any())
                g["visible_frames"] += int(visible)
                g["no_target_pixels_frames"] += int(not visible)
                g["visible_with_candidate"] += int(visible and bool(candidates))
                g["visible_with_overlapping_candidate"] += int(visible and any(v > 0 for v in ious))
                g["candidate_without_target_pixels"] += int(not visible and bool(candidates))
                observations[frontend] = dict(
                    scores=[c["detector_score"] for c in candidates], bbox_ious=ious
                )
            frames.append(
                dict(
                    cell=cell["directory"],
                    index=i,
                    heading=HEADINGS[i],
                    target_pixels=int(mask.sum()),
                    rgb_sha256=sha(raw.payload_bytes),
                    frontends=observations,
                )
            )
    require(
        groups == json.loads((directory / "summary.json").read_text())["groups"],
        "published denominator or counts differ",
    )
    return dict(
        image_size=size,
        frames=len(frames),
        fresh_detector_readouts=len(frames) * 2 if weights else 0,
        groups=groups,
        raw_rows=frames,
    )


def main(args):
    torch.set_num_threads(2)
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    source = git_source_map("b0a2abaeb945ab60f8fd6697ec10595db92a8596")
    weights = (
        None
        if args.mode == "records"
        else dict(ssdlite=args.ssdlite_weights, fasterrcnn=args.fasterrcnn_weights)
    )
    result = dict(
        scope="LOCAL_ARCHIVED_RECORD_AND_MEASUREMENT_AUDIT_NOT_EXTERNAL_ATTESTATION",
        mode=args.mode,
        auditor_sha256=sha(Path(__file__).read_bytes()),
        historical_code="b0a2abaeb945ab60f8fd6697ec10595db92a8596",
        inventory=inventory(args.archive, args.inventory),
    )
    (output / "inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    result["grids"] = []
    for size in (320, 640):
        row = audit_grid(
            args.archive / "round7-attempt01" / f"grid-{size}",
            size=size,
            historical_sources=source,
            weights=weights,
        )
        result["grids"].append(row)
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                dict(size=size, frames=row["frames"], fresh_readouts=row["fresh_detector_readouts"])
            ),
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("records", "inference"), required=True)
    for name in ("archive", "inventory", "output", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
