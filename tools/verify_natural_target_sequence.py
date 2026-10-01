"""Fresh raw replay plus separately labelled offline instance-box diagnostics."""

import argparse
import base64
import json
from datetime import datetime
from pathlib import Path

import torch

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_target_sequence import NaturalTargetSequence
from cpswm.system.reproducibility import content_sha256


def overlap(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def verify(root, weights):
    report = json.loads((root / "result.json").read_text())
    sequence = NaturalTargetSequence(weights_path=weights)
    replay = []
    for folder in sorted((root / "public").iterdir()):
        row = json.loads((folder / "raw.json").read_text())
        raw = row["observations"][0]
        observation = RawModalityObservation(
            raw["envelope_json"],
            base64.b64decode(raw["payload_base64"]),
            raw["capture_receipt_sha256"],
            raw["depth_unit"],
        )
        replay.append(
            sequence.observe(observation, cutoff=datetime.fromisoformat(row["received_at"]))
        )
    # JSON-normalize UUID/datetime fields identically to capture output.
    replay = json.loads(json.dumps(replay, default=str))
    assert content_sha256(replay) == content_sha256(report["frames"]), "fresh inference differs"
    rows = []
    initial_boxes = json.loads(
        (root / "transport/evaluator_only/sdk-events/004-boxes.json").read_text()
    )
    for frame in replay:
        index = frame["frame_index"]
        boxes = json.loads(
            (root / f"transport/evaluator_only/sdk-events/{index + 4:03d}-boxes.json").read_text()
        )
        for track in frame["tracks"]:
            first = next(t for t in replay[0]["tracks"] if t["anchor_id"] == track["anchor_id"])
            initial = first["box_xyxy"]
            ranking = (
                sorted(
                    ((overlap(initial, b), key) for key, b in initial_boxes.items()), reverse=True
                )
                if initial
                else []
            )
            box = track["box_xyxy"]
            # Retain all reference overlaps, no evaluator target returned to inference.
            rows.append(
                dict(
                    index=index,
                    anchor=track["anchor_id"],
                    status=track["status"],
                    initial_top3=ranking[:3],
                    patch_correlation=track["patch_correlation"],
                    tracked_overlaps={key: overlap(box, b) for key, b in boxes.items()}
                    if box
                    else {},
                    detector_categories=[c["category"] for c in frame["detector"]["candidates"]],
                )
            )
    result = dict(
        fresh_replay_equal=True,
        frames=len(replay),
        evaluator_only=True,
        rows=rows,
        scope="instance box overlap diagnostics, not calibrated identity or task success",
    )
    (root / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(fresh_replay_equal=True, frames=len(replay))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("weights", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(2)
    verify(args.root, args.weights)
