"""Canonical content identities shared by the F0 benchmark pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
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
    if isinstance(value, dict):
        return {
            str(_canonical_value(key)): _canonical_value(nested) for key, nested in value.items()
        }
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
