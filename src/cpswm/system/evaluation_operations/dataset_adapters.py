"""Adapter boundary between raw sources and the project-one data contract.

Every data source — deterministic scenarios today, semi-synthetic injections
and real household logs later, LLM-extracted events in 阶段 9 — implements
:class:`DatasetAdapter`.  The adapter is the only place that knows the source's
quirks; downstream code sees one record type.

An adapter emits records and truth as two separate values so that truth cannot
travel with the stream by accident.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from .project_one_dataset import (
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
    build_manifest,
)

__all__ = ["DatasetAdapter", "InMemoryAdapter"]


class DatasetAdapter(ABC):
    """Turn one raw source into a validated stream plus its evaluator truth."""

    #: Stable identifier written into every manifest this adapter produces.
    source: str = "unspecified"
    source_version: str = "0.0"

    @abstractmethod
    def _emit(self) -> tuple[Sequence[ProjectOneDatasetRecord], Sequence[ProjectOneGroundTruth]]:
        """Produce records in emission order and their evaluator truth."""

    def preprocessing(self) -> Mapping[str, str]:
        """Preprocessing steps worth recording in the manifest."""

        return {}

    def carries_change_labels(self) -> bool:
        """Whether this source annotates change points.

        Defaults to ``False`` -- the safe answer for anything external, because
        reporting a supervised metric that was never checkable is worse than
        omitting one that was.
        """

        return False

    def load(self, *, stream_id: str, split: str) -> tuple[ProjectOneStream, ProjectOneTruthSet]:
        """Validate, sort and package one stream.

        Sorting is stable and by timestamp only, so an adapter that already
        emits chronologically keeps its own order for equal timestamps.  The
        stream constructor then re-checks monotonicity and event-id uniqueness,
        which means an adapter cannot ship an unordered or duplicated stream
        even if it sorts incorrectly.
        """

        raw_records, raw_truths = self._emit()
        records = tuple(sorted(raw_records, key=lambda record: record.timestamp))
        manifest = build_manifest(
            stream_id=stream_id,
            source=self.source,
            source_version=self.source_version,
            split=split,
            records=records,
            preprocessing=self.preprocessing(),
        )
        stream = ProjectOneStream(manifest=manifest, records=records)
        known_events = {record.event_id for record in records}
        for truth in raw_truths:
            if truth.event_id not in known_events:
                raise ValueError(f"truth references unknown event {truth.event_id}")
        return stream, ProjectOneTruthSet(
            stream_id, raw_truths, carries_change_labels=self.carries_change_labels()
        )


class InMemoryAdapter(DatasetAdapter):
    """Adapter over records already in memory.

    Used by the deterministic scenario generator and by tests; also the
    shortest path for trying a new source before writing a real adapter.
    """

    source = "in-memory"
    source_version = "0.1"

    def __init__(
        self,
        records: Sequence[ProjectOneDatasetRecord],
        truths: Sequence[ProjectOneGroundTruth] = (),
        *,
        source: str | None = None,
        source_version: str | None = None,
        preprocessing: Mapping[str, str] | None = None,
        change_labels: bool = False,
    ) -> None:
        self._records = tuple(records)
        self._truths = tuple(truths)
        self._preprocessing = dict(preprocessing or {})
        self._change_labels = change_labels
        if source is not None:
            self.source = source
        if source_version is not None:
            self.source_version = source_version

    def _emit(self) -> tuple[Sequence[ProjectOneDatasetRecord], Sequence[ProjectOneGroundTruth]]:
        return self._records, self._truths

    def preprocessing(self) -> Mapping[str, str]:
        return dict(self._preprocessing)

    def carries_change_labels(self) -> bool:
        return self._change_labels
