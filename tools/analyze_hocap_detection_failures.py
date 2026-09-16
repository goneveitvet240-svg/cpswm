"""Offline, pinned per-target diagnosis; annotations never feed capture/inference.

Keep old localization calibration failed. No fitting or threshold selection here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np

from cpswm.data_preflight.detection_diagnostics import classify_miss
from cpswm.data_preflight.hocap_evaluation import match_targets, read_author_targets
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource
from cpswm.perception_mapping.natural_vision import DetectionCandidate
from cpswm.system.reproducibility import content_sha256


def pinned(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("artifact pin mismatch: " + str(path))
    return json.loads(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-manifest", "annotation-manifest", "capture-manifest", "baseline-frames"):
        p.add_argument("--" + name, type=Path, required=True)
        p.add_argument("--" + name + "-sha256", required=True)
    p.add_argument("--evaluator-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    raw = pinned(args.raw_manifest, args.raw_manifest_sha256)
    labels = pinned(args.annotation_manifest, args.annotation_manifest_sha256)
    capture = pinned(args.capture_manifest, args.capture_manifest_sha256)
    baseline = pinned(args.baseline_frames, args.baseline_frames_sha256)
    root = args.capture_manifest.parent.resolve()
    frames = pinned(root / "frames.json", capture["frames_sha256"])
    if frames != baseline:
        raise ValueError("instrumentation changed retained production predictions")
    if capture["manifest_sha256"] != args.raw_manifest_sha256:
        raise ValueError("capture uses different raw input")
    sources = [HOCapFrameSource(**r) for r in raw]
    scope = uuid5(NAMESPACE_URL, "hocap-development:" + args.raw_manifest_sha256)
    by_id = {str(uuid5(scope, s.member("rgb"))): s for s in sources}
    by_label = {(r["sequence_id"], r["camera_id"], r["frame_index"]): r for r in labels}
    by_artifact = {r["observation_id"]: r for r in capture["artifacts"]}
    if (
        len(by_id) != len(raw)
        or len(by_label) != len(labels)
        or len(by_artifact) != len(capture["artifacts"])
        or {f["observation_id"] for f in frames} != set(by_id)
        or len(frames) != len(by_id)
        or set(by_artifact) != set(by_id)
        or set(by_label) != {(s.sequence_id, s.camera_id, s.frame_index) for s in sources}
    ):
        raise ValueError("duplicate or mismatched frame pairing")
    valid_classes = [
        i for i, c in enumerate(capture["categories"]) if i > 0 and c not in {"person", "N/A"}
    ]
    person_label = capture["categories"].index("person")
    rows = []
    label_root = args.evaluator_root.resolve()
    for f in frames:
        s = by_id[f["observation_id"]]
        if (
            f["receipt_sha256"] != content_sha256(s)
            or f["frame_id"] != f"hocap:{s.sequence_id}:{s.camera_id}"
            or f["minimum_score"] != capture["application_score_threshold"]
        ):
            raise ValueError("frame receipt or configuration mismatch")
        label = by_label[(s.sequence_id, s.camera_id, s.frame_index)]
        expected = f"{s.sequence_id}/{s.camera_id}/label_{s.frame_index:06d}.npz"
        path = (label_root / label["member"]).resolve()
        if label["member"] != expected or not path.is_relative_to(label_root):
            raise ValueError("invalid annotation member")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != label["annotation_sha256"]:
            raise ValueError("annotation digest mismatch")
        targets = read_author_targets(payload)
        candidates = tuple(
            DetectionCandidate(
                UUID(c["candidate_id"]), c["category"], c["detector_score"], tuple(c["box_xyxy"])
            )
            for c in f["candidates"]
        )
        matches, missed = match_targets(candidates, targets)
        matched = {m.matched_target for m in matches if m.matched_target is not None}
        artifact = by_artifact[f["observation_id"]]
        path = (root / artifact["file"]).resolve()
        if not path.is_relative_to(root) or path.suffix != ".npz":
            raise ValueError("invalid stage member")
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("stage digest mismatch")
        with np.load(path, allow_pickle=False) as stages:
            boxes = stages["boxes"][:, valid_classes].reshape(-1, 4).astype(float)
            scores = stages["scores"][:, valid_classes].reshape(-1).astype(float)
            native_mask = np.isin(stages["native_labels"], valid_classes)
            nb = stages["native_boxes"][native_mask].astype(float)
            ns = stages["native_scores"][native_mask].astype(float)
            pb = stages["native_boxes"][
                (stages["native_labels"] == person_label) & (stages["native_scores"] >= 0.5)
            ].astype(float)
        for target in targets:
            if target.box_xyxy is None:
                continue
            result = classify_miss(
                target.box_xyxy,
                matched=target.name in matched,
                roi_boxes=boxes,
                roi_scores=scores,
                native_boxes=nb,
                native_scores=ns,
                person_boxes=pb,
                native_threshold=capture["native_score_threshold"],
            )
            rows.append(
                dict(
                    sequence_id=s.sequence_id,
                    camera_id=s.camera_id,
                    frame_index=s.frame_index,
                    target=target.name,
                    box_xyxy=target.box_xyxy,
                    observation_id=f["observation_id"],
                    annotation_sha256=label["annotation_sha256"],
                    missed=target.name in missed,
                    **asdict(result),
                )
            )
    groups = defaultdict(list)
    for row in rows:
        groups[(row["sequence_id"], row["target"])].append(row)
    by_target, windows = [], []
    for (sequence, target), group in sorted(groups.items()):
        group.sort(key=lambda r: r["frame_index"])
        by_target.append(
            dict(
                sequence_id=sequence,
                target=target,
                target_frames=len(group),
                mechanisms=dict(Counter(r["mechanism"] for r in group)),
            )
        )
        centers = [
            ((r["box_xyxy"][0] + r["box_xyxy"][2]) / 2, (r["box_xyxy"][1] + r["box_xyxy"][3]) / 2)
            for r in group
        ]
        motion = [0.0] + [float(np.linalg.norm(np.array(b) - a)) for a, b in pairwise(centers)]
        peak = int(np.argmax(motion))
        center = group[peak]["frame_index"]
        for name, start, end in [
            ("ordinal_start", 0, 19),
            ("ordinal_middle", 20, 39),
            ("ordinal_end", 40, 59),
            ("max_visible_bbox_motion_proxy", max(0, center - 5), min(59, center + 5)),
        ]:
            subset = [r for r in group if start <= r["frame_index"] <= end]
            windows.append(
                dict(
                    sequence_id=sequence,
                    target=target,
                    window=name,
                    start_frame=start,
                    end_frame=end,
                    target_frames=len(subset),
                    mechanisms=dict(Counter(r["mechanism"] for r in subset)),
                    peak_center_shift_pixels=motion[peak] if name.endswith("proxy") else None,
                    event_label_authority="NO_CONTACT_OR_RELEASE_ANNOTATION",
                )
            )
    summary = dict(
        target_frames=len(rows),
        misses=sum(r["missed"] for r in rows),
        mechanisms=dict(Counter(r["mechanism"] for r in rows)),
        byte_equivalent_retained_predictions=True,
        paired_frames_validated=len(frames),
        pairing_validation="exact_identity_member_and_hash_not_independent_label_quality_audit",
        association_used_in_localization_metric=False,
        native_score_floor=capture["native_score_threshold"],
        native_top_k=capture["native_top_k"],
        native_nms=capture["native_nms_threshold"],
        interpretation="stage_opportunity_hierarchy_not_proven_causal_intervention",
        no_candidate_scope="after_RPN_only_not_all_anchors",
        calibration_refit=False,
        calibration_acceptance=False,
        label_scope="class_agnostic_visible_manipulation_target_bbox_matching",
        inputs={k: str(v) for k, v in vars(args).items() if k != "output"},
    )
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [
        ("summary", summary),
        ("per_target_frame", rows),
        ("by_sequence_target", by_target),
        ("event_windows", windows),
    ]:
        (args.output / (name + ".json")).write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
