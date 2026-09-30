"""Owned RGB-D positive paths and complete-but-wrong private supervision attacks."""

import copy
import json
from dataclasses import asdict, replace
from uuid import uuid4

import instance_affinity_dataset as task
import numpy as np
import pytest
from test_offline_frontend_evaluation import frame_args
from test_surface_factor_diagnostic import EmptyDecoder

from cpswm.perception_mapping.unity_rgbd import surface_support
from cpswm.system.owned_visual_support import _frame_support
from cpswm.system.reproducibility import canonical_json


def plain(value):
    return json.loads(canonical_json(value))


def frontends(args, *, frame=None):
    support = args["public"]
    if frame is not None:
        support = replace(
            _frame_support(args["delivery"].observations[0], frame, args["delivery"].received_at),
            geometry=surface_support(
                args["delivery"].observations, frame, cutoff=args["delivery"].received_at
            ),
        )
    entry = plain(
        dict(command=asdict(args["command"]), frame=asdict(support), decoder_binding="a" * 64)
    )
    return {method: copy.deepcopy(entry) for method in task.METHODS}


def public(args, entries=None):
    return task.public_frame(args["command"], args["delivery"], entries or frontends(args))


def labels(args, record):
    return task.label_frame(
        record,
        args["sdk"],
        args["info"],
        args["masks"],
        args["segmentation"],
        args["eligibility"],
        sdk_rgb_bytes=args["delivery"].observations[0].payload_bytes,
        sdk_depth_bytes=args["delivery"].observations[1].payload_bytes,
    )


def test_full_public_grid_union_deduplicates_methods_boxes_and_preserves_sources(tmp_path):
    args = frame_args(tmp_path)
    record = public(args)
    assert record["pairs"].shape == (120, 4)  # all unordered pairs of 16 unique pixels
    assert record["X"].shape == (120, 8) and record["valid"].all()
    assert record["pairs"].tolist() == sorted(record["pairs"].tolist())
    assert len({tuple(pair) for pair in record["pairs"]}) == 120
    assert len(record["candidates"]) == 6
    assert record["candidates"][0]["pair_indices"] == list(range(120))
    assert record["candidates"][3]["pair_indices"] == list(range(120))
    assert sum(len(row["pair_indices"]) for row in record["candidates"]) == 264
    assert all("category" not in row for row in record["candidates"])
    assert not {"split", "house_index", "targets", "instances"} & set(record)
    assert not {"split", "house_index"} & set(record["public_metadata"])
    assert not record["X"].flags.writeable
    assert not record["pairs"].flags.writeable
    assert set(record["public_metadata"]["sources"]) == set(task.METHODS)


def test_same_and_different_use_instance_membership_without_category_mapping(tmp_path):
    args = frame_args(tmp_path)
    for row in args["eligibility"]:
        row.update(eligible=True, exclusion_reasons=[])
    record = public(args)
    result = labels(args, record)
    assert result["targets"].dtype == np.int8
    assert dict(zip(*np.unique(result["targets"], return_counts=True), strict=True)) == {
        0: 64,
        1: 56,
    }
    assert sum(result["void_reasons"].values()) == 0
    for pair, label in zip(record["pairs"], result["targets"], strict=True):
        assert label == int((pair[1] < 2) == (pair[3] < 2))
    assert len(result["instances"]) == 3
    absent = next(row for row in result["instances"] if row["object_id"] == "Bottle|absent")
    assert absent["pixels"] == 0 and absent["eligible"] and absent["bbox"] is None
    assert not result["semantic_category_mapping"]
    assert not result["formal_position_reference_selected"]


def test_ineligible_context_never_becomes_different_negative(tmp_path):
    args = frame_args(tmp_path)
    result = labels(args, public(args))
    assert int((result["targets"] == 1).sum()) == 28
    assert not (result["targets"] == 0).any()
    assert result["void_reasons"] == dict(
        invalid_depth=0, ambiguous_membership=0, unmapped_pixel=0, ineligible_instance=92
    )
    assert len(result["point_members"]) == 16
    tomato = [point for point in result["point_members"] if point["pixel_uv"][1] >= 2]
    assert all(point["object_ids"] == ["Tomato|two"] for point in tomato)
    assert all(not point["eligible_object_ids"] for point in tomato)


