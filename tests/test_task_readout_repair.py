"""Action-level readout boundaries on the real stateful feedback path."""

from dataclasses import asdict
from uuid import UUID

import pytest
from run_task_readout_repair import choose, evaluate

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    habit_readout_profile,
    task_separated_prediction,
)
from cpswm.system.runtime_readout import current_action_readout


def test_conflicting_task_targets_remain_distinct():
    habit, current = UUID(int=1), UUID(int=2)
    native = _Prediction(habit, (current, habit), 0.2)
    got = task_separated_prediction({habit: 0.9, current: 0.1}, native, unknown_probability=0.3)
    assert got.put_back == habit
    assert got.search_order == (current, habit)
    assert got.unknown_probability == 0.3


@pytest.mark.parametrize(
    "mass,unknown",
    [
        ({}, 0),
        ({UUID(int=1): float("nan")}, 0),
        ({UUID(int=1): -1}, 0),
        ({UUID(int=1): 0}, 0),
        ({UUID(int=1): 1}, float("inf")),
    ],
)
def test_invalid_outputs_fail_closed(mass, unknown):
    with pytest.raises(ValueError):
        task_separated_prediction(
            mass, _Prediction(UUID(int=1), (UUID(int=1),), 0), unknown_probability=unknown
        )


def test_profiles_change_only_explicit_readout_weights_and_ties_keep_v06():
    original = asdict(current_action_readout())
    for profile in ("v06", "balanced", "slow"):
        candidate = asdict(habit_readout_profile(profile))
        assert {
            k: v
            for k, v in candidate.items()
            if k not in ("fast_action_weight", "surviving_revision_weight", "regime_local_weight")
        } == {
            k: v
            for k, v in original.items()
            if k not in ("fast_action_weight", "surviving_revision_weight", "regime_local_weight")
        }
    assert (
        choose(
            [
                {"parameter": p, "cumulative_action_regret_per_step": 0.2}
                for p in ("v06", "balanced", "slow")
            ]
        )
        == "v06"
    )


def test_real_feedback_keeps_put_back_and_binds_final_search():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(7,),
        test_seeds=(30,),
        max_steps_per_episode=10,
        guest_window=(2, 5),
        scenario_duration_days=10,
        abrupt_day=7,
        recurrence_day=9,
        sealed_secret="task-readout-unit-only",
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    legacy = evaluate(dataset, episode, "legacy", "v06")
    split = evaluate(dataset, episode, "joint", "v06")
    assert [r["put_back"] for r in legacy["actions"]] == [r["put_back"] for r in split["actions"]]
    assert any(
        a["search_order"] != b["search_order"]
        for a, b in zip(legacy["actions"], split["actions"], strict=True)
    )
    assert split["metric"]["search_error_rate"] < legacy["metric"]["search_error_rate"]
    traces = split["metric"]["revision_action_traces"]
    assert traces
    for row in split["actions"]:
        receipt = row["task_readout"]
        assert receipt["search_order"] == row["search_order"] == receipt["native_search_order"]
    for trace in traces:
        index = trace["planner_prediction_index"]
        if index is not None:
            output = trace["next_action_distribution"]
            put = [r["location_id"] for r in output if r["action"] == "put_back"]
            search = [
                r["location_id"]
                for r in sorted(output, key=lambda r: -r["probability"])
                if r["action"] == "search"
            ]
            assert put == [split["actions"][index]["put_back"]]
            assert search == split["actions"][index]["search_order"]


def test_slow_profile_can_change_real_actions_with_live_long_term_state():
    from run_task_readout_repair import dataset_for

    dataset = dataset_for("sparse32", (30,))
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    fast = evaluate(dataset, episode, "joint", "v06")
    slow = evaluate(dataset, episode, "joint", "slow")
    changed = [
        (a, b)
        for a, b in zip(fast["actions"], slow["actions"], strict=True)
        if a["put_back"] != b["put_back"]
    ]
    assert changed
    assert any(b["committed"] > 0 for _, b in changed)
    assert slow["metric"]["full_feedback_revision_calls"] > 0
    assert slow["runtime_audit"]["fairness_receipts"]


def test_cold_start_and_direct_feedback_binding():
    from run_task_readout_repair import ROOT, dataset_for

    from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm
    from cpswm.system.evaluation_operations.structure_two_task_readout import (
        build_task_separated_full_joint_state,
    )

    dataset = dataset_for("complete32", (30,))
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    state = build_task_separated_full_joint_state(
        repository_root=ROOT, dataset=dataset, episode=episode, arm=FullJointArm.STATEFUL_FULL_JOINT
    )
    state.predict()
    assert state.task_readout_receipts[-1].joint_cold_start
    bound = 0
    for step in episode.steps[:10]:
        state.observe(step)
        prediction = state.predict()  # No evaluator rebinding is involved here.
        index = state.task_readout_receipts[-1].prediction_index
        for trace in state.revision_action_traces:
            if trace.planner_prediction_index == index:
                search = [
                    p.location_id
                    for p in sorted(trace.next_action_distribution, key=lambda p: -p.probability)
                    if p.action.value == "search"
                ]
                assert tuple(search) == prediction.search_order
                bound += 1
        state.feedback(step)
    assert bound > 0


@pytest.mark.parametrize("rank", [(UUID(int=1),), (UUID(int=1), UUID(int=1))])
def test_incomplete_or_duplicate_search_support_is_rejected(rank):
    with pytest.raises(ValueError):
        task_separated_prediction(
            {UUID(int=1): 0.9, UUID(int=2): 0.1},
            _Prediction(UUID(int=1), rank, 0.1),
            unknown_probability=0.1,
        )
