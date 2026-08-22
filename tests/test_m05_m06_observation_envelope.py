"""M05/M06 observation envelope, calibration, and time-sync contract tests.

Covers the unified observation entry, the adapter rejection rules, the
synthetic simulator adapter, serialization/replay, and adversarial negatives.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import SourceType
from cpswm.foundation.identity_time_frames import FrameTransform, Quaternion, Vector3
from cpswm.perception_mapping.adapters import (
    ObservationEnvelope,
    ObservationEnvelopeValidationError,
    ObservationIdentity,
    OracleAuthorization,
    PayloadRef,
    SensorModality,
    SensorRef,
    SyntheticSimulatorAdapter,
    validate_observation_envelope,
)
from cpswm.perception_mapping.calibration_sync import (
    CalibrationNotFoundError,
    CalibrationRegistry,
    IntrinsicsModel,
    SensorCalibration,
    SensorTimeSyncResult,
)
from simobs import SyntheticObservation


def _envelope(**overrides):
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    base = dict(
        metadata=dict(
            schema_name="cpswm.observation.Envelope",
            schema_version="0.1.0",
            household_id=household,
            session_id=session,
            recorded_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            source_type=SourceType.SIMULATION.value,
            source_id="sim-sensor-1",
            trace_id=trace,
        ),
        identity=dict(
            household_id=household,
            session_id=session,
            trace_id=trace,
        ),
        sensor=dict(sensor_id="cam-1", modality=SensorModality.RGB.value),
        capture_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        arrival_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        clock_domain="simulation",
        frame_id="cam_1_optical",
        payload=dict(
            payload_sha256="0" * 64,
            size_bytes=0,
        ),
        oracle_channel=False,
    )
    base.update(overrides)
    return ObservationEnvelope.model_validate(base)


def _observation(*, oracle_channel: bool = False, ground_truth_refs: tuple[UUID, ...] = ()):
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    return SyntheticObservation(
        metadata=dict(
            schema_name="simobs.SyntheticObservation",
            schema_version="0.1.0",
            household_id=household,
            session_id=session,
            recorded_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            source_type=SourceType.SIMULATION.value,
            source_id="sim-source",
            trace_id=trace,
        ),
        observation_type="rgb",
        payload={"frame": 17},
        noise_profile_id="controlled_noise_v1",
        oracle_channel=oracle_channel,
        ground_truth_refs=ground_truth_refs,
    )


# ------------------------------------------------------------------ envelope


def test_envelope_rejects_cross_household_identity():
    household = uuid4()
    other = uuid4()
    session = uuid4()
    trace = uuid4()
    with pytest.raises(ValidationError):
        ObservationEnvelope(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=ObservationIdentity(
                household_id=other,
                session_id=session,
                trace_id=trace,
            ),
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            capture_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            arrival_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            clock_domain="simulation",
            frame_id="cam_1",
            payload=PayloadRef(payload_sha256="0" * 64, size_bytes=0),
        )


def test_envelope_rejects_naive_capture_time():
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    with pytest.raises(ValidationError):
        ObservationEnvelope(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=ObservationIdentity(
                household_id=household,
                session_id=session,
                trace_id=trace,
            ),
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            capture_time=datetime(2026, 8, 10, 8, 0),
            arrival_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            clock_domain="simulation",
            frame_id="cam_1",
            payload=PayloadRef(payload_sha256="0" * 64, size_bytes=0),
        )


def test_envelope_rejects_oracle_channel_without_authorization():
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    with pytest.raises(ValidationError):
        ObservationEnvelope(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=ObservationIdentity(
                household_id=household,
                session_id=session,
                trace_id=trace,
            ),
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            capture_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            arrival_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            clock_domain="simulation",
            frame_id="cam_1",
            payload=PayloadRef(payload_sha256="0" * 64, size_bytes=0),
            oracle_channel=True,
        )


def test_envelope_rejects_sensor_source_with_oracle_channel():
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    with pytest.raises(ValidationError):
        ObservationEnvelope(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                source_type=SourceType.SENSOR.value,
                source_id="s",
            ),
            identity=ObservationIdentity(
                household_id=household,
                session_id=session,
                trace_id=trace,
            ),
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            capture_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            arrival_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            clock_domain="sensor",
            frame_id="cam_1",
            payload=PayloadRef(payload_sha256="0" * 64, size_bytes=0),
            oracle_channel=True,
            oracle_authorization=OracleAuthorization(
                authorization_id=uuid4(),
                declared_purpose="evaluation",
                issued_by="evaluator",
            ),
        )


def test_envelope_payload_hash_verification():
    envelope = _envelope(
        payload=dict(
            payload_sha256=("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
            size_bytes=5,
        ),
    )
    assert envelope.verify_payload(b"hello")
    assert not envelope.verify_payload(b"tampered")


def test_validate_envelope_rejects_payload_mismatch():
    envelope = _envelope(
        payload=dict(
            payload_sha256=("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
            size_bytes=5,
        ),
    )
    with pytest.raises(ObservationEnvelopeValidationError):
        validate_observation_envelope(envelope, payload_bytes=b"tampered")


def test_validate_envelope_rejects_expired_calibration():
    envelope = _envelope()
    with pytest.raises(ObservationEnvelopeValidationError):
        validate_observation_envelope(envelope, calibration_valid=False)


def test_envelope_roundtrip_serialization():
    envelope = _envelope()
    data = envelope.model_dump(mode="json")
    restored = ObservationEnvelope.model_validate(data)
    assert restored == envelope


# ---------------------------------------------------------- synthetic adapter


def test_adapter_rejects_ground_truth_on_normal_channel():
    from cpswm.perception_mapping.adapters import reject_ground_truth_leakage

    # A normal channel carrying ground-truth references must be rejected at
    # the boundary (simobs already refuses to *build* such an observation, so
    # the boundary check is exercised directly here).
    with pytest.raises(ObservationEnvelopeValidationError):
        reject_ground_truth_leakage(ground_truth_refs=(uuid4(),), oracle_channel=False)


def test_adapter_adapts_oracle_channel_with_authorization():
    adapter = SyntheticSimulatorAdapter()
    observation = _observation(oracle_channel=True, ground_truth_refs=(uuid4(),))
    envelope = adapter.adapt(
        observation,
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1",
        oracle_authorization=OracleAuthorization(
            authorization_id=uuid4(),
            declared_purpose="evaluation",
            issued_by="evaluator",
        ),
    )
    assert envelope.oracle_channel is True
    assert envelope.payload.payload_sha256
    assert envelope.verify_payload(adapter.payload_bytes(observation))


def test_adapter_roundtrip_replay_preserves_payload_hash():
    adapter = SyntheticSimulatorAdapter()
    observation = _observation()
    envelope = adapter.adapt(
        observation,
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1",
    )
    data = envelope.model_dump(mode="json")
    restored = ObservationEnvelope.model_validate(data)
    assert restored.payload.payload_sha256 == envelope.payload.payload_sha256
    assert restored.verify_payload(adapter.payload_bytes(observation))


def test_adapter_source_never_imports_ground_truth():
    import re
    from pathlib import Path

    adapter_file = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "cpswm"
        / "perception_mapping"
        / "adapters"
        / "synthetic_adapter.py"
    )
    source = adapter_file.read_text(encoding="utf-8")
    assert not re.search(r"\b(?:from|import)\s+cpswm_gt\b", source)


# ------------------------------------------------------------------ M06 sync


def test_time_sync_preserves_source_time():
    source_time = datetime(2026, 8, 10, 8, 0, 0, tzinfo=UTC)
    result = SensorTimeSyncResult(
        household_id=uuid4(),
        sensor_id="cam-1",
        source_clock_domain="sensor",
        target_clock_domain="host",
        source_time=source_time,
        target_time=source_time + timedelta(seconds=0.25),
        offset_seconds=0.25,
        uncertainty_seconds=0.01,
        sync_version="0.1.0",
        valid_time=dict(
            start=source_time - timedelta(seconds=1),
            end=source_time + timedelta(seconds=10),
        ),
    )
    # The raw source time is untouched by alignment.
    assert result.source_time == source_time
    assert result.target_time == source_time + timedelta(seconds=0.25)


def test_time_sync_rejects_wrong_offset():
    source_time = datetime(2026, 8, 10, 8, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        SensorTimeSyncResult(
            household_id=uuid4(),
            sensor_id="cam-1",
            source_clock_domain="sensor",
            target_clock_domain="host",
            source_time=source_time,
            target_time=source_time + timedelta(seconds=0.5),
            offset_seconds=0.25,
            uncertainty_seconds=0.01,
            sync_version="0.1.0",
            valid_time=dict(start=source_time, end=source_time + timedelta(seconds=10)),
        )


def test_calibration_registry_rejects_expired_lookup():
    household = uuid4()
    start = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
    calibration = SensorCalibration(
        household_id=household,
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        calibration_version="0.1.0",
        valid_time=dict(start=start, end=start + timedelta(minutes=5)),
        frame_id="cam_1_optical",
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
        extrinsics=FrameTransform(
            household_id=household,
            source_frame_id="cam_1_optical",
            target_frame_id="base_link",
            translation=Vector3(x=0.0, y=0.0, z=1.0),
            rotation=Quaternion(),
            valid_time=dict(start=start, end=start + timedelta(minutes=5)),
            transform_version="0.1.0",
        ),
        artifact_sha256="0" * 64,
    )
    registry = CalibrationRegistry()
    registry.register(calibration)
    assert registry.is_calibration_valid(
        sensor_id="cam-1",
        household_id=household,
        at_time=start + timedelta(minutes=1),
    )
    assert not registry.is_calibration_valid(
        sensor_id="cam-1",
        household_id=household,
        at_time=start + timedelta(minutes=10),
    )
    with pytest.raises(CalibrationNotFoundError):
        registry.calibration_at(
            sensor_id="cam-1",
            household_id=household,
            at_time=start + timedelta(minutes=10),
        )


def test_calibration_registry_is_household_scoped():
    household = uuid4()
    other = uuid4()
    start = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
    calibration = SensorCalibration(
        household_id=household,
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        calibration_version="0.1.0",
        valid_time=dict(start=start, end=start + timedelta(minutes=5)),
        frame_id="cam_1_optical",
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
        artifact_sha256="0" * 64,
    )
    registry = CalibrationRegistry()
    registry.register(calibration)
    assert not registry.is_calibration_valid(
        sensor_id="cam-1",
        household_id=other,
        at_time=start + timedelta(minutes=1),
    )
