"""Complete controlled archives and coherent forgeries; no empirical capture claim."""

import json
import shutil
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from offline_factor_manifest import FAR, IMAGE_SIZE, NEAR, OBSERVATION_ACTIONS
from unity_offline_factor_worker import OfflineFactorRecorder
from unity_rgbd_capture import rgbd_response
from verify_offline_factor_capture import verify_capture

from cpswm.perception_mapping.unity_rgbd import PROFILE, observations_from_response
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


def write_json(path, value):
    path.write_text(json.dumps(value))


def xyz(x=0.0, y=0.0, z=0.0):
    return dict(x=x, y=y, z=z)


class ControlledController:
    def __init__(self, initial_motion=False):
        self.initial_motion, self.index, self.yaw = initial_motion, 0, 90.0
        self.last_event = self.event("CreateHouse")

    def event(self, action):
        objects = []
        for identity, category, asset in (
            ("a", "Apple", "apple_asset"),
            ("b", "Bottle", "bottle_asset"),
            ("floor", "Floor", None),
        ):
            position = xyz(x=1.0 if identity == "a" and self.initial_motion and self.index else 0.0)
            objects.append(
                dict(
                    objectId=identity,
                    objectType=category,
                    assetId=asset,
                    position=position,
                    rotation=xyz(),
                    axisAlignedBoundingBox=dict(center={**position, "y": 0.05}),
                )
            )
        shape = (IMAGE_SIZE, IMAGE_SIZE)
        mask = np.zeros(shape, dtype=bool)
        mask[self.index : self.index + 8, :8] = True
        segmentation = np.zeros((*shape, 3), dtype=np.uint8)
        segmentation[mask] = [1, 2, 3]
        return SimpleNamespace(
            frame=np.full((*shape, 3), self.index, dtype=np.uint8),
            depth_frame=np.full(shape, 1.0 + self.index / 10, dtype=np.float32),
            instance_segmentation_frame=segmentation,
            instance_masks={"a": mask},
            metadata=dict(
                lastAction=action,
                lastActionSuccess=True,
                errorMessage="",
                depthFormat="Meters",
                screenWidth=IMAGE_SIZE,
                screenHeight=IMAGE_SIZE,
                fov=60.0,
                cameraPosition=xyz(x=1.0, y=1.6, z=3.0),
                agent=dict(
                    position=xyz(x=1.0, y=0.95, z=3.0), rotation=xyz(y=self.yaw), cameraHorizon=30.0
                ),
                objects=objects,
                colors=[dict(name="a", color=[1, 2, 3])],
            ),
        )

    def step(self, action, **kwargs):
        self.index += 1
        if action == "RotateRight":
            self.yaw = (self.yaw + kwargs["degrees"]) % 360
        self.last_event = self.event(action)
        return self.last_event


def build_capture(directory, *, initial_motion=False):
    directory.mkdir()
    public = directory / "public"
    public.mkdir()
    private = directory / "unity-logs/evaluator_only"
    private.mkdir(parents=True)
    house_path = directory / "house.json"
    write_json(
        house_path,
        dict(
            metadata=dict(
                agent=dict(position=xyz(x=1.0, y=0.95, z=3.0), rotation=xyz(y=90.0), horizon=30.0)
            ),
            objects=[
                dict(
                    id="a",
                    assetId="apple_asset",
                    position=xyz(),
                    children=[dict(id="b", assetId="bottle_asset", position=xyz())],
                )
            ],
        ),
    )
    provenance = dict(
        worker="a" * 64,
        unity="b" * 64,
        house=sha256(house_path.read_bytes()).hexdigest(),
        capture_configuration=content_sha256(
            (PROFILE, IMAGE_SIZE, IMAGE_SIZE, 60.0, NEAR, FAR, False)
        ),
    )
    recorder = OfflineFactorRecorder(ControlledController(initial_motion), private, IMAGE_SIZE)
    recorder.prepare()
    scope = tuple(uuid4() for _ in range(3))
    start = datetime(2026, 9, 30, tzinfo=UTC)
    for index, (action, degrees) in enumerate(OBSERVATION_ACTIONS):
        decision = start + timedelta(seconds=index * 3)
        command = ObservationCommand(
            uuid4(), uuid4(), action, degrees, "fixed-offline-factor-view@1", (), decision
        )
        event = recorder.observe(
            dict(action_id=str(command.action_id), action=action, degrees=degrees)
        )
        response = rgbd_response(str(command.action_id), event)
        response["capture_time"] = (decision + timedelta(seconds=1)).isoformat()
        arrival = decision + timedelta(seconds=2)
        rows = observations_from_response(
            response,
            action_id=command.action_id,
            scope=scope,
            arrival=arrival,
            provenance=provenance,
        )
        delivery = ObservationDelivery(command.action_id, rows, True, "", arrival)
        (public / f"{index:03d}-state.json").write_text(StateCodec().dumps((command, delivery)))
    return house_path, provenance


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    directory = tmp_path_factory.mktemp("offline-verifier") / "capture"
    house, provenance = build_capture(directory)
    return directory, house, provenance


