"""Offline arithmetic audit; imports no CPSWM inference or evaluator code.

Reuses saved neural masks and flow features. This is not independent perception,
identity adjudication, simulator acceptance, or a second-machine review.
"""

import argparse
import base64
import gzip
import io
import json
from collections import Counter
from hashlib import sha256
from math import cos, radians, sin, tan
from pathlib import Path

import numpy as np


def read(path, pin=None):
    data = path.read_bytes()
    if pin is not None:
        assert sha256(data).hexdigest() == pin, path
    return json.loads(data)


def project(c, depth, u, v):
    z = float(depth[v, u]) * c["far_plane_m"] / (c["far_plane_m"] - c["near_plane_m"])
    f = c["height"] / (2 * tan(radians(c["vertical_fov_degrees"]) / 2))
    x, y = (u + 0.5 - c["width"] / 2) * z / f, -(v + 0.5 - c["height"] / 2) * z / f
    p, a = radians(c["pitch_degrees"]), radians(c["yaw_degrees"])
    yy, zz = cos(p) * y - sin(p) * z, sin(p) * y + cos(p) * z
    return np.add(c["position_m"], (cos(a) * x + sin(a) * zz, yy, -sin(a) * x + cos(a) * zz))


def selected(mask, depth, c, record, support=None):
    valid = (
        (mask >= 0.5)
        & np.isfinite(depth)
        & (depth > 0)
        & (depth < c["far_plane_m"] - c["near_plane_m"])
    )
    if support is not None:
        restrict = np.zeros(mask.shape, dtype=bool)
        for u, v in support:
            restrict[v, u] = True
        valid &= restrict
    vs, us = np.nonzero(valid)
    assert len(us), "this archive has no active empty-depth example"
    probability = max(float(mask[v, u]) for u, v in zip(us, vs, strict=True))
    u, v = min(
        (int(u), int(v)) for u, v in zip(us, vs, strict=True) if float(mask[v, u]) == probability
    )
    assert record["selected_pixel_uv"] == [u, v]
    assert record["depth_m"] == float(depth[v, u])
    assert record["selected_mask_probability"] == probability
    assert record["mask_pixels"] == int((mask >= 0.5).sum())
    assert record["valid_mask_pixels"] == int(valid.sum())
    np.testing.assert_allclose(record["world_point_m"], project(c, depth, u, v), rtol=0, atol=1e-12)


