"""Controlled public-pixel learning and hostile checkpoint boundaries, no real data."""

import copy
import io
import json
import math

import numpy as np
import pytest
from test_unity_rgbd import packet

from cpswm.data_preflight import instance_affinity as task
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256


@pytest.fixture
def sensors():
    rows, cutoff = packet()
    camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
    rgb = np.load(io.BytesIO(rows[0].payload_bytes), allow_pickle=False)
    return rgb, depth.copy(), camera


def test_grid_cells_half_open_bounds_deduplication_and_canonical_all_pairs():
    points = task.grid_pixels((0.0, 0.0, 320.0, 320.0), 320, 320)
    assert points == tuple((u, v) for u in range(20, 320, 40) for v in range(20, 320, 40))
    pairs = task.pixel_pairs([*reversed(points), points[0], points[-1]])
    assert pairs.dtype == np.int64 and pairs.shape == (2016, 4)
    assert len({tuple(pair) for pair in pairs.tolist()}) == 2016
    assert all(tuple(row[:2]) < tuple(row[2:]) for row in pairs.tolist())
    assert task.grid_pixels((-3, -2, 1, 2), 4, 4) == ((0, 0), (0, 1))
    assert task.grid_pixels((0.6, 0.6, 0.9, 0.9), 4, 4) == ()
    assert task.grid_pixels((0.5, 0.5, 1.5, 1.5), 4, 4) == ((0, 0),)
    assert task.grid_pixels((4, 0, 5, 4), 4, 4) == ()
    assert task.pixel_pairs(()).shape == task.pixel_pairs(((0, 0),)).shape == (0, 4)
    for box in ((0.2, 0.8, 2.1, 3.7), (-4, -4, 1.5, 1.5), (1.49, 1.49, 1.51, 1.51)):
        for u, v in task.grid_pixels(box, 4, 4):
            assert 0 <= u < 4 and 0 <= v < 4
            assert box[0] <= u + 0.5 < box[2] and box[1] <= v + 0.5 < box[3]


@pytest.mark.parametrize(
    "box,width,height",
    [
        ((0, 0, 1, 1), True, 4),
        ((0, 0, 1, 1), 0, 4),
        ((0, 0, 1), 4, 4),
        ((0, 0, 0, 1), 4, 4),
        ((0, 0, float("nan"), 1), 4, 4),
        ((0, False, 1, 1), 4, 4),
    ],
)
def test_invalid_grid_inputs_are_not_silently_repaired(box, width, height):
    with pytest.raises(ValueError):
        task.grid_pixels(box, width, height)


@pytest.mark.parametrize("points", [[[True, 1]], [[1.0, 1]], [[-1, 0]], [[640, 0]], [[1, 2, 3]]])
def test_invalid_pair_coordinates_are_rejected(points):
    with pytest.raises(ValueError):
        task.pixel_pairs(points)


def test_public_features_have_analytic_values_and_exact_swap_symmetry(sensors):
    rgb, depth, camera = sensors
    rgb[0, 0] = (255, 0, 128)
    rgb[1, 2] = (0, 128, 0)
    depth[0, 0], depth[1, 2] = 1.0, 2.0
    pairs = np.asarray([[0, 0, 2, 1], [2, 1, 0, 0]], dtype=np.int64)
    x, valid = task.pair_features(rgb, depth, camera, pairs)
    expected = [
        1.0,
        128 / 255,
        128 / 255,
        0.5,
        0.25,
        1.0,
        math.log(2),
        math.dist(camera.world_point(0, 0, 1.0), camera.world_point(2, 1, 2.0)),
    ]
    assert x.dtype == np.float64 and valid.dtype == np.bool_
    np.testing.assert_allclose(x[0], expected, rtol=1e-14)
    np.testing.assert_array_equal(x[0], x[1])
    assert valid.tolist() == [True, True]
    empty, mask = task.pair_features(rgb, depth, camera, np.empty((0, 4), dtype=np.int64))
    assert empty.shape == (0, 8) and mask.shape == (0,)


@pytest.mark.parametrize("bad_depth", [0.0, -1.0, float("nan"), float("inf"), 19.9, 20.0])
def test_invalid_depth_is_retained_as_void_placeholder(sensors, bad_depth):
    rgb, depth, camera = sensors
    depth = depth.astype(np.float64)
    depth[0, 0] = bad_depth
    pairs = np.asarray([[0, 0, 1, 1], [1, 1, 2, 2]], dtype=np.int64)
    x, valid = task.pair_features(rgb, depth, camera, pairs)
    assert valid.tolist() == [False, True]
    assert np.all(x[0] == 0) and np.isfinite(x).all()


