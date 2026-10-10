"""Isolated CPU ConceptGraphs kernel worker; JSON files in, JSON files out.

Inputs contain RGB, public masks converted to world points, and detector metadata.
No evaluator paths, ground truth identities or boxes are consumed by this worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import conceptgraph_object_kernel as cg
import numpy as np
import open3d as o3d
import open_clip
import torch

MODEL_SHA = "9a78ef8e8c73fd0df621682e7a8e8eb36c6916cb3c16b291a082ecd52ab79cc4"


def sha(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Mapper:
    def __init__(self, weights):
        if sha(weights) != MODEL_SHA:
            raise ValueError("OpenCLIP checkpoint differs")
        torch.set_num_threads(2)
        torch.manual_seed(0)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-H-14", pretrained=str(weights), device="cpu"
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-H-14")
        self.features = {}

    def frame(self, value):
        key = (sha(value["arrays"]), json.dumps(value["candidates"], sort_keys=True))
        if key in self.features:
            return self.features[key]
        arrays = np.load(value["arrays"], allow_pickle=False)
        rows = value["candidates"]
        image_features, text_features = [], []
        # Bounded batching changes neither official crop nor normalization rules.
        for begin in range(0, len(rows), 4):
            subset = rows[begin : begin + 4]
            det = SimpleNamespace(
                xyxy=np.array([r["box_xyxy"] for r in subset]),
                class_id=np.arange(len(subset)),
            )
            _, images, texts = cg.compute_clip_features_batched(
                arrays["rgb"],
                det,
                self.model,
                self.preprocess,
                self.tokenizer,
                [r["category"] for r in subset],
                "cpu",
            )
            image_features.extend(images)
            text_features.extend(texts)
        result = (arrays, image_features, text_features)
        self.features[key] = result
        return result

    def run(self, request):
        started = time.perf_counter()
        cfg = SimpleNamespace(
            spatial_sim_type="iou",
            device="cpu",
            downsample_voxel_size=0.025,
            dbscan_remove_noise=True,
            dbscan_eps=0.05,
            dbscan_min_points=10,
            match_method="sim_sum",
            phys_bias=0.0,
            sim_threshold=1.2,
        )
        if request.get("spatial", "iou") not in ("iou", "overlap_aabb"):
            raise ValueError("unsupported spatial mode")
        objects, steps = cg.MapObjectList(), []
        for frame_index, frame in enumerate(request["frames"]):
            arrays, images, texts = self.frame(frame)
            detections, diagnostics = cg.DetectionList(), []
            for i, candidate in enumerate(frame["candidates"]):
                points = arrays[f"points_{i}"]
                cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
                cloud.colors = o3d.utility.Vector3dVector(arrays[f"colors_{i}"])
                if len(points):
                    cloud = cg.process_pcd(cloud, cfg)
                diagnostics.append(
                    dict(
                        candidate_id=candidate["candidate_id"],
                        raw_points=len(points),
                        retained_points=len(cloud.points),
                    )
                )
                if len(cloud.points) < 16:
                    continue
                detections.append(
                    dict(
                        pcd=cloud,
                        bbox=cg.get_bounding_box(cfg, cloud),
                        clip_ft=torch.tensor(images[i]),
                        text_ft=torch.tensor(texts[i]),
                        num_detections=1,
                        observations=[dict(frame=frame_index, candidate=i)],
                        candidate_ids=[candidate["candidate_id"]],
                    )
                )
            association = None
            if not objects:
                objects.extend(detections)
            elif detections:
                spatial = cg.compute_iou_batch(
                    detections.get_stacked_values_torch("bbox"),
                    objects.get_stacked_values_torch("bbox"),
                ).float()
                if request.get("spatial") == "overlap_aabb":
                    # Author overlap ratio, explicitly AABB-prefiltered (not OBB).
                    # Deterministic KDTree avoids the platform-specific FAISS dependency.
                    from scipy.spatial import cKDTree

                    overlap = torch.zeros_like(spatial)
                    for i, detection in enumerate(detections):
                        for j, obj in enumerate(objects):
                            if spatial[i, j] >= 1e-6:
                                distances, _ = cKDTree(np.asarray(obj["pcd"].points)).query(
                                    np.asarray(detection["pcd"].points), k=1
                                )
                                overlap[i, j] = float(
                                    (distances < cfg.downsample_voxel_size).mean()
                                )
                    spatial = overlap
                visual = cg.compute_visual_similarities(cfg, detections, objects)
                combined = cg.aggregate_similarities(cfg, spatial, visual)
                association = dict(
                    detection_ids=[d["candidate_ids"][0] for d in detections],
                    map_anchor_ids=[o["candidate_ids"][0] for o in objects],
                    spatial=spatial.tolist(),
                    visual=visual.tolist(),
                    combined=combined.tolist(),
                )
                combined[combined < cfg.sim_threshold] = float("-inf")
                objects = cg.merge_detections_to_objects(cfg, detections, objects, combined)
            snapshots = [
                dict(
                    anchor_id=o["candidate_ids"][0],
                    observations=o["observations"],
                    num_detections=o["num_detections"],
                    cloud_points=len(o["pcd"].points),
                    bbox_min=o["bbox"].get_min_bound().tolist(),
                    bbox_max=o["bbox"].get_max_bound().tolist(),
                    image_feature=o["clip_ft"].tolist(),
                )
                for o in objects
            ]
            # Freeze every prefix; upstream fusion mutates object lists in place.
            steps.append(
                json.loads(
                    json.dumps(
                        dict(objects=snapshots, association=association, diagnostics=diagnostics)
                    )
                )
            )
        return dict(
            steps=steps,
            model_sha256=MODEL_SHA,
            elapsed_s=time.perf_counter() - started,
            config=vars(cfg),
            spatial=request.get("spatial", "iou"),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("weights", type=Path)
    args = parser.parse_args()
    mapper = Mapper(args.weights)
    print("READY", flush=True)
    for line in sys.stdin:
        pair = json.loads(line)
        try:
            result = mapper.run(json.loads(Path(pair["input"]).read_text()))
            Path(pair["output"]).write_text(json.dumps(result, sort_keys=True, allow_nan=False))
            print("DONE", flush=True)
        except Exception:
            import traceback

            traceback.print_exc()
            print("ERROR", flush=True)


if __name__ == "__main__":
    main()
