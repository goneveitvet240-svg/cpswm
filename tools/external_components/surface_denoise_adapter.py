"""Experimental readout adapter; no owner, memory, identity or action authority.

Only the pinned ConceptGraphs largest-cluster function is reused. Unity camera
geometry and the existing maximum-mask-probability readout remain CPSWM's.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from cpswm.perception_mapping.natural_mask_surface import MASK_THRESHOLD, select_surface
from cpswm.perception_mapping.unity_rgbd import CameraSelfPose

UPSTREAM_COMMIT = "93277a02bd89171f8121e84203121cf7af9ebb5d"
EPS_M = 0.05
MIN_POINTS = 10


def external_denoise(
    points: np.ndarray, component_python: Path
) -> tuple[np.ndarray, dict[str, Any]]:
    worker = Path(__file__).with_name("run_denoise.py")
    with tempfile.TemporaryDirectory(prefix="cpswm-cg-component-") as folder:
        source, output = Path(folder) / "input.npy", Path(folder) / "output.npy"
        np.save(source, points, allow_pickle=False)
        result = subprocess.run(
            [str(component_python), str(worker), str(source), str(output)],
            check=True,
            text=True,
            capture_output=True,
            timeout=120,
        )
        retained = np.load(output, allow_pickle=False)
        metadata = json.loads(output.with_suffix(".json").read_text())
        metadata.update(stdout=result.stdout, stderr=result.stderr)
    if retained.ndim != 2 or retained.shape[1] != 3 or not np.isfinite(retained).all():
        raise ValueError("malformed external point output")
    return retained, metadata


def cluster_support(
    camera: CameraSelfPose, depth: np.ndarray, probability: np.ndarray, component_python: Path
) -> tuple[tuple[tuple[int, int], ...], dict[str, Any]]:
    # Reuse the production input guard before any allocation or external call.
    select_surface(camera, depth, probability)
    valid = (
        (probability >= MASK_THRESHOLD)
        & np.isfinite(depth)
        & (depth > 0)
        & (depth < camera.far_plane_m - camera.near_plane_m)
    )
    v, u = np.nonzero(valid)
    uv = tuple((int(x), int(y)) for x, y in zip(u, v, strict=True))
    if not uv:
        return (), dict(input_points=0, retained_points=0, removed_points=0)
    points = np.asarray([camera.world_point(x, y, float(depth[y, x])) for x, y in uv])
    retained, metadata = external_denoise(points, component_python)
    # The upstream function preserves exact coordinates (no voxelization/jitter).
    kept = {tuple(row) for row in retained}
    if not kept.issubset({tuple(row) for row in points}):
        raise ValueError("external component synthesized a point")
    selected = tuple(pixel for pixel, point in zip(uv, points, strict=True) if tuple(point) in kept)
    return selected, dict(
        input_points=len(uv),
        retained_points=len(selected),
        removed_points=len(uv) - len(selected),
        worker=metadata,
    )


def filtered_readout(
    camera: CameraSelfPose,
    depth: np.ndarray,
    probability: np.ndarray,
    retained_uv: tuple[tuple[int, int], ...],
    original_support: tuple[tuple[int, int], ...] | None,
) -> dict[str, Any]:
    allowed = set(retained_uv)
    if original_support is not None:
        allowed.intersection_update(original_support)
    return select_surface(camera, depth, probability, support_uv=tuple(sorted(allowed)))
