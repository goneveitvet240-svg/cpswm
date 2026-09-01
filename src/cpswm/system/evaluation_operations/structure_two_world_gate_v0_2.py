"""Frozen method-free Gate A for the Structure-Two world generator v0.2."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    PROTOCOL_ID as GENERATOR_PROTOCOL_ID,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorldGeneratorV02,
    StructureTwoWorldRollout,
    WorldDistributionConfig,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-generator-gate-a@0.2"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/project_two_v04_development/structure_two_world_generator_gate_a_v0_2.json"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenWorldGateDesign:
    train_world_seeds: tuple[int, ...]
    validation_world_seeds: tuple[int, ...]
    holdout_world_seed_commitments: tuple[str, ...]
    sealed_holdout_world_count: int
    trajectory_seeds: tuple[int, ...]
    observation_seeds: tuple[int, ...]
    distribution: WorldDistributionConfig
    thresholds: Mapping[str, float | int]
    aggregation_window_days: int
    owner_probability_threshold: float
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class RolloutGateReading:
    world_seed: int
    rollout_id: str
    step_count: int
    put_back_sticky_error: float
    put_back_global_mode_error: float
    put_back_context_mode_error: float
    search_last_observed_error: float
    search_contextual_fallback_error: float
    on_owner_observed_target_match_rate: float
    unobserved_location_change_rate: float
    observed_step_count: int
    unobserved_step_count: int


def load_frozen_world_gate_design(
    manifest_path: Path,
) -> FrozenWorldGateDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != GENERATOR_PROTOCOL_ID:
        raise ValueError("world-generator manifest protocol mismatch")
    if payload.get("status") != "frozen-before-first-gate-a-run":
        raise ValueError("world-generator manifest was not frozen before Gate A")
    split = payload["split_policy"]
    train = tuple(int(item) for item in split["train_world_seeds"])
    validation = tuple(int(item) for item in split["validation_world_seeds"])
    if set(train) & set(validation):
        raise ValueError("world-level train and validation splits overlap")
    commitments = tuple(str(item) for item in split["sealed_holdout_world_seed_commitments"])
    sealed_count = int(split["sealed_holdout_world_count"])
    if len(commitments) != sealed_count or len(set(commitments)) != sealed_count:
        raise ValueError("sealed world commitment coverage mismatch")
    if split.get("holdout_raw_world_seeds_disclosed") is not False:
        raise ValueError("Gate A must not disclose holdout world seeds")
    rules = payload["gate_a_rules"]
    thresholds = {
        key: int(value) if key == "bootstrap_draws" else float(value)
        for key, value in payload["gate_a_thresholds"].items()
    }
    return FrozenWorldGateDesign(
        train_world_seeds=train,
        validation_world_seeds=validation,
        holdout_world_seed_commitments=commitments,
        sealed_holdout_world_count=sealed_count,
        trajectory_seeds=tuple(
            int(item) for item in split["trajectory_seeds_per_validation_world"]
        ),
        observation_seeds=tuple(
            int(item) for item in split["observation_seeds_per_validation_trajectory"]
        ),
        distribution=WorldDistributionConfig.from_manifest(payload["world_distribution"]),
        thresholds=thresholds,
        aggregation_window_days=int(rules["aggregation_window_days"]),
        owner_probability_threshold=float(rules["visible_owner_probability_threshold"]),
        manifest_sha256=_file_sha256(manifest_path),
    )


def _counter_mode(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return min(counter.items(), key=lambda item: (-item[1], item[0]))[0]


def _prune(
    rows: deque[tuple[int, str]],
    counter: Counter[str],
    *,
    minimum_day: int,
) -> None:
    while rows and rows[0][0] < minimum_day:
        _day, location = rows.popleft()
        counter[location] -= 1
        if counter[location] <= 0:
            del counter[location]


def evaluate_rollout_gate_a(
    rollout: StructureTwoWorldRollout,
    *,
    aggregation_window_days: int,
    owner_probability_threshold: float,
) -> RolloutGateReading:
    fallback = rollout.locations[0]
    sticky = fallback
    last_observed = fallback
    global_rows: deque[tuple[int, str]] = deque()
    global_counts: Counter[str] = Counter()
    context_rows = {"weekday": deque(), "weekend": deque()}
    context_counts = {"weekday": Counter(), "weekend": Counter()}
    errors = Counter()
    observed_owner_matches = observed_owner_total = 0
    unobserved_changes = unobserved_total = 0
    previous_true_location: str | None = None

    for step in rollout.steps:
        minimum_day = step.day - aggregation_window_days + 1
        _prune(global_rows, global_counts, minimum_day=minimum_day)
        for context in context_rows:
            _prune(
                context_rows[context],
                context_counts[context],
                minimum_day=minimum_day,
            )
        if step.observed and step.observed_location is not None:
            last_observed = step.observed_location
            visible_owner = (
                step.visible_owner_probability is not None
                and step.visible_owner_probability >= owner_probability_threshold
            )
            if visible_owner:
                sticky = step.observed_location
                global_rows.append((step.day, step.observed_location))
                global_counts[step.observed_location] += 1
                context_rows[step.context].append((step.day, step.observed_location))
                context_counts[step.context][step.observed_location] += 1

        global_mode = _counter_mode(global_counts, sticky)
        context_mode = _counter_mode(context_counts[step.context], global_mode)
        contextual_search = (
            step.observed_location
            if step.observed and step.observed_location is not None
            else context_mode
        )
        errors["put_sticky"] += sticky != step.true_owner_habit_location
        errors["put_global"] += global_mode != step.true_owner_habit_location
        errors["put_context"] += context_mode != step.true_owner_habit_location
        errors["search_last"] += last_observed != step.true_location
        errors["search_context"] += contextual_search != step.true_location

        if step.true_actor == rollout.owner_actor and step.observed:
            observed_owner_total += 1
            observed_owner_matches += step.observed_location == step.true_owner_habit_location
        if not step.observed and previous_true_location is not None:
            unobserved_total += 1
            unobserved_changes += step.true_location != previous_true_location
        previous_true_location = step.true_location

    total = len(rollout.steps)
    observed_steps = sum(step.observed for step in rollout.steps)
    return RolloutGateReading(
        world_seed=rollout.world_seed,
        rollout_id=rollout.rollout_id,
        step_count=total,
        put_back_sticky_error=errors["put_sticky"] / total,
        put_back_global_mode_error=errors["put_global"] / total,
        put_back_context_mode_error=errors["put_context"] / total,
        search_last_observed_error=errors["search_last"] / total,
        search_contextual_fallback_error=errors["search_context"] / total,
        on_owner_observed_target_match_rate=(
            observed_owner_matches / observed_owner_total if observed_owner_total else 0.0
        ),
        unobserved_location_change_rate=(
            unobserved_changes / unobserved_total if unobserved_total else 0.0
        ),
        observed_step_count=observed_steps,
        unobserved_step_count=total - observed_steps,
    )


def _world_means(
    readings: Sequence[RolloutGateReading],
) -> dict[int, dict[str, float]]:
    grouped: dict[int, list[RolloutGateReading]] = {}
    for reading in readings:
        grouped.setdefault(reading.world_seed, []).append(reading)
    fields = (
        "put_back_sticky_error",
        "put_back_global_mode_error",
        "put_back_context_mode_error",
        "search_last_observed_error",
        "search_contextual_fallback_error",
        "on_owner_observed_target_match_rate",
        "unobserved_location_change_rate",
    )
    return {
        world_seed: {
            field: mean(float(getattr(item, field)) for item in values) for field in fields
        }
        for world_seed, values in sorted(grouped.items())
    }


def _bootstrap_ci(
    values: Sequence[float],
    *,
    draws: int,
    name: str,
) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{name}:world-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def run_structure_two_world_gate_a(*, repository_root: Path) -> dict[str, Any]:
    manifest_path = repository_root / DEFAULT_MANIFEST
    design = load_frozen_world_gate_design(manifest_path)
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    worlds = [generator.sample_world(seed) for seed in design.validation_world_seeds]
    readings: list[RolloutGateReading] = []
    for world in worlds:
        for trajectory_seed in design.trajectory_seeds:
            for observation_seed in design.observation_seeds:
                readings.append(
                    evaluate_rollout_gate_a(
                        generator.generate_rollout(
                            world,
                            trajectory_seed=trajectory_seed,
                            observation_seed=observation_seed,
                        ),
                        aggregation_window_days=design.aggregation_window_days,
                        owner_probability_threshold=design.owner_probability_threshold,
                    )
                )
    world_means = _world_means(readings)
    fields = next(iter(world_means.values())).keys()
    overall = {field: mean(values[field] for values in world_means.values()) for field in fields}
    aggregation_gains = [
        values["put_back_sticky_error"] - values["put_back_context_mode_error"]
        for values in world_means.values()
    ]
    context_gains = [
        values["put_back_global_mode_error"] - values["put_back_context_mode_error"]
        for values in world_means.values()
    ]
    search_gains = [
        values["search_last_observed_error"] - values["search_contextual_fallback_error"]
        for values in world_means.values()
    ]
    draws = int(design.thresholds["bootstrap_draws"])
    aggregation_ci = _bootstrap_ci(
        aggregation_gains,
        draws=draws,
        name="put-back-aggregation-gain",
    )
    context_ci = _bootstrap_ci(
        context_gains,
        draws=draws,
        name="put-back-context-gain",
    )
    search_ci = _bootstrap_ci(
        search_gains,
        draws=draws,
        name="search-contextual-fallback-gain",
    )
    unique_fraction = len({world.world_hash for world in worlds}) / len(worlds)
    criteria = {
        "all_validation_worlds_are_structurally_unique": unique_fraction
        >= float(design.thresholds["minimum_unique_validation_world_fraction"]),
        "put_back_sticky_rule_leaves_headroom": overall["put_back_sticky_error"]
        >= float(design.thresholds["minimum_put_back_sticky_error"]),
        "put_back_aggregation_beats_sticky": mean(aggregation_gains)
        >= float(design.thresholds["minimum_put_back_aggregation_gain"]),
        "put_back_aggregation_gain_is_world_robust": aggregation_ci[0]
        >= float(design.thresholds["minimum_put_back_aggregation_gain_ci_lower"]),
        "put_back_context_is_action_relevant": mean(context_gains)
        >= float(design.thresholds["minimum_put_back_context_gain"]),
        "put_back_retains_method_headroom": overall["put_back_context_mode_error"]
        >= float(design.thresholds["minimum_remaining_put_back_error"]),
        "owner_observation_is_not_the_habit_target": overall["on_owner_observed_target_match_rate"]
        <= float(design.thresholds["maximum_on_owner_observed_target_recurrence"]),
        "search_last_observed_rule_leaves_headroom": overall["search_last_observed_error"]
        >= float(design.thresholds["minimum_search_last_observed_error"]),
        "search_contextual_fallback_beats_last_observed": mean(search_gains)
        >= float(design.thresholds["minimum_search_contextual_fallback_gain"]),
        "search_retains_method_headroom": overall["search_contextual_fallback_error"]
        >= float(design.thresholds["minimum_remaining_search_error"]),
        "unobserved_location_dynamics_are_nontrivial": overall["unobserved_location_change_rate"]
        >= float(design.thresholds["minimum_unobserved_location_change_rate"]),
    }
    gate_passed = all(criteria.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "generator_protocol": GENERATOR_PROTOCOL_ID,
        "evidence_status": (
            "method-free D0 validation-world target-structure gate; no method was run"
        ),
        "manifest_frozen_before_first_run": True,
        "sealed_holdout_opened": False,
        "raw_holdout_world_seeds_disclosed": False,
        "method_comparison_executed": False,
        "randomness_hierarchy": ["world_seed", "trajectory_seed", "observation_seed"],
        "split_unit": "world_seed",
        "validation_world_count": len(worlds),
        "trajectory_count_per_world": len(design.trajectory_seeds),
        "observation_replicates_per_trajectory": len(design.observation_seeds),
        "rollout_count": len(readings),
        "unique_world_hash_count": len({world.world_hash for world in worlds}),
        "unique_validation_world_fraction": unique_fraction,
        "validation_world_parameter_summaries": [
            {
                "world_hash": world.world_hash,
                "duration_days": world.duration_days,
                "location_count": len(world.locations),
                "guest_actor_count": len(world.guest_actors),
                "abrupt_day": world.abrupt_day,
                "recurrence_day": world.recurrence_day,
            }
            for world in worlds
        ],
        "overall_world_weighted_metrics": overall,
        "put_back_aggregation_gain": {
            "mean": mean(aggregation_gains),
            "world_bootstrap_ci_95": aggregation_ci,
        },
        "put_back_context_gain": {
            "mean": mean(context_gains),
            "world_bootstrap_ci_95": context_ci,
        },
        "search_contextual_fallback_gain": {
            "mean": mean(search_gains),
            "world_bootstrap_ci_95": search_ci,
        },
        "world_metrics": {str(key): value for key, value in world_means.items()},
        "thresholds": dict(design.thresholds),
        "criteria": criteria,
        "gate_a_passed": gate_passed,
        "method_comparison_allowed": gate_passed,
        "provenance": {
            "manifest_sha256": design.manifest_sha256,
            "generator_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
            ),
            "gate_source_sha256": _file_sha256(Path(__file__).resolve()),
        },
        "limitations": [
            (
                "D0 distributions and thresholds are author-selected and lack "
                "real-household grounding."
            ),
            "Gate A passing would establish target headroom, not method effectiveness.",
            "No train or sealed holdout world was generated or scored in this run.",
            (
                "Direct identity, cause, regime, and event-chain endpoint gates remain "
                "required before method comparison."
            ),
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_structure_two_world_gate_a_report(
    report: Mapping[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_structure_two_world_gate_a_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("world Gate A report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("world Gate A report protocol mismatch")
    design = load_frozen_world_gate_design(repository_root / DEFAULT_MANIFEST)
    expected_provenance = {
        "manifest_sha256": design.manifest_sha256,
        "generator_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py"
        ),
        "gate_source_sha256": _file_sha256(Path(__file__).resolve()),
    }
    if report.get("provenance") != expected_provenance:
        raise ValueError("world Gate A report provenance mismatch")
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("world Gate A criteria are missing")
    expected_gate = all(value is True for value in criteria.values())
    if report.get("gate_a_passed") != expected_gate:
        raise ValueError("world Gate A decision mismatch")
    if report.get("method_comparison_allowed") != expected_gate:
        raise ValueError("method-comparison authorization mismatch")
    if report.get("sealed_holdout_opened") is not False:
        raise ValueError("world Gate A illegally opened sealed holdout")
    if recompute:
        expected = run_structure_two_world_gate_a(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("world Gate A deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "FrozenWorldGateDesign",
    "RolloutGateReading",
    "evaluate_rollout_gate_a",
    "load_frozen_world_gate_design",
    "run_structure_two_world_gate_a",
    "verify_structure_two_world_gate_a_report",
    "write_structure_two_world_gate_a_report",
]
