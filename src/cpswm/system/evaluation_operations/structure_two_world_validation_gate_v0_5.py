"""Fresh, externally attested Structure-Two v0.5 Gate A."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    ShrunkEstimatorConfig,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorldGeneratorV02,
    WorldDistributionConfig,
)
from cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4 import (
    DEFAULT_DESIGN as DEFAULT_TRAIN_DESIGN,
)
from cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4 import (
    _world_metric,
    evaluate_rolling_rollout,
    load_rolling_train_gate_design,
    verify_rolling_train_gate_report,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    compute_v0_5_source_bundle,
    load_fresh_seed_block_attestation,
    verify_fresh_seed_block_attestation,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-validation-gate-a@0.5"
DEFAULT_DRAFT = Path(
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
)
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
)
DEFAULT_OUTPUT = Path("benchmarks/structure_two/structure_two_world_validation_gate_a_v0_5.json")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenValidationGateDesignV05:
    manifest_sha256: str
    distribution: WorldDistributionConfig
    validation_world_seeds: tuple[int, ...]
    trajectory_seeds: tuple[int, ...]
    observation_seeds: tuple[int, ...]
    estimator: ShrunkEstimatorConfig
    thresholds: Mapping[str, float | int]
    train_artifact_content_sha256: str
    attestation_sha256: str


def load_frozen_validation_gate_design_v0_5(
    manifest_path: Path, *, repository_root: Path
) -> FrozenValidationGateDesignV05:
    if not manifest_path.is_file():
        raise ValueError(
            "v0.5 frozen manifest is missing; external public-key enrollment and fresh "
            "seed-block attestation must complete before Gate A"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != "structure-two-world-generator-validation-gate@0.5":
        raise ValueError("v0.5 validation manifest protocol mismatch")
    if payload.get("status") != "frozen-before-first-v0.5-validation-run":
        raise ValueError("v0.5 validation manifest is not frozen")
    policy = payload["execution_policy"]
    if policy.get("validation_gate_a_allowed") is not True:
        raise ValueError("v0.5 frozen manifest does not authorize Gate A")
    if policy.get("gate_b_allowed") is not False:
        raise ValueError("v0.5 Gate B must remain closed before Gate A")
    if policy.get("official_method_comparison_allowed") is not False:
        raise ValueError("v0.5 freeze cannot authorize official-method comparison")

    draft_path = repository_root / DEFAULT_DRAFT
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if payload["freeze_record"]["draft_file_sha256"] != _file_sha256(draft_path):
        raise ValueError("v0.5 frozen manifest does not bind the current draft")
    if payload["freeze_record"]["validation_metrics_observed_before_freeze"] is not False:
        raise ValueError("v0.5 was not frozen before validation metrics")
    frozen_compare = json.loads(json.dumps(payload))
    draft_compare = json.loads(json.dumps(draft))
    for item in (frozen_compare, draft_compare):
        item.pop("status", None)
        item.pop("custodian_attestation", None)
        item.pop("execution_policy", None)
        item.pop("freeze_record", None)
    frozen_compare["split_policy"]["sealed_holdout_world_seed_commitments"] = []
    if frozen_compare != draft_compare:
        raise ValueError("v0.5 frozen manifest changed preregistered public design")

    source = compute_v0_5_source_bundle(repository_root)
    gate_b = payload["gate_b_contract"]
    if gate_b["producer_source_bundle_sha256"] != source.content_sha256:
        raise ValueError("v0.5 current source differs from the frozen source bundle")
    if gate_b["producer_source_bundle_file_count"] != len(source.files):
        raise ValueError("v0.5 source bundle file-count mismatch")

    split = payload["split_policy"]
    validation = tuple(
        int(item) for item in split["v0_5_validation_world_seeds_preregistered_not_generated"]
    )
    spent = {
        *(int(item) for item in split["train_world_seeds_spent_for_tuning"]),
        *(int(item) for item in split["prior_validation_world_seeds_spent"]),
    }
    if not validation or len(set(validation)) != len(validation) or set(validation) & spent:
        raise ValueError("v0.5 validation seeds are empty, duplicated, or spent")

    inheritance = payload["inheritance"]
    train_path = repository_root / inheritance["train_artifact"]
    train = verify_rolling_train_gate_report(
        train_path, repository_root=repository_root, recompute=True
    )
    if train["content_sha256"] != inheritance["train_artifact_content_sha256"]:
        raise ValueError("v0.5 points to the wrong train artifact content")
    if _file_sha256(train_path) != inheritance["train_artifact_file_sha256"]:
        raise ValueError("v0.5 points to the wrong train artifact file")
    train_design = load_rolling_train_gate_design(
        repository_root / DEFAULT_TRAIN_DESIGN, repository_root=repository_root
    )
    distribution = WorldDistributionConfig.from_manifest(payload["world_distribution"])
    if distribution != train_design.distribution:
        raise ValueError("v0.5 distribution differs from train-only selection")
    selected = train["final_config_selected_on_all_train_worlds_for_future_validation"]
    estimator_payload = payload["rolling_visible_history_reference"]
    for key in (
        "window_days",
        "context_shrinkage_pseudocounts",
        "owner_probability_threshold",
    ):
        if estimator_payload[key] != selected[key]:
            raise ValueError(f"v0.5 estimator differs from train selection: {key}")
    for key, value in payload["gate_a_thresholds"].items():
        if train["thresholds"][key] != value:
            raise ValueError(f"v0.5 Gate A threshold differs from train design: {key}")

    custody = payload["custodian_attestation"]
    if custody.get("verified") is not True:
        raise ValueError("v0.5 fresh seed attestation is not verified")
    attestation_path = repository_root / custody["artifact"]
    if _file_sha256(attestation_path) != custody["artifact_file_sha256"]:
        raise ValueError("v0.5 fresh seed attestation file hash mismatch")
    record = load_fresh_seed_block_attestation(attestation_path)
    verify_fresh_seed_block_attestation(
        record,
        draft_manifest_path=draft_path,
        expected_train_artifact_content_sha256=train["content_sha256"],
    )
    if tuple(split["sealed_holdout_world_seed_commitments"]) != (record.holdout_seed_commitments):
        raise ValueError("v0.5 frozen commitments differ from the signed seed block")

    return FrozenValidationGateDesignV05(
        manifest_sha256=_file_sha256(manifest_path),
        distribution=distribution,
        validation_world_seeds=validation,
        trajectory_seeds=tuple(int(x) for x in split["validation_trajectory_seeds"]),
        observation_seeds=tuple(int(x) for x in split["validation_observation_seeds"]),
        estimator=ShrunkEstimatorConfig(
            window_days=int(estimator_payload["window_days"]),
            context_shrinkage_pseudocounts=float(
                estimator_payload["context_shrinkage_pseudocounts"]
            ),
            owner_probability_threshold=float(estimator_payload["owner_probability_threshold"]),
        ),
        thresholds={
            key: int(value) if key == "bootstrap_draws" else float(value)
            for key, value in payload["gate_a_thresholds"].items()
        },
        train_artifact_content_sha256=train["content_sha256"],
        attestation_sha256=_file_sha256(attestation_path),
    )


def _bootstrap_ci(values: Sequence[float], *, draws: int, name: str) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{name}:world-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def run_structure_two_world_validation_gate_a_v0_5(*, repository_root: Path) -> dict[str, Any]:
    design = load_frozen_validation_gate_design_v0_5(
        repository_root / DEFAULT_MANIFEST, repository_root=repository_root
    )
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    worlds = [generator.sample_world(seed) for seed in design.validation_world_seeds]
    world_metrics: dict[int, dict[str, float]] = {}
    rollouts: list[dict[str, Any]] = []
    for world in worlds:
        readings = []
        for trajectory_seed in design.trajectory_seeds:
            for observation_seed in design.observation_seeds:
                rollout = generator.generate_rollout(
                    world,
                    trajectory_seed=trajectory_seed,
                    observation_seed=observation_seed,
                )
                reading = evaluate_rolling_rollout(
                    rollout, world, design.distribution, design.estimator
                )
                readings.append(reading)
                rollouts.append(
                    {
                        "rollout_id": rollout.rollout_id,
                        "world_seed": world.world_seed,
                        "trajectory_seed": trajectory_seed,
                        "observation_seed": observation_seed,
                        "scored_step_count": reading.step_count,
                    }
                )
        world_metrics[world.world_seed] = _world_metric(readings)
    fields = tuple(next(iter(world_metrics.values())))
    overall = {
        field: mean(world_metrics[seed][field] for seed in design.validation_world_seeds)
        for field in fields
    }
    thresholds = design.thresholds
    put = [
        world_metrics[s]["put_back_visible_history_gain_over_sticky"]
        for s in design.validation_world_seeds
    ]
    context = [
        world_metrics[s]["put_back_context_gain_over_pooled"] for s in design.validation_world_seeds
    ]
    search = [world_metrics[s]["search_top1_gain"] for s in design.validation_world_seeds]
    put_ci = _bootstrap_ci(put, draws=int(thresholds["bootstrap_draws"]), name="put")
    criteria = {
        "all_validation_worlds_are_structurally_unique": len({world.world_hash for world in worlds})
        / len(worlds)
        >= float(thresholds["minimum_unique_validation_world_fraction"]),
        "put_back_sticky_rule_leaves_headroom": overall["put_back_sticky_error"]
        >= float(thresholds["minimum_put_back_sticky_error"]),
        "put_back_visible_history_beats_sticky": overall[
            "put_back_visible_history_gain_over_sticky"
        ]
        >= float(thresholds["minimum_put_back_aggregation_gain"]),
        "put_back_visible_history_gain_is_world_robust": put_ci[0]
        >= float(thresholds["minimum_put_back_aggregation_gain_ci_lower"]),
        "put_back_context_is_action_relevant": overall["put_back_context_gain_over_pooled"]
        >= float(thresholds["minimum_put_back_context_gain"]),
        "put_back_retains_method_headroom": overall["put_back_visible_history_error"]
        >= float(thresholds["minimum_remaining_put_back_error"]),
        "owner_observation_is_not_the_habit_target": overall["on_owner_observed_target_match_rate"]
        <= float(thresholds["maximum_on_owner_observed_target_recurrence"]),
        "search_last_observed_rule_leaves_headroom": overall["search_last_observed_error"]
        >= float(thresholds["minimum_search_last_observed_error"]),
        "search_visible_history_beats_last_observed": overall["search_top1_gain"]
        >= float(thresholds["minimum_search_contextual_fallback_gain"]),
        "search_retains_method_headroom": overall["search_visible_history_error"]
        >= float(thresholds["minimum_remaining_search_error"]),
        "unobserved_location_dynamics_are_nontrivial": overall["unobserved_location_change_rate"]
        >= float(thresholds["minimum_unobserved_location_change_rate"]),
    }
    passed = all(criteria.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "fresh externally attested v0.5 Gate A; no method arm run",
        "ordered_scored_rollouts": rollouts,
        "overall_world_weighted_metrics": overall,
        "world_metrics": {str(k): v for k, v in world_metrics.items()},
        "put_back_visible_history_gain_ci_95": put_ci,
        "put_back_context_gain_ci_95": _bootstrap_ci(
            context, draws=int(thresholds["bootstrap_draws"]), name="context"
        ),
        "search_top1_gain_ci_95": _bootstrap_ci(
            search, draws=int(thresholds["bootstrap_draws"]), name="search"
        ),
        "criteria": criteria,
        "gate_a_passed": passed,
        "gate_b_allowed": passed,
        "method_comparison_allowed": False,
        "sealed_holdout_opened": False,
        "provenance": {
            "manifest_sha256": design.manifest_sha256,
            "train_artifact_content_sha256": design.train_artifact_content_sha256,
            "seed_attestation_sha256": design.attestation_sha256,
            "validation_gate_source_sha256": _file_sha256(Path(__file__).resolve()),
        },
    }
    report["content_sha256"] = content_sha256(report)
    return report


def verify_validation_gate_report_v0_5(
    report_path: Path, *, repository_root: Path, recompute: bool = True
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("v0.5 Gate A content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("v0.5 Gate A protocol mismatch")
    expected = all(value is True for value in report.get("criteria", {}).values())
    if report.get("gate_a_passed") is not expected or report.get("gate_b_allowed") is not expected:
        raise ValueError("v0.5 Gate A authorization mismatch")
    if report.get("method_comparison_allowed") is not False:
        raise ValueError("v0.5 Gate A alone cannot authorize method comparison")
    if recompute:
        rerun = run_structure_two_world_validation_gate_a_v0_5(repository_root=repository_root)
        if rerun["content_sha256"] != stored:
            raise ValueError("v0.5 Gate A deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_DRAFT",
    "DEFAULT_MANIFEST",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "FrozenValidationGateDesignV05",
    "load_frozen_validation_gate_design_v0_5",
    "run_structure_two_world_validation_gate_a_v0_5",
    "verify_validation_gate_report_v0_5",
]
