"""Fresh native-source/command replay and optional real physics verification."""

import argparse
import hashlib
import json
from pathlib import Path


def verify_core(path):
    from native_goal_worker import controller_for

    from cpswm.simulation.goal_control import GoalPlan, observation_from_payload

    source = json.loads((path / "native_source.json").read_text())
    controller, expected = controller_for(source["source"]["arm"])
    assert expected == source["source"]
    assert controller.audit() == source["audit"]
    journal = json.loads((path / "journal.json").read_text())
    inferences, actions = {}, []
    validated = None
    for row in journal:
        if row["event"] == "core_rpc":
            body = row["request"]
            op = body["operation"]
            result = {}
            if op == "visual":
                controller.observe_visual(
                    observation_from_payload(body["observation"]), body["now"]
                )
            elif op == "plan":
                result = controller.plan(body["tick"])
            elif op in ("validate", "step", "feedback"):
                plan = GoalPlan.from_payload(body["plan"])
                if op == "validate":
                    controller.validate(plan)
                    validated = (
                        plan.command.payload()
                        if hasattr(plan.command, "payload")
                        else body["plan"]["command"]
                    )
                elif op == "step":
                    assert actions[-1]["tick"] == body["completed_at"]
                    controller.record_step(plan, body["completed_at"])
                else:
                    controller.feedback(
                        plan, observation_from_payload(body["observation"]), body["control_steps"]
                    )
            else:
                raise ValueError("unexpected core operation")
            reply = {
                "ok": True,
                **result,
                "audit": controller.audit(),
                "revision": controller.revision,
            }
            assert json.loads(json.dumps(reply)) == row["receipt"]
        elif row["event"] == "inference":
            plan = GoalPlan.from_payload(row["plan"])
            controller.validate(plan)
            assert row["tick"] not in inferences
            inferences[row["tick"]] = row
        elif row["event"] == "action":
            assert row["command"] == validated
            validated = None
            assert row["inference_tick"] in inferences
            assert row["tick"] == 101 + len(actions)
            actions.append(row)
        else:
            raise ValueError("unexpected journal event")
    summary = json.loads((path / "summary.json").read_text())
    assert summary["steps"] == len(actions) and summary["inferences"] == len(inferences)
    assert summary["goal_success"] == actions[-1]["goal_evaluator_only"]["success"]
    assert not controller.step_ticks and controller.pending is None
    return {
        "native_source_and_commands": True,
        "steps": len(actions),
        "inferences": len(inferences),
        "journal_sha256": hashlib.sha256((path / "journal.json").read_bytes()).hexdigest(),
    }


def verify_physics(path):
    import imageio.v2 as imageio
    import numpy as np
    from synergy_goal_evaluator import evaluate_goal

    from cpswm.simulation.integrations.libero_env import LiberoEnvironment, configure_libero
    from cpswm.simulation.integrations.policy import policy_input

    root = Path(__file__).resolve().parents[1]
    configure_libero(
        root.parent / "vendor/openpi/third_party/libero", root.parent / "config/libero"
    )
    journal = json.loads((path / "journal.json").read_text())
    manifest = json.loads((path / "manifest.json").read_text())
    summary = json.loads((path / "summary.json").read_text())
    assert summary["pi05_inference_executed"] == (manifest["policy"] == "pi05-local")
    if summary["pi05_inference_executed"]:
        assert (
            hashlib.sha256(
                (root.parent / "models/pi05_libero/verified-manifest.json").read_bytes()
            ).hexdigest()
            == manifest["checkpoint_manifest_sha256"]
        )
    env = LiberoEnvironment("table_center", 0, 7)
    actions = 0

    def compare(saved, actual):
        with np.load(saved, allow_pickle=False) as data:
            assert set(data.files) == set(actual)
            for k in actual:
                np.testing.assert_array_equal(data[k], actual[k])

    try:
        obs = env.observation
        compare(path / "initial_observation.npz", obs)
        for row in journal:
            if row["event"] == "inference":
                plan, tick = row["plan"], row["tick"]
                compare(path / f"input_{tick}.npz", policy_input(obs, plan["prompt"]))
                with np.load(path / f"output_{tick}.npz", allow_pickle=False) as data:
                    output = data["actions"].copy()
                assert np.isfinite(output).all()
            elif row["event"] == "action":
                assert row["inference_tick"] == tick
                assert row["command"] == plan["command"]
                np.testing.assert_array_equal(row["action"], output[row["offset"]])
                obs = env.step(np.asarray(row["action"]))
                np.testing.assert_allclose(row["eef"], obs["robot0_eef_pos"], rtol=0, atol=1e-9)
                np.testing.assert_allclose(
                    row["gripper"], obs["robot0_gripper_qpos"], rtol=0, atol=1e-9
                )
                assert row["goal_evaluator_only"] == evaluate_goal(
                    env, plan["command"]["destination"]
                )
                actions += 1
        compare(path / "final_observation.npz", obs)
        np.testing.assert_array_equal(
            imageio.imread(path / "last_frame.png"), obs["agentview_image"][::-1, ::-1]
        )
        assert actions == summary["steps"]
    finally:
        env.close()
    with imageio.get_reader(path / "rollout.mp4") as reader:
        frames = sum(1 for _ in reader)
    assert frames == actions + 1
    return {"physical_replay": True, "actions": actions, "video_frames": frames}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--physics", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_physics(args.path) if args.physics else verify_core(args.path)
    args.output.write_text(json.dumps(result, indent=2))
    print(result)
