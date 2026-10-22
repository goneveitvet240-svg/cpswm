# ruff: noqa: E402
"""Replay native goal receipts and check actual actions against model outputs.

An internal evidence consistency audit, not independent physical attestation.
Run in the locked core environment at the source SHA recorded in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpswm.simulation.goal_control import (
    GoalPlan,
    MemoryGoalController,
    fixture_observations,
    observation_from_payload,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_policy_claim(manifest: dict, summary: dict, inference_count: int) -> None:
    policy = manifest["arguments"]["policy"]
    require(policy in {"smoke", "pi05-local"}, "unknown policy implementation")
    claim = summary["pi05_inference_executed"]
    require(type(claim) is bool, "policy claim must be boolean")
    require(claim == (policy == "pi05-local" and inference_count > 0), "policy claim mismatch")
    if policy == "pi05-local":
        for field in ("pi05_checkpoint_manifest_sha256", "tokenizer_sha256"):
            value = manifest.get(field)
            require(
                isinstance(value, str)
                and len(value) == 64
                and all(c in "0123456789abcdef" for c in value),
                "pi05 claim lacks model provenance",
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = args.run
    manifest = json.loads((run / "manifest.json").read_text())
    fixture = json.loads((run / "fixture.json").read_text())
    journal = json.loads((run / "journal.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    sha = manifest["code_sha"]
    require(len(sha) == 40 and not manifest["git_status"], "run must start at a clean full SHA")
    required = {
        "src/cpswm/simulation/goal_control.py",
        "src/cpswm/simulation/memory.py",
        "src/cpswm/simulation/contracts.py",
        "src/cpswm/simulation/integrations/policy.py",
        "src/cpswm/simulation/integrations/perception.py",
        "src/cpswm/simulation/integrations/libero_env.py",
        "src/cpswm/simulation/integrations/bridge.py",
        "tools/run_libero_goal_loop.py",
        "tools/simulation_goal_worker.py",
    }
    memory_replay = manifest["arguments"].get("memory_replay", "full")
    require(memory_replay in {"full", "suffix"}, "unknown memory replay implementation")
    if memory_replay == "suffix":
        required.add("src/cpswm/simulation/suffix_memory.py")
    require(required <= set(manifest["sources"]), "source manifest is incomplete")
    for path, expected in manifest["sources"].items():
        committed = subprocess.check_output(["git", "show", f"{sha}:{path}"], cwd=ROOT)
        require(hashlib.sha256(committed).hexdigest() == expected, f"unbound source: {path}")
        require(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected,
            f"replay code differs from run: {path}",
        )
    require(all(not v["status"] for v in manifest["vendor"].values()), "modified vendor")
    config_blob = subprocess.check_output(
        ["git", "show", f"{sha}:configs/simulation/libero_goal_fixture.json"], cwd=ROOT
    )
    require(
        hashlib.sha256(config_blob).hexdigest() == manifest["fixture_sha256"], "unbound fixture"
    )
    require(json.loads(config_blob) == fixture, "fixture content changed")
    history, corrections = fixture_observations(fixture)
    controlled = json.loads((run / "controlled_sources.json").read_text())
    expected_sources = json.loads(
        json.dumps(
            {
                "history": [o.payload() for o in history],
                "corrections": [o.payload() for o in corrections],
            }
        )
    )
    require(controlled == expected_sources, "controlled history differs from declared fixture")
    controller = MemoryGoalController(
        fixture["episode_id"],
        fixture["catalogue"],
        manifest["arguments"]["arm"],
        memory_replay=memory_replay,
    )
    actual_steps = []
    actual_visual = {}
    inferred = {}
    feedback_count = 0
    bound = []
    history_sources = []
    pending_physics_receipt = None
    for entry in journal:
        event = entry["event"]
        if event == "sam_observation":
            obs = entry["observation"]
            source = obs["source_id"]
            require(source not in actual_visual, "duplicate camera receipt")
            actual_visual[source] = obs
            mask = run / f"mask_{entry['tick']:05d}.png"
            require(mask.is_file(), "missing SAM mask")
        elif event == "bound_goal":
            controller.validate(GoalPlan.from_payload(entry["plan"]))
            bound.append(entry)
        elif event == "policy_inference":
            plan = GoalPlan.from_payload(entry["plan"])
            controller.validate(plan)
            require(bound[-1]["plan"] == entry["plan"], "model did not consume bound plan")
            inputs = np.load(run / f"policy_input_{entry['tick']:05d}.npz")
            require(str(inputs["prompt"]) == plan.prompt, "model input prompt is not memory goal")
            require(
                set(inputs.files)
                == {"observation/image", "observation/wrist_image", "observation/state", "prompt"},
                "unexpected policy input / truth leakage",
            )
            output = np.load(run / f"policy_output_{entry['tick']:05d}.npz")["actions"]
            require(
                output.ndim == 2 and output.shape[1] == 7 and len(output) >= 5,
                "invalid saved policy chunk",
            )
            require(bool(np.isfinite(output).all()), "nonfinite policy actions")
            require(entry["tick"] not in inferred, "duplicate inference tick")
            inferred[entry["tick"]] = (entry["plan"], output)
        elif event == "executed_action":
            require(pending_physics_receipt is None, "unacknowledged earlier physics step")
            plan_body, output = inferred[entry["policy_tick"]]
            plan = GoalPlan.from_payload(plan_body)
            controller.validate(plan)
            offset = len(controller.step_ticks)
            require(entry["command_id"] == plan.command.command_id, "action command mismatch")
            require(entry["output_offset"] == offset, "skipped/reused chunk action")
            require(
                np.array_equal(entry["action"], output[offset]), "action differs from model output"
            )
            require(
                entry["tick"] == fixture["initial_visual_tick"] + len(actual_steps) + 1,
                "physics step time is not contiguous",
            )
            require(entry["result"] == "simulator_step_returned", "no physics return")
            actual_steps.append(entry)
            pending_physics_receipt = entry
        elif event == "core_rpc":
            body = entry["request"]
            operation = body["operation"]
            result = {}
            if operation in {"history", "visual"}:
                observation = observation_from_payload(body["observation"])
                if operation == "history":
                    controller.observe_history(observation, body["now"])
                    history_sources.append(observation.source_id)
                else:
                    require(
                        actual_visual[observation.source_id] == body["observation"],
                        "visual substitution",
                    )
                    controller.observe_visual(observation, body["now"])
            elif operation == "plan":
                result = controller.plan(body["tick"])
            elif operation == "validate":
                controller.validate(GoalPlan.from_payload(body["plan"]))
            elif operation == "step":
                require(pending_physics_receipt is not None, "step acknowledgment without physics")
                require(
                    body["completed_at"] == pending_physics_receipt["tick"], "step tick mismatch"
                )
                require(
                    body["plan"]["command"]["command_id"] == pending_physics_receipt["command_id"],
                    "step acknowledgment command mismatch",
                )
                controller.record_step(GoalPlan.from_payload(body["plan"]), body["completed_at"])
                pending_physics_receipt = None
            elif operation == "feedback":
                observation = observation_from_payload(body["observation"])
                require(
                    actual_visual[observation.source_id] == body["observation"],
                    "feedback substitution",
                )
                controller.feedback(
                    GoalPlan.from_payload(body["plan"]), observation, body["control_steps"]
                )
                feedback_count += 1
            else:
                require(operation == "audit", "unknown operation")
            expected = {
                "ok": True,
                **result,
                "audit": controller.audit(),
                "revision": controller.revision,
            }
            require(
                entry["receipt"] == json.loads(json.dumps(expected)),
                f"core replay differs: {operation}",
            )
        else:
            require(
                event == "corrections_withheld_control" and manifest["arguments"]["no_correction"],
                "unexpected journal event",
            )
    require(pending_physics_receipt is None, "final physics step not acknowledged")
    require(summary["status"] == "GOAL_LOOP_COMPLETE", "probe did not complete")
    require(len(actual_steps) == summary["steps"] == 7, "incomplete physical segment count")
    require(len(inferred) == 2 and feedback_count == 2, "missing model/feedback segments")
    validate_policy_claim(manifest, summary, len(inferred))
    require(len(actual_visual) == summary["sam_frames"] == 3, "missing visual receipts")
    expected_history = [o.source_id for o in history]
    if not manifest["arguments"]["no_correction"]:
        expected_history.extend(o.source_id for o in corrections)
    require(history_sources == expected_history, "history budget/content mismatch")
    require([b["cancelled_actions"] for b in bound] == [0, 3], "old action chunk was not discarded")
    require(summary["cancelled_actions"] == 3, "cancellation summary mismatch")
    require(summary["prompts"] == [b["plan"]["prompt"] for b in bound], "prompt summary mismatch")
    require(
        summary["goal_changed"] == (len(set(summary["prompts"])) > 1),
        "goal-change summary mismatch",
    )
    require(
        summary["source_unchanged"] and not summary["scientific_acceptance"],
        "invalid claim boundary",
    )
    require(
        summary["final_core_receipt"]["audit"] == json.loads(json.dumps(controller.audit())),
        "final state mismatch",
    )
    print(
        json.dumps(
            {
                "status": "CONSISTENCY_VERIFIED",
                "source_sha": sha,
                "steps": len(actual_steps),
                "inferences": len(inferred),
                "policy": manifest["arguments"]["policy"],
                "pi05_inference_executed": summary["pi05_inference_executed"],
                "memory_replay": memory_replay,
                "feedback_segments": feedback_count,
                "goal_changed": summary["goal_changed"],
                "prompts": summary["prompts"],
                "cancelled_actions": summary["cancelled_actions"],
                "task_success_evaluator_only": summary["task_success_evaluator_only"],
                "scientific_acceptance": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
