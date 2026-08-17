"""M16 derived belief-projection contracts."""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EvidenceRef,
    InputWatermark,
    NonNegativeInt,
    PositiveInt,
    PosteriorMixin,
    ValidTimeInterval,
)


class BeliefVariableType(StrEnum):
    LOCATION = "location"
    IDENTITY = "identity"
    OWNER = "owner"
    STATE = "state"
    RELATION = "relation"


class BeliefHypothesis(ContractModel):
    hypothesis_id: UUID = Field(default_factory=uuid4)
    label: str = Field(min_length=1)
    state: JsonValue
    posterior: PosteriorMixin
    evidence_refs: tuple[EvidenceRef, ...] = ()


class RebuildCostEstimate(ContractModel):
    rebuild_from_checkpoint_id: UUID | None = None
    records_to_replay: NonNegativeInt
    estimated_wall_time_ms: NonNegativeInt
    estimated_peak_memory_bytes: NonNegativeInt
    estimator_version: str = Field(min_length=1)


class BeliefSnapshot(ContractModel):
    """Versioned, rebuildable projection for one normalized belief variable."""

    metadata: BaseRecordMetadata
    projection_version: PositiveInt
    parent_projection_id: UUID | None = None
    input_watermark: InputWatermark
    valid_time: ValidTimeInterval
    belief_key: str = Field(min_length=1)
    variable_type: BeliefVariableType
    hypotheses: tuple[BeliefHypothesis, ...] = Field(min_length=1)
    inference_model_version: str = Field(min_length=1)
    habit_model_version: str | None = None
    observation_likelihood_model_versions: tuple[str, ...] = ()
    rebuild_from_checkpoint_id: UUID | None = None
    rebuild_cost_estimate: RebuildCostEstimate | None = None

    @model_validator(mode="after")
    def validate_distribution(self) -> BeliefSnapshot:
        groups = {item.posterior.normalization_group for item in self.hypotheses}
        if len(groups) != 1:
            raise ValueError("all hypotheses in one snapshot must share a normalization_group")
        total = sum(item.posterior.posterior_probability for item in self.hypotheses)
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("posterior probabilities must sum to 1")
        ids = [item.hypothesis_id for item in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("hypothesis_id values must be unique")
        if (
            self.rebuild_cost_estimate is not None
            and self.rebuild_cost_estimate.rebuild_from_checkpoint_id
            != self.rebuild_from_checkpoint_id
        ):
            raise ValueError("snapshot and cost estimate must use the same checkpoint")
        return self


class ProjectionCheckpoint(ContractModel):
    checkpoint_id: UUID = Field(default_factory=uuid4)
    metadata: BaseRecordMetadata
    input_watermark: InputWatermark
    projection_snapshot_refs: tuple[UUID, ...] = Field(min_length=1)
    inference_model_version: str = Field(min_length=1)
    habit_model_version: str | None = None
    valid: bool = True
    invalidation_reasons: tuple[str, ...] = ()
    contains_evidence_refs: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_invalidation(self) -> ProjectionCheckpoint:
        if not self.valid and not self.invalidation_reasons:
            raise ValueError("invalid checkpoint must state at least one reason")
        if self.valid and self.invalidation_reasons:
            raise ValueError("valid checkpoint cannot contain invalidation reasons")
        return self
