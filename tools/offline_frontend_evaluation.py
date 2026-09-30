"""Complete offline candidate-instance diagnostics, without identity assignment.

The driver binds the archive and same-event SDK RGB-D bytes before calling this
module. Native detector and SDK vocabularies remain separate. Pixel membership
and raw surface-to-reference distances are descriptive, not detection accuracy,
calibrated localization error, independent samples or authority to write memory.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, replace

import numpy as np
from run_instance_correspondence_diagnostic import reconstruct_catalog

from cpswm.perception_mapping.unity_rgbd import surface_support
from cpswm.system.owned_visual_support import _frame_support
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _plain(value):
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def _xyz(value):
    _require(type(value) is dict and set(value) == {"x", "y", "z"}, "invalid SDK position")
    result = tuple(value[k] for k in ("x", "y", "z"))
    _require(
        all(type(v) in (int, float) and math.isfinite(v) for v in result), "nonfinite SDK position"
    )
    return result


def _displacement(point, reference):
    delta = [a - b for a, b in zip(point, reference, strict=True)]
    return dict(delta_xyz_m=delta, distance_m=math.sqrt(sum(v * v for v in delta)))


def _audit_rows(eligibility, objects):
    _require(type(eligibility) is list, "eligibility must contain this house's complete audit")
    rows = {row["object_id"]: row for row in eligibility}
    _require(
        len(rows) == len(eligibility) and set(rows) == set(objects),
        "eligibility omits or duplicates SDK instances",
    )
    groups = set()
    for identity, row in rows.items():
        obj = objects[identity]
        _require(
            type(row["eligible"]) is bool
            and type(row["exclusion_reasons"]) is list
            and all(type(reason) is str and reason for reason in row["exclusion_reasons"])
            and row["eligible"] == (not row["exclusion_reasons"]),
            "eligibility flag contradicts exclusion reasons",
        )
        _require(
            type(row["house_index"]) is int
            and 1 <= row["house_index"] <= 12
            and row["split"] == ("train" if row["house_index"] <= 8 else "validation"),
            "eligibility partition differs from fixed house index",
        )
        groups.add((row["house_index"], row["split"]))
        _require(
            row["object_type"] == obj["objectType"]
            and row["asset_id"] == obj.get("assetId")
            and tuple(row["position_m"]) == _xyz(obj["position"])
            and tuple(row["aabb_center_m"]) == _xyz(obj["axisAlignedBoundingBox"]["center"]),
            "eligibility differs from same SDK instance references",
        )
    _require(len(groups) <= 1, "eligibility mixes houses or partitions")
    return rows


def evaluate_frame(command, delivery, public, sdk, info, masks, segmentation, eligibility):
    """Return every candidate x SDK instance pair, including all zero overlaps."""
    _require(
        type(command) is ObservationCommand
        and type(delivery) is ObservationDelivery
        and delivery.success
        and command.action_id == delivery.action_id,
        "invalid or unsuccessful public command/delivery",
    )
    _require(public.geometry is not None, "public RGB-D geometry is required")
    geometry = surface_support(delivery.observations, public.frame, cutoff=delivery.received_at)
    _require(
        public
        == replace(
            _frame_support(delivery.observations[0], public.frame, delivery.received_at),
            geometry=geometry,
        ),
        "public support differs from rederived public sensor geometry",
    )
    camera = geometry.camera
    _require(
        command.action_id == camera.action_id
        and command.decision_time <= public.frame.capture_time <= delivery.received_at,
        "public capture ownership or chronology differs",
    )
    metadata = sdk["metadata"]
    requested = dict(action=command.action)
    if command.action != "Pass":
        requested["degrees"] = command.degrees
    _require(
        info["action_id"] == sdk["owner"] == str(command.action_id)
        and sdk["requested"] == requested
        and metadata["lastAction"] == command.action
        and metadata["lastActionSuccess"] is True,
        "SDK action owner or result differs",
    )
    _require(
        camera.position_m == _xyz(metadata["cameraPosition"])
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
    objects = {row["objectId"]: row for row in metadata["objects"]}
    audits = _audit_rows(eligibility, objects)
    for row in instances:
        obj, audit = objects[row["object_id"]], audits[row["object_id"]]
        row.update(
            sdk_transform_position_m=_xyz(obj["position"]),
            sdk_aabb_center_m=_xyz(obj["axisAlignedBoundingBox"]["center"]),
            eligible=audit["eligible"],
            exclusion_reasons=audit["exclusion_reasons"],
            eligibility=audit,
        )
    yy, xx = np.indices(segmentation.shape[:2])
    candidates = []
    for candidate, detection in zip(geometry.candidates, public.frame.candidates, strict=True):
        _require(
            candidate.detection_candidate_id == detection.candidate_id, "candidate order differs"
        )
        x0, y0, x1, y1 = candidate.box_xyxy
        inside = (xx + 0.5 >= x0) & (xx + 0.5 < x1) & (yy + 0.5 >= y0) & (yy + 0.5 < y1)
        _require(int(inside.sum()) == candidate.box_pixel_count, "box pixel convention differs")
        samples = []
        for sample in candidate.samples:
            u, v = sample.pixel_uv
            members = [row["object_id"] for row in instances if masks[row["array_key"]][v, u]]
            samples.append(dict(**asdict(sample), rendered_instance_ids=members))
        candidates.append(
            dict(
                candidate_id=str(candidate.detection_candidate_id),
                category=candidate.category,
                detector_score_uncalibrated=detection.detector_score,
                box_xyxy=candidate.box_xyxy,
                box_pixel_count=candidate.box_pixel_count,
                valid_depth_pixel_count=candidate.valid_depth_pixel_count,
                samples=samples,
                overlaps=[
                    dict(
                        object_id=row["object_id"],
                        intersection_pixels=int((masks[row["array_key"]] & inside).sum()),
                        instance_pixels=row["pixels"],
                        sample_displacements=[
                            dict(
                                depth_rank_fraction=sample.depth_rank_fraction,
                                pixel_uv=sample.pixel_uv,
                                pixel_on_rendered_instance=bool(
                                    masks[row["array_key"]][sample.pixel_uv[1], sample.pixel_uv[0]]
                                ),
                                to_sdk_transform=_displacement(
                                    sample.nominal_world_xyz_m, row["sdk_transform_position_m"]
                                ),
                                to_sdk_aabb_center=_displacement(
                                    sample.nominal_world_xyz_m, row["sdk_aabb_center_m"]
                                ),
                            )
                            for sample in candidate.samples
                        ],
                    )
                    for row in instances
                ],
            )
        )
    return _plain(
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
            native_detector_vocabulary="detector category strings; no SDK mapping applied",
            native_instance_vocabulary="SDK objectType strings; no detector mapping applied",
            instances=instances,
            candidates=candidates,
        )
    )


def _distribution(values):
    return dict(
        count=len(values),
        values_m=values,
        minimum_m=min(values) if values else None,
        median_m=float(np.quantile(values, 0.5)) if values else None,
        p90_m=float(np.quantile(values, 0.9)) if values else None,
        maximum_m=max(values) if values else None,
        quantile_method="linear interpolation at (n-1)*q",
    )


def _population(frames, *, eligible_only):
    counts = Counter(
        dict(
            frames=len(frames),
            frames_without_candidates=0,
            candidates=0,
            surface_samples=0,
            instance_frames=0,
            visible_instance_frames=0,
            invisible_instance_frames=0,
            candidate_instance_pairs=0,
            positive_overlap_pairs=0,
            zero_overlap_pairs=0,
            candidate_boxes_with_any_selected_instance=0,
            candidate_boxes_with_no_selected_instance=0,
            candidate_boxes_with_multiple_selected_instances=0,
            multiply_box_overlapped_instance_frames=0,
            box_overlapping_instance_frames=0,
            sample_hit_instance_frames=0,
            surface_samples_hitting_selected_instances=0,
            surface_samples_hitting_no_selected_instance=0,
            surface_samples_hitting_multiple_selected_instances=0,
            member_sample_instance_pairs=0,
        )
    )
    unions = {
        key: set()
        for key in (
            "instances",
            "visible_instances",
            "box_overlapping_instances",
            "sample_hit_instances",
            "multiply_box_overlapped_instances",
        )
    }
    pivot, aabb = [], []
    detector_categories, sdk_types = Counter(), Counter()
    for frame in frames:
        selected = {
            row["object_id"]: row
            for row in frame["instances"]
            if not eligible_only or row["eligible"]
        }

        def key(identity, house=frame["house_index"]):
            return house, identity

        counts["instance_frames"] += len(selected)
        counts["visible_instance_frames"] += sum(row["pixels"] > 0 for row in selected.values())
        counts["invisible_instance_frames"] += sum(row["pixels"] == 0 for row in selected.values())
        unions["instances"].update(key(identity) for identity in selected)
        unions["visible_instances"].update(
            key(identity) for identity, row in selected.items() if row["pixels"] > 0
        )
        sdk_types.update(row["object_type"] for row in selected.values())
        candidates = frame["candidates"]
        counts["frames_without_candidates"] += not candidates
        counts["candidates"] += len(candidates)
        overlap_per_object = Counter()
        member_objects = set()
        for candidate in candidates:
            detector_categories[candidate["category"]] += 1
            samples = candidate["samples"]
            counts["surface_samples"] += len(samples)
            pairs = [row for row in candidate["overlaps"] if row["object_id"] in selected]
            counts["candidate_instance_pairs"] += len(pairs)
            positive = [row for row in pairs if row["intersection_pixels"] > 0]
            counts["positive_overlap_pairs"] += len(positive)
            counts["zero_overlap_pairs"] += len(pairs) - len(positive)
            counts["candidate_boxes_with_any_selected_instance"] += bool(positive)
            counts["candidate_boxes_with_no_selected_instance"] += not positive
            counts["candidate_boxes_with_multiple_selected_instances"] += len(positive) > 1
            overlap_per_object.update(row["object_id"] for row in positive)
            for sample in samples:
                membership = set(sample["rendered_instance_ids"]) & set(selected)
                counts["surface_samples_hitting_selected_instances"] += bool(membership)
                counts["surface_samples_hitting_no_selected_instance"] += not membership
                counts["surface_samples_hitting_multiple_selected_instances"] += len(membership) > 1
            for pair in pairs:
                for displacement in pair["sample_displacements"]:
                    if displacement["pixel_on_rendered_instance"]:
                        member_objects.add(pair["object_id"])
                        counts["member_sample_instance_pairs"] += 1
                        pivot.append(displacement["to_sdk_transform"]["distance_m"])
                        aabb.append(displacement["to_sdk_aabb_center"]["distance_m"])
        counts["box_overlapping_instance_frames"] += len(overlap_per_object)
        counts["sample_hit_instance_frames"] += len(member_objects)
        repeated = {identity for identity, n in overlap_per_object.items() if n > 1}
        counts["multiply_box_overlapped_instance_frames"] += len(repeated)
        unions["box_overlapping_instances"].update(key(identity) for identity in overlap_per_object)
        unions["sample_hit_instances"].update(key(identity) for identity in member_objects)
        unions["multiply_box_overlapped_instances"].update(key(identity) for identity in repeated)
    return dict(
        **counts,
        **{f"unique_{name}": len(values) for name, values in unions.items()},
        **{
            f"{name}_keys": [dict(house_index=h, object_id=i) for h, i in sorted(values)]
            for name, values in unions.items()
        },
        native_detector_category_candidate_counts=dict(sorted(detector_categories.items())),
        native_sdk_object_type_instance_frame_counts=dict(sorted(sdk_types.items())),
        member_surface_to_sdk_pivot_raw_distance=_distribution(pivot),
        member_surface_to_sdk_aabb_center_raw_distance=_distribution(aabb),
    )


def _group(frames):
    return dict(
        frames=len(frames),
        houses=sorted({frame["house_index"] for frame in frames}),
        unique_rgb=len({frame["rgb_sha256"] for frame in frames}),
        unique_depth=len({frame["depth_sha256"] for frame in frames}),
        unique_geometry_inputs=len({frame["geometry_input_group"] for frame in frames}),
        all_instances=_population(frames, eligible_only=False),
        eligible_instances=_population(frames, eligible_only=True),
    )


def _validate_matrix(frame):
    instances = {row["object_id"]: row for row in frame["instances"]}
    _require(len(instances) == len(frame["instances"]), "duplicate summary instance")
    candidate_ids = [row["candidate_id"] for row in frame["candidates"]]
    _require(len(candidate_ids) == len(set(candidate_ids)), "duplicate summary candidate")
    for instance in instances.values():
        audit = instance["eligibility"]
        _require(
            type(instance["eligible"]) is bool
            and instance["eligible"] == audit["eligible"]
            and instance["exclusion_reasons"] == audit["exclusion_reasons"]
            and instance["eligible"] == (not instance["exclusion_reasons"])
            and instance["object_type"] == audit["object_type"]
            and instance["asset_id"] == audit["asset_id"]
            and instance["sdk_transform_position_m"] == audit["position_m"]
            and instance["sdk_aabb_center_m"] == audit["aabb_center_m"],
            "summary instance differs from retained eligibility audit",
        )
        _require(
            type(instance["pixels"]) is int and instance["pixels"] >= 0,
            "invalid summary instance pixels",
        )
    for candidate in frame["candidates"]:
        pairs = {row["object_id"]: row for row in candidate["overlaps"]}
        _require(
            len(pairs) == len(candidate["overlaps"]) and set(pairs) == set(instances),
            "summary matrix omits or duplicates candidate-instance pairs",
        )
        for sample in candidate["samples"]:
            ids = sample["rendered_instance_ids"]
            _require(
                len(ids) == len(set(ids)) and set(ids) <= set(instances),
                "summary sample membership refers to invalid instances",
            )
        for identity, pair in pairs.items():
            instance = instances[identity]
            _require(
                type(pair["intersection_pixels"]) is int
                and 0
                <= pair["intersection_pixels"]
                <= min(instance["pixels"], candidate["box_pixel_count"])
                and pair["instance_pixels"] == instance["pixels"]
                and len(pair["sample_displacements"]) == len(candidate["samples"]),
                "summary pair pixels or displacement coverage differs",
            )
            for sample, distance in zip(
                candidate["samples"], pair["sample_displacements"], strict=True
            ):
                _require(
                    type(distance["pixel_on_rendered_instance"]) is bool
                    and distance["pixel_on_rendered_instance"]
                    == (identity in sample["rendered_instance_ids"])
                    and distance["pixel_uv"] == sample["pixel_uv"]
                    and distance["depth_rank_fraction"] == sample["depth_rank_fraction"],
                    "summary sample membership or ordering differs",
                )
                for field, reference in (
                    ("to_sdk_transform", "sdk_transform_position_m"),
                    ("to_sdk_aabb_center", "sdk_aabb_center_m"),
                ):
                    _require(
                        distance[field]
                        == _displacement(sample["nominal_world_xyz_m"], instance[reference]),
                        "summary raw sample displacement differs",
                    )


def summarize(frames):
    """House/split populations with raw memberships; no score-based assignment."""
    frames = list(frames)
    action_ids = set()
    instance_audits = {}
    for frame in frames:
        _validate_matrix(frame)
        house = frame["house_index"]
        _require(
            type(house) is int
            and 1 <= house <= 12
            and frame["split"] == ("train" if house <= 8 else "validation"),
            "frame partition differs from fixed house index",
        )
        _require(frame["action_id"] not in action_ids, "duplicate frame action in summary")
        action_ids.add(frame["action_id"])
        _require(
            all(
                row["eligibility"]["house_index"] == house
                and row["eligibility"]["split"] == frame["split"]
                for row in frame["instances"]
            ),
            "frame partition differs from instance audit",
        )
        for row in frame["instances"]:
            key = (house, row["object_id"])
            _require(
                key not in instance_audits or instance_audits[key] == row["eligibility"],
                "eligibility audit changed between frames",
            )
            instance_audits[key] = row["eligibility"]
    return _plain(
        dict(
            scope="DESCRIPTIVE_ALL_CANDIDATE_ALL_INSTANCE_OFFLINE_PIXEL_MEMBERSHIP",
            category_mapping_applied=False,
            automatic_instance_assignment=False,
            formal_detection_accuracy=False,
            calibrated_position_error=False,
            independence_claim=False,
            position_interpretation=(
                "Only rendered mask-member surface samples enter distance "
                "summaries; SDK pivot and AABB center remain separate references."
            ),
            overall=_group(frames),
            by_split={
                split: _group([frame for frame in frames if frame["split"] == split])
                for split in ("train", "validation")
            },
            by_house={
                str(house): _group([frame for frame in frames if frame["house_index"] == house])
                for house in sorted({frame["house_index"] for frame in frames})
            },
        )
    )
