"""Native CPSWM goal controller in the locked core Python environment."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController, observation_from_payload
from cpswm.simulation.memory import SimulationMemory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--arm", choices=sorted(SimulationMemory.ARMS), default="native_joint")
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    controller = MemoryGoalController(args.episode, fixture["catalogue"], args.arm)
    print(
        json.dumps({"ok": True, "python": sys.executable, "revision": controller.revision}),
        flush=True,
    )
    for line in sys.stdin:
        try:
            body = json.loads(line)
            result = {}
            with redirect_stdout(sys.stderr):
                operation = body["operation"]
                if operation in {"history", "visual"}:
                    obs = observation_from_payload(body["observation"])
                    ingest = (
                        controller.observe_history
                        if operation == "history"
                        else controller.observe_visual
                    )
                    ingest(obs, body["now"])
                elif operation == "plan":
                    result = controller.plan(body["tick"])
                elif operation in {"validate", "step", "feedback"}:
                    plan = GoalPlan.from_payload(body["plan"])
                    if operation == "validate":
                        controller.validate(plan)
                    elif operation == "step":
                        controller.record_step(plan, body["completed_at"])
                    else:
                        controller.feedback(
                            plan,
                            observation_from_payload(body["observation"]),
                            body["control_steps"],
                        )
                elif operation != "audit":
                    raise ValueError("unknown operation")
                audit = controller.audit()
            reply = {"ok": True, **result, "audit": audit, "revision": controller.revision}
        except Exception as error:
            reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        print(json.dumps(reply, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
