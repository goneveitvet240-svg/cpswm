"""Read-only consistency audit of one recorded LIBERO integration run.

This checks artifacts against the bound Git commit, not independent attestation
or scientific acceptance. Run using the isolated simulation Python environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = args.run
    manifest = json.loads((run / "manifest.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    journal = json.loads((run / "journal.json").read_text())
    assert manifest["git_status"] == "" and summary["source_unchanged"]
    for path, digest in manifest["sources"].items():
        content = subprocess.check_output(
            ["git", "show", f"{manifest['code_sha']}:{path}"], cwd=root
        )
        assert hashlib.sha256(content).hexdigest() == digest, path
    assert all(not vendor["status"] for vendor in manifest["vendor"].values())
    assert summary["pi05_inference_executed"] and summary["native_memory_connected"]
    actions = [r for r in journal if r.get("event") == "executed_action"]
    inferences = [r for r in journal if r.get("event") == "policy_inference"]
    observations = [r for r in journal if "memory" in r]
    assert len(actions) == summary["steps"] > 0
    assert [r["tick"] for r in actions] == list(range(summary["steps"]))
    assert len(observations) == summary["sam_frames"]
    for item in inferences:
        output = np.load(run / f"policy_output_{item['tick']:05d}.npz")["actions"]
        assert output.shape == (10, 7) and np.isfinite(output).all()
        used = [r for r in actions if item["tick"] <= r["tick"] < item["tick"] + 5]
        for index, action in enumerate(used):
            np.testing.assert_array_equal(action["action"], output[index])
            assert action["revision"] == item["revision"]
            assert action["result"] == "simulator_step_returned"
    for index, item in enumerate(observations):
        event, receipt = item["observation"], item["memory"]
        assert receipt["ok"] and receipt["audit"]["particles"] == 24
        assert receipt["audit"]["event_count"] == index + 1
        assert event["occurred_at"] == event["available_at"] == item["tick"]
        assert event["actors"] == [["unknown_actor", 1.0]]
        assert event["robot_generated"] == (item["tick"] > 0)
        if index:
            assert event["visibility"] in ("predicted", "lost")
            assert receipt["current_location"] is None
    initial = np.load(run / "initial_observation.npz")
    displacement = float(
        np.linalg.norm(np.asarray(actions[-1]["eef_position_after"]) - initial["robot0_eef_pos"])
    )
    assert displacement > 0
    with imageio.get_reader(run / "rollout.mp4") as video:
        frames = list(video.iter_data())
    assert len(frames) == summary["steps"] + 1
    assert all(frame.shape == (256, 256, 3) for frame in frames)
    print(
        json.dumps(
            {
                "status": "CONSISTENCY_PASS",
                "code_sha": manifest["code_sha"],
                "source_files_bound": len(manifest["sources"]),
                "inferences": len(inferences),
                "inference_seconds": [r["seconds"] for r in inferences],
                "actions": len(actions),
                "visual_receipts": len(observations),
                "video_frames": len(frames),
                "eef_displacement_m": displacement,
                "task_success_evaluator_only": summary["task_success_evaluator_only"],
                "scientific_acceptance": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
