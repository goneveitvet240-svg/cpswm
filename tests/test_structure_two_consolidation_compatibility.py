from __future__ import annotations

from pathlib import Path

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.structure_two_consolidation_compatibility import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    AdaptiveParticleConsolidationLedger,
    CompatibilityArm,
    ConsolidationStrategy,
    _compatibility_score,
    _dataset,
    _evaluate,
    _load_and_verify_holdout_seeds,
    load_frozen_compatibility_design,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import _ActionParticle
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _particle(
    label: str,
    *,
    actor: str,
    cause: ChangeCause,
    regime_change: bool,
    run_length: int,
    probability: float = 0.12,
) -> PersistentParticle:
    return PersistentParticle(
        hypothesis=_ActionParticle(actor, True, cause, regime_change),
        particle_id=content_uuid("compatibility-test-particle", label),
        parent_particle_id=None,
        revision_id=content_uuid("compatibility-test-revision", label),
        posterior_probability=probability,
        run_length=run_length,
    )


def test_compatibility_design_freezes_eight_arms_and_new_seeds() -> None:
    design = load_frozen_compatibility_design(ROOT / DEFAULT_MANIFEST)

    assert len(design.families) == 4
    assert len(design.holdout_seed_commitments) == 12
    assert set(design.search_spaces) == {arm.value for arm in CompatibilityArm}
    assert set(design.validation_seeds).isdisjoint(
        _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)
    )


def test_revision_compatibility_scores_all_four_axes() -> None:
    baseline = "owner|target|habit|stay"

    assert _compatibility_score(baseline, baseline) == 1.0
    assert _compatibility_score(baseline, "guest|target|habit|stay") == 0.7
    assert _compatibility_score(baseline, "owner|mismatch|habit|stay") == 0.75
    assert _compatibility_score(baseline, "owner|target|actor|stay") == 0.75
    assert _compatibility_score(baseline, "owner|target|habit|change") == 0.8


def test_each_strategy_emits_its_runtime_receipt_and_suppresses_conflict() -> None:
    location_a = content_uuid("compatibility-test-location", "a")
    location_b = content_uuid("compatibility-test-location", "b")
    stable = _particle(
        "stable",
        actor="owner",
        cause=ChangeCause.HABIT,
        regime_change=False,
        run_length=2,
    )
    conflict = _particle(
        "conflict",
        actor="guest",
        cause=ChangeCause.ACTOR,
        regime_change=True,
        run_length=0,
    )
    corrected = _particle(
        "corrected",
        actor="guest",
        cause=ChangeCause.ACTOR,
        regime_change=True,
        run_length=2,
    )
    promoted_distribution = {location_a: 0.75, location_b: 0.25}
    current_distribution = {location_a: 0.25, location_b: 0.75}

    ledgers = {
        strategy: AdaptiveParticleConsolidationLedger(strategy=strategy)
        for strategy in ConsolidationStrategy
    }
    for ledger in ledgers.values():
        ledger.update((stable,), promoted_distribution, step_index=1)
        ledger.blend(promoted_distribution)
        ledger.update((conflict,), current_distribution, step_index=2)
        ledger.blend(current_distribution)

    compatibility = ledgers[ConsolidationStrategy.COMPATIBILITY]
    assert compatibility.compatibility_suppression_count > 0
    assert compatibility.blend(current_distribution) == pytest.approx(current_distribution)
    uncertainty = ledgers[ConsolidationStrategy.UNCERTAINTY_DECAY]
    assert uncertainty.uncertainty_decay_count > 0
    assert uncertainty.current_influence_weight < 0.28
    assert uncertainty.blend(current_distribution) != pytest.approx(current_distribution)
    quarantine = ledgers[ConsolidationStrategy.IMMEDIATE_QUARANTINE]
    assert quarantine.immediate_quarantine_count > 0
    assert quarantine.blend(current_distribution) == pytest.approx(current_distribution)
    combined = ledgers[ConsolidationStrategy.ADAPTIVE_COMBINED]
    assert combined.blend(current_distribution) == pytest.approx(current_distribution)
    combined.update((corrected,), current_distribution, step_index=3)
    combined.blend(current_distribution)
    receipt = combined.strategy_receipt
    assert receipt["compatibility_suppression_count"] > 0
    assert receipt["uncertainty_decay_count"] > 0
    assert receipt["immediate_quarantine_count"] > 0


def test_all_eight_arms_share_one_visible_stream_and_execute() -> None:
    design = load_frozen_compatibility_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(94991,),
        max_steps=design.max_steps,
        split_label="eight-arm-smoke-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    evaluator = ProjectTwoActionBenchmarkV02()
    readings = {
        arm: _evaluate(
            evaluator,
            dataset,
            episode,
            family,
            arm,
            0.2 if arm is CompatibilityArm.CORRECTED_AMG else "balanced",
        )
        for arm in CompatibilityArm
    }

    assert len({reading.consumed_visible_stream_hash for reading in readings.values()}) == 1
    assert all(
        readings[arm].ancestry_edge_count > 0
        for arm in CompatibilityArm
        if arm
        not in {
            CompatibilityArm.CORRECTED_AMG,
            CompatibilityArm.PER_STEP_PARTICLE,
        }
    )
    assert (
        readings[CompatibilityArm.ADAPTIVE_COMBINED].strategy_receipt["strategy"]
        == ConsolidationStrategy.ADAPTIVE_COMBINED.value
    )
