"""Bounded development views of the already selected ProcTHOR training house.

No evaluator object/pose metadata is used to choose the four camera directions.
This is acquisition, not a CPSWM policy or a multi-person interaction episode.
Run with the existing AI2-THOR interpreter and local executable.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpswm.data_preflight.simulator_capture import RawCaptureSession  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unity-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    house_path = (
        ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    house_bytes = house_path.read_bytes()
    binary = args.unity_binary.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    import ai2thor
    from ai2thor.controller import Controller

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return str(args.output / "unity_logs")

    controller = None
    receipt = {
        "scope": "four fixed development camera views, no persons added",
        "sdk": ai2thor.__version__,
        "python": sys.version,
        "unity_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "house_sha256": hashlib.sha256(house_bytes).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "width": 512,
        "height": 512,
        "complete": False,
    }
    try:
        controller = LocalLogs(
            local_executable_path=str(binary),
            scene=json.loads(house_bytes),
            width=512,
            height=512,
            renderDepthImage=True,
            server_timeout=30.0,
            server_start_timeout=30.0,
        )
        if controller.last_event.metadata.get("lastActionSuccess") is not True:
            raise RuntimeError("house initialization failed")
        session = RawCaptureSession(
            controller,
            args.output / "raw",
            run_id=args.output.name,
            runtime_provenance=receipt,
            allowed_actions=("Pass", "RotateRight"),
            depth_unit="m",
        )
        retained = []
        for request in [
            {"action": "Pass"},
            *[{"action": "RotateRight", "degrees": 90} for _ in range(3)],
        ]:
            row = session.capture(request)
            path = args.output / "raw/observations" / f"{row['step_index']:06d}.json"
            retained.append(
                {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
        receipt["captures"] = retained
        receipt["complete"] = True
    finally:
        if controller is not None:
            controller.stop()
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
