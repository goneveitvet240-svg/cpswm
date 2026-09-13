"""Verify frozen G1 source, actual captured bytes, linters, and all stored evidence."""

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpswm.data_preflight.capture_prefix import (  # noqa: E402
    read_sensor_snapshot,
    released_capture_prefix,
)

OUT = ROOT / "docs/reviews/pc_a/proposal_g1_fix_2026-09-13"
CHECK = OUT / "verification"
CHECK.mkdir(exist_ok=False)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


cpu = read(OUT / "run_03/receipt.json")
assert cpu["source_unchanged"]
for name, expected in cpu["source_after"].items():
    assert sha(ROOT / name) == expected, name
real = read(OUT / "procthor_run_01/receipt.json")
assert real["source_unchanged"] and real["execution"]["complete"]
for name, expected in real["source_after"].items():
    assert sha(ROOT / name) == expected, name
run = OUT / "procthor_run_01/schedule_run"
captures = released_capture_prefix(run / "observation_candidates", 10000)
for candidate in captures:
    receipt = read(
        run / "evaluator_only/raw/observations" / candidate["sensor_file"].replace(".npz", ".json")
    )
    assert candidate["sensor_sha256"] == receipt["sensor_sha256"]
    read_sensor_snapshot(
        run / "observation_candidates" / candidate["sensor_file"],
        expected_sha256=receipt["sensor_sha256"],
        depth_unit=receipt["depth_unit"],
    )
assert len(captures) == 36
results = {}
for name in ("baseline", "round1", "round2"):
    suite = ET.parse(OUT / f"run_03/{name}.xml").getroot().find("testsuite")
    results[name] = {k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")}
    assert results[name]["failures"] == results[name]["errors"] == results[name]["skipped"] == 0
checks = [
    (
        "ruff",
        [
            "ruff",
            "check",
            "src/cpswm/data_preflight",
            "tests/test_structure_two_proposal_g1_repair.py",
            "tests/test_pc_a_proposal_two_round_audit.py",
            "tests/test_structure_two_proposal_scheduler.py",
            "tools/structure_two_prepare_proposals.py",
            "tools/structure_two_proposal_g1_checks.py",
            "tools/structure_two_procthor_multiagent_probe.py",
            "tools/structure_two_proposal_g1_verify.py",
        ],
    ),
    (
        "mypy",
        [
            "mypy",
            *[
                f"src/cpswm/data_preflight/{name}.py"
                for name in (
                    "capture_prefix",
                    "prepared_samples",
                    "proposal_samples",
                    "procthor_schedule",
                    "procthor_execution",
                )
            ],
        ],
    ),
]
command_results = []
for label, args in checks:
    command = [sys.executable, "-m", *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (CHECK / f"{label}.log").write_text(result.stdout + result.stderr)
    command_results.append({"command": command, "exit_code": result.returncode})
    assert result.returncode == 0, result.stdout + result.stderr
summary = {
    "frozen_code_sha": "2ebd815543a9e51948c0eba237aacff8629b51ed",
    "cpu_and_actual_source_verified": True,
    "tests": results,
    "real_events": real["execution"]["completed_events"],
    "real_captures_validated": len(captures),
    "commands": command_results,
    "training_started": False,
    "training_ready": False,
    "independent_acceptance": False,
    "dependencies": {
        name: importlib.metadata.version(name)
        for name in ("pytest", "pydantic", "numpy", "ruff", "mypy")
    },
}
(CHECK / "summary.json").write_text(json.dumps(summary, indent=2))
manifest = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(summary), flush=True)
