"""Public seed-conditioned surface representatives, never object centres.

The input contains no masks, SDK instances, partitions or target positions.
Transport ownership is checked by the caller; all numerical support is rebuilt
from pixels and the externally pinned affinity checkpoint, never supplied scores.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import UTC
from typing import Any
from uuid import UUID

import numpy as np

from cpswm.data_preflight.instance_affinity import (
    _array_sha256,
    grid_pixels,
    pair_features,
    pixel_pairs,
    predict,
    restore,
)
from cpswm.perception_mapping.unity_rgbd import CameraSelfPose
from cpswm.system.reproducibility import content_sha256

SCHEMA = "public-soft-surface-position@1"
DOMAIN = "unity-rgbd-world-m-fixed-grid@1"
ESTIMATORS = ("soft_affinity", "uniform")
FIXED_AFFINITY_PIN = "492ae03792fef90f6a1428b80a68da27818df1e595b42f2290ac874079458d22"
# A deployment resource guard, not sample selection: exceeding it rejects the frame.
MAX_CANDIDATES = 1024
MAX_PAIR_OCCURRENCES = MAX_CANDIDATES * 2016
DEFINITION = {
    "grid": "8x8-half-open-pixel-centres",
    "seed_selection": "every-grid-pixel-including-invalid",
    "neighborhood": "complete-canonical-grid-including-invalid",
    "self_coefficient": 1.0,
    "invalid_neighbor_coefficient": 0.0,
    "invalid_seed": "unavailable-no-readout",
    "normalization": "sum-valid-neighbor-coefficients",
    "deduplication": "same-action-complete-grid-and-seed",
    "depth": "Linear01Depth_times_far_minus_near",
    "output": "world-surface-representative-not-object-centre",
    "max_candidates": MAX_CANDIDATES,
    "max_pair_occurrences": MAX_PAIR_OCCURRENCES,
}


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _uuid(value: object) -> bool:
    try:
        return type(value) is str and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def readout_frame(
    rgb: np.ndarray,
    depth: np.ndarray,
    camera: CameraSelfPose,
    candidates: list[dict[str, Any]],
    model: dict[str, Any],
    externalpin: str,
    *,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Return complete JSON support and two observations for every unique seed.

    ``candidates`` contains only method/id/box. ``provenance`` contains source,
    receipt and original payload/observation identities, supplied by an owner.
    It is not an authority assertion: the dataset/owner must bind actual bytes.
    Empty candidates/grids remain represented; unusable seeds are not dropped.
    """
    # Empty pairs deliberately exercise the same sensor/camera validation as nonempty frames.
    pair_features(rgb, depth, camera, np.empty((0, 4), dtype=np.int64))
    camera = CameraSelfPose.model_validate(dict(vars(camera)))
    checkpoint = restore(model, externalpin)
    _require(
        type(provenance) is dict
        and set(provenance)
        == {"source_sha256", "receipt_sha256", "observation_ids", "payload_sha256"}
        and _digest(provenance["source_sha256"])
        and _digest(provenance["receipt_sha256"])
        and type(provenance["observation_ids"]) is list
        and len(provenance["observation_ids"]) == 3
        and all(_uuid(v) for v in provenance["observation_ids"])
        and len(set(provenance["observation_ids"])) == 3
        and type(provenance["payload_sha256"]) is list
        and len(provenance["payload_sha256"]) == 3
        and all(_digest(v) for v in provenance["payload_sha256"]),
        "invalid public capture provenance",
    )
    _require(
        provenance["payload_sha256"][:2] == [camera.rgb_sha256, camera.depth_sha256],
        "camera and provenance RGB-D identities differ",
    )
    _require(
        type(candidates) is list and len(candidates) <= MAX_CANDIDATES,
        "candidate resource limit or type differs",
    )
    source_keys: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    grids: dict[tuple[tuple[int, int], ...], list[dict[str, Any]]] = {}
    all_pairs: set[tuple[int, int, int, int]] = set()
    pair_occurrences = 0
    for candidate in candidates:
        _require(
            type(candidate) is dict
            and set(candidate) == {"method", "id", "box"}
            and type(candidate["method"]) is str
            and 0 < len(candidate["method"]) <= 128
            and _uuid(candidate["id"]),
            "invalid public candidate source",
        )
        source_key = candidate["method"], candidate["id"]
        _require(source_key not in source_keys, "duplicate candidate source identity")
        source_keys.add(source_key)
        grid = grid_pixels(candidate["box"], camera.width, camera.height)
        pairs = pixel_pairs(grid)
        pair_occurrences += len(pairs)
        _require(pair_occurrences <= MAX_PAIR_OCCURRENCES, "pair resource limit exceeded")
        all_pairs.update(map(tuple, pairs.tolist()))
        source = copy.deepcopy(candidate)
        source["box"] = list(source["box"])
        grids.setdefault(grid, []).append(source)
        rows.append({**source, "grid_pixels_uv": [list(point) for point in grid]})
    rows.sort(key=lambda row: (row["method"], row["id"]))
    for sources in grids.values():
        sources.sort(key=lambda row: (row["method"], row["id"]))
    pairs = np.asarray(sorted(all_pairs), dtype=np.int64).reshape(-1, 4)
    features, valid = pair_features(rgb, depth, camera, pairs)
    scores = predict(checkpoint, features, valid)
    score_lookup = dict(zip(map(tuple, pairs.tolist()), scores, strict=True))
    input_binding = dict(
        camera=camera.model_dump(mode="json"),
        rgb_array_sha256=_array_sha256(rgb),
        depth_array_sha256=_array_sha256(depth),
        provenance=copy.deepcopy(provenance),
        candidates=rows,
    )
    input_sha = content_sha256(input_binding)
    estimator_pins = {
        estimator: content_sha256(
            dict(
                schema=SCHEMA,
                estimator=estimator,
                definition=DEFINITION,
                affinity_pin=externalpin if estimator == "soft_affinity" else None,
            )
        )
        for estimator in ESTIMATORS
    }
    neighborhoods, seeds, observations = [], [], []
    for grid, sources in sorted(grids.items()):
        neighborhood_id = content_sha256(dict(input_sha256=input_sha, pixels=grid))
        points, depths, point_valid = [], [], []
        for u, v in grid:
            d = float(depth[v, u])
            use = math.isfinite(d) and 0 < d < camera.far_plane_m - camera.near_plane_m
            point_valid.append(use)
            depths.append(d if math.isfinite(d) else None)
            points.append(list(camera.world_point(u, v, d)) if use else None)
        neighborhoods.append(
            dict(
                neighborhood_id=neighborhood_id,
                pixels_uv=[list(p) for p in grid],
                rgb_values=[rgb[v, u].tolist() for u, v in grid],
                rendered_depth_m=depths,
                valid=point_valid,
                world_points_m=points,
                sources=copy.deepcopy(sources),
            )
        )
        for index, seed in enumerate(grid):
            seed_id = content_sha256(dict(neighborhood_id=neighborhood_id, seed_uv=seed))
            coefficients: dict[str, dict[str, list[float] | float | None]] = {}
            representatives: dict[str, list[float] | None] = {}
            for estimator in ESTIMATORS:
                if not point_valid[index]:
                    coefficients[estimator] = dict(raw=None, normalized=None, total=None)
                    representatives[estimator] = None
                    continue
                weights = []
                for other, use in zip(grid, point_valid, strict=True):
                    if not use:
                        weight = 0.0
                    elif other == seed or estimator == "uniform":
                        weight = 1.0
                    else:
                        left, right = sorted((seed, other))
                        coefficient = score_lookup[(*left, *right)]
                        if (
                            type(coefficient) is not float
                            or not math.isfinite(coefficient)
                            or not 0 <= coefficient <= 1
                        ):
                            raise ValueError("invalid recomputed affinity coefficient")
                        weight = coefficient
                    weights.append(weight)
                total = math.fsum(weights)
                _require(math.isfinite(total) and total >= 1.0, "invalid coefficient sum")
                normalized = [weight / total for weight in weights]
                representative = [
                    math.fsum(
                        w * point[axis]
                        for w, point in zip(normalized, points, strict=True)
                        if point is not None
                    )
                    for axis in range(3)
                ]
                _require(all(math.isfinite(x) for x in representative), "nonfinite readout")
                coefficients[estimator] = dict(raw=weights, normalized=normalized, total=total)
                representatives[estimator] = representative
            seeds.append(
                dict(
                    seed_id=seed_id,
                    measurement_id=seed_id,
                    neighborhood_id=neighborhood_id,
                    pixel_uv=list(seed),
                    valid=point_valid[index],
                    reason=None if point_valid[index] else "invalid_depth",
                    coefficients=coefficients,
                    sources=copy.deepcopy(sources),
                )
            )
            for estimator in ESTIMATORS:
                observations.append(
                    dict(
                        measurement_id=seed_id,
                        seed_id=seed_id,
                        estimator=estimator,
                        estimator_pin=estimator_pins[estimator],
                        domain_id=DOMAIN,
                        frame_id=camera.world_frame,
                        action_id=str(camera.action_id),
                        valid_at=camera.capture_time.astimezone(UTC).isoformat(),
                        world_point_m=representatives[estimator],
                        available=point_valid[index],
                        reason=None if point_valid[index] else "invalid_depth",
                    )
                )
    return dict(
        schema=SCHEMA,
        affinity_pin=externalpin,
        input_sha256=input_sha,
        provenance=input_binding,
        definition=copy.deepcopy(DEFINITION),
        estimator_pins=estimator_pins,
        candidates=rows,
        neighborhoods=neighborhoods,
        pairs=pairs.tolist(),
        pair_valid=valid.tolist(),
        pair_scores=scores,
        pair_features_sha256=_array_sha256(features),
        seeds=seeds,
        observations=observations,
        instance_labels_used=False,
        formal_position_reference_selected=False,
        observation_likelihood_written=False,
    )
