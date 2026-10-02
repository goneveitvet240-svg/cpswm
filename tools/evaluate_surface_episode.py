"""Isolated exact-instance-mask + AABB evaluator for frozen public task reports.

The target map is predeclared evaluator input. It is never passed to the runtime,
selector, command issuer or inference producer. Every query remains in output.
"""

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np

from cpswm.system.reproducibility import content_sha256
from cpswm.system.target_position_report import (
    EvaluationTruth,
    ReportTask,
    TargetPositionReport,
    assess_report,
)


def load(path):
    return json.loads(path.read_text())


def evaluate(root, targets, output, all_steps=False):
    if output.exists():
        raise ValueError("evaluation output must be new")
    result = load(root / "result.json")
    if result["status"] not in ("COMPLETED", "COMPLETED_WITH_FAILURES"):
        raise ValueError("incomplete run cannot be scored as completed")
    if len(targets) != len(result["queries"]):
        raise ValueError("all declared queries require evaluator targets")
    sdk = {}
    folder = root / "transport/evaluator_only/sdk-events"
    for p in sorted(folder.glob("*.json")):
        if p.stem.isdigit():
            e = load(p)
            if e["owner"] is not None:
                if e["owner"] in sdk:
                    raise ValueError("duplicate evaluator action")
                sdk[e["owner"]] = (p, e)
    if result["physical_dispatches"] > result["budget"]:
        raise ValueError("physical action budget exceeded")
    reference = result["reference_action"]
    first_raw = load(root / "public/000/raw.json")
    rows = []
    batches = (
        [(step["index"], step["reports"], step["action_id"]) for step in result["steps"]]
        if all_steps
        else [
            (
                result["steps"][-1]["index"],
                result["final_reports"],
                result["steps"][-1]["action_id"],
            )
        ]
    )
    for step_index, batch_reports, batch_action in batches:
        for query, report, target in zip(result["queries"], batch_reports, targets, strict=True):
            if query != {k: report[k] for k in ("category", "ordinal")}:
                raise ValueError("query and report differ")
            # A known target is required even for failed/unknown reporting. No search
            # for a truth object that happens to contain the prediction is performed.
            action = report["action_id"] or batch_action
            path, event = sdk[action]
            target_objects = [o for o in event["metadata"]["objects"] if o["objectId"] == target]
            if len(target_objects) != 1:
                raise ValueError("predeclared evaluator target absent or duplicate")
            corners = np.asarray(target_objects[0]["axisAlignedBoundingBox"]["cornerPoints"])
            if corners.shape != (8, 3) or not np.isfinite(corners).all():
                raise ValueError("invalid true AABB")
            raw = next(
                load(p)
                for p in (root / "public").glob("*/raw.json")
                if load(p)["action_id"] == action
            )
            task = ReportTask(
                task_id=uuid5(NAMESPACE_URL, content_sha256((query, reference))),
                scene_id=content_sha256(first_raw["observations"][2]["payload_base64"]),
                frame_id="unity-scene-world-x-right-y-up-z-forward",
                target_description=(
                    f"initial {query['category']} at zero-based x-order {query['ordinal']}"
                ),
                valid_at=datetime.fromisoformat(raw["received_at"]),
                initial_input_sha256=content_sha256(first_raw),
                allowed_actions_sha256=content_sha256(result["schedule"]),
                action_budget=result["budget"],
                position_origin_m=(0.0, 0.0, 0.0),
            )
            value = TargetPositionReport(
                task_sha256=task.digest,
                source_view_sha256=report["source_view_sha256"],
                status=report["status"],
                particle_id=UUID(report["anchor_id"]) if report["anchor_id"] else None,
                instance_hypothesis=report["anchor_id"],
                point_m=report["world_point_m"],
                observation_ids=tuple(UUID(x) for x in report["observation_ids"]),
                reason="surface-support-value; not-centre-posterior",
            )
            reported = None
            maskpath = path.with_name(path.stem + "-instances.npz")
            idpath = path.with_name(path.stem + "-instances.json")
            ids = load(idpath)
            masks = np.load(maskpath, allow_pickle=False)["masks"]
            if masks.dtype != np.bool_ or len(masks) != len(ids):
                raise ValueError("malformed instance mask bundle")
            if report["selected_pixel_uv"] is not None:
                u, v = report["selected_pixel_uv"]
                matches = [key for key, mask in zip(ids, masks, strict=True) if mask[v, u]]
                if len(matches) == 1:
                    reported = matches[0]
            truth = EvaluationTruth(
                task_sha256=task.digest,
                report_sha256=value.digest,
                annotation_artifact_sha256=content_sha256(
                    (
                        sha256(path.read_bytes()).hexdigest(),
                        sha256(maskpath.read_bytes()).hexdigest(),
                        sha256(idpath.read_bytes()).hexdigest(),
                    )
                ),
                target_instance_id=target,
                reported_instance_id=reported,
                lower_m=tuple(corners.min(0)),
                upper_m=tuple(corners.max(0)),
            )
            score = assess_report(task, value, truth)
            rows.append(
                dict(
                    step_index=step_index,
                    query=query,
                    task=task.model_dump(mode="json"),
                    report=value.model_dump(mode="json"),
                    truth=truth.model_dump(mode="json"),
                    score=score.model_dump(mode="json"),
                    evaluation_mask=maskpath.name,
                )
            )
    summary = dict(
        status="EVALUATED",
        runtime_result_sha256=sha256((root / "result.json").read_bytes()).hexdigest(),
        task_count=len(rows),
        physical_dispatches=result["physical_dispatches"],
        joint_success=sum(r["score"]["joint_success"] is True for r in rows),
        identity_correct=sum(r["score"]["identity_correct"] is True for r in rows),
        position_correct=sum(r["score"]["position_correct"] is True for r in rows),
        rows=rows,
    )
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("targets", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--all-steps", action="store_true")
    a = p.parse_args()
    evaluate(a.root, load(a.targets), a.output, a.all_steps)
