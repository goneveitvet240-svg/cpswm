"""Structure-Two v0.4 train outer-CV gate with a plain rolling estimator.

This protocol deliberately removes every TV/CUSUM/change-detector reading from
the binding path.  The old detector implementation, frozen probe design, and
failed artifact remain intact under their v0.3 names.  The only finite-sample
reference here is an executable window + context-shrinkage count estimator that
reads visible history.

The train result is retrospective train-only development evidence for drafting
a *new* validation manifest.  Its exact design was written after exploratory
probes and must never be called preregistered or confirmatory.  It never
authorises method comparison and never generates validation or sealed holdout
worlds.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_2 import (
    load_frozen_world_gate_design,
)
from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    ShrunkEstimatorConfig,
    _argmax,
    _normalised_path_cost,
    _ranked,
    _RollingEstimator,
    analytic_world_unobserved_error,
    encounter_order,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    IntegerRangeSpec,
    StructureTwoWorld,
    StructureTwoWorldGeneratorV02,
    StructureTwoWorldRollout,
    WorldDistributionConfig,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-rolling-train-gate@0.4"
DEFAULT_DESIGN = Path(
    "configs/project_two_experiments/structure_two_world_rolling_train_gate_v0_4.json"
)
DEFAULT_OUTPUT = Path("benchmarks/structure_two/structure_two_world_rolling_train_gate_v0_4.json")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class RollingTrainGateDesign:
    design_path: Path
    design_sha256: str
    base_manifest: Path
    base_manifest_sha256: str
    distribution: WorldDistributionConfig
    duration_days: tuple[int, int]
    world_seeds: tuple[int, ...]
    trajectory_seeds: tuple[int, ...]
    observation_seeds: tuple[int, ...]
    folds: tuple[tuple[int, ...], ...]
    windows: tuple[int, ...]
    shrinkages: tuple[float, ...]
    owner_probability_thresholds: tuple[float, ...]
    minimum_mean_search_gain: float
    minimum_worst_fold_search_gain: float
    v0_2_thresholds: Mapping[str, float | int]
    validation_world_seed_candidates: tuple[int, ...]
    validation_trajectory_seeds: tuple[int, ...]
    validation_observation_seeds: tuple[int, ...]

    def candidates(self) -> tuple[ShrunkEstimatorConfig, ...]:
        return tuple(
            ShrunkEstimatorConfig(
                window_days=int(window),
                context_shrinkage_pseudocounts=float(shrinkage),
                owner_probability_threshold=float(threshold),
            )
            for window, shrinkage, threshold in itertools.product(
                self.windows,
                self.shrinkages,
                self.owner_probability_thresholds,
            )
        )


def load_rolling_train_gate_design(
    path: Path,
    *,
    repository_root: Path,
) -> RollingTrainGateDesign:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("rolling train-gate protocol mismatch")
    if payload.get("status") != "retrospective-train-design-after-exploratory-probes":
        raise ValueError("rolling train-gate retrospective-design status mismatch")

    base_manifest = repository_root / str(payload["base_manifest"])
    base_hash = _file_sha256(base_manifest)
    if base_hash != payload.get("base_manifest_sha256"):
        raise ValueError("base v0.2 manifest hash mismatch")
    base = load_frozen_world_gate_design(base_manifest)

    sampling = payload["train_sampling"]
    worlds = tuple(int(item) for item in sampling["world_seeds"])
    if worlds != base.train_world_seeds:
        raise ValueError("train worlds must equal the frozen v0.2 train split exactly")
    folds = tuple(tuple(int(item) for item in fold) for fold in payload["outer_world_folds"])
    flattened = tuple(item for fold in folds for item in fold)
    if len(set(flattened)) != len(flattened) or set(flattened) != set(worlds):
        raise ValueError("outer folds must cover every train world exactly once")
    if len(folds) < 2 or any(not fold for fold in folds):
        raise ValueError("outer CV requires at least two nonempty world folds")

    grid = payload["rolling_estimator_grid"]
    candidate_count = (
        len(grid["window_days"])
        * len(grid["context_shrinkage_pseudocounts"])
        * len(grid["owner_probability_threshold"])
    )
    if candidate_count != int(grid["cartesian_candidate_count"]):
        raise ValueError("rolling-estimator grid size mismatch")

    legacy = payload["legacy_detector_status"]
    archived_source = repository_root / str(legacy["archived_exact_gate_source"])
    if _file_sha256(archived_source) != legacy["archived_exact_gate_source_sha256"]:
        raise ValueError("archived v0.3 gate source hash mismatch")
    failed_artifact = repository_root / str(legacy["preserved_failed_artifact"])
    if _file_sha256(failed_artifact) != legacy["preserved_failed_artifact_file_sha256"]:
        raise ValueError("preserved v0.3 failed-artifact hash mismatch")

    duration = tuple(
        int(item) for item in payload["world_change_under_test"]["duration_days_inclusive"]
    )
    if len(duration) != 2 or duration[0] > duration[1]:
        raise ValueError("invalid duration range")
    long_distribution = replace(
        base.distribution,
        duration_days=IntegerRangeSpec(duration[0], duration[1]),
    )
    requirements = payload["promotion_requirements"]
    downstream = payload["downstream_prereservation_not_authorized_for_use"]
    validation_candidates = tuple(
        int(item) for item in downstream["validation_world_seed_candidates"]
    )
    if set(validation_candidates) & (set(worlds) | set(base.validation_world_seeds)):
        raise ValueError("candidate validation worlds overlap a disclosed spent split")

    return RollingTrainGateDesign(
        design_path=path,
        design_sha256=_file_sha256(path),
        base_manifest=base_manifest,
        base_manifest_sha256=base_hash,
        distribution=long_distribution,
        duration_days=(duration[0], duration[1]),
        world_seeds=worlds,
        trajectory_seeds=tuple(int(item) for item in sampling["trajectory_seeds"]),
        observation_seeds=tuple(int(item) for item in sampling["observation_seeds"]),
        folds=folds,
        windows=tuple(int(item) for item in grid["window_days"]),
        shrinkages=tuple(float(item) for item in grid["context_shrinkage_pseudocounts"]),
        owner_probability_thresholds=tuple(
            float(item) for item in grid["owner_probability_threshold"]
        ),
        minimum_mean_search_gain=float(
            requirements["minimum_outer_cv_world_weighted_mean_search_top1_gain"]
        ),
        minimum_worst_fold_search_gain=float(
            requirements["minimum_outer_cv_worst_held_out_fold_search_top1_gain"]
        ),
        v0_2_thresholds=base.thresholds,
        validation_world_seed_candidates=validation_candidates,
        validation_trajectory_seeds=tuple(
            int(item) for item in downstream["validation_trajectory_seeds"]
        ),
        validation_observation_seeds=tuple(
            int(item) for item in downstream["validation_observation_seeds"]
        ),
    )


@dataclass(frozen=True, slots=True)
class RollingRolloutReading:
    world_seed: int
    rollout_id: str
    step_count: int
    put_back_sticky_error: float
    put_back_pooled_error: float
    put_back_visible_history_error: float
    search_last_observed_error: float
    search_visible_history_error: float
    search_last_observed_normalised_path_cost: float
    search_visible_history_normalised_path_cost: float
    on_owner_observed_target_match_rate: float
    unobserved_location_change_rate: float
    admitted_weekday_count: int
    admitted_weekend_count: int
    unobserved_weekday_prediction_count: int
    unobserved_weekend_prediction_count: int
    active_weekday_context_sample_sum: int
    active_weekend_context_sample_sum: int
    active_weekday_effective_mass_sum: float
    active_weekend_effective_mass_sum: float
    analytic_world_unobserved_error: float


def _visible_encounters(rollout: StructureTwoWorldRollout) -> tuple[str, ...]:
    return tuple(
        step.observed_location
        for step in rollout.steps
        if step.observed and step.observed_location is not None
    )


def evaluate_rolling_rollout(
    rollout: StructureTwoWorldRollout,
    world: StructureTwoWorld,
    distribution: WorldDistributionConfig,
    estimator_config: ShrunkEstimatorConfig,
    *,
    tie_break_scope: str = "complete_rollout",
) -> RollingRolloutReading:
    """Evaluate one executable visible-history reference without a detector."""

    locations = tuple(rollout.locations)
    if tie_break_scope not in {"complete_rollout", "causal_prefix"}:
        raise ValueError("unknown encounter-order tie-break scope")
    causal_encounters: list[str] = []
    positions = encounter_order(
        locations,
        _visible_encounters(rollout) if tie_break_scope == "complete_rollout" else (),
    )
    fallback = min(locations, key=positions.__getitem__)
    rolling = _RollingEstimator(fallback, estimator_config)
    last_observed = fallback
    cumulative_observed_counts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    path: Counter[str] = Counter()
    admitted: Counter[str] = Counter()
    unobserved_predictions: Counter[str] = Counter()
    active_samples: Counter[str] = Counter()
    active_mass: Counter[str] = Counter()
    owner_observed_matches = owner_observed_total = 0
    unobserved_changes = unobserved_total = 0
    previous_true_location: str | None = None

    for step in rollout.steps:
        rolling.advance(step)
        visible_now = step.observed and step.observed_location is not None
        if visible_now:
            assert step.observed_location is not None
            if tie_break_scope == "causal_prefix":
                causal_encounters.append(step.observed_location)
            last_observed = step.observed_location
            cumulative_observed_counts[step.observed_location] += 1
            if rolling.admit(step):
                admitted[step.context] += 1
                rolling.observe(step, step.observed_location)
        if tie_break_scope == "causal_prefix":
            positions = encounter_order(locations, causal_encounters)

        pooled_scores = (
            {item: float(count) for item, count in rolling.pooled.items()}
            if rolling.pooled
            else {rolling.sticky: 1.0}
        )
        context_scores = rolling.scores(step.context)
        pooled_mode = _argmax(pooled_scores, positions)
        context_mode = _argmax(context_scores, positions)
        head = step.observed_location if visible_now else None
        last_order = _ranked(
            {item: float(cumulative_observed_counts.get(item, 0)) for item in locations},
            locations,
            head or last_observed,
            positions,
        )
        rolling_order = _ranked(
            context_scores,
            locations,
            head or context_mode,
            positions,
        )

        errors["put_sticky"] += rolling.sticky != step.true_owner_habit_location
        errors["put_pooled"] += pooled_mode != step.true_owner_habit_location
        errors["put_context"] += context_mode != step.true_owner_habit_location
        errors["search_last"] += last_order[0] != step.true_location
        errors["search_context"] += rolling_order[0] != step.true_location
        path["last"] += _normalised_path_cost(last_order, step.true_location, len(locations))
        path["context"] += _normalised_path_cost(rolling_order, step.true_location, len(locations))

        if step.true_actor == rollout.owner_actor and step.observed:
            owner_observed_total += 1
            owner_observed_matches += step.observed_location == step.true_owner_habit_location
        if not step.observed:
            unobserved_predictions[step.context] += 1
            cell_count = sum(rolling.by_context[step.context].values())
            active_samples[step.context] += cell_count
            active_mass[step.context] += cell_count + (
                estimator_config.context_shrinkage_pseudocounts if rolling.pooled else 0.0
            )
            if previous_true_location is not None:
                unobserved_total += 1
                unobserved_changes += step.true_location != previous_true_location
        previous_true_location = step.true_location

    total = len(rollout.steps)
    return RollingRolloutReading(
        world_seed=rollout.world_seed,
        rollout_id=rollout.rollout_id,
        step_count=total,
        put_back_sticky_error=errors["put_sticky"] / total,
        put_back_pooled_error=errors["put_pooled"] / total,
        put_back_visible_history_error=errors["put_context"] / total,
        search_last_observed_error=errors["search_last"] / total,
        search_visible_history_error=errors["search_context"] / total,
        search_last_observed_normalised_path_cost=path["last"] / total,
        search_visible_history_normalised_path_cost=path["context"] / total,
        on_owner_observed_target_match_rate=(
            owner_observed_matches / owner_observed_total if owner_observed_total else 0.0
        ),
        unobserved_location_change_rate=(
            unobserved_changes / unobserved_total if unobserved_total else 0.0
        ),
        admitted_weekday_count=admitted["weekday"],
        admitted_weekend_count=admitted["weekend"],
        unobserved_weekday_prediction_count=unobserved_predictions["weekday"],
        unobserved_weekend_prediction_count=unobserved_predictions["weekend"],
        active_weekday_context_sample_sum=active_samples["weekday"],
        active_weekend_context_sample_sum=active_samples["weekend"],
        active_weekday_effective_mass_sum=active_mass["weekday"],
        active_weekend_effective_mass_sum=active_mass["weekend"],
        analytic_world_unobserved_error=analytic_world_unobserved_error(world, distribution),
    )


_ERROR_FIELDS = (
    "put_back_sticky_error",
    "put_back_pooled_error",
    "put_back_visible_history_error",
    "search_last_observed_error",
    "search_visible_history_error",
    "search_last_observed_normalised_path_cost",
    "search_visible_history_normalised_path_cost",
    "on_owner_observed_target_match_rate",
    "unobserved_location_change_rate",
    "analytic_world_unobserved_error",
)


def _world_metric(readings: Sequence[RollingRolloutReading]) -> dict[str, float]:
    result = {
        field: mean(float(getattr(item, field)) for item in readings) for field in _ERROR_FIELDS
    }
    result["put_back_visible_history_gain_over_sticky"] = (
        result["put_back_sticky_error"] - result["put_back_visible_history_error"]
    )
    result["put_back_context_gain_over_pooled"] = (
        result["put_back_pooled_error"] - result["put_back_visible_history_error"]
    )
    result["search_top1_gain"] = (
        result["search_last_observed_error"] - result["search_visible_history_error"]
    )
    result["search_normalised_path_cost_gain"] = (
        result["search_last_observed_normalised_path_cost"]
        - result["search_visible_history_normalised_path_cost"]
    )
    for context in ("weekday", "weekend"):
        prediction_count = sum(
            getattr(item, f"unobserved_{context}_prediction_count") for item in readings
        )
        result[f"admitted_{context}_count_per_rollout"] = mean(
            float(getattr(item, f"admitted_{context}_count")) for item in readings
        )
        result[f"active_{context}_context_samples_per_unobserved_prediction"] = (
            sum(getattr(item, f"active_{context}_context_sample_sum") for item in readings)
            / prediction_count
            if prediction_count
            else 0.0
        )
        result[f"active_{context}_effective_mass_per_unobserved_prediction"] = (
            sum(getattr(item, f"active_{context}_effective_mass_sum") for item in readings)
            / prediction_count
            if prediction_count
            else 0.0
        )
    return result


def _mean_metrics(
    metrics: Mapping[int, Mapping[str, float]],
    seeds: Sequence[int],
) -> dict[str, float]:
    fields = tuple(next(iter(metrics.values())).keys())
    return {field: mean(float(metrics[seed][field]) for seed in seeds) for field in fields}


def _config_payload(config: ShrunkEstimatorConfig) -> dict[str, float | int]:
    return asdict(config)


def _config_id(config: ShrunkEstimatorConfig) -> str:
    return (
        f"window={config.window_days};"
        f"shrinkage={config.context_shrinkage_pseudocounts:g};"
        f"owner_threshold={config.owner_probability_threshold:g}"
    )


def _select_config(
    candidates: Sequence[ShrunkEstimatorConfig],
    candidate_world_metrics: Mapping[str, Mapping[int, Mapping[str, float]]],
    train_folds: Sequence[Sequence[int]],
) -> ShrunkEstimatorConfig:
    """Select without receiving any held-out fold seeds or metrics."""

    def objective(config: ShrunkEstimatorConfig) -> tuple[float, float, int, float, float]:
        metrics = candidate_world_metrics[_config_id(config)]
        fold_gains = [
            mean(metrics[seed]["search_top1_gain"] for seed in fold) for fold in train_folds
        ]
        all_train = tuple(seed for fold in train_folds for seed in fold)
        return (
            min(fold_gains),
            mean(metrics[seed]["search_top1_gain"] for seed in all_train),
            -config.window_days,
            -config.context_shrinkage_pseudocounts,
            -config.owner_probability_threshold,
        )

    return max(candidates, key=objective)


def _bootstrap_ci(
    values: Sequence[float],
    *,
    draws: int,
    name: str,
) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{name}:world-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _score_all_candidates(
    design: RollingTrainGateDesign,
) -> tuple[
    list[StructureTwoWorld],
    dict[str, dict[int, dict[str, float]]],
]:
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    worlds = [generator.sample_world(seed) for seed in design.world_seeds]
    rollouts: dict[int, tuple[StructureTwoWorldRollout, ...]] = {}
    for world in worlds:
        rollouts[world.world_seed] = tuple(
            generator.generate_rollout(
                world,
                trajectory_seed=trajectory_seed,
                observation_seed=observation_seed,
            )
            for trajectory_seed in design.trajectory_seeds
            for observation_seed in design.observation_seeds
        )

    candidate_world_metrics: dict[str, dict[int, dict[str, float]]] = {}
    for candidate in design.candidates():
        per_world: dict[int, dict[str, float]] = {}
        for world in worlds:
            readings = [
                evaluate_rolling_rollout(
                    rollout,
                    world,
                    design.distribution,
                    candidate,
                )
                for rollout in rollouts[world.world_seed]
            ]
            per_world[world.world_seed] = _world_metric(readings)
        candidate_world_metrics[_config_id(candidate)] = per_world
    return worlds, candidate_world_metrics


def _score_single_config(
    design: RollingTrainGateDesign,
    worlds: Sequence[StructureTwoWorld],
    config: ShrunkEstimatorConfig,
    *,
    tie_break_scope: str,
) -> dict[int, dict[str, float]]:
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    result: dict[int, dict[str, float]] = {}
    for world in worlds:
        readings = [
            evaluate_rolling_rollout(
                generator.generate_rollout(
                    world,
                    trajectory_seed=trajectory_seed,
                    observation_seed=observation_seed,
                ),
                world,
                design.distribution,
                config,
                tie_break_scope=tie_break_scope,
            )
            for trajectory_seed in design.trajectory_seeds
            for observation_seed in design.observation_seeds
        ]
        result[world.world_seed] = _world_metric(readings)
    return result


def run_rolling_train_outer_cv_gate(*, repository_root: Path) -> dict[str, Any]:
    design_path = repository_root / DEFAULT_DESIGN
    design = load_rolling_train_gate_design(design_path, repository_root=repository_root)
    worlds, candidate_world_metrics = _score_all_candidates(design)
    candidates = design.candidates()

    candidate_summaries: dict[str, Any] = {}
    for candidate in candidates:
        config_id = _config_id(candidate)
        metrics = candidate_world_metrics[config_id]
        candidate_summaries[config_id] = {
            "config": _config_payload(candidate),
            "fold_metrics": [_mean_metrics(metrics, fold) for fold in design.folds],
            "all_train_world_metrics": _mean_metrics(metrics, design.world_seeds),
        }

    outer_world_metrics: dict[int, Mapping[str, float]] = {}
    outer_folds: list[dict[str, Any]] = []
    for held_index, held_fold in enumerate(design.folds):
        train_folds = tuple(fold for index, fold in enumerate(design.folds) if index != held_index)
        selected = _select_config(
            candidates,
            candidate_world_metrics,
            train_folds,
        )
        selected_metrics = candidate_world_metrics[_config_id(selected)]
        for seed in held_fold:
            outer_world_metrics[seed] = selected_metrics[seed]
        outer_folds.append(
            {
                "held_out_fold_index": held_index,
                "held_out_world_seeds": list(held_fold),
                "selection_world_seeds": [seed for fold in train_folds for seed in fold],
                "selected_config": _config_payload(selected),
                "selection_fold_search_top1_gains": [
                    mean(selected_metrics[seed]["search_top1_gain"] for seed in fold)
                    for fold in train_folds
                ],
                "held_out_metrics": _mean_metrics(selected_metrics, held_fold),
            }
        )

    if set(outer_world_metrics) != set(design.world_seeds):
        raise RuntimeError("outer CV did not score every train world exactly once")
    outer_overall = _mean_metrics(outer_world_metrics, design.world_seeds)
    worst_fold_search_gain = min(
        item["held_out_metrics"]["search_top1_gain"] for item in outer_folds
    )
    thresholds = design.v0_2_thresholds
    draws = int(thresholds["bootstrap_draws"])
    put_gain_values = [
        outer_world_metrics[seed]["put_back_visible_history_gain_over_sticky"]
        for seed in design.world_seeds
    ]
    search_gain_values = [
        outer_world_metrics[seed]["search_top1_gain"] for seed in design.world_seeds
    ]
    put_gain_ci = _bootstrap_ci(
        put_gain_values,
        draws=draws,
        name="outer-put-back-visible-history-gain",
    )
    search_gain_ci = _bootstrap_ci(
        search_gain_values,
        draws=draws,
        name="outer-search-top1-gain",
    )
    unique_fraction = len({world.world_hash for world in worlds}) / len(worlds)
    criteria = {
        "all_train_worlds_are_structurally_unique": unique_fraction
        >= float(thresholds["minimum_unique_validation_world_fraction"]),
        "put_back_sticky_rule_leaves_headroom": outer_overall["put_back_sticky_error"]
        >= float(thresholds["minimum_put_back_sticky_error"]),
        "put_back_visible_history_beats_sticky": outer_overall[
            "put_back_visible_history_gain_over_sticky"
        ]
        >= float(thresholds["minimum_put_back_aggregation_gain"]),
        "put_back_visible_history_gain_is_world_robust": put_gain_ci[0]
        >= float(thresholds["minimum_put_back_aggregation_gain_ci_lower"]),
        "put_back_context_is_action_relevant": outer_overall["put_back_context_gain_over_pooled"]
        >= float(thresholds["minimum_put_back_context_gain"]),
        "put_back_retains_method_headroom": outer_overall["put_back_visible_history_error"]
        >= float(thresholds["minimum_remaining_put_back_error"]),
        "owner_observation_is_not_the_habit_target": outer_overall[
            "on_owner_observed_target_match_rate"
        ]
        <= float(thresholds["maximum_on_owner_observed_target_recurrence"]),
        "search_last_observed_rule_leaves_headroom": outer_overall["search_last_observed_error"]
        >= float(thresholds["minimum_search_last_observed_error"]),
        "search_outer_cv_mean_gain_passes": outer_overall["search_top1_gain"]
        >= design.minimum_mean_search_gain,
        "search_outer_cv_worst_fold_gain_passes": worst_fold_search_gain
        >= design.minimum_worst_fold_search_gain,
        "search_retains_method_headroom": outer_overall["search_visible_history_error"]
        >= float(thresholds["minimum_remaining_search_error"]),
        "unobserved_location_dynamics_are_nontrivial": outer_overall[
            "unobserved_location_change_rate"
        ]
        >= float(thresholds["minimum_unobserved_location_change_rate"]),
    }
    train_gate_passed = all(criteria.values())

    final_config = _select_config(candidates, candidate_world_metrics, design.folds)
    final_metrics = candidate_world_metrics[_config_id(final_config)]
    causal_prefix_metrics = _score_single_config(
        design,
        worlds,
        final_config,
        tie_break_scope="causal_prefix",
    )
    formal_final_overall = _mean_metrics(final_metrics, design.world_seeds)
    causal_prefix_overall = _mean_metrics(causal_prefix_metrics, design.world_seeds)
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": (
            "retrospective exploratory method-free train-world outer CV; the design "
            "followed exploratory probes; no validation, holdout, Gate B, or method "
            "arm was run"
        ),
        "train_design_frozen_before_run": False,
        "train_evidence_confirmatory": False,
        "duration_days_inclusive": list(design.duration_days),
        "train_world_seeds": list(design.world_seeds),
        "trajectory_seeds": list(design.trajectory_seeds),
        "observation_seeds": list(design.observation_seeds),
        "outer_world_folds": [list(fold) for fold in design.folds],
        "candidate_count": len(candidates),
        "candidate_grid_results": candidate_summaries,
        "outer_cv_folds": outer_folds,
        "outer_cv_world_metrics": {
            str(seed): dict(outer_world_metrics[seed]) for seed in design.world_seeds
        },
        "outer_cv_overall_world_weighted_metrics": outer_overall,
        "outer_cv_worst_held_out_fold_search_top1_gain": worst_fold_search_gain,
        "outer_cv_put_back_visible_history_gain_world_bootstrap_ci_95": put_gain_ci,
        "outer_cv_search_top1_gain_world_bootstrap_ci_95": search_gain_ci,
        "final_config_selected_on_all_train_worlds_for_future_validation": _config_payload(
            final_config
        ),
        "final_config_all_train_fold_metrics_report_only": [
            _mean_metrics(final_metrics, fold) for fold in design.folds
        ],
        "final_config_all_train_metrics_report_only": _mean_metrics(
            final_metrics, design.world_seeds
        ),
        "encounter_order_causal_prefix_sensitivity_report_only": {
            "formal_complete_rollout_metrics": formal_final_overall,
            "causal_prefix_metrics": causal_prefix_overall,
            "search_top1_gain_difference_formal_minus_causal": (
                formal_final_overall["search_top1_gain"] - causal_prefix_overall["search_top1_gain"]
            ),
            "causal_prefix_mean_search_gain_still_meets_train_threshold": (
                causal_prefix_overall["search_top1_gain"] >= design.minimum_mean_search_gain
            ),
            "binding": False,
        },
        "effective_sample_size_definition": {
            "admitted_context_count_per_rollout": (
                "visible observations passing owner_probability_threshold"
            ),
            "active_context_samples_per_unobserved_prediction": (
                "matching-context admitted samples still inside the rolling window"
            ),
            "active_effective_mass_per_unobserved_prediction": (
                "active context samples plus pooled shrinkage pseudocount when pooled "
                "history is nonempty"
            ),
        },
        "thresholds": {
            **dict(thresholds),
            "minimum_outer_cv_world_weighted_mean_search_top1_gain": (
                design.minimum_mean_search_gain
            ),
            "minimum_outer_cv_worst_held_out_fold_search_top1_gain": (
                design.minimum_worst_fold_search_gain
            ),
        },
        "criteria": criteria,
        "train_promotion_gate_passed": train_gate_passed,
        "validation_authorized": False,
        "holdout_opened": False,
        "gate_b_executed": False,
        "method_comparison_allowed": False,
        "prereserved_validation_seeds_not_generated": {
            "world": list(design.validation_world_seed_candidates),
            "trajectory": list(design.validation_trajectory_seeds),
            "observation": list(design.validation_observation_seeds),
        },
        "formal_ranking_contract": {
            "tie_break": (
                "complete-rollout robot-visible first encounter order; never-observed "
                "candidates append in frozen catalogue order"
            ),
            "evaluation_scope": "offline frozen episode",
            "online_information_claimed": False,
        },
        "legacy_detector": {
            "binding": False,
            "failed_artifact_preserved": True,
            "exact_execution_source_archived": True,
            "archived_gate_source": (
                "artifacts/project_two_v04_development/source_snapshots/"
                "structure_two_world_gate_v0_3_at_horizon_probe.py"
            ),
            "archived_gate_source_sha256": (
                "8b8b9010ce219b32750446271778a78c0378ca7b930bc389d29418a59d6529f7"
            ),
            "current_development_source_evolved_after_artifact": True,
        },
        "world_parameter_summaries": [
            {
                "world_seed": world.world_seed,
                "world_hash": world.world_hash,
                "duration_days": world.duration_days,
                "location_count": len(world.locations),
                "guest_actor_count": len(world.guest_actors),
                "abrupt_day": world.abrupt_day,
                "recurrence_day": world.recurrence_day,
            }
            for world in worlds
        ],
        "provenance": {
            "design_sha256": design.design_sha256,
            "base_manifest_sha256": design.base_manifest_sha256,
            "generator_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
            ),
            "rolling_reference_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_gate_v0_3.py"
            ),
            "train_gate_source_sha256": _file_sha256(Path(__file__).resolve()),
        },
        "limitations": [
            "Passing this train gate only permits drafting and signing a new validation manifest.",
            (
                "The [320,380] horizon is a reopened world-distribution field and "
                "must not be described as byte-identical to v0.2."
            ),
            (
                "The synthetic D0 distribution and author-selected thresholds still "
                "lack real-household grounding."
            ),
            (
                "Identity, cause, regime, event-chain, and embodied-feedback "
                "capabilities remain in Structure Two but are not validated by this "
                "target gate alone."
            ),
            (
                "The train design was recorded after exploratory probes. Its outer-CV "
                "numbers are development evidence, not preregistered evidence."
            ),
            (
                "The formal encounter-order tie break is reconstructed offline from the "
                "complete frozen rollout. It is an evaluator convention, not information "
                "available to an online method."
            ),
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_rolling_train_gate_report(
    report: Mapping[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_rolling_train_gate_report(
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
        raise ValueError("rolling train-gate report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("rolling train-gate report protocol mismatch")
    design = load_rolling_train_gate_design(
        repository_root / DEFAULT_DESIGN,
        repository_root=repository_root,
    )
    expected_provenance = {
        "design_sha256": design.design_sha256,
        "base_manifest_sha256": design.base_manifest_sha256,
        "generator_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
        ),
        "rolling_reference_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/structure_two_world_gate_v0_3.py"
        ),
        "train_gate_source_sha256": _file_sha256(Path(__file__).resolve()),
    }
    if report.get("provenance") != expected_provenance:
        raise ValueError("rolling train-gate provenance mismatch")
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("rolling train-gate criteria missing")
    expected_pass = all(value is True for value in criteria.values())
    if report.get("train_promotion_gate_passed") != expected_pass:
        raise ValueError("rolling train-gate decision mismatch")
    if report.get("validation_authorized") is not False:
        raise ValueError("train evidence may not authorise validation before attestation")
    if report.get("method_comparison_allowed") is not False:
        raise ValueError("train evidence may never authorise method comparison")
    if recompute:
        expected = run_rolling_train_outer_cv_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("rolling train-gate deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_DESIGN",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "RollingRolloutReading",
    "RollingTrainGateDesign",
    "evaluate_rolling_rollout",
    "load_rolling_train_gate_design",
    "run_rolling_train_outer_cv_gate",
    "verify_rolling_train_gate_report",
    "write_rolling_train_gate_report",
]
