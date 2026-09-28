"""Audit selected instance correspondence twice, collect three snapshots, and re-infer."""

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
    source = snapshot()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    python = str(ROOT / ".venv/bin/python")
    pytest = [python, "-m", "pytest", "-o", "addopts=", "-q"]
    shared = [
        "--sdk-python",
        str(args.sdk_python),
        "--binary",
        str(args.binary),
        "--ssdlite-weights",
        str(args.ssdlite_weights),
        "--fasterrcnn-weights",
        str(args.fasterrcnn_weights),
    ]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "b0a2aba", "HEAD"], cwd=ROOT, text=True
    )
    commands = [
        (
            "round1_instances",
            [
                *pytest,
                "tests/test_instance_correspondence.py",
                "tests/test_neural_pixel_camera_loop.py",
                "tests/test_natural_vision.py",
                "tests/test_unity_capture_resolution.py",
            ],
        ),
        (
            "live_instance_fixture",
            [
                python,
                "-u",
                "tools/run_instance_correspondence_diagnostic.py",
                "--mode",
                "fixture",
                "--output",
                str(output / "audit-fixture"),
                *shared,
            ],
        ),
        (
            "round2_instances",
            [
                *pytest,
                "tests/test_instance_correspondence_artifacts.py",
                "tests/test_pixel_camera_detector_binding.py",
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
                *[p for p in changed.splitlines() if p.endswith(".py")],
            ],
        ),
        (
            "actual_instances",
            [
                python,
                "-u",
                "tools/run_instance_correspondence_diagnostic.py",
                "--mode",
                "run",
                "--output",
                str(output / "snapshots"),
                *shared,
            ],
        ),
        (
            "recompute_instances",
            [
                python,
                "-u",
                "tools/run_instance_correspondence_diagnostic.py",
                "--mode",
                "verify",
                "--output",
                str(output / "snapshots"),
                *shared,
            ],
        ),
    ]
    env = dict(
        os.environ,
        PYTHONPATH="src:tests:tools",
        PYTHONHASHSEED="0",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        CPSWM_SSDLITE_WEIGHTS=str(args.ssdlite_weights),
        CPSWM_FASTERRCNN_WEIGHTS=str(args.fasterrcnn_weights),
        CPSWM_INSTANCE_FIXTURE=str(output / "audit-fixture"),
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
        started, start = datetime.now(UTC).isoformat(), monotonic()
        with (output / (name + ".log")).open("w") as log:
            result = subprocess.run(
                command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        row = dict(
            name=name,
            command=command,
            head=head,
            cwd=str(ROOT),
            started_at=started,
            seconds=monotonic() - start,
            exit_code=result.returncode,
            source_unchanged=snapshot() == source,
        )
        receipts.append(row)
        (output / "commands.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if result.returncode or not row["source_unchanged"]:
            raise SystemExit(result.returncode or 2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
