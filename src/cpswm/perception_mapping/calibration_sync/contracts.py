"""M06 sensor calibration and multi-modal time-sync contracts.

``SensorCalibration`` binds intrinsics/extrinsics, a calibration version, a
valid-time interval, the source/target frames, uncertainty, and the calibration
artifact hash.  ``SensorTimeSyncResult`` keeps the *original* source time next
to the aligned target time and offset -- it never overwrites the raw timestamp,
so a later re-sync or a corrected offset cannot destroy evidence of what the
sensor originally reported.

M06 is a B1 vertical slice: it provides calibration and time-sync *contracts*
plus a deterministic registry.  It does not estimate real sensor intrinsics or
run clock synchronization against real devices.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, ValidationInfo, field_validator, model_validator

from cpswm.contracts.base import (
    ContractModel,
    PositiveInt,
    ValidTimeInterval,
    require_aware,
)
from cpswm.foundation.identity_time_frames.contracts import FrameTransform
from cpswm.perception_mapping.adapters.contracts import ObservationEnvelope, SensorRef


class IntrinsicsModel(ContractModel):
    """Camera/sensor intrinsics for one calibration."""

    model: str = Field(min_length=1)
    parameters: dict[str, float] = Field(default_factory=dict)
    width: PositiveInt | None = None
    height: PositiveInt | None = None


class CalibrationUncertainty(ContractModel):
    """Uncertainty attached to a calibration.

    Covariance tuples are raw numeric arrays; their layout is documented by the
    producer and is not interpreted here (B1 does not claim covariance
    propagation).
    """

    intrinsics_covariance: tuple[float, ...] | None = None
    extrinsics_covariance: tuple[float, ...] | None = None

    @model_validator(mode="after")
    def validate_uncertainty(self) -> CalibrationUncertainty:
        if self.intrinsics_covariance is None and self.extrinsics_covariance is None:
            raise ValueError("calibration uncertainty requires at least one covariance")
        if self.extrinsics_covariance is not None and len(self.extrinsics_covariance) not in {
            6,
            36,
        }:
            raise ValueError("extrinsics covariance must contain 6 or 36 values")
        return self


class SensorCalibration(ContractModel):
    """One versioned calibration binding sensor frame to a reference frame."""

    calibration_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    sensor: SensorRef
    calibration_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    valid_time: ValidTimeInterval
    frame_id: str = Field(min_length=1)
    intrinsics: IntrinsicsModel | None = None
    extrinsics: FrameTransform | None = None
    uncertainty: CalibrationUncertainty | None = None
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_calibration(self) -> SensorCalibration:
        if self.intrinsics is None and self.extrinsics is None:
            raise ValueError("a calibration requires intrinsics or extrinsics")
        if self.extrinsics is not None:
            if self.extrinsics.household_id != self.household_id:
                raise ValueError("extrinsics household does not match calibration household")
            if self.extrinsics.source_frame_id != self.frame_id:
                raise ValueError("extrinsics source frame must equal the calibration frame_id")
        return self


class SensorTimeSyncResult(ContractModel):
    """One time-sync estimate between two clock domains.

    ``source_time`` is the original timestamp and is always preserved.
    ``target_time`` is the aligned copy.  ``offset_seconds`` and
    ``uncertainty_seconds`` record the applied mapping.
    """

    sync_result_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    sensor_id: str = Field(min_length=1)
    source_clock_domain: str = Field(min_length=1)
    target_clock_domain: str = Field(min_length=1)
    source_time: datetime
    target_time: datetime
    offset_seconds: float
    uncertainty_seconds: float = Field(ge=0.0)
    sync_version: str = Field(min_length=1)
    valid_time: ValidTimeInterval

    @field_validator("source_time", "target_time")
    @classmethod
    def validate_times_aware(cls, value: datetime, info: ValidationInfo) -> datetime:
        return require_aware(value, info.field_name or "timestamp")

    @model_validator(mode="after")
    def validate_sync(self) -> SensorTimeSyncResult:
        if self.source_clock_domain == self.target_clock_domain:
            raise ValueError("time sync requires two different clock domains")
        expected = self.source_time.timestamp() + self.offset_seconds
        if abs(expected - self.target_time.timestamp()) > 1e-6:
            raise ValueError("target_time must equal source_time plus offset_seconds")
        return self


class CalibratedObservation(ContractModel):
    """An M06 output: the original envelope plus an aligned capture time.

    The raw envelope is preserved by reference; ``aligned_capture_time`` is the
    only added field, so the original capture timestamp is never overwritten.
    """

    envelope: ObservationEnvelope
    calibration_id: UUID
    sync_result_id: UUID | None = None
    aligned_capture_time: datetime | None = None

    @field_validator("aligned_capture_time")
    @classmethod
    def validate_aligned_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return require_aware(value, "aligned_capture_time")

    @model_validator(mode="after")
    def validate_calibrated(self) -> CalibratedObservation:
        if self.sync_result_id is not None and self.aligned_capture_time is None:
            raise ValueError("a synced observation requires an aligned capture time")
        return self


class CalibrationState(ContractModel):
    """The currently active calibration and sync result for one sensor."""

    household_id: UUID
    sensor: SensorRef
    active_calibration: SensorCalibration | None = None
    last_sync: SensorTimeSyncResult | None = None


__all__ = [
    "CalibratedObservation",
    "CalibrationState",
    "CalibrationUncertainty",
    "IntrinsicsModel",
    "SensorCalibration",
    "SensorTimeSyncResult",
]
