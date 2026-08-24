"""Seeded scenario variants: more data, same meaning.

A randomizer is only useful if it cannot quietly change what a family means.
The dangerous failure is not a crash -- it is a `short_disturbance` seed that
happens to emit a change point, because that turns a false-alarm guardrail into
a change detector and rewards exactly the over-triggering the project is trying
to suppress.  Every invariant below is therefore checked across **every family
and a sweep of seeds**, not on one hand-picked example.

The power helpers are tested alongside, because a seed count is only justified
by the number it is supposed to reach.
"""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_one_power import (
    DEFAULT_MDE,
    PowerReport,
    paired_bootstrap_ci,
    power_check,
    required_pairs,
)
from cpswm.system.evaluation_operations.project_one_scenarios import (
    LOCATIONS,
    RANDOMIZED_SCENARIO_VERSION,
    SCENARIO_NAMES,
    SCENARIO_VERSION,
    ZERO_CHANGE_POINT_FAMILIES,
    build_all_scenarios,
    build_randomized_scenario,
    build_stream,
    scenario_stream_id,
)

SEEDS = tuple(range(12))


# ---------------------------------------------------------------------------
# The anchors still exist and still behave
# ---------------------------------------------------------------------------


def test_the_deterministic_anchor_is_unchanged_by_the_seeded_path() -> None:
    """Every pre-multi-seed reading must stay reproducible."""

    stream, truth = build_stream("permanent_change")
    assert stream.manifest.stream_id == "permanent_change"
    assert stream.manifest.source == SCENARIO_VERSION
    assert dict(stream.manifest.preprocessing)["rng"] == "none"
    assert truth.get("permanent_change-000") is not None


def test_build_all_scenarios_without_seeds_is_the_ten_anchors() -> None:
    streams = build_all_scenarios()
    assert len(streams) == len(SCENARIO_NAMES)
    assert [item[0].manifest.stream_id for item in streams] == list(SCENARIO_NAMES)


# ---------------------------------------------------------------------------
# Meaning survives every seed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCENARIO_NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_false_alarm_family_never_emits_a_change_point(name: str, seed: int) -> None:
    scenario = build_randomized_scenario(name, seed)
    changes = [index for index, day in enumerate(scenario.days) if day.change_point]
    if name in ZERO_CHANGE_POINT_FAMILIES:
        assert changes == [], f"{name} seed {seed} invented a change point"
    else:
        assert changes, f"{name} seed {seed} lost its change point"


