"""Controlled real RGB-D surface support; never natural detector accuracy evidence.
PYTEST_DONT_REWRITE: imported fixture detector implementation stays source-bound.
"""

import copy
import json
import math
from dataclasses import replace
from uuid import uuid4

import numpy as np
import offline_frontend_evaluation as task
import pytest
from test_surface_factor_diagnostic import EmptyDecoder, archive

from cpswm.system.continuous_state_codec import StateCodec


def frame_args(tmp_path, *, decoder=None, depth=None, repeat=False, house=1, frame_index=0):
    directory, _, _ = archive(tmp_path, decoder=decoder, depth=depth, repeat=repeat)
    codec = StateCodec()
    history = codec.loads((directory / "owned-history.json").read_text())
    support = codec.loads((directory / "visual-support.json").read_text())
    command, delivery = history[frame_index]
    public = support.actions[frame_index].frames[0]
    private = directory / "unity-logs/evaluator_only"
    index = 4 + frame_index
    sdk = json.loads((private / f"sdk-events/{index:03d}.json").read_text())
    info = json.loads((private / f"instances/{index:03d}.json").read_text())
    segmentation = np.load(private / f"instances/{index:03d}-segmentation.npy", allow_pickle=False)
    with np.load(private / f"instances/{index:03d}-masks.npz", allow_pickle=False) as data:
        masks = {key: data[key].copy() for key in data.files}
    eligibility = [
        dict(
            object_id=obj["objectId"],
            object_type=obj["objectType"],
            asset_id=obj["assetId"],
            position_m=[obj["position"][key] for key in "xyz"],
            aabb_center_m=[obj["axisAlignedBoundingBox"]["center"][key] for key in "xyz"],
            eligible=obj["objectType"] != "Tomato",
            exclusion_reasons=["controlled_exclusion"] if obj["objectType"] == "Tomato" else [],
            house_index=house,
            split="train" if house <= 8 else "validation",
        )
        for obj in sdk["metadata"]["objects"]
    ]
    return dict(
        command=command,
        delivery=delivery,
        public=public,
        sdk=sdk,
        info=info,
        masks=masks,
        segmentation=segmentation,
        eligibility=eligibility,
    )


def evaluated(args):
    row = task.evaluate_frame(**args)
    row.update(
        house_index=args["eligibility"][0]["house_index"], split=args["eligibility"][0]["split"]
    )
    return row


def test_complete_cross_category_matrix_preserves_invisible_and_noneligible_instances(tmp_path):
    args = frame_args(tmp_path)
    frame = evaluated(args)
    assert [row["category"] for row in frame["candidates"]] == ["apple", "apple", "cup"]
    instances = {row["object_id"]: row for row in frame["instances"]}
    assert instances["Bottle|absent"]["pixels"] == 0
    assert instances["Bottle|absent"]["eligible"]
    assert not instances["Tomato|two"]["eligible"]
    assert instances["Tomato|two"]["object_type"] == "Tomato"
    assert len(frame["instances"]) == 3
    assert all(len(candidate["overlaps"]) == 3 for candidate in frame["candidates"])
    assert all(
        len(pair["sample_displacements"]) == 3
        for candidate in frame["candidates"]
        for pair in candidate["overlaps"]
    )
    first = {row["object_id"]: row for row in frame["candidates"][0]["overlaps"]}
    assert first["Apple|one"]["intersection_pixels"] == 8
    assert first["Tomato|two"]["intersection_pixels"] == 8
    assert first["Bottle|absent"]["intersection_pixels"] == 0
    summary = task.summarize([frame])
    all_rows = summary["overall"]["all_instances"]
    selected = summary["overall"]["eligible_instances"]
    assert all_rows["candidate_instance_pairs"] == 9
    assert all_rows["positive_overlap_pairs"] == 4 and all_rows["zero_overlap_pairs"] == 5
    assert all_rows["candidate_boxes_with_multiple_selected_instances"] == 1
    assert all_rows["multiply_box_overlapped_instance_frames"] == 2
    assert all_rows["unique_instances"] == 3 and all_rows["visible_instance_frames"] == 2
    assert selected["unique_instances"] == 2 and selected["visible_instance_frames"] == 1
    assert selected["candidate_boxes_with_no_selected_instance"] == 1
    assert all_rows["native_detector_category_candidate_counts"] == {"apple": 2, "cup": 1}
    assert all_rows["native_sdk_object_type_instance_frame_counts"] == {
        "Apple": 1,
        "Bottle": 1,
        "Tomato": 1,
    }
    assert not any(
        summary[key]
        for key in (
            "category_mapping_applied",
            "automatic_instance_assignment",
            "formal_detection_accuracy",
            "calibrated_position_error",
            "independence_claim",
        )
    )


