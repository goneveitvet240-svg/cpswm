"""Offline, uncalibrated rendered-instance pair affinity; no runtime authority.

Features use public RGB-D and camera self-pose only. Mask-derived targets enter
only the train-partition fit. Scores imply neither transitivity, a complete
mask, target selection, cross-view identity, nor an observation likelihood.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from typing import Any, cast

import numpy as np

from cpswm.perception_mapping.unity_rgbd import CameraSelfPose
from cpswm.system.reproducibility import canonical_json, content_sha256

FEATURES = (
    "abs_red_difference_div_255",
    "abs_green_difference_div_255",
    "abs_blue_difference_div_255",
    "abs_u_difference_div_width",
    "abs_v_difference_div_height",
    "abs_rendered_depth_difference_m",
    "abs_log_rendered_depth_difference",
    "camera_world_point_distance_m",
)
CONFIG = {
    "grid_cells_per_axis": 8,
    "solver": "damped_newton",
    "iterations": 30,
    "backtracking_steps": 40,
    "l2_weights_only": 0.01,
    "gradient_tolerance": 1e-10,
    "armijo": 1e-4,
    "constant_feature_scale": 1.0,
}
SCHEMA = "offline-instance-affinity-logistic@1"
SCOPE = "UNCALIBRATED_RENDERED_INSTANCE_PAIR_AFFINITY_ONLY"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def grid_pixels(box: Any, width: int, height: int) -> tuple[tuple[int, int], ...]:
    """8x8 uniform cells, clamped to legal pixel centres in the clipped half-open box."""
    _require(
        type(width) is int and type(height) is int and 0 < width <= 640 and 0 < height <= 640,
        "invalid image dimensions",
    )
    _require(type(box) in (tuple, list) and len(box) == 4, "invalid public box")
    _require(
        all(type(v) in (int, float) and math.isfinite(v) for v in box), "invalid box coordinate"
    )
    x0, y0, x1, y1 = box
    _require(x0 < x1 and y0 < y1, "empty or reversed public box")
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1)
    if x0 >= x1 or y0 >= y1:
        return ()
    left, top = max(0, math.ceil(x0 - 0.5)), max(0, math.ceil(y0 - 0.5))
    right, bottom = (
        min(width - 1, math.ceil(x1 - 0.5) - 1),
        min(height - 1, math.ceil(y1 - 0.5) - 1),
    )
    if left > right or top > bottom:
        return ()
    us = {min(right, max(left, math.floor(x0 + (i + 0.5) * (x1 - x0) / 8))) for i in range(8)}
    vs = {min(bottom, max(top, math.floor(y0 + (i + 0.5) * (y1 - y0) / 8))) for i in range(8)}
    return tuple(sorted(itertools.product(us, vs)))


def pixel_pairs(pixels: Any) -> np.ndarray:
    """Deduplicate pixels, sort by (u,v), and enumerate every unordered distinct pair."""
    _require(type(pixels) in (tuple, list), "pixels must be a sequence")
    for pixel in pixels:
        _require(
            type(pixel) in (tuple, list)
            and len(pixel) == 2
            and all(type(v) is int and 0 <= v < 640 for v in pixel),
            "invalid pixel coordinate",
        )
    unique = sorted({tuple(pixel) for pixel in pixels})
    _require(len(unique) <= 64, "more than the fixed grid's 64 pixels")
    return np.asarray(
        [(*a, *b) for a, b in itertools.combinations(unique, 2)], dtype=np.int64
    ).reshape(-1, 4)


def pair_features(
    rgb: np.ndarray, depth: np.ndarray, camera: CameraSelfPose, pairs: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric public features; invalid/clipped depth rows remain zero and invalid.

    The caller owns the transport receipt/payload binding: arrays alone cannot
    prove original NPY byte identity. Camera fields and geometry are revalidated.
    """
    _require(
        type(rgb) is np.ndarray and rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3,
        "RGB must be uint8 HxWx3",
    )
    _require(
        type(depth) is np.ndarray
        and depth.dtype in (np.dtype("float32"), np.dtype("float64"))
        and depth.shape == rgb.shape[:2],
        "depth must be floating HxW matching RGB",
    )
    _require(
        type(camera) is CameraSelfPose and set(vars(camera)) == set(CameraSelfPose.model_fields),
        "invalid camera object",
    )
    camera = CameraSelfPose.model_validate(dict(vars(camera)))
    _require((camera.height, camera.width) == rgb.shape[:2], "camera dimensions differ from RGB")
    _require(
        type(pairs) is np.ndarray
        and pairs.dtype.kind in "iu"
        and pairs.ndim == 2
        and pairs.shape[1] == 4,
        "pairs must be an integer Nx4 array",
    )
    _require(
        bool(np.all(pairs >= 0))
        and bool(np.all(pairs[:, (0, 2)] < camera.width))
        and bool(np.all(pairs[:, (1, 3)] < camera.height))
        and not bool(np.any(np.all(pairs[:, :2] == pairs[:, 2:], axis=1))),
        "pair pixels must be distinct and within the image",
    )
    result = np.zeros((len(pairs), 8), dtype=np.float64)
    valid = np.zeros(len(pairs), dtype=bool)
    for index, (u1, v1, u2, v2) in enumerate(pairs.tolist()):
        a, b = float(depth[v1, u1]), float(depth[v2, u2])
        if not (
            math.isfinite(a)
            and math.isfinite(b)
            and 0 < a < camera.far_plane_m - camera.near_plane_m
            and 0 < b < camera.far_plane_m - camera.near_plane_m
        ):
            continue
        color = np.abs(rgb[v1, u1].astype(np.float64) - rgb[v2, u2]) / 255.0
        result[index] = (
            *color,
            abs(u1 - u2) / camera.width,
            abs(v1 - v2) / camera.height,
            abs(a - b),
            abs(math.log(a) - math.log(b)),
            math.dist(camera.world_point(u1, v1, a), camera.world_point(u2, v2, b)),
        )
        valid[index] = True
    _require(bool(np.isfinite(result).all()), "nonfinite public geometry features")
    return result, valid