@pytest.mark.parametrize("name", SCENARIO_NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_change_point_lands_inside_the_warm_up(name: str, seed: int) -> None:
    """A detector with three days of history has nothing to be surprised by."""

    scenario = build_randomized_scenario(name, seed)
    for index, day in enumerate(scenario.days):
        if day.change_point:
            assert index >= 8, f"{name} seed {seed} changed on day {index}"


@pytest.mark.parametrize("name", SCENARIO_NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_change_point_is_always_the_first_day_of_its_regime(name: str, seed: int) -> None:
    scenario = build_randomized_scenario(name, seed)
    previous: str | None = None
    for index, day in enumerate(scenario.days):
        if day.change_point:
            assert day.regime_id != previous, (
                f"{name} seed {seed} day {index} is flagged but continues regime {previous}"
            )
        previous = day.regime_id


@pytest.mark.parametrize("name", SCENARIO_NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_every_regime_transition_is_flagged(name: str, seed: int) -> None:
    """The converse: a silent regime switch would be an unscoreable change."""

    scenario = build_randomized_scenario(name, seed)
    previous: str | None = None
    for index, day in enumerate(scenario.days):
        if previous is not None and day.regime_id != previous:
            assert day.change_point, (
                f"{name} seed {seed} day {index} switched regime without a change point"
            )
        previous = day.regime_id


@pytest.mark.parametrize("name", SCENARIO_NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_locations_and_lengths_stay_inside_the_contract(name: str, seed: int) -> None:
    scenario = build_randomized_scenario(name, seed)
    assert len(scenario.days) >= 18
    for day in scenario.days:
        assert day.observed_location in LOCATIONS
        assert day.expected_location in LOCATIONS
        assert 0.0 <= day.observation_quality <= 1.0


@pytest.mark.parametrize("seed", SEEDS)
def test_a_disturbance_leaves_the_expected_location_alone(seed: int) -> None:
    """The habit did not move, so the truth must not move with the observation."""

    scenario = build_randomized_scenario("short_disturbance", seed)
    moved = [day for day in scenario.days if day.observed_location != day.expected_location]
    assert len(moved) == 1
    assert moved[0].change_cause == "transient"


@pytest.mark.parametrize("seed", SEEDS)
def test_guest_days_never_move_the_owner_habit(seed: int) -> None:
    scenario = build_randomized_scenario("biased_observation", seed)
    expected = {day.expected_location for day in scenario.days}
    assert len(expected) == 1, "the owner's habit must be constant in this family"
    guests = [day for day in scenario.days if day.change_cause == "guest"]
    assert 2 <= len(guests) <= 5
    assert all(day.actor_id != "owner" for day in guests)


@pytest.mark.parametrize("seed", SEEDS)
def test_recurring_regime_returns_to_the_first_regime(seed: int) -> None:
    scenario = build_randomized_scenario("recurring_regime", seed)
    flagged = [day for day in scenario.days if day.change_point]
    assert len(flagged) == 2
    assert flagged[0].change_cause == "owner_habit"
    assert flagged[1].change_cause == "regime_recurrence"
    assert scenario.days[-1].regime_id == scenario.days[0].regime_id


@pytest.mark.parametrize("seed", SEEDS)
def test_gradual_drift_ramps_rather_than_jumps(seed: int) -> None:
    """Before the ramp opens the old location must be certain, after it the new one."""

    scenario = build_randomized_scenario("gradual_drift", seed)
    flip = next(i for i, day in enumerate(scenario.days) if day.change_point)
    before = scenario.days[0].expected_location
    after = scenario.days[flip].expected_location
    assert before != after
    assert all(day.observed_location == before for day in scenario.days[:4])
    assert scenario.days[-1].observed_location == after


# ---------------------------------------------------------------------------
# Seeds actually add information
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_a_seed_is_deterministic(name: str) -> None:
    assert build_randomized_scenario(name, 5) == build_randomized_scenario(name, 5)


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_different_seeds_produce_different_streams(name: str) -> None:
    variants = {build_randomized_scenario(name, seed).days for seed in SEEDS}
    assert len(variants) >= len(SEEDS) - 1, f"{name} barely varies across seeds"


def test_families_do_not_move_together_at_the_same_seed() -> None:
    """Seeding from the seed alone would add one degree of freedom, not ten."""

    lengths = {name: len(build_randomized_scenario(name, 3).days) for name in SCENARIO_NAMES}
    assert len(set(lengths.values())) > 1


def test_seeded_streams_carry_a_distinct_identity() -> None:
    assert scenario_stream_id("stable_habit", None) == "stable_habit"
    assert scenario_stream_id("stable_habit", 7) == "stable_habit@s0007"
    stream, _truth = build_stream("stable_habit", seed=7)
    assert stream.manifest.stream_id == "stable_habit@s0007"
    assert stream.manifest.source == RANDOMIZED_SCENARIO_VERSION
    assert dict(stream.manifest.preprocessing)["seed"] == "7"


def test_the_cross_product_is_families_times_seeds() -> None:
    streams = build_all_scenarios(("stable_habit", "permanent_change"), seeds=(0, 1, 2))
    ids = [item[0].manifest.stream_id for item in streams]
    assert ids == [
        "stable_habit@s0000",
        "stable_habit@s0001",
        "stable_habit@s0002",
        "permanent_change@s0000",
        "permanent_change@s0001",
        "permanent_change@s0002",
    ]


def test_every_seeded_stream_has_unique_event_ids_across_the_cross_product() -> None:
    streams = build_all_scenarios(seeds=(0, 1))
    seen: set[str] = set()
    for stream, _truth in streams:
        for record in stream.records:
            assert record.event_id not in seen
            seen.add(record.event_id)


def test_an_empty_seed_list_is_refused() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_all_scenarios(seeds=())


# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------


def test_required_pairs_reproduces_the_shift_v5_number() -> None:
    """SHIFT v5 reported required n = 17 at powered SD 0.072521, MDE 0.05."""

    assert required_pairs(0.072521, mde=0.05) == 17


def test_a_larger_spread_needs_more_pairs() -> None:
    assert required_pairs(0.2) > required_pairs(0.1) > required_pairs(0.05)


def test_the_sd_floor_stops_a_zero_variance_endpoint_claiming_one_pair() -> None:
    check = power_check(
        {f"s{i}": 0.1 for i in range(4)}, endpoint="confirmation", reference="no_rls"
    )
    assert check.empirical_sd == 0.0
    assert check.powered_sd == pytest.approx(0.05)
    assert check.required_pairs > 1


def test_a_small_study_is_reported_underpowered() -> None:
    check = power_check(
        {"a": 0.1, "b": -0.2, "c": 0.3, "d": 0.0, "e": -0.1},
        endpoint="confirmation",
        reference="no_rls",
    )
    assert check.achieved_pairs == 5
    assert check.powered is False
    assert check.as_dict()["conclusion"] == "inconclusive"


def test_enough_streams_flips_the_verdict() -> None:
    tight = {f"s{i}": 0.10 + 0.001 * (i % 3) for i in range(60)}
    check = power_check(tight, endpoint="confirmation", reference="no_rls")
    assert check.powered is True
    assert PowerReport((check,)).verdict() == "CONCLUSIVE"


def test_one_underpowered_endpoint_makes_the_whole_report_underpowered() -> None:
    strong = power_check({f"s{i}": 0.1 for i in range(60)}, endpoint="a", reference="ref")
    weak = power_check({"x": 0.4, "y": -0.4}, endpoint="b", reference="ref")
    report = PowerReport((strong, weak))
    assert report.verdict() == "UNDERPOWERED"
    assert [item.endpoint for item in report.shortfall()] == ["b"]


def test_a_duplicate_stream_cannot_be_weighted_twice() -> None:
    """Keying by stream id is the guardrail; a mapping cannot hold a key twice."""

    check = power_check({"s0": 0.1, "s1": 0.2}, endpoint="a", reference="ref")
    assert check.achieved_pairs == 2


def test_the_bootstrap_interval_brackets_the_mean() -> None:
    values = [0.1, 0.2, 0.15, 0.05, 0.12, 0.18]
    low, high = paired_bootstrap_ci(values, iterations=500, seed=1)
    assert low <= sum(values) / len(values) <= high


def test_the_bootstrap_is_deterministic_under_a_seed() -> None:
    values = [0.1, -0.2, 0.3, 0.0]
    assert paired_bootstrap_ci(values, seed=3) == paired_bootstrap_ci(values, seed=3)


def test_an_all_positive_difference_is_significant() -> None:
    check = power_check({f"s{i}": 0.2 for i in range(30)}, endpoint="a", reference="ref")
    assert check.significant is True


def test_a_difference_straddling_zero_is_not_significant() -> None:
    check = power_check(
        {f"s{i}": (0.3 if i % 2 else -0.3) for i in range(30)},
        endpoint="a",
        reference="ref",
    )
    assert check.significant is False


def test_the_default_mde_matches_the_shift_guardrail() -> None:
    assert DEFAULT_MDE == 0.05
