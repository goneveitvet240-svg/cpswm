"""M06 calibration registry and time-sync bookkeeping.

The registry is deterministic and household-scoped: a calibration registered
for household A can never be used to validate an observation from household B.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from cpswm.contracts.base import ValidTimeInterval, require_aware
from cpswm.foundation.identity_time_frames.contracts import FrameTransform
from cpswm.perception_mapping.adapters.contracts import ObservationEnvelope, SensorRef

from .contracts import (
    CalibratedObservation,
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

    def create_calibration(
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
        external_artifact_ref: str | None = None,
    ) -> SensorCalibration:
        """Build, hash, and register one calibration.

        The provenance hash is either recomputed from the canonical parameters
        (``parameters`` mode) or taken from external artifact bytes
        (``external_artifact`` mode); it is never caller-supplied as a bare
        string.
        """

        if artifact_bytes is not None:
            if external_artifact_ref is None:
                raise ValueError("external artifact bytes require a reference")
            provenance_mode: Literal["parameters", "external_artifact"] = "external_artifact"
            parameters_sha256 = None
            external_artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        else:
            provenance_mode = "parameters"
            parameters_sha256 = calibration_artifact_hash(
                calibration_version=calibration_version,
                frame_id=frame_id,
                intrinsics=intrinsics,
                extrinsics=extrinsics,
            )
            external_artifact_sha256 = None
            external_artifact_ref = None
        calibration = SensorCalibration(
            household_id=household_id,
            sensor=sensor,
            calibration_version=calibration_version,
            valid_time=valid_time,
            frame_id=frame_id,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
            uncertainty=uncertainty,
            provenance_mode=provenance_mode,
            parameters_sha256=parameters_sha256,
            external_artifact_sha256=external_artifact_sha256,
            external_artifact_ref=external_artifact_ref,
        )
        self.register(calibration)
        return calibration

    def apply_calibration(
        self,
        envelope: ObservationEnvelope,
        *,
        target_clock: str | None = None,
        require_sync: bool = False,
        max_sync_uncertainty_seconds: float | None = None,
    ) -> CalibratedObservation:
        """Apply a registered calibration to one observation.

        The capture time is always ``envelope.capture_time`` -- it cannot be
        overridden by a caller (replay overrides need a separate audited API).
        ``require_sync=True`` fails closed when no matching sync exists, and
        ``max_sync_uncertainty_seconds`` rejects an out-of-tolerance sync.
        """

        if max_sync_uncertainty_seconds is not None and not (
            math.isfinite(max_sync_uncertainty_seconds) and max_sync_uncertainty_seconds >= 0.0
        ):
            # NaN compares false against everything, so an unvalidated NaN
            # threshold silently accepts every sync however uncertain.
            raise CalibrationConflictError(
                "max_sync_uncertainty_seconds must be a finite non-negative number"
            )
        at_time = require_aware(envelope.capture_time, "capture_time")
        calibration = self.calibration_at(
            sensor_id=envelope.sensor.sensor_id,
            household_id=envelope.metadata.household_id,
            at_time=at_time,
        )
        if calibration.household_id != envelope.metadata.household_id:
            raise CalibrationConflictError("calibration household does not match observation")
        if calibration.sensor.sensor_id != envelope.sensor.sensor_id:
            raise CalibrationConflictError("calibration sensor does not match observation")
        if calibration.frame_id != envelope.frame_id:
            raise CalibrationConflictError("calibration frame does not match observation")
        if not calibration.valid_time.contains(at_time):
            raise CalibrationConflictError("calibration is not valid at the capture time")

        sync = self._find_sync(calibration, envelope, at_time, target_clock)
        if require_sync and sync is None:
            raise CalibrationConflictError("a matching sync is required but none exists")
        if (
            sync is not None
            and max_sync_uncertainty_seconds is not None
            and sync.uncertainty_seconds > max_sync_uncertainty_seconds
        ):
            raise CalibrationConflictError("sync uncertainty exceeds the tolerated maximum")
        if sync is not None:
            aligned = at_time + timedelta(seconds=sync.offset_seconds)
            return CalibratedObservation(
                envelope=envelope,
                calibration_id=calibration.calibration_id,
                sync_result_id=sync.sync_result_id,
                aligned_capture_time=aligned,
            )
        return CalibratedObservation(
            envelope=envelope,
            calibration_id=calibration.calibration_id,
            sync_result_id=None,
            aligned_capture_time=None,
        )

    def _find_sync(
        self,
        calibration: SensorCalibration,
        envelope: ObservationEnvelope,
        at_time: datetime,
        target_clock: str | None,
    ) -> SensorTimeSyncResult | None:
        matches: list[SensorTimeSyncResult] = []
        for item in self._syncs:
            if item.household_id != calibration.household_id:
                continue
            if item.sensor_id != calibration.sensor.sensor_id:
                continue
            if not item.valid_time.contains(at_time):
                continue
            if item.source_clock_domain != envelope.clock_domain:
                continue
            if target_clock is not None and item.target_clock_domain != target_clock:
                continue
            matches.append(item)
        if not matches:
            return None
        if len(matches) > 1:
            # Two overlapping syncs give two different aligned times for the
            # same observation. Picking the first would make alignment depend
            # on registration order, so the ambiguity is refused instead.
            raise CalibrationConflictError(
                "multiple overlapping syncs match this observation; "
                f"ambiguous alignment between {[str(item.sync_result_id) for item in matches]}"
            )
        return matches[0]

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
