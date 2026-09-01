"""Post-diagnostic development benchmark for structure-two action readouts.

This module intentionally does not reuse the 2026-08-26 sealed households.  It
compares the explicit latest-owner control, the frozen v0.3 slow readout, and a
dual-timescale reversible readout on fresh development seeds.  Actor-evidence
stress cells are deterministic transformations of robot-visible posteriors; no
evaluator truth is read by a method or by a transformation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from enum import StrEnum
from statistics import mean
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayStep
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ActionReadout,
    ActionReadoutConfig,
    ProjectTwoActionBenchmarkV02,
    _AMGOpenWorldMethod,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)


class ActorEvidenceStress(StrEnum):
    CLEAN = "clean"
    AMBIGUOUS = "ambiguous"
    SYMMETRIC_MISATTRIBUTION = "symmetric_misattribution"


class DualTimescaleArm(StrEnum):
    AMG = "amg_matched_open_world"
    LATEST_OWNER = "pchmp_latest_owner"
    SLOW_REVERSIBLE = "surviving_owner_revisions"
    DUAL_TIMESCALE = "dual_timescale_reversible"


READOUT_SEARCH_SPACE: dict[DualTimescaleArm, tuple[dict[str, float | str], ...]] = {
    DualTimescaleArm.AMG: (
        {"parameter": 0.2},
        {"parameter": 0.33},
        {"parameter": 0.5},
    ),
    DualTimescaleArm.LATEST_OWNER: (
        {"fast_owner_mass_floor": 0.4},
        {"fast_owner_mass_floor": 0.5},
        {"fast_owner_mass_floor": 0.6},
    ),
    DualTimescaleArm.SLOW_REVERSIBLE: (
        {"owner_mass_floor": 0.4, "recency_half_life": 0.5},
        {"owner_mass_floor": 0.5, "recency_half_life": 1.0},
        {"owner_mass_floor": 0.6, "recency_half_life": 2.0},
    ),
    DualTimescaleArm.DUAL_TIMESCALE: (
        {
            "fast_action_weight": 0.8,
            "surviving_revision_weight": 0.2,
            "regime_local_weight": 0.0,
            "fast_owner_mass_floor": 0.5,
        },
        {
            "fast_action_weight": 0.7,
            "surviving_revision_weight": 0.2,
            "regime_local_weight": 0.1,
            "fast_owner_mass_floor": 0.5,
        },
        {
            "fast_action_weight": 0.6,
            "surviving_revision_weight": 0.2,
            "regime_local_weight": 0.2,
            "fast_owner_mass_floor": 0.6,
        },
    ),
}


def _stress_transform(
    stress: ActorEvidenceStress,
    *,
    owner_key: str,
    stress_namespace: str,
) -> Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep]:
    def transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
        evidence = step.actor_evidence
        if evidence is None or stress is ActorEvidenceStress.CLEAN:
            return step
        posterior = dict(evidence.actor_posterior)
        prior = dict(evidence.reference_actor_prior)
        update: dict[str, object] = {}
        if stress is ActorEvidenceStress.AMBIGUOUS:
            posterior = {actor: 0.5 * posterior[actor] + 0.5 * prior[actor] for actor in posterior}
            if step.ordered_role_evidence is not None:
                role = step.ordered_role_evidence
                role_posterior = {
                    key: 0.5 * value + 0.5 * role.reference_ordered_role_prior[key]
                    for key, value in role.ordered_role_posterior.items()
                }
                update["ordered_role_evidence"] = role.model_copy(
                    update={"ordered_role_posterior": role_posterior}
                )
        else:
            stable_key = f"{stress_namespace}|{step.timestamp.isoformat()}".encode()
            draw = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big") / float(2**64)
            if draw < 0.15:
                known_other = sorted(
                    actor for actor in posterior if actor not in {owner_key, "unknown_actor"}
                )
                if known_other:
                    other = known_other[0]
                    posterior[owner_key], posterior[other] = (
                        posterior[other],
                        posterior[owner_key],
                    )
                    if step.ordered_role_evidence is not None:
                        role = step.ordered_role_evidence
                        update["ordered_role_evidence"] = role.model_copy(
                            update={
                                "ordered_role_posterior": dict(role.reference_ordered_role_prior)
                            }
                        )
        update["actor_evidence"] = evidence.model_copy(update={"actor_posterior": posterior})
        return step.model_copy(update=update)

    return transform


class _TransformedState:
    """Apply one registered visible-evidence transform to any replay method."""

    def __init__(
        self,
        state: Any,
        transform: Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep],
    ) -> None:
        self._state = state
        self._transform = transform

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(self._transform(step))

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(self._transform(step))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _state(
    episode: Any,
    arm: DualTimescaleArm,
    parameters: Mapping[str, float | str],
    stress: ActorEvidenceStress,
) -> Any:
    transform = _stress_transform(
        stress,
        owner_key=episode.owner_actor_key,
        stress_namespace=episode.scene_id,
    )
    if arm is DualTimescaleArm.AMG:
        return _TransformedState(
            _AMGOpenWorldMethod(
                episode,
                mode="amg",
                parameter=float(parameters["parameter"]),
            ),
            transform,
        )
    if arm is DualTimescaleArm.LATEST_OWNER:
        readout = ActionReadoutConfig(
            readout=ActionReadout.LATEST_OWNER_EVENT,
            fast_owner_mass_floor=float(parameters["fast_owner_mass_floor"]),
        )
    elif arm is DualTimescaleArm.SLOW_REVERSIBLE:
        readout = ActionReadoutConfig(
            readout=ActionReadout.SURVIVING_OWNER_REVISIONS,
            owner_mass_floor=float(parameters["owner_mass_floor"]),
            recency_half_life=float(parameters["recency_half_life"]),
        )
    else:
        readout = ActionReadoutConfig(
            readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
            hybrid_alpha_weight=0.0,
            fast_action_weight=float(parameters["fast_action_weight"]),
            surviving_revision_weight=float(parameters["surviving_revision_weight"]),
            regime_local_weight=float(parameters["regime_local_weight"]),
            fast_owner_mass_floor=float(parameters["fast_owner_mass_floor"]),
            fast_confirmation_observations=int(
                float(parameters.get("fast_confirmation_observations", 1.0))
            ),
            unconfirmed_fast_discount=float(parameters.get("unconfirmed_fast_discount", 1.0)),
            owner_mass_floor=0.5,
            recency_half_life=1.0,
        )
    return _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=readout,
        evidence_transform=transform,
    )


def _summary(cases: list[ActionCaseMetric]) -> dict[str, float]:
    return {
        "put_back_error_rate": mean(item.put_back_error_rate for item in cases),
        "cumulative_action_regret": mean(item.cumulative_action_regret for item in cases),
        "owner_habit_contamination": mean(item.owner_habit_contamination for item in cases),
        "incorrect_statistic_recovery_cost": mean(
            item.incorrect_statistic_recovery_cost for item in cases
        ),
        "unknown_calibration_brier": mean(item.unknown_calibration_brier for item in cases),
    }


def run_dual_timescale_development(
    *,
    validation_seeds: tuple[int, ...],
    holdout_seeds: tuple[int, ...],
    max_steps: int = 32,
) -> dict[str, object]:
    """Tune on fresh validation seeds and score once on fresh development holdout."""

    if set(validation_seeds) & set(holdout_seeds):
        raise ValueError("development validation and holdout seeds must be disjoint")
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=holdout_seeds,
        max_steps_per_episode=max_steps,
    ).build()
    validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    holdout = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    evaluator = ProjectTwoActionBenchmarkV02()
    cells: dict[str, object] = {}
    for stress in ActorEvidenceStress:
        selected: dict[DualTimescaleArm, Mapping[str, float | str]] = {}
        validation_scores: dict[str, list[dict[str, object]]] = {}
        for arm in DualTimescaleArm:
            candidates: list[tuple[float, str, Mapping[str, float | str]]] = []
            rows: list[dict[str, object]] = []
            for parameters in READOUT_SEARCH_SPACE[arm]:
                cases = [
                    evaluator.evaluate_custom_state(
                        dataset,
                        episode,
                        _state(episode, arm, parameters, stress),
                    )
                    for episode in validation
                ]
                score = mean(item.put_back_error_rate for item in cases)
                fingerprint = repr(sorted(parameters.items()))
                candidates.append((score, fingerprint, parameters))
                rows.append({"parameters": dict(parameters), "put_back_error_rate": score})
            selected[arm] = min(candidates, key=lambda item: (item[0], item[1]))[2]
            validation_scores[arm.value] = rows
        holdout_cases: dict[DualTimescaleArm, list[ActionCaseMetric]] = {}
        for arm in DualTimescaleArm:
            holdout_cases[arm] = [
                evaluator.evaluate_custom_state(
                    dataset,
                    episode,
                    _state(episode, arm, selected[arm], stress),
                )
                for episode in holdout
            ]
        amg = holdout_cases[DualTimescaleArm.AMG]
        results: dict[str, object] = {}
        for arm, cases in holdout_cases.items():
            result = _summary(cases)
            result["paired_put_back_difference_vs_amg"] = mean(
                case.put_back_error_rate - baseline.put_back_error_rate
                for case, baseline in zip(cases, amg, strict=True)
            )
            results[arm.value] = result
        cells[stress.value] = {
            "selected_parameters": {arm.value: dict(value) for arm, value in selected.items()},
            "validation_scores": validation_scores,
            "holdout_results": results,
        }
    return {
        "protocol": "project-two-dual-timescale-development@0.1",
        "evidence_status": "post-diagnostic development; not confirmatory",
        "validation_seeds": list(validation_seeds),
        "holdout_seeds": list(holdout_seeds),
        "max_steps": max_steps,
        "actor_evidence_stress": {
            "ambiguous": "50% posterior plus 50% registered reference prior",
            "symmetric_misattribution": (
                "deterministic 15% owner/known-guest posterior swap keyed only by step id"
            ),
        },
        "same_visible_stream_and_action_evaluator": True,
        "search_budget_per_arm_per_cell": 3,
        "cells": cells,
    }


__all__ = [
    "READOUT_SEARCH_SPACE",
    "ActorEvidenceStress",
    "DualTimescaleArm",
    "run_dual_timescale_development",
]
