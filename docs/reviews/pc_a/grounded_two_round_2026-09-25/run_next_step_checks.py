"""Source-bound regression for the follow-on connection, separate from PR34 audit."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
tests = [
    "test_grounded_development_audit",
    "test_visual_target_tracking",
    "test_natural_vision",
    "test_natural_hands",
    "test_hand_object_evidence",
    "test_structure_two_continuous_input",
    "test_continuous_state_recovery",
    "test_joint_camera_policy",
    "test_continuous_camera_collection",
    "test_continuous_camera_cli",
    "test_native_joint_production",
    "test_structure_two_w3_native_posterior_projection",
    "test_structure_two_w3_native_particles",
    "test_structure_two_w3_native_bundle",
    "test_structure_two_joint_consumption_components",
    "test_structure_two_pose",
    "test_pose_observation_model",
    "test_proposal_decoder",
]
lint = [
    "src/cpswm/system/native_joint_production.py",
    "src/cpswm/system/structure_two_continuous_input.py",
    "src/cpswm/system/continuous_camera_collection.py",
    "tests/test_native_joint_production.py",
    "tests/test_grounded_development_audit.py",
    "tools/run_initialized_target_tracking.py",
    "tools/run_configured_joint_unity_probe.py",
    "tools/run_continuous_unity_camera.py",
]
commands = {
    "regression": [
        str(ROOT / ".venv/bin/pytest"),
        "-o",
        "addopts=",
        "-q",
        *[f"tests/{name}.py" for name in tests],
    ],
    "mypy": [str(ROOT / ".venv/bin/mypy"), "src"],
    "ruff": [str(ROOT / ".venv/bin/ruff"), "check", *lint],
}


def hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }


before = hashes()
report = {
    "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_files": before,
    "commands": {},
}
for label, command in commands.items():
    start = time.monotonic()
    with (out / f"{label}.txt").open("w") as log:
        proc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    report["commands"][label] = {
        "argv": command,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(time.monotonic() - start, 3),
    }
    print(label, proc.returncode, flush=True)
report["source_unchanged"] = hashes() == before
(out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
if not report["source_unchanged"] or any(c["exit_code"] for c in report["commands"].values()):
    raise SystemExit(1)
