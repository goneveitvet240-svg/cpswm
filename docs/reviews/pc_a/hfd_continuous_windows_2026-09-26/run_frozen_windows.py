"""Freeze -> two sequential audits -> original windows -> hand and object frontend."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AUDIT = Path(__file__).resolve().parent


def sources():
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT).decode()
    state = {}
    for line in tree.splitlines():
        metadata, name = line.split("\t", 1)
        if not name.endswith(".py") or not name.startswith(
            ("src/", "tests/", "tools/", "docs/reviews/pc_a/")
        ):
            continue
        raw = (ROOT / name).read_bytes()
        if (
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            != metadata.split()[2]
        ):
            raise ValueError("working Python differs from Git: " + name)
        state[name] = hashlib.sha256(raw).hexdigest()
    return state


def run(main, output):
    output.mkdir(parents=True, exist_ok=False)
    baseline = sources()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    (output / "source-before.json").write_text(json.dumps(baseline, indent=2) + "\n")
    receipts = []

    def command(name, argv):
        if sources() != baseline:
            raise ValueError("Python source changed before command")
        start, tick = datetime.now(UTC).isoformat(), time.monotonic()
        with (output / f"{name}.log").open("wb") as stream:
            result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        receipt = {
            "name": name,
            "argv": argv,
            "started_utc": start,
            "seconds": time.monotonic() - tick,
            "exit_code": result.returncode,
        }
        receipts.append(receipt)
        (output / "commands.json").write_text(
            json.dumps({"source_sha": sha, "commands": receipts}, indent=2) + "\n"
        )
        print(json.dumps(receipt), flush=True)
        if sources() != baseline:
            raise ValueError("Python source changed during command")
        if result.returncode:
            raise RuntimeError("failed command: " + name)

    python = sys.executable
    command(
        "round1",
        [
            python,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "tests/test_hfd_continuous_windows.py",
            "tests/test_hfd_observation_alignment.py",
            "tests/test_natural_hands.py",
            "tests/test_hand_object_evidence.py",
            "tests/test_hand_person_regions.py",
            "tests/test_continuous_state_recovery.py",
            "tests/test_structure_two_continuous_input.py",
            "tests/test_archive_media_timeline.py",
            "tests/test_natural_vision.py",
            "tests/test_runtime_candidates.py",
            "tests/test_interaction_evidence.py",
        ],
    )
    command(
        "round2",
        [
            python,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            str(AUDIT / "audit_windows_second.py"),
            str(AUDIT.parent / "hfd_observation_alignment_2026-09-26/audit_alignment_second.py"),
        ],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    imported = datetime.now(UTC).isoformat()
    argv = [
        python,
        "tools/align_hfd_observations.py",
        "--archive",
        str(main / "output/datasets/hfd-full-training-20260926/raw/training_set.verified.tar.gz"),
        "--metadata",
        str(main / "output/joint-training-loop-20260925/public-evidence"),
        "--intake",
        str(main / "output/complete-hfd-resume-20260926/closed/final-02/packet"),
        "--output",
        str(output / "aligned"),
        "--imported-at",
        imported,
        "--sampling",
        "continuous",
    ]
    command("real-alignment", argv)
    command("fresh-source-reconstruction", [*argv, "--verify"])
    runtime = output / "aligned/runtime"
    pin = hashlib.sha256((runtime / "manifest.json").read_bytes()).hexdigest()
    command(
        "real-frontend",
        [
            python,
            "tools/run_hfd_continuous_frontend.py",
            "--runtime",
            str(runtime),
            "--manifest-sha256",
            pin,
            "--weights",
            str(main / "output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"),
            "--hand-model",
            str(main / "output/models/mediapipe/hand_landmarker-1.task"),
            "--output",
            str(output / "frontend"),
        ],
    )
    (output / "source-after.json").write_text(json.dumps(sources(), indent=2) + "\n")
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(baseline)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve())
