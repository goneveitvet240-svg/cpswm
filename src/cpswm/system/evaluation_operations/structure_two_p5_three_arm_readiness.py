"""Fresh readiness inventory for the matched direct-P5 three-arm death test."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import audit_project_two_replay
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    decode_task_separated_actions,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
    TypedLocationPosterior,
)
from cpswm.system.evaluation_operations.structure_two_task8_online_compute import _LearnedModel
from cpswm.system.prototype_spine import CorePrototypeSpine
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-matched-three-arm-readiness@0.1"
STATUS: Final = "PROTOCOL_FROZEN_EXECUTION_BLOCKED"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_three_arm_readiness_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_three_arm_readiness_v0_1.json"
)
EXPECTED_BLOCKERS: Final = (
    "shared_ciav_scheduler_not_selected",
    "learned_two_stage_location_head_not_selected_or_implemented",
    "amg_distribution_adapter_not_implemented",
    "direct_p5_typed_location_adapter_not_implemented",
    "direct_p5_shared_ciav_packet_adapter_not_implemented",
    "learned_two_stage_ciav_consumer_not_implemented",
    "amg_ciav_consumer_not_implemented",
    "negative_observation_p5_closure_not_implemented",
)
CLAIM_BOUNDARY: Final = (
    "This fresh D0 readiness inventory binds the registered validation/test episodes, common "
    "typed-location contract, exact three-arm CIAV receipt contract, and currently missing "
    "adapters. It does not execute the three-arm death test, establish matched CIAV consumption, "
    "open confirmatory data, establish action benefit, pass Task 7/8/9, or narrow Structure Two."
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_readiness_config(root: Path) -> dict[str, Any]:
    payload = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version",
        "protocol_id",
        "status",
        "decision_source",
        "dataset_source",
        "evidence_level",
        "arms",
        "evaluation_splits",
        "typed_action_contract",
        "ciav_matching_contract",
        "unresolved_owner_choices",
        "current_known_blockers",
        "scope_policy",
        "claim_boundary",
    }
    if set(payload) != expected_keys:
        raise ValueError("P5 three-arm readiness configuration schema drifted")
    if (
        payload["schema_version"] != SCHEMA_VERSION
        or payload["protocol_id"] != "structure-two-p5-matched-three-arm@0.1-development"
        or payload["status"] != "INTERFACE_FREEZE_IN_PROGRESS_EXECUTION_BLOCKED"
        or payload["arms"] != [arm.value for arm in P5ComparisonArm]
        or tuple(payload["current_known_blockers"]) != EXPECTED_BLOCKERS
    ):
        raise ValueError("P5 three-arm readiness configuration identity drifted")
    choices = payload["unresolved_owner_choices"]
    if (
        not isinstance(choices, Mapping)
        or choices["shared_ciav_scheduler"]["selected"] is not None
        or choices["learned_two_stage_location_head"]["selected"] is not None
    ):
        raise ValueError("unresolved P5 method choices were silently selected")
    scope = payload["scope_policy"]
    if not isinstance(scope, Mapping) or scope["scope_reduction_authorized"] is not False:
        raise ValueError("P5 readiness configuration narrowed Structure Two")
    if not all(
        value is True for key, value in scope.items() if key != "scope_reduction_authorized"
    ):
        raise ValueError("P5 readiness configuration omitted a retained capability")
    return cast(dict[str, Any], payload)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        "readiness_config": DEFAULT_CONFIG,
        "decision_source": Path(config["decision_source"]),
        "dataset_source": Path(config["dataset_source"]),
        "contract_module": Path(
            "src/cpswm/system/evaluation_operations/structure_two_p5_three_arm_contract.py"
        ),
        "readiness_module": Path(__file__).resolve().relative_to(root),
        "direct_p5_module": Path("src/cpswm/system/structure_two_production_system.py"),
        "learned_two_stage_module": Path(
            "src/cpswm/system/evaluation_operations/structure_two_task8_online_compute.py"
        ),
        "amg_module": Path(
            "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py"
        ),
        "shared_decoder_module": Path(
            "src/cpswm/system/evaluation_operations/structure_two_action_utility_construct_gate.py"
        ),
    }
    return {
        name: {"path": path.as_posix(), "sha256": _file_sha256(root / path)}
        for name, path in paths.items()
    }


def _episode_manifest(dataset: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in dataset.episodes:
        if episode.split not in {
            ProjectTwoDatasetSplit.VALIDATION,
            ProjectTwoDatasetSplit.TEST,
        }:
            continue
        truth = dataset.truth_for(episode.episode_id)
        step_commitments = []
        eligible = 0
        negative = 0
        for step in episode.steps:
            direct_eligible = bool(
                step.before is not None
                and step.after is not None
                and step.observation_opportunity is not None
            )
            eligible += direct_eligible
            negative += not direct_eligible
            step_commitments.append(
                {
                    "step_id": str(step.step_id),
                    "visible_step_sha256": content_sha256(step),
                    "direct_p5_transition_eligible": direct_eligible,
                    "evaluator_truth_commitment_sha256": content_sha256(
                        truth.truth_by_step[step.step_id]
                    ),
                }
            )
        rows.append(
            {
                "episode_id": str(episode.episode_id),
                "split": episode.split.value,
                "visible_episode_sha256": content_sha256(episode),
                "evaluator_envelope_sha256": truth.evaluator_content_hash,
                "step_count": len(episode.steps),
                "direct_p5_transition_eligible_count": eligible,
                "negative_or_incomplete_observation_count": negative,
                "step_manifest_sha256": content_sha256(step_commitments),
            }
        )
    return rows


def _capability_inventory() -> dict[str, bool]:
    return {
        "direct_p5_evaluation_entrypoint": callable(
            getattr(
                StructureTwoProductionSystem,
                "process_evaluation_direct_p5_transition",
                None,
            )
        ),
        "direct_p5_native_putback_distribution": callable(
            getattr(CorePrototypeSpine, "action_location_distribution", None)
        ),
        "shared_typed_decoder": callable(decode_task_separated_actions),
        "typed_location_posterior_contract": inspect.isclass(TypedLocationPosterior),
        "direct_p5_typed_location_adapter": callable(
            getattr(StructureTwoProductionSystem, "emit_typed_location_posterior", None)
        ),
        "direct_p5_shared_ciav_packet_consumer": callable(
            getattr(StructureTwoProductionSystem, "consume_matched_ciav_packet", None)
        ),
        "learned_two_stage_location_posterior": callable(
            getattr(_LearnedModel, "predict_location_posteriors", None)
        ),
        "learned_two_stage_shared_ciav_packet_consumer": callable(
            getattr(_LearnedModel, "consume_matched_ciav_packet", None)
        ),
        "amg_location_posterior": callable(
            getattr(_AMGOpenWorldMethod, "predict_location_posteriors", None)
        ),
        "amg_shared_ciav_packet_consumer": callable(
            getattr(_AMGOpenWorldMethod, "consume_matched_ciav_packet", None)
        ),
        "negative_observation_direct_p5_closure": callable(
            getattr(
                StructureTwoProductionSystem,
                "process_evaluation_direct_p5_negative_observation",
                None,
            )
        ),
    }


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def run_p5_three_arm_readiness(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_readiness_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(root / config["dataset_source"])
    dataset = dataset_config.build_adapter().build()
    quality = audit_project_two_replay(dataset)
    if not quality.ready:
        raise ValueError("registered D0 dataset failed its replay quality gate")
    rows = _episode_manifest(dataset)
    split_counts = Counter(row["split"] for row in rows)
    capability = _capability_inventory()
    checks = {
        "dataset_quality_gate_passed": quality.ready,
        "validation_and_test_only": set(split_counts) == {"validation", "test"},
        "registered_episode_count_complete": len(rows)
        == dataset_config.validation_seed_count + dataset_config.test_seed_count,
        "common_typed_contract_available": capability["typed_location_posterior_contract"],
        "shared_decoder_available": capability["shared_typed_decoder"],
        "direct_p5_entrypoint_available": capability["direct_p5_evaluation_entrypoint"],
        "all_arm_location_adapters_available": all(
            capability[key]
            for key in (
                "direct_p5_typed_location_adapter",
                "learned_two_stage_location_posterior",
                "amg_location_posterior",
            )
        ),
        "all_arm_ciav_consumers_available": all(
            capability[key]
            for key in (
                "direct_p5_shared_ciav_packet_consumer",
                "learned_two_stage_shared_ciav_packet_consumer",
                "amg_shared_ciav_packet_consumer",
            )
        ),
        "negative_observation_closure_available": capability[
            "negative_observation_direct_p5_closure"
        ],
        "owner_choices_resolved": False,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": STATUS,
        "source_binding": _source_binding(root, config),
        "dataset": {
            "dataset_version": dataset.manifest.dataset_version,
            "confirmatory": dataset_config.confirmatory,
            "episode_count": len(rows),
            "step_count": sum(row["step_count"] for row in rows),
            "split_episode_counts": dict(sorted(split_counts.items())),
            "direct_p5_transition_eligible_count": sum(
                row["direct_p5_transition_eligible_count"] for row in rows
            ),
            "negative_or_incomplete_observation_count": sum(
                row["negative_or_incomplete_observation_count"] for row in rows
            ),
            "episode_manifest": rows,
        },
        "capability_inventory": capability,
        "readiness_checks": checks,
        "blocking_reasons": list(EXPECTED_BLOCKERS),
        "unresolved_owner_choices": config["unresolved_owner_choices"],
        "three_arm_execution_ready": all(checks.values()),
        "three_arm_execution_started": False,
        "cross_arm_ciav_matching_established": False,
        "action_benefit_established": False,
        "task_7_8_9_passed": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def verify_p5_three_arm_readiness(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    expected_keys = {
        "schema_version",
        "protocol_id",
        "status",
        "source_binding",
        "dataset",
        "capability_inventory",
        "readiness_checks",
        "blocking_reasons",
        "unresolved_owner_choices",
        "three_arm_execution_ready",
        "three_arm_execution_started",
        "cross_arm_ciav_matching_established",
        "action_benefit_established",
        "task_7_8_9_passed",
        "claim_boundary",
        "content_sha256",
    }
    if set(payload) != expected_keys:
        raise ValueError("P5 three-arm readiness artifact schema drifted")
    if (
        payload["schema_version"] != SCHEMA_VERSION
        or payload["protocol_id"] != PROTOCOL_ID
        or payload["status"] != STATUS
        or payload["claim_boundary"] != CLAIM_BOUNDARY
    ):
        raise ValueError("P5 three-arm readiness artifact identity drifted")
    for field in (
        "three_arm_execution_ready",
        "three_arm_execution_started",
        "cross_arm_ciav_matching_established",
        "action_benefit_established",
        "task_7_8_9_passed",
    ):
        if payload[field] is not False:
            raise ValueError("blocked P5 readiness artifact promoted an unauthorized claim")
    if tuple(payload["blocking_reasons"]) != EXPECTED_BLOCKERS:
        raise ValueError("P5 readiness blockers were omitted or reordered")
    if payload["content_sha256"] != content_sha256(_unsigned(payload)):
        raise ValueError("P5 three-arm readiness artifact hash mismatch")
    root = repository_root.resolve()
    config = _load_readiness_config(root)
    if payload["source_binding"] != _source_binding(root, config):
        raise ValueError("P5 three-arm readiness source binding mismatch")
    if fresh_recompute:
        expected = run_p5_three_arm_readiness(repository_root=root)
        if dict(payload) != expected:
            raise ValueError("fresh P5 three-arm readiness recomputation disagrees")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "run_p5_three_arm_readiness",
    "verify_p5_three_arm_readiness",
]
