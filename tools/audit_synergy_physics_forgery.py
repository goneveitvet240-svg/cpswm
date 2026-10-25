"""A complete goal journal with a forged physical response must fail physics replay."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from replay_synergy_goal_physics import run as physical_replay
from run_libero_stack import save

ROOT = Path(__file__).resolve().parents[1]


def run(directory):
    with tempfile.TemporaryDirectory(prefix="synergy-physics-forgery-") as scratch:
        fake = Path(scratch) / "run"
        shutil.copytree(directory, fake)
        journal = json.loads((fake / "journal.json").read_text())
        first = next(x for x in journal if x["event"] == "executed_action")
        first["eef_position_after"][0] += 0.05
        (fake / "journal.json").write_text(json.dumps(journal))
        core = subprocess.run(
            [
                str(ROOT.parent / "envs/core/bin/python"),
                str(ROOT / "tools/verify_synergy_goal_episode.py"),
                str(fake),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if core.returncode != 0:
            raise AssertionError("forgery must pass structural core replay first: " + core.stderr)
        try:
            physical_replay(fake)
        except AssertionError as error:
            if "Not equal to tolerance" not in str(error):
                raise
            return {
                "status": "STRUCTURALLY_VALID_PHYSICS_FORGERY_REJECTED",
                "mutation": "first returned EEF x coordinate +0.05 m; other files retained",
                "core_replay_exit": core.returncode,
                "physics_rejection": str(error),
                "scientific_acceptance": False,
            }
        raise AssertionError("physical forgery incorrectly accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, run(args.run))
