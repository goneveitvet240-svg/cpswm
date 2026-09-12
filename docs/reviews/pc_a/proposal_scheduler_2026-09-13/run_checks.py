"""Source-bound CPU contract checks; preserve every run including failures."""

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
paths = [
    *sorted((ROOT / "src/cpswm/data_preflight").glob("*.py")),
    ROOT / "tests/test_structure_two_proposal_scheduler.py",
    ROOT / "tools/structure_two_procthor_pilot.py",
    ROOT / "tools/structure_two_prepare_proposals.py",
]


def sources():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }


env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONHASHSEED="0")
record = {
    "python": sys.executable,
    "version": sys.version,
    "cwd": str(ROOT),
    "base_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_before": sources(),
    "commands": [],
}
files = [
    str(x.relative_to(ROOT))
    for x in paths
    if x.name
    not in {"__init__.py", "train_coverage.py", "visible_prefix.py", "simulator_capture.py"}
]
commands = {
    "pytest": [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_structure_two_proposal_scheduler.py",
        "tests/test_structure_two_data_preflight.py",
        "tests/test_d0_shift_scenarios.py",
        f"--junitxml={OUT / 'pytest.xml'}",
    ],
    "ruff": [sys.executable, "-m", "ruff", "check", *files, "--output-format", "concise"],
    "mypy": [
        sys.executable,
        "-m",
        "mypy",
        "--follow-imports=silent",
        "src/cpswm/data_preflight/proposal_samples.py",
        "src/cpswm/data_preflight/procthor_schedule.py",
        "src/cpswm/data_preflight/procthor_execution.py",
        "src/cpswm/data_preflight/capture_prefix.py",
    ],
}
for name, command in commands.items():
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    with (OUT / f"{name}.log").open("x", encoding="utf-8") as handle:
        handle.write(result.stdout + result.stderr)
    record["commands"].append(
        {
            "name": name,
            "argv": command,
            "exit_code": result.returncode,
            "seconds": time.monotonic() - started,
        }
    )
    print(name, result.returncode, result.stdout[-500:])
record["source_after"] = sources()
record["source_unchanged"] = record["source_before"] == record["source_after"]
with (OUT / "manifest.json").open("x", encoding="utf-8") as handle:
    json.dump(record, handle, indent=2)
raise SystemExit(
    int(any(x["exit_code"] for x in record["commands"]) or not record["source_unchanged"])
)
