"""Track a reviewed first-frame bag patch without later labels or author answers.

The annotation file is split before tracking: only initialization is given to the
tracker. Later support proxies are evaluation-only and do not calibrate contact.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker


def run(pixels: Path, annotation_path: Path, output: Path) -> dict:
    import cv2

    annotation_bytes = annotation_path.read_bytes()
    annotations = json.loads(annotation_bytes)
    root = Path(__file__).resolve().parents[1]
    sources = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (
            Path(__file__),
            root / "src/cpswm/perception_mapping/visual_target_tracking.py",
            root / "uv.lock",
            root / "pyproject.toml",
        )
    }
    if not annotations.get("clips"):
        raise ValueError("nonempty complete clip coverage required")
    names = [c["clip_id"] for c in annotations["clips"]]
    if len(set(names)) != len(names) or any(
        not name or Path(name).name != name or name in {".", ".."} for name in names
    ):
        raise ValueError("unique local clip directory names required")
    output.mkdir(parents=True, exist_ok=False)
    clips = []
    for clip in annotations["clips"]:
        directory = pixels / clip["clip_id"]
        archive_bytes = (directory / "result.json").read_bytes()
        if hashlib.sha256(archive_bytes).hexdigest() != clip["input_result_sha256"]:
            raise ValueError("original pixel run changed")
        archive = json.loads(archive_bytes)
        rows = clip["rows"]
        if len(rows) != archive["frames"] or len(rows) != len(archive["records"]) or not rows:
            raise ValueError("annotation must cover the complete original frame count")
        for index, (row, recorded) in enumerate(zip(rows, archive["records"], strict=True)):
            if (
                type(row["frame_index"]) is not int
                or row["frame_index"] != index
                or row["payload_sha256"] != recorded["visual"]["input_sha256"]
            ):
                raise ValueError("annotation differs from ordered original archive payloads")
        tracker = InitializedPixelTargetTracker(tuple(clip["first_frame_initialization_xyxy"]))
        frames = []
        for row in clip["rows"]:
            raw = (directory / f"{row['frame_index']:04d}.npy").read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["payload_sha256"]:
                raise ValueError("reviewed pixels changed")
            # Load exactly the bytes just checked.
            rgb = np.load(io.BytesIO(raw), allow_pickle=False)
            measured = tracker.update(rgb, frame_index=row["frame_index"])
            frames.append({**asdict(measured), "payload_sha256": row["payload_sha256"]})
            im = Image.fromarray(rgb)
            if measured.box_xyxy is not None:
                ImageDraw.Draw(im).rectangle(measured.box_xyxy, outline="red", width=5)
            im.thumbnail((640, 320))
            im.save(output / f"{clip['clip_id']}-{row['frame_index']:04d}.jpg")
        clips.append({"clip": clip["clip_id"], "measurements": frames})
    result = {
        "track": "FIRST_FRAME_ANNOTATION_ASSISTED_PIXEL_TRACKING",
        "annotation_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
        "source_files": sources,
        "runtime_dependencies": {
            "python": sys.version,
            "numpy": np.__version__,
            "opencv": cv2.__version__,
        },
        "measurement_input_sha256_encoding": "RGB_UINT8_C_ORDER_BYTES",
        "later_labels_used_by_tracker": False,
        "independent_contact_calibration": False,
        "world_instance_or_pose_established": False,
        "natural_grounded_transition_authorized": False,
        "clips": clips,
    }
    if annotation_path.read_bytes() != annotation_bytes:
        raise ValueError("annotation changed during tracking")
    if any(
        hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
        for name, digest in sources.items()
    ):
        raise ValueError("source changed during tracking")
    result["source_unchanged"] = True
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
