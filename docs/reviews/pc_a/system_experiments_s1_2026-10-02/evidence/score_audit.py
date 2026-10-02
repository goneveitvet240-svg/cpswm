"""A-side raw-artifact cross-check; not B independent acceptance."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def audit(root, source):
    plan = read(root / "plan.json")
    summary = read(root / "summary.json")
    for name, digest in plan["sources"].items():
        assert sha(source / name) == digest, ("changed source", name)
    for spec in plan["externals"].values():
        assert sha(Path(spec["path"])) == spec["sha256"], spec
    targets = read(Path(plan["externals"]["targets"]["path"]))
    rows, restores = [], []
    for group in summary["groups"]:
        for entry in group["arms"]:
            arm = root / group["id"] / entry["arm"]
            if entry["evaluated_query_slots"] == 0:
                rows.extend(
                    dict(
                        group=group["id"],
                        arm=entry["arm"],
                        query=q,
                        result="UNSCORED",
                        joint_success=None,
                    )
                    for q in plan["queries"]
                )
                continue
            result = read(arm / "result.json")
            scored = read(arm / "evaluation.json")
            assert scored["runtime_result_sha256"] == sha(arm / "result.json")
            assert scored["physical_dispatches"] == result["physical_dispatches"] <= 3
            assert len(list((arm / "public").glob("*/raw.json"))) == result["physical_dispatches"]
            fresh = read(arm / "fresh.json")
            assert fresh["before"] == fresh["after"] == result["final_reports"]
            assert fresh["physical_dispatches"] == result["physical_dispatches"]
            restores.append(str(arm.relative_to(root)))
            for index, row in enumerate(scored["rows"]):
                final = result["final_reports"][index]
                sdk_folder = arm / "transport/evaluator_only/sdk-events"
                mask_path = sdk_folder / row["evaluation_mask"]
                event_path = sdk_folder / row["evaluation_mask"].replace("-instances.npz", ".json")
                event = read(event_path)
                ids = read(mask_path.with_suffix(".json"))
                with np.load(mask_path, allow_pickle=False) as bundle:
                    masks = bundle["masks"]
                uv = final["selected_pixel_uv"]
                matched = (
                    [] if uv is None else [ids[i] for i in np.flatnonzero(masks[:, uv[1], uv[0]])]
                )
                actual_id = matched[0] if len(matched) == 1 else None
                truth = row["truth"]
                assert truth["reported_instance_id"] == actual_id
                assert truth["target_instance_id"] == targets[index]
                if final["action_id"] is not None:
                    assert event["owner"] == final["action_id"]
                obj = next(
                    o for o in event["metadata"]["objects"] if o["objectId"] == targets[index]
                )
                corners = np.asarray(obj["axisAlignedBoundingBox"]["cornerPoints"])
                lower, upper = corners.min(0), corners.max(0)
                assert lower.tolist() == truth["lower_m"] and upper.tolist() == truth["upper_m"]
                point = final["world_point_m"]
                assert row["report"]["point_m"] == point
                reported = final["status"] == "reported"
                identity = reported and actual_id == targets[index]
                position = (
                    reported
                    and point is not None
                    and bool(
                        np.all(np.asarray(point) >= lower) and np.all(np.asarray(point) <= upper)
                    )
                )
                joint = identity and position
                for k, value in [
                    ("identity_correct", identity),
                    ("position_correct", position),
                    ("joint_success", joint),
                ]:
                    assert row["score"][k] == value, (group["id"], entry["arm"], index, k)
                outside = (
                    None
                    if point is None
                    else (
                        1000 * np.maximum(np.maximum(lower - point, np.asarray(point) - upper), 0)
                    ).tolist()
                )
                rows.append(
                    dict(
                        group=group["id"],
                        arm=entry["arm"],
                        query=plan["queries"][index],
                        result=final["status"],
                        reason=final["reason"],
                        actual_instance=actual_id,
                        identity_correct=identity,
                        position_correct=position,
                        joint_success=joint,
                        outside_aabb_mm_xyz=outside,
                    )
                )
    assert len(rows) == plan["planned_query_slots"]
    return dict(
        status="A_SIDE_ARTIFACT_RECOMPUTATION_PASS",
        source_files=len(plan["sources"]),
        fresh_restore_count=len(restores),
        restored_arms=restores,
        rows=rows,
        claim="recomputation only; not simulator rerun or B independent acceptance",
    )


if __name__ == "__main__":
    root, source, output = map(Path, sys.argv[1:])
    if output.exists():
        raise FileExistsError(output)
    result = audit(root, source)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "restored_arms")}))
