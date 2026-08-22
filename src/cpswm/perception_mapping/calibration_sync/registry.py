"""M06 calibration registry and time-sync bookkeeping.

The registry is deterministic and household-scoped: a calibration registered
for household A can never be used to validate an observation from household B.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cpswm.contracts.base import require_aware

from .contracts import CalibrationState, SensorCalibration, SensorTimeSyncResult


class CalibrationConflictError(ValueError):
    """Two calibrations overlap for one sensor in one household."""


class CalibrationNotFoundError(LookupError):
    """No calibration is valid for the requested instant."""


class CalibrationRegistry:
    """Household-scoped, versioned calibration store with valid-time lookup."""

    def __init__(self) -> None:
        self._calibrations: list[SensorCalibration] = []
        self._syncs: list[SensorTimeSyncResult] = []

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
