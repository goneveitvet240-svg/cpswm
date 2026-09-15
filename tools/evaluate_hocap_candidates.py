"""Evaluate frozen pixel predictions against separately supplied HO-Cap labels.

The fit/evaluation split is two sequences versus a third sequence from the same
subject and object group. Results are exploratory component measurements only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.data_preflight.hocap_evaluation import match_targets, read_author_targets
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource
from cpswm.perception_mapping.interaction_evidence import (
    CalibrationExample,
    evaluate_calibration,
    fit_calibration,
)
from cpswm.perception_mapping.natural_vision import MODEL_ID, WEIGHTS_SHA256, DetectionCandidate
from cpswm.system.reproducibility import content_sha256

FIT_SEQUENCES = ("subject_5/20231027_112303", "subject_5/20231027_113202")
HOLDOUT_SEQUENCE = "subject_5/20231027_113535"


def pinned_json(path: Path, digest: str):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("artifact differs from retained pin: " + str(path))
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-manifest", "annotation-manifest", "frames"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--evaluator-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = pinned_json(args.raw_manifest, args.raw_manifest_sha256)
    labels = pinned_json(args.annotation_manifest, args.annotation_manifest_sha256)
    frames = pinned_json(args.frames, args.frames_sha256)
    scope = uuid5(NAMESPACE_URL, "hocap-development:" + args.raw_manifest_sha256)
    sources = [HOCapFrameSource(**row) for row in raw]
    by_id = {str(uuid5(scope, s.member("rgb"))): s for s in sources}
    by_frame = {f["observation_id"]: f for f in frames}
    by_label = {(r["sequence_id"], r["camera_id"], r["frame_index"]): r for r in labels}
    if (
        len(by_id) != len(raw)
        or len(by_frame) != len(frames)
        or len(by_label) != len(labels)
        or set(by_id) != set(by_frame)
        or set(by_label) != {(s.sequence_id, s.camera_id, s.frame_index) for s in sources}
    ):
        raise ValueError("evaluation must cover exactly every unique raw frame")
    root = args.evaluator_root.resolve()
    examples, per_frame = [], []
    configs = set()
    for identity, s in by_id.items():
        f = by_frame[identity]
        if (
            f["model_id"] != MODEL_ID
            or f["weights_sha256"] != WEIGHTS_SHA256
            or f["frame_id"] != f"hocap:{s.sequence_id}:{s.camera_id}"
            or f["receipt_sha256"] != content_sha256(s)
            or (f["width"], f["height"]) != (640, 480)
        ):
            raise ValueError("prediction source/model/frame mismatch")
        configs.add((f["minimum_score"], f["torch_version"], f["torchvision_version"]))
        if len(configs) != 1:
            raise ValueError("evaluation crosses detector configurations")
        label = by_label[(s.sequence_id, s.camera_id, s.frame_index)]
        expected_member = f"{s.sequence_id}/{s.camera_id}/label_{s.frame_index:06d}.npz"
        p = (root / label["member"]).resolve()
        if label["member"] != expected_member or not p.is_relative_to(root):
            raise ValueError("annotation member mismatch")
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != label["annotation_sha256"]:
            raise ValueError("annotation bytes changed")
        targets = read_author_targets(data)
        candidates = tuple(
            DetectionCandidate(
                UUID(c["candidate_id"]), c["category"], c["detector_score"], tuple(c["box_xyxy"])
            )
            for c in f["candidates"]
        )
        matches, missed = match_targets(candidates, targets)
        signature = content_sha256(
            {
                "weights": WEIGHTS_SHA256,
                "config": next(iter(configs)),
                "event": "class_agnostic_score_ranked_unique_annotated_target_iou_ge_0.5",
                "domain": "HO-Cap_subject5_G15_camera105322251564_first60frames",
            }
        )
        for m in matches:
            examples.append(
                CalibrationExample(
                    str(m.candidate_id),
                    s.sequence_id,
                    f["input_sha256"],
                    signature,
                    m.score,
                    m.matched_target is not None,
                    label["annotation_sha256"],
                    "dataset_annotation",
                )
            )
        per_frame.append(
            {
                "observation_id": identity,
                "sequence_id": s.sequence_id,
                "frame_index": s.frame_index,
                "targets": [asdict(t) for t in targets],
                "matches": [asdict(m) for m in matches],
                "missed_visible_targets": missed,
                "annotation_sha256": label["annotation_sha256"],
            }
        )
    fit = tuple(e for e in examples if e.sequence_id in FIT_SEQUENCES)
    heldout = tuple(e for e in examples if e.sequence_id == HOLDOUT_SEQUENCE)
    if len(fit) + len(heldout) != len(examples):
        raise ValueError("unregistered development sequence")
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {
        "frames": len(per_frame),
        "target_candidate_matches": sum(e.label for e in examples),
        "nonperson_candidates": len(examples),
        "missed_visible_target_frames": sum(len(f["missed_visible_targets"]) for f in per_frame),
        "visible_target_frames": sum(
            sum(t["box_xyxy"] is not None for t in f["targets"]) for f in per_frame
        ),
        "ambiguous_candidates": sum(m["ambiguous"] for f in per_frame for m in f["matches"]),
        "invisible_target_frames": sum(
            sum(t["box_xyxy"] is None for t in f["targets"]) for f in per_frame
        ),
        "fit_sequences": FIT_SEQUENCES,
        "heldout_sequence": HOLDOUT_SEQUENCE,
        "raw_manifest_sha256": args.raw_manifest_sha256,
        "annotation_manifest_sha256": args.annotation_manifest_sha256,
        "predictions_sha256": args.frames_sha256,
        "meaning": "localization_of_annotated_manipulation_targets_only",
        "scope": "same_subject_same_objects_exploratory_sequence_holdout",
        "scientific_acceptance": "NOT_ESTABLISHED",
        "role_calibration": False,
        "pose_error_calibration": False,
        "runtime_calibration_consumed": False,
    }
    if len(fit) >= 4 and len({e.label for e in fit}) == 2 and heldout:
        artifact = fit_calibration(fit)
        summary["calibration"] = evaluate_calibration(artifact, heldout)
        (args.output / "calibration.json").write_text(json.dumps(asdict(artifact), indent=2) + "\n")
    else:
        summary["calibration"] = "NOT_FIT: insufficient independent positive/negative support"
    for name, data in [
        ("summary.json", summary),
        ("per_frame.json", per_frame),
        ("calibration_examples.json", [asdict(e) for e in examples]),
    ]:
        (args.output / name).write_text(json.dumps(data, default=str, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