def _features(features: np.ndarray) -> np.ndarray:
    _require(
        type(features) is np.ndarray
        and features.dtype in (np.dtype("float32"), np.dtype("float64"))
        and features.ndim == 2
        and features.shape[1] == 8
        and bool(np.isfinite(features).all())
        and bool(np.all(features >= 0))
        and bool(np.all(features[:, :5] <= 1)),
        "features must be finite nonnegative Nx8 floats with normalized first five columns",
    )
    return features.astype(np.float64, copy=False)


def _array_sha256(array: np.ndarray) -> str:
    return content_sha256(
        {
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "bytes_sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest(),
        }
    )


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    return cast(np.ndarray, np.exp(-np.logaddexp(0.0, -logits)))


def fit(features: np.ndarray, targets: np.ndarray, *, partition: str = "train") -> dict[str, Any]:
    """Fit only train rows labeled 0/1; VOID=-1 enters neither scaling nor optimization."""
    _require(
        type(partition) is str and partition == "train", "fit accepts only the train partition"
    )
    x = _features(features)
    _require(
        type(targets) is np.ndarray
        and targets.dtype == np.int8
        and targets.shape == (len(x),)
        and bool(np.isin(targets, (-1, 0, 1)).all()),
        "targets must be int8 {-1 VOID,0,1} matching features",
    )
    keep = targets != -1
    y = targets[keep].astype(np.float64)
    counts = [int(np.count_nonzero(y == value)) for value in (0, 1)]
    _require(all(counts), "training needs both non-VOID classes")
    selected = x[keep]
    maximum = np.maximum(selected.max(axis=0), 1.0)
    normalized = selected / maximum
    mean = normalized.mean(axis=0) * maximum
    scale = normalized.std(axis=0) * maximum
    constant = selected.min(axis=0) == selected.max(axis=0)
    mean[constant] = selected[0, constant]
    scale[constant] = 1.0
    scale[scale == 0] = 1.0
    z = np.column_stack(((selected - mean) / scale, np.ones(len(y))))
    _require(bool(np.isfinite(z).all()), "nonfinite standardized training features")
    prevalence = counts[1] / len(y)
    theta = np.zeros(9, dtype=np.float64)
    theta[-1] = math.log(prevalence / (1 - prevalence))
    penalty = np.diag([0.01] * 8 + [0.0])

    def loss(value: np.ndarray) -> float:
        logits = z @ value
        return float(
            np.mean(np.logaddexp(0.0, logits) - y * logits) + 0.005 * (value[:8] @ value[:8])
        )

    losses = [loss(theta)]
    for _ in range(30):
        probability = _sigmoid(z @ theta)
        gradient = z.T @ (probability - y) / len(y) + penalty @ theta
        if float(np.max(np.abs(gradient))) <= 1e-10:
            losses.append(losses[-1])
            continue
        curvature = probability * (1.0 - probability)
        hessian = (z.T * curvature) @ z / len(y) + penalty
        direction = np.linalg.solve(hessian, gradient)
        _require(bool(np.isfinite(direction).all()), "nonfinite Newton step")
        decrease = float(gradient @ direction)
        for backtrack in range(40):
            step = 0.5**backtrack
            candidate = theta - step * direction
            objective = loss(candidate)
            if math.isfinite(objective) and objective <= losses[-1] - 1e-4 * step * decrease:
                theta = candidate
                losses.append(objective)
                break
        else:
            raise ValueError("logistic line search failed")
    model = dict(
        schema=SCHEMA,
        scope=SCOPE,
        runtime_authority=False,
        calibrated=False,
        training_partition="train",
        features=list(FEATURES),
        config=dict(CONFIG),
        training_features_sha256=_array_sha256(features),
        training_targets_sha256=_array_sha256(targets),
        rows_total=len(x),
        rows_fit=len(y),
        rows_void=int(np.count_nonzero(~keep)),
        class_counts=counts,
        mean=mean.tolist(),
        scale=scale.tolist(),
        weights=theta[:8].tolist(),
        bias=float(theta[-1]),
        prevalence=prevalence,
        optimization_loss=losses,
    )
    _validate_model(model)
    return model


