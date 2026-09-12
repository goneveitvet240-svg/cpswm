"""Component arithmetic/consumer tests, NOT default producer or end-to-end proof."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_posterior_projection import projected

from cpswm.contracts.grounded_search import ObservationActionCandidate
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_joint_consumption import JointDecisionView
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState
from cpswm.world_model.grounded_search.active_verification import (
    CauseInformationActiveVerificationPlanner,
    JointParticleVerificationBelief,
    VerificationCause,
)


def prior():
    return ConditionalAnalyticState(
        (UUID(int=1), UUID(int=2)),
        (1.0, 1.0),
        ((2.0, 0.0), (0.0, 2.0)),
        (0.0, 0.0),
        ((1.0, 0.0), (0.0, 1.0)),
        (0.0, 0.0),
    )


def measurement():
    return ConditionalMeasurement(
        evidence_cluster_id=UUID(int=10),
        source_record_ids=(UUID(int=11),),
        observation_model_id="unit-test-explicit-linear-model",
        location_mass=(0.25, 0.75),
        rls_features=(1.0, 2.0),
        rls_target=3.0,
        rls_weight=0.5,
        measurement=(4.0,),
        observation_matrix=((1.0, 2.0),),
        noise_covariance=((2.0,),),
        information_weight=0.5,
    )


def test_three_blocks_match_independent_scalar_equations():
    before = prior()
    state = rebuild_conditional_state(before, (measurement(),))
    assert state.alpha == (1.25, 1.75)
    assert state.a == ((2.5, 1.0), (1.0, 4.0))
    assert state.b == (1.5, 3.0)
    assert state.information == ((1.25, 0.5), (0.5, 2.0))
    assert state.information_vector == (1.0, 2.0)
    assert before == prior()
    assert state.evidence_cluster_ids == (UUID(int=10),)


def test_multivariate_observation_correlated_noise():
    item = replace(
        measurement(),
        measurement=(2.0, 3.0),
        observation_matrix=((1.0, 0.0), (0.0, 1.0)),
        noise_covariance=((2.0, 1.0), (1.0, 2.0)),
        information_weight=1.0,
    )
    state = rebuild_conditional_state(prior(), (item,))
    assert np.allclose(state.information, ((5 / 3, -1 / 3), (-1 / 3, 5 / 3)))
    assert np.allclose(state.information_vector, (1 / 3, 4 / 3))


def test_replay_retraction_and_correction_rebuild_all_blocks():
    first = measurement()
    second = replace(first, evidence_cluster_id=UUID(int=12), measurement=(8.0,))
    both = rebuild_conditional_state(prior(), (first, second))
    assert both.evidence_cluster_ids == (first.evidence_cluster_id, second.evidence_cluster_id)
    removed = rebuild_conditional_state(prior(), (second,))
    corrected = rebuild_conditional_state(prior(), (replace(first, measurement=(6.0,)), second))
    assert removed.information_vector == (2.0, 4.0)
    assert corrected.information_vector == (3.5, 7.0)
    assert rebuild_conditional_state(prior(), ()) == prior()
    reverse = rebuild_conditional_state(prior(), (second, first))
    for field in ("alpha", "a", "b", "information", "information_vector"):
        assert np.allclose(getattr(reverse, field), getattr(both, field))


@pytest.mark.parametrize(
    "changes",
    [
        {"rls_weight": -1.0},
        {"information_weight": float("nan")},
        {"rls_target": float("inf")},
        {"location_mass": (-1.0, 2.0)},
        {"location_mass": (1.0,)},
        {"rls_features": (1.0,)},
        {"noise_covariance": ((0.0,),)},
        {"noise_covariance": ((-1.0,),)},
        {"observation_matrix": ((1.0,),)},
        {"measurement": (float("nan"),)},
        {"source_record_ids": ()},
        {"observation_model_id": ""},
        {"rls_features": (1e308, 1e308)},
    ],
)
def test_invalid_measurement_has_no_partial_update(changes):
    before = prior()
    with pytest.raises(ValueError):
        rebuild_conditional_state(before, (replace(measurement(), **changes),))
    assert before == prior()


def test_repeated_cluster_and_prior_cluster_rejected():
    item = measurement()
    with pytest.raises(ValueError, match="repeated"):
        rebuild_conditional_state(prior(), (item, item))
    state = rebuild_conditional_state(prior(), (item,))
    with pytest.raises(ValueError, match="repeated"):
        rebuild_conditional_state(state, (item,))


def test_zero_information_is_preserved_not_fabricated():
    state = rebuild_conditional_state(prior(), (replace(measurement(), information_weight=0.0),))
    assert state.information == prior().information
    assert state.information_vector == prior().information_vector
    assert state.a != prior().a


def joint_problem(correlated):
    # Four complete atoms (R,I) = (0,0),(0,1),(1,0),(1,1), plus unresolved.
    atoms = [UUID(int=100 + i) for i in range(5)]
    probabilities = (0.4, 0.0, 0.0, 0.4, 0.2) if correlated else (0.2, 0.2, 0.2, 0.2, 0.2)
    belief = JointParticleVerificationBelief(
        posterior=dict(zip(atoms, probabilities, strict=True)),
        cause_by_atom={
            a: VerificationCause.HABIT if i < 4 else VerificationCause.UNRESOLVED
            for i, a in enumerate(atoms)
        },
        source_snapshot_sha256="a" * 64,
    )
    action = ObservationActionCandidate(
        action_type="micro_verify",
        label="component-test observe role",
        observation_likelihood_model_id="explicit-test-role-model",
        calibration_domain="unit-test",
        outcome_likelihoods={
            "role0": dict(zip(atoms, (1.0, 1.0, 0.0, 0.0, 0.5), strict=True)),
            "role1": dict(zip(atoms, (0.0, 0.0, 1.0, 1.0, 0.5), strict=True)),
        },
        motion_cost=0.0,
        time_cost=0.1,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    utilities = {
        UUID(int=200): dict(zip(atoms, (1.0, 0.0, 1.0, 0.0, 0.5), strict=True)),
        UUID(int=201): dict(zip(atoms, (0.0, 1.0, 0.0, 1.0, 0.5), strict=True)),
    }
    consolidation = {UUID(int=202): dict.fromkeys(atoms, 0.0)}
    return belief, action, utilities, consolidation


def select(problem, **kwargs):
    belief, action, utilities, consolidation = problem
    return CauseInformationActiveVerificationPlanner().select(
        belief,
        (action,),
        terminal_decision_utilities=utilities,
        consolidation_decision_utilities=consolidation,
        privacy_budget=kwargs.get("privacy", 1.0),
    )


def test_joint_correlation_changes_ciav_even_with_identical_marginals():
    correlated, independent = joint_problem(True), joint_problem(False)
    assert correlated[0].cause_marginal(correlated[0].posterior) == independent[0].cause_marginal(
        independent[0].posterior
    )
    yes, no = select(correlated), select(independent)
    assert yes.should_act and not no.should_act
    assert yes.scores[0].expected_cause_information_gain == pytest.approx(0.0)
    assert yes.scores[0].expected_utility_gain == pytest.approx(0.4)
    assert yes.scores[0].net_value == pytest.approx(0.3)
    assert no.scores[0].expected_utility_gain == pytest.approx(0.0)


def test_joint_privacy_blocks_profitable_verification():
    b, a, u, c = joint_problem(True)
    a = a.model_copy(update={"privacy_cost": 2.0})
    assert not select((b, a, u, c)).should_act


@pytest.mark.parametrize("attack", ["posterior", "cause", "likelihood", "utility", "duplicate"])
def test_joint_consumer_revalidates_mutable_inputs(attack):
    b, a, u, c = joint_problem(True)
    if attack == "posterior":
        b.posterior[UUID(int=100)] = 0.9
    elif attack == "cause":
        b.cause_by_atom.pop(UUID(int=100))
    elif attack == "likelihood":
        a.outcome_likelihoods["role0"][UUID(int=100)] = 0.1
    elif attack == "utility":
        u[UUID(int=200)].pop(UUID(int=104))
    with pytest.raises(ValueError):
        CauseInformationActiveVerificationPlanner().select(
            b,
            (a, a) if attack == "duplicate" else (a,),
            terminal_decision_utilities=u,
            consolidation_decision_utilities=c,
            privacy_budget=1.0,
        )


@pytest.fixture(scope="module")
def prepared_view_inputs():
    # Integration of an existing explicit seam only; NOT default candidate generation.
    core = old._legacy_history(1).system.core
    batch = core.stage_prepared_particle_candidates(**projected(core))
    return core, batch


def view(core, batch):
    return JointDecisionView.from_batch(
        runtime_id=core._particle_workspace.runtime_id,
        expected_snapshot_id=core.current_snapshot.snapshot_id,
        batch=batch,
        records=core._particle_workspace.records,
    )


def test_real_posterior_explicit_seam_view_preserves_full_state_and_has_no_commit(
    prepared_view_inputs,
):
    core, batch = prepared_view_inputs
    before = core._hybrid_loop.ledger.export_state()
    v = view(core, batch)
    assert all(a.event_chain_json and a.state_json and a.statistics for a in v.atoms)
    assert v.verification_belief().posterior[v.unresolved_id] == batch.unresolved_probability
    rows = {UUID(int=500): dict.fromkeys(v.verification_belief().posterior, 0.5)}
    assert v.expected_utilities(rows, source_belief_sha256=v.content_sha256)[
        UUID(int=500)
    ] == pytest.approx(0.5)
    assert core._hybrid_loop.ledger.export_state() == before
    with pytest.raises(ValueError, match="another joint snapshot"):
        v.expected_utilities(rows, source_belief_sha256="b" * 64)


def test_view_rejects_stale_snapshot(prepared_view_inputs):
    core, batch = prepared_view_inputs
    with pytest.raises(ValueError, match="stale"):
        JointDecisionView.from_batch(
            runtime_id=core._particle_workspace.runtime_id,
            expected_snapshot_id=uuid4(),
            batch=batch,
            records=core._particle_workspace.records,
        )


@pytest.mark.parametrize(
    "module", ["structure_two_conditional_updates", "structure_two_joint_consumption"]
)
def test_new_modules_import_without_fixture_import_order(module):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    completed = subprocess.run(
        [sys.executable, "-c", f"import cpswm.system.{module}"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_mutated_joint_objective_weights_rejected(bad):
    b, a, u, c = joint_problem(True)
    planner = CauseInformationActiveVerificationPlanner()
    planner.task_utility_weight = bad
    with pytest.raises(ValueError, match="weights"):
        planner.select(
            b,
            (a,),
            terminal_decision_utilities=u,
            consolidation_decision_utilities=c,
            privacy_budget=1.0,
        )


def test_view_consumes_actual_ciav_without_mutating_core(prepared_view_inputs):
    core, batch = prepared_view_inputs
    v = view(core, batch)
    atoms = v.verification_belief().posterior
    rows = {UUID(int=800): dict.fromkeys(atoms, 0.5)}
    action = ObservationActionCandidate(
        action_type="micro_verify",
        label="explicit seam integration only",
        observation_likelihood_model_id="unit-test-uninformative",
        calibration_domain="unit-test",
        outcome_likelihoods={"yes": dict.fromkeys(atoms, 0.5), "no": dict.fromkeys(atoms, 0.5)},
        motion_cost=0.0,
        time_cost=0.1,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    before = core._hybrid_loop.ledger.export_state()
    plan = v.select_verification(
        CauseInformationActiveVerificationPlanner(),
        (action,),
        source_belief_sha256=v.content_sha256,
        terminal_decision_utilities=rows,
        consolidation_decision_utilities=rows,
        privacy_budget=1.0,
    )
    assert not plan.should_act
    assert plan.scores[0].net_value == pytest.approx(-0.1)
    assert core._hybrid_loop.ledger.export_state() == before
