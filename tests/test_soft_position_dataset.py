"""Real owned fixture capture, independent seed labels and complete forged readouts."""

import copy
from dataclasses import replace

import numpy as np
import pytest
import soft_position_dataset as task
from test_instance_affinity_dataset import frontends, public
from test_offline_frontend_evaluation import frame_args
from test_soft_surface_position import controlled_model
from test_surface_factor_diagnostic import EmptyDecoder

from cpswm.system.reproducibility import content_sha256


def build(args, entries=None):
    record = public(args, entries)
    model = controlled_model()
    pin = content_sha256(model)
    return record, model, pin, task.public_readout(record, model, pin)


def labels(args, record, model, pin, readout):
    return task.label_readout(
        record,
        readout,
        args["sdk"],
        args["info"],
        args["masks"],
        args["segmentation"],
        args["eligibility"],
        affinity_model=model,
        affinity_pin=pin,
        sdk_rgb_bytes=args["delivery"].observations[0].payload_bytes,
        sdk_depth_bytes=args["delivery"].observations[1].payload_bytes,
    )


def test_public_to_private_full_path_preserves_all_seeds_instances_and_dual_references(tmp_path):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    before = content_sha256(readout)
    result = labels(args, record, model, pin, readout)
    assert len(result["labels"]) == len(readout["observations"])
    assert result["readout_sha256"] == before == content_sha256(readout)
    assert len(result["instances"]) == 3
    assert next(r for r in result["instances"] if r["object_id"] == "Bottle|absent")["pixels"] == 0
    assert set(result["references"]) == {"sdk_transform_position_m", "sdk_aabb_center_m"}
    for observation, label in zip(readout["observations"], result["labels"], strict=True):
        assert observation["measurement_id"] == label["measurement_id"]
        assert observation["estimator"] == label["estimator"]
        assert not {"house_index", "split", "object_id", "targets"} & set(observation)
        if label["eligible"]:
            assert label["object_id"] == "Apple|one"
            assert (
                label["targets"]["sdk_transform_position_m"]
                != label["targets"]["sdk_aabb_center_m"]
            )
        else:
            assert label["object_id"] is None
            assert set(label["targets"].values()) == {None}
    assert result["void_counts"]["ineligible_instance"] > 0
    assert sum(result["void_counts"].values()) == sum(not r["eligible"] for r in result["labels"])


def test_mask_eligibility_only_changes_labels_never_public_readout(tmp_path):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    first = labels(args, record, model, pin, readout)
    for row in args["eligibility"]:
        row.update(eligible=True, exclusion_reasons=[])
    second = labels(args, record, model, pin, readout)
    assert sum(r["eligible"] for r in second["labels"]) > sum(
        r["eligible"] for r in first["labels"]
    )
    assert task.public_readout(record, model, pin) == readout
    assert first["private_lineage_sha256"] != second["private_lineage_sha256"]


def test_single_pixel_grid_has_supervision_without_any_pair(tmp_path):
    args = frame_args(tmp_path)
    visual = args["public"].frame
    frame = replace(
        visual, candidates=(replace(visual.candidates[0], box_xyxy=(0.0, 0.0, 1.0, 1.0)),)
    )
    record, model, pin, readout = build(args, frontends(args, frame=frame))
    assert record["pairs"].shape == (0, 4) and len(readout["seeds"]) == 1
    result = labels(args, record, model, pin, readout)
    assert len(result["point_members"]) == 1 and len(result["labels"]) == 2
    assert all(r["eligible"] and r["object_id"] == "Apple|one" for r in result["labels"])


def test_zero_candidates_keeps_complete_private_catalog(tmp_path):
    args = frame_args(tmp_path, decoder=EmptyDecoder())
    record, model, pin, readout = build(args)
    result = labels(args, record, model, pin, readout)
    assert readout["observations"] == readout["seeds"] == result["labels"] == []
    assert len(result["instances"]) == 3 and sum(result["void_counts"].values()) == 0


def test_invalid_seed_priority_and_unmapped_and_ambiguous_membership(tmp_path):
    args = frame_args(tmp_path, depth=np.zeros((4, 4), dtype=np.float32))
    record, model, pin, readout = build(args)
    result = labels(args, record, model, pin, readout)
    assert result["void_counts"]["invalid_depth"] == len(result["labels"])
    assert all(row["world_point_m"] is None for row in readout["observations"])


@pytest.mark.parametrize("kind", ["unmapped", "ambiguous"])
def test_rendered_membership_void_is_not_a_negative_or_arbitrary_object(tmp_path, kind):
    args = frame_args(tmp_path)
    if kind == "unmapped":
        args["segmentation"][0, 0] = [0, 0, 0]
        for mask in args["masks"].values():
            mask[0, 0] = False
    else:
        for color in args["info"]["colors"]:
            if color["name"] == "Bottle|absent":
                color["color"] = [100, 0, 0]
        args["sdk"]["metadata"]["colors"] = copy.deepcopy(args["info"]["colors"])
        keys = {r["object_id"]: r["array_key"] for r in args["info"]["catalog"]}
        args["masks"][keys["Bottle|absent"]] = args["masks"][keys["Apple|one"]].copy()
    record, model, pin, readout = build(args)
    result = labels(args, record, model, pin, readout)
    reason = "unmapped_pixel" if kind == "unmapped" else "ambiguous_membership"
    assert result["void_counts"][reason] > 0
    assert all(r["object_id"] is None for r in result["labels"] if r["void_reason"] == reason)


@pytest.mark.parametrize(
    "attack", ["readout", "weight", "pair_score", "sources", "seed_drop", "pin"]
)
def test_complete_forged_public_output_cannot_enter_supervision(tmp_path, attack):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    bad = copy.deepcopy(readout)
    if attack == "readout":
        bad["observations"][0]["world_point_m"][0] += 1
    elif attack == "weight":
        bad["seeds"][0]["coefficients"]["soft_affinity"]["raw"][0] = 0.3
    elif attack == "pair_score":
        bad["pair_scores"][0] = 0.9
    elif attack == "sources":
        bad["seeds"][0]["sources"] = []
    elif attack == "seed_drop":
        bad["observations"] = bad["observations"][2:]
        bad["seeds"] = bad["seeds"][1:]
    else:
        bad["affinity_pin"] = "f" * 64
    # The attacker may freely compute an outer hash; equality to trusted recomputation still fails.
    assert content_sha256(bad) != content_sha256(readout)
    with pytest.raises(ValueError, match="readout differs"):
        labels(args, record, model, pin, bad)
    assert labels(args, record, model, pin, readout)["labels"]


@pytest.mark.parametrize(
    "attack", ["empty_audit", "mixed_house", "camera", "rgb", "mask", "pivot", "catalog"]
)
def test_same_event_private_binding_and_complete_catalog_are_mandatory(tmp_path, attack):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    if attack == "empty_audit":
        args["eligibility"] = []
    elif attack == "mixed_house":
        args["eligibility"][0]["house_index"] = 2
    elif attack == "camera":
        args["sdk"]["metadata"]["cameraPosition"]["x"] += 1
    elif attack == "rgb":
        record["rgb"] = record["rgb"].copy()
        record["rgb"][0, 0, 0] ^= 1
    elif attack == "mask":
        next(iter(args["masks"].values()))[0, 0] ^= True
    elif attack == "pivot":
        args["eligibility"][0]["position_m"][0] += 1
    else:
        args["info"]["catalog"] = args["info"]["catalog"][:-1]
    with pytest.raises(ValueError):
        labels(args, record, model, pin, readout)
