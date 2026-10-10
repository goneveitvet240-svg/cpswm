"""Evaluator-only aggregation; never imported by the learned frontend or owner."""

import argparse
from collections import Counter
from pathlib import Path

from run_matched_transition_death_test import _bounds, _instance_at, _sdk_bundle, load, save


def inside(point, event, target):
    lower, upper = _bounds(event, target)
    return point is not None and all(
        lo <= x <= hi for x, lo, hi in zip(point, lower, upper, strict=True)
    )


def main(args):
    source = Path("docs/reviews/pc_a/matched_transition_death_test_2026-10-09")
    manifest = load(source / "evidence/manifest.json")
    capture = source / "evidence/natural-30-5-5"
    targets = load(source / "TARGETS.json")
    reference = load(args.development / "current.json")
    _, ids, masks = _sdk_bundle(capture, manifest["frames"][0])
    truth = {
        t["anchor_id"]: _instance_at(t["selected_pixel_uv"], ids, masks)
        for t in reference["steps"][0]["record"]["tracks"]
    }
    summary = {
        "development": {},
        "historical_check": {},
        "limits": [
            "9 correlated primary query slots, one scene, no new physical actions",
            "16 older frames are previously exposed same-house checks, not a blind test",
            "Older capture lacks instance masks; AABB geometry only, identity/joint unscored",
            "All-initial-track identity uses the same reference first-frame pixels across arms",
        ],
    }
    for arm in ("current", "iou", "hybrid"):
        result = load(args.development / (arm + ".json"))
        queries, tracks = [], []
        for frame, step in zip(manifest["frames"], result["steps"], strict=True):
            event, ids, masks = _sdk_bundle(capture, frame)
            for query, report, target in zip(
                manifest["queries"], step["reports"], targets, strict=True
            ):
                identity = _instance_at(report["selected_pixel_uv"], ids, masks) == target
                position = inside(report["world_point_m"], event, target)
                queries.append(
                    dict(
                        index=step["index"],
                        query=query,
                        identity=identity,
                        position=position,
                        joint=identity and position,
                    )
                )
            by_anchor = {t["anchor_id"]: t for t in step["record"]["tracks"]}
            for anchor, target in truth.items():
                t = by_anchor[anchor]
                actual = _instance_at(t["selected_pixel_uv"], ids, masks)
                identity = actual is not None and actual == target
                position = target is not None and inside(t["world_point_m"], event, target)
                tracks.append(
                    dict(
                        index=step["index"],
                        anchor=anchor,
                        target=target,
                        actual=actual,
                        identity=identity,
                        position=position,
                        joint=identity and position,
                        status=t["status"],
                    )
                )
        summary["development"][arm] = dict(
            query_slots=len(queries),
            identity=sum(q["identity"] for q in queries),
            position=sum(q["position"] for q in queries),
            joint=sum(q["joint"] for q in queries),
            initial_track_slots=len(tracks),
            initial_track_joint=sum(t["joint"] for t in tracks),
            queries=queries,
            tracks=tracks,
        )
    historical_root = Path("/private/tmp/cpswm-object-memory-holdout-20261010")
    em = load(historical_root / "experiment/manifests/evaluation-manifest.json")
    fixed = load(
        Path("docs/reviews/pc_a/natural_mask_surface_2026-10-02/evidence/independent-geometry.json")
    )["all_initial_anchors"]
    for trial, path in (("live-1deg", args.one_degree), ("live-5deg", args.five_degree)):
        rows = [r for r in em if r["trial"] == trial]
        summary["historical_check"][trial] = {}
        for arm in ("current", "iou", "hybrid"):
            result = load(path / (arm + ".json"))
            counts = Counter()
            bytarget = {}
            records = []
            for entry, step in zip(rows, result["steps"], strict=True):
                event = load(historical_root / "source" / entry["sdk"])
                tracks = {t["anchor_id"]: t for t in step["record"]["tracks"]}
                for anchor, initial in fixed[trial].items():
                    target = initial["offline_first_frame_box_reference"]
                    track = tracks[anchor]
                    passed = inside(track["world_point_m"], event, target)
                    counts["slots"] += 1
                    counts["aabb_hits"] += passed
                    counts["reported"] += track["world_point_m"] is not None
                    bytarget.setdefault(target, Counter())
                    bytarget[target]["slots"] += 1
                    bytarget[target]["aabb_hits"] += passed
                    records.append(
                        dict(
                            index=entry["index"],
                            anchor=anchor,
                            target=target,
                            aabb_hit=passed,
                            status=track["status"],
                        )
                    )
            summary["historical_check"][trial][arm] = dict(counts, by_target=bytarget, rows=records)
    save(args.output, summary)
    print(
        {
            k: {
                a: {n: v for n, v in x.items() if n not in ("tracks", "queries")}
                for a, x in val.items()
            }
            for k, val in summary.items()
            if k == "development"
        }
    )
    for trial, value in summary["historical_check"].items():
        print(
            trial,
            {a: {k: x[k] for k in ("slots", "reported", "aabb_hits")} for a, x in value.items()},
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("development", "one-degree", "five-degree", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    main(parser.parse_args())