@pytest.mark.parametrize(
    "attack",
    [
        "rgb_float",
        "rgb_channels",
        "depth_int",
        "depth_shape",
        "pairs_float",
        "pairs_bool",
        "pairs_shape",
        "negative_pixel",
        "outside_pixel",
        "self_pair",
        "camera_nan",
        "camera_extra",
        "camera_shape",
        "camera_config",
    ],
)
def test_malformed_public_arrays_and_unvalidated_camera_are_rejected(sensors, attack):
    rgb, depth, camera = sensors
    pairs = np.asarray([[0, 0, 1, 1]], dtype=np.int64)
    if attack == "rgb_float":
        rgb = rgb.astype(float)
    elif attack == "rgb_channels":
        rgb = rgb[:, :, :2]
    elif attack == "depth_int":
        depth = depth.astype(np.int64)
    elif attack == "depth_shape":
        depth = depth[:2]
    elif attack == "pairs_float":
        pairs = pairs.astype(float)
    elif attack == "pairs_bool":
        pairs = pairs.astype(bool)
    elif attack == "pairs_shape":
        pairs = pairs.reshape(4)
    elif attack == "negative_pixel":
        pairs[0, 0] = -1
    elif attack == "outside_pixel":
        pairs[0, 1] = 4
    elif attack == "self_pair":
        pairs[0] = 0
    else:
        changes = {
            "camera_nan": {"position_m": (float("nan"), 0.0, 0.0)},
            "camera_extra": {"private_id": "forbidden"},
            "camera_shape": {"width": 8},
            "camera_config": {"configuration_sha256": "0" * 64},
        }
        camera = camera.model_copy(update=changes[attack])
    with pytest.raises(ValueError):
        task.pair_features(rgb, depth, camera, pairs)


def training_arrays():
    x = np.zeros((80, 8), dtype=np.float64)
    x[:, 0] = np.tile(np.linspace(0.02, 0.15, 20), 4)
    x[40:, 0] += 0.75
    x[:, 3] = np.tile(np.linspace(0.0, 0.5, 20), 4)
    x[:, 1] = 0.2  # Exact constant must not gain a tiny artificial std.
    y = np.asarray([1] * 40 + [0] * 40, dtype=np.int8)
    return x, y


def test_real_numeric_learning_beats_prevalence_and_is_deterministic():
    x, y = training_arrays()
    model = task.fit(x, y)
    scores = np.asarray(task.predict(model, x, np.ones(len(x), dtype=bool)))
    assert scores[:40].min() > 0.9 and scores[40:].max() < 0.1
    logloss = -np.mean(y * np.log(scores) + (1 - y) * np.log1p(-scores))
    assert logloss < -math.log(0.5) / 5
    assert model["weights"][0] < -1.0
    assert model["scale"][1] == 1.0 and model["mean"][1] == 0.2
    assert len(model["optimization_loss"]) == 31
    assert model["optimization_loss"][-1] < model["optimization_loss"][0]
    assert all(
        b <= a
        for a, b in zip(
            model["optimization_loss"][:-1], model["optimization_loss"][1:], strict=True
        )
    )
    assert task.fit(x, y) == model
    assert model["scope"] == task.SCOPE and model["runtime_authority"] is False
    assert model["calibrated"] is False


def test_synthetic_rgbd_pairs_flow_through_feature_fit_and_new_public_prediction(sensors):
    rgb, depth, camera = sensors
    rgb[:2] = 0
    rgb[2:] = 255
    pairs = task.pixel_pairs(task.grid_pixels((0, 0, 4, 4), 4, 4))
    x, valid = task.pair_features(rgb, depth, camera, pairs)
    targets = np.asarray([(v1 < 2) == (v2 < 2) for _, v1, _, v2 in pairs], dtype=np.int8)
    model = task.fit(x, targets)
    # A separate controlled public image, not any real validation scene.
    rgb[:2] = 20
    rgb[2:] = 230
    changed, new_valid = task.pair_features(rgb, depth, camera, pairs)
    scores = np.asarray(task.predict(model, changed, new_valid))
    assert valid.all() and new_valid.all() and not np.array_equal(x, changed)
    assert scores[targets == 1].min() > scores[targets == 0].max()
    assert model["rows_fit"] == 120


def test_void_rows_affect_input_identity_but_not_scaling_weights_or_prevalence():
    x, y = training_arrays()
    baseline = task.fit(x, y)
    void = np.zeros((5, 8), dtype=np.float64)
    void[:, 5:] = 1e100
    model = task.fit(np.vstack((x, void)), np.concatenate((y, np.full(5, -1, dtype=np.int8))))
    for key in (
        "mean",
        "scale",
        "weights",
        "bias",
        "prevalence",
        "optimization_loss",
        "class_counts",
    ):
        assert model[key] == baseline[key]
    assert (model["rows_total"], model["rows_fit"], model["rows_void"]) == (85, 80, 5)
    assert model["training_features_sha256"] != baseline["training_features_sha256"]
    assert model["training_targets_sha256"] != baseline["training_targets_sha256"]


def test_constant_training_features_produce_prevalence_without_nan():
    x = np.full((10, 8), 0.2, dtype=np.float64)
    y = np.asarray([0] * 7 + [1] * 3, dtype=np.int8)
    model = task.fit(x, y)
    np.testing.assert_allclose(task.predict(model, x, np.ones(10, dtype=bool)), 0.3, atol=1e-14)
    assert model["scale"] == [1.0] * 8 and model["weights"] == [0.0] * 8


