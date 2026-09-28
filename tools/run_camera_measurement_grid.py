"""Fixed 66-frame live grid: both existing detectors see identical delivered RGB.

This is descriptive single-house measurement diagnosis, not natural semantic
supervision, detector training, a fitted camera model or a held-out task benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import numpy as np
import torch
from run_neural_pixel_camera_loop import ROOT, diagnostic_house, source_identity
from verify_neural_camera_comparison import bbox_iou, plain, require

from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery
from cpswm.system.unity_observation import UnityObservationExecutor

XS = (1.05, 1.25, 1.45)
SITES = ("north", "south")
HEADINGS = tuple(range(195, 346, 15))
FRONTENDS = ("ssdlite", "fasterrcnn")
GRID = {
    "sites": SITES,
    "camera_x": XS,
    "headings": HEADINGS,
    "fov": 60,
    "shape": (320, 320, 3),
    "detector_filter": 0.5,
    "empirical_calibration": False,
    "scope": "SINGLE_HOUSE_FIXED_GRID_DESCRIPTIVE_MEASUREMENTS",
}
SOURCES = CameraModelSources(
    observation_model_id="fixed-grid-measurement-only@1",
    observation_artifact_sha256=content_sha256(GRID),
    calibration_domain="NOT_FITTED_OR_CALIBRATED",
    calibration_data_sha256=content_sha256("no-calibration-fit"),
    utility_definition_id="no-action-utility",
    utility_artifact_sha256=content_sha256("fixed-collection-not-adaptive"),
)


def configuration(image_size=320):
    if type(image_size) is not int or image_size not in (320, 640):
        raise ValueError("unsupported fixed-grid resolution")
    return {**GRID, "shape": (image_size, image_size, 3)}


def measurement_sources(image_size):
    return SOURCES.model_copy(
        update={"observation_artifact_sha256": content_sha256(configuration(image_size))}
    )


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def grid_house(original, site, x):
    if x not in XS:
        raise ValueError("undeclared camera position")
    house = diagnostic_house(original, site)
    pose = house["metadata"]["agent"]
    pose["position"]["x"] = x
    pose["rotation"]["y"] = HEADINGS[0]
    house["metadata"]["agentPoses"]["default"] = pose
    return house


def action_at(index):
    if type(index) is not int or not 0 <= index < len(HEADINGS):
        raise ValueError("grid action index outside fixed schedule")
    return ("Pass", 0.0) if index == 0 else ("RotateRight", 15.0)


def original_house():
    path = ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    return json.loads(path.read_text())


def capture_case(directory, *, sdk_python, binary, site, x, image_size=320):
    grid = configuration(image_size)
    directory.mkdir(parents=True, exist_ok=False)
    house = directory / "evaluator_house.json"
    write_json(house, grid_house(original_house(), site, x))
    scope = dict(household_id=uuid4(), session_id=uuid4(), trace_id=uuid4())
    source, files = source_identity()
    metadata = {
        "scope": GRID["scope"],
        "grid": plain(grid),
        "site": site,
        "camera_x": x,
        "source_sha256": source,
        "source_files": files,
        "runtime_scope": plain(scope),
        "sdk_python_sha256": hashlib.sha256(sdk_python.resolve().read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "house_sha256": hashlib.sha256(house.read_bytes()).hexdigest(),
        "status": "RUNNING",
    }
    write_json(directory / "capture.json", metadata)
    executor = None
    records, source_ids = [], ()
    started = monotonic()
    try:
        executor = UnityObservationExecutor(
            python=sdk_python,
            worker=ROOT / "tools/unity_camera_feedback_worker.py",
            binary=binary,
            house=house,
            log_dir=directory / "unity-logs",
            image_size=image_size,
            **scope,
        )
        for index in range(len(HEADINGS)):
            action, degrees = action_at(index)
            command = ObservationCommand(
                uuid4(),
                content_uuid("fixed-grid-session", scope),
                action,
                degrees,
                "fixed-view-grid@1:" + str(index),
                source_ids,
                datetime.now(UTC),
            )
            delivery = executor.execute(command)
            records.append((command, delivery))
            source_ids += tuple(o.envelope().identity.observation_id for o in delivery.observations)
            document = StateCodec().dumps(tuple(records))
            (directory / "capture-state.json").write_text(document)
            metadata.update(
                captured_frames=len(records),
                state_sha256=hashlib.sha256(document.encode()).hexdigest(),
            )
            write_json(directory / "capture.json", metadata)
        require(source_identity()[0] == source, "source changed during fixed collection")
        metadata.update(status="COMPLETE", seconds=monotonic() - started, source_unchanged=True)
        write_json(directory / "capture.json", metadata)
        return metadata
    except BaseException:
        metadata.update(
            status="FAILED", seconds=monotonic() - started, error=traceback.format_exc()
        )
        write_json(directory / "capture.json", metadata)
        raise
    finally:
        if executor is not None:
            executor.close()


def load_public_capture(directory, *, site, x, image_size=320):
    grid = configuration(image_size)
    manifest = json.loads((directory / "capture.json").read_text())
    require(
        manifest["status"] == "COMPLETE" and manifest["source_unchanged"] is True,
        "incomplete fixed capture",
    )
    require(
        manifest["grid"] == plain(grid) and (manifest["site"], manifest["camera_x"]) == (site, x),
        "capture differs from declared grid cell",
    )
    source, files = source_identity()
    require(
        manifest["source_sha256"] == source and manifest["source_files"] == files,
        "capture source differs from verifier",
    )
    document = (directory / "capture-state.json").read_text()
    require(
        hashlib.sha256(document.encode()).hexdigest() == manifest["state_sha256"],
        "capture-state digest differs",
    )
    records = StateCodec().loads(document)
    require(
        type(records) is tuple and len(records) == len(HEADINGS) == manifest["captured_frames"],
        "fixed grid frame count differs",
    )
    ids, commands, raw_ids, snapshot = (), set(), set(), None
    for index, (command, delivery) in enumerate(records):
        require(
            type(command) is ObservationCommand and type(delivery) is ObservationDelivery,
            "unexpected capture record type",
        )
        require(
            (command.action, command.degrees) == action_at(index)
            and command.source_ids == ids
            and command.reason == "fixed-view-grid@1:" + str(index),
            "command differs from fixed schedule",
        )
        require(
            command.action_id == delivery.action_id and command.action_id not in commands,
            "duplicated or mismatched delivered action",
        )
        require(
            delivery.success is True and len(delivery.observations) == 1,
            "failed action or wrong frame count",
        )
        snapshot = command.snapshot_id if snapshot is None else snapshot
        require(command.snapshot_id == snapshot, "capture session changed")
        raw = delivery.observations[0]
        env, pixels = decode_rgb(raw, cutoff=delivery.received_at)
        require(
            env.metadata.source_id == str(command.action_id)
            and command.decision_time
            <= env.capture_time
            <= env.arrival_time
            <= delivery.received_at,
            "capture does not follow its issued action",
        )
        require(tuple(pixels.shape) == grid["shape"], "capture resolution changed")
        require(env.identity.observation_id not in raw_ids, "duplicated raw observation")
        require(
            plain(
                dict(
                    household_id=env.identity.household_id,
                    session_id=env.identity.session_id,
                    trace_id=env.identity.trace_id,
                )
            )
            == manifest["runtime_scope"],
            "capture scope changed",
        )
        commands.add(command.action_id)
        raw_ids.add(env.identity.observation_id)
        ids += (env.identity.observation_id,)
    return manifest, records


def measure_public(records, *, weights):
    """No scene label, position, mask, SDK metadata or evaluator path is accepted."""
    observations = tuple(delivery.observations[0] for _, delivery in records)
    identity = observations[0].envelope().identity
    shapes = [
        tuple(decode_rgb(raw, cutoff=records[-1][1].received_at)[1].shape) for raw in observations
    ]
    grid = configuration(shapes[0][0])
    require(all(shape == grid["shape"] for shape in shapes), "mixed or invalid public image shapes")
    sources = measurement_sources(shapes[0][0])
    scope = dict(
        household_id=identity.household_id,
        session_id=identity.session_id,
        trace_id=identity.trace_id,
    )
    measurements, bindings = {}, {}
    for frontend in FRONTENDS:
        decoder = PixelCategoryOutcomeDecoder(
            weights_path=weights[frontend],
            category="apple",
            sources=sources,
            detector_kind=frontend,
            **scope,
        )
        bindings[frontend] = decoder.binding_sha256
        measurements[frontend] = plain(
            [
                asdict(f)
                for f in decoder.measurements(observations, cutoff=records[-1][1].received_at)
            ]
        )
    return {"decoder_bindings": bindings, "measurements": measurements}


def evaluate_case(directory, records, predictions, *, site, x, image_size=320):
    """Read privileged evaluation only after both models have produced predictions."""
    grid = configuration(image_size)
    expected_house = grid_house(original_house(), site, x)
    require(
        json.loads((directory / "evaluator_house.json").read_text()) == expected_house,
        "grid scene differs from fixed placement",
    )
    private = directory / "unity-logs/evaluator_only"
    truth = json.loads((private / "actions.json").read_text())
    require(len(truth) == len(HEADINGS), "evaluator frame count differs")
    initial = json.loads((private / "initial.json").read_text())
    target_id = expected_house["metadata"]["cpswm_diagnostic_target"]
    target = next(o for o in initial["objects"] if o["objectId"] == target_id)
    expected_target = next(
        o for o in expected_house["objects"][0]["children"] if o["id"] == target_id
    )
    require(
        all(
            math.isclose(
                target["axisAlignedBoundingBox"]["center"][k],
                expected_target["position"][k],
                abs_tol=1e-4,
            )
            for k in ("x", "y", "z")
        ),
        "actual target bounds center differs",
    )
    initial_agent, initial_camera = initial["agent"], initial["cameraPosition"]
    require(
        math.isclose(initial_agent["position"]["x"], x, abs_tol=1e-4)
        and math.isclose(
            initial_agent["position"]["z"],
            expected_house["metadata"]["agent"]["position"]["z"],
            abs_tol=1e-4,
        ),
        "actual horizontal camera setup differs",
    )
    require(set(predictions["measurements"]) == set(FRONTENDS), "missing detector arm")
    require(
        all(len(predictions["measurements"][f]) == len(HEADINGS) for f in FRONTENDS),
        "detector frame count differs",
    )
    rows = []
    for index, ((command, delivery), evaluator) in enumerate(zip(records, truth, strict=True)):
        require(
            evaluator["index"] == index
            and evaluator["request"]
            == {
                "action_id": str(command.action_id),
                "action": command.action,
                "degrees": command.degrees,
            }
            and evaluator["success"] is True,
            "evaluator action differs from delivered command",
        )
        require(
            math.isclose(evaluator["agent"]["rotation"]["y"], HEADINGS[index], abs_tol=1e-3),
            "actual heading differs from fixed schedule",
        )
        require(
            all(
                math.isclose(
                    evaluator["agent"]["position"][k], initial_agent["position"][k], abs_tol=1e-4
                )
                and math.isclose(evaluator["camera_position"][k], initial_camera[k], abs_tol=1e-4)
                for k in ("x", "y", "z")
            )
            and math.isclose(evaluator["agent"]["cameraHorizon"], 30, abs_tol=1e-3)
            and evaluator["fov"] == 60,
            "actual camera geometry drifted",
        )
        require(
            all(
                math.isclose(evaluator["target_position"][k], target["position"][k], abs_tol=1e-4)
                for k in ("x", "y", "z")
            ),
            "target moved during fixed sweep",
        )
        require(
            evaluator["image_size"] == [image_size, image_size],
            "actual evaluator image size differs",
        )
        raw = delivery.observations[0]
        require(
            (private / f"{index:03d}-rgb.npy").read_bytes() == raw.payload_bytes,
            "evaluator RGB differs from actual delivered bytes",
        )
        mask = np.load(private / f"{index:03d}-mask.npy", allow_pickle=False)
        require(mask.dtype == bool and mask.shape == grid["shape"][:2], "invalid target mask")
        positions = np.argwhere(mask)
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
        require(
            evaluator["target_pixels"] == int(mask.sum()) and evaluator["target_bbox"] == box,
            "evaluator visibility differs from actual mask",
        )
        row = {
            "index": index,
            "heading": HEADINGS[index],
            "site": site,
            "camera_x": x,
            "rgb_sha256": hashlib.sha256(raw.payload_bytes).hexdigest(),
            "target_pixels": int(mask.sum()),
            "target_sdk_visible": evaluator["target_sdk_visible"],
            "frontends": {},
        }
        for frontend in FRONTENDS:
            frame = predictions["measurements"][frontend][index]
            require(
                frame["input_sha256"] == row["rgb_sha256"]
                and frame["observation_id"] == str(raw.envelope().identity.observation_id)
                and frame["minimum_score"] == 0.5
                and frame["negative_observation_authorized"] is False
                and frame["identity_status"] == "UNRESOLVED",
                "prediction has different pixels or authority",
            )
            candidates = [c for c in frame["candidates"] if c["category"] == "apple"]
            row["frontends"][frontend] = {
                "scores": [c["detector_score"] for c in candidates],
                "bbox_ious": [bbox_iou(c["box_xyxy"], box) for c in candidates],
            }
        rows.append(row)
    return {
        "site": site,
        "camera_x": x,
        "frame_count": len(rows),
        "image_size": image_size,
        "actual_agent_position": initial_agent["position"],
        "actual_camera_position": initial_camera,
        "frames": rows,
    }


def analyze_case(directory, *, weights, site, x, verify=False, image_size=320):
    torch.set_num_threads(2)
    manifest, records = load_public_capture(directory, site=site, x=x, image_size=image_size)
    predictions = measure_public(records, weights=weights)
    if verify:
        require(
            predictions == json.loads((directory / "predictions.json").read_text()),
            "predictions differ from fresh actual inference",
        )
    else:
        write_json(directory / "predictions.json", predictions)
    evaluated = evaluate_case(
        directory, records, predictions, site=site, x=x, image_size=image_size
    )
    if verify:
        require(
            evaluated == json.loads((directory / "evaluation.json").read_text()),
            "evaluation differs from owned data",
        )
    else:
        write_json(directory / "evaluation.json", evaluated)
    require(source_identity()[0] == manifest["source_sha256"], "source changed during measurement")
    return evaluated


def summarize(cases, image_size=320):
    configuration(image_size)
    require(all(c["image_size"] == image_size for c in cases), "grid contains another resolution")
    require(
        [(c["site"], c["camera_x"]) for c in cases] == [(s, x) for s in SITES for x in XS],
        "grid omitted, duplicated or reordered a cell",
    )
    frames = [r for case in cases for r in case["frames"]]
    require(len(frames) == 66, "grid is not complete")
    groups = {}
    for frontend in FRONTENDS:
        for site in SITES:
            for x in XS:
                rows = [r for r in frames if (r["site"], r["camera_x"]) == (site, x)]
                visible = [r for r in rows if r["target_pixels"] > 0]
                absent = [r for r in rows if r["target_pixels"] == 0]
                groups[f"{frontend}:{site}:{x}"] = {
                    "frames": len(rows),
                    "visible_frames": len(visible),
                    "visible_with_candidate": sum(
                        bool(r["frontends"][frontend]["scores"]) for r in visible
                    ),
                    "visible_with_overlapping_candidate": sum(
                        any(i > 0 for i in r["frontends"][frontend]["bbox_ious"]) for r in visible
                    ),
                    "no_target_pixels_frames": len(absent),
                    "candidate_without_target_pixels": sum(
                        bool(r["frontends"][frontend]["scores"]) for r in absent
                    ),
                }
    return {
        "scope": GRID["scope"],
        "complete_frames": 66,
        "image_size": image_size,
        "house_count": 1,
        "asset_count": 1,
        "scene_initializations": 6,
        "independent_scenes": False,
        "empirical_model_fitted": False,
        "natural_semantic_labels": 0,
        "same_raw_bytes_for_both_frontends": True,
        "groups": groups,
        "cases": cases,
    }


def main(args):
    configuration(args.image_size)
    weights = {"ssdlite": args.ssdlite_weights, "fasterrcnn": args.fasterrcnn_weights}
    if args.mode == "fixture":
        capture_case(
            args.output,
            sdk_python=args.sdk_python,
            binary=args.binary,
            site="north",
            x=1.25,
            image_size=args.image_size,
        )
        analyze_case(args.output, weights=weights, site="north", x=1.25, image_size=args.image_size)
        return
    plan = [
        {
            "site": site,
            "camera_x": x,
            "directory": f"{site}-{x:.2f}",
            "status": "PENDING",
            "image_size": args.image_size,
        }
        for site in SITES
        for x in XS
    ]
    if args.mode == "run":
        args.output.mkdir(parents=True, exist_ok=False)
        write_json(args.output / "grid.json", plan)
    else:
        saved = json.loads((args.output / "grid.json").read_text())
        require(
            [(r["site"], r["camera_x"], r["directory"]) for r in saved]
            == [(r["site"], r["camera_x"], r["directory"]) for r in plan]
            and all(
                r["status"] == "COMPLETE" and r["image_size"] == args.image_size for r in saved
            ),
            "incomplete or redirected grid",
        )
    cases = []
    for cell in plan:
        site, x = cell["site"], cell["camera_x"]
        directory = args.output / cell["directory"]
        try:
            if args.mode == "run":
                cell["status"] = "RUNNING"
                write_json(args.output / "grid.json", plan)
                capture_case(
                    directory,
                    sdk_python=args.sdk_python,
                    binary=args.binary,
                    site=site,
                    x=x,
                    image_size=args.image_size,
                )
            result = analyze_case(
                directory,
                weights=weights,
                site=site,
                x=x,
                verify=args.mode == "verify",
                image_size=args.image_size,
            )
            cases.append(result)
            cell["status"] = "COMPLETE"
            print(
                json.dumps(
                    {
                        "site": site,
                        "camera_x": x,
                        "frames": result["frame_count"],
                        "mode": args.mode,
                    }
                ),
                flush=True,
            )
        except Exception:
            cell.update(status="FAILED", error=traceback.format_exc())
            if args.mode == "verify":
                raise
            print(json.dumps(cell), flush=True)
        finally:
            if args.mode == "run":
                write_json(args.output / "grid.json", plan)
    if any(r["status"] != "COMPLETE" for r in plan):
        raise SystemExit(1)
    summary = summarize(cases, args.image_size)
    if args.mode == "verify":
        require(
            summary == json.loads((args.output / "summary.json").read_text()),
            "grid summary differs from full recomputation",
        )
        write_json(
            args.output / "verification.json",
            {
                "verified_frames": 66,
                "image_size": args.image_size,
                "source_sha256": source_identity()[0],
                "summary_sha256": content_sha256(summary),
            },
        )
    else:
        write_json(args.output / "summary.json", summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image-size", type=int, choices=(320, 640), default=320)
    p.add_argument("--mode", choices=("fixture", "run", "verify"), required=True)
    for name in ("output", "sdk-python", "binary", "ssdlite-weights", "fasterrcnn-weights"):
        p.add_argument("--" + name, type=Path, required=True)
    main(p.parse_args())
