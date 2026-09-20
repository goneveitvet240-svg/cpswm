"""Evaluate fixed hand predictions against separately pinned HO-Cap keypoints.

Hungarian assignment is geometric and side-independent. Assignment is not a
correct-detection claim; all pixel errors and unmatched counts remain visible.
No contact/release, person identity or 3D pose probability is fitted here.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from cpswm.data_preflight.natural_event_coverage import inspect_annotation, pinned_bytes
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource
from cpswm.system.reproducibility import content_sha256


def evaluate_frame(predictions, payload):
    with np.load(io.BytesIO(payload), allow_pickle=False) as annotation:
        truth = annotation["hand_joints_2d"].astype(float)
        xyz = annotation["hand_joints_3d"]
    valid = (
        np.isfinite(truth).all(axis=2)
        & np.isfinite(xyz).all(axis=2)
        & ~(xyz == -1).all(axis=2)
        & (truth[:, :, 0] >= 0)
        & (truth[:, :, 0] < 640)
        & (truth[:, :, 1] >= 0)
        & (truth[:, :, 1] < 480)
    )
    sides = [i for i in range(2) if valid[i].any()]
    costs = np.zeros((len(predictions), len(sides)))
    for i, prediction in enumerate(predictions):
        points = np.asarray(prediction["landmarks_xy_pixels"], dtype=float)
        if points.shape != (21, 2) or not np.isfinite(points).all():
            raise ValueError("invalid prediction landmarks")
        for j, side in enumerate(sides):
            costs[i, j] = np.linalg.norm(
                points[valid[side]] - truth[side, valid[side]], axis=1
            ).mean()
    p_indices, t_indices = linear_sum_assignment(costs)
    matches = []
    for i, j in zip(p_indices.tolist(), t_indices.tolist(), strict=True):
        side = sides[j]
        points = np.asarray(predictions[i]["landmarks_xy_pixels"])
        errors = np.linalg.norm(points[valid[side]] - truth[side, valid[side]], axis=1)
        matches.append(
            dict(
                candidate_id=predictions[i]["candidate_id"],
                author_side=("Right", "Left")[side],
                predicted_side=predictions[i]["handedness"],
                mean_pixel_error=float(errors.mean()),
                joint_errors_px=errors.tolist(),
            )
        )
    return dict(
        visible_annotated_hands=len(sides),
        predicted_hands=len(predictions),
        assigned_pairs=matches,
        unassigned_annotations=len(sides) - len(matches),
        unassigned_predictions=len(predictions) - len(matches),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "hand-frames", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("raw-manifest-sha256", "annotation-manifest-sha256", "hand-frames-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    sources = [
        HOCapFrameSource(**r)
        for r in json.loads(
            pinned_bytes(
                (args.dataset / "raw_manifest.json").read_bytes(), args.raw_manifest_sha256
            )
        )
    ]
    labels = json.loads(
        pinned_bytes(
            (args.dataset / "annotation_manifest.json").read_bytes(),
            args.annotation_manifest_sha256,
        )
    )
    frames = json.loads(pinned_bytes(args.hand_frames.read_bytes(), args.hand_frames_sha256))
    if len(sources) != len(labels) or len(sources) != len(frames):
        raise ValueError("prediction/raw/annotation coverage differs")
    label_index = {(r["sequence_id"], r["camera_id"], r["frame_index"]): r for r in labels}
    if len(label_index) != len(labels):
        raise ValueError("duplicate label identity")
    seen, rows, groups = set(), [], defaultdict(list)
    for source, frame in zip(sources, frames, strict=True):
        key = (source.sequence_id, source.camera_id, source.frame_index)
        if key in seen or frame["capture_receipt_sha256"] != content_sha256(source):
            raise ValueError("duplicate or mismatched raw prediction identity")
        seen.add(key)
        if frame["width"] != 640 or frame["height"] != 480:
            raise ValueError("hand prediction dimensions differ")
        label = label_index[key]
        member = f"{source.sequence_id}/{source.camera_id}/label_{source.frame_index:06d}.npz"
        if label["member"] != member:
            raise ValueError("label belongs to a different frame")
        path = (args.dataset / "evaluator" / member).resolve()
        if not path.is_relative_to((args.dataset / "evaluator").resolve()):
            raise ValueError("label escaped evaluator root")
        payload = pinned_bytes(path.read_bytes(), label["annotation_sha256"])
        inspect_annotation(payload, expected_sha256=label["annotation_sha256"])
        result = dict(
            sequence_id=source.sequence_id,
            frame_index=source.frame_index,
            **evaluate_frame(frame["candidates"], payload),
        )
        rows.append(result)
        groups[source.sequence_id].append(result)
    summaries = []
    for sequence, group in sorted(groups.items()):
        errors = [m["mean_pixel_error"] for row in group for m in row["assigned_pairs"]]
        summaries.append(
            dict(
                sequence=sequence,
                frames=len(group),
                annotated_hands=sum(r["visible_annotated_hands"] for r in group),
                predictions=sum(r["predicted_hands"] for r in group),
                assignments=len(errors),
                unassigned_annotations=sum(r["unassigned_annotations"] for r in group),
                unassigned_predictions=sum(r["unassigned_predictions"] for r in group),
                assigned_error_quantiles_px=(
                    None if not errors else np.quantile(errors, [0, 0.25, 0.5, 0.75, 1]).tolist()
                ),
            )
        )
    args.output.mkdir(parents=True, exist_ok=False)
    summary = dict(
        sequences=summaries,
        heldout_confirmation=False,
        supervised_event_calibration=False,
        predictions_fitted_on_labels=False,
        hand_frames_sha256=args.hand_frames_sha256,
        raw_manifest_sha256=args.raw_manifest_sha256,
        annotation_manifest_sha256=args.annotation_manifest_sha256,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        interpretation="Unthresholded assignment error; no contact/person/3D claims",
    )
    for name, value in (("summary.json", summary), ("per_frame.json", rows)):
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
