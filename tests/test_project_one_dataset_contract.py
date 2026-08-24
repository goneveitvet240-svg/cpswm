"""阶段 2 acceptance: one adapter is all a new data source costs.

完成标准: "任意数据集只需要实现 adapter" (no core change).  The last
test in this file demonstrates that literally: a brand-new source is added by
subclassing :class:`DatasetAdapter`, and the untouched chain arm consumes it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.dataset_adapters import DatasetAdapter, InMemoryAdapter
from cpswm.system.evaluation_operations.project_one_dataset import (
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
    build_manifest,
)
from cpswm.system.evaluation_operations.project_one_methods import CoreHabitChainMethod
from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneProtocolConfig
from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner

EPOCH = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
LOCATIONS = ("kitchen", "study", "porch")


def _record(
    index: int, *, location: str = "kitchen", **overrides: object
) -> ProjectOneDatasetRecord:
    base = {
        "stream_id": "unit",
        "event_id": f"unit-{index:03d}",
        "subject_id": "owner",
        "household_id": "h1",
        "object_id": "mug",
        "actor_id": "owner",
        "timestamp": EPOCH + timedelta(days=index),
        "context_key": "weekday",
        "context_value": 0.0,
        "observed_location": location,
        "observation_quality": 0.9,
    }
    base.update(overrides)
    return ProjectOneDatasetRecord(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Record validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("observation_quality", 1.4, "observation_quality"),
        ("observation_quality", -0.1, "observation_quality"),
        ("context_value", float("nan"), "context_value"),
        ("stream_id", "  ", "stream_id"),
        ("object_id", "", "object_id"),
    ],
)
def test_a_record_rejects_an_out_of_range_field(
    field_name: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _record(0, **{field_name: value})


def test_a_record_rejects_a_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _record(0, timestamp=datetime(2026, 5, 1, 9, 0))


# ---------------------------------------------------------------------------
# Stream validation: unique ids, monotone time, manifest agreement
# ---------------------------------------------------------------------------


def test_a_stream_rejects_a_duplicate_event_id() -> None:
    records = [_record(0), _record(0)]
    manifest = build_manifest(
        stream_id="unit", source="test", source_version="0", split="unit", records=records
    )
    with pytest.raises(ValueError, match="duplicate event id"):
        ProjectOneStream(manifest=manifest, records=tuple(records))


def test_a_stream_rejects_a_backwards_timestamp() -> None:
    records = [_record(1), _record(0)]
    manifest = build_manifest(
        stream_id="unit", source="test", source_version="0", split="unit", records=records
    )
    with pytest.raises(ValueError, match="non-decreasing"):
        ProjectOneStream(manifest=manifest, records=tuple(records))


def test_a_stream_rejects_a_record_from_another_stream() -> None:
    records = [_record(0), _record(1, stream_id="other")]
    manifest = build_manifest(
        stream_id="unit", source="test", source_version="0", split="unit", records=records
    )
    with pytest.raises(ValueError, match="stream_id"):
        ProjectOneStream(manifest=manifest, records=tuple(records))


def test_a_manifest_hash_changes_when_any_visible_field_changes() -> None:
    original = [_record(0), _record(1)]
    modified = [_record(0), _record(1, location="study")]
    left = build_manifest(
        stream_id="unit", source="t", source_version="0", split="unit", records=original
    )
    right = build_manifest(
        stream_id="unit", source="t", source_version="0", split="unit", records=modified
    )
    assert left.content_hash != right.content_hash


def test_a_manifest_records_provenance_and_preprocessing() -> None:
    stream, _ = InMemoryAdapter(
        [_record(0), _record(1)],
        source="my-source",
        source_version="2.1",
        preprocessing={"dedup": "by-event-id"},
    ).load(stream_id="unit", split="train")
    assert stream.manifest.source == "my-source"
    assert stream.manifest.source_version == "2.1"
    assert stream.manifest.split == "train"
    assert stream.manifest.preprocessing["dedup"] == "by-event-id"
    assert stream.manifest.record_count == 2


# ---------------------------------------------------------------------------
# Truth isolation
# ---------------------------------------------------------------------------


def test_a_truth_set_rejects_a_duplicate_event() -> None:
    truth = ProjectOneGroundTruth(stream_id="unit", event_id="unit-000")
    with pytest.raises(ValueError, match="duplicate truth"):
        ProjectOneTruthSet("unit", [truth, truth])


def test_a_truth_set_rejects_a_foreign_stream() -> None:
    with pytest.raises(ValueError, match="does not match"):
        ProjectOneTruthSet("unit", [ProjectOneGroundTruth(stream_id="other", event_id="x")])


def test_an_adapter_rejects_truth_for_an_unknown_event() -> None:
    adapter = InMemoryAdapter(
        [_record(0)],
        [ProjectOneGroundTruth(stream_id="unit", event_id="unit-999")],
    )
    with pytest.raises(ValueError, match="unknown event"):
        adapter.load(stream_id="unit", split="unit")


def test_a_truth_set_is_not_iterable_as_a_mapping() -> None:
    """A method that somehow held one still cannot enumerate the labels."""

    truth = ProjectOneTruthSet("unit", [ProjectOneGroundTruth(stream_id="unit", event_id="e")])
    assert not hasattr(truth, "items")
    assert not hasattr(truth, "keys")
    assert not hasattr(truth, "__iter__")
    assert truth.get("e") is not None
    assert truth.get("missing") is None


def test_unknown_truth_stays_unknown() -> None:
    """``None`` must survive; a missing label is never coerced into a value."""

    truth = ProjectOneGroundTruth(stream_id="unit", event_id="e")
    assert truth.expected_location is None
    assert truth.true_regime_id is None
    assert truth.true_change_cause is None
    assert truth.true_change_point is False


# ---------------------------------------------------------------------------
# Adapter ordering
# ---------------------------------------------------------------------------


def test_an_adapter_sorts_an_unordered_source() -> None:
    stream, _ = InMemoryAdapter([_record(2), _record(0), _record(1)]).load(
        stream_id="unit", split="unit"
    )
    assert [record.event_id for record in stream] == ["unit-000", "unit-001", "unit-002"]


def test_a_stream_reports_its_locations_in_first_observed_order() -> None:
    stream, _ = InMemoryAdapter(
        [_record(0, location="porch"), _record(1, location="kitchen"), _record(2, location="porch")]
    ).load(stream_id="unit", split="unit")
    assert stream.locations() == ("porch", "kitchen")


# ---------------------------------------------------------------------------
# 完成标准: a new source costs one adapter and no core change
# ---------------------------------------------------------------------------


class _FakeSmartHomeLogAdapter(DatasetAdapter):
    """A source with its own quirks — arbitrary order, its own vocabulary."""

    source = "fake-smart-home-log"
    source_version = "9.9"

    def __init__(self, rows: Sequence[tuple[int, str]]) -> None:
        self._rows = tuple(rows)

    def preprocessing(self) -> dict[str, str]:
        return {"unit": "days", "location_vocabulary": "native"}

    def _emit(
        self,
    ) -> tuple[Sequence[ProjectOneDatasetRecord], Sequence[ProjectOneGroundTruth]]:
        records = [
            _record(day, location=location, stream_id="smart-home", event_id=f"sh-{day:03d}")
            for day, location in self._rows
        ]
        truths = [
            ProjectOneGroundTruth(
                stream_id="smart-home",
                event_id=f"sh-{day:03d}",
                expected_location="kitchen",
            )
            for day, _ in self._rows
        ]
        return records, truths


def test_a_new_source_needs_only_an_adapter() -> None:
    rows = [(index, "kitchen" if index % 4 else "study") for index in reversed(range(16))]
    stream, truth = _FakeSmartHomeLogAdapter(rows).load(stream_id="smart-home", split="dev")

    assert stream.manifest.source == "fake-smart-home-log"
    assert [record.event_id for record in stream] == sorted(record.event_id for record in stream)
    assert len(truth) == len(stream)

    arm = CoreHabitChainMethod(
        name="full",
        locations=LOCATIONS,
        owner_id="owner",
        household_id="h1",
        object_id="mug",
        config=replace(ProjectOneProtocolConfig()),
    )
    result = ProjectOneRunner().run_arm(arm, stream, truth)
    assert result.failure is None
    assert len(result.predictions) == len(stream)
