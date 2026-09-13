"""Record both post-fix adversarial rounds, preserving failure and source snapshots."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/pc_a/proposal_g1_fix_2026-09-13" / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)
PATHS = [
    *sorted((ROOT / "src/cpswm/data_preflight").glob("*.py")),
    ROOT / "tests/test_structure_two_proposal_g1_repair.py",
    ROOT / "tests/test_structure_two_proposal_scheduler.py",
    ROOT / "tests/test_pc_a_proposal_two_round_audit.py",
    ROOT / "tools/structure_two_prepare_proposals.py",
    Path(__file__),
]


def sources():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS}


before = sources()
for path in PATHS:
    target = OUT / "source_snapshot" / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(path.read_bytes())
commands = []
checks = [
    (
        "baseline",
        [
            "tests/test_structure_two_proposal_scheduler.py",
            "tests/test_structure_two_data_preflight.py",
            "tests/test_d0_shift_scenarios.py",
        ],
    ),
    (
        "round1",
        [
            "tests/test_pc_a_proposal_two_round_audit.py",
            "tests/test_structure_two_proposal_g1_repair.py",
            "-k",
            "round1",
        ],
    ),
    (
        "round2",
        [
            "tests/test_pc_a_proposal_two_round_audit.py",
            "tests/test_structure_two_proposal_g1_repair.py",
            "-k",
            "round2",
        ],
    ),
]
for label, args in checks:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        *args,
        "--tb=short",
        f"--junitxml={OUT / (label + '.xml')}",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    (OUT / f"{label}.log").write_text(result.stdout + result.stderr)
    commands.append({"label": label, "argv": command, "exit_code": result.returncode})
    print(label, result.returncode, result.stdout[-950:], flush=True)
receipt = {
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "python": sys.version,
    "executable": sys.executable,
    "platform": platform.platform(),
    "source_before": before,
    "source_after": sources(),
    "source_unchanged": before == sources(),
    "commands": commands,
    "training_started": False,
}
(OUT / "receipt.json").write_text(json.dumps(receipt, indent=2))
sys.exit(0 if all(c["exit_code"] == 0 for c in commands) and receipt["source_unchanged"] else 1)
