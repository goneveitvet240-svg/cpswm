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


def test_paid_source_withdrawal_restores_typed_evidence_and_habit_distribution():
    from test_current_event import advance, data, state_for

    inputs = data.__wrapped__()
    state = state_for(inputs)
    old = state.runtime
    state.runtime = MemoryActionRuntime(
        arm=old.arm, config=old.config, neural_model=old.neural_model
    )
    advance(state, inputs[1].steps[:4])
    r = state.runtime
    source_id = next(iter(r.location_sources))
    source = r.location_sources[source_id]
    assert source["original"].regime_evidence_available is False
    assert source["updated"].regime_evidence_available is False
    before = r._state_sha256()
    distribution, receipt = owner_habit_readout(r)
    r.revise_location_source(source_id, source["sha256"])
    assert r._state_sha256() != before
    r.revise_location_source(source_id, source["sha256"], restore=True)
    assert r._state_sha256() == before
    restored, restored_receipt = owner_habit_readout(r)
    assert restored == distribution and restored_receipt == receipt
    r.verify_internal_contracts()


@pytest.mark.parametrize("attack", ["typed_regime", "actor", "position", "operation"])
def test_typed_source_replay_rejects_semantically_changed_complete_input(attack):
    from test_current_event import advance, data, state_for

    inputs = data.__wrapped__()
    state = state_for(inputs)
    old = state.runtime
    state.runtime = MemoryActionRuntime(
        arm=old.arm, config=old.config, neural_model=old.neural_model
    )
    advance(state, inputs[1].steps[:2])
    r = state.runtime
    source_id = next(iter(r.location_sources))
    source = r.location_sources[source_id]
    before = r._state_sha256()
    if attack == "typed_regime":
        kind, payload, digest = r.operations[0]
        r.operations[0] = (kind, replace(payload, regime_evidence_available=True), digest)
    elif attack == "actor":
        source["payload"]["location_likelihood"] = (("owner", 1.0),)
    elif attack == "position":
        source["payload"]["paid_updates"][-1]["receipt"]["found"] = False
    else:
        kind, payload, digest = r.operations[0]
        r.operations[0] = ("feedback", payload, digest)
    with pytest.raises((ValueError, AttributeError)):
        r.revise_location_source(source_id, source["sha256"])
    assert r._state_sha256() == before


def test_goal_revision_binds_actual_rb_content_not_only_native_history_labels():
    from native_goal_worker import controller_for

    controller, _ = controller_for()
    memory = controller.memory
    old_revision = memory.revision
    old_native = memory.runtime._state_sha256()
    # A complete valid-shaped replacement preserves event/role/regime labels.
    # It must STILL invalidate the previously bound memory revision.
    for particle in memory.runtime.particles:
        for key, cell in list(particle.world.rb_cells.items()):
            particle.world.rb_cells[key] = replace(
                cell,
                location_alpha=tuple(reversed(cell.location_alpha)),
                ridge_precision=tuple(reversed(cell.ridge_precision)),
                ridge_natural=tuple(reversed(cell.ridge_natural)),
            )
    assert memory.runtime._state_sha256() == old_native
    assert memory.revision != old_revision
