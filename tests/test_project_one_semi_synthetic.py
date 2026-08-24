"""Semi-synthetic injection: known changes planted into a real stream.

Real household logs have no change-point labels.  Waiting for hand-annotated
ones means never running on real data; inferring them from the same model under
test means grading its own homework.  The third option is to take a real stream
and plant a change whose time, location and cause we chose ourselves.

That only works if two things hold, and both are asserted here.

**The distinction between a disturbance and a change must survive injection.**
``one_shot_disturbance`` and ``temporary_disturbance`` deliberately carry
``true_change_point = False``: they exist to catch false alarms, and an
injector that labelled them as changes would reward exactly the behaviour the
project is trying to suppress.

**The original stream is never mutated.**  A run that silently edited its input
cannot be re-run against the same baseline, and the injection log would then
describe a stream nobody has.  The source content hash is compared before and
after.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.dataset_adapters import InMemoryAdapter
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_semi_synthetic import (
    InjectionKind,
    inject_changes,
)

EPOCH = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
HOME = "table"
AWAY = "balcony"


def _stream(days: int = 24, *, location: str = HOME):
    records = [
        ProjectOneDatasetRecord(
            stream_id="real-a",
            event_id=f"r{index:03d}",
            subject_id="alice",
            household_id="h1",
            object_id="cup",
            actor_id="alice",
            timestamp=EPOCH + timedelta(days=index),
            context_key="morning",
            context_value=0.0,
            observed_location=location,
            observation_quality=0.9,
        )
        for index in range(days)
    ]
    return InMemoryAdapter(records, (), source="test", source_version="0.1").load(
        stream_id="real-a", split="pilot"
    )


# ---------------------------------------------------------------------------
# Non-mutation
# ---------------------------------------------------------------------------


def test_the_source_stream_is_never_modified_in_place() -> None:
    stream, truth = _stream()
    before_hash = stream.manifest.content_hash
    before_locations = [record.observed_location for record in stream.records]

    inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=7)

    assert stream.manifest.content_hash == before_hash
    assert [record.observed_location for record in stream.records] == before_locations


def test_the_result_records_the_hash_of_what_it_was_built_from() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=7)
    assert result.source_content_hash == stream.manifest.content_hash
    assert result.stream.manifest.content_hash != stream.manifest.content_hash


def test_the_injected_stream_is_still_a_valid_stream() -> None:
    stream, truth = _stream()
    result = inject_changes(
        stream,
        truth,
        kinds=(InjectionKind.PERMANENT_CHANGE, InjectionKind.ONE_SHOT_DISTURBANCE),
        seed=3,
    )
    stamps = [record.timestamp for record in result.stream.records]
    ids = [record.event_id for record in result.stream.records]
    assert stamps == sorted(stamps)
    assert len(set(ids)) == len(ids)
    assert len(result.stream) == len(stream)


def test_event_ids_are_preserved_so_truth_still_binds() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=1)
    assert [item.event_id for item in result.stream.records] == [
        item.event_id for item in stream.records
    ]
    for record in result.stream.records:
        assert result.truth.get(record.event_id) is not None


# ---------------------------------------------------------------------------
# What each injection means
# ---------------------------------------------------------------------------


def test_one_shot_disturbance_moves_exactly_one_event() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.ONE_SHOT_DISTURBANCE,), seed=5)

    (injection,) = result.injections
    assert injection.kind is InjectionKind.ONE_SHOT_DISTURBANCE
    assert injection.duration == 1
    assert len(injection.affected_event_ids) == 1

    moved = [record for record in result.stream.records if record.observed_location != HOME]
    assert [record.event_id for record in moved] == list(injection.affected_event_ids)


def test_a_disturbance_is_not_labelled_as_a_change_point() -> None:
    """The whole point of the disturbance scenarios is to catch false alarms."""

    stream, truth = _stream()
    for kind in (InjectionKind.ONE_SHOT_DISTURBANCE, InjectionKind.TEMPORARY_DISTURBANCE):
        result = inject_changes(stream, truth, kinds=(kind,), seed=5)
        (injection,) = result.injections
        assert injection.change_point_event_id is None
        for event_id in injection.affected_event_ids:
            entry = result.truth.get(event_id)
            assert entry is not None
            assert entry.true_change_point is False


def test_a_disturbance_leaves_the_expected_location_unchanged() -> None:
    """The habit did not move, so the truth still says where it should have been."""

    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.ONE_SHOT_DISTURBANCE,), seed=5)
    (injection,) = result.injections
    entry = result.truth.get(injection.affected_event_ids[0])
    assert entry is not None
    assert entry.expected_location == HOME


def test_temporary_disturbance_spans_more_than_one_event_and_returns() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.TEMPORARY_DISTURBANCE,), seed=11)
    (injection,) = result.injections
    assert injection.duration > 1
    assert len(injection.affected_event_ids) == injection.duration

    by_id = {record.event_id: record for record in result.stream.records}
    affected = set(injection.affected_event_ids)
    tail = [
        record
        for record in result.stream.records
        if record.event_id not in affected
        and record.timestamp > by_id[injection.affected_event_ids[-1]].timestamp
    ]
    assert tail, "a temporary disturbance must be followed by a return"
    assert all(record.observed_location == HOME for record in tail)


def test_permanent_change_relocates_every_later_event() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=9)
    (injection,) = result.injections

    start = injection.affected_event_ids[0]
    started = False
    for record in result.stream.records:
        if record.event_id == start:
            started = True
        if started:
            assert record.observed_location == injection.injected_location
        else:
            assert record.observed_location == injection.original_location


def test_permanent_change_marks_exactly_one_change_point() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=9)
    (injection,) = result.injections

    assert injection.change_point_event_id == injection.affected_event_ids[0]
    flagged = [
        record.event_id
        for record in result.stream.records
        if (entry := result.truth.get(record.event_id)) is not None and entry.true_change_point
    ]
    assert flagged == [injection.change_point_event_id]


def test_permanent_change_moves_the_expected_location_too() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=9)
    (injection,) = result.injections
    entry = result.truth.get(injection.affected_event_ids[-1])
    assert entry is not None
    assert entry.expected_location == injection.injected_location


def test_recurring_regime_returns_to_a_location_it_already_used() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.RECURRING_REGIME,), seed=13)
    (injection,) = result.injections

    assert injection.kind is InjectionKind.RECURRING_REGIME
    assert len(injection.blocks) >= 2
    first, second = injection.blocks[0], injection.blocks[1]
    assert first.location == second.location
    assert first.event_ids[-1] < second.event_ids[0]


def test_recurring_regime_marks_each_block_start_as_a_change_point() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.RECURRING_REGIME,), seed=13)
    (injection,) = result.injections

    starts = {block.event_ids[0] for block in injection.blocks}
    flagged = {
        record.event_id
        for record in result.stream.records
        if (entry := result.truth.get(record.event_id)) is not None and entry.true_change_point
    }
    assert starts <= flagged


# ---------------------------------------------------------------------------
# The injection log
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(InjectionKind))
def test_every_injection_records_the_five_required_facts(kind: InjectionKind) -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(kind,), seed=21)
    for injection in result.injections:
        assert injection.original_location
        assert injection.injected_location
        assert injection.injected_location != injection.original_location
        assert injection.duration >= 1
        assert injection.cause
        # change point is allowed to be None -- for disturbances it must be.
        assert injection.change_point_event_id is None or isinstance(
            injection.change_point_event_id, str
        )


def test_the_injected_location_is_drawn_from_outside_the_current_habit() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=21)
    (injection,) = result.injections
    assert injection.injected_location != HOME


def test_injection_is_deterministic_under_a_seed() -> None:
    stream, truth = _stream()
    kinds = (InjectionKind.PERMANENT_CHANGE, InjectionKind.TEMPORARY_DISTURBANCE)
    first = inject_changes(stream, truth, kinds=kinds, seed=42)
    second = inject_changes(stream, truth, kinds=kinds, seed=42)
    assert first.stream.manifest.content_hash == second.stream.manifest.content_hash
    assert first.injections == second.injections


def test_a_different_seed_produces_a_different_plan() -> None:
    stream, truth = _stream()
    first = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=1)
    second = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=2)
    assert first.injections != second.injections


def test_the_manifest_declares_the_stream_as_semi_synthetic() -> None:
    stream, truth = _stream()
    result = inject_changes(stream, truth, kinds=(InjectionKind.PERMANENT_CHANGE,), seed=1)
    preprocessing = dict(result.stream.manifest.preprocessing)
    assert "semi-synthetic" in result.stream.manifest.source
    assert preprocessing["injections"] == "1"
    assert preprocessing["seed"] == "1"


def test_multiple_kinds_do_not_overlap_on_the_same_event() -> None:
    stream, truth = _stream(days=40)
    result = inject_changes(
        stream,
        truth,
        kinds=(
            InjectionKind.ONE_SHOT_DISTURBANCE,
            InjectionKind.TEMPORARY_DISTURBANCE,
            InjectionKind.PERMANENT_CHANGE,
        ),
        seed=17,
    )
    seen: set[str] = set()
    for injection in result.injections:
        assert seen.isdisjoint(injection.affected_event_ids)
        seen.update(injection.affected_event_ids)


def test_a_stream_too_short_to_inject_into_fails_loudly() -> None:
    stream, truth = _stream(days=2)
    with pytest.raises(ValueError, match="too short"):
        inject_changes(stream, truth, kinds=(InjectionKind.RECURRING_REGIME,), seed=1)
