"""Contracts for observation-aware personalized habit learning.

These contracts connect M09/M10 observation semantics to M17 habit updates
without allowing model predictions or missing observations to become evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isclose
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EvidenceRef,
    Probability,
    SourceType,
    require_aware,
)


StrictlyPositiveProbability = Annotated[float, Field(gt=0.0, le=1.0)]


class ObservationMode(StrEnum):
    """How an observation relates to the robot's current primary task."""

    INCIDENTAL = "incidental"
    MICRO_VERIFY = "micro_verify"
    PLANNED_VERIFY = "planned_verify"
    DETOUR_VERIFY = "detour_verify"


class OcclusionState(StrEnum):
    CLEAR = "clear"
    PARTIAL = "partial"
    FULL = "full"
    UNKNOWN = "unknown"


class ObservationOutcome(StrEnum):
    """Mutually exclusive outcome of one candidate observation opportunity."""

    DETECTED = "detected"
    VERIFIED_ABSENCE = "verified_absence"
    NOT_OBSERVED = "not_observed"
    AMBIGUOUS = "ambiguous"


class HabitEvidenceSource(StrEnum):
    """Semantic source of one proposed M17 learning update."""

    DIRECT_OBSERVATION = "direct_observation"
    USER_REPORT = "user_report"
    INFERRED_EVENT = "inferred_event"
    MODEL_PREDICTION = "model_prediction"


class ActorEvidenceTrack(StrEnum):
    """How a robot-visible actor posterior was produced for evaluation."""

    CONTROLLED_NOISE = "controlled_noise"
    ORACLE = "oracle"


class IncidentalObservationContext(ContractModel):
    """Task and sensing context for a non-target observation opportunity."""

    primary_task_id: UUID
    primary_task_goal: str = Field(min_length=1)
    observation_mode: ObservationMode
    frame_id: str = Field(min_length=1)
    # An opportunity is recorded before any detection result exists, so an
    # empty candidate set is valid and avoids filling identity from simulator
    # truth when the view is missed or ambiguous.
    candidate_entity_ids: tuple[UUID, ...] = ()
    field_of_view_coverage: Probability
    occlusion_state: OcclusionState
    additional_action_cost: float = Field(ge=0.0)
    selection_probability: StrictlyPositiveProbability
    observation_likelihood_model_id: str = Field(min_length=1)
    observed_time: datetime

    @field_validator("observed_time")
    @classmethod
    def validate_observed_time(cls, value: datetime) -> datetime:
        return require_aware(value, "observed_time")


class ObservationOpportunityRecord(ContractModel):
    """A sensing opportunity, recorded before any detection result is known.

    It intentionally carries no incidental object identity, realized location,
    event time, or outcome. Those values belong to a separate detection result
    and may only be populated when the sensor actually detects an object.
    """

    metadata: BaseRecordMetadata
    observation_action_id: UUID
    opportunity_time: datetime
    selected: bool
    selection_probability: StrictlyPositiveProbability
    p_visible_given_state: Probability
    p_detect_given_visible: Probability
    likelihood_model_id: str = Field(min_length=1)
    incidental_context: IncidentalObservationContext | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("opportunity_time")
    @classmethod
    def validate_opportunity_time(cls, value: datetime) -> datetime:
        return require_aware(value, "opportunity_time")

    @model_validator(mode="after")
    def validate_source_and_context(self) -> ObservationOpportunityRecord:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        }:
            raise ValueError("observation opportunity requires a sensing source")
        context = self.incidental_context
        if context is not None:
            if context.observed_time != self.opportunity_time:
                raise ValueError("context and opportunity time must match")
            if not isclose(
                context.selection_probability,
                self.selection_probability,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("context and opportunity selection_probability must match")
            if context.observation_likelihood_model_id != self.likelihood_model_id:
                raise ValueError("context and opportunity likelihood model must match")
        if self.metadata.source_type == SourceType.SIMULATION and self.evidence_refs:
            raise ValueError(
                "robot-visible simulation opportunity cannot carry privileged evidence references"
            )
        return self

    @property
    def p_detect_given_state_action(self) -> float:
        """Probability that the target would be detected if at this location."""

        return self.p_visible_given_state * self.p_detect_given_visible


class ObservationDetectionResult(ContractModel):
    """Robot-visible outcome produced by one observation opportunity.

    Identity, realized location, and detection time are all-or-none and are
    permitted only for ``DETECTED``. This makes it structurally impossible for
    a missed or ambiguous observation to be filled from simulator truth.
    """

    metadata: BaseRecordMetadata
    observation_opportunity_id: UUID
    outcome: ObservationOutcome
    detected_object_instance_id: UUID | None = None
    detected_location_id: UUID | None = None
    detection_time: datetime | None = None
    negative_evidence_strength: Probability = 0.0
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("detection_time")
    @classmethod
    def validate_detection_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware(value, "detection_time")

    @model_validator(mode="after")
    def validate_source_and_outcome(self) -> ObservationDetectionResult:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        }:
            raise ValueError("detection result requires a sensing source")
        realized = (
            self.detected_object_instance_id,
            self.detected_location_id,
            self.detection_time,
        )
        if self.outcome == ObservationOutcome.DETECTED:
            if any(value is None for value in realized):
                raise ValueError(
                    "detected result requires object identity, location, and time"
                )
        elif any(value is not None for value in realized):
            raise ValueError(
                "non-detected result cannot carry object identity, location, or time"
            )
        if self.outcome == ObservationOutcome.VERIFIED_ABSENCE:
            if self.negative_evidence_strength <= 0.0:
                raise ValueError("verified absence requires positive evidence strength")
        elif self.negative_evidence_strength != 0.0:
            raise ValueError(
                "only verified absence can carry negative evidence strength"
            )
        if self.metadata.source_type == SourceType.SIMULATION and self.evidence_refs:
            raise ValueError(
                "robot-visible simulation result cannot carry privileged evidence references"
            )
        return self

    @property
    def supports_negative_evidence(self) -> bool:
        return self.outcome == ObservationOutcome.VERIFIED_ABSENCE


