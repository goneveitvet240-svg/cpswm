"""Budgeted M20 world-model query contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EvidenceRef,
    InputWatermark,
    NonNegativeInt,
    PositiveInt,
    Probability,
    ValidTimeInterval,
)


class QueryConsistencyMode(StrEnum):
    LATEST_COMPLETE_PROJECTION = "latest_complete_projection"
    AT_INPUT_WATERMARK = "at_input_watermark"
    HISTORICAL_VALID_TIME = "historical_valid_time"


class RetrievalBudget(ContractModel):
    max_events: PositiveInt | None = None
    max_relations: PositiveInt | None = None
    max_vector_candidates: PositiveInt | None = None
    max_wall_time_ms: PositiveInt | None = None
    max_memory_bytes: PositiveInt | None = None

    @model_validator(mode="after")
    def require_a_limit(self) -> RetrievalBudget:
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("retrieval_budget must set at least one finite limit")
        return self


class RetrievalCoverage(ContractModel):
    events_scanned: NonNegativeInt = 0
    events_available: NonNegativeInt | None = None
    relations_scanned: NonNegativeInt = 0
    relations_available: NonNegativeInt | None = None
    vector_candidates_scanned: NonNegativeInt = 0
    vector_candidates_available: NonNegativeInt | None = None
    wall_time_ms: NonNegativeInt = 0
    peak_memory_bytes: NonNegativeInt = 0
    budget_exhausted: bool = False
    exhaustion_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_coverage(self) -> RetrievalCoverage:
        pairs = (
            (self.events_scanned, self.events_available, "events"),
            (self.relations_scanned, self.relations_available, "relations"),
            (
                self.vector_candidates_scanned,
                self.vector_candidates_available,
                "vector_candidates",
            ),
        )
        for scanned, available, name in pairs:
            if available is not None and scanned > available:
                raise ValueError(f"{name}_scanned cannot exceed {name}_available")
        if self.budget_exhausted and not self.exhaustion_reasons:
            raise ValueError("budget exhaustion must include at least one reason")
        if not self.budget_exhausted and self.exhaustion_reasons:
            raise ValueError("non-exhausted query cannot include exhaustion reasons")
        return self


class QueryConstraint(ContractModel):
    field: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: JsonValue


class WorldModelQuery(ContractModel):
    metadata: BaseRecordMetadata
    constraints: tuple[QueryConstraint, ...] = Field(min_length=1)
    consistency_mode: QueryConsistencyMode
    retrieval_budget: RetrievalBudget
    at_input_watermark: InputWatermark | None = None
    historical_valid_time: ValidTimeInterval | None = None

    @model_validator(mode="after")
    def validate_consistency_target(self) -> WorldModelQuery:
        if (
            self.consistency_mode == QueryConsistencyMode.AT_INPUT_WATERMARK
            and self.at_input_watermark is None
        ):
            raise ValueError("at_input_watermark mode requires an input watermark")
        if (
            self.consistency_mode == QueryConsistencyMode.HISTORICAL_VALID_TIME
            and self.historical_valid_time is None
        ):
            raise ValueError("historical_valid_time mode requires a valid-time interval")
        return self


class QueryCandidate(ContractModel):
    rank: PositiveInt
    entity: EntityRef
    posterior_probability: Probability
    evidence_refs: tuple[EvidenceRef, ...] = ()


class ProjectionLag(ContractModel):
    projection_commit_seq: NonNegativeInt
    latest_normative_commit_seq: NonNegativeInt

    @model_validator(mode="after")
    def validate_order(self) -> ProjectionLag:
        if self.projection_commit_seq > self.latest_normative_commit_seq:
            raise ValueError("projection cannot be ahead of normative inputs")
        return self


class WorldModelQueryResult(ContractModel):
    metadata: BaseRecordMetadata
    query_id: UUID
    projection_id: UUID
    candidates: tuple[QueryCandidate, ...]
    retrieval_coverage: RetrievalCoverage
    projection_lag: ProjectionLag | None = None

    @model_validator(mode="after")
    def validate_ranking(self) -> WorldModelQueryResult:
        ranks = [candidate.rank for candidate in self.candidates]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("candidate ranks must be contiguous and start at 1")
        return self
