from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    MultiAxisBelief,
    _ActionParticle,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    PersistentParticle,
    ReversibleParticleConsolidationLedger,
    SequentialGateArm,
    SequentialParticleRuntime,
    _dataset,
    _evaluate,
    _load_and_verify_holdout_seeds,
    _visible_transform,
    load_frozen_sequential_gate_design,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _belief(*, identity: float = 0.85, regime: float = 0.25) -> MultiAxisBelief:
    locations = (
        content_uuid("sequential-gate-test-location", "a"),
        content_uuid("sequential-gate-test-location", "b"),
    )
    return MultiAxisBelief(
        actor_posterior={"owner": 0.75, "guest": 0.25},
        owner_actor_key="owner",
        identity_target_probability=identity,
        cause_posterior={
            ChangeCause.OBSERVATION: 0.10,
            ChangeCause.ACTOR: 0.15,
            ChangeCause.HABIT: 0.65,
            ChangeCause.NOISE: 0.10,
        },
        regime_change_probability=regime,
        active_regime="test-regime",
        observed_location_id=locations[1],
        base_location_distribution={locations[0]: 0.7, locations[1]: 0.3},
    )


def test_design_freezes_new_families_arms_and_disjoint_sealed_seeds() -> None:
    design = load_frozen_sequential_gate_design(ROOT / DEFAULT_MANIFEST)

    assert len(design.families) == 4
    assert len(design.holdout_seed_commitments) == 12
    assert set(design.search_spaces) == {arm.value for arm in SequentialGateArm}
    assert any(family.decoy_days for family in design.families)
    assert set(design.validation_seeds).isdisjoint(
        _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)
    )


def test_sequential_runtime_preserves_parent_ancestry_across_steps() -> None:
    runtime = SequentialParticleRuntime(profile="balanced")

    first = runtime.revise(_belief())
    second = runtime.revise(_belief(identity=0.80))

    assert len(first) == len(second) == 24
    assert all(item.parent_particle_id is not None for item in second)
    assert len(runtime.ancestry_trace) == 24
    assert max(item.run_length for item in second) >= 1


def test_particle_ledger_promotes_exactly_once_then_retracts_and_corrects() -> None:
    ledger = ReversibleParticleConsolidationLedger(stability_steps=1)
    location = content_uuid("sequential-gate-test-location", "ledger")
    revision_a = content_uuid("sequential-gate-test-revision", "a")
    revision_b = content_uuid("sequential-gate-test-revision", "b")
    particle_a = PersistentParticle(
        hypothesis=_ActionParticle("owner", True, ChangeCause.HABIT, False),
        particle_id=content_uuid("sequential-gate-test-particle", "a"),
        parent_particle_id=None,
        revision_id=revision_a,
        posterior_probability=0.8,
        run_length=2,
    )
    particle_b = PersistentParticle(
        hypothesis=_ActionParticle("guest", True, ChangeCause.ACTOR, True),
        particle_id=content_uuid("sequential-gate-test-particle", "b"),
        parent_particle_id=particle_a.particle_id,
        revision_id=revision_b,
        posterior_probability=0.8,
        run_length=2,
    )

    ledger.update((particle_a,), {location: 1.0}, step_index=1)
    ledger.update((particle_a,), {location: 1.0}, step_index=2)
    ledger.update((particle_b,), {location: 1.0}, step_index=3)

    assert ledger.operation_counts["promote"] == 1
    assert ledger.operation_counts["retract"] == 1
    assert ledger.operation_counts["corrected_revision"] == 1
    assert ledger.duplicate_promotion_count == 0
    assert all(
        record.previous_hash == ("GENESIS" if index == 0 else ledger.records[index - 1].record_hash)
        for index, record in enumerate(ledger.records)
    )


def test_identity_decoy_is_visible_and_contract_consistent() -> None:
    design = load_frozen_sequential_gate_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(73991,),
        max_steps=design.max_steps,
        split_label="decoy-contract-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    index, step = next(
        (index, step) for index, step in enumerate(episode.steps) if step.after is not None
    )
    transformed = _visible_transform(replace(family, decoy_days=(index + 1,)), episode)(step)

    assert transformed.after is not None
    assert transformed.after.detected_object_instance_id != step.object_instance_id
    assert transformed.detection_confidence == pytest.approx(0.92)
    if transformed.unified_evidence is not None:
        assert transformed.unified_evidence.detected_object_key == str(
            transformed.after.detected_object_instance_id
        )


def test_all_five_arms_execute_on_one_frozen_episode() -> None:
    design = load_frozen_sequential_gate_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(73992,),
        max_steps=design.max_steps,
        split_label="five-arm-smoke-test",
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
            0.2 if arm is SequentialGateArm.CORRECTED_AMG else "balanced",
        )
        for arm in SequentialGateArm
    }

    assert len({item.consumed_visible_stream_hash for item in readings.values()}) == 1
    assert readings[SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION].ancestry_edge_count > 0
    consolidated = readings[SequentialGateArm.SEQUENTIAL_CONSOLIDATION]
    assert consolidated.ancestry_edge_count > 0
    assert consolidated.ledger_operation_counts["promote"] > 0
    assert consolidated.duplicate_promotion_count == 0
