"""Two ordered audits then complete 320/640 live matrices and reconstruction."""

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
            "round1_resolution",
            [
                *pytest,
                "tests/test_unity_capture_resolution.py",
                "tests/test_neural_camera_comparison.py",
                "tests/test_neural_pixel_camera_loop.py",
                "tests/test_joint_camera_feedback.py",
                "tests/test_pixel_camera_detector_binding.py",
            ],
        )
    ]
    for size, kind in ((320, "ssdlite"), (320, "fasterrcnn"), (640, "fasterrcnn")):
        weights = args.ssdlite_weights if kind == "ssdlite" else args.fasterrcnn_weights
        commands.append(
            (
                f"audit_live_{size}_{kind}",
                [
                    python,
                    "-u",
                    "tools/run_neural_pixel_camera_loop.py",
                    "--output",
                    str(output / f"audit-{size}" / kind),
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
                    "--image-size",
                    str(size),
                ],
            )
        )
    commands += [
        (
            "round2_artifacts",
            [
                *pytest,
                "tests/test_neural_camera_comparison_artifacts.py",
                "tests/test_resolution_comparison_artifacts.py",
            ],
        ),
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
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "8d0cfa3", "HEAD"], cwd=ROOT, text=True
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
    for size in (320, 640):
        directory = output / f"matrix-{size}"
        commands += [
            (
                f"matrix_{size}",
                [
                    python,
                    "-u",
                    "tools/run_neural_camera_comparison.py",
                    "--output",
                    str(directory),
                    "--sdk-python",
                    str(args.sdk_python),
                    "--binary",
                    str(args.binary),
                    "--image-size",
                    str(size),
                    *shared,
                ],
            ),
            (
                f"verify_{size}",
                [
                    python,
                    "-u",
                    "tools/verify_neural_camera_comparison.py",
                    "--directory",
                    str(directory),
                    "--image-size",
                    str(size),
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
        CPSWM_CHECKPOINTS=str(args.checkpoints),
        CPSWM_COMPARISON_FIXTURES=str(output / "audit-320"),
        CPSWM_RESOLUTION_FIXTURE=str(output / "audit-640/fasterrcnn"),
        MPLCONFIGDIR=str(output / "matplotlib-cache"),
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
    summaries = {
        str(s): json.loads((output / f"matrix-{s}/verified-summary.json").read_text())
        for s in (320, 640)
    }
    assert all(
        v["verified_episodes"] == 24 and v["same_initial_priors"] for v in summaries.values()
    )
    report = {
        "source_head": head,
        "verified_episodes": 48,
        "shared_methods_models_thresholds_and_budget": True,
        "complete_natural_closed_loop": False,
        "matrices": summaries,
    }
    (output / "resolution-summary.json").write_text(json.dumps(report, indent=2) + "\n")


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
