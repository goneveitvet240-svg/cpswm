from __future__ import annotations

from pathlib import Path
from uuid import UUID

from cpswm.contracts import ProjectTwoDataMaturity, ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    _ActionParticle,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    ADAPTER_RECEIPTS,
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    PUBLISHED_NEIGHBOR_ARMS,
    AttributedPolicyLedger,
    MemoryDecision,
    NeighborArm,
    NeighborVisibleDecisionState,
    _dataset,
    _evaluate,
    _external_family,
    _load_and_verify_holdout_seeds,
    _load_external_dataset,
    _quarantine_correlated_evidence,
    choose_neighbor_decision,
    load_frozen_neighbor_design,
)
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _visible(*, commit_risk: float, escrow_risk: float) -> NeighborVisibleDecisionState:
    return NeighborVisibleDecisionState(
        posterior_confidence=0.72,
        normalized_entropy=0.30,
        coverage_score=0.75,
        preservation_score=0.60,
        novelty_score=0.40,
        future_utility_score=1.20,
        commit_risk=commit_risk,
        escrow_risk=escrow_risk,
        verification_cost=0.50,
        remaining_steps=12,
        remaining_physical_verifications=2,
    )


def _particle(*, actor: str, revision: int, probability: float) -> PersistentParticle:
    return PersistentParticle(
        hypothesis=_ActionParticle(
            actor_key=actor,
            identity_target=True,
            cause=ChangeCause.HABIT,
            regime_change=True,
        ),
        particle_id=UUID(int=revision + 100),
        parent_particle_id=None,
        revision_id=UUID(int=revision),
        posterior_probability=probability,
        run_length=2,
    )


def test_design_freezes_eleven_arms_six_families_and_fresh_seeds() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)

    assert len(design.families) == 6
    assert len(design.holdout_seed_commitments) == 24
    assert set(design.search_spaces) == {arm.value for arm in NeighborArm}
    assert set(design.published_neighbor_arms) == PUBLISHED_NEIGHBOR_ARMS
    assert set(design.validation_seeds).isdisjoint(seeds)
    assert set(seeds).isdisjoint(range(220201, 220225))


def test_care_responds_to_embodied_regret_while_ablation_does_not() -> None:
    high = _visible(commit_risk=1.20, escrow_risk=1.00)
    low = _visible(commit_risk=0.20, escrow_risk=0.10)

    care_high = choose_neighbor_decision(NeighborArm.CARE_WM, high, 1.0)
    care_low = choose_neighbor_decision(NeighborArm.CARE_WM, low, 1.0)
    ablation_high = choose_neighbor_decision(
        NeighborArm.CARE_NO_ACTION_REGRET,
        high,
        0.70,
    )
    ablation_low = choose_neighbor_decision(
        NeighborArm.CARE_NO_ACTION_REGRET,
        low,
        0.70,
    )

    assert care_high.action is MemoryDecision.VERIFY
    assert care_low.action is MemoryDecision.ESCROW
    assert ablation_high.action is ablation_low.action


def test_published_neighbor_decisions_require_no_truth_fields() -> None:
    visible = _visible(commit_risk=0.60, escrow_risk=0.40)
    parameters = {
        NeighborArm.ACTIVE_DREAMING: 0.60,
        NeighborArm.AUTO_DREAMER: 0.0,
        NeighborArm.TRUSTMEM: 0.65,
        NeighborArm.BRAINCTL: 0.60,
    }

    decisions = {
        arm: choose_neighbor_decision(arm, visible, parameter)
        for arm, parameter in parameters.items()
    }

    assert set(decisions) == PUBLISHED_NEIGHBOR_ARMS
    assert all(decision.decision_rule for decision in decisions.values())


def test_inspected_neighbor_receipts_do_not_claim_external_fidelity() -> None:
    for arm in (NeighborArm.ACTIVE_DREAMING, NeighborArm.BRAINCTL):
        assert (
            ADAPTER_RECEIPTS[arm]["fidelity"] == "reduced_proxy_not_faithful_external_reproduction"
        )
    for arm in (NeighborArm.AUTO_DREAMER, NeighborArm.TRUSTMEM):
        assert (
            ADAPTER_RECEIPTS[arm]["fidelity"]
            == "reduced_proxy_not_independently_verified_external_reproduction"
        )


def test_all_arms_execute_on_the_same_visible_validation_episode() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(519991,),
        max_steps=design.max_steps,
        split_label="unit-validation-smoke",
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
            design.search_spaces[arm.value][0],
            max_physical_verifications=design.max_physical_verifications_per_episode,
        )
        for arm in NeighborArm
    }

    assert len({reading.consumed_visible_stream_hash for reading in readings.values()}) == 1
    assert all(
        reading.decision_truth_isolation
        for arm, reading in readings.items()
        if arm is not NeighborArm.ORACLE
    )
    assert all(reading.metric.step_count == design.max_steps for reading in readings.values())


def test_all_arms_quarantine_d2_shared_clusters_on_the_same_visible_stream() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    dataset = _load_external_dataset(
        ROOT,
        directory="d2_real_perception_example_v0_1",
        maturity=ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
    )
    family = _external_family("d2-unit-smoke")
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    evaluator = ProjectTwoActionBenchmarkV02()
    quarantine_count = sum(_quarantine_correlated_evidence(step)[1] for step in episode.steps)

    readings = {
        arm: _evaluate(
            evaluator,
            dataset,
            episode,
            family,
            arm,
            design.search_spaces[arm.value][0],
            max_physical_verifications=design.max_physical_verifications_per_episode,
        )
        for arm in NeighborArm
    }

    assert quarantine_count > 0
    assert len({reading.consumed_visible_stream_hash for reading in readings.values()}) == 1
    assert all(
        reading.decision_truth_isolation
        for arm, reading in readings.items()
        if arm is not NeighborArm.ORACLE
    )


def test_attributed_ledger_hash_chain_replays_exactly_after_correction() -> None:
    first = _particle(actor="resident", revision=1, probability=0.80)
    corrected = _particle(actor="guest", revision=2, probability=0.90)
    location_a = UUID(int=11)
    location_b = UUID(int=12)
    ledger = AttributedPolicyLedger()

    ledger.escrow((first,), {location_a: 0.8, location_b: 0.2}, step_index=1)
    ledger.verify((first,), {location_a: 0.8, location_b: 0.2}, step_index=1)
    ledger.update((first,), {location_a: 0.8, location_b: 0.2}, step_index=1)
    ledger.update((corrected,), {location_a: 0.1, location_b: 0.9}, step_index=2)

    counts = ledger.policy_operation_counts
    assert counts["escrow"] == 1
    assert counts["verify"] == 1
    assert counts["promote"] == 1
    assert counts["retract"] == 1
    assert counts["corrected_revision"] == 1
    assert ledger.duplicate_promotion_count == 0
    assert ledger.replay_equivalent
