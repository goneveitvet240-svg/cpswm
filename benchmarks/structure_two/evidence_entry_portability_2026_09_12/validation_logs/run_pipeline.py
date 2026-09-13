"""Sequential native validation; stop on any incomplete or failed stage."""

import json
import subprocess
import sys
import time
from pathlib import Path

root = Path.cwd()
logs = Path("benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs")
while True:
    rows = [json.loads(line) for line in (logs / "commands.jsonl").read_text().splitlines()]
    prerequisite = next((r for r in rows if r["name"] == "original79_plus36_regressions"), None)
    if prerequisite:
        break
    time.sleep(2)
assert prerequisite["exit_code"] == 0, prerequisite
stages = [
    (
        "generate_five_v04",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/run_structure_two_evidence_repair.py",
            "--generate-current",
        ],
    ),
    (
        "verify_five_v04",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/run_structure_two_evidence_repair.py",
            "--verify-current",
        ],
    ),
    (
        "generate_history_v03",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/audit_structure_two_evidence_history.py",
            "--recompute-first-failure",
            "--recompute-failed-replay",
            "--output",
            "benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json",
        ],
    ),
    (
        "verify_history_v03",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/audit_structure_two_evidence_history.py",
            "--verify",
            "benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json",
        ],
    ),
    (
        "aggregate_history_v03",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/run_structure_two_evidence_repair.py",
            "--verify-history",
        ],
    ),
    (
        "v05_compatibility",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/audit_structure_two_world_source_bundle_v0_5.py",
        ],
    ),
    (
        "preservation_and_scientific_equality",
        [".venv/bin/python", str(logs / "check_preservation_and_semantics.py")],
    ),
    (
        "generate_p0",
        [".venv/bin/python", "apps/evaluation_runner/generate_p0_checkpoint_manifest.py"],
    ),
    (
        "native_engineering_audit",
        [
            ".venv/bin/python",
            "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py",
        ],
    ),
]
for name, argv in stages:
    print(json.dumps({"starting": name, "argv": argv}), flush=True)
    result = subprocess.run([sys.executable, str(logs / "run_logged.py"), name, *argv], cwd=root)
    if result.returncode:
        print(json.dumps({"failed_stage": name, "exit_code": result.returncode}), flush=True)
        sys.exit(result.returncode)
print("PIPELINE_THROUGH_NATIVE_AUDIT_COMPLETE; fresh checkpoint still required", flush=True)
