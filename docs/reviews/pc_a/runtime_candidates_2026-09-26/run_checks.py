"""Source-bound runtime candidate regression and static checks."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=False)
python = str(ROOT / ".venv/bin/python")
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
    "test_proposal_learning",
    "test_structure_two_proposal_scheduler",
    "test_hocap_joint_supervision",
    "test_typed_proposal_training",
    "test_conditional_revision_replay",
    "test_public_handover_evidence",
    "test_joint_package_adversarial",
    "test_proposal_inference_session",
    "test_runtime_candidates",
    "test_interaction_evidence",
]
changed = subprocess.check_output(
    [
        "git",
        "diff",
        "--name-only",
        "7727d893e139e46512488474b268399dce7b6714",
        "HEAD",
        "--",
        "src",
        "tests",
        "tools",
    ],
    cwd=ROOT,
    text=True,
).splitlines()
commands = {
    "regression": [
        python,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        *[f"tests/{n}.py" for n in tests],
    ],
    "mypy": [python, "-m", "mypy", "src"],
    "ruff": [python, "-m", "ruff", "check", *changed],
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
    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "commands": {},
    "scope": "A_LOCAL_RUNTIME_CANDIDATE_CHECKS",
    "independent_auditors": 0,
}
for label, command in commands.items():
    start = time.monotonic()
    with (OUT / f"{label}.log").open("w") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    report["commands"][label] = {
        "argv": command,
        "exit_code": result.returncode,
        "seconds": time.monotonic() - start,
    }
    print(label, result.returncode, flush=True)
report["source_unchanged"] = hashes() == before
report["all_checks_passed"] = report["source_unchanged"] and all(
    v["exit_code"] == 0 for v in report["commands"].values()
)
(OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
raise SystemExit(0 if report["all_checks_passed"] else 1)
