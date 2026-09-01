from __future__ import annotations

from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    MultiAxisBelief,
    _ActionParticle,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
)
from cpswm.system.evaluation_operations.structure_two_transition_reactivation import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    ConflictAwareSequentialParticleRuntime,
    ReactivatingParticleLedger,
    TransitionReactivationArm,
    _dataset,
    _evaluate,
    _load_and_verify_holdout_seeds,
    load_frozen_transition_reactivation_design,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _belief(cause: ChangeCause, regime_change: float) -> MultiAxisBelief:
    locations = (
        content_uuid("transition-reactivation-test-location", "a"),
        content_uuid("transition-reactivation-test-location", "b"),
    )
    posterior = dict.fromkeys(ChangeCause, 0.05)
    posterior[cause] = 0.85
    return MultiAxisBelief(
        actor_posterior={"owner": 0.8, "guest": 0.2},
        owner_actor_key="owner",
        identity_target_probability=0.85,
        cause_posterior=posterior,
        regime_change_probability=regime_change,
        active_regime="test-regime",
        observed_location_id=locations[1],
        base_location_distribution={locations[0]: 0.7, locations[1]: 0.3},
    )


def _particle(label: str, cause: ChangeCause, run_length: int) -> PersistentParticle:
    return PersistentParticle(
        hypothesis=_ActionParticle("owner", True, cause, cause is ChangeCause.HABIT),
        particle_id=content_uuid("transition-reactivation-test-particle", label),
        parent_particle_id=None,
        revision_id=content_uuid("transition-reactivation-test-revision", label),
        posterior_probability=0.2,
        run_length=run_length,
    )


def test_design_freezes_seven_arms_and_new_holdout_seeds() -> None:
    design = load_frozen_transition_reactivation_design(ROOT / DEFAULT_MANIFEST)

    assert len(design.families) == 4
    assert len(design.holdout_seed_commitments) == 12
    assert set(design.search_spaces) == {arm.value for arm in TransitionReactivationArm}
    assert set(design.validation_seeds).isdisjoint(
        _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)
    )


def test_conflict_aware_runtime_emits_transition_receipt_and_keeps_ancestry() -> None:
    runtime = ConflictAwareSequentialParticleRuntime(profile="balanced")

    runtime.revise(_belief(ChangeCause.HABIT, 0.85))
    runtime.revise(_belief(ChangeCause.ACTOR, 0.10))

    assert runtime.conflict_transition_receipts
    assert runtime.ancestry_trace
    assert all(particle.parent_particle_id is not None for particle in runtime.particles)


def test_reactivating_ledger_archives_then_reuses_prior_signature() -> None:
    ledger = ReactivatingParticleLedger()
    location_a = content_uuid("transition-reactivation-test-location", "ledger-a")
    location_b = content_uuid("transition-reactivation-test-location", "ledger-b")
    habit = _particle("habit-first", ChangeCause.HABIT, 2)
    actor = _particle("actor", ChangeCause.ACTOR, 2)
    habit_return = _particle("habit-return", ChangeCause.HABIT, 2)

    ledger.update((habit,), {location_a: 0.8, location_b: 0.2}, step_index=1)
    ledger.update((actor,), {location_a: 0.2, location_b: 0.8}, step_index=2)
    ledger.update((habit_return,), {location_a: 0.6, location_b: 0.4}, step_index=3)

    assert ledger.reactivation_count == 1
    assert ledger.operation_counts["reactivate"] == 1
    assert ledger.duplicate_promotion_count == 0
    assert ledger.records[-1].operation == "reactivate"


def test_all_seven_arms_execute_on_same_visible_stream() -> None:
    design = load_frozen_transition_reactivation_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(106991,),
        max_steps=design.max_steps,
        split_label="seven-arm-smoke-test",
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
            0.2 if arm is TransitionReactivationArm.CORRECTED_AMG else "balanced",
        )
        for arm in TransitionReactivationArm
    }

    assert len({reading.consumed_visible_stream_hash for reading in readings.values()}) == 1
    assert (
        readings[
            TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION
        ].conflict_transition_count
        > 0
    )
    assert readings[TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION].ancestry_edge_count > 0