def _validate_model(model: Any) -> None:
    keys = {
        "schema",
        "scope",
        "runtime_authority",
        "calibrated",
        "training_partition",
        "features",
        "config",
        "training_features_sha256",
        "training_targets_sha256",
        "rows_total",
        "rows_fit",
        "rows_void",
        "class_counts",
        "mean",
        "scale",
        "weights",
        "bias",
        "prevalence",
        "optimization_loss",
    }
    _require(type(model) is dict and set(model) == keys, "invalid checkpoint fields")
    _require(
        type(model["schema"]) is str
        and model["schema"] == SCHEMA
        and type(model["scope"]) is str
        and model["scope"] == SCOPE
        and model["runtime_authority"] is False
        and model["calibrated"] is False
        and type(model["training_partition"]) is str
        and model["training_partition"] == "train"
        and type(model["features"]) is list
        and all(type(v) is str for v in model["features"])
        and model["features"] == list(FEATURES)
        and type(model["config"]) is dict
        and set(model["config"]) == set(CONFIG)
        and all(type(model["config"][key]) is type(value) for key, value in CONFIG.items())
        and content_sha256(model["config"]) == content_sha256(CONFIG),
        "checkpoint definition, fixed config or authority differs",
    )
    for field in ("training_features_sha256", "training_targets_sha256"):
        _require(
            type(model[field]) is str and re.fullmatch("[0-9a-f]{64}", model[field]) is not None,
            "invalid training content digest",
        )
    for field in ("rows_total", "rows_fit", "rows_void"):
        _require(type(model[field]) is int and model[field] >= 0, "invalid training row count")
    counts = model["class_counts"]
    _require(
        type(counts) is list and len(counts) == 2 and all(type(n) is int and n > 0 for n in counts),
        "invalid class counts",
    )
    _require(
        sum(counts) == model["rows_fit"]
        and model["rows_total"] == model["rows_fit"] + model["rows_void"],
        "training row counts disagree",
    )
    for field in ("mean", "scale", "weights"):
        value = model[field]
        _require(
            type(value) is list
            and len(value) == 8
            and all(type(v) is float and math.isfinite(v) for v in value),
            "invalid checkpoint parameter vector",
        )
    _require(
        all(v >= 0 for v in model["mean"])
        and all(v <= 1 for v in model["mean"][:5])
        and all(v > 0 for v in model["scale"]),
        "invalid feature scaling",
    )
    _require(
        type(model["bias"]) is float
        and math.isfinite(model["bias"])
        and type(model["prevalence"]) is float
        and math.isfinite(model["prevalence"])
        and model["prevalence"] == counts[1] / sum(counts),
        "invalid bias or prevalence",
    )
    losses = model["optimization_loss"]
    _require(
        type(losses) is list
        and len(losses) == 31
        and all(type(v) is float and math.isfinite(v) and v >= 0 for v in losses)
        and all(b <= a for a, b in itertools.pairwise(losses)),
        "invalid optimization record",
    )


def checkpoint_sha256(model: dict[str, Any]) -> str:
    _validate_model(model)
    return content_sha256(model)


def restore(model: dict[str, Any], externalpin: str) -> dict[str, Any]:
    """Validate a JSON checkpoint against the caller's independently retained content pin."""
    _require(
        type(externalpin) is str and re.fullmatch("[0-9a-f]{64}", externalpin) is not None,
        "invalid external checkpoint pin",
    )
    _require(checkpoint_sha256(model) == externalpin, "external checkpoint pin differs")
    return cast(dict[str, Any], json.loads(canonical_json(model)))


def predict(model: dict[str, Any], features: np.ndarray, valid: np.ndarray) -> list[float | None]:
    """Uncalibrated scores for every valid pair; invalid zero placeholders yield None."""
    _validate_model(model)
    x = _features(features)
    _require(
        type(valid) is np.ndarray and valid.dtype == np.bool_ and valid.shape == (len(x),),
        "valid must be a boolean row mask",
    )
    _require(bool(np.all(x[~valid] == 0)), "invalid feature rows must be zero placeholders")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        z = (x[valid] - np.asarray(model["mean"])) / np.asarray(model["scale"])
        logits = z @ np.asarray(model["weights"]) + model["bias"]
    _require(bool(np.isfinite(logits).all()), "nonfinite prediction logits")
    scores = iter(_sigmoid(logits).tolist())
    return [next(scores) if use else None for use in valid]
