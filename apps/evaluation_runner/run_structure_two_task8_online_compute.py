#!/usr/bin/env python3
"""Run and verify the frozen Task-8 learned online-compute pre-death test."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_task8_online_compute import (  # noqa: E402
    PROTOCOL_ID,
    content_sha256,
    run_task8_online_compute_study,
    verify_result,
)

DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_task8_online_compute_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_task8_online_compute_v0_1.json"
)
FROZEN_PREDECESSOR_CHECKPOINT: Final = "81e5015"
ARTIFACT_PROTOCOL_ID: Final = "structure-two-task8-online-compute-artifact@0.1-development"
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_task8_online_compute.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("apps/evaluation_runner/run_structure_two_task8_online_compute.py"),
    Path(
        "configs/project_two_experiments/structure_two_task7_task8_next_research_decision_v0_1.json"
    ),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("Task-8 frozen config must be a JSON object")
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Task-8 frozen protocol substitution")
    if payload.get("status") != "FROZEN_BEFORE_FIRST_EXECUTION":
        raise ValueError("Task-8 config was not frozen before execution")
    if payload.get("historical_task8_v0_4_status") != "IMMUTABLE_FAIL":
        raise ValueError("Task-8 historical v0.4 failure was rewritten")
    if payload.get("familywise_alpha") != 0.05:
        raise ValueError("Task-8 familywise alpha changed")
    if payload.get("primary_axis") != "online_compute":
        raise ValueError("Task-8 primary axis changed")
    if payload.get("secondary_axes") != [
        "distribution_shift",
        "information_restriction",
    ]:
        raise ValueError("Task-8 secondary axes changed")
    matching = payload.get("budget_matching")
    if not isinstance(matching, Mapping) or any(
        matching.get(field) is not expected
        for field, expected in {
            "same_training_data": True,
            "same_robot_visible_input": True,
            "same_active_parameter_count": True,
            "same_training_multiply_adds": True,
            "same_inference_multiply_adds": True,
            "same_action_readout": True,
            "truth_visible_to_arm": False,
        }.items()
    ):
        raise ValueError("Task-8 equal-budget contract changed")
    scope = payload.get("scope_policy")
    if (
        not isinstance(scope, Mapping)
        or len(scope) != 6
        or not all(value is True for value in scope.values())
    ):
        raise ValueError("Task-8 retained Structure-Two scope changed")
    return payload


def _study_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return run_task8_online_compute_study(
        gaps=int(config["gaps"]),
        training_seeds=tuple(int(value) for value in config["training_seeds"]),
        validation_seeds=tuple(int(value) for value in config["validation_seeds"]),
        confirmatory_seeds=tuple(int(value) for value in config["confirmatory_seeds"]),
        base_widths=tuple(int(value) for value in config["base_widths"]),
        learning_rates=tuple(float(value) for value in config["learning_rates"]),
        l2_values=tuple(float(value) for value in config["l2_values"]),
        minimum_relative_improvement=float(config["minimum_relative_improvement"]),
    )


def _source_files(config_path: Path) -> list[dict[str, str]]:
    paths = (*SOURCE_PATHS, config_path)
    return [
        {
            "path": path.as_posix(),
            "sha256": _sha256_bytes((REPOSITORY_ROOT / path).read_bytes()),
        }
        for path in paths
    ]


def run(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    absolute_config = REPOSITORY_ROOT / config_path
    config = load_config(absolute_config)
    result = _study_from_config(config)
    verify_result(result, config)
    source_files = _source_files(config_path)
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty_paths = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    unsigned = {
        "artifact_protocol_id": ARTIFACT_PROTOCOL_ID,
        "generated_on": "2026-09-07",
        "frozen_predecessor_checkpoint": FROZEN_PREDECESSOR_CHECKPOINT,
        "producer_git_head": git_head,
        "producer_worktree_dirty": bool(dirty_paths),
        "evidence_tier": "D0_DEVELOPMENT_PRE_DEATH_TEST_ONLY",
        "config": {
            "path": config_path.as_posix(),
            "sha256": _sha256_bytes(absolute_config.read_bytes()),
        },
        "source_files": source_files,
        "source_bundle_sha256": content_sha256(source_files),
        "result": result,
        "result_content_sha256": content_sha256(result),
        "positive_output_trust_chain": {
            "validation_selection_hash_checked": True,
            "per_arm_budget_maps_recomputed": True,
            "confirmatory_unit_coverage_recomputed": True,
            "action_costs_recomputed_from_probabilities_and_truth": True,
            "frontier_and_bootstrap_recomputed_from_cluster_rows": True,
            "forbidden_formal_transitions_fail_closed": True,
            "fresh_source_replay_required_for_verification": True,
            "independent_historical_custody_established": False,
        },
        "claim_boundary": config["claim_boundary"],
    }
    return {**unsigned, "content_sha256": content_sha256(unsigned)}


def verify_artifact(
    artifact: Mapping[str, Any],
    *,
    config_path: Path = DEFAULT_CONFIG,
    fresh_replay: bool = True,
) -> None:
    if artifact.get("artifact_protocol_id") != ARTIFACT_PROTOCOL_ID:
        raise ValueError("Task-8 artifact protocol substitution")
    unsigned = dict(artifact)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != content_sha256(unsigned):
        raise ValueError("Task-8 artifact content hash mismatch")
    config_binding = artifact.get("config")
    if not isinstance(config_binding, Mapping):
        raise ValueError("Task-8 config binding is missing")
    if config_binding.get("path") != config_path.as_posix():
        raise ValueError("Task-8 config path substitution")
    absolute_config = REPOSITORY_ROOT / config_path
    if config_binding.get("sha256") != _sha256_bytes(absolute_config.read_bytes()):
        raise ValueError("Task-8 frozen config content drift")
    config = load_config(absolute_config)
    expected_sources = _source_files(config_path)
    if artifact.get("source_files") != expected_sources:
        raise ValueError("Task-8 current source bundle drift")
    if artifact.get("source_bundle_sha256") != content_sha256(expected_sources):
        raise ValueError("Task-8 source-bundle hash mismatch")
    result = artifact.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("Task-8 result payload is missing")
    if artifact.get("result_content_sha256") != content_sha256(result):
        raise ValueError("Task-8 result hash mismatch")
    trust = artifact.get("positive_output_trust_chain")
    if not isinstance(trust, Mapping) or any(
        trust.get(field) is not True
        for field in (
            "validation_selection_hash_checked",
            "per_arm_budget_maps_recomputed",
            "confirmatory_unit_coverage_recomputed",
            "action_costs_recomputed_from_probabilities_and_truth",
            "frontier_and_bootstrap_recomputed_from_cluster_rows",
            "forbidden_formal_transitions_fail_closed",
            "fresh_source_replay_required_for_verification",
        )
    ):
        raise ValueError("Task-8 positive-output trust chain is incomplete")
    if trust.get("independent_historical_custody_established") is not False:
        raise ValueError("Task-8 local artifact cannot claim independent historical custody")
    verify_result(result, config)
    if fresh_replay:
        replayed = _study_from_config(config)
        if content_sha256(replayed) != content_sha256(result):
            raise ValueError("Task-8 fresh-source replay disagrees with the artifact")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        artifact = cast(
            dict[str, Any],
            json.loads(
                (REPOSITORY_ROOT / args.verify).read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            ),
        )
        verify_artifact(artifact, config_path=args.config, fresh_replay=True)
        print("Task-8 online-compute artifact verified with fresh-source replay")
        return
    artifact = run(args.config)
    verify_artifact(artifact, config_path=args.config, fresh_replay=True)
    output = REPOSITORY_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "fairness_gate_passed": artifact["result"]["fairness_gate_passed"],
        "any_strict_development_signal": artifact["result"]["any_strict_development_signal"],
        "next_disposition": artifact["result"]["next_disposition"],
        "frontier": artifact["result"]["primary_online_compute_frontier"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
