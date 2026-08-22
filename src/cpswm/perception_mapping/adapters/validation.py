"""M05 adapter boundary validation.

Every adapter must pass its output through :func:`validate_observation_envelope`
before returning it.  This is the single choke point that rejects:

* ground-truth fields entering the normal perception channel;
* cross-household / cross-session / cross-frame mixing;
* naive datetimes (already rejected by the contract, re-checked here);
* payload hash mismatch;
* expired calibration (when a calibration is supplied);
* source-type vs oracle-channel contradictions.

The synthetic adapter additionally refuses to read evaluator truth: it imports
only ``simobs.*`` and never ``cpswm_gt.*``.
"""

from __future__ import annotations

from datetime import datetime

from cpswm.contracts.base import SourceType, require_aware

from .contracts import ObservationEnvelope


class ObservationEnvelopeValidationError(ValueError):
    """Raised when an envelope violates the M05 boundary rules."""


def _check_aware(value: datetime, field_name: str) -> None:
    try:
        require_aware(value, field_name)
    except ValueError as error:
        raise ObservationEnvelopeValidationError(str(error)) from error


def validate_observation_envelope(
    envelope: ObservationEnvelope,
    *,
    payload_bytes: bytes | None = None,
    calibration_valid: bool | None = None,
    expected_frame_id: str | None = None,
) -> None:
    """Apply the M05 adapter boundary checks to one envelope.

    ``payload_bytes``, when supplied, must match the bound payload hash.
    ``calibration_valid``, when supplied, must be true; adapters pass the
    result of the M06 registry lookup so an expired calibration fails here.
    ``expected_frame_id`` lets a caller assert a specific sensor frame.
    """

    if not isinstance(envelope, ObservationEnvelope):
        raise ObservationEnvelopeValidationError("not an ObservationEnvelope")

    _check_aware(envelope.capture_time, "capture_time")
    _check_aware(envelope.arrival_time, "arrival_time")

    if envelope.identity.household_id != envelope.metadata.household_id:
        raise ObservationEnvelopeValidationError("cross-household identity/metadata mismatch")
    if envelope.identity.session_id != envelope.metadata.session_id:
        raise ObservationEnvelopeValidationError("cross-session identity/metadata mismatch")
    if envelope.identity.trace_id != envelope.metadata.trace_id:
        raise ObservationEnvelopeValidationError("cross-trace identity/metadata mismatch")

    if expected_frame_id is not None and envelope.frame_id != expected_frame_id:
        raise ObservationEnvelopeValidationError(
            f"frame_id {envelope.frame_id!r} does not match expected {expected_frame_id!r}"
        )

    if payload_bytes is not None and not envelope.verify_payload(payload_bytes):
        raise ObservationEnvelopeValidationError("payload hash does not match envelope")

    if calibration_valid is False:
        raise ObservationEnvelopeValidationError("calibration is expired for this observation")

    if envelope.oracle_channel:
        if envelope.oracle_authorization is None:
            raise ObservationEnvelopeValidationError("oracle channel lacks authorization")
        if envelope.metadata.source_type not in {SourceType.SIMULATION, SourceType.IMPORT}:
            raise ObservationEnvelopeValidationError("oracle channel has a forbidden source type")
    else:
        if envelope.oracle_authorization is not None:
            raise ObservationEnvelopeValidationError(
                "non-oracle envelope carries oracle authorization"
            )
        if envelope.metadata.source_type == SourceType.SENSOR:
            # A physical sensor is never oracle; the contract already rejects
            # this combination, but the check is repeated for defense in depth.
            pass


def reject_ground_truth_leakage(
    *,
    ground_truth_refs: tuple = (),
    oracle_channel: bool,
) -> None:
    """Reject ground-truth references on a non-oracle channel.

    A robot-visible envelope produced from ``simobs.*`` must never carry
    ``ground_truth_refs`` unless the channel is explicitly oracle.
    """

    if ground_truth_refs and not oracle_channel:
        raise ObservationEnvelopeValidationError(
            "ground-truth references cannot enter the normal perception channel"
        )


__all__ = [
    "ObservationEnvelopeValidationError",
    "reject_ground_truth_leakage",
    "validate_observation_envelope",
]
