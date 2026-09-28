"""Sequential two-round checks and actual replay, bound to one committed source tree."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[4]
BASE = "2a0bbdf2e77e76b8e45d5f92211e820d337c3cf3"


def snapshot():
    entries = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT, text=True)
    result = {}
    for row in entries.splitlines():
        meta, name = row.split("\t", 1)
        if not (name.endswith(".py") or name in {"pyproject.toml", "uv.lock"}):
            continue
        blob = (ROOT / name).read_bytes()
        git_hash = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
        if git_hash != meta.split()[2]:
            raise ValueError("Python/dependency file differs from committed tree: " + name)
        result[name] = hashlib.sha256(blob).hexdigest()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
    )
    if any(n.endswith(".py") for n in untracked.splitlines()):
        raise ValueError("untracked Python could change executed source")
    return result


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = snapshot()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, text=True
    )
    python_files = [n for n in changed.splitlines() if n.endswith(".py")]
    python = str(ROOT / ".venv/bin/python")
    common = [python, "-m", "pytest", "-o", "addopts=", "-q"]
    commands = [
        ("round1_neural", [*common, "tests/test_native_neural_production.py"]),
        (
            "round1_adjacent",
            [
                *common,
                "tests/test_structure_two_selected_method.py",
                "tests/test_proposal_decoder.py",
                "tests/test_native_joint_production.py",
                "tests/test_continuous_camera_collection.py",
            ],
        ),
        ("round2_recovery", [*common, "tests/test_native_neural_recovery.py"]),
        (
            "round2_dependencies",
            [
                *common,
                "tests/test_native_joint_producer_binding.py",
                "tests/test_native_joint_full_replay.py",
            ],
        ),
        ("mypy", [python, "-m", "mypy", "--no-incremental", "src"]),
        ("ruff", [python, "-m", "ruff", "check", *python_files]),
        (
            "three_arm_actual_replay",
            [
                python,
                "-u",
                "tools/run_neural_native_replay.py",
                "--output",
                str(output / "actual-replay"),
            ],
        ),
    ]
    receipts = []
    env = dict(
        os.environ,
        PYTHONHASHSEED="0",
        PYTHONPATH="src:tests:tools",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
    )
    (output / "source.json").write_text(
        json.dumps({"head": head, "files": source}, indent=2) + "\n"
    )
    for name, command in commands:
        assert snapshot() == source
        if name.startswith("round"):
            command += ["--junitxml", str(output / (name + ".xml"))]
        start = monotonic()
        started = datetime.now(UTC).isoformat()
        with (output / (name + ".log")).open("w") as log:
            completed = subprocess.run(
                command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        same = snapshot() == source
        receipts.append(
            {
                "name": name,
                "command": command,
                "cwd": str(ROOT),
                "head": head,
                "started_at": started,
                "seconds": monotonic() - start,
                "exit_code": completed.returncode,
                "source_unchanged": same,
            }
        )
        (output / "commands.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps(receipts[-1]), flush=True)
        if completed.returncode or not same:
            raise SystemExit(completed.returncode or 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    main(parser.parse_args().output.resolve())
