"""Integrity tests for the frozen train-only v0.3 horizon probe."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_2 import (
    load_frozen_world_gate_design,
)
from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    ShrunkEstimatorConfig,
    evaluate_rollout_v0_3,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    IntegerRangeSpec,
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_horizon_probe_v0_3 import (
    DEFAULT_DESIGN,
    _false_reset_count,
    _score_witness_rollout,
    load_horizon_probe_design,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_MANIFEST = (
    ROOT / "configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json"
)


@pytest.fixture(scope="module")
def probe_design():
    return load_horizon_probe_design(ROOT / DEFAULT_DESIGN, repository_root=ROOT)


def test_probe_is_train_only_and_has_exactly_48_frozen_candidates(probe_design) -> None:
    base = load_frozen_world_gate_design(BASE_MANIFEST)
    assert probe_design.duration_days == (320, 380)
    assert set(probe_design.world_seeds) == set(base.train_world_seeds)
    assert set(probe_design.world_seeds).isdisjoint(base.validation_world_seeds)
    assert len(probe_design.witness_configs()) == 48


def test_four_folds_cover_each_train_world_once(probe_design) -> None:
    flattened = [seed for fold in probe_design.folds for seed in fold]
    assert len(flattened) == len(set(flattened)) == 24
    assert set(flattened) == set(probe_design.world_seeds)
    assert {len(fold) for fold in probe_design.folds} == {6}


def test_false_reset_matching_is_one_to_one(probe_design) -> None:
    base = load_frozen_world_gate_design(BASE_MANIFEST)
    generator = StructureTwoWorldGeneratorV02(base.distribution)
    world = generator.sample_world(probe_design.world_seeds[0])
    resets = (
        world.abrupt_day,
        world.abrupt_day + 1,
        world.recurrence_day + 5,
        world.recurrence_day + probe_design.grace_days + 1,
    )
    assert _false_reset_count(resets, world, grace_days=probe_design.grace_days) == 2


def test_failed_probe_retains_its_legacy_tie_break_and_is_not_a_gate_input(
    probe_design,
) -> None:
    base = load_frozen_world_gate_design(BASE_MANIFEST)
    long_config = replace(
        base.distribution,
        duration_days=IntegerRangeSpec(*probe_design.duration_days),
    )
    generator = StructureTwoWorldGeneratorV02(long_config)
    world = generator.sample_world(probe_design.world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=probe_design.trajectory_seeds[0],
        observation_seed=probe_design.observation_seeds[0],
    )
    witness = probe_design.witness_configs()[0]
    slim = _score_witness_rollout(
        rollout,
        world,
        witness,
        grace_days=probe_design.grace_days,
    )
    full = evaluate_rollout_v0_3(
        rollout,
        world,
        long_config,
        frozen=ShrunkEstimatorConfig(
            window_days=35,
            context_shrinkage_pseudocounts=0.0,
            owner_probability_threshold=0.5,
        ),
        witness=witness,
    )
    expected = (
        full.search_last_observed_normalised_path_cost - full.search_witness_normalised_path_cost
    )
    # The archived probe predates the formal visible-encounter tie-break now
    # used by Gate A.  Rewriting its readings would destroy the failed artifact
    # we are explicitly preserving, so the difference is recorded rather than
    # silently normalised away.  The v0.4 gate has its own formal path-cost test.
    assert slim.normalised_path_cost_gain != pytest.approx(expected)


def test_promotion_requirements_are_frozen_before_run(probe_design) -> None:
    assert probe_design.minimum_mean_top1_gain == pytest.approx(0.020)
    assert probe_design.minimum_worst_fold_top1_gain == pytest.approx(0.018)
    assert probe_design.maximum_false_resets_per_rollout == pytest.approx(1.0)
    assert probe_design.maximum_stationary_false_alarm_rate == pytest.approx(0.025)
