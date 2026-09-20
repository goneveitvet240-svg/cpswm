"""Audit fixed raw clips and produce evaluator-only nominal author phase references."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from cpswm.data_preflight.handover_phase_supervision import (
    parse_author_phases,
    phase_boundaries,
    project_nominal_phase,
)


def read_member(root: Path, receipt: dict) -> bytes:
    path = (root / receipt["local_path"]).resolve()
    if not path.is_relative_to(root.resolve()) or not 0 < receipt["bytes"] <= 16 * 1024 * 1024:
        raise ValueError("invalid member path or size")
    if path.stat().st_size != receipt["bytes"]:
        raise ValueError("member size differs from fixed manifest")
    data = path.read_bytes()
    if len(data) != receipt["bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
        raise ValueError("member differs from fixed manifest")
    return data


def inspect_video(data: bytes) -> dict:
    if not any(data):
        return {"status": "INVALID_ALL_ZERO", "decoded_frames": 0}
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "source.mp4"
        p.write_bytes(data)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time:stream=width,height",
                "-of",
                "json",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if probe.returncode:
            return {"status": "INVALID_VIDEO", "error": probe.stderr[-1000:], "decoded_frames": 0}
        metadata = json.loads(probe.stdout)
        decoded = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(p),
                "-fps_mode",
                "passthrough",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if decoded.returncode:
            return {"status": "DECODE_FAILED", "error": decoded.stderr[-1000:], "decoded_frames": 0}
    times = [float(f["best_effort_timestamp_time"]) for f in metadata.get("frames", [])]
    import math
    from itertools import pairwise

    if (
        not times
        or any(not math.isfinite(t) or t < 0 for t in times)
        or any(b <= a for a, b in pairwise(times))
    ):
        raise ValueError("invalid video presentation timeline")
    return {
        "status": "DECODED",
        "decoded_frames": len(times),
        "times": times,
        "stream": metadata["streams"][0],
    }


def depth_timestamp_status(data: bytes) -> dict:
    if b"\0" in data:
        return {"status": "INVALID_NULL_BYTES", "alignment_authorized": False}
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        header = next(reader, [])
        if len(set(header)) != len(header) or not {"Index", "Time"} <= set(header):
            raise ValueError("invalid depth header")
        rows = list(reader)
        if any(len(row) != len(header) for row in rows):
            raise ValueError("invalid depth row width")
        times = [float(r[header.index("Time")]) for r in rows]
        indices = [int(r[header.index("Index")]) for r in rows]
        import math
        from itertools import pairwise

        if (
            not times
            or indices != list(range(len(rows)))
            or not all(math.isfinite(t) for t in times)
            or any(b <= a for a, b in pairwise(times))
        ):
            raise ValueError("bad depth clock")
    except (ValueError, KeyError, UnicodeError, csv.Error):
        return {"status": "INVALID_TABLE", "alignment_authorized": False}
    return {
        "status": "PARSED_NO_DEPTH_FRAMES_ACQUIRED",
        "rows": len(rows),
        "first_seconds": times[0],
        "last_seconds": times[-1],
        "alignment_authorized": False,
    }


def validate_member_pairing(phase_record: dict, video: dict, depth: dict, camera: int) -> None:
    seq = Path(phase_record["member"]).stem
    pair = "_".join(sorted(seq.split("_")[:2]))
    prefix = f"Bimanual Handovers Dataset/{pair}/"
    expected = (
        prefix + f"OptiTrack_Global_Frame/{seq}.csv",
        prefix + f"Kinect_{camera}/{seq}.mp4",
        prefix + f"Kinect_{camera}/{seq}_Depth_Timestamps.csv",
    )
    if tuple(r["member"] for r in (phase_record, video, depth)) != expected:
        raise ValueError("cross-file author sequence/camera mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wire = (args.dataset / "manifest.json").read_bytes()
    if hashlib.sha256(wire).hexdigest() != args.manifest_sha256:
        raise ValueError("manifest changed")
    manifest = json.loads(wire)
    records = manifest["receipts"]
    if len({r["local_path"] for r in records}) != len(records):
        raise ValueError("duplicate manifest members")
    repo = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__).resolve(),
        repo / "src/cpswm/data_preflight/handover_phase_supervision.py",
    ]
    sources = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    code_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    args.output.mkdir(parents=True, exist_ok=False)
    output = []
    for phase_record in sorted(
        (r for r in records if r["local_path"].endswith("/author-motion-phases.csv")),
        key=lambda r: r["local_path"],
    ):
        clip = Path(phase_record["local_path"]).parent.name
        seq = Path(phase_record["member"]).stem
        series = parse_author_phases(
            read_member(args.dataset, phase_record),
            expected_sha256=phase_record["sha256"],
            sequence_name=seq,
        )
        cameras = []
        for camera in (1, 2):
            name = f"raw/{clip}/camera-{camera}.mp4"
            matching = [r for r in records if r["local_path"] == name]
            if len(matching) != 1:
                raise ValueError("missing camera receipt")
            record = matching[0]
            probe = inspect_video(read_member(args.dataset, record))
            refs = [project_nominal_phase(series, t) for t in probe.pop("times", [])]
            timestamps = [
                r
                for r in records
                if r["local_path"] == f"evaluator/{clip}/camera-{camera}-depth-timestamps.csv"
            ]
            if len(timestamps) != 1:
                raise ValueError("missing timestamp receipt")
            validate_member_pairing(phase_record, record, timestamps[0], camera)
            cameras.append(
                {
                    "camera": camera,
                    "video_sha256": record["sha256"],
                    **probe,
                    "phase_reference_status_counts": dict(
                        Counter(r["roles"]["giver"]["status"] for r in refs)
                    ),
                    "frame_references": refs,
                    "depth_timestamp": depth_timestamp_status(
                        read_member(args.dataset, timestamps[0])
                    ),
                }
            )
        output.append(
            {
                "clip": clip,
                "sequence_name": seq,
                "author_giver_id": series.giver_id,
                "author_receiver_id": series.receiver_id,
                "author_rows": len(series.samples),
                "phase_source_sha256": series.source_sha256,
                "phase_counts": {
                    role: dict(Counter(getattr(r, role) for r in series.samples))
                    for role in ("giver", "receiver")
                },
                "phase_boundaries": phase_boundaries(series),
                "cameras": cameras,
            }
        )
    after = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if (
        sources != after
        or code_sha
        != subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    ):
        raise RuntimeError("audit source changed")
    result = {
        "code_sha": code_sha,
        "source_files": sources,
        "manifest_sha256": args.manifest_sha256,
        "lane": "evaluator_only",
        "contact_gold": False,
        "published_pixels": "BURNED_IN_AUTHOR_PHASE_LABELS_NOT_MODEL_READY",
        "runtime_semantic_transitions": 0,
        "clips": output,
    }
    (args.output / "phase-references.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "code_sha": code_sha,
                "clips": len(output),
                "valid_videos": sum(c["status"] == "DECODED" for r in output for c in r["cameras"]),
                "decoded_frames": sum(c["decoded_frames"] for r in output for c in r["cameras"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
