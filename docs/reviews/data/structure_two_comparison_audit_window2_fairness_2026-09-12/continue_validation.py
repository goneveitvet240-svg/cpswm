"""Run AFTER bundle_v4 generation; record real commands, exit codes and logs.

After attribution/interface creation, independent correctness verifications run concurrently.
None of their timing samples is used for performance comparison.
All paths are derived from this worktree; never overwrites retained audit bundles.
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
bundle = out / "bundle_v4"
assert (bundle / "audit.json").exists(), "finish fresh generation first"
env = {
    **os.environ,
    "PYTHONPATH": str(root / "src"),
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "S2_AUDIT_BUNDLE": str(bundle),
    "S2_AUDIT_EVIDENCE_DIR": str(out / "evidence/r1_matrix"),
    "S2_SOURCE_EVIDENCE_DIR": str(out / "evidence/source_tests"),
    "S2_FAIRNESS_EVIDENCE_DIR": str(out / "evidence/fairness_tests"),
}
commands = [
    (
        "attribution_generation",
        [
            sys.executable,
            "apps/evaluation_runner/summarize_structure_two_comparison_audit.py",
            "--bundle",
            str(bundle),
        ],
    ),
    (
        "main_verify",
        [
            sys.executable,
            "apps/evaluation_runner/run_structure_two_comparison_audit.py",
            "--output",
            str(bundle),
            "--verify",
            "--timing-repeats",
            "1",
            "--timing-episodes",
            "1",
        ],
    ),
    (
        "attribution_verify",
        [
            sys.executable,
            "apps/evaluation_runner/summarize_structure_two_comparison_audit.py",
            "--bundle",
            str(bundle),
            "--verify",
        ],
    ),
    ("p5_interface", [sys.executable, str(out / "reproduce_p5_interface.py")]),
    (
        "regressions",
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "3",
            "-q",
            "-o",
            "addopts=",
            "--junitxml=" + str(out / "evidence/pytest.xml"),
            "tests/test_structure_two_comparison_audit.py",
            "tests/test_structure_two_comparison_audit_verification.py",
            "tests/test_structure_two_comparison_audit_execution_source.py",
            "tests/test_structure_two_comparison_fairness.py",
        ],
    ),
]
receipts = []


def execute(item):
    name, command = item
    print("RUNNING", name, flush=True)
    start = time.time()
    log = out / "evidence" / f"{name}.log"
    if log.exists():
        raise FileExistsError(log)
    with log.open("w") as stream:
        p = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    print("FINISHED", name, p.returncode, flush=True)
    return {
        "name": name,
        "command": command,
        "cwd": str(root),
        "environment": {
            k: env[k]
            for k in (
                "PYTHONPATH",
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
            )
        },
        "start_unix": start,
        "end_unix": time.time(),
        "exit_code": p.returncode,
        "log": str(log.relative_to(root)),
        "timing_for_performance_comparison": False,
    }


def record(receipt):
    receipts.append(receipt)
    (out / "command_receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")


for index in (0, 3):
    receipt = execute(commands[index])
    record(receipt)
    if receipt["exit_code"]:
        raise SystemExit(receipt["exit_code"])
with ThreadPoolExecutor(max_workers=3) as pool:
    for future in as_completed([pool.submit(execute, commands[i]) for i in (1, 2, 4)]):
        record(future.result())
raise SystemExit(int(any(r["exit_code"] for r in receipts)))
