"""Primitive contracts shared by M01 schema v0.1."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def require_aware(value: datetime, field_name: str) -> datetime:
    """Reject naive datetimes at contract boundaries."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class ContractModel(BaseModel):
    """Immutable, strict base for every public contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceType(StrEnum):
    SENSOR = "sensor"
    MODEL = "model"
    USER = "user"
    INFERENCE = "inference"
    ACTION = "action"
    IMPORT = "import"
    SIMULATION = "simulation"


class PrivacyScope(StrEnum):
    PRIVATE = "private"
    HOUSEHOLD = "household"
    RESEARCH_DEIDENTIFIED = "research_deidentified"


class EntityType(StrEnum):
    PERSON = "person"
    OBJECT_INSTANCE = "object_instance"
    PLACE = "place"
    CONTAINER = "container"
    ACTIVITY = "activity"
    TASK = "task"
    DEVICE = "device"


class BaseRecordMetadata(ContractModel):
    """Fields that are meaningful on every record.

    Evidence reliability and posterior probability intentionally do not live
    here. They are separate semantic components.
    """

    record_id: UUID = Field(default_factory=uuid4)
    schema_name: str = Field(min_length=1)
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    household_id: UUID
    session_id: UUID
    recorded_time: datetime = Field(default_factory=utc_now)
    source_type: SourceType
    source_id: str = Field(min_length=1)
    model_version: str | None = None
    privacy_scope: PrivacyScope = PrivacyScope.HOUSEHOLD
    trace_id: UUID = Field(default_factory=uuid4)

    @field_validator("recorded_time")
    @classmethod
    def validate_recorded_time(cls, value: datetime) -> datetime:
        return require_aware(value, "recorded_time")


class ValidTimeInterval(ContractModel):
    """Half-open interval [start, end); end=None means still valid."""

    start: datetime
    end: datetime | None = None

    @field_validator("start", "end")
    @classmethod
    def validate_awareness(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return value
        return require_aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_order(self) -> ValidTimeInterval:
        if self.end is not None and self.end <= self.start:
            raise ValueError("valid_time.end must be later than start")
        return self

    def contains(self, instant: datetime) -> bool:
        instant = require_aware(instant, "instant")
        return self.start <= instant and (self.end is None or instant < self.end)

    def overlaps(self, other: ValidTimeInterval) -> bool:
        self_end = self.end or datetime.max.replace(tzinfo=timezone.utc)
        other_end = other.end or datetime.max.replace(tzinfo=timezone.utc)
        return self.start < other_end and other.start < self_end


class TemporalValidityMixin(ContractModel):
    """Temporal semantics composed only into observations and claims."""

    valid_time: ValidTimeInterval
    observed_time: datetime

    @field_validator("observed_time")
    @classmethod
    def validate_observed_time(cls, value: datetime) -> datetime:
        return require_aware(value, "observed_time")


class EntityRef(ContractModel):
    entity_id: UUID
    entity_type: EntityType


class EvidenceRef(ContractModel):
    evidence_id: UUID = Field(default_factory=uuid4)
    evidence_type: str = Field(min_length=1)
    source_record_id: UUID
    locator: str | None = None


class EvidenceScoredMixin(ContractModel):
    """Reliability of one observation or assertion, not a posterior."""

    evidence_reliability: Probability
    evidence_refs: tuple[EvidenceRef, ...] = ()
    supersedes: tuple[UUID, ...] = ()


class ProbabilityInterval(ContractModel):
    lower: Probability
    upper: Probability

    @model_validator(mode="after")
    def validate_bounds(self) -> ProbabilityInterval:
        if self.upper < self.lower:
            raise ValueError("uncertainty upper bound must be >= lower bound")
        return self


class PosteriorMixin(ContractModel):
    """Posterior semantics composed only into normalized hypotheses."""

    posterior_probability: Probability
    uncertainty: ProbabilityInterval | None = None
    normalization_group: str = Field(min_length=1)


class InputWatermark(ContractModel):
    """Central transaction-log watermark for the first implementation."""

    global_commit_seq: NonNegativeInt
    transaction_id: UUID
    source_local_seq: dict[str, NonNegativeInt] = Field(default_factory=dict)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return require_aware(value, "recorded_at")
