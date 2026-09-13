"""Local R^3 x SO(3) pose coordinates; no detector, dynamics or write authority.

Translation residuals are in the named world frame (meters), rotation residuals
in the reference object's local axes (radians). They are NOT an SE(3) logarithm.
A reference belongs to one object at one epoch. Changing reference requires
relinearizing retained evidence; covariance cannot be copied across charts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import pi
from typing import Any, Self
from uuid import UUID

import numpy as np
from pydantic import field_validator, model_validator
from scipy.spatial.transform import Rotation

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.contracts.likelihoods import Pose3D

_CUT_MARGIN = 64 * np.finfo(float).eps


def _pose(value: Any) -> Pose3D:
    # Reconstruct even model_copy / externally mutated instances at the boundary.
    if isinstance(value, Pose3D):
        raw = dict(vars(value))
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raise ValueError("pose must be a Pose3D or field mapping")
    try:
        numbers = np.asarray([raw[k] for k in ("x", "y", "z", "qx", "qy", "qz", "qw")], dtype=float)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("invalid pose coordinates") from error
    # A normalized quaternion cannot have a component larger than two. This
    # loose pre-bound avoids overflow in the existing squared-norm validator.
    if not np.isfinite(numbers).all() or np.any(np.abs(numbers[3:]) > 2):
        raise ValueError("finite coordinates and normalized quaternion required")
    result = Pose3D.model_validate(raw)
    if (
        not result.frame_id.strip()
        or not np.isfinite(
            [result.x, result.y, result.z, result.qx, result.qy, result.qz, result.qw]
        ).all()
    ):
        raise ValueError("pose frame and finite coordinates required")
    return result


class PoseState(ContractModel):
    object_instance_id: UUID
    valid_at: datetime
    pose: Pose3D

    @field_validator("pose", mode="before")
    @classmethod
    def validate_pose_input(cls, value: Any) -> Pose3D:
        return _pose(value)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        require_aware(self.valid_at, "pose epoch")
        _pose(self.pose)
        return self


def _state(value: PoseState) -> PoseState:
    raw = dict(vars(value))
    raw["pose"] = _pose(value.pose).model_dump()
    return PoseState.model_validate(raw)


def _rotation(pose: Pose3D) -> Rotation:
    return Rotation.from_quat([pose.qx, pose.qy, pose.qz, pose.qw])


def pose_residual(reference: PoseState, observed: PoseState) -> tuple[float, ...]:
    """Express one pose at the same epoch in a reference chart.

    q and -q have the same residual. The ambiguous pi cut is rejected; callers
    must retain alternate hypotheses or choose/rebuild a suitable reference.
    No claim of Gaussian uncertainty or visibility follows from this geometry.
    """
    reference, observed = _state(reference), _state(observed)
    if (
        reference.object_instance_id != observed.object_instance_id
        or reference.valid_at.astimezone(UTC) != observed.valid_at.astimezone(UTC)
        or reference.pose.frame_id != observed.pose.frame_id
    ):
        raise ValueError("pose object, epoch and coordinate frame must match")
    a, b = reference.pose, observed.pose
    rotation = (_rotation(a).inv() * _rotation(b)).as_rotvec()
    if np.linalg.norm(rotation) >= pi - _CUT_MARGIN:
        raise ValueError("ambiguous rotation chart cut; retain hypotheses and relinearize")
    result = (b.x - a.x, b.y - a.y, b.z - a.z, *map(float, rotation))
    if not np.isfinite(result).all():
        raise ValueError("pose residual overflow")
    return result


def apply_pose_delta(reference: PoseState, delta: tuple[float, ...]) -> PoseState:
    """Retract six local coordinates at a fixed reference; not a time predictor."""
    reference = _state(reference)
    vector = np.asarray(delta, dtype=float)
    if vector.shape != (6,) or not np.isfinite(vector).all():
        raise ValueError("six finite pose delta coordinates required")
    if np.linalg.norm(vector[3:]) >= pi - _CUT_MARGIN:
        raise ValueError("pose delta crosses rotation chart cut")
    a = reference.pose
    xyz = np.asarray([a.x, a.y, a.z]) + vector[:3]
    quat = (_rotation(a) * Rotation.from_rotvec(vector[3:])).as_quat()
    return PoseState(
        object_instance_id=reference.object_instance_id,
        valid_at=reference.valid_at,
        pose=Pose3D(
            frame_id=a.frame_id,
            x=xyz[0],
            y=xyz[1],
            z=xyz[2],
            qx=quat[0],
            qy=quat[1],
            qz=quat[2],
            qw=quat[3],
        ),
    )
