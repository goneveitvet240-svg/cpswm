"""One log, many entities -- with the truth still exact per binding.

The generator's job is to produce the shape a real export has (interleaved
objects across households) without giving up the thing the controlled families
bought (a known answer for every event).  The tests below pin both halves, and
one operational property that is easy to lose: determinism.

The determinism test is not ceremony.  The first version of this module derived
its per-triple seeds from ``hash()``, which CPython salts per process -- the log
would have differed on every run while every artifact claimed a seed.
"""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_one_dataset import UNKNOWN_LOCATION
from cpswm.system.evaluation_operations.project_one_household_generator import (
    HOUSEHOLD_LOG_VERSION,
    build_household_log,
)
from cpswm.system.evaluation_operations.project_one_scenarios import (
    LOCATIONS,
    SCENARIO_NAMES,
    ZERO_CHANGE_POINT_FAMILIES,
)
from cpswm.system.evaluation_operations.project_one_stream_binding import (
    CandidatePolicy,
    bind_stream,
)


def _log(**overrides):
    kwargs = {
        "households": 3,
        "residents_per_household": 2,
        "objects_per_resident": 4,
        "seed": 0,
    }
    kwargs.update(overrides)
    return build_household_log(**kwargs)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_entity_grid_is_exactly_what_was_asked_for() -> None:
    log = _log()
    assert len(log.assignments) == 3 * 2 * 4
    assert len({item.household_id for item in log.assignments}) == 3
    assert len({(item.household_id, item.actor_id) for item in log.assignments}) == 6


def test_it_is_one_chronologically_ordered_stream() -> None:
    log = _log()
    stamps = [record.timestamp for record in log.stream.records]
    assert stamps == sorted(stamps)
    assert len(log.stream) > 400


def test_objects_are_interleaved_rather_than_concatenated() -> None:
    """A real export does not finish one object before starting the next."""

    log = _log()
    first_twenty = [record.object_id for record in log.stream.records[:20]]
    assert len(set(first_twenty)) > 1


def test_every_event_has_truth() -> None:
    log = _log()
    for record in log.stream.records:
        assert log.truth.get(record.event_id) is not None


def test_event_ids_are_unique_across_the_whole_log() -> None:
    log = _log()
    ids = [record.event_id for record in log.stream.records]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# It binds the way the pilot needs
# ---------------------------------------------------------------------------


def test_bind_stream_recovers_exactly_the_generated_triples() -> None:
    log = _log()
    bindings = bind_stream(log.stream, candidate_locations=log.candidate_locations)
    assert {binding.key for binding in bindings} == {item.key for item in log.assignments}


def test_the_declared_manifest_makes_every_binding_evaluable() -> None:
    """Including the false-alarm families, which observe only one location."""

    log = _log()
    bindings = bind_stream(log.stream, candidate_locations=log.candidate_locations)
    assert all(binding.is_evaluable for binding in bindings)
    assert all(binding.location_source == "manifest" for binding in bindings)
    assert all(
        binding.candidate_locations == (*LOCATIONS, UNKNOWN_LOCATION) for binding in bindings
    )


def test_without_the_manifest_the_single_location_bindings_are_skipped() -> None:
    """The contrast that justifies shipping a manifest at all."""

    log = _log(families=("stable_habit", "permanent_change"))
    bindings = bind_stream(
        log.stream,
        policy=CandidatePolicy.OBSERVED_ALL,
        allow_leaky_observed_all=True,
    )
    assert any(not binding.is_evaluable for binding in bindings)


def test_each_binding_holds_only_its_own_records() -> None:
    log = _log()
    for binding in bind_stream(log.stream, candidate_locations=log.candidate_locations):
        for record in binding.records:
            assert record.household_id == binding.key.household_id
            assert record.object_id == binding.key.object_id


# ---------------------------------------------------------------------------
# Truth survives the interleaving
# ---------------------------------------------------------------------------


def test_a_false_alarm_family_still_carries_no_change_point() -> None:
    log = _log()
    by_key = {item.key: item for item in log.assignments}
    for binding in bind_stream(log.stream, candidate_locations=log.candidate_locations):
        if by_key[binding.key].family not in ZERO_CHANGE_POINT_FAMILIES:
            continue
        for record in binding.records:
            entry = log.truth.get(record.event_id)
            assert entry is not None
            assert entry.true_change_point is False, by_key[binding.key].family


def test_a_true_change_family_still_carries_its_change_point() -> None:
    log = _log()
    by_key = {item.key: item for item in log.assignments}
    checked = 0
    for binding in bind_stream(log.stream, candidate_locations=log.candidate_locations):
        if by_key[binding.key].family in ZERO_CHANGE_POINT_FAMILIES:
            continue
        flagged = [
            record.event_id
            for record in binding.records
            if (entry := log.truth.get(record.event_id)) is not None and entry.true_change_point
        ]
        assert flagged, by_key[binding.key].family
        checked += 1
    assert checked > 0


def test_regime_ids_are_namespaced_per_binding() -> None:
    """Two objects both in ``regime-0`` are not in the *same* regime."""

    log = _log()
    entry = log.truth.get(log.stream.records[0].event_id)
    assert entry is not None
    assert entry.true_regime_id is not None
    assert ":" in entry.true_regime_id


def test_observed_locations_stay_inside_the_shared_vocabulary() -> None:
    log = _log()
    assert {record.observed_location for record in log.stream.records} <= set(LOCATIONS)


# ---------------------------------------------------------------------------
# Determinism and configuration
# ---------------------------------------------------------------------------


def test_the_same_seed_produces_the_same_log() -> None:
    assert _log().stream.manifest.content_hash == _log().stream.manifest.content_hash


def test_a_different_seed_produces_a_different_log() -> None:
    assert _log(seed=0).stream.manifest.content_hash != _log(seed=1).stream.manifest.content_hash


def test_two_objects_in_one_household_do_not_share_jitter() -> None:
    """Correlated seeds would look like many entities carrying one degree of freedom."""

    log = _log()
    alice_h1 = [
        item for item in log.assignments if item.household_id == "h1" and item.actor_id == "alice"
    ]
    assert len({item.seed for item in alice_h1}) == len(alice_h1)


def test_the_family_pool_can_be_restricted() -> None:
    log = _log(families=("permanent_change",))
    assert {item.family for item in log.assignments} == {"permanent_change"}


def test_an_unknown_family_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown scenario families"):
        _log(families=("not_a_family",))


def test_asking_for_more_residents_than_are_named_is_refused() -> None:
    with pytest.raises(ValueError, match="residents"):
        _log(residents_per_household=99)


def test_the_summary_reports_what_was_built() -> None:
    summary = _log().manifest_summary()
    assert summary["generator"] == HOUSEHOLD_LOG_VERSION
    assert summary["bindings"] == 24
    assert summary["households"] == 3
    assert len(summary["assignments"]) == 24
    assert {item["family"] for item in summary["assignments"]} <= set(SCENARIO_NAMES)


def test_the_manifest_records_the_generator_and_seed() -> None:
    log = _log(seed=4)
    preprocessing = dict(log.stream.manifest.preprocessing)
    assert preprocessing["generator"] == "household-log"
    assert preprocessing["seed"] == "4"
    assert preprocessing["bindings"] == "24"


def test_it_scales_to_a_larger_household_grid() -> None:
    log = _log(households=5, residents_per_household=4, objects_per_resident=8)
    assert len(log.assignments) == 160
    assert len(log.stream) > 3000
