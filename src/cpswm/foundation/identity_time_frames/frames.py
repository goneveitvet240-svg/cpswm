"""Time-valid coordinate transform registry for M02."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from math import sqrt
from uuid import NAMESPACE_URL, UUID, uuid5

from .contracts import FrameTransform, Quaternion, Vector3


class FrameTransformConflictError(ValueError):
    """Raised when transform registration would make a direct edge ambiguous."""


class FrameTransformNotFoundError(LookupError):
    """Raised when no valid frame path exists."""


def _multiply(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _as_tuple(value: Quaternion) -> tuple[float, float, float, float]:
    return value.x, value.y, value.z, value.w


def _conjugate(value: Quaternion) -> Quaternion:
    return Quaternion(x=-value.x, y=-value.y, z=-value.z, w=value.w)


def _rotate(rotation: Quaternion, point: Vector3) -> Vector3:
    pure = (point.x, point.y, point.z, 0.0)
    rotated = _multiply(_multiply(_as_tuple(rotation), pure), _as_tuple(_conjugate(rotation)))
    return Vector3(x=rotated[0], y=rotated[1], z=rotated[2])


def _normalized_quaternion(x: float, y: float, z: float, w: float) -> Quaternion:
    norm = sqrt(x * x + y * y + z * z + w * w)
    return Quaternion(x=x / norm, y=y / norm, z=z / norm, w=w / norm)


def invert_transform(transform: FrameTransform) -> FrameTransform:
    rotation = _conjugate(transform.rotation)
    negative = Vector3(
        x=-transform.translation.x,
        y=-transform.translation.y,
        z=-transform.translation.z,
    )
    translation = _rotate(rotation, negative)
    return FrameTransform(
        transform_id=transform.transform_id,
        household_id=transform.household_id,
        source_frame_id=transform.target_frame_id,
        target_frame_id=transform.source_frame_id,
        translation=translation,
        rotation=rotation,
        # A0 does not claim covariance propagation through inversion.
        covariance=None,
        valid_time=transform.valid_time,
        transform_version=transform.transform_version,
        component_transform_ids=transform.component_transform_ids or (transform.transform_id,),
    )


def compose_transforms(first: FrameTransform, second: FrameTransform) -> FrameTransform:
    """Compose source->middle and middle->target transforms."""

    if first.household_id != second.household_id:
        raise ValueError("cannot compose transforms from different households")
    if first.target_frame_id != second.source_frame_id:
        raise ValueError("frame transform endpoints do not compose")
    if not first.valid_time.overlaps(second.valid_time):
        raise ValueError("frame transforms do not share a valid-time interval")
    translated = _rotate(second.rotation, first.translation)
    translation = Vector3(
        x=translated.x + second.translation.x,
        y=translated.y + second.translation.y,
        z=translated.z + second.translation.z,
    )
    raw_rotation = _multiply(_as_tuple(second.rotation), _as_tuple(first.rotation))
    rotation = _normalized_quaternion(
        raw_rotation[0], raw_rotation[1], raw_rotation[2], raw_rotation[3]
    )
    starts = max(first.valid_time.start, second.valid_time.start)
    ends = [end for end in (first.valid_time.end, second.valid_time.end) if end]
    end = min(ends) if ends else None
    component_ids = (first.component_transform_ids or (first.transform_id,)) + (
        second.component_transform_ids or (second.transform_id,)
    )
    derived_id = uuid5(
        NAMESPACE_URL,
        "cpswm-frame-compose:"
        + ":".join(
            [
                str(first.household_id),
                first.source_frame_id,
                second.target_frame_id,
                *(str(item) for item in component_ids),
            ]
        ),
    )
    return FrameTransform(
        transform_id=derived_id,
        household_id=first.household_id,
        source_frame_id=first.source_frame_id,
        target_frame_id=second.target_frame_id,
        translation=translation,
        rotation=rotation,
        covariance=None,
        valid_time={"start": starts, "end": end},
        transform_version=f"composed:{first.transform_version}+{second.transform_version}",
        component_transform_ids=component_ids,
    )


class FrameRegistry:
    """Household-scoped transform graph with deterministic path lookup."""

    def __init__(self) -> None:
        self._transforms: list[FrameTransform] = []

    def register(self, transform: FrameTransform) -> None:
        for existing in self._transforms:
            if existing.transform_id == transform.transform_id:
                if existing != transform:
                    raise FrameTransformConflictError("transform_id is already registered")
                return
            same_pair = existing.household_id == transform.household_id and {
                existing.source_frame_id,
                existing.target_frame_id,
            } == {transform.source_frame_id, transform.target_frame_id}
            if same_pair and existing.valid_time.overlaps(transform.valid_time):
                raise FrameTransformConflictError(
                    "overlapping transforms for one frame pair are ambiguous"
                )
        self._transforms.append(transform)

    def lookup(
        self,
        *,
        source_frame_id: str,
        target_frame_id: str,
        household_id: UUID,
        at_time: datetime,
    ) -> FrameTransform:
        if source_frame_id == target_frame_id:
            raise ValueError("identity transforms are implicit and are not returned")
        queue = deque([(source_frame_id, None)])
        visited = {source_frame_id}
        while queue:
            frame_id, accumulated = queue.popleft()
            for edge in self._edges(frame_id, household_id, at_time):
                neighbor = edge.target_frame_id
                if neighbor in visited:
                    continue
                combined = edge if accumulated is None else compose_transforms(accumulated, edge)
                if neighbor == target_frame_id:
                    return combined
                visited.add(neighbor)
                queue.append((neighbor, combined))
        raise FrameTransformNotFoundError(
            f"no frame path {source_frame_id!r} -> {target_frame_id!r}"
        )

    def transform_point(self, point: Vector3, transform: FrameTransform) -> Vector3:
        rotated = _rotate(transform.rotation, point)
        return Vector3(
            x=rotated.x + transform.translation.x,
            y=rotated.y + transform.translation.y,
            z=rotated.z + transform.translation.z,
        )

    def _edges(self, frame_id: str, household_id: UUID, at_time: datetime) -> list[FrameTransform]:
        edges: list[FrameTransform] = []
        for item in self._transforms:
            if item.household_id != household_id or not item.valid_time.contains(at_time):
                continue
            if item.source_frame_id == frame_id:
                edges.append(item)
            elif item.target_frame_id == frame_id:
                edges.append(invert_transform(item))
        edges.sort(key=lambda edge: (edge.target_frame_id, str(edge.transform_id)))
        return edges
