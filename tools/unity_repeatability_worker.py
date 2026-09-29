"""Optional private full-metadata observer; public RGB/status response is unchanged."""

import argparse
import json
from pathlib import Path

import unity_camera_feedback_worker as transport


def wrap_response(responder, log_dir):
    index = 0

    def observe(identity, event):
        nonlocal index
        response = responder(identity, event)
        private = log_dir / "evaluator_only/full_metadata"
        private.mkdir(parents=True, exist_ok=True)
        (private / f"{index:03d}.json").write_text(
            json.dumps(dict(action_id=identity, metadata=event.metadata), indent=2) + "\n"
        )
        index += 1
        return response

    return observe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log-dir", type=Path, required=True)
    args, _ = parser.parse_known_args()
    transport.method_response = wrap_response(transport.method_response, args.log_dir)
    transport.main()
