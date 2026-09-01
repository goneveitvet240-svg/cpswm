"""Interactive CIAV development test over the project-two replay environment.

Every policy first receives the ordinary robot-visible stream.  Only after it
chooses a registered micro-verification action does the evaluator-only outcome
simulator read hidden actor truth and return a noisy result.  That result may
update the reversible fast-action ledger, but never the long-term statistics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from statistics import mean
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts import (
    ObservationActionCandidate,
    ObservationActionType,
    ProjectTwoDatasetSplit,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionReadout,
    ActionReadoutConfig,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
    ActorEvidenceStress,
    _stress_transform,
)
from cpswm.world_model.grounded_search import (
    CauseInformationActiveVerificationPlanner,
    StructureTwoCauseBelief,
    VerificationBaselinePolicy,
    VerificationCause,
    select_verification_baseline,
    verification_cause_hypothesis_id,
)


class InteractiveVerificationPolicy(StrEnum):
    NEVER_ACT = "never_act"
    ALWAYS_VERIFY = "always_verify"
    RANDOM = "random"
    MAX_ENTROPY = "max_entropy"
    CIAV = "ciav"


SEARCH_SPACE: dict[InteractiveVerificationPolicy, tuple[dict[str, float], ...]] = {
    policy: (
        {"max_verifications": 2.0},
        {"max_verifications": 4.0},
        {"max_verifications": 8.0},
    )
    for policy in InteractiveVerificationPolicy
}
SEARCH_SPACE[InteractiveVerificationPolicy.CIAV] = (
    {"max_verifications": 4.0, "minimum_attribution_shift": 0.25},
    {"max_verifications": 4.0, "minimum_attribution_shift": 0.50},
    {"max_verifications": 4.0, "minimum_attribution_shift": 0.75},
)


@dataclass(frozen=True, slots=True)
class _OutcomeModel:
    sensitivity: float
    specificity: float


@dataclass(frozen=True, slots=True)
class InteractiveVerificationCase:
    put_back_error_rate: float
    cumulative_action_regret: float
    owner_habit_contamination: float
    incorrect_statistic_recovery_cost: float
    verification_count: int
    verification_total_cost: float
    privacy_cost: float
    fast_ledger_updates: int
    mean_net_utility_per_step: float


_QUICK_ACTION_ID = uuid5(NAMESPACE_URL, "cpswm-ciav-quick-owner-check@0.1")
_IDENTITY_ACTION_ID = uuid5(NAMESPACE_URL, "cpswm-ciav-identity-owner-check@0.1")
_OUTCOME_MODELS = {
    _QUICK_ACTION_ID: _OutcomeModel(sensitivity=0.80, specificity=0.80),
    _IDENTITY_ACTION_ID: _OutcomeModel(sensitivity=0.92, specificity=0.92),
}


def _actions(*, cost_multiplier: float = 1.0) -> tuple[ObservationActionCandidate, ...]:
    if cost_multiplier < 0.0:
        raise ValueError("cost_multiplier must be non-negative")
    hypothesis_ids = {cause: verification_cause_hypothesis_id(cause) for cause in VerificationCause}

    def candidate(
        *,
        action_id: UUID,
        label: str,
        owner_likelihood: dict[VerificationCause, float],
        costs: tuple[float, float, float, float, float],
    ) -> ObservationActionCandidate:
        return ObservationActionCandidate(
            action_id=action_id,
            action_type=ObservationActionType.MICRO_VERIFY,
            label=label,
            observation_likelihood_model_id=f"{label.replace(' ', '-')}@0.1",
            calibration_domain="D0-interactive-verification-development",
            outcome_likelihoods={
                "owner_supported": {
                    hypothesis_ids[cause]: probability
                    for cause, probability in owner_likelihood.items()
                },
                "owner_rejected": {
                    hypothesis_ids[cause]: 1.0 - probability
                    for cause, probability in owner_likelihood.items()
                },
            },
            motion_cost=cost_multiplier * costs[0],
            time_cost=cost_multiplier * costs[1],
            interruption_cost=cost_multiplier * costs[2],
            privacy_cost=cost_multiplier * costs[3],
            safety_cost=cost_multiplier * costs[4],
        )

    return (
        candidate(
            action_id=_QUICK_ACTION_ID,
            label="quick owner check",
            owner_likelihood={
                VerificationCause.OBSERVATION: 0.45,
                VerificationCause.ACTOR: 0.20,
                VerificationCause.HABIT: 0.80,
                VerificationCause.NOISE: 0.50,
                VerificationCause.IDENTITY: 0.25,
                VerificationCause.UNRESOLVED: 0.50,
            },
            costs=(0.02, 0.04, 0.01, 0.02, 0.0),
        ),
        candidate(
            action_id=_IDENTITY_ACTION_ID,
            label="identity aware owner check",
            owner_likelihood={
                VerificationCause.OBSERVATION: 0.40,
                VerificationCause.ACTOR: 0.08,
                VerificationCause.HABIT: 0.82,
                VerificationCause.NOISE: 0.45,
                VerificationCause.IDENTITY: 0.05,
                VerificationCause.UNRESOLVED: 0.50,
            },
            costs=(0.02, 0.06, 0.04, 0.15, 0.0),
        ),
    )


def _terminal_utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return {
        decision: {
            hypothesis: 1.0 if hypothesis == decision else -0.25 for hypothesis in hypotheses
        }
        for decision in hypotheses
    }


def _consolidation_utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = {cause: verification_cause_hypothesis_id(cause) for cause in VerificationCause}
    commit = uuid5(NAMESPACE_URL, "cpswm-ciav-commit")
    quarantine = uuid5(NAMESPACE_URL, "cpswm-ciav-quarantine")
    retract = uuid5(NAMESPACE_URL, "cpswm-ciav-retract")
    return {
        commit: {
            hypothesis: 1.0 if cause is VerificationCause.HABIT else -0.8
            for cause, hypothesis in hypotheses.items()
        },
        quarantine: dict.fromkeys(hypotheses.values(), 0.15),
        retract: {
            hypothesis: (
                0.8
                if cause
                in {
                    VerificationCause.OBSERVATION,
                    VerificationCause.ACTOR,
                    VerificationCause.NOISE,
                    VerificationCause.IDENTITY,
                }
                else -0.4
            )
            for cause, hypothesis in hypotheses.items()
        },
    }


def _select_action(
    policy: InteractiveVerificationPolicy,
    belief: StructureTwoCauseBelief,
    actions: tuple[ObservationActionCandidate, ...],
    *,
    owner_prior: float,
    outcome_models: dict[UUID, _OutcomeModel],
    minimum_attribution_shift: float,
    privacy_budget: float,
    random_seed: int,
) -> tuple[UUID | None, float]:
    if policy is InteractiveVerificationPolicy.CIAV:
        plan = CauseInformationActiveVerificationPlanner().select(
            belief,
            actions,
            consolidation_decision_utilities=_consolidation_utilities(),
            terminal_decision_utilities=_terminal_utilities(),
            privacy_budget=privacy_budget,
            minimum_net_value=0.0,
        )
        # PCHMP can be confidently wrong under actor-evidence shift.  CIAV uses
        # CF-BOCPD's actor/identity cause mass to widen that confidence toward
        # 0.5, then asks whether a registered observation can actually change
        # the binary fast-ledger inclusion decision.  Cause information is a
        # small tie-breaking benefit; it cannot by itself justify a costly act.
        attribution_shift = min(
            0.8,
            belief.posterior[VerificationCause.ACTOR]
            + belief.posterior[VerificationCause.IDENTITY],
        )
        robust_owner_prior = (1.0 - attribution_shift) * owner_prior + attribution_shift * 0.5
        if attribution_shift < minimum_attribution_shift:
            return None, robust_owner_prior
        action_by_id = {action.action_id: action for action in actions}
        candidates = []
        for score in plan.scores:
            action = action_by_id[score.action_id]
            if action.privacy_cost > privacy_budget:
                continue
            decision_value = _binary_decision_value_of_information(
                robust_owner_prior,
                outcome_models[action.action_id],
            )
            action_net = (
                decision_value + 0.1 * score.expected_cause_information_gain - score.total_cost
            )
            candidates.append((action_net, str(action.action_id), action.action_id))
        if not candidates:
            return None, robust_owner_prior
        best = max(candidates, key=lambda item: (item[0], item[1]))
        return (best[2] if best[0] > 0.0 else None), robust_owner_prior
    else:
        baseline = VerificationBaselinePolicy(policy.value)
        plan = select_verification_baseline(
            baseline,
            belief.as_uuid_prior(),
            actions,
            privacy_budget=privacy_budget,
            random_seed=random_seed,
        )
    return (plan.selected_action_id if plan.should_act else None), owner_prior


def _binary_decision_value_of_information(prior: float, model: _OutcomeModel) -> float:
    """Expected reduction in owner/non-owner Bayes decision error."""

    positive = prior * model.sensitivity + (1.0 - prior) * (1.0 - model.specificity)
    negative = 1.0 - positive
    positive_posterior = _owner_posterior_after_verification(
        prior,
        outcome="owner_supported",
        model=model,
    )
    negative_posterior = _owner_posterior_after_verification(
        prior,
        outcome="owner_rejected",
        model=model,
    )
    posterior_risk = positive * min(positive_posterior, 1.0 - positive_posterior)
    posterior_risk += negative * min(negative_posterior, 1.0 - negative_posterior)
    return max(0.0, min(prior, 1.0 - prior) - posterior_risk)


def _potential_outcome(
    *,
    episode_id: UUID,
    step_id: UUID,
    action_id: UUID,
    true_owner: bool,
    model: _OutcomeModel,
) -> tuple[str, UUID]:
    """Evaluator-only noisy outcome; policy identity is deliberately absent."""

    digest = hashlib.sha256(f"{episode_id}:{step_id}:{action_id}".encode()).digest()
    draw = int.from_bytes(digest[:8], "big") / float(2**64)
    probability = model.sensitivity if true_owner else 1.0 - model.specificity
    label = "owner_supported" if draw < probability else "owner_rejected"
    source_record_id = uuid5(NAMESPACE_URL, f"ciav-outcome:{episode_id}:{step_id}:{action_id}")
    return label, source_record_id


def _owner_posterior_after_verification(
    prior: float,
    *,
    outcome: str,
    model: _OutcomeModel,
) -> float:
    if outcome == "owner_supported":
        numerator = prior * model.sensitivity
        denominator = numerator + (1.0 - prior) * (1.0 - model.specificity)
    else:
        numerator = prior * (1.0 - model.sensitivity)
        denominator = numerator + (1.0 - prior) * model.specificity
    return numerator / denominator if denominator > 0.0 else prior


def _evaluate_case(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    policy: InteractiveVerificationPolicy,
    *,
    max_verifications: int,
    stress: ActorEvidenceStress,
    minimum_attribution_shift: float = 0.0,
    privacy_budget_per_episode: float = 0.50,
    quick_sensitivity: float = 0.80,
    quick_specificity: float = 0.80,
    identity_sensitivity: float = 0.92,
    identity_specificity: float = 0.92,
    cost_multiplier: float = 1.0,
) -> InteractiveVerificationCase:
    probabilities = (
        quick_sensitivity,
        quick_specificity,
        identity_sensitivity,
        identity_specificity,
    )
    if any(not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError("verification sensitivity and specificity must lie in [0, 1]")
    transform = _stress_transform(
        stress,
        owner_key=episode.owner_actor_key,
        stress_namespace=episode.scene_id,
    )
    state = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        evidence_transform=transform,
        action_readout=ActionReadoutConfig(
            readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
            hybrid_alpha_weight=0.0,
            fast_action_weight=0.8,
            surviving_revision_weight=0.2,
            regime_local_weight=0.0,
            fast_owner_mass_floor=0.5,
        ),
    )
    truth = dataset.truth_for(episode.episode_id)
    actions = _actions(cost_multiplier=cost_multiplier)
    outcome_models = {
        _QUICK_ACTION_ID: _OutcomeModel(
            sensitivity=quick_sensitivity,
            specificity=quick_specificity,
        ),
        _IDENTITY_ACTION_ID: _OutcomeModel(
            sensitivity=identity_sensitivity,
            specificity=identity_specificity,
        ),
    }
    by_id = {action.action_id: action for action in actions}
    predictions = []
    verification_count = 0
    total_cost = 0.0
    privacy_cost = 0.0
    fast_updates = 0
    for step_index, step in enumerate(episode.steps):
        state.observe(step)
        result = state.step_results.get(step.step_id)
        cause_snapshot = state.spine.current_cause_snapshot
        if (
            result is not None
            and cause_snapshot is not None
            and verification_count < max_verifications
        ):
            # This replay contract has no independent identity-switch channel.
            # Open-world ``unknown_actor`` mass is evidence for a stranger, not
            # evidence that a known identity was switched, so it must not be
            # repurposed as an identity proxy.  The identity branch remains in
            # CIAV but is explicitly unobserved in this development adapter.
            identity_uncertainty = 0.0
            belief = StructureTwoCauseBelief.from_snapshot(
                cause_snapshot,
                identity_switch_probability=identity_uncertainty,
            )
            remaining_privacy = privacy_budget_per_episode - privacy_cost
            owner_prior = result.actor_posterior.get(episode.owner_actor_key, 0.0)
            action_id, verification_prior = _select_action(
                policy,
                belief,
                actions,
                owner_prior=owner_prior,
                outcome_models=outcome_models,
                minimum_attribution_shift=minimum_attribution_shift,
                privacy_budget=max(0.0, remaining_privacy),
                random_seed=int.from_bytes(step.step_id.bytes[:8], "big") + step_index,
            )
            if action_id is not None:
                action = by_id[action_id]
                target = truth.truth_by_step[step.step_id]
                outcome, source_record_id = _potential_outcome(
                    episode_id=episode.episode_id,
                    step_id=step.step_id,
                    action_id=action_id,
                    true_owner=target.true_actor == episode.owner_actor_key,
                    model=outcome_models[action_id],
                )
                owner_after = _owner_posterior_after_verification(
                    verification_prior,
                    outcome=outcome,
                    model=outcome_models[action_id],
                )
                receipt = state.spine.apply_fast_action_verification(
                    revision_id=result.event_revision_id,
                    verified_owner_probability=owner_after,
                    source_record_id=source_record_id,
                )
                verification_count += 1
                fast_updates += int(receipt.changed)
                action_cost = (
                    action.motion_cost
                    + action.time_cost
                    + action.interruption_cost
                    + action.privacy_cost
                    + action.safety_cost
                )
                total_cost += action_cost
                privacy_cost += action.privacy_cost
        predictions.append(state.predict())
        state.feedback(step)
    evaluator = ProjectTwoActionBenchmarkV02()
    metric = evaluator._score_predictions(
        dataset=dataset,
        episode=episode,
        method=ProjectTwoActionMethod.PROJECT_TWO,
        predictions=predictions,
        stats=(
            state.revision_calls,
            state.project_one_requests,
            state.project_one_applications,
            state.rejected_feedback,
            state.unnecessary_revisions,
            state.project_one_rejections,
            state.project_one_deferred,
            state.project_one_replay_noops,
            tuple(state.revision_action_traces),
        ),
    )
    step_count = max(metric.step_count, 1)
    return InteractiveVerificationCase(
        put_back_error_rate=metric.put_back_error_rate,
        cumulative_action_regret=metric.cumulative_action_regret,
        owner_habit_contamination=metric.owner_habit_contamination,
        incorrect_statistic_recovery_cost=metric.incorrect_statistic_recovery_cost,
        verification_count=verification_count,
        verification_total_cost=total_cost,
        privacy_cost=privacy_cost,
        fast_ledger_updates=fast_updates,
        mean_net_utility_per_step=(
            2.0 - metric.cumulative_action_regret / step_count - total_cost / step_count
        ),
    )


def _summarize(cases: list[InteractiveVerificationCase]) -> dict[str, float]:
    names = InteractiveVerificationCase.__dataclass_fields__
    return {name: mean(getattr(case, name) for case in cases) for name in names}


def run_ciav_interactive_development(
    *,
    validation_seeds: tuple[int, ...],
    holdout_seeds: tuple[int, ...],
    max_steps: int = 32,
) -> dict[str, object]:
    if set(validation_seeds) & set(holdout_seeds):
        raise ValueError("development validation and holdout seeds must be disjoint")
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=holdout_seeds,
        max_steps_per_episode=max_steps,
    ).build()
    validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    holdout = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    cells: dict[str, object] = {}
    for stress in ActorEvidenceStress:
        selected: dict[InteractiveVerificationPolicy, dict[str, float]] = {}
        validation_rows: dict[str, list[dict[str, float]]] = {}
        for policy in InteractiveVerificationPolicy:
            rows = []
            candidates = []
            for parameters in SEARCH_SPACE[policy]:
                cases = [
                    _evaluate_case(
                        dataset,
                        episode,
                        policy,
                        max_verifications=int(parameters["max_verifications"]),
                        minimum_attribution_shift=float(
                            parameters.get("minimum_attribution_shift", 0.0)
                        ),
                        stress=stress,
                    )
                    for episode in validation
                ]
                score = mean(case.mean_net_utility_per_step for case in cases)
                rows.append({**parameters, "mean_net_utility_per_step": score})
                candidates.append((score, -parameters["max_verifications"], parameters))
            selected[policy] = max(candidates, key=lambda item: (item[0], item[1]))[2]
            validation_rows[policy.value] = rows
        holdout_results = {}
        for policy in InteractiveVerificationPolicy:
            cases = [
                _evaluate_case(
                    dataset,
                    episode,
                    policy,
                    max_verifications=int(selected[policy]["max_verifications"]),
                    minimum_attribution_shift=float(
                        selected[policy].get("minimum_attribution_shift", 0.0)
                    ),
                    stress=stress,
                )
                for episode in holdout
            ]
            holdout_results[policy.value] = _summarize(cases)
        cells[stress.value] = {
            "selected_parameters": {
                policy.value: parameters for policy, parameters in selected.items()
            },
            "validation_scores": validation_rows,
            "holdout_results": holdout_results,
        }
    action_payload = tuple(
        (str(action.action_id), action.model_dump(mode="json")) for action in _actions()
    )
    return {
        "protocol": "project-two-ciav-interactive-development@0.1",
        "evidence_status": "post-diagnostic synthetic development; not confirmatory",
        "validation_seeds": list(validation_seeds),
        "holdout_seeds": list(holdout_seeds),
        "max_steps": max_steps,
        "search_budget_per_policy_per_cell": 3,
        "same_action_set_and_outcome_model": True,
        "truth_released_only_after_selected_action": True,
        "privacy_budget_per_episode": 0.5,
        "action_set_sha256": hashlib.sha256(repr(action_payload).encode()).hexdigest(),
        "outcome_models": {
            str(action_id): {
                "sensitivity": model.sensitivity,
                "specificity": model.specificity,
            }
            for action_id, model in _OUTCOME_MODELS.items()
        },
        "cells": cells,
    }


__all__ = [
    "SEARCH_SPACE",
    "InteractiveVerificationPolicy",
    "run_ciav_interactive_development",
]
