"""M05 synthetic simulator adapter.

This adapter converts the robot-visible :class:`simobs.SyntheticObservation`
into the unified :class:`ObservationEnvelope`.  It reads *only* ``simobs.*``
outputs and never imports ``cpswm_gt``, so evaluator ground truth cannot leak
through it.

The adapter is a B1 vertical slice: it implements the adapter boundary and its
rejection rules, but it does not implement real SLAM, detection, or any real
robot driver.  Real device adapters remain a future replacement.
"""

from __future__ import annotations

from datetime import datetime

from cpswm.contracts.base import require_aware
from cpswm.foundation.persistence_replay.contracts import canonical_json
from cpswm.system.privacy_governance.contracts import OracleAccessDecision
from cpswm.system.privacy_governance.governance import HouseholdGovernance
from simobs import SyntheticObservation

from .contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorRef,
    content_hash_bytes,
)
from .validation import (
    ObservationEnvelopeValidationError,
    reject_forbidden_payload_fields,
    reject_ground_truth_leakage,
    validate_observation_envelope,
)


def _payload_bytes(observation: SyntheticObservation) -> bytes:
    return canonical_json(observation.payload).encode("utf-8")


class SyntheticSimulatorAdapter:
    """Adapt robot-visible ``simobs.*`` observations into M05 envelopes.

    ``governance`` is required whenever an oracle-channel observation is
    adapted: the oracle authorization must be a *verifiable decision receipt*
    whose provenance is checked against the append-only log, never a bare
    ``allowed=True`` object.
    """

    def __init__(self, governance: HouseholdGovernance | None = None) -> None:
        self._governance = governance

    def adapt(
        self,
        observation: SyntheticObservation,
        *,
        sensor: SensorRef,
        frame_id: str,
        clock_domain: str = "simulation",
        capture_time: datetime | None = None,
        arrival_time: datetime | None = None,
        oracle_authorization: OracleAccessDecision | None = None,
    ) -> ObservationEnvelope:
        if not isinstance(observation, SyntheticObservation):
            raise ObservationEnvelopeValidationError("expected a simobs.SyntheticObservation")

        oracle_channel = observation.oracle_channel
        if oracle_authorization is not None:
            oracle_channel = True
        reject_ground_truth_leakage(
            ground_truth_refs=observation.ground_truth_refs,
            oracle_channel=oracle_channel,
        )
        if oracle_channel:
            if oracle_authorization is None:
                raise ObservationEnvelopeValidationError(
                    "an oracle-channel synthetic observation requires an M28 decision receipt"
                )
            if self._governance is None:
                raise ObservationEnvelopeValidationError(
                    "an oracle-channel observation requires a governance verifier"
                )
            if not self._governance.verify_oracle_receipt(oracle_authorization):
                raise ObservationEnvelopeValidationError(
                    "oracle decision receipt failed provenance verification"
                )
        else:
            # Normal payloads must not carry evaluator-only fields anywhere,
            # including nested dict/list structures.
            reject_forbidden_payload_fields(observation.payload)
            if observation.oracle_channel:
                raise ObservationEnvelopeValidationError(
                    "simobs oracle_channel cannot be downgraded to a normal channel"
                )

        capture = capture_time or observation.metadata.recorded_time
        arrival = arrival_time or capture
        require_aware(capture, "capture_time")
        require_aware(arrival, "arrival_time")

        payload = _payload_bytes(observation)
        payload_ref = PayloadRef(
            payload_sha256=content_hash_bytes(payload),
            size_bytes=len(payload),
        )
        envelope = ObservationEnvelope(
            metadata=observation.metadata,
            identity=ObservationIdentity(
                household_id=observation.metadata.household_id,
                session_id=observation.metadata.session_id,
                trace_id=observation.metadata.trace_id,
            ),
            sensor=sensor,
            capture_time=capture,
            arrival_time=arrival,
            clock_domain=clock_domain,
            frame_id=frame_id,
            payload=None if oracle_channel else payload_ref,
            oracle_payload=payload_ref if oracle_channel else None,
            oracle_channel=oracle_channel,
            oracle_authorization=oracle_authorization,
        )
        validate_observation_envelope(envelope, payload_bytes=payload)
        return envelope

    def payload_bytes(self, observation: SyntheticObservation) -> bytes:
        """Return the canonical payload bytes for replay-time verification."""

        return _payload_bytes(observation)


__all__ = ["SyntheticSimulatorAdapter"]
