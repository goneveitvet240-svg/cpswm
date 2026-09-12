"""Scoped, source-bound checks; each run uses a new directory and preserves failures."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / sys.argv[1]
OUT.mkdir(exist_ok=False)
SOURCES = [
    "src/cpswm/system/structure_two_conditional_updates.py",
    "src/cpswm/system/structure_two_joint_consumption.py",
    "src/cpswm/world_model/grounded_search/active_verification.py",
]
TESTS = [
    "tests/test_structure_two_joint_consumption_components.py",
    "tests/test_structure_two_ciav.py",
    "tests/test_structure_two_ciav_negative_observation_layers.py",
    "tests/test_structure_two_w3_native_posterior_projection.py",
    "tests/test_project_two_ciav_interactive_development.py",
    "tests/test_project_two_ciav_break_even.py",
]


def hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "configs", "artifacts")
        for p in sorted((ROOT / folder).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


env = dict(
    os.environ,
    PYTHONPATH=str(ROOT / "src"),
    PYTHONDONTWRITEBYTECODE="1",
    PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="joint-check-cache-"),
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    OMP_NUM_THREADS="1",
)
commands = {
    "pytest": [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
        *TESTS,
    ],
    "ruff": [sys.executable, "-m", "ruff", "check", *SOURCES, TESTS[0], str(Path(__file__))],
    "mypy": [sys.executable, "-m", "mypy", "--follow-imports=silent", *SOURCES],
}
before = hashes()
results = {}
for name, command in commands.items():
    started = time.time()
    with (OUT / (name + ".log")).open("x") as log:
        result = subprocess.run(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    results[name] = dict(
        command=command, returncode=result.returncode, seconds=time.time() - started
    )
    print(name, result.returncode, flush=True)
after = hashes()
record = dict(
    base_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    python=sys.version,
    executable=sys.executable,
    cwd=str(ROOT),
    commands=results,
    source_before=before,
    source_after=after,
    source_unchanged=before == after,
)
with (OUT / "manifest.json").open("x") as output:
    json.dump(record, output, indent=2)
sys.exit(int(before != after or any(r["returncode"] for r in results.values())))
