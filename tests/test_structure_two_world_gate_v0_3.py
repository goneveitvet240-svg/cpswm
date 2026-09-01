"""Tests for the additive v0.3 Gate A references and learnability witness."""

from __future__ import annotations

import json
import random
from pathlib import Path
from statistics import mean

import pytest

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    RegimeAdaptiveWitnessConfig,
    ShrunkEstimatorConfig,
    _actor_components,
    _argmax,
    _WitnessEstimator,
    analytic_world_unobserved_error,
    encounter_order,
    evaluate_rollout_v0_3,
    unobserved_location_posterior,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorldGeneratorV02,
    StructureTwoWorldStep,
    WorldDistributionConfig,
)

MANIFEST = Path("configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json")


@pytest.fixture(scope="module")
def design() -> tuple[WorldDistributionConfig, StructureTwoWorldGeneratorV02, dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = WorldDistributionConfig.from_manifest(payload["world_distribution"])
    return config, StructureTwoWorldGeneratorV02(config), payload


def _frozen(payload: dict) -> ShrunkEstimatorConfig:
    rules = payload["gate_a_rules"]
    return ShrunkEstimatorConfig(
        window_days=rules["aggregation_window_days"],
        context_shrinkage_pseudocounts=0.0,
        owner_probability_threshold=rules["visible_owner_probability_threshold"],
    )


def _witness(threshold: float, **overrides: object) -> RegimeAdaptiveWitnessConfig:
    settings: dict = {
        "recent_window": 6,
        "divergence_threshold": 0.55,
        "minimum_reference_observations": 8,
        "context_shrinkage_pseudocounts": 4.0,
        "owner_probability_threshold": threshold,
    }
    settings.update(overrides)
    return RegimeAdaptiveWitnessConfig(**settings)  # type: ignore[arg-type]


def test_analytic_oracle_field_does_not_move_with_any_seed(design) -> None:
    """The reported analytic field must equal the world-level value exactly.

    Calling the pure function twice proves nothing: the defect this guards
    against was a correct function that was never wired to the reading, which
    kept averaging over whichever days one rollout happened to leave unobserved.
    So the assertion is made on readings from rollouts with different trajectory
    AND observation seeds.
    """

    config, generator, payload = design
    world = generator.sample_world(410001)
    expected = analytic_world_unobserved_error(world, config)
    assert 0.0 < expected < 1.0
    readings = [
        evaluate_rollout_v0_3(
            generator.generate_rollout(
                world, trajectory_seed=trajectory, observation_seed=observation
            ),
            world,
            config,
            frozen=_frozen(payload),
            witness=_witness(0.5),
        )
        for trajectory, observation in ((13, 103), (29, 223), (41, 331))
    ]
    values = {item.search_observable_oracle_unobserved_error_analytic for item in readings}
    assert values == {expected}
    # the empirical companion must still move with the mask, or the two fields
    # are not measuring different things
    assert len({item.search_observable_oracle_unobserved_error_empirical for item in readings}) > 1


def test_mnar_conditioning_never_lowers_expected_accuracy(design) -> None:
    """q(argmax q) >= q(argmax p), where q conditions on unobserved and p does not.

    Comparing 1 - max(q) against 1 - max(p) would compare accuracies under two
    different measures and would not test the inversion at all.
    """

    config, generator, payload = design
    for world_seed in payload["split_policy"]["train_world_seeds"][:6]:
        world = generator.sample_world(world_seed)
        for regime in ("baseline", "shifted", "recurrent"):
            for context in ("weekday", "weekend"):
                conditioned = unobserved_location_posterior(
                    world, config, regime=regime, context=context
                )
                plain = unobserved_location_posterior(
                    world, config, regime=regime, context=context, apply_mnar_correction=False
                )
                assert conditioned[_argmax(conditioned)] >= conditioned[_argmax(plain)] - 1e-12


def test_actor_component_priors_sum_to_one(design) -> None:
    _config, generator, _unused = design
    world = generator.sample_world(410002)
    components = _actor_components(world, regime="baseline", context="weekday")
    assert sum(prior for _, prior, _ in components) == pytest.approx(1.0)


def test_ties_follow_visible_first_encounter_not_location_label() -> None:
    locations = ("location-z", "location-a", "location-m", "location-q")
    visible = ("location-m", "location-z", "location-m")
    order = encounter_order(locations, visible)
    assert [item for item, _ in sorted(order.items(), key=lambda pair: pair[1])] == [
        "location-m",
        "location-z",
        "location-a",
        "location-q",
    ]
    assert _argmax({item: 1.0 for item in locations}, order) == "location-m"

    rename = {
        "location-z": "00",
        "location-a": "zz",
        "location-m": "middle-renamed",
        "location-q": "aa",
    }
    renamed_locations = tuple(rename[item] for item in locations)
    renamed_visible = tuple(rename[item] for item in visible)
    renamed_order = encounter_order(renamed_locations, renamed_visible)
    selected = _argmax({item: 1.0 for item in renamed_locations}, renamed_order)
    assert selected == rename["location-m"]


def test_each_estimator_uses_its_own_admission_threshold(design) -> None:
    """A threshold declared on a config must actually change that estimator."""

    config, generator, payload = design
    world = generator.sample_world(410003)
    rollout = generator.generate_rollout(world, trajectory_seed=13, observation_seed=103)
    permissive = evaluate_rollout_v0_3(
        rollout, world, config, frozen=_frozen(payload), witness=_witness(0.0)
    )
    strict = evaluate_rollout_v0_3(
        rollout, world, config, frozen=_frozen(payload), witness=_witness(0.99)
    )
    assert permissive.witness_admitted_weekday_count > 0
    assert permissive.witness_admitted_weekend_count > 0
    assert strict.witness_admitted_weekday_count == 0
    assert strict.witness_admitted_weekend_count == 0
    assert permissive.search_frozen_context_error == strict.search_frozen_context_error


def _stationary_reset_rate(
    seed: int, observations: int, mode_mass: float, *, burn_in: int = 60
) -> float:
    """Resets per observation on an i.i.d. stationary stream, after warm-up.

    The warm-up matters: while the reference window holds fewer than
    ``minimum_reference_observations`` the detector cannot fire at all, so a
    short stream is diluted by a stretch where the rate is zero by construction.
    Comparing raw rates across lengths would read that dilution as drift.
    """

    rng = random.Random(seed)
    locations = [f"loc{index}" for index in range(10)]
    tail = (1.0 - mode_mass) / (len(locations) - 1)
    weights = [mode_mass] + [tail] * (len(locations) - 1)
    estimator = _WitnessEstimator("loc0", _witness(0.0))
    for day in range(observations):
        location = rng.choices(locations, weights=weights)[0]
        estimator.observe(
            StructureTwoWorldStep(
                day=day,
                context="weekday" if day % 7 < 5 else "weekend",
                regime="baseline",
                true_actor="owner",
                true_location=location,
                true_owner_habit_location=locations[0],
                true_habit_distribution=dict(zip(locations, weights, strict=True)),
                true_mechanism="direct",
                true_cause="owner_habit_sample",
                true_identity_match=True,
                event_chain=("pick_up", "carry", "place"),
                observed=True,
                observation_propensity=1.0,
                observed_location=location,
                visible_actor_map="owner",
                visible_owner_probability=1.0,
                visible_identity_confidence=1.0,
            ),
            location,
        )
    scored = max(1, observations - burn_in)
    return sum(1 for day in estimator.reset_days if day >= burn_in) / scored


def test_false_reset_rate_does_not_rise_with_stream_length() -> None:
    """Centeredness is a rate property, not a count property.

    Any detector with a non-zero false-positive rate accumulates resets linearly
    in time, so a bound on the total count is not a centeredness test -- a
    properly centered detector would fail it.  What must hold is that the rate
    per observation stays flat as the stream lengthens.  A drifting statistic
    fails this because a longer stream lets it climb to the threshold from any
    starting point.
    """

    for mass in (0.45, 0.55):
        short = _stationary_reset_rate(seed=11, observations=200, mode_mass=mass)
        long = _stationary_reset_rate(seed=11, observations=900, mode_mass=mass)
        assert long <= short + 0.02


# One false alarm per regime is the most a witness may cost.  At the horizon
# under consideration a regime holds roughly forty observed owner placements, so
# the ceiling is 1/40.  This is derived from the world design, not chosen to let
# any particular configuration pass.
STATIONARY_FALSE_ALARM_CEILING = 0.025


def test_default_configuration_false_alarm_rate_is_measured_not_assumed() -> None:
    """Record what the current defaults actually cost on stationary streams."""

    rates = [
        _stationary_reset_rate(seed=seed, observations=400, mode_mass=0.5) for seed in range(8)
    ]
    measured = mean(rates)
    # The k=6 / tau=0.55 defaults fire far above the ceiling: a six-sample window
    # against a well-estimated reference produces large total variation by
    # sampling noise alone.  This is asserted as a recorded fact so that any
    # configuration promoted into the manifest must be checked against
    # STATIONARY_FALSE_ALARM_CEILING rather than inheriting these defaults.
    assert measured > STATIONARY_FALSE_ALARM_CEILING


def test_reference_and_recent_windows_do_not_overlap() -> None:
    """A sample counted in both windows pulls them together and suppresses the test."""

    estimator = _WitnessEstimator("loc0", _witness(0.0, recent_window=4))
    locations = [f"loc{index}" for index in range(6)]
    for day in range(12):
        location = locations[day % len(locations)]
        estimator.observe(
            StructureTwoWorldStep(
                day=day,
                context="weekday",
                regime="baseline",
                true_actor="owner",
                true_location=location,
                true_owner_habit_location=location,
                true_habit_distribution={item: 1 / len(locations) for item in locations},
                true_mechanism="direct",
                true_cause="owner_habit_sample",
                true_identity_match=True,
                event_chain=("pick_up", "carry", "place"),
                observed=True,
                observation_propensity=1.0,
                observed_location=location,
                visible_actor_map="owner",
                visible_owner_probability=1.0,
                visible_identity_confidence=1.0,
            ),
            location,
        )
    windows = estimator.detector_windows()
    assert windows is not None
    reference, recent = windows
    assert {day for day, _context, _location in reference}.isdisjoint(
        day for day, _context, _location in recent
    )
    assert max(day for day, _context, _location in reference) < min(
        day for day, _context, _location in recent
    )


def test_frozen_rule_still_reproduces_the_v0_2_readings(design) -> None:
    config, generator, payload = design
    split = payload["split_policy"]
    world = generator.sample_world(split["validation_world_seeds"][0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=split["trajectory_seeds_per_validation_world"][0],
        observation_seed=split["observation_seeds_per_validation_trajectory"][0],
    )
    reading = evaluate_rollout_v0_3(
        rollout,
        world,
        config,
        frozen=_frozen(payload),
        witness=_witness(payload["gate_a_rules"]["visible_owner_probability_threshold"]),
    )
    assert 0.0 < reading.search_frozen_context_error < 1.0
    assert reading.search_frozen_context_error <= reading.search_last_observed_error
    assert reading.unobserved_step_count > 0


def test_analytic_and_empirical_oracle_fields_are_distinct(design) -> None:
    config, generator, payload = design
    world = generator.sample_world(410004)
    rollout = generator.generate_rollout(world, trajectory_seed=13, observation_seed=103)
    reading = evaluate_rollout_v0_3(
        rollout, world, config, frozen=_frozen(payload), witness=_witness(0.5)
    )
    assert (
        reading.search_observable_oracle_unobserved_error_analytic
        != reading.search_observable_oracle_unobserved_error_empirical
    )
