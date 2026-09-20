"""Run only allowlisted development pixels after mandatory bottom-label removal.

The runtime reads no author phase CSV, participant mapping, or acquisition manifest.
Original published videos contain phase banners; their full frames are not model inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from run_person_interaction_video import run

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "configs/data/bimanual_pixel_policy.json"
CROP = (0, 0, 1920, 960)


def validate_pixel_input(video: Path, policy: dict) -> dict:
    if policy["crop_xywh"] != list(CROP) or policy["original_size"] != [1920, 1080]:
        raise ValueError("mandatory label-removal geometry changed")
    if not 0 < video.stat().st_size <= 16 * 1024 * 1024:
        raise ValueError("video size exceeds bounded allowlist")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    matching = [r for r in policy["videos"] if r["sha256"] == digest]
    if len(matching) != 1 or video.stat().st_size != matching[0]["bytes"]:
        raise ValueError("video is not in the inspected pixel allowlist")
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration",
                "-of",
                "json",
                str(video),
            ],
            text=True,
            timeout=60,
        )
    )["streams"]
    if len(probe) != 1 or [probe[0]["width"], probe[0]["height"]] != [1920, 1080]:
        raise ValueError("unexpected video dimensions")
    return {**matching[0], "duration": float(probe[0]["duration"])}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--hand-model", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    files = (Path(__file__).resolve(), POLICY)
    sources = {str(f.relative_to(REPO)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    policy = json.loads(POLICY.read_bytes())
    record = validate_pixel_input(args.video, policy)
    result = run(
        video=args.video,
        expected_sha256=record["sha256"],
        source_url=policy["source_url"],
        crop=CROP,
        start=0,
        duration=record["duration"],
        fps=10,
        weights=args.weights,
        hand_model=args.hand_model,
        hand_person_rois=True,
        detector_name="fasterrcnn",
        output=args.output,
    )
    after = {str(f.relative_to(REPO)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    if sources != after:
        raise RuntimeError("pixel policy source changed during inference")
    (args.output / "pixel-policy-receipt.json").write_text(
        json.dumps(
            {
                "source_files": sources,
                "video_sha256": record["sha256"],
                "crop_xywh": CROP,
                "removed_rectangle_xywh": [0, 960, 1920, 120],
                "author_tables_read": False,
                "full_published_frames_model_visible": False,
                "domain": "motion_capture_development_not_marker_free_household",
                "result_sha256": hashlib.sha256(
                    (args.output / "result.json").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
