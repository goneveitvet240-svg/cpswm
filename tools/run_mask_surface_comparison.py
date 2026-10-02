"""Pinned public sequence inference followed by a separate geometry evaluator.

No simulator annotation enters inference. All original frames and all natural
mask proposals are kept. This is a development comparison, not a task benchmark.
"""

import argparse
import base64
import gzip
import json
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import numpy as np
import torch

from cpswm.data_preflight.instance_affinity import grid_pixels
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector
from cpswm.perception_mapping.natural_target_sequence import NaturalTargetSequence
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256

TRIALS = {"live-1deg": 11, "live-5deg": 5}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def checked(path, pin):
    if digest(path) != pin:
        raise ValueError(f"artifact differs from external pin: {path}")
    return load(path)


def prepare(source, output):
    if output.exists():
        raise ValueError("manifest output directory must be new")
    public, evaluation = [], []
    for trial, count in TRIALS.items():
        original = load(source / trial / "result.json")
        if original["status"] != "CAPTURE_COMPLETED" or len(original["frames"]) != count:
            raise ValueError("original complete fixed sequence differs")
        frames = sorted((source / trial / "public").glob("*/raw.json"))
        if len(frames) != count:
            raise ValueError("all original frames must be represented")
        for index, path in enumerate(frames):
            if path.parent.name != f"{index:03d}":
                raise ValueError("original sequence ordering differs")
            row = load(path)
            public.append(
                dict(
                    trial=trial,
                    index=index,
                    raw=str(path.relative_to(source)),
                    raw_sha256=digest(path),
                    original_track=original["frames"][index],
                    original_result_sha256=digest(source / trial / "result.json"),
                )
            )
            sdk = source / trial / f"transport/evaluator_only/sdk-events/{index + 4:03d}.json"
            boxes = sdk.with_name(f"{index + 4:03d}-boxes.json")
            if load(sdk)["owner"] != row["action_id"]:
                raise ValueError("evaluator and public action differ")
            evaluation.append(
                dict(
                    trial=trial,
                    index=index,
                    sdk=str(sdk.relative_to(source)),
                    sdk_sha256=digest(sdk),
                    boxes=str(boxes.relative_to(source)),
                    boxes_sha256=digest(boxes),
                )
            )
    save(output / "public-manifest.json", public)
    save(output / "evaluation-manifest.json", evaluation)
    save(output / "pins.json", {p.name: digest(p) for p in output.glob("*-manifest.json")})


def raw_rows(row):
    return tuple(
        RawModalityObservation(
            r["envelope_json"],
            base64.b64decode(r["payload_base64"], validate=True),
            r["capture_receipt_sha256"],
            r["depth_unit"],
        )
        for r in row["observations"]
    )


def verify_panel(manifest):
    if [(r["trial"], r["index"]) for r in manifest] != [
        (t, i) for t, n in TRIALS.items() for i in range(n)
    ]:
        raise ValueError("fixed complete ordered sequence panel required")


def old_points(track, camera, depth):
    if track["status"] != "PIXEL_SUPPORTED":
        return dict(
            anchor_id=track["anchor_id"], status=track["status"], first_seed_m=None, soft_m=None
        )
    grid = grid_pixels(track["box_xyxy"], camera.width, camera.height)
    valid = [
        (u, v)
        for u, v in grid
        if np.isfinite(depth[v, u]) and 0 < depth[v, u] < camera.far_plane_m - camera.near_plane_m
    ]
    if not valid:
        return dict(
            anchor_id=track["anchor_id"],
            status="UNKNOWN_NO_VALID_DEPTH",
            first_seed_m=None,
            soft_m=None,
        )
    u, v = min(valid)
    first = np.asarray(camera.world_point(u, v, float(depth[v, u])))
    points = np.array([camera.world_point(x, y, float(depth[y, x])) for x, y in valid])
    # Exactly the old constant-affinity fixture: self=1, other valid grid points=0.5.
    soft = (points.sum(axis=0) + first) / (len(points) + 1)
    return dict(
        anchor_id=track["anchor_id"],
        status="SURFACE_CANDIDATE",
        first_seed_uv=[u, v],
        first_seed_m=first.tolist(),
        soft_m=soft.tolist(),
        box_xyxy=track["box_xyxy"],
    )


def infer(source, manifest_path, manifest_pin, weights, old_weights, output):
    if output.exists():
        raise ValueError("inference output must be new")
    manifest = checked(manifest_path, manifest_pin)
    verify_panel(manifest)
    report = dict(
        status="RUNNING",
        manifest_sha256=manifest_pin,
        frames=[],
        failures=[],
        scope="public mask/flow surface development; not natural task success",
        new_actions=0,
    )
    sequence, old_sequence, trial = None, None, None
    output.mkdir(parents=True)
    try:
        for item in manifest:
            raw = checked(source / item["raw"], item["raw_sha256"])
            if raw["success"] is not True:
                raise ValueError("original failed capture must not masquerade as an observation")
            rows, cutoff = raw_rows(raw), datetime.fromisoformat(raw["received_at"])
            if item["trial"] != trial:
                identity = rows[0].envelope().identity
                detector = NaturalMaskSurfaceDetector(
                    weights_path=weights,
                    household_id=identity.household_id,
                    session_id=identity.session_id,
                    trace_id=identity.trace_id,
                )
                sequence, old_sequence = (
                    MaskSurfaceSequence(detector),
                    NaturalTargetSequence(weights_path=old_weights),
                )
                trial = item["trial"]
            start = time.perf_counter()
            record, masks = sequence.observe(rows, cutoff=cutoff)
            old = json.loads(json.dumps(old_sequence.observe(rows[0], cutoff=cutoff), default=str))
            if content_sha256(old) != content_sha256(item["original_track"]):
                raise ValueError("fresh old tracker differs from original public record")
            camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
            record["old_box_tracks"] = [old_points(t, camera, depth) for t in old["tracks"]]
            record["old_fresh_equal"] = True
            folder = output / trial / f"{item['index']:03d}"
            save(folder / "public.json", record)
            (folder / "masks.npy.gz").write_bytes(gzip.compress(masks, mtime=0))
            report["frames"].append(
                dict(
                    trial=trial,
                    index=item["index"],
                    raw_sha256=item["raw_sha256"],
                    public=str((folder / "public.json").relative_to(output)),
                    public_sha256=digest(folder / "public.json"),
                    masks_sha256=digest(folder / "masks.npy.gz"),
                )
            )
            save(output / "result.json", report)
            print(
                json.dumps(
                    dict(
                        trial=trial,
                        index=item["index"],
                        seconds=time.perf_counter() - start,
                        statuses=[t["status"] for t in record["tracks"]],
                    )
                ),
                flush=True,
            )
        report["status"] = "COMPLETED"
    except BaseException as exc:
        report["status"] = "FAILED"
        report["failures"].append(dict(type=type(exc).__name__, message=str(exc)))
        raise
    finally:
        report["unprocessed"] = [
            {k: r[k] for k in ("trial", "index")} for r in manifest[len(report["frames"]) :]
        ]
        save(output / "result.json", report)


