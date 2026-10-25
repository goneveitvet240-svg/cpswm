"""Read-only gate witnesses, harmful-history counterexample, and native replay."""

import copy
from dataclasses import replace

import pytest
from run_joint_three_questions import (
    HistoryReadRuntime,
    eligible,
    experimental_state,
    paired_counts,
    scalar_read,
    write_state,
)
from run_matched_value import dataset_for, make_state
from run_short_history_reference import fixed_inputs
from test_matched_readout import hand_raw

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def test_actor_read_restores_history_and_preserves_instance_guard():
    raw = hand_raw()
    raw["particles"][0]["actor"] = "guest"
    before = copy.deepcopy(raw)
    assert scalar_read(raw, "original")["distribution"] == raw["base"]
    assert scalar_read(raw, "actor_read")["distribution"] == pytest.approx(
        {"left": 0.53, "right": 0.47}
    )
    raw["particles"][0]["instance"] = "other_instance"
    assert scalar_read(raw, "actor_read")["distribution"] == raw["base"]
    assert scalar_read(raw, "history_read")["distribution"] == pytest.approx(
        {"left": 0.53, "right": 0.47}
    )
    raw["particles"][0]["instance"] = "target_instance"
    assert raw == before


def test_valid_history_can_help_or_harm_without_any_new_write():
    raw = hand_raw()
    p = raw["particles"][0]
    p["actor"] = "guest"
    p["weight"] = 1
    p["owner_cell"]["information_natural"] = 1.8
    before = copy.deepcopy(raw)
    base = scalar_read(raw, "original")["action"]
    variant = scalar_read(raw, "actor_read")["action"]
    assert base == "left" and variant == "right"
    assert paired_counts([base], [variant], ["right"])["fixed"] == 1
    assert paired_counts([base], [variant], ["left"])["harmed"] == 1
    assert raw == before


def test_empty_or_unlearned_history_cannot_invent_evidence():
    raw = hand_raw()
    p = raw["particles"][0]
    p["actor"] = "guest"
    p["owner_cell"] = None
    assert scalar_read(raw, "history_read")["distribution"] == raw["base"]
    p["owner_cell"] = hand_raw()["particles"][0]["owner_cell"]
    p["owner_cell"]["information_natural"] = 0
    assert scalar_read(raw, "history_read")["distribution"] == raw["base"]


def test_wrong_policy_support_and_pair_alignment_are_rejected():
    with pytest.raises(ValueError, match="unknown"):
        eligible("a", "b", "c", "unregistered")
    with pytest.raises(ValueError, match="unaligned"):
        paired_counts(["a"], [], ["a"])
    raw = hand_raw()
    raw["locations"] = ["left", "left"]
    with pytest.raises(ValueError, match="support"):
        scalar_read(raw, "actor_read")


def test_paired_report_keeps_regressions_and_both_wrong_changes():
    result = paired_counts(["a", "b", "c", "x"], ["b", "a", "d", "x"], ["b", "b", "z", "x"])
    assert result == dict(points=4, errors=2, fixed=1, harmed=1, changed_actions=3, both_wrong=1)


@pytest.fixture(scope="module")
def native_inputs():
    return fixed_inputs()[0]


def test_native_owner_then_visitor_preserves_owner_cell_and_write_reads(native_inputs):
    _, config, model, observations, _ = native_inputs
    runtime = HistoryReadRuntime(
        read_policy="actor_read",
        arm=FullJointArm.STATEFUL_FULL_JOINT,
        config=config,
        neural_model=model,
    )
    runtime.revise(copy.deepcopy(observations[0]))
    observation = runtime._last_observation
    owner = observation.owner_actor_key
    guest = next(a for a in observation.actor_posterior if a != owner)
    template = next(
        p for p in runtime.particles if (owner, p.world.active_regime) in p.world.rb_cells
    )
    # Construct a legal visitor successor of a genuinely written owner history.
    runtime.step_index = 2
    successor_observation = observations[1]
    candidate = next(
        c
        for c, _ in runtime._candidates(successor_observation, template)
        if c.placement_actor == guest
        and c.instance_association_key == "target_instance"
        and c.active_regime_after == template.world.active_regime
    )
    from cpswm.system.reproducibility import content_uuid

    world = runtime._world_from_candidate(
        parent=template,
        candidate=candidate,
        observation=successor_observation,
        draw_index=0,
        snapshot_id=content_uuid("gate-test", "visitor"),
    )
    world.validate_complete()
    assert (
        world.rb_cells[owner, world.active_regime]
        == template.world.rb_cells[owner, template.world.active_regime]
    )
    runtime.particles = (replace(template, world=world, posterior_probability=0.95),)
    runtime._last_observation = successor_observation
    before = write_state(runtime)
    from types import SimpleNamespace

    from analyze_matched_readout import capture

    raw = capture(SimpleNamespace(runtime=runtime))
    assert raw["actual"] == pytest.approx(scalar_read(raw, "actor_read")["distribution"])
    assert runtime._posterior_action_distribution(
        successor_observation, include_ledger=False
    ) == pytest.approx(successor_observation.base_location_distribution)
    assert write_state(runtime) == before


@pytest.mark.parametrize("policy", ["actor_read", "history_read"])
def test_actual_native_read_matches_scalar_and_keeps_feedback_contract(policy):
    from analyze_matched_readout import capture

    ds = dataset_for("complete32")
    episode = ds.visible_episodes(Split.TEST)[0]
    s = experimental_state(episode, "native_joint", policy)
    original = make_state(episode, "native_joint")
    for step in episode.steps[:4]:
        original.observe(step)
        original.predict()
        s.observe(step)
        before = write_state(s.runtime)
        s.predict()
        raw = capture(s)
        assert scalar_read(raw, policy)["distribution"] == pytest.approx(raw["actual"], abs=1e-12)
        assert write_state(s.runtime) == before == write_state(original.runtime)
        s.feedback(step)
        original.feedback(step)
        s.runtime.verify_internal_contracts()
