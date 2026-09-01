from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    ApproximationMethod,
    enumerate_latent_states,
    exact_posterior,
    registered_scenarios,
    run_exact_enumeration_falsifier,
)


def test_exact_enumeration_space_and_registered_stress_design_are_complete() -> None:
    states = enumerate_latent_states()
    scenarios = registered_scenarios()

    assert len(states) == 360
    assert len({state.key for state in states}) == len(states)
    assert len(scenarios) == 16
    assert len({scenario.scenario_id for scenario in scenarios}) == 16
    for factor in (
        "high_attribution_ambiguity",
        "adverse_delayed_feedback",
        "short_regime",
        "open_world_actor",
    ):
        assert sum(bool(getattr(scenario, factor)) for scenario in scenarios) == 8


def test_exact_posterior_is_normalized_and_keeps_explicit_unresolved_mass() -> None:
    scenario = registered_scenarios()[0]
    posterior = exact_posterior(scenario.frames)

    assert sum(posterior.values()) == pytest.approx(1.0)
    assert posterior["__unresolved__"] > 0.0
    assert scenario.truth.key in posterior


def test_falsifier_runs_all_non_neural_arms_and_keeps_neural_arm_fail_closed() -> None:
    report = run_exact_enumeration_falsifier(particle_budget=24, bootstrap_seed=8701)

    assert report["protocol"] == "structure-two-exact-enumeration-falsifier@0.1"
    assert report["evidence_status"].endswith("not paper evidence")
    assert report["neural_proposer_status"] == "not_run_no_trained_artifact"
    assert set(report["method_summaries"]) == {method.value for method in ApproximationMethod}
    assert report["scenario_count"] == 16
    assert len(report["content_sha256"]) == 64
    assert all(len(value) == 64 for value in report["provenance"].values())


def test_typed_revision_passes_registered_development_conformance_gates() -> None:
    report = run_exact_enumeration_falsifier(particle_budget=24, bootstrap_seed=8701)
    typed = report["method_summaries"][ApproximationMethod.TYPED_PARTICLE_REVISION.value]
    incremental = report["method_summaries"][ApproximationMethod.INCREMENTAL_BEAM.value]
    full_rerun = report["method_summaries"][ApproximationMethod.FULL_RERUN_BEAM.value]

    assert report["all_development_gates_passed"]
    assert typed["mean_posterior_total_variation"] < incremental["mean_posterior_total_variation"]
    assert typed["mean_posterior_total_variation"] <= (
        full_rerun["mean_posterior_total_variation"] + 0.05
    )
    assert typed["mean_action_regret_against_exact_bayes"] == pytest.approx(0.0)
    assert typed["mean_candidate_evaluations"] < full_rerun["mean_candidate_evaluations"]


def test_falsifier_rejects_invalid_particle_budgets() -> None:
    with pytest.raises(ValueError, match="particle_budget"):
        run_exact_enumeration_falsifier(particle_budget=1)
    with pytest.raises(ValueError, match="particle_budget"):
        run_exact_enumeration_falsifier(particle_budget=360)
