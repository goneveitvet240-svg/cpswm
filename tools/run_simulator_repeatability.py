"""Predeclared 16-cell, 128-frame camera repetition diagnosis; no policy fitting."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import torch
from audit_simulation_evidence import inspect_frame, overlap, require, sha
from run_camera_measurement_grid import (
    ROOT,
    measure_public,
    original_house,
    source_identity,
    write_json,
)
from run_neural_pixel_camera_loop import diagnostic_house

from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_uuid
from cpswm.system.structure_two_continuous_input import ObservationCommand
from cpswm.system.unity_observation import UnityObservationExecutor

STEPS = 8
SCOPE = "LOCAL_FIXED_REPETITION_DIAGNOSIS_NOT_CALIBRATION_OR_GENERALIZATION"


def plan():
    return [
        dict(
            name=f"{site}-{size}-{route}-{repeat}", site=site, size=size, route=route, repeat=repeat
        )
        for site in ("north", "south")
        for size in (320, 640)
        for repeat in (0, 1)
        for route in (("direct", "rotate") if repeat == 0 else ("rotate", "direct"))
    ]


def action_at(route, index):
    require(
        route in ("direct", "rotate") and type(index) is int and 0 <= index < STEPS,
        "undeclared repetition step",
    )
    return ("RotateLeft", 45.0) if route == "rotate" and index == 0 else ("Pass", 0.0)


def house_for(cell):
    house = diagnostic_house(original_house(), cell["site"])
    house["metadata"]["agent"]["rotation"]["y"] = 225 if cell["route"] == "direct" else 270
    house["metadata"]["agentPoses"]["default"] = house["metadata"]["agent"]
    return house


def capture(directory, cell, *, sdk, binary):
    directory.mkdir(parents=True, exist_ok=False)
    house = directory / "evaluator_house.json"
    write_json(house, house_for(cell))
    source, files = source_identity()
    scope = dict(household_id=uuid4(), session_id=uuid4(), trace_id=uuid4())
    executor = UnityObservationExecutor(
        python=sdk,
        worker=ROOT / "tools/unity_repeatability_worker.py",
        binary=binary,
        house=house,
        log_dir=directory / "unity-logs",
        image_size=cell["size"],
        **scope,
    )
    records = []
    ids = ()
    try:
        for i in range(STEPS):
            action, degrees = action_at(cell["route"], i)
            command = ObservationCommand(
                uuid4(),
                content_uuid("repeatability-session", scope),
                action,
                degrees,
                f"fixed-repetition@1:{i}",
                ids,
                datetime.now(UTC),
            )
            delivery = executor.execute(command)
            require(
                delivery.success and len(delivery.observations) == 1,
                "actual repetition capture failed",
            )
            records.append((command, delivery))
            ids += tuple(r.envelope().identity.observation_id for r in delivery.observations)
            document = StateCodec().dumps(tuple(records))
            (directory / "capture-state.json").write_text(document)
            write_json(
                directory / "capture.json",
                dict(
                    scope=SCOPE,
                    cell=cell,
                    source_sha256=source,
                    source_files=files,
                    state_sha256=sha(document.encode()),
                    frames=len(records),
                    status="COMPLETE" if len(records) == STEPS else "RUNNING",
                ),
            )
        require(source_identity() == (source, files), "source changed during repeated capture")
    finally:
        executor.close()


def image_delta(first, last, mask):
    require(
        first.dtype == last.dtype == np.uint8 and first.shape == last.shape, "invalid repeated RGB"
    )
    require(mask.dtype == bool and mask.shape == first.shape[:2], "invalid repeated mask")
    delta = np.abs(first.astype(np.int16) - last.astype(np.int16))
    return dict(
        equal=bool(np.array_equal(first, last)),
        mean_abs_byte=float(delta.mean()),
        maximum_abs_byte=int(delta.max()),
        changed_pixel_fraction=float(np.any(delta, axis=2).mean()),
        target_region_mean_abs_byte=float(delta[mask].mean()) if mask.any() else None,
    )


def geometry_delta(initial, later):
    a = {o["objectId"]: o for o in initial["objects"]}
    b = {o["objectId"]: o for o in later["objects"]}
    require(
        len(a) == len(initial["objects"]) and len(b) == len(later["objects"]) and set(a) == set(b),
        "SDK object set changed",
    )
    translations = []
    rotations = []
    for key in a:
        require(
            (a[key]["objectType"], a[key].get("assetId"))
            == (b[key]["objectType"], b[key].get("assetId")),
            "SDK object identity changed",
        )
        translations.append(
            max(
                abs(a[key]["position"][axis] - b[key]["position"][axis]) for axis in ("x", "y", "z")
            )
        )
        rotations.append(
            max(
                abs((a[key]["rotation"][axis] - b[key]["rotation"][axis] + 180) % 360 - 180)
                for axis in ("x", "y", "z")
            )
        )
    return dict(
        max_object_translation=max(translations, default=0),
        max_object_rotation=max(rotations, default=0),
    )


def analyze(directory, cell, *, weights, verify=False):
    manifest = json.loads((directory / "capture.json").read_text())
    source, files = source_identity()
    require(
        manifest["cell"] == cell
        and manifest["status"] == "COMPLETE"
        and manifest["frames"] == STEPS,
        "incomplete repetition cell",
    )
    require(
        (manifest["source_sha256"], manifest["source_files"]) == (source, files),
        "repetition source differs",
    )
    document = (directory / "capture-state.json").read_bytes()
    require(sha(document) == manifest["state_sha256"], "owned repeated state differs")
    records = StateCodec().loads(document.decode())
    require(len(records) == STEPS, "repetition count differs")
    predictions = measure_public(records, weights=weights)
    if verify:
        require(
            predictions == json.loads((directory / "predictions.json").read_text()),
            "repeated predictions differ from fresh inference",
        )
    else:
        write_json(directory / "predictions.json", predictions)
    private = directory / "unity-logs/evaluator_only"
    initial = json.loads((private / "initial.json").read_text())
    truth = json.loads((private / "actions.json").read_text())
    require(
        json.loads((directory / "evaluator_house.json").read_text()) == house_for(cell),
        "repetition house differs",
    )
    require(len(truth) == STEPS, "private repeated frame coverage differs")
    expected_pose = house_for(cell)["metadata"]["agent"]["position"]
    require(
        all(abs(initial["agent"]["position"][k] - expected_pose[k]) < 1e-4 for k in ("x", "z")),
        "initial camera translation differs",
    )
    require(
        abs(initial["agent"]["rotation"]["y"] - (225 if cell["route"] == "direct" else 270)) < 1e-3,
        "initial camera route differs",
    )
    target_id = house_for(cell)["metadata"]["cpswm_diagnostic_target"]
    target = next(o for o in initial["objects"] if o["objectId"] == target_id)
    frames = []
    rgbs = []
    masks = []
    ids = ()
    for i, ((command, delivery), row) in enumerate(zip(records, truth, strict=True)):
        require(
            (command.action, command.degrees) == action_at(cell["route"], i)
            and command.source_ids == ids
            and row["index"] == i
            and command.reason == f"fixed-repetition@1:{i}",
            "repetition action schedule differs",
        )
        ids += tuple(r.envelope().identity.observation_id for r in delivery.observations)
        require(len(set(ids)) == len(ids), "duplicate repeated observation")
        raw = (private / f"{i:03d}-rgb.npy").read_bytes()
        mask = np.load(private / f"{i:03d}-mask.npy", allow_pickle=False)
        box = inspect_frame(command, delivery, row, raw, mask, cell["size"], 225, initial)
        require(
            all(
                abs(row["target_position"][k] - target["position"][k]) < 1e-4
                for k in ("x", "y", "z")
            ),
            "target translated",
        )
        full = json.loads((private / f"full_metadata/{i:03d}.json").read_text())
        require(full["action_id"] == str(command.action_id), "full metadata command differs")
        require(
            full["metadata"]["agent"] == row["agent"]
            and full["metadata"]["cameraPosition"] == row["camera_position"],
            "full metadata pose differs",
        )
        outputs = {}
        for kind in ("ssdlite", "fasterrcnn"):
            (frame,) = predictions["measurements"][kind][i : i + 1]
            require(
                frame["input_sha256"] == sha(raw)
                and frame["identity_status"] == "UNRESOLVED"
                and frame["negative_observation_authorized"] is False,
                "repeated prediction authority differs",
            )
            candidates = [c for c in frame["candidates"] if c["category"] == "apple"]
            outputs[kind] = dict(
                scores=[c["detector_score"] for c in candidates],
                target_bbox_ious=[overlap(c["box_xyxy"], box) for c in candidates],
            )
        frames.append(
            dict(
                index=i,
                rgb_sha256=sha(raw),
                target_pixels=int(mask.sum()),
                geometry=geometry_delta(initial, full["metadata"]),
                frontends=outputs,
            )
        )
        rgbs.append(np.load(private / f"{i:03d}-rgb.npy", allow_pickle=False))
        masks.append(mask)
    result = dict(
        cell=cell,
        frames=frames,
        unique_rgb=len({f["rgb_sha256"] for f in frames}),
        target_masks_equal=all(np.array_equal(masks[0], m) for m in masks),
        first_last=image_delta(rgbs[0], rgbs[-1], np.logical_or.reduce(masks)),
        successive_deltas=[
            image_delta(a, b, ma | mb)
            for a, b, ma, mb in zip(rgbs[:-1], rgbs[1:], masks[:-1], masks[1:], strict=True)
        ],
    )
    if verify:
        require(
            result == json.loads((directory / "analysis.json").read_text()),
            "repeated analysis differs",
        )
    else:
        write_json(directory / "analysis.json", result)
    return result


def summarize(rows):
    require([r["cell"] for r in rows] == plan(), "complete repeated matrix differs")
    return dict(
        scope=SCOPE,
        cells=len(rows),
        frames=sum(len(r["frames"]) for r in rows),
        independent_scenes=False,
        calibration_fitted=False,
        results=rows,
    )


def main(args):
    torch.set_num_threads(2)
    weights = dict(ssdlite=args.ssdlite_weights, fasterrcnn=args.fasterrcnn_weights)
    if args.mode == "fixture":
        cell = plan()[0]
        capture(args.output, cell, sdk=args.sdk_python, binary=args.binary)
        analyze(args.output, cell, weights=weights)
        return
    if args.mode == "run":
        args.output.mkdir(parents=True, exist_ok=False)
    cells = [dict(**c, status="PENDING") for c in plan()]
    results = []
    if args.mode == "verify":
        require(
            json.loads((args.output / "matrix.json").read_text())
            == [dict(**c, status="COMPLETE") for c in plan()],
            "incomplete published matrix",
        )
    for cell in cells:
        spec = {k: v for k, v in cell.items() if k != "status"}
        directory = args.output / cell["name"]
        try:
            if args.mode == "run":
                cell["status"] = "RUNNING"
                write_json(args.output / "matrix.json", cells)
                capture(directory, spec, sdk=args.sdk_python, binary=args.binary)
            results.append(analyze(directory, spec, weights=weights, verify=args.mode == "verify"))
            cell["status"] = "COMPLETE"
        except Exception as error:
            cell.update(status="FAILED", error=repr(error))
            if args.mode == "verify":
                raise
        finally:
            if args.mode == "run":
                write_json(args.output / "matrix.json", cells)
        print(json.dumps(cell), flush=True)
    result = summarize(results)
    if args.mode == "verify":
        require(
            result == json.loads((args.output / "summary.json").read_text()),
            "published repeated summary differs",
        )
    else:
        write_json(args.output / "summary.json", result)
    write_json(
        args.output / ("verification.json" if args.mode == "verify" else "completion.json"),
        dict(
            complete_cells=len(results), frames=result["frames"], source_sha256=source_identity()[0]
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("fixture", "run", "verify"), required=True)
    for name in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
