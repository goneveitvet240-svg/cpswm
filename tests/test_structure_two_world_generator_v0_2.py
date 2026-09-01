"""Integrity tests for the frozen Structure-Two world generator v0.2."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_2 import (
    DEFAULT_MANIFEST,
    evaluate_rollout_gate_a,
    load_frozen_world_gate_design,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    CONTEXTS,
    PROTOCOL_ID,
    StructureTwoWorldGeneratorV02,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / DEFAULT_MANIFEST


@pytest.fixture(scope="module")
def frozen_design():
    return load_frozen_world_gate_design(MANIFEST)


@pytest.fixture(scope="module")
def generator(frozen_design):
    return StructureTwoWorldGeneratorV02(frozen_design.distribution)


def test_world_level_splits_are_disjoint_and_holdout_is_only_committed(
    frozen_design,
) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    split = payload["split_policy"]
    assert set(frozen_design.train_world_seeds).isdisjoint(frozen_design.validation_world_seeds)
    assert split["unit"] == "world_seed"
    assert split["holdout_raw_world_seeds_disclosed"] is False
    assert len(frozen_design.holdout_world_seed_commitments) == 24
    assert len(set(frozen_design.holdout_world_seed_commitments)) == 24
    assert all(len(item) == 64 for item in frozen_design.holdout_world_seed_commitments)
    assert payload["method_comparison_policy"].startswith("forbidden unless every")


def test_validation_worlds_are_deterministic_and_structurally_unique(
    frozen_design,
    generator,
) -> None:
    first = [generator.sample_world(seed) for seed in frozen_design.validation_world_seeds]
    second = [generator.sample_world(seed) for seed in frozen_design.validation_world_seeds]
    assert [item.world_hash for item in first] == [item.world_hash for item in second]
    assert len({item.world_hash for item in first}) == len(first)
    assert all(
        item.world_seed == seed
        for item, seed in zip(first, frozen_design.validation_world_seeds, strict=True)
    )


def test_observation_seed_only_changes_observation_process(frozen_design, generator) -> None:
    world = generator.sample_world(frozen_design.validation_world_seeds[0])
    common = {
        "trajectory_seed": frozen_design.trajectory_seeds[0],
    }
    left = generator.generate_rollout(
        world,
        observation_seed=frozen_design.observation_seeds[0],
        **common,
    )
    right = generator.generate_rollout(
        world,
        observation_seed=frozen_design.observation_seeds[1],
        **common,
    )

    def truth(rollout):
        return [
            (
                step.true_actor,
                step.true_location,
                step.true_owner_habit_location,
                step.true_mechanism,
                step.true_cause,
                step.regime,
                step.event_chain,
            )
            for step in rollout.steps
        ]

    assert truth(left) == truth(right)
    assert [step.observed for step in left.steps] != [step.observed for step in right.steps]


def test_trajectory_seed_changes_latent_world_evolution(frozen_design, generator) -> None:
    world = generator.sample_world(frozen_design.validation_world_seeds[0])
    rollouts = [
        generator.generate_rollout(
            world,
            trajectory_seed=seed,
            observation_seed=frozen_design.observation_seeds[0],
        )
        for seed in frozen_design.trajectory_seeds[:2]
    ]
    sequences = [
        [(step.true_actor, step.true_location, step.true_mechanism) for step in rollout.steps]
        for rollout in rollouts
    ]
    assert sequences[0] != sequences[1]


def test_habit_target_is_distribution_mode_not_latest_sample(frozen_design, generator) -> None:
    saw_non_mode_owner_sample = False
    saw_context_specific_mode = False
    for seed in frozen_design.validation_world_seeds:
        world = generator.sample_world(seed)
        for context in CONTEXTS:
            assert world.habit_distribution("recurrent", context) == world.habit_distribution(
                "baseline", context
            )
        if max(
            world.habit_distribution("baseline", "weekday"),
            key=world.habit_distribution("baseline", "weekday").get,
        ) != max(
            world.habit_distribution("baseline", "weekend"),
            key=world.habit_distribution("baseline", "weekend").get,
        ):
            saw_context_specific_mode = True
        rollout = generator.generate_rollout(
            world,
            trajectory_seed=frozen_design.trajectory_seeds[0],
            observation_seed=frozen_design.observation_seeds[0],
        )
        for step in rollout.steps:
            assert sum(step.true_habit_distribution.values()) == pytest.approx(1.0)
            expected_mode = min(
                step.true_habit_distribution,
                key=lambda item: (-step.true_habit_distribution[item], item),
            )
            assert step.true_owner_habit_location == expected_mode
            if (
                step.true_actor == rollout.owner_actor
                and step.true_location != step.true_owner_habit_location
            ):
                saw_non_mode_owner_sample = True
    assert saw_non_mode_owner_sample
    assert saw_context_specific_mode


def test_visibility_is_mnar_and_bounded(frozen_design, generator) -> None:
    world = generator.sample_world(frozen_design.validation_world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=frozen_design.trajectory_seeds[0],
        observation_seed=frozen_design.observation_seeds[0],
    )
    by_location: dict[str, set[float]] = defaultdict(set)
    all_propensities = set()
    for step in rollout.steps:
        assert 0.05 <= step.observation_propensity <= 0.98
        by_location[step.true_location].add(step.observation_propensity)
        all_propensities.add(step.observation_propensity)
    assert len(all_propensities) > 4
    assert len(by_location) >= 4


def test_rollout_gate_reader_is_pure_and_deterministic(frozen_design, generator) -> None:
    world = generator.sample_world(frozen_design.validation_world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=frozen_design.trajectory_seeds[0],
        observation_seed=frozen_design.observation_seeds[0],
    )
    kwargs = {
        "aggregation_window_days": frozen_design.aggregation_window_days,
        "owner_probability_threshold": frozen_design.owner_probability_threshold,
    }
    assert evaluate_rollout_gate_a(rollout, **kwargs) == evaluate_rollout_gate_a(rollout, **kwargs)


def test_manifest_protocol_is_exactly_v0_2() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["protocol"] == PROTOCOL_ID
    assert payload["status"] == "frozen-before-first-gate-a-run"
