"""Real development-only ProcTHOR geometry pilot. No training or hidden splits.

Run with an AI2-THOR interpreter and an existing local Unity binary. The supplied
archive must match the pinned official train LFS digest before any house is read.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.data_preflight.procthor_execution import execute_schedule, write_json  # noqa: E402
from cpswm.data_preflight.procthor_schedule import build_schedule  # noqa: E402

DATA_REVISION = "439193522244720b86d8c81cde2e51e3a4d150cf"
TRAIN_SHA256 = "ee3c4aa14b4d8f0895fecfb5fdaca59395427ca1018b2f9aeeedbc61e5824587"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-archive", type=Path, required=True)
    parser.add_argument("--unity-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--house-index", type=int, default=0)
    parser.add_argument("--days", type=int, choices=range(7, 15), default=7)
    parser.add_argument("--actors", type=int, choices=range(3, 6), default=3)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()
    if args.house_index < 0 or args.house_index >= 10000:
        raise ValueError("index outside official training split")
    archive = args.train_archive.resolve(strict=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != TRAIN_SHA256:
        raise ValueError("archive is not the pinned complete official TRAIN artifact")
    binary = args.unity_binary.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with gzip.open(archive, "rt", encoding="utf-8") as handle:
        for index, line in enumerate(handle):  # noqa: B007 - selected line used after break
            if index == args.house_index:
                break
        else:
            raise ValueError("training house missing")
    house = json.loads(line)
    house_bytes = line.encode()
    with (output / "train_house.json").open("xb") as handle:
        handle.write(house_bytes)
    import ai2thor
    from ai2thor.controller import Controller

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return str(output / "unity_logs")

    source_paths = [Path(__file__), *sorted((ROOT / "src/cpswm/data_preflight").glob("*.py"))]
    sources = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }
    receipt = {
        "argv": [sys.executable, *sys.argv],
        "cwd": str(Path.cwd()),
        "python": sys.version,
        "platform": platform.platform(),
        "sdk_version": ai2thor.__version__,
        "sdk_path": ai2thor.__file__,
        "dataset_revision": DATA_REVISION,
        "dataset_split": "train",
        "use_partition": "development",
        "archive_sha256": TRAIN_SHA256,
        "house_index": args.house_index,
        "house_sha256": hashlib.sha256(house_bytes).hexdigest(),
        "unity_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "sdk_controller_sha256": hashlib.sha256(
            (Path(ai2thor.__file__).parent / "controller.py").read_bytes()
        ).hexdigest(),
        "source_before": sources,
        "real_procthor_loaded": False,
        "complete_D1": False,
        "training_started": False,
    }
    controller = None
    started = time.monotonic()
    try:
        controller = LocalLogs(
            local_executable_path=str(binary),
            scene=house,
            width=96,
            height=96,
            renderDepthImage=True,
            server_timeout=30.0,
            server_start_timeout=30.0,
        )
        initial = controller.last_event.metadata
        write_json(output / "initial_metadata.json", initial)
        if initial.get("lastActionSuccess") is not True:
            raise RuntimeError("ProcTHOR house load failed")
        receipt["real_procthor_loaded"] = True
        groups = defaultdict(list)
        for obj in initial["objects"]:
            if obj.get("pickupable") and not obj.get("isBroken"):
                groups[obj["objectType"]].append(obj)
        eligible = sorted(key for key, objects in groups.items() if len(objects) >= 2)
        if not eligible:
            raise RuntimeError(
                "house has no same-type physical instance pair; no synthetic duplication"
            )
        pair = sorted(groups[eligible[0]], key=lambda x: x["objectId"])[:2]
        # Original resting contact can contain small collider penetration that a
        # collision-checked teleport rejects. Explicit development initialization,
        # not forceAction: raise each selected object 2.5 cm, log and verify it.
        initialization = []
        for obj in pair:
            point = {**obj["position"], "y": obj["position"]["y"] + 0.025}
            request = {
                "action": "TeleportObject",
                "objectId": obj["objectId"],
                "position": point,
                "rotation": obj["rotation"],
                "forceAction": False,
                "forceKinematic": True,
            }
            event = controller.step(**request)
            initialization.append({"request": request, "metadata": event.metadata})
            if event.metadata.get("lastActionSuccess") is not True:
                write_json(output / "initialization.json", initialization)
                raise RuntimeError("collision-checked clearance initialization failed")
        write_json(output / "initialization.json", initialization)
        current = {obj["objectId"]: obj for obj in controller.last_event.metadata["objects"]}
        pair = [current[obj["objectId"]] for obj in pair]
        receipt["initialization"] = (
            "explicit 0.025 m collision-checked clearance; not unmodified house"
        )
        reach = controller.step(action="GetReachablePositions")
        write_json(output / "reachable_metadata.json", reach.metadata)
        if reach.metadata["lastActionSuccess"] is not True:
            raise RuntimeError("actual reachability query failed")
        points = reach.metadata["actionReturn"]
        agent = reach.metadata["agent"]["position"]
        points = sorted(
            (p for p in points if (p["x"] - agent["x"]) ** 2 + (p["z"] - agent["z"]) ** 2 > 1),
            key=lambda p: (p["x"], p["z"]),
        )
        if len(points) < 12:
            raise RuntimeError("not enough reachable development anchors")
        floor_y = min(p["y"] for room in house["rooms"] for p in room["floorPolygon"])
        instances = ("instance_0", "instance_1")
        locations = ("location_0", "location_1", "location_2")
        anchors = {}
        for location_index, location in enumerate(locations):
            anchors[location] = {}
            for instance_index, (instance, obj) in enumerate(zip(instances, pair, strict=True)):
                if location_index == instance_index:
                    anchors[location][instance] = obj["position"]
                else:
                    point = points[(location_index * 2 + instance_index) * (len(points) // 6)]
                    bbox = obj["axisAlignedBoundingBox"]
                    anchors[location][instance] = {
                        "x": point["x"],
                        "z": point["z"],
                        "y": floor_y
                        + bbox["size"]["y"] / 2
                        - (bbox["center"]["y"] - obj["position"]["y"])
                        + 0.015,
                    }
        schedule = build_schedule(
            house_id=f"procthor-10k:{DATA_REVISION}:train:{args.house_index}",
            house_sha256=receipt["house_sha256"],
            schedule_block_id=f"dev-house-{args.house_index}-seed-{args.seed}",
            seed=args.seed,
            days=args.days,
            actors=tuple(f"actor_{i}" for i in range(args.actors)),
            instance_keys=instances,
            location_keys=locations,
        )
        # Reserve separate fixed observer lanes, disjoint from EVERY planned object
        # anchor, not just the current hidden object position. No truth-following route.
        reserved = [point for poses in anchors.values() for point in poses.values()]
        observer_points = [
            point
            for point in points
            if all(
                (point["x"] - anchor["x"]) ** 2 + (point["z"] - anchor["z"]) ** 2 > 0.75**2
                for anchor in reserved
            )
        ]
        if len(observer_points) < 6:
            raise RuntimeError("no collision-separated fixed observer route")
        receipt["execution"] = execute_schedule(
            controller,
            schedule,
            output / "schedule_run",
            object_ids={key: obj["objectId"] for key, obj in zip(instances, pair, strict=True)},
            rotations={key: obj["rotation"] for key, obj in zip(instances, pair, strict=True)},
            anchors=anchors,
            observer_route=tuple(
                {
                    "position": observer_points[(i % 6) * (len(observer_points) // 6)],
                    "rotation": {"x": 0.0, "y": float((i // 6) * 90), "z": 0.0},
                    "horizon": 45.0,
                    "standing": True,
                }
                for i in range(24)
            ),
            runtime_provenance={
                key: receipt[key]
                for key in (
                    "sdk_version",
                    "dataset_revision",
                    "archive_sha256",
                    "house_sha256",
                    "unity_sha256",
                )
            },
        )
    except BaseException as error:
        receipt["error_type"], receipt["error"] = type(error).__name__, str(error)
        raise
    finally:
        if controller is not None:
            controller.stop()
        receipt["seconds"] = time.monotonic() - started
        receipt["source_after"] = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        }
        receipt["source_unchanged"] = receipt["source_before"] == receipt["source_after"]
        write_json(output / "receipt.json", receipt)
        print(
            json.dumps(
                {
                    key: receipt[key]
                    for key in (
                        "real_procthor_loaded",
                        "complete_D1",
                        "seconds",
                        "source_unchanged",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
