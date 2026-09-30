"""Reconstruct one fixed offline capture, keeping SDK truth outside public inputs.

This is same-machine archive verification under caller-supplied source/runtime
pins, not independent custody or a learned observation-factor evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
from offline_factor_asset_provenance import resolve_exposures
from offline_factor_manifest import FAR, IMAGE_SIZE, NEAR, OBSERVATION_ACTIONS
from run_instance_correspondence_diagnostic import reconstruct_catalog
from unity_rgbd_capture import camera_values

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.unity_rgbd import PROFILE, SCHEMA, decode_unity_rgbd
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


def _require(value, message):
    if not value:
        raise ValueError(message)


def _json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=constant)


def _inventory(directory, expected):
    _require(directory.is_dir() and not directory.is_symlink(), "missing capture directory")
    actual = set()
    for path in directory.iterdir():
        _require(path.is_file() and not path.is_symlink(), "nonregular capture entry")
        actual.add(path.name)
    _require(actual == expected, "capture file inventory differs from fixed protocol")
    return {str(directory / name): _sha((directory / name).read_bytes()) for name in actual}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _xyz(value):
    _require(type(value) is dict and set(value) == {"x", "y", "z"}, "invalid SDK xyz")
    result = [value[k] for k in ("x", "y", "z")]
    _require(all(type(v) in (float, int) and math.isfinite(v) for v in result), "nonfinite SDK xyz")
    return result


def _objects(metadata):
    objects = metadata["objects"]
    _require(type(objects) is list, "SDK object catalog is not a list")
    result = {}
    for obj in objects:
        identity = obj["objectId"]
        _require(type(identity) is str and identity and identity not in result, "invalid SDK ID")
        _require(type(obj["objectType"]) is str and obj["objectType"], "invalid SDK category")
        _xyz(obj["position"])
        _xyz(obj["rotation"])
        _xyz(obj["axisAlignedBoundingBox"]["center"])
        asset = obj.get("assetId")
        _require(asset is None or type(asset) is str, "invalid SDK asset ID")
        result[identity] = obj
    return result


def _source_objects(house):
    rows = {}

    def visit(objects):
        _require(type(objects) is list, "source objects must be a list")
        for obj in objects:
            identity = obj["id"]
            _require(identity not in rows, "duplicate source object ID")
            rows[identity] = obj
            visit(obj.get("children", []))

    visit(house["objects"])
    return rows


def _moved(before, after):
    return (
        math.dist(_xyz(before["position"]), _xyz(after["position"])) > 1e-5
        or math.dist(_xyz(before["rotation"]), _xyz(after["rotation"])) > 1e-5
        or math.dist(
            _xyz(before["axisAlignedBoundingBox"]["center"]),
            _xyz(after["axisAlignedBoundingBox"]["center"]),
        )
        > 1e-5
    )


def _public(directory, provenance):
    frames, scope, seen_actions, seen_observations = [], None, set(), set()
    previous_arrival = None
    binding_fields = {
        "worker": "worker_sha256",
        "unity": "unity_sha256",
        "house": "scene_sha256",
        "capture_configuration": "configuration_sha256",
    }
    for i, (action, degrees) in enumerate(OBSERVATION_ACTIONS):
        path = directory / f"{i:03d}-state.json"
        document = _json(path)
        decoded = StateCodec().loads(path.read_text())
        _require(
            json.loads(StateCodec().dumps(decoded)) == document,
            "public state contains noncanonical or unreachable data",
        )
        _require(type(decoded) is tuple and len(decoded) == 2, "invalid public state pair")
        command, delivery = decoded
        for value, cls in ((command, ObservationCommand), (delivery, ObservationDelivery)):
            _require(
                type(value) is cls and set(vars(value)) == {f.name for f in fields(cls)},
                "public command or delivery contains unexpected fields",
            )
        _require(
            type(command.action_id) is UUID
            and command.action_id not in seen_actions
            and type(command.snapshot_id) is UUID
            and command.action == action
            and type(command.degrees) in (int, float)
            and command.degrees == degrees
            and command.reason == "fixed-offline-factor-view@1"
            and command.source_ids == ()
            and delivery.action_id == command.action_id
            and delivery.success is True
            and delivery.error == ""
            and type(delivery.observations) is tuple,
            "public action trace differs from fixed protocol",
        )
        seen_actions.add(command.action_id)
        camera, _ = decode_unity_rgbd(delivery.observations, cutoff=delivery.received_at)
        env = delivery.observations[0].envelope()
        current_scope = (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
        if scope is None:
            scope = current_scope
        _require(
            current_scope == scope
            and len(set(scope)) == 3
            and all(key.version == 4 for key in scope),
            "public scope differs or encodes nonrandom house identifiers",
        )
        _require(
            command.action_id == camera.action_id
            and command.decision_time <= camera.capture_time <= delivery.received_at
            and env.arrival_time == delivery.received_at
            and (previous_arrival is None or previous_arrival <= command.decision_time),
            "public command capture times are not causal",
        )
        previous_arrival = delivery.received_at
        _require(
            all(
                getattr(camera, field) == provenance[name] for name, field in binding_fields.items()
            ),
            "public camera provenance differs from trusted capture pins",
        )
        for raw in delivery.observations:
            _require(
                type(raw) is RawModalityObservation
                and set(vars(raw)) == {f.name for f in fields(RawModalityObservation)},
                "unexpected raw observation fields",
            )
            e = raw.envelope()
            identity = e.identity.observation_id
            _require(
                identity not in seen_observations
                and e.metadata.record_id == identity
                and e.metadata.schema_name == SCHEMA
                and e.metadata.schema_version == "0.1.0"
                and e.metadata.model_version == "unity-camera-transport-rgbd-v1"
                and e.metadata.recorded_time == delivery.received_at
                and e.payload.payload_id == identity
                and e.payload.payload_uri is None,
                "public envelope metadata differs from the transport whitelist",
            )
            seen_observations.add(identity)
        frames.append((command, delivery, camera))
    return frames, scope


def verify_capture(directory: Path, house_path: Path, expected_provenance: dict) -> dict:
    """Verify every fixed exposure; caller separately pins original plan and runtime.

    Unknown or source-unmapped assets are retained and ineligible for supervision.
    The returned all-assets set includes invisible/context objects, so a caller can
    quarantine shared assets across partitions without hiding training exposure.
    """
    directory, house_path = Path(directory), Path(house_path)
    _require(
        set(expected_provenance) == {"worker", "unity", "house", "capture_configuration"}
        and all(
            type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in expected_provenance.values()
        ),
        "invalid trusted provenance",
    )
    _require(
        house_path.is_file()
        and not house_path.is_symlink()
        and _sha(house_path.read_bytes()) == expected_provenance["house"],
        "original house bytes differ from trusted plan",
    )
    _require(
        expected_provenance["capture_configuration"]
        == content_sha256((PROFILE, IMAGE_SIZE, IMAGE_SIZE, 60.0, NEAR, FAR, False)),
        "capture configuration differs from fixed protocol",
    )
    house = _json(house_path)
    source = _source_objects(house)
    hashes = _inventory(directory / "public", {f"{i:03d}-state.json" for i in range(8)})
    private = directory / "unity-logs/evaluator_only"
    hashes.update(
        _inventory(
            private / "sdk-events",
            {
                f"{i:03d}{suffix}"
                for i in range(12)
                for suffix in (".json", "-rgb.npy", "-depth.npy")
            },
        )
    )
    hashes.update(
        _inventory(
            private / "instances",
            {
                f"{i:03d}{suffix}"
                for i in range(12)
                for suffix in (".json", "-segmentation.npy", "-masks.npz")
            },
        )
    )
    # Public boundary and causality are checked before opening SDK instance labels.
    frames, scope = _public(directory / "public", expected_provenance)
    initial, paused, initial_camera, moved_at_pause, frame_rows = None, None, None, [], []
    initial_agent_position = None
    for i in range(12):
        record = _json(private / "sdk-events" / f"{i:03d}.json")
        _require(
            set(record) == {"index", "requested", "owner", "metadata"}, "unexpected SDK record"
        )
        metadata = record["metadata"]
        expected_request = (
            None
            if i == 0
            else {"action": ("PausePhysicsAutoSim", "Pass", "Pass")[i - 1]}
            if i < 4
            else {"action": OBSERVATION_ACTIONS[i - 4][0], **({"degrees": 45.0} if i > 4 else {})}
        )
        owner = None if i < 4 else str(frames[i - 4][0].action_id)
        _require(
            type(record["index"]) is int
            and record["index"] == i
            and record["requested"] == expected_request
            and record["owner"] == owner
            and metadata["lastActionSuccess"] is True
            and metadata["errorMessage"] == ""
            and metadata["lastAction"] == ("CreateHouse" if i == 0 else expected_request["action"]),
            "SDK action trace differs from fixed protocol",
        )
        rgb_path = private / "sdk-events" / f"{i:03d}-rgb.npy"
        depth_path = private / "sdk-events" / f"{i:03d}-depth.npy"
        rgb, depth = (np.load(p, allow_pickle=False) for p in (rgb_path, depth_path))
        _require(
            rgb.dtype == np.uint8
            and rgb.shape == (IMAGE_SIZE, IMAGE_SIZE, 3)
            and depth.dtype == np.float32
            and depth.shape == (IMAGE_SIZE, IMAGE_SIZE)
            and np.isfinite(depth).all()
            and (depth >= 0).all()
            and (depth <= FAR - NEAR + 1e-5).all(),
            "SDK RGB-D dimensions or depth range differ",
        )
        camera = camera_values(SimpleNamespace(metadata=metadata, frame=rgb, depth_frame=depth))
        objects = _objects(metadata)
        if initial is None:
            initial, initial_camera = objects, camera
            initial_agent_position = _xyz(metadata["agent"]["position"])
            agent = house["metadata"]["agentPoses"]["default"]
            _require(agent == house["metadata"]["agent"], "source default agent alias differs")
            _require(
                math.dist(
                    [initial_agent_position[k] for k in (0, 2)],
                    [_xyz(agent["position"])[k] for k in (0, 2)],
                )
                < 1e-3
                and abs((camera["yaw_degrees"] - agent["rotation"]["y"] + 180) % 360 - 180) < 1e-3
                and abs(camera["pitch_degrees"] - agent["horizon"]) < 1e-3,
                "SDK initial lateral pose or heading differs from original house agent",
            )
        _require(set(objects) == set(initial), "SDK object coverage changed during capture")
        for identity, obj in objects.items():
            _require(
                (obj["objectType"], obj.get("assetId"))
                == (initial[identity]["objectType"], initial[identity].get("assetId")),
                "SDK object category or asset changed during capture",
            )
        if i == 1:
            paused = objects
            moved_at_pause = sorted(key for key in initial if _moved(initial[key], objects[key]))
        if i > 1:
            _require(
                not any(_moved(paused[key], objects[key]) for key in objects),
                "object moved after physics pause",
            )
        yaw = (initial_camera["yaw_degrees"] + max(0, i - 4) * 45) % 360
        _require(
            abs((camera["yaw_degrees"] - yaw + 180) % 360 - 180) < 1e-3
            and abs(camera["pitch_degrees"] - initial_camera["pitch_degrees"]) < 1e-3
            and math.dist(camera["position_m"], initial_camera["position_m"]) < 1e-5
            and camera["vertical_fov_degrees"] == 60
            and math.dist(_xyz(metadata["agent"]["position"]), initial_agent_position) < 1e-5,
            "SDK camera moved outside fixed rotation schedule",
        )
        info = _json(private / "instances" / f"{i:03d}.json")
        _require(
            set(info) == {"action_id", "catalog", "colors"}
            and info["action_id"] == owner
            and info["colors"] == metadata["colors"],
            "instance catalog owner or SDK colors differ",
        )
        segmentation = np.load(
            private / "instances" / f"{i:03d}-segmentation.npy", allow_pickle=False
        )
        _require(
            segmentation.shape == (IMAGE_SIZE, IMAGE_SIZE, 3), "instance image dimensions differ"
        )
        with np.load(private / "instances" / f"{i:03d}-masks.npz", allow_pickle=False) as masks:
            instances = reconstruct_catalog(
                info["catalog"], info["colors"], masks, segmentation, metadata["objects"]
            )
        if i >= 4:
            command, delivery, public_camera = frames[i - 4]
            _require(
                rgb_path.read_bytes() == delivery.observations[0].payload_bytes
                and depth_path.read_bytes() == delivery.observations[1].payload_bytes,
                "public RGB-D bytes differ from same SDK event",
            )
            public_values = public_camera.model_dump(mode="json")
            _require(
                all(public_values[k] == value for k, value in camera.items()),
                "public self-pose differs from same SDK event",
            )
            frame_rows.append(
                dict(
                    index=i - 4,
                    action_id=str(command.action_id),
                    sdk_event=i,
                    instances=instances,
                    rgb_sha256=public_camera.rgb_sha256,
                    depth_sha256=public_camera.depth_sha256,
                    decision_time=command.decision_time.isoformat(),
                    capture_time=public_camera.capture_time.isoformat(),
                    received_at=delivery.received_at.isoformat(),
                )
            )
    rows, differences = [], []
    for identity, obj in sorted(paused.items()):
        original = source.get(identity)
        asset = obj.get("assetId")
        known = type(asset) is str and bool(asset.strip()) and asset == asset.strip()
        reasons = []
        if not known:
            reasons.append("unknown_sdk_asset")
        if original is None:
            reasons.append("sdk_instance_not_in_source_objects")
        elif original.get("assetId") != asset:
            reasons.append("source_sdk_asset_mismatch")
        source_residual = (
            None
            if original is None
            else math.dist(_xyz(original["position"]), _xyz(initial[identity]["position"]))
        )
        # Source placement centers and runtime transform pivots are different
        # reference points in this pinned renderer. Their distance is not motion.
        if identity in moved_at_pause:
            reasons.append("object_changed_before_physics_pause")
        row = dict(
            object_id=identity,
            object_type=obj["objectType"],
            asset_id=asset,
            source_asset_id=None if original is None else original.get("assetId"),
            position_m=_xyz(obj["position"]),
            aabb_center_m=_xyz(obj["axisAlignedBoundingBox"]["center"]),
            source_position_m=None if original is None else _xyz(original["position"]),
            position_changed_during_initialization=identity in moved_at_pause,
            source_placement_to_sdk_pivot_distance_m=source_residual,
            source_placement_to_sdk_aabb_center_distance_m=(
                None
                if original is None
                else math.dist(
                    _xyz(original["position"]),
                    _xyz(initial[identity]["axisAlignedBoundingBox"]["center"]),
                )
            ),
            eligible_pending_partition_audit=not reasons,
            exclusion_reasons=reasons,
        )
        rows.append(row)
        if reasons:
            differences.append(dict(object_id=identity, reasons=reasons))
    exposures = resolve_exposures(house, list(initial.values()))
    missing = sorted(set(source) - set(initial))
    _require(
        all(_sha(Path(path).read_bytes()) == digest for path, digest in hashes.items()),
        "capture changed during verification",
    )
    _require(
        _sha(house_path.read_bytes()) == expected_provenance["house"],
        "house changed during verification",
    )
    return dict(
        schema="cpswm.offline-factor-capture-verification.v1",
        frames=8,
        sdk_events=12,
        scope=[str(key) for key in scope],
        all_assets=sorted(
            {row["exposure_asset_id"] for row in exposures if row["exposure_asset_id"] is not None}
        ),
        unknown_assets=[row["object_id"] for row in exposures if not row["known"]],
        asset_exposure_provenance=exposures,
        raw_missing_asset_id_objects=[
            row["object_id"] for row in rows if "unknown_sdk_asset" in row["exclusion_reasons"]
        ],
        source_initial_agent_position_m=_xyz(
            house["metadata"]["agentPoses"]["default"]["position"]
        ),
        sdk_initial_agent_position_m=initial_agent_position,
        initial_agent_vertical_displacement_m=initial_agent_position[1]
        - house["metadata"]["agentPoses"]["default"]["position"]["y"],
        position_reference_definitions=dict(
            source_position_m="prefab_bounds_center_placement_input",
            position_m="SDK_transform_pivot_at_capture",
            aabb_center_m="SDK_world_axis_aligned_bounds_center_at_capture",
        ),
        formal_training_position_target_selected=False,
        instances=rows,
        source_sdk_differences=differences,
        source_instances_missing_in_sdk=missing,
        initial_to_pause_changed_objects=moved_at_pause,
        frame_records=frame_rows,
        independence_claim=False,
        supervision_export_authorized=False,
        verification_scope="same_machine_archive_consistency_with_external_source_runtime_pins",
    )
