"""Raw RGB-D surface candidates, deliberately not object-centre/6D pose evidence.

Depth order statistics describe pixels within detector boxes, not probabilities
of object identity. A box can include hands, the support or background. No label,
pose ground truth, learned noise, or invented orientation is accepted here.
"""

from __future__ import annotations

import io
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np

from cpswm.contracts.base import require_aware
from cpswm.perception_mapping.adapters.contracts import SensorModality
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import VisualFrame, decode_rgb
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class PinholeIntrinsics:
    camera_id: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    source_sha256: str
    distortion_coefficients: tuple[float, ...]

    def validate(self) -> None:
        if (
            not self.camera_id
            or self.width <= 0
            or self.height <= 0
            or not all(
                math.isfinite(v)
                for v in (self.fx, self.fy, self.cx, self.cy, *self.distortion_coefficients)
            )
            or min(self.fx, self.fy) <= 0
            or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
        ):
            raise ValueError("invalid pinned camera intrinsics")


@dataclass(frozen=True)
class SurfacePoint:
    depth_rank_fraction: float
    pixel_uv: tuple[int, int]
    nominal_pinhole_xyz_m: tuple[float, float, float]


@dataclass(frozen=True)
class SurfaceCandidate:
    detection_candidate_id: UUID
    rgb_observation_id: UUID
    depth_observation_id: UUID
    rgb_sha256: str
    depth_sha256: str
    capture_receipt_sha256: str
    camera_intrinsics_sha256: str
    frame_id: str
    detector_category: str
    detector_score_uncalibrated: float
    box_xyxy: tuple[float, float, float, float]
    pixel_count: int
    valid_depth_pixels: int
    depth_spread_90_m: float | None
    surface_samples: tuple[SurfacePoint, ...]
    status: str
    orientation: None = None
    instance_id: None = None
    likelihood_model: None = None
    ambiguity: tuple[str, ...] = (
        "BOX_MAY_MIX_OBJECT_HAND_SUPPORT_BACKGROUND",
        "SURFACE_IS_NOT_OBJECT_CENTRE",
        "PINHOLE_COORDINATES_IGNORE_RETAINED_DISTORTION_COEFFICIENTS",
        "DEPTH_RANK_IS_NOT_PROBABILITY",
        "IDENTITY_AND_ORIENTATION_UNOBSERVED",
    )


def extract_surface_candidates(
    rgb: RawModalityObservation,
    depth: RawModalityObservation,
    frame: VisualFrame,
    intrinsics: PinholeIntrinsics,
    *,
    cutoff: datetime,
) -> tuple[SurfaceCandidate, ...]:
    """Source-bound partial geometry; no Gaussian covariance can be inferred here."""
    intrinsics.validate()
    renv, pixels = decode_rgb(rgb, cutoff=cutoff)
    denv = depth.envelope()
    if renv.payload is None or denv.payload is None:
        raise ValueError("RGB-D payload references required")
    if (
        denv.oracle_channel
        or denv.sensor.modality is not SensorModality.DEPTH
        or depth.depth_unit != "m"
        or denv.metadata.source_type != renv.metadata.source_type
        or (denv.identity.household_id, denv.identity.session_id, denv.identity.trace_id)
        != (renv.identity.household_id, renv.identity.session_id, renv.identity.trace_id)
        or denv.frame_id != renv.frame_id
        or denv.capture_time != renv.capture_time
        or depth.capture_receipt_sha256 != rgb.capture_receipt_sha256
        or not denv.capture_time <= denv.arrival_time <= require_aware(cutoff, "cutoff")
        or renv.sensor.sensor_id != f"hocap:{intrinsics.camera_id}:rgb"
        or denv.sensor.sensor_id != f"hocap:{intrinsics.camera_id}:depth"
    ):
        raise ValueError("RGB/depth pairing, camera, source or cutoff mismatch")
    if (
        frame.observation_id != renv.identity.observation_id
        or frame.input_sha256 != renv.payload.payload_sha256
        or frame.receipt_sha256 != rgb.capture_receipt_sha256
        or frame.frame_id != renv.frame_id
        or frame.capture_time != renv.capture_time
        or frame.arrival_time != renv.arrival_time
        or frame.inference_cutoff > cutoff
        or (frame.household_id, frame.session_id, frame.trace_id)
        != (renv.identity.household_id, renv.identity.session_id, renv.identity.trace_id)
        or (frame.width, frame.height) != (intrinsics.width, intrinsics.height)
        or pixels.shape[:2] != (intrinsics.height, intrinsics.width)
    ):
        raise ValueError("prediction differs from delivered RGB source")
    if len(depth.payload_bytes) > intrinsics.width * intrinsics.height * 4 + 65536:
        raise ValueError("depth allocation exceeds bound")
    stream = io.BytesIO(depth.payload_bytes)
    version = np.lib.format.read_magic(stream)
    if version != (1, 0):
        raise ValueError("expected bounded float32 NPY v1 depth")
    shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
    if (
        shape != (intrinsics.height, intrinsics.width)
        or fortran
        or dtype != np.dtype("float32")
        or math.prod(shape) * 4 != len(depth.payload_bytes) - stream.tell()
    ):
        raise ValueError("invalid depth shape, dtype or byte size")
    z = np.load(io.BytesIO(depth.payload_bytes), allow_pickle=False)
    if not np.isfinite(z).all() or (z < 0).any():
        raise ValueError("nonfinite or negative depth")
    records = []
    seen = set()
    for c in frame.candidates:
        if c.candidate_id in seen:
            raise ValueError("duplicate detection identity")
        seen.add(c.candidate_id)
        if c.category == "person":
            continue
        x0, y0, x1, y1 = c.box_xyxy
        if (
            not all(math.isfinite(v) for v in c.box_xyxy)
            or not 0 <= x0 < x1 <= intrinsics.width
            or not 0 <= y0 < y1 <= intrinsics.height
            or not math.isfinite(c.detector_score)
            or not 0 <= c.detector_score <= 1
        ):
            raise ValueError("invalid detector candidate")
        # Include integer pixel centres within the box; no mask/foreground assertion.
        left, top, right, bottom = map(math.ceil, (x0, y0, x1, y1))
        crop = z[top:bottom, left:right]
        v, u = np.nonzero(crop > 0)
        depths = crop[v, u]
        order = np.argsort(depths, kind="stable")
        samples = []
        for rank in (0.05, 0.5, 0.95) if len(order) else ():
            i = order[round(rank * (len(order) - 1))]
            px, py, d = int(u[i]) + left, int(v[i]) + top, float(depths[i])
            samples.append(
                SurfacePoint(
                    rank,
                    (px, py),
                    (
                        (px - intrinsics.cx) * d / intrinsics.fx,
                        (py - intrinsics.cy) * d / intrinsics.fy,
                        d,
                    ),
                )
            )
        records.append(
            SurfaceCandidate(
                c.candidate_id,
                renv.identity.observation_id,
                denv.identity.observation_id,
                renv.payload.payload_sha256,
                denv.payload.payload_sha256,
                rgb.capture_receipt_sha256,
                intrinsics.source_sha256,
                frame.frame_id,
                c.category,
                c.detector_score,
                c.box_xyxy,
                crop.size,
                len(order),
                (samples[2].nominal_pinhole_xyz_m[2] - samples[0].nominal_pinhole_xyz_m[2])
                if samples
                else None,
                tuple(samples),
                "UNCALIBRATED_SURFACE_CANDIDATE" if samples else "NO_VALID_DEPTH",
            )
        )
    return tuple(records)


