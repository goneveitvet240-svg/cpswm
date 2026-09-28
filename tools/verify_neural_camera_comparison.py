"""Reconstruct the fixed camera comparison from owned state and evaluator pixels.

The evaluator reads privileged masks only after an episode. These local evidence
checks detect reporting faults, not a hostile interpreter or jointly fabricated
simulator, SQLite and all source artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

import numpy as np
import torch
from run_neural_pixel_camera_loop import (
    ARMS,
    ASSUMPTIONS,
    METHODS,
    SOURCES,
    DiagnosticViewModel,
    DurableFixtureProducer,
    JointFixture,
    canonical_probabilities,
    diagnostic_house,
    scan_rotation,
    source_identity,
)

from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.joint_camera_feedback import condition_view
from cpswm.system.joint_camera_policy import JointCameraProblem
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationDelivery

FRONTENDS = ("ssdlite", "fasterrcnn")
SITES = ("north", "south")


def plain(value):
    return json.loads(json.dumps(value, default=str))


def require(value, message):
    if not value:
        raise ValueError(message)


def bbox_iou(box, target):
    if target is None:
        return 0.0
    x0, y0 = max(box[0], target[0]), max(box[1], target[1])
    x1, y1 = min(box[2], target[2]), min(box[3], target[3])
    overlap = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area = (box[2] - box[0]) * (box[3] - box[1])
    area += (target[2] - target[0]) * (target[3] - target[1]) - overlap
    return overlap / area if area > 0 else 0.0


def verify_episode(directory, *, weights, checkpoint, method, frontend, site, image_size=320):
    torch.set_num_threads(2)
    report = json.loads((directory / "result.json").read_text())
    require(method in METHODS and frontend in FRONTENDS and site in SITES, "undeclared case")
    require(
        (report["method"], report["detector_kind"], report["site_evaluator_only"])
        == (method, frontend, site),
        "episode differs from expected matrix cell",
    )
    require(
        report["assumptions"] == ASSUMPTIONS and report["max_actions"] == 3,
        "comparison assumptions or budget changed",
    )
    require(
        type(image_size) is int
        and image_size in (320, 640)
        and report["image_size"] == image_size
        and report["dependencies"]["image_size"] == image_size,
        "capture resolution differs from declared condition",
    )
    source, files = source_identity()
    require(
        report["source_sha256"] == source and report["source_files"] == files,
        "episode source differs from verifier",
    )
    require(report["feedback_enabled"] is (method in ARMS), "feedback treatment changed")
    require(
        report["checkpoint_arm"] == (method if method in ARMS else ARMS[0]),
        "checkpoint arm differs from method",
    )
    require(
        all(
            report[k] is True
            for k in (
                "source_unchanged",
                "same_view_after_resume",
                "native_batch_unchanged_by_camera",
                "ledger_unchanged_by_camera",
            )
        ),
        "incomplete execution or state preservation",
    )
    require(
        report["natural_semantic_transitions"] == report["physical_manipulations"] == 0
        and report["complete_natural_closed_loop"] is False,
        "unsupported task claim",
    )
    with sqlite3.connect(f"file:{directory / 'state.sqlite'}?mode=ro", uri=True) as db:
        source_db, dependency, document, digest = db.execute(
            "SELECT source,dependencies,document,digest FROM checkpoint WHERE id=1"
        ).fetchone()
    require(
        source_db == source
        and dependency == content_sha256(report["dependencies"])
        and hashlib.sha256(document.encode()).hexdigest() == digest,
        "owned state source, dependencies or digest differ",
    )
    fields = StateCodec().loads(document)["fields"]
    commands = fields["_observation_commands"]
    statuses = fields["_observation_status"]
    require(set(commands) == set(statuses), "incomplete owned action history")
    scope = dict(
        household_id=fields["_scope"][0],
        session_id=fields["_scope"][1],
        trace_id=fields["_scope"][2],
    )
    decoder = PixelCategoryOutcomeDecoder(
        weights_path=weights, category="apple", sources=SOURCES, detector_kind=frontend, **scope
    )
    require(
        decoder.binding_sha256 == report["dependencies"]["decoder_binding"],
        "pixel decoder dependency differs",
    )
    pin = hashlib.sha256((checkpoint / "manifest.json").read_bytes()).hexdigest()
    require(pin == report["checkpoint_manifest_sha256"], "neural checkpoint manifest differs")
    joint = NeuralNativeProducer(JointFixture(), checkpoint, manifest_sha256=pin)
    require(
        joint.binding_sha256 == report["dependencies"]["joint_binding"], "neural binding differs"
    )

    def no_execution(*args, **kwargs):
        raise ValueError("artifact verification must not execute a new semantic step")

    store = ContinuousStateStore(
        directory / "state.sqlite", source_identity=source, dependency_identity=dependency
    )
    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=DurableFixtureProducer(),
            context_builder=no_execution,
            joint_producer=joint,
            observation_decoder=decoder if method in ARMS else None,
        )
        base = stream._native_joint_decision_view()
        final = stream.current_joint_decision_view()
        updates = stream.joint_observation_updates()
        require(
            report["initial_joint_probabilities"] == canonical_probabilities(base)
            and report["final_joint_probabilities"] == canonical_probabilities(final),
            "reported posterior differs from actual native state and pixel replay",
        )
    finally:
        store.close()
    by_action = {str(u.action_id): u for u in updates}
    actions = [x for x in report["actions"] if not x.get("stopped")]
    stops = [x for x in report["actions"] if x.get("stopped")]
    require(
        len(actions) == len(commands) and 0 < len(actions) <= report["max_actions"],
        "action count mismatch or empty episode",
    )
    require(
        len(stops) <= 1 and (not stops or report["actions"][-1] is stops[0]),
        "invalid stop placement",
    )
    require(len({a["action_id"] for a in actions}) == len(actions), "duplicate action row")
    require({UUID(a["action_id"]) for a in actions} == set(commands), "action identity mismatch")
    private = directory / "unity-logs/evaluator_only"
    truth = json.loads((private / "actions.json").read_text())
    require(len(truth) == len(actions) + 1, "evaluator actions do not match owned actions")
    initial = report["initial_capture"]
    require(
        initial["action_id"] == truth[0]["request"]["action_id"]
        and initial["success"] is True
        and truth[0]["request"]["action"] == "Pass"
        and truth[0]["request"]["degrees"] == 0,
        "initial acquisition mismatch",
    )
    original_path = Path(__file__).resolve().parents[1] / (
        "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    expected_house = diagnostic_house(json.loads(original_path.read_text()), site)
    require(
        json.loads((directory / "evaluator_house.json").read_text()) == expected_house,
        "scene initialization differs from fixed site",
    )
    target_id = expected_house["metadata"]["cpswm_diagnostic_target"]
    actual_initial = json.loads((private / "initial.json").read_text())
    target = next(o for o in actual_initial["objects"] if o["objectId"] == target_id)
    scene_target = next(o for o in expected_house["objects"][0]["children"] if o["id"] == target_id)
    require(
        all(
            math.isclose(
                target["axisAlignedBoundingBox"]["center"][k],
                scene_target["position"][k],
                abs_tol=1e-4,
            )
            for k in ("x", "y", "z")
        ),
        "actual asset bounds center differs from requested house placement",
    )
    expected_heading = ASSUMPTIONS["initial_heading"]
    rows, history = [], []
    decision_view = base
    raw_map = fields["_raw"]
    # Initial Pass is retained but not a semantic or posterior observation command.
    records = [(None, None, initial["observation_ids"])]
    for row in actions:
        command, command_digest = commands[UUID(row["action_id"])]
        delivery = statuses[command.action_id]
        require(
            type(delivery) is ObservationDelivery and content_sha256(command) == command_digest,
            "non-delivered or corrupt command",
        )
        require(row["command"] == plain(asdict(command)), "reported command differs from owner")
        if method.startswith("scan_"):
            rotation = scan_rotation(
                tuple(history), DiagnosticViewModel(decoder), left_first=method == "scan_left_first"
            )
            require(
                rotation == (command.action, command.degrees),
                "scan action differs from public policy",
            )
        else:
            declared = JointCameraProblem.model_validate_json(
                command.reason.removeprefix("joint-ciav@1:")
            )
            expected = DiagnosticViewModel(decoder).problem(
                decision_view,
                stream.visible_prefix(cutoff=command.decision_time),
                decision_time=command.decision_time,
                execution_history=tuple(history),
            )
            require(declared == expected, "camera likelihood or decision differs from fixed policy")
        update = by_action.get(row["action_id"])
        require(
            row["update"] == (None if update is None else plain(asdict(update))),
            "reported conditioning differs from actual replay",
        )
        expected_prior = {
            str(k): v for k, v in decision_view.verification_belief().posterior.items()
        }
        if update is not None:
            _, selected = declared.select(decision_view, stream._system.cause_information_planner)
            likelihood = (
                selected.candidate.outcome_likelihoods[update.outcome]
                if update.execution_success and update.outcome is not None
                else None
            )
            decision_view, _ = condition_view(
                decision_view, likelihood, evidence_sha256=update.evidence_sha256
            )
        expected_posterior = {
            str(k): v for k, v in decision_view.verification_belief().posterior.items()
        }
        require(
            row["prior"] == expected_prior
            and row["posterior"] == expected_posterior
            and row["probabilities_changed"] is (expected_prior != expected_posterior),
            "reported per-action posterior differs",
        )
        require(
            (row["action"], row["degrees"], row["success"])
            == (command.action, command.degrees, delivery.success),
            "reported execution differs",
        )
        require(
            row["delivery_observation_ids"]
            == [str(x.envelope().identity.observation_id) for x in delivery.observations],
            "reported delivered observations differ",
        )
        frames = decoder.measurements(delivery.observations, cutoff=delivery.received_at)
        require(
            row["pixel_measurements"] == plain([asdict(f) for f in frames]),
            "reported pixel predictions differ from actual inference",
        )
        expected_outcome = (
            "category_candidate"
            if any(c.category == "apple" for f in frames for c in f.candidates)
            else "no_category_candidate"
        )
        require(row["outcome"] == expected_outcome, "reported outcome differs from actual pixels")
        require(
            all(raw_map[x.envelope().identity.observation_id] == x for x in delivery.observations),
            "delivery differs from owned raw",
        )
        history.append((command, delivery))
        records.append((row, delivery, row["delivery_observation_ids"]))
    for index, ((row, delivery, identities), evaluator) in enumerate(
        zip(records, truth, strict=True)
    ):
        require(
            evaluator["index"] == index and len(identities) == 1, "nonsequential image evidence"
        )
        raw = raw_map[UUID(identities[0])]
        require(
            raw.payload_bytes == (private / f"{index:03d}-rgb.npy").read_bytes(),
            "evaluator pixels differ from delivered RGB",
        )
        rgb = np.load(private / f"{index:03d}-rgb.npy", allow_pickle=False)
        require(
            rgb.shape == (image_size, image_size, 3)
            and evaluator["image_size"] == [image_size, image_size],
            "actual image dimensions differ from declared condition",
        )
        mask = np.load(private / f"{index:03d}-mask.npy", allow_pickle=False)
        require(mask.dtype == bool and mask.shape == rgb.shape[:2], "invalid evaluator mask")
        locations = np.argwhere(mask)
        bbox = (
            None
            if len(locations) == 0
            else [
                int(locations[:, 1].min()),
                int(locations[:, 0].min()),
                int(locations[:, 1].max() + 1),
                int(locations[:, 0].max() + 1),
            ]
        )
        require(
            evaluator["target_pixels"] == int(mask.sum()) and evaluator["target_bbox"] == bbox,
            "evaluator visibility differs from mask",
        )
        if index == 0:
            require(int(mask.sum()) == 0, "initial-visible episode is outside this diagnostic")
        else:
            require(
                evaluator["request"]
                == {
                    "action_id": row["action_id"],
                    "action": row["action"],
                    "degrees": row["degrees"],
                }
                and evaluator["success"] is row["success"],
                "evaluator action mismatch",
            )
            if delivery.success:
                expected_heading = (
                    expected_heading
                    + row["degrees"] * (1 if row["action"] == "RotateRight" else -1)
                ) % 360
        require(
            math.isclose(evaluator["agent"]["rotation"]["y"], expected_heading, abs_tol=1e-3),
            "actual camera heading differs from successful commands",
        )
        require(
            all(
                math.isclose(evaluator["target_position"][k], target["position"][k], abs_tol=1e-4)
                for k in ("x", "y", "z")
            ),
            "static target moved during episode",
        )
        candidates = (
            []
            if row is None
            else [
                c
                for f in row["pixel_measurements"]
                for c in f["candidates"]
                if c["category"] == "apple"
            ]
        )
        rows.append(
            {
                "index": index,
                "heading": expected_heading,
                "rgb_sha256": hashlib.sha256(raw.payload_bytes).hexdigest(),
                "target_pixels": int(mask.sum()),
                "target_sdk_visible": evaluator["target_sdk_visible"],
                "apple_scores": [c["detector_score"] for c in candidates],
                "apple_bbox_ious": [bbox_iou(c["box_xyxy"], bbox) for c in candidates],
                "false_positive_without_target_pixels": bool(candidates) and not mask.any(),
            }
        )
    _, outcomes = DiagnosticViewModel(decoder).history(tuple(history))
    if stops:
        expected_stop = (
            "category_candidate"
            if "category_candidate" in outcomes.values()
            else "no_remaining_positive_utility_or_views"
        )
        require(
            stops[0]["stop_reason"] == expected_stop, "stop claim differs from delivered history"
        )
    else:
        require(len(actions) == 3, "early incomplete episode without a stop decision")
    require(
        report["executed_camera_updates"] == (len(actions) if method in ARMS else 0)
        and report["conditional_evidence_count"] == report["executed_camera_updates"],
        "posterior treatment count differs",
    )
    if method not in ARMS:
        require(
            report["initial_joint_probabilities"] == report["final_joint_probabilities"]
            and all(not x["probabilities_changed"] and x["update"] is None for x in actions),
            "no-feedback control changed probability",
        )
    require(
        math.isclose(sum(report["initial_joint_probabilities"].values()), 1, abs_tol=1e-12),
        "initial posterior is not normalized",
    )
    return {
        "method": method,
        "image_size": image_size,
        "frontend": frontend,
        "site": site,
        "verified": True,
        "source_sha256": source,
        "checkpoint_manifest_sha256": report["checkpoint_manifest_sha256"],
        "initial_joint_probabilities": report["initial_joint_probabilities"],
        "final_joint_probabilities": report["final_joint_probabilities"],
        "actions": [
            {k: x[k] for k in ("action", "degrees", "success", "outcome", "seconds")}
            for x in actions
        ],
        "rotation_count": len(actions),
        "rotation_degrees": sum(x["degrees"] for x in actions),
        "all_actions_succeeded": all(x["success"] for x in actions),
        "any_category_positive": any(x["apple_scores"] for x in rows),
        "any_bbox_overlap": any(any(v > 0 for v in x["apple_bbox_ious"]) for x in rows),
        "any_false_positive_without_pixels": any(
            x["false_positive_without_target_pixels"] for x in rows
        ),
        "frames": rows,
        "seconds": report["seconds"],
        "stop_reason": stops[0]["stop_reason"] if stops else "budget_exhausted",
    }


def verify_matrix(directory, weights, checkpoints, *, image_size=320):
    plan = json.loads((directory / "matrix.json").read_text())
    expected = [(f, s, m) for f in FRONTENDS for s in SITES for m in METHODS]
    require(
        [(x["frontend"], x["site"], x["method"]) for x in plan] == expected,
        "matrix is incomplete, reordered or duplicated",
    )
    results = []
    for case in plan:
        cell = f"{case['frontend']}/{case['site']}/{case['method']}"
        require(
            case["directory"] == cell and case["exit_code"] == 0, "failed or redirected matrix cell"
        )
        require(case["image_size"] == image_size, "matrix capture condition differs")
        result = verify_episode(
            directory / cell,
            weights=weights[case["frontend"]],
            checkpoint=checkpoints
            / (case["method"] if case["method"] in ARMS else ARMS[0])
            / "checkpoint",
            method=case["method"],
            frontend=case["frontend"],
            site=case["site"],
            image_size=image_size,
        )
        results.append(result)
    prior = results[0]["initial_joint_probabilities"]
    require(
        all(
            set(r["initial_joint_probabilities"]) == set(prior)
            and all(
                math.isclose(r["initial_joint_probabilities"][k], v, abs_tol=1e-12, rel_tol=0)
                for k, v in prior.items()
            )
            for r in results
        ),
        "unequal initial priors across methods",
    )
    pixel_groups = {}
    for result in results:
        for frame in result["frames"]:
            key = f"{result['site']}:{frame['heading']}"
            pixel_groups.setdefault(key, set()).add(frame["rgb_sha256"])
    return {
        "scope": "A_LOCAL_CONTROLLED_PRIOR_CAMERA_DIAGNOSTIC_NOT_FORMAL_B_ACCEPTANCE",
        "image_size": image_size,
        "expected_episodes": 24,
        "verified_episodes": len(results),
        "same_initial_priors": True,
        "same_pixels_per_site_heading": all(len(v) == 1 for v in pixel_groups.values()),
        "pixel_hash_counts_per_site_heading": {k: len(v) for k, v in pixel_groups.items()},
        "results": results,
        "complete_natural_closed_loop": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--ssdlite-weights", type=Path, required=True)
    p.add_argument("--fasterrcnn-weights", type=Path, required=True)
    p.add_argument("--checkpoints", type=Path, required=True)
    p.add_argument("--image-size", type=int, choices=(320, 640), default=320)
    a = p.parse_args()
    result = verify_matrix(
        a.directory,
        {"ssdlite": a.ssdlite_weights, "fasterrcnn": a.fasterrcnn_weights},
        a.checkpoints,
        image_size=a.image_size,
    )
    (a.directory / "verified-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
