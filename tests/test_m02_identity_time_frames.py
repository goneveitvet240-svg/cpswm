from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from cpswm.contracts import ValidTimeInterval
from cpswm.foundation.identity_time_frames import (
    ClockAlignment,
    FrameRegistry,
    FrameTransform,
    IdentityNamespace,
    IdentityRegistry,
    Quaternion,
    TimeAlignmentRegistry,
    Vector3,
    normalize_utc,
)
from cpswm.foundation.identity_time_frames.clocks import ClockAlignmentConflictError
from cpswm.foundation.identity_time_frames.frames import (
    FrameTransformConflictError,
    FrameTransformNotFoundError,
)
from cpswm.foundation.identity_time_frames.identity import IdentityConflictError


def test_identity_registry_enforces_namespace_and_household():
    registry = IdentityRegistry()
    household = registry.issue(IdentityNamespace.HOUSEHOLD)
    session = registry.issue(IdentityNamespace.SESSION, household_id=household.value)

    assert (
        registry.resolve(
            session.value,
            namespace=IdentityNamespace.SESSION,
            household_id=household.value,
        )
        == session
    )
    with pytest.raises(IdentityConflictError):
        registry.resolve(session.value, namespace=IdentityNamespace.EVENT)
    with pytest.raises(IdentityConflictError):
        registry.resolve(session.value, household_id=uuid4())


def test_normalize_utc_preserves_instant_and_rejects_naive(now):
    local = now.astimezone(timezone(timedelta(hours=8)))
    assert normalize_utc(local) == now
    with pytest.raises(ValueError):
        normalize_utc(datetime(2026, 8, 11, 8, 0))


def test_clock_alignment_supports_multihop_and_inverse(now, household_id):
    registry = TimeAlignmentRegistry()
    valid = ValidTimeInterval(start=now - timedelta(hours=1), end=None)
    sensor_to_session = ClockAlignment(
        household_id=household_id,
        source_clock_id="camera",
        target_clock_id="session",
        offset_seconds=0.1,
        uncertainty_seconds=0.01,
        valid_time=valid,
        alignment_version="calibration@1",
    )
    session_to_utc = ClockAlignment(
        household_id=household_id,
        source_clock_id="session",
        target_clock_id="utc",
        offset_seconds=-0.05,
        uncertainty_seconds=0.02,
        valid_time=valid,
        alignment_version="sync@1",
    )
    registry.register(sensor_to_session)
    registry.register(session_to_utc)

    result = registry.align(
        now,
        source_clock_id="camera",
        target_clock_id="utc",
        household_id=household_id,
    )
    assert result.target_time == now + timedelta(seconds=0.05)
    assert result.total_offset_seconds == pytest.approx(0.05)
    assert result.uncertainty_seconds == pytest.approx(0.03)

    inverse = registry.align(
        result.target_time,
        source_clock_id="utc",
        target_clock_id="camera",
        household_id=household_id,
    )
    assert inverse.target_time == now


def test_clock_registry_rejects_overlapping_versions(now, household_id):
    registry = TimeAlignmentRegistry()
    first = ClockAlignment(
        household_id=household_id,
        source_clock_id="sensor",
        target_clock_id="utc",
        offset_seconds=0.1,
        uncertainty_seconds=0.0,
        valid_time=ValidTimeInterval(start=now, end=None),
        alignment_version="v1",
    )
    registry.register(first)
    with pytest.raises(ClockAlignmentConflictError):
        registry.register(first.model_copy(update={"alignment_id": uuid4()}))


def test_frame_registry_composes_and_inverts_transforms(now, household_id):
    registry = FrameRegistry()
    valid = ValidTimeInterval(start=now - timedelta(minutes=1), end=None)
    camera_to_session = FrameTransform(
        household_id=household_id,
        source_frame_id="camera",
        target_frame_id="session_map",
        translation=Vector3(x=1, y=0, z=0),
        rotation=Quaternion(),
        valid_time=valid,
        transform_version="extrinsics@1",
    )
    session_to_household = FrameTransform(
        household_id=household_id,
        source_frame_id="session_map",
        target_frame_id="household_map",
        translation=Vector3(x=0, y=2, z=0),
        rotation=Quaternion(),
        valid_time=valid,
        transform_version="alignment@1",
    )
    registry.register(camera_to_session)
    registry.register(session_to_household)

    composed = registry.lookup(
        source_frame_id="camera",
        target_frame_id="household_map",
        household_id=household_id,
        at_time=now,
    )
    point = registry.transform_point(Vector3(x=1, y=1, z=1), composed)
    assert point == Vector3(x=2, y=3, z=1)
    assert composed.component_transform_ids == (
        camera_to_session.transform_id,
        session_to_household.transform_id,
    )
    assert (
        registry.lookup(
            source_frame_id="camera",
            target_frame_id="household_map",
            household_id=household_id,
            at_time=now,
        ).transform_id
        == composed.transform_id
    )

    inverse = registry.lookup(
        source_frame_id="household_map",
        target_frame_id="camera",
        household_id=household_id,
        at_time=now,
    )
    restored = registry.transform_point(point, inverse)
    assert restored.x == pytest.approx(1)
    assert restored.y == pytest.approx(1)
    assert restored.z == pytest.approx(1)


def test_frame_registry_isolates_households(now, household_id):
    registry = FrameRegistry()
    registry.register(
        FrameTransform(
            household_id=household_id,
            source_frame_id="camera",
            target_frame_id="map",
            translation=Vector3(x=0, y=0, z=0),
            valid_time=ValidTimeInterval(start=now, end=None),
            transform_version="v1",
        )
    )
    with pytest.raises(FrameTransformNotFoundError):
        registry.lookup(
            source_frame_id="camera",
            target_frame_id="map",
            household_id=uuid4(),
            at_time=now,
        )


def test_frame_registry_rejects_overlapping_reverse_edge(now, household_id):
    registry = FrameRegistry()
    direct = FrameTransform(
        household_id=household_id,
        source_frame_id="camera",
        target_frame_id="map",
        translation=Vector3(x=0, y=0, z=0),
        valid_time=ValidTimeInterval(start=now, end=None),
        transform_version="v1",
    )
    registry.register(direct)
    with pytest.raises(FrameTransformConflictError):
        registry.register(
            direct.model_copy(
                update={
                    "transform_id": uuid4(),
                    "source_frame_id": "map",
                    "target_frame_id": "camera",
                }
            )
        )
