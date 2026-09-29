"""Authorized, source-paired Unity RGB-D and ideal camera self-localization.

The f0825767 renderer encodes Linear01Depth * (far-near), not ray range.
Correct the documented shader scale before pinhole unprojection. Returned
points are sampled box surfaces, never object centres, identities or densities.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Any, Literal, cast
from uuid import UUID

import numpy as np
from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, SourceType, require_aware
from cpswm.perception_mapping.adapters.contracts import SensorModality
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import VisualFrame, decode_rgb
from cpswm.system.reproducibility import content_sha256

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Finite = Annotated[float, Field(allow_inf_nan=False, strict=True)]
SCHEMA = "unity-rgbd-self-pose@1"
PROFILE = "rgbd_self_pose"
SENSORS = ("live-unity-rgbd:rgb", "live-unity-rgbd:depth", "live-unity-rgbd:self-pose")


class CameraSelfPose(ContractModel):
    schema_id: Literal["unity-rgbd-self-pose@1"]
    action_id: UUID
    capture_time: datetime
    width: Annotated[int, Field(strict=True, ge=1, le=640)]
    height: Annotated[int, Field(strict=True, ge=1, le=640)]
    vertical_fov_degrees: Annotated[Finite, Field(gt=0, lt=180)]
    position_m: tuple[Finite, Finite, Finite]
    yaw_degrees: Annotated[Finite, Field(ge=0, lt=360)]
    pitch_degrees: Annotated[Finite, Field(ge=-90, le=90)]
    near_plane_m: Annotated[Finite, Field(gt=0)]
    far_plane_m: Annotated[Finite, Field(gt=0)]
    depth_semantics: Literal["Linear01Depth_times_far_minus_near"]
    depth_unit: Literal["m"]
    unity_commit: Literal["f0825767cd50d69f666c7f282e54abfe58f1e917"]
    world_frame: Literal["unity-scene-world-x-right-y-up-z-forward"]
    localization: Literal["AUTHORIZED_IDEAL_SIMULATOR_CAMERA_SELF_POSE"]
    rgb_sha256: Digest
    depth_sha256: Digest
    worker_sha256: Digest
    unity_sha256: Digest
    scene_sha256: Digest
    configuration_sha256: Digest

    @model_validator(mode="after")
    def validate_camera(self) -> CameraSelfPose:
        require_aware(self.capture_time, "camera capture")
        if self.near_plane_m >= self.far_plane_m:
            raise ValueError("invalid camera clipping planes")
        if self.configuration_sha256 != content_sha256(
            (
                PROFILE,
                self.width,
                self.height,
                self.vertical_fov_degrees,
                self.near_plane_m,
                self.far_plane_m,
                False,
            )
        ):
            raise ValueError("camera configuration differs from capture binding")
        return self

    @property
    def focal_pixels(self) -> float:
        return self.height / (2.0 * math.tan(math.radians(self.vertical_fov_degrees) / 2.0))

    def world_point(self, u: int, v: int, rendered_depth: float) -> tuple[float, float, float]:
        """Pixel indices; sample centre (u+.5,v+.5). Unity local Y points up."""
        if (
            type(u) is not int
            or type(v) is not int
            or not 0 <= u < self.width
            or not 0 <= v < self.height
            or not math.isfinite(rendered_depth)
            or not 0 < rendered_depth < self.far_plane_m - self.near_plane_m
        ):
            raise ValueError("invalid surface pixel or clipped depth")
        z = rendered_depth * self.far_plane_m / (self.far_plane_m - self.near_plane_m)
        x = (u + 0.5 - self.width / 2.0) * z / self.focal_pixels
        y = -(v + 0.5 - self.height / 2.0) * z / self.focal_pixels
        p, a = math.radians(self.pitch_degrees), math.radians(self.yaw_degrees)
        # R_y(yaw) R_x(pitch); positive pitch looks down in Unity.
        yy, zz = math.cos(p) * y - math.sin(p) * z, math.sin(p) * y + math.cos(p) * z
        return (
            self.position_m[0] + math.cos(a) * x + math.sin(a) * zz,
            self.position_m[1] + yy,
            self.position_m[2] - math.sin(a) * x + math.cos(a) * zz,
        )


def packet_receipt(payloads: tuple[bytes, bytes, bytes]) -> str:
    return content_sha256((SCHEMA, tuple(sha256(p).hexdigest() for p in payloads)))


def decode_unity_rgbd(
    observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
) -> tuple[CameraSelfPose, np.ndarray]:
    """Reject partial, cross-exposure, privileged or reordered bundles."""
    if len(observations) != 3:
        raise ValueError("RGB-D requires RGB, depth and self-pose in capture order")
    rgb, depth, pose = observations
    envs = tuple(r.envelope() for r in observations)
    renv, denv, penv = envs
    _, pixels = decode_rgb(rgb, cutoff=cutoff)
    if len(pose.payload_bytes) > 16384:
        raise ValueError("camera self-pose packet exceeds bound")
    camera = CameraSelfPose.model_validate_json(pose.payload_bytes)
    scope = (renv.identity.household_id, renv.identity.session_id, renv.identity.trace_id)
    receipt = packet_receipt((rgb.payload_bytes, depth.payload_bytes, pose.payload_bytes))
    if len({e.identity.observation_id for e in envs}) != 3:
        raise ValueError("duplicate RGB-D channel identity")
    for item, e, modality, sensor in zip(
        observations,
        envs,
        (SensorModality.RGB, SensorModality.DEPTH, SensorModality.ODOMETRY),
        SENSORS,
        strict=True,
    ):
        if (
            e.oracle_channel
            or e.metadata.source_type is not SourceType.SIMULATION
            or e.sensor.modality is not modality
            or e.sensor.sensor_id != sensor
            or e.frame_id != "unity-main-camera"
            or e.clock_domain != "host-utc"
            or (e.identity.household_id, e.identity.session_id, e.identity.trace_id) != scope
            or e.metadata.source_id != str(camera.action_id)
            or e.capture_time != camera.capture_time
            or e.arrival_time != renv.arrival_time
            or not e.capture_time <= e.arrival_time <= require_aware(cutoff, "cutoff")
            or item.capture_receipt_sha256 != receipt
            or item.archive_sampling_json is not None
            or item.depth_unit != ("m" if modality is SensorModality.DEPTH else None)
        ):
            raise ValueError("RGB-D exposure, scope, ownership, units or receipt mismatch")
    assert renv.payload is not None and denv.payload is not None and penv.payload is not None
    if (
        renv.payload.payload_sha256 != camera.rgb_sha256
        or denv.payload.payload_sha256 != camera.depth_sha256
        or pixels.shape[:2] != (camera.height, camera.width)
    ):
        raise ValueError("camera calibration is not paired with these RGB-D bytes")
    if len(depth.payload_bytes) > camera.width * camera.height * 4 + 65536:
        raise ValueError("depth allocation exceeds bound")
    stream = io.BytesIO(depth.payload_bytes)
    if np.lib.format.read_magic(stream) != (1, 0):
        raise ValueError("expected float32 NPY v1 depth")
    shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
    if (
        shape != (camera.height, camera.width)
        or fortran
        or dtype != np.dtype("float32")
        or math.prod(shape) * 4 != len(depth.payload_bytes) - stream.tell()
    ):
        raise ValueError("invalid bounded depth array")
    values = np.load(io.BytesIO(depth.payload_bytes), allow_pickle=False)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or (values > camera.far_plane_m - camera.near_plane_m + 1e-5).any()
    ):
        raise ValueError("invalid depth range")
    values.flags.writeable = False
    return camera, values


def public_rgb_observations(
    observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
) -> tuple[RawModalityObservation, ...]:
    """RGB control stays RGB; additional channels require the explicit paired profile."""
    envs = tuple(r.envelope() for r in observations)
    if any(
        e.sensor.modality is not SensorModality.RGB or e.sensor.sensor_id in SENSORS for e in envs
    ):
        decode_unity_rgbd(observations, cutoff=cutoff)
        return observations[:1]
    return observations


@dataclass(frozen=True)
class WorldSurfaceSample:
    depth_rank_fraction: float
    pixel_uv: tuple[int, int]
    rendered_depth_m: float
    nominal_world_xyz_m: tuple[float, float, float]


@dataclass(frozen=True)
class WorldSurfaceCandidate:
    detection_candidate_id: UUID
    category: str
    box_xyxy: tuple[float, float, float, float]
    box_pixel_count: int
    valid_depth_pixel_count: int
    samples: tuple[WorldSurfaceSample, ...]
    object_instance_id: None = None
    object_centre_m: None = None
    orientation: None = None
    probability: None = None


@dataclass(frozen=True)
class RGBDSurfaceSupport:
    observation_ids: tuple[UUID, UUID, UUID]
    payload_sha256: tuple[str, str, str]
    capture_receipt_sha256: str
    camera: CameraSelfPose
    candidates: tuple[WorldSurfaceCandidate, ...]
    status: str = "UNCALIBRATED_BOX_SURFACES_WITH_IDEAL_CAMERA_SELF_POSE"
    identity_association: None = None
    likelihood_model: None = None
    memory_write_authorized: bool = False


def surface_support(
    observations: tuple[RawModalityObservation, ...], frame: VisualFrame, *, cutoff: datetime
) -> RGBDSurfaceSupport:
    camera, depth = decode_unity_rgbd(observations, cutoff=cutoff)
    rgb = observations[0]
    env = rgb.envelope()
    if (
        frame.observation_id != env.identity.observation_id
        or frame.input_sha256 != camera.rgb_sha256
        or frame.receipt_sha256 != rgb.capture_receipt_sha256
        or frame.capture_time != camera.capture_time
        or frame.arrival_time != env.arrival_time
        or frame.inference_cutoff != cutoff
        or (frame.height, frame.width) != depth.shape
    ):
        raise ValueError("surface candidates differ from paired RGB measurement")
    rows = []
    for c in frame.candidates:
        x0, y0, x1, y1 = c.box_xyxy
        if not (
            all(math.isfinite(v) for v in c.box_xyxy)
            and 0 <= x0 < x1 <= camera.width
            and 0 <= y0 < y1 <= camera.height
        ):
            raise ValueError("invalid surface candidate box")
        left, top, right, bottom = (max(0, math.ceil(v - 0.5)) for v in (x0, y0, x1, y1))
        box = depth[top:bottom, left:right]
        yy, xx = np.nonzero((box > 0) & (box < camera.far_plane_m - camera.near_plane_m))
        order = np.argsort(box[yy, xx], kind="stable")
        samples = []
        for rank in (0.05, 0.5, 0.95) if len(order) else ():
            idx = order[int(rank * (len(order) - 1))]
            u, v = int(xx[idx]) + left, int(yy[idx]) + top
            value = float(depth[v, u])
            samples.append(WorldSurfaceSample(rank, (u, v), value, camera.world_point(u, v, value)))
        rows.append(
            WorldSurfaceCandidate(
                c.candidate_id, c.category, c.box_xyxy, box.size, len(order), tuple(samples)
            )
        )
    return RGBDSurfaceSupport(
        cast(
            tuple[UUID, UUID, UUID],
            tuple(r.envelope().identity.observation_id for r in observations),
        ),
        cast(
            tuple[str, str, str], tuple(sha256(r.payload_bytes).hexdigest() for r in observations)
        ),
        rgb.capture_receipt_sha256,
        camera,
        tuple(rows),
    )


def observations_from_response(
    response: dict[str, Any],
    *,
    action_id: UUID,
    scope: tuple[UUID, UUID, UUID],
    arrival: datetime,
    provenance: dict[str, str],
) -> tuple[RawModalityObservation, ...]:
    """Transport-only constructor; validate before admission to the owner journal."""
    import base64
    from uuid import uuid4

    from cpswm.contracts.base import BaseRecordMetadata
    from cpswm.perception_mapping.adapters.contracts import (
        ObservationEnvelope,
        ObservationIdentity,
        PayloadRef,
        SensorRef,
    )

    if (
        set(response)
        != {"action_id", "capture_time", "success", "error", "rgb_npy", "depth_npy", "camera"}
        or response["action_id"] != str(action_id)
        or type(response["success"]) is not bool
        or type(response["error"]) is not str
    ):
        raise ValueError("unexpected public RGB-D response fields or owner")
    if any(
        type(response[k]) is not str or len(response[k]) > 4_000_000
        for k in ("rgb_npy", "depth_npy")
    ):
        raise ValueError("RGB-D transport payload exceeds bound")
    rgb, depth = (base64.b64decode(response[k], validate=True) for k in ("rgb_npy", "depth_npy"))
    # The worker may supply only camera sensor fields; conflicting/privileged keys fail.
    fixed = dict(
        schema_id=SCHEMA,
        action_id=action_id,
        capture_time=response["capture_time"],
        rgb_sha256=sha256(rgb).hexdigest(),
        depth_sha256=sha256(depth).hexdigest(),
        worker_sha256=provenance["worker"],
        unity_sha256=provenance["unity"],
        scene_sha256=provenance["house"],
        configuration_sha256=provenance["capture_configuration"],
    )
    if type(response["camera"]) is not dict or set(fixed) & set(response["camera"]):
        raise ValueError("worker camera packet overrides capture binding")
    camera = CameraSelfPose.model_validate({**response["camera"], **fixed})
    payloads = (rgb, depth, camera.model_dump_json().encode())
    receipt = packet_receipt(payloads)
    household, session, trace = scope
    rows = []
    for sensor, modality, payload in zip(
        SENSORS,
        (SensorModality.RGB, SensorModality.DEPTH, SensorModality.ODOMETRY),
        payloads,
        strict=True,
    ):
        identity = uuid4()
        envelope = ObservationEnvelope(
            metadata=BaseRecordMetadata(
                record_id=identity,
                schema_name=SCHEMA,
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                recorded_time=arrival,
                source_type=SourceType.SIMULATION,
                source_id=str(action_id),
                model_version="unity-camera-transport-rgbd-v1",
            ),
            identity=ObservationIdentity(
                observation_id=identity, household_id=household, session_id=session, trace_id=trace
            ),
            sensor=SensorRef(sensor_id=sensor, modality=modality),
            capture_time=camera.capture_time,
            arrival_time=arrival,
            clock_domain="host-utc",
            frame_id="unity-main-camera",
            payload=PayloadRef(
                payload_id=identity,
                payload_sha256=sha256(payload).hexdigest(),
                size_bytes=len(payload),
            ),
        )
        rows.append(
            RawModalityObservation(
                envelope.model_dump_json(),
                payload,
                receipt,
                "m" if modality is SensorModality.DEPTH else None,
            )
        )
    result = tuple(rows)
    decode_unity_rgbd(result, cutoff=arrival)
    return result


def implementation_binding() -> str:
    """Bind source plus loaded geometry helpers; include mutable declared constants."""
    from pathlib import Path

    from cpswm.system.structure_two_execution import _code_object_payload

    names = (
        "packet_receipt",
        "decode_unity_rgbd",
        "public_rgb_observations",
        "surface_support",
        "observations_from_response",
        "implementation_binding",
        "_stable_code_value",
    )
    functions = [(name, globals()[name]) for name in names]
    functions.extend(
        (name, vars(CameraSelfPose)[name]) for name in ("world_point", "validate_camera")
    )
    functions.append(("focal_pixels", vars(CameraSelfPose)["focal_pixels"].fget))
    return content_sha256(
        (
            sha256(Path(__file__).read_bytes()).hexdigest(),
            SCHEMA,
            PROFILE,
            SENSORS,
            CameraSelfPose.model_json_schema(),
            tuple(
                (name, content_sha256(_stable_code_value(_code_object_payload(fn.__code__))))
                for name, fn in functions
            ),
        )
    )


def _stable_code_value(value: Any) -> Any:
    """No marshal reference flags: retained float constants must not change code identity."""
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    if isinstance(value, tuple):
        return ("tuple", tuple(_stable_code_value(v) for v in value))
    if isinstance(value, frozenset):
        return ("frozenset", tuple(sorted((_stable_code_value(v) for v in value), key=repr)))
    if isinstance(value, complex):
        return ("complex", value.real.hex(), value.imag.hex())
    if isinstance(value, float):
        return ("float", value.hex())
    if value is Ellipsis:
        return ("ellipsis",)
    if value is None or type(value) in (bool, int, str):
        return (type(value).__name__, value)
    raise ValueError("unsupported code constant for stable geometry binding")
