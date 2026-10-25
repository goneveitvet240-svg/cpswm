"""A complete action journal can be structurally valid and physically false."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from verify_native_pi05_probe import verify_physics

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="native-physical-negative-") as tmp:
        target = Path(tmp) / "run"
        shutil.copytree(args.path, target)
        journal = json.loads((target / "journal.json").read_text())
        first = next(row for row in journal if row["event"] == "action")
        first["eef"][0] += 0.05
        (target / "journal.json").write_text(json.dumps(journal))
        environment = dict(os.environ, PYTHONPATH=str(ROOT / "src") + ":" + str(ROOT / "tools"))
        process = subprocess.run(
            [
                str(ROOT.parent / "envs/core/bin/python"),
                str(ROOT / "tools/verify_native_pi05_probe.py"),
                str(target),
                "--output",
                str(Path(tmp) / "core.json"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            verify_physics(target)
        except AssertionError as error:
            result = {
                "complete_journal_structural_replay_passed": True,
                "physical_replay_rejected": True,
                "mutation": "first returned EEF x +0.05m",
                "reason": str(error),
                "core_stdout": process.stdout,
            }
        else:
            raise AssertionError("false physical state was accepted")
    args.output.write_text(json.dumps(result, indent=2))
    print(result)


if __name__ == "__main__":
    main()
