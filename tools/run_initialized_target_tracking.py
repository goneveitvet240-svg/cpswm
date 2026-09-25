"""Track a reviewed first-frame bag patch without later labels or author answers.

The annotation file is split before tracking: only initialization is given to the
tracker. Later support proxies are evaluation-only and do not calibrate contact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker


def run(pixels: Path, annotation_path: Path, output: Path) -> dict:
    annotations = json.loads(annotation_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    clips = []
    for clip in annotations["clips"]:
        directory = pixels / clip["clip_id"]
        if (
            hashlib.sha256((directory / "result.json").read_bytes()).hexdigest()
            != clip["input_result_sha256"]
        ):
            raise ValueError("original pixel run changed")
        tracker = InitializedPixelTargetTracker(tuple(clip["first_frame_initialization_xyxy"]))
        frames = []
        for row in clip["rows"]:
            raw = (directory / f"{row['frame_index']:04d}.npy").read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["payload_sha256"]:
                raise ValueError("reviewed pixels changed")
            # Load exactly the bytes just checked.
            import io

            rgb = np.load(io.BytesIO(raw), allow_pickle=False)
            measured = tracker.update(rgb, frame_index=row["frame_index"])
            frames.append(asdict(measured))
            im = Image.fromarray(rgb)
            if measured.box_xyxy is not None:
                ImageDraw.Draw(im).rectangle(measured.box_xyxy, outline="red", width=5)
            im.thumbnail((640, 320))
            im.save(output / f"{clip['clip_id']}-{row['frame_index']:04d}.jpg")
        clips.append({"clip": clip["clip_id"], "measurements": frames})
    result = {
        "track": "FIRST_FRAME_ANNOTATION_ASSISTED_PIXEL_TRACKING",
        "annotation_sha256": hashlib.sha256(annotation_path.read_bytes()).hexdigest(),
        "later_labels_used_by_tracker": False,
        "independent_contact_calibration": False,
        "world_instance_or_pose_established": False,
        "natural_grounded_transition_authorized": False,
        "clips": clips,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixels", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.pixels, args.annotations, args.output)
    print(
        json.dumps(
            {
                c["clip"]: {
                    "frames": len(c["measurements"]),
                    "retained": sum(m["box_xyxy"] is not None for m in c["measurements"]),
                }
                for c in result["clips"]
            }
        )
    )
