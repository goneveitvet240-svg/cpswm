"""Convert independently pinned simulator sensor bytes to the existing M05 boundary.

This adapter exports only RGB/depth arrays. It does not infer objects, roles or
calibration, and does not grant posterior or long-term-memory authority. The
runtime owner must supply the expected receipt digest from its own capture log;
a digest supplied by the same untrusted archive does not authenticate a source.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid5

from cpswm.contracts.base import BaseRecordMetadata, SourceType, require_aware
from cpswm.data_preflight.capture_prefix import validate_sensor_bytes
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.validation import validate_observation_envelope

_RECEIPT_FIELDS = frozenset(
    {
        "run_id",
        "step_index",
        "request",
        "request_time",
        "received_at",
        "last_action_success",
        "sensor_file",
        "sensor_sha256",
        "depth_unit",
        "status",
    }
)


@dataclass(frozen=True)
class RawModalityObservation:
    """Immutable wire representation, avoiding a mutable envelope/payload split."""

    envelope_json: str
    payload_bytes: bytes
    capture_receipt_sha256: str
    depth_unit: str | None
    archive_sampling_json: str | None = None

    def envelope(self) -> ObservationEnvelope:
        value = ObservationEnvelope.model_validate_json(self.envelope_json)
        validate_observation_envelope(value, payload_bytes=self.payload_bytes)
        if self.archive_sampling_json is not None:
            from cpswm.system.reproducibility import content_sha256

            receipt = _unique_json(self.archive_sampling_json.encode())
            common = {
                "source_url",
                "source_sha256",
                "crop_xywh",
                "time_semantics",
                "payload_sha256",
                "observation_id",
            }
            exact = (
                receipt.get("time_semantics") == "original_frame_author_clock_unverified_exposure"
            )
            timing = (
                {
                    "original_frame_index",
                    "source_frame_count",
                    "source_clock_sha256",
                    "author_clock_seconds",
                    "author_clock_origin_seconds",
                    "media_time_seconds",
                }
                if exact
                else {"sampling_grid_time_seconds", "sampling_fps"}
            )
            crop = receipt.get("crop_xywh")
            time: Any = receipt.get("media_time_seconds" if exact else "sampling_grid_time_seconds")
            if (
                set(receipt) != common | timing
                or value.metadata.source_type is not SourceType.IMPORT
                or value.sensor.modality is not SensorModality.RGB
                or value.clock_domain != "archive-import-acquisition-utc"
                or value.payload is None
                or receipt["source_url"] != value.metadata.source_id
                or not str(receipt["source_url"]).startswith("https://")
                or re.fullmatch(r"[0-9a-f]{64}", str(receipt["source_sha256"])) is None
                or receipt["payload_sha256"] != value.payload.payload_sha256
                or receipt["observation_id"] != str(value.identity.observation_id)
                or type(time) not in (int, float)
                or not math.isfinite(time)
                or time < 0
                or type(crop) is not list
                or len(crop) != 4
                or any(type(x) is not int for x in crop)
                or min(crop[:2]) < 0
                or min(crop[2:]) <= 0
                or content_sha256(receipt) != self.capture_receipt_sha256
            ):
                raise ValueError("archive sampling differs from bound RGB receipt")
            if exact:
                index, count = receipt["original_frame_index"], receipt["source_frame_count"]
                stamp, origin = (
                    receipt["author_clock_seconds"],
                    receipt["author_clock_origin_seconds"],
                )
                if (
                    type(index) is not int
                    or type(count) is not int
                    or not 0 <= index < count
                    or re.fullmatch(r"[0-9a-f]{64}", str(receipt["source_clock_sha256"])) is None
                    or type(stamp) not in (int, float)
                    or type(origin) not in (int, float)
                    or not math.isfinite(stamp)
                    or not math.isfinite(origin)
                    or time != stamp - origin
                ):
                    raise ValueError("invalid original frame index or author clock")
            elif (
                receipt["time_semantics"] != "resampled_grid_not_original_exposure"
                or type(receipt["sampling_fps"]) is not int
                or not 1 <= receipt["sampling_fps"] <= 240
            ):
                raise ValueError("invalid resampled archive clock")
        return value

    def archive_timeline(self) -> tuple[str, float] | None:
        if self.archive_sampling_json is None:
            return None
        from cpswm.system.reproducibility import content_sha256

        self.envelope()  # Validate before promoting sampling metadata to a timeline.
        receipt = _unique_json(self.archive_sampling_json.encode())
        if receipt["time_semantics"] == "original_frame_author_clock_unverified_exposure":
            return (
                content_sha256(
                    (
                        receipt["source_sha256"],
                        receipt["crop_xywh"],
                        receipt["source_clock_sha256"],
                        receipt["time_semantics"],
                    )
                ),
                float(receipt["media_time_seconds"]),
            )
        return (
            content_sha256((receipt["source_sha256"], receipt["crop_xywh"])),
            float(receipt["sampling_grid_time_seconds"]),
        )


def _unique_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate capture receipt field")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    if type(value) is not dict:
        raise ValueError("capture receipt must be an object")
    return cast(dict[str, Any], value)


def adapt_raw_rgbd_capture(
    *,
    receipt_bytes: bytes,
    sensor_bytes: bytes,
    expected_receipt_sha256: str,
    expected_run_id: str,
    household_id: UUID,
    session_id: UUID,
    trace_id: UUID,
    sensor_id: str,
    frame_id: str,
    delivered_at: datetime,
    cutoff: datetime,
) -> tuple[RawModalityObservation, ...]:
    """Bind actual raw bytes to one capture and expose only delivered observations.

    The source timestamp is the SDK return time, NOT the request start time;
    no assertion of hardware exposure-time precision or calibration is made.
    Failed actions may yield valid pixels; their receipt is not action success.
    Caller/session ownership enforces exactly-once dispatch; this pure adapter
    produces stable IDs for replay and delayed delivery of the same capture.
    """
    if (
        not isinstance(expected_receipt_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_receipt_sha256) is None
        or hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha256
    ):
        raise ValueError("capture receipt differs from independently retained digest")
    receipt = _unique_json(receipt_bytes)
    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("unexpected capture receipt fields")
    index = receipt["step_index"]
    if (
        not expected_run_id
        or not sensor_id.strip()
        or not frame_id.strip()
        or receipt["run_id"] != expected_run_id
        or type(index) is not int
        or index < 0
        or type(receipt["last_action_success"]) is not bool
        or receipt["status"] != "RAW_OBSERVATION_CANDIDATE_NOT_METHOD_AUTHORIZATION"
        or receipt["sensor_file"] != f"{index:06d}.npz"
    ):
        raise ValueError("capture identity or receipt contract mismatch")
    if receipt["depth_unit"] not in (None, "m"):
        raise ValueError("only explicit meter depth is supported")
    source_time = require_aware(datetime.fromisoformat(receipt["received_at"]), "SDK return")
    request_time = require_aware(datetime.fromisoformat(receipt["request_time"]), "request time")
    require_aware(delivered_at, "delivery time")
    require_aware(cutoff, "causal cutoff")
    if not request_time <= source_time <= delivered_at <= cutoff:
        raise ValueError("capture is not in the delivered causal prefix")
    if hashlib.sha256(sensor_bytes).hexdigest() != receipt["sensor_sha256"]:
        raise ValueError("sensor bytes differ from captured receipt")
    validate_sensor_bytes(sensor_bytes, receipt["depth_unit"])
    result = []
    with zipfile.ZipFile(io.BytesIO(sensor_bytes)) as archive:
        for name, modality in (
            ("rgb.npy", SensorModality.RGB),
            ("depth.npy", SensorModality.DEPTH),
        ):
            if name not in archive.namelist():
                continue
            payload = archive.read(name)
            identity = uuid5(trace_id, f"{expected_run_id}:{index}:{modality.value}")
            envelope = ObservationEnvelope(
                metadata=BaseRecordMetadata(
                    record_id=identity,
                    schema_name="raw_simulator_modality",
                    schema_version="1.0.0",
                    household_id=household_id,
                    session_id=session_id,
                    trace_id=trace_id,
                    recorded_time=delivered_at,
                    source_type=SourceType.SIMULATION,
                    source_id=expected_run_id,
                ),
                identity=ObservationIdentity(
                    observation_id=identity,
                    household_id=household_id,
                    session_id=session_id,
                    trace_id=trace_id,
                ),
                sensor=SensorRef(sensor_id=f"{sensor_id}:{modality.value}", modality=modality),
                capture_time=source_time,
                arrival_time=delivered_at,
                clock_domain="simulator_sdk_utc_return",
                frame_id=frame_id,
                payload=PayloadRef(
                    payload_id=identity,
                    payload_sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                ),
            )
            validate_observation_envelope(envelope, payload_bytes=payload)
            result.append(
                RawModalityObservation(
                    envelope.model_dump_json(),
                    payload,
                    expected_receipt_sha256,
                    "m" if modality is SensorModality.DEPTH else None,
                )
            )
    return tuple(result)
