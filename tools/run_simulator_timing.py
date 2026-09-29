"""Fixed 24-cell timing intervention; no calibration or detector-driven selection."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import torch
from audit_simulation_evidence import inspect_frame, overlap, require, sha
from run_camera_measurement_grid import ROOT, measure_public, source_identity, write_json
from run_simulator_repeatability import geometry_delta, house_for, image_delta
from unity_timing_worker import DT, MODES, STEPS, schedule

from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_uuid
from cpswm.system.structure_two_continuous_input import ObservationCommand
from cpswm.system.unity_observation import UnityObservationExecutor

SCOPE = "LOCAL_TIMING_INTERVENTION_NOT_CALIBRATION_OR_METHOD_BENEFIT"


def plan():
    return [
        dict(name=f"{site}-{size}-{mode}-{repeat}", site=site, size=size, mode=mode, repeat=repeat)
        for site in ("north", "south")
        for size in (320, 640)
        for repeat in (0, 1)
        for mode in (MODES if repeat == 0 else tuple(reversed(MODES)))
    ]


def configured_house(cell):
    require(cell in plan(), "undeclared timing cell")
    house = house_for(dict(site=cell["site"], route="direct"))
    house["metadata"]["cpswm_timing_mode"] = cell["mode"]
    return house


def capture(directory, cell, *, sdk, binary):
    house = configured_house(cell)
    directory.mkdir(parents=True, exist_ok=False)
    house_path = directory / "evaluator_house.json"
    write_json(house_path, house)
    source, files = source_identity()
    scope = dict(household_id=uuid4(), session_id=uuid4(), trace_id=uuid4())
    executor = UnityObservationExecutor(
        python=sdk,
        worker=ROOT / "tools/unity_timing_worker.py",
        binary=binary,
        house=house_path,
        log_dir=directory / "unity-logs",
        image_size=cell["size"],
        **scope,
    )
    records, ids = [], ()
    try:
        for i in range(STEPS):
            command = ObservationCommand(
                uuid4(),
                content_uuid("timing-session", scope),
                "Pass",
                0.0,
                f"fixed-timing@1:{i}",
                ids,
                datetime.now(UTC),
            )
            delivery = executor.execute(command)
            require(delivery.success and len(delivery.observations) == 1, "timing capture failed")
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
                    frames=len(records),
                    state_sha256=sha(document.encode()),
                    status="COMPLETE" if len(records) == STEPS else "RUNNING",
                ),
            )
        require(source_identity() == (source, files), "timing source changed")
    finally:
        executor.close()


def check_metadata(metadata):
    for obj in metadata["objects"]:
        require(
            all(
                type(obj[k][axis]) in (int, float) and np.isfinite(obj[k][axis])
                for k in ("position", "rotation")
                for axis in ("x", "y", "z")
            ),
            "nonfinite SDK pose",
        )


def check_sdk_events(private, cell, records):
    count = 2 + 2 * STEPS
    require(
        json.loads((private / "timing.json").read_text())
        == dict(mode=cell["mode"], sdk_events=count, frames=STEPS),
        "timing coverage differs",
    )
    directory = private / "sdk-events"
    require(
        {p.name for p in directory.iterdir()}
        == {
            f"{i:03d}{suffix}"
            for i in range(count)
            for suffix in (".json", "-rgb.npy", "-mask.npy")
        },
        "SDK event coverage differs",
    )
    rows, rgbs, masks = [], [], []
    for i in range(count):
        row = json.loads((directory / f"{i:03d}.json").read_text())
        phase = "prepare" if i == 1 else "clock" if i % 2 == 0 else "observe"
        expected = None if i == 0 else schedule(cell["mode"], phase)
        owner = None if i < 2 else str(records[(i - 2) // 2][0].action_id)
        require(
            row["index"] == i and row["requested"] == expected and row["owner"] == owner,
            "SDK requested timing differs",
        )
        metadata = row["metadata"]
        check_metadata(metadata)
        if i:
            require(
                metadata["lastAction"] == expected["action"]
                and metadata["lastActionSuccess"] is True,
                "SDK executed timing differs",
            )
        rgb = np.load(directory / f"{i:03d}-rgb.npy", allow_pickle=False)
        mask = np.load(directory / f"{i:03d}-mask.npy", allow_pickle=False)
        require(
            rgb.dtype == np.uint8
            and rgb.shape == (cell["size"], cell["size"], 3)
            and mask.dtype == bool
            and mask.shape == rgb.shape[:2],
            "SDK image shape differs",
        )
        rows.append(row)
        rgbs.append(rgb)
        masks.append(mask)
    require(
        rows[0]["metadata"] == json.loads((private / "initial.json").read_text()),
        "initial SDK state differs",
    )
    return rows, rgbs, masks


def analyze(directory, cell, *, weights, verify=False):
    manifest = json.loads((directory / "capture.json").read_text())
    require(
        manifest["cell"] == cell
        and manifest["scope"] == SCOPE
        and manifest["frames"] == STEPS
        and manifest["status"] == "COMPLETE",
        "incomplete timing cell",
    )
    require(
        (manifest["source_sha256"], manifest["source_files"]) == source_identity(),
        "timing source differs",
    )
    document = (directory / "capture-state.json").read_bytes()
    require(sha(document) == manifest["state_sha256"], "owned timing state differs")
    records = StateCodec().loads(document.decode())
    require(len(records) == STEPS, "timing record count differs")
    predictions = measure_public(records, weights=weights)
    if verify:
        require(
            predictions == json.loads((directory / "predictions.json").read_text()),
            "fresh timing predictions differ",
        )
    else:
        write_json(directory / "predictions.json", predictions)
    private = directory / "unity-logs/evaluator_only"
    house = configured_house(cell)
    require(
        json.loads((directory / "evaluator_house.json").read_text()) == house,
        "timing house differs",
    )
    sdk, rgbs, masks = check_sdk_events(private, cell, records)
    initial = sdk[0]["metadata"]
    require(
        all(
            abs(initial["agent"]["position"][axis] - house["metadata"]["agent"]["position"][axis])
            < 1e-4
            for axis in ("x", "z")
        ),
        "initial timing pose differs",
    )
    truth = json.loads((private / "actions.json").read_text())
    require(len(truth) == STEPS, "timing private coverage differs")
    target_id = house["metadata"]["cpswm_diagnostic_target"]
    target_initial = next(o for o in initial["objects"] if o["objectId"] == target_id)
    frames, ids = [], ()
    for i, ((command, delivery), row) in enumerate(zip(records, truth, strict=True)):
        j = 3 + 2 * i
        metadata = sdk[j]["metadata"]
        require(
            command.action == "Pass"
            and command.degrees == 0
            and command.source_ids == ids
            and command.reason == f"fixed-timing@1:{i}"
            and row["index"] == i
            and row["sdk_index"] == j,
            "timing public schedule differs",
        )
        ids += tuple(o.envelope().identity.observation_id for o in delivery.observations)
        require(len(set(ids)) == len(ids), "duplicate timing observation")
        raw = (private / f"{i:03d}-rgb.npy").read_bytes()
        mask = np.load(private / f"{i:03d}-mask.npy", allow_pickle=False)
        require(
            raw == (private / f"sdk-events/{j:03d}-rgb.npy").read_bytes()
            and np.array_equal(mask, masks[j]),
            "SDK/public image differs",
        )
        box = inspect_frame(command, delivery, row, raw, mask, cell["size"], 225, initial)
        target = next(o for o in metadata["objects"] if o["objectId"] == target_id)
        require(
            row["agent"] == metadata["agent"]
            and row["camera_position"] == metadata["cameraPosition"]
            and row["target_position"] == target["position"]
            and row["target_sdk_visible"] == target["visible"],
            "SDK/public geometry differs",
        )
        require(
            target["position"] == target_initial["position"]
            and target["rotation"] == target_initial["rotation"],
            "timing target moved",
        )
        outputs = {}
        for kind in ("ssdlite", "fasterrcnn"):
            frame = predictions["measurements"][kind][i]
            require(
                frame["input_sha256"] == sha(raw)
                and frame["identity_status"] == "UNRESOLVED"
                and frame["negative_observation_authorized"] is False,
                "timing detector authority differs",
            )
            candidates = [c for c in frame["candidates"] if c["category"] == "apple"]
            outputs[kind] = dict(
                scores=[c["detector_score"] for c in candidates],
                target_bbox_ious=[overlap(c["box_xyxy"], box) for c in candidates],
            )
        frames.append(
            dict(
                index=i,
                sdk_index=j,
                target_pixels=int(mask.sum()),
                frontends=outputs,
                geometry_since_pause=geometry_delta(sdk[1]["metadata"], metadata),
                scene_at_rest=metadata["isSceneAtRest"],
            )
        )
    public_rgbs = rgbs[3::2]
    public_masks = masks[3::2]
    result = dict(
        cell=cell,
        frames=frames,
        requested_physics_seconds=STEPS * DT if cell["mode"] == "stepped" else None,
        explicit_physics_calls=STEPS if cell["mode"] == "stepped" else 0,
        sdk_first_last=image_delta(rgbs[1], rgbs[-1], masks[1] | masks[-1]),
        public_first_last=image_delta(
            public_rgbs[0], public_rgbs[-1], public_masks[0] | public_masks[-1]
        ),
        sdk_adjacent_deltas=[
            image_delta(a, b, ma | mb)
            for a, b, ma, mb in zip(rgbs[:-1], rgbs[1:], masks[:-1], masks[1:], strict=True)
        ],
        tail_rgb_equal=all(np.array_equal(public_rgbs[8], a) for a in public_rgbs[8:]),
        tail_mask_equal=all(np.array_equal(public_masks[8], a) for a in public_masks[8:]),
        tail_max_translation=max(
            f["geometry_since_pause"]["max_object_translation"] for f in frames[8:]
        ),
        tail_geometry=[geometry_delta(sdk[19]["metadata"], s["metadata"]) for s in sdk[19::2]],
        calibration_fitted=False,
    )
    if verify:
        require(
            result == json.loads((directory / "analysis.json").read_text()),
            "timing analysis differs",
        )
    else:
        write_json(directory / "analysis.json", result)
    return result


def summarize(rows):
    require(
        [r["cell"] for r in rows] == plan() and all(len(r["frames"]) == STEPS for r in rows),
        "incomplete timing matrix",
    )
    return dict(
        scope=SCOPE,
        cells=len(rows),
        frames=STEPS * len(rows),
        independent_scenes=False,
        calibration_fitted=False,
        results=rows,
    )


def main(args):
    torch.set_num_threads(2)
    weights = dict(ssdlite=args.ssdlite_weights, fasterrcnn=args.fasterrcnn_weights)
    fixture = args.mode == "fixture"
    cells = (
        [c for c in plan() if c["site"] == "south" and c["size"] == 320 and c["repeat"] == 0]
        if fixture
        else plan()
    )
    if args.mode != "verify":
        args.output.mkdir(parents=True, exist_ok=False)
    matrix = [dict(**c, status="PENDING") for c in cells]
    if args.mode == "verify":
        require(
            json.loads((args.output / "matrix.json").read_text())
            == [dict(**c, status="COMPLETE") for c in cells],
            "published timing matrix incomplete",
        )
    results = []
    for row in matrix:
        cell = {k: v for k, v in row.items() if k != "status"}
        try:
            if args.mode != "verify":
                row["status"] = "RUNNING"
                write_json(args.output / "matrix.json", matrix)
                capture(args.output / cell["name"], cell, sdk=args.sdk_python, binary=args.binary)
            results.append(
                analyze(
                    args.output / cell["name"], cell, weights=weights, verify=args.mode == "verify"
                )
            )
            row["status"] = "COMPLETE"
        except Exception as error:
            row.update(status="FAILED", error=repr(error))
            if args.mode == "verify":
                raise
        finally:
            if args.mode != "verify":
                write_json(args.output / "matrix.json", matrix)
        print(json.dumps(row), flush=True)
    if fixture:
        require(len(results) == 3, "timing fixture incomplete")
        return
    summary = summarize(results)
    if args.mode == "verify":
        require(
            summary == json.loads((args.output / "summary.json").read_text()),
            "timing summary differs",
        )
    else:
        write_json(args.output / "summary.json", summary)
    write_json(
        args.output / ("verification.json" if args.mode == "verify" else "completion.json"),
        dict(cells=len(results), frames=summary["frames"], source_sha256=source_identity()[0]),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("fixture", "run", "verify"), required=True)
    for name in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
