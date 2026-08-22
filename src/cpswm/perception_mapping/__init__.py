"""B-layer embodied observation, perception, and spatial mapping.

M05-M12 live here.  The B1 slice currently implements only:

* ``adapters``        -- M05 unified ``ObservationEnvelope`` entry;
* ``calibration_sync`` -- M06 sensor calibration and multi-modal time sync.

M07-M12 remain ``contract_only`` and are intentionally absent from this
package.  This package never imports ``cpswm_gt``; the synthetic adapter only
reads robot-visible ``simobs.*`` outputs.
"""

from .adapters import (
    ObservationAdapter,
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
    SyntheticSimulatorAdapter,
    validate_observation_envelope,
)
from .calibration_sync import (
    CalibrationRegistry,
    CalibrationState,
    CalibratedObservation,
    IntrinsicsModel,
    SensorCalibration,
    SensorTimeSyncResult,
)

__all__ = [
    "CalibratedObservation",
    "CalibrationRegistry",
    "CalibrationState",
    "IntrinsicsModel",
    "ObservationAdapter",
    "ObservationEnvelope",
    "ObservationIdentity",
    "PayloadRef",
    "SensorCalibration",
    "SensorModality",
    "SensorRef",
    "SensorTimeSyncResult",
    "SyntheticSimulatorAdapter",
    "validate_observation_envelope",
]
