"""Run with the core CPSWM venv; stdout is only a JSON-lines protocol."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.memory import SimulationMemory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--arm", choices=sorted(SimulationMemory.ARMS), default="native_joint")
    args = parser.parse_args()
    memory = SimulationMemory(args.episode, ("image_left", "image_center", "image_right"), args.arm)
    print(
        json.dumps({"ok": True, "revision": memory.revision, "python": sys.executable}), flush=True
    )
    for line in sys.stdin:
        try:
            body = json.loads(line)
            body["visibility"] = Visibility(body["visibility"])
            body["actors"] = tuple(
                tuple(pair) for pair in body.get("actors", [["unknown_actor", 1.0]])
            )
            observation = Observation(**body)
            with redirect_stdout(sys.stderr):
                memory.ingest(observation, observation.available_at)
                audit = memory.audit()
            reply = {
                "ok": True,
                "revision": memory.revision,
                "audit": audit,
                "current_location": memory.current_location,
            }
        except Exception as error:
            reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        print(json.dumps(reply, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