@pytest.mark.parametrize("empty", ["candidates", "subpixel_box"])
def test_zero_pairs_keep_frame_candidates_and_complete_invisible_catalog(tmp_path, empty):
    args = frame_args(tmp_path, decoder=EmptyDecoder() if empty == "candidates" else None)
    entries = None
    if empty == "subpixel_box":
        visual = args["public"].frame
        candidate = replace(visual.candidates[0], box_xyxy=(0.01, 0.01, 0.02, 0.02))
        entries = frontends(args, frame=replace(visual, candidates=(candidate,)))
    record = public(args, entries)
    assert record["pairs"].shape == (0, 4)
    assert record["X"].shape == (0, 8) and record["valid"].shape == (0,)
    assert len(record["candidates"]) == (0 if empty == "candidates" else 2)
    result = labels(args, record)
    assert result["targets"].shape == (0,)
    assert result["pair_point_indices"].shape == (0, 2)
    assert result["point_members"] == [] and len(result["instances"]) == 3
    assert sum(result["void_reasons"].values()) == 0


def test_invalid_depth_has_priority_and_is_retained_as_void(tmp_path):
    args = frame_args(tmp_path, depth=np.zeros((4, 4), dtype=np.float32))
    record = public(args)
    assert len(record["pairs"]) == 120 and not record["valid"].any()
    assert not record["X"].any()
    result = labels(args, record)
    assert (result["targets"] == -1).all()
    assert result["void_reasons"]["invalid_depth"] == 120
    assert sum(result["void_reasons"].values()) == 120


@pytest.mark.parametrize("second_eligible", [False, True])
def test_ambiguous_membership_is_void_even_with_one_or_two_eligible_members(
    tmp_path, second_eligible
):
    args = frame_args(tmp_path)
    # A coherent ambiguous SDK color catalog, not a broken standalone mask hash.
    for color in args["info"]["colors"]:
        if color["name"] == "Bottle|absent":
            color["color"] = [100, 0, 0]
    args["sdk"]["metadata"]["colors"] = copy.deepcopy(args["info"]["colors"])
    keys = {row["object_id"]: row["array_key"] for row in args["info"]["catalog"]}
    args["masks"][keys["Bottle|absent"]] = args["masks"][keys["Apple|one"]].copy()
    if not second_eligible:
        args["eligibility"][2].update(eligible=False, exclusion_reasons=["controlled_exclusion"])
    result = labels(args, public(args))
    assert (result["targets"] == -1).all()
    assert result["void_reasons"]["ambiguous_membership"] == 92
    assert result["void_reasons"]["ineligible_instance"] == 28
    assert sum(result["void_reasons"].values()) == 120


def test_unknown_asset_context_stays_in_catalog_and_void_membership(tmp_path):
    args = frame_args(tmp_path)
    for obj in args["sdk"]["metadata"]["objects"]:
        if obj["objectId"] == "Tomato|two":
            obj.update(assetId=None, objectType="GeneratedComponent")
    for row in args["info"]["catalog"]:
        if row["object_id"] == "Tomato|two":
            row.update(asset_id=None, object_type="GeneratedComponent")
    args["eligibility"][1].update(
        asset_id=None, object_type="GeneratedComponent", exclusion_reasons=["unknown_sdk_instance"]
    )
    result = labels(args, public(args))
    unknown = next(row for row in result["instances"] if row["object_id"] == "Tomato|two")
    assert unknown["asset_id"] is None and unknown["pixels"] == 8
    assert unknown["exclusion_reasons"] == ["unknown_sdk_instance"]
    assert result["void_reasons"]["ineligible_instance"] == 92
    assert not (result["targets"] == 0).any()


def test_unmapped_pixel_is_not_background_negative(tmp_path):
    args = frame_args(tmp_path)
    args["segmentation"][0, 0] = [0, 0, 0]
    for mask in args["masks"].values():
        mask[0, 0] = False
    result = labels(args, public(args))
    assert result["void_reasons"]["unmapped_pixel"] == 15
    assert sum(result["void_reasons"].values()) == int((result["targets"] == -1).sum())


