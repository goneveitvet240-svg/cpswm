"""Robot-visible evidence contracts for hidden-event mechanism and actor roles."""

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
ROLE_PAIR_SEPARATOR = "=>"


class HiddenEventEvidenceTrack(StrEnum):
    """How mechanism/role evidence was obtained for an evaluation track."""

    CONTROLLED_NOISE = "controlled_noise"
    ORACLE = "oracle"


class EventMechanism(StrEnum):
    DIRECT_RELOCATION = "direct_relocation"
    HANDOFF_RELOCATION = "handoff_relocation"


def ordered_role_key(initiator_actor_key: str, recipient_actor_key: str) -> str:
    """Return a stable JSON-safe key for one ordered handoff role pair."""

    if not initiator_actor_key.strip() or not recipient_actor_key.strip():
        raise ValueError("ordered role actors must be non-empty")
    if ROLE_PAIR_SEPARATOR in initiator_actor_key or ROLE_PAIR_SEPARATOR in recipient_actor_key:
        raise ValueError("actor keys cannot contain the ordered-role separator")
    if initiator_actor_key == recipient_actor_key:
        raise ValueError("handoff initiator and recipient must differ")
    return f"{initiator_actor_key}{ROLE_PAIR_SEPARATOR}{recipient_actor_key}"


def parse_ordered_role_key(value: str) -> tuple[str, str]:
    """Parse and validate a key created by :func:`ordered_role_key`."""

    parts = value.split(ROLE_PAIR_SEPARATOR)
    if len(parts) != 2:
        raise ValueError("ordered role key must contain exactly one separator")
    initiator, recipient = parts
    ordered_role_key(initiator, recipient)
    return initiator, recipient


class EventMechanismEvidence(ContractModel):
    """Posterior evidence distinguishing direct relocation from handoff."""

    metadata: BaseRecordMetadata
    source_detection_result_id: UUID
    object_instance_id: UUID
    evidence_time: datetime
    mechanism_posterior: dict[EventMechanism, Probability]
    reference_mechanism_prior: dict[EventMechanism, StrictlyPositiveProbability]
    evidence_cluster_id: UUID
    effective_sample_weight: StrictlyPositiveProbability = 1.0
    evidence_track: HiddenEventEvidenceTrack
    evidence_model_id: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("evidence_time")
    @classmethod
    def validate_evidence_time(cls, value: datetime) -> datetime:
        return require_aware(value, "evidence_time")

    @model_validator(mode="after")
    def validate_evidence(self) -> EventMechanismEvidence:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        }:
            raise ValueError("event mechanism evidence requires a sensing/model source")
        if self.metadata.recorded_time != self.evidence_time:
            raise ValueError("event mechanism metadata time must equal evidence_time")
        expected = set(EventMechanism)
        if set(self.mechanism_posterior) != expected:
            raise ValueError("mechanism_posterior must cover direct and handoff")
        if set(self.reference_mechanism_prior) != expected:
            raise ValueError("reference_mechanism_prior must cover direct and handoff")
        if not isclose(sum(self.mechanism_posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("mechanism_posterior probabilities must sum to one")
        if not isclose(
            sum(self.reference_mechanism_prior.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("reference_mechanism_prior probabilities must sum to one")
        if (
            self.evidence_track == HiddenEventEvidenceTrack.CONTROLLED_NOISE
            and max(self.mechanism_posterior.values()) >= 1.0
        ):
            raise ValueError("controlled-noise mechanism evidence must retain uncertainty")
        if self.metadata.source_type == SourceType.SIMULATION and self.evidence_refs:
            raise ValueError("simulation mechanism evidence cannot cite privileged references")
        return self

    @property
    def mechanism_likelihood_ratios(self) -> dict[EventMechanism, float]:
        return {
            mechanism: posterior / self.reference_mechanism_prior[mechanism]
            for mechanism, posterior in self.mechanism_posterior.items()
        }


class RoleBindingEvidence(ContractModel):
    """Posterior over ordered initiator-to-recipient handoff role bindings."""

    metadata: BaseRecordMetadata
    source_detection_result_id: UUID
    object_instance_id: UUID
    evidence_time: datetime
    ordered_role_posterior: dict[str, Probability] = Field(min_length=2)
    reference_ordered_role_prior: dict[str, StrictlyPositiveProbability] = Field(min_length=2)
    evidence_cluster_id: UUID
    effective_sample_weight: StrictlyPositiveProbability = 1.0
    evidence_track: HiddenEventEvidenceTrack
    evidence_model_id: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("evidence_time")
    @classmethod
    def validate_evidence_time(cls, value: datetime) -> datetime:
        return require_aware(value, "evidence_time")

    @model_validator(mode="after")
    def validate_evidence(self) -> RoleBindingEvidence:
        if self.metadata.source_type not in {
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        }:
            raise ValueError("role-binding evidence requires a sensing/model source")
        if self.metadata.recorded_time != self.evidence_time:
            raise ValueError("role-binding metadata time must equal evidence_time")
        if set(self.reference_ordered_role_prior) != set(self.ordered_role_posterior):
            raise ValueError("role posterior and reference prior require identical support")
        for key in self.ordered_role_posterior:
            parse_ordered_role_key(key)
        if not isclose(
            sum(self.ordered_role_posterior.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("ordered_role_posterior probabilities must sum to one")
        if not isclose(
            sum(self.reference_ordered_role_prior.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("reference_ordered_role_prior probabilities must sum to one")
        if (
            self.evidence_track == HiddenEventEvidenceTrack.CONTROLLED_NOISE
            and max(self.ordered_role_posterior.values()) >= 1.0
        ):
            raise ValueError("controlled-noise role evidence must retain uncertainty")
        if self.metadata.source_type == SourceType.SIMULATION and self.evidence_refs:
            raise ValueError("simulation role evidence cannot cite privileged references")
        return self

    @property
    def ordered_role_likelihood_ratios(self) -> dict[str, float]:
        return {
            role: posterior / self.reference_ordered_role_prior[role]
            for role, posterior in self.ordered_role_posterior.items()
        }
