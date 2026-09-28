"""Freeze -> two sequential camera audits -> two fixed real Unity scene initializations."""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from run_frozen import ROOT, snapshot


def main(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = snapshot()
    python = str(ROOT / ".venv/bin/python")
    common = [python, "-m", "pytest", "-o", "addopts=", "-q"]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "87ef8525929c67ff180c5200fbd07193e5b25325", "HEAD"],
        cwd=ROOT,
        text=True,
    )
    commands = [
        (
            "round1_feedback",
            [
                *common,
                "tests/test_joint_camera_feedback.py",
                "tests/test_neural_pixel_camera_loop.py",
                "tests/test_native_neural_production.py",
            ],
        ),
        (
            "round1_adjacent",
            [
                *common,
                "tests/test_joint_camera_policy.py",
                "tests/test_continuous_camera_collection.py",
                "tests/test_native_joint_production.py",
            ],
        ),
        (
            "round2_feedback_recovery",
            [
                *common,
                "tests/test_joint_camera_feedback_recovery.py",
                "tests/test_native_neural_recovery.py",
            ],
        ),
        (
            "round2_state_dependencies",
            [
                *common,
                "tests/test_native_joint_producer_binding.py",
                "tests/test_native_joint_full_replay.py",
                "tests/test_continuous_state_recovery.py",
            ],
        ),
        ("mypy", [python, "-m", "mypy", "--no-incremental", "src"]),
        (
            "ruff",
            [
                python,
                "-m",
                "ruff",
                "check",
                *[n for n in changed.splitlines() if n.endswith(".py")],
            ],
        ),
    ]
    for site in ("north", "south"):
        commands.append(
            (
                "live_" + site,
                [
                    python,
                    "-u",
                    "tools/run_neural_pixel_camera_loop.py",
                    "--output",
                    str(output / ("live-" + site)),
                    "--sdk-python",
                    str(args.sdk_python),
                    "--binary",
                    str(args.binary),
                    "--weights",
                    str(args.weights),
                    "--checkpoint",
                    str(args.checkpoint),
                    "--site",
                    site,
                ],
            )
        )
    env = dict(
        os.environ,
        PYTHONHASHSEED="0",
        PYTHONPATH="src:tests:tools",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        CPSWM_SSDLITE_WEIGHTS=str(args.weights),
        MPLCONFIGDIR=str(output / "matplotlib-cache"),
    )
    (output / "source.json").write_text(
        json.dumps({"head": head, "files": source}, indent=2) + "\n"
    )
    receipts = []
    for name, command in commands:
        assert snapshot() == source
        if name.startswith("round"):
            command += ["--junitxml", str(output / (name + ".xml"))]
        started = datetime.now(UTC).isoformat()
        start = monotonic()
        with (output / (name + ".log")).open("w") as log:
            result = subprocess.run(
                command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        same = snapshot() == source
        row = {
            "name": name,
            "command": command,
            "cwd": str(ROOT),
            "head": head,
            "started_at": started,
            "seconds": monotonic() - start,
            "exit_code": result.returncode,
            "source_unchanged": same,
        }
        receipts.append(row)
        (output / "commands.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if result.returncode or not same:
            raise SystemExit(result.returncode or 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "sdk-python", "binary", "weights", "checkpoint"):
        parser.add_argument("--" + name, type=Path, required=True)
    main(parser.parse_args())
