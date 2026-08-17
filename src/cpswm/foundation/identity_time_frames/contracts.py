"""Public M02 contracts.

The contracts add services around M01 fields; they do not redefine the M01
record metadata or temporal validity models.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isclose
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, ValidTimeInterval, require_aware


class IdentityNamespace(StrEnum):
    HOUSEHOLD = "household"
    SESSION = "session"
    ENTITY = "entity"
    OBSERVATION = "observation"
    EVENT = "event"
    TRANSACTION = "transaction"
    TRACE = "trace"
    FRAME = "frame"
    RECORD = "record"


class ScopedIdentity(ContractModel):
    """A UUID with an explicit semantic namespace and household owner."""

    namespace: IdentityNamespace
    value: UUID = Field(default_factory=uuid4)
    household_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> ScopedIdentity:
        if self.namespace == IdentityNamespace.HOUSEHOLD:
            if self.household_id is not None:
                raise ValueError("household identities cannot belong to another household")
        elif self.household_id is None:
            raise ValueError(f"{self.namespace.value} identities require household_id")
        return self


class ClockAlignment(ContractModel):
    """Offset mapping where target_time = source_time + offset_seconds."""

    alignment_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    source_clock_id: str = Field(min_length=1)
    target_clock_id: str = Field(min_length=1)
    offset_seconds: float
    uncertainty_seconds: float = Field(ge=0.0)
    valid_time: ValidTimeInterval
    alignment_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_clocks(self) -> ClockAlignment:
        if self.source_clock_id == self.target_clock_id:
            raise ValueError("clock alignment requires two different clocks")
        return self


class TimeAlignmentResult(ContractModel):
    source_clock_id: str
    target_clock_id: str
    source_time: datetime
    target_time: datetime
    total_offset_seconds: float
    uncertainty_seconds: float = Field(ge=0.0)
    alignment_ids: tuple[UUID, ...]

    @field_validator("source_time", "target_time")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return require_aware(value, info.field_name)


class Vector3(ContractModel):
    x: float
    y: float
    z: float


class Quaternion(ContractModel):
    """Normalized quaternion in x, y, z, w order."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @model_validator(mode="after")
    def validate_normalized(self) -> Quaternion:
        norm_sq = self.x**2 + self.y**2 + self.z**2 + self.w**2
        if not isclose(norm_sq, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("frame-transform quaternion must be normalized")
        return self


class FrameTransform(ContractModel):
    """Rigid transform mapping points from source_frame_id to target_frame_id."""

    transform_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    source_frame_id: str = Field(min_length=1)
    target_frame_id: str = Field(min_length=1)
    translation: Vector3
    rotation: Quaternion = Field(default_factory=Quaternion)
    covariance: tuple[float, ...] | None = None
    valid_time: ValidTimeInterval
    transform_version: str = Field(min_length=1)
    component_transform_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_transform(self) -> FrameTransform:
        if self.source_frame_id == self.target_frame_id:
            raise ValueError("stored frame transform requires different frames")
        if self.covariance is not None and len(self.covariance) != 36:
            raise ValueError("frame-transform covariance must contain 36 values")
        return self
