"""Run every cell of the predeclared 6 x 2 x 2 development comparison."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from run_neural_pixel_camera_loop import ARMS, METHODS, ROOT, source_identity
from verify_neural_camera_comparison import FRONTENDS, SITES


def main(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = source_identity()[0]
    plan = [
        {
            "frontend": f,
            "site": s,
            "method": m,
            "directory": f"{f}/{s}/{m}",
            "exit_code": None,
            "status": "PENDING",
            "image_size": args.image_size,
        }
        for f in FRONTENDS
        for s in SITES
        for m in METHODS
    ]
    (output / "matrix.json").write_text(json.dumps(plan, indent=2) + "\n")
    for case in plan:
        if source_identity()[0] != source:
            raise ValueError("source changed during matrix")
        directory = output / case["directory"]
        directory.parent.mkdir(parents=True, exist_ok=True)
        weights = args.ssdlite_weights if case["frontend"] == "ssdlite" else args.fasterrcnn_weights
        arm = case["method"] if case["method"] in ARMS else ARMS[0]
        command = [
            sys.executable,
            "-u",
            "tools/run_neural_pixel_camera_loop.py",
            "--output",
            str(directory),
            "--sdk-python",
            str(args.sdk_python),
            "--binary",
            str(args.binary),
            "--weights",
            str(weights),
            "--checkpoint",
            str(args.checkpoints / arm / "checkpoint"),
            "--site",
            case["site"],
            "--max-actions",
            "3",
            "--method",
            case["method"],
            "--detector-kind",
            case["frontend"],
            "--image-size",
            str(args.image_size),
        ]
        case.update(status="RUNNING", command=command, started_at=datetime.now(UTC).isoformat())
        (output / "matrix.json").write_text(json.dumps(plan, indent=2) + "\n")
        started = monotonic()
        with (directory.parent / (directory.name + ".log")).open("w") as log:
            result = subprocess.run(
                command, cwd=ROOT, env=os.environ, stdout=log, stderr=subprocess.STDOUT
            )
        case.update(
            exit_code=result.returncode,
            seconds=monotonic() - started,
            status="COMPLETE" if result.returncode == 0 else "FAILED",
            source_unchanged=source_identity()[0] == source,
        )
        (output / "matrix.json").write_text(json.dumps(plan, indent=2) + "\n")
        print(json.dumps(case), flush=True)
        if not case["source_unchanged"]:
            raise ValueError("source changed during episode")
    if any(c["exit_code"] for c in plan):
        raise SystemExit(1)


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
    p.add_argument("--image-size", type=int, choices=(320, 640), default=320)
    main(p.parse_args())
