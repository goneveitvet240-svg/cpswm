"""Freeze-bound sequential A audits, then actual import and fresh-source verification."""

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
        meta, name = line.split("\t", 1)
        if not name.endswith(".py") or not name.startswith(
            ("src/", "tests/", "tools/", "docs/reviews/pc_a/")
        ):
            continue
        raw = (ROOT / name).read_bytes()
        if (
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            != meta.split()[2]
        ):
            raise ValueError("working Python differs from Git: " + name)
        state[name] = hashlib.sha256(raw).hexdigest()
    return state


def run(main, output):
    output.mkdir(parents=True, exist_ok=False)
    before = sources()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    (output / "source-before.json").write_text(json.dumps(before, indent=2) + "\n")
    receipts = []

    def command(name, argv):
        assert sources() == before
        started = datetime.now(UTC).isoformat()
        tick = time.monotonic()
        with (output / (name + ".log")).open("wb") as stream:
            result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row = {
            "name": name,
            "argv": argv,
            "started_utc": started,
            "seconds": time.monotonic() - tick,
            "exit_code": result.returncode,
        }
        receipts.append(row)
        (output / "commands.json").write_text(
            json.dumps({"source_sha": sha, "commands": receipts}, indent=2) + "\n"
        )
        assert sources() == before
        (output / "source-after.json").write_text(json.dumps(sources(), indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if result.returncode:
            raise RuntimeError("failed: " + name)

    python = sys.executable
    command(
        "round1",
        [
            python,
            "-m",
            "pytest",
            "--import-mode=importlib",
            "-o",
            "addopts=",
            "-q",
            "tests/test_visor_feature_control.py",
            "tests/test_visor_pixel_supervision.py",
            "tests/test_visor_contact_supervision.py",
        ],
    )
    command(
        "round2",
        [
            python,
            "-m",
            "pytest",
            "--import-mode=importlib",
            "-o",
            "addopts=",
            "-q",
            str(AUDIT / "audit_second.py"),
            "docs/reviews/pc_a/visor_pixel_supervision_2026-09-27/audit_second.py",
            "tests/test_structure_two_continuous_input.py",
            "tests/test_continuous_state_recovery.py",
        ],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    closed = main / "output/visor-contact-supervision-20260927/closed"
    argv = [
        python,
        "-u",
        "tools/run_visor_feature_control.py",
        "--source",
        str(closed / "raw"),
        "--contact-packet",
        str(closed / "final-02/packet"),
        "--pixel-packet",
        str(main / "output/visor-pixel-supervision-20260927/closed/final-01/pixel-packet"),
        "--diagnostic-source",
        str(ROOT / "output/visor-control/raw"),
        "--weights",
        str(main / "output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"),
        "--output",
        str(output / "control"),
    ]
    command("actual-control", argv)
    command("fresh-complete-replay", [*argv, "--verify"])
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(before)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve())
