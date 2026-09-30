"""Analytic public surface estimates and hostile inputs; no real-data training."""

import copy
import io
from uuid import uuid4

import numpy as np
import pytest
from test_unity_rgbd import packet

from cpswm.data_preflight import instance_affinity
from cpswm.data_preflight import soft_surface_position as task
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256


def controlled_model():
    # A controlled schema-valid constant score, not the real fixed trained model.
    x = np.array([[0.0] * 8, [0.2] * 8, [0.1] * 8, [0.3] * 8])
    model = instance_affinity.fit(x, np.array([1, 0, 1, 0], dtype=np.int8))
    model.update(weights=[0.0] * 8, bias=0.0)
    return model


@pytest.fixture
def args():
    rows, cutoff = packet()
    camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
    return dict(
        rgb=np.load(io.BytesIO(rows[0].payload_bytes), allow_pickle=False),
        depth=depth.copy(),
        camera=camera,
        candidates=[
            dict(method=method, id=str(uuid4()), box=[0.0, 0.0, 4.0, 4.0])
            for method in ("fasterrcnn", "ssdlite")
        ],
        model=controlled_model(),
        provenance=dict(
            source_sha256="b" * 64,
            receipt_sha256="c" * 64,
            observation_ids=[str(row.envelope().identity.observation_id) for row in rows],
            payload_sha256=[row.envelope().payload.payload_sha256 for row in rows],
        ),
    )


def evaluated(args):
    return task.readout_frame(**args, externalpin=content_sha256(args["model"]))


def test_analytic_soft_and_uniform_readouts_keep_all_seeds_and_cross_method_sources(args):
    result = evaluated(args)
    assert len(result["candidates"]) == 2 and len(result["neighborhoods"]) == 1
    assert len(result["seeds"]) == 16 and len(result["observations"]) == 32
    assert len(result["pairs"]) == 120 and set(result["pair_scores"]) == {0.5}
    points = np.array(result["neighborhoods"][0]["world_points_m"])
    for index, seed in enumerate(result["seeds"]):
        assert len(seed["sources"]) == 2
        soft, uniform = result["observations"][2 * index : 2 * index + 2]
        assert soft["measurement_id"] == uniform["measurement_id"] == seed["seed_id"]
        assert soft["domain_id"] == task.DOMAIN
        np.testing.assert_allclose(soft["world_point_m"], (points.sum(0) + points[index]) / 17)
        np.testing.assert_allclose(uniform["world_point_m"], points.mean(0))
        weights = seed["coefficients"]["soft_affinity"]
        assert weights["raw"][index] == 1 and weights["total"] == 8.5
        assert sum(weights["normalized"]) == pytest.approx(1)
        assert soft["estimator_pin"] != uniform["estimator_pin"]
    assert not result["instance_labels_used"] and not result["observation_likelihood_written"]
    assert not result["formal_position_reference_selected"]


def test_exact_grid_deduplication_but_same_seed_different_neighborhoods_remain(args):
    args["candidates"][1]["box"] = [0.01, 0.01, 3.99, 3.99]
    assert len(evaluated(args)["seeds"]) == 16
    args["candidates"].append(dict(method="fasterrcnn", id=str(uuid4()), box=[0, 0, 2, 2]))
    result = evaluated(args)
    assert len(result["neighborhoods"]) == 2 and len(result["seeds"]) == 20
    at_origin = [s for s in result["seeds"] if s["pixel_uv"] == [0, 0]]
    assert len(at_origin) == 2 and at_origin[0]["seed_id"] != at_origin[1]["seed_id"]


def test_candidate_input_order_is_canonical(args):
    first = evaluated(args)
    args["candidates"].reverse()
    assert evaluated(args) == first


