"""Auditable S3-1 multi-scenario oracle suite and machine-readable metrics.

The suite exercises the existing direction-three contracts and closed-loop
pipeline without pretending that oracle evidence is a real perception system.
Identity, location, person, event, and habit truth stay explicit in every
scenario report so failures can be attributed to one upstream dimension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    BaseRecordMetadata,
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    EntityRef,
    EntityType,
    EvidenceChannel,
    EvidenceRef,
    ExecutionFeedbackRecord,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    ObservationSafetyApproval,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    ValidTimeInterval,
    VerificationObservation,
    build_query_compiler_provenance,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.world_model.grounded_search import (
    DirectionThreePipeline,
    GroundedTaskExecution,
    OracleActionOutcomeModelProvider,
    OracleGroundedTaskExecutor,
    OracleObservationActionProvider,
    OracleVerificationObservationProvider,
)

_NAMESPACE = UUID("e805b8ea-b026-4f8b-a797-02bc3fc9e9a7")
_RECORDED_AT = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
_CALIBRATION_DOMAIN = "s3-1-multi-scenario-oracle-v0.1"


class OracleInitialBelief(StrEnum):
    AMBIGUOUS = "ambiguous"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


class OracleTruthDimension(StrEnum):
    IDENTITY = "identity"
    LOCATION = "location"
    PERSON = "person"
    EVENT = "event"
    HABIT = "habit"


_DIMENSION_CHANNEL = {
    OracleTruthDimension.IDENTITY: EvidenceChannel.VISUAL,
    OracleTruthDimension.LOCATION: EvidenceChannel.GEOMETRY,
    OracleTruthDimension.PERSON: EvidenceChannel.PERSON,
    OracleTruthDimension.EVENT: EvidenceChannel.EVENT,
    OracleTruthDimension.HABIT: EvidenceChannel.HABIT,
}


@dataclass(frozen=True, slots=True)
class OracleScenarioSpec:
    scenario_id: str
    description: str
    semantic_tags: tuple[str, ...]
    initial_belief: OracleInitialBelief
    decisive_dimension: OracleTruthDimension | None = None
    additional_decisive_dimensions: tuple[OracleTruthDimension, ...] = ()
    verification_action: ObservationActionType | None = None
    terminal_action: RobotActionType | None = RobotActionType.GRASP
    terminal_outcome: RobotActionOutcome | None = RobotActionOutcome.SUCCESS
    replan_after_not_found: bool = False
    expected_termination: str = "task_success_feedback_committed"
    true_target_is_unknown: bool = False

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.description.strip():
            raise ValueError("oracle scenario id and description must be non-empty")
        if self.initial_belief == OracleInitialBelief.AMBIGUOUS:
            stopping = self.verification_action is None and self.terminal_action is None
            if self.verification_action is None and not stopping:
                raise ValueError("ambiguous scenarios must verify or explicitly stop")
        decisive_dimensions = (
            () if self.decisive_dimension is None else (self.decisive_dimension,)
        ) + self.additional_decisive_dimensions
        if len(decisive_dimensions) != len(set(decisive_dimensions)):
            raise ValueError("oracle decisive truth dimensions must be unique")
        if self.initial_belief != OracleInitialBelief.RESOLVED and decisive_dimensions:
            raise ValueError("decisive truth dimensions apply to resolved oracle probes")
        if self.true_target_is_unknown and self.initial_belief != OracleInitialBelief.UNKNOWN:
            raise ValueError("unknown truth requires an unknown initial belief")

    def to_manifest_payload(self) -> dict[str, Any]:
        if self.additional_decisive_dimensions:
            raise ValueError("v0.1 manifest cannot serialize combination truth dimensions")
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "semantic_tags": list(self.semantic_tags),
            "initial_belief": self.initial_belief.value,
            "decisive_dimension": (
                None if self.decisive_dimension is None else self.decisive_dimension.value
            ),
            "verification_action": (
                None if self.verification_action is None else self.verification_action.value
            ),
            "terminal_action": (
                None if self.terminal_action is None else self.terminal_action.value
            ),
            "terminal_outcome": (
                None if self.terminal_outcome is None else self.terminal_outcome.value
            ),
            "replan_after_not_found": self.replan_after_not_found,
            "expected_termination": self.expected_termination,
            "true_target_is_unknown": self.true_target_is_unknown,
        }

    @classmethod
    def from_manifest_payload(cls, payload: dict[str, Any]) -> OracleScenarioSpec:
        expected = {
            "scenario_id",
            "description",
            "semantic_tags",
            "initial_belief",
            "decisive_dimension",
            "verification_action",
            "terminal_action",
            "terminal_outcome",
            "replan_after_not_found",
            "expected_termination",
            "true_target_is_unknown",
        }
        if set(payload) != expected:
            raise ValueError("oracle scenario manifest fields must match the frozen v0.1 schema")
        return cls(
            scenario_id=str(payload["scenario_id"]),
            description=str(payload["description"]),
            semantic_tags=tuple(str(value) for value in payload["semantic_tags"]),
            initial_belief=OracleInitialBelief(payload["initial_belief"]),
            decisive_dimension=(
                None
                if payload["decisive_dimension"] is None
                else OracleTruthDimension(payload["decisive_dimension"])
            ),
            verification_action=(
                None
                if payload["verification_action"] is None
                else ObservationActionType(payload["verification_action"])
            ),
            terminal_action=(
                None
                if payload["terminal_action"] is None
                else RobotActionType(payload["terminal_action"])
            ),
            terminal_outcome=(
                None
                if payload["terminal_outcome"] is None
                else RobotActionOutcome(payload["terminal_outcome"])
            ),
            replan_after_not_found=bool(payload["replan_after_not_found"]),
            expected_termination=str(payload["expected_termination"]),
            true_target_is_unknown=bool(payload["true_target_is_unknown"]),
        )


def default_oracle_scenarios() -> tuple[OracleScenarioSpec, ...]:
    """Return the frozen S3-1 scenario matrix.

    The five ``*_truth_probe`` cases independently inject identity, location,
    person, event, and habit truth. The remaining cases cover all active
    verification actions, correct stopping, and every M27 outcome family.
    """

    return (
        OracleScenarioSpec(
            "identity_truth_probe",
            "Two visually similar instances separated by identity truth.",
            ("similar_instances", "identity"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.IDENTITY,
        ),
        OracleScenarioSpec(
            "location_truth_probe",
            "Cross-time candidates separated by current grounded location truth.",
            ("cross_time", "location"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.LOCATION,
        ),
        OracleScenarioSpec(
            "person_truth_probe",
            "Multiple people use similar objects; person truth selects the owner-used instance.",
            ("multi_person", "similar_instances", "person"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.PERSON,
        ),
        OracleScenarioSpec(
            "event_truth_probe",
            "An unobserved move is resolved by the oracle hidden-event chain.",
            ("hidden_event", "object_moved", "event"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.EVENT,
        ),
        OracleScenarioSpec(
            "habit_truth_probe",
            "A non-stationary habit phase selects the current personalized instance.",
            ("habit_regime", "cross_time", "habit"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.HABIT,
        ),
        OracleScenarioSpec(
            "ask_user_disambiguation",
            "A low-interruption user question separates two grounded instances.",
            ("multi_person", "clarification"),
            OracleInitialBelief.AMBIGUOUS,
            verification_action=ObservationActionType.ASK_USER,
        ),
        OracleScenarioSpec(
            "move_viewpoint_disambiguation",
            "A new viewpoint resolves an occluded cross-time location hypothesis.",
            ("occlusion", "cross_time"),
            OracleInitialBelief.AMBIGUOUS,
            verification_action=ObservationActionType.MOVE_VIEWPOINT,
        ),
        OracleScenarioSpec(
            "micro_verify_similar_instances",
            "A local view change distinguishes two visually similar instances.",
            ("similar_instances", "multi_view"),
            OracleInitialBelief.AMBIGUOUS,
            verification_action=ObservationActionType.MICRO_VERIFY,
        ),
        OracleScenarioSpec(
            "open_closed_container",
            "An authorized container-opening action reveals the hidden target.",
            ("closed_container", "occlusion"),
            OracleInitialBelief.AMBIGUOUS,
            verification_action=ObservationActionType.OPEN_CONTAINER,
        ),
        OracleScenarioSpec(
            "safe_touch_disambiguation",
            "Calibrated and authorized touch resolves a residual identity ambiguity.",
            ("similar_instances", "tactile"),
            OracleInitialBelief.AMBIGUOUS,
            verification_action=ObservationActionType.TOUCH,
        ),
        OracleScenarioSpec(
            "stop_without_positive_value",
            "The system stops when no grounded observation action has positive value.",
            ("stop", "abstention"),
            OracleInitialBelief.AMBIGUOUS,
            terminal_action=None,
            terminal_outcome=None,
            expected_termination="no_candidate_observation_action",
        ),
        OracleScenarioSpec(
            "unknown_unmapped_target",
            "The described target is absent or not mapped and the system abstains.",
            ("unknown", "unmapped", "unexplored"),
            OracleInitialBelief.UNKNOWN,
            terminal_action=None,
            terminal_outcome=None,
            expected_termination="abstained_with_unknown_target",
            true_target_is_unknown=True,
        ),
        OracleScenarioSpec(
            "not_found_hidden_move_replan",
            "A calibrated not-found result lowers one location belief and replans.",
            ("not_found", "hidden_event", "object_moved", "recovery"),
            OracleInitialBelief.RESOLVED,
            terminal_action=RobotActionType.SEARCH,
            replan_after_not_found=True,
        ),
        OracleScenarioSpec(
            "grasp_failed_feedback",
            "A grasp failure remains uncertain action evidence rather than identity negation.",
            ("grasp_failed", "failure_feedback"),
            OracleInitialBelief.RESOLVED,
            terminal_outcome=RobotActionOutcome.GRASP_FAILED,
            expected_termination="task_incomplete_feedback_committed",
        ),
        OracleScenarioSpec(
            "object_slipped_feedback",
            "A slipped object records a potential robot-caused location transition.",
            ("object_slipped", "failure_feedback"),
            OracleInitialBelief.RESOLVED,
            terminal_action=RobotActionType.TRANSFER,
            terminal_outcome=RobotActionOutcome.OBJECT_SLIPPED,
            expected_termination="task_incomplete_feedback_committed",
        ),
        OracleScenarioSpec(
            "partial_execution_feedback",
            "Partial execution retains probability mass without claiming task completion.",
            ("partial", "failure_feedback"),
            OracleInitialBelief.RESOLVED,
            terminal_outcome=RobotActionOutcome.PARTIAL,
            expected_termination="task_incomplete_feedback_committed",
        ),
        OracleScenarioSpec(
            "unknown_execution_feedback",
            "An unknown execution result is appended without fabricating success or failure.",
            ("unknown_outcome", "failure_feedback"),
            OracleInitialBelief.RESOLVED,
            terminal_outcome=RobotActionOutcome.UNKNOWN,
            expected_termination="task_incomplete_feedback_committed",
        ),
    )


def combination_oracle_scenarios() -> tuple[OracleScenarioSpec, ...]:
    """Parallel multi-truth probes without changing the frozen v0.1 suite."""

    return (
        OracleScenarioSpec(
            "identity_location_combination_probe",
            "Similar cross-time instances require identity and current location jointly.",
            ("similar_instances", "cross_time", "identity", "location"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.IDENTITY,
            additional_decisive_dimensions=(OracleTruthDimension.LOCATION,),
        ),
        OracleScenarioSpec(
            "person_event_habit_combination_probe",
            "Multiple actors, a hidden move, and a changed habit jointly select the target.",
            ("multi_person", "hidden_event", "object_moved", "habit_regime", "cross_time"),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.PERSON,
            additional_decisive_dimensions=(
                OracleTruthDimension.EVENT,
                OracleTruthDimension.HABIT,
            ),
        ),
        OracleScenarioSpec(
            "all_dimensions_container_time_combination_probe",
            "A closed-container cross-time scene combines all five truth dimensions.",
            (
                "multi_person",
                "similar_instances",
                "hidden_event",
                "closed_container",
                "occlusion",
                "cross_time",
                "habit_regime",
            ),
            OracleInitialBelief.RESOLVED,
            OracleTruthDimension.IDENTITY,
            additional_decisive_dimensions=(
                OracleTruthDimension.LOCATION,
                OracleTruthDimension.PERSON,
                OracleTruthDimension.EVENT,
                OracleTruthDimension.HABIT,
            ),
        ),
    )


def oracle_scenario_manifest_payload(
    scenarios: tuple[OracleScenarioSpec, ...] | None = None,
) -> dict[str, Any]:
    selected = scenarios or default_oracle_scenarios()
    return {
        "schema_name": "cpswm.DirectionThreeOracleScenarioManifest",
        "schema_version": "0.1.0",
        "scenario_count": len(selected),
        "scenarios": [scenario.to_manifest_payload() for scenario in selected],
    }


def load_oracle_scenario_manifest(path: Path) -> tuple[OracleScenarioSpec, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"schema_name", "schema_version", "scenario_count", "scenarios"}:
        raise ValueError("oracle manifest top-level fields do not match v0.1")
    if payload["schema_name"] != "cpswm.DirectionThreeOracleScenarioManifest":
        raise ValueError("oracle manifest schema name is invalid")
    if payload["schema_version"] != "0.1.0":
        raise ValueError("oracle manifest schema version is unsupported")
    scenarios = tuple(
        OracleScenarioSpec.from_manifest_payload(item) for item in payload["scenarios"]
    )
    if payload["scenario_count"] != len(scenarios):
        raise ValueError("oracle manifest scenario_count does not match its scenarios")
    ids = [scenario.scenario_id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("oracle manifest scenario ids must be unique")
    return scenarios


def _uid(scenario_id: str, role: str) -> UUID:
    return uuid5(_NAMESPACE, f"{scenario_id}:{role}")


def _metadata(
    scenario_id: str,
    schema_name: str,
    source_type: SourceType,
    role: str,
    *,
    recorded_time: datetime = _RECORDED_AT,
) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        record_id=_uid(scenario_id, f"record:{role}"),
        schema_name=schema_name,
        schema_version="0.1.0",
        household_id=_uid(scenario_id, "household"),
        session_id=_uid(scenario_id, "session"),
        recorded_time=recorded_time,
        source_type=source_type,
        source_id=f"s3-oracle-suite:{scenario_id}:{role}",
        model_version="s3-oracle-suite@0.1",
        trace_id=_uid(scenario_id, "trace"),
    )


def _channel_evidence(
    scenario: OracleScenarioSpec,
    *,
    candidate_role: str,
) -> dict[EvidenceChannel, ChannelEvidence]:
    evidence: dict[EvidenceChannel, ChannelEvidence] = {}
    decisive_dimensions = set(scenario.additional_decisive_dimensions)
    if scenario.decisive_dimension is not None:
        decisive_dimensions.add(scenario.decisive_dimension)
    decisive_channels = {_DIMENSION_CHANNEL[dimension] for dimension in decisive_dimensions}
    for channel in EvidenceChannel:
        if scenario.initial_belief == OracleInitialBelief.AMBIGUOUS:
            likelihood = 0.70 if candidate_role != "unknown" else 0.10
        elif scenario.initial_belief == OracleInitialBelief.UNKNOWN:
            likelihood = 0.10 if candidate_role != "unknown" else 0.95
        elif channel in decisive_channels:
            likelihood = {"target": 0.97, "distractor": 0.08, "unknown": 0.05}[candidate_role]
        else:
            likelihood = 0.70 if candidate_role != "unknown" else 0.10
        evidence[channel] = ChannelEvidence(
            likelihood_given_candidate=likelihood,
            availability=1.0,
            model_version=f"oracle-{channel.value}@0.1",
            calibration_domain=_CALIBRATION_DOMAIN,
        )
    return evidence


def build_oracle_request(
    scenario: OracleScenarioSpec,
) -> tuple[JointPosteriorRequest, UUID, UUID, UUID]:
    target = _uid(scenario.scenario_id, "target")
    distractor = _uid(scenario.scenario_id, "distractor")
    unknown = _uid(scenario.scenario_id, "unknown")
    target_location = _uid(scenario.scenario_id, "target-location")
    distractor_location = _uid(scenario.scenario_id, "distractor-location")
    if scenario.initial_belief == OracleInitialBelief.UNKNOWN:
        priors = (0.25, 0.20, 0.55)
    elif scenario.replan_after_not_found:
        # The distractor is deliberately ranked first. The true target is the
        # second instance and becomes top-ranked only after calibrated negative evidence.
        priors = (0.15, 0.80, 0.05)
    elif (
        scenario.initial_belief == OracleInitialBelief.RESOLVED
        and scenario.decisive_dimension is None
    ):
        priors = (0.80, 0.15, 0.05)
    else:
        priors = (0.45, 0.45, 0.10)
    query_utterance = f"oracle query for {scenario.scenario_id}"
    query_source_record_id = _uid(scenario.scenario_id, "query-source")
    query = CompiledSemanticQuery(
        query_id=_uid(scenario.scenario_id, "query"),
        utterance=query_utterance,
        category_candidates=("personal_object",),
        attributes=("similar_instance",),
        relations=("used_by", "currently_located_at"),
        person_entity_ids=(_uid(scenario.scenario_id, "person"),),
        time_expression="cross-session",
        activity_candidates=("household_use",),
        soft_constraints=scenario.semantic_tags,
        compiler_model_version="s3-oracle-compiler@0.1",
        input_evidence_refs=(
            EvidenceRef(
                evidence_type="oracle_query_utterance",
                source_record_id=query_source_record_id,
            ),
        ),
        invocation_provenance=build_query_compiler_provenance(
            provider="oracle-fixture",
            model="s3-oracle-compiler",
            version="0.1",
            temperature=0.0,
            prompt_template_version="s3-oracle-query@0.1",
            prompt=query_utterance,
            input_evidence_refs=(query_source_record_id,),
        ),
    )
    candidates = (
        JointCandidateEvidence(
            candidate_id=target,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(entity_id=target, entity_type=EntityType.OBJECT_INSTANCE),
            location_id=target_location,
            prior_probability=priors[0],
            channel_evidence=_channel_evidence(scenario, candidate_role="target"),
        ),
        JointCandidateEvidence(
            candidate_id=distractor,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(
                entity_id=distractor,
                entity_type=EntityType.OBJECT_INSTANCE,
            ),
            location_id=distractor_location,
            prior_probability=priors[1],
            channel_evidence=_channel_evidence(scenario, candidate_role="distractor"),
        ),
        JointCandidateEvidence(
            candidate_id=unknown,
            kind=CandidateKind.UNKNOWN,
            prior_probability=priors[2],
            channel_evidence=_channel_evidence(scenario, candidate_role="unknown"),
        ),
    )
    request = JointPosteriorRequest(
        metadata=_metadata(
            scenario.scenario_id,
            "cpswm.JointPosteriorRequest",
            SourceType.SIMULATION,
            "request",
        ),
        compiled_query=query,
        candidates=candidates,
        resolution_threshold=0.70,
        ambiguity_margin=0.12,
        unknown_threshold=0.45,
        unknown_policy=(
            "abstain" if scenario.initial_belief == OracleInitialBelief.UNKNOWN else "active_verify"
        ),
    )
    true_target = unknown if scenario.true_target_is_unknown else target
    return request, true_target, target, distractor


def _build_verification(
    scenario: OracleScenarioSpec,
    candidate_ids: tuple[UUID, UUID, UUID],
) -> tuple[tuple[ObservationActionCandidate, ...], dict[UUID, VerificationObservation]]:
    if scenario.verification_action is None:
        return (), {}
    target, distractor, unknown = candidate_ids
    action_id = _uid(scenario.scenario_id, "verification-action")
    outcome_likelihoods = {
        "target_signal": {target: 0.95, distractor: 0.05, unknown: 0.20},
        "other_signal": {target: 0.05, distractor: 0.95, unknown: 0.80},
    }
    safety_approval = None
    if scenario.verification_action in {
        ObservationActionType.OPEN_CONTAINER,
        ObservationActionType.TOUCH,
    }:
        safety_approval = ObservationSafetyApproval(
            authorization_granted=True,
            affordance_safe=True,
            assessor_version="s3-oracle-safety@0.1",
            calibration_domain=_CALIBRATION_DOMAIN,
        )
    costs = {
        ObservationActionType.ASK_USER: (0.0, 0.01, 0.03, 0.0, 0.0),
        ObservationActionType.MOVE_VIEWPOINT: (0.08, 0.05, 0.0, 0.0, 0.01),
        ObservationActionType.MICRO_VERIFY: (0.02, 0.02, 0.0, 0.0, 0.0),
        ObservationActionType.OPEN_CONTAINER: (0.03, 0.04, 0.01, 0.02, 0.02),
        ObservationActionType.TOUCH: (0.01, 0.02, 0.01, 0.01, 0.03),
    }
    motion, time, interruption, privacy, safety = costs[scenario.verification_action]
    action = ObservationActionCandidate(
        action_id=action_id,
        action_type=scenario.verification_action,
        label=f"oracle {scenario.verification_action.value} for {scenario.scenario_id}",
        observation_likelihood_model_id=f"oracle-{scenario.verification_action.value}@0.1",
        calibration_domain=_CALIBRATION_DOMAIN,
        outcome_likelihoods=outcome_likelihoods,
        motion_cost=motion,
        time_cost=time,
        interruption_cost=interruption,
        privacy_cost=privacy,
        safety_cost=safety,
        safety_approval=safety_approval,
    )
    channel = {
        ObservationActionType.ASK_USER: EvidenceChannel.PERSON,
        ObservationActionType.MOVE_VIEWPOINT: EvidenceChannel.GEOMETRY,
        ObservationActionType.MICRO_VERIFY: EvidenceChannel.VISUAL,
        ObservationActionType.OPEN_CONTAINER: EvidenceChannel.VISUAL,
        ObservationActionType.TOUCH: EvidenceChannel.VISUAL,
    }[scenario.verification_action]
    observation = VerificationObservation(
        metadata=_metadata(
            scenario.scenario_id,
            "cpswm.VerificationObservation",
            SourceType.SIMULATION,
            "verification-observation",
            recorded_time=_RECORDED_AT + timedelta(seconds=1),
        ),
        action_id=action_id,
        observation_opportunity_id=_uid(scenario.scenario_id, "verification-opportunity"),
        outcome_label="target_signal",
        evidence_channel=channel,
        candidate_likelihoods=outcome_likelihoods["target_signal"],
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=_CALIBRATION_DOMAIN,
    )
    return (action,), {action_id: observation}


def _outcome_distribution(outcome: RobotActionOutcome) -> dict[RobotActionOutcome, float]:
    if outcome in {RobotActionOutcome.SUCCESS, RobotActionOutcome.UNKNOWN}:
        return {outcome: 1.0}
    return {outcome: 0.90, RobotActionOutcome.UNKNOWN: 0.10}


def _execution(
    scenario: OracleScenarioSpec,
    *,
    candidate_id: UUID,
    location_id: UUID,
    action_role: str,
    action_type: RobotActionType,
    outcome: RobotActionOutcome,
    task_success: bool,
) -> GroundedTaskExecution:
    action_id = _uid(scenario.scenario_id, f"execution:{action_role}")
    opportunity_id = _uid(scenario.scenario_id, f"record:opportunity:{action_role}")
    opportunity_time = _RECORDED_AT + timedelta(seconds=2)
    opportunities: tuple[ObservationOpportunityRecord, ...] = ()
    if action_type == RobotActionType.SEARCH:
        opportunities = (
            ObservationOpportunityRecord(
                metadata=_metadata(
                    scenario.scenario_id,
                    "cpswm.ObservationOpportunityRecord",
                    SourceType.SIMULATION,
                    f"opportunity:{action_role}",
                    recorded_time=opportunity_time,
                ),
                observation_action_id=action_id,
                opportunity_time=opportunity_time,
                selected=True,
                selection_probability=1.0,
                p_visible_given_state=0.90,
                p_detect_given_visible=0.90,
                likelihood_model_id="s3-oracle-search-outcome@0.1",
            ),
        )
    feedback_time = _RECORDED_AT + timedelta(seconds=3)
    feedback = ExecutionFeedbackRecord(
        metadata=_metadata(
            scenario.scenario_id,
            "cpswm.ExecutionFeedbackRecord",
            SourceType.ACTION,
            f"feedback:{action_role}",
            recorded_time=feedback_time,
        ),
        action_id=action_id,
        action_type=action_type,
        target_entity=EntityRef(
            entity_id=candidate_id,
            entity_type=EntityType.OBJECT_INSTANCE,
        ),
        attempted_location_id=location_id,
        valid_time=ValidTimeInterval(
            start=_RECORDED_AT,
            end=_RECORDED_AT + timedelta(seconds=10),
        ),
        outcome_distribution=_outcome_distribution(outcome),
        task_goal_satisfied_probability=1.0 if task_success else 0.0,
        observation_opportunity_id=(opportunity_id if opportunities else None),
        diagnostics={"oracle_scenario_id": scenario.scenario_id},
    )
    return GroundedTaskExecution(
        selected_target_candidate_id=candidate_id,
        target_entity=feedback.target_entity,
        target_location_id=location_id,
        executed_action_id=action_id,
        executed_action_type=action_type,
        action_outcome_model_version=(
            "s3-oracle-search-outcome@0.1" if action_type == RobotActionType.SEARCH else None
        ),
        action_outcome_calibration_domain=(
            _CALIBRATION_DOMAIN if action_type == RobotActionType.SEARCH else None
        ),
        observation_opportunities=opportunities,
        feedback_records=(feedback,),
    )


def _build_executions(
    scenario: OracleScenarioSpec,
    request: JointPosteriorRequest,
    target: UUID,
    distractor: UUID,
) -> tuple[dict[UUID, GroundedTaskExecution], dict[RobotActionType, ActionOutcomeLikelihoodModel]]:
    if scenario.terminal_action is None or scenario.terminal_outcome is None:
        return {}, {}
    location_by_id = {
        candidate.candidate_id: candidate.location_id for candidate in request.candidates
    }
    target_location = location_by_id[target]
    distractor_location = location_by_id[distractor]
    if target_location is None or distractor_location is None:
        raise ValueError("oracle execution candidates require grounded locations")
    if scenario.replan_after_not_found:
        first = _execution(
            scenario,
            candidate_id=distractor,
            location_id=distractor_location,
            action_role="first-not-found",
            action_type=RobotActionType.SEARCH,
            outcome=RobotActionOutcome.NOT_FOUND,
            task_success=False,
        )
        second = _execution(
            scenario,
            candidate_id=target,
            location_id=target_location,
            action_role="second-success",
            action_type=RobotActionType.SEARCH,
            outcome=RobotActionOutcome.SUCCESS,
            task_success=True,
        )
        model = ActionOutcomeLikelihoodModel(
            action_type=RobotActionType.SEARCH,
            p_outcome_given_target_present={
                RobotActionOutcome.SUCCESS: 0.94,
                RobotActionOutcome.NOT_FOUND: 0.01,
                RobotActionOutcome.UNKNOWN: 0.05,
            },
            p_outcome_given_target_absent={
                RobotActionOutcome.SUCCESS: 0.01,
                RobotActionOutcome.NOT_FOUND: 0.94,
                RobotActionOutcome.UNKNOWN: 0.05,
            },
            calibration_domain=_CALIBRATION_DOMAIN,
            model_version="s3-oracle-search-outcome@0.1",
        )
        return {distractor: first, target: second}, {RobotActionType.SEARCH: model}
    execution = _execution(
        scenario,
        candidate_id=target,
        location_id=target_location,
        action_role="terminal",
        action_type=scenario.terminal_action,
        outcome=scenario.terminal_outcome,
        task_success=scenario.terminal_outcome == RobotActionOutcome.SUCCESS,
    )
    return {target: execution}, {}


def _truth_payload(
    scenario: OracleScenarioSpec,
    *,
    true_target: UUID,
    target: UUID,
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    decisive_dimensions = set(scenario.additional_decisive_dimensions)
    if scenario.decisive_dimension is not None:
        decisive_dimensions.add(scenario.decisive_dimension)
    for dimension in OracleTruthDimension:
        injected = dimension in decisive_dimensions
        payload[dimension.value] = {
            "true_candidate_id": str(true_target),
            "oracle_value": (
                f"unknown:{dimension.value}"
                if scenario.true_target_is_unknown
                else f"{dimension.value}:{target}"
            ),
            "injected_as_decisive_evidence": injected,
            "evidence_channel": _DIMENSION_CHANNEL[dimension].value,
        }
    return payload


def run_oracle_scenario(scenario: OracleScenarioSpec) -> dict[str, Any]:
    request, true_target, target, distractor = build_oracle_request(scenario)
    unknown = next(
        item.candidate_id for item in request.candidates if item.kind == CandidateKind.UNKNOWN
    )
    actions, observations = _build_verification(
        scenario,
        (target, distractor, unknown),
    )
    executions, outcome_models = _build_executions(scenario, request, target, distractor)
    canonical_log = AppendOnlyTransactionLog()
    trace = DirectionThreePipeline().run_closed_loop(
        request,
        action_provider=OracleObservationActionProvider(actions),
        observation_provider=OracleVerificationObservationProvider(observations),
        task_executor=OracleGroundedTaskExecutor(executions),
        outcome_model_provider=OracleActionOutcomeModelProvider(outcome_models),
        canonical_log=canonical_log,
        max_cycles=8,
    )
    action_by_id = {action.action_id: action for action in actions}
    selected_actions = [
        action_by_id[cycle.observation_plan.selected_action_id]
        for cycle in trace.cycles
        if cycle.observation_plan is not None
        and cycle.observation_plan.selected_action_id is not None
    ]
    outcomes = [
        outcome.value
        for feedback in trace.execution_feedback
        for outcome, probability in feedback.outcome_distribution.items()
        if probability > 0.0
    ]
    task_success = any(
        feedback.task_goal_satisfied_probability >= 0.95 for feedback in trace.execution_feedback
    )
    wrong_object_pickup = bool(
        trace.selected_target_candidate_id is not None
        and trace.selected_target_candidate_id != true_target
        and any(
            feedback.action_type in {RobotActionType.GRASP, RobotActionType.TRANSFER}
            for feedback in trace.execution_feedback
        )
    )
    expected_target = (
        None if scenario.true_target_is_unknown or scenario.terminal_action is None else target
    )
    expected_behavior_met = trace.termination_reason == scenario.expected_termination and (
        expected_target is None or trace.selected_target_candidate_id == expected_target
    )
    return {
        "scenario_id": scenario.scenario_id,
        "description": scenario.description,
        "semantic_tags": list(scenario.semantic_tags),
        "oracle_truth": _truth_payload(
            scenario,
            true_target=true_target,
            target=target,
        ),
        "initial_belief_mode": scenario.initial_belief.value,
        "resolution_sequence": [
            cycle.search_result.resolution_status.value for cycle in trace.cycles
        ],
        "response_policy_sequence": [
            cycle.search_result.response_policy.value for cycle in trace.cycles
        ],
        "selected_observation_actions": [action.action_type.value for action in selected_actions],
        "selected_target_candidate_id": (
            None
            if trace.selected_target_candidate_id is None
            else str(trace.selected_target_candidate_id)
        ),
        "true_target_candidate_id": str(true_target),
        "execution_outcomes": outcomes,
        "termination_reason": trace.termination_reason,
        "task_success": task_success,
        "wrong_object_pickup": wrong_object_pickup,
        "clarification_count": sum(
            action.action_type == ObservationActionType.ASK_USER for action in selected_actions
        ),
        "observation_count": len(trace.verification_observations),
        "motion_cost": sum(action.motion_cost for action in selected_actions),
        "time_cost": sum(action.time_cost for action in selected_actions),
        "interruption_cost": sum(action.interruption_cost for action in selected_actions),
        "privacy_cost": sum(action.privacy_cost for action in selected_actions),
        "safety_cost": sum(action.safety_cost for action in selected_actions),
        "canonical_observation_commits": list(trace.observation_commit_sequences),
        "canonical_feedback_commits": list(trace.feedback_commit_sequences),
        "canonical_log_watermark": canonical_log.latest_watermark().global_commit_seq,
        "expected_behavior_met": expected_behavior_met,
    }


def run_oracle_suite(
    scenarios: tuple[OracleScenarioSpec, ...] | None = None,
) -> dict[str, Any]:
    selected = scenarios or default_oracle_scenarios()
    ids = [scenario.scenario_id for scenario in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("oracle scenario ids must be unique")
    reports = [run_oracle_scenario(scenario) for scenario in selected]
    action_coverage = sorted(
        {action for report in reports for action in report["selected_observation_actions"]}
    )
    outcome_coverage = sorted(
        {outcome for report in reports for outcome in report["execution_outcomes"]}
    )
    dimension_coverage = {
        dimension.value: sum(
            report["oracle_truth"][dimension.value]["injected_as_decisive_evidence"]
            for report in reports
        )
        for dimension in OracleTruthDimension
    }
    if any(
        scenario.terminal_action is None and scenario.verification_action is None
        for scenario in selected
    ):
        action_coverage.append("stop_or_abstain")
    target_tasks = [report for report in reports if "unknown" not in report["semantic_tags"]]
    return {
        "schema_name": "cpswm.DirectionThreeOracleSuiteReport",
        "schema_version": "0.1.0",
        "maturity": "s3-1-multi-scenario-oracle-suite",
        "generated_from": "deterministic_oracle_truth",
        "scenario_count": len(reports),
        "summary": {
            "expected_behavior_met_rate": sum(report["expected_behavior_met"] for report in reports)
            / len(reports),
            "task_success_rate": sum(report["task_success"] for report in target_tasks)
            / len(target_tasks),
            "wrong_object_pickup_rate": sum(
                report["wrong_object_pickup"] for report in target_tasks
            )
            / len(target_tasks),
            "clarification_rate": sum(report["clarification_count"] > 0 for report in reports)
            / len(reports),
            "failure_recovery_success_rate": sum(
                report["task_success"]
                for report in reports
                if "recovery" in report["semantic_tags"]
            )
            / max(
                1,
                sum("recovery" in report["semantic_tags"] for report in reports),
            ),
            "total_motion_cost": sum(report["motion_cost"] for report in reports),
            "total_time_cost": sum(report["time_cost"] for report in reports),
            "total_interruption_cost": sum(report["interruption_cost"] for report in reports),
            "action_coverage": action_coverage,
            "execution_outcome_coverage": outcome_coverage,
            "oracle_dimension_coverage": dimension_coverage,
        },
        "scenarios": reports,
    }
