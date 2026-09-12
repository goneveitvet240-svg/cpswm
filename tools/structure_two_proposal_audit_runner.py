"""Run and preserve author audit evidence; never changes production source."""

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/pc_a/proposal_two_round_audit_2026-09-13" / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)


def hashes():
    paths = [
        *(ROOT / "src/cpswm/data_preflight").glob("*.py"),
        ROOT / "tools/structure_two_prepare_proposals.py",
        ROOT / "tools/structure_two_procthor_pilot.py",
        ROOT / "tests/test_pc_a_proposal_two_round_audit.py",
        Path(__file__),
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


before = hashes()
results = []
for label, args in [
    (
        "baseline",
        [
            "tests/test_structure_two_proposal_scheduler.py",
            "tests/test_structure_two_data_preflight.py",
            "tests/test_d0_shift_scenarios.py",
        ],
    ),
    ("round1", ["tests/test_pc_a_proposal_two_round_audit.py", "-k", "round1"]),
    ("round2", ["tests/test_pc_a_proposal_two_round_audit.py", "-k", "round2"]),
]:
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
    (OUT / (label + ".log")).write_text(result.stdout + result.stderr)
    results.append({"label": label, "command": command, "exit_code": result.returncode})
    print(label, result.returncode, result.stdout[-1200:], flush=True)
(OUT / "receipt.json").write_text(
    json.dumps(
        {
            "tested_base": "5ec6204dfecc9137523b6c0e5dfb66658e574d41",
            "head_at_run": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "source_before": before,
            "source_after": hashes(),
            "source_unchanged": before == hashes(),
            "results": results,
            "scope": "author self-audit; component counterexamples, not independent B acceptance",
        },
        indent=2,
    )
)
