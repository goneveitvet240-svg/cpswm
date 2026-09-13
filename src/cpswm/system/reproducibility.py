"""Canonical content identities shared by the F0 benchmark pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    # IEEE negative zero is numerically and semantically equal to positive
    # zero for these contracts.  Normalizing it prevents content identities
    # and de-duplication keys from treating a sign-bit-only change as evidence.
    if isinstance(value, float) and value == 0.0:
        return 0.0
    if isinstance(value, (set, frozenset)):
        # Python's hash seed changes set repr/order between processes. Cause-set
        # keys must retain one identity across a durable runtime restart.
        items = [_canonical_value(item) for item in value]
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, allow_nan=False))
        return {"__" + type(value).__name__ + "__": items}
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(_canonical_value(key))
            if normalized_key in normalized:
                raise ValueError(
                    "mapping contains keys that collide after canonical JSON normalization"
                )
            normalized[normalized_key] = _canonical_value(nested)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize semantically equivalent F0 inputs in one stable form."""

    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def content_uuid(kind: str, value: Any) -> UUID:
    return uuid5(NAMESPACE_URL, f"cpswm:{kind}:{content_sha256(value)}")