@pytest.mark.parametrize(
    "attack", ["method", "command", "rgb_hash", "camera", "support_box", "decoder_binding", "extra"]
)
def test_public_frontend_bindings_reject_cross_source_or_forged_entries(tmp_path, attack):
    args = frame_args(tmp_path)
    entries = frontends(args)
    entry = entries["fasterrcnn"]
    if attack == "method":
        entries["other"] = entries.pop("ssdlite")
    elif attack == "command":
        entry["command"]["action_id"] = str(uuid4())
    elif attack == "rgb_hash":
        entry["frame"]["frame"]["input_sha256"] = "b" * 64
    elif attack == "camera":
        entry["frame"]["geometry"]["camera"]["position_m"][0] += 1
    elif attack == "support_box":
        entry["frame"]["candidates"][0]["normalized_box_xyxy"][0] = 0.2
    elif attack == "decoder_binding":
        entry["decoder_binding"] = "not-a-digest"
    else:
        entry["frame"]["frame"]["object_id"] = "oracle"
    with pytest.raises(ValueError):
        public(args, entries)


@pytest.mark.parametrize("field", ["X", "pairs", "valid", "rgb", "public_metadata", "candidates"])
def test_label_join_rederives_public_arrays_instead_of_trusting_mutable_record(tmp_path, field):
    args = frame_args(tmp_path)
    record = public(args)
    if field in ("X", "pairs", "valid", "rgb"):
        record[field] = record[field].copy()
        record[field].flat[0] = 0 if field == "valid" else record[field].flat[0] + 1
    elif field == "public_metadata":
        record[field]["sources"]["fasterrcnn"]["weights_sha256"] = "b" * 64
    else:
        record[field][0]["pair_indices"] = []
    with pytest.raises(ValueError):
        labels(args, record)


@pytest.mark.parametrize(
    "attack",
    [
        "sdk_owner",
        "info_owner",
        "camera",
        "action",
        "mask",
        "drop_instance",
        "eligible",
        "partition",
    ],
)
def test_private_labels_reject_wrong_owner_same_count_mask_or_incomplete_audit(tmp_path, attack):
    args = frame_args(tmp_path)
    record = public(args)
    if attack == "sdk_owner":
        args["sdk"]["owner"] = str(uuid4())
    elif attack == "info_owner":
        args["info"]["action_id"] = str(uuid4())
    elif attack == "camera":
        args["sdk"]["metadata"]["cameraPosition"]["x"] += 1
    elif attack == "action":
        args["sdk"]["requested"]["action"] = "RotateRight"
    elif attack == "mask":
        key = args["info"]["catalog"][0]["array_key"]
        args["masks"][key] = ~args["masks"][key]
    elif attack == "drop_instance":
        args["eligibility"].pop()
    elif attack == "eligible":
        args["eligibility"][1]["eligible"] = True
    else:
        args["eligibility"][0]["split"] = "validation"
    with pytest.raises(ValueError):
        labels(args, record)


@pytest.mark.parametrize("modality", ["rgb", "depth"])
def test_same_event_raw_npy_bytes_are_required_not_caller_hash(tmp_path, modality):
    args = frame_args(tmp_path)
    payloads = dict(
        sdk_rgb_bytes=args["delivery"].observations[0].payload_bytes,
        sdk_depth_bytes=args["delivery"].observations[1].payload_bytes,
    )
    payloads[f"sdk_{modality}_bytes"] += b"forged"
    with pytest.raises(ValueError, match="SDK RGB-D bytes"):
        task.label_frame(
            public(args),
            args["sdk"],
            args["info"],
            args["masks"],
            args["segmentation"],
            args["eligibility"],
            **payloads,
        )


def test_public_features_do_not_depend_on_labels_categories_or_candidate_ids(tmp_path):
    args = frame_args(tmp_path)
    first = public(args)
    visual = args["public"].frame
    candidates = tuple(
        replace(candidate, candidate_id=uuid4(), category="unmapped-native-name")
        for candidate in visual.candidates
    )
    second = public(args, frontends(args, frame=replace(visual, candidates=candidates)))
    for name in ("pairs", "X", "valid"):
        assert np.array_equal(first[name], second[name])
    # Changing only eligibility modifies labels, never the already built feature rows.
    one = labels(args, first)
    for row in args["eligibility"]:
        row.update(eligible=True, exclusion_reasons=[])
    two = labels(args, first)
    assert not np.array_equal(one["targets"], two["targets"])
    assert np.array_equal(first["X"], second["X"])
