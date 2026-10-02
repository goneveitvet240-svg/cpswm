"""Read-only surface diagnostic under the archive's original frozen inference code.

No target label enters detector, tracker, grid, affinity, or seed selection.
This is retrospective geometry scoring, not a new live capture or identity proof.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
from run_correction_replay_comparison import OracleProducer
from test_owned_rgbd_support import RGBDSupportDecoder
from test_temporal_target_position import SOURCE, association_joint

from cpswm.data_preflight.soft_surface_position import readout_frame
from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.native_joint_replay import consumed_schedule
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.temporal_target_position import PROFILE


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def run(source, output, target):
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((source / "restore.json").read_text())
    shutil.copy2(source / "copy.db", output / "copy.db")
    store = ContinuousStateStore(
        output / "copy.db", source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def forbidden(*args):
        raise AssertionError("diagnostic cannot rerun semantic P5")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=forbidden,
            joint_producer=association_joint(config),
            observation_decoder=RGBDSupportDecoder(),
        )
        before = store._db.execute("SELECT * FROM checkpoint").fetchall()
        view = stream.current_joint_decision_view()
        producer = stream._joint_producer._candidate_model
        contexts = [
            u.context
            for u in consumed_schedule(stream._system.core._particle_workspace)
            if u.context is not None and u.context.observation_update is not None
        ]
        if len(contexts) != 1:
            raise ValueError("this archived failure must contain exactly one effective capture")
        context = contexts[0]
        capture = context.observation_update
        keys = capture.packet["observation_ids"]
        lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
        rows = tuple(lookup[k] for k in keys)
        camera, depth = decode_unity_rgbd(rows, cutoff=capture.received_at)
        _, rgb = decode_rgb(rows[0], cutoff=capture.received_at)
        record = producer.last_diagnostic["sequence"]["records"][0]
        candidates = [
            dict(method=PROFILE, id=t["anchor_id"], box=list(t["box_xyxy"]))
            for t in record["tracks"]
            if t["status"] == "PIXEL_SUPPORTED"
        ]
        surface = readout_frame(
            rgb,
            depth,
            camera,
            candidates,
            producer.affinity_model,
            producer.affinity_pin,
            provenance=dict(
                source_sha256=capture.packet["raw_sha256"],
                receipt_sha256=rows[0].capture_receipt_sha256,
                observation_ids=keys,
                payload_sha256=[hashlib.sha256(r.payload_bytes).hexdigest() for r in rows],
            ),
        )
        selected = {}
        for candidate in candidates:
            seeds = [
                s
                for s in surface["seeds"]
                if s["valid"] and any(p["id"] == candidate["id"] for p in s["sources"])
            ]
            selected[candidate["id"]] = (
                min(seeds, key=lambda s: tuple(s["pixel_uv"]))["seed_id"] if seeds else None
            )
        # Public output is complete before evaluator annotation is opened.
        public = dict(surface=surface, selected=selected, posterior_sha256=view.content_sha256)
        save(output / "public.json", public)
        annotation_path = source / "transport/evaluator_only/sdk-events/004.json"
        boxes_path = source / "transport/evaluator_only/sdk-events/004-boxes.json"
        annotation = json.loads(annotation_path.read_text())
        boxes = json.loads(boxes_path.read_text())
        obj = next(o for o in annotation["metadata"]["objects"] if o["objectId"] == target)
        corners = np.asarray(obj["axisAlignedBoundingBox"]["cornerPoints"])
        lower, upper = corners.min(axis=0), corners.max(axis=0)
        box = boxes[target]

        def inside(point):
            return point is not None and bool(np.all(lower <= point) and np.all(point <= upper))

        diagnostics = []
        for n in surface["neighborhoods"]:
            seeds = [s for s in surface["seeds"] if s["neighborhood_id"] == n["neighborhood_id"]]
            pixels = []
            for uv, point in zip(n["pixels_uv"], n["world_points_m"], strict=True):
                pixels.append(
                    dict(
                        pixel=uv,
                        point_m=point,
                        in_target_2d_box=box[0] <= uv[0] < box[2] and box[1] <= uv[1] < box[3],
                        in_target_aabb=inside(point),
                    )
                )
            first = [s for s in seeds if s["seed_id"] in selected.values()]
            selected_rows = []
            for seed in first:
                point = n["world_points_m"][n["pixels_uv"].index(seed["pixel_uv"])]
                selected_rows.append(
                    dict(
                        seed_id=seed["seed_id"],
                        pixel=seed["pixel_uv"],
                        bare_point_m=point,
                        bare_in_target_aabb=inside(point),
                        estimators=[
                            dict(
                                estimator=o["estimator"],
                                point_m=o["world_point_m"],
                                in_target_aabb=inside(o["world_point_m"]),
                            )
                            for o in surface["observations"]
                            if o["seed_id"] == seed["seed_id"]
                        ],
                    )
                )
            diagnostics.append(
                dict(
                    sources=n["sources"],
                    pixel_count=len(pixels),
                    inside_2d_box=sum(p["in_target_2d_box"] for p in pixels),
                    inside_aabb=sum(p["in_target_aabb"] for p in pixels),
                    pixels=pixels,
                    selected=selected_rows,
                )
            )
        assert store._db.execute("SELECT * FROM checkpoint").fetchall() == before
        result = dict(
            scope="retrospective geometry diagnostic; no natural instance adjudication",
            target=target,
            true_mask_available=False,
            mask_note="004-mask.npy is the original Apple query mask, not this WineBottle",
            annotation_sha256=hashlib.sha256(annotation_path.read_bytes()).hexdigest(),
            boxes_sha256=hashlib.sha256(boxes_path.read_bytes()).hexdigest(),
            public_sha256=content_sha256(public),
            lower_m=lower.tolist(),
            upper_m=upper.tolist(),
            box_2d=box,
            new_actions=0,
            checkpoint_unchanged=True,
            diagnostics=diagnostics,
        )
        save(output / "result.json", result)
        print(json.dumps(result), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    run(args.source, args.output, args.target)
