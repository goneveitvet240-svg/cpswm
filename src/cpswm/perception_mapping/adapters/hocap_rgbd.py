"""HO-Cap raw RGB-D import; annotation files are not accepted by this adapter.

Replay timestamps are caller-owned ordinal clocks, not measured exposure times.
Author labels, object IDs and hand sides must stay in the evaluator process.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

import numpy as np
from PIL import Image

from cpswm.contracts.base import BaseRecordMetadata, SourceType, require_aware
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class HOCapFrameSource:
    sequence_id: str
    camera_id: str
    frame_index: int
    rgb_sha256: str
    depth_sha256: str

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"subject_[1-9]/[0-9]{8}_[0-9]{6}", self.sequence_id) is None
            or re.fullmatch(r"[0-9]{12}", self.camera_id) is None
            or type(self.frame_index) is not int
            or not 0 <= self.frame_index <= 999999
            or any(
                re.fullmatch(r"[0-9a-f]{64}", h) is None
                for h in (self.rgb_sha256, self.depth_sha256)
            )
        ):
            raise ValueError("invalid HO-Cap raw frame identity or digest")

    def member(self, modality: str) -> str:
        if modality not in {"rgb", "depth"}:
            raise ValueError("only RGB and depth members are method inputs")
        stem, suffix = ("color", "jpg") if modality == "rgb" else ("depth", "png")
        return f"{self.sequence_id}/{self.camera_id}/{stem}_{self.frame_index:06d}.{suffix}"


def adapt_hocap_rgbd(
    source: HOCapFrameSource,
    *,
    rgb_bytes: bytes,
    depth_bytes: bytes,
    expected_source_sha256: str,
    household_id: UUID,
    session_id: UUID,
    trace_id: UUID,
    capture_time: datetime,
    arrival_time: datetime,
) -> tuple[RawModalityObservation, RawModalityObservation]:
    """Bind decoded sensor pixels to original JPEG/PNG and an external manifest pin.

    HO-Cap's author loader uses color intrinsics and divides aligned depth by
    1000. No pose, identity, contact label, camera likelihood, or covariance is
    inferred here. This conversion requires the native 640x480 RealSense format.
    """
    source = HOCapFrameSource(**vars(source))
    if content_sha256(source) != expected_source_sha256:
        raise ValueError("raw frame source differs from retained manifest")
    if require_aware(capture_time, "ordinal capture") > require_aware(arrival_time, "arrival"):
        raise ValueError("capture follows arrival")
    decoded = []
    for mode, data, expected, fmt in (
        ("rgb", rgb_bytes, source.rgb_sha256, "JPEG"),
        ("depth", depth_bytes, source.depth_sha256, "PNG"),
    ):
        if type(data) is not bytes or not 0 < len(data) <= 4 * 1024 * 1024:
            raise ValueError("bounded immutable sensor bytes required")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("raw sensor differs from pinned source bytes")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != fmt or image.size != (640, 480):
                raise ValueError("unexpected HO-Cap sensor encoding or size")
            if mode == "rgb":
                if image.mode != "RGB":
                    raise ValueError("RGB JPEG required")
                array = np.asarray(image).copy()
            else:
                if image.mode != "I;16":
                    raise ValueError("16-bit depth PNG required")
                array = np.asarray(image, dtype=np.float32) / 1000.0
        wire = io.BytesIO()
        np.save(wire, array, allow_pickle=False)
        payload = wire.getvalue()
        identity = uuid5(trace_id, source.member(mode))
        modality = SensorModality(mode)
        envelope = ObservationEnvelope(
            metadata=BaseRecordMetadata(
                record_id=identity,
                schema_name="hocap_raw_modality",
                schema_version="1.0.0",
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=arrival_time,
                source_type=SourceType.IMPORT,
                source_id=source.member(mode),
            ),
            identity=ObservationIdentity(
                observation_id=identity,
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
            ),
            sensor=SensorRef(sensor_id=f"hocap:{source.camera_id}:{mode}", modality=modality),
            capture_time=capture_time,
            arrival_time=arrival_time,
            clock_domain="hocap_frame_ordinal_development_clock_not_exposure_timestamp",
            frame_id=f"hocap:{source.sequence_id}:{source.camera_id}",
            payload=PayloadRef(
                payload_id=identity,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            ),
        )
        result = RawModalityObservation(
            envelope.model_dump_json(),
            payload,
            expected_source_sha256,
            "m" if mode == "depth" else None,
        )
        result.envelope()
        decoded.append(result)
    return decoded[0], decoded[1]
