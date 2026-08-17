"""Clock normalization and cross-session alignment for M02."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from uuid import UUID

from cpswm.contracts.base import require_aware

from .contracts import ClockAlignment, TimeAlignmentResult


def normalize_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC without changing its instant."""

    return require_aware(value, "timestamp").astimezone(UTC)


class ClockAlignmentConflictError(ValueError):
    """Raised for ambiguous or overlapping clock alignments."""


class ClockAlignmentNotFoundError(LookupError):
    """Raised when no valid alignment path exists."""


class TimeAlignmentRegistry:
    """Versioned, household-scoped graph of clock offsets."""

    def __init__(self) -> None:
        self._alignments: list[ClockAlignment] = []

    def register(self, alignment: ClockAlignment) -> None:
        for existing in self._alignments:
            if existing.alignment_id == alignment.alignment_id:
                if existing != alignment:
                    raise ClockAlignmentConflictError("alignment_id is already registered")
                return
            same_pair = existing.household_id == alignment.household_id and {
                existing.source_clock_id,
                existing.target_clock_id,
            } == {alignment.source_clock_id, alignment.target_clock_id}
            if same_pair and existing.valid_time.overlaps(alignment.valid_time):
                raise ClockAlignmentConflictError(
                    "overlapping alignments for one clock pair are ambiguous"
                )
        self._alignments.append(alignment)

    def align(
        self,
        value: datetime,
        *,
        source_clock_id: str,
        target_clock_id: str,
        household_id: UUID,
    ) -> TimeAlignmentResult:
        source_value = normalize_utc(value)
        if source_clock_id == target_clock_id:
            return TimeAlignmentResult(
                source_clock_id=source_clock_id,
                target_clock_id=target_clock_id,
                source_time=source_value,
                target_time=source_value,
                total_offset_seconds=0.0,
                uncertainty_seconds=0.0,
                alignment_ids=(),
            )

        queue = deque([(source_clock_id, 0.0, 0.0, tuple())])
        visited = {source_clock_id}
        while queue:
            current, total_offset, uncertainty, path = queue.popleft()
            for neighbor, offset, edge_uncertainty, alignment_id in self._edges(
                current, household_id, source_value
            ):
                if neighbor in visited:
                    continue
                next_offset = total_offset + offset
                next_uncertainty = uncertainty + edge_uncertainty
                next_path = (*path, alignment_id)
                if neighbor == target_clock_id:
                    target_value = source_value + timedelta(seconds=next_offset)
                    return TimeAlignmentResult(
                        source_clock_id=source_clock_id,
                        target_clock_id=target_clock_id,
                        source_time=source_value,
                        target_time=target_value,
                        total_offset_seconds=next_offset,
                        uncertainty_seconds=next_uncertainty,
                        alignment_ids=next_path,
                    )
                visited.add(neighbor)
                queue.append((neighbor, next_offset, next_uncertainty, next_path))
        raise ClockAlignmentNotFoundError(
            f"no clock path {source_clock_id!r} -> {target_clock_id!r}"
        )

    def _edges(
        self, clock_id: str, household_id: UUID, at_time: datetime
    ) -> list[tuple[str, float, float, UUID]]:
        edges: list[tuple[str, float, float, UUID]] = []
        for item in self._alignments:
            if item.household_id != household_id or not item.valid_time.contains(at_time):
                continue
            if item.source_clock_id == clock_id:
                edges.append(
                    (
                        item.target_clock_id,
                        item.offset_seconds,
                        item.uncertainty_seconds,
                        item.alignment_id,
                    )
                )
            elif item.target_clock_id == clock_id:
                edges.append(
                    (
                        item.source_clock_id,
                        -item.offset_seconds,
                        item.uncertainty_seconds,
                        item.alignment_id,
                    )
                )
        edges.sort(key=lambda edge: (edge[0], str(edge[3])))
        return edges
