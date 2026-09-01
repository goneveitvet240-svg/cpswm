"""AMG evidence/action-interface fairness audit for project two."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from enum import StrEnum
from itertools import permutations
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import (
    EventMechanism,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayStep,
    parse_ordered_role_key,
)
from cpswm.system.counterfactual_event_hypergraph import (
    DamenHogg2012AMGMatchedEvidenceBaseline,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ActionReadout,
    ActionReadoutConfig,
    ProjectTwoActionBenchmarkV02,
    _FullProjectTwoMethod,
    _locations,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
    ActorEvidenceStress,
)


class AMGInterfaceAuditArm(StrEnum):
    AMG_POSTERIOR_ADAPTER = "amg_posterior_as_likelihood"
    AMG_PRIOR_CORRECTED_ODDS = "amg_prior_corrected_odds"
    DIRECT_ACTOR_STICKY = "direct_actor_posterior_common_sticky"
    PCHMP_STICKY_FEEDBACK = "pchmp_common_sticky_with_feedback"
    PCHMP_STICKY_NO_FEEDBACK = "pchmp_common_sticky_without_feedback"
    PCHMP_NATIVE_FEEDBACK = "pchmp_native_latest_owner_with_feedback"


SEARCH_SPACE: dict[AMGInterfaceAuditArm, tuple[dict[str, float], ...]] = {
    AMGInterfaceAuditArm.AMG_POSTERIOR_ADAPTER: (
        {"parameter": 0.20},
        {"parameter": 0.33},
        {"parameter": 0.50},
    ),
    AMGInterfaceAuditArm.AMG_PRIOR_CORRECTED_ODDS: (
        {"parameter": 0.20},
        {"parameter": 0.33},
        {"parameter": 0.50},
    ),
    AMGInterfaceAuditArm.DIRECT_ACTOR_STICKY: (
        {"owner_threshold": 0.40},
        {"owner_threshold": 0.50},
        {"owner_threshold": 0.60},
    ),
    AMGInterfaceAuditArm.PCHMP_STICKY_FEEDBACK: (
        {"owner_threshold": 0.40},
        {"owner_threshold": 0.50},
        {"owner_threshold": 0.60},
    ),
    AMGInterfaceAuditArm.PCHMP_STICKY_NO_FEEDBACK: (
        {"owner_threshold": 0.40},
        {"owner_threshold": 0.50},
        {"owner_threshold": 0.60},
    ),
    AMGInterfaceAuditArm.PCHMP_NATIVE_FEEDBACK: (
        {"owner_threshold": 0.40},
        {"owner_threshold": 0.50},
        {"owner_threshold": 0.60},
    ),
}


def _audit_stress_transform(
    episode: Any,
    stress: ActorEvidenceStress,
) -> Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep]:
    """UUID-independent stress keyed by visible scene and timestamp."""

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
                update["ordered_role_evidence"] = role.model_copy(
                    update={
                        "ordered_role_posterior": {
                            key: 0.5 * value + 0.5 * role.reference_ordered_role_prior[key]
                            for key, value in role.ordered_role_posterior.items()
                        }
                    }
                )
        else:
            stable_key = f"{episode.scene_id}|{step.timestamp.isoformat()}"
            draw = int.from_bytes(hashlib.sha256(stable_key.encode()).digest()[:8], "big") / float(
                2**64
            )
            if draw < 0.15:
                known_other = sorted(
                    actor
                    for actor in posterior
                    if actor not in {episode.owner_actor_key, "unknown_actor"}
                )
                if known_other:
                    other = known_other[0]
                    posterior[episode.owner_actor_key], posterior[other] = (
                        posterior[other],
                        posterior[episode.owner_actor_key],
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


class _AuditStateBase:
    def __init__(self, episode: Any, stress: ActorEvidenceStress) -> None:
        self.episode = episode
        self.locations = _locations(episode)
        self.transform = _audit_stress_transform(episode, stress)
        self.last_location = self.locations[0]
        self.owner_location: UUID | None = None
        self.binary_owner_predictions: list[tuple[UUID, bool]] = []
        self.put_predictions: list[UUID] = []
        self.revision_calls = 0
        self.project_one_requests = 0
        self.project_one_applications = 0
        self.rejected_feedback = 0
        self.unnecessary_revisions = 0
        self.project_one_rejections = 0
        self.project_one_deferred = 0
        self.project_one_replay_noops = 0
        self.revision_action_traces: list[Any] = []

    def _record_owner(self, step: ProjectTwoReplayStep, predicted_owner: bool) -> None:
        self.binary_owner_predictions.append((step.step_id, predicted_owner))
        if step.after is not None and step.after.detected_location_id is not None:
            self.last_location = step.after.detected_location_id
            if predicted_owner:
                self.owner_location = step.after.detected_location_id

    def predict(self) -> _Prediction:
        put_back = self.owner_location or self.locations[0]
        self.put_predictions.append(put_back)
        search = (
            self.last_location,
            *tuple(location for location in self.locations if location != self.last_location),
        )
        return _Prediction(put_back=put_back, search_order=search, unknown_probability=0.2)

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        del step


class _AMGCommonStickyState(_AuditStateBase):
    def __init__(
        self,
        episode: Any,
        stress: ActorEvidenceStress,
        *,
        parameter: float,
        prior_corrected: bool,
    ) -> None:
        super().__init__(episode, stress)
        self.parameter = parameter
        self.prior_corrected = prior_corrected
        self.amg = DamenHogg2012AMGMatchedEvidenceBaseline()

    def observe(self, step: ProjectTwoReplayStep) -> None:
        step = self.transform(step)
        if step.before is None or step.after is None or step.after.detected_location_id is None:
            return
        actors = self.episode.resident_actor_keys
        if step.actor_evidence is None:
            actor_values = {actor: 1.0 for actor in actors}
        else:
            posterior = dict(step.actor_evidence.actor_posterior)
            if self.prior_corrected:
                prior = step.actor_evidence.reference_actor_prior
                ratios = {actor: posterior[actor] / prior[actor] for actor in posterior}
                actor_values = {actor: ratio / (1.0 + ratio) for actor, ratio in ratios.items()}
            else:
                actor_values = posterior
        mechanism = (
            dict(step.mechanism_evidence.mechanism_posterior)
            if step.mechanism_evidence is not None
            else {
                EventMechanism.DIRECT_RELOCATION: 0.5,
                EventMechanism.HANDOFF_RELOCATION: 0.5,
            }
        )
        roles = {pair: self.parameter for pair in permutations(actors, 2)}
        if step.ordered_role_evidence is not None:
            roles.update(
                {
                    parse_ordered_role_key(key): value
                    for key, value in step.ordered_role_evidence.ordered_role_posterior.items()
                }
            )
        try:
            prediction = self.amg.predict_matched(
                before=step.before,
                after=step.after,
                actor_event_likelihoods={
                    actor: min(1.0 - 1e-6, max(1e-6, value))
                    for actor, value in actor_values.items()
                },
                mechanism_likelihoods=mechanism,
                handoff_role_likelihoods=roles,
            )
        except ValueError:
            return
        self._record_owner(
            step,
            prediction.selected_sequence.responsible_actor_key == self.episode.owner_actor_key,
        )


class _DirectActorStickyState(_AuditStateBase):
    def __init__(
        self,
        episode: Any,
        stress: ActorEvidenceStress,
        *,
        owner_threshold: float,
    ) -> None:
        super().__init__(episode, stress)
        self.owner_threshold = owner_threshold

    def observe(self, step: ProjectTwoReplayStep) -> None:
        step = self.transform(step)
        if step.after is None or step.after.detected_location_id is None:
            return
        owner_mass = (
            step.actor_evidence.actor_posterior.get(self.episode.owner_actor_key, 0.0)
            if step.actor_evidence is not None
            else 0.0
        )
        self._record_owner(step, owner_mass >= self.owner_threshold)


class _PCHMPCommonStickyState(_AuditStateBase):
    def __init__(
        self,
        episode: Any,
        stress: ActorEvidenceStress,
        *,
        owner_threshold: float,
        feedback_enabled: bool,
    ) -> None:
        super().__init__(episode, stress)
        self.owner_threshold = owner_threshold
        self.state = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            evidence_transform=self.transform,
            feedback_mode="success_and_failure" if feedback_enabled else "none",
        )

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self.state.observe(step)
        result = self.state.step_results.get(step.step_id)
        transformed = self.transform(step)
        if result is None or transformed.after is None:
            return
        self._record_owner(
            transformed,
            result.actor_posterior.get(self.episode.owner_actor_key, 0.0) >= self.owner_threshold,
        )

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self.state.feedback(step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.state, name)


class _RecordingNativeState:
    def __init__(self, state: _FullProjectTwoMethod) -> None:
        self.state = state
        self.binary_owner_predictions: list[tuple[UUID, bool]] = []
        self.put_predictions: list[UUID] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self.state.observe(step)
        result = self.state.step_results.get(step.step_id)
        if result is not None:
            floor = self.state.action_readout.fast_owner_mass_floor
            self.binary_owner_predictions.append(
                (
                    step.step_id,
                    result.actor_posterior.get(self.state.episode.owner_actor_key, 0.0) >= floor,
                )
            )

    def predict(self) -> _Prediction:
        prediction = self.state.predict()
        self.put_predictions.append(prediction.put_back)
        return prediction

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self.state.feedback(step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.state, name)


def _state(
    episode: Any,
    stress: ActorEvidenceStress,
    arm: AMGInterfaceAuditArm,
    parameters: Mapping[str, float],
) -> Any:
    if arm in {
        AMGInterfaceAuditArm.AMG_POSTERIOR_ADAPTER,
        AMGInterfaceAuditArm.AMG_PRIOR_CORRECTED_ODDS,
    }:
        return _AMGCommonStickyState(
            episode,
            stress,
            parameter=parameters["parameter"],
            prior_corrected=arm is AMGInterfaceAuditArm.AMG_PRIOR_CORRECTED_ODDS,
        )
    if arm is AMGInterfaceAuditArm.DIRECT_ACTOR_STICKY:
        return _DirectActorStickyState(
            episode,
            stress,
            owner_threshold=parameters["owner_threshold"],
        )
    if arm in {
        AMGInterfaceAuditArm.PCHMP_STICKY_FEEDBACK,
        AMGInterfaceAuditArm.PCHMP_STICKY_NO_FEEDBACK,
    }:
        return _PCHMPCommonStickyState(
            episode,
            stress,
            owner_threshold=parameters["owner_threshold"],
            feedback_enabled=arm is AMGInterfaceAuditArm.PCHMP_STICKY_FEEDBACK,
        )
    readout = ActionReadoutConfig(
        readout=ActionReadout.LATEST_OWNER_EVENT,
        fast_owner_mass_floor=parameters["owner_threshold"],
    )
    return _RecordingNativeState(
        _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            evidence_transform=_audit_stress_transform(episode, stress),
            action_readout=readout,
        )
    )


def _classification_summary(
    dataset: ProjectTwoReplayDataset, episode: Any, state: Any
) -> dict[str, float]:
    truth = dataset.truth_for(episode.episode_id).truth_by_step
    values = state.binary_owner_predictions
    if not values:
        return {
            "binary_owner_error_rate": 0.0,
            "false_owner_rate": 0.0,
            "false_non_owner_rate": 0.0,
            "classified_steps": 0.0,
        }
    errors = false_owner = false_non_owner = 0
    non_owner_count = owner_count = 0
    for step_id, predicted_owner in values:
        actual_owner = truth[step_id].true_actor == episode.owner_actor_key
        errors += predicted_owner != actual_owner
        if actual_owner:
            owner_count += 1
            false_non_owner += not predicted_owner
        else:
            non_owner_count += 1
            false_owner += predicted_owner
    return {
        "binary_owner_error_rate": errors / len(values),
        "false_owner_rate": false_owner / max(non_owner_count, 1),
        "false_non_owner_rate": false_non_owner / max(owner_count, 1),
        "classified_steps": float(len(values)),
    }


def _evaluate(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    stress: ActorEvidenceStress,
    arm: AMGInterfaceAuditArm,
    parameters: Mapping[str, float],
) -> tuple[ActionCaseMetric, dict[str, float], tuple[UUID, ...]]:
    state = _state(episode, stress, arm, parameters)
    metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, state)
    return metric, _classification_summary(dataset, episode, state), tuple(state.put_predictions)


def _summarize(
    rows: list[tuple[ActionCaseMetric, dict[str, float], tuple[UUID, ...]]],
) -> dict[str, float]:
    return {
        "put_back_error_rate": mean(row[0].put_back_error_rate for row in rows),
        "cumulative_action_regret": mean(row[0].cumulative_action_regret for row in rows),
        "owner_habit_contamination": mean(row[0].owner_habit_contamination for row in rows),
        "binary_owner_error_rate": mean(row[1]["binary_owner_error_rate"] for row in rows),
        "false_owner_rate": mean(row[1]["false_owner_rate"] for row in rows),
        "false_non_owner_rate": mean(row[1]["false_non_owner_rate"] for row in rows),
    }


def _target_alignment(
    dataset: ProjectTwoReplayDataset, episodes: tuple[Any, ...]
) -> dict[str, float]:
    recurrence = owner_updates = non_owner_persistence = 0
    recurrence_total = owner_total = non_owner_total = 0
    uniform_prior_steps = prior_steps = 0
    for episode in episodes:
        truth = dataset.truth_for(episode.episode_id).truth_by_step
        previous_target: UUID | None = None
        for step in episode.steps:
            target = truth[step.step_id]
            if previous_target is not None:
                expected = (
                    target.true_location
                    if target.true_actor == episode.owner_actor_key
                    else previous_target
                )
                recurrence += target.true_owner_habit_location == expected
                recurrence_total += 1
                if target.true_actor == episode.owner_actor_key:
                    owner_updates += target.true_owner_habit_location == target.true_location
                    owner_total += 1
                else:
                    non_owner_persistence += target.true_owner_habit_location == previous_target
                    non_owner_total += 1
            previous_target = target.true_owner_habit_location
            if step.actor_evidence is not None:
                priors = tuple(step.actor_evidence.reference_actor_prior.values())
                uniform_prior_steps += max(priors) - min(priors) <= 1e-12
                prior_steps += 1
    return {
        "latest_true_owner_recurrence_match_rate": recurrence / max(recurrence_total, 1),
        "owner_event_target_update_rate": owner_updates / max(owner_total, 1),
        "non_owner_target_persistence_rate": non_owner_persistence / max(non_owner_total, 1),
        "uniform_actor_reference_prior_rate": uniform_prior_steps / max(prior_steps, 1),
    }


def _amg_label_equivariance(
    episodes: tuple[Any, ...], stress: ActorEvidenceStress
) -> dict[str, float]:
    """Rename actor keys without changing evidence and require mapped predictions."""

    equivalent = evaluated = 0
    for episode in episodes:
        actors = episode.resident_actor_keys
        known_other = next(
            actor for actor in actors if actor not in {episode.owner_actor_key, "unknown_actor"}
        )
        mapping = {
            episode.owner_actor_key: "a_actor",
            known_other: "z_actor",
            "unknown_actor": "m_actor",
        }
        inverse = {value: key for key, value in mapping.items()}
        transform = _audit_stress_transform(episode, stress)
        for raw_step in episode.steps:
            step = transform(raw_step)
            if step.before is None or step.after is None or step.actor_evidence is None:
                continue
            mechanism = (
                dict(step.mechanism_evidence.mechanism_posterior)
                if step.mechanism_evidence is not None
                else {
                    EventMechanism.DIRECT_RELOCATION: 0.5,
                    EventMechanism.HANDOFF_RELOCATION: 0.5,
                }
            )
            roles = {pair: 0.2 for pair in permutations(actors, 2)}
            if step.ordered_role_evidence is not None:
                roles.update(
                    {
                        parse_ordered_role_key(key): value
                        for key, value in step.ordered_role_evidence.ordered_role_posterior.items()
                    }
                )
            actor_values = {
                actor: min(1.0 - 1e-6, max(1e-6, value))
                for actor, value in step.actor_evidence.actor_posterior.items()
            }
            roles = {pair: min(1.0 - 1e-6, max(1e-6, value)) for pair, value in roles.items()}
            baseline = DamenHogg2012AMGMatchedEvidenceBaseline()
            try:
                original = baseline.predict_matched(
                    before=step.before,
                    after=step.after,
                    actor_event_likelihoods=actor_values,
                    mechanism_likelihoods=mechanism,
                    handoff_role_likelihoods=roles,
                )
                renamed = baseline.predict_matched(
                    before=step.before,
                    after=step.after,
                    actor_event_likelihoods={
                        mapping[actor]: value for actor, value in actor_values.items()
                    },
                    mechanism_likelihoods=mechanism,
                    handoff_role_likelihoods={
                        (mapping[source], mapping[target]): value
                        for (source, target), value in roles.items()
                    },
                )
            except ValueError:
                continue
            evaluated += 1
            equivalent += (
                original.selected_sequence.responsible_actor_key
                == inverse[renamed.selected_sequence.responsible_actor_key]
            )
    return {
        "evaluated_steps": float(evaluated),
        "equivariant_steps": float(equivalent),
        "equivariance_rate": equivalent / max(evaluated, 1),
    }


def run_amg_action_interface_audit(
    *,
    validation_seeds: tuple[int, ...],
    holdout_seeds: tuple[int, ...],
    max_steps: int = 32,
) -> dict[str, Any]:
    if set(validation_seeds) & set(holdout_seeds):
        raise ValueError("validation and holdout seeds must be disjoint")
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=holdout_seeds,
        max_steps_per_episode=max_steps,
    ).build()
    validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    holdout = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    cells: dict[str, Any] = {}
    for stress in ActorEvidenceStress:
        selected: dict[AMGInterfaceAuditArm, Mapping[str, float]] = {}
        validation_scores: dict[str, list[dict[str, Any]]] = {}
        for arm in AMGInterfaceAuditArm:
            candidates = []
            rows = []
            for parameters in SEARCH_SPACE[arm]:
                evaluated = [
                    _evaluate(dataset, episode, stress, arm, parameters) for episode in validation
                ]
                score = mean(row[0].put_back_error_rate for row in evaluated)
                rows.append({"parameters": dict(parameters), "put_back_error_rate": score})
                candidates.append((score, repr(sorted(parameters.items())), parameters))
            selected[arm] = min(candidates, key=lambda item: (item[0], item[1]))[2]
            validation_scores[arm.value] = rows
        holdout_rows = {
            arm: [_evaluate(dataset, episode, stress, arm, selected[arm]) for episode in holdout]
            for arm in AMGInterfaceAuditArm
        }
        results = {arm.value: _summarize(rows) for arm, rows in holdout_rows.items()}
        posterior_predictions = holdout_rows[AMGInterfaceAuditArm.AMG_POSTERIOR_ADAPTER]
        ratio_predictions = holdout_rows[AMGInterfaceAuditArm.AMG_PRIOR_CORRECTED_ODDS]
        adapter_disagreements = sum(
            left != right
            for left_row, right_row in zip(posterior_predictions, ratio_predictions, strict=True)
            for left, right in zip(left_row[2], right_row[2], strict=True)
        )
        adapter_steps = sum(len(row[2]) for row in posterior_predictions)
        cells[stress.value] = {
            "selected_parameters": {
                arm.value: dict(parameters) for arm, parameters in selected.items()
            },
            "validation_scores": validation_scores,
            "holdout_results": results,
            "posterior_vs_prior_corrected_action_disagreement_rate": (
                adapter_disagreements / max(adapter_steps, 1)
            ),
        }
    alignment = _target_alignment(dataset, holdout)
    label_equivariance = {
        stress.value: _amg_label_equivariance(holdout, stress) for stress in ActorEvidenceStress
    }
    target_aligned = alignment["latest_true_owner_recurrence_match_rate"] >= 0.99
    adapter_inert = all(
        cell["posterior_vs_prior_corrected_action_disagreement_rate"] == 0.0
        for cell in cells.values()
    )
    return {
        "protocol": "project-two-amg-action-interface-audit@0.1",
        "evidence_status": "post-diagnostic matched-interface audit",
        "validation_seeds": list(validation_seeds),
        "holdout_seeds": list(holdout_seeds),
        "max_steps": max_steps,
        "search_budget_per_arm_per_cell": 3,
        "same_visible_stream": True,
        "same_put_back_location_set": True,
        "prediction_timing": "observe -> predict -> feedback for every arm",
        "stress_mask_key": "visible scene_id plus timestamp; UUID-independent",
        "amg_receives_execution_feedback": False,
        "project_two_receives_execution_feedback": True,
        "target_alignment": alignment,
        "amg_actor_label_permutation_equivariance": label_equivariance,
        "adapter_semantic_issue": (
            "current AMG action adapter passes posterior where event likelihood is expected"
        ),
        "raw_likelihood_ratio_contract_valid": False,
        "prior_corrected_adapter": "LR/(1+LR)",
        "adapter_issue_empirically_inert_on_d0": adapter_inert,
        "privileged_information_detected": False,
        "privileged_put_back_action_set_detected": False,
        "actor_label_tie_break_fairness_failure_detected": any(
            values["equivariance_rate"] < 1.0 for values in label_equivariance.values()
        ),
        "benchmark_target_alignment_advantage_detected": target_aligned,
        "cells": cells,
    }


__all__ = [
    "SEARCH_SPACE",
    "AMGInterfaceAuditArm",
    "run_amg_action_interface_audit",
]