def test_distance_distributions_include_only_actual_sample_mask_members_and_both_references(
    tmp_path,
):
    frame = evaluated(frame_args(tmp_path))
    pivot, aabb = [], []
    all_displacements = []
    for candidate in frame["candidates"]:
        for pair in candidate["overlaps"]:
            reference = next(r for r in frame["instances"] if r["object_id"] == pair["object_id"])
            for sample, delta in zip(
                candidate["samples"], pair["sample_displacements"], strict=True
            ):
                point = sample["nominal_world_xyz_m"]
                expected_pivot = math.dist(point, reference["sdk_transform_position_m"])
                expected_aabb = math.dist(point, reference["sdk_aabb_center_m"])
                assert delta["to_sdk_transform"]["distance_m"] == pytest.approx(expected_pivot)
                assert delta["to_sdk_aabb_center"]["distance_m"] == pytest.approx(expected_aabb)
                all_displacements.append(delta)
                if delta["pixel_on_rendered_instance"]:
                    pivot.append(delta["to_sdk_transform"]["distance_m"])
                    aabb.append(delta["to_sdk_aabb_center"]["distance_m"])
    group = task.summarize([frame])["overall"]["all_instances"]
    assert len(all_displacements) == 27
    assert group["member_sample_instance_pairs"] == len(pivot) == 9
    assert group["member_surface_to_sdk_pivot_raw_distance"]["values_m"] == pivot
    assert group["member_surface_to_sdk_aabb_center_raw_distance"]["values_m"] == aabb
    assert pivot != aabb
    assert group["member_surface_to_sdk_pivot_raw_distance"]["median_m"] == pytest.approx(
        float(np.median(pivot))
    )


@pytest.mark.parametrize("case", ["no_candidates", "invalid_depth"])
def test_empty_candidates_or_samples_retain_all_instances_and_zero_coverage(tmp_path, case):
    args = frame_args(
        tmp_path,
        decoder=EmptyDecoder() if case == "no_candidates" else None,
        depth=np.zeros((4, 4), dtype=np.float32) if case == "invalid_depth" else None,
    )
    frame = evaluated(args)
    group = task.summarize([frame])["overall"]["all_instances"]
    assert len(frame["instances"]) == 3 and group["instance_frames"] == 3
    assert group["visible_instance_frames"] == 2
    assert group["surface_samples"] == 0 and group["sample_hit_instance_frames"] == 0
    distribution = group["member_surface_to_sdk_pivot_raw_distance"]
    assert distribution["values_m"] == [] and distribution["median_m"] is None
    if case == "no_candidates":
        assert group["frames_without_candidates"] == 1 and group["candidates"] == 0
        assert group["box_overlapping_instance_frames"] == 0
    else:
        assert group["candidates"] == 3 and group["candidate_instance_pairs"] == 9
        assert group["box_overlapping_instance_frames"] == 2


def test_repeated_inputs_keep_object_unions_separate_from_object_frame_counts(tmp_path):
    first = evaluated(frame_args(tmp_path / "one"))
    second = evaluated(frame_args(tmp_path / "two"))
    summary = task.summarize([first, second])
    overall = summary["overall"]
    assert (
        overall["frames"] == 2 and overall["unique_rgb"] == overall["unique_geometry_inputs"] == 1
    )
    assert overall["all_instances"]["unique_instances"] == 3
    assert overall["all_instances"]["instance_frames"] == 6
    assert overall["all_instances"]["box_overlapping_instance_frames"] == 4
    assert overall["all_instances"]["unique_box_overlapping_instances"] == 2
    assert overall["eligible_instances"]["visible_instance_frames"] == 2
    assert overall["eligible_instances"]["unique_visible_instances"] == 1


