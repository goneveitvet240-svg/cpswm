"""Recompute public RGB-D candidates, then diagnose them against private labels.

Evaluation only: no fitted noise, identity assignment, likelihood or online write.
The externally supplied input pin binds an archive, not independent label custody.
This diagnostic does not replay the historical semantic/ledger/action machinery.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import numpy as np
from run_history_action_loop import decoder_for, load
from run_instance_correspondence_diagnostic import reconstruct_catalog

from cpswm.perception_mapping.unity_rgbd import PROFILE, surface_support
from cpswm.system.joint_camera_feedback import decoder_binding
from cpswm.system.owned_visual_support import _frame_support
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery

SCOPE = "PRIVATE_RENDERED_MEMBERSHIP_AND_RAW_POSITION_DISPLACEMENTS_EVALUATION_ONLY"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plain(value):
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def inventory(directory):
    """Pin every original file, including public state and private evaluation sources."""
    files = sorted(directory.rglob("*"))
    require(not any(p.is_symlink() for p in files), "archive contains symbolic links")
    return {
        p.relative_to(directory).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in files
        if p.is_file()
    }


def public_predictions(history, decoder, expected):
    """No evaluator input: real detector calls and public sensor unprojection only."""
    require(
        history and len({c.action_id for c, _ in history}) == len(history),
        "empty/duplicate history",
    )
    require(
        [a.command for a in expected.actions] == [c for c, _ in history]
        and expected.decoder_binding_sha256 == decoder_binding(decoder)
        and expected.scored_joint_density is None
        and not expected.memory_write_authorized
        and not expected.negative_observation_authorized,
        "public support coverage or authority differs",
    )
    result = []
    scope = None
    observation_ids = set()
    for (command, delivery), old in zip(history, expected.actions, strict=True):
        require(type(command) is ObservationCommand, "invalid public command")
        if type(delivery) is not ObservationDelivery:
            require(
                delivery in {"READY", "OUTCOME_UNCERTAIN", "CANCELLED_STALE_JOINT"}
                and delivery == old.status
                and not old.frames,
                "pending action differs",
            )
            continue
        require(
            delivery.success
            and command.action_id == delivery.action_id
            and old.status == "DELIVERED"
            and command.decision_time <= delivery.received_at,
            "failed or mismatched public delivery",
        )
        frames = decoder.measurements(delivery.observations, cutoff=delivery.received_at)
        require(len(frames) == 1 and len(old.frames) == 1, "expected one complete RGB-D frame")
        frame = _frame_support(delivery.observations[0], frames[0], delivery.received_at)
        frame = replace(
            frame,
            geometry=surface_support(delivery.observations, frames[0], cutoff=delivery.received_at),
        )
        require(
            frame.geometry.camera.action_id == command.action_id
            and command.decision_time <= frame.frame.capture_time
            and frame == old.frames[0],
            "fresh public candidates/geometry differ",
        )
        current_scope = (frame.frame.household_id, frame.frame.session_id, frame.frame.trace_id)
        current_ids = set(frame.geometry.observation_ids)
        require(
            (scope is None or scope == current_scope)
            and not observation_ids.intersection(current_ids),
            "public history scope or observation reuse differs",
        )
        scope = current_scope
        observation_ids.update(current_ids)
        result.append((command, delivery, frame))
    require(bool(result), "no delivered public RGB-D frames")
    return tuple(result)


def xyz(value):
    require(type(value) is dict and set(value) == {"x", "y", "z"}, "invalid SDK position")
    result = tuple(value[k] for k in ("x", "y", "z"))
    require(
        all(type(v) in (int, float) and math.isfinite(v) for v in result),
        "nonfinite SDK position",
    )
    return result


def displacement(point, reference):
    delta = [a - b for a, b in zip(point, reference, strict=True)]
    return dict(delta_xyz_m=delta, distance_m=math.sqrt(sum(v * v for v in delta)))


def evaluate_frame(command, delivery, public, sdk, info, masks, segmentation, target):
    """All candidate/instance pairs, including zero overlap and invisible objects."""
    geometry = public.geometry
    camera = geometry.camera
    metadata = sdk["metadata"]
    requested = dict(action=command.action)
    if command.action != "Pass":
        requested["degrees"] = command.degrees
    require(
        info["action_id"] == sdk["owner"] == str(command.action_id)
        and sdk["requested"] == requested
        and metadata["lastAction"] == command.action
        and metadata["lastActionSuccess"] is True,
        "SDK action owner or result differs",
    )
    require(
        camera.position_m == xyz(metadata["cameraPosition"])
        and camera.yaw_degrees == metadata["agent"]["rotation"]["y"]
        and camera.pitch_degrees == metadata["agent"]["cameraHorizon"]
        and camera.vertical_fov_degrees == metadata["fov"]
        and segmentation.shape == (camera.height, camera.width, 3)
        and info["colors"] == metadata["colors"],
        "SDK camera or segmentation source differs",
    )
    instances = reconstruct_catalog(
        info["catalog"], info["colors"], masks, segmentation, metadata["objects"]
    )
    objects = {r["objectId"]: r for r in metadata["objects"]}
    require(target in objects, "missing diagnostic target")
    # Explicitly distinguish the transform origin from the AABB centre.
    for row in instances:
        obj = objects[row["object_id"]]
        row["sdk_transform_position_m"] = xyz(obj["position"])
        row["sdk_aabb_center_m"] = xyz(obj["axisAlignedBoundingBox"]["center"])
    yy, xx = np.indices(segmentation.shape[:2])
    candidates = []
    for candidate, detection in zip(geometry.candidates, public.frame.candidates, strict=True):
        require(
            candidate.detection_candidate_id == detection.candidate_id, "candidate order differs"
        )
        x0, y0, x1, y1 = candidate.box_xyxy
        inside = (xx + 0.5 >= x0) & (xx + 0.5 < x1) & (yy + 0.5 >= y0) & (yy + 0.5 < y1)
        require(int(inside.sum()) == candidate.box_pixel_count, "box pixel convention differs")
        points = []
        for sample in candidate.samples:
            u, v = sample.pixel_uv
            members = [r["object_id"] for r in instances if masks[r["array_key"]][v, u]]
            points.append(dict(**asdict(sample), rendered_instance_ids=members))
        candidates.append(
            dict(
                candidate_id=str(candidate.detection_candidate_id),
                category=candidate.category,
                detector_score_uncalibrated=detection.detector_score,
                box_xyxy=candidate.box_xyxy,
                box_pixel_count=candidate.box_pixel_count,
                valid_depth_pixel_count=candidate.valid_depth_pixel_count,
                samples=points,
                overlaps=[
                    dict(
                        object_id=r["object_id"],
                        intersection_pixels=int((masks[r["array_key"]] & inside).sum()),
                        instance_pixels=r["pixels"],
                        sample_displacements=[
                            dict(
                                depth_rank_fraction=s.depth_rank_fraction,
                                pixel_on_rendered_instance=bool(
                                    masks[r["array_key"]][s.pixel_uv[1], s.pixel_uv[0]]
                                ),
                                to_sdk_transform=displacement(
                                    s.nominal_world_xyz_m, r["sdk_transform_position_m"]
                                ),
                                to_sdk_aabb_center=displacement(
                                    s.nominal_world_xyz_m, r["sdk_aabb_center_m"]
                                ),
                            )
                            for s in candidate.samples
                        ],
                    )
                    for r in instances
                ],
            )
        )
    return plain(
        dict(
            action_id=str(command.action_id),
            sdk_index=sdk["index"],
            rgb_sha256=camera.rgb_sha256,
            depth_sha256=camera.depth_sha256,
            identical_rgb_group=camera.rgb_sha256,
            geometry_input_group=content_sha256(
                (
                    camera.rgb_sha256,
                    camera.depth_sha256,
                    camera.position_m,
                    camera.yaw_degrees,
                    camera.pitch_degrees,
                    camera.width,
                    camera.height,
                    camera.vertical_fov_degrees,
                    camera.near_plane_m,
                    camera.far_plane_m,
                )
            ),
            target_id=target,
            target_pixels=next(r["pixels"] for r in instances if r["object_id"] == target),
            instances=instances,
            candidates=candidates,
        )
    )


def diagnose(directory, *, decoder, input_sha256):
    before = inventory(directory)
    require(content_sha256(before) == input_sha256, "archive differs from external input pin")
    manifest = json.loads((directory / "manifest.json").read_text())
    require(
        manifest["status"] == "COMPLETE"
        and manifest["sensor_profile"] == PROFILE
        and manifest["private_instance_evaluation"] is True
        and decoder.binding_sha256 == manifest["decoder_binding"],
        "archive profile or detector differs",
    )
    history = load(directory / "owned-history.json")
    public = public_predictions(history, decoder, load(directory / "visual-support.json"))
    public_document = plain([dict(command=asdict(c), frame=asdict(f)) for c, _, f in public])
    # Inventory hashes private bytes, but labels are first decoded after inference.
    private = directory / "unity-logs/evaluator_only"
    sdk = [json.loads(p.read_text()) for p in sorted((private / "sdk-events").glob("*.json"))]
    require(
        len(sdk) == 4 + len(public)
        and [r["index"] for r in sdk] == list(range(len(sdk)))
        and len(list((private / "instances").glob("*.json"))) == len(sdk),
        "SDK/instance frame coverage differs",
    )
    target = json.loads((directory / "evaluator_house.json").read_text())["metadata"][
        "cpswm_diagnostic_target"
    ]
    rows = []
    for (command, delivery, frame), row in zip(public, sdk[4:], strict=True):
        i = row["index"]
        for index, name in ((0, "rgb"), (1, "depth")):
            require(
                (private / f"sdk-events/{i:03d}-{name}.npy").read_bytes()
                == delivery.observations[index].payload_bytes,
                "SDK/public RGB-D pixels differ",
            )
        info = json.loads((private / f"instances/{i:03d}.json").read_text())
        segmentation = np.load(private / f"instances/{i:03d}-segmentation.npy", allow_pickle=False)
        with np.load(private / f"instances/{i:03d}-masks.npz", allow_pickle=False) as masks:
            result = evaluate_frame(
                command, delivery, frame, row, info, masks, segmentation, target
            )
            target_key = next(r["array_key"] for r in info["catalog"] if r["object_id"] == target)
            target_mask = np.load(private / f"sdk-events/{i:03d}-mask.npy", allow_pickle=False)
            require(
                target_mask.dtype == bool and np.array_equal(target_mask, masks[target_key]),
                "target mask differs",
            )
            rows.append(result)
    require(inventory(directory) == before, "input changed during diagnosis")
    return (
        public_document,
        dict(
            scope=SCOPE,
            input_sha256=input_sha256,
            tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            historical_source_sha256=manifest["source"],
            public_predictions_sha256=content_sha256(public_document),
            frames=rows,
            automatic_identity_assignment=False,
            empirical_calibration=False,
            online_memory_write=False,
            historical_full_replay=False,
            independent_label_custody=False,
            interpretation=(
                "Rendered pixel membership is not depth-surface identity; "
                "displacements to SDK references are not calibrated localization error."
            ),
            summary=dict(
                frames=len(rows),
                unique_rgb=len({r["identical_rgb_group"] for r in rows}),
                unique_geometry_inputs=len({r["geometry_input_group"] for r in rows}),
                candidates=sum(len(r["candidates"]) for r in rows),
                samples=sum(len(c["samples"]) for r in rows for c in r["candidates"]),
                target_visible_frames=sum(r["target_pixels"] > 0 for r in rows),
            ),
        ),
        before,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "output", "weights"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require(
        not args.output.resolve().is_relative_to(args.history.resolve()),
        "output must be outside input archive",
    )
    require(args.verify or not args.output.exists(), "refuse to overwrite prior diagnosis")
    manifest = json.loads((args.history / "manifest.json").read_text())
    import torch

    torch.set_num_threads(2)
    decoder, _ = decoder_for(args.weights, manifest["task"], manifest["detector_kind"])
    public, report, inputs = diagnose(args.history, decoder=decoder, input_sha256=args.input_sha256)
    documents = dict(public=public, report=report, inputs=inputs)
    if args.verify:
        for name, value in documents.items():
            require(
                json.loads((args.output / (name + ".json")).read_text()) == value,
                "fresh " + name + " differs",
            )
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in documents.items():
            (args.output / (name + ".json")).write_text(
                json.dumps(value, indent=2, allow_nan=False) + "\n"
            )
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
