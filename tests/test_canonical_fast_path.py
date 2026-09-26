"""Differential content identities against the pinned, unmodified predecessor."""

import hashlib
import importlib.util
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum
from pathlib import Path
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel

from cpswm.system.reproducibility import canonical_json, content_sha256, content_uuid

REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "docs/reviews/pc_a/canonical_speed_2026-09-26/reference_reproducibility.py"
)
assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == (
    "bdfcaddd9866b7c1f014b079e7732ac04dc27d28a8e0befc4e1798c437fb4506"
)
spec = importlib.util.spec_from_file_location("canonical_before_fast_path", REFERENCE)
assert spec is not None and spec.loader is not None
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)

finite_scalar = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
documents = st.recursive(
    finite_scalar,
    lambda inner: (
        st.lists(inner, max_size=8) | st.dictionaries(st.text(max_size=12), inner, max_size=8)
    ),
    max_leaves=40,
)


@settings(max_examples=400, derandomize=True, deadline=None)
@given(documents)
def test_recursive_json_bytes_hashes_and_uuids_match_predecessor(value):
    assert canonical_json(value) == reference.canonical_json(value)
    assert content_sha256(value) == reference.content_sha256(value)
    assert content_uuid("proposal", value) == reference.content_uuid("proposal", value)


class TextEnum(str, Enum):  # noqa: UP042 - preserve pre-StrEnum subclass precedence
    VALUE = "person"


class IntegerEnum(IntEnum):
    VALUE = 7


class NumberEnum(float, Enum):
    VALUE = -0.0


@dataclass(frozen=True)
class Record:
    value: object


class Model(BaseModel):
    key: UUID
    at: datetime
    zero: float


@pytest.mark.parametrize(
    "value",
    [
        TextEnum.VALUE,
        IntegerEnum.VALUE,
        NumberEnum.VALUE,
        Record({"enum": NumberEnum.VALUE, "set": frozenset({1, "1", -0.0})}),
        Model(key=UUID(int=5), at=datetime(2026, 9, 26, tzinfo=UTC), zero=-0.0),
        {UUID(int=9): (datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=8))), -0.0)},
        {"tuple": (True, 2**130, "人物", {3, 1}), "nested": [{"signed_zero": -0.0}]},
    ],
)
def test_structured_types_and_enum_precedence_match_predecessor(value):
    assert canonical_json(value) == reference.canonical_json(value)
    assert content_sha256(value) == reference.content_sha256(value)


@pytest.mark.parametrize(
    "value",
    [
        {1: "attacker", "1": "trusted"},
        {None: 1, "None": 2},
        {False: 1, "False": 2},
        {-0.0: 1, "0.0": 2},
        float("nan"),
        float("inf"),
        {"inside": [float("-inf")]},
        b"unsupported",
    ],
)
def test_collision_nonfinite_and_unsupported_failures_are_unchanged(value):
    with pytest.raises((TypeError, ValueError)) as before:
        reference.canonical_json(value)
    with pytest.raises(type(before.value)) as after:
        canonical_json(value)
    assert str(after.value) == str(before.value)


def test_negative_zero_and_in_place_mutation_are_not_hidden_by_a_cache():
    payload = {"points": [(-0.0, 0.0)]}
    original = content_sha256(payload)
    assert original == content_sha256({"points": [(0.0, -0.0)]})
    payload["points"][0] = (1.0, 0.0)
    assert content_sha256(payload) != original
    assert content_sha256(payload) == reference.content_sha256(payload)
