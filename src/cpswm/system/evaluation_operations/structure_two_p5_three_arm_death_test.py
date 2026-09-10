"""Matched direct-P5 SEARCH/PUT_BACK development death test.

The run uses the project-owner-selected A1 exogenous observation schedule and
B1 learned conditional location head.  Evaluator truth is used only to fit the
training-only labels and to score already committed typed actions.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Final, Literal, cast
from uuid import UUID

import numpy as np
import numpy.typing as npt
from pydantic import Field, model_validator

from cpswm.contracts import (
    DetectionFailureReason,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
    reject_truth_leakage,
)
from cpswm.contracts.base import ContractModel
from cpswm.contracts.hidden_event_evidence import EventMechanism
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
    _locations,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    ProjectTwoReplayDataset,
    enforce_project_two_replay_gate,
)
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_direct_trace_probe import (
    _ProbeTraceSink,
    _router_features,
    _utilities,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
    TypedLocationPosterior,
)
from cpswm.system.evaluation_operations.structure_two_task8_online_compute import (
    ARM_TWO_STAGE,
    CAUSE_GROUPS,
    EVENT_GROUPS,
    _fit_arm,
    _LearnedModel,
)
from cpswm.system.prototype_spine import PrototypeTransition
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
    AdaptiveExecutionContext,
)
from cpswm.system.structure_two_execution import verify_execution_trace
from cpswm.system.structure_two_production_system import (
    StructureTwoProductionSystem,
    build_production_assembly_manifest,
)
from cpswm.world_model.grounded_search import (
    RealizedCIAVObservation,
    VerificationCause,
    verification_cause_hypothesis_id,
)

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-matched-three-arm-death-test@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_three_arm_death_test_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json"
)
EXPECTED_SCHEDULER: Final = "exogenous_precommitted_schedule"
EXPECTED_LOCATION_HEAD: Final = "shared_conditional_location_head_given_cause_event"
OBSERVATION_RELEASE_PHASE: Final = "before_typed_actions_committed"
EVALUATOR_TRUTH_RELEASE_PHASE: Final = "after_typed_actions_committed"
CLAIM_BOUNDARY: Final = (
    "This fresh D0 development result evaluates separate SEARCH and PUT_BACK signals for "
    "evaluation-only direct P5 under an exactly matched exogenous CIAV stream. It does not "
    "aggregate the tasks, estimate production CIAV net utility, pass Task 7/8/9, validate "
    "adaptive routing, authorize scientific superiority, establish external validity, or "
    "narrow Structure Two."
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise(values: Mapping[UUID, float], support: Sequence[UUID]) -> dict[UUID, float]:
    checked = {location: max(0.0, float(values.get(location, 0.0))) for location in support}
    total = sum(checked.values())
    if total <= 0.0:
        return {location: 1.0 / len(support) for location in support}
    return {location: value / total for location, value in checked.items()}


def _rank_first(values: Mapping[UUID, float], support: Sequence[UUID]) -> UUID:
    return max(
        enumerate(support),
        key=lambda item: (float(values.get(item[1], 0.0)), -item[0]),
    )[1]


class PrecommittedCIAVPacket(ContractModel):
    """One robot-visible outcome bound to an outcome-free A1 schedule commitment."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    protocol_id: Literal["structure-two-p5-matched-three-arm-death-test@0.1-development"] = (
        PROTOCOL_ID
    )
    episode_id: UUID
    step_id: UUID
    schedule_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_step_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: ObservationActionCandidate
    candidate_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_action_id: UUID
    realized_outcome: ObservationOutcome
    realized_detected_location_id: UUID | None = None
    realized_observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_budget_before: float = Field(ge=0.0)
    observation_release_phase: Literal["before_typed_actions_committed"] = OBSERVATION_RELEASE_PHASE
    evaluator_truth_release_phase: Literal["after_typed_actions_committed"] = (
        EVALUATOR_TRUTH_RELEASE_PHASE
    )
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_packet(self) -> PrecommittedCIAVPacket:
        if self.candidate.action_id != self.selected_action_id:
            raise ValueError("A1 packet selected action differs from its only candidate")
        if self.candidate_set_sha256 != content_sha256((self.candidate,)):
            raise ValueError("A1 packet candidate-set hash mismatch")
        detected = self.realized_outcome is ObservationOutcome.DETECTED
        if detected != (self.realized_detected_location_id is not None):
            raise ValueError("A1 packet detection outcome/location mismatch")
        observation = {
            "visible_step_sha256": self.visible_step_sha256,
            "outcome": self.realized_outcome.value,
            "detected_location_id": (
                str(self.realized_detected_location_id)
                if self.realized_detected_location_id is not None
                else None
            ),
        }
        if self.realized_observation_sha256 != content_sha256(observation):
            raise ValueError("A1 packet realized observation hash mismatch")
        unsigned = self.model_dump(mode="json", exclude={"packet_sha256"})
        if self.packet_sha256 != content_sha256(unsigned):
            raise ValueError("A1 packet hash mismatch")
        return self

    @classmethod
    def seal(
        cls,
        *,
        episode_id: UUID,
        step: ProjectTwoReplayStep,
        schedule_commitment_sha256: str,
        candidate: ObservationActionCandidate,
        privacy_budget_before: float,
    ) -> PrecommittedCIAVPacket:
        visible_step_sha256 = content_sha256(step)
        detected_location = (
            step.after.detected_location_id
            if step.after is not None and step.after.outcome is ObservationOutcome.DETECTED
            else None
        )
        outcome = (
            ObservationOutcome.DETECTED
            if detected_location is not None
            else ObservationOutcome.NOT_OBSERVED
        )
        observation = {
            "visible_step_sha256": visible_step_sha256,
            "outcome": outcome.value,
            "detected_location_id": str(detected_location) if detected_location else None,
        }
        payload = {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "episode_id": episode_id,
            "step_id": step.step_id,
            "schedule_commitment_sha256": schedule_commitment_sha256,
            "visible_step_sha256": visible_step_sha256,
            "candidate": candidate,
            "candidate_set_sha256": content_sha256((candidate,)),
            "selected_action_id": candidate.action_id,
            "realized_outcome": outcome,
            "realized_detected_location_id": detected_location,
            "realized_observation_sha256": content_sha256(observation),
            "privacy_budget_before": privacy_budget_before,
            "observation_release_phase": OBSERVATION_RELEASE_PHASE,
            "evaluator_truth_release_phase": EVALUATOR_TRUTH_RELEASE_PHASE,
        }
        return cls(**payload, packet_sha256=content_sha256(payload))