class NaturalGeometryProducer:
    """Consume a pinned prediction replay and actual raw input in the existing stream.

    This is partial surface geometry admission, not registered P5-first semantic
    consumption. The absence of an observation model is an explicit rejection.
    """

    def __init__(self, frames: tuple[VisualFrame, ...], intrinsics: PinholeIntrinsics) -> None:
        intrinsics.validate()
        if len({f.observation_id for f in frames}) != len(frames):
            raise ValueError("duplicate prediction frames")
        self._frames = {f.observation_id: deepcopy(f) for f in frames}
        self._intrinsics = deepcopy(intrinsics)
        self._binding = content_sha256((frames, intrinsics))
        self._history: tuple[tuple[UUID, str, str], ...] = ()
        self._records: tuple[SurfaceCandidate, ...] = ()
        self._completed: tuple[UUID, ...] = ()
        self._cutoff: datetime | None = None

    def checkpoint_state(self) -> dict[str, Any]:
        return deepcopy(
            dict(
                binding=self._binding,
                history=self._history,
                records=self._records,
                completed=self._completed,
                cutoff=self._cutoff,
            )
        )

    def restore_state(self, state: dict[str, Any]) -> None:
        if state["binding"] != self._binding:
            raise ValueError("geometry restore requires same predictions and camera")
        self._history, self._records, self._completed, self._cutoff = deepcopy(
            (state["history"], state["records"], state["completed"], state["cutoff"])
        )

    def records(self) -> tuple[SurfaceCandidate, ...]:
        return deepcopy(self._records)

    def infer(
        self, visible_prefix: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> None:
        when = require_aware(cutoff, "cutoff")
        if self._cutoff is not None and when < self._cutoff:
            raise ValueError("geometry cutoff moved backwards")
        envelopes = [r.envelope() for r in visible_prefix]
        if any(e.arrival_time > when or e.oracle_channel for e in envelopes):
            raise ValueError("future or oracle input")
        if any(e.payload is None for e in envelopes):
            raise ValueError("raw payload references required")
        history = tuple(
            (
                e.identity.observation_id,
                e.payload.payload_sha256 if e.payload is not None else "",
                content_sha256((r.envelope_json, r.capture_receipt_sha256, r.depth_unit)),
            )
            for e, r in zip(envelopes, visible_prefix, strict=True)
        )
        if len({row[0] for row in history}) != len(history):
            raise ValueError("duplicate raw observations")
        if history[: len(self._history)] != self._history:
            raise ValueError("geometry raw history changed or truncated")
        pairs: dict[tuple[str, datetime, str], dict[SensorModality, RawModalityObservation]] = {}
        for e, raw in zip(envelopes, visible_prefix, strict=True):
            key = (e.frame_id, e.capture_time, raw.capture_receipt_sha256)
            group = pairs.setdefault(key, {})
            if e.sensor.modality in group:
                raise ValueError("ambiguous RGB-D pairing")
            group[e.sensor.modality] = raw
        records, completed = list(self._records), list(self._completed)
        for group in pairs.values():
            if SensorModality.RGB not in group or SensorModality.DEPTH not in group:
                continue
            rgb, depth = group[SensorModality.RGB], group[SensorModality.DEPTH]
            observation_id = rgb.envelope().identity.observation_id
            if observation_id in completed:
                continue
            if observation_id not in self._frames:
                raise ValueError("delivered RGB missing pinned prediction")
            records.extend(
                extract_surface_candidates(
                    rgb, depth, self._frames[observation_id], self._intrinsics, cutoff=when
                )
            )
            completed.append(observation_id)
        self._history, self._records = history, tuple(records)
        self._completed, self._cutoff = tuple(completed), when
        return None
