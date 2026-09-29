"""Recomputed public visual support from the runtime's owned camera history.

These are frame detections and image locations, not scored world hypotheses.
No identity association, metric pose, likelihood, absence or memory right is
created. The existing durable raw/action journal is the only retained source.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import isfinite
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from cpswm.contracts.base import require_aware
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame, decode_rgb
from cpswm.perception_mapping.unity_rgbd import (
    RGBDSurfaceSupport,
    public_rgb_observations,
    surface_support,
)
from cpswm.system.joint_camera_feedback import CameraOutcomeDecoder, decoder_binding
from cpswm.system.reproducibility import content_sha256

if TYPE_CHECKING:
    from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


class VisualMeasurementDecoder(CameraOutcomeDecoder, Protocol):
    def measurements(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> tuple[VisualFrame, ...]: ...


@dataclass(frozen=True)
class ImageCandidateSupport:
    candidate_id: UUID
    category: str
    detector_score_uncalibrated: float
    box_xyxy: tuple[float, float, float, float]
    normalized_box_xyxy: tuple[float, float, float, float]
    world_instance_id: None = None
    world_position_m: None = None
    orientation: None = None
    probability: None = None


@dataclass(frozen=True)
class OwnedVisualFrame:
    frame: VisualFrame
    candidates: tuple[ImageCandidateSupport, ...]
    identical_pixel_group: str
    geometry: RGBDSurfaceSupport | None = None


@dataclass(frozen=True)
class OwnedVisualAction:
    command: ObservationCommand
    status: str
    receipt_sha256: str | None
    native_origin_sha256: str | None
    frames: tuple[OwnedVisualFrame, ...]


@dataclass(frozen=True)
class OwnedVisualSupport:
    decoder_binding_sha256: str
    owned_history_sha256: str
    actions: tuple[OwnedVisualAction, ...]
    scope: str = "PUBLIC_FRAME_CANDIDATES_AND_OPTIONAL_SURFACE_GEOMETRY_ONLY"
    scored_joint_density: None = None
    negative_observation_authorized: bool = False
    memory_write_authorized: bool = False


def _frame_support(
    raw: RawModalityObservation, frame: VisualFrame, cutoff: datetime
) -> OwnedVisualFrame:
    env, pixels = decode_rgb(raw, cutoff=cutoff)
    if (
        type(frame) is not VisualFrame
        or env.payload is None
        or frame.observation_id != env.identity.observation_id
        or (frame.household_id, frame.session_id, frame.trace_id)
        != (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
        or frame.sensor_id != env.sensor.sensor_id
        or frame.frame_id != env.frame_id
        or frame.capture_time != env.capture_time
        or frame.arrival_time != env.arrival_time
        or frame.inference_cutoff != cutoff
        or frame.input_sha256 != env.payload.payload_sha256
        or frame.receipt_sha256 != raw.capture_receipt_sha256
        or (frame.height, frame.width) != pixels.shape[:2]
        or frame.calibration_status != "UNCALIBRATED_CANDIDATES_ONLY"
        or frame.identity_status != "UNRESOLVED"
        or frame.pose_status != "NOT_ESTIMATED"
        or frame.negative_observation_authorized is not False
        or type(frame.candidates) is not tuple
        or not isfinite(frame.minimum_score)
        or not 0 <= frame.minimum_score <= 1
        or (frame.archive_sequence_id, frame.archive_media_time)
        != (raw.archive_timeline() or (None, None))
    ):
        raise ValueError("visual support frame/raw binding or authority differs")
    rows, seen = [], set()
    for candidate in frame.candidates:
        if type(candidate) is not DetectionCandidate or candidate.candidate_id in seen:
            raise ValueError("invalid or duplicate visual candidate")
        seen.add(candidate.candidate_id)
        box = candidate.box_xyxy
        if (
            type(box) is not tuple
            or len(box) != 4
            or not all(isfinite(v) for v in (*box, candidate.detector_score))
            or not 0 <= box[0] < box[2] <= frame.width
            or not 0 <= box[1] < box[3] <= frame.height
            or not frame.minimum_score <= candidate.detector_score <= 1
            or not candidate.category.strip()
        ):
            raise ValueError("invalid visual candidate geometry or score")
        rows.append(
            ImageCandidateSupport(
                candidate.candidate_id,
                candidate.category,
                candidate.detector_score,
                box,
                (
                    box[0] / frame.width,
                    box[1] / frame.height,
                    box[2] / frame.width,
                    box[3] / frame.height,
                ),
            )
        )
    # Equal pixels are a dependency warning, NOT an assertion that other frames
    # are independent, the same world object, or acquired at the same pose.
    group = content_sha256((pixels.shape, str(pixels.dtype), sha256(pixels.tobytes()).hexdigest()))
    return OwnedVisualFrame(frame, tuple(rows), group)


def reconstruct_visual_support(
    *,
    commands: Mapping[UUID, tuple[ObservationCommand, str]],
    statuses: Mapping[UUID, str | ObservationDelivery],
    native_origins: Mapping[UUID, str],
    raw: Mapping[UUID, RawModalityObservation],
    scope: tuple[UUID, UUID, UUID],
    decoder: VisualMeasurementDecoder,
    expected_binding: str,
) -> OwnedVisualSupport:
    """No evaluator data, predicted frames or cached support accepted as inputs.

    The caller is the runtime owner. Hashes bind its declared inputs; they do not
    authenticate a fabricated replacement for the entire owner or physical run.
    """
    from cpswm.perception_mapping import unity_rgbd
    from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery

    if (
        public_rgb_observations is not unity_rgbd.public_rgb_observations
        or surface_support is not unity_rgbd.surface_support
        or decoder_binding(decoder) != expected_binding
    ):
        raise ValueError("visual support decoder dependency changed")
    if not callable(getattr(decoder, "measurements", None)):
        raise ValueError("configured camera decoder has no visual measurements")
    if set(commands) != set(statuses) or not set(native_origins) <= set(commands):
        raise ValueError("visual support action journal coverage differs")
    actions, seen = [], set()
    for key, (command, digest) in commands.items():
        if (
            type(command) is not ObservationCommand
            or command.action_id != key
            or content_sha256(command) != digest
            or not set(command.source_ids) <= set(raw)
        ):
            raise ValueError("visual support command or dependencies differ")
        require_aware(command.decision_time, "decision")
        origin = native_origins.get(key)
        if command.reason.startswith("joint-ciav@1:") and origin is None:
            raise ValueError("visual support modeled command lost its native origin")
        if origin is not None and (
            len(origin) != 64
            or any(c not in "0123456789abcdef" for c in origin)
            or not command.reason.startswith("joint-ciav@1:")
        ):
            raise ValueError("visual support native origin differs")
        delivery = statuses[key]
        if type(delivery) is str:
            if delivery not in {"READY", "OUTCOME_UNCERTAIN", "CANCELLED_STALE_JOINT"}:
                raise ValueError("invalid visual support action status")
            actions.append(OwnedVisualAction(command, delivery, None, origin, ()))
            continue
        if (
            type(delivery) is not ObservationDelivery
            or delivery.action_id != key
            or type(delivery.success) is not bool
            or delivery.received_at < command.decision_time
            or (delivery.success and (not delivery.observations or delivery.error))
            or (not delivery.success and not delivery.error)
        ):
            raise ValueError("invalid visual support delivery")
        require_aware(delivery.received_at, "received")
        rgb = public_rgb_observations(delivery.observations, cutoff=delivery.received_at)
        for item in delivery.observations:
            env = item.envelope()
            identity = env.identity.observation_id
            if (
                identity in seen
                or identity in command.source_ids
                or raw.get(identity) != item
                or (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
                != scope
                or env.metadata.source_id != str(key)
                or not command.decision_time
                <= env.capture_time
                <= env.arrival_time
                <= delivery.received_at
            ):
                raise ValueError("visual support public ownership differs")
            seen.add(identity)
        frames: tuple[OwnedVisualFrame, ...] = ()
        if delivery.success:
            measured = decoder.measurements(delivery.observations, cutoff=delivery.received_at)
            if type(measured) is not tuple or len(measured) != len(rgb):
                raise ValueError("visual support measurement coverage differs")
            frames = tuple(
                _frame_support(item, frame, delivery.received_at)
                for item, frame in zip(rgb, measured, strict=True)
            )
        if delivery.success and len(rgb) != len(delivery.observations):
            frames = (
                replace(
                    frames[0],
                    geometry=surface_support(
                        delivery.observations, frames[0].frame, cutoff=delivery.received_at
                    ),
                ),
            )
        actions.append(
            OwnedVisualAction(
                command,
                "DELIVERED" if delivery.success else "FAILED",
                content_sha256(
                    (
                        delivery.action_id,
                        delivery.success,
                        delivery.error,
                        delivery.received_at,
                        tuple(
                            (
                                r.envelope_json,
                                sha256(r.payload_bytes).hexdigest(),
                                r.capture_receipt_sha256,
                                r.depth_unit,
                                r.archive_sampling_json,
                            )
                            for r in delivery.observations
                        ),
                    )
                ),
                origin,
                frames,
            )
        )
    if decoder_binding(decoder) != expected_binding:
        raise ValueError("visual support decoder dependency changed during inference")
    return OwnedVisualSupport(
        expected_binding,
        content_sha256(
            tuple((a.command, a.status, a.receipt_sha256, a.native_origin_sha256) for a in actions)
        ),
        tuple(actions),
    )