@pytest.fixture
def archive(original, tmp_path):
    source, _, provenance = original
    directory = tmp_path / "copy"
    shutil.copytree(source, directory)
    return directory, directory / "house.json", provenance


def test_complete_owned_archive_reconstructs_visible_and_invisible_instances(original):
    result = verify_capture(*original)
    assert (result["frames"], result["sdk_events"]) == (8, 12)
    assert result["all_assets"] == ["apple_asset", "bottle_asset"]
    assert result["unknown_assets"] == ["floor"]
    assert [row["object_id"] for row in result["instances"]] == ["a", "b", "floor"]
    assert result["instances"][0]["position_m"] != result["instances"][0]["aabb_center_m"]
    assert all(len(frame["instances"]) == 3 for frame in result["frame_records"])
    assert all(frame["instances"][1]["pixels"] == 0 for frame in result["frame_records"])
    assert result["independence_claim"] is False
    assert result["supervision_export_authorized"] is False


def rewrite_public(directory, *, camera_change=None, provenance_change=None, swap_depth=False):
    path = directory / "public/001-state.json"
    command, delivery = StateCodec().loads(path.read_text())
    camera = json.loads(delivery.observations[2].payload_bytes)
    metadata = json.loads(
        (directory / "unity-logs/evaluator_only/sdk-events/005.json").read_text()
    )["metadata"]
    event = SimpleNamespace(
        metadata=metadata,
        frame=np.load(directory / "unity-logs/evaluator_only/sdk-events/005-rgb.npy"),
        depth_frame=np.load(
            directory
            / f"unity-logs/evaluator_only/sdk-events/{'006' if swap_depth else '005'}-depth.npy"
        ),
    )
    response = rgbd_response(str(command.action_id), event)
    response["capture_time"] = camera["capture_time"]
    response["camera"].update(camera_change or {})
    provenance = {
        name: camera[key]
        for name, key in (
            ("worker", "worker_sha256"),
            ("unity", "unity_sha256"),
            ("house", "scene_sha256"),
            ("capture_configuration", "configuration_sha256"),
        )
    }
    provenance.update(provenance_change or {})
    env = delivery.observations[0].envelope()
    rows = observations_from_response(
        response,
        action_id=command.action_id,
        scope=(env.identity.household_id, env.identity.session_id, env.identity.trace_id),
        arrival=delivery.received_at,
        provenance=provenance,
    )
    path.write_text(
        StateCodec().dumps(
            (command, ObservationDelivery(command.action_id, rows, True, "", delivery.received_at))
        )
    )


@pytest.mark.parametrize("attack", ["depth", "camera", "provenance"])
def test_coherent_public_packet_forgery_with_all_hashes_and_receipts_rebuilt(archive, attack):
    directory, house, provenance = archive
    rewrite_public(
        directory,
        swap_depth=attack == "depth",
        camera_change={"position_m": [1.1, 1.6, 3.0]} if attack == "camera" else None,
        provenance_change={"worker": "f" * 64} if attack == "provenance" else None,
    )
    with pytest.raises(
        ValueError,
        match={"depth": "same SDK event", "camera": "same SDK event", "provenance": "provenance"}[
            attack
        ],
    ):
        verify_capture(directory, house, provenance)


