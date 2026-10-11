"""Bounded oracle search: paid evidence, local memory, and actual feedback output."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from run_active_location_search import dataset_for, evaluate
from score_active_location_search import completion_cost, score_run

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    D0LocationInspectionEnvironment,
    LocationInspectionRequest,
)
from cpswm.system.reproducibility import content_sha256


def fixture_environment(budget=2):
    episode = SimpleNamespace(
        episode_id=UUID(int=1),
        steps=[
            SimpleNamespace(step_id=UUID(int=2), object_instance_id=UUID(int=3)),
            SimpleNamespace(step_id=UUID(int=4), object_instance_id=UUID(int=3)),
        ],
    )
    accesses = []

    def truth(step):
        assert env.requests and env.requests[-1].step_id == step
        accesses.append(step)
        return UUID(int=12)

    env = D0LocationInspectionEnvironment(
        episode, [UUID(int=k) for k in (10, 11, 12)], truth, budget=budget
    )

    def request(location, identity=20, step=2):
        return LocationInspectionRequest(
            UUID(int=identity), episode.episode_id, UUID(int=step), UUID(int=3), UUID(int=location)
        )

    return env, accesses, request


def test_queries_pay_before_truth_and_return_no_other_location():
    env, access, request = fixture_environment()
    assert not access
    env.begin_step(UUID(int=2))
    negative = env.inspect(request(10))
    positive = env.inspect(request(12, 21))
    assert negative.found is False and positive.found is True
    assert negative.ordinal == 1 and positive.ordinal == 2 and len(access) == 2
    assert set(negative.__dataclass_fields__) == {"request", "ordinal", "found", "receipt_sha256"}
    env.validate_receipt(request(10), negative)
    assert len(env.requests) == 2


def test_complete_forged_receipt_rejected_even_with_recomputed_hash():
    env, _, request = fixture_environment()
    env.begin_step(UUID(int=2))
    req = request(10)
    real = env.inspect(req)
    forged = replace(
        real,
        found=True,
        receipt_sha256=content_sha256({"request": req, "ordinal": 1, "found": True}),
    )
    with pytest.raises(ValueError, match="not issued"):
        env.validate_receipt(req, forged)
    env.validate_receipt(req, real)


@pytest.mark.parametrize(
    "attack",
    [
        "before_step",
        "wrong_step",
        "wrong_object",
        "wrong_episode",
        "outside",
        "duplicate_location",
        "duplicate_id",
        "budget",
        "stale_receipt",
        "repeat_step",
    ],
)
def test_query_boundaries_reject_without_extra_truth_access(attack):
    env, access, request = fixture_environment()
    if attack == "before_step":
        with pytest.raises(ValueError):
            env.inspect(request(10))
        assert not access
        return
    env.begin_step(UUID(int=2))
    real = env.inspect(request(10))
    count = len(access)
    with pytest.raises(ValueError):
        if attack == "wrong_step":
            env.inspect(request(11, 21, 4))
        elif attack == "wrong_object":
            env.inspect(replace(request(11, 21), object_id=UUID(int=99)))
        elif attack == "wrong_episode":
            env.inspect(replace(request(11, 21), episode_id=UUID(int=99)))
        elif attack == "outside":
            env.inspect(request(99, 21))
        elif attack == "duplicate_location":
            env.inspect(request(10, 21))
        elif attack == "duplicate_id":
            env.inspect(request(11))
        elif attack == "budget":
            env.inspect(request(11, 21))
            count += 1
            env.inspect(request(12, 22))
        elif attack == "stale_receipt":
            env.begin_step(UUID(int=4))
            env.validate_receipt(request(10), real)
        else:
            env.begin_step(UUID(int=2))
    assert len(access) == count


def test_real_missing_observation_loop_preserves_put_and_binds_feedback():
    dataset = dataset_for("sparse32", (30,))
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    passive = evaluate(dataset, episode, "passive")
    active = evaluate(dataset, episode, "current_rank")
    assert [a["put_back"] for a in passive["actions"]] == [a["put_back"] for a in active["actions"]]
    assert sum(len(a["active_search"]["inspections"]) for a in active["actions"]) > 0
    assert any(a["active_search"]["found_location"] is not None for a in active["actions"])
    assert any(not r["found"] for a in active["actions"] for r in a["active_search"]["inspections"])
    assert all(
        not a["active_search"]["location_query_changed_habit_state"] for a in active["actions"]
    )
    counts, _ = score_run(
        active,
        episode.model_dump(mode="json"),
        dataset.truth_for(episode.episode_id).model_dump(mode="json"),
    )
    assert counts["charged_completion_inspections"] >= counts["queries"] > 0
    for trace in active["metric_post_query_uncharged"]["revision_action_traces"]:
        i = trace["planner_prediction_index"]
        if i is None:
            continue
        order = [
            p["location_id"]
            for p in sorted(trace["next_action_distribution"], key=lambda p: -p["probability"])
            if p["action"] == "search"
        ]
        assert order == active["actions"][i]["search_order"]


@pytest.mark.parametrize(
    "order,negatives,found,queries,target,expected",
    [
        (["a", "b", "c"], [], None, 0, "c", (3, 3, True, 1.0)),
        (["c", "b", "a"], ["a"], "c", 2, "c", (2, 0, True, 0.5)),
        (["c", "a", "b"], ["a", "b"], None, 2, "c", (3, 1, True, 1.0)),
        (["c", "a", "b"], ["a", "b"], None, 2, "outside", (3, 1, False, 1.0)),
        (["a", "b", "c"], [], "a", 1, "a", (1, 0, True, 0.0)),
    ],
)
def test_independent_cost_includes_paid_queries_and_counts_support_failures(
    order, negatives, found, queries, target, expected
):
    assert completion_cost(order, negatives, found, queries, target) == expected
