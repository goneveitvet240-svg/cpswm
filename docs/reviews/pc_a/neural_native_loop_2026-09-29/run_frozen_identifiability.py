"""Freeze source, conduct two ordered reviews, then exhaust and reexecute 24 cases."""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from run_frozen import ROOT, snapshot


def main(output, checkpoints):
    output.mkdir(parents=True, exist_ok=False)
    source = snapshot()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    python = str(ROOT / ".venv/bin/python")
    pytest = [python, "-m", "pytest", "-o", "addopts=", "-q"]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "c54f890", "HEAD"], cwd=ROOT, text=True
    )
    commands = [
        (
            "round1_paths",
            [
                *pytest,
                "tests/test_camera_policy_identifiability.py",
                "tests/test_neural_camera_comparison.py",
            ],
        ),
        ("round2_artifacts", [*pytest, "tests/test_camera_policy_identifiability_artifacts.py"]),
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
    ]
    for mode in ("run", "verify"):
        commands.append(
            (
                mode + "_matrix",
                [
                    python,
                    "-u",
                    "tools/run_camera_policy_identifiability.py",
                    mode,
                    "--output",
                    str(output / "matrix"),
                    "--checkpoints",
                    str(checkpoints),
                ],
            )
        )
    env = dict(
        os.environ,
        PYTHONPATH="src:tests:tools",
        PYTHONHASHSEED="0",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        CPSWM_CHECKPOINTS=str(checkpoints),
    )
    (output / "source.json").write_text(json.dumps(dict(head=head, files=source), indent=2) + "\n")
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    args = parser.parse_args()
    main(args.output.resolve(), args.checkpoints.resolve())