@pytest.mark.parametrize(
    "attack",
    [
        "omit_event",
        "extra_public",
        "invisible_instance",
        "mask",
        "colors",
        "asset",
        "camera_motion",
        "object_motion",
        "owner",
        "failed_action",
        "house",
        "private_metadata",
        "initial_action",
    ],
)
def test_complete_archives_reject_protocol_and_label_attacks(archive, attack):
    directory, house, provenance = archive
    private = directory / "unity-logs/evaluator_only"
    event_path, info_path = private / "sdk-events/006.json", private / "instances/006.json"
    event, info = json.loads(event_path.read_text()), json.loads(info_path.read_text())
    if attack == "omit_event":
        (private / "sdk-events/002-rgb.npy").unlink()
    elif attack == "extra_public":
        (directory / "public/labels.json").write_text("{}")
    elif attack in {"invisible_instance", "mask"}:
        mask_path = private / "instances/006-masks.npz"
        with np.load(mask_path) as masks:
            arrays = {k: masks[k].copy() for k in masks.files}
        if attack == "invisible_instance":
            omitted = info["catalog"].pop(1)
            arrays.pop(omitted["array_key"])
        else:
            arrays[info["catalog"][0]["array_key"]][100, 100] = True
        np.savez_compressed(mask_path, **arrays)
    elif attack == "colors":
        info["colors"][0]["color"] = [7, 8, 9]
    elif attack == "asset":
        info["catalog"][1]["asset_id"] = "renamed-held-out-asset"
    elif attack == "camera_motion":
        event["metadata"]["agent"]["rotation"]["y"] += 1
    elif attack == "object_motion":
        event["metadata"]["objects"][1]["position"]["x"] += 1
    elif attack == "owner":
        event["owner"] = str(uuid4())
    elif attack == "failed_action":
        event["metadata"]["lastActionSuccess"] = False
    elif attack == "initial_action":
        path = private / "sdk-events/000.json"
        value = json.loads(path.read_text())
        value["metadata"]["lastAction"] = "TeleportFull"
        write_json(path, value)
    elif attack == "house":
        house.write_text(house.read_text() + " ")
    else:
        path = directory / "public/000-state.json"
        command, delivery = StateCodec().loads(path.read_text())
        raw = delivery.observations[0]
        e = json.loads(raw.envelope_json)
        e["metadata"]["asset_id"] = "private-label"
        object.__setattr__(raw, "envelope_json", json.dumps(e))
        path.write_text(StateCodec().dumps((command, delivery)))
    write_json(event_path, event)
    write_json(info_path, info)
    with pytest.raises(ValueError):
        verify_capture(directory, house, provenance)


def test_initial_physics_change_is_recorded_and_quarantines_affected_instance(tmp_path):
    directory = tmp_path / "initial-motion"
    house, provenance = build_capture(directory, initial_motion=True)
    result = verify_capture(directory, house, provenance)
    assert result["initial_to_pause_changed_objects"] == ["a"]
    assert result["instances"][0]["position_changed_during_initialization"] is True
    assert result["instances"][0]["eligible_pending_partition_audit"] is False


@pytest.mark.parametrize("attack", ["asset", "position"])
def test_complete_sdk_relabeling_cannot_create_source_eligible_target(archive, attack):
    directory, house, provenance = archive
    private = directory / "unity-logs/evaluator_only"
    for i in range(12):
        path = private / f"sdk-events/{i:03d}.json"
        record = json.loads(path.read_text())
        if attack == "asset":
            record["metadata"]["objects"][1]["assetId"] = "same-asset-renamed"
        else:
            record["metadata"]["objects"][1]["position"]["x"] = 1.0
        write_json(path, record)
        if attack == "asset":
            path = private / f"instances/{i:03d}.json"
            record = json.loads(path.read_text())
            record["catalog"][1]["asset_id"] = "same-asset-renamed"
            write_json(path, record)
    result = verify_capture(directory, house, provenance)
    changed = result["instances"][1]
    assert changed["eligible_pending_partition_audit"] is False
    assert (
        "source_sdk_asset_mismatch" if attack == "asset" else "source_sdk_initial_position_mismatch"
    ) in changed["exclusion_reasons"]


def test_repeated_noncausal_whole_public_frame_rejected(archive):
    directory, house, provenance = archive
    source = directory / "public/001-state.json"
    (directory / "public/002-state.json").write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="action trace"):
        verify_capture(directory, house, provenance)


def test_agent_translation_with_unchanged_camera_is_rejected(archive):
    directory, house, pins = archive
    path = directory / "unity-logs/evaluator_only/sdk-events/005.json"
    record = json.loads(path.read_text())
    record["metadata"]["agent"]["position"]["x"] += 1.0
    write_json(path, record)
    with pytest.raises(ValueError, match="fixed rotation"):
        verify_capture(directory, house, pins)
