"""Shared evidence contract for structure one and structure two data ingress."""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from uuid import UUID

from pydantic import Field, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EvidenceRef,
    Probability,
    SourceType,
    ValidTimeInterval,
)
from .habit_learning import ObservationOpportunityRecord, ObservationOutcome, OcclusionState


class EvidenceProductionMode(StrEnum):
    DIRECT = "direct"
    INFERRED = "inferred"
    MODEL = "model"


class DetectionFailureReason(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OUT_OF_VIEW = "out_of_view"
    OCCLUDED = "occluded"
    CLOSED_CONTAINER = "closed_container"
    BELOW_DETECTION_THRESHOLD = "below_detection_threshold"
    SENSOR_FAILURE = "sensor_failure"
    UNRESOLVED_IDENTITY = "unresolved_identity"
    UNKNOWN = "unknown"


class OpenSetEvidenceSupport(ContractModel):
    """Candidate support is frozen before evidence is scored."""

    actor_keys: tuple[str, ...] = Field(min_length=1)
    object_instance_ids: tuple[UUID, ...] = ()
    location_keys: tuple[str, ...] = Field(min_length=1)
    mechanism_keys: tuple[str, ...] = Field(min_length=1)
    unknown_object_supported: bool = True

    @model_validator(mode="after")
    def _unknowns_and_uniqueness(self) -> OpenSetEvidenceSupport:
        if "unknown_actor" not in self.actor_keys:
            raise ValueError("open-set actor support must include unknown_actor")
        if "unknown_mechanism" not in self.mechanism_keys:
            raise ValueError("open-set mechanism support must include unknown_mechanism")
        for name, values in (
            ("actor_keys", self.actor_keys),
            ("object_instance_ids", self.object_instance_ids),
            ("location_keys", self.location_keys),
            ("mechanism_keys", self.mechanism_keys),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
        return self


class UnifiedEvidenceContract(ContractModel):
    """Formal evidence ingress shared by structure one and structure two.

    The record separates observation selection, sensing outcome, actor uncertainty,
    temporal validity, production authority, correlation, and open-set support. It
    contains no evaluator truth.
    """

    contract_version: str = "unified-evidence@0.1"
    metadata: BaseRecordMetadata
    valid_time: ValidTimeInterval
    object_instance_id: UUID
    object_posterior: dict[str, Probability] = Field(min_length=1)
    location_posterior: dict[str, Probability] = Field(min_length=1)
    detected_object_key: str | None = None
    detected_location_key: str | None = None
    actor_posterior: dict[str, Probability] = Field(min_length=1)
    observation_opportunity: ObservationOpportunityRecord | None = None
    selected_for_observation: bool
    selection_probability: Probability | None = None
    field_of_view_coverage: Probability | None = None
    occlusion_state: OcclusionState = OcclusionState.UNKNOWN
    container_open: bool | None = None
    detection_outcome: ObservationOutcome | None = None
    detection_failure_reason: DetectionFailureReason = DetectionFailureReason.NOT_APPLICABLE
    production_mode: EvidenceProductionMode
    evidence_cluster_id: UUID
    correlation_group_id: str = Field(min_length=1)
    within_cluster_correlation: Probability = 0.0
    effective_sample_weight: float = Field(gt=0.0, le=1.0)
    open_set_support: OpenSetEvidenceSupport
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _semantics(self) -> UnifiedEvidenceContract:
        if self.contract_version != "unified-evidence@0.1":
            raise ValueError("unsupported unified evidence contract version")
        if not isclose(sum(self.actor_posterior.values()), 1.0, abs_tol=1e-6):
            raise ValueError("actor_posterior must sum to one")
        if set(self.actor_posterior) != set(self.open_set_support.actor_keys):
            raise ValueError("actor posterior and open-set actor support must match")
        expected_objects = {
            *(str(item) for item in self.open_set_support.object_instance_ids),
            "unknown_object",
        }
        if set(self.object_posterior) != expected_objects:
            raise ValueError("object posterior must match open-set object support plus unknown")
        if not isclose(sum(self.object_posterior.values()), 1.0, abs_tol=1e-6):
            raise ValueError("object_posterior must sum to one")
        if set(self.location_posterior) != set(self.open_set_support.location_keys):
            raise ValueError("location posterior and open-set location support must match")
        if "unknown_location" not in self.location_posterior:
            raise ValueError("open-set location support must include unknown_location")
        if not isclose(sum(self.location_posterior.values()), 1.0, abs_tol=1e-6):
            raise ValueError("location_posterior must sum to one")
        if self.observation_opportunity is None:
            if self.selected_for_observation or self.selection_probability is not None:
                raise ValueError("observation selection requires a recorded opportunity")
        else:
            opportunity = self.observation_opportunity
            if opportunity.selected != self.selected_for_observation:
                raise ValueError("selection flag must match the observation opportunity")
            if not isclose(
                opportunity.selection_probability,
                self.selection_probability if self.selection_probability is not None else -1.0,
                abs_tol=1e-12,
            ):
                raise ValueError("selection probability must match the observation opportunity")
            if opportunity.metadata.record_id == self.metadata.record_id:
                raise ValueError("evidence and opportunity require distinct record identities")
            if (
                opportunity.metadata.household_id,
                opportunity.metadata.session_id,
                opportunity.metadata.trace_id,
            ) != (
                self.metadata.household_id,
                self.metadata.session_id,
                self.metadata.trace_id,
            ):
                raise ValueError("opportunity and evidence provenance scope must match")
            if not self.valid_time.contains(opportunity.opportunity_time):
                raise ValueError("opportunity time must lie inside evidence valid time")
        if self.selected_for_observation and (self.selection_probability or 0.0) <= 0.0:
            raise ValueError("a realized selected observation requires positive probability")
        if (
            self.production_mode is EvidenceProductionMode.DIRECT
            and self.detection_outcome is not None
        ):
            if self.observation_opportunity is None or not self.selected_for_observation:
                raise ValueError("direct detection requires a selected observation opportunity")
        if self.detection_outcome is ObservationOutcome.DETECTED:
            if self.detection_failure_reason is not DetectionFailureReason.NOT_APPLICABLE:
                raise ValueError("detected evidence cannot carry a detection failure reason")
            if self.detected_object_key is None or self.detected_location_key is None:
                raise ValueError("detected evidence requires supported object and location keys")
            if self.detected_object_key not in self.object_posterior:
                raise ValueError("detected object must be present in object posterior")
            if self.detected_location_key not in self.location_posterior:
                raise ValueError("detected location must be present in location posterior")
        elif self.detection_outcome is not None:
            if self.detection_failure_reason is DetectionFailureReason.NOT_APPLICABLE:
                raise ValueError("non-detection must carry an explicit failure reason")
            if self.detected_object_key is not None or self.detected_location_key is not None:
                raise ValueError("non-detection cannot carry hard object or location keys")
        elif self.detected_object_key is not None or self.detected_location_key is not None:
            raise ValueError("hard object/location keys require a detected outcome")
        source_modes = {
            EvidenceProductionMode.DIRECT: {
                SourceType.SENSOR,
                SourceType.USER,
                SourceType.SIMULATION,
            },
            EvidenceProductionMode.INFERRED: {SourceType.INFERENCE},
            EvidenceProductionMode.MODEL: {SourceType.MODEL},
        }
        if self.metadata.source_type not in source_modes[self.production_mode]:
            raise ValueError("source type is incompatible with evidence production mode")
        if self.production_mode in {EvidenceProductionMode.INFERRED, EvidenceProductionMode.MODEL}:
            if not self.evidence_refs:
                raise ValueError("inferred/model evidence requires parent evidence references")
        if self.metadata.recorded_time < self.valid_time.start:
            raise ValueError("recorded time cannot precede evidence valid time")
        return self


__all__ = [
    "DetectionFailureReason",
    "EvidenceProductionMode",
    "OpenSetEvidenceSupport",
    "UnifiedEvidenceContract",
]
