"""Mac-capable LIBERO smoke / frozen pi05 run with optional SAM and native CPSWM.

Use the isolated simulation environment, not the core Python environment.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import imageio.v2 as imageio
import numpy as np

from cpswm.simulation.integrations.bridge import NativeBridge
from cpswm.simulation.integrations.libero_env import TASKS, LiberoEnvironment, configure_libero
from cpswm.simulation.integrations.perception import Sam2Tracker
from cpswm.simulation.integrations.policy import ActionChunks, SmokePolicy, local_pi05, policy_input


def save(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stack-root", type=Path, default=ROOT.parent)
    p.add_argument("--task", choices=TASKS, default="table_center")
    p.add_argument("--initial-state", type=int, default=0)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--policy", choices=("smoke", "pi05-local", "pi05-websocket"), default="smoke")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    p.add_argument("--sam", action="store_true")
    p.add_argument("--box", type=float, nargs=4)
    p.add_argument("--sam-device", choices=("cpu", "mps"), default="cpu")
    p.add_argument(
        "--arm",
        default="native_joint",
        choices=("native_joint", "native_factorized", "source_replay", "ordinary_memory"),
    )
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.steps < 0 or (args.sam and args.box is None):
        p.error("nonnegative steps and explicit operator box for SAM required")
    stack = args.stack_root.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("MPLCONFIGDIR", str(stack / "cache/matplotlib"))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(stack / "cache/numba"))
    os.environ.setdefault("HF_HOME", str(stack / "cache/huggingface"))
    os.environ.setdefault("OPENPI_DATA_HOME", str(stack / "cache/openpi"))
    configure_libero(stack / "vendor/openpi/third_party/libero", stack / "config/libero")
    sources = list((ROOT / "src/cpswm/simulation").rglob("*.py")) + [
        ROOT / "tools" / name
        for name in ("run_libero_stack.py", "simulation_python.py", "simulation_memory_worker.py")
    ]
    manifest = {
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "platform": platform.platform(),
        "python": sys.executable,
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "sources": {str(x.relative_to(ROOT)): sha(x) for x in sorted(sources)},
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
        "camera_convention": "agentview RGB rotated 180 degrees; declared image-space thirds only",
        "initialization": "operator box, no simulator object ID" if args.sam else "no perception",
        "decision_source": (
            "official LIBERO task instruction; CPSWM audits visual evidence "
            "and binds command revisions"
        ),
        "scientific_acceptance": False,
    }
    if args.sam:
        manifest["sam_checkpoint_sha256"] = sha(stack / "models/sam2.1_hiera_tiny.pt")
    if args.policy == "pi05-local":
        manifest["pi05_checkpoint_manifest_sha256"] = sha(
            stack / "models/pi05_libero/verified-manifest.json"
        )
        manifest["tokenizer_sha256"] = sha(
            stack / "cache/openpi/big_vision/paligemma_tokenizer.model"
        )
    save(args.output / "manifest.json", manifest)
    env = bridge = writer = None
    logs: list[dict] = []
    started = time.monotonic()
    try:
        print("LIBERO: initializing real simulator", flush=True)
        env = LiberoEnvironment(args.task, args.initial_state, args.seed)
        obs = env.observation
        np.savez_compressed(args.output / "initial_observation.npz", **obs)
        print(f"LIBERO: ready, task={env.prompt}", flush=True)
        imageio.imwrite(
            args.output / "first_frame.png",
            np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]),
        )
        tracker = None
        episode = f"{args.task}:init{args.initial_state}:seed{args.seed}"
        revision = "task-instruction-only"
        if args.sam:
            tracker = Sam2Tracker(
                stack / "models/sam2.1_hiera_tiny.pt",
                args.output / "sam_prefix",
                args.box,
                device=args.sam_device,
            )
            bridge = NativeBridge(str(stack / "envs/core/bin/python"), ROOT, episode, args.arm)
            save(args.output / "core_worker.json", bridge.initial)
        policy = None
        if args.steps:
            if args.policy == "smoke":
                policy = SmokePolicy()
            elif args.policy == "pi05-local":
                policy = local_pi05(str(stack / "models/pi05_libero"), args.device, args.seed)
                save(args.output / "policy_metadata.json", policy.metadata)
                print("pi05: model ready", flush=True)
            else:
                from cpswm.simulation.integrations.websocket_policy import BoundedWebsocketPolicy

                policy = BoundedWebsocketPolicy(args.host, args.port)
        queue = ActionChunks(5)
        writer = imageio.get_writer(args.output / "rollout.mp4", fps=10)
        for tick in range(args.steps + 1):
            rgb = np.ascontiguousarray(obs["agentview_image"][::-1, ::-1])
            writer.append_data(rgb)
            if tick % 5 == 0 or tick == args.steps:
                entry = {"tick": tick}
                if tracker is not None:
                    event, mask = tracker.observe(rgb, episode, tick)
                    # Frames after an executed action cannot establish a human habit.
                    event["robot_generated"] = tick > 0
                    assert bridge is not None
                    receipt = bridge.observe(event)
                    revision = receipt["revision"]
                    entry.update(observation=event, memory=receipt)
                    imageio.imwrite(
                        args.output / f"mask_{tick:05d}.png", mask.astype(np.uint8) * 255
                    )
                    overlay = rgb.copy()
                    overlay[mask] = (0.55 * overlay[mask] + 0.45 * np.array([0, 255, 0])).astype(
                        np.uint8
                    )
                    imageio.imwrite(args.output / f"overlay_{tick:05d}.png", overlay)
                logs.append(entry)
                # Persist each sensor receipt before issuing another action.
                save(args.output / "journal.json", logs)
            if tick == args.steps:
                break
            queue.bind(revision, env.prompt)
            if not queue.actions:
                t0 = time.monotonic()
                print(f"{args.policy}: inference at tick {tick}", flush=True)
                output = policy.infer(policy_input(obs, env.prompt))
                queue.load(output)
                np.savez_compressed(
                    args.output / f"policy_output_{tick:05d}.npz", actions=output["actions"]
                )
                logs.append(
                    {
                        "tick": tick,
                        "event": "policy_inference",
                        "seconds": time.monotonic() - t0,
                        "policy": args.policy,
                        "prompt": env.prompt,
                        "revision": revision,
                    }
                )
                save(args.output / "journal.json", logs)
            action = queue.pop(revision, env.prompt)
            obs = env.step(action)
            logs.append(
                {
                    "tick": tick,
                    "event": "executed_action",
                    "action": action.tolist(),
                    "revision": revision,
                    "result": "simulator_step_returned",
                    "eef_position_after": obs["robot0_eef_pos"].tolist(),
                    "gripper_position_after": obs["robot0_gripper_qpos"].tolist(),
                }
            )
            save(args.output / "journal.json", logs)
        writer.close()
        writer = None
        save(args.output / "journal.json", logs)
        source_unchanged = all(sha(ROOT / k) == v for k, v in manifest["sources"].items())
        if not source_unchanged:
            raise RuntimeError("source changed during run")
        save(
            args.output / "summary.json",
            {
                "status": "CAMERA_PREFLIGHT_COMPLETE"
                if not args.steps
                else "ACTUATOR_SMOKE_COMPLETE"
                if args.policy == "smoke"
                else "POLICY_ROLLOUT_COMPLETE",
                "task": args.task,
                "prompt": env.prompt,
                "steps": env.steps,
                "task_success_evaluator_only": env.evaluator_success,
                "pi05_inference_executed": args.policy.startswith("pi05") and args.steps > 0,
                "sam_frames": 0 if tracker is None else tracker.count,
                "native_memory_connected": bridge is not None,
                "cancelled_actions": queue.cancelled_actions,
                "elapsed_seconds": time.monotonic() - started,
                "source_unchanged": source_unchanged,
                "limitations": [
                    "single episode engineering run",
                    "SAM propagation is prediction, not a fresh independent sighting",
                    "no automatic visual person attribution or cross-session identity",
                    "image regions are not calibrated physical places",
                    "official task prompt; native memory has not selected a new manipulation goal",
                    "task success is evaluation only, not a visual success receipt",
                ],
                "scientific_acceptance": False,
            },
        )
    except BaseException as error:
        save(args.output / "journal.json", logs)
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
