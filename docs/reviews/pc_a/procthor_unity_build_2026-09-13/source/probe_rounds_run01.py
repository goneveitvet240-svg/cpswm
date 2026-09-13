"""Two real-Unity author audit rounds. Robot capability only; never human/learning acceptance."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
import sys
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--house", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--round", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import ai2thor.controller
    import ai2thor.fifo_server
    import ai2thor.server
    import msgpack
    import numpy as np

    house = json.loads(args.house.read_text())
    bound = [
        Path(__file__),
        args.binary,
        args.house,
        args.binary.parent.parent / "Resources/Data/Managed/AI2-THOR-Base.dll",
    ]
    before = {str(p): sha(p) for p in bound}
    results = []
    active_stream = None
    case_directory = None

    def record(value):
        active_stream.write(json.dumps(value, cls=ai2thor.server.NumpyAwareEncoder) + "\n")
        active_stream.flush()

    class Wire(ai2thor.fifo_server.FifoServer):
        pending = None

        def _read_with_timeout(self, *a, **kw):
            data = super()._read_with_timeout(*a, **kw)
            if self.pending is None:
                if len(data) == self.header_size:
                    field, length = struct.unpack(self.header_format, data)
                    record({"kind": "wire_header", "field": field, "length": length})
                    if field != ai2thor.fifo_server.FieldType.END_OF_MESSAGE:
                        self.pending = field
            else:
                field, self.pending = self.pending, None
                item = {
                    "kind": "wire_payload",
                    "field": field,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                if field in (
                    ai2thor.fifo_server.FieldType.METADATA,
                    ai2thor.fifo_server.FieldType.METADATA_PATCH,
                ):
                    item["metadata"] = msgpack.loads(data, raw=False, strict_map_key=False)
                record(item)
            return data

        def _send_message(self, field_type, payload):
            record({"kind": "send", "payload": json.loads(payload)})
            return super()._send_message(field_type, payload)

        def create_event(self, metadata, files):
            record({"kind": "raw_metadata", "metadata": metadata})
            event = super().create_event(metadata, files)
            record(
                {
                    "kind": "decoded",
                    "agents": [e.metadata for e in event.events],
                    "frames": [hashlib.sha256(e.frame.tobytes()).hexdigest() for e in event.events],
                }
            )
            return event

    class Controller(ai2thor.controller.Controller):
        def _build_server(self, host, port, width, height):
            if self.server is None:
                self.server = Wire(
                    width=width,
                    height=height,
                    timeout=self.server_timeout,
                    depth_format=self.depth_format,
                    add_depth_noise=self.add_depth_noise,
                )

        @property
        def log_dir(self):
            return str(case_directory / "unity_logs")

    def check(name, condition):
        record({"kind": "assertion", "name": name, "pass": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def pose(event):
        return [copy.deepcopy(e.metadata["agent"]) for e in event.events]

    def spawn(c, generation, count=2, request_id="audit", **extra):
        return c.step(
            action="CpswmSpawnAgents",
            generation=generation,
            agentCount=count,
            requestId=request_id,
            **extra,
        )

    def context(c):
        event = c.step(action="CpswmHouseContext")
        check("context_success", event.metadata["lastActionSuccess"])
        return event.metadata["actionReturn"]

    def roster(event, count):
        check("exact_roster", len(event.events) == count)
        check("unique_ids", [e.metadata["agentId"] for e in event.events] == list(range(count)))
        check("all_success", all(e.metadata["lastActionSuccess"] for e in event.events))
        points = [
            np.array([e.metadata["agent"]["position"][k] for k in ("x", "y", "z")])
            for e in event.events
        ]
        check(
            "finite_distinct_positions",
            all(np.isfinite(p).all() for p in points)
            and all(
                np.linalg.norm(points[i] - points[j]) > 0.4 for i in range(count) for j in range(i)
            ),
        )
        check(
            "real_rgb_depth",
            all(
                e.frame.shape == (96, 96, 3)
                and e.depth_frame.shape == (96, 96)
                and np.isfinite(e.depth_frame).all()
                for e in event.events
            ),
        )

    def isolate(c, count):
        for identity in range(count):
            for action, delta in (("RotateRight", 90), ("RotateLeft", -90)):
                previous = pose(c.last_event)
                event = c.step(action=action, agentId=identity, degrees=90)
                following = pose(event)
                check(
                    "addressed_action_success",
                    event.metadata["lastActionSuccess"] and event.metadata["agentId"] == identity,
                )
                for i in range(count):
                    check(
                        "translation_isolated",
                        all(
                            abs(previous[i]["position"][k] - following[i]["position"][k]) < 0.002
                            for k in ("x", "y", "z")
                        ),
                    )
                    turn = (following[i]["rotation"]["y"] - previous[i]["rotation"]["y"]) % 360
                    expected = delta % 360 if i == identity else 0
                    check("rotation_isolated", abs((turn - expected + 180) % 360 - 180) < 0.02)

    def reject_unchanged(c, **request):
        previous = pose(c.last_event)
        event = c.step(**request)
        check("reject", not event.metadata["lastActionSuccess"])
        check("reject_no_roster_pose_change", pose(event) == previous)

    def positive(c, count):
        info = context(c)
        check("house_ready", info["houseReady"] and not info["poisoned"])
        roster(spawn(c, info["generation"], count=count), count)
        isolate(c, count)

    def negatives(c):
        info = context(c)
        base = {
            "action": "CpswmSpawnAgents",
            "generation": info["generation"],
            "agentCount": 2,
            "requestId": "negative",
        }
        for key, value in (
            ("generation", "foreign"),
            ("generation", None),
            ("agentCount", 0),
            ("agentCount", 7),
            ("agentCount", 2.5),
            ("agentCount", True),
            ("requestId", ""),
            ("requestId", "x" * 129),
            ("untrusted", 1),
        ):
            reject_unchanged(c, **{**base, key: value})
        missing = dict(base)
        missing.pop("generation")
        reject_unchanged(c, **missing)
        roster(spawn(c, info["generation"]), 2)

    def no_house(c):
        info = context(c)
        check("not_ready", not info["houseReady"])
        reject_unchanged(
            c,
            action="CpswmSpawnAgents",
            generation=info["generation"],
            agentCount=2,
            requestId="early",
        )

    def state_machine(c):
        original_generation = context(c)["generation"]
        roster(spawn(c, original_generation), 2)
        isolate(c, 2)
        prior = pose(c.last_event)
        event = spawn(c, original_generation)
        check("idempotent", event.metadata["lastActionSuccess"] and pose(event) == prior)
        for change in (
            {"requestId": "different"},
            {"agentCount": 3},
            {"generation": "stale"},
            {"agentId": 1},
        ):
            request = {
                "action": "CpswmSpawnAgents",
                "generation": original_generation,
                "agentCount": 2,
                "requestId": "audit",
                **change,
            }
            reject_unchanged(c, **request)
        for identity in (0, 1):
            reject_unchanged(c, action="Initialize", agentCount=2, agentId=identity)
        c.reset(scene=copy.deepcopy(house))
        fresh = context(c)
        check(
            "fresh_generation", fresh["generation"] != original_generation and fresh["houseReady"]
        )
        reject_unchanged(
            c,
            action="CpswmSpawnAgents",
            generation=original_generation,
            agentCount=2,
            requestId="audit",
        )
        roster(spawn(c, fresh["generation"]), 2)
        isolate(c, 2)

    cases = [(f"positive_{n}", lambda c, n=n: positive(c, n), True) for n in (1, 2, 3, 6)]
    cases += [("malformed_then_valid", negatives, True), ("before_house", no_house, False)]
    if args.round == 2:
        cases = [("continuous_state_machine", state_machine, True)]
    for name, execute, create_house in cases:
        case_directory = args.output / name
        case_directory.mkdir()
        active_stream = (case_directory / "transport.jsonl").open("x")
        c = Controller.__new__(Controller)
        started = time.monotonic()
        result = {"case": name, "passed": False}
        try:
            c.__init__(
                local_executable_path=str(args.binary),
                scene=copy.deepcopy(house) if create_house else "Procedural",
                server_class=Wire,
                width=96,
                height=96,
                renderDepthImage=True,
                makeAgentsVisible=True,
                agentCount=1,
                server_timeout=15,
                server_start_timeout=30,
            )
            execute(c)
            result["passed"] = True
        except Exception as error:
            result["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            try:
                c.stop()
            except Exception as error:
                result["stop_error"] = str(error)
                result["passed"] = False
            active_stream.close()
            result["seconds"] = time.monotonic() - started
            result["transport_sha256"] = sha(case_directory / "transport.jsonl")
        results.append(result)
        print(json.dumps(result), flush=True)
    after = {str(p): sha(p) for p in bound}
    receipt = {
        "round": args.round,
        "python": sys.version,
        "argv": sys.argv,
        "files_before": before,
        "files_after": after,
        "files_unchanged": before == after,
        "cases": results,
        "human_execution_verified": False,
        "training_started": False,
        "coverage": (
            "partial author runtime audit; partial-child failure, held-object "
            "and all collision states remain separate"
        ),
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    return int(before != after or not all(r["passed"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
