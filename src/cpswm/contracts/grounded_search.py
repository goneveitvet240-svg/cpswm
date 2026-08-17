"""Contracts for direction structure three: grounded ambiguous-object search.

The contracts keep language interpretation, multimodal evidence, derived
posteriors, active verification, and execution feedback semantically separate.
An LLM may compile a query or propose candidates, but it cannot create a
canonical world-state fact through any type in this module.
"""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EntityType,
    EvidenceRef,
    PositiveInt,
    Probability,
    SourceType,
    ValidTimeInterval,
)
from .likelihoods import Pose3D

StrictlyPositiveProbability = Annotated[float, Field(gt=0.0, le=1.0)]


class EvidenceChannel(StrEnum):
    """Required evidence families in the first auditable joint baseline."""

    LANGUAGE = "language"
    VISUAL = "visual"
    GEOMETRY = "geometry"
    EVENT = "event"
    PERSON = "person"
    HABIT = "habit"


JOINT_EVIDENCE_CHANNELS = tuple(EvidenceChannel)


class CandidateKind(StrEnum):
    OBJECT_INSTANCE = "object_instance"
    UNKNOWN = "unknown"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class HardConstraintStatus(StrEnum):
    """Candidate-level truth status for one compiled hard constraint."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class ResponsePolicy(StrEnum):
    RETURN_TOP_K = "return_top_k"
    ACTIVE_VERIFY = "active_verify"
    ASK_USER = "ask_user"
    ABSTAIN = "abstain"


class VerificationModality(StrEnum):
    RGB = "rgb"
    RGBD = "rgbd"
    POINT_CLOUD = "point_cloud"
    TACTILE = "tactile"


class ObservationActionType(StrEnum):
    MOVE_VIEWPOINT = "move_viewpoint"
    MICRO_VERIFY = "micro_verify"
    OPEN_CONTAINER = "open_container"
    TOUCH = "touch"
    ASK_USER = "ask_user"


class ObservationRiskType(StrEnum):
    """Risk families that require an explicit gate before physical inspection."""

    FRAGILE = "fragile"
    HAZARDOUS = "hazardous"
    CONTAMINATION = "contamination"
    MEDICATION = "medication"
    PRIVACY = "privacy"
    UNAUTHORIZED = "unauthorized"


class RobotActionType(StrEnum):
    SEARCH = "search"
    NAVIGATE = "navigate"
    GRASP = "grasp"
    TRANSFER = "transfer"
    PLACE = "place"


class RobotActionOutcome(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    GRASP_FAILED = "grasp_failed"
    OBJECT_SLIPPED = "object_slipped"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class MemoryEvidenceFactor(StrEnum):
    ORIGINAL_OBSERVATION = "original_observation"
    INSTANCE_IDENTITY = "instance_identity"
    LOCALIZATION_ALIGNMENT = "localization_alignment"
    INTERVENING_EVENTS = "intervening_events"
    TRANSITION_SURVIVAL = "transition_survival"
    OBSERVATION_OPPORTUNITY = "observation_opportunity"
    HABIT_REGIME = "habit_regime"
    EXECUTION_FEEDBACK = "execution_feedback"
    USER_CORRECTION = "user_correction"


class MemoryReliabilityStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"
    HISTORICAL = "historical"
    SUPERSEDED = "superseded"


class MemoryLifecycleAction(StrEnum):
    USE_WITH_CURRENT_POSTERIOR = "use_with_current_posterior"
    VERIFY_BEFORE_HIGH_RISK_USE = "verify_before_high_risk_use"
    KEEP_AS_HISTORICAL = "keep_as_historical"
    MARK_CONTRADICTED = "mark_contradicted"
    FOLLOW_SUPERSEDING_RECORD = "follow_superseding_record"


class CompiledSemanticQuery(ContractModel):
    """Validated output of M21 language compilation, never a map write."""

    query_id: UUID = Field(default_factory=uuid4)
    utterance: str = Field(min_length=1)
    category_candidates: tuple[str, ...] = ()
    attributes: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    affordances: tuple[str, ...] = ()
    person_entity_ids: tuple[UUID, ...] = ()
    time_expression: str | None = None
    activity_candidates: tuple[str, ...] = ()
    hard_constraints: tuple[str, ...] = ()
    soft_constraints: tuple[str, ...] = ()
    compiler_model_version: str = Field(min_length=1)


class ChannelEvidence(ContractModel):
    """Calibrated evidence likelihood for one candidate and channel.

    ``availability=0`` makes a channel explicitly missing rather than silently
    treating a missing score as negative evidence.
    """

    likelihood_given_candidate: StrictlyPositiveProbability
    reliability: Probability = 1.0
    availability: Probability = 1.0
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()


class HardConstraintEvaluation(ContractModel):
    """Auditable evaluation of one hard constraint against one candidate."""

    constraint: str = Field(min_length=1)
    status: HardConstraintStatus
    evaluator_model_version: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()


class JointCandidateEvidence(ContractModel):
    candidate_id: UUID = Field(default_factory=uuid4)
    kind: CandidateKind
    entity: EntityRef | None = None
    location_id: UUID | None = None
    prior_probability: StrictlyPositiveProbability
    channel_evidence: dict[EvidenceChannel, ChannelEvidence]
    hard_constraint_evaluations: tuple[HardConstraintEvaluation, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(self) -> JointCandidateEvidence:
        channels = set(self.channel_evidence)
        if channels != set(JOINT_EVIDENCE_CHANNELS):
            missing = sorted(item.value for item in set(JOINT_EVIDENCE_CHANNELS) - channels)
            extra = sorted(str(item) for item in channels - set(JOINT_EVIDENCE_CHANNELS))
            raise ValueError(
                f"all six joint channels must be explicit; missing={missing}, extra={extra}"
            )
        constraints = [item.constraint for item in self.hard_constraint_evaluations]
        if len(constraints) != len(set(constraints)):
            raise ValueError("candidate hard-constraint evaluations must be unique")
        if self.kind == CandidateKind.UNKNOWN:
            if self.entity is not None or self.location_id is not None:
                raise ValueError("unknown candidate cannot carry an entity or location")
            if any(
                item.status != HardConstraintStatus.UNKNOWN
                for item in self.hard_constraint_evaluations
            ):
                raise ValueError("unknown candidate hard constraints must remain unknown")
        else:
            if self.entity is None:
                raise ValueError("object candidate requires an entity")
            if self.entity.entity_type != EntityType.OBJECT_INSTANCE:
                raise ValueError("grounded candidate entity must be an object instance")
        return self


class JointPosteriorRequest(ContractModel):
    metadata: BaseRecordMetadata
    compiled_query: CompiledSemanticQuery
    candidates: tuple[JointCandidateEvidence, ...] = Field(min_length=2)
    channel_weights: dict[EvidenceChannel, float] = Field(
        default_factory=lambda: {channel: 1.0 for channel in JOINT_EVIDENCE_CHANNELS}
    )
    top_k: PositiveInt = 5
    resolution_threshold: Probability = 0.70
    ambiguity_margin: Probability = 0.12
    unknown_threshold: Probability = 0.45
    ambiguity_policy: ResponsePolicy = ResponsePolicy.ACTIVE_VERIFY
    unknown_policy: ResponsePolicy = ResponsePolicy.ACTIVE_VERIFY
    fusion_model_version: str = "log-opinion-pool@0.1"

    @model_validator(mode="after")
    def validate_request(self) -> JointPosteriorRequest:
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique")
        unknown_count = sum(item.kind == CandidateKind.UNKNOWN for item in self.candidates)
        if unknown_count != 1:
            raise ValueError("exactly one explicit unknown candidate is required")
        expected_constraints = set(self.compiled_query.hard_constraints)
        if len(expected_constraints) != len(self.compiled_query.hard_constraints):
            raise ValueError("compiled hard constraints must be unique")
        for candidate in self.candidates:
            actual_constraints = {item.constraint for item in candidate.hard_constraint_evaluations}
            if actual_constraints != expected_constraints:
                raise ValueError("every candidate must explicitly evaluate every hard constraint")
        total = sum(item.prior_probability for item in self.candidates)
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("candidate prior probabilities must sum to 1")
        if set(self.channel_weights) != set(JOINT_EVIDENCE_CHANNELS):
            raise ValueError("channel_weights must explicitly cover all six channels")
        if any(weight < 0.0 for weight in self.channel_weights.values()):
            raise ValueError("channel weights cannot be negative")
        if self.ambiguity_policy not in {
            ResponsePolicy.ACTIVE_VERIFY,
            ResponsePolicy.ASK_USER,
        }:
            raise ValueError("ambiguous queries must verify or ask the user")
        if self.unknown_policy not in {
            ResponsePolicy.ACTIVE_VERIFY,
            ResponsePolicy.ABSTAIN,
        }:
            raise ValueError("unknown queries must verify or abstain")
        return self


class ChannelContribution(ContractModel):
    channel: EvidenceChannel
    weighted_log_likelihood: float
    effective_weight: float = Field(ge=0.0)


class GroundedObjectCandidate(ContractModel):
    rank: PositiveInt
    candidate_id: UUID
    kind: CandidateKind
    entity: EntityRef | None = None
    location_id: UUID | None = None
    posterior_probability: Probability
    contributions: tuple[ChannelContribution, ...]

    @model_validator(mode="after")
    def validate_shape(self) -> GroundedObjectCandidate:
        if self.kind == CandidateKind.UNKNOWN and (
            self.entity is not None or self.location_id is not None
        ):
            raise ValueError("unknown result cannot carry grounded state")
        if self.kind == CandidateKind.OBJECT_INSTANCE and self.entity is None:
            raise ValueError("object result requires an entity")
        return self


class GroundedSearchResult(ContractModel):
    metadata: BaseRecordMetadata
    query_id: UUID
    candidates: tuple[GroundedObjectCandidate, ...] = Field(min_length=1)
    posterior_by_candidate_id: dict[UUID, Probability] = Field(min_length=2)
    hard_constraint_evaluations_by_candidate_id: dict[UUID, tuple[HardConstraintEvaluation, ...]]
    posterior_mass_returned: Probability
    unknown_probability: Probability
    resolution_status: ResolutionStatus
    response_policy: ResponsePolicy
    explanation_codes: tuple[str, ...] = Field(min_length=1)
    fusion_model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> GroundedSearchResult:
        ranks = [item.rank for item in self.candidates]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("result ranks must be contiguous and start at one")
        total = sum(item.posterior_probability for item in self.candidates)
        if not isclose(total, self.posterior_mass_returned, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("posterior_mass_returned must match returned candidates")
        if not isclose(
            sum(self.posterior_by_candidate_id.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("full candidate posterior must sum to one")
        if set(self.hard_constraint_evaluations_by_candidate_id) != set(
            self.posterior_by_candidate_id
        ):
            raise ValueError("hard-constraint results must cover the full candidate posterior")
        for item in self.candidates:
            if not isclose(
                self.posterior_by_candidate_id[item.candidate_id],
                item.posterior_probability,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError("top-k and full posterior probabilities must agree")
        allowed = {
            ResolutionStatus.RESOLVED: {ResponsePolicy.RETURN_TOP_K},
            ResolutionStatus.AMBIGUOUS: {
                ResponsePolicy.ACTIVE_VERIFY,
                ResponsePolicy.ASK_USER,
            },
            ResolutionStatus.UNKNOWN: {
                ResponsePolicy.ACTIVE_VERIFY,
                ResponsePolicy.ABSTAIN,
            },
        }
        if self.response_policy not in allowed[self.resolution_status]:
            raise ValueError("response policy is incompatible with resolution status")
        return self


class IdentityViewEvidence(ContractModel):
    view_id: UUID = Field(default_factory=uuid4)
    evidence_cluster_id: UUID
    modality: VerificationModality
    viewpoint_pose: Pose3D | None = None
    candidate_likelihoods: dict[UUID, StrictlyPositiveProbability] = Field(min_length=2)
    quality: Probability
    evidence_refs: tuple[EvidenceRef, ...] = ()


class IdentityVerificationRequest(ContractModel):
    candidate_ids: tuple[UUID, ...] = Field(min_length=2)
    prior_probabilities: dict[UUID, StrictlyPositiveProbability]
    view_evidence: tuple[IdentityViewEvidence, ...] = Field(min_length=1)
    required_independent_views: PositiveInt = 2
    confirmation_threshold: Probability = 0.85
    ambiguity_margin: Probability = 0.15
    allow_tactile: bool = False
    tactile_safe: bool = False

    @model_validator(mode="after")
    def validate_identity_request(self) -> IdentityVerificationRequest:
        candidate_set = set(self.candidate_ids)
        if len(candidate_set) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if set(self.prior_probabilities) != candidate_set:
            raise ValueError("identity priors must cover every candidate")
        total = sum(self.prior_probabilities.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("identity priors must sum to one")
        for evidence in self.view_evidence:
            if set(evidence.candidate_likelihoods) != candidate_set:
                raise ValueError("each view must score every identity candidate")
        tactile_present = any(
            evidence.modality == VerificationModality.TACTILE for evidence in self.view_evidence
        )
        if tactile_present and not self.allow_tactile:
            raise ValueError("tactile identity evidence requires explicit authorization")
        if tactile_present and not self.tactile_safe:
            raise ValueError("tactile identity evidence requires a positive safety gate")
        return self


class IdentityVerificationResult(ContractModel):
    posterior_probabilities: dict[UUID, Probability]
    confirmed_candidate_id: UUID | None = None
    independent_view_count: PositiveInt
    status: ResolutionStatus
    recommended_modality: VerificationModality | None = None
    explanation_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity_result(self) -> IdentityVerificationResult:
        total = sum(self.posterior_probabilities.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("identity posterior must sum to one")
        if self.status == ResolutionStatus.RESOLVED and self.confirmed_candidate_id is None:
            raise ValueError("resolved identity requires a confirmed candidate")
        if self.status != ResolutionStatus.RESOLVED and self.confirmed_candidate_id is not None:
            raise ValueError("unresolved identity cannot confirm a candidate")
        return self


class StaticGeometryAnchor(ContractModel):
    anchor_id: UUID = Field(default_factory=uuid4)
    parent_anchor_id: UUID | None = None
    semantic_label: str = Field(min_length=1)
    geometry_ref: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)


class DynamicObjectState(ContractModel):
    object_instance: EntityRef
    anchor_id: UUID
    pose: Pose3D
    point_cloud_ref: str | None = None
    visual_feature_ref: str | None = None
    state_probability: Probability
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def validate_object(self) -> DynamicObjectState:
        if self.object_instance.entity_type != EntityType.OBJECT_INSTANCE:
            raise ValueError("dynamic layer only accepts object instances")
        return self


class ObservationSafetyApproval(ContractModel):
    """Auditable authorization and safety gate for contact/container actions."""

    authorization_granted: bool
    affordance_safe: bool
    assessor_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    blocked_risks: tuple[ObservationRiskType, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @property
    def approved(self) -> bool:
        return self.authorization_granted and self.affordance_safe and not self.blocked_risks


class ObservationActionCandidate(ContractModel):
    action_id: UUID = Field(default_factory=uuid4)
    action_type: ObservationActionType
    label: str = Field(min_length=1)
    viewpoint_pose: Pose3D | None = None
    observation_likelihood_model_id: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    outcome_likelihoods: dict[str, dict[UUID, Probability]] = Field(min_length=2)
    motion_cost: float = Field(ge=0.0)
    time_cost: float = Field(ge=0.0)
    interruption_cost: float = Field(ge=0.0)
    privacy_cost: float = Field(ge=0.0)
    safety_cost: float = Field(ge=0.0)
    safety_approval: ObservationSafetyApproval | None = None

    @model_validator(mode="after")
    def validate_likelihoods(self) -> ObservationActionCandidate:
        hypothesis_ids: set[UUID] | None = None
        for outcome, likelihoods in self.outcome_likelihoods.items():
            if not outcome:
                raise ValueError("observation outcome labels cannot be empty")
            current = set(likelihoods)
            if hypothesis_ids is None:
                hypothesis_ids = current
            elif current != hypothesis_ids:
                raise ValueError("all outcomes must score the same hypotheses")
        if not hypothesis_ids:
            raise ValueError("observation action requires hypotheses")
        for hypothesis_id in hypothesis_ids:
            total = sum(
                likelihoods[hypothesis_id] for likelihoods in self.outcome_likelihoods.values()
            )
            if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("outcome likelihoods must sum to one for every hypothesis")
        if self.action_type in {
            ObservationActionType.TOUCH,
            ObservationActionType.OPEN_CONTAINER,
        }:
            if self.safety_approval is None or not self.safety_approval.approved:
                raise ValueError("touch/open-container actions require an approved safety gate")
        return self


class VerificationObservation(ContractModel):
    """One realized verification outcome and its candidate-conditioned likelihoods.

    The likelihood-model ID is shared with the planned action so M24 cannot plan
    with one observation model and M16 interpret the result with another.
    """

    metadata: BaseRecordMetadata
    action_id: UUID
    observation_opportunity_id: UUID
    outcome_label: str = Field(min_length=1)
    evidence_channel: EvidenceChannel
    candidate_likelihoods: dict[UUID, StrictlyPositiveProbability] = Field(min_length=2)
    reliability: Probability = 1.0
    observation_likelihood_model_id: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def validate_source(self) -> VerificationObservation:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.USER,
            SourceType.SIMULATION,
        }:
            raise ValueError("verification observations require an evidence source")
        return self


class ObservationActionScore(ContractModel):
    action_id: UUID
    expected_information_gain: float = Field(ge=0.0)
    expected_posterior_entropy: float = Field(ge=0.0)
    total_cost: float = Field(ge=0.0)
    net_value: float


class ActiveObservationPlan(ContractModel):
    selected_action_id: UUID | None = None
    scores: tuple[ObservationActionScore, ...]
    should_act: bool
    stop_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plan(self) -> ActiveObservationPlan:
        score_ids = {item.action_id for item in self.scores}
        if self.should_act:
            if self.selected_action_id not in score_ids:
                raise ValueError("selected action must be present in scores")
        elif self.selected_action_id is not None:
            raise ValueError("stopped plan cannot select an action")
        return self


class ExecutionFeedbackRecord(ContractModel):
    """Canonical M27 action evidence with an uncertain outcome distribution."""

    metadata: BaseRecordMetadata
    action_id: UUID
    action_type: RobotActionType
    target_entity: EntityRef | None = None
    attempted_location_id: UUID | None = None
    valid_time: ValidTimeInterval
    outcome_distribution: dict[RobotActionOutcome, Probability] = Field(min_length=1)
    task_goal_satisfied_probability: Probability = 0.0
    observation_opportunity_id: UUID | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_feedback(self) -> ExecutionFeedbackRecord:
        if self.metadata.source_type != SourceType.ACTION:
            raise ValueError("execution feedback must use source_type=action")
        total = sum(self.outcome_distribution.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("execution outcome distribution must sum to one")
        if self.task_goal_satisfied_probability > self.outcome_distribution.get(
            RobotActionOutcome.SUCCESS, 0.0
        ):
            raise ValueError("task goal satisfaction cannot exceed action success probability")
        if self.outcome_distribution.get(RobotActionOutcome.NOT_FOUND, 0.0) > 0.0:
            if self.action_type != RobotActionType.SEARCH:
                raise ValueError("not_found is only valid for search feedback")
            if self.observation_opportunity_id is None:
                raise ValueError(
                    "not_found requires an observation opportunity for likelihood-aware use"
                )
            if self.target_entity is None:
                raise ValueError("not_found requires a bound target entity")
            if self.attempted_location_id is None:
                raise ValueError("not_found requires a bound attempted location")
        if self.outcome_distribution.get(RobotActionOutcome.GRASP_FAILED, 0.0) > 0.0:
            if self.action_type != RobotActionType.GRASP:
                raise ValueError("grasp_failed is only valid for grasp feedback")
        if self.outcome_distribution.get(RobotActionOutcome.OBJECT_SLIPPED, 0.0) > 0.0:
            if self.action_type not in {
                RobotActionType.GRASP,
                RobotActionType.TRANSFER,
                RobotActionType.PLACE,
            }:
                raise ValueError("object_slipped requires a manipulation action")
        return self


class ActionOutcomeLikelihoodModel(ContractModel):
    """Calibrated likelihood needed to turn feedback into belief evidence."""

    action_type: RobotActionType
    p_outcome_given_target_present: dict[RobotActionOutcome, Probability]
    p_outcome_given_target_absent: dict[RobotActionOutcome, Probability]
    calibration_domain: str = Field(min_length=1)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_distributions(self) -> ActionOutcomeLikelihoodModel:
        if set(self.p_outcome_given_target_present) != set(self.p_outcome_given_target_absent):
            raise ValueError("present and absent models must cover the same outcomes")
        for distribution in (
            self.p_outcome_given_target_present,
            self.p_outcome_given_target_absent,
        ):
            if not isclose(sum(distribution.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("action outcome likelihoods must sum to one")
        return self


class FeedbackBeliefUpdate(ContractModel):
    """Derived M16 update produced from canonical M27 feedback."""

    feedback_record_id: UUID
    prior_target_present: Probability
    posterior_target_present: Probability
    likelihood_ratio: float | None = Field(default=None, ge=0.0)
    outcome_model_version: str = Field(min_length=1)


class MemoryFactorEvidence(ContractModel):
    """Calibrated evidence likelihood under current vs no-longer-current claims."""

    p_evidence_given_current: StrictlyPositiveProbability
    p_evidence_given_not_current: StrictlyPositiveProbability
    reliability: Probability = 1.0
    independence_weight: Probability = 1.0
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @property
    def likelihood_ratio(self) -> float:
        return self.p_evidence_given_current / self.p_evidence_given_not_current


class MemoryReliabilityRequest(ContractModel):
    metadata: BaseRecordMetadata
    memory_record_id: UUID
    prior_current_probability: StrictlyPositiveProbability
    factor_evidence: dict[MemoryEvidenceFactor, MemoryFactorEvidence] = Field(min_length=1)
    seconds_since_last_direct_observation: float = Field(ge=0.0)
    stale_after_seconds: float = Field(gt=0.0)
    fresh_threshold: Probability = 0.75
    usable_threshold: Probability = 0.45
    contradicted_threshold: Probability = 0.20
    explicit_contradiction: bool = False
    historical_only: bool = False
    superseded_by_record_id: UUID | None = None
    reliability_model_version: str = "likelihood-ratio-memory@0.1"

    @model_validator(mode="after")
    def validate_memory_request(self) -> MemoryReliabilityRequest:
        if self.prior_current_probability >= 1.0:
            raise ValueError("memory prior must retain non-zero not-current mass")
        if self.usable_threshold > self.fresh_threshold:
            raise ValueError("usable threshold cannot exceed fresh threshold")
        if self.contradicted_threshold > self.usable_threshold:
            raise ValueError("contradicted threshold cannot exceed usable threshold")
        if self.superseded_by_record_id == self.memory_record_id:
            raise ValueError("memory cannot supersede itself")
        return self


class MemoryFactorContribution(ContractModel):
    factor: MemoryEvidenceFactor
    log_likelihood_ratio: float
    effective_weight: float = Field(ge=0.0)


class MemoryReliabilityProjection(ContractModel):
    metadata: BaseRecordMetadata
    memory_record_id: UUID
    prior_current_probability: Probability
    posterior_current_probability: Probability
    status: MemoryReliabilityStatus
    lifecycle_action: MemoryLifecycleAction
    contributions: tuple[MemoryFactorContribution, ...]
    age_used_as_direct_reliability_evidence: bool = False
    explanation_codes: tuple[str, ...] = Field(min_length=1)
    reliability_model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def protect_age_semantics(self) -> MemoryReliabilityProjection:
        if self.age_used_as_direct_reliability_evidence:
            raise ValueError("time since last seen cannot be a direct reliability likelihood")
        return self
