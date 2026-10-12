from __future__ import annotations

import copy
from dataclasses import replace
from uuid import uuid4

import pytest
from run_current_event import build, dataset_for

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_current_event import missing_event_observation
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm
from cpswm.system.reproducibility import content_uuid


@pytest.fixture(scope="module")
def data():
    dataset = dataset_for("sparse32", [66001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    assert episode.steps[0].after is None
    return dataset, episode


def state_for(data, *, consume=True, arm=FullJointArm.STATEFUL_FULL_JOINT):
    return build(*data, arm, consume_new=consume)


def advance(state, steps):
    for step in steps:
        state.observe(step)
        state.predict()
        state.feedback(step)


def test_missing_event_has_current_binding_no_location_writes(data):
    s = state_for(data)
    step = data[1].steps[0]
    s.observe(step)
    o = s.runtime._last_observation
    assert o.source_update_id == content_uuid(
        "current-event-prediction", (data[1].episode_id, step.step_id, step.object_instance_id)
    )
    assert o.observed_location_id is None and o.prediction_only
    assert s.runtime.step_index == 1 and all(not p.world.rb_cells for p in s.runtime.particles)
    assert not s.runtime.rgrc_ledger.records
    s.runtime.verify_internal_contracts()


def test_real_paid_evidence_replaces_same_event_and_reaches_native_statistics(data):
    s = state_for(data)
    step = data[1].steps[0]
    s.observe(step)
    original = s.runtime._last_observation.source_update_id
    s.predict()
    assert s.runtime.step_index == 1 and len(s.runtime.fairness_receipts) == 1
    assert all(len(p.world.event_chain) == 1 for p in s.runtime.particles)
    assert s.runtime._last_observation.source_update_id == original
    assert s.runtime._last_observation.position_source_id is not None
    assert any(p.world.rb_cells for p in s.runtime.particles)
    for receipt in s.runtime.importance_revision_receipts[-1]:
        assert receipt.evidence_semantics == "posterior_projection_with_independent_likelihood"
        assert receipt.independent_observation_source_id != receipt.source_posterior_snapshot_id
    s.feedback(step)
    s.runtime.verify_internal_contracts()


def test_observed_location_not_double_counted_and_missing_step_count_preserved(data):
    s = state_for(data)
    advance(s, data[1].steps[:6])
    assert s.runtime.step_index == 6
    for step, row in zip(data[1].steps[:6], s.event_actions, strict=True):
        if step.after is not None:
            assert row["location_source_id"] is None
    assert len({r["event_id"] for r in s.event_actions}) == 6


def test_native_withdrawal_replays_causal_suffix_and_restores(data):
    s = state_for(data)
    advance(s, data[1].steps[:6])
    r = s.runtime
    source_id = next(iter(r.location_sources))
    digest = r.location_sources[source_id]["sha256"]
    original = r._state_sha256()
    ledger = r.rgrc_ledger.head_hash
    actions = copy.deepcopy(s.event_actions)
    readouts = copy.deepcopy(r.action_readout_traces)
    r.revise_location_source(source_id, digest)
    assert r.step_index == 6 and r._state_sha256() != original
    assert s.event_actions == actions and r.action_readout_traces == readouts
    r.revise_location_source(source_id, digest, restore=True)
    assert r._state_sha256() == original and r.rgrc_ledger.head_hash == ledger
    r.verify_internal_contracts()


@pytest.mark.parametrize(
    "attack", ["wrong_hash", "unknown", "restore_active", "mutated_source", "mutated_operation"]
)
def test_revision_rejects_invalid_source_atomically(data, attack):
    s = state_for(data)
    advance(s, data[1].steps[:2])
    r = s.runtime
    sid = next(iter(r.location_sources))
    digest = r.location_sources[sid]["sha256"]
    restore = False
    if attack == "wrong_hash":
        digest = "0" * 64
    elif attack == "unknown":
        sid = uuid4()
    elif attack == "restore_active":
        restore = True
    elif attack == "mutated_source":
        r.location_sources[sid]["payload"]["step_id"] = "forged"
    else:
        next(p for k, p, _ in r.operations if k == "observation").actor_posterior["owner"] = 0.9
    state = r._state_sha256()
    ledger = r.rgrc_ledger.head_hash
    receipts = copy.deepcopy(r.location_revisions)
    with pytest.raises(ValueError):
        r.revise_location_source(sid, digest, restore=restore)
    assert r._state_sha256() == state and r.rgrc_ledger.head_hash == ledger
    assert receipts == r.location_revisions


@pytest.mark.parametrize(
    "attack", ["forged_paid", "wrong_event", "wrong_location", "duplicate", "after_feedback"]
)
def test_new_location_rejects_invalid_or_reused_binding(data, attack):
    s = state_for(data)
    advance(s, data[1].steps[:1])
    r = s.runtime
    sid = next(iter(r.location_sources))
    source = r.location_sources[sid]
    observation = source["updated"]
    payload = copy.deepcopy(source["payload"])
    if attack == "forged_paid":
        payload["paid_updates"][-1]["receipt"]["receipt_sha256"] = "0" * 64
        observation = replace(
            observation, position_source_id=content_uuid("paid-current-location", payload)
        )
    elif attack == "wrong_event":
        observation = replace(observation, source_update_id=uuid4())
    elif attack == "wrong_location":
        observation = replace(
            observation,
            observed_location_id=next(
                x for x in observation.known_location_ids if x != observation.observed_location_id
            ),
        )
    elif attack == "after_feedback":
        advance(s, data[1].steps[1:2])
    old = r._state_sha256()
    n = r.step_index
    with pytest.raises(ValueError):
        r.replace_current_location(observation, payload, s.environment)
    assert r._state_sha256() == old and r.step_index == n


def test_matching_inputs_budget_and_no_evidence_ablation(data):
    a = state_for(data)
    b = state_for(data, arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED)
    c = state_for(data, consume=False)
    for s in (a, b, c):
        advance(s, data[1].steps[:4])
    assert (
        [x["search"] for x in a.event_actions]
        == [x["search"] for x in b.event_actions]
        == [x["search"] for x in c.event_actions]
    )
    for x, y in zip(a.runtime.fairness_receipts, b.runtime.fairness_receipts, strict=True):
        assert (
            x.particle_budget == y.particle_budget
            and x.target_score_evaluations == y.target_score_evaluations
        )
        assert x.common_random_number_sha256 == y.common_random_number_sha256
        assert x.robot_visible_input_sha256 == y.robot_visible_input_sha256
    assert len(a.runtime.location_sources) > 0 and not c.runtime.location_sources


def test_prediction_cannot_claim_a_location_without_flag_change(data):
    s = state_for(data)
    o = missing_event_observation(s._state, data[1], data[1].steps[0])
    with pytest.raises(ValueError):
        replace(o, observed_location_id=o.known_location_ids[0])
    with pytest.raises(ValueError):
        replace(o, location_likelihood=(("owner", 0.5),))


def test_mixed_receipt_cannot_hide_or_reuse_sources(data):
    s = state_for(data)
    advance(s, data[1].steps[:1])
    p = s.runtime.importance_revision_receipts[-1][0]
    for changes in (
        {"independent_observation_source_id": None},
        {"independent_observation_source_id": p.source_posterior_snapshot_id},
        {"evidence_semantics": "posterior_projection_not_likelihood"},
    ):
        with pytest.raises(ValueError):
            type(p).model_validate({**p.model_dump(), **changes})
