"""Three real iTHOR SDK steps using the existing local build, not a D1 schedule."""

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / sys.argv[1]
OUT.mkdir(exist_ok=False)
sys.path.insert(0, str(ROOT / "src"))

import ai2thor  # noqa: E402
from ai2thor.controller import Controller  # noqa: E402

from cpswm.data_preflight.simulator_capture import RawCaptureSession  # noqa: E402

binary = Path(sys.argv[2]).resolve(strict=True)


class IsolatedLogController(Controller):
    # Only change SDK log destination. Simulator events and execution are untouched.
    @property
    def log_dir(self):
        return str(OUT / "unity_logs")


started = time.time()
controller = None
status = {
    "argv": [sys.executable, *sys.argv],
    "cwd": str(Path.cwd()),
    "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "sdk_controller_sha256": hashlib.sha256(
        (Path(ai2thor.__file__).parent / "controller.py").read_bytes()
    ).hexdigest(),
    "scope": "real iTHOR transport smoke, NOT ProcTHOR multi-actor D1 or model closed loop",
    "python": sys.version,
    "executable": sys.executable,
    "platform": platform.platform(),
    "sdk_version": ai2thor.__version__,
    "sdk_path": ai2thor.__file__,
    "unity_binary": str(binary),
    "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "source_sha256": hashlib.sha256(
        (ROOT / "src/cpswm/data_preflight/simulator_capture.py").read_bytes()
    ).hexdigest(),
    "real_simulator_run_verified": False,
}
try:
    controller = IsolatedLogController(
        local_executable_path=str(binary),
        scene="FloorPlan1",
        width=64,
        height=64,
        renderDepthImage=True,
        server_timeout=20.0,
        server_start_timeout=30.0,
    )
    capture = RawCaptureSession(
        controller,
        OUT / "capture",
        run_id="pc-a-ithor-transport-smoke-20260913",
        runtime_provenance={
            "sdk_version": ai2thor.__version__,
            "scene": "FloorPlan1",
            "binary_sha256": status["binary_sha256"],
        },
        allowed_actions=("Pass", "RotateRight", "MoveAhead"),
        depth_unit="m",
    )
    status["steps"] = [
        capture.capture({"action": action}) for action in ("Pass", "RotateRight", "MoveAhead")
    ]
    status["real_simulator_run_verified"] = True
except BaseException as error:
    status["error_type"] = type(error).__name__
    status["error"] = str(error)
    raise
finally:
    if controller is not None:
        controller.stop()
    status["seconds"] = time.time() - started
    status["source_after_sha256"] = hashlib.sha256(
        (ROOT / "src/cpswm/data_preflight/simulator_capture.py").read_bytes()
    ).hexdigest()
    status["source_unchanged"] = status["source_sha256"] == status["source_after_sha256"]
    with (OUT / "result.json").open("x", encoding="utf-8") as handle:
        json.dump(status, handle, indent=2)
    print(json.dumps({k: status[k] for k in ("scope", "real_simulator_run_verified", "seconds")}))
