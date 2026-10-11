"""Sharing, causal history correction and native event-time readiness."""

import copy
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from run_shared_location import dataset_for, evaluate
from score_shared_location import score_run

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_current_location import execute_current_search
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.evaluation_operations.structure_two_shared_location import (
    SharedLocationBelief,
    SharedLocationConfig,
)
from cpswm.system.reproducibility import content_sha256

LOCS = [str(UUID(int=i)) for i in (10, 11)]


def setup(config=None, targets=(10, 11, 10, 11)):
    steps = [
        SimpleNamespace(step_id=UUID(int=20 + i), object_instance_id=UUID(int=3))
        for i in range(len(targets))
    ]
    episode = SimpleNamespace(episode_id=UUID(int=1), steps=steps)
    truth = {step.step_id: UUID(int=target) for step, target in zip(steps, targets, strict=True)}
    env = ExecutedD0SearchEnvironment(episode, tuple(map(UUID, LOCS)), truth.__getitem__)
    head = SharedLocationBelief(
        LOCS, ("a", "b"), config or SharedLocationConfig("joint", 0.25, 0.9, 2, 2)
    )
    projections = [
        {
            "step_id": str(s.step_id),
            "object_id": str(s.object_instance_id),
            "view": "cue_only",
            "actor_cue": {"a": 0.8, "b": 0.2},
            "visible_location": None,
        }
        for s in steps
    ]
    return head, env, projections


def test_sharing_transfers_actor_location_information_into_unseen_context():
    pooled, env, inputs = setup(SharedLocationConfig("joint", 0.25, 0.9, 2, 0))
    execute_current_search(pooled, inputs[0], env)
    raw, _, _ = setup(SharedLocationConfig("joint", 0.25, 0.9))
    raw.history = copy.deepcopy(pooled.history)
    raw.previous = pooled.previous
    pooled.begin(inputs[1])
    raw.begin(inputs[1])
    assert raw.location_distribution()[LOCS[0]] == pytest.approx(0.5)
    expected = 0.8 * ((0.0625 + 0.9875 / 1.175) / 1.125)
    expected += 0.2 * ((0.0625 + 0.3875 / 0.575) / 1.125)
    assert pooled.location_distribution()[LOCS[0]] == pytest.approx(expected)


def test_paid_withdrawal_changes_next_action_and_restore_recovers_it():
    results = {}
    for mode in ("control", "withdraw", "restore"):
        head, env, inputs = setup()
        for inp in inputs[:2]:
            execute_current_search(head, inp, env)
        source = head.source_digest(inputs[1]["step_id"])
        if mode != "control":
            head.revise_location_source(inputs[1]["step_id"], source)
        if mode == "restore":
            head.revise_location_source(inputs[1]["step_id"], source, restore=True)
        results[mode] = execute_current_search(head, inputs[2], env)
    assert results["control"] == results["restore"]
    assert results["control"]["planned_order"][0] == LOCS[1]
    assert results["withdraw"]["planned_order"][0] == LOCS[0]
    assert results["control"]["paid_checks"] == 2 and results["withdraw"]["paid_checks"] == 1


def test_withdrawal_rebuilds_descendant_edges_keeps_elapsed_slots_and_original_actions():
    head, env, inputs = setup()
    for inp in inputs[:3]:
        execute_current_search(head, inp, env)
    original = copy.deepcopy(head.records)
    table_before = head.table()
    source = head.source_digest(inputs[1]["step_id"])
    receipt = head.revise_location_source(inputs[1]["step_id"], source)
    assert len(head.history) == 3
    assert head.history[1]["found"] is None
    assert head.history[2]["previous"] == LOCS[0]
    assert head.records == original
    assert receipt["receipt_sha256"] == content_sha256(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    )
    # Independent weighted count: tick 0 still decays twice; withdrawn tick remains.
    raw = copy.deepcopy(head.history)
    assert head.config.decay ** (len(raw) - 1) == pytest.approx(0.81)
    head.revise_location_source(inputs[1]["step_id"], source, restore=True)
    assert head.table() == table_before and head.records == original


@pytest.mark.parametrize(
    "attack",
    ["unknown", "wrong_hash", "duplicate_withdraw", "restore_active", "pending", "mutated_source"],
)
def test_invalid_source_revisions_are_atomic(attack):
    head, env, inputs = setup()
    execute_current_search(head, inputs[0], env)
    step_id = inputs[0]["step_id"]
    source = head.source_digest(step_id)
    if attack == "duplicate_withdraw":
        head.revise_location_source(step_id, source)
    if attack == "pending":
        head.begin(inputs[1])
    if attack == "mutated_source":
        head._sources[step_id][0]["found"] = LOCS[1]
    before = (copy.deepcopy(head.history), head.previous, copy.deepcopy(head.revision_receipts))
    with pytest.raises(ValueError):
        head.revise_location_source(
            "unknown" if attack == "unknown" else step_id,
            "0" * 64 if attack == "wrong_hash" else source,
            restore=attack == "restore_active",
        )
    assert (head.history, head.previous, head.revision_receipts) == before


@pytest.mark.parametrize(
    "sharing,persistence", [(-1, 0), (float("nan"), 0), (0, float("inf")), (0, -1)]
)
def test_invalid_augmented_mass_is_rejected(sharing, persistence):
    with pytest.raises(ValueError):
        SharedLocationConfig("joint", sharing=sharing, persistence=persistence)


def test_full_adapter_matches_isolated_and_exposes_missing_event_time_binding():
    dataset = dataset_for("sparse32", seeds=[65001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    config = SharedLocationConfig("joint", 0.25, 0.9, 2, 2)
    isolated = evaluate(dataset, episode, config, "cue_only")
    integrated = evaluate(dataset, episode, config, "cue_only", integrate=True)
    assert integrated["actions"] == isolated["actions"]
    counts, _ = score_run(
        json.loads(json.dumps(integrated)),
        episode.model_dump(mode="json"),
        dataset.truth_for(episode.episode_id).model_dump(mode="json"),
    )
    assert counts["n"] == 32
    for audit in integrated["native_time_audits"]:
        assert not audit["location_factor_applied_to_native"]
        assert audit["native_binds_current_transition"] == audit["original_location_visible"]
    assert any(not a["current_transition_exists"] for a in integrated["native_time_audits"])
    assert any(a["current_transition_exists"] for a in integrated["native_time_audits"])
