"""Two separate CLI stages: RGB-only inference, then source-rebuilt offline geometry."""

import argparse
import json
import os
import platform
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.visor_candidate_alignment import (
    PROFILE,
    SCOPE,
    evaluate,
    observation,
    runtime_frames,
    sha,
)
from cpswm.perception_mapping.natural_hands import NaturalHandDetector
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector


def infer(runtime, manifest_sha256, weights, hand_model):
    import mediapipe
    import torch
    import torchvision

    frames = runtime_frames(runtime, manifest_sha256)
    torch.set_num_threads(2)
    detector = FasterNaturalAppearanceDetector(
        weights_path=weights,
        **dict(zip(("household_id", "session_id", "trace_id"), SCOPE, strict=True)),
    )
    hands = NaturalHandDetector(model_path=hand_model, scope=SCOPE, person_rois=True)
    records = []
    when = datetime.now(UTC)
    try:
        for i, (row, raw_bytes) in enumerate(frames):
            raw = observation(row, raw_bytes, when)
            visual = detector.infer(raw, cutoff=when)
            hand = hands.infer_with_visual(raw, visual, cutoff=when)
            records.append(
                {
                    "input": row,
                    "hands": [
                        {
                            "id": str(h.candidate_id),
                            "points": h.landmarks_xy_pixels,
                            "side": h.handedness,
                            "score": h.handedness_score,
                            "region_id": str(h.region_id),
                        }
                        for h in hand.candidates
                    ],
                    "objects": [
                        {
                            "id": str(o.candidate_id),
                            "box": o.box_xyxy,
                            "category": o.category,
                            "score": o.detector_score,
                        }
                        for o in visual.candidates
                    ],
                }
            )
            print(
                json.dumps(
                    {
                        "done": i + 1,
                        "total": len(frames),
                        "hands": len(hand.candidates),
                        "objects": len(visual.candidates),
                    }
                ),
                flush=True,
            )
    finally:
        hands.close()
    return {
        "format": "visor_frontend_candidates_v1",
        "profile": PROFILE,
        "runtime_manifest_sha256": manifest_sha256,
        "imported_at": when.isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "mediapipe": mediapipe.__version__,
        },
        "records": records,
    }


def save_new(path, value):
    """Publish whole artifacts without overwriting an existing result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".visor-result-", dir=path.parent))
    try:
        tmp = staging / "result.json"
        tmp.write_bytes(encoded(value))
        os.link(tmp, path)  # atomic no-replace; temporary alias removed immediately
    finally:
        shutil.rmtree(staging)
    return sha(path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    a = sub.add_parser("infer")
    for name in ("runtime", "weights", "hand-model", "output"):
        a.add_argument("--" + name, type=Path, required=True)
    a.add_argument("--manifest-sha256", required=True)
    b = sub.add_parser("evaluate")
    for name in ("source", "packet", "prediction", "output"):
        b.add_argument("--" + name, type=Path, required=True)
    b.add_argument("--prediction-sha256", required=True)
    args = vars(parser.parse_args())
    stage, output = args.pop("stage"), args.pop("output")
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    value = infer(**args) if stage == "infer" else evaluate(**args)
    digest = save_new(output, value)
    print(
        json.dumps({"output": str(output), "sha256": digest, "summary": value.get("summary")}),
        flush=True,
    )
