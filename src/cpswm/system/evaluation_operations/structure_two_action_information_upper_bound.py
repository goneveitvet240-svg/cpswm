"""Exploratory action-information upper bounds for Structure Two.

This diagnostic deliberately uses evaluator truth in labelled oracle arms.  It
does not define a deployable method and it never opens a new sealed holdout.
The purpose is to locate headroom before another mechanism is proposed:

* top-k readout headroom from the current deterministic transition trace;
* true-actor headroom while keeping location and owner-habit truth hidden;
* task-target headroom from current-location and owner-habit truth separately;
* complementarity among already implemented memory/transition policies.

The evaluator envelope does not contain identity, change-cause, or regime
truth.  Those axes are therefore reported as unavailable rather than invented.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.contracts import (
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _FullProjectTwoMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_consolidation_compatibility import (
    AdaptiveParticleConsolidationLedger,
    ConsolidationStrategy,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    _action_readout,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    _DecoyAwareMultiAxisActionState,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    DEFAULT_MANIFEST as DEFAULT_NEIGHBOR_MANIFEST,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    NeighborArm,
    NeighborFamily,
    _dataset,
    _wrap_visible_family,
    load_frozen_neighbor_design,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    _state_for_arm as _neighbor_state_for_arm,
)
from cpswm.system.evaluation_operations.structure_two_transition_reactivation import (
    _TransitionReactivationState,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-action-information-upper-bound@0.1"
DEFAULT_STRONGEST_ARTIFACT = Path(
    "artifacts/project_two_v04_development/structure_two_strongest_neighbor_gate_v0_1.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/project_two_v04_development/structure_two_action_information_upper_bound_v0_1.json"
)


class InformationArm(StrEnum):
    BRAINCTL_REFERENCE = "brainctl_reference"
    SEQUENTIAL = "sequential_no_consolidation"
    IMMEDIATE_QUARANTINE = "immediate_conflict_quarantine"
    DETERMINISTIC_TRANSITION = "deterministic_conflict_transition"
    HISTORICAL_REACTIVATION = "historical_regime_reactivation"
    JOINT_TRANSITION_REACTIVATION = "joint_transition_reactivation"
    TOP2_READOUT_ORACLE = "top2_readout_oracle"
    TRUE_ACTOR_ORACLE = "true_actor_oracle"
    OWNER_HABIT_ORACLE = "owner_habit_target_oracle"
    SEARCH_LOCATION_ORACLE = "search_location_target_oracle"
    EXISTING_OPERATOR_SELECTOR_ORACLE = "existing_operator_selector_oracle"
    FULL_ACTION_ORACLE = "full_action_oracle"


FIXED_OPERATOR_ARMS = (
    InformationArm.DETERMINISTIC_TRANSITION,
    InformationArm.SEQUENTIAL,
    InformationArm.IMMEDIATE_QUARANTINE,
    InformationArm.HISTORICAL_REACTIVATION,
    InformationArm.JOINT_TRANSITION_REACTIVATION,
)


@dataclass(frozen=True, slots=True)
class CollectedTrace:
    predictions: tuple[_Prediction, ...]
    consumed_visible_stream_hash: str
    verification_cost: float
    truth_read_count: int


@dataclass(frozen=True, slots=True)
class EpisodeReading:
    family_id: str
    episode_id: str
    arm: InformationArm
    metric: ActionCaseMetric
    verification_cost: float
    consumed_visible_stream_hash: str
    truth_read_count: int
    oracle_intervention_count: int
    selection_counts: Mapping[str, int]

    @property
    def action_regret_per_step(self) -> float:
        return float(self.metric.cumulative_action_regret / max(1, self.metric.step_count))


class _PredictionTraceState:
    """Feed an already collected trace through the unchanged frozen evaluator."""

    def __init__(self, predictions: Sequence[_Prediction]) -> None:
        self._predictions = tuple(predictions)
        self._index = 0
        self.revision_calls = 0
        self.project_one_requests = 0
        self.project_one_applications = 0
        self.rejected_feedback = 0
        self.unnecessary_revisions = 0
        self.project_one_rejections = 0

    def observe(self, step: ProjectTwoReplayStep) -> None:
        del step

    def predict(self) -> _Prediction:
        if self._index >= len(self._predictions):
            raise RuntimeError("prediction trace exhausted")
        prediction = self._predictions[self._index]
        self._index += 1
        return prediction

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        del step


class _TrueActorTransitionState(_TransitionReactivationState):  # type: ignore[misc]
    """Inject only evaluator true actor before the particle proposal is revised."""

    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: ProjectTwoReplayEpisode,
        dataset: ProjectTwoReplayDataset,
        *,
        profile: str,
    ) -> None:
        super().__init__(
            state,
            episode,
            profile=profile,
            conflict_transition=True,
            reactivation=False,
        )
        self._oracle_dataset = dataset
        self.truth_read_count = 0

    def observe(self, step: ProjectTwoReplayStep) -> None:
        # The parent sequential implementation would revise once before an
        # actor override.  Call its belief-building parent explicitly so the
        # oracle actor is consumed exactly once by the proposal.
        _DecoyAwareMultiAxisActionState.observe(self, step)
        if self._belief is None:
            return
        truth = self._oracle_dataset.truth_for(self._episode.episode_id).truth_by_step[step.step_id]
        actors = set(self._belief.actor_posterior) | {truth.true_actor}
        self._belief = replace(
            self._belief,
            actor_posterior={actor: float(actor == truth.true_actor) for actor in actors},
        )
        self.truth_read_count += 1
        self._runtime.revise(self._belief)


def _load_frozen_parameters(repository_root: Path) -> tuple[float, str]:
    artifact_path = repository_root / DEFAULT_STRONGEST_ARTIFACT
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != "structure-two-strongest-neighbor-gate@0.1":
        raise ValueError("unexpected strongest-neighbor source artifact")
    if payload.get("selected_strongest_published_neighbor") != NeighborArm.BRAINCTL.value:
        raise ValueError("diagnostic expects the previously selected brainctl matched reference")
    selected = payload["selected_parameters"]
    return float(selected[NeighborArm.BRAINCTL.value]), str(
        selected[NeighborArm.NO_CONSOLIDATION.value]
    )


def _transition_state(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    *,
    profile: str,
    conflict_transition: bool,
    ledger: str,
    true_actor_oracle: bool = False,
) -> Any:
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    if true_actor_oracle:
        state: Any = _TrueActorTransitionState(
            base,
            episode,
            dataset,
            profile=profile,
        )
    else:
        state = _TransitionReactivationState(
            base,
            episode,
            profile=profile,
            conflict_transition=conflict_transition,
            reactivation=ledger == "reactivation",
        )
    if ledger == "immediate_quarantine":
        state._particle_ledger = AdaptiveParticleConsolidationLedger(
            strategy=ConsolidationStrategy.IMMEDIATE_QUARANTINE
        )
    elif ledger not in {"none", "reactivation"}:
        raise ValueError(f"unknown diagnostic ledger mode: {ledger}")
    state = _CIAVState(state, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {
        **state.operator_retention_receipt,
        "ciav": bool(state._enabled),
    }
    return _wrap_visible_family(state, episode, family)


def _collect_trace(
    state: Any,
    episode: ProjectTwoReplayEpisode,
) -> CollectedTrace:
    predictions: list[_Prediction] = []
    for step in episode.steps:
        state.observe(step)
        predictions.append(state.predict())
        state.feedback(step)
    return CollectedTrace(
        predictions=tuple(predictions),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
        truth_read_count=int(getattr(state, "truth_read_count", 0)),
    )


def _move_first(order: Sequence[Any], target: Any) -> tuple[Any, ...]:
    return (target, *(item for item in order if item != target))


def _top2_readout_oracle(
    base: Sequence[_Prediction],
    truths: Sequence[ProjectTwoEvaluatorStepTruth],
) -> tuple[tuple[_Prediction, ...], int, dict[str, int]]:
    predictions: list[_Prediction] = []
    interventions = 0
    support = Counter()
    for prediction, truth in zip(base, truths, strict=True):
        top2 = tuple(dict.fromkeys((prediction.put_back, *prediction.search_order[:2])))
        put_back = prediction.put_back
        search_order = prediction.search_order
        if truth.true_owner_habit_location in top2:
            support["owner_habit_in_top2"] += 1
            put_back = truth.true_owner_habit_location
        if truth.true_location in prediction.search_order[:2]:
            support["search_location_in_top2"] += 1
            search_order = _move_first(prediction.search_order, truth.true_location)
        changed = put_back != prediction.put_back or search_order[0] != prediction.search_order[0]
        interventions += int(changed)
        predictions.append(
            _Prediction(
                put_back=put_back,
                search_order=search_order,
                unknown_probability=prediction.unknown_probability,
            )
        )
    return tuple(predictions), interventions, dict(support)


def _owner_habit_oracle(
    base: Sequence[_Prediction],
    truths: Sequence[ProjectTwoEvaluatorStepTruth],
) -> tuple[tuple[_Prediction, ...], int]:
    predictions = tuple(
        _Prediction(
            put_back=truth.true_owner_habit_location,
            search_order=prediction.search_order,
            unknown_probability=prediction.unknown_probability,
        )
        for prediction, truth in zip(base, truths, strict=True)
    )
    changed = sum(
        prediction.put_back != truth.true_owner_habit_location
        for prediction, truth in zip(base, truths, strict=True)
    )
    return predictions, changed


def _search_location_oracle(
    base: Sequence[_Prediction],
    truths: Sequence[ProjectTwoEvaluatorStepTruth],
) -> tuple[tuple[_Prediction, ...], int]:
    predictions = tuple(
        _Prediction(
            put_back=prediction.put_back,
            search_order=_move_first(prediction.search_order, truth.true_location),
            unknown_probability=prediction.unknown_probability,
        )
        for prediction, truth in zip(base, truths, strict=True)
    )
    changed = sum(
        prediction.search_order[0] != truth.true_location
        for prediction, truth in zip(base, truths, strict=True)
    )
    return predictions, changed


def _full_action_oracle(
    truths: Sequence[ProjectTwoEvaluatorStepTruth],
) -> tuple[_Prediction, ...]:
    return tuple(
        _Prediction(
            put_back=truth.true_owner_habit_location,
            search_order=(truth.true_location,),
            unknown_probability=float(truth.true_actor == "unknown_actor"),
        )
        for truth in truths
    )


def _instantaneous_regret(
    prediction: _Prediction,
    truth: ProjectTwoEvaluatorStepTruth,
) -> int:
    return int(prediction.put_back != truth.true_owner_habit_location) + int(
        prediction.search_order[0] != truth.true_location
    )


def _operator_selector_oracle(
    traces: Mapping[InformationArm, Sequence[_Prediction]],
    truths: Sequence[ProjectTwoEvaluatorStepTruth],
) -> tuple[tuple[_Prediction, ...], dict[str, int], int]:
    if tuple(traces) != FIXED_OPERATOR_ARMS:
        raise ValueError("operator selector requires the frozen tie-priority arm order")
    predictions: list[_Prediction] = []
    selected = Counter()
    interventions = 0
    for index, truth in enumerate(truths):
        winner = min(
            FIXED_OPERATOR_ARMS,
            key=lambda arm: (
                _instantaneous_regret(traces[arm][index], truth),
                FIXED_OPERATOR_ARMS.index(arm),
            ),
        )
        selected[winner.value] += 1
        interventions += int(winner is not InformationArm.DETERMINISTIC_TRANSITION)
        predictions.append(traces[winner][index])
    return tuple(predictions), dict(selected), interventions


def _score(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    predictions: Sequence[_Prediction],
) -> ActionCaseMetric:
    return evaluator.evaluate_custom_state(
        dataset,
        episode,
        _PredictionTraceState(predictions),
    )


def _bootstrap_ci(values: Sequence[float], *, draws: int = 3000) -> tuple[float, float]:
    if not values:
        raise ValueError("bootstrap requires values")
    rng = random.Random(f"{PROTOCOL_ID}:episode-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _summary(readings: Sequence[EpisodeReading]) -> dict[str, Any]:
    return {
        "episode_count": len(readings),
        "step_count": sum(reading.metric.step_count for reading in readings),
        "action_regret_per_step": mean(reading.action_regret_per_step for reading in readings),
        "put_back_error_rate": mean(reading.metric.put_back_error_rate for reading in readings),
        "search_error_rate": mean(reading.metric.search_error_rate for reading in readings),
        "search_success_rate": mean(reading.metric.search_success_rate for reading in readings),
        "mean_search_path_cost": mean(reading.metric.mean_search_path_cost for reading in readings),
        "verification_cost": sum(reading.verification_cost for reading in readings),
        "truth_read_count": sum(reading.truth_read_count for reading in readings),
        "oracle_intervention_count": sum(reading.oracle_intervention_count for reading in readings),
        "selection_counts": dict(
            sum((Counter(reading.selection_counts) for reading in readings), Counter())
        ),
    }


def _paired_difference(
    readings_by_arm: Mapping[InformationArm, Sequence[EpisodeReading]],
    left: InformationArm,
    right: InformationArm,
) -> dict[str, Any]:
    differences = [
        left_reading.action_regret_per_step - right_reading.action_regret_per_step
        for left_reading, right_reading in zip(
            readings_by_arm[left], readings_by_arm[right], strict=True
        )
    ]
    return {
        "left": left.value,
        "right": right.value,
        "mean": mean(differences),
        "confidence_interval_95": _bootstrap_ci(differences),
        "negative_favors_left": True,
    }


def run_action_information_upper_bound(*, repository_root: Path) -> dict[str, Any]:
    design = load_frozen_neighbor_design(repository_root / DEFAULT_NEIGHBOR_MANIFEST)
    brainctl_parameter, profile = _load_frozen_parameters(repository_root)
    evaluator = ProjectTwoActionBenchmarkV02()
    readings_by_arm: dict[InformationArm, list[EpisodeReading]] = {
        arm: [] for arm in InformationArm
    }
    family_reports: dict[str, Any] = {}
    non_oracle_stream_gates: dict[str, bool] = {}
    actor_oracle_action_change_count = 0

    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(619991 + family_index,),
            max_steps=design.max_steps,
            split_label="action-information-upper-bound-validation-only",
        )
        family_readings: dict[InformationArm, list[EpisodeReading]] = {
            arm: [] for arm in InformationArm
        }
        for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
            truth_envelope = dataset.truth_for(episode.episode_id)
            truths = tuple(truth_envelope.truth_by_step[step.step_id] for step in episode.steps)
            brainctl = _collect_trace(
                _neighbor_state_for_arm(
                    dataset,
                    episode,
                    family,
                    NeighborArm.BRAINCTL,
                    brainctl_parameter,
                    max_physical_verifications=(design.max_physical_verifications_per_episode),
                ),
                episode,
            )
            fixed_traces = {
                InformationArm.SEQUENTIAL: _collect_trace(
                    _transition_state(
                        dataset,
                        episode,
                        family,
                        profile=profile,
                        conflict_transition=False,
                        ledger="none",
                    ),
                    episode,
                ),
                InformationArm.IMMEDIATE_QUARANTINE: _collect_trace(
                    _transition_state(
                        dataset,
                        episode,
                        family,
                        profile=profile,
                        conflict_transition=False,
                        ledger="immediate_quarantine",
                    ),
                    episode,
                ),
                InformationArm.DETERMINISTIC_TRANSITION: _collect_trace(
                    _transition_state(
                        dataset,
                        episode,
                        family,
                        profile=profile,
                        conflict_transition=True,
                        ledger="none",
                    ),
                    episode,
                ),
                InformationArm.HISTORICAL_REACTIVATION: _collect_trace(
                    _transition_state(
                        dataset,
                        episode,
                        family,
                        profile=profile,
                        conflict_transition=False,
                        ledger="reactivation",
                    ),
                    episode,
                ),
                InformationArm.JOINT_TRANSITION_REACTIVATION: _collect_trace(
                    _transition_state(
                        dataset,
                        episode,
                        family,
                        profile=profile,
                        conflict_transition=True,
                        ledger="reactivation",
                    ),
                    episode,
                ),
            }
            actor_trace = _collect_trace(
                _transition_state(
                    dataset,
                    episode,
                    family,
                    profile=profile,
                    conflict_transition=True,
                    ledger="none",
                    true_actor_oracle=True,
                ),
                episode,
            )
            deterministic = fixed_traces[InformationArm.DETERMINISTIC_TRANSITION]
            top2, top2_interventions, top2_support = _top2_readout_oracle(
                deterministic.predictions,
                truths,
            )
            owner_habit, owner_interventions = _owner_habit_oracle(
                deterministic.predictions,
                truths,
            )
            search_location, search_interventions = _search_location_oracle(
                deterministic.predictions,
                truths,
            )
            operator_trace, selection_counts, operator_interventions = _operator_selector_oracle(
                {arm: fixed_traces[arm].predictions for arm in FIXED_OPERATOR_ARMS},
                truths,
            )
            actor_action_changes = sum(
                left.put_back != right.put_back or left.search_order[0] != right.search_order[0]
                for left, right in zip(
                    actor_trace.predictions,
                    deterministic.predictions,
                    strict=True,
                )
            )
            actor_oracle_action_change_count += actor_action_changes
            traces: dict[
                InformationArm,
                tuple[Sequence[_Prediction], CollectedTrace | None, int, Mapping[str, int]],
            ] = {
                InformationArm.BRAINCTL_REFERENCE: (
                    brainctl.predictions,
                    brainctl,
                    0,
                    {},
                ),
                **{arm: (trace.predictions, trace, 0, {}) for arm, trace in fixed_traces.items()},
                InformationArm.TOP2_READOUT_ORACLE: (
                    top2,
                    None,
                    top2_interventions,
                    top2_support,
                ),
                InformationArm.TRUE_ACTOR_ORACLE: (
                    actor_trace.predictions,
                    actor_trace,
                    actor_action_changes,
                    {},
                ),
                InformationArm.OWNER_HABIT_ORACLE: (
                    owner_habit,
                    None,
                    owner_interventions,
                    {},
                ),
                InformationArm.SEARCH_LOCATION_ORACLE: (
                    search_location,
                    None,
                    search_interventions,
                    {},
                ),
                InformationArm.EXISTING_OPERATOR_SELECTOR_ORACLE: (
                    operator_trace,
                    None,
                    operator_interventions,
                    selection_counts,
                ),
                InformationArm.FULL_ACTION_ORACLE: (
                    _full_action_oracle(truths),
                    None,
                    len(truths),
                    {},
                ),
            }
            non_oracle_hashes = {
                brainctl.consumed_visible_stream_hash,
                *(trace.consumed_visible_stream_hash for trace in fixed_traces.values()),
            }
            non_oracle_stream_gates[f"{family.family_id}:{episode.episode_id}"] = (
                len(non_oracle_hashes) == 1
            )
            for arm, (predictions, collected, interventions, counts) in traces.items():
                truth_reads = 0
                if arm is InformationArm.BRAINCTL_REFERENCE:
                    truth_reads = int(getattr(collected, "truth_read_count", 0))
                elif arm in {
                    InformationArm.TOP2_READOUT_ORACLE,
                    InformationArm.OWNER_HABIT_ORACLE,
                    InformationArm.SEARCH_LOCATION_ORACLE,
                    InformationArm.EXISTING_OPERATOR_SELECTOR_ORACLE,
                    InformationArm.FULL_ACTION_ORACLE,
                }:
                    truth_reads = len(truths)
                elif arm is InformationArm.TRUE_ACTOR_ORACLE:
                    truth_reads = actor_trace.truth_read_count
                reading = EpisodeReading(
                    family_id=family.family_id,
                    episode_id=str(episode.episode_id),
                    arm=arm,
                    metric=_score(evaluator, dataset, episode, predictions),
                    verification_cost=(0.0 if collected is None else collected.verification_cost),
                    consumed_visible_stream_hash=(
                        deterministic.consumed_visible_stream_hash
                        if collected is None
                        else collected.consumed_visible_stream_hash
                    ),
                    truth_read_count=truth_reads,
                    oracle_intervention_count=interventions,
                    selection_counts=dict(counts),
                )
                readings_by_arm[arm].append(reading)
                family_readings[arm].append(reading)
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "summaries": {arm.value: _summary(values) for arm, values in family_readings.items()},
        }

    best_fixed_operator = min(
        FIXED_OPERATOR_ARMS,
        key=lambda arm: (
            mean(reading.action_regret_per_step for reading in readings_by_arm[arm]),
            FIXED_OPERATOR_ARMS.index(arm),
        ),
    )
    comparisons = {
        "top2_readout_minus_deterministic": _paired_difference(
            readings_by_arm,
            InformationArm.TOP2_READOUT_ORACLE,
            InformationArm.DETERMINISTIC_TRANSITION,
        ),
        "true_actor_minus_deterministic": _paired_difference(
            readings_by_arm,
            InformationArm.TRUE_ACTOR_ORACLE,
            InformationArm.DETERMINISTIC_TRANSITION,
        ),
        "owner_habit_target_minus_deterministic": _paired_difference(
            readings_by_arm,
            InformationArm.OWNER_HABIT_ORACLE,
            InformationArm.DETERMINISTIC_TRANSITION,
        ),
        "search_location_target_minus_deterministic": _paired_difference(
            readings_by_arm,
            InformationArm.SEARCH_LOCATION_ORACLE,
            InformationArm.DETERMINISTIC_TRANSITION,
        ),
        "operator_selector_minus_best_fixed_operator": _paired_difference(
            readings_by_arm,
            InformationArm.EXISTING_OPERATOR_SELECTOR_ORACLE,
            best_fixed_operator,
        ),
        "deterministic_minus_brainctl": _paired_difference(
            readings_by_arm,
            InformationArm.DETERMINISTIC_TRANSITION,
            InformationArm.BRAINCTL_REFERENCE,
        ),
    }
    criteria = {
        "full_action_oracle_zero_regret": (
            _summary(readings_by_arm[InformationArm.FULL_ACTION_ORACLE])["action_regret_per_step"]
            == 0.0
        ),
        "same_visible_stream_for_non_oracle_policies": all(non_oracle_stream_gates.values()),
        "top2_readout_has_action_headroom": comparisons["top2_readout_minus_deterministic"]["mean"]
        < 0.0,
        "true_actor_has_action_headroom": comparisons["true_actor_minus_deterministic"]["mean"]
        < 0.0,
        "existing_operator_complementarity_exists": comparisons[
            "operator_selector_minus_best_fixed_operator"
        ]["mean"]
        < 0.0,
        "perfect_search_observation_has_action_headroom": comparisons[
            "search_location_target_minus_deterministic"
        ]["mean"]
        < 0.0,
        "perfect_owner_habit_target_has_action_headroom": comparisons[
            "owner_habit_target_minus_deterministic"
        ]["mean"]
        < 0.0,
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": ("exploratory_validation_only_oracle_diagnostic_not_a_method_result"),
        "source_manifest_sha256": design.manifest_file_sha256,
        "source_strongest_neighbor_artifact_sha256": content_sha256(
            json.loads((repository_root / DEFAULT_STRONGEST_ARTIFACT).read_text(encoding="utf-8"))
        ),
        "validation_seeds": list(design.validation_seeds),
        "sealed_holdout_opened": False,
        "selected_parameters_reused_without_retuning": {
            "brainctl_matched": brainctl_parameter,
            "structure_two_profile": profile,
        },
        "evaluator_truth_capabilities": {
            "available": [
                "true_actor",
                "true_mechanism",
                "true_location",
                "true_owner_habit_location",
            ],
            "used_by_labelled_oracles": [
                "true_actor",
                "true_location",
                "true_owner_habit_location",
            ],
            "unavailable_not_fabricated": [
                "true_identity_match",
                "true_change_cause",
                "true_regime_change",
                "true_regime_id",
            ],
        },
        "oracle_semantics": {
            InformationArm.TOP2_READOUT_ORACLE.value: (
                "truth may only reorder actions already present in deterministic top-2"
            ),
            InformationArm.TRUE_ACTOR_ORACLE.value: (
                "only actor posterior is replaced by one-hot evaluator actor before proposal"
            ),
            InformationArm.OWNER_HABIT_ORACLE.value: (
                "only put-back target is replaced; search prediction is untouched"
            ),
            InformationArm.SEARCH_LOCATION_ORACLE.value: (
                "only current search target is placed first; put-back is untouched"
            ),
            InformationArm.EXISTING_OPERATOR_SELECTOR_ORACLE.value: (
                "per-step truth selects among five already implemented fixed policies"
            ),
            InformationArm.FULL_ACTION_ORACLE.value: (
                "evaluator supplies both action targets; sanity upper bound only"
            ),
        },
        "best_fixed_operator": best_fixed_operator.value,
        "overall_summaries": {
            arm.value: _summary(values) for arm, values in readings_by_arm.items()
        },
        "paired_episode_comparisons": comparisons,
        "family_reports": family_reports,
        "actor_oracle_action_change_count": actor_oracle_action_change_count,
        "non_oracle_stream_gates": non_oracle_stream_gates,
        "diagnostic_criteria": criteria,
        "limitations": [
            "Validation-only retrospective oracle analysis; no confirmatory claim is allowed.",
            (
                "Top-2 and operator-selector oracles use evaluator truth and are not "
                "deployable policies."
            ),
            (
                "Operator selection scores immediate two-component action regret, not "
                "bounded-horizon causal utility."
            ),
            (
                "The evaluator does not expose identity, cause, or regime truth, so those "
                "oracle axes remain unresolved."
            ),
            (
                "The actor-only intervention can create an off-manifold combination with "
                "unchanged identity, cause, and regime beliefs; failure does not prove actor "
                "information is irrelevant."
            ),
            "All results remain synthetic D0 replay evidence without external validity.",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_action_information_upper_bound(report: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_action_information_upper_bound(
    artifact_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    claimed = payload.pop("content_sha256")
    if claimed != content_sha256(payload):
        raise ValueError("action-information artifact content hash mismatch")
    payload["content_sha256"] = claimed
    if payload.get("sealed_holdout_opened") is not False:
        raise ValueError("action-information diagnostic must remain validation-only")
    if recompute:
        regenerated = run_action_information_upper_bound(repository_root=repository_root)
        # JSON round-tripping turns tuple confidence intervals into lists.
        # Compare the canonical serialized payload rather than Python sequence
        # container types so a deterministic recomputation is not rejected for
        # a representation-only difference.
        if json.dumps(regenerated, ensure_ascii=False, sort_keys=True) != json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ):
            raise ValueError("action-information deterministic recomputation mismatch")
    return payload


__all__ = [
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "InformationArm",
    "run_action_information_upper_bound",
    "verify_action_information_upper_bound",
    "write_action_information_upper_bound",
]
