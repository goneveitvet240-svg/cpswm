"""Run a pinned natural-appearance detector on an explicitly pinned RGB-D archive.

Produces uncalibrated visual candidates, not GroundedTransition/memory/actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from cpswm.perception_mapping.adapters.contracts import ObservationEnvelope, SensorModality
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-score", type=float, default=0.5)
    args = parser.parse_args()
    root = args.archive.resolve()
    raw_manifest = (root / "receipt.json").read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != args.manifest_sha256:
        raise ValueError("archive differs from retained manifest digest")
    manifest = json.loads(raw_manifest)
    verified: dict[Path, bytes] = {}
    for entry in manifest["output_manifest"]:
        path = (root / entry["file"]).resolve()
        if not path.is_relative_to(root) or path in verified:
            raise ValueError("duplicate or escaping archive path")
        payload = path.read_bytes()
        if (
            len(payload) != entry["size_bytes"]
            or hashlib.sha256(payload).hexdigest() != entry["sha256"]
        ):
            raise ValueError("archive payload mismatch")
        verified[path] = payload
    captures = {row["capture_ref"]: row for row in manifest["captures"]}
    raws = []
    for entry in manifest["output_manifest"]:
        if not entry["file"].endswith(".json"):
            continue
        path = root / entry["file"]
        body = verified[path.resolve()].decode("utf-8")
        env = ObservationEnvelope.model_validate_json(body)
        if env.sensor.modality is not SensorModality.RGB:
            continue
        npy_path = path.with_suffix(".npy").resolve()
        if npy_path not in verified:
            raise ValueError("RGB pixels absent from manifest")
        raws.append(
            RawModalityObservation(
                body,
                verified[npy_path],
                captures[entry["capture_ref"]]["source_receipt_sha256"],
                None,
            )
        )
    if not raws:
        raise ValueError("archive contains no RGB frames")
    args.output.mkdir(parents=True, exist_ok=False)
    import torch

    torch.set_num_threads(2)
    scope = raws[0].envelope().identity
    detector = NaturalAppearanceDetector(
        weights_path=args.weights,
        household_id=scope.household_id,
        session_id=scope.session_id,
        trace_id=scope.trace_id,
        minimum_score=args.minimum_score,
    )
    started = time.monotonic()
    counts: dict[str, int] = {}
    records = []
    for raw in raws:
        frame = detector.infer(raw, cutoff=raw.envelope().arrival_time)
        records.append(asdict(frame))
        for candidate in frame.candidates:
            counts[candidate.category] = counts.get(candidate.category, 0) + 1
    (args.output / "frames.json").write_text(json.dumps(records, default=str, indent=2) + "\n")
    summary = {
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_files": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).resolve().parents[1]
                / "src/cpswm/perception_mapping/natural_vision.py",
            )
        },
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "archive_manifest_sha256": args.manifest_sha256,
        "archive_source_sha": manifest["source_sha"],
        "frames": len(records),
        "candidate_counts": counts,
        "inference_seconds": time.monotonic() - started,
        "semantic_transitions": 0,
        "physical_actions": 0,
        "status": "NATURAL_PIXEL_DETECTIONS_UNCALIBRATED",
        "new_simulator_run": False,
        "frames_sha256": hashlib.sha256((args.output / "frames.json").read_bytes()).hexdigest(),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
