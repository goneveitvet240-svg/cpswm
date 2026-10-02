"""Render saved public predictions without evaluator masks or labels."""

import base64
import gzip
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

source, evidence, output = map(Path, sys.argv[1:])
fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
examples = [("live-1deg", 0), ("live-1deg", 10), ("live-5deg", 4)]
for ax, (trial, index) in zip(axes, examples, strict=True):
    raw = json.loads((source / trial / f"public/{index:03d}/raw.json").read_text())
    rgb = np.load(
        io.BytesIO(base64.b64decode(raw["observations"][0]["payload_base64"])), allow_pickle=False
    )
    public = json.loads((evidence / "run" / trial / f"{index:03d}/public.json").read_text())
    masks = np.load(
        io.BytesIO(
            gzip.decompress((evidence / "run" / trial / f"{index:03d}/masks.npy.gz").read_bytes())
        ),
        allow_pickle=False,
    )
    ax.imshow(rgb)
    bottles = [t for t in public["tracks"] if t["category"] == "bottle"]
    initial = json.loads((evidence / "run" / trial / "000/public.json").read_text())
    anchors = sorted(
        [
            c
            for c in initial["detector"]["candidates"]
            if c["category"] == "bottle" and c["detector_score"] >= 0.5
        ],
        key=lambda c: c["box_xyxy"][0],
    )
    lines = []
    for n, anchor in enumerate(anchors):
        track = next(t for t in bottles if t["anchor_id"] == anchor["candidate_id"])
        color = ["#35e5ff", "#ffcc33"][n]
        if track["current_candidate_id"] is not None:
            c = next(
                c
                for c in public["detector"]["candidates"]
                if c["candidate_id"] == track["current_candidate_id"]
            )
            ax.contour(
                masks[c["native_index"]] >= 0.5, levels=[0.5], colors=[color], linewidths=0.8
            )
        points = np.array(track["flow_points_uv"])
        if points.size:
            ax.scatter(points[:, 0], points[:, 1], s=5, c=color)
        if track["selected_pixel_uv"]:
            u, v = track["selected_pixel_uv"]
            ax.scatter([u], [v], s=100, c=color, marker="+", linewidths=2)
        status = (
            "supported"
            if track["world_point_m"] is not None
            else track["status"].replace("_NO_REINITIALIZATION", "")
        )
        lines.append(f"Bottle anchor {n + 1}: {status}")
    ax.set_title(f"{trial}, frame {index}\n" + "\n".join(lines), fontsize=10)
    ax.set_axis_off()
fig.suptitle(
    "Public RGB predictions: mask contours, original flow features, selected surface pixel (+)",
    fontsize=12,
)
fig.savefig(output, dpi=170)
