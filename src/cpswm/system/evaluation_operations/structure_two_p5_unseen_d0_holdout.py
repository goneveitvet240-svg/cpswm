"""Repository-frozen internal unseen-D0 confirmation for corrected direct P5."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_dataset import enforce_project_two_replay_gate
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_evidence_versions import (
    current_evidence_context,
    require_execution_source,
    require_frozen_p5_inputs,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    _evaluate_posthoc_episode,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import P5ComparisonArm
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _learned_training_material,
    _pairwise_signal,
    _summaries,
    _validation_selection,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _load_config as _load_method_config,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import build_production_assembly_manifest

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-unseen-d0-holdout@0.1-internal"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_unseen_d0_holdout_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/evidence_entry_portability_2026_09_12/current_v0_4/"
    "structure_two_p5_unseen_d0_holdout_v0_4.json"
)
CLAIM_BOUNDARY: Final = (
    "This repository-frozen, previously unused D0 test-seed range can internally check "
    "whether the jointly repaired direct-P5 path generalizes beyond the opened development "
    "split under the frozen v0.1 matched three-arm rule. It is synthetic and not "
    "independently custodied; it cannot establish external validity, independent "
    "confirmation, scientific superiority, combined SEARCH/PUT_BACK utility, Task 7/8/9 "
    "completion, adaptive-router validity, or permission to narrow Structure Two."
)


REPLAY_CLAIM_BOUNDARY: Final = (
    "This is a post-open replay of the already recorded internal D0 holdout. "
    "It does not establish first use, unseen data, preregistration before execution, "
    "independent confirmation, external validity, scientific superiority, combined utility, "
    "Task 7/8/9 completion, adaptive-router validity, or ablation authorization."
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    custody = cast(Mapping[str, Any], config.get("holdout_custody"))
    if (
        config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status") != "FROZEN_BEFORE_HOLDOUT_OPEN"
        or config.get("choice") != "unseen_D0_holdout"
        or config.get("claim_boundary") != CLAIM_BOUNDARY
        or custody.get("test_seed_start") != 12001
        or custody.get("test_seed_count") != 60
        or custody.get("independent_custodian") is not False
        or custody.get("confirmatory") is not False
    ):
        raise ValueError("P5 unseen-D0 holdout configuration drifted")
    method_path = root / Path(str(config["method_source"]))
    readout_path = root / Path(
        str(cast(Mapping[str, Any], config["corrected_components"])["action_readout_source"])
    )
    if _file_sha256(method_path) != config.get("method_source_file_sha256"):
        raise ValueError("holdout method source drifted after freeze")
    if _file_sha256(readout_path) != cast(Mapping[str, Any], config["corrected_components"]).get(
        "action_readout_source_file_sha256"
    ):
        raise ValueError("holdout readout selection source drifted after freeze")
    return cast(dict[str, Any], config)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    require_execution_source(root)
    require_frozen_p5_inputs(root)
    corrected = cast(Mapping[str, Any], config["corrected_components"])
    paths = {
        "configuration": DEFAULT_CONFIG,
        "dataset_configuration": Path(str(config["dataset_source"])),
        "method_configuration": Path(str(config["method_source"])),
        "readout_selection": Path(str(corrected["action_readout_source"])),
        "execution_module": Path(__file__).resolve().relative_to(root),
        "posthoc_adapter": Path(
            "src/cpswm/system/evaluation_operations/structure_two_p5_readout_posthoc_diagnostic.py"
        ),
    }
    binding: dict[str, Any] = {
        name: {"path": path.as_posix(), "sha256": _file_sha256(root / path)}
        for name, path in paths.items()
    }
    binding["production_assembly_manifest_sha256"] = build_production_assembly_manifest(root)[
        "content_sha256"
    ]
    binding["execution_source"] = require_execution_source(root)
    return binding


def run_p5_unseen_d0_holdout(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    require_execution_source(root)
    require_frozen_p5_inputs(root)
    config = _load_config(root)
    method_config = _load_method_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(
        root / Path(str(config["dataset_source"]))
    )
    custody = cast(Mapping[str, Any], config["holdout_custody"])
    if (
        dataset_config.confirmatory
        or dataset_config.test_seed_start != custody["test_seed_start"]
        or dataset_config.test_seed_count != custody["test_seed_count"]
    ):
        raise ValueError("holdout dataset differs from the frozen internal custody declaration")
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    material = _learned_training_material(dataset)
    selection, learned_model, smoothing, amg_parameter = _validation_selection(
        dataset,
        method_config,
        material,
    )
    metrics: list[Any] = []
    diagnostics: list[dict[str, Any]] = []
    test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    for episode in test:
        episode_metrics, diagnostic = _evaluate_posthoc_episode(
            dataset,
            episode,
            learned_model=learned_model,
            material=material,
            learned_smoothing=smoothing,
            amg_parameter=amg_parameter,
        )
        metrics.extend(episode_metrics)
        diagnostics.append(diagnostic)
    summaries = _summaries(metrics)
    pairwise, signal = _pairwise_signal(metrics, method_config)
    p5_metrics = [item for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5]
    positive_count = sum(item.full_p5_transition_count for item in p5_metrics)
    negative_count = sum(item.negative_ciav_opceu_closure_count for item in p5_metrics)
    if positive_count + negative_count != sum(len(episode.steps) for episode in test):
        raise RuntimeError("corrected P5 closures do not cover the unseen holdout stream")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_context": current_evidence_context(),
        "protocol_id": PROTOCOL_ID,
        "status": (
            "INTERNAL_UNSEEN_D0_SIGNAL_DETECTED"
            if signal["p5_action_signal_detected"]
            else "INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED"
        ),
        "source_binding": _source_binding(root, config),
        "choice": config["choice"],
        "choice_rationale": config["choice_rationale"],
        "holdout_custody": config["holdout_custody"],
        "data_scope": {
            "dataset_version": dataset.manifest.dataset_version,
            "test_episode_count": len(test),
            "test_step_count": sum(len(episode.steps) for episode in test),
            "previously_unused_test_seed_range": False,
            "independent_custodian": False,
            "confirmatory": False,
        },
        "corrected_components": config["corrected_components"],
        "validation_only_selection": selection,
        "holdout_episode_metrics": [item.to_dict() for item in metrics],
        "holdout_arm_summaries": summaries,
        "paired_episode_results": pairwise,
        "signal_gate": signal,
        "readout_diagnostics": {
            "owner_habit_posterior_nonuniform_step_count": sum(
                int(item["owner_habit_posterior_nonuniform_step_count"]) for item in diagnostics
            ),
            "per_episode": diagnostics,
        },
        "execution_audit": {
            "corrected_direct_p5_full_transition_count": positive_count,
            "corrected_direct_p5_all_seven_primary_trace_count": sum(
                item.all_seven_primary_trace_count for item in p5_metrics
            ),
            "corrected_direct_p5_negative_ciav_opceu_closure_count": negative_count,
            "truth_visible_to_arms_before_typed_action_commit": False,
        },
        "scope_policy": config["scope_policy"],
        "combined_utility_evaluated": False,
        "independent_confirmation_established": False,
        "task_7_8_9_passed": False,
        "adaptive_router_validated": False,
        "external_validity_established": False,
        "claim_boundary": REPLAY_CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def verify_p5_unseen_d0_holdout(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    if payload.get("evidence_context") != current_evidence_context() and fresh_recompute:
        raise ValueError("current evidence lifecycle/version mismatch; use historical audit")
    if not fresh_recompute:
        raise ValueError("P5 unseen-D0 artifact verification requires fresh recomputation")
    root = repository_root.resolve()
    config = _load_config(root)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("protocol_id") != PROTOCOL_ID
        or payload.get("status")
        not in {
            "INTERNAL_UNSEEN_D0_SIGNAL_DETECTED",
            "INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED",
        }
        or payload.get("claim_boundary") != REPLAY_CLAIM_BOUNDARY
        or payload.get("content_sha256") != content_sha256(_unsigned(payload))
        or payload.get("source_binding") != _source_binding(root, config)
        or payload.get("independent_confirmation_established") is not False
    ):
        raise ValueError("P5 unseen-D0 result identity, hash, or binding drifted")
    expected = run_p5_unseen_d0_holdout(repository_root=root)
    if dict(payload) != expected:
        raise ValueError("fresh P5 unseen-D0 recomputation disagrees")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "run_p5_unseen_d0_holdout",
    "verify_p5_unseen_d0_holdout",
]
