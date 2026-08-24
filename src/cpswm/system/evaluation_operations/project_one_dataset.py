"""Unified project-one data contract (阶段 2).

Synthetic scenarios, semi-synthetic injections, real household logs and
LLM-extracted events all converge on one record type before they reach any
project-one method.  A new data source therefore costs one adapter, never a
change to the decision chain.

Label isolation is structural, not a convention:
:class:`ProjectOneDatasetRecord` has no truth-bearing field, and the truth for a
stream lives in a separate :class:`ProjectOneTruthSet` that the evaluation
runner holds and never hands to a method.  ``tests/
test_project_one_dataset_contract.py`` asserts the separation by inspecting the
record's field names, so a future truth field cannot be added by accident.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite

from cpswm.system.reproducibility import content_sha256

__all__ = [
    "ANOMALY_CAUSES",
    "DATASET_CONTRACT_VERSION",
    "REGIME_CAUSES",
    "ChangeCause",
    "ProjectOneDatasetManifest",
    "ProjectOneDatasetRecord",
    "ProjectOneGroundTruth",
    "ProjectOneStream",
    "ProjectOneTruthSet",
    "build_manifest",
]


class ChangeCause(StrEnum):
    """Why the evaluator says an event looks the way it does.

    One vocabulary, shared by every truth producer.  Before this existed there
    were three: the controlled scenarios said ``transient``, the semi-synthetic
    injector said ``planted_one_shot_disturbance``, and the metric module
    recognised only ``{"transient", "guest"}``.  The injector's disturbances
    were therefore invisible to scoring, and ``anomaly_detection_rate`` on any
    semi-synthetic stream was structurally zero -- not a low reading, an
    arithmetic certainty.

    :class:`ProjectOneGroundTruth` validates against this enum, so a future
    producer cannot reintroduce a private spelling and have it silently score
    as nothing.  A producer that needs finer provenance (which *kind* of
    disturbance was planted) records that alongside, never in place of, the
    cause.
    """

    #: A genuine new regime: the owner's habit moved and stayed moved.
    OWNER_HABIT = "owner_habit"
    #: A return to a regime seen earlier in the same stream.
    REGIME_RECURRENCE = "regime_recurrence"
    #: One-off or short-lived displacement; the habit did not move.
    TRANSIENT = "transient"
    #: Someone other than the subject moved it; the subject's habit is intact.
    GUEST = "guest"
    #: The context changed and the habit followed it.  Not a regime change.
    CONTEXT_SWITCH = "context_switch"
    #: Degraded or missing observation.  Absence of evidence, not evidence.
    OBSERVATION_GAP = "observation_gap"


#: Steps an arm *ought* to react to: the object is somewhere the habit would not
#: have put it, and the cause is transient rather than a new regime.
ANOMALY_CAUSES: frozenset[ChangeCause] = frozenset({ChangeCause.TRANSIENT, ChangeCause.GUEST})

#: Causes that mark a real regime boundary.
REGIME_CAUSES: frozenset[ChangeCause] = frozenset(
    {ChangeCause.OWNER_HABIT, ChangeCause.REGIME_RECURRENCE}
)

DATASET_CONTRACT_VERSION = "project-one-dataset@0.1"

#: Field names a record may never carry.  Enforced by the contract test.
FORBIDDEN_RECORD_FIELDS = frozenset(
    {
        "expected_location",
        "true_regime_id",
        "true_change_point",
        "true_change_cause",
        "label",
        "ground_truth",
    }
)


def _require_unit(value: float, name: str) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ProjectOneDatasetRecord:
    """One robot-visible observation, with no truth attached."""

    stream_id: str
    event_id: str
    subject_id: str
    household_id: str
    object_id: str
    actor_id: str
    timestamp: datetime
    context_key: str
    context_value: float
    observed_location: str
    observation_quality: float

    def __post_init__(self) -> None:
        for name in (
            "stream_id",
            "event_id",
            "subject_id",
            "household_id",
            "object_id",
            "actor_id",
            "context_key",
            "observed_location",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be a non-empty identifier")
        _require_aware(self.timestamp, "timestamp")
        _require_unit(self.observation_quality, "observation_quality")
        if not isfinite(self.context_value):
            raise ValueError("context_value must be finite")


@dataclass(frozen=True, slots=True)
class ProjectOneGroundTruth:
    """Evaluator-only truth for one event.

    ``expected_location`` is the location the owner's *true* habit would place
    the object at, which is not always the observed location — that gap is the
    anomaly an arm is supposed to notice.  ``None`` means genuinely unknown and
    must never be coerced into a label.
    """

    stream_id: str
    event_id: str
    expected_location: str | None = None
    true_regime_id: str | None = None
    true_change_point: bool = False
    true_change_cause: ChangeCause | None = None

    def __post_init__(self) -> None:
        if not self.stream_id.strip() or not self.event_id.strip():
            raise ValueError("truth must bind a stream and an event")
        if self.true_change_cause is not None:
            # Validated rather than free text: a private spelling would score as
            # nothing at all, silently, and the reading would look like a
            # detector failure rather than a vocabulary mismatch.
            try:
                object.__setattr__(self, "true_change_cause", ChangeCause(self.true_change_cause))
            except ValueError as error:
                allowed = sorted(item.value for item in ChangeCause)
                raise ValueError(
                    f"unknown true_change_cause {self.true_change_cause!r}; allowed: {allowed}"
                ) from error


@dataclass(frozen=True, slots=True)
class ProjectOneDatasetManifest:
    """Provenance for one stream: where it came from and how it was built."""

    stream_id: str
    source: str
    source_version: str
    split: str
    preprocessing: Mapping[str, str] = field(default_factory=dict)
    record_count: int = 0
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("stream_id", "source", "source_version", "split"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be a non-empty identifier")
        if self.record_count < 0:
            raise ValueError("record_count must be non-negative")


class ProjectOneTruthSet:
    """Evaluator-side truth, keyed by event id.

    Deliberately not a mapping a method could iterate: a method that somehow
    received this object still has to ask for a specific event id, and the
    runner never passes it one.
    """

    __slots__ = ("_by_event", "_carries_change_labels", "_stream_id")

    def __init__(
        self,
        stream_id: str,
        truths: Iterable[ProjectOneGroundTruth],
        *,
        carries_change_labels: bool = False,
    ) -> None:
        self._stream_id = stream_id
        self._carries_change_labels = carries_change_labels
        by_event: dict[str, ProjectOneGroundTruth] = {}
        for truth in truths:
            if truth.stream_id != stream_id:
                raise ValueError("truth stream_id does not match the stream")
            if truth.event_id in by_event:
                raise ValueError(f"duplicate truth for event {truth.event_id}")
            by_event[truth.event_id] = truth
        self._by_event = by_event

    @property
    def stream_id(self) -> str:
        return self._stream_id

    @property
    def carries_change_labels(self) -> bool:
        """Whether this truth set annotates change points at all.

        **Declared by the producer, never inferred from the contents.**  A
        controlled ``stable_habit`` stream is fully annotated and contains zero
        changes; a raw household log contains zero change *annotations*.  Those
        look identical from the data -- every entry has ``true_change_point =
        False`` -- and they mean opposite things.  Counting changes to decide
        would report "no false switches" for a log where nothing was checked.
        """

        return self._carries_change_labels

    def get(self, event_id: str) -> ProjectOneGroundTruth | None:
        return self._by_event.get(event_id)

    def __len__(self) -> int:
        return len(self._by_event)


@dataclass(frozen=True, slots=True)
class ProjectOneStream:
    """An ordered event stream plus its manifest.

    Truth is *not* a field of this object.  A dataset builder returns the
    stream and the truth set as two values; only the runner ever holds both.
    """

    manifest: ProjectOneDatasetManifest
    records: tuple[ProjectOneDatasetRecord, ...]

    def __post_init__(self) -> None:
        if not self.records:
            raise ValueError("a stream must contain at least one record")
        seen: set[str] = set()
        previous: datetime | None = None
        for record in self.records:
            if record.stream_id != self.manifest.stream_id:
                raise ValueError("record stream_id does not match the manifest")
            if record.event_id in seen:
                raise ValueError(f"duplicate event id {record.event_id}")
            seen.add(record.event_id)
            if previous is not None and record.timestamp < previous:
                raise ValueError("records must be sorted by non-decreasing timestamp")
            previous = record.timestamp
        if self.manifest.record_count and self.manifest.record_count != len(self.records):
            raise ValueError("manifest record_count disagrees with the stream")

    def locations(self) -> tuple[str, ...]:
        """Every location that appears, in first-observed order."""

        return tuple(dict.fromkeys(record.observed_location for record in self.records))

    def __iter__(self) -> Iterator[ProjectOneDatasetRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)


def build_manifest(
    *,
    stream_id: str,
    source: str,
    source_version: str,
    split: str,
    records: Sequence[ProjectOneDatasetRecord],
    preprocessing: Mapping[str, str] | None = None,
) -> ProjectOneDatasetManifest:
    """Build a manifest whose ``content_hash`` covers every visible field."""

    payload = [asdict(record) for record in records]
    return ProjectOneDatasetManifest(
        stream_id=stream_id,
        source=source,
        source_version=source_version,
        split=split,
        preprocessing=dict(preprocessing or {}),
        record_count=len(records),
        content_hash=content_sha256(payload),
    )
