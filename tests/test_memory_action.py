import copy
from dataclasses import replace

import pytest
from run_matched_value import dataset_for, make_state
from run_short_history_reference import fixed_inputs

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController
from cpswm.system.evaluation_operations.structure_two_memory_action import (
    MemoryActionRuntime,
    NativeGoalMemory,
    owner_habit_readout,
    projection_observation,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def runtime():
    _, config, model, observations, _ = fixed_inputs()[0]
    r = MemoryActionRuntime(arm=FullJointArm.STATEFUL_FULL_JOINT, config=config, neural_model=model)
    return r, observations


def test_absent_evidence_is_not_explicit_zero_even_after_location_update():
    r, obs = runtime()
    missing = replace(
        obs[0],
        prediction_only=True,
        observed_location_id=None,
        position_source_id=None,
        location_likelihood=(),
        regime_change_probability=0.0,
    )
    absent = projection_observation(missing)
    explicit = replace(absent, regime_evidence_available=True)
    deltas = [
        r._main_log_factor(absent, c) - r._main_log_factor(explicit, c)
        for c, _ in r._candidates(absent, None)
    ]
    assert max(deltas) > 690
    paid = replace(absent, prediction_only=False, observed_location_id=obs[0].observed_location_id)
    assert paid.regime_evidence_available is False
    assert projection_observation(explicit) is explicit
    with pytest.raises(ValueError):
        replace(absent, regime_evidence_available=0)


def test_readout_consumes_all_rb_blocks_not_current_mover_and_never_mutates():
    r, observations = runtime()
    for obs in observations:
        r.revise(obs)
    before = r._state_sha256()
    dist, receipt = owner_habit_readout(r)
    assert r._state_sha256() == before
    assert sum(dist.values()) == pytest.approx(1)
    assert receipt["consumed_mass"] > 0
    # Change current actor alone, with admitted owner cells held fixed. Current
    # actor is not the query owner; historical cell attribution is unchanged.
    other = copy.deepcopy(r)
    owner = r._last_observation.owner_actor_key
    guest = next(a for a in r._last_observation.actor_posterior if a != owner)
    altered = []
    for p in other.particles:
        roles = p.world.ordered_actor_role_history[-1]
        changed = tuple(role.model_copy(update={"actor_key": guest}) for role in roles)
        world = replace(
            p.world, ordered_actor_role_history=(*p.world.ordered_actor_role_history[:-1], changed)
        )
        altered.append(replace(p, world=world))
    other.particles = tuple(altered)
    assert owner_habit_readout(other)[0] == pytest.approx(dist)
    # Removing admitted content must remove its contribution, not just the receipt.
    for p in other.particles:
        p.world.rb_cells.clear()
    reset, reset_receipt = owner_habit_readout(other)
    assert reset == pytest.approx(r._last_observation.base_location_distribution)
    assert reset_receipt["consumed_mass"] == 0


def test_real_d0_runtime_binds_goal_and_rejects_forged_or_stale_plan():
    from test_memory_goal_control import visual

    episode = dataset_for("sparse32").visible_episodes(Split.TEST)[0]
    state = make_state(episode, "native_joint")
    old = state.runtime
    state.runtime = MemoryActionRuntime(
        arm=old.arm, config=old.config, neural_model=old.neural_model
    )
    for step in episode.steps[:2]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    bindings = {loc: f"place-{i}" for i, loc in enumerate(episode.known_location_ids)}
    memory = NativeGoalMemory(state.runtime, bindings)
    catalogue = {v: "put target at " + v for v in bindings.values()}
    camera = replace(visual(), episode_id=str(episode.episode_id))
    controller = MemoryGoalController(str(episode.episode_id), catalogue, native_memory=memory)
    controller.observe_visual(camera, 100)
    first = GoalPlan.from_payload(controller.plan(100)["plan"])
    expected = min(
        state.runtime.action_distribution(),
        key=lambda k: (-state.runtime.action_distribution()[k], str(k)),
    )
    assert first.command.destination == bindings[expected]
    with pytest.raises(ValueError):
        controller.validate(replace(first, prompt="forged but otherwise complete"))
    step = episode.steps[2]
    state.observe(step)
    state.predict()
    state.feedback(step)
    with pytest.raises(ValueError):
        controller.validate(first)
    second = GoalPlan.from_payload(controller.plan(101)["plan"])
    assert second.goal_memory_revision != first.goal_memory_revision
    assert controller.audit()["semantic_memory"]["memory_source"] == "live_native_posterior"
    with pytest.raises(ValueError):
        controller.observe_history(camera, 102)
    with pytest.raises(ValueError):
        NativeGoalMemory(state.runtime, {next(iter(bindings)): "only"})
