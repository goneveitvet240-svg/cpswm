# ruff: noqa: E402
"""Source-owned D0 native posterior feeding the real manipulation goal protocol.

The cross-world location/object map is an explicit operator fixture. It tests
interface consumption, not natural grounding or transfer of physical semantics.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from run_matched_value import dataset_for, make_state

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController, observation_from_payload
from cpswm.system.evaluation_operations.structure_two_memory_action import (
    MemoryActionRuntime,
    NativeGoalMemory,
)
from cpswm.system.reproducibility import content_sha256


def controller_for(arm="native_joint"):
    episode = dataset_for("sparse32").visible_episodes(Split.TEST)[0]
    state = make_state(episode, arm)
    r = state.runtime
    state.runtime = MemoryActionRuntime(arm=r.arm, config=r.config, neural_model=r.neural_model)
    prefix = episode.steps[:3]
    for step in prefix:
        state.observe(step.model_copy(deep=True))
        state.predict()
        state.feedback(step.model_copy(deep=True))
    # Frozen location order from the PUBLIC map, never sorted by truth/outcome.
    destinations = ("stove", "plate", "unbound-2", "unbound-3")
    if len(episode.known_location_ids) != len(destinations):
        raise ValueError("explicit four-location development binding changed")
    bindings = dict(zip(episode.known_location_ids, destinations, strict=True))
    memory = NativeGoalMemory(state.runtime, bindings)
    catalogue = {x: f"put the black bowl on the {x}" for x in destinations}
    controller = MemoryGoalController(
        str(episode.episode_id), catalogue, "source_replay", native_memory=memory
    )
    source = {
        "condition": "sparse32",
        "episode_index": 0,
        "prefix_steps": 3,
        "episode_id": str(episode.episode_id),
        "arm": arm,
        "public_prefix_sha256": content_sha256(prefix),
        "public_prefix": [s.model_dump(mode="json") for s in prefix],
        "bindings": {str(k): v for k, v in bindings.items()},
        "binding_scope": "operator-defined D0-to-LIBERO interface test, not natural grounding",
    }
    return controller, source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--arm", choices=("native_joint", "native_six_potential_ablation"), default="native_joint"
    )
    args = parser.parse_args()
    controller, source = controller_for(args.arm)
    print(json.dumps({"ok": True, "source": source, "audit": controller.audit()}), flush=True)
    for line in sys.stdin:
        try:
            body = json.loads(line)
            op = body["operation"]
            result = {}
            if op == "visual":
                controller.observe_visual(
                    observation_from_payload(body["observation"]), body["now"]
                )
            elif op == "plan":
                dist = controller.memory.destination_distribution()
                if min(dist, key=lambda k: (-dist[k], k)).startswith("unbound-"):
                    result = {"status": "needs_execution_binding", "distribution": dist}
                else:
                    result = controller.plan(body["tick"])
            elif op in ("validate", "step", "feedback"):
                plan = GoalPlan.from_payload(body["plan"])
                if op == "validate":
                    controller.validate(plan)
                elif op == "step":
                    controller.record_step(plan, body["completed_at"])
                else:
                    controller.feedback(
                        plan, observation_from_payload(body["observation"]), body["control_steps"]
                    )
            elif op != "audit":
                raise ValueError("unknown native goal operation")
            reply = {
                "ok": True,
                **result,
                "audit": controller.audit(),
                "revision": controller.revision,
            }
        except Exception as error:
            reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        print(json.dumps(reply, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
