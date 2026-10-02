"""Independent equality gates and matched identity+position pilot summary."""

import argparse
import base64
import json
from pathlib import Path

from cpswm.system.reproducibility import content_sha256
from cpswm.system.target_position_report import (
    CameraAttempt,
    EvaluationTruth,
    ReportRun,
    ReportTask,
    TargetPositionReport,
    compare_report_runs,
)


def read(path):
    return json.loads(path.read_text())


def public_signature(raw):
    pose = json.loads(base64.b64decode(raw["observations"][2]["payload_base64"]))
    for key in ("action_id", "capture_time"):
        pose.pop(key)
    return content_sha256(
        (raw["observations"][0]["payload_base64"], raw["observations"][1]["payload_base64"], pose)
    )


def world_signature(event):
    return content_sha256(
        sorted(
            [
                (o["objectId"], o["position"], o["rotation"], o["axisAlignedBoundingBox"])
                for o in event["metadata"]["objects"]
            ],
            key=lambda o: o[0],
        )
    )


def summarize(root, output):
    from datetime import datetime

    if output.exists():
        raise ValueError("comparison output must be new")
    manifest = read(root / "manifest.json")
    expected = ["fixed", "active", "no-update"]
    if manifest["arms"] != expected:
        raise ValueError("missing arm must remain incomplete")
    signatures, worlds, runs, truths = {}, {}, {}, {}
    common_tasks = None
    for arm in expected:
        folder = root / arm
        result, scored = read(folder / "result.json"), read(folder / "evaluation.json")
        raws = [read(p) for p in sorted((folder / "public").glob("*/raw.json"))]
        signatures[arm] = public_signature(raws[0])
        events = {}
        for p in (folder / "transport/evaluator_only/sdk-events").glob("*.json"):
            if p.stem.isdigit():
                event = read(p)
                if event["owner"] is not None:
                    events[event["owner"]] = event
        worldpins = [world_signature(events[r["action_id"]]) for r in raws]
        worlds[arm] = worldpins
        attempts = []
        for raw in raws:
            event = events[raw["action_id"]]
            if event["requested"]["action"] != raw["action"]:
                raise ValueError("SDK and public action differ")
            if raw["action"] != "Pass" and event["requested"]["degrees"] != raw["degrees"]:
                raise ValueError("SDK and public angle differ")
            if (
                dict(action=raw["action"], degrees=raw["degrees"])
                not in manifest["common_allowed_actions"]
            ):
                raise ValueError("action outside common allowed set")
            attempts.append(
                CameraAttempt(
                    action_id=raw["action_id"],
                    action=raw["action"],
                    degrees=raw["degrees"],
                    success=raw["success"],
                    elapsed_seconds=(
                        datetime.fromisoformat(raw["received_at"])
                        - datetime.fromisoformat(raw["decision_time"])
                    ).total_seconds(),
                )
            )
        if len(attempts) != result["physical_dispatches"]:
            raise ValueError("physical dispatch count differs")
        if common_tasks is None:
            common_tasks = [
                ReportTask.model_validate(
                    dict(
                        r["task"],
                        initial_input_sha256=signatures[arm],
                        allowed_actions_sha256=content_sha256(manifest["common_allowed_actions"]),
                    )
                )
                for r in scored["rows"]
            ]
        if [r["query"] for r in scored["rows"]] != result["queries"]:
            raise ValueError("incomplete query slots")
        runs[arm], truths[arm] = [], []
        for task, row in zip(common_tasks, scored["rows"], strict=True):
            # Same frozen-world task epoch, verified below. No location or identity
            # is altered when rebinding per-process receipt IDs to the common task.
            report = TargetPositionReport.model_validate(
                dict(row["report"], task_sha256=task.digest)
            )
            truth = EvaluationTruth.model_validate(
                dict(row["truth"], task_sha256=task.digest, report_sha256=report.digest)
            )
            runs[arm].append(
                ReportRun(
                    task=task,
                    policy_id=arm,
                    attempts=tuple(attempts),
                    report=report,
                    stop_reason=result.get("stop", {}).get("reason", "budget_exhausted"),
                )
            )
            truths[arm].append(truth)
    equality = dict(
        initial_public_equal=len(set(signatures.values())) == 1,
        entire_frozen_world_equal=len({v for vs in worlds.values() for v in vs}) == 1,
    )
    comparisons = {
        name: compare_report_runs(
            tuple(runs["fixed"]),
            tuple(runs[name]),
            first_truth=tuple(truths["fixed"]),
            second_truth=tuple(truths[name]),
        )
        for name in ("active", "no-update")
    }
    valid = all(equality.values()) and all(
        c["paired_design_and_count_budget_valid"] for c in comparisons.values()
    )
    output.write_text(
        json.dumps(
            dict(
                status="VALID_DEVELOPMENT_PAIR" if valid else "UNMATCHED_PAIR_NO_BENEFIT_CLAIM",
                equality=equality,
                public_signatures=signatures,
                world_signatures=worlds,
                comparisons=comparisons,
                task_count=3,
                independent_scenes=1,
                action_accounting=(
                    "three query outcomes share each physical episode; "
                    "group action sums repeat shared actions"
                ),
                scope="frozen development pilot; not generalization or B acceptance",
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    summarize(a.root, a.output)
