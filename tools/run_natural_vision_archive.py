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
    FasterNaturalAppearanceDetector,
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
    parser.add_argument("--detector", choices=("ssdlite", "fasterrcnn"), default="ssdlite")
    parser.add_argument("--hand-model", type=Path)
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parents[1]
    git = ["git", "--no-replace-objects", "-C", str(source_root)]
    source_sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    source_paths = (
        Path(__file__).resolve(),
        source_root / "src/cpswm/perception_mapping/natural_vision.py",
        source_root / "src/cpswm/perception_mapping/natural_hands.py",
    )
    source_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    root = args.archive.resolve()
    raw_manifest = (root / "receipt.json").read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != args.manifest_sha256:
        raise ValueError("archive differs from retained manifest digest")
    manifest = json.loads(raw_manifest)
    verified: dict[Path, bytes] = {}
    entries_by_path = {}
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
        entries_by_path[path] = entry
    captures = {}
    for row in manifest["captures"]:
        key = row["capture_ref"]
        if key in captures:
            raise ValueError("duplicate capture reference")
        captures[key] = row
    for path, entry in entries_by_path.items():
        if entry["capture_ref"] not in captures:
            raise ValueError("unknown capture reference")
        if path.suffix not in {".json", ".npy"}:
            raise ValueError("unexpected observation payload extension")
        other = path.with_suffix(".npy" if path.suffix == ".json" else ".json")
        if (
            other not in entries_by_path
            or entries_by_path[other]["capture_ref"] != entry["capture_ref"]
        ):
            raise ValueError("paired observation capture references differ or are incomplete")
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
        for paired in (entry, entries_by_path[path.with_suffix(".npy").resolve()]):
            if "observation_id" in paired and paired["observation_id"] != str(
                env.identity.observation_id
            ):
                raise ValueError("manifest observation identity differs from envelope")
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
    detector_type = (
        NaturalAppearanceDetector if args.detector == "ssdlite" else FasterNaturalAppearanceDetector
    )
    detector = detector_type(
        weights_path=args.weights,
        household_id=scope.household_id,
        session_id=scope.session_id,
        trace_id=scope.trace_id,
        minimum_score=args.minimum_score,
    )
    hand_detector = None
    if args.hand_model is not None:
        from cpswm.perception_mapping.natural_hands import NaturalHandDetector

        hand_detector = NaturalHandDetector(
            model_path=args.hand_model, scope=(scope.household_id, scope.session_id, scope.trace_id)
        )
    producer = NaturalVisionEvidenceProducer(detector, hand_detector)
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
    for raw_index, raw in enumerate(raws):
        when = raw.envelope().arrival_time
        stream.admit((raw,), received_at=when)
        result = stream.advance(cutoff=when)
        if (raw_index + 1) % 60 == 0:
            print(
                json.dumps(
                    {
                        "processed_raw_observations": raw_index + 1,
                        "elapsed_seconds": time.monotonic() - started,
                    }
                ),
                flush=True,
            )
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
    hands = [asdict(frame) for frame in producer.hand_frames()]
    (args.output / "hand_frames.json").write_text(json.dumps(hands, default=str, indent=2) + "\n")
    if hand_detector is not None:
        hand_detector.close()
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
        "hand_frames": len(hands),
        "hand_candidates": sum(len(f["candidates"]) for f in hands),
        "hand_frames_sha256": hashlib.sha256(
            (args.output / "hand_frames.json").read_bytes()
        ).hexdigest(),
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
