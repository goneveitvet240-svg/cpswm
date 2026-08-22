"""M06 calibration registry and time-sync bookkeeping.

The registry is deterministic and household-scoped: a calibration registered
for household A can never be used to validate an observation from household B.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from cpswm.contracts.base import ValidTimeInterval, require_aware
from cpswm.foundation.identity_time_frames.contracts import FrameTransform
from cpswm.perception_mapping.adapters.contracts import SensorRef

from .contracts import (
    CalibrationState,
    CalibrationUncertainty,
    IntrinsicsModel,
    SensorCalibration,
    SensorTimeSyncResult,
    calibration_artifact_hash,
)


class CalibrationConflictError(ValueError):
    """Two calibrations overlap for one sensor in one household."""


class CalibrationNotFoundError(LookupError):
    """No calibration is valid for the requested instant."""


class CalibrationRegistry:
    """Household-scoped, versioned calibration store with valid-time lookup."""

    def __init__(self) -> None:
        self._calibrations: list[SensorCalibration] = []
        self._syncs: list[SensorTimeSyncResult] = []

    def calibrate(
        self,
        *,
        sensor: SensorRef,
        frame_id: str,
        household_id: UUID,
        valid_time: ValidTimeInterval,
        intrinsics: IntrinsicsModel | None = None,
        extrinsics: FrameTransform | None = None,
        uncertainty: CalibrationUncertainty | None = None,
        calibration_version: str = "0.1.0",
        artifact_bytes: bytes | None = None,
        sync: SensorTimeSyncResult | None = None,
    ) -> SensorCalibration:
        """Build, hash, and register one calibration, optionally with a sync.

        The artifact hash is either recomputed from the canonical parameters or
        taken from the external artifact bytes; it is never caller-supplied.
        """

        if artifact_bytes is not None:
            artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        else:
            artifact_sha256 = calibration_artifact_hash(
                calibration_version=calibration_version,
                frame_id=frame_id,
                intrinsics=intrinsics,
                extrinsics=extrinsics,
            )
        calibration = SensorCalibration(
            household_id=household_id,
            sensor=sensor,
            calibration_version=calibration_version,
            valid_time=valid_time,
            frame_id=frame_id,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
            uncertainty=uncertainty,
            artifact_sha256=artifact_sha256,
        )
        self.register(calibration)
        if sync is not None:
            self.record_sync(sync)
        return calibration

    def register(self, calibration: SensorCalibration) -> None:
        for existing in self._calibrations:
            if existing.calibration_id == calibration.calibration_id:
                if existing != calibration:
                    raise CalibrationConflictError("calibration_id is already registered")
                return
            same_sensor = (
                existing.household_id == calibration.household_id
                and existing.sensor.sensor_id == calibration.sensor.sensor_id
            )
            if same_sensor and existing.valid_time.overlaps(calibration.valid_time):
                raise CalibrationConflictError(
                    "overlapping calibrations for one sensor are ambiguous"
                )
        self._calibrations.append(calibration)

    def calibration_at(
        self,
        *,
        sensor_id: str,
        household_id: UUID,
        at_time: datetime,
    ) -> SensorCalibration:
        at_time = require_aware(at_time, "at_time")
        candidates = [
            item
            for item in self._calibrations
            if item.household_id == household_id
            and item.sensor.sensor_id == sensor_id
            and item.valid_time.contains(at_time)
        ]
        if not candidates:
            raise CalibrationNotFoundError(
                f"no calibration for sensor {sensor_id!r} in household {household_id}"
            )
        candidates.sort(key=lambda item: item.valid_time.start)
        return candidates[-1]

    def is_calibration_valid(
        self,
        *,
        sensor_id: str,
        household_id: UUID,
        at_time: datetime,
    ) -> bool:
        try:
            self.calibration_at(sensor_id=sensor_id, household_id=household_id, at_time=at_time)
        except CalibrationNotFoundError:
            return False
        return True

    def record_sync(self, sync: SensorTimeSyncResult) -> None:
        if any(existing.sync_result_id == sync.sync_result_id for existing in self._syncs):
            if sync in self._syncs:
                return
            raise CalibrationConflictError("sync_result_id is already registered")
        self._syncs.append(sync)

    def state(
        self,
        *,
        sensor_id: str,
        household_id: UUID,
        at_time: datetime,
    ) -> CalibrationState:
        calibration = self.calibration_at(
            sensor_id=sensor_id,
            household_id=household_id,
            at_time=at_time,
        )
        last_sync = None
        for item in self._syncs:
            if (
                item.household_id == household_id
                and item.sensor_id == sensor_id
                and item.valid_time.contains(at_time)
            ):
                last_sync = item
        return CalibrationState(
            household_id=household_id,
            sensor=calibration.sensor,
            active_calibration=calibration,
            last_sync=last_sync,
        )


__all__ = [
    "CalibrationConflictError",
    "CalibrationNotFoundError",
    "CalibrationRegistry",
]