def overlap(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area
    return area / union if union > 0 else 0.0


def evaluate(source, inference, inference_pin, manifest_path, manifest_pin, output):
    if output.exists():
        raise ValueError("evaluation output must be new")
    report = checked(inference / "result.json", inference_pin)
    manifest = checked(manifest_path, manifest_pin)
    verify_panel(manifest)
    if report["status"] != "COMPLETED" or report["unprocessed"] or report["failures"]:
        raise ValueError("cannot score incomplete execution as a complete panel")
    verify_panel(report["frames"])
    results = []
    for item, prediction in zip(manifest, report["frames"], strict=True):
        if (item["trial"], item["index"]) != (prediction["trial"], prediction["index"]):
            raise ValueError("inference and evaluation frame pairing differs")
        public = checked(inference / prediction["public"], prediction["public_sha256"])
        mask_path = (inference / prediction["public"]).with_name("masks.npy.gz")
        if (
            digest(mask_path) != prediction["masks_sha256"]
            or sha256(gzip.decompress(mask_path.read_bytes())).hexdigest()
            != public["detector"]["masks_npy_sha256"]
        ):
            raise ValueError("saved native masks differ from public frame binding")
        sdk = checked(source / item["sdk"], item["sdk_sha256"])
        boxes = checked(source / item["boxes"], item["boxes_sha256"])
        if sdk["owner"] != public["detector"]["camera"]["action_id"]:
            raise ValueError("evaluator action differs from public exposure")
        bounds = {}
        for obj in sdk["metadata"]["objects"]:
            corners = np.asarray(obj["axisAlignedBoundingBox"]["cornerPoints"])
            if corners.shape != (8, 3) or not np.isfinite(corners).all():
                raise ValueError("invalid evaluator AABB")
            bounds[obj["objectId"]] = dict(
                lower=corners.min(axis=0).tolist(), upper=corners.max(axis=0).tolist()
            )

        def scores(point, bounds=bounds):
            if point is None:
                return dict(status="UNKNOWN", inside_aabbs=[])
            if np.asarray(point).shape != (3,) or not np.isfinite(point).all():
                raise ValueError("invalid reported point")
            return dict(
                status="REPORTED",
                inside_aabbs=[
                    key
                    for key, b in bounds.items()
                    if all(
                        lo <= v <= hi
                        for lo, v, hi in zip(b["lower"], point, b["upper"], strict=True)
                    )
                ],
            )

        candidates = [
            dict(
                candidate_id=c["candidate_id"],
                category=c["category"],
                status=c["status"],
                box_overlaps={key: overlap(c["box_xyxy"], b) for key, b in boxes.items()},
                point=scores(c["world_point_m"]),
            )
            for c in public["detector"]["candidates"]
        ]
        tracks = [
            dict(
                anchor_id=t["anchor_id"],
                category=t["category"],
                status=t["status"],
                point=scores(t["world_point_m"]),
            )
            for t in public["tracks"]
        ]
        old = [
            dict(
                anchor_id=t["anchor_id"],
                status=t["status"],
                first=scores(t["first_seed_m"]),
                soft=scores(t["soft_m"]),
            )
            for t in public["old_box_tracks"]
        ]
        results.append(
            dict(
                trial=item["trial"],
                index=item["index"],
                sdk_sha256=item["sdk_sha256"],
                candidates=candidates,
                tracks=tracks,
                old=old,
            )
        )
    save(
        output,
        dict(
            scope="all-object isolated AABB and box-overlap diagnostics; no instance adjudication",
            inference_sha256=inference_pin,
            evaluation_manifest_sha256=manifest_pin,
            frames=results,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="mode", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    p = commands.add_parser("infer")
    for name in ("source", "manifest", "weights", "old_weights", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--manifest-pin", required=True)
    p = commands.add_parser("evaluate")
    for name in ("source", "inference", "manifest", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--manifest-pin", required=True)
    p.add_argument("--inference-pin", required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    if args.mode == "prepare":
        prepare(args.source, args.output)
    elif args.mode == "infer":
        infer(
            args.source,
            args.manifest,
            args.manifest_pin,
            args.weights,
            args.old_weights,
            args.output,
        )
    else:
        evaluate(
            args.source,
            args.inference,
            args.inference_pin,
            args.manifest,
            args.manifest_pin,
            args.output,
        )
