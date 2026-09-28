"""Selected simulation snapshots with full, unassigned candidate-instance overlaps.

Private simulator instance labels support evaluation only, not human supervision
or certified identity. Fixed model predictions precede all instance evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import torch
from run_camera_measurement_grid import (
    FRONTENDS,
    ROOT,
    grid_house,
    measure_public,
    original_house,
    source_identity,
    write_json,
)
from verify_neural_camera_comparison import bbox_iou, plain, require

from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_uuid
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery
from cpswm.system.unity_observation import UnityObservationExecutor

CASES = (("south_320", "south", 320), ("south_640", "south", 640), ("north_640", "north", 640))
SCOPE = "POST_HOC_SELECTED_SIMULATOR_INSTANCE_CORRESPONDENCE_NOT_NATURAL_IDENTITY"


def fixed_house(site):
    house = grid_house(original_house(), site, 1.25)
    house["metadata"]["agent"]["rotation"]["y"] = 225
    house["metadata"]["agentPoses"]["default"] = house["metadata"]["agent"]
    return house


def capture(directory, *, site, size, sdk_python, binary):
    require((site, size) in {(s, n) for _, s, n in CASES}, "undeclared snapshot")
    directory.mkdir(parents=True, exist_ok=False)
    house = directory / "evaluator_house.json"
    write_json(house, fixed_house(site))
    scope = dict(household_id=uuid4(), session_id=uuid4(), trace_id=uuid4())
    source, files = source_identity()
    executor = UnityObservationExecutor(
        python=sdk_python,
        worker=ROOT / "tools/unity_instance_audit_worker.py",
        binary=binary,
        house=house,
        log_dir=directory / "unity-logs",
        image_size=size,
        **scope,
    )
    try:
        command = ObservationCommand(
            uuid4(),
            content_uuid("instance-snapshot", scope),
            "Pass",
            0.0,
            "fixed-instance-correspondence@1",
            (),
            datetime.now(UTC),
        )
        delivery = executor.execute(command)
        require(delivery.success and len(delivery.observations) == 1, "actual capture failed")
        document = StateCodec().dumps((command, delivery))
        (directory / "capture-state.json").write_text(document)
        write_json(
            directory / "capture.json",
            dict(
                scope=SCOPE,
                site=site,
                image_size=size,
                source_sha256=source,
                source_files=files,
                state_sha256=hashlib.sha256(document.encode()).hexdigest(),
                runtime_scope=plain(scope),
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                sdk_python_sha256=hashlib.sha256(sdk_python.resolve().read_bytes()).hexdigest(),
            ),
        )
        require(source_identity() == (source, files), "source changed during instance capture")
    finally:
        executor.close()


def load_public(directory, site, size):
    require((site, size) in {(s, n) for _, s, n in CASES}, "undeclared snapshot")
    manifest = json.loads((directory / "capture.json").read_text())
    source, files = source_identity()
    require(
        manifest["scope"] == SCOPE and (manifest["site"], manifest["image_size"]) == (site, size),
        "instance capture scope differs",
    )
    require(
        (manifest["source_sha256"], manifest["source_files"]) == (source, files),
        "instance capture source differs",
    )
    document = (directory / "capture-state.json").read_text()
    require(
        hashlib.sha256(document.encode()).hexdigest() == manifest["state_sha256"],
        "state digest differs",
    )
    command, delivery = StateCodec().loads(document)
    require(
        type(command) is ObservationCommand
        and type(delivery) is ObservationDelivery
        and command.action == "Pass"
        and command.degrees == 0
        and command.reason == "fixed-instance-correspondence@1"
        and not command.source_ids
        and command.action_id == delivery.action_id
        and delivery.success
        and len(delivery.observations) == 1,
        "invalid owned instance capture",
    )
    env, pixels = decode_rgb(delivery.observations[0], cutoff=delivery.received_at)
    require(
        pixels.shape == (size, size, 3)
        and env.metadata.source_id == str(command.action_id)
        and command.decision_time <= env.capture_time <= env.arrival_time <= delivery.received_at,
        "public capture dimensions or ownership differ",
    )
    require(
        plain(
            dict(
                household_id=env.identity.household_id,
                session_id=env.identity.session_id,
                trace_id=env.identity.trace_id,
            )
        )
        == manifest["runtime_scope"],
        "scope differs",
    )
    return command, delivery


def reconstruct_catalog(catalog, colors, masks, segmentation, initial_objects):
    expected = {o["objectId"]: o for o in initial_objects}
    require(len(expected) == len(initial_objects), "duplicate SDK initialization object")
    require(
        len(catalog) == len(expected) and {r["object_id"] for r in catalog} == set(expected),
        "instance catalog omits or duplicates SDK objects",
    )
    require(
        len({r["array_key"] for r in catalog}) == len(catalog)
        and set(masks) == {r["array_key"] for r in catalog},
        "mask array coverage differs",
    )
    require(
        segmentation.dtype == np.uint8 and segmentation.ndim == 3 and segmentation.shape[2] == 3,
        "invalid segmentation image",
    )
    result = []
    for row in catalog:
        original = expected[row["object_id"]]
        require(
            (row["object_type"], row["asset_id"])
            == (original["objectType"], original.get("assetId")),
            "instance category or asset differs from SDK initialization",
        )
        reconstructed = np.zeros(segmentation.shape[:2], dtype=bool)
        for color in colors:
            if color["name"] == row["object_id"]:
                rgb = color["color"]
                require(
                    len(rgb) == 3 and all(type(v) is int and 0 <= v <= 255 for v in rgb),
                    "invalid SDK color",
                )
                reconstructed |= np.all(segmentation == np.array(rgb, dtype=np.uint8), axis=2)
        actual = masks[row["array_key"]]
        require(
            actual.dtype == bool
            and actual.shape == reconstructed.shape
            and np.array_equal(actual, reconstructed),
            "instance mask differs from segmentation colors",
        )
        positions = np.argwhere(actual)
        box = (
            None
            if not len(positions)
            else [
                int(positions[:, 1].min()),
                int(positions[:, 0].min()),
                int(positions[:, 1].max() + 1),
                int(positions[:, 0].max() + 1),
            ]
        )
        result.append(dict(**row, pixels=int(actual.sum()), bbox=box))
    return result


def evaluate(directory, command, delivery, predictions, site, size):
    require(
        json.loads((directory / "evaluator_house.json").read_text()) == fixed_house(site),
        "scene differs",
    )
    private = directory / "unity-logs/evaluator_only"
    initial = json.loads((private / "initial.json").read_text())
    actions = json.loads((private / "actions.json").read_text())
    require(
        len(actions) == 1
        and actions[0]["request"]
        == dict(action_id=str(command.action_id), action="Pass", degrees=0.0)
        and actions[0]["success"] is True,
        "private command differs",
    )
    action = actions[0]
    require(
        action["image_size"] == [size, size]
        and action["fov"] == 60
        and abs(action["agent"]["rotation"]["y"] - 225) < 1e-3
        and abs(action["agent"]["cameraHorizon"] - 30) < 1e-3
        and abs(action["agent"]["position"]["x"] - 1.25) < 1e-4,
        "camera geometry differs",
    )
    expected_pose = fixed_house(site)["metadata"]["agent"]["position"]
    require(
        abs(action["agent"]["position"]["z"] - expected_pose["z"]) < 1e-4
        and all(
            abs(action["agent"]["position"][k] - initial["agent"]["position"][k]) < 1e-4
            and abs(action["camera_position"][k] - initial["cameraPosition"][k]) < 1e-4
            for k in ("x", "y", "z")
        ),
        "actual snapshot camera translated",
    )
    raw = delivery.observations[0]
    require(
        (private / "000-rgb.npy").read_bytes() == raw.payload_bytes,
        "private pixels differ from delivery",
    )
    info = json.loads((private / "instances/000.json").read_text())
    require(info["action_id"] == str(command.action_id), "instance label action differs")
    require(
        sorted(info["colors"], key=lambda r: (r["name"], r["color"]))
        == sorted(initial["colors"], key=lambda r: (r["name"], r["color"])),
        "SDK color catalog changed",
    )
    segmentation = np.load(private / "instances/000-segmentation.npy", allow_pickle=False)
    require(segmentation.shape == (size, size, 3), "segmentation resolution differs")
    target_id = fixed_house(site)["metadata"]["cpswm_diagnostic_target"]
    with np.load(private / "instances/000-masks.npz", allow_pickle=False) as arrays:
        instances = reconstruct_catalog(
            info["catalog"], info["colors"], arrays, segmentation, initial["objects"]
        )
        target_key = next(r["array_key"] for r in info["catalog"] if r["object_id"] == target_id)
        instance_target_mask = np.array(arrays[target_key], copy=True)
    target = next(r for r in instances if r["object_id"] == target_id)
    target_mask = np.load(private / "000-mask.npy", allow_pickle=False)
    require(
        target_mask.dtype == bool
        and np.array_equal(target_mask, instance_target_mask)
        and int(target_mask.sum()) == action["target_pixels"] == target["pixels"],
        "target mask count differs",
    )
    require(set(predictions["measurements"]) == set(FRONTENDS), "missing detector")
    matrix = []
    for kind in FRONTENDS:
        (frame,) = predictions["measurements"][kind]
        require(
            frame["input_sha256"] == hashlib.sha256(raw.payload_bytes).hexdigest()
            and frame["observation_id"] == str(raw.envelope().identity.observation_id)
            and frame["minimum_score"] == 0.5
            and frame["identity_status"] == "UNRESOLVED"
            and frame["negative_observation_authorized"] is False,
            "prediction authority or pixels differ",
        )
        for candidate in frame["candidates"]:
            if candidate["category"] == "apple":
                matrix.append(
                    dict(
                        frontend=kind,
                        candidate=candidate,
                        overlaps=[
                            dict(
                                object_id=r["object_id"],
                                object_type=r["object_type"],
                                asset_id=r["asset_id"],
                                mask_pixels=r["pixels"],
                                bbox_iou=bbox_iou(candidate["box_xyxy"], r["bbox"]),
                            )
                            for r in instances
                        ],
                    )
                )
    return dict(
        scope=SCOPE,
        site=site,
        image_size=size,
        sdk_instances=len(instances),
        visible_instances=sum(r["pixels"] > 0 for r in instances),
        target_id=target_id,
        target_pixels=target["pixels"],
        instances=instances,
        candidate_instance_matrix=matrix,
        automatic_identity_assignment=False,
        natural_identity_labels=0,
    )


def analyze(directory, *, site, size, weights, verify=False):
    command, delivery = load_public(directory, site, size)
    predictions = measure_public(((command, delivery),), weights=weights)
    if verify:
        require(
            predictions == json.loads((directory / "predictions.json").read_text()),
            "fresh predictions differ",
        )
    else:
        write_json(directory / "predictions.json", predictions)
    result = evaluate(directory, command, delivery, predictions, site, size)
    if verify:
        require(
            result == json.loads((directory / "correspondence.json").read_text()),
            "correspondence differs from reconstruction",
        )
    else:
        write_json(directory / "correspondence.json", result)
    return result


def main(args):
    torch.set_num_threads(2)
    weights = dict(ssdlite=args.ssdlite_weights, fasterrcnn=args.fasterrcnn_weights)
    if args.mode == "fixture":
        capture(args.output, site="north", size=640, sdk_python=args.sdk_python, binary=args.binary)
        analyze(args.output, site="north", size=640, weights=weights)
        return
    if args.mode == "run":
        args.output.mkdir(parents=True, exist_ok=False)
    plan = [dict(name=n, site=s, image_size=z, status="PENDING") for n, s, z in CASES]
    if args.mode == "verify":
        require(
            json.loads((args.output / "matrix.json").read_text())
            == [dict(name=n, site=s, image_size=z, status="COMPLETE") for n, s, z in CASES],
            "incomplete snapshot plan",
        )
    results = []
    for cell in plan:
        directory = args.output / cell["name"]
        try:
            if args.mode == "run":
                cell["status"] = "RUNNING"
                write_json(args.output / "matrix.json", plan)
                capture(
                    directory,
                    site=cell["site"],
                    size=cell["image_size"],
                    sdk_python=args.sdk_python,
                    binary=args.binary,
                )
            results.append(
                analyze(
                    directory,
                    site=cell["site"],
                    size=cell["image_size"],
                    weights=weights,
                    verify=args.mode == "verify",
                )
            )
            cell["status"] = "COMPLETE"
        except Exception as error:
            cell.update(status="FAILED", error=repr(error))
            if args.mode == "verify":
                raise
        finally:
            if args.mode == "run":
                write_json(args.output / "matrix.json", plan)
        print(json.dumps(cell), flush=True)
    if len(results) != len(CASES):
        raise SystemExit(1)
    summary = dict(scope=SCOPE, complete_snapshots=3, independent_scenes=False, results=results)
    if args.mode == "verify":
        require(
            summary == json.loads((args.output / "summary.json").read_text()), "summary differs"
        )
        write_json(
            args.output / "verification.json",
            dict(verified_snapshots=3, source_sha256=source_identity()[0]),
        )
    else:
        write_json(args.output / "summary.json", summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("fixture", "run", "verify"), required=True)
    for key in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + key, type=Path, required=True)
    main(p.parse_args())
