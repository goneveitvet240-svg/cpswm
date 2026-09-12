"""Run source-bound checks; never overwrite an earlier attempt."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / sys.argv[1]
OUT.mkdir(exist_ok=False)
env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), OMP_NUM_THREADS="1")


def hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "configs", "tools")
        for p in sorted((ROOT / folder).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


commands = {
    "pytest": [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        "tests/test_structure_two_data_preflight.py",
        "tests/test_d0_shift_scenarios.py",
    ],
    "ruff": [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "src/cpswm/data_preflight",
        "tools/structure_two_data_preflight.py",
        "tests/test_structure_two_data_preflight.py",
    ],
    "mypy": [sys.executable, "-m", "mypy", "--follow-imports=silent", "src/cpswm/data_preflight"],
    "coverage": [
        sys.executable,
        "tools/structure_two_data_preflight.py",
        "coverage",
        "--output",
        str(OUT / "coverage.json"),
    ],
    "simulator_preflight": [
        sys.executable,
        "tools/structure_two_data_preflight.py",
        "simulator-preflight",
        "--output",
        str(OUT / "simulator.json"),
    ],
}
before = hashes()
results = {}
for name, command in commands.items():
    start = time.time()
    with (OUT / (name + ".log")).open("x") as output:
        result = subprocess.run(
            command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    results[name] = dict(command=command, exit_code=result.returncode, seconds=time.time() - start)
    print(name, result.returncode, flush=True)
after = hashes()
with (OUT / "manifest.json").open("x") as output:
    json.dump(
        dict(
            base_sha=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            executable=sys.executable,
            python=sys.version,
            commands=results,
            source_before=before,
            source_after=after,
            source_unchanged=before == after,
        ),
        output,
        indent=2,
    )
# Preflight exit 2 is a genuine unresolved runtime, not part of pytest pass totals.
sys.exit(
    int(
        before != after
        or any(
            r["exit_code"] != (2 if n == "simulator_preflight" else 0) for n, r in results.items()
        )
    )
)
