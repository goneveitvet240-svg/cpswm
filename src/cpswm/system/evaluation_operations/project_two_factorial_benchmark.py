"""Fresh-seed factorial death test for the seven project-two operators.

The design is a regular 2^(6-2) resolution-IV fractional factorial.  Main
effects are not aliased with two-factor interactions; two-factor interactions
are deliberately not interpreted.  Every cell compares a corrected AMG arm,
the complete seven-operator system, and seven one-operator cuts under the same
visible replay, action evaluator, tuning budget, and simulated CIAV outcomes.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import product
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import (
    EvidenceFactorConsumptionTrace,
    ObservationOutcome,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayStep,
    RobotActionOutcome,
)
from cpswm.system.attestation import Ed25519AttestationVerifier
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.evaluation_operations.project_two_ablation import PriorOnlyMessagePassing
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _AMGOpenWorldMethod,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_ciav_interactive_development import (
    _OUTCOME_MODELS,
    InteractiveVerificationPolicy,
    _actions,
    _potential_outcome,
    _select_action,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
    _TransformedState,
)
from cpswm.system.evaluation_operations.structure_two_trusted_ablation_authorization import (
    ReceiptReplayRegistry,
    ReceiptTrustAnchorManifest,
    TrustedAblationAuthorizationPolicy,
    TrustedSevenOperatorAblationAuthorization,
    verify_trusted_seven_operator_ablation_authorization,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.world_model.grounded_search import (
    CIAVOPCEUObservationLoop,
    CIAVOPCEUReceipt,
    RealizedCIAVObservation,
    StructureTwoCauseBelief,
)
from cpswm.world_model.habits_transitions import PropensityCorrectionMode

PROTOCOL_VERSION = "project-two-seven-operator-factorial@0.1"


class TrustedSevenOperatorAuthorizationRequired(RuntimeError):
    """Raised before workload construction when no verified authorization exists."""


class Factor(StrEnum):
    ATTRIBUTION_AMBIGUITY = "attribution_ambiguity"
    FEEDBACK_ADVERSITY = "feedback_delay_and_contradiction"
    SHORT_REGIMES = "short_regime_duration"
    UNKNOWN_ACTOR_RATE = "unknown_actor_rate"
    OBSERVATION_COST = "active_observation_cost"
    POLLUTION_RECOVERY = "misattribution_pollution_and_recovery"


class OperatorArm(StrEnum):
    AMG = "corrected_amg_adapter"
    FULL = "full_seven_operator_system"
    NO_OPCEU = "without_opceu"
    NO_ORRER = "without_orrer"
    NO_PCHMP = "without_pchmp"
    NO_CF_BOCPD = "without_cf_bocpd"
    NO_RGRC = "without_rgrc"
    NO_CCRR = "without_ccrr"
    NO_CIAV = "without_ciav"


READOUT_SEARCH_SPACE: tuple[dict[str, float], ...] = (
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
)

AMG_SEARCH_SPACE: tuple[dict[str, float], ...] = (
    {"parameter": 0.2},
    {"parameter": 0.33},
    {"parameter": 0.5},
)


@dataclass(frozen=True, slots=True)
class FactorialCell:
    cell_id: str
    levels: Mapping[Factor, int]


@dataclass(frozen=True, slots=True)
class _CaseReading:
    metric: ActionCaseMetric
    verification_count: int
    verification_cost: float

    @property
    def net_action_loss_per_step(self) -> float:
        steps = max(1, self.metric.step_count)
        return (self.metric.cumulative_action_regret + self.verification_cost) / steps


def registered_factorial_cells() -> tuple[FactorialCell, ...]:
    """Return the 16-run resolution-IV design E=ABC, F=BCD."""

    cells = []
    for index, (a, b, c, d) in enumerate(product((-1, 1), repeat=4)):
        levels = {
            Factor.ATTRIBUTION_AMBIGUITY: a,
            Factor.FEEDBACK_ADVERSITY: b,
            Factor.SHORT_REGIMES: c,
            Factor.UNKNOWN_ACTOR_RATE: d,
            Factor.OBSERVATION_COST: a * b * c,
            Factor.POLLUTION_RECOVERY: b * c * d,
        }
        cells.append(FactorialCell(cell_id=f"f{index:02d}", levels=levels))
    return tuple(cells)


def _scenario_windows(duration: int, short: bool) -> tuple[tuple[int, int], int, int]:
    if duration < 12:
        raise ValueError("factorial benchmark requires at least 12 steps")
    if short:
        guest = (max(1, duration // 10), max(2, duration // 5))
        abrupt = max(guest[1] + 1, int(0.40 * duration))
        recurrence = max(abrupt + 1, int(0.65 * duration))
    else:
        guest = (max(1, duration // 5), max(2, int(0.32 * duration)))
        abrupt = max(guest[1] + 1, int(0.56 * duration))
        recurrence = max(abrupt + 1, int(0.82 * duration))
    if recurrence >= duration:
        recurrence = duration - 1
    return guest, abrupt, recurrence


def _dataset_for_cell(
    cell: FactorialCell,
    *,
    validation_seeds: tuple[int, ...],
    holdout_seeds: tuple[int, ...],
    max_steps: int,
) -> ProjectTwoReplayDataset:
    short = cell.levels[Factor.SHORT_REGIMES] == 1
    high_unknown = cell.levels[Factor.UNKNOWN_ACTOR_RATE] == 1
    guest, abrupt, recurrence = _scenario_windows(max_steps, short)
    unknown_days = tuple(range(1, max_steps, 3)) if high_unknown else (1,)
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=holdout_seeds,
        max_steps_per_episode=max_steps,
        dataset_version=f"{PROTOCOL_VERSION}:{cell.cell_id}",
        sealed_secret=f"{PROTOCOL_VERSION}:{cell.cell_id}:fixed-seal",
        scenario_duration_days=max_steps,
        guest_window=guest,
        abrupt_day=abrupt,
        recurrence_day=recurrence,
        observation_coverage=0.85,
        unknown_event_days=unknown_days,
    ).build()


def _evidence_transform(
    episode: Any,
    cell: FactorialCell,
) -> Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep]:
    ambiguous = cell.levels[Factor.ATTRIBUTION_AMBIGUITY] == 1
    pollution = cell.levels[Factor.POLLUTION_RECOVERY] == 1
    midpoint = episode.steps[len(episode.steps) // 2].timestamp

    def transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
        evidence = step.actor_evidence
        if evidence is None:
            return step
        posterior = dict(evidence.actor_posterior)
        prior = dict(evidence.reference_actor_prior)
        if ambiguous:
            posterior = {actor: 0.4 * posterior[actor] + 0.6 * prior[actor] for actor in posterior}
        stable_key = f"{episode.scene_id}|{step.timestamp.isoformat()}|pollution".encode()
        draw = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big") / float(2**64)
        if pollution and step.timestamp < midpoint and draw < 0.30:
            alternatives = tuple(
                actor
                for actor in episode.resident_actor_keys
                if actor not in {episode.owner_actor_key, "unknown_actor"}
            )
            if alternatives and episode.owner_actor_key in posterior:
                other = alternatives[0]
                posterior[episode.owner_actor_key], posterior[other] = (
                    posterior[other],
                    posterior[episode.owner_actor_key],
                )
        return step.model_copy(
            update={"actor_evidence": evidence.model_copy(update={"actor_posterior": posterior})}
        )

    return transform


def _adverse_feedback(
    step: ProjectTwoReplayStep, episode: Any, enabled: bool
) -> ProjectTwoReplayStep:
    if not enabled or not step.execution_feedback:
        return step
    transformed = []
    for feedback in step.execution_feedback:
        stable_key = f"{episode.scene_id}|{step.timestamp.isoformat()}|feedback".encode()
        draw = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big") / float(2**64)
        if draw >= 0.20:
            transformed.append(feedback)
            continue
        distribution = dict(feedback.outcome_distribution)
        success = distribution.get(RobotActionOutcome.SUCCESS, 0.0)
        non_success = 1.0 - success
        distribution = dict.fromkeys(distribution, 0.0)
        distribution[RobotActionOutcome.SUCCESS] = non_success
        distribution[RobotActionOutcome.NOT_FOUND] = success
        transformed.append(feedback.model_copy(update={"outcome_distribution": distribution}))
    return step.model_copy(update={"execution_feedback": tuple(transformed)})


class _CIAVState:
    """Add action-selected verification without exposing truth before selection."""

    def __init__(
        self,
        state: Any,
        dataset: ProjectTwoReplayDataset,
        episode: Any,
        *,
        enabled: bool,
        cost_multiplier: float,
        max_verifications: int = 4,
    ) -> None:
        self._state = state
        self._dataset = dataset
        self._episode = episode
        self._enabled = enabled
        self._actions = _actions(cost_multiplier=cost_multiplier)
        self._by_id = {item.action_id: item for item in self._actions}
        self._max_verifications = max_verifications
        self.verification_count = 0
        self.verification_cost = 0.0
        self._privacy_cost = 0.0
        self.evidence_factor_trace = getattr(
            state,
            "evidence_factor_trace",
            EvidenceFactorConsumptionTrace(),
        )
        self._opceu_loop = CIAVOPCEUObservationLoop(self.evidence_factor_trace)
        self.ciav_opceu_receipts: list[CIAVOPCEUReceipt] = []

    def _actor_posterior_after_verification(
        self,
        prior: Mapping[str, float],
        owner_probability: float,
    ) -> dict[str, float]:
        actors = tuple(dict.fromkeys((*self._episode.resident_actor_keys, "unknown_actor")))
        owner = self._episode.owner_actor_key
        other_prior = sum(prior.get(actor, 0.0) for actor in actors if actor != owner)
        remainder = 1.0 - owner_probability
        if other_prior <= 0.0:
            share = remainder / max(1, len(actors) - 1)
            return {actor: owner_probability if actor == owner else share for actor in actors}
        return {
            actor: (
                owner_probability
                if actor == owner
                else remainder * prior.get(actor, 0.0) / other_prior
            )
            for actor in actors
        }

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(step)
        if not self._enabled or self.verification_count >= self._max_verifications:
            return
        result = self._state.step_results.get(step.step_id)
        snapshot = self._state.spine.current_cause_snapshot
        if result is None or snapshot is None:
            return
        belief = StructureTwoCauseBelief.from_snapshot(
            snapshot,
            identity_switch_probability=0.0,
        )
        owner_prior = result.actor_posterior.get(self._episode.owner_actor_key, 0.0)
        action_id, _verification_prior = _select_action(
            InteractiveVerificationPolicy.CIAV,
            belief,
            self._actions,
            owner_prior=owner_prior,
            outcome_models=_OUTCOME_MODELS,
            minimum_attribution_shift=0.25,
            privacy_budget=max(0.0, 0.50 - self._privacy_cost),
            random_seed=int.from_bytes(
                hashlib.sha256(
                    f"{self._episode.scene_id}|{step.timestamp.isoformat()}|ciav".encode()
                ).digest()[:8],
                "big",
            ),
        )
        if action_id is None:
            return
        action = self._by_id[action_id]
        if step.after is None or step.after.detected_location_id is None:
            raise ValueError("CIAV owner check requires a robot-visible object location")
        visible_location = step.after.detected_location_id
        model = _OUTCOME_MODELS[action_id]
        actors = tuple(dict.fromkeys((*self._episode.resident_actor_keys, "unknown_actor")))
        actor_likelihoods_by_outcome = {
            outcome_label: {
                actor: (
                    model.sensitivity
                    if outcome_label == "owner_supported"
                    else 1.0 - model.sensitivity
                )
                if actor == self._episode.owner_actor_key
                else (
                    1.0 - model.specificity
                    if outcome_label == "owner_supported"
                    else model.specificity
                )
                for actor in actors
            }
            for outcome_label in action.outcome_likelihoods
        }

        def realize(_opportunity: Any) -> RealizedCIAVObservation:
            # Evaluator truth is read only inside the post-selection realizer.
            target = self._dataset.truth_for(self._episode.episode_id).truth_by_step[step.step_id]
            outcome, _ = _potential_outcome(
                episode_id=self._episode.episode_id,
                step_id=step.step_id,
                action_id=action_id,
                true_owner=target.true_actor == self._episode.owner_actor_key,
                model=_OUTCOME_MODELS[action_id],
            )
            return RealizedCIAVObservation(
                outcome_label=outcome,
                likelihood_model_id=action.observation_likelihood_model_id,
                detection_outcome=ObservationOutcome.DETECTED,
            )

        receipt = self._opceu_loop.execute_selected_action(
            action=action,
            update_id=result.event_revision_id,
            household_id=self._episode.household_id,
            session_id=self._episode.session_id,
            trace_id=self._episode.trace_id,
            opportunity_time=step.timestamp,
            object_instance_id=step.object_instance_id,
            actor_keys=self._episode.resident_actor_keys,
            actor_prior=result.actor_posterior,
            actor_likelihoods_by_outcome=actor_likelihoods_by_outcome,
            location_keys=tuple(
                str(item)
                for item in getattr(self._state, "locations", self._episode.known_location_ids)
            ),
            expected_detected_location_id=visible_location,
            selection_probability=1.0,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            realizer=realize,
        )
        owner_after = receipt.evidence.actor_posterior[self._episode.owner_actor_key]
        self._state.spine.apply_fast_action_verification(
            revision_id=result.event_revision_id,
            verified_owner_probability=owner_after,
            source_record_id=receipt.evidence.metadata.record_id,
        )
        self.ciav_opceu_receipts.append(receipt)
        cost = (
            action.motion_cost
            + action.time_cost
            + action.interruption_cost
            + action.privacy_cost
            + action.safety_cost
        )
        self.verification_count += 1
        self.verification_cost += cost
        self._privacy_cost += action.privacy_cost

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


class _DelayedFeedbackState:
    def __init__(self, state: Any, episode: Any, *, enabled: bool) -> None:
        self._state = state
        self._episode = episode
        self._enabled = enabled
        self._queue: list[ProjectTwoReplayStep] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(step)

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        transformed = _adverse_feedback(step, self._episode, self._enabled)
        if not self._enabled:
            self._state.feedback(transformed)
            return
        self._queue.append(transformed)
        if len(self._queue) > 2:
            self._state.feedback(self._queue.pop(0))

    @property
    def verification_count(self) -> int:
        return int(getattr(self._state, "verification_count", 0))

    @property
    def verification_cost(self) -> float:
        return float(getattr(self._state, "verification_cost", 0.0))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _readout(parameters: Mapping[str, float]) -> ActionReadoutConfig:
    return ActionReadoutConfig(
        readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
        hybrid_alpha_weight=0.0,
        fast_action_weight=parameters["fast_action_weight"],
        surviving_revision_weight=parameters["surviving_revision_weight"],
        regime_local_weight=parameters["regime_local_weight"],
        fast_owner_mass_floor=parameters["fast_owner_mass_floor"],
        owner_mass_floor=0.5,
        recency_half_life=1.0,
    )


def _state(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    cell: FactorialCell,
    arm: OperatorArm,
    parameters: Mapping[str, float],
) -> Any:
    transform = _evidence_transform(episode, cell)
    if arm is OperatorArm.AMG:
        return _TransformedState(
            _AMGOpenWorldMethod(
                episode,
                mode="amg",
                parameter=parameters["parameter"],
            ),
            transform,
        )

    loop_config = PrototypeLoopConfig(owner_evidence_threshold=0.4)
    kwargs: dict[str, Any] = {
        "owner_threshold": 0.4,
        "evidence_transform": transform,
        "action_readout": _readout(parameters),
    }
    if arm is OperatorArm.NO_OPCEU:
        kwargs["propensity_correction_mode"] = PropensityCorrectionMode.NONE
    elif arm is OperatorArm.NO_ORRER:
        kwargs["revision_strategy"] = "in_place"
    elif arm is OperatorArm.NO_PCHMP:
        kwargs["message_passing"] = PriorOnlyMessagePassing()
    elif arm is OperatorArm.NO_CF_BOCPD:
        kwargs["loop_config"] = replace(loop_config, cause_factorized_bocpd_enabled=False)
    elif arm is OperatorArm.NO_RGRC:
        kwargs["rgrc_gate_enabled"] = False
    elif arm is OperatorArm.NO_CCRR:
        kwargs["loop_config"] = replace(
            loop_config,
            ccrr_enabled=False,
            regime_reactivation_enabled=False,
        )
    base = _FullProjectTwoMethod(episode, **kwargs)
    with_ciav = _CIAVState(
        base,
        dataset,
        episode,
        enabled=arm is not OperatorArm.NO_CIAV,
        cost_multiplier=(4.0 if cell.levels[Factor.OBSERVATION_COST] == 1 else 1.0),
    )
    return _DelayedFeedbackState(
        with_ciav,
        episode,
        enabled=cell.levels[Factor.FEEDBACK_ADVERSITY] == 1,
    )


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    cell: FactorialCell,
    arm: OperatorArm,
    parameters: Mapping[str, float],
) -> _CaseReading:
    state = _state(dataset, episode, cell, arm, parameters)
    try:
        metric = evaluator.evaluate_custom_state(dataset, episode, state)
    except Exception as error:
        raise RuntimeError(
            f"factorial evaluation failed in cell={cell.cell_id} arm={arm.value} "
            f"episode={episode.episode_id}"
        ) from error
    return _CaseReading(
        metric=metric,
        verification_count=int(getattr(state, "verification_count", 0)),
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
    )


def _summary(readings: list[_CaseReading]) -> dict[str, float]:
    return {
        "put_back_error_rate": mean(item.metric.put_back_error_rate for item in readings),
        "persistent_owner_mode_error_rate": mean(
            item.metric.persistent_owner_mode_error_rate for item in readings
        ),
        "owner_habit_contamination": mean(
            item.metric.owner_habit_contamination for item in readings
        ),
        "incorrect_statistic_recovery_cost": mean(
            item.metric.incorrect_statistic_recovery_cost for item in readings
        ),
        "unknown_calibration_brier": mean(
            item.metric.unknown_calibration_brier for item in readings
        ),
        "verification_count": mean(item.verification_count for item in readings),
        "verification_cost": mean(item.verification_cost for item in readings),
        "net_action_loss_per_step": mean(item.net_action_loss_per_step for item in readings),
    }


def _bootstrap_ci(values: list[float], *, draws: int = 2000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(f"{PROTOCOL_VERSION}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def run_project_two_factorial_benchmark(
    *,
    validation_seeds: tuple[int, ...],
    holdout_seeds: tuple[int, ...],
    max_steps: int = 16,
    authorization: TrustedSevenOperatorAblationAuthorization | None = None,
    authorization_policy: TrustedAblationAuthorizationPolicy | None = None,
    trust_anchor_manifest: ReceiptTrustAnchorManifest | None = None,
    authorization_registry_authority: Ed25519AttestationVerifier | None = None,
    expected_run_id: UUID | None = None,
    authorization_replay_registry: ReceiptReplayRegistry | None = None,
) -> dict[str, object]:
    authorization_inputs = (
        authorization,
        authorization_policy,
        trust_anchor_manifest,
        authorization_registry_authority,
        expected_run_id,
        authorization_replay_registry,
    )
    if any(item is None for item in authorization_inputs):
        raise TrustedSevenOperatorAuthorizationRequired(
            "trusted seven-operator ablation authorization is missing; workload was not created"
        )
    assert authorization is not None
    assert authorization_policy is not None
    assert trust_anchor_manifest is not None
    assert authorization_registry_authority is not None
    assert expected_run_id is not None
    assert authorization_replay_registry is not None
    try:
        verify_trusted_seven_operator_ablation_authorization(
            authorization,
            policy=authorization_policy,
            manifest=trust_anchor_manifest,
            registry_authority=authorization_registry_authority,
            expected_run_id=expected_run_id,
            replay_registry=authorization_replay_registry,
        )
    except (TypeError, ValueError) as exc:
        raise TrustedSevenOperatorAuthorizationRequired(
            "trusted seven-operator ablation authorization failed verification; "
            "workload was not created"
        ) from exc
    if not validation_seeds or not holdout_seeds:
        raise ValueError("factorial validation and holdout splits must be non-empty")
    if set(validation_seeds) & set(holdout_seeds):
        raise ValueError("factorial validation and holdout seeds must be disjoint")
    evaluator = ProjectTwoActionBenchmarkV02()
    cell_reports: dict[str, Any] = {}
    cell_level_rows: dict[str, Mapping[Factor, int]] = {}
    paired_by_cell: dict[str, dict[str, list[float]]] = {}
    for cell in registered_factorial_cells():
        dataset = _dataset_for_cell(
            cell,
            validation_seeds=validation_seeds,
            holdout_seeds=holdout_seeds,
            max_steps=max_steps,
        )
        validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        holdout = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        selected: dict[OperatorArm, Mapping[str, float]] = {}
        validation_scores: dict[str, list[dict[str, object]]] = {}
        for arm in OperatorArm:
            space = AMG_SEARCH_SPACE if arm is OperatorArm.AMG else READOUT_SEARCH_SPACE
            candidates = []
            rows = []
            for parameters in space:
                readings = [
                    _evaluate(evaluator, dataset, episode, cell, arm, parameters)
                    for episode in validation
                ]
                score = mean(item.net_action_loss_per_step for item in readings)
                candidates.append((score, repr(sorted(parameters.items())), parameters))
                rows.append({"parameters": dict(parameters), "net_action_loss_per_step": score})
            selected[arm] = min(candidates, key=lambda item: (item[0], item[1]))[2]
            validation_scores[arm.value] = rows

        holdout_readings = {
            arm: [
                _evaluate(evaluator, dataset, episode, cell, arm, selected[arm])
                for episode in holdout
            ]
            for arm in OperatorArm
        }
        summaries = {arm: _summary(values) for arm, values in holdout_readings.items()}
        full_loss = summaries[OperatorArm.FULL]["net_action_loss_per_step"]
        amg_loss = summaries[OperatorArm.AMG]["net_action_loss_per_step"]
        operator_contributions = {
            arm.value.removeprefix("without_"): (
                summaries[arm]["net_action_loss_per_step"] - full_loss
            )
            for arm in OperatorArm
            if arm.value.startswith("without_")
        }
        paired_differences = {
            "full_minus_amg": [
                full.net_action_loss_per_step - amg.net_action_loss_per_step
                for full, amg in zip(
                    holdout_readings[OperatorArm.FULL],
                    holdout_readings[OperatorArm.AMG],
                    strict=True,
                )
            ],
            **{
                arm.value.removeprefix("without_"): [
                    cut.net_action_loss_per_step - full.net_action_loss_per_step
                    for cut, full in zip(
                        holdout_readings[arm],
                        holdout_readings[OperatorArm.FULL],
                        strict=True,
                    )
                ]
                for arm in OperatorArm
                if arm.value.startswith("without_")
            },
        }
        cell_reports[cell.cell_id] = {
            "levels": {factor.value: level for factor, level in cell.levels.items()},
            "selected_parameters": {
                arm.value: dict(parameters) for arm, parameters in selected.items()
            },
            "validation_scores": validation_scores,
            "holdout_results": {arm.value: value for arm, value in summaries.items()},
            "full_minus_amg_net_action_loss": full_loss - amg_loss,
            "operator_net_loss_contribution": operator_contributions,
            "paired_holdout_seed_differences": paired_differences,
            "paired_confidence_intervals_95": {
                name: _bootstrap_ci(values) for name, values in paired_differences.items()
            },
        }
        cell_level_rows[cell.cell_id] = cell.levels
        paired_by_cell[cell.cell_id] = paired_differences

    main_effects: dict[str, Any] = {}
    for factor in Factor:
        high_cells = [key for key, levels in cell_level_rows.items() if levels[factor] == 1]
        low_cells = [key for key, levels in cell_level_rows.items() if levels[factor] == -1]

        def average(keys: list[str], path: str) -> float:
            if path == "full_minus_amg":
                return float(
                    mean(cell_reports[key]["full_minus_amg_net_action_loss"] for key in keys)
                )
            return float(
                mean(cell_reports[key]["operator_net_loss_contribution"][path] for key in keys)
            )

        main_effects[factor.value] = {
            "full_minus_amg_high": average(high_cells, "full_minus_amg"),
            "full_minus_amg_low": average(low_cells, "full_minus_amg"),
            "full_minus_amg_main_effect": (
                average(high_cells, "full_minus_amg") - average(low_cells, "full_minus_amg")
            ),
            "operator_contribution_main_effects": {
                name: average(high_cells, name) - average(low_cells, name)
                for name in (
                    "opceu",
                    "orrer",
                    "pchmp",
                    "cf_bocpd",
                    "rgrc",
                    "ccrr",
                    "ciav",
                )
            },
        }

    effect_names = (
        "full_minus_amg",
        "opceu",
        "orrer",
        "pchmp",
        "cf_bocpd",
        "rgrc",
        "ccrr",
        "ciav",
    )
    clustered_over_cells = {
        name: [
            mean(
                paired_by_cell[cell.cell_id][name][seed_index]
                for cell in registered_factorial_cells()
            )
            for seed_index in range(len(holdout_seeds))
        ]
        for name in effect_names
    }
    overall_paired_effects = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(values),
            "holdout_seed_cluster_values": values,
        }
        for name, values in clustered_over_cells.items()
    }

    return {
        "protocol": PROTOCOL_VERSION,
        "evidence_status": "fresh-seed factorial development; not confirmatory",
        "design": {
            "type": "regular 2^(6-2) resolution-IV fractional factorial",
            "generators": ["E=ABC", "F=BCD"],
            "cell_count": len(registered_factorial_cells()),
            "main_effects_aliased_with_two_factor_interactions": False,
            "two_factor_interactions_identifiable": False,
        },
        "validation_seeds": list(validation_seeds),
        "holdout_seeds": list(holdout_seeds),
        "max_steps": max_steps,
        "same_visible_stream_within_cell": True,
        "same_action_evaluator_within_cell": True,
        "truth_access": "CIAV outcome simulator only, after action selection",
        "search_budget_per_arm_per_cell": 3,
        "arms": [arm.value for arm in OperatorArm],
        "cells": cell_reports,
        "factor_main_effects": main_effects,
        "overall_paired_effects_clustered_by_holdout_seed": overall_paired_effects,
        "interpretation_rule": (
            "positive without-operator minus full net loss means the operator helped; "
            "negative means the operator hurt"
        ),
    }


__all__ = [
    "AMG_SEARCH_SPACE",
    "PROTOCOL_VERSION",
    "READOUT_SEARCH_SPACE",
    "Factor",
    "FactorialCell",
    "OperatorArm",
    "registered_factorial_cells",
    "run_project_two_factorial_benchmark",
]