def test_house_identity_and_split_remain_distinct_even_with_identical_sdk_ids(tmp_path):
    train = evaluated(frame_args(tmp_path / "train", house=1))
    validation = evaluated(frame_args(tmp_path / "validation", house=9))
    summary = task.summarize([train, validation])
    assert summary["overall"]["all_instances"]["unique_instances"] == 6
    assert summary["overall"]["eligible_instances"]["unique_visible_instances"] == 2
    assert set(summary["by_house"]) == {"1", "9"}
    assert (
        summary["by_split"]["train"]["frames"] == summary["by_split"]["validation"]["frames"] == 1
    )
    assert summary["by_house"]["9"]["eligible_instances"]["unique_instances"] == 2


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "duplicate",
        "asset",
        "category",
        "position",
        "aabb",
        "flag",
        "other_house",
        "split",
    ],
)
def test_forged_or_incomplete_eligibility_is_rejected(tmp_path, attack):
    args = frame_args(tmp_path)
    audit = args["eligibility"]
    if attack == "missing":
        audit.pop()
    elif attack == "duplicate":
        audit.append(copy.deepcopy(audit[0]))
    elif attack == "asset":
        audit[0]["asset_id"] = "invented"
    elif attack == "category":
        audit[0]["object_type"] = "invented"
    elif attack == "position":
        audit[0]["position_m"][0] += 1
    elif attack == "aabb":
        audit[0]["aabb_center_m"][0] += 1
    elif attack == "flag":
        audit[0]["eligible"] = False
    elif attack == "other_house":
        audit[0]["house_index"] = 2
    else:
        audit[0]["split"] = "validation"
    with pytest.raises(ValueError, match="eligibility"):
        task.evaluate_frame(**args)


@pytest.mark.parametrize("attack", ["sdk_owner", "delivery_owner", "camera", "mask", "sample"])
def test_complete_but_wrong_frame_sources_are_rejected(tmp_path, attack):
    args = frame_args(tmp_path)
    if attack == "sdk_owner":
        args["sdk"]["owner"] = str(uuid4())
    elif attack == "delivery_owner":
        args["delivery"] = replace(args["delivery"], action_id=uuid4())
    elif attack == "camera":
        args["sdk"]["metadata"]["cameraPosition"]["x"] += 1
    elif attack == "mask":
        key = args["info"]["catalog"][0]["array_key"]
        args["masks"][key] = ~args["masks"][key]
    else:
        public = args["public"]
        candidate = public.geometry.candidates[0]
        wrong = replace(candidate.samples[0], nominal_world_xyz_m=(99.0, 99.0, 99.0))
        candidate = replace(candidate, samples=(wrong, *candidate.samples[1:]))
        args["public"] = replace(
            public,
            geometry=replace(
                public.geometry, candidates=(candidate, *public.geometry.candidates[1:])
            ),
        )
    with pytest.raises(ValueError):
        task.evaluate_frame(**args)


def test_summary_rejects_duplicate_frame_and_partition_relabel(tmp_path):
    row = evaluated(frame_args(tmp_path))
    with pytest.raises(ValueError, match="duplicate frame"):
        task.summarize([row, row])
    row["house_index"] = 9
    row["split"] = "validation"
    with pytest.raises(ValueError, match="instance audit"):
        task.summarize([row])


def test_zero_frame_summary_retains_both_partitions_and_no_fake_distribution():
    summary = task.summarize([])
    assert summary["overall"]["frames"] == 0 and summary["by_house"] == {}
    assert set(summary["by_split"]) == {"train", "validation"}
    assert summary["overall"]["all_instances"]["unique_instances"] == 0
    assert (
        summary["overall"]["all_instances"]["member_surface_to_sdk_pivot_raw_distance"]["values_m"]
        == []
    )


@pytest.mark.parametrize(
    "attack",
    [
        "omit_zero_pair",
        "duplicate_pair",
        "omit_displacement",
        "flip_membership",
        "forge_distance",
        "flip_eligibility",
        "duplicate_candidate",
    ],
)
def test_summary_rejects_incomplete_or_self_inconsistent_full_matrix(tmp_path, attack):
    frame = evaluated(frame_args(tmp_path))
    candidate = frame["candidates"][0]
    invisible = next(row for row in candidate["overlaps"] if row["object_id"] == "Bottle|absent")
    if attack == "omit_zero_pair":
        candidate["overlaps"].remove(invisible)
    elif attack == "duplicate_pair":
        candidate["overlaps"].append(copy.deepcopy(invisible))
    elif attack == "omit_displacement":
        invisible["sample_displacements"].pop()
    elif attack == "flip_membership":
        invisible["sample_displacements"][0]["pixel_on_rendered_instance"] = True
    elif attack == "forge_distance":
        invisible["sample_displacements"][0]["to_sdk_transform"]["distance_m"] = 0.0
    elif attack == "flip_eligibility":
        frame["instances"][0]["eligible"] = not frame["instances"][0]["eligible"]
    else:
        frame["candidates"].append(copy.deepcopy(candidate))
    with pytest.raises(ValueError, match=r"summary|duplicate"):
        task.summarize([frame])
