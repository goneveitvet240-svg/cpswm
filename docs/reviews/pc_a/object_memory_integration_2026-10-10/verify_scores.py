"""Independent arithmetic check: stdlib/numpy only, no CPSWM evaluator imports."""

import json
import sys
from pathlib import Path

import numpy as np

repo, outputs, historical, summary_path = map(Path, sys.argv[1:])
summary = json.loads(summary_path.read_text())
source = repo / "docs/reviews/pc_a/matched_transition_death_test_2026-10-09"
manifest = json.loads((source / "evidence/manifest.json").read_text())
capture = source / "evidence/natural-30-5-5"
targets = json.loads((source / "TARGETS.json").read_text())
checked = 0


def within(point, event, target):
    if point is None:
        return False
    obj = next(o for o in event["metadata"]["objects"] if o["objectId"] == target)
    corners = obj["axisAlignedBoundingBox"]["cornerPoints"]
    return all(
        min(c[j] for c in corners) <= point[j] <= max(c[j] for c in corners) for j in range(3)
    )


def pixel_identity(pixel, ids, masks):
    if pixel is None:
        return None
    present = np.flatnonzero(masks[:, pixel[1], pixel[0]])
    return ids[int(present[0])] if len(present) == 1 else None


for arm in ("current", "iou", "hybrid"):
    run = json.loads((outputs / "dev" / f"{arm}.json").read_text())
    expected = summary["development"][arm]
    actual = [0, 0, 0]
    for f, step in zip(manifest["frames"], run["steps"], strict=True):
        event = json.loads((capture / f["sdk"]).read_text())
        ids = json.loads((capture / f["instance_ids"]).read_text())
        masks = np.load(capture / f["instances"], allow_pickle=False)["masks"]
        for report, target in zip(step["reports"], targets, strict=True):
            identity = pixel_identity(report["selected_pixel_uv"], ids, masks) == target
            position = within(report["world_point_m"], event, target)
            actual[0] += identity
            actual[1] += position
            actual[2] += identity and position
            checked += 1
        for row in expected["tracks"]:
            if row["index"] != step["index"]:
                continue
            track = next(t for t in step["record"]["tracks"] if t["anchor_id"] == row["anchor"])
            identity = pixel_identity(track["selected_pixel_uv"], ids, masks) == row["target"]
            position = within(track["world_point_m"], event, row["target"])
            assert (identity, position, identity and position) == (
                row["identity"],
                row["position"],
                row["joint"],
            )
            checked += 1
    assert actual == [expected[k] for k in ("identity", "position", "joint")]

em = json.loads((historical / "experiment/manifests/evaluation-manifest.json").read_text())
for trial, short in (("live-1deg", "1deg"), ("live-5deg", "5deg")):
    for arm in ("current", "iou", "hybrid"):
        run = json.loads((outputs / short / f"{arm}.json").read_text())
        expected = summary["historical_check"][trial][arm]
        total = 0
        for row in expected["rows"]:
            step = run["steps"][row["index"]]
            entry = next(e for e in em if e["trial"] == trial and e["index"] == row["index"])
            event = json.loads((historical / "source" / entry["sdk"]).read_text())
            track = next(t for t in step["record"]["tracks"] if t["anchor_id"] == row["anchor"])
            value = within(track["world_point_m"], event, row["target"])
            assert value == row["aabb_hit"]
            total += value
            checked += 1
        assert total == expected["aabb_hits"]
print(
    json.dumps(
        dict(
            checked_rows=checked,
            status="PASS",
            scope="arithmetic recheck; same annotations, no independent perception",
        )
    )
)
