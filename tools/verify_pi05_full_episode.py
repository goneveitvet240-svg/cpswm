"""Replay recorded full-episode actions in LIBERO; no policy inference rerun.

Same-machine consistency evidence, not model-execution attestation or an
independent scientific review. The simulator success flag is evaluation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import numpy as np

from cpswm.simulation.integrations.libero_env import LiberoEnvironment, configure_libero
from cpswm.simulation.integrations.policy import policy_input


def validate_records(manifest: dict, summary: dict, journal: list) -> tuple[list, list]:
    args = manifest["arguments"]
    assert args["policy"] == "pi05-local" and args["stop_on_success"] is True
    assert args["steps"] == 220 and not args["sam"]
    assert summary["status"] == "POLICY_ROLLOUT_COMPLETE"
    assert summary["pi05_inference_executed"] is True
    assert summary["native_memory_connected"] is False
    assert summary["scientific_acceptance"] is False
    assert summary["source_unchanged"] is True and manifest["git_status"] == ""
    assert summary["task"] == args["task"]
    assert summary["requested_steps"] == args["steps"]
    actions = [x for x in journal if x.get("event") == "executed_action"]
    inferences = [x for x in journal if x.get("event") == "policy_inference"]
    n = len(actions)
    assert 0 < n <= args["steps"] and n == summary["steps"]
    assert [x["tick"] for x in actions] == list(range(n))
    assert [x["tick"] for x in inferences] == list(range(0, n, 5))
    assert all(type(x["task_success_evaluator_only"]) is bool for x in actions)
    success = [x["tick"] + 1 for x in actions if x["task_success_evaluator_only"]]
    if success:
        assert success == [n] and summary["stop_reason"] == "success"
        assert summary["first_success_step_evaluator_only"] == n
    else:
        assert n == args["steps"] and summary["stop_reason"] == "step_limit"
        assert summary["first_success_step_evaluator_only"] is None
    assert summary["task_success_evaluator_only"] is bool(success)
    for item in inferences:
        assert item["policy"] == args["policy"]
        assert item["prompt"] == summary["prompt"]
        assert item["revision"] == "task-instruction-only"
    return actions, inferences


def compare_observation(saved: Path, current: dict) -> None:
    with np.load(saved, allow_pickle=False) as recorded:
        assert set(recorded.files) == set(current)
        for key, value in current.items():
            if np.asarray(value).dtype.kind in "USui":
                np.testing.assert_array_equal(recorded[key], value, err_msg=key)
            else:
                np.testing.assert_allclose(recorded[key], value, rtol=0, atol=1e-9, err_msg=key)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stack = root.parent
    run = args.run.resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    journal = json.loads((run / "journal.json").read_text())
    actions, inferences = validate_records(manifest, summary, journal)
    for path, digest in manifest["sources"].items():
        assert not Path(path).is_absolute() and ".." not in Path(path).parts
        data = subprocess.check_output(["git", "show", f"{manifest['code_sha']}:{path}"], cwd=root)
        assert hashlib.sha256(data).hexdigest() == digest, path
    for name, vendor in manifest["vendor"].items():
        assert not vendor["status"]
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=stack / "vendor" / name, text=True
        ).strip()
        assert current == vendor["sha"]
        assert not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=stack / "vendor" / name, text=True
        )
    for key, path in (
        ("pi05_checkpoint_manifest_sha256", stack / "models/pi05_libero/verified-manifest.json"),
        ("tokenizer_sha256", stack / "cache/openpi/big_vision/paligemma_tokenizer.model"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[key]
    metadata = json.loads((run / "policy_metadata.json").read_text())
    assert metadata["config"] == "pi05_libero" and metadata["policy_rng_seed"] == 0
    assert metadata["upstream"] == manifest["vendor"]["openpi"]["sha"]
    inference_map = {x["tick"]: x for x in inferences}
    configure_libero(stack / "vendor/openpi/third_party/libero", stack / "config/libero")
    parameters = manifest["arguments"]
    env = LiberoEnvironment(parameters["task"], parameters["initial_state"], parameters["seed"])
    try:
        assert env.prompt == summary["prompt"]
        obs = env.observation
        compare_observation(run / "initial_observation.npz", obs)
        output = None
        for item in actions:
            tick = item["tick"]
            if tick in inference_map:
                compare_observation(
                    run / f"policy_input_{tick:05d}.npz", policy_input(obs, env.prompt)
                )
                with np.load(run / f"policy_output_{tick:05d}.npz", allow_pickle=False) as saved:
                    output = saved["actions"].copy()
                assert output.shape == (10, 7) and np.isfinite(output).all()
            assert output is not None
            np.testing.assert_array_equal(item["action"], output[tick % 5])
            assert item["revision"] == "task-instruction-only"
            assert item["result"] == "simulator_step_returned"
            obs = env.step(np.asarray(item["action"], dtype=np.float64))
            assert env.evaluator_success == item["task_success_evaluator_only"]
            np.testing.assert_allclose(
                obs["robot0_eef_pos"], item["eef_position_after"], rtol=0, atol=1e-9
            )
            np.testing.assert_allclose(
                obs["robot0_gripper_qpos"], item["gripper_position_after"], rtol=0, atol=1e-9
            )
        compare_observation(run / "final_observation.npz", obs)
        np.testing.assert_array_equal(
            imageio.imread(run / "last_frame.png"), obs["agentview_image"][::-1, ::-1]
        )
    finally:
        env.close()
    with imageio.get_reader(run / "rollout.mp4") as video:
        count = 0
        for frame in video:
            assert frame.shape == (256, 256, 3)
            count += 1
    assert count == summary["steps"] + 1
    result = {
        "status": "ACTION_PHYSICS_AND_SUCCESS_REPLAY_PASS",
        "run_source_sha": manifest["code_sha"],
        "verifier_source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "actions": len(actions),
        "inferences_recorded_not_reexecuted": len(inferences),
        "policy_inputs_reconstructed": len(inferences),
        "video_frames": count,
        "first_success_step_evaluator_only": summary["first_success_step_evaluator_only"],
        "task_success_evaluator_only": summary["task_success_evaluator_only"],
        "scope": (
            "same-machine action replay; no independent model attestation or scientific acceptance"
        ),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
