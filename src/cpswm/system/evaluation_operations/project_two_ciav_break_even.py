"""Preregistered CIAV accuracy--cost break-even surface."""

from __future__ import annotations

from statistics import mean
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_ciav_interactive_development import (
    InteractiveVerificationCase,
    InteractiveVerificationPolicy,
    _evaluate_case,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
    ActorEvidenceStress,
)

ACCURACY_LEVELS = (0.75, 0.85, 0.95)
COST_MULTIPLIERS = (0.25, 0.50, 0.75, 1.00)
PRACTICAL_MAX_ACCURACY = 0.85
PRACTICAL_MIN_COST_MULTIPLIER = 0.50
CLEAN_AMBIGUOUS_NET_TOLERANCE = -0.0025


def _summary(cases: list[InteractiveVerificationCase]) -> dict[str, float]:
    return {
        name: mean(getattr(case, name) for case in cases)
        for name in InteractiveVerificationCase.__dataclass_fields__
    }


def _delta(ciav: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    return {
        "net_utility_delta": (
            ciav["mean_net_utility_per_step"] - baseline["mean_net_utility_per_step"]
        ),
        "put_back_error_delta": ciav["put_back_error_rate"] - baseline["put_back_error_rate"],
        "contamination_delta": (
            ciav["owner_habit_contamination"] - baseline["owner_habit_contamination"]
        ),
    }


def _point_passes(deltas: dict[str, dict[str, float]]) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    shifted = deltas[ActorEvidenceStress.SYMMETRIC_MISATTRIBUTION.value]
    if shifted["net_utility_delta"] <= 0.0:
        failures.append("misattribution_net_utility_not_positive")
    if shifted["put_back_error_delta"] > 1e-12:
        failures.append("misattribution_put_back_error_worse")
    if shifted["contamination_delta"] > 1e-12:
        failures.append("misattribution_contamination_worse")
    for stress in (ActorEvidenceStress.CLEAN, ActorEvidenceStress.AMBIGUOUS):
        values = deltas[stress.value]
        if values["put_back_error_delta"] > 1e-12:
            failures.append(f"{stress.value}_put_back_error_worse")
        if values["contamination_delta"] > 1e-12:
            failures.append(f"{stress.value}_contamination_worse")
        if values["net_utility_delta"] < CLEAN_AMBIGUOUS_NET_TOLERANCE:
            failures.append(f"{stress.value}_net_utility_below_tolerance")
    return not failures, tuple(failures)


def run_ciav_accuracy_cost_break_even(
    *,
    evaluation_seeds: tuple[int, ...],
    max_steps: int = 32,
) -> dict[str, Any]:
    if not evaluation_seeds:
        raise ValueError("evaluation_seeds must be non-empty")
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=evaluation_seeds,
        test_seeds=(max(evaluation_seeds) + 1000,),
        max_steps_per_episode=max_steps,
    ).build()
    episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    baseline: dict[str, dict[str, float]] = {}
    for stress in ActorEvidenceStress:
        baseline[stress.value] = _summary(
            [
                _evaluate_case(
                    dataset,
                    episode,
                    InteractiveVerificationPolicy.NEVER_ACT,
                    max_verifications=0,
                    stress=stress,
                )
                for episode in episodes
            ]
        )

    points: list[dict[str, Any]] = []
    for accuracy in ACCURACY_LEVELS:
        identity_accuracy = min(0.99, accuracy + 0.12)
        for cost_multiplier in COST_MULTIPLIERS:
            results: dict[str, dict[str, float]] = {}
            deltas: dict[str, dict[str, float]] = {}
            for stress in ActorEvidenceStress:
                results[stress.value] = _summary(
                    [
                        _evaluate_case(
                            dataset,
                            episode,
                            InteractiveVerificationPolicy.CIAV,
                            max_verifications=4,
                            minimum_attribution_shift=0.75,
                            stress=stress,
                            quick_sensitivity=accuracy,
                            quick_specificity=accuracy,
                            identity_sensitivity=identity_accuracy,
                            identity_specificity=identity_accuracy,
                            cost_multiplier=cost_multiplier,
                        )
                        for episode in episodes
                    ]
                )
                deltas[stress.value] = _delta(results[stress.value], baseline[stress.value])
            passed, failures = _point_passes(deltas)
            practical = (
                accuracy <= PRACTICAL_MAX_ACCURACY
                and cost_multiplier >= PRACTICAL_MIN_COST_MULTIPLIER
            )
            points.append(
                {
                    "quick_accuracy": accuracy,
                    "identity_accuracy": identity_accuracy,
                    "cost_multiplier": cost_multiplier,
                    "practical_candidate": practical,
                    "passed": passed,
                    "failures": list(failures),
                    "ciav": results,
                    "delta_vs_never_act": deltas,
                }
            )

    practical_passes = [
        point for point in points if point["practical_candidate"] and point["passed"]
    ]
    accuracy_span = {point["quick_accuracy"] for point in practical_passes}
    cost_span = {point["cost_multiplier"] for point in practical_passes}
    direction_gate_passed = (
        len(practical_passes) >= 3 and len(accuracy_span) >= 2 and len(cost_span) >= 2
    )
    break_even_by_accuracy = {
        str(accuracy): max(
            (
                point["cost_multiplier"]
                for point in points
                if point["quick_accuracy"] == accuracy and point["passed"]
            ),
            default=None,
        )
        for accuracy in ACCURACY_LEVELS
    }
    return {
        "protocol": "project-two-ciav-accuracy-cost-break-even@0.1",
        "evidence_status": "preregistered synthetic mechanism falsifier",
        "evaluation_seeds": list(evaluation_seeds),
        "max_steps": max_steps,
        "frozen_ciav": {
            "max_verifications": 4,
            "minimum_attribution_shift": 0.75,
        },
        "accuracy_levels": list(ACCURACY_LEVELS),
        "cost_multipliers": list(COST_MULTIPLIERS),
        "practical_region": {
            "maximum_quick_accuracy": PRACTICAL_MAX_ACCURACY,
            "minimum_cost_multiplier": PRACTICAL_MIN_COST_MULTIPLIER,
        },
        "clean_ambiguous_net_tolerance": CLEAN_AMBIGUOUS_NET_TOLERANCE,
        "baseline_never_act": baseline,
        "points": points,
        "practical_pass_count": len(practical_passes),
        "practical_accuracy_span": sorted(accuracy_span),
        "practical_cost_span": sorted(cost_span),
        "break_even_max_cost_multiplier_by_accuracy": break_even_by_accuracy,
        "direction_gate_passed": direction_gate_passed,
        "decision": (
            "continue_to_larger_confirmation"
            if direction_gate_passed
            else "do_not_scale_ciav_confirmation"
        ),
    }


__all__ = [
    "ACCURACY_LEVELS",
    "COST_MULTIPLIERS",
    "run_ciav_accuracy_cost_break_even",
]