class CIAVConsumptionReceipt(ContractModel):
    """An arm-specific state transition over one exactly shared packet."""

    arm: P5ComparisonArm
    episode_id: UUID
    step_id: UUID
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_action_id: UUID
    realized_observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    motion_cost: float = Field(ge=0.0)
    time_cost: float = Field(ge=0.0)
    interruption_cost: float = Field(ge=0.0)
    privacy_cost: float = Field(ge=0.0)
    safety_cost: float = Field(ge=0.0)
    privacy_budget_before: float = Field(ge=0.0)
    privacy_budget_after: float = Field(ge=0.0)
    observation_release_phase: Literal["before_typed_actions_committed"] = OBSERVATION_RELEASE_PHASE
    evaluator_truth_release_phase: Literal["after_typed_actions_committed"] = (
        EVALUATOR_TRUTH_RELEASE_PHASE
    )
    consumer_state_before_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consumer_state_after_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_kind: str = Field(min_length=1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> CIAVConsumptionReceipt:
        values = (
            self.motion_cost,
            self.time_cost,
            self.interruption_cost,
            self.privacy_cost,
            self.safety_cost,
            self.privacy_budget_before,
            self.privacy_budget_after,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("CIAV costs and budgets must be finite")
        expected_budget = self.privacy_budget_before - self.privacy_cost
        if not math.isclose(self.privacy_budget_after, expected_budget, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("CIAV privacy budget delta differs from privacy cost")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != content_sha256(unsigned):
            raise ValueError("CIAV consumption receipt hash mismatch")
        return self

    @classmethod
    def seal(
        cls,
        *,
        arm: P5ComparisonArm,
        packet: PrecommittedCIAVPacket,
        consumer_state_before_sha256: str,
        consumer_state_after_sha256: str,
        closure_kind: str,
    ) -> CIAVConsumptionReceipt:
        action = packet.candidate
        payload = {
            "arm": arm,
            "episode_id": packet.episode_id,
            "step_id": packet.step_id,
            "packet_sha256": packet.packet_sha256,
            "schedule_commitment_sha256": packet.schedule_commitment_sha256,
            "candidate_set_sha256": packet.candidate_set_sha256,
            "selected_action_id": packet.selected_action_id,
            "realized_observation_sha256": packet.realized_observation_sha256,
            "motion_cost": action.motion_cost,
            "time_cost": action.time_cost,
            "interruption_cost": action.interruption_cost,
            "privacy_cost": action.privacy_cost,
            "safety_cost": action.safety_cost,
            "privacy_budget_before": packet.privacy_budget_before,
            "privacy_budget_after": packet.privacy_budget_before - action.privacy_cost,
            "observation_release_phase": OBSERVATION_RELEASE_PHASE,
            "evaluator_truth_release_phase": EVALUATOR_TRUTH_RELEASE_PHASE,
            "consumer_state_before_sha256": consumer_state_before_sha256,
            "consumer_state_after_sha256": consumer_state_after_sha256,
            "closure_kind": closure_kind,
        }
        return cls(**payload, receipt_sha256=content_sha256(payload))


def verify_matched_consumption(receipts: Sequence[CIAVConsumptionReceipt]) -> None:
    if tuple(receipt.arm for receipt in receipts) != tuple(P5ComparisonArm):
        raise ValueError("CIAV receipts must cover all three registered arms in order")
    anchor = receipts[0]
    common = (
        "episode_id",
        "step_id",
        "packet_sha256",
        "schedule_commitment_sha256",
        "candidate_set_sha256",
        "selected_action_id",
        "realized_observation_sha256",
        "motion_cost",
        "time_cost",
        "interruption_cost",
        "privacy_cost",
        "safety_cost",
        "privacy_budget_before",
        "privacy_budget_after",
        "observation_release_phase",
        "evaluator_truth_release_phase",
    )
    for receipt in receipts:
        CIAVConsumptionReceipt.model_validate(receipt.model_dump(mode="json"))
        if any(getattr(receipt, name) != getattr(anchor, name) for name in common):
            raise ValueError("CIAV information, action, outcome, cost, or release phase differs")


def _candidate_for_step(step: ProjectTwoReplayStep) -> ObservationActionCandidate:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return ObservationActionCandidate(
        action_id=content_uuid(PROTOCOL_ID, {"step_id": str(step.step_id), "kind": "A1-CIAV"}),
        action_type=ObservationActionType.MICRO_VERIFY,
        label="A1 exogenous precommitted micro verification",
        observation_likelihood_model_id="structure-two-p5-A1-neutral-detection@0.1",
        calibration_domain="D0 development matched three-arm",
        outcome_likelihoods={
            ObservationOutcome.DETECTED.value: {item: 0.8 for item in hypotheses},
            ObservationOutcome.NOT_OBSERVED.value: {item: 0.2 for item in hypotheses},
        },
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )


def _episode_schedule_commitment(episode: ProjectTwoReplayEpisode) -> str:
    """Commit action identities and costs without committing realized outcomes."""

    rows = []
    for step in episode.steps:
        action = _candidate_for_step(step)
        rows.append(
            {
                "episode_id": str(episode.episode_id),
                "step_id": str(step.step_id),
                "selected_action_id": str(action.action_id),
                "candidate_set_sha256": content_sha256((action,)),
                "costs": {
                    "motion": action.motion_cost,
                    "time": action.time_cost,
                    "interruption": action.interruption_cost,
                    "privacy": action.privacy_cost,
                    "safety": action.safety_cost,
                },
            }
        )
    return content_sha256(
        {
            "scheduler": EXPECTED_SCHEDULER,
            "episode_id": str(episode.episode_id),
            "outcomes_present": False,
            "rows": rows,
        }
    )


def _packet_for_step(
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    *,
    schedule_commitment_sha256: str,
) -> PrecommittedCIAVPacket:
    return PrecommittedCIAVPacket.seal(
        episode_id=episode.episode_id,
        step=step,
        schedule_commitment_sha256=schedule_commitment_sha256,
        candidate=_candidate_for_step(step),
        privacy_budget_before=1.0,
    )


def _make_realizer(
    packet: PrecommittedCIAVPacket,
) -> Callable[[ObservationOpportunityRecord], RealizedCIAVObservation]:
    outcome_label = packet.realized_outcome.value
    detection_outcome = packet.realized_outcome
    model_id = packet.candidate.observation_likelihood_model_id
    failure_reason = (
        DetectionFailureReason.NOT_APPLICABLE
        if detection_outcome is ObservationOutcome.DETECTED
        else DetectionFailureReason.OUT_OF_VIEW
    )
    occlusion_state = (
        OcclusionState.CLEAR
        if detection_outcome is ObservationOutcome.DETECTED
        else OcclusionState.UNKNOWN
    )

    def realize(_opportunity: ObservationOpportunityRecord) -> RealizedCIAVObservation:
        return RealizedCIAVObservation(
            outcome_label=outcome_label,
            likelihood_model_id=model_id,
            detection_outcome=detection_outcome,
            failure_reason=failure_reason,
            occlusion_state=occlusion_state,
        )

    return realize


def _ciav_input(
    packet: PrecommittedCIAVPacket,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    locations: Sequence[UUID],
) -> AdaptiveCIAVRuntimeInput:
    actors = tuple(dict.fromkeys((*episode.resident_actor_keys, "unknown_actor")))
    expected = packet.realized_detected_location_id or locations[0]
    assert step.observation_opportunity is not None
    return AdaptiveCIAVRuntimeInput(
        actions=(packet.candidate,),
        consolidation_decision_utilities=_utilities(),
        terminal_decision_utilities=_utilities(),
        privacy_budget=packet.privacy_budget_before,
        opportunity_time=step.timestamp + timedelta(microseconds=1),
        actor_likelihoods_by_outcome={
            outcome: dict.fromkeys(actors, 1.0) for outcome in packet.candidate.outcome_likelihoods
        },
        expected_detected_location_id=expected,
        selection_probability=1.0,
        p_visible_given_state=step.observation_opportunity.p_visible_given_state,
        p_detect_given_visible=step.observation_opportunity.p_detect_given_visible,
        realizer=_make_realizer(packet),
        minimum_net_value=-1.0,
    )


def _transition(
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    step_index: int,
) -> PrototypeTransition:
    if step.before is None or step.after is None or step.observation_opportunity is None:
        raise ValueError("positive direct P5 transition requires before, after, and opportunity")
    actors = tuple(dict.fromkeys((*episode.resident_actor_keys, "unknown_actor")))
    return PrototypeTransition(
        opportunity=step.observation_opportunity,
        before=step.before,
        after=step.after,
        actor_prior={actor: 1.0 / len(actors) for actor in actors},
        evidence=tuple(
            item
            for item in (
                step.actor_evidence,
                step.mechanism_evidence,
                step.ordered_role_evidence,
            )
            if item is not None
        ),
        context_key="D0-replay",
        context_value=step_index / max(1, len(episode.steps) - 1),
    )


class DirectP5LocationAdapter:
    """Evaluation-only P5 plus an honest no-transition negative observation closure."""

    arm = P5ComparisonArm.DIRECT_P5

    def __init__(self, episode: ProjectTwoReplayEpisode) -> None:
        self.episode = episode
        self.locations = _locations(episode)
        self.system = StructureTwoProductionSystem(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=self.locations,
            authorization_scope_id=content_uuid(
                PROTOCOL_ID, {"episode_id": str(episode.episode_id), "scope": "direct-P5"}
            ),
            adaptive_authorization_policy=AdaptiveAuthorizationPolicy(
                policy_id="structure-two-p5-death-test-evaluation-only",
                memory_transition_authorized=True,
                privacy_policy_satisfied=True,
                safety_context_authorized=True,
            ),
        )
        self._current = {location: 1.0 / len(self.locations) for location in self.locations}
        self.full_p5_transition_count = 0
        self.negative_ciav_opceu_closure_count = 0
        self.transition_dependent_no_new_transition_count = 0
        self.all_seven_primary_trace_count = 0

    def _state_sha256(self) -> str:
        return content_sha256(
            {
                "runtime": self.system.adaptive_router_state_sha256(),
                "current": tuple((str(key), value) for key, value in self._current.items()),
                "full_p5_transition_count": self.full_p5_transition_count,
                "negative_ciav_opceu_closure_count": self.negative_ciav_opceu_closure_count,
                "transition_dependent_no_new_transition_count": (
                    self.transition_dependent_no_new_transition_count
                ),
            }
        )

    def consume_matched_ciav_packet(
        self,
        packet: PrecommittedCIAVPacket,
        step: ProjectTwoReplayStep,
        *,
        step_index: int,
    ) -> CIAVConsumptionReceipt:
        _validate_packet_step(packet, self.episode, step)
        before = self._state_sha256()
        if packet.realized_outcome is ObservationOutcome.DETECTED:
            transition = _transition(self.episode, step, step_index)
            sink = _ProbeTraceSink()
            result = self.system.process_evaluation_direct_p5_transition(
                transition,
                context=AdaptiveExecutionContext(
                    router_features=_router_features(self.system),
                    step_index=step_index,
                    ciav_input=_ciav_input(packet, self.episode, step, self.locations),
                ),
                trace_sink=sink,
            )
            trace = sink.trace
            if trace is None:
                raise RuntimeError("direct P5 did not commit an execution trace")
            verify_execution_trace(trace)
            if not trace.all_seven_operators_invoked or trace.plan.plan_id != "P5_FULL_EAGER":
                raise RuntimeError("direct P5 did not execute the registered seven-operator plan")
            if (
                result.ciav_plan is None
                or result.ciav_plan.selected_action_id != packet.selected_action_id
                or result.ciav_receipt is None
                or result.ciav_receipt.detection.outcome is not packet.realized_outcome
            ):
                raise RuntimeError("direct P5 CIAV consumption differs from the A1 packet")
            assert packet.realized_detected_location_id is not None
            if (
                result.ciav_receipt.detection.detected_location_id
                != packet.realized_detected_location_id
            ):
                raise RuntimeError("direct P5 consumed a substituted detected location")
            self._current = {
                location: float(location == packet.realized_detected_location_id)
                for location in self.locations
            }
            self.full_p5_transition_count += 1
            self.all_seven_primary_trace_count += 1
            closure_kind = f"full_p5:{trace.feedback_closure_kind}"
        else:
            ciav_input = _ciav_input(packet, self.episode, step, self.locations)
            opportunity = step.observation_opportunity
            assert opportunity is not None
            actors = tuple(
                actor for actor in self.episode.resident_actor_keys if actor != "unknown_actor"
            )
            open_actors = tuple(dict.fromkeys((*actors, "unknown_actor")))
            receipt = self.system.ciav_opceu_loop.execute_selected_action(
                action=packet.candidate,
                update_id=content_uuid(
                    PROTOCOL_ID, {"step_id": str(step.step_id), "kind": "negative-closure"}
                ),
                household_id=opportunity.metadata.household_id,
                session_id=opportunity.metadata.session_id,
                trace_id=opportunity.metadata.trace_id,
                opportunity_time=ciav_input.opportunity_time,
                object_instance_id=step.object_instance_id,
                actor_keys=actors,
                actor_prior={actor: 1.0 / len(open_actors) for actor in open_actors},
                actor_likelihoods_by_outcome={
                    outcome: dict.fromkeys(open_actors, 1.0)
                    for outcome in packet.candidate.outcome_likelihoods
                },
                location_keys=tuple(str(location) for location in self.locations),
                expected_detected_location_id=self.locations[0],
                selection_probability=1.0,
                p_visible_given_state=opportunity.p_visible_given_state,
                p_detect_given_visible=opportunity.p_detect_given_visible,
                realizer=ciav_input.realizer,
            )
            if receipt.detection.outcome is not ObservationOutcome.NOT_OBSERVED:
                raise RuntimeError("negative P5 closure received a substituted positive outcome")
            self.negative_ciav_opceu_closure_count += 1
            self.transition_dependent_no_new_transition_count += 1
            closure_kind = "negative_ciav_opceu_explicit_no_new_transition"
        after = self._state_sha256()
        return CIAVConsumptionReceipt.seal(
            arm=self.arm,
            packet=packet,
            consumer_state_before_sha256=before,
            consumer_state_after_sha256=after,
            closure_kind=closure_kind,
        )

    def predict_location_posteriors(self, packet: PrecommittedCIAVPacket) -> TypedLocationPosterior:
        habit = self.system.action_location_distribution(self.system.current_snapshot)
        state = self._state_sha256()
        return TypedLocationPosterior.seal(
            arm=self.arm,
            episode_id=self.episode.episode_id,
            step_id=packet.step_id,
            target_object_id=self.episode.steps[0].object_instance_id,
            source_visible_step_sha256=packet.visible_step_sha256,
            belief_state_sha256=state,
            location_support=self.locations,
            current_location_distribution=_normalise(self._current, self.locations),
            owner_habit_location_distribution=_normalise(habit, self.locations),
        )


def _validate_packet_step(
    packet: PrecommittedCIAVPacket,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
) -> None:
    reject_truth_leakage(step.model_dump(mode="python"))
    if packet.episode_id != episode.episode_id or packet.step_id != step.step_id:
        raise ValueError("CIAV packet episode/step binding mismatch")
    if packet.visible_step_sha256 != content_sha256(step):
        raise ValueError("CIAV packet visible-step binding mismatch")
    expected_action = _candidate_for_step(step)
    if packet.candidate != expected_action:
        raise ValueError("CIAV packet candidate differs from the precommitted A1 action")


def _feature_row(
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    *,
    step_index: int,
    last_observed: UUID | None,
    seen_counts: Mapping[UUID, float],
) -> tuple[float, ...]:
    actor = (
        dict(step.actor_evidence.actor_posterior)
        if step.actor_evidence is not None
        else dict.fromkeys((*episode.resident_actor_keys, "unknown_actor"), 0.0)
    )
    owner_mass = float(actor.get(episode.owner_actor_key, 0.0))
    unknown_actor = float(actor.get("unknown_actor", 0.0))
    non_owner_mass = max(0.0, 1.0 - owner_mass - unknown_actor)
    mechanism = (
        dict(step.mechanism_evidence.mechanism_posterior)
        if step.mechanism_evidence is not None
        else {}
    )
    direct = float(mechanism.get(EventMechanism.DIRECT_RELOCATION, 0.0))
    handoff = float(mechanism.get(EventMechanism.HANDOFF_RELOCATION, 0.0))
    unknown_mechanism = float(mechanism.get(EventMechanism.UNKNOWN_MECHANISM, 0.0))
    current = step.after.detected_location_id if step.after is not None else None
    observed = float(current is not None)
    changed = float(current is not None and last_observed is not None and current != last_observed)
    seen = float(seen_counts.get(current, 0.0)) if current is not None else 0.0
    seen_total = max(1.0, sum(seen_counts.values()))
    return (
        observed,
        float(step.visibility_probability),
        float(step.detection_confidence or 0.0),
        owner_mass,
        non_owner_mass,
        unknown_actor,
        direct,
        handoff,
        unknown_mechanism,
        changed,
        seen / seen_total,
        step_index / max(1, len(episode.steps) - 1),
    )


def _truth_labels(
    episode: ProjectTwoReplayEpisode,
    truth: ProjectTwoEvaluatorStepTruth,
    previous_owner_habit: UUID | None,
) -> tuple[int, int]:
    regime_change = (
        previous_owner_habit is not None and truth.true_owner_habit_location != previous_owner_habit
    )
    if truth.true_actor != episode.owner_actor_key:
        cause = CAUSE_GROUPS.index("actor")
    elif regime_change:
        cause = CAUSE_GROUPS.index("habit")
    else:
        cause = CAUSE_GROUPS.index("other")
    if truth.true_mechanism is EventMechanism.HANDOFF_RELOCATION and not regime_change:
        event = EVENT_GROUPS.index("handoff_stay")
    elif regime_change:
        event = EVENT_GROUPS.index("regime_change")
    else:
        event = EVENT_GROUPS.index("other")
    return cause, event


@dataclass(frozen=True, slots=True)
class LearnedTrainingMaterial:
    raw: FloatArray
    cause: IntArray
    event: IntArray
    location_successes: FloatArray
    location_totals: FloatArray
    training_episode_ids: tuple[UUID, ...]


def _learned_training_material(dataset: ProjectTwoReplayDataset) -> LearnedTrainingMaterial:
    rows: list[tuple[float, ...]] = []
    causes: list[int] = []
    events: list[int] = []
    successes = np.zeros((len(CAUSE_GROUPS), len(EVENT_GROUPS)), dtype=np.float64)
    totals = np.zeros_like(successes)
    episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)
    if not episodes:
        raise ValueError("B1 learned location head requires a non-empty training split")
    for episode in episodes:
        envelope = dataset.truth_for(episode.episode_id)
        last_observed: UUID | None = None
        seen_counts: defaultdict[UUID, float] = defaultdict(float)
        previous_owner_habit: UUID | None = None
        for index, step in enumerate(episode.steps):
            rows.append(
                _feature_row(
                    episode,
                    step,
                    step_index=index,
                    last_observed=last_observed,
                    seen_counts=seen_counts,
                )
            )
            truth = envelope.truth_by_step[step.step_id]
            cause, event = _truth_labels(episode, truth, previous_owner_habit)
            causes.append(cause)
            events.append(event)
            current = step.after.detected_location_id if step.after is not None else None
            if current is not None:
                totals[cause, event] += 1.0
                successes[cause, event] += float(current == truth.true_owner_habit_location)
                seen_counts[current] += 1.0
                last_observed = current
            previous_owner_habit = truth.true_owner_habit_location
    return LearnedTrainingMaterial(
        raw=np.asarray(rows, dtype=np.float64),
        cause=np.asarray(causes, dtype=np.int64),
        event=np.asarray(events, dtype=np.int64),
        location_successes=successes,
        location_totals=totals,
        training_episode_ids=tuple(episode.episode_id for episode in episodes),
    )


class LearnedTwoStageLocationAdapter:
    """Task-8 two-stage predictor plus the selected B1 conditional location head."""

    arm = P5ComparisonArm.LEARNED_TWO_STAGE

    def __init__(
        self,
        episode: ProjectTwoReplayEpisode,
        *,
        model: _LearnedModel,
        location_successes: FloatArray,
        location_totals: FloatArray,
        smoothing: float,
    ) -> None:
        if model.arm != ARM_TWO_STAGE or smoothing <= 0.0:
            raise ValueError("B1 requires the learned matched two-stage arm and positive smoothing")
        self.episode = episode
        self.locations = _locations(episode)
        self.model = model
        self.smoothing = float(smoothing)
        self.theta = (location_successes + smoothing) / (location_totals + 2.0 * smoothing)
        self.habit_counts = dict.fromkeys(self.locations, self.smoothing)
        self.last_observed: UUID | None = None
        self.seen_counts: defaultdict[UUID, float] = defaultdict(float)
        self.current = dict.fromkeys(self.locations, 1.0 / len(self.locations))
        self.last_joint = np.full(
            len(CAUSE_GROUPS) * len(EVENT_GROUPS),
            1.0 / (len(CAUSE_GROUPS) * len(EVENT_GROUPS)),
            dtype=np.float64,
        )

    def _state_sha256(self) -> str:
        return content_sha256(
            {
                "model_arm": self.model.arm,
                "smoothing": self.smoothing,
                "theta": self.theta.tolist(),
                "habit_counts": tuple(
                    (str(location), self.habit_counts[location]) for location in self.locations
                ),
                "current": tuple(
                    (str(location), self.current[location]) for location in self.locations
                ),
                "last_observed": str(self.last_observed) if self.last_observed else None,
                "last_joint": self.last_joint.tolist(),
            }
        )

    def consume_matched_ciav_packet(
        self,
        packet: PrecommittedCIAVPacket,
        step: ProjectTwoReplayStep,
        *,
        step_index: int,
    ) -> CIAVConsumptionReceipt:
        _validate_packet_step(packet, self.episode, step)
        before = self._state_sha256()
        raw = np.asarray(
            [
                _feature_row(
                    self.episode,
                    step,
                    step_index=step_index,
                    last_observed=self.last_observed,
                    seen_counts=self.seen_counts,
                )
            ],
            dtype=np.float64,
        )
        self.last_joint = self.model.predict_joint(raw)[0]
        current = packet.realized_detected_location_id
        if current is not None:
            owner_habit_match = 0.0
            for cause in range(len(CAUSE_GROUPS)):
                for event in range(len(EVENT_GROUPS)):
                    owner_habit_match += float(
                        self.last_joint[cause * len(EVENT_GROUPS) + event]
                    ) * float(self.theta[cause, event])
            self.habit_counts[current] += owner_habit_match
            self.current = {location: float(location == current) for location in self.locations}
            self.seen_counts[current] += 1.0
            self.last_observed = current
            closure_kind = "learned_two_stage_positive_update"
        else:
            closure_kind = "learned_two_stage_negative_carry_forward"
        after = self._state_sha256()
        return CIAVConsumptionReceipt.seal(
            arm=self.arm,
            packet=packet,
            consumer_state_before_sha256=before,
            consumer_state_after_sha256=after,
            closure_kind=closure_kind,
        )

    def predict_location_posteriors(self, packet: PrecommittedCIAVPacket) -> TypedLocationPosterior:
        return TypedLocationPosterior.seal(
            arm=self.arm,
            episode_id=self.episode.episode_id,
            step_id=packet.step_id,
            target_object_id=self.episode.steps[0].object_instance_id,
            source_visible_step_sha256=packet.visible_step_sha256,
            belief_state_sha256=self._state_sha256(),
            location_support=self.locations,
            current_location_distribution=_normalise(self.current, self.locations),
            owner_habit_location_distribution=_normalise(self.habit_counts, self.locations),
        )


class AMGLocationAdapter:
    """Distribution adapter over the existing independently tuned AMG replay state."""

    arm = P5ComparisonArm.TUNED_AMG

    def __init__(self, episode: ProjectTwoReplayEpisode, *, parameter: float) -> None:
        self.episode = episode
        self.locations = _locations(episode)
        self.parameter = float(parameter)
        self.state = _AMGOpenWorldMethod(episode, mode="amg", parameter=self.parameter)
        self.current = dict.fromkeys(self.locations, 1.0 / len(self.locations))

    def _state_sha256(self) -> str:
        prediction = self.state.predict()
        return content_sha256(
            {
                "parameter": self.parameter,
                "last": str(self.state.last) if self.state.last else None,
                "amg_owner_location": (
                    str(self.state.amg_owner_location)
                    if self.state.amg_owner_location is not None
                    else None
                ),
                "put_back": str(prediction.put_back),
                "search_order": tuple(str(item) for item in prediction.search_order),
                "current": tuple(
                    (str(location), self.current[location]) for location in self.locations
                ),
            }
        )

    def consume_matched_ciav_packet(
        self,
        packet: PrecommittedCIAVPacket,
        step: ProjectTwoReplayStep,
        *,
        step_index: int,
    ) -> CIAVConsumptionReceipt:
        del step_index
        _validate_packet_step(packet, self.episode, step)
        before = self._state_sha256()
        self.state.observe(step)
        current = packet.realized_detected_location_id
        if current is not None:
            self.current = {location: float(location == current) for location in self.locations}
            closure_kind = "amg_positive_update"
        else:
            closure_kind = "amg_negative_carry_forward"
        self.state.feedback(step)
        after = self._state_sha256()
        return CIAVConsumptionReceipt.seal(
            arm=self.arm,
            packet=packet,
            consumer_state_before_sha256=before,
            consumer_state_after_sha256=after,
            closure_kind=closure_kind,
        )

    def predict_location_posteriors(self, packet: PrecommittedCIAVPacket) -> TypedLocationPosterior:
        prediction = self.state.predict()
        habit = {location: float(location == prediction.put_back) for location in self.locations}
        return TypedLocationPosterior.seal(
            arm=self.arm,
            episode_id=self.episode.episode_id,
            step_id=packet.step_id,
            target_object_id=self.episode.steps[0].object_instance_id,
            source_visible_step_sha256=packet.visible_step_sha256,
            belief_state_sha256=self._state_sha256(),
            location_support=self.locations,
            current_location_distribution=_normalise(self.current, self.locations),
            owner_habit_location_distribution=habit,
        )


@dataclass(frozen=True, slots=True)
class _EpisodeMetric:
    episode_id: UUID
    arm: P5ComparisonArm
    step_count: int
    search_errors: int
    put_back_errors: int
    normalized_search_regret: float
    typed_action_chain_sha256: str
    ciav_receipt_chain_sha256: str
    schedule_commitment_sha256: str
    full_p5_transition_count: int = 0
    negative_ciav_opceu_closure_count: int = 0
    transition_dependent_no_new_transition_count: int = 0
    all_seven_primary_trace_count: int = 0

    @property
    def search_error_rate(self) -> float:
        return self.search_errors / self.step_count

    @property
    def put_back_error_rate(self) -> float:
        return self.put_back_errors / self.step_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": str(self.episode_id),
            "arm": self.arm.value,
            "step_count": self.step_count,
            "search_errors": self.search_errors,
            "search_error_rate": self.search_error_rate,
            "put_back_errors": self.put_back_errors,
            "put_back_error_rate": self.put_back_error_rate,
            "normalized_search_regret": self.normalized_search_regret,
            "typed_action_chain_sha256": self.typed_action_chain_sha256,
            "ciav_receipt_chain_sha256": self.ciav_receipt_chain_sha256,
            "schedule_commitment_sha256": self.schedule_commitment_sha256,
            "full_p5_transition_count": self.full_p5_transition_count,
            "negative_ciav_opceu_closure_count": self.negative_ciav_opceu_closure_count,
            "transition_dependent_no_new_transition_count": (
                self.transition_dependent_no_new_transition_count
            ),
            "all_seven_primary_trace_count": self.all_seven_primary_trace_count,
        }


def _decode_and_score(
    posterior: TypedLocationPosterior,
    *,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    step_index: int,
    run_execution_id: UUID,
    truth: ProjectTwoEvaluatorStepTruth,
) -> tuple[int, int, float, dict[str, Any]]:
    readout = posterior.decode(
        step_index=step_index,
        run_execution_id=run_execution_id,
        visible_observation=step.model_dump(mode="json"),
    )
    search_locations = tuple(action.location_id for action in readout.search_plan)
    put_back = readout.put_back_action.location_id
    search_error = int(search_locations[0] != truth.true_location)
    put_back_error = int(put_back != truth.true_owner_habit_location)
    try:
        inspected = search_locations.index(truth.true_location) + 1
    except ValueError:
        inspected = len(search_locations)
    normalized_regret = (inspected - 1) / max(1, len(search_locations) - 1)
    return (
        search_error,
        put_back_error,
        normalized_regret,
        {
            "posterior_sha256": posterior.posterior_sha256,
            "information_set_sha256": readout.information_set_sha256,
            "search_location_id": str(search_locations[0]),
            "put_back_location_id": str(put_back),
        },
    )


def _evaluate_single_state(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    state: LearnedTwoStageLocationAdapter | AMGLocationAdapter,
) -> _EpisodeMetric:
    schedule = _episode_schedule_commitment(episode)
    run_id = content_uuid(
        PROTOCOL_ID, {"episode_id": str(episode.episode_id), "arm": state.arm.value}
    )
    truth_envelope = dataset.truth_for(episode.episode_id)
    search_errors = put_errors = 0
    search_regret = 0.0
    actions: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for index, step in enumerate(episode.steps):
        packet = _packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        receipt = state.consume_matched_ciav_packet(packet, step, step_index=index)
        posterior = state.predict_location_posteriors(packet)
        truth = truth_envelope.truth_by_step[step.step_id]
        search_error, put_error, regret, action = _decode_and_score(
            posterior,
            episode=episode,
            step=step,
            step_index=index,
            run_execution_id=run_id,
            truth=truth,
        )
        search_errors += search_error
        put_errors += put_error
        search_regret += regret
        actions.append(action)
        receipts.append(receipt.model_dump(mode="json"))
    return _EpisodeMetric(
        episode_id=episode.episode_id,
        arm=state.arm,
        step_count=len(episode.steps),
        search_errors=search_errors,
        put_back_errors=put_errors,
        normalized_search_regret=search_regret / len(episode.steps),
        typed_action_chain_sha256=content_sha256(actions),
        ciav_receipt_chain_sha256=content_sha256(receipts),
        schedule_commitment_sha256=schedule,
    )


def _fit_learned_model(
    material: LearnedTrainingMaterial,
    params: Mapping[str, float | int],
) -> _LearnedModel:
    return _fit_arm(
        ARM_TWO_STAGE,
        material.raw,
        material.cause,
        material.event,
        base_width=int(params["base_width"]),
        learning_rate=float(params["learning_rate"]),
        l2=float(params["l2"]),
    )


def _validation_selection(
    dataset: ProjectTwoReplayDataset,
    config: Mapping[str, Any],
    material: LearnedTrainingMaterial,
) -> tuple[dict[str, Any], _LearnedModel, float, float]:
    validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    learned_config = cast(Mapping[str, Any], config["learned_two_stage"])
    learned_trials: list[dict[str, Any]] = []
    model_cache: dict[tuple[int, float, float], _LearnedModel] = {}
    for width in learned_config["base_widths"]:
        for learning_rate in learned_config["learning_rates"]:
            for l2 in learned_config["l2_values"]:
                key = (int(width), float(learning_rate), float(l2))
                model = _fit_learned_model(
                    material,
                    {"base_width": key[0], "learning_rate": key[1], "l2": key[2]},
                )
                model_cache[key] = model
                for smoothing in learned_config["location_smoothing_values"]:
                    metrics = [
                        _evaluate_single_state(
                            dataset,
                            episode,
                            LearnedTwoStageLocationAdapter(
                                episode,
                                model=model,
                                location_successes=material.location_successes,
                                location_totals=material.location_totals,
                                smoothing=float(smoothing),
                            ),
                        )
                        for episode in validation
                    ]
                    learned_trials.append(
                        {
                            "parameters": {
                                "base_width": key[0],
                                "learning_rate": key[1],
                                "l2": key[2],
                                "location_smoothing": float(smoothing),
                            },
                            "validation_put_back_error_rate": mean(
                                item.put_back_error_rate for item in metrics
                            ),
                            "validation_search_error_rate": mean(
                                item.search_error_rate for item in metrics
                            ),
                        }
                    )
    selected_learned = min(
        learned_trials,
        key=lambda row: (
            float(row["validation_put_back_error_rate"]),
            json.dumps(row["parameters"], sort_keys=True),
        ),
    )
    learned_parameters = cast(dict[str, Any], selected_learned["parameters"])
    learned_key = (
        int(learned_parameters["base_width"]),
        float(learned_parameters["learning_rate"]),
        float(learned_parameters["l2"]),
    )

    amg_trials: list[dict[str, Any]] = []
    for parameter in cast(Mapping[str, Any], config["amg"])["parameter_values"]:
        metrics = [
            _evaluate_single_state(
                dataset,
                episode,
                AMGLocationAdapter(episode, parameter=float(parameter)),
            )
            for episode in validation
        ]
        amg_trials.append(
            {
                "parameter": float(parameter),
                "validation_put_back_error_rate": mean(
                    item.put_back_error_rate for item in metrics
                ),
                "validation_search_error_rate": mean(item.search_error_rate for item in metrics),
            }
        )
    selected_amg = min(
        amg_trials,
        key=lambda row: (
            float(row["validation_put_back_error_rate"]),
            float(row["parameter"]),
        ),
    )
    receipt = {
        "selection_metric": "validation_put_back_error_rate",
        "training_episode_ids": [str(item) for item in material.training_episode_ids],
        "validation_episode_ids": [str(item.episode_id) for item in validation],
        "test_episode_ids_seen": [],
        "learned_trials": learned_trials,
        "selected_learned_parameters": learned_parameters,
        "amg_trials": amg_trials,
        "selected_amg_parameter": float(selected_amg["parameter"]),
    }
    receipt["content_sha256"] = content_sha256(receipt)
    return (
        receipt,
        model_cache[learned_key],
        float(learned_parameters["location_smoothing"]),
        float(selected_amg["parameter"]),
    )


def _evaluate_matched_test_episode(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    *,
    learned_model: _LearnedModel,
    material: LearnedTrainingMaterial,
    learned_smoothing: float,
    amg_parameter: float,
) -> tuple[_EpisodeMetric, ...]:
    schedule = _episode_schedule_commitment(episode)
    states = (
        DirectP5LocationAdapter(episode),
        LearnedTwoStageLocationAdapter(
            episode,
            model=learned_model,
            location_successes=material.location_successes,
            location_totals=material.location_totals,
            smoothing=learned_smoothing,
        ),
        AMGLocationAdapter(episode, parameter=amg_parameter),
    )
    if tuple(state.arm for state in states) != tuple(P5ComparisonArm):
        raise AssertionError("three-arm execution order drifted")
    run_id = content_uuid(PROTOCOL_ID, {"episode_id": str(episode.episode_id)})
    truth_envelope = dataset.truth_for(episode.episode_id)
    counters = {arm: {"search": 0, "put_back": 0, "regret": 0.0} for arm in P5ComparisonArm}
    action_rows: dict[P5ComparisonArm, list[dict[str, Any]]] = {arm: [] for arm in P5ComparisonArm}
    receipt_rows: dict[P5ComparisonArm, list[dict[str, Any]]] = {arm: [] for arm in P5ComparisonArm}
    for index, step in enumerate(episode.steps):
        packet = _packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        receipts = tuple(
            state.consume_matched_ciav_packet(packet, step, step_index=index) for state in states
        )
        verify_matched_consumption(receipts)
        posteriors = tuple(state.predict_location_posteriors(packet) for state in states)
        truth = truth_envelope.truth_by_step[step.step_id]
        for _state, posterior, receipt in zip(states, posteriors, receipts, strict=True):
            search_error, put_error, regret, action = _decode_and_score(
                posterior,
                episode=episode,
                step=step,
                step_index=index,
                run_execution_id=run_id,
                truth=truth,
            )
            counters[receipt.arm]["search"] += search_error
            counters[receipt.arm]["put_back"] += put_error
            counters[receipt.arm]["regret"] += regret
            action_rows[receipt.arm].append(action)
            receipt_rows[receipt.arm].append(receipt.model_dump(mode="json"))
    direct = states[0]
    output = []
    for state in states:
        values = counters[state.arm]
        output.append(
            _EpisodeMetric(
                episode_id=episode.episode_id,
                arm=state.arm,
                step_count=len(episode.steps),
                search_errors=int(values["search"]),
                put_back_errors=int(values["put_back"]),
                normalized_search_regret=float(values["regret"]) / len(episode.steps),
                typed_action_chain_sha256=content_sha256(action_rows[state.arm]),
                ciav_receipt_chain_sha256=content_sha256(receipt_rows[state.arm]),
                schedule_commitment_sha256=schedule,
                full_p5_transition_count=(
                    direct.full_p5_transition_count if state.arm is P5ComparisonArm.DIRECT_P5 else 0
                ),
                negative_ciav_opceu_closure_count=(
                    direct.negative_ciav_opceu_closure_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
                transition_dependent_no_new_transition_count=(
                    direct.transition_dependent_no_new_transition_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
                all_seven_primary_trace_count=(
                    direct.all_seven_primary_trace_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
            )
        )
    return tuple(output)


def _bootstrap_ci(values: Sequence[float], *, draws: int, seed: str) -> tuple[float, float]:
    if not values:
        raise ValueError("paired episode bootstrap requires values")
    rng = random.Random(seed)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return (
        samples[int(0.025 * draws)],
        samples[min(draws - 1, int(0.975 * draws))],
    )


def _summaries(metrics: Sequence[_EpisodeMetric]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for arm in P5ComparisonArm:
        rows = [item for item in metrics if item.arm is arm]
        output[arm.value] = {
            "episode_count": len(rows),
            "step_count": sum(item.step_count for item in rows),
            "search_error_rate": mean(item.search_error_rate for item in rows),
            "put_back_error_rate": mean(item.put_back_error_rate for item in rows),
            "normalized_search_regret": mean(item.normalized_search_regret for item in rows),
        }
    return output


def _pairwise_signal(
    metrics: Sequence[_EpisodeMetric], config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    signal_config = cast(Mapping[str, Any], config["signal_rule"])
    draws = int(signal_config["bootstrap_replicates"])
    minimum_absolute = float(signal_config["minimum_absolute_error_rate_improvement"])
    minimum_relative = float(signal_config["minimum_relative_error_rate_improvement"])
    by_key = {(item.episode_id, item.arm): item for item in metrics}
    episode_ids = tuple(
        item.episode_id for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5
    )
    rows: list[dict[str, Any]] = []
    per_task: dict[str, list[bool]] = {"search": [], "put_back": []}
    for task, attribute in (
        ("search", "search_error_rate"),
        ("put_back", "put_back_error_rate"),
    ):
        for comparator in (
            P5ComparisonArm.LEARNED_TWO_STAGE,
            P5ComparisonArm.TUNED_AMG,
        ):
            differences = [
                float(getattr(by_key[(episode_id, comparator)], attribute))
                - float(getattr(by_key[(episode_id, P5ComparisonArm.DIRECT_P5)], attribute))
                for episode_id in episode_ids
            ]
            comparator_mean = mean(
                float(getattr(by_key[(episode_id, comparator)], attribute))
                for episode_id in episode_ids
            )
            improvement = mean(differences)
            relative = improvement / comparator_mean if comparator_mean > 0.0 else 0.0
            ci = _bootstrap_ci(
                differences,
                draws=draws,
                seed=f"{PROTOCOL_ID}:{task}:{comparator.value}",
            )
            supported = (
                improvement >= minimum_absolute and relative >= minimum_relative and ci[0] > 0.0
            )
            per_task[task].append(supported)
            rows.append(
                {
                    "task": task,
                    "comparison": f"{comparator.value}_minus_direct_p5_full_eager",
                    "mean_error_rate_improvement": improvement,
                    "relative_error_rate_improvement": relative,
                    "paired_episode_confidence_interval_95": list(ci),
                    "registered_signal_supported": supported,
                }
            )
    task_signal = {task: all(values) for task, values in per_task.items()}
    return rows, {
        "search_signal_supported": task_signal["search"],
        "put_back_signal_supported": task_signal["put_back"],
        "p5_action_signal_detected": any(task_signal.values()),
        "combined_utility_evaluated": False,
    }


def _load_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    if (
        config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status") != "FROZEN_BEFORE_FIRST_EXECUTION"
        or config.get("arms") != [arm.value for arm in P5ComparisonArm]
        or config.get("shared_ciav", {}).get("scheduler") != EXPECTED_SCHEDULER
        or config.get("learned_two_stage", {}).get("location_head") != EXPECTED_LOCATION_HEAD
        or config.get("split_policy", {}).get("confirmatory") is not False
        or config.get("typed_actions", {}).get("combined_utility") != "UNRESOLVED_NOT_AGGREGATED"
        or config.get("claim_boundary")
        != (
            "This frozen D0 development death test can locate a SEARCH or PUT_BACK action "
            "signal for direct P5 under matched precommitted observation information and cost. "
            "It cannot aggregate the two tasks, estimate production CIAV net utility, pass "
            "Task 7/8/9, validate adaptive routing, authorize scientific superiority, "
            "establish external validity, or narrow Structure Two."
        )
    ):
        raise ValueError("P5 three-arm death-test configuration identity drifted")
    method_decision = json.loads(
        (root / Path(config["method_decision_source"])).read_text(encoding="utf-8")
    )
    if (
        method_decision.get("status") != "PROJECT_OWNER_SELECTED"
        or method_decision.get("shared_ciav_scheduler", {}).get("selection_label") != "A1"
        or method_decision.get("learned_two_stage_location_head", {}).get("selection_label") != "B1"
    ):
        raise ValueError("P5 A1+B1 project-owner decision binding is absent or drifted")
    return cast(dict[str, Any], config)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        "configuration": DEFAULT_CONFIG,
        "p5_first_decision": Path(str(config["decision_source"])),
        "A1_B1_method_decision": Path(str(config["method_decision_source"])),
        "dataset_configuration": Path(str(config["dataset_source"])),
        "execution_module": Path(__file__).resolve().relative_to(root),
        "typed_contract": Path(
            "src/cpswm/system/evaluation_operations/structure_two_p5_three_arm_contract.py"
        ),
        "shared_decoder": Path(
            "src/cpswm/system/evaluation_operations/structure_two_action_utility_construct_gate.py"
        ),
        "production_system": Path("src/cpswm/system/structure_two_production_system.py"),
        "task8_two_stage": Path(
            "src/cpswm/system/evaluation_operations/structure_two_task8_online_compute.py"
        ),
        "amg_adapter_source": Path(
            "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py"
        ),
    }
    binding: dict[str, Any] = {
        name: {"path": path.as_posix(), "sha256": _file_sha256(root / path)}
        for name, path in paths.items()
    }
    assembly = build_production_assembly_manifest(root)
    binding["production_assembly_manifest_sha256"] = assembly["content_sha256"]
    return binding


def run_p5_three_arm_death_test(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(
        root / Path(str(config["dataset_source"]))
    )
    if dataset_config.confirmatory:
        raise ValueError("P5 development death test cannot open confirmatory data")
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    material = _learned_training_material(dataset)
    selection, learned_model, smoothing, amg_parameter = _validation_selection(
        dataset, config, material
    )
    test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    metrics = [
        metric
        for episode in test
        for metric in _evaluate_matched_test_episode(
            dataset,
            episode,
            learned_model=learned_model,
            material=material,
            learned_smoothing=smoothing,
            amg_parameter=amg_parameter,
        )
    ]
    summaries = _summaries(metrics)
    pairwise, signal = _pairwise_signal(metrics, config)
    p5_metrics = [item for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5]
    detected_count = sum(item.full_p5_transition_count for item in p5_metrics)
    negative_count = sum(item.negative_ciav_opceu_closure_count for item in p5_metrics)
    if detected_count + negative_count != sum(len(episode.steps) for episode in test):
        raise RuntimeError("P5 positive and negative closures do not cover the test stream")
    status = (
        "P5_ACTION_SIGNAL_DETECTED"
        if signal["p5_action_signal_detected"]
        else "P5_ACTION_SIGNAL_NOT_DETECTED"
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": status,
        "source_binding": _source_binding(root, config),
        "data_scope": {
            "dataset_version": dataset.manifest.dataset_version,
            "train_episode_count": len(dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)),
            "validation_episode_count": len(
                dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
            ),
            "test_episode_count": len(test),
            "test_step_count": sum(len(episode.steps) for episode in test),
            "confirmatory": False,
        },
        "project_owner_decisions": {
            "shared_ciav_scheduler": EXPECTED_SCHEDULER,
            "learned_two_stage_location_head": EXPECTED_LOCATION_HEAD,
        },
        "validation_only_selection": selection,
        "test_episode_metrics": [item.to_dict() for item in metrics],
        "test_arm_summaries": summaries,
        "pairwise_episode_results": pairwise,
        "signal_gate": signal,
        "execution_audit": {
            "matched_ciav_step_count": sum(len(episode.steps) for episode in test),
            "exact_three_arm_receipt_match_established": True,
            "direct_p5_full_transition_count": detected_count,
            "direct_p5_all_seven_primary_trace_count": sum(
                item.all_seven_primary_trace_count for item in p5_metrics
            ),
            "direct_p5_negative_ciav_opceu_closure_count": negative_count,
            "negative_transition_fabrication_count": 0,
            "transition_dependent_explicit_no_new_transition_count": sum(
                item.transition_dependent_no_new_transition_count for item in p5_metrics
            ),
            "truth_visible_to_arms_before_typed_action_commit": False,
            "observation_release_phase": OBSERVATION_RELEASE_PHASE,
            "evaluator_truth_release_phase": EVALUATOR_TRUTH_RELEASE_PHASE,
        },
        "adaptive_router_policy": config["adaptive_router_policy"],
        "combined_utility_evaluated": False,
        "task_7_8_9_passed": False,
        "scientific_superiority_established": False,
        "external_validity_established": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def verify_p5_three_arm_death_test(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = False,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("P5 three-arm result identity drifted")
    if payload.get("status") not in {
        "P5_ACTION_SIGNAL_DETECTED",
        "P5_ACTION_SIGNAL_NOT_DETECTED",
    }:
        raise ValueError("P5 three-arm result status is not derived from the signal gate")
    if payload.get("claim_boundary") != CLAIM_BOUNDARY:
        raise ValueError("P5 three-arm result claim boundary drifted")
    if payload.get("content_sha256") != content_sha256(_unsigned(payload)):
        raise ValueError("P5 three-arm result hash mismatch")
    for field in (
        "combined_utility_evaluated",
        "task_7_8_9_passed",
        "scientific_superiority_established",
        "external_validity_established",
    ):
        if payload.get(field) is not False:
            raise ValueError("P5 development result promoted an unauthorized claim")
    config = _load_config(repository_root.resolve())
    if payload.get("source_binding") != _source_binding(repository_root.resolve(), config):
        raise ValueError("P5 three-arm result source binding mismatch")
    signal = cast(Mapping[str, Any], payload.get("signal_gate"))
    expected_status = (
        "P5_ACTION_SIGNAL_DETECTED"
        if signal.get("p5_action_signal_detected") is True
        else "P5_ACTION_SIGNAL_NOT_DETECTED"
    )
    if payload.get("status") != expected_status:
        raise ValueError("P5 result status differs from its retained signal gate")
    execution = cast(Mapping[str, Any], payload.get("execution_audit"))
    if (
        execution.get("exact_three_arm_receipt_match_established") is not True
        or execution.get("truth_visible_to_arms_before_typed_action_commit") is not False
        or execution.get("negative_transition_fabrication_count") != 0
        or execution.get("direct_p5_full_transition_count")
        != execution.get("direct_p5_all_seven_primary_trace_count")
    ):
        raise ValueError("P5 execution audit contains an unsupported positive claim")
    if fresh_recompute:
        expected = run_p5_three_arm_death_test(repository_root=repository_root)
        if dict(payload) != expected:
            raise ValueError("fresh P5 three-arm recomputation disagrees")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "AMGLocationAdapter",
    "CIAVConsumptionReceipt",
    "DirectP5LocationAdapter",
    "LearnedTwoStageLocationAdapter",
    "PrecommittedCIAVPacket",
    "run_p5_three_arm_death_test",
    "verify_matched_consumption",
    "verify_p5_three_arm_death_test",
]
