from __future__ import annotations

from pathlib import Path

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


def test_model_payload_declares_trained_mlp_not_deterministic_heuristic() -> None:
    design = load_frozen_neural_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(
        tuple(_example(index % 4, float(index % 2)) for index in range(16)), design.model
    )
    payload = model.payload()

    assert payload["model_type"] == "trained_one_hidden_layer_mlp"
    assert payload["training_data_boundary"] == "training_seeds_visible_beliefs_only"
    assert payload["training_example_count"] == 16
