"""Source-bound commands with a fresh Python cache domain; no old-output overwrite."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
label = sys.argv[1]
files = sys.argv[2:] or [
    "tests/test_structure_two_selected_method.py",
    "tests/test_structure_two_particle_falsifier.py",
    "tests/test_structure_two_neural_amortized.py",
    "tests/test_structure_two_stateful_full_joint.py",
    "tests/test_structure_two_stateful_full_joint_adversarial.py",
    "tests/test_structure_two_task7_support_recovery.py",
]


def hashes():
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "configs", "artifacts")
        for p in sorted((root / folder).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


command = [
    sys.executable,
    "-m",
    "pytest",
    "-o",
    "addopts=",
    "-q",
    "-n",
    "4",
    "-p",
    "no:cacheprovider",
    "--junitxml=" + str(out / (label + ".xml")),
    *files,
]
before = hashes()
env = {
    **os.environ,
    "PYTHONPATH": str(root / "src"),
    "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(prefix="w3-r7-cache-"),
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
}
started = time.time()
with (out / (label + ".txt")).open("x") as log:
    result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
after = hashes()
(out / (label + ".command.json")).write_text(
    json.dumps(
        {
            "command": command,
            "cwd": str(root),
            "exit_code": result.returncode,
            "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root)
            .decode()
            .strip(),
            "seconds": time.time() - started,
            "python_version": sys.version,
            "environment": {
                k: env[k]
                for k in (
                    "PYTHONPATH",
                    "PYTHONPYCACHEPREFIX",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "OMP_NUM_THREADS",
                )
            },
            "source_before": before,
            "source_after": after,
            "source_unchanged": before == after,
        },
        indent=2,
    )
)
print(label, result.returncode, flush=True)
sys.exit(result.returncode)
