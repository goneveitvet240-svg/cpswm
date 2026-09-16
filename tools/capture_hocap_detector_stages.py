"""Raw-only Faster R-CNN stage capture; never opens annotation files.

Observe the existing RoI postprocessor without replacing its return value.
The captured pre-NMS boxes start AFTER RPN filtering, not at all network anchors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector
from cpswm.system.reproducibility import content_sha256


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-root", "manifest", "weights", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    args = p.parse_args()
    manifest = args.manifest.read_bytes()
    if hashlib.sha256(manifest).hexdigest() != args.manifest_sha256:
        raise ValueError("raw manifest pin mismatch")
    sources = [HOCapFrameSource(**row) for row in json.loads(manifest)]
    keys = [(s.sequence_id, s.camera_id, s.frame_index) for s in sources]
    if not keys or keys != sorted(set(keys)):
        raise ValueError("nonempty unique ordered frames required")
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    from torchvision.models.detection.transform import resize_boxes
    from torchvision.ops import boxes as box_ops

    torch.set_num_threads(2)
    scope = uuid5(NAMESPACE_URL, "hocap-development:" + args.manifest_sha256)
    detector = FasterNaturalAppearanceDetector(
        weights_path=args.weights,
        household_id=scope,
        session_id=scope,
        trace_id=scope,
        minimum_score=0.5,
    )
    roi = detector._model.roi_heads
    original = roi.postprocess_detections
    captured = {}

    def observe(logits, regression, proposals, shapes):
        result = original(logits, regression, proposals, shapes)
        if len(proposals) != 1:
            raise ValueError("single frame diagnostic required")
        decoded = roi.box_coder.decode(regression, proposals)
        decoded = box_ops.clip_boxes_to_image(decoded, shapes[0])
        scaled = resize_boxes(decoded.reshape(-1, 4), shapes[0], (480, 640))
        captured.update(
            boxes=scaled.reshape(decoded.shape).detach().cpu().numpy(),
            scores=torch.softmax(logits, -1).detach().cpu().numpy(),
            proposals=resize_boxes(proposals[0], shapes[0], (480, 640)).cpu().numpy(),
            native_boxes=resize_boxes(result[0][0], shapes[0], (480, 640)).cpu().numpy(),
            native_scores=result[1][0].cpu().numpy(),
            native_labels=result[2][0].cpu().numpy(),
        )
        return result

    roi.postprocess_detections = observe
    sequences = {s: i for i, s in enumerate(sorted({r.sequence_id for r in sources}))}
    frames, artifacts = [], []
    source_root = Path(__file__).resolve().parents[1]
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    files = [Path(__file__), source_root / "src/cpswm/perception_mapping/natural_vision.py"]
    source_files = {
        str(f.relative_to(source_root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files
    }
    for index, source in enumerate(sources):
        when = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(
            days=sequences[source.sequence_id], milliseconds=source.frame_index * 100
        )
        rgb, _ = adapt_hocap_rgbd(
            source,
            rgb_bytes=(args.raw_root / source.member("rgb")).read_bytes(),
            depth_bytes=(args.raw_root / source.member("depth")).read_bytes(),
            expected_source_sha256=content_sha256(source),
            household_id=scope,
            session_id=scope,
            trace_id=scope,
            capture_time=when,
            arrival_time=when,
        )
        captured.clear()
        frame = detector.infer(rgb, cutoff=when)
        frames.append(asdict(frame))
        path = args.output / f"{index:06d}_stages.npz"
        np.savez_compressed(path, **captured)
        artifacts.append(
            dict(
                observation_id=str(frame.observation_id),
                file=path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
        if (index + 1) % 20 == 0:
            print(json.dumps({"captured": index + 1}), flush=True)
    out = args.output / "frames.json"
    out.write_text(json.dumps(frames, default=str, indent=2) + "\n")
    after = {
        str(f.relative_to(source_root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files
    }
    if after != source_files:
        raise RuntimeError("capture source changed")
    summary = dict(
        source_sha=source_sha,
        source_files=source_files,
        manifest_sha256=args.manifest_sha256,
        frames_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        categories=detector._categories,
        native_score_threshold=roi.score_thresh,
        native_nms_threshold=roi.nms_thresh,
        native_top_k=roi.detections_per_img,
        application_score_threshold=0.5,
        artifacts=artifacts,
        stage_scope="after_RPN_before_RoI_score_size_NMS_topk",
        annotations_read=False,
        runtime_semantic_update=False,
        source_identity_scope="capture_and_detector_files_not_full_runtime_attestation",
    )
    (args.output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"artifacts", "categories"}}))


if __name__ == "__main__":
    main()
