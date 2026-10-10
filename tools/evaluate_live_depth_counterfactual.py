"""Public-only inference first, then evaluator-only simulator intervention scoring."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from run_matched_transition_death_test import digest, load, save

from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector
from cpswm.perception_mapping.unity_rgbd import (
    PROFILE,
    decode_unity_rgbd,
    observations_from_response,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.surface_episode import report_from_surface_state


def run(directory, output, weights):
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    files = {
        str(p.relative_to(root)): digest(p)
        for p in [
            *(root / "src").rglob("*.py"),
            Path(__file__),
            Path(__file__).with_name("unity_depth_counterfactual_capture.py"),
        ]
    }
    capture = load(directory / "capture.json")
    scope = tuple(uuid4() for _ in range(3))
    detector = NaturalMaskSurfaceDetector(
        weights_path=weights, household_id=scope[0], session_id=scope[1], trace_id=scope[2]
    )
    sequence = MaskSurfaceSequence(detector)
    records, action_ids, results = [], [], []
    provenance = dict(
        worker=digest(Path(__file__).with_name("unity_depth_counterfactual_capture.py")),
        unity=capture["binary_sha256"],
        house=capture["house_sha256"],
        capture_configuration=content_sha256((PROFILE, 320, 320, 60.0, 0.1, 20.0, False)),
    )
    for frame in capture["frames"]:
        label = frame["label"]
        public = load(directory / label / "public.json")
        assert digest(directory / label / "public.json") == frame["public_sha256"]
        arrival = datetime.fromisoformat(public["capture_time"]) + timedelta(seconds=1)
        rows = observations_from_response(
            public,
            action_id=UUID(public["action_id"]),
            scope=scope,
            arrival=arrival,
            provenance=provenance,
        )
        record, masks = sequence.observe(rows, cutoff=arrival)
        records.append(record)
        action_ids.append(public["action_id"])
        state = dict(
            view_sha256=content_sha256(record), records=records, history={}, action_ids=action_ids
        )
        reports = [
            report_from_surface_state(
                state, category=category, ordinal=ordinal, reference_action=action_ids[0]
            )
            for category, ordinal in [("bottle", 0), ("bottle", 1), ("bowl", 0)]
        ]
        save(output / (label + "-public-inference.json"), dict(record=record, reports=reports))
        results.append(
            dict(
                label=label,
                action_id=public["action_id"],
                reports=reports,
                active_candidates=record["detector"]["active_candidate_count"],
            )
        )
        print(label, [(r["status"], r.get("world_point_m")) for r in reports], flush=True)
    # No evaluator metadata/instance pixels have been read before this point.
    targets = ("Bowl|surface|2|11", "WineBottle|surface|2|8", "SoapBottle|surface|2|14")
    baseline = load(directory / "baseline" / "evaluator.json")
    masks = np.load(directory / "baseline" / "evaluator-masks.npz")
    # Score each retained report against instance masks only after inference.
    expected = (targets[1], targets[2], targets[0])
    membership = []
    for frame in results:
        frame_masks = np.load(directory / frame["label"] / "evaluator-masks.npz")
        for target, report in zip(expected, frame["reports"], strict=True):
            pixel, point = report.get("selected_pixel_uv"), report.get("world_point_m")
            actual = (
                []
                if pixel is None
                else [key for key in frame_masks.files if frame_masks[key][pixel[1], pixel[0]]]
            )
            obj = next(o for o in baseline["objects"] if o["objectId"] == target)
            box = obj["axisAlignedBoundingBox"]
            centre = np.array([box["center"][k] for k in ("x", "y", "z")])
            extent = np.array([box["size"][k] for k in ("x", "y", "z")]) / 2
            inside = point is not None and bool(np.all(np.abs(np.array(point) - centre) <= extent))
            membership.append(
                dict(
                    label=frame["label"],
                    expected=target,
                    actual=actual,
                    status=report["status"],
                    identity_correct=actual == [target],
                    inside_original_aabb=inside,
                    joint_correct=actual == [target] and inside,
                )
            )
    effects = []
    for index, target in enumerate(targets):
        label = f"removed-{index}"
        after = np.load(directory / label / "depth.npy")
        after_rgb = np.load(directory / label / "rgb.npy")
        before_label = "baseline" if index == 0 else f"removed-{index - 1}"
        before = np.load(directory / before_label / "depth.npy")
        before_rgb = np.load(directory / before_label / "rgb.npy")
        mask = masks[target]
        difference = np.abs(after - before)[mask]
        actual = next(o for o in baseline["objects"] if o["objectId"] == target)
        effects.append(
            dict(
                target=target,
                asset=actual.get("assetId"),
                materials=actual.get("salientMaterials"),
                pixels=int(mask.sum()),
                depth_changed_gt_0_5mm=int((difference > 0.0005).sum()),
                depth_unchanged_fraction=float((difference <= 0.0005).mean()),
                median_depth_change_m=float(np.median(difference)),
                rgb_changed_pixels=int(np.any(before_rgb != after_rgb, axis=2)[mask].sum()),
            )
        )
    # The selected archived glass pixel is fixed before this new capture.
    public = load(directory / "baseline" / "public.json")
    arrival = datetime.fromisoformat(public["capture_time"]) + timedelta(seconds=1)
    rows = observations_from_response(
        public,
        action_id=UUID(public["action_id"]),
        scope=scope,
        arrival=arrival,
        provenance=provenance,
    )
    camera, depth = decode_unity_rgbd(rows, cutoff=arrival)
    rays = []
    for ray in load(directory / "evaluator-rays.json"):
        u, v = ray["pixel"]
        point = camera.world_point(u, v, float(depth[v, u]))
        world = tuple(ray["world"][k] for k in ("x", "y", "z"))
        rays.append(
            dict(
                pixel=[u, v],
                depth_world=point,
                raycast_world=world,
                error_m=float(np.linalg.norm(np.array(point) - world)),
            )
        )
    assert all(digest(root / name) == value for name, value in files.items())
    save(
        output / "evaluation.json",
        dict(
            source_files=files,
            source_unchanged=True,
            capture_sha256=digest(directory / "capture.json"),
            public_results=results,
            intervention_effects=effects,
            membership=membership,
            rays=rays,
            semantic_feedback_status="BLOCKED_NO_NATURAL_INSTANCE_ROLE_TRANSITION_BRIDGE",
            scope="REAL_SIMULATOR_RENDER_AND_CAMERA_RECEIPTS;_EXOGENOUS_REMOVAL;NO_PHYSICAL_ROBOT_MANIPULATION;NO_GLOBAL_ABSENCE_OR_PERSON_INFERENCE",
            inference_opened_truth_after_all_frames=True,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "output", "weights"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.directory, a.output, a.weights)
