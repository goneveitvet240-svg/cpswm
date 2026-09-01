"""Reproducible train-only horizon probe for Structure Two v0.3.

The probe changes only the duration range to 320--380 days, evaluates a frozen
48-cell visible-information TV-witness grid on train worlds, and never samples
validation or sealed-holdout worlds.  It is benchmark-design evidence, not a
research-method comparison.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_2 import (
    load_frozen_world_gate_design,
)
from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    RegimeAdaptiveWitnessConfig,
    _argmax,
    _normalised_path_cost,
    _ranked,
    _WitnessEstimator,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    IntegerRangeSpec,
    StructureTwoWorld,
    StructureTwoWorldGeneratorV02,
    StructureTwoWorldRollout,
    StructureTwoWorldStep,
    WorldDistributionConfig,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-horizon-probe@0.3"
DEFAULT_DESIGN = Path("configs/project_two_experiments/structure_two_world_horizon_probe_v0_3.json")
DEFAULT_OUTPUT = Path(
    "artifacts/project_two_v04_development/structure_two_world_horizon_probe_v0_3.json"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class HorizonProbeDesign:
    base_manifest: Path
    base_manifest_sha256: str
    duration_days: tuple[int, int]
    world_seeds: tuple[int, ...]
    trajectory_seeds: tuple[int, ...]
    observation_seeds: tuple[int, ...]
    folds: tuple[tuple[int, ...], ...]
    recent_windows: tuple[int, ...]
    divergence_thresholds: tuple[float, ...]
    minimum_reference_observations: tuple[int, ...]
    shrinkages: tuple[float, ...]
    owner_probability_thresholds: tuple[float, ...]
    stationary_stream_seeds: tuple[int, ...]
    stationary_observations: int
    stationary_burn_in: int
    stationary_mode_masses: tuple[float, ...]
    stationary_location_count: int
    grace_days: int
    minimum_mean_top1_gain: float
    minimum_worst_fold_top1_gain: float
    maximum_false_resets_per_rollout: float
    maximum_stationary_false_alarm_rate: float
    design_sha256: str

    def witness_configs(self) -> tuple[RegimeAdaptiveWitnessConfig, ...]:
        return tuple(
            RegimeAdaptiveWitnessConfig(
                recent_window=int(recent),
                divergence_threshold=float(threshold),
                minimum_reference_observations=int(reference),
                context_shrinkage_pseudocounts=float(shrinkage),
                owner_probability_threshold=float(owner_threshold),
            )
            for recent, threshold, reference, shrinkage, owner_threshold in itertools.product(
                self.recent_windows,
                self.divergence_thresholds,
                self.minimum_reference_observations,
                self.shrinkages,
                self.owner_probability_thresholds,
            )
        )


def load_horizon_probe_design(path: Path, *, repository_root: Path) -> HorizonProbeDesign:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("horizon-probe protocol mismatch")
    if payload.get("status") != "frozen-before-320-380-train-only-run":
        raise ValueError("horizon-probe design is not frozen")
    base_manifest = repository_root / payload["base_manifest"]
    base_hash = _file_sha256(base_manifest)
    if base_hash != payload["base_manifest_sha256"]:
        raise ValueError("base v0.2 manifest hash mismatch")
    sampling = payload["train_sampling"]
    world_seeds = tuple(int(item) for item in sampling["world_seeds"])
    folds = tuple(tuple(int(item) for item in fold) for fold in payload["four_fold_world_split"])
    flattened = tuple(item for fold in folds for item in fold)
    if len(set(flattened)) != len(flattened) or set(flattened) != set(world_seeds):
        raise ValueError("four-fold world split must cover train worlds exactly once")
    grid = payload["witness_grid"]
    candidate_count = (
        len(grid["recent_window"])
        * len(grid["divergence_threshold"])
        * len(grid["minimum_reference_observations"])
        * len(grid["context_shrinkage_pseudocounts"])
        * len(grid["owner_probability_threshold"])
    )
    if candidate_count != int(grid["cartesian_candidate_count"]):
        raise ValueError("witness-grid candidate count mismatch")
    stationary = payload["stationary_false_alarm_check"]
    promotion = payload["promotion_requirements"]
    grace = payload["false_reset_definition"]
    low, high = payload["world_change_under_test"]["duration_days_inclusive"]
    return HorizonProbeDesign(
        base_manifest=base_manifest,
        base_manifest_sha256=base_hash,
        duration_days=(int(low), int(high)),
        world_seeds=world_seeds,
        trajectory_seeds=tuple(int(item) for item in sampling["trajectory_seeds"]),
        observation_seeds=tuple(int(item) for item in sampling["observation_seeds"]),
        folds=folds,
        recent_windows=tuple(int(item) for item in grid["recent_window"]),
        divergence_thresholds=tuple(float(item) for item in grid["divergence_threshold"]),
        minimum_reference_observations=tuple(
            int(item) for item in grid["minimum_reference_observations"]
        ),
        shrinkages=tuple(float(item) for item in grid["context_shrinkage_pseudocounts"]),
        owner_probability_thresholds=tuple(
            float(item) for item in grid["owner_probability_threshold"]
        ),
        stationary_stream_seeds=tuple(int(item) for item in stationary["stream_seeds"]),
        stationary_observations=int(stationary["observations_per_stream"]),
        stationary_burn_in=int(stationary["burn_in_observations"]),
        stationary_mode_masses=tuple(float(item) for item in stationary["mode_masses"]),
        stationary_location_count=int(stationary["location_count"]),
        grace_days=int(grace["grace_days_after_true_change_inclusive"]),
        minimum_mean_top1_gain=float(promotion["minimum_world_weighted_mean_top1_gain"]),
        minimum_worst_fold_top1_gain=float(promotion["minimum_worst_held_out_fold_top1_gain"]),
        maximum_false_resets_per_rollout=float(promotion["maximum_mean_false_resets_per_rollout"]),
        maximum_stationary_false_alarm_rate=float(
            promotion["maximum_stationary_false_alarm_rate_per_observation"]
        ),
        design_sha256=_file_sha256(path),
    )


@dataclass(frozen=True, slots=True)
class WitnessProbeReading:
    world_seed: int
    top1_gain: float
    normalised_path_cost_gain: float
    false_reset_count: int
    total_reset_count: int
    admitted_weekday_count: int
    admitted_weekend_count: int


def _false_reset_count(
    reset_days: Sequence[int],
    world: StructureTwoWorld,
    *,
    grace_days: int,
) -> int:
    """One-to-one reset/change matching; extra resets in a grace window are false."""

    unmatched_changes = [world.abrupt_day, world.recurrence_day]
    false_count = 0
    for reset_day in sorted(int(item) for item in reset_days):
        match_index = next(
            (
                index
                for index, change_day in enumerate(unmatched_changes)
                if change_day <= reset_day <= change_day + grace_days
            ),
            None,
        )
        if match_index is None:
            false_count += 1
        else:
            unmatched_changes.pop(match_index)
    return false_count


def _score_witness_rollout(
    rollout: StructureTwoWorldRollout,
    world: StructureTwoWorld,
    witness_config: RegimeAdaptiveWitnessConfig,
    *,
    grace_days: int,
) -> WitnessProbeReading:
    locations = tuple(rollout.locations)
    fallback = locations[0]
    witness = _WitnessEstimator(fallback, witness_config)
    last_observed = fallback
    cumulative_observed_counts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    path: Counter[str] = Counter()
    admitted: Counter[str] = Counter()
    for step in rollout.steps:
        visible_now = step.observed and step.observed_location is not None
        if visible_now:
            assert step.observed_location is not None
            last_observed = step.observed_location
            cumulative_observed_counts[step.observed_location] += 1
            if witness.admit(step):
                admitted[step.context] += 1
                witness.observe(step, step.observed_location)
        head = step.observed_location if visible_now else None
        witness_scores = witness.scores(step.context)
        witness_mode = _argmax(witness_scores)
        orders = {
            "last": _ranked(
                {item: float(cumulative_observed_counts.get(item, 0)) for item in locations},
                locations,
                head or last_observed,
            ),
            "witness": _ranked(witness_scores, locations, head or witness_mode),
        }
        for name, order in orders.items():
            errors[name] += order[0] != step.true_location
            path[name] += _normalised_path_cost(order, step.true_location, len(locations))
    total = len(rollout.steps)
    return WitnessProbeReading(
        world_seed=rollout.world_seed,
        top1_gain=(errors["last"] - errors["witness"]) / total,
        normalised_path_cost_gain=(path["last"] - path["witness"]) / total,
        false_reset_count=_false_reset_count(
            witness.reset_days,
            world,
            grace_days=grace_days,
        ),
        total_reset_count=witness.reset_count,
        admitted_weekday_count=admitted["weekday"],
        admitted_weekend_count=admitted["weekend"],
    )


def _stationary_step(
    *, day: int, context: str, location: str, distribution: Mapping[str, float]
) -> StructureTwoWorldStep:
    return StructureTwoWorldStep(
        day=day,
        context=context,
        regime="baseline",
        true_actor="owner",
        true_location=location,
        true_owner_habit_location=max(distribution, key=distribution.__getitem__),
        true_habit_distribution=dict(distribution),
        true_mechanism="direct",
        true_cause="owner_habit_sample",
        true_identity_match=True,
        event_chain=("pick_up", "carry", "place"),
        observed=True,
        observation_propensity=1.0,
        observed_location=location,
        visible_actor_map="owner",
        visible_owner_probability=1.0,
        visible_identity_confidence=1.0,
    )


def _stationary_false_alarm_rate(
    config: RegimeAdaptiveWitnessConfig,
    *,
    seed: int,
    observations: int,
    burn_in: int,
    mode_mass: float,
    location_count: int,
) -> float:
    rng = random.Random(f"{PROTOCOL_ID}:stationary:{seed}:{mode_mass}")
    locations = tuple(f"stationary_location_{index}" for index in range(location_count))
    tail = (1.0 - mode_mass) / (location_count - 1)
    distribution = {
        location: mode_mass if index == 0 else tail for index, location in enumerate(locations)
    }
    witness = _WitnessEstimator(locations[0], config)
    for day in range(observations):
        location = str(
            rng.choices(locations, weights=[distribution[item] for item in locations], k=1)[0]
        )
        witness.observe(
            _stationary_step(
                day=day,
                context="weekday" if day % 7 < 5 else "weekend",
                location=location,
                distribution=distribution,
            ),
            location,
        )
    denominator = max(1, observations - burn_in)
    return sum(day >= burn_in for day in witness.reset_days) / denominator


def _config_dict(config: RegimeAdaptiveWitnessConfig) -> dict[str, float | int]:
    return {
        "recent_window": config.recent_window,
        "divergence_threshold": config.divergence_threshold,
        "minimum_reference_observations": config.minimum_reference_observations,
        "context_shrinkage_pseudocounts": config.context_shrinkage_pseudocounts,
        "owner_probability_threshold": config.owner_probability_threshold,
    }


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(item) for item in values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def run_horizon_probe(*, repository_root: Path) -> dict[str, Any]:
    design_path = repository_root / DEFAULT_DESIGN
    design = load_horizon_probe_design(design_path, repository_root=repository_root)
    base = load_frozen_world_gate_design(design.base_manifest)
    long_config: WorldDistributionConfig = replace(
        base.distribution,
        duration_days=IntegerRangeSpec(*design.duration_days),
    )
    generator = StructureTwoWorldGeneratorV02(long_config)
    worlds = {seed: generator.sample_world(seed) for seed in design.world_seeds}
    rollouts = {
        seed: tuple(
            generator.generate_rollout(
                worlds[seed],
                trajectory_seed=trajectory_seed,
                observation_seed=observation_seed,
            )
            for trajectory_seed in design.trajectory_seeds
            for observation_seed in design.observation_seeds
        )
        for seed in design.world_seeds
    }
    candidate_rows: list[dict[str, Any]] = []
    for witness_config in design.witness_configs():
        world_readings: dict[int, dict[str, float]] = {}
        for world_seed in design.world_seeds:
            readings = [
                _score_witness_rollout(
                    rollout,
                    worlds[world_seed],
                    witness_config,
                    grace_days=design.grace_days,
                )
                for rollout in rollouts[world_seed]
            ]
            world_readings[world_seed] = {
                "top1_gain": mean(item.top1_gain for item in readings),
                "normalised_path_cost_gain": mean(
                    item.normalised_path_cost_gain for item in readings
                ),
                "false_resets_per_rollout": mean(item.false_reset_count for item in readings),
                "total_resets_per_rollout": mean(item.total_reset_count for item in readings),
                "admitted_weekday_per_rollout": mean(
                    item.admitted_weekday_count for item in readings
                ),
                "admitted_weekend_per_rollout": mean(
                    item.admitted_weekend_count for item in readings
                ),
            }
        fold_gains = [
            mean(world_readings[seed]["top1_gain"] for seed in fold) for fold in design.folds
        ]
        stationary_rates = [
            _stationary_false_alarm_rate(
                witness_config,
                seed=seed,
                observations=design.stationary_observations,
                burn_in=design.stationary_burn_in,
                mode_mass=mode_mass,
                location_count=design.stationary_location_count,
            )
            for seed in design.stationary_stream_seeds
            for mode_mass in design.stationary_mode_masses
        ]
        mean_false_resets = mean(
            item["false_resets_per_rollout"] for item in world_readings.values()
        )
        stationary_rate = mean(stationary_rates)
        candidate_rows.append(
            {
                "parameters": _config_dict(witness_config),
                "world_weighted_mean_top1_gain": mean(
                    item["top1_gain"] for item in world_readings.values()
                ),
                "fold_top1_gains": fold_gains,
                "worst_fold_top1_gain": min(fold_gains),
                "world_weighted_mean_normalised_path_cost_gain": mean(
                    item["normalised_path_cost_gain"] for item in world_readings.values()
                ),
                "mean_false_resets_per_rollout": mean_false_resets,
                "mean_total_resets_per_rollout": mean(
                    item["total_resets_per_rollout"] for item in world_readings.values()
                ),
                "stationary_false_alarm_rate_per_observation": stationary_rate,
                "eligible": (
                    mean_false_resets <= design.maximum_false_resets_per_rollout
                    and stationary_rate <= design.maximum_stationary_false_alarm_rate
                ),
                "world_metrics": {str(key): value for key, value in world_readings.items()},
            }
        )
    eligible = [item for item in candidate_rows if item["eligible"]]
    eligible.sort(
        key=lambda item: (
            -item["worst_fold_top1_gain"],
            -item["world_weighted_mean_top1_gain"],
            item["mean_false_resets_per_rollout"],
            tuple(item["parameters"].values()),
        )
    )
    selected = eligible[0] if eligible else None
    # Admission counts depend only on the frozen owner-probability threshold,
    # whose grid has one value.  Report them even when no detector is eligible;
    # a failed probe must not erase the requested weekday/weekend sample audit.
    admission_worlds = candidate_rows[0]["world_metrics"].values()
    weekday_admissions = [item["admitted_weekday_per_rollout"] for item in admission_worlds]
    weekend_admissions = [item["admitted_weekend_per_rollout"] for item in admission_worlds]
    admissions: dict[str, Any] = {
        "weekday": {
            "world_weighted_mean_per_rollout": mean(weekday_admissions),
            "minimum_world_mean_per_rollout": min(weekday_admissions),
            "p10_world_mean_per_rollout": _quantile(weekday_admissions, 0.10),
        },
        "weekend": {
            "world_weighted_mean_per_rollout": mean(weekend_admissions),
            "minimum_world_mean_per_rollout": min(weekend_admissions),
            "p10_world_mean_per_rollout": _quantile(weekend_admissions, 0.10),
        },
    }
    if selected is None:
        criteria = {
            "eligible_witness_exists": False,
            "mean_top1_gain_passes": False,
            "worst_fold_top1_gain_passes": False,
            "false_reset_constraint_passes": False,
            "stationary_false_alarm_constraint_passes": False,
            "context_admissions_reported": True,
            "formal_pooled_tail_used": True,
        }
    else:
        criteria = {
            "eligible_witness_exists": True,
            "mean_top1_gain_passes": selected["world_weighted_mean_top1_gain"]
            >= design.minimum_mean_top1_gain,
            "worst_fold_top1_gain_passes": selected["worst_fold_top1_gain"]
            >= design.minimum_worst_fold_top1_gain,
            "false_reset_constraint_passes": selected["mean_false_resets_per_rollout"]
            <= design.maximum_false_resets_per_rollout,
            "stationary_false_alarm_constraint_passes": selected[
                "stationary_false_alarm_rate_per_observation"
            ]
            <= design.maximum_stationary_false_alarm_rate,
            "context_admissions_reported": True,
            "formal_pooled_tail_used": True,
        }
    passed = all(criteria.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "train-only horizon-design probe; no method comparison",
        "duration_days_inclusive": list(design.duration_days),
        "validation_worlds_generated": False,
        "sealed_holdout_opened": False,
        "method_comparison_executed": False,
        "train_world_count": len(design.world_seeds),
        "rollouts_per_world": len(design.trajectory_seeds) * len(design.observation_seeds),
        "candidate_count": len(candidate_rows),
        "eligible_candidate_count": len(eligible),
        "selected_candidate": selected,
        "effective_admissions_by_context": admissions,
        "promotion_requirements": {
            "minimum_world_weighted_mean_top1_gain": design.minimum_mean_top1_gain,
            "minimum_worst_held_out_fold_top1_gain": design.minimum_worst_fold_top1_gain,
            "maximum_mean_false_resets_per_rollout": (design.maximum_false_resets_per_rollout),
            "maximum_stationary_false_alarm_rate_per_observation": (
                design.maximum_stationary_false_alarm_rate
            ),
        },
        "criteria": criteria,
        "horizon_probe_passed": passed,
        "draft_manifest_may_adopt_duration": passed,
        "candidate_results": candidate_rows,
        "provenance": {
            "design_sha256": design.design_sha256,
            "base_manifest_sha256": design.base_manifest_sha256,
            "generator_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
            ),
            "gate_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_gate_v0_3.py"
            ),
            "probe_source_sha256": _file_sha256(Path(__file__).resolve()),
        },
        "limitations": [
            "This is synthetic train-world design evidence, not validation evidence.",
            "The 0.020 and 0.018 requirements are author-selected and not externally grounded.",
            "Passing authorises only an unsigned manifest draft, never a method comparison.",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_horizon_probe_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_horizon_probe_report(
    path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("horizon-probe content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("horizon-probe report protocol mismatch")
    if report.get("validation_worlds_generated") is not False:
        raise ValueError("horizon probe generated validation worlds")
    if report.get("sealed_holdout_opened") is not False:
        raise ValueError("horizon probe opened sealed holdout")
    if report.get("method_comparison_executed") is not False:
        raise ValueError("horizon probe ran a research method")
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("horizon-probe criteria missing")
    expected_pass = all(value is True for value in criteria.values())
    if report.get("horizon_probe_passed") != expected_pass:
        raise ValueError("horizon-probe decision mismatch")
    if report.get("draft_manifest_may_adopt_duration") != expected_pass:
        raise ValueError("draft-manifest authorisation mismatch")
    if recompute:
        expected = run_horizon_probe(repository_root=repository_root)
        if expected["content_sha256"] != stored_hash:
            raise ValueError("horizon-probe deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_DESIGN",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "HorizonProbeDesign",
    "WitnessProbeReading",
    "load_horizon_probe_design",
    "run_horizon_probe",
    "verify_horizon_probe_report",
    "write_horizon_probe_report",
]