def test_json_restore_and_invalid_rows_preserve_all_scores_without_aliasing():
    x, y = training_arrays()
    model = task.fit(x, y)
    restored = task.restore(
        json.loads(json.dumps(model, allow_nan=False)), task.checkpoint_sha256(model)
    )
    mixed = np.vstack((x[:2], np.zeros((1, 8))))
    valid = np.asarray([True, True, False])
    scores = task.predict(restored, mixed, valid)
    assert scores[:2] == task.predict(model, x[:2], valid[:2]) and scores[-1] is None
    json.dumps(scores, allow_nan=False)
    restored["weights"][0] += 1
    assert restored["weights"] != model["weights"]
    assert task.predict(model, np.empty((0, 8), dtype=float), np.empty(0, dtype=bool)) == []


@pytest.mark.parametrize(
    "attack",
    [
        "partition",
        "single_class",
        "all_void",
        "targets_dtype",
        "targets_shape",
        "target_unknown",
        "feature_int",
        "feature_nan",
        "feature_negative",
        "feature_width",
    ],
)
def test_fit_rejects_invalid_or_nontraining_data(attack):
    x, y = training_arrays()
    kwargs = {}
    if attack == "partition":
        kwargs["partition"] = "validation"
    elif attack == "single_class":
        y[:] = 1
    elif attack == "all_void":
        y[:] = -1
    elif attack == "targets_dtype":
        y = y.astype(np.int64)
    elif attack == "targets_shape":
        y = y[:, None]
    elif attack == "target_unknown":
        y[0] = 2
    elif attack == "feature_int":
        x = x.astype(np.int64)
    elif attack == "feature_nan":
        x[0, 0] = float("nan")
    elif attack == "feature_negative":
        x[0, 0] = -1
    else:
        x = x[:, :7]
    with pytest.raises(ValueError):
        task.fit(x, y, **kwargs)


@pytest.mark.parametrize(
    "attack",
    [
        "unknown",
        "authority_int",
        "authority_true",
        "weight_nan",
        "weight_integer",
        "scale_zero",
        "vector_shape",
        "rows_bool",
        "prevalence",
        "config_type",
        "config_unknown",
        "feature_definition",
        "training_digest",
        "loss_increase",
        "externalpin",
    ],
)
def test_strict_restore_rejects_structural_forgeries_even_with_rehashed_content(attack):
    x, y = training_arrays()
    model = task.fit(x, y)
    bad = copy.deepcopy(model)
    if attack == "unknown":
        bad["identity_permission"] = True
    elif attack == "authority_int":
        bad["runtime_authority"] = 0
        assert bad == model
    elif attack == "authority_true":
        bad["runtime_authority"] = True
    elif attack == "weight_nan":
        bad["weights"][0] = float("nan")
    elif attack == "weight_integer":
        bad["weights"][0] = 1
    elif attack == "scale_zero":
        bad["scale"][0] = 0.0
    elif attack == "vector_shape":
        bad["mean"].pop()
    elif attack == "rows_bool":
        bad["rows_void"] = False
    elif attack == "prevalence":
        bad["prevalence"] = 0.1
    elif attack == "config_type":
        bad["config"]["iterations"] = 30.0
        assert bad == model
    elif attack == "config_unknown":
        bad["config"]["threshold"] = 0.5
    elif attack == "feature_definition":
        bad["features"][0] = "private_instance_id"
    elif attack == "training_digest":
        bad["training_targets_sha256"] = "not-a-hash"
    elif attack == "loss_increase":
        bad["optimization_loss"][-1] = 100.0
    pin = (
        "0" * 64
        if attack == "externalpin"
        else (task.checkpoint_sha256(model) if attack == "weight_nan" else content_sha256(bad))
    )
    with pytest.raises(ValueError):
        task.restore(bad, pin)


def test_fully_formed_weight_change_cannot_reuse_original_external_pin():
    x, y = training_arrays()
    model = task.fit(x, y)
    pin = task.checkpoint_sha256(model)
    forged = copy.deepcopy(model)
    forged["weights"][0] = -forged["weights"][0]
    # This is a valid parameter schema with a materially different score ordering.
    assert task.predict(forged, x[:1], np.ones(1, dtype=bool)) != task.predict(
        model, x[:1], np.ones(1, dtype=bool)
    )
    with pytest.raises(ValueError, match="external checkpoint pin differs"):
        task.restore(forged, pin)


@pytest.mark.parametrize("attack", ["mask_int", "mask_shape", "invalid_nonzero", "logit_overflow"])
def test_predict_rejects_invalid_row_masks_and_nonfinite_arithmetic(attack):
    x, y = training_arrays()
    model = task.fit(x, y)
    valid = np.ones(len(x), dtype=bool)
    if attack == "mask_int":
        valid = valid.astype(np.int8)
    elif attack == "mask_shape":
        valid = valid[:, None]
    elif attack == "invalid_nonzero":
        valid[0] = False
    else:
        model["weights"][0] = 1e308
        model["scale"][0] = 1e-308
    with pytest.raises(ValueError):
        task.predict(model, x, valid)
