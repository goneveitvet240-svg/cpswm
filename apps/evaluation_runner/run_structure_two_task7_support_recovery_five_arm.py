#!/usr/bin/env python3
"""Run the frozen Task-7 five-arm history-support recovery study."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_task7_support_recovery import (  # noqa: E402
    PROTOCOL_ID,
    Task7SupportRecoveryArm,
    run_task7_support_recovery_five_arm_study,
)

DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_task7_support_recovery_five_arm_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_task7_support_recovery_five_arm_v0_1.json"
)
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_task7_support_recovery.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("apps/evaluation_runner/run_structure_two_task7_support_recovery_five_arm.py"),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Task-7 five-arm protocol mismatch")
    if payload.get("status") != "AUDIT_REPAIRED_BEFORE_V0_2_EXECUTION":
        raise ValueError("Task-7 five-arm config is not the audit-repaired protocol")
    required = [arm.value for arm in Task7SupportRecoveryArm]
    if payload.get("required_arms") != required:
        raise ValueError("Task-7 five-arm attribution set changed")
    if payload.get("reservoir_budget") != payload.get("particle_budget"):
        raise ValueError("Task-7 reservoir budget must equal the particle budget")
    if payload.get("backward_message_descendants_per_reservoir_entry") != 1:
        raise ValueError("Task-7 backward-message branching changed")
    return payload


def run(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    absolute_config = REPOSITORY_ROOT / config_path
    config = load_config(absolute_config)
    control = config["v0_4_failure_control"]
    result = run_task7_support_recovery_five_arm_study(
        scenario_seeds=tuple(int(value) for value in config["scenario_seeds"]),
        replicate_seeds=tuple(int(value) for value in config["replicate_seeds"]),
        gaps=int(config["gaps"]),
        correction_index=int(config["correction_index"]),
        budget=int(config["particle_budget"]),
        v04_window_length=int(control["window_length"]),
        v04_sweeps=int(control["rejuvenation_sweeps"]),
    )
    thresholds = config["equivalence_gate"]
    approximate_arms = (
        Task7SupportRecoveryArm.RESERVOIR_ONLY,
        Task7SupportRecoveryArm.BACKWARD_MESSAGE_ONLY,
        Task7SupportRecoveryArm.COMBINED,
    )
    result["equivalence_gate"] = {
        "thresholds": thresholds,
        "arms": {
            arm.value: {
                "passed": (
                    result["summaries"][arm.value]["mean_max_belief_axis_tv"]
                    <= thresholds["maximum_mean_belief_axis_tv"]
                    and result["summaries"][arm.value]["mean_action_distribution_tv"]
                    <= thresholds["maximum_mean_action_distribution_tv"]
                    and result["summaries"][arm.value]["selected_action_match_rate"]
                    >= thresholds["minimum_selected_action_match_rate"]
                )
            }
            for arm in approximate_arms
        },
    }
    result["equivalence_gate"]["any_approximate_arm_passed"] = any(
        item["passed"] for item in result["equivalence_gate"]["arms"].values()
    )
    source_files = [
        {
            "path": path.as_posix(),
            "sha256": _sha256_bytes((REPOSITORY_ROOT / path).read_bytes()),
        }
        for path in (*SOURCE_PATHS, config_path)
    ]
    unsigned = {
        "artifact_protocol_id": "structure-two-task7-five-arm-artifact@0.1-development",
        "config": {
            "path": config_path.as_posix(),
            "sha256": _sha256_bytes(absolute_config.read_bytes()),
        },
        "source_files": source_files,
        "result": result,
        "claim_boundary": config["claim_boundary"],
    }
    return {
        **unsigned,
        "content_sha256": _sha256_bytes(_canonical_bytes(unsigned)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    artifact = run(args.config)
    output = REPOSITORY_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact["result"]["summaries"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
