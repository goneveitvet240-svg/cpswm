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


@pytest.mark.parametrize("success_step", [1, 5, 6, None])
def test_runner_stops_at_first_success_and_preserves_final_frame(
    monkeypatch, tmp_path, success_step
):
    import json

    import numpy as np
    import run_libero_stack as runner

    class FakeEnvironment:
        prompt = "put bowl on plate"
        steps = 0
        evaluator_success = False

        def __init__(self, *args):
            self.observation = {
                "agentview_image": np.zeros((256, 256, 3), dtype=np.uint8),
                "robot0_eef_pos": np.zeros(3),
                "robot0_gripper_qpos": np.zeros(2),
            }

        def step(self, action):
            assert action.shape == (7,)
            self.steps += 1
            self.evaluator_success = self.steps == success_step
            self.observation["robot0_eef_pos"][0] = self.steps
            return self.observation

        def close(self):
            pass

    class Writer:
        count = 0

        def append_data(self, frame):
            self.count += 1

        def close(self):
            pass

    writer = Writer()
    monkeypatch.setattr(runner, "LiberoEnvironment", FakeEnvironment)
    monkeypatch.setattr(runner, "configure_libero", lambda *args: None)
    monkeypatch.setattr(runner.platform, "platform", lambda: "test-platform")
    monkeypatch.setattr(runner, "policy_input", lambda obs, prompt: {"prompt": prompt})
    monkeypatch.setattr(runner.imageio, "get_writer", lambda *args, **kwargs: writer)
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: "" if "status" in args else "a" * 40,
    )
    output = tmp_path / "episode"
    monkeypatch.setattr(
        runner.sys, "argv", ["run", "--steps", "12", "--stop-on-success", "--output", str(output)]
    )
    runner.main()
    summary = json.loads((output / "summary.json").read_text())
    expected = success_step or 12
    assert summary["steps"] == expected
    assert summary["first_success_step_evaluator_only"] == success_step
    assert summary["stop_reason"] == ("success" if success_step else "step_limit")
    assert writer.count == expected + 1
    assert (output / "last_frame.png").is_file()
    with np.load(output / "final_observation.npz") as final:
        assert final["robot0_eef_pos"][0] == expected
    journal = json.loads((output / "journal.json").read_text())
    actions = [x for x in journal if x.get("event") == "executed_action"]
    assert len(actions) == expected
    assert [x["tick"] for x in journal if x.get("event") == "policy_inference"] == list(
        range(0, expected, 5)
    )
