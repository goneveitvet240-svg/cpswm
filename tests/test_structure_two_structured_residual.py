from __future__ import annotations

from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_fresh_triarm import MultiAxisBelief
from cpswm.system.evaluation_operations.structure_two_neural_amortized import FEATURE_NAMES
from cpswm.system.evaluation_operations.structure_two_structured_residual import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    FORBIDDEN_INFERENCE_INPUTS,
    ResidualArm,
    ResidualTrainingExample,
    StructuredResidualParticleRuntime,
    _load_and_verify_holdout_seeds,
    _train_model,
    load_frozen_residual_design,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def _example(target: float) -> ResidualTrainingExample:
    values = [0.0 for _ in FEATURE_NAMES]
    values[ChangeCause.HABIT.value == "habit" and 2] = 0.85
    values[4] = target
    values[5] = 0.8
    values[6] = 0.75
    values[7] = 0.75
    return ResidualTrainingExample(tuple(values), target, 1.0)


def _belief(cause: ChangeCause, regime: float) -> MultiAxisBelief:
    first = content_uuid("structured-residual-test", "a")
    second = content_uuid("structured-residual-test", "b")
    posterior = dict.fromkeys(ChangeCause, 0.05)
    posterior[cause] = 0.85
    return MultiAxisBelief(
        actor_posterior={"owner": 0.8, "guest": 0.2},
        owner_actor_key="owner",
        identity_target_probability=0.8,
        cause_posterior=posterior,
        regime_change_probability=regime,
        active_regime="test",
        observed_location_id=first,
        base_location_distribution={first: 0.7, second: 0.3},
    )


def test_design_freezes_eight_arms_and_disjoint_seed_phases() -> None:
    design = load_frozen_residual_design(ROOT / DEFAULT_MANIFEST)
    holdout = _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)

    assert set(design.search_spaces) == {arm.value for arm in ResidualArm}
    assert len(design.training_seeds) == 8
    assert len(design.validation_seeds) == 4
    assert len(holdout) == 12
    assert set(design.training_seeds).isdisjoint(design.validation_seeds)
    assert set(design.training_seeds).isdisjoint(holdout)
    assert set(design.validation_seeds).isdisjoint(holdout)


def test_inference_firewall_excludes_action_target_and_latent_state() -> None:
    assert not (set(FEATURE_NAMES) & FORBIDDEN_INFERENCE_INPUTS)
    assert all("oracle" not in feature and "latent" not in feature for feature in FEATURE_NAMES)


def test_residual_gate_training_and_runtime_are_deterministic() -> None:
    design = load_frozen_residual_design(ROOT / DEFAULT_MANIFEST)
    examples = tuple(_example(float(index % 2)) for index in range(32))
    first = _train_model(examples, design.model)
    second = _train_model(examples, design.model)
    assert first.model_hash == second.model_hash
    assert first.payload()["model_type"] == "trained_structured_residual_action_advantage_gate"

    runtime = StructuredResidualParticleRuntime(
        profile="balanced",
        model=first,
        residual_scale=0.75,
        deterministic_prior=True,
    )
    runtime.revise(_belief(ChangeCause.HABIT, 0.85))
    runtime.revise(_belief(ChangeCause.ACTOR, 0.10))
    assert runtime.residual_receipts
    assert runtime.ancestry_trace


def test_residual_only_and_deterministic_prior_have_distinct_strength_semantics() -> None:
    design = load_frozen_residual_design(ROOT / DEFAULT_MANIFEST)
    model = _train_model(tuple(_example(0.5) for _ in range(16)), design.model)
    residual_only = StructuredResidualParticleRuntime(
        profile="balanced",
        model=model,
        residual_scale=0.75,
        deterministic_prior=False,
    )
    combined = StructuredResidualParticleRuntime(
        profile="balanced",
        model=model,
        residual_scale=0.75,
        deterministic_prior=True,
    )
    residual_only.revise(_belief(ChangeCause.HABIT, 0.85))
    combined.revise(_belief(ChangeCause.HABIT, 0.85))
    residual_only.revise(_belief(ChangeCause.ACTOR, 0.10))
    combined.revise(_belief(ChangeCause.ACTOR, 0.10))

    assert residual_only.residual_receipts
    assert combined.residual_receipts
    assert residual_only.particles != combined.particles
