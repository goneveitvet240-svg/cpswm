from __future__ import annotations

import math
from pathlib import Path

import pytest

from cpswm.contracts import EvidenceFactorKind, EvidenceFactorOperator
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import MultiAxisBelief
from cpswm.system.evaluation_operations.structure_two_neural_amortized import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    FEATURE_NAMES,
    FORBIDDEN_INPUTS,
    NeuralAmortizedParticleRuntime,
    NeuralProposalArm,
    TrainingExample,
    _load_and_verify_holdout_seeds,
    _train_model,
    load_frozen_neural_design,
)
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _example(cause_index: int, regime: float) -> TrainingExample:
    features = [0.0 for _ in FEATURE_NAMES]
    features[cause_index] = 0.85
    features[4] = regime
    features[5] = 0.8
    features[6] = 0.75
    features[7] = 0.75
    return TrainingExample(tuple(features), cause_index, regime)


def _belief(cause: ChangeCause, regime: float) -> MultiAxisBelief:
    from cpswm.system.reproducibility import content_uuid

    location_a = content_uuid("neural-amortized-test", "a")
    location_b = content_uuid("neural-amortized-test", "b")
    posterior = dict.fromkeys(ChangeCause, 0.05)
    posterior[cause] = 0.85
    return MultiAxisBelief(
        actor_posterior={"owner": 0.8, "guest": 0.2},
        owner_actor_key="owner",
        identity_target_probability=0.8,
        cause_posterior=posterior,
        regime_change_probability=regime,
        active_regime="test",
        observed_location_id=location_a,
        base_location_distribution={location_a: 0.7, location_b: 0.3},
    )


def test_design_freezes_disjoint_train_validation_and_holdout() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    holdout = _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)

    assert len(FEATURE_NAMES) == 16
    assert len(design.training_seeds) == 8
    assert len(design.validation_seeds) == 4
    assert len(holdout) == 12
    assert set(design.training_seeds).isdisjoint(design.validation_seeds)
    assert set(design.training_seeds).isdisjoint(holdout)
    assert set(design.validation_seeds).isdisjoint(holdout)
    assert set(design.search_spaces) == {arm.value for arm in NeuralProposalArm}


def test_feature_firewall_excludes_oracle_and_latent_inputs() -> None:
    assert not (set(FEATURE_NAMES) & FORBIDDEN_INPUTS)
    assert all("oracle" not in name and "latent" not in name for name in FEATURE_NAMES)


def test_trained_mlp_is_deterministic_and_emits_neural_receipt() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    examples = tuple(_example(index % 4, float(index % 2)) for index in range(32))
    first = _train_model(examples, design.model)
    second = _train_model(examples, design.model)
    assert first.model_hash == second.model_hash
    assert first.training_example_count == 32

    runtime = NeuralAmortizedParticleRuntime(profile="balanced", model=first, mix=0.7)
    runtime.revise(_belief(ChangeCause.HABIT, 0.85))
    runtime.revise(_belief(ChangeCause.ACTOR, 0.10))
    assert runtime.neural_proposal_receipts
    assert runtime.ancestry_trace
    assert len(runtime.importance_revision_receipts) == 2
    assert all(len(batch) == 24 for batch in runtime.importance_revision_receipts)
    assert runtime.revision_batches[-1].unresolved_probability > 0.0
    assert sum(item.posterior_probability for item in runtime.particles) + (
        runtime.unresolved_probability
    ) == pytest.approx(1.0)
    q_receipts = [
        item
        for item in runtime.evidence_factor_trace.receipts
        if item.operator is EvidenceFactorOperator.NEURAL_PROPOSER
    ]
    assert q_receipts
    assert all(item.factor_kind is EvidenceFactorKind.PROPOSAL_DISTRIBUTION for item in q_receipts)
    likelihood_consumptions = [
        item for item in runtime.evidence_factor_trace.receipts if item.consumed_as_likelihood
    ]
    assert not likelihood_consumptions
    projection_reads = [
        item
        for item in runtime.evidence_factor_trace.receipts
        if any(
            source.startswith("visible-posterior-projection:") for source in item.source_factor_ids
        )
    ]
    assert projection_reads
    assert not any(
        item.consumed_as_likelihood
        and any(source.startswith("neural-q:") for source in item.source_factor_ids)
        for item in runtime.evidence_factor_trace.receipts
    )
    assert runtime.evidence_factor_trace.verify_chain()


def test_neural_score_is_only_q_and_every_runtime_weight_subtracts_log_q() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(
        tuple(_example(index % 4, float(index % 2)) for index in range(16)), design.model
    )
    runtime = NeuralAmortizedParticleRuntime(profile="balanced", model=model, mix=0.9)
    belief = _belief(ChangeCause.HABIT, 0.8)

    runtime.revise(belief)

    receipts = runtime.importance_revision_receipts[-1]
    assert receipts
    for receipt in receipts:
        target_without_q = (
            receipt.prior_log_weight
            + receipt.transition_log_probability
            + receipt.observation_log_likelihood
            + receipt.posterior_projection_log_factor
            + sum(item.log_potential for item in receipt.constraints)
        )
        assert receipt.unnormalized_log_weight == pytest.approx(
            target_without_q - receipt.proposal.proposal_log_probability
        )
        assert receipt.proposal.proposal_log_probability <= 0.0
        assert math.isfinite(receipt.proposal.proposal_log_probability)
        assert receipt.evidence_semantics == "posterior_projection_not_likelihood"
        assert receipt.observation_log_likelihood == 0.0


def test_same_visible_posterior_snapshot_cannot_be_replayed_as_new_evidence() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(
        tuple(_example(index % 4, float(index % 2)) for index in range(16)), design.model
    )
    runtime = NeuralAmortizedParticleRuntime(profile="balanced", model=model, mix=0.7)
    belief = _belief(ChangeCause.HABIT, 0.8)

    runtime.revise(belief)
    receipt_count = len(runtime.evidence_factor_trace.receipts)
    with pytest.raises(ValueError, match="already consumed"):
        runtime.revise(belief)

    assert len(runtime.evidence_factor_trace.receipts) == receipt_count
    assert runtime.evidence_factor_trace.verify_chain()


def test_systematic_proposal_is_reproducible_but_not_deterministic_top_k() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(
        tuple(_example(index % 4, float(index % 2)) for index in range(16)), design.model
    )
    first = NeuralAmortizedParticleRuntime(profile="balanced", model=model, mix=0.8)
    second = NeuralAmortizedParticleRuntime(profile="balanced", model=model, mix=0.8)
    belief = _belief(ChangeCause.ACTOR, 0.2)

    first.revise(belief)
    second.revise(belief)

    assert first.neural_proposal_receipts == second.neural_proposal_receipts
    assert [item.hypothesis.key for item in first.particles] == [
        item.hypothesis.key for item in second.particles
    ]
    # Systematic sampling may retain repeated high-q hypotheses; each draw is a
    # proposal sample with an auditable q, not a unique deterministic Top-K row.
    assert len({item.hypothesis.key for item in first.particles}) < len(first.particles)


def test_model_payload_declares_trained_mlp_not_deterministic_heuristic() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(
        tuple(_example(index % 4, float(index % 2)) for index in range(16)), design.model
    )
    payload = model.payload()

    assert payload["model_type"] == "trained_one_hidden_layer_mlp"
    assert payload["training_data_boundary"] == "training_seeds_visible_beliefs_only"
    assert payload["training_example_count"] == 16
