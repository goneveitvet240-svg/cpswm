"""Real robot simulation with controlled-history CPSWM goal selection.

Run via simulation_python.py. The two-segment probe interrupts a five-action
chunk after two actual steps, then delivers existing delayed-attribution data.
Natural semantic history / placement confirmation are deliberately not claimed.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import imageio.v2 as imageio
import numpy as np
from run_libero_stack import save, sha

from cpswm.simulation.goal_control import fixture_observations
from cpswm.simulation.integrations.bridge import NativeBridge
from cpswm.simulation.integrations.libero_env import LiberoEnvironment, configure_libero
from cpswm.simulation.integrations.perception import Sam2Tracker
from cpswm.simulation.integrations.policy import ActionChunks, SmokePolicy, local_pi05, policy_input


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack-root", type=Path, default=ROOT.parent)
    parser.add_argument(
        "--fixture", type=Path, default=ROOT / "configs/simulation/libero_goal_fixture.json"
    )
    parser.add_argument("--policy", choices=("smoke", "pi05-local"), default="pi05-local")
    parser.add_argument(
        "--arm",
        choices=("native_joint", "native_factorized", "source_replay", "ordinary_memory"),
        default="native_joint",
    )
    parser.add_argument("--no-correction", action="store_true")
    parser.add_argument("--memory-replay", choices=("full", "suffix"), default="full")
    parser.add_argument("--box", type=float, nargs=4, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    history, corrections = fixture_observations(fixture)
    first_steps = fixture["correction_after_control_steps"]
    if type(first_steps) is not int or not 0 < first_steps < 5 or not corrections:
        parser.error("probe requires a delayed correction inside a five-action chunk")
    start_tick = fixture["initial_visual_tick"]
    stack = args.stack_root.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_libero(stack / "vendor/openpi/third_party/libero", stack / "config/libero")
    sources = list((ROOT / "src/cpswm/simulation").rglob("*.py")) + [
        ROOT / "tools" / name
        for name in (
            "run_libero_goal_loop.py",
            "run_libero_stack.py",
            "simulation_goal_worker.py",
            "simulation_python.py",
            "verify_libero_goal_run.py",
        )
    ]
    manifest = {
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "sources": {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)},
        "fixture_sha256": sha(args.fixture),
        "platform": platform.platform(),
        "python": sys.executable,
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "vendor": {
            name: {
                "sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=stack / "vendor" / name, text=True
                ).strip(),
                "status": subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=stack / "vendor" / name, text=True
                ),
            }
            for name in ("openpi", "openpi/third_party/libero", "sam2")
        },
        "sam_checkpoint_sha256": sha(stack / "models/sam2.1_hiera_tiny.pt"),
        "decision_source": "CPSWM controlled-history readout + operator prompt catalogue",
        "semantic_history_source": "existing delayed_attribution controlled fixture",
        "physical_success_feedback_available": False,
        "scientific_acceptance": False,
    }
    if args.policy == "pi05-local":
        manifest["pi05_checkpoint_manifest_sha256"] = sha(
            stack / "models/pi05_libero/verified-manifest.json"
        )
        manifest["tokenizer_sha256"] = sha(
            stack / "cache/openpi/big_vision/paligemma_tokenizer.model"
        )
    save(args.output / "manifest.json", manifest)
    save(args.output / "fixture.json", fixture)
    save(
        args.output / "controlled_sources.json",
        {
            "history": [o.payload() for o in history],
            "corrections": [o.payload() for o in corrections],
        },
    )
    env = bridge = writer = None
    logs: list[dict] = []
    started = time.monotonic()

    def record(entry: dict) -> None:
        logs.append(entry)
        save(args.output / "journal.json", logs)

    def rpc(body: dict) -> dict:
        assert bridge is not None
        result = bridge.observe(body)
        record({"event": "core_rpc", "request": body, "receipt": result})
        return result

    try:
        episode = fixture["episode_id"]
        bridge = NativeBridge(
            str(stack / "envs/core/bin/python"),
            ROOT,
            episode,
            args.arm,
            goal_fixture=args.fixture.resolve(),
            memory_replay=args.memory_replay,
        )
        save(args.output / "core_worker.json", bridge.initial)
        for observation in history:
            rpc(
                {
                    "operation": "history",
                    "observation": observation.payload(),
                    "now": observation.available_at,
                }
            )
        print("LIBERO: initializing real simulator", flush=True)
        env = LiberoEnvironment("table_center", 0, 7)
        obs = env.observation
        np.savez_compressed(args.output / "initial_observation.npz", **obs)
        tracker = Sam2Tracker(
            stack / "models/sam2.1_hiera_tiny.pt", args.output / "sam_prefix", args.box
        )

        def visual(tick: int) -> dict:
            rgb = np.ascontiguousarray(obs["agentview_image"][::-1, ::-1])
            event, mask = tracker.observe(rgb, episode, tick)
            event["robot_generated"] = env.steps > 0
            imageio.imwrite(args.output / f"frame_{tick:05d}.png", rgb)
            imageio.imwrite(args.output / f"mask_{tick:05d}.png", mask.astype(np.uint8) * 255)
            overlay = rgb.copy()
            overlay[mask] = (0.55 * overlay[mask] + 0.45 * np.array([0, 255, 0])).astype(np.uint8)
            imageio.imwrite(args.output / f"overlay_{tick:05d}.png", overlay)
            record({"event": "sam_observation", "tick": tick, "observation": event})
            return event

        rpc({"operation": "visual", "observation": visual(start_tick), "now": start_tick})
        policy = (
            SmokePolicy()
            if args.policy == "smoke"
            else local_pi05(str(stack / "models/pi05_libero"))
        )
        if args.policy == "pi05-local":
            save(args.output / "policy_metadata.json", policy.metadata)
        print(f"{args.policy}: ready for memory-selected prompts", flush=True)
        chunks = ActionChunks(5)
        writer = imageio.get_writer(args.output / "rollout.mp4", fps=10)
        writer.append_data(np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]))
        prompts: list[str] = []
        status = "GOAL_LOOP_COMPLETE"
        for segment, count in enumerate((first_steps, 5)):
            tick = start_tick + env.steps
            if segment:
                if args.no_correction:
                    record({"event": "corrections_withheld_control", "tick": tick})
                else:
                    for correction in corrections:
                        rpc(
                            {
                                "operation": "history",
                                "observation": correction.payload(),
                                "now": tick,
                            }
                        )
            selected = rpc({"operation": "plan", "tick": tick})
            if selected["status"] != "ready":
                status = selected["status"]
                break
            plan = selected["plan"]
            prompt = plan["prompt"]
            revision = plan["command"]["memory_revision"]
            prompts.append(prompt)
            cancelled_before = chunks.cancelled_actions
            chunks.bind(revision, prompt)
            record(
                {
                    "event": "bound_goal",
                    "tick": tick,
                    "plan": plan,
                    "cancelled_actions": chunks.cancelled_actions - cancelled_before,
                }
            )
            inputs = policy_input(obs, prompt)
            np.savez_compressed(args.output / f"policy_input_{tick:05d}.npz", **inputs)
            print(
                f"{args.policy}: inference at {tick}, "
                f"goal={plan['command']['destination']}, prompt={prompt}",
                flush=True,
            )
            infer_start = time.monotonic()
            output = policy.infer(inputs)
            chunks.load(output)
            np.savez_compressed(
                args.output / f"policy_output_{tick:05d}.npz", actions=output["actions"]
            )
            record(
                {
                    "event": "policy_inference",
                    "tick": tick,
                    "plan": plan,
                    "seconds": time.monotonic() - infer_start,
                    "policy": args.policy,
                }
            )
            for offset in range(count):
                rpc({"operation": "validate", "plan": plan})
                action = chunks.pop(revision, prompt)
                obs = env.step(action)
                completed_at = start_tick + env.steps
                # Persist the actual return BEFORE attempting the core receipt.
                record(
                    {
                        "event": "executed_action",
                        "tick": completed_at,
                        "command_id": plan["command"]["command_id"],
                        "policy_tick": tick,
                        "output_offset": offset,
                        "action": action.tolist(),
                        "result": "simulator_step_returned",
                        "eef_position_after": obs["robot0_eef_pos"].tolist(),
                        "gripper_position_after": obs["robot0_gripper_qpos"].tolist(),
                    }
                )
                writer.append_data(np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]))
                rpc({"operation": "step", "plan": plan, "completed_at": completed_at})
            rpc(
                {
                    "operation": "feedback",
                    "plan": plan,
                    "observation": visual(start_tick + env.steps),
                    "control_steps": count,
                }
            )
        writer.close()
        writer = None
        final = rpc({"operation": "audit"})
        unchanged = all(sha(ROOT / k) == v for k, v in manifest["sources"].items())
        if not unchanged:
            raise RuntimeError("source changed during execution")
        save(
            args.output / "summary.json",
            {
                "status": status,
                "steps": env.steps,
                "prompts": prompts,
                "goal_changed": len(set(prompts)) > 1,
                "cancelled_actions": chunks.cancelled_actions,
                "sam_frames": tracker.count,
                "pi05_inference_executed": args.policy == "pi05-local" and bool(prompts),
                "elapsed_seconds": time.monotonic() - started,
                "source_unchanged": unchanged,
                "final_core_receipt": final,
                "task_success_evaluator_only": env.evaluator_success,
                "evaluator_scope": "original LIBERO bowl-to-plate task only",
                "limitations": [
                    "single bounded engineering probe, not a full task episode",
                    "semantic history is controlled, not visually inferred",
                    "operator supplies object binding and destination prompt catalogue",
                    "existing fixture readout, not frozen production task readout",
                    "SAM prediction permits continuation but cannot certify placement success",
                    "feedback status unknown; no human habit update from robot motion",
                    "no native global ORRER acceptance or joint-specific scientific gain",
                    "local trusted process protocol; execution evidence is audited separately",
                ],
                "scientific_acceptance": False,
            },
        )
    except BaseException as error:
        save(
            args.output / "failure.json",
            {
                "error": f"{type(error).__name__}: {error}",
                "elapsed_seconds": time.monotonic() - started,
            },
        )
        raise
    finally:
        if writer is not None:
            writer.close()
        if bridge is not None:
            bridge.close()
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
