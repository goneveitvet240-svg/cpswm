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


def run(source, output):
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
            "-o",
            "addopts=",
            "-q",
            "tests/test_visor_contact_supervision.py",
            "tests/test_full_hfd_training.py",
            "tests/test_public_handover_evidence.py",
            "tests/test_hocap_joint_supervision.py",
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
            str(AUDIT / "audit_second.py"),
            "tests/test_structure_two_continuous_input.py",
            "tests/test_continuous_state_recovery.py",
        ],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    args = [
        python,
        "tools/prepare_visor_contact_supervision.py",
        "--source",
        str(source),
        "--output",
        str(output / "packet"),
    ]
    command("real-import", args)
    command("fresh-source-verify", [*args, "--verify"])
    command(
        "learning-consumer",
        [
            python,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from cpswm.data_preflight.visor_contact_supervision import load_contact_component; "
            "x=load_contact_component(Path(sys.argv[1]),Path(sys.argv[2])); "
            'print(json.dumps({"inputs":len(x["inputs"]),"targets":len(x["targets"]),"report":x["report"]},indent=2))',
            str(source),
            str(output / "packet"),
        ],
    )
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(before)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source.resolve(), args.output.resolve())