class ActorResponsibilityEvidence(ContractModel):
    """Robot-visible posterior over who caused one detected object transition.

    The contract never exposes a ``true_actor`` field.  An oracle evaluation
    track is explicit in ``evidence_track``; controlled-noise evidence must keep
    non-zero uncertainty and therefore cannot silently masquerade as oracle.
    """

    metadata: BaseRecordMetadata
    source_detection_result_id: UUID
    object_instance_id: UUID
    evidence_time: datetime
    actor_posterior: dict[str, Probability] = Field(min_length=1)
    reference_actor_prior: dict[str, StrictlyPositiveProbability] = Field(min_length=1)
    evidence_cluster_id: UUID
    effective_sample_weight: StrictlyPositiveProbability = 1.0
    evidence_track: ActorEvidenceTrack
    evidence_model_id: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("evidence_time")
    @classmethod
    def validate_evidence_time(cls, value: datetime) -> datetime:
        return require_aware(value, "evidence_time")

    @model_validator(mode="after")
    def validate_evidence(self) -> ActorResponsibilityEvidence:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        }:
            raise ValueError("actor responsibility requires a sensing/model source")
        if self.metadata.recorded_time != self.evidence_time:
            raise ValueError("actor evidence metadata time must equal evidence_time")
        if not isclose(
            sum(self.actor_posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("actor_posterior probabilities must sum to 1")
        if any(not actor.strip() for actor in self.actor_posterior):
            raise ValueError("actor_posterior keys must be non-empty")
        if set(self.reference_actor_prior) != set(self.actor_posterior):
            raise ValueError(
                "reference_actor_prior and actor_posterior require identical support"
            )
        if not isclose(
            sum(self.reference_actor_prior.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("reference_actor_prior probabilities must sum to 1")
        if (
            self.evidence_track == ActorEvidenceTrack.CONTROLLED_NOISE
            and max(self.actor_posterior.values()) >= 1.0
        ):
            raise ValueError("controlled-noise actor evidence must retain uncertainty")
        if self.metadata.source_type == SourceType.SIMULATION and self.evidence_refs:
            raise ValueError(
                "robot-visible simulation actor evidence cannot carry privileged references"
            )
        return self

    @property
    def actor_likelihood_ratios(self) -> dict[str, float]:
        """Recover likelihood ratios so an upstream prior is not counted twice."""

        return {
            actor: posterior / self.reference_actor_prior[actor]
            for actor, posterior in self.actor_posterior.items()
        }


class HabitLearningEvidence(ContractModel):
    """Evidence proposed for a person-conditioned M17 habit update.

    Actor keys are stable person UUID strings or ``unknown_actor``. A model
    prediction may be retained for audit, but its effective training weight is
    always zero so a prediction cannot train itself.
    """

    metadata: BaseRecordMetadata
    object_instance_id: UUID
    location_id: UUID
    event_time: datetime
    context_key: str = Field(min_length=1)
    actor_posterior: dict[str, Probability] = Field(min_length=1)
    evidence_source: HabitEvidenceSource
    proposed_training_weight: Probability = 1.0
    source_record_ids: tuple[UUID, ...] = Field(min_length=1)
    observation_opportunity_id: UUID | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def validate_semantics(self) -> HabitLearningEvidence:
        total = sum(self.actor_posterior.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("actor_posterior probabilities must sum to 1")
        if any(not actor.strip() for actor in self.actor_posterior):
            raise ValueError("actor_posterior keys must be non-empty")

        allowed_sources = {
            HabitEvidenceSource.DIRECT_OBSERVATION: {
                SourceType.SENSOR,
                SourceType.MODEL,
                SourceType.SIMULATION,
            },
            HabitEvidenceSource.USER_REPORT: {SourceType.USER, SourceType.IMPORT},
            HabitEvidenceSource.INFERRED_EVENT: {SourceType.INFERENCE},
            HabitEvidenceSource.MODEL_PREDICTION: {SourceType.MODEL},
        }
        if self.metadata.source_type not in allowed_sources[self.evidence_source]:
            raise ValueError(
                f"source_type={self.metadata.source_type.value} is incompatible with "
                f"evidence_source={self.evidence_source.value}"
            )
        return self

    @property
    def effective_training_weight(self) -> float:
        if self.evidence_source == HabitEvidenceSource.MODEL_PREDICTION:
            return 0.0
        return self.proposed_training_weight
