"""Replay an explicitly cropped RGB view through M05/detection/association/roles.

This diagnostic entry does not promote candidates or execute robot actions. PTS
belongs to the original media timeline; envelope times record import acquisition,
not fictional original exposure times. Composite views require inspected crops.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from cpswm.contracts.base import BaseRecordMetadata, SourceType
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.interaction_evidence import CausalInstanceAssociator, role_readout
from cpswm.perception_mapping.natural_vision import (
    NaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def run(
    *,
    video: Path,
    expected_sha256: str,
    source_url: str,
    crop: tuple[int, int, int, int],
    start: float,
    duration: float,
    fps: int,
    weights: Path,
    output: Path,
) -> dict:
    if (
        not source_url.startswith("https://")
        or not np.isfinite([start, duration]).all()
        or start < 0
        or not 0 < duration <= 30
        or not 1 <= fps <= 10
    ):
        raise ValueError("bounded, source-described video window required")
    x, y, w, h = crop
    if min(x, y) < 0 or not 0 < w <= 1920 or not 0 < h <= 1080:
        raise ValueError("invalid RGB crop")
    if duration * fps * w * h * 3 > 128 * 1024 * 1024 or video.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("video decode exceeds local development budget")
    source = video.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError("video differs from pinned source")
    if output.exists():
        raise ValueError("output already exists")
    output.mkdir(parents=True)
    seq = content_sha256((expected_sha256, crop))
    household = uuid5(NAMESPACE_URL, "public-interaction-development")
    session = uuid5(household, seq)
    trace = uuid5(session, str((start, duration, fps)))
    detector = NaturalAppearanceDetector(
        weights_path=weights, household_id=household, session_id=session, trace_id=trace
    )
    producer = NaturalVisionEvidenceProducer(detector)
    system = StructureTwoProductionSystem(
        owner_key="unresolved-visual-observer",
        object_instance_id=uuid5(session, "unresolved-object"),
        locations=(
            uuid5(session, "unresolved-location-1"),
            uuid5(session, "unresolved-location-2"),
        ),
        authorization_scope_id=uuid5(session, "no-semantic-authorization"),
    )
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="legacy_component_diagnostic",
        household_id=household,
        session_id=session,
        trace_id=trace,
        producer=producer,
    )
    before = system.core.current_snapshot
    associator = CausalInstanceAssociator()
    # Decode exactly the bytes whose digest was verified, avoiding source TOCTOU.
    with tempfile.TemporaryDirectory() as tmp:
        frozen = Path(tmp) / "source.mp4"
        frozen.write_bytes(source)
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    str(frozen),
                ]
            )
        )["streams"][0]
        if x + w > probe["width"] or y + h > probe["height"]:
            raise ValueError("crop exceeds source video")
        # fps selects a documented regular sampling grid, not original frame IDs.
        data = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(start),
                "-i",
                str(frozen),
                "-t",
                str(duration),
                "-vf",
                f"crop={w}:{h}:{x}:{y},fps={fps}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )
    if not data or len(data) % (w * h * 3):
        raise ValueError("empty or incomplete RGB decode")
    arrays = np.frombuffer(data, dtype=np.uint8).reshape(-1, h, w, 3)
    records = []
    previous = None
    for index, pixels in enumerate(arrays):
        acquired = datetime.now(UTC)
        observation = uuid5(trace, str(index))
        media_time = start + index / fps
        wire = io.BytesIO()
        np.save(wire, pixels, allow_pickle=False)
        payload = wire.getvalue()
        receipt = {
            "source_url": source_url,
            "source_sha256": expected_sha256,
            "crop_xywh": crop,
            "sampling_grid_time_seconds": media_time,
            "sampling_fps": fps,
            "time_semantics": "resampled_grid_not_original_exposure",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "observation_id": str(observation),
        }
        env = ObservationEnvelope(
            metadata=BaseRecordMetadata(
                schema_name="public_video_rgb_import",
                schema_version="1.0.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                recorded_time=acquired,
                source_type=SourceType.IMPORT,
                source_id=source_url,
            ),
            identity=ObservationIdentity(
                observation_id=observation,
                household_id=household,
                session_id=session,
                trace_id=trace,
            ),
            sensor=SensorRef(sensor_id="fixed-rgb-panel", modality=SensorModality.RGB),
            capture_time=acquired,
            arrival_time=acquired,
            clock_domain="archive-import-acquisition-utc",
            frame_id="fixed-camera-pixel-frame",
            payload=PayloadRef(
                payload_id=observation,
                payload_sha256=receipt["payload_sha256"],
                size_bytes=len(payload),
            ),
        )
        raw = RawModalityObservation(env.model_dump_json(), payload, content_sha256(receipt), None)
        stream.admit((raw,), received_at=acquired)
        outcome = stream.advance(cutoff=acquired)
        if outcome.status != "INSUFFICIENT_SEMANTIC_EVIDENCE":
            raise RuntimeError("uncalibrated input unexpectedly advanced semantic state")
        visual = producer.frames()[-1]
        associated = associator.update(visual, sequence_id=seq, media_time=media_time)
        readout = role_readout(previous, associated)
        (output / f"{index:04d}.npy").write_bytes(payload)
        (output / f"{index:04d}.envelope.json").write_text(env.model_dump_json())
        records.append(
            {
                "receipt": receipt,
                "visual": asdict(visual),
                "association": asdict(associated),
                "interaction": asdict(readout),
            }
        )
        previous = associated
    if system.core.current_snapshot != before or stream.execution_traces():
        raise RuntimeError("candidate analysis changed long-term memory")
    summary = {
        "continuous_input_invoked": True,
        "core_unchanged_verified": True,
        "source_url": source_url,
        "source_sha256": expected_sha256,
        "frames": len(records),
        "candidates": dict(
            Counter(d["category"] for r in records for d in r["visual"]["candidates"])
        ),
        "association_statuses": dict(
            Counter(d["status"] for r in records for d in r["association"]["detections"])
        ),
        "ordered_role_alternatives": sum(
            len(r["interaction"]["role_alternatives"]) for r in records
        ),
        "calibration": "NO_INDEPENDENT_LABELS",
        "memory_writes": 0,
        "executed_actions": 0,
        "lane": "real_video_frontend_diagnostic",
        "records": records,
    }
    (output / "result.json").write_text(json.dumps(summary, default=str, indent=2))
    return {k: v for k, v in summary.items() if k != "records"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--crop", nargs=4, type=int, required=True, metavar=("X", "Y", "W", "H"))
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--fps", type=int, default=5)
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            run(
                video=args.video,
                expected_sha256=args.sha256,
                source_url=args.source_url,
                crop=tuple(args.crop),
                start=args.start,
                duration=args.duration,
                fps=args.fps,
                weights=args.weights,
                output=args.output,
            ),
            indent=2,
        )
    )
