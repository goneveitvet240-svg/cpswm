"""Python 3.11/Open3D worker. Accepts only finite point arrays, no scene truth."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import open3d as o3d
from conceptgraph_denoise import pcd_denoise_dbscan


def run(source: Path, destination: Path) -> None:
    points = np.load(source, allow_pickle=False)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or len(points) > 640 * 640
        or points.dtype != np.float64
        or not np.isfinite(points).all()
    ):
        raise ValueError("bounded finite float64 Nx3 point array required")
    if destination.exists():
        raise ValueError("output must be new")
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)
    cloud.colors = o3d.utility.Vector3dVector(np.zeros_like(points))
    start = time.perf_counter()
    result = pcd_denoise_dbscan(cloud, eps=0.05, min_points=10)
    np.save(destination, np.asarray(result.points), allow_pickle=False)
    destination.with_suffix(".json").write_text(
        json.dumps(dict(open3d=o3d.__version__, compute_s=time.perf_counter() - start))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    run(args.source, args.destination)
