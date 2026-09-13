"""Sequential generation, then parallel correctness checks; no speed comparison.

Run with native Python, from this fixed worktree. A phase cannot overwrite logs.
"""

import concurrent.futures
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUNDLE = HERE / "bundle_v5"
PYTHON = "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python"
ENV = {
    **os.environ,
    "PYTHONPATH": str(ROOT / "src"),
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "S2_AUDIT_BUNDLE": str(BUNDLE),
    "S2_AUDIT_EVIDENCE_DIR": str(HERE / "r1_matrix"),
    "S2_SOURCE_EVIDENCE_DIR": str(HERE / "source_tests"),
    "S2_FAIRNESS_EVIDENCE_DIR": str(HERE / "fairness_tests"),
    "S2_DYNAMIC_EVIDENCE_DIR": str(HERE / "dynamic_tests"),
}
MAIN = ROOT / "apps/evaluation_runner/run_structure_two_comparison_audit.py"
ATTR = ROOT / "apps/evaluation_runner/summarize_structure_two_comparison_audit.py"


def run(name, args):
    command = [PYTHON, *map(str, args)]
    record = {
        "command": command,
        "cwd": str(ROOT),
        "environment_overrides": {
            k: v
            for k, v in ENV.items()
            if k.startswith("S2_")
            or k
            in ("PYTHONPATH", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
        },
        "started_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    print(name, "started", flush=True)
    with (HERE / "logs" / (name + ".log")).open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, env=ENV, stdout=stream, stderr=subprocess.STDOUT)
    record.update(
        exit_code=result.returncode, ended_utc=datetime.datetime.now(datetime.UTC).isoformat()
    )
    (HERE / (name + "_command.json")).write_text(json.dumps(record, indent=2) + "\n")
    print(name, "exit", result.returncode, flush=True)
    return result.returncode


if __name__ == "__main__":
    if sys.argv[1] == "generate":
        if run("generate", [MAIN, "--output", BUNDLE]):
            raise SystemExit(1)
        raise SystemExit(run("attribution_generate", [ATTR, "--bundle", BUNDLE]))
    if sys.argv[1] == "verify":
        commands = {
            "main_verify": [MAIN, "--output", BUNDLE, "--verify"],
            "attribution_verify": [ATTR, "--bundle", BUNDLE, "--verify"],
            "pytest_all": [
                "-m",
                "pytest",
                "-n",
                "3",
                "-q",
                "-o",
                "addopts=",
                "--junitxml=" + str(HERE / "pytest.xml"),
                "tests/test_structure_two_comparison_audit.py",
                "tests/test_structure_two_comparison_audit_verification.py",
                "tests/test_structure_two_comparison_audit_execution_source.py",
                "tests/test_structure_two_comparison_fairness.py",
                "tests/test_structure_two_comparison_dynamic.py",
            ],
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda pair: run(*pair), commands.items()))
        raise SystemExit(int(any(results)))
    raise SystemExit("choose generate or verify")