@pytest.mark.parametrize("invalid", [0.0, -1.0, float("nan"), float("inf"), 20.0])
def test_invalid_seed_unavailable_and_invalid_neighbor_never_averaged(args, invalid):
    args["depth"][0, 0] = invalid
    result = evaluated(args)
    invalid_seed = next(s for s in result["seeds"] if s["pixel_uv"] == [0, 0])
    assert invalid_seed["valid"] is False and invalid_seed["reason"] == "invalid_depth"
    invalid_rows = [o for o in result["observations"] if o["seed_id"] == invalid_seed["seed_id"]]
    assert len(invalid_rows) == 2 and all(o["world_point_m"] is None for o in invalid_rows)
    assert sum(v is None for v in result["pair_scores"]) == 15
    for seed in result["seeds"]:
        for coefficient in seed["coefficients"].values():
            if seed["valid"]:
                assert coefficient["raw"][0] == coefficient["normalized"][0] == 0
            else:
                assert coefficient == dict(raw=None, normalized=None, total=None)
    assert len(result["seeds"]) == 16


def test_all_invalid_empty_candidates_empty_grid_and_one_pixel_are_distinct(args):
    args["depth"][:] = 0
    result = evaluated(args)
    assert len(result["seeds"]) == 16 and all(not o["available"] for o in result["observations"])
    args["candidates"] = []
    result = evaluated(args)
    assert result["candidates"] == result["neighborhoods"] == result["seeds"] == []
    args["candidates"] = [dict(method="fasterrcnn", id=str(uuid4()), box=[0.01, 0.01, 0.02, 0.02])]
    result = evaluated(args)
    assert len(result["candidates"]) == len(result["neighborhoods"]) == 1
    assert result["seeds"] == result["pairs"] == []
    args["depth"][0, 0] = 1
    args["candidates"][0]["box"] = [0, 0, 1, 1]
    result = evaluated(args)
    assert len(result["seeds"]) == 1 and result["pairs"] == []
    expected = args["camera"].world_point(0, 0, 1)
    for row in result["observations"]:
        np.testing.assert_allclose(row["world_point_m"], expected)
    assert result["seeds"][0]["coefficients"]["soft_affinity"]["raw"] == [1.0]


def test_new_action_or_scene_does_not_reuse_measurement_identity(args):
    first = evaluated(args)
    args["camera"] = args["camera"].model_copy(update={"action_id": uuid4()})
    second = evaluated(args)
    assert first["pair_scores"] == second["pair_scores"]
    assert not {o["measurement_id"] for o in first["observations"]} & {
        o["measurement_id"] for o in second["observations"]
    }
    args["camera"] = args["camera"].model_copy(update={"scene_sha256": "d" * 64})
    third = evaluated(args)
    assert second["input_sha256"] != third["input_sha256"]


def test_model_pin_changes_only_soft_estimator_and_recomputed_coefficients(args):
    first = evaluated(args)
    args["model"]["bias"] = 2.0
    with pytest.raises(ValueError, match="pin differs"):
        task.readout_frame(**args, externalpin=first["affinity_pin"])
    second = evaluated(args)
    assert first["pair_scores"] != second["pair_scores"]
    assert first["estimator_pins"]["soft_affinity"] != second["estimator_pins"]["soft_affinity"]
    assert first["estimator_pins"]["uniform"] == second["estimator_pins"]["uniform"]
    assert first["observations"][0]["world_point_m"] != second["observations"][0]["world_point_m"]
    assert first["observations"][1] == second["observations"][1]


@pytest.mark.parametrize("attack", ["private", "duplicate", "rgbpin", "uuid", "resource"])
def test_untrusted_public_inputs_and_resource_overflow_fail_closed(args, attack):
    if attack == "private":
        args["candidates"][0]["object_id"] = "SDK-target"
    elif attack == "duplicate":
        args["candidates"].append(copy.deepcopy(args["candidates"][0]))
    elif attack == "rgbpin":
        args["provenance"]["payload_sha256"][0] = "f" * 64
    elif attack == "uuid":
        args["provenance"]["observation_ids"][0] = "not-an-id"
    else:
        args["candidates"] *= task.MAX_CANDIDATES
    with pytest.raises(ValueError):
        evaluated(args)
