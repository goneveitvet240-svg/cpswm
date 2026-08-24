"""The first real-data entry point: a generic JSONL event adapter.

Everything the controlled scenarios get for free -- ordering, unique event ids,
timezone-aware timestamps, a closed location vocabulary -- a real log fails to
provide.  The adapter is the single place allowed to know that, and it has to
fail loudly rather than quietly repair, because a quiet repair is an
unrecorded preprocessing step.

Five hazards are pinned here:

* **ordering** -- lines arrive in whatever order the exporter wrote them;
* **duplicates** -- the same ``event_id`` appearing twice must not silently
  double-count, and must not crash the run either;
* **timezones** -- a naive timestamp is ambiguous, so it is either rejected or
  localized under an explicitly declared zone, never guessed;
* **missing fields** -- a line missing a required field is rejected with its
  line number, not defaulted;
* **unknown locations** -- ``null``/``""``/``"unknown"`` is a real value in real
  logs and means "we do not know", which is not the same as a location.

And one structural rule: **truth never travels with the events.**  A line
carrying ``expected_location`` or any other truth field is rejected outright,
even though it would parse.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.real_data_adapters import (
    UNKNOWN_LOCATION,
    JSONLAdapter,
    UnknownLocationPolicy,
)

EPOCH = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


def _row(index: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "stream_id": "home-a",
        "event_id": f"e{index:03d}",
        "subject_id": "alice",
        "household_id": "h1",
        "object_id": "cup",
        "actor_id": "alice",
        "timestamp": (EPOCH + timedelta(hours=index)).isoformat(),
        "context_key": "morning",
        "context_value": 0.0,
        "observed_location": "table" if index % 2 == 0 else "sink",
        "observation_quality": 0.9,
    }
    row.update(overrides)
    return row


def _write(tmp_path: Path, rows, name: str = "events.jsonl") -> Path:
    path = tmp_path / name
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_clean_file_becomes_a_validated_stream(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(index) for index in range(6)])
    stream, truth = JSONLAdapter(path).load(stream_id="home-a", split="pilot")

    assert len(stream) == 6
    assert stream.manifest.source == "jsonl"
    assert stream.manifest.record_count == 6
    assert stream.manifest.content_hash
    assert len(truth) == 0


def test_out_of_order_lines_are_sorted_by_timestamp(tmp_path: Path) -> None:
    rows = [_row(index) for index in (4, 0, 5, 2, 1, 3)]
    path = _write(tmp_path, rows)
    stream, _truth = JSONLAdapter(path).load(stream_id="home-a", split="pilot")

    stamps = [record.timestamp for record in stream.records]
    assert stamps == sorted(stamps)
    assert [record.event_id for record in stream.records] == [f"e{i:03d}" for i in range(6)]


def test_the_manifest_records_the_preprocessing_that_was_applied(tmp_path: Path) -> None:
    """A repair that is not in the manifest is an untracked experiment."""

    rows = [_row(index) for index in range(4)] + [_row(1)]
    path = _write(tmp_path, rows)
    stream, _truth = JSONLAdapter(path).load(stream_id="home-a", split="pilot")

    preprocessing = dict(stream.manifest.preprocessing)
    assert preprocessing["sorted_by"] == "timestamp"
    assert preprocessing["duplicates_dropped"] == "1"


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_an_exact_duplicate_event_id_is_dropped_once(tmp_path: Path) -> None:
    rows = [_row(index) for index in range(4)]
    rows.append(_row(2))
    path = _write(tmp_path, rows)
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 4
    assert adapter.report.duplicates_dropped == 1


def test_a_conflicting_duplicate_is_a_hard_error(tmp_path: Path) -> None:
    """Same id, different content: the exporter is broken and we must not pick."""

    rows = [_row(index) for index in range(4)]
    rows.append(_row(2, observed_location="balcony"))
    path = _write(tmp_path, rows)
    with pytest.raises(ValueError, match="conflicting"):
        JSONLAdapter(path).load(stream_id="home-a", split="pilot")


# ---------------------------------------------------------------------------
# Timezones
# ---------------------------------------------------------------------------


def test_a_naive_timestamp_is_rejected_by_default(tmp_path: Path) -> None:
    rows = [_row(0), _row(1, timestamp="2026-06-01T10:00:00")]
    path = _write(tmp_path, rows)
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 1
    assert adapter.report.malformed[0].line_number == 2
    assert "timezone" in adapter.report.malformed[0].reason


def test_a_declared_default_timezone_localizes_naive_timestamps(tmp_path: Path) -> None:
    rows = [_row(0), _row(1, timestamp="2026-06-01T10:00:00")]
    path = _write(tmp_path, rows)
    shanghai = timezone(timedelta(hours=8))
    adapter = JSONLAdapter(path, naive_timestamp_zone=shanghai)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 2
    localized = next(item for item in stream.records if item.event_id == "e001")
    assert localized.timestamp.utcoffset() == timedelta(hours=8)
    assert dict(stream.manifest.preprocessing)["naive_timestamp_zone"] == "UTC+08:00"


def test_offset_timestamps_are_compared_on_the_absolute_instant(tmp_path: Path) -> None:
    """``12:00+08:00`` precedes ``09:00Z``; sorting on the local wall clock inverts them."""

    rows = [
        _row(0, event_id="later", timestamp="2026-06-01T09:00:00+00:00"),
        _row(1, event_id="earlier", timestamp="2026-06-01T12:00:00+08:00"),
    ]
    path = _write(tmp_path, rows)
    stream, _truth = JSONLAdapter(path).load(stream_id="home-a", split="pilot")

    assert [record.event_id for record in stream.records] == ["earlier", "later"]


# ---------------------------------------------------------------------------
# Missing and malformed fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "stream_id",
        "event_id",
        "subject_id",
        "household_id",
        "object_id",
        "actor_id",
        "timestamp",
        "context_key",
        "context_value",
        "observed_location",
        "observation_quality",
    ],
)
def test_every_required_field_is_actually_required(tmp_path: Path, field: str) -> None:
    row = _row(1)
    del row[field]
    path = _write(tmp_path, [_row(0), row, _row(2)])
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 2
    assert len(adapter.report.malformed) == 1
    assert field in adapter.report.malformed[0].reason


def test_a_field_is_never_defaulted_into_existence(tmp_path: Path) -> None:
    row = _row(1)
    del row["observation_quality"]
    path = _write(tmp_path, [_row(0), row])
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")
    assert [record.event_id for record in stream.records] == ["e000"]


def test_unparseable_json_is_reported_with_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(_row(0)) + "\n" + "{not json\n" + json.dumps(_row(2)) + "\n",
        encoding="utf-8",
    )
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 2
    assert adapter.report.malformed[0].line_number == 2


def test_blank_lines_are_skipped_without_being_called_malformed(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(_row(0)) + "\n\n   \n" + json.dumps(_row(1)) + "\n", encoding="utf-8"
    )
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 2
    assert adapter.report.malformed == ()


def test_an_out_of_range_observation_quality_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(0), _row(1, observation_quality=1.4)])
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")
    assert len(stream) == 1
    assert "observation_quality" in adapter.report.malformed[0].reason


# ---------------------------------------------------------------------------
# Unknown locations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   ", "unknown", "UNKNOWN"])
def test_unknown_locations_are_rejected_by_default(tmp_path: Path, value) -> None:
    path = _write(tmp_path, [_row(0), _row(1, observed_location=value)])
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 1
    assert "unknown location" in adapter.report.malformed[0].reason.lower()


def test_unknown_locations_can_be_kept_as_an_explicit_sentinel(tmp_path: Path) -> None:
    """Keeping them is a modelling choice, so it has to be asked for by name."""

    path = _write(tmp_path, [_row(0), _row(1, observed_location=None)])
    adapter = JSONLAdapter(path, unknown_location=UnknownLocationPolicy.SENTINEL)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 2
    assert stream.records[1].observed_location == UNKNOWN_LOCATION
    assert dict(stream.manifest.preprocessing)["unknown_location"] == "sentinel"


# ---------------------------------------------------------------------------
# Truth isolation
# ---------------------------------------------------------------------------


def test_a_truth_field_inside_the_event_file_is_rejected(tmp_path: Path) -> None:
    """Structural: truth must arrive through its own file or not at all."""

    path = _write(tmp_path, [_row(0), _row(1, expected_location="table")])
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")

    assert len(stream) == 1
    assert "expected_location" in adapter.report.malformed[0].reason


def test_truth_is_read_from_its_own_file(tmp_path: Path) -> None:
    events = _write(tmp_path, [_row(index) for index in range(4)])
    truth_rows = [
        {
            "stream_id": "home-a",
            "event_id": "e002",
            "expected_location": "table",
            "true_change_point": True,
            "true_change_cause": "owner_habit",
        }
    ]
    truth_path = _write(tmp_path, truth_rows, name="truth.jsonl")

    stream, truth = JSONLAdapter(events, truth_path=truth_path).load(
        stream_id="home-a", split="pilot"
    )
    assert len(stream) == 4
    assert len(truth) == 1
    entry = truth.get("e002")
    assert entry is not None
    assert entry.expected_location == "table"
    assert entry.true_change_point is True


def test_truth_for_an_unknown_event_is_a_hard_error(tmp_path: Path) -> None:
    events = _write(tmp_path, [_row(index) for index in range(2)])
    truth_path = _write(tmp_path, [{"stream_id": "home-a", "event_id": "nope"}], name="truth.jsonl")
    with pytest.raises(ValueError, match="unknown event"):
        JSONLAdapter(events, truth_path=truth_path).load(stream_id="home-a", split="pilot")


def test_no_record_field_can_ever_carry_truth(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(index) for index in range(3)])
    stream, _truth = JSONLAdapter(path).load(stream_id="home-a", split="pilot")
    fields = set(vars(type(stream.records[0])).get("__slots__", ()))
    assert "expected_location" not in fields
    assert "true_change_point" not in fields


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_the_report_accounts_for_every_line(tmp_path: Path) -> None:
    rows = [_row(0), _row(1), _row(1), _row(2, observation_quality=9.0)]
    path = _write(tmp_path, rows)
    adapter = JSONLAdapter(path)
    stream, _truth = adapter.load(stream_id="home-a", split="pilot")
    report = adapter.report

    assert report.total_lines == 4
    assert report.accepted == len(stream)
    assert report.accepted + report.duplicates_dropped + len(report.malformed) == 4


def test_a_file_with_no_usable_rows_fails_loudly(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(0, observation_quality=9.0)])
    with pytest.raises(ValueError, match="no usable"):
        JSONLAdapter(path).load(stream_id="home-a", split="pilot")


# ---------------------------------------------------------------------------
# Naming the stream
# ---------------------------------------------------------------------------


def test_the_stream_id_is_read_from_the_file_not_the_filename(tmp_path: Path) -> None:
    """A filename-derived id disagrees with the records and fails three layers down."""

    path = _write(tmp_path, [_row(index) for index in range(3)], name="whatever.jsonl")
    adapter = JSONLAdapter(path)
    assert adapter.discover_stream_id() == "home-a"
    stream, _truth = adapter.load(stream_id=adapter.discover_stream_id(), split="pilot")
    assert stream.manifest.stream_id == "home-a"


def test_a_file_holding_two_streams_is_refused(tmp_path: Path) -> None:
    rows = [_row(0), _row(1, stream_id="home-b")]
    path = _write(tmp_path, rows)
    with pytest.raises(ValueError, match="holds 2 streams"):
        JSONLAdapter(path).discover_stream_id()


def test_discovery_ignores_unparseable_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("{broken\n" + json.dumps(_row(0)) + "\n", encoding="utf-8")
    assert JSONLAdapter(path).discover_stream_id() == "home-a"
