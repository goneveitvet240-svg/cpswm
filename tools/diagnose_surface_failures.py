"""Evaluator-only decomposition of frozen surface reports. Never import in inference."""

from __future__ import annotations

import argparse
import io
import math
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from run_matched_transition_death_test import (
    _bounds,
    _instance_at,
    _mask_bytes,
    _sdk_bundle,
    checked,
    digest,
    evaluate,
    load,
    raw_rows,
    replay,
    save,
)

from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256


def project(camera, depth, *, offset=0.5, scale=True):
    """Independent matrix implementation; parity is not external geometry truth."""
    v, u = np.indices(depth.shape)
    f = camera.height / (2 * math.tan(math.radians(camera.vertical_fov_degrees) / 2))
    k = np.array([[f, 0, camera.width / 2], [0, -f, camera.height / 2], [0, 0, 1]])
    rays = np.stack([u + offset, v + offset, np.ones_like(u)], -1) @ np.linalg.inv(k).T
    p, y = map(math.radians, (camera.pitch_degrees, camera.yaw_degrees))
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    z = depth.astype(float) * (
        camera.far_plane_m / (camera.far_plane_m - camera.near_plane_m) if scale else 1
    )
    return (rays * z[..., None]) @ (ry @ rx).T + camera.position_m


def box_gap(points, lower, upper):
    return np.maximum(np.maximum(np.asarray(lower) - points, points - np.asarray(upper)), 0).max(
        axis=-1
    )


def erode(mask):
    padded = np.pad(mask, 1)
    h, w = mask.shape
    return np.logical_and.reduce([padded[y : y + h, x : x + w] for y in range(3) for x in range(3)])


def distribution(points, mask, lower, upper):
    gap = box_gap(points[mask], lower, upper)
    return {
        "pixels": int(mask.sum()),
        "inside_aabb": int((gap == 0).sum()),
        "median_outside_mm": float(np.median(gap) * 1000) if len(gap) else None,
        "max_outside_mm": float(gap.max() * 1000) if len(gap) else None,
    }


def failure_class(report, actual, target, gap):
    if report["status"] != "reported" or report["world_point_m"] is None:
        return "no_report"
    if actual != target:
        return "wrong_or_unresolved_instance"
    return "correct_instance_outside_aabb" if gap > 0 else "joint_correct"