def main(source, evidence):
    pins = read(evidence / "manifests/pins.json")
    pub = read(evidence / "manifests/public-manifest.json", pins["public-manifest.json"])
    ev = read(evidence / "manifests/evaluation-manifest.json", pins["evaluation-manifest.json"])
    fresh = read(evidence / "fresh-equality.json")
    result = read(evidence / "run/result.json", fresh["files"]["result.json"])
    evaluation = read(evidence / "run-evaluation.json", fresh["evaluation_sha256"])
    assert result["status"] == "COMPLETED" and not result["failures"] and not result["unprocessed"]
    assert evaluation["inference_sha256"] == fresh["files"]["result.json"]
    assert result["manifest_sha256"] == pins["public-manifest.json"]
    assert evaluation["evaluation_manifest_sha256"] == pins["evaluation-manifest.json"]
    assert [(r["trial"], r["index"]) for r in pub] == [
        (t, i) for t, n in [("live-1deg", 11), ("live-5deg", 5)] for i in range(n)
    ]
    count, summary, previous = Counter(), {}, {}
    for m, e, r, score in zip(pub, ev, result["frames"], evaluation["frames"], strict=True):
        key = (m["trial"], m["index"])
        assert all((x["trial"], x["index"]) == key for x in (e, r, score))
        raw = read(source / m["raw"], m["raw_sha256"])
        frame = read(evidence / "run" / r["public"], r["public_sha256"])
        sdk = read(source / e["sdk"], e["sdk_sha256"])
        read(source / e["boxes"], e["boxes_sha256"])
        det = frame["detector"]
        payload = [
            base64.b64decode(x["payload_base64"], validate=True) for x in raw["observations"]
        ]
        assert [sha256(x).hexdigest() for x in payload] == det["payload_sha256"]
        depth, camera = np.load(io.BytesIO(payload[1]), allow_pickle=False), json.loads(payload[2])
        assert camera == det["camera"] and sdk["owner"] == camera["action_id"] == raw["action_id"]
        assert frame["identity_status"] == "UNRESOLVED" and not frame["memory_update_authorized"]
        packed = (evidence / "run" / Path(r["public"]).with_name("masks.npy.gz")).read_bytes()
        assert sha256(packed).hexdigest() == r["masks_sha256"]
        unpacked = gzip.decompress(packed)
        assert sha256(unpacked).hexdigest() == det["masks_npy_sha256"]
        masks = np.load(io.BytesIO(unpacked), allow_pickle=False)
        bounds = {
            o["objectId"]: np.array(o["axisAlignedBoundingBox"]["cornerPoints"])
            for o in sdk["metadata"]["objects"]
        }

        def check_score(point, saved, bounds=bounds):
            if point is None:
                assert saved == {"status": "UNKNOWN", "inside_aabbs": []}
                return
            assert saved["status"] == "REPORTED"
            inside = [
                name
                for name, b in bounds.items()
                if np.all(b.min(0) <= point) and np.all(point <= b.max(0))
            ]
            assert inside == saved["inside_aabbs"]
            count["aabb_point_checks"] += 1
            count["aabb_membership_checks"] += len(bounds)

        active = {}
        for candidate, cs in zip(det["candidates"], score["candidates"], strict=True):
            mask = masks[candidate["native_index"]]
            assert sha256(mask.tobytes()).hexdigest() == candidate["mask_array_sha256"]
            assert cs["candidate_id"] == candidate["candidate_id"]
            if candidate["detector_score"] >= 0.5:
                selected(mask, depth, camera, candidate)
                active[candidate["candidate_id"]] = candidate
                count["standalone_points_recomputed"] += 1
            else:
                assert (
                    candidate["status"] == "BELOW_DETECTOR_THRESHOLD"
                    and candidate["world_point_m"] is None
                )
                count["retained_low_score"] += 1
            check_score(candidate["world_point_m"], cs["point"])
        if key[1] == 0:
            summary[key[0]] = {}
            for track in frame["tracks"]:
                cs = next(x for x in score["candidates"] if x["candidate_id"] == track["anchor_id"])
                target = max(cs["box_overlaps"], key=cs["box_overlaps"].get)
                summary[key[0]][track["anchor_id"]] = dict(
                    category=track["category"],
                    offline_first_frame_box_reference=target,
                    initial_iou=cs["box_overlaps"][target],
                    statuses=Counter(),
                    inside_reference_aabb=0,
                    reported=0,
                    selected_feature_changes=0,
                )
        for track, ts in zip(frame["tracks"], score["tracks"], strict=True):
            assert track["anchor_id"] == ts["anchor_id"]
            assert len(track["flow_feature_ids"]) == len(track["flow_points_uv"])
            anchor = (key[0], track["anchor_id"])
            points = sorted(
                {
                    (round(u), round(v))
                    for u, v in track["flow_points_uv"]
                    if 0 <= round(u) < camera["width"] and 0 <= round(v) < camera["height"]
                }
            )
            support = [
                dict(
                    candidate_id=cid,
                    points_uv=[[u, v] for u, v in points if masks[c["native_index"]][v, u] >= 0.5],
                )
                for cid, c in active.items()
                if c["category"] == track["category"]
            ]
            support = [s for s in support if len(s["points_uv"]) >= 4]
            assert support == track["mask_support"]
            if anchor in previous:
                assert set(track["flow_feature_ids"]) <= set(previous[anchor]["flow_feature_ids"])
                if previous[anchor]["status"] == "LOST_NO_REINITIALIZATION":
                    assert track["status"] == "LOST_NO_REINITIALIZATION"
            if track["world_point_m"] is not None:
                assert len(support) == 1 and track["status"] == "FLOW_AND_MASK_SUPPORTED"
                candidate = active[track["current_candidate_id"]]
                selected(
                    masks[candidate["native_index"]],
                    depth,
                    camera,
                    track["surface"],
                    support[0]["points_uv"],
                )
                assert track["world_point_m"] == track["surface"]["world_point_m"]
                ids = [
                    k
                    for k, (u, v) in zip(
                        track["flow_feature_ids"], track["flow_points_uv"], strict=True
                    )
                    if [round(u), round(v)] == track["selected_pixel_uv"]
                ]
                assert ids == track["selected_feature_ids"]
                count["flow_supported_points_recomputed"] += 1
            else:
                assert (
                    track["surface"] is None
                    and track["selected_pixel_uv"] is None
                    and not track["selected_feature_ids"]
                )
                count["retained_unknown_or_lost"] += 1
            check_score(track["world_point_m"], ts["point"])
            row = summary[key[0]][track["anchor_id"]]
            row["statuses"][track["status"]] += 1
            row["reported"] += track["world_point_m"] is not None
            row["inside_reference_aabb"] += (
                row["offline_first_frame_box_reference"] in ts["point"]["inside_aabbs"]
            )
            if (
                anchor in previous
                and previous[anchor]["selected_feature_ids"]
                and track["selected_feature_ids"]
            ):
                row["selected_feature_changes"] += (
                    previous[anchor]["selected_feature_ids"] != track["selected_feature_ids"]
                )
            previous[anchor] = track
        for old, os in zip(frame["old_box_tracks"], score["old"], strict=True):
            check_score(old["first_seed_m"], os["first"])
            check_score(old["soft_m"], os["soft"])
        count["frames"] += 1
    old_counts = {}
    for trial in summary:
        rows = [x for f in evaluation["frames"] if f["trial"] == trial for x in f["old"]]
        old_counts[trial] = dict(
            frames=len(rows),
            statuses=dict(Counter(x["status"] for x in rows)),
            first_inside_wine=sum(
                "WineBottle|surface|2|8" in x["first"]["inside_aabbs"] for x in rows
            ),
            constant_soft_inside_wine=sum(
                "WineBottle|surface|2|8" in x["soft"]["inside_aabbs"] for x in rows
            ),
        )
    output = dict(
        scope=(
            "independent selection/projection/AABB arithmetic using saved masks and flow; "
            "not independent perception or identity"
        ),
        passed=True,
        counts=count,
        all_initial_anchors=summary,
        old_wine_reference=old_counts,
    )
    (evidence / "independent-geometry.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    main(args.source, args.evidence)
