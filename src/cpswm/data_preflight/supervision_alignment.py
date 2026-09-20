"""Evaluator-only structural checks; alignment hypotheses never authorize labels."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

import numpy as np
from numpy.typing import NDArray


def timestamp_audit(timestamps_ns: tuple[int, ...], frame_count: int) -> dict[str, Any]:
    if (
        type(frame_count) is not int
        or frame_count <= 0
        or len(timestamps_ns) != frame_count
        or any(type(t) is not int or t < 0 for t in timestamps_ns)
        or any(b <= a for a, b in pairwise(timestamps_ns))
    ):
        raise ValueError("one strictly increasing integer timestamp per decoded frame required")
    # Subtract integer epoch timestamps BEFORE conversion to float.
    intervals = [(b - a) / 1e9 for a, b in pairwise(timestamps_ns)]
    return {
        "frame_count": frame_count,
        "relative_seconds": [(t - timestamps_ns[0]) / 1e9 for t in timestamps_ns],
        "interval_min_seconds": min(intervals) if intervals else None,
        "interval_max_seconds": max(intervals) if intervals else None,
        "timestamp_unit_interpretation": "nanoseconds by data convention; clock not calibrated",
        "cross_stream_alignment_verified": False,
    }


def pose_audit(poses: NDArray[Any], *, tolerance: float = 1e-5) -> dict[str, Any]:
    """Report rigid-transform defects; never silently project/repair author data."""
    if (
        poses.ndim != 3
        or poses.shape[1:] != (4, 4)
        or len(poses) == 0
        or not np.issubdtype(poses.dtype, np.floating)
        or not math.isfinite(tolerance)
        or not 0 < tolerance <= 1e-3
    ):
        raise ValueError("floating 4x4 transforms and bounded numerical tolerance required")
    rows: list[dict[str, Any]] = []
    for i, p in enumerate(poses):
        if not np.isfinite(p).all():
            rows.append({"row": i, "finite": False, "rigid": False})
            continue
        rotation = p[:3, :3]
        determinant = float(np.linalg.det(rotation))
        residual = float(np.max(np.abs(rotation.T @ rotation - np.eye(3))))
        bottom = float(np.max(np.abs(p[3] - [0, 0, 0, 1])))
        rows.append(
            {
                "row": i,
                "finite": True,
                "determinant": determinant,
                "orthogonality_max_error": residual,
                "homogeneous_row_max_error": bottom,
                "rigid": abs(determinant - 1) <= tolerance
                and residual <= tolerance
                and bottom <= tolerance,
            }
        )
    return {
        "numerical_tolerance": tolerance,
        "rows": rows,
        "invalid_rows": [r["row"] for r in rows if not r["rigid"]],
        "calibrated_pose_error": False,
        "repaired": False,
    }


def alignment_inventory(
    masks: NDArray[Any], aligned: NDArray[Any], *, video_frames: int, pose_rows: int
) -> dict[str, Any]:
    if (
        masks.ndim != 3
        or masks.dtype != np.uint8
        or 0 in masks.shape
        or aligned.ndim != 2
        or 0 in aligned.shape
        or not np.issubdtype(aligned.dtype, np.integer)
        or np.any(aligned < 0)
        or type(video_frames) is not int
        or video_frames <= 0
        or type(pose_rows) is not int
        or pose_rows <= 0
    ):
        raise ValueError(
            "uint8 masks, nonnegative integer index table and positive counts required"
        )
    values = [int(v) for v in np.unique(masks)]
    presence = {
        str(v): [int(i) for i in np.flatnonzero(np.any(masks == v, axis=(1, 2)))] for v in values
    }
    hypotheses = {
        "mask_row_equals_video_frame": list(range(len(masks))),
        "three_times_mask_row": [3 * i for i in range(len(masks))],
    }
    # Merely a candidate mapping: published column semantics are unverified.
    if len(aligned[::3]) == len(masks):
        hypotheses["every_third_table_row_first_column"] = aligned[::3, 0].tolist()
    return {
        "status": "UNVERIFIED_ALIGNMENT",
        "usable_for_role_or_contact_calibration": False,
        "accepted_frame_links": [],
        "mask_shape": list(masks.shape),
        "mask_values": values,
        "value_identity_mapping": "UNKNOWN",
        "value_present_rows": presence,
        "absent_value_means_absent_object": False,
        "aligned_shape": list(aligned.shape),
        "pose_rows": pose_rows,
        "video_frames": video_frames,
        "aligned_rows_equal_pose_rows": len(aligned) == pose_rows,
        "current_author_generator_columns": 7,
        "published_table_matches_current_generator_width": aligned.shape[1] == 7,
        "hypotheses": {
            name: {
                "frame_indices": ids,
                "all_in_range": all(0 <= i < video_frames for i in ids),
                "accepted": False,
            }
            for name, ids in hypotheses.items()
        },
    }


def boundary_support(rgb: NDArray[Any], masks: NDArray[Any]) -> NDArray[np.float64]:
    """Exploratory edge support for EVERY RGB/mask pairing, not an accuracy metric.

    Inputs are already resized with nearest-neighbor mask sampling. Equal weighting
    of present nonzero regions avoids the largest body dominating other regions.
    Strong background edges can win: scores never certify alignment or identity.
    """
    from scipy.ndimage import binary_erosion, sobel  # type: ignore[import-untyped]

    if (
        rgb.ndim != 4
        or rgb.shape[-1] != 3
        or rgb.dtype != np.uint8
        or masks.ndim != 3
        or masks.dtype != np.uint8
        or rgb.shape[1:3] != masks.shape[1:]
        or len(rgb) == 0
        or len(masks) == 0
        or min(masks.shape[1:]) < 3
    ):
        raise ValueError("nonempty matching RGB/mask grids required")
    gray = rgb.astype(np.float64).mean(axis=-1) / 255
    gradients = np.hypot(sobel(gray, axis=1), sobel(gray, axis=2))
    norms = gradients.mean(axis=(1, 2), keepdims=True)
    gradients /= np.maximum(norms, 1e-12)
    scores = np.zeros((len(masks), len(rgb)), dtype=np.float64)
    for row, mask in enumerate(masks):
        regions = []
        for value in np.unique(mask):
            if value == 0:
                continue
            region = mask == value
            boundary = region & ~binary_erosion(region)
            if boundary.any():
                regions.append(gradients[:, boundary].mean(axis=1))
        if regions:
            scores[row] = np.mean(regions, axis=0)
    return scores
