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
from uuid import uuid5

from cpswm.perception_mapping.adapters.contracts import ObservationEnvelope, SensorModality
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import (
    NaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-score", type=float, default=0.5)
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parents[1]
    git = ["git", "--no-replace-objects", "-C", str(source_root)]
    source_sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    source_paths = (
        Path(__file__).resolve(),
        source_root / "src/cpswm/perception_mapping/natural_vision.py",
    )
    source_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
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
    captures = {}
    for row in manifest["captures"]:
        key = row["capture_ref"]
        if key in captures:
            raise ValueError("duplicate capture reference")
        captures[key] = row
    raws = []
    observation_ids = set()
    for entry in manifest["output_manifest"]:
        if not entry["file"].endswith(".json"):
            continue
        path = root / entry["file"]
        body = verified[path.resolve()].decode("utf-8")
        env = ObservationEnvelope.model_validate_json(body)
        if env.identity.observation_id in observation_ids:
            raise ValueError("duplicate observation identity")
        observation_ids.add(env.identity.observation_id)
        if env.sensor.modality not in {SensorModality.RGB, SensorModality.DEPTH}:
            continue
        npy_path = path.with_suffix(".npy").resolve()
        if npy_path not in verified:
            raise ValueError("RGB pixels absent from manifest")
        raws.append(
            RawModalityObservation(
                body,
                verified[npy_path],
                captures[entry["capture_ref"]]["source_receipt_sha256"],
                "m" if env.sensor.modality is SensorModality.DEPTH else None,
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
    producer = NaturalVisionEvidenceProducer(detector)
    # Initialization IDs are bookkeeping only, never recognized object/person identities.
    system = StructureTwoProductionSystem(
        owner_key="unresolved-visual-observer",
        object_instance_id=uuid5(scope.session_id, "unresolved-object"),
        locations=(
            uuid5(scope.session_id, "unresolved-location-1"),
            uuid5(scope.session_id, "unresolved-location-2"),
        ),
        authorization_scope_id=uuid5(scope.session_id, "no-semantic-authorization"),
    )
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="legacy_component_diagnostic",
        household_id=scope.household_id,
        session_id=scope.session_id,
        trace_id=scope.trace_id,
        producer=producer,
    )
    before = system.core.current_snapshot
    started = time.monotonic()
    for raw in raws:
        when = raw.envelope().arrival_time
        stream.admit((raw,), received_at=when)
        result = stream.advance(cutoff=when)
        if result.status != "INSUFFICIENT_SEMANTIC_EVIDENCE":
            raise RuntimeError("uncalibrated vision unexpectedly advanced memory")
    if system.core.current_snapshot != before or stream.execution_traces():
        raise RuntimeError("visual candidate inference changed semantic memory")
    counts: dict[str, int] = {}
    records = []
    for frame in producer.frames():
        records.append(asdict(frame))
        for candidate in frame.candidates:
            counts[candidate.category] = counts.get(candidate.category, 0) + 1
    (args.output / "frames.json").write_text(json.dumps(records, default=str, indent=2) + "\n")
    source_after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    if (
        source_before != source_after
        or source_sha != subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    ):
        raise RuntimeError("source changed during inference")
    summary = {
        "source_sha": source_sha,
        "source_files": source_after,
        "source_unchanged": True,
        "source_identity_scope": "entry_and_detector_files_not_whole_runtime_attestation",
        "git_dirty": bool(
            subprocess.check_output([*git, "status", "--porcelain"], text=True).strip()
        ),
        "archive_manifest_sha256": args.manifest_sha256,
        "archive_source_sha": manifest["source_sha"],
        "frames": len(records),
        "raw_observations": len(raws),
        "continuous_input_invoked": True,
        "core_unchanged_verified": True,
        "bookkeeping_initialization_only": True,
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
