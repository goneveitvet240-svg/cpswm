"""Read-only counterfactual gate diagnostic over the published release archive.

This reuses the current appearance/geometry gate against recorded public RGB and
recorded detector candidates. It does not rerun detector masks, optical flow,
transactions, task reports, the simulator, or SDK scoring, so an accepted pair
is evidence only that a lost row reaches the reinitialization gate.
"""

from __future__ import annotations

import argparse
import base64
import json
import tarfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.mask_surface_sequence import _appearance, _comparison, _descriptor
from cpswm.perception_mapping.natural_vision import decode_rgb

EXPECTED_ARCHIVE_SHA256 = "abe866c6f00018134452eb0f7d737ae85582fa05d8ec85c9b158918839b9561c"
PREFIX = "evidence-data/release-comparison/fixed/public"


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json_member(archive: tarfile.TarFile, name: str) -> tuple[dict[str, Any], str]:
    member = archive.getmember(name)
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"archive member is not a regular readable file: {name}")
    data = stream.read()
    return json.loads(data), _digest(data)


def _raw_rows(row: dict[str, Any]) -> tuple[RawModalityObservation, ...]:
    return tuple(
        RawModalityObservation(
            item["envelope_json"],
            base64.b64decode(item["payload_base64"], validate=True),
            item["capture_receipt_sha256"],
            item["depth_unit"],
        )
        for item in row["observations"]
    )


def replay(archive_path: Path) -> dict[str, Any]:
    archive_sha256 = _digest(archive_path.read_bytes())
    if archive_sha256 != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("release archive differs from the published SHA-256")
    with tarfile.open(archive_path, "r:gz") as archive:
        raw_names = sorted(
            name
            for name in archive.getnames()
            if name.startswith(PREFIX + "/") and name.endswith("/raw.json")
        )
        if [Path(name).parent.name for name in raw_names] != ["000", "001", "002"]:
            raise ValueError("frozen fixed arm must contain exactly frames 000, 001 and 002")
        frames = []
        initial_evidence: dict[str, dict[str, Any]] = {}
        initial_categories: set[str] = set()
        for frame_index, raw_name in enumerate(raw_names):
            surface_name = str(Path(raw_name).with_name("surface.json"))
            raw, raw_sha256 = _json_member(archive, raw_name)
            surface, surface_sha256 = _json_member(archive, surface_name)
            if raw["success"] is not True:
                raise ValueError("failed capture cannot enter the diagnostic")
            rows = _raw_rows(raw)
            cutoff = datetime.fromisoformat(raw["received_at"])
            _, rgb = decode_rgb(rows[0], cutoff=cutoff)
            matches = [
                record for record in surface["records"] if record["frame_index"] == frame_index
            ]
            if len(matches) != 1:
                raise ValueError("surface state does not contain the matching frozen frame")
            record = matches[0]
            if record["detector"]["camera"]["action_id"] != raw["action_id"]:
                raise ValueError("public RGB and recorded candidates have different actions")
            active = [
                candidate
                for candidate in record["detector"]["candidates"]
                if candidate["detector_score"] >= 0.5
            ]
            if frame_index == 0:
                by_id = {candidate["candidate_id"]: candidate for candidate in active}
                for track in record["tracks"]:
                    anchor = track["anchor_id"]
                    if anchor not in by_id:
                        raise ValueError("first-frame track lacks its recorded candidate")
                    initial_evidence[anchor] = _descriptor(rgb, by_id[anchor], birth_frame=0)
                    if track["world_point_m"] is not None:
                        initial_evidence[anchor]["last_world_point_m"] = tuple(
                            track["world_point_m"]
                        )
                    initial_categories.add(track["category"])
            candidate_appearance = {
                candidate["candidate_id"]: _appearance(rgb, candidate) for candidate in active
            }
            lost = [track for track in record["tracks"] if track["flow"]["status"] == "LOST"]
            comparisons = []
            accepted_by_anchor: dict[str, list[str]] = {}
            accepted_by_candidate: dict[str, list[str]] = {}
            for track in lost:
                anchor = track["anchor_id"]
                accepted_by_anchor[anchor] = []
                for candidate in active:
                    item = _comparison(
                        anchor,
                        initial_evidence[anchor],
                        candidate,
                        candidate_appearance[candidate["candidate_id"]],
                    )
                    comparisons.append(item)
                    if item["accepted_energy"]:
                        accepted_by_anchor[anchor].append(candidate["candidate_id"])
                        accepted_by_candidate.setdefault(candidate["candidate_id"], []).append(
                            anchor
                        )
            unique_pairs = [
                dict(anchor_id=anchor, candidate_id=candidates[0])
                for anchor, candidates in accepted_by_anchor.items()
                if len(candidates) == 1 and len(accepted_by_candidate[candidates[0]]) == 1
            ]
            frames.append(
                dict(
                    frame_index=frame_index,
                    raw_sha256=raw_sha256,
                    surface_sha256=surface_sha256,
                    active_candidate_count=len(active),
                    recorded_lost_anchors=[track["anchor_id"] for track in lost],
                    comparisons=comparisons,
                    unique_gate_pairs=unique_pairs,
                    provisional_late_birth_candidates=[
                        candidate["candidate_id"]
                        for candidate in active
                        if candidate["category"] not in initial_categories
                    ],
                )
            )
    return dict(
        status="COMPLETED",
        scope=(
            "read-only counterfactual gate diagnostic; no detector-mask, optical-flow, "
            "transaction, task-score, simulator or SDK replay"
        ),
        source_archive=str(archive_path),
        source_archive_sha256=archive_sha256,
        frames=frames,
        recorded_lost_rows=sum(len(frame["recorded_lost_anchors"]) for frame in frames),
        unique_gate_pairs=sum(len(frame["unique_gate_pairs"]) for frame in frames),
        provisional_late_birth_rows=sum(
            len(frame["provisional_late_birth_candidates"]) for frame in frames
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be new")
    result = replay(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
