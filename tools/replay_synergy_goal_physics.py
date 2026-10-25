"""Replay saved goal-bound actions, inputs and destination predicates in real LIBERO."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from run_libero_stack import save
from synergy_goal_evaluator import evaluate_goal
from verify_pi05_full_episode import compare_observation
from verify_synergy_goal_episode import validate_goal_outcomes, validate_policy_claim

from cpswm.simulation.integrations.libero_env import LiberoEnvironment, configure_libero
from cpswm.simulation.integrations.policy import policy_input

ROOT = Path(__file__).resolve().parents[1]


def run(path):
    manifest = json.loads((path / "manifest.json").read_text())
    summary = json.loads((path / "summary.json").read_text())
    journal = json.loads((path / "journal.json").read_text())
    validate_goal_outcomes(manifest, summary, journal)
    inferences = {x["tick"]: x for x in journal if x["event"] == "policy_inference"}
    actions = [x for x in journal if x["event"] == "executed_action"]
    validate_policy_claim(manifest, summary, len(inferences))
    for name, spec in manifest["vendor"].items():
        vendor = ROOT.parent / "vendor" / name
        assert not spec["status"]
        assert (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=vendor, text=True).strip()
            == spec["sha"]
        )
        assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=vendor, text=True)
    if manifest["arguments"]["policy"] == "pi05-local":
        for key, file in (
            ("pi05_checkpoint_manifest_sha256", "models/pi05_libero/verified-manifest.json"),
            ("tokenizer_sha256", "cache/openpi/big_vision/paligemma_tokenizer.model"),
        ):
            assert hashlib.sha256((ROOT.parent / file).read_bytes()).hexdigest() == manifest[key]
        metadata = json.loads((path / "policy_metadata.json").read_text())
        assert metadata["policy_rng_seed"] == 0 and metadata["config"] == "pi05_libero"
    configure_libero(
        ROOT.parent / "vendor/openpi/third_party/libero", ROOT.parent / "config/libero"
    )
    env = LiberoEnvironment("table_center", 0, 7)
    try:
        obs = env.observation
        compare_observation(path / "initial_observation.npz", obs)
        loaded = {}
        for record in actions:
            tick = record["policy_tick"]
            inference = inferences[tick]
            plan = inference["plan"]
            if tick not in loaded:
                compare_observation(
                    path / f"policy_input_{tick:05d}.npz", policy_input(obs, plan["prompt"])
                )
                with np.load(path / f"policy_output_{tick:05d}.npz", allow_pickle=False) as data:
                    loaded[tick] = data["actions"].copy()
                assert np.isfinite(loaded[tick]).all()
            np.testing.assert_array_equal(record["action"], loaded[tick][record["output_offset"]])
            assert record["command_id"] == plan["command"]["command_id"]
            obs = env.step(np.asarray(record["action"], dtype=np.float64))
            assert (
                evaluate_goal(env, plan["command"]["destination"]) == record["goal_evaluation_only"]
            )
            assert env.evaluator_success == record["official_plate_success_evaluator_only"]
            np.testing.assert_allclose(
                obs["robot0_eef_pos"], record["eef_position_after"], rtol=0, atol=1e-9
            )
            np.testing.assert_allclose(
                obs["robot0_gripper_qpos"], record["gripper_position_after"], rtol=0, atol=1e-9
            )
        compare_observation(path / "final_observation.npz", obs)
        np.testing.assert_array_equal(
            imageio.imread(path / "last_frame.png"), obs["agentview_image"][::-1, ::-1]
        )
    finally:
        env.close()
    with imageio.get_reader(path / "rollout.mp4") as video:
        frames = sum(1 for _ in video)
    assert frames == len(actions) + 1
    return {
        "status": "GOAL_ACTION_PHYSICS_REPLAY_PASS",
        "source_sha": manifest["code_sha"],
        "steps": len(actions),
        "inferences": len(inferences),
        "frames": frames,
        "goal_success": summary["goal_success_evaluator_only"],
        "scientific_acceptance": False,
        "scope": "saved-action replay; does not rerun model inference or SAM",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, run(args.run))
