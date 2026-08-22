"""M05 unified observation adapters."""

from .contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    OracleAuthorization,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from .synthetic_adapter import SyntheticSimulatorAdapter
from .validation import (
    ObservationEnvelopeValidationError,
    reject_ground_truth_leakage,
    validate_observation_envelope,
)

#: Adapter entry point shared by real robots, simulators, and offline datasets.
ObservationAdapter = SyntheticSimulatorAdapter

__all__ = [
    "ObservationAdapter",
    "ObservationEnvelope",
    "ObservationEnvelopeValidationError",
    "ObservationIdentity",
    "OracleAuthorization",
    "PayloadRef",
    "SensorModality",
    "SensorRef",
    "SyntheticSimulatorAdapter",
    "reject_ground_truth_leakage",
    "validate_observation_envelope",
]
