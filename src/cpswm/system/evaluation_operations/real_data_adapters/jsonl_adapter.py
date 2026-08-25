"""A generic JSONL adapter -- the first real-data entry point.

Everything the controlled scenarios provide for free, a real export fails to:
lines arrive unordered, event ids repeat, timestamps lose their offset, fields
go missing, and "where was it?" is sometimes answered with ``null``.

The adapter is the only place allowed to know that.  Its governing rule is
**report, never quietly repair**: a line it cannot trust is rejected with its
line number and a reason, and every repair it *does* perform (sorting, dropping
an exact duplicate, localizing a naive timestamp) is written into the manifest's
``preprocessing`` map.  A repair that is not in the manifest is an untracked
experiment, and two runs of "the same data" would no longer be the same data.

Truth never travels with the events.  Truth lives in its own file; an event line
carrying ``expected_location`` or any other truth-bearing key is rejected even
though it would parse, because a record type with no truth field is only half
the guarantee.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from enum import StrEnum
from math import isfinite
from pathlib import Path

from ..dataset_adapters import DatasetAdapter
from ..project_one_dataset import (
    FORBIDDEN_RECORD_FIELDS,
    UNKNOWN_LOCATION,
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
)

__all__ = [
    "JSONL_ADAPTER_VERSION",
    "REQUIRED_EVENT_FIELDS",
    "UNKNOWN_LOCATION",
    "JSONLAdapter",
    "JSONLLoadReport",
    "JSONLRejection",
    "UnknownLocationPolicy",
]

JSONL_ADAPTER_VERSION = "0.1"

#: Every field the project-one record contract needs.  None of them is
#: defaulted: a guessed ``observation_quality`` or a guessed ``actor_id`` would
#: silently become evidence.
REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
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
)

#: Explicit stand-in for "the log says it does not know".  Distinct from every
#: real location, and only ever produced under
#: :attr:`UnknownLocationPolicy.SENTINEL`.
#: Spellings real exports use for "no idea".  Matched case-insensitively after
#: stripping, so ``"  Unknown "`` is caught too.
_UNKNOWN_TOKENS = frozenset({"", "unknown", "none", "null", "n/a", "na", "?", "-"})

_MAX_RAW_ECHO = 120


class UnknownLocationPolicy(StrEnum):
    """What to do with an event whose location the log does not know."""

    #: Drop the line and report it.  The default, because an unknown location is
    #: not an observation and treating it as one invents evidence.
    REJECT = "reject"
    #: Keep the line with :data:`UNKNOWN_LOCATION`.  A modelling choice -- the
    #: candidate set gains a member that means "unobserved" -- so it must be
    #: asked for by name.
    SENTINEL = "sentinel"


@dataclass(frozen=True, slots=True)
class JSONLRejection:
    """One line the adapter refused, with enough context to go fix the export."""

    line_number: int
    reason: str
    raw: str


@dataclass(frozen=True, slots=True)
class JSONLLoadReport:
    """Line-level accounting.  ``accepted + duplicates + malformed == total``."""

    total_lines: int
    accepted: int
    duplicates_dropped: int
    malformed: tuple[JSONLRejection, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "total_lines": self.total_lines,
            "accepted": self.accepted,
            "duplicates_dropped": self.duplicates_dropped,
            "malformed": [
                {"line_number": item.line_number, "reason": item.reason, "raw": item.raw}
                for item in self.malformed
            ],
        }


def _format_zone(zone: tzinfo) -> str:
    offset = zone.utcoffset(datetime(2026, 1, 1)) or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


class JSONLAdapter(DatasetAdapter):
    """Load newline-delimited JSON events into the project-one contract."""

    source = "jsonl"
    source_version = JSONL_ADAPTER_VERSION

    def __init__(
        self,
        path: Path | str,
        *,
        truth_path: Path | str | None = None,
        naive_timestamp_zone: tzinfo | None = None,
        unknown_location: UnknownLocationPolicy = UnknownLocationPolicy.REJECT,
    ) -> None:
        self.path = Path(path)
        self.truth_path = Path(truth_path) if truth_path is not None else None
        self.naive_timestamp_zone = naive_timestamp_zone
        self.unknown_location = unknown_location
        self._report = JSONLLoadReport(
            total_lines=0, accepted=0, duplicates_dropped=0, malformed=()
        )

    @property
    def report(self) -> JSONLLoadReport:
        """Line-level accounting for the most recent :meth:`load`."""

        return self._report

    # -- parsing -----------------------------------------------------------

    def _parse_timestamp(self, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("timestamp must be an ISO-8601 string")
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is not None and stamp.tzinfo.utcoffset(stamp) is not None:
            return stamp
        if self.naive_timestamp_zone is None:
            raise ValueError(
                "timestamp has no timezone; pass naive_timestamp_zone to declare one "
                "rather than letting the adapter guess"
            )
        return stamp.replace(tzinfo=self.naive_timestamp_zone)

    def _parse_location(self, value: object) -> str:
        if value is None or (isinstance(value, str) and value.strip().lower() in _UNKNOWN_TOKENS):
            if self.unknown_location is UnknownLocationPolicy.SENTINEL:
                return UNKNOWN_LOCATION
            raise ValueError(
                f"unknown location {value!r}; pass unknown_location=SENTINEL to keep it "
                "as an explicit unobserved marker"
            )
        if not isinstance(value, str):
            raise ValueError("observed_location must be a string")
        return value

    def _record_from(self, payload: Mapping[str, object]) -> ProjectOneDatasetRecord:
        leaked = sorted(FORBIDDEN_RECORD_FIELDS.intersection(payload))
        if leaked:
            raise ValueError(
                f"event line carries truth field(s) {leaked}; truth must arrive through "
                "its own file so it cannot reach a method by accident"
            )
        missing = [name for name in REQUIRED_EVENT_FIELDS if name not in payload]
        if missing:
            raise ValueError(f"missing required field(s) {missing}")

        context_value = payload["context_value"]
        quality = payload["observation_quality"]
        if not isinstance(context_value, int | float) or isinstance(context_value, bool):
            raise ValueError("context_value must be a number")
        if not isinstance(quality, int | float) or isinstance(quality, bool):
            raise ValueError("observation_quality must be a number")
        if not isfinite(float(context_value)):
            raise ValueError("context_value must be finite")

        return ProjectOneDatasetRecord(
            stream_id=str(payload["stream_id"]),
            event_id=str(payload["event_id"]),
            subject_id=str(payload["subject_id"]),
            household_id=str(payload["household_id"]),
            object_id=str(payload["object_id"]),
            actor_id=str(payload["actor_id"]),
            timestamp=self._parse_timestamp(payload["timestamp"]),
            context_key=str(payload["context_key"]),
            context_value=float(context_value),
            observed_location=self._parse_location(payload["observed_location"]),
            observation_quality=float(quality),
        )

    def _read_events(self) -> tuple[list[ProjectOneDatasetRecord], JSONLLoadReport]:
        records: list[ProjectOneDatasetRecord] = []
        by_event: dict[str, ProjectOneDatasetRecord] = {}
        rejections: list[JSONLRejection] = []
        duplicates = 0
        total = 0

        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                total += 1
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    rejections.append(
                        JSONLRejection(
                            line_number,
                            f"not valid JSON: {error.msg}",
                            line[:_MAX_RAW_ECHO].strip(),
                        )
                    )
                    continue
                if not isinstance(payload, dict):
                    rejections.append(
                        JSONLRejection(
                            line_number,
                            "line is not a JSON object",
                            line[:_MAX_RAW_ECHO].strip(),
                        )
                    )
                    continue
                try:
                    record = self._record_from(payload)
                except ValueError as error:
                    rejections.append(
                        JSONLRejection(line_number, str(error), line[:_MAX_RAW_ECHO].strip())
                    )
                    continue

                seen = by_event.get(record.event_id)
                if seen is not None:
                    if seen != record:
                        # Two different observations claiming one id means the
                        # exporter is broken.  Picking one would be a guess.
                        raise ValueError(
                            f"conflicting duplicate for event {record.event_id!r} on line "
                            f"{line_number}: the same id carries two different observations"
                        )
                    duplicates += 1
                    continue
                by_event[record.event_id] = record
                records.append(record)

        report = JSONLLoadReport(
            total_lines=total,
            accepted=len(records),
            duplicates_dropped=duplicates,
            malformed=tuple(rejections),
        )
        if not records:
            raise ValueError(
                f"no usable rows in {self.path}: {total} line(s) read, "
                f"{len(rejections)} rejected, {duplicates} duplicate(s)"
            )
        return records, report

    def _read_truths(self) -> list[ProjectOneGroundTruth]:
        if self.truth_path is None:
            return []
        truths: list[ProjectOneGroundTruth] = []
        with self.truth_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"truth line {line_number} is not a JSON object")
                truths.append(
                    ProjectOneGroundTruth(
                        stream_id=str(payload["stream_id"]),
                        event_id=str(payload["event_id"]),
                        expected_location=payload.get("expected_location"),
                        true_regime_id=payload.get("true_regime_id"),
                        true_change_point=bool(payload.get("true_change_point", False)),
                        true_change_cause=payload.get("true_change_cause"),
                    )
                )
        return truths

    def discover_stream_id(self) -> str:
        """The ``stream_id`` the file itself declares.

        A caller has to name the stream before loading it, and deriving that
        name from the filename would silently disagree with the records'
        own field -- which the stream constructor then rejects with a message
        about a manifest, several layers from the actual cause.  Reading it
        here also catches a file that holds more than one stream, which needs a
        split rather than a guess.
        """

        found: list[str] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and isinstance(payload.get("stream_id"), str):
                    name = payload["stream_id"].strip()
                    if name and name not in found:
                        found.append(name)
        if not found:
            raise ValueError(f"no stream_id found in {self.path}")
        if len(found) > 1:
            raise ValueError(
                f"{self.path} holds {len(found)} streams {sorted(found)}; split it before "
                "loading, or the manifest would describe only one of them"
            )
        return found[0]

    # -- adapter surface ---------------------------------------------------

    def _emit(self) -> tuple[Sequence[ProjectOneDatasetRecord], Sequence[ProjectOneGroundTruth]]:
        records, report = self._read_events()
        self._report = report
        return records, self._read_truths()

    def preprocessing(self) -> Mapping[str, str]:
        steps: dict[str, str] = {
            "adapter": "jsonl",
            "sorted_by": "timestamp",
            "duplicates_dropped": str(self._report.duplicates_dropped),
            "malformed_rejected": str(len(self._report.malformed)),
            "unknown_location": self.unknown_location.value,
        }
        if self.naive_timestamp_zone is not None:
            steps["naive_timestamp_zone"] = _format_zone(self.naive_timestamp_zone)
        if self.truth_path is not None:
            steps["truth_source"] = self.truth_path.name
        return steps
