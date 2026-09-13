"""One live Unity controller; JSON transport only, no CPSWM memory initialization."""

import argparse
import base64
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--house", required=True)
    parser.add_argument("--log-dir", required=True)
    args = parser.parse_args()
    from ai2thor.controller import Controller

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return args.log_dir

    controller = LocalLogs(
        local_executable_path=args.binary,
        scene=json.loads(Path(args.house).read_text()),
        width=320,
        height=320,
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    seen = set()
    try:
        print("CPSWM_RESPONSE " + json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request.get("stop"):
                break
            identity = request["action_id"]
            if identity in seen:
                raise ValueError("worker will not redispatch an action ID")
            action = request["action"]
            if action not in {"Pass", "RotateRight", "RotateLeft"}:
                raise ValueError("unsupported camera request")
            degrees = request["degrees"]
            if not 0 <= degrees <= 90:
                raise ValueError("unbounded rotation")
            seen.add(identity)
            kwargs = {} if action == "Pass" else {"degrees": degrees}
            event = controller.step(action=action, **kwargs)
            capture_time = datetime.now(UTC).isoformat()
            buffer = io.BytesIO()
            np.save(buffer, event.frame, allow_pickle=False)
            response = {
                "action_id": identity,
                "capture_time": capture_time,
                "success": event.metadata.get("lastActionSuccess") is True,
                "error": event.metadata.get("errorMessage", ""),
                "rgb_npy": base64.b64encode(buffer.getvalue()).decode(),
            }
            # Only pixels and the execution status leave this process. Scene truth
            # (object IDs, poses, names, visibility lists) is not forwarded.
            print("CPSWM_RESPONSE " + json.dumps(response), flush=True)
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
