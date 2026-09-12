"""Causal loader for raw simulator candidates. Not a calibrated detector adapter."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any


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
        if payload["sensor_file"] != ref.replace(".json", ".npz"):
            raise ValueError("sensor and capture identities disagree")
        sensor = directory / payload["sensor_file"]
        if (
            sensor.is_symlink()
            or hashlib.sha256(sensor.read_bytes()).hexdigest() != payload["sensor_sha256"]
        ):
            raise ValueError("sensor bytes differ from capture receipt")
        selected.append(
            {**payload, "event_tick": row["event_tick"], "received_tick": row["received_tick"]}
        )
    return tuple(
        sorted(selected, key=lambda x: (x["received_tick"], x["event_tick"], x["sensor_file"]))
    )
