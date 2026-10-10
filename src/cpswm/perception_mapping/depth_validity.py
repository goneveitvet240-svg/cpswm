"""Conservative mask/depth separation using public pixels only.

A background-continuous depth is not object surface evidence, including for
transparent objects and flat/flush objects. This guard detects one failure
mode; passing it does not prove opacity, identity or calibrated geometry.
"""

from __future__ import annotations

import numpy as np

PROFILE = "public-mask-background-continuity@1"
RING_RADIUS = 5
DEPTH_TOLERANCE_M = 0.0005
MIN_RING_POINTS = 24
MIN_PLANE_FRACTION = 0.25
RANSAC_TRIALS = 96


def background_continuity(depth: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, dict]:
    """Fit surrounding inverse-depth planes and mark indistinguishable pixels.

    The ring contains no predicted object pixels. Fixed deterministic RANSAC
    handles multiple background planes; no category, SDK masks or material IDs
    enter the calculation. Threshold is a development numerical tolerance.
    """
    h, w = depth.shape
    radius = RING_RADIUS
    padded = np.pad(mask, radius)
    dilated = np.logical_or.reduce(
        [padded[y : y + h, x : x + w] for y in range(2 * radius + 1) for x in range(2 * radius + 1)]
    )
    valid = np.isfinite(depth) & (depth > 0)
    ring = dilated & ~mask & valid
    yy, xx = np.nonzero(ring)
    flagged = np.zeros_like(mask)
    detail = dict(
        profile=PROFILE,
        ring_pixels=len(xx),
        plane_support=[],
        depth_tolerance_m=DEPTH_TOLERANCE_M,
        background_continuous_pixels=0,
        scope="DEVELOPMENT_AMBIGUITY_GUARD_NOT_OBJECT_DEPTH_CERTIFICATE",
    )
    if len(xx) < MIN_RING_POINTS:
        detail["status"] = "INSUFFICIENT_SURROUND_SUPPORT"
        return flagged, detail
    # Normalized pixels improve conditioning. 1/z is affine on a 3D plane.
    matrix = np.column_stack((xx / w, yy / h, np.ones(len(xx))))
    values = depth[yy, xx].astype(float)
    vv, uu = np.nonzero(mask & valid)
    inside = np.column_stack((uu / w, vv / h, np.ones(len(uu))))
    remaining = np.arange(len(xx))
    rng = np.random.default_rng(0)
    # At most three surrounding surfaces; the minimum support is relative to
    # the original ring, so isolated/small accidental fits cannot qualify.
    minimum = max(MIN_RING_POINTS, int(np.ceil(len(xx) * MIN_PLANE_FRACTION)))
    for _ in range(3):
        if len(remaining) < minimum:
            break
        best = np.zeros(len(remaining), dtype=bool)
        for _ in range(RANSAC_TRIALS):
            sample = rng.choice(remaining, 3, replace=False)
            a = matrix[sample]
            if abs(np.linalg.det(a)) < 1e-9:
                continue
            coef = np.linalg.solve(a, 1.0 / values[sample])
            inverse = matrix[remaining] @ coef
            predicted = np.divide(
                1.0, inverse, out=np.full_like(inverse, np.inf), where=inverse > 0
            )
            match = np.abs(predicted - values[remaining]) <= DEPTH_TOLERANCE_M
            if match.sum() > best.sum():
                best = match
        if best.sum() < minimum:
            break
        support = remaining[best]
        coef = np.linalg.lstsq(matrix[support], 1.0 / values[support], rcond=None)[0]
        inverse = inside @ coef
        predicted = np.divide(1.0, inverse, out=np.full_like(inverse, np.inf), where=inverse > 0)
        matches = np.abs(predicted - depth[vv, uu]) <= DEPTH_TOLERANCE_M
        flagged[vv[matches], uu[matches]] = True
        detail["plane_support"].append(len(support))
        remaining = remaining[~best]
    detail["background_continuous_pixels"] = int(flagged.sum())
    detail["status"] = (
        "SURROUND_PLANES_EVALUATED" if detail["plane_support"] else "NO_SUPPORTED_SURROUND_PLANE"
    )
    return flagged, detail
