"""Strong memory controls with common recorded pi05 inputs/actions, explicitly shared inference.

No second model call is claimed. Physical replay checks the common input sequence.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from run_matched_value import save

from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController, observation_from_payload

ROOT = Path(__file__).resolve().parents[1]


def run(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["arguments"]["arm"] == "native_joint"
    fixture = json.loads((directory / "fixture.json").read_text())
    journal = json.loads((directory / "journal.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    controllers = {
        arm: MemoryGoalController(fixture["episode_id"], fixture["catalogue"], arm, ROOT)
        for arm in ("native_joint", "native_factorized", "source_replay")
    }
    pending = {}
    plans = {}
    inference_rows = []
    actions = []
    for entry in journal:
        if entry["event"] == "core_rpc":
            body = entry["request"]
            op = body["operation"]
            for arm, c in controllers.items():
                if op in ("history", "visual"):
                    fn = c.observe_history if op == "history" else c.observe_visual
                    fn(observation_from_payload(body["observation"]), body["now"])
                elif op == "plan":
                    result = c.plan(body["tick"])
                    assert result["status"] == entry["receipt"]["status"] == "ready"
                    plan = GoalPlan.from_payload(result["plan"])
                    assert plan.prompt == entry["receipt"]["plan"]["prompt"]
                    assert (
                        plan.command.destination
                        == entry["receipt"]["plan"]["command"]["destination"]
                    )
                    pending[arm] = plan
                    plans.setdefault(body["tick"], {})[arm] = result
                elif op == "validate":
                    c.validate(pending[arm])
                elif op == "step":
                    c.record_step(pending[arm], body["completed_at"])
                elif op == "feedback":
                    before = c.memory.revision
                    c.feedback(
                        pending[arm],
                        observation_from_payload(body["observation"]),
                        body["control_steps"],
                    )
                    assert before == c.memory.revision
                else:
                    assert op == "audit"
        elif entry["event"] == "policy_inference":
            tick = entry["tick"]
            with np.load(directory / f"policy_input_{tick:05d}.npz", allow_pickle=False) as inputs:
                assert set(inputs.files) == {
                    "observation/image",
                    "observation/wrist_image",
                    "observation/state",
                    "prompt",
                }
                assert all(str(inputs["prompt"]) == p.prompt for p in pending.values())
            inference_rows.append(
                {
                    "tick": tick,
                    "controls": plans[tick],
                    "common_policy_input_sha256": hashlib.sha256(
                        (directory / f"policy_input_{tick:05d}.npz").read_bytes()
                    ).hexdigest(),
                }
            )
        elif entry["event"] == "executed_action":
            for c, plan in ((controllers[a], p) for a, p in pending.items()):
                c.validate(plan)
            actions.append(
                {
                    "tick": entry["tick"],
                    "policy_tick": entry["policy_tick"],
                    "output_offset": entry["output_offset"],
                    "action": entry["action"],
                    "control_commands": {a: p.command.command_id for a, p in pending.items()},
                }
            )
    assert len(actions) == summary["steps"]
    return {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "actual_manifest_sha256": hashlib.sha256(
            (directory / "manifest.json").read_bytes()
        ).hexdigest(),
        "actual_journal_sha256": hashlib.sha256(
            (directory / "journal.json").read_bytes()
        ).hexdigest(),
        "inferences": inference_rows,
        "actions": actions,
        "final_controls": {a: c.audit() for a, c in controllers.items()},
        "all_goal_and_prompt_choices_identical": True,
        "scientific_acceptance": False,
        "scope": "shared recorded policy inference; controls replay admitted history and vision",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, run(args.run))