def run(root, manifest_path, targets_path, archive, output):
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest, targets = load(manifest_path), load(targets_path)
    current = replay(
        root, manifest_path, output / "current-replay.json", arm="current", expected_sha=head
    )
    old = load(archive / "current.json")
    if content_sha256(current["steps"]) != content_sha256(old["steps"]):
        raise ValueError("fresh current replay differs from archived public steps")
    arms = {
        "current": current,
        **{name: load(archive / f"{name}.json") for name in ("iou", "hybrid")},
    }
    bindings = load(archive.parent / "files.json")["files"]
    for name in arms:
        checked(
            archive.parent,
            f"{archive.name}/{name}.json",
            bindings[f"{archive.name}/{name}.json"]["sha256"],
        )
    rows, pixels, parity = [], [], []
    for name, result in arms.items():
        if result["manifest_sha256"] != digest(manifest_path):
            raise ValueError("archived arm manifest binding differs")
        evaluate(
            root,
            manifest_path,
            output / "current-replay.json" if name == "current" else archive / f"{name}.json",
            targets_path,
            output / f"{name}-evaluation.json",
        )
    for item, fresh_step in zip(manifest["frames"], current["steps"], strict=True):
        raw = load(checked(root, item["raw"], item["raw_sha256"]))
        camera, depth = decode_unity_rgbd(
            raw_rows(raw), cutoff=datetime.fromisoformat(raw["received_at"])
        )
        points = project(camera, depth)
        variants = {
            "production_convention": points,
            "pixel_index_no_half_offset": project(camera, depth, offset=0),
            "without_shader_scale": project(camera, depth, scale=False),
        }
        valid = (depth > 0) & (depth < camera.far_plane_m - camera.near_plane_m)
        vv, uu = np.where(valid)
        scalar = np.array(
            [
                camera.world_point(int(u), int(v), float(depth[v, u]))
                for v, u in zip(vv, uu, strict=True)
            ]
        )
        parity.append(
            {
                "frame": item["index"],
                "valid_pixels": len(uu),
                "max_abs_difference_m": float(np.abs(scalar - points[valid]).max()),
            }
        )
        event, ids, masks = _sdk_bundle(root, item)
        native = np.load(
            io.BytesIO(_mask_bytes(checked(root, item["masks"], item["masks_sha256"]))),
            allow_pickle=False,
        )
        detector = fresh_step["record"]["detector"]
        for qi, target in enumerate(targets):
            lower, upper = _bounds(event, target)
            target_mask = masks[ids.index(target)] & valid
            interior = erode(target_mask)
            pixels.append(
                {
                    "frame": item["index"],
                    "target": target,
                    "all": distribution(points, target_mask, lower, upper),
                    "interior": distribution(points, interior, lower, upper),
                    "boundary": distribution(points, target_mask & ~interior, lower, upper),
                    "convention_sensitivity_evaluator_only": {
                        n: distribution(p, target_mask, lower, upper) for n, p in variants.items()
                    },
                }
            )
            for name, result in arms.items():
                step = result["steps"][item["index"]]
                report = step["reports"][qi]
                actual = _instance_at(report["selected_pixel_uv"], ids, masks)
                gap = (
                    float(box_gap(np.asarray(report["world_point_m"]), lower, upper))
                    if report["world_point_m"] is not None
                    else None
                )
                track = next(
                    (
                        t
                        for t in step["record"]["tracks"]
                        if t["anchor_id"]
                        == (report["anchor_id"] or result["steps"][0]["reports"][qi]["anchor_id"])
                    ),
                    None,
                )
                candidate = next(
                    (
                        c
                        for c in detector["candidates"]
                        if track and c["candidate_id"] == track["current_candidate_id"]
                    ),
                    None,
                )
                mixture = None
                if candidate:
                    candidate_mask = (
                        native[candidate["native_index"]].squeeze() >= detector["mask_threshold"]
                    )
                    counts = sorted(
                        [
                            (key, int((mask & candidate_mask).sum()))
                            for key, mask in zip(ids, masks, strict=True)
                        ],
                        key=lambda x: -x[1],
                    )
                    mixture = {
                        "candidate_id": candidate["candidate_id"],
                        "category": candidate["category"],
                        "mask_pixels": int(candidate_mask.sum()),
                        "target_pixels": int((target_mask & candidate_mask).sum()),
                        "top_instances": counts[:5],
                        "target_valid_aabb_pixels": int(
                            (
                                target_mask & candidate_mask & (box_gap(points, lower, upper) == 0)
                            ).sum()
                        ),
                    }
                selected_variants = None
                if report["selected_pixel_uv"] is not None:
                    u, v = report["selected_pixel_uv"]
                    selected_variants = {
                        n: float(box_gap(p[v, u], lower, upper) * 1000) for n, p in variants.items()
                    }
                rows.append(
                    {
                        "arm": name,
                        "frame": item["index"],
                        "query": manifest["queries"][qi],
                        "target": target,
                        "selected_instance": actual,
                        "selected_pixel": report["selected_pixel_uv"],
                        "outside_aabb_mm": gap * 1000 if gap is not None else None,
                        "class": failure_class(report, actual, target, gap),
                        "candidate_mixture": mixture,
                        "report_reason": report["reason"],
                        "track_status": track["status"] if track else None,
                        "surviving_flow_points": track["flow"]["surviving_points"]
                        if track and track.get("flow")
                        else None,
                        "detector_threshold": detector["minimum_detector_score"],
                        "same_category_candidates": [
                            {k: c[k] for k in ("candidate_id", "detector_score", "status")}
                            for c in detector["candidates"]
                            if c["category"] == report["category"]
                        ],
                        "selected_convention_sensitivity_mm": selected_variants,
                    }
                )
    result = {
        "schema": "surface-failure-diagnostic@1",
        "code_sha": head,
        "tool_sha256": digest(Path(__file__)),
        "manifest_sha256": digest(manifest_path),
        "targets_sha256": digest(targets_path),
        "archived_arm_sha256": {n: digest(archive / f"{n}.json") for n in arms},
        "fresh_current_steps_equal_archive": True,
        "new_physical_actions": 0,
        "formal_scores_unchanged": True,
        "inference_consumes_truth": False,
        "counts": {n: dict(Counter(r["class"] for r in rows if r["arm"] == n)) for n in arms},
        "rows": rows,
        "pixel_geometry": pixels,
        "matrix_parity": parity,
        "limits": (
            "Development panel, no new detector inference; GT pixels and convention "
            "variants evaluator-only. Matrix parity does not validate renderer, mesh, "
            "mask alignment or AABB truth."
        ),
    }
    save(output / "diagnosis.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "manifest", "targets", "archive", "output"):
        p.add_argument(f"--{arg}", type=Path, required=True)
    a = p.parse_args()
    print(run(a.root, a.manifest, a.targets, a.archive, a.output)["counts"])
