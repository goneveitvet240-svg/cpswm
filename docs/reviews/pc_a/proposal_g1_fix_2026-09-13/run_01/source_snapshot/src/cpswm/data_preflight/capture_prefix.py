"""Causal loader for raw simulator candidates. Not a calibrated detector adapter."""

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

MAX_SENSOR_BYTES = 64 * 1024 * 1024


def validate_sensor_bytes(raw: bytes, depth_unit: str | None) -> None:
    """Validate the actual bytes, not a filename. Does not authenticate the camera."""
    if len(raw) > MAX_SENSOR_BYTES:
        raise ValueError("sensor archive exceeds byte limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            expected = {"rgb.npy"} if depth_unit is None else {"rgb.npy", "depth.npy"}
            if len(names) != len(expected) or set(names) != expected:
                raise ValueError("sensor archive must contain exactly the allowed arrays")
            if sum(info.file_size for info in archive.infolist()) > MAX_SENSOR_BYTES:
                raise ValueError("expanded sensor archive exceeds byte limit")
        with np.load(io.BytesIO(raw), allow_pickle=False) as arrays:
            rgb = arrays["rgb"]
            if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3 or not rgb.size:
                raise ValueError("invalid RGB sensor array")
            if depth_unit is not None:
                depth = arrays["depth"]
                if (
                    depth.dtype.kind != "f"
                    or depth.shape != rgb.shape[:2]
                    or not np.isfinite(depth).all()
                    or (depth < 0).any()
                ):
                    raise ValueError("invalid depth sensor array")
    except (OSError, EOFError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError("invalid sensor archive") from error


def read_sensor_snapshot(path: Path, *, expected_sha256: str, depth_unit: str | None) -> bytes:
    """Return immutable validated bytes. Caller must independently trust expected hash.

    Consumers must use these bytes, not reopen the mutable path after validation.
    """
    if depth_unit is not None and (type(depth_unit) is not str or depth_unit != "m"):
        raise ValueError("only explicitly calibrated meter depth or absent depth supported")
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("invalid trusted sensor digest")
    if path.is_symlink() or path.stat().st_size > MAX_SENSOR_BYTES:
        raise ValueError("invalid sensor path or size")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SENSOR_BYTES + 1)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("sensor bytes differ from capture receipt")
    validate_sensor_bytes(raw, depth_unit)
    return raw


def released_capture_prefix(directory: Path, cutoff_tick: int) -> tuple[dict[str, Any], ...]:
    """Load only delivered images, never expose the full journal or evaluator metadata.

    Files on disk are offline archives, NOT an access-control boundary. The method
    must be given this projection, not a mount of the full capture directory.
    """
    if type(cutoff_tick) is not int or cutoff_tick < 0:
        raise ValueError("nonnegative integer causal cutoff required")
    journal = json.loads((directory / "release_journal.json").read_text())
    selected = []
    seen: set[str] = set()
    for row in journal:
        if set(row) != {"capture_ref", "event_tick", "received_tick"}:
            raise ValueError("unexpected release journal fields")
        if any(type(row[key]) is not int for key in ("event_tick", "received_tick")):
            raise ValueError("integer event/arrival clocks required")
        if not 0 <= row["event_tick"] <= row["received_tick"]:
            raise ValueError("receipt precedes occurrence")
        if row["received_tick"] > cutoff_tick:
            continue
        ref = row["capture_ref"]
        if not isinstance(ref, str) or re.fullmatch(r"[0-9]{6}\.json", ref) is None:
            raise ValueError("invalid capture reference")
        if ref in seen:
            raise ValueError("duplicate released capture cannot become independent evidence")
        seen.add(ref)
        path = directory / ref
        if path.is_symlink():
            raise ValueError("capture symlinks forbidden")
        payload = json.loads(path.read_text())
        if set(payload) != {"sensor_file", "sensor_sha256", "depth_unit", "status"}:
            raise ValueError("candidate must contain only raw sensor fields")
        if (
            type(payload["status"]) is not str
            or payload["status"] != "raw_candidate_requires_visible_evidence_adapter"
        ):
            raise ValueError("candidate status is not an authorized raw-sensor enum")
        if payload["sensor_file"] != ref.replace(".json", ".npz"):
            raise ValueError("sensor and capture identities disagree")
        sensor = directory / payload["sensor_file"]
        read_sensor_snapshot(
            sensor, expected_sha256=payload["sensor_sha256"], depth_unit=payload["depth_unit"]
        )
        selected.append(
            {**payload, "event_tick": row["event_tick"], "received_tick": row["received_tick"]}
        )
    return tuple(
        sorted(selected, key=lambda x: (x["received_tick"], x["event_tick"], x["sensor_file"]))
    )
