"""Audit twice, collect both complete resolution grids and re-infer all 132 frames."""

import argparse
import json
import math
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
        ["git", "diff", "--name-only", "db67b66", "HEAD"], cwd=ROOT, text=True
    )
    commands = [
        (
            "round1_grid",
            [
                *pytest,
                "tests/test_camera_measurement_grid.py",
                "tests/test_camera_grid_resolution.py",
                "tests/test_unity_capture_resolution.py",
                "tests/test_natural_vision.py",
            ],
        ),
        (
            "live_grid_320_fixture",
            [
                python,
                "-u",
                "tools/run_camera_measurement_grid.py",
                "--mode",
                "fixture",
                "--output",
                str(output / "audit-fixture"),
                "--image-size",
                "320",
                *shared,
            ],
        ),
        (
            "live_grid_640_fixture",
            [
                python,
                "-u",
                "tools/run_camera_measurement_grid.py",
                "--mode",
                "fixture",
                "--output",
                str(output / "audit-640-fixture"),
                "--image-size",
                "640",
                *shared,
            ],
        ),
        (
            "round2_grid",
            [
                *pytest,
                "tests/test_camera_measurement_grid_artifacts.py",
                "tests/test_camera_grid_resolution_artifacts.py",
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
    ]
    for size in (320, 640):
        for mode in ("run", "verify"):
            commands.append(
                (
                    f"{mode}_grid_{size}",
                    [
                        python,
                        "-u",
                        "tools/run_camera_measurement_grid.py",
                        "--mode",
                        mode,
                        "--output",
                        str(output / f"grid-{size}"),
                        "--image-size",
                        str(size),
                        *shared,
                    ],
                )
            )
    env = dict(
        os.environ,
        PYTHONPATH="src:tests:tools",
        PYTHONHASHSEED="0",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        CPSWM_SSDLITE_WEIGHTS=str(args.ssdlite_weights),
        CPSWM_FASTERRCNN_WEIGHTS=str(args.fasterrcnn_weights),
        CPSWM_GRID_FIXTURE=str(output / "audit-fixture"),
        CPSWM_GRID_640_FIXTURE=str(output / "audit-640-fixture"),
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

    summaries = {
        str(size): json.loads((output / f"grid-{size}/summary.json").read_text())
        for size in (320, 640)
    }
    for size in (320, 640):
        verification = json.loads((output / f"grid-{size}/verification.json").read_text())
        assert verification["verified_frames"] == 66 and verification["image_size"] == size
    for a, b in zip(summaries["320"]["cases"], summaries["640"]["cases"], strict=True):
        assert (a["site"], a["camera_x"]) == (b["site"], b["camera_x"])
        assert all(
            math.isclose(a[field][k], b[field][k], abs_tol=1e-5)
            for field in ("actual_agent_position", "actual_camera_position")
            for k in ("x", "y", "z")
        )
    comparison = dict(
        source_head=head,
        complete_frames=132,
        detector_frame_measurements=264,
        same_actual_camera_positions_across_resolutions=True,
        independent_scenes=False,
        empirical_model_fitted=False,
        complete_natural_closed_loop=False,
        summaries=summaries,
    )
    (output / "resolution-grid-summary.json").write_text(json.dumps(comparison, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
