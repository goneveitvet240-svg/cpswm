"""Real Unity diagnostic; raw transport evidence, never a human/learning gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def summarize(metadata):
    return {
        key: metadata.get(key)
        for key in (
            "agentId", "agent", "sceneName", "lastAction", "lastActionSuccess",
            "errorCode", "errorMessage", "actionReturn", "inventoryObjects",
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--house", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scene", choices=("ordinary", "procedural"), required=True)
    parser.add_argument("--count", type=int, choices=(1, 2), required=True)
    parser.add_argument("--post-initialize", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import ai2thor
    import ai2thor.controller
    import ai2thor.fifo_server
    import ai2thor.server

    trace = []
    trace_stream = (args.output / "transport.jsonl").open("x")

    def record(entry):
        entry = {"index": len(trace), "monotonic": time.monotonic(), **entry}
        trace_stream.write(json.dumps(entry, cls=ai2thor.server.NumpyAwareEncoder) + "\n")
        trace_stream.flush()
        trace.append(entry)

    class RecordingServer(ai2thor.fifo_server.FifoServer):
        def _send_message(self, field_type, payload):
            # Captures the serialized transport payload, not caller intent.
            record({"kind": "send", "payload": json.loads(payload)})
            return super()._send_message(field_type, payload)

        def create_event(self, metadata, files):
            record({"kind": "receive", "metadata": metadata})
            event = super().create_event(metadata, files)
            record({
                "kind": "decoded", "type": type(event).__name__,
                "events": [summarize(e.metadata) for e in event.events],
            })
            return event

    class LocalController(ai2thor.controller.Controller):
        def _build_server(self, host, port, width, height):
            # SDK 5.0 compares server classes by identity; explicitly construct
            # this instrumentation subclass without patching the installed SDK.
            if self.server is None:
                self.server = RecordingServer(
                    width=width, height=height, timeout=self.server_timeout,
                    depth_format=self.depth_format, add_depth_noise=self.add_depth_noise,
                )

        @property
        def log_dir(self):
            return str(args.output / "unity_logs")

    assembly = args.binary.parent.parent / "Resources/Data/Managed/Assembly-CSharp.dll"
    bound = [Path(__file__), args.binary, assembly, args.house,
             Path(ai2thor.controller.__file__), Path(ai2thor.server.__file__),
             Path(ai2thor.fifo_server.__file__)]
    before = {str(p.resolve()): sha(p) for p in bound}
    receipt = {
        "scope": "actual Unity multi-agent diagnosis; NOT human execution or training",
        "sdk": ai2thor.__version__, "python": sys.version,
        "executable": sys.executable, "argv": sys.argv,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "files_before": before, "scene_kind": args.scene, "requested_count": args.count,
        "post_initialize": args.post_initialize,
        "human_execution_verified": False, "training_started": False,
    }
    controller = None
    started = time.monotonic()
    try:
        scene = json.loads(args.house.read_text()) if args.scene == "procedural" else "FloorPlan1"
        controller = LocalController(
            local_executable_path=str(args.binary), scene=scene,
            server_class=RecordingServer, width=96, height=96,
            renderDepthImage=True, agentCount=1 if args.post_initialize else args.count,
            makeAgentsVisible=True, server_timeout=8.0, server_start_timeout=20.0,
        )
        if args.post_initialize:
            controller.step(action="Initialize", agentCount=args.count, makeAgentsVisible=True)
        receipt["initialized"] = [summarize(e.metadata) for e in controller.last_event.events]
        event = controller.step(action="Pass", agentId=args.count - 1)
        receipt["address_probe"] = [summarize(e.metadata) for e in event.events]
        receipt["observed_count"] = len(event.events)
    except Exception as error:
        receipt["exception"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if controller is not None:
            try:
                controller.stop()
            except Exception as error:
                receipt["stop_exception"] = repr(error)
        trace_stream.close()
        receipt["seconds"] = time.monotonic() - started
        receipt["files_after"] = {str(p.resolve()): sha(p) for p in bound}
        receipt["files_unchanged"] = before == receipt["files_after"]
        receipt["trace_sha256"] = sha(args.output / "transport.jsonl")
        save(args.output / "receipt.json", receipt)
        save(args.output / "trace_summary.json", [
            ({"index": r["index"], "kind": "receive", "sequenceId": r["metadata"].get("sequenceId"),
              "activeAgentId": r["metadata"].get("activeAgentId"),
              "agents": [summarize(a) for a in r["metadata"]["agents"]]}
             if r["kind"] == "receive" else
             {**r, "payload": {k: ("<bound house>" if k == "house" else v)
                               for k, v in r["payload"].items()}}
             if r["kind"] == "send" else r)
            for r in trace
        ])
    print(json.dumps({k: receipt.get(k) for k in (
        "scene_kind", "requested_count", "post_initialize", "observed_count",
        "exception", "seconds", "files_unchanged",
    )}), flush=True)


if __name__ == "__main__":
    main()
