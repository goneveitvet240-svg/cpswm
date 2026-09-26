"""Sequential two-review and full-source HFD intake with frozen Python receipts."""

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
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != metadata.split()[2]:
            raise ValueError(f"working Python differs from Git: {name}")
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
        start = datetime.now(UTC).isoformat()
        tick = time.monotonic()
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
            raise RuntimeError(f"failed command: {name}; retained log, no acceptance")

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
            "docs/reviews/pc_a/hfd_normal_evidence_2026-09-26/audit_round1.py",
            "tests/test_full_hfd_training.py",
            "tests/test_public_handover_evidence.py",
        ],
    )
    command(
        "round2",
        [python, "-m", "pytest", "-o", "addopts=", "-q", str(AUDIT / "audit_intake_second.py")],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    archive = main / "output/datasets/hfd-full-training-20260926/raw/training_set.verified.tar.gz"
    metadata = main / "output/joint-training-loop-20260925/public-evidence"
    argv = [
        python,
        "tools/inspect_hfd_training_archive.py",
        "--archive",
        str(archive),
        "--metadata",
        str(metadata),
        "--output",
        str(output / "packet"),
    ]
    command("real-intake", argv)
    # subprocess.run starts a fresh interpreter, rereads the complete source,
    # redecodes every trial and reconstructs every evaluator row and the report.
    command("fresh-source-reconstruction", [*argv, "--verify"])
    (output / "source-after.json").write_text(json.dumps(sources(), indent=2) + "\n")
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(baseline)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve())
