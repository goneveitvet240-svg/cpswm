"""Two sequential frozen audits, then three independent fixed-window matrix arms."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

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
    receipt_lock = Lock()

    def command(name, argv):
        if sources() != baseline:
            raise ValueError("Python source changed before command")
        start, tick = datetime.now(UTC).isoformat(), time.monotonic()
        remaining = (datetime(2026, 9, 26, 16, 40, tzinfo=UTC) - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise RuntimeError("compute deadline reached; preserve incomplete matrix")
        timed_out = False
        with (output / f"{name}.log").open("wb") as stream:
            try:
                result = subprocess.run(
                    argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=remaining
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = 124
        receipt = {
            "name": name,
            "argv": argv,
            "started_utc": start,
            "seconds": time.monotonic() - tick,
            "exit_code": exit_code,
            "timed_out_at_compute_deadline": timed_out,
        }
        with receipt_lock:
            receipts.append(receipt)
            (output / "commands.json").write_text(
                json.dumps({"source_sha": sha, "commands": receipts}, indent=2) + "\n"
            )
            print(json.dumps(receipt), flush=True)
            if sources() != baseline:
                raise ValueError("Python source changed during command")
            (output / "source-latest.json").write_text(json.dumps(sources(), indent=2) + "\n")
        if exit_code:
            raise RuntimeError("failed or deadline-limited command: " + name)

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
            "tests/test_full_hand_proposal_matrix.py",
            "tests/test_proposal_hand_input.py",
            "tests/test_typed_proposal_training.py",
            "tests/test_proposal_inference_session.py",
            "tests/test_person_identity_ambiguity.py",
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
            str(AUDIT / "audit_matrix_second.py"),
            str(AUDIT.parent / "hand_proposal_input_2026-09-26/audit_hands_second.py"),
            str(AUDIT.parent / "person_ambiguity_2026-09-26/audit_person_second.py"),
            str(AUDIT.parent / "hfd_continuous_windows_2026-09-26/audit_windows_second.py"),
            str(AUDIT.parent / "hfd_observation_alignment_2026-09-26/audit_alignment_second.py"),
        ],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    frontend = main / "output/hand-proposal-input-20260926/closed/final-01/frontend"
    training = main / "output/hand-proposal-input-20260926/closed/final-01/derived"
    front_pin = "677505fa2891aab0b2602a5ec002ea3fb3612d5e219ad788437b5b03feaf3c48"

    def matrix_arm(arm):
        command(
            "full-" + arm,
            [
                python,
                "tools/run_hfd_hand_proposals.py",
                "--frontend",
                str(frontend),
                "--frontend-sha256",
                front_pin,
                "--training",
                str(training),
                "--output",
                str(output / arm),
                "--arm",
                arm,
                "--prefix-frames",
                "4",
                "--window-scope",
                "all",
                "--restore-scope",
                "first",
            ],
        )

    failures = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(matrix_arm, arm): arm
            for arm in (
                "typed_factor_graph_transformer",
                "slot_conditioned_perceiver",
                "autoregressive_typed_graph_policy",
            )
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:
                failures.append({"arm": futures[future], "error": str(error)})
    if sources() != baseline:
        raise ValueError("Python source changed across full matrix")
    (output / "source-after.json").write_text(json.dumps(sources(), indent=2) + "\n")
    (output / "matrix-status.json").write_text(
        json.dumps({"complete": not failures, "failures": failures}, indent=2) + "\n"
    )
    if failures:
        raise RuntimeError("matrix incomplete; preserve all arm receipts: " + str(failures))
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(baseline)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve())
