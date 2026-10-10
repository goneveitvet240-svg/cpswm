"""Evaluator-only material/plane diagnosis and archived independent raycast control."""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from diagnose_surface_failures import project
from run_matched_transition_death_test import (
    _bounds,
    _sdk_bundle,
    checked,
    digest,
    load,
    raw_rows,
    save,
)
from verify_rgbd_geometry import verify

from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd


def run(panel, raycast_root, output):
    manifest = load(panel / "manifest.json")
    rows = []
    for item in manifest["frames"]:
        root = panel / "natural-30-5-5"
        raw = load(checked(root, item["raw"], item["raw_sha256"]))
        cam, depth = decode_unity_rgbd(
            raw_rows(raw), cutoff=datetime.fromisoformat(raw["received_at"])
        )
        event, ids, masks = _sdk_bundle(root, item)
        obj = next(x for x in event["metadata"]["objects"] if x["objectId"] == "Bowl|surface|2|11")
        world = project(cam, depth)
        pts = world[masks[ids.index(obj["objectId"])]]
        counter_y = world[masks[ids.index("CounterTop|2|0")]][:, 1]
        bins, counts = np.unique(counter_y.round(3), return_counts=True)
        dominant_bin = bins[np.argmax(counts)]
        rendered_counter_y = float(np.median(counter_y[counter_y.round(3) == dominant_bin]))
        _, counter_upper = _bounds(event, "CounterTop|2|0")
        rows.append(
            dict(
                frame=item["index"],
                asset_id=obj["assetId"],
                materials=obj["salientMaterials"],
                pixels=len(pts),
                countertop_top_y=counter_upper[1],
                rendered_countertop_dominant_y=rendered_counter_y,
                countertop_dominant_bin_pixels=int(counts.max()),
                bowl_pixels_in_same_1mm_y_bin=int((pts[:, 1].round(3) == dominant_bin).sum()),
                within_0_1mm_countertop_top_plane=int(
                    (abs(pts[:, 1] - counter_upper[1]) < 0.0001).sum()
                ),
                within_0_1mm_wall_x_zero=int((abs(pts[:, 0]) < 0.0001).sum()),
                scope=(
                    "plane proximity and 1mm histogram bin are diagnostic; "
                    "not surface ownership truth or relaxed AABB scoring"
                ),
            )
        )
    inventory_path = "docs/reviews/pc_a/rgbd_camera_geometry_2026-09-30/evidence/inventory.json"
    inventory_bytes = subprocess.check_output(["git", "show", f"HEAD:{inventory_path}"])
    inventory = json.loads(inventory_bytes)
    verified = {}
    for row in inventory:
        if row["path"].startswith("attempt01/geometry/"):
            relative = row["path"].removeprefix("attempt01/geometry/")
            checked(raycast_root, relative, row["sha256"])
            verified[relative] = row["sha256"]
    control = verify(raycast_root, expected=raycast_root / "evaluation.json")
    variants = {name: [] for name in ("production", "no_half_pixel", "no_depth_scale")}
    for i, event in enumerate(load(raycast_root / "evaluator_only.json")):
        camera = SimpleNamespace(**event["camera"])
        depth = np.load(raycast_root / f"{i:03d}-depth.npy", allow_pickle=False)
        points = {
            "production": project(camera, depth),
            "no_half_pixel": project(camera, depth, offset=0),
            "no_depth_scale": project(camera, depth, scale=False),
        }
        for ray in event["rays"]:
            u, v = ray["pixel"]
            truth = [ray["world"][k] for k in ("x", "y", "z")]
            for name, values in points.items():
                variants[name].append(float(np.linalg.norm(values[v, u] - truth)))
    result = dict(
        tool_sha256=digest(Path(__file__)),
        panel_manifest_sha256=digest(panel / "manifest.json"),
        material_rows=rows,
        raycast_input_sha256=verified,
        archived_raycast_recomputed_equal=True,
        raycast_control=control,
        raycast_variants={
            k: dict(median_m=float(np.median(v)), p90_m=float(np.quantile(v, 0.9)), max_m=max(v))
            for k, v in variants.items()
        },
        limitation=(
            "Archived 54 rays do not target these Bowl pixels. Glass metadata "
            "and background-plane depth support a transparency/depth-surface "
            "mismatch diagnosis, not a verified shader fix."
        ),
    )
    save(output, result)
    print(result["material_rows"])
    print(result["raycast_variants"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("panel", "raycast-root", "output"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    run(a.panel, a.raycast_root, a.output)
