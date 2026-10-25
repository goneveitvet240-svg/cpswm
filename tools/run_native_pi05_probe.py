"""Actual native posterior -> goal -> pi05 -> physics, with an explicit binding."""

import argparse
import subprocess
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from run_libero_stack import save, sha
from synergy_goal_evaluator import evaluate_goal

from cpswm.simulation.integrations.bridge import NativeBridge
from cpswm.simulation.integrations.libero_env import LiberoEnvironment, configure_libero
from cpswm.simulation.integrations.perception import Sam2Tracker
from cpswm.simulation.integrations.policy import ActionChunks, SmokePolicy, local_pi05, policy_input

ROOT = Path(__file__).resolve().parents[1]


class NativePosteriorBridge(NativeBridge):
    def __init__(self):
        self.process = subprocess.Popen(
            [str(ROOT.parent / "envs/core/bin/python"), str(ROOT / "tools/native_goal_worker.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=ROOT,
        )
        self.timeout = 120.0
        try:
            self.initial = self._read()
        except BaseException:
            self.close()
            raise
        self.episode = self.initial["source"]["episode_id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--policy", choices=("smoke", "pi05-local"), default="pi05-local")
    args = parser.parse_args()
    if not 1 <= args.steps <= 220:
        raise ValueError("bounded 1..220 control steps")
    args.output.mkdir(parents=True, exist_ok=False)
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status:
        raise ValueError("clean committed source required")
    stack = ROOT.parent
    sources = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tools/*.py"), *ROOT.glob("configs/**/*.json")]
    save(
        args.output / "manifest.json",
        {
            "sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "sources": {str(p.relative_to(ROOT)): sha(p) for p in sources},
            "policy": args.policy,
            "steps_limit": args.steps,
            "checkpoint_manifest_sha256": sha(stack / "models/pi05_libero/verified-manifest.json"),
            "task": "table_center",
            "init": 0,
            "seed": 7,
            "semantic_source": "D0 sparse32 episode0 first3 public steps; no truth input",
            "binding": "operator-specified cross-world map; no natural grounding claim",
        },
    )
    configure_libero(stack / "vendor/openpi/third_party/libero", stack / "config/libero")
    bridge = env = writer = None
    journal = []

    def record(row):
        journal.append(row)
        save(args.output / "journal.json", journal)

    def rpc(request):
        reply = bridge.observe(request)
        record({"event": "core_rpc", "request": request, "receipt": reply})
        return reply

    try:
        bridge = NativePosteriorBridge()
        save(args.output / "native_source.json", bridge.initial)
        env = LiberoEnvironment("table_center", 0, 7)
        obs = env.observation
        np.savez_compressed(args.output / "initial_observation.npz", **obs)
        tracker = Sam2Tracker(
            stack / "models/sam2.1_hiera_tiny.pt", args.output / "sam", (104, 131, 143, 163)
        )

        def visual():
            rgb = np.ascontiguousarray(obs["agentview_image"][::-1, ::-1])
            event, mask = tracker.observe(rgb, bridge.episode, 100 + env.steps)
            event["robot_generated"] = env.steps > 0
            imageio.imwrite(args.output / f"mask_{env.steps:04}.png", mask.astype(np.uint8) * 255)
            return event

        rpc({"operation": "visual", "observation": visual(), "now": 100})
        policy = (
            SmokePolicy()
            if args.policy == "smoke"
            else local_pi05(str(stack / "models/pi05_libero"))
        )
        if args.policy != "smoke":
            save(args.output / "policy_metadata.json", policy.metadata)
        chunks = ActionChunks(5)
        writer = imageio.get_writer(args.output / "rollout.mp4", fps=10)
        writer.append_data(np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]))
        inferences, success = 0, False
        while env.steps < args.steps:
            tick = 100 + env.steps
            selected = rpc({"operation": "plan", "tick": tick})
            if selected["status"] != "ready":
                raise ValueError(
                    "native goal requires evidence or physical binding: " + selected["status"]
                )
            plan = selected["plan"]
            inputs = policy_input(obs, plan["prompt"])
            np.savez_compressed(args.output / f"input_{tick}.npz", **inputs)
            started = time.monotonic()
            output = policy.infer(inputs)
            np.savez_compressed(args.output / f"output_{tick}.npz", actions=output["actions"])
            inferences += 1
            record(
                {
                    "event": "inference",
                    "tick": tick,
                    "plan": plan,
                    "seconds": time.monotonic() - started,
                }
            )
            revision = plan["command"]["memory_revision"]
            chunks.bind(revision, plan["prompt"])
            chunks.load(output)
            count = min(5, args.steps - env.steps)
            for offset in range(count):
                rpc({"operation": "validate", "plan": plan})
                action = chunks.pop(revision, plan["prompt"])
                obs = env.step(action)
                score = evaluate_goal(env, plan["command"]["destination"])
                success = score["success"]
                record(
                    {
                        "event": "action",
                        "tick": 100 + env.steps,
                        "inference_tick": tick,
                        "offset": offset,
                        "action": action.tolist(),
                        "command": plan["command"],
                        "eef": obs["robot0_eef_pos"].tolist(),
                        "gripper": obs["robot0_gripper_qpos"].tolist(),
                        "goal_evaluator_only": score,
                    }
                )
                writer.append_data(np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]))
                rpc({"operation": "step", "plan": plan, "completed_at": 100 + env.steps})
                if success:
                    count = offset + 1
                    break
            rpc(
                {
                    "operation": "feedback",
                    "plan": plan,
                    "observation": visual(),
                    "control_steps": count,
                }
            )
            print("native", env.steps, plan["prompt"], "success", success, flush=True)
            if success:
                break
        np.savez_compressed(args.output / "final_observation.npz", **obs)
        imageio.imwrite(args.output / "last_frame.png", obs["agentview_image"][::-1, ::-1])
        save(
            args.output / "summary.json",
            {
                "steps": env.steps,
                "inferences": inferences,
                "pi05_inference_executed": args.policy == "pi05-local",
                "goal_success": success,
                "native_readout_consumed": True,
                "natural_grounding": False,
                "scientific_acceptance": False,
            },
        )
    finally:
        if writer is not None:
            writer.close()
        if env is not None:
            env.close()
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
