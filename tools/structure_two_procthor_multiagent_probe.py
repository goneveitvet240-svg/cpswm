"""Bounded real-runtime capability probe, not a human model or training producer."""

import hashlib
import json
import sys
import time
from pathlib import Path

import ai2thor
from ai2thor.controller import Controller

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/pc_a/proposal_g1_fix_2026-09-13" / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)
binary = Path(sys.argv[2])
house_path = (
    ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
)


class LocalLogs(Controller):
    @property
    def log_dir(self):
        return str(OUT / "unity_logs")


receipt = {
    "scope": "minimum two-agent capability probe, not D1 coverage or human execution",
    "sdk": ai2thor.__version__,
    "python": sys.version,
    "unity_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "house_sha256": hashlib.sha256(house_path.read_bytes()).hexdigest(),
    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "request": {
        "sdk_method": "reset",
        "scene": "same pinned house",
        "agentCount": 2,
        "makeAgentsVisible": True,
    },
    "multiple_agents_verified": False,
    "training_started": False,
}
controller = None
started = time.monotonic()
try:
    controller = LocalLogs(
        local_executable_path=str(binary),
        scene=json.loads(house_path.read_text()),
        width=96,
        height=96,
        renderDepthImage=True,
        server_timeout=8.0,
        server_start_timeout=20.0,
    )
    receipt["house_loaded"] = controller.last_event.metadata["lastActionSuccess"]
    if receipt["house_loaded"] is not True:
        raise RuntimeError("house did not load")
    event = controller.reset(
        scene=json.loads(house_path.read_text()), agentCount=2, makeAgentsVisible=True
    )
    receipt["response"] = event.metadata
    receipt["agent_events"] = len(getattr(event, "events", []))
    receipt["multiple_agents_verified"] = (
        event.metadata["lastActionSuccess"] and receipt["agent_events"] >= 2
    )
except BaseException as error:
    receipt.update(exception_type=type(error).__name__, exception=str(error))
finally:
    if controller is not None:
        controller.stop()
    receipt["seconds"] = time.monotonic() - started
    with (OUT / "receipt.json").open("x") as handle:
        json.dump(receipt, handle, indent=2)
print(json.dumps({k: v for k, v in receipt.items() if k != "response"}), flush=True)
