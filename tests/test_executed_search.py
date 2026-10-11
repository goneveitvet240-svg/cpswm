"""Paid completion lifecycle, causal memory and unchanged pre-execution plans."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from run_executed_search import dataset_for, evaluate
from score_executed_search import score_run

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    LocationInspectionRequest,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.reproducibility import content_sha256


def environment(target=12):
    episode = SimpleNamespace(
        episode_id=UUID(int=1),
        steps=[
            SimpleNamespace(step_id=UUID(int=i), object_instance_id=UUID(int=3)) for i in (2, 4)
        ],
    )
    accesses = []

    def truth(step):
        assert env.requests[-1].step_id == step
        accesses.append(step)
        return UUID(int=target)

    env = ExecutedD0SearchEnvironment(episode, [UUID(int=i) for i in (10, 11, 12)], truth)

    def request(loc, action=20):
        return LocationInspectionRequest(
            UUID(int=action), UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=loc)
        )

    return env, accesses, request


def test_actual_completion_pays_each_check_and_stops_at_success():
    env, accesses, request = environment()
    env.begin_step(UUID(int=2))
    env.inspect(request(10))
    env.inspect(request(11, 21))
    env.finish_probing()
    found = env.inspect(request(12, 22))
    env.validate_receipt(request(12, 22), found)
    env.close()
    assert len(accesses) == 3 and found.found
    assert [p["phase"] for p in env.step_receipts] == ["probe", "probe", "completion"]
    assert [p["receipt"]["ordinal"] for p in env.step_receipts] == [1, 2, 3]
    env.begin_step(UUID(int=4))
    assert not env.requests and env.found is None


def test_support_exhaustion_is_explicit_failure_not_false_success():
    env, accesses, request = environment(target=99)
    env.begin_step(UUID(int=2))
    env.finish_probing()
    for i, loc in enumerate((10, 11, 12)):
        assert not env.inspect(request(loc, 20 + i)).found
    env.close()
    assert env.found is None and len(accesses) == 3


@pytest.mark.parametrize(
    "attack",
    [
        "before_start",
        "unfinished_next",
        "early_close",
        "double_finish",
        "probe_overbudget",
        "after_found",
        "after_close",
        "old_phase_receipt",
        "forged_response",
    ],
)
def test_phase_and_complete_receipt_rejections_do_not_read_extra_truth(attack):
    env, accesses, request = environment()
    if attack == "before_start":
        with pytest.raises(ValueError):
            env.inspect(request(10))
        assert not accesses
        return
    env.begin_step(UUID(int=2))
    real = env.inspect(request(10))
    if attack in ("early_close", "double_finish", "after_close", "old_phase_receipt"):
        env.finish_probing()
    if attack == "after_found":
        env.inspect(request(12, 21))
    elif attack == "after_close":
        env.inspect(request(12, 21))
        env.close()
    elif attack == "probe_overbudget":
        env.inspect(request(11, 21))
    count = len(accesses)
    with pytest.raises(ValueError):
        if attack == "unfinished_next":
            env.begin_step(UUID(int=4))
        elif attack == "early_close":
            env.close()
        elif attack == "double_finish":
            env.finish_probing()
        elif attack == "old_phase_receipt":
            env.validate_receipt(request(10), real)
        elif attack == "forged_response":
            forged = replace(
                real,
                found=True,
                receipt_sha256=content_sha256(
                    {"request": real.request, "ordinal": real.ordinal, "found": True}
                ),
            )
            env.validate_receipt(request(10), forged)
        else:
            env.inspect(request(12, 22))
    assert len(accesses) == count


def test_real_execution_carries_paid_results_and_keeps_submitted_prediction():
    dataset = dataset_for("sparse32", (30,))
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    runs = {
        arm: evaluate(dataset, episode, arm)
        for arm in ("terminal_only", "current_rank", "current_no_carry")
    }
    visible = episode.model_dump(mode="json")
    truth = dataset.truth_for(episode.episode_id).model_dump(mode="json")
    counts = {arm: score_run(r, visible, truth)[0] for arm, r in runs.items()}
    assert counts["terminal_only"]["executed_checks"] == counts["current_rank"]["executed_checks"]
    assert counts["terminal_only"]["pre_completion_search_errors"] > 0
    assert counts["terminal_only"]["retrieval_failures"] == 0
    assert any(
        r["search_execution"]["search_memory_before_completion"]
        != r["search_execution"]["search_memory_after_completion"]
        for r in runs["terminal_only"]["actions"]
    )
    assert all(
        r["search_execution"]["search_memory_before_completion"]
        == r["search_execution"]["search_memory_after_completion"]
        for r in runs["current_no_carry"]["actions"]
    )
    for arm, run in runs.items():
        for row in run["actions"]:
            assert row["search_execution"]["submitted_search_order"] == row["search_order"]
        assert (
            run["runtime_audit"]["final_state_sha256"]
            == runs["terminal_only"]["runtime_audit"]["final_state_sha256"]
        ), arm
