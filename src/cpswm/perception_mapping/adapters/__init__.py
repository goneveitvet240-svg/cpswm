"""M05 unified observation adapters."""

from cpswm.system.privacy_governance.contracts import OracleAccessDecision

from .contracts import (
    ObservationEnvelope,
    ObservationIdentity,
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
    "OracleAccessDecision",
    "PayloadRef",
    "SensorModality",
    "SensorRef",
    "SyntheticSimulatorAdapter",
    "reject_ground_truth_leakage",
    "validate_observation_envelope",
]
