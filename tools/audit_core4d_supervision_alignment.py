"""Pinned evaluator-only alignment diagnostics; never create accepted frame links."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tempfile
import zipfile
from itertools import pairwise
from pathlib import Path

import numpy as np
from PIL import Image

from cpswm.data_preflight.supervision_alignment import (
    alignment_inventory,
    boundary_support,
    pose_audit,
    timestamp_audit,
)


def pinned(path: Path, expected: str, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("input exceeds byte budget")
    data = path.read_bytes()
    if len(data) > limit or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("input differs from pinned digest/budget")
    return data


def array_bytes(data: bytes, limit: int) -> np.ndarray:
    stream = io.BytesIO(data)
    version = np.lib.format.read_magic(stream)
    if version not in {(1, 0), (2, 0)}:
        raise ValueError("unsupported NPY version")
    header = (
        np.lib.format.read_array_header_1_0
        if version == (1, 0)
        else np.lib.format.read_array_header_2_0
    )
    shape, _, dtype = header(stream)
    import math

    size = math.prod(shape) * dtype.itemsize
    if dtype.hasobject or size > limit or size != len(data) - stream.tell():
        raise ValueError("unsafe or inconsistent array allocation")
    return np.load(io.BytesIO(data), allow_pickle=False)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    for name in ("raw", "motion", "mask"):
        p.add_argument(f"--{name}-manifest-sha256", required=True)
    args = p.parse_args()
    root = args.dataset
    manifests = {}
    lanes = {
        "raw": root,
        "motion": root / "evaluator/motion",
        "mask": root / "evaluator/segmentation",
    }
    for name, lane in lanes.items():
        manifests[name] = json.loads(
            pinned(lane / "manifest.json", getattr(args, f"{name}_manifest_sha256"), 1024 * 1024)
        )
    if len({m["revision"] for m in manifests.values()}) != 1:
        raise ValueError("mixed dataset revisions")
    args.output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    files = [Path(__file__).resolve(), repo / "src/cpswm/data_preflight/supervision_alignment.py"]
    before = {str(f.relative_to(repo)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    results = []
    for seq in ("023", "024"):

        def member(lane: str, suffix: str, sequence: str = seq) -> bytes:
            rows = [
                r
                for r in manifests[lane]["receipts"]
                if r["member"].endswith(f"/20231002/{sequence}/" + suffix)
            ]
            if len(rows) != 1:
                raise ValueError("unique pinned member required")
            r = rows[0]
            relative = r["file"] if lane == "mask" else r["member"]
            directory = lanes[lane] / "raw" if lane == "raw" else lanes[lane]
            dest = (directory / relative).resolve()
            if not dest.is_relative_to(directory.resolve()):
                raise ValueError("manifest path escapes lane")
            return pinned(dest, r["sha256"], 128 * 1024 * 1024)

        video = member("raw", "camera1/color.mp4")
        timestamps = tuple(
            int(t) for t in member("raw", "camera1/timestamp.txt").decode().strip().split(",")
        )
        table = np.loadtxt(
            io.BytesIO(member("motion", "aligned_frame_ids.txt")), delimiter=",", dtype=np.int64
        )
        poses = array_bytes(member("motion", "smooth_objposes.npy"), 1024 * 1024)
        with zipfile.ZipFile(io.BytesIO(member("mask", "camera1_mask.npz"))) as archive:
            infos = archive.infolist()
            if (
                len(infos) != 1
                or infos[0].filename != "arr_0.npy"
                or infos[0].file_size > 256 * 1024 * 1024
            ):
                raise ValueError("unexpected mask archive")
            masks = array_bytes(archive.read(infos[0]), 256 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / "source.mp4"
            frozen.write_bytes(video)
            wire = subprocess.check_output(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(frozen),
                    "-vf",
                    "scale=240:135",
                    "-frames:v",
                    "1025",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-",
                ],
                timeout=120,
            )
            rgb = np.frombuffer(wire, np.uint8).reshape(-1, 135, 240, 3)
            if not 0 < len(rgb) <= 1024:
                raise ValueError("decoded frame budget exceeded")
            probe = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_frames",
                        "-show_entries",
                        "frame=best_effort_timestamp_time",
                        "-of",
                        "json",
                        str(frozen),
                    ],
                    timeout=120,
                )
            )
        pts = [float(r["best_effort_timestamp_time"]) for r in probe["frames"]]
        if (
            len(pts) != len(rgb)
            or not np.isfinite(pts).all()
            or any(b <= a for a, b in pairwise(pts))
        ):
            raise ValueError("invalid decoded media timeline")
        clocks = timestamp_audit(timestamps, len(rgb))
        inventory = alignment_inventory(masks, table, video_frames=len(rgb), pose_rows=len(poses))
        small = np.stack(
            [
                np.asarray(Image.fromarray(m).resize((240, 135), Image.Resampling.NEAREST))
                for m in masks
            ]
        )
        scores = boundary_support(rgb, small)
        np.save(args.output / f"{seq}-edge-support.npy", scores, allow_pickle=False)
        for hypothesis in inventory["hypotheses"].values():
            ids = hypothesis["frame_indices"]
            if hypothesis["all_in_range"]:
                hypothesis["mean_boundary_support"] = float(scores[np.arange(len(ids)), ids].mean())
        ranking = np.argsort(-scores, axis=1, kind="stable")[:, :5].tolist()
        result = {
            "sequence": seq,
            "input_sha256": hashlib.sha256(video).hexdigest(),
            "timestamps": clocks,
            "media_pts_seconds": pts,
            "inventory": inventory,
            "pose": pose_audit(poses),
            "exploratory_top5_rgb_indices_per_mask": ranking,
            "edge_score_semantics": "relative edge support, not probability; static edges can win",
            "event_labels": [],
            "identity_labels": [],
            "lane": "evaluator_only",
        }
        results.append(result)
        (args.output / f"{seq}.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
    after = {str(f.relative_to(repo)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    if (
        before != after
        or sha
        != subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    ):
        raise RuntimeError("source changed during audit")
    summary = {
        "code_sha": sha,
        "source_files": after,
        "dataset_revision": manifests["raw"]["revision"],
        "manifest_sha256": {n: getattr(args, f"{n}_manifest_sha256") for n in lanes},
        "sequences": [r["sequence"] for r in results],
        "status": "UNVERIFIED_ALIGNMENT",
        "accepted_frame_links": [],
        "semantic_transitions": 0,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
