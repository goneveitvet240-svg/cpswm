"""Fresh-world Structure-Two v0.4 Gate A.

Loading fails closed unless the train gate passed, an external custodian seed
attestation verifies under the user-approved trust anchor, and the manifest was
frozen before any validation metric was observed.  Gate A can permit Gate B;
it can never directly permit method comparison.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    ARM_PARAMETERS,
    DIAGNOSTIC_FAMILY,
    EXPECTED_ARMS,
    GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES,
    GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE,
    MAX_PHYSICAL_VERIFICATIONS_PER_ROLLOUT,
    SOURCE_BUNDLE_PROTOCOL,
    compute_producer_source_bundle,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    PROTOCOL_ID as ARM_ADAPTER_PROTOCOL,
)
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
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_4 import (
    load_seed_block_attestation,
    verify_seed_block_attestation,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-validation-gate-a@0.4"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4.json"
)
DEFAULT_OUTPUT = Path("benchmarks/structure_two/structure_two_world_validation_gate_a_v0_4.json")
DEFAULT_DRAFT = Path(
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenValidationGateDesign:
    manifest_path: Path
    manifest_sha256: str
    distribution: WorldDistributionConfig
    validation_world_seeds: tuple[int, ...]
    trajectory_seeds: tuple[int, ...]
    observation_seeds: tuple[int, ...]
    estimator: ShrunkEstimatorConfig
    thresholds: Mapping[str, float | int]
    train_artifact_path: Path
    train_artifact_content_sha256: str
    attestation_path: Path
    attestation_sha256: str


def verify_validation_manifest_against_train_evidence(
    payload: Mapping[str, Any],
    train_report: Mapping[str, Any],
    *,
    repository_root: Path,
) -> None:
    """Ensure the validation design is exactly the train-supported proposal."""

    train_design = load_rolling_train_gate_design(
        repository_root / DEFAULT_TRAIN_DESIGN,
        repository_root=repository_root,
    )
    train_info = payload["train_promotion_evidence"]
    if train_info.get("design_file_sha256") != train_design.design_sha256:
        raise ValueError("validation manifest names the wrong train design")
    if (
        train_report.get("train_design_frozen_before_run") is not False
        or train_report.get("train_evidence_confirmatory") is not False
    ):
        raise ValueError("train evidence must retain its retrospective disclosure")
    manifest_distribution = WorldDistributionConfig.from_manifest(payload["world_distribution"])
    if manifest_distribution != train_design.distribution:
        raise ValueError("validation world distribution differs from the train proposal")
    estimator = payload["rolling_visible_history_reference"]
    expected_estimator = train_report[
        "final_config_selected_on_all_train_worlds_for_future_validation"
    ]
    for key in (
        "window_days",
        "context_shrinkage_pseudocounts",
        "owner_probability_threshold",
    ):
        if estimator.get(key) != expected_estimator.get(key):
            raise ValueError(f"validation estimator differs from train selection: {key}")
    for key, value in payload["gate_a_thresholds"].items():
        if train_report["thresholds"].get(key) != value:
            raise ValueError(f"validation Gate A threshold differs from train design: {key}")
    gate_b = payload["gate_b_contract"]
    expected_arms = tuple(str(item) for item in gate_b["expected_arms"])
    if expected_arms != EXPECTED_ARMS:
        raise ValueError("validation Gate B arm order differs from the official adapter")
    if gate_b.get("arm_adapter_protocol") != ARM_ADAPTER_PROTOCOL:
        raise ValueError("validation Gate B names the wrong arm adapter")
    if gate_b.get("legacy_family_visible_transforms_applied") is not False:
        raise ValueError("v0.4 Gate B must not reapply legacy family perturbations")
    if gate_b.get("arm_parameters") != dict(ARM_PARAMETERS):
        raise ValueError("validation Gate B arm parameters differ from the adapter")
    expected_diagnostic_cost = json.loads(json.dumps(asdict(DIAGNOSTIC_FAMILY)))
    if gate_b.get("diagnostic_cost_configuration") != expected_diagnostic_cost:
        raise ValueError("validation Gate B diagnostic cost configuration mismatch")
    if (
        gate_b.get("max_physical_verifications_per_rollout")
        != MAX_PHYSICAL_VERIFICATIONS_PER_ROLLOUT
    ):
        raise ValueError("validation Gate B physical verification budget mismatch")
    if gate_b.get("excluded_report_only_arm") != "full_rerun_oracle":
        raise ValueError("validation Gate B oracle exclusion is not explicit")
    if gate_b.get("distinguishability_thresholds") != {
        "min_pairwise_prediction_disagreement_rate": (
            GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE
        ),
        "min_episode_fraction_with_multiple_arm_trajectories": (
            GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES
        ),
    }:
        raise ValueError("validation Gate B distinguishability thresholds mismatch")
    if gate_b.get("self_rehashed_unsigned_trace_never_authorizes") is not True or (
        gate_b.get("trace_attestation")
        != "every arm trace must be independently recomputed from the frozen source bundle "
        "in the custodian environment, match the supplied trace exactly, and carry an "
        "Ed25519 signature from the preregistered custodian key under "
        "cpswm.evaluation.structure_two.bound_arm_trace.v0.4"
    ):
        raise ValueError("validation Gate B lacks the frozen external trace signature")
    producer_hash = str(gate_b.get("producer_source_bundle_sha256", ""))
    if gate_b.get("producer_source_bundle_configured_before_custodian_signature") is not True or (
        len(producer_hash) != 64 or any(item not in "0123456789abcdef" for item in producer_hash)
    ):
        raise ValueError("validation Gate B producer source bundle is not preregistered")
    if gate_b.get("producer_source_bundle_protocol") != SOURCE_BUNDLE_PROTOCOL:
        raise ValueError("validation Gate B producer source bundle protocol mismatch")
    source_bundle = compute_producer_source_bundle(repository_root)
    if producer_hash != source_bundle.content_sha256:
        raise ValueError("current Gate B producer sources differ from the frozen bundle")
    if gate_b.get("producer_source_bundle_file_count") != len(source_bundle.files):
        raise ValueError("validation Gate B producer source file count mismatch")


def load_frozen_validation_gate_design(
    manifest_path: Path,
    *,
    repository_root: Path,
) -> FrozenValidationGateDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != "structure-two-world-generator-validation-gate@0.4":
        raise ValueError("validation manifest protocol mismatch")
    if payload.get("status") != "frozen-before-first-validation-run":
        raise ValueError("validation manifest is not frozen")
    policy = payload["execution_policy"]
    if policy.get("validation_gate_a_allowed") is not True:
        raise ValueError("frozen manifest does not authorise Gate A")
    if policy.get("gate_b_allowed") is not False:
        raise ValueError("Gate B must be forbidden before Gate A")
    if policy.get("method_comparison_allowed") is not False:
        raise ValueError("method comparison must be forbidden before both gates")
    if payload["freeze_record"].get("validation_metrics_observed_before_freeze") is not False:
        raise ValueError("manifest was not frozen before validation metrics")

    draft_path = repository_root / DEFAULT_DRAFT
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if payload["freeze_record"].get("draft_file_sha256") != _file_sha256(draft_path):
        raise ValueError("frozen manifest does not bind the current validation draft")
    mutable_freeze_fields = {
        "status",
        "custodian_attestation",
        "freeze_record",
        "execution_policy",
    }
    if set(payload) != set(draft) | {"freeze_record"}:
        raise ValueError("frozen manifest has unexpected or missing top-level fields")
    for key in set(draft) - mutable_freeze_fields:
        if payload.get(key) != draft.get(key):
            raise ValueError(f"frozen manifest changed preregistered field: {key}")
    authorization = draft["freeze_authorization"]
    if authorization.get("configured_before_custodian_signature") is not True:
        raise ValueError("validation draft lacks preregistered freeze authorization")
    if payload["freeze_record"].get("user_approval_id") != authorization.get("user_approval_id"):
        raise ValueError("frozen manifest user approval differs from the draft")

    split = payload["split_policy"]
    validation = tuple(
        int(item) for item in split["v0_4_validation_world_seeds_preregistered_not_generated"]
    )
    disclosed_spent = {
        *(int(item) for item in split["train_world_seeds_spent_for_tuning"]),
        *(int(item) for item in split["v0_2_validation_worlds_spent"]),
    }
    if set(validation) & disclosed_spent:
        raise ValueError("validation worlds overlap a disclosed spent split")

    train_info = payload["train_promotion_evidence"]
    train_path = repository_root / train_info["artifact"]
    train_report = verify_rolling_train_gate_report(
        train_path,
        repository_root=repository_root,
        recompute=True,
    )
    if not train_report["train_promotion_gate_passed"]:
        raise ValueError("train promotion gate did not pass")
    if train_report["content_sha256"] != train_info["artifact_content_sha256"]:
        raise ValueError("manifest points to the wrong train artifact content")
    if _file_sha256(train_path) != train_info["artifact_file_sha256"]:
        raise ValueError("manifest points to the wrong train artifact file")
    verify_validation_manifest_against_train_evidence(
        payload,
        train_report,
        repository_root=repository_root,
    )

    custody = payload["custodian_attestation"]
    if custody.get("verified") is not True:
        raise ValueError("custodian seed attestation was not verified")
    if custody.get("trusted_custodian_key_id") != authorization.get(
        "trusted_custodian_key_id"
    ) or custody.get("trusted_custodian_public_key_sha256") != authorization.get(
        "trusted_custodian_public_key_sha256"
    ):
        raise ValueError("frozen manifest trust anchor differs from the draft")
    attestation_path = repository_root / custody["artifact"]
    if _file_sha256(attestation_path) != custody["artifact_file_sha256"]:
        raise ValueError("custodian attestation file hash mismatch")
    record = load_seed_block_attestation(attestation_path)
    base_manifest = repository_root / payload["inheritance"]["base_v0_2_manifest"]
    verify_seed_block_attestation(
        record,
        draft_manifest_path=draft_path,
        base_manifest_path=base_manifest,
        expected_train_artifact_content_sha256=train_report["content_sha256"],
        expected_validation_world_seeds=validation,
        trusted_key_id=custody["trusted_custodian_key_id"],
        trusted_public_key_sha256=custody["trusted_custodian_public_key_sha256"],
    )

    estimator = payload["rolling_visible_history_reference"]
    return FrozenValidationGateDesign(
        manifest_path=manifest_path,
        manifest_sha256=_file_sha256(manifest_path),
        distribution=WorldDistributionConfig.from_manifest(payload["world_distribution"]),
        validation_world_seeds=validation,
        trajectory_seeds=tuple(int(item) for item in split["validation_trajectory_seeds"]),
        observation_seeds=tuple(int(item) for item in split["validation_observation_seeds"]),
        estimator=ShrunkEstimatorConfig(
            window_days=int(estimator["window_days"]),
            context_shrinkage_pseudocounts=float(estimator["context_shrinkage_pseudocounts"]),
            owner_probability_threshold=float(estimator["owner_probability_threshold"]),
        ),
        thresholds={
            key: int(value) if key == "bootstrap_draws" else float(value)
            for key, value in payload["gate_a_thresholds"].items()
        },
        train_artifact_path=train_path,
        train_artifact_content_sha256=train_report["content_sha256"],
        attestation_path=attestation_path,
        attestation_sha256=_file_sha256(attestation_path),
    )


def _mean_metrics(
    metrics: Mapping[int, Mapping[str, float]],
    seeds: Sequence[int],
) -> dict[str, float]:
    fields = tuple(next(iter(metrics.values())).keys())
    return {field: mean(metrics[seed][field] for seed in seeds) for field in fields}


def _bootstrap_ci(
    values: Sequence[float],
    *,
    draws: int,
    name: str,
) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{name}:world-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def run_structure_two_world_validation_gate_a_v0_4(
    *,
    repository_root: Path,
) -> dict[str, Any]:
    design = load_frozen_validation_gate_design(
        repository_root / DEFAULT_MANIFEST,
        repository_root=repository_root,
    )
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    worlds = [generator.sample_world(seed) for seed in design.validation_world_seeds]
    world_metrics: dict[int, dict[str, float]] = {}
    scored_rollouts: list[dict[str, Any]] = []
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
                    rollout,
                    world,
                    design.distribution,
                    design.estimator,
                )
                readings.append(reading)
                scored_rollouts.append(
                    {
                        "rollout_id": rollout.rollout_id,
                        "world_seed": world.world_seed,
                        "trajectory_seed": trajectory_seed,
                        "observation_seed": observation_seed,
                        "scored_step_count": reading.step_count,
                    }
                )
        world_metrics[world.world_seed] = _world_metric(readings)
    overall = _mean_metrics(world_metrics, design.validation_world_seeds)
    thresholds = design.thresholds
    draws = int(thresholds["bootstrap_draws"])
    put_gains = [
        world_metrics[seed]["put_back_visible_history_gain_over_sticky"]
        for seed in design.validation_world_seeds
    ]
    context_gains = [
        world_metrics[seed]["put_back_context_gain_over_pooled"]
        for seed in design.validation_world_seeds
    ]
    search_gains = [
        world_metrics[seed]["search_top1_gain"] for seed in design.validation_world_seeds
    ]
    put_ci = _bootstrap_ci(put_gains, draws=draws, name="put-back-visible-history-gain")
    context_ci = _bootstrap_ci(context_gains, draws=draws, name="put-back-context-gain")
    search_ci = _bootstrap_ci(search_gains, draws=draws, name="search-top1-gain")
    unique_fraction = len({world.world_hash for world in worlds}) / len(worlds)
    criteria = {
        "all_validation_worlds_are_structurally_unique": unique_fraction
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
    gate_passed = all(criteria.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "fresh validation-world Gate A; no method arm was run",
        "manifest_frozen_before_first_validation_run": True,
        "world_seed_count": len(worlds),
        "trajectory_count_per_world": len(design.trajectory_seeds),
        "observation_replicates_per_trajectory": len(design.observation_seeds),
        "rollout_count": (
            len(worlds) * len(design.trajectory_seeds) * len(design.observation_seeds)
        ),
        "validation_world_seeds": list(design.validation_world_seeds),
        "trajectory_seeds": list(design.trajectory_seeds),
        "observation_seeds": list(design.observation_seeds),
        "ordered_scored_rollouts": scored_rollouts,
        "frozen_estimator": {
            "window_days": design.estimator.window_days,
            "context_shrinkage_pseudocounts": (design.estimator.context_shrinkage_pseudocounts),
            "owner_probability_threshold": design.estimator.owner_probability_threshold,
        },
        "overall_world_weighted_metrics": overall,
        "put_back_visible_history_gain": {
            "mean": mean(put_gains),
            "world_bootstrap_ci_95": put_ci,
        },
        "put_back_context_gain": {
            "mean": mean(context_gains),
            "world_bootstrap_ci_95": context_ci,
        },
        "search_top1_gain": {
            "mean": mean(search_gains),
            "world_bootstrap_ci_95": search_ci,
        },
        "world_metrics": {str(seed): world_metrics[seed] for seed in design.validation_world_seeds},
        "thresholds": dict(thresholds),
        "criteria": criteria,
        "gate_a_passed": gate_passed,
        "gate_b_allowed": gate_passed,
        "gate_b_executed": False,
        "sealed_holdout_opened": False,
        "method_comparison_allowed": False,
        "provenance": {
            "manifest_sha256": design.manifest_sha256,
            "train_artifact_content_sha256": design.train_artifact_content_sha256,
            "seed_attestation_sha256": design.attestation_sha256,
            "generator_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
            ),
            "rolling_gate_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_rolling_gate_v0_4.py"
            ),
            "validation_gate_source_sha256": _file_sha256(Path(__file__).resolve()),
        },
        "limitations": [
            (
                "Gate A passing establishes target nontriviality and finite-sample "
                "recoverability, not method effectiveness."
            ),
            "Gate B must pass before any Structure-Two method comparison resumes.",
            "This remains a synthetic D0 benchmark without real-household external validity.",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_validation_gate_report(report: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_validation_gate_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = True,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("validation Gate A report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("validation Gate A protocol mismatch")
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("validation Gate A criteria missing")
    expected_pass = all(value is True for value in criteria.values())
    if report.get("gate_a_passed") != expected_pass:
        raise ValueError("validation Gate A decision mismatch")
    if report.get("gate_b_allowed") != expected_pass:
        raise ValueError("Gate B authorization mismatch")
    if report.get("method_comparison_allowed") is not False:
        raise ValueError("Gate A alone may not authorize method comparison")
    design = load_frozen_validation_gate_design(
        repository_root / DEFAULT_MANIFEST,
        repository_root=repository_root,
    )
    expected_provenance = {
        "manifest_sha256": design.manifest_sha256,
        "train_artifact_content_sha256": design.train_artifact_content_sha256,
        "seed_attestation_sha256": design.attestation_sha256,
        "generator_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
        ),
        "rolling_gate_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/structure_two_world_rolling_gate_v0_4.py"
        ),
        "validation_gate_source_sha256": _file_sha256(Path(__file__).resolve()),
    }
    if report.get("provenance") != expected_provenance:
        raise ValueError("validation Gate A provenance mismatch")
    if recompute:
        expected = run_structure_two_world_validation_gate_a_v0_4(repository_root=repository_root)
        if expected["content_sha256"] != stored_hash:
            raise ValueError("validation Gate A deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_DRAFT",
    "DEFAULT_MANIFEST",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "FrozenValidationGateDesign",
    "load_frozen_validation_gate_design",
    "run_structure_two_world_validation_gate_a_v0_4",
    "verify_validation_gate_report",
    "verify_validation_manifest_against_train_evidence",
    "write_validation_gate_report",
]
