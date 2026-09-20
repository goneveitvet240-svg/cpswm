"""Audit pinned raw/author lanes and full-sequence coverage without model input leakage."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import yaml

from cpswm.data_preflight.natural_event_coverage import (
    inspect_annotation,
    pinned_bytes,
    pose_pair_diagnostic,
)
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource


def checked_path(root: Path, member: str) -> Path:
    p = (root / member).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError("source escapes its lane root")
    return p


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    for name in ("raw-manifest-sha256", "annotation-manifest-sha256", "receipts-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.dataset
    raw = json.loads(
        pinned_bytes((root / "raw_manifest.json").read_bytes(), args.raw_manifest_sha256)
    )
    labels = json.loads(
        pinned_bytes(
            (root / "annotation_manifest.json").read_bytes(), args.annotation_manifest_sha256
        )
    )
    receipts = json.loads(
        pinned_bytes((root / "download_receipts.json").read_bytes(), args.receipts_sha256)
    )
    source_receipts = {}
    repeated_receipts = 0
    for receipt in receipts:
        member = receipt["member"]
        if member in source_receipts:
            if source_receipts[member] != receipt:
                raise ValueError("conflicting download receipts")
            repeated_receipts += 1
        source_receipts[member] = receipt
    indexed_labels = {}
    for row in labels:
        key = (row["sequence_id"], row["camera_id"], row["frame_index"])
        if key in indexed_labels:
            raise ValueError("duplicate annotation identity")
        indexed_labels[key] = row
    rows, groups, seen = [], defaultdict(list), set()
    for row in raw:
        source = HOCapFrameSource(**row)
        key = (source.sequence_id, source.camera_id, source.frame_index)
        if key in seen:
            raise ValueError("duplicate raw identity")
        seen.add(key)
        for mode, digest in (("rgb", source.rgb_sha256), ("depth", source.depth_sha256)):
            member = source.member(mode)
            if source_receipts[member]["sha256"] != digest:
                raise ValueError("raw pin and receipt disagree")
            pinned_bytes(checked_path(root / "raw", member).read_bytes(), digest)
        label = indexed_labels[key]
        expected_member = (
            f"{source.sequence_id}/{source.camera_id}/label_{source.frame_index:06d}.npz"
        )
        if label["member"] != expected_member:
            raise ValueError("annotation is paired to another frame")
        if source_receipts[expected_member]["sha256"] != label["annotation_sha256"]:
            raise ValueError("annotation pin and receipt disagree")
        inventory = inspect_annotation(
            checked_path(root / "evaluator", expected_member).read_bytes(),
            expected_sha256=label["annotation_sha256"],
        )
        item = dict(
            sequence_id=source.sequence_id,
            camera_id=source.camera_id,
            frame_index=source.frame_index,
            **inventory,
        )
        rows.append(item)
        groups[(source.sequence_id, source.camera_id)].append(item)
    if seen != set(indexed_labels):
        raise ValueError("raw and annotation coverage differ")
    summaries, pairs = [], []
    for (sequence, camera), frames in sorted(groups.items()):
        frames.sort(key=lambda x: x["frame_index"])
        member = sequence + "/meta.yaml"
        metadata = yaml.safe_load(
            pinned_bytes(
                checked_path(root / "evaluator", member).read_bytes(),
                source_receipts[member]["sha256"],
            )
        )
        total = metadata["num_frames"]
        if any(not 0 <= f["frame_index"] < total for f in frames):
            raise ValueError("frame index outside declared sequence")
        for previous, current in pairwise(frames):
            pairs.append(
                dict(
                    sequence_id=sequence,
                    camera_id=camera,
                    before_frame=previous["frame_index"],
                    after_frame=current["frame_index"],
                    **pose_pair_diagnostic(
                        previous,
                        current,
                        frame_gap=current["frame_index"] - previous["frame_index"],
                    ),
                )
            )
        summaries.append(
            dict(
                sequence_id=sequence,
                camera_id=camera,
                downloaded_frames=len(frames),
                sequence_frames=total,
                fraction=len(frames) / total,
                task_id=metadata["task_id"],
                subject_id=metadata["subject_id"],
                hand_sides=metadata["mano_sides"],
                independently_annotated_interperson_handoffs=0,
                independently_annotated_corrections=0,
            )
        )
    result = dict(
        raw_frames=len(rows),
        sequences=summaries,
        identical_receipts_deduplicated=repeated_receipts,
        raw_and_author_hashes_verified=True,
        explicit_event_labels_available=False,
        two_hands_do_not_establish_two_people=True,
        runtime_labels_injected=False,
        natural_p5_acceptance=False,
        pose_pairs=len(pairs),
        provenance=dict(
            raw_manifest=args.raw_manifest_sha256,
            annotation_manifest=args.annotation_manifest_sha256,
            download_receipts=args.receipts_sha256,
        ),
        limitations=[
            "Author poses/keypoints are supervision, not raw predictions",
            "Endpoint motion is not independently annotated pickup/release",
            "No interperson role or correction annotations in these files",
            "Replay frame ordinal is not a measured physical clock",
        ],
    )
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, value in (
        ("summary.json", result),
        ("frame_inventory.json", rows),
        ("pose_pairs.json", pairs),
    ):
        (args.output / filename).write_text(json.dumps(value, indent=2) + "\n")
    source = {
        p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in (__file__, "src/cpswm/data_preflight/natural_event_coverage.py")
    }
    (args.output / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
