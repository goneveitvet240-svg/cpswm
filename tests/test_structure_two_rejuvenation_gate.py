from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    LATENT_STATES,
    registered_scenarios,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    RejuvenationMethod,
    run_structured_rejuvenation_gate,
    structured_joint_pool,
)


def test_joint_pool_is_bounded_and_contains_role_chain_proposals() -> None:
    scenario = next(
        item
        for item in registered_scenarios()
        if item.high_attribution_ambiguity and item.adverse_delayed_feedback
    )
    pool = structured_joint_pool(scenario, budget=24)

    assert 24 < len(pool.states) < len(LATENT_STATES)
    assert any(
        "mechanism_actor_physical_role_chain" in families
        for families in pool.families_by_key.values()
    )
    assert all(state.key in pool.parent_by_key for state in pool.states)


def test_preregistered_joint_rejuvenation_gate_is_complete_and_passes() -> None:
    report = run_structured_rejuvenation_gate(particle_budget=24)

    assert report["protocol"] == "structure-two-structured-rejuvenation-gate@0.2"
    assert report["neural_proposer_status"] == "not_run_no_frozen_training_artifact"
    assert report["scenario_count"] == 16
    assert set(report["method_summaries"]) == {method.value for method in RejuvenationMethod}
    assert report["all_preregistered_blocking_gates_passed"]
    assert all(report["preregistered_blocking_gates"].values())
    assert len(report["content_sha256"]) == 64
    assert all(len(value) == 64 for value in report["provenance"].values())


def test_joint_rejuvenation_reaches_full_rerun_stress_support_under_budget_gate() -> None:
    report = run_structured_rejuvenation_gate(particle_budget=24)
    summaries = report["method_summaries"]
    stress = report["stress_summaries"]
    joint = summaries[RejuvenationMethod.STRUCTURED_JOINT.value]
    full = summaries[RejuvenationMethod.FULL_RERUN.value]

    assert (
        stress[RejuvenationMethod.STRUCTURED_JOINT.value]["truth_support_rate"]
        >= stress[RejuvenationMethod.FULL_RERUN.value]["truth_support_rate"]
    )
    assert joint["mean_candidate_evaluations"] <= 0.90 * full["mean_candidate_evaluations"]


def test_joint_rejuvenation_gate_rejects_invalid_budget() -> None:
    for budget in (1, 23, 25, 360):
        with pytest.raises(ValueError, match="freezes particle_budget=24"):
            run_structured_rejuvenation_gate(particle_budget=budget)
