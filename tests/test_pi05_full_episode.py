"""Recorded episode contracts: first success, full limit and false claims."""

from copy import deepcopy

import pytest
from verify_pi05_full_episode import validate_records


def fixture(success=True):
    n = 6 if success else 220
    manifest = {
        "git_status": "",
        "arguments": {
            "policy": "pi05-local",
            "stop_on_success": True,
            "steps": 220,
            "sam": False,
            "task": "table_center",
        },
    }
    summary = {
        "status": "POLICY_ROLLOUT_COMPLETE",
        "pi05_inference_executed": True,
        "native_memory_connected": False,
        "scientific_acceptance": False,
        "source_unchanged": True,
        "task": "table_center",
        "requested_steps": 220,
        "steps": n,
        "stop_reason": "success" if success else "step_limit",
        "first_success_step_evaluator_only": n if success else None,
        "task_success_evaluator_only": success,
        "prompt": "place bowl on plate",
    }
    journal = []
    for tick in range(n):
        if tick % 5 == 0:
            journal.append(
                {
                    "tick": tick,
                    "event": "policy_inference",
                    "policy": "pi05-local",
                    "prompt": summary["prompt"],
                    "revision": "task-instruction-only",
                }
            )
        journal.append(
            {
                "tick": tick,
                "event": "executed_action",
                "task_success_evaluator_only": success and tick == n - 1,
            }
        )
    return manifest, summary, journal


@pytest.mark.parametrize("success", [True, False])
def test_legal_success_and_exhausted_limit(success):
    args = fixture(success)
    actions, inference = validate_records(*args)
    assert len(actions) == (6 if success else 220)
    assert len(inference) == (2 if success else 44)


@pytest.mark.parametrize(
    "attack",
    [
        "early",
        "false_summary",
        "wrong_step",
        "omitted_action",
        "omitted_inference",
        "prompt",
        "smoke",
        "dirty",
        "early_failure",
        "truthy_flag",
        "scientific",
    ],
)
def test_reject_inconsistent_complete_episode_claims(attack):
    manifest, summary, journal = deepcopy(fixture())
    if attack == "early":
        journal[1]["task_success_evaluator_only"] = True
    elif attack == "false_summary":
        summary["task_success_evaluator_only"] = False
    elif attack == "wrong_step":
        summary["first_success_step_evaluator_only"] = 5
    elif attack == "omitted_action":
        journal.pop()
    elif attack == "omitted_inference":
        journal.pop(0)
    elif attack == "prompt":
        journal[0]["prompt"] = "place bowl on stove"
    elif attack == "smoke":
        manifest["arguments"]["policy"] = "smoke"
    elif attack == "dirty":
        manifest["git_status"] = " M tools/run_libero_stack.py"
    elif attack == "early_failure":
        journal[-1]["task_success_evaluator_only"] = False
        summary.update(
            task_success_evaluator_only=False,
            first_success_step_evaluator_only=None,
            stop_reason="step_limit",
        )
    elif attack == "truthy_flag":
        journal[-1]["task_success_evaluator_only"] = 1
    elif attack == "scientific":
        summary["scientific_acceptance"] = True
    with pytest.raises(AssertionError):
        validate_records(manifest, summary, journal)
