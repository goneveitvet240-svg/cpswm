"""Summarize completed command/test outputs; this is not an authenticity verifier."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(path.read_text())


commands = {}
for name in ("generate", "attribution_generate", "main_verify", "attribution_verify", "pytest_all"):
    commands[name] = read(HERE / (name + "_command.json"))
    assert commands[name]["exit_code"] == 0, (name, commands[name])
xml = ET.parse(HERE / "pytest.xml")
suites = list(xml.getroot().iter("testsuite"))
counts = {
    key: sum(int(s.get(key, "0")) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
assert counts == {"tests": 77, "failures": 0, "errors": 0, "skipped": 0}, counts
matrices = {}
for name, path in (
    ("original_complete_forgeries", "r1_matrix/adversarial_matrix.json"),
    ("fairness_forgeries", "fairness_tests/fairness_forgery_matrix.json"),
    ("dynamic_forgeries", "dynamic_tests/matrix.json"),
):
    data = read(HERE / path)
    rows = data["result"]["results"]
    assert rows[0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    assert all(r["status"] == "REJECTED" and r["error"] for r in rows[1:])
    matrices[name] = {"valid_positive": rows[0]["status"], "rejected": len(rows) - 1, "path": path}
source_runs = []
for path in sorted((HERE / "source_tests").glob("*.json")):
    data = read(path)
    source_runs.append(
        {
            "name": path.stem,
            "exit_code": data["exit_code"],
            "outputs": [
                {k: v for k, v in row.items() if k in ("status", "error", "steps", "results")}
                for row in data["stdout_json"]
            ],
        }
    )
retained = read(HERE / "preservation_before.json")["protected_prior_files"]
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in retained.items())
baseline = "45850dc680cb83169c3108d6a1a5455f7e069457"
paths = [
    "apps/evaluation_runner/_structure_two_audit_source.py",
    "apps/evaluation_runner/run_structure_two_comparison_audit.py",
    "apps/evaluation_runner/summarize_structure_two_comparison_audit.py",
    "tests/test_structure_two_comparison_audit.py",
    "tests/test_structure_two_comparison_audit_verification.py",
    "tests/test_structure_two_comparison_audit_execution_source.py",
    "tests/test_structure_two_comparison_fairness.py",
    "tests/structure_two_comparison_audit_adversary.py",
]
unchanged = {}
for path in paths:
    old = subprocess.check_output(["git", "show", baseline + ":" + path], cwd=ROOT)
    unchanged[path] = old == (ROOT / path).read_bytes()
assert all(unchanged.values())
summary = {
    "classification": "DEVELOPMENT_DIAGNOSTIC_TOOLING_VERIFIED; SCIENTIFIC_PARTIAL",
    "runtime_source": read(HERE / "source_version.json"),
    "command_exit_codes": {k: v["exit_code"] for k, v in commands.items()},
    "tests": counts,
    "complete_forgery_matrices": matrices,
    "source_runs": source_runs,
    "protected_prior_files_unchanged": len(retained),
    "original_58_tests_and_source_protection_unchanged": unchanged,
    "scientific_fairness_established": False,
    "complete_direct_p5_mechanism": False,
    "three_arm_environment_execution_verified": False,
}
(HERE / "validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({"tests": counts, "matrices": matrices, "protected_files": len(retained)}))
