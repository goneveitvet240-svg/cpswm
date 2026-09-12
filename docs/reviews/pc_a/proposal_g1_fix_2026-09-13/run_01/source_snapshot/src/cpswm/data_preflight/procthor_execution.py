"""Execute an exogenous schedule in a real supplied AI2-THOR controller.

No simulator replacement is created here. TeleportObject is explicitly an
evaluator intervention, not humanoid/robot pickup, navigation, or handoff success.
Pixels are captured from Unity; schedule actors are never exported as detections.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any

from cpswm.data_preflight.procthor_schedule import (
    ReleaseQueue,
    Schedule,
    digest,
    event_chain,
    validate_position,
)
from cpswm.data_preflight.simulator_capture import ControllerLike, RawCaptureSession


def write_json(path: Path, data: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, indent=2, allow_nan=False)


def execute_schedule(
    controller: ControllerLike,
    schedule: Schedule,
    output: Path,
    *,
    object_ids: dict[str, str],
    anchors: dict[str, dict[str, dict[str, float]]],
    rotations: dict[str, dict[str, float]],
    runtime_provenance: dict[str, Any],
    observer_route: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """Fail closed on uncertain/failed actions; preserve attempted and partial receipts.

    Calling owner must have loaded and source-bound the declared ProcTHOR house.
    This function cannot authenticate an arbitrary controller supplied by a caller.
    All raw intervention requests and metadata remain in evaluator_only.
    """
    # Detach even object.__setattr__ bypasses before any controller callback.
    schedule = replace(schedule, events=tuple(replace(event) for event in schedule.events))
    schedule.validate()
    route = json.loads(json.dumps(observer_route, allow_nan=False))
    for view in route:
        if set(view) != {"position", "rotation", "horizon", "standing"}:
            raise ValueError("observer route must be fixed poses, not target-conditioned commands")
        validate_position(view["position"])
        validate_position(view["rotation"])
        if type(view["standing"]) is not bool or type(view["horizon"]) not in {int, float}:
            raise ValueError("invalid observer pose")
        if not math.isfinite(view["horizon"]) or not -30 <= view["horizon"] <= 60:
            raise ValueError("observer horizon outside SDK range")
    object_ids = dict(object_ids)
    rotations = json.loads(json.dumps(rotations, allow_nan=False))
    if set(rotations) != set(object_ids):
        raise ValueError("explicit per-instance rotations required")
    for rotation in rotations.values():
        validate_position(rotation)
    anchors = json.loads(json.dumps(anchors, allow_nan=False))
    if set(object_ids) != set(schedule.instance_keys) or len(set(object_ids.values())) != len(
        object_ids
    ):
        raise ValueError("physical instances require distinct SDK IDs")
    if set(anchors) != set(schedule.location_keys):
        raise ValueError("anchors must cover the location support exactly")
    for points in anchors.values():
        if set(points) != set(object_ids):
            raise ValueError("each location needs one explicit pose per instance")
        for point in points.values():
            validate_position(point)
    for instance in object_ids:
        for first, second in combinations((points[instance] for points in anchors.values()), 2):
            if all(math.isclose(first[k], second[k], abs_tol=0.002, rel_tol=0) for k in first):
                raise ValueError("different destinations cannot alias one physical pose")
    output.mkdir(parents=True, exist_ok=False)
    private = output / "evaluator_only"
    private.mkdir()
    visible = output / "observation_candidates"
    visible.mkdir()
    write_json(private / "schedule.json", schedule.payload())
    write_json(private / "observer_route.json", route)
    write_json(
        private / "binding.json",
        {"object_ids": object_ids, "anchors": anchors, "rotations": rotations},
    )
    capture = RawCaptureSession(
        controller,
        private / "raw",
        run_id=schedule.schedule_block_id,
        runtime_provenance=runtime_provenance,
        allowed_actions=("Pass", "TeleportObject", "TeleportFull"),
        depth_unit="m",
    )
    queue = ReleaseQueue()
    records: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    status: dict[str, Any] = {
        "scope": "controller exogenous geometry schedule; NOT embodied actor/model closed loop",
        "schedule_sha256": digest(schedule.payload()),
        "scheduled_events": len(schedule.events),
        "completed_events": 0,
        "complete": False,
        "method_input_authorized": False,
        "rendered_human_roles_verified": False,
        "physical_manipulation_verified": False,
    }

    def positions(metadata: dict[str, Any]) -> dict[str, dict[str, float]]:
        by_id = {obj["objectId"]: obj for obj in metadata["objects"]}
        if not set(object_ids.values()) <= set(by_id):
            raise ValueError("tracked physical instance disappeared")
        return {
            key: validate_position(by_id[value]["position"]) for key, value in object_ids.items()
        }

    def same(a: dict[str, float], b: dict[str, float]) -> bool:
        return all(math.isclose(a[k], b[k], abs_tol=0.002, rel_tol=0) for k in a)

    def step(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        receipt = capture.capture(request)
        index = receipt["step_index"]
        metadata = json.loads((private / "raw/evaluator_only" / f"{index:06d}.json").read_text())
        if not receipt["last_action_success"]:
            raise RuntimeError(
                f"actual SDK action failed at step {index}: {metadata.get('errorMessage')}"
            )
        return receipt, metadata

    try:
        _, initial = step({"action": "Pass"})
        actual = positions(initial)
        for index, instance in enumerate(schedule.instance_keys):
            if not same(
                actual[instance],
                anchors[schedule.location_keys[index % len(schedule.location_keys)]][instance],
            ):
                raise ValueError("schedule initial location disagrees with real simulator state")
        for event_index, event in enumerate(schedule.events):
            before = actual
            if not same(
                actual[event.instance_key], anchors[event.source_location][event.instance_key]
            ):
                raise ValueError("actual instance trajectory diverged from scheduled source")
            attempt: dict[str, Any] = {
                "event_id": event.event_id,
                "chain_plan": event_chain(event),
                "actual_steps": [],
                "actual_before": before,
            }
            records.append(attempt)
            # Handoff roles are explicit in the plan; only geometric movement is executed.
            # Never call a Pass a successful embodied handoff.
            if event.destination_location != event.source_location:
                receipt, metadata = step(
                    {
                        "action": "TeleportObject",
                        "objectId": object_ids[event.instance_key],
                        "position": anchors[event.destination_location][event.instance_key],
                        "rotation": rotations[event.instance_key],
                        "forceAction": False,
                        "forceKinematic": True,
                    }
                )
            else:
                receipt, metadata = step({"action": "Pass"})
            attempt["actual_steps"].append(receipt["step_index"])
            actual = positions(metadata)
            for instance in object_ids:
                expected = (
                    anchors[event.destination_location][instance]
                    if instance == event.instance_key
                    else before[instance]
                )
                if not same(actual[instance], expected):
                    raise ValueError(
                        "post-action pose mismatch or unintended second-instance movement"
                    )
            attempt["actual_after"] = actual
            attempt["geometry_verified"] = True
            attempt["actor_role_execution_verified"] = False
            if route and event.observation_selected:
                # Route index depends only on the clock, never object truth/visibility.
                receipt, metadata = step(
                    {
                        "action": "TeleportFull",
                        **route[event_index % len(route)],
                        "forceAction": False,
                    }
                )
                attempt["actual_steps"].append(receipt["step_index"])
                observer_after = positions(metadata)
                if any(not same(observer_after[key], actual[key]) for key in actual):
                    raise ValueError("observer route unexpectedly changed tracked instance state")
            # Export only pixels. Do not export intervention object IDs, intended locations,
            # success labels as detections, event types, role truth, phase, or correction truth.
            if event.observation_selected:
                sensor_name = f"{receipt['step_index']:06d}.npz"
                source = private / "raw/observations" / sensor_name
                target = visible / sensor_name
                with target.open("xb") as handle:
                    handle.write(source.read_bytes())
                write_json(
                    visible / f"{receipt['step_index']:06d}.json",
                    {
                        "sensor_file": sensor_name,
                        "sensor_sha256": receipt["sensor_sha256"],
                        "depth_unit": receipt["depth_unit"],
                        "status": "raw_candidate_requires_visible_evidence_adapter",
                    },
                )
            queue.enqueue(event, f"{receipt['step_index']:06d}.json")
            deliveries.extend(queue.release(event.tick))
            status["completed_events"] += 1
        deliveries.extend(queue.finish(max(x.release_tick for x in schedule.events)))
        if len(deliveries) != sum(e.observation_selected for e in schedule.events):
            raise ValueError("selected captures and deliveries disagree")
        status["complete"] = True
    except BaseException as error:
        status["error_type"] = type(error).__name__
        status["error"] = str(error)
        raise
    finally:
        write_json(private / "execution.json", records)
        write_json(visible / "release_journal.json", deliveries)
        status["released_captures"] = len(deliveries)
        write_json(output / "result.json", status)
    return status
