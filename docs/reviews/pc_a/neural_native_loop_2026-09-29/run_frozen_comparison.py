"""Two ordered audits, actual live artifacts, then the complete fixed matrix."""

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
    commands = [
        (
            "round1_comparison",
            [
                *pytest,
                "tests/test_neural_camera_comparison.py",
                "tests/test_pixel_camera_detector_binding.py",
                "tests/test_neural_pixel_camera_loop.py",
                "tests/test_joint_camera_feedback.py",
            ],
        )
    ]
    for kind, weights in (
        ("ssdlite", args.ssdlite_weights),
        ("fasterrcnn", args.fasterrcnn_weights),
    ):
        commands.append(
            (
                "audit_live_" + kind,
                [
                    python,
                    "-u",
                    "tools/run_neural_pixel_camera_loop.py",
                    "--output",
                    str(output / "audit-fixtures" / kind),
                    "--sdk-python",
                    str(args.sdk_python),
                    "--binary",
                    str(args.binary),
                    "--weights",
                    str(weights),
                    "--checkpoint",
                    str(args.checkpoints / "typed_factor_graph_transformer/checkpoint"),
                    "--site",
                    "north",
                    "--detector-kind",
                    kind,
                ],
            )
        )
    commands.extend(
        [
            ("round2_artifacts", [*pytest, "tests/test_neural_camera_comparison_artifacts.py"]),
            (
                "round2_recovery",
                [
                    *pytest,
                    "tests/test_joint_camera_feedback_recovery.py",
                    "tests/test_native_neural_recovery.py",
                ],
            ),
            ("mypy", [python, "-m", "mypy", "--no-incremental", "src"]),
        ]
    )
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "47b0bea", "HEAD"], cwd=ROOT, text=True
    )
    commands.append(
        (
            "ruff",
            [
                python,
                "-m",
                "ruff",
                "check",
                *[p for p in changed.splitlines() if p.endswith(".py")],
            ],
        )
    )
    shared = [
        "--ssdlite-weights",
        str(args.ssdlite_weights),
        "--fasterrcnn-weights",
        str(args.fasterrcnn_weights),
        "--checkpoints",
        str(args.checkpoints),
    ]
    commands.extend(
        [
            (
                "matrix",
                [
                    python,
                    "-u",
                    "tools/run_neural_camera_comparison.py",
                    "--output",
                    str(output / "matrix"),
                    "--sdk-python",
                    str(args.sdk_python),
                    "--binary",
                    str(args.binary),
                    *shared,
                ],
            ),
            (
                "verify_matrix",
                [
                    python,
                    "-u",
                    "tools/verify_neural_camera_comparison.py",
                    "--directory",
                    str(output / "matrix"),
                    *shared,
                ],
            ),
        ]
    )
    env = dict(
        os.environ,
        PYTHONHASHSEED="0",
        PYTHONPATH="src:tests:tools",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        CPSWM_SSDLITE_WEIGHTS=str(args.ssdlite_weights),
        CPSWM_FASTERRCNN_WEIGHTS=str(args.fasterrcnn_weights),
        CPSWM_CHECKPOINTS=str(args.checkpoints),
        CPSWM_COMPARISON_FIXTURES=str(output / "audit-fixtures"),
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
        start, started = monotonic(), datetime.now(UTC).isoformat()
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
    for name in (
        "output",
        "sdk-python",
        "binary",
        "ssdlite-weights",
        "fasterrcnn-weights",
        "checkpoints",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
