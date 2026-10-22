"""Independent arithmetic and source-bound checks for the diagnostic reference."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest
from run_research_pilot import (
    conditional_reference,
    enumerate_update,
    normalize_logs,
    revision_stream,
    validate_readings,
)

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


class HandModel:
    config = SimpleNamespace(unresolved_prior=0.1)
    particles = (
        SimpleNamespace(posterior_probability=0.8),
        SimpleNamespace(posterior_probability=0.2),
    )

    def _candidates(self, observation, parent):
        return ((0, 0.9), (1, 0.1))

    def _transition_raw(self, parent, candidate):
        return math.log((3, 1)[candidate])

    def _constraints(self, candidate):
        return (SimpleNamespace(accepted=True, log_potential=math.log((1, 0.5)[candidate])),)

    def _observation_log_likelihood(self, observation, candidate):
        return math.log((2, 4)[candidate])

    def _main_log_factor(self, observation, candidate):
        return 0.0

    def _interaction_log_factor(self, observation, candidate):
        return 0.0


def test_enumeration_uses_parent_prior_transition_likelihood_constraint_but_not_q():
    _, logs, q, posterior = enumerate_update(HandModel(), None)
    # Hand targets: [.8*3/4*2, .8*1/4*4*.5, .2*3/4*2, .2*1/4*4*.5].
    assert [math.exp(x) for x in logs] == pytest.approx([1.2, 0.4, 0.3, 0.1])
    assert posterior == pytest.approx([0.54, 0.18, 0.135, 0.045])
    assert q == pytest.approx([0.45, 0.05, 0.45, 0.05])
    # Duplicate sampled indices retain multiplicity; importance division belongs here only.
    draws = [0, 0, 1, 3]
    weighted = normalize_logs([logs[i] - math.log(q[i]) for i in draws])
    assert weighted == pytest.approx([4 / 23, 4 / 23, 12 / 23, 3 / 23])


def test_rejected_support_is_zero_and_all_rejected_is_error():
    model = HandModel()
    model._constraints = lambda c: (SimpleNamespace(accepted=c == 0, log_potential=0.0),)
    _, _, _, p = enumerate_update(model, None)
    assert p == pytest.approx([0.72, 0, 0.18, 0])
    model._constraints = lambda c: (SimpleNamespace(accepted=False, log_potential=0.0),)
    with pytest.raises(ValueError, match="no finite"):
        enumerate_update(model, None)


def test_reference_is_invariant_to_proposal_but_not_target():
    model = HandModel()
    before = enumerate_update(model, None)[-1]
    model._candidates = lambda o, p: ((0, 0.1), (1, 0.9))
    assert enumerate_update(model, None)[-1] == before
    model._observation_log_likelihood = lambda o, c: 0.0
    assert enumerate_update(model, None)[-1] != before


@pytest.fixture(scope="module")
def native_state():
    from run_current_event import build, dataset_for

    dataset = dataset_for("sparse32", [67001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    state = build(dataset, episode, FullJointArm.STATEFUL_FULL_JOINT)
    state.observe(episode.steps[0])
    state.predict()
    state.feedback(episode.steps[0])
    state.observe(episode.steps[1])
    return state.runtime


def test_native_conditional_reference_has_matching_support_and_importance(native_state):
    before = native_state._state_sha256()
    row = conditional_reference(native_state)
    assert row["parent_count"] == 24
    assert row["max_importance_weight_error"] < 1e-10
    assert row["max_log_receipt_error"] < 1e-10
    assert row["reference_target_evaluations"] > row["sample_target_evaluations"]
    assert native_state._state_sha256() == before
    for reading in row["marginals"].values():
        assert sum(reading["reference"].values()) == pytest.approx(1)
        assert sum(reading["sampled"].values()) == pytest.approx(1)


def test_reference_detects_normalized_but_forged_particle_weights(native_state):
    import copy

    forged = copy.deepcopy(native_state)
    particles = list(forged.particles)
    mass = sum(p.posterior_probability for p in particles)
    forged.particles = tuple(
        replace(p, posterior_probability=mass / len(particles)) for p in particles
    )
    assert conditional_reference(forged)["max_importance_weight_error"] > 1e-6


@pytest.mark.parametrize("condition", ["delayed_attribution", "identity_correction"])
def test_revision_streams_have_legal_sources_and_restore_original_semantics(condition):
    _, stream = revision_stream(condition, "wrong_then_recorrect")
    active, source_ids = {}, set()
    for obs in stream:
        obs.__post_init__()
        assert obs.source_id not in source_ids
        assert obs.revises == (
            None if obs.event_id not in active else active[obs.event_id].source_id
        )
        source_ids.add(obs.source_id)
        active[obs.event_id] = obs
    for initial in stream[:3]:
        restored = active[initial.event_id]
        assert restored.actors == initial.actors
        assert restored.identity_probability == initial.identity_probability


@pytest.mark.parametrize("error", [1e-3, float("nan"), float("inf")])
def test_reporting_does_not_accept_bad_arithmetic(error):
    with pytest.raises(ValueError, match="arithmetic"):
        validate_readings({"e0": {"rows": [{"max_importance_weight_error": error}]}})


def test_false_equivalence_flag_cannot_pass_a_matching_state_hash():
    point = dict.fromkeys(("same_state", "same_ledger", "same_rb", "same_current_location"), True)
    point.update(
        rb_digest="same",
        reference_rb_digest="same",
        audit={"native_state": "same"},
        reference_state="same",
        distribution_tv=0,
        stale_command_rejected=True,
    )
    validate_readings({"e2": {"rows": [{"checkpoints": [point]}]}})
    point["same_ledger"] = False
    with pytest.raises(ValueError, match="equivalence"):
        validate_readings({"e2": {"rows": [{"checkpoints": [point]}]}})
