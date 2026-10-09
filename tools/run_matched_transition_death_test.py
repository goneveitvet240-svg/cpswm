"""Freeze one natural detector pass and replay matched object transitions.

Runtime inference consumes only public RGB-D, self pose, and frozen Mask R-CNN
outputs. SDK instance masks and AABBs are opened only by ``evaluate``. The same
manifest can be replayed by the pre-reidentification and candidate source trees.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import MaskSurfaceFrame
from cpswm.system.reproducibility import content_sha256
from cpswm.system.surface_episode import report_from_surface_state
from cpswm.system.target_position_report import (
    EvaluationTruth,
    ReportTask,
    TargetPositionReport,
    assess_report,
)

SCHEMA = "cpswm-matched-transition-death-test@1"
BASELINE_SHA = "6e9c953a81e2fc072f4d079d7a19194b1324ea64"
CANDIDATE_SHA = "a5385ddaf6724d2d346fc222866edc2b7ec9407c"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def checked(root: Path, relative: str, expected: str) -> Path:
    path = root / relative
    if not path.is_file() or digest(path) != expected:
        raise ValueError(f"frozen artifact differs: {relative}")
    return path


def raw_rows(value: dict[str, Any]) -> tuple[RawModalityObservation, ...]:
    return tuple(
        RawModalityObservation(
            row["envelope_json"],
            base64.b64decode(row["payload_base64"], validate=True),
            row["capture_receipt_sha256"],
            row["depth_unit"],
        )
        for row in value["observations"]
    )


def _mask_bytes(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes())


def _validate_frozen_frame(raw: dict[str, Any], prediction: dict[str, Any], masks: bytes) -> None:
    if raw["success"] is not True or raw["error"] not in (None, ""):
        raise ValueError("failed capture cannot enter the frozen panel")
    detector = prediction["detector"]
    rows = raw_rows(raw)
    if detector["observation_ids"] != [str(row.envelope().identity.observation_id) for row in rows]:
        raise ValueError("detector observation lineage differs from raw capture")
    if detector["payload_sha256"] != [sha256(row.payload_bytes).hexdigest() for row in rows]:
        raise ValueError("detector payload lineage differs from raw capture")
    if sha256(masks).hexdigest() != detector["masks_npy_sha256"]:
        raise ValueError("native mask bytes differ from detector record")
    array = np.load(io.BytesIO(masks), allow_pickle=False)
    camera = detector["camera"]
    if (
        array.dtype != np.float32
        or array.shape != (detector["native_candidate_count"], camera["height"], camera["width"])
        or not np.isfinite(array).all()
        or np.any(array < 0)
        or np.any(array > 1)
    ):
        raise ValueError("frozen native masks are malformed")
    candidates = detector["candidates"]
    if len(candidates) != len(array) or [row["native_index"] for row in candidates] != list(
        range(len(array))
    ):
        raise ValueError("candidate and native-mask ordering differs")
    if detector["active_candidate_count"] != sum(
        row["detector_score"] >= detector["minimum_detector_score"] for row in candidates
    ):
        raise ValueError("active detector count differs")


def prepare(capture: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("manifest output must be new")
    result_path = capture / "result.json"
    result = load(result_path)
    if result["status"] != "COMPLETED" or result["failures"]:
        raise ValueError("only a completed capture can be frozen")
    if (
        len(result["steps"]) != result["budget"]
        or result["physical_dispatches"] != result["budget"]
    ):
        raise ValueError("capture action budget differs")
    sdk_by_owner: dict[str, Path] = {}
    sdk_root = capture / "transport/evaluator_only/sdk-events"
    for path in sorted(sdk_root.glob("*.json")):
        if not path.stem.isdigit():
            continue
        event = load(path)
        owner = event.get("owner")
        if owner is not None:
            if owner in sdk_by_owner:
                raise ValueError("duplicate evaluator action owner")
            sdk_by_owner[owner] = path
    frames = []
    for index, step in enumerate(result["steps"]):
        folder = capture / "public" / f"{index:03d}"
        raw_path = folder / "raw.json"
        prediction_path = folder / "prediction.json"
        masks_path = folder / "masks.npy.gz"
        raw, prediction = load(raw_path), load(prediction_path)
        masks = _mask_bytes(masks_path)
        _validate_frozen_frame(raw, prediction, masks)
        if raw["action_id"] != step["action_id"] or raw["action_id"] not in sdk_by_owner:
            raise ValueError("public and evaluator action lineage differs")
        sdk = sdk_by_owner[raw["action_id"]]
        instances = sdk.with_name(sdk.stem + "-instances.npz")
        instance_ids = sdk.with_name(sdk.stem + "-instances.json")
        boxes = sdk.with_name(sdk.stem + "-boxes.json")
        for required in (sdk, instances, instance_ids, boxes):
            if not required.is_file():
                raise ValueError(f"evaluator artifact missing: {required.name}")
        frames.append(
            dict(
                index=index,
                action_id=raw["action_id"],
                raw=str(raw_path.relative_to(capture)),
                raw_sha256=digest(raw_path),
                prediction=str(prediction_path.relative_to(capture)),
                prediction_sha256=digest(prediction_path),
                masks=str(masks_path.relative_to(capture)),
                masks_sha256=digest(masks_path),
                sdk=str(sdk.relative_to(capture)),
                sdk_sha256=digest(sdk),
                instances=str(instances.relative_to(capture)),
                instances_sha256=digest(instances),
                instance_ids=str(instance_ids.relative_to(capture)),
                instance_ids_sha256=digest(instance_ids),
                boxes=str(boxes.relative_to(capture)),
                boxes_sha256=digest(boxes),
            )
        )
    manifest = dict(
        schema=SCHEMA,
        capture_result_sha256=digest(result_path),
        schedule=result["schedule"],
        queries=result["queries"],
        budget=result["budget"],
        physical_dispatches=result["physical_dispatches"],
        frames=frames,
        detector_runs=1,
        inference_truth_isolation="SDK artifacts are evaluator-only",
    )
    manifest["input_sha256"] = content_sha256(manifest)
    save(output, manifest)
    return manifest


class FrozenDetector:
    def __init__(
        self,
        root: Path,
        manifest: dict[str, Any],
        *,
        duplicate_frame: int | None = None,
        duplicate_candidate: str | None = None,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.index = 0
        self.duplicate_frame = duplicate_frame
        self.duplicate_candidate = duplicate_candidate
        first = manifest["frames"][0]
        raw = load(checked(root, first["raw"], first["raw_sha256"]))
        rows = raw_rows(raw)
        detector = load(checked(root, first["prediction"], first["prediction_sha256"]))["detector"]
        identity = rows[0].envelope().identity
        self._scope = (identity.household_id, identity.session_id, identity.trace_id)
        self.model_id = detector["model_id"]
        self.weights_sha256 = detector["weights_sha256"]
        self._versions = (detector["torch_version"], detector["torchvision_version"])
        self._minimum_score = detector["minimum_detector_score"]

    def infer_surface(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> MaskSurfaceFrame:
        if self.index >= len(self.manifest["frames"]):
            raise ValueError("frozen detector panel exhausted")
        item = self.manifest["frames"][self.index]
        raw_path = checked(self.root, item["raw"], item["raw_sha256"])
        prediction_path = checked(self.root, item["prediction"], item["prediction_sha256"])
        masks_path = checked(self.root, item["masks"], item["masks_sha256"])
        raw = load(raw_path)
        frozen_rows = raw_rows(raw)
        if cutoff != datetime.fromisoformat(raw["received_at"]):
            raise ValueError("replay cutoff differs from frozen capture")
        if [row.envelope_json for row in observations] != [
            row.envelope_json for row in frozen_rows
        ] or [row.payload_bytes for row in observations] != [
            row.payload_bytes for row in frozen_rows
        ]:
            raise ValueError("replay observations differ from frozen bytes")
        record = deepcopy(load(prediction_path)["detector"])
        masks = _mask_bytes(masks_path)
        _validate_frozen_frame(raw, {"detector": record}, masks)
        if self.index == self.duplicate_frame:
            candidates = record["candidates"]
            selected = [
                row for row in candidates if row["candidate_id"] == self.duplicate_candidate
            ]
            if len(selected) != 1:
                raise ValueError("ambiguity control candidate is absent or duplicated")
            array = np.load(io.BytesIO(masks), allow_pickle=False)
            duplicate = deepcopy(selected[0])
            duplicate["candidate_id"] = str(
                uuid5(NAMESPACE_URL, duplicate["candidate_id"] + ":ambiguity-control")
            )
            duplicate["native_index"] = len(array)
            candidates.append(duplicate)
            array = np.concatenate((array, array[selected[0]["native_index"]][None]), axis=0)
            wire = io.BytesIO()
            np.save(wire, array, allow_pickle=False)
            masks = wire.getvalue()
            record["native_candidate_count"] += 1
            if duplicate["detector_score"] >= record["minimum_detector_score"]:
                record["active_candidate_count"] += 1
            record["masks_npy_sha256"] = sha256(masks).hexdigest()
            record["adversarial_control"] = dict(
                type="complete_duplicate_native_candidate",
                source_candidate_id=selected[0]["candidate_id"],
                duplicate_candidate_id=duplicate["candidate_id"],
            )
        self.index += 1
        return MaskSurfaceFrame(record=record, masks_npy=masks)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()


def replay(
    root: Path,
    manifest_path: Path,
    output: Path,
    *,
    arm: str,
    expected_sha: str,
    duplicate_frame: int | None = None,
    duplicate_candidate: str | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("replay output must be new")
    actual_sha = _head_sha()
    if actual_sha != expected_sha:
        raise ValueError(f"source checkout differs: {actual_sha}")
    manifest = load(manifest_path)
    if manifest.get("schema") != SCHEMA or manifest.get("input_sha256") != content_sha256(
        {k: v for k, v in manifest.items() if k != "input_sha256"}
    ):
        raise ValueError("manifest schema or content binding differs")
    if len(manifest["frames"]) != manifest["budget"]:
        raise ValueError("manifest frame budget differs")
    detector = FrozenDetector(
        root,
        manifest,
        duplicate_frame=duplicate_frame,
        duplicate_candidate=duplicate_candidate,
    )
    sequence = MaskSurfaceSequence(detector)  # type: ignore[arg-type]
    records: list[dict[str, Any]] = []
    action_ids: list[str] = []
    steps = []
    for item in manifest["frames"]:
        raw = load(checked(root, item["raw"], item["raw_sha256"]))
        rows = raw_rows(raw)
        record, _ = sequence.observe(rows, cutoff=datetime.fromisoformat(raw["received_at"]))
        records.append(record)
        action_ids.append(raw["action_id"])
        state = dict(
            view_sha256=content_sha256(record),
            records=records,
            history={},
            action_ids=action_ids,
        )
        reports = [
            report_from_surface_state(
                state,
                category=query["category"],
                ordinal=query["ordinal"],
                reference_action=action_ids[0],
            )
            for query in manifest["queries"]
        ]
        steps.append(
            dict(
                index=item["index"],
                action_id=item["action_id"],
                record=record,
                reports=reports,
            )
        )
    result = dict(
        schema=SCHEMA,
        status="COMPLETED",
        arm=arm,
        code_sha=actual_sha,
        source_file_sha256=digest(Path(str(sys.modules[MaskSurfaceSequence.__module__].__file__))),
        manifest_sha256=digest(manifest_path),
        input_sha256=manifest["input_sha256"],
        budget=manifest["budget"],
        source_physical_dispatches=manifest["physical_dispatches"],
        replay_physical_dispatches=0,
        queries=manifest["queries"],
        schedule=manifest["schedule"],
        detector_runs=0,
        control=(
            None
            if duplicate_frame is None
            else dict(
                type="adversarial_ambiguity",
                duplicate_frame=duplicate_frame,
                duplicate_candidate=duplicate_candidate,
                included_in_natural_score=False,
            )
        ),
        steps=steps,
    )
    save(output, result)
    return result


def _sdk_bundle(root: Path, item: dict[str, Any]) -> tuple[dict[str, Any], list[str], np.ndarray]:
    event = load(checked(root, item["sdk"], item["sdk_sha256"]))
    ids = load(checked(root, item["instance_ids"], item["instance_ids_sha256"]))
    path = checked(root, item["instances"], item["instances_sha256"])
    masks = np.load(path, allow_pickle=False)["masks"]
    if masks.dtype != np.bool_ or len(ids) != len(masks):
        raise ValueError("evaluator instance mask bundle is malformed")
    return event, ids, masks


def _instance_at(pixel: list[int] | None, ids: list[str], masks: np.ndarray) -> str | None:
    if pixel is None:
        return None
    u, v = pixel
    matches = [key for key, mask in zip(ids, masks, strict=True) if mask[v, u]]
    return matches[0] if len(matches) == 1 else None


def _bounds(event: dict[str, Any], object_id: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    objects = [row for row in event["metadata"]["objects"] if row["objectId"] == object_id]
    if len(objects) != 1:
        raise ValueError("evaluator target is absent or duplicated")
    corners = np.asarray(objects[0]["axisAlignedBoundingBox"]["cornerPoints"], dtype=float)
    if corners.shape != (8, 3) or not np.isfinite(corners).all():
        raise ValueError("target AABB is malformed")
    return tuple(corners.min(0)), tuple(corners.max(0))


def evaluate(
    root: Path, manifest_path: Path, replay_path: Path, targets_path: Path, output: Path
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("evaluation output must be new")
    manifest, result, targets = load(manifest_path), load(replay_path), load(targets_path)
    if result["status"] != "COMPLETED" or result["manifest_sha256"] != digest(manifest_path):
        raise ValueError("replay is incomplete or belongs to another manifest")
    if len(targets) != len(manifest["queries"]):
        raise ValueError("each query requires one predeclared evaluator target")
    first_raw = load(
        checked(root, manifest["frames"][0]["raw"], manifest["frames"][0]["raw_sha256"])
    )
    _first_event, first_ids, first_masks = _sdk_bundle(root, manifest["frames"][0])
    first_tracks = result["steps"][0]["record"]["tracks"]
    anchor_truth = {
        track["anchor_id"]: _instance_at(track["selected_pixel_uv"], first_ids, first_masks)
        for track in first_tracks
    }
    rows, track_rows = [], []
    for item, step in zip(manifest["frames"], result["steps"], strict=True):
        event, ids, masks = _sdk_bundle(root, item)
        raw = load(checked(root, item["raw"], item["raw_sha256"]))
        for query, report, target in zip(
            manifest["queries"], step["reports"], targets, strict=True
        ):
            task = ReportTask(
                task_id=uuid5(
                    NAMESPACE_URL, content_sha256((query, result["steps"][0]["action_id"]))
                ),
                scene_id=content_sha256(first_raw["observations"][2]["payload_base64"]),
                frame_id="unity-scene-world-x-right-y-up-z-forward",
                target_description=(
                    f"initial {query['category']} at zero-based x-order {query['ordinal']}"
                ),
                valid_at=datetime.fromisoformat(raw["received_at"]),
                initial_input_sha256=content_sha256(first_raw),
                allowed_actions_sha256=content_sha256(manifest["schedule"]),
                action_budget=manifest["budget"],
                position_origin_m=(0.0, 0.0, 0.0),
            )
            value = TargetPositionReport(
                task_sha256=task.digest,
                source_view_sha256=report["source_view_sha256"],
                status=report["status"],
                particle_id=UUID(report["anchor_id"]) if report["anchor_id"] else None,
                instance_hypothesis=report["anchor_id"],
                point_m=report["world_point_m"],
                observation_ids=tuple(UUID(value) for value in report["observation_ids"]),
                reason=report["reason"],
            )
            lower, upper = _bounds(event, target)
            truth = EvaluationTruth(
                task_sha256=task.digest,
                report_sha256=value.digest,
                annotation_artifact_sha256=content_sha256(
                    (item["sdk_sha256"], item["instances_sha256"], item["instance_ids_sha256"])
                ),
                target_instance_id=target,
                reported_instance_id=_instance_at(report["selected_pixel_uv"], ids, masks),
                lower_m=lower,
                upper_m=upper,
            )
            score = assess_report(task, value, truth)
            rows.append(
                dict(
                    step_index=step["index"],
                    query=query,
                    target_instance_id=target,
                    report=report,
                    score=score.model_dump(mode="json"),
                )
            )
        for track in step["record"]["tracks"]:
            expected = anchor_truth.get(track["anchor_id"])
            actual = _instance_at(track["selected_pixel_uv"], ids, masks)
            point = track["world_point_m"]
            position = None
            if expected is not None and point is not None:
                lower, upper = _bounds(event, expected)
                position = all(lo <= x <= hi for x, lo, hi in zip(point, lower, upper, strict=True))
            track_rows.append(
                dict(
                    step_index=step["index"],
                    anchor_id=track["anchor_id"],
                    status=track["status"],
                    identity_status=track["identity_status"],
                    query_eligible=track.get("query_eligible", track["anchor_id"] in anchor_truth),
                    birth_frame=track.get("birth_frame", 0),
                    reidentification=track.get("reidentification"),
                    expected_instance_id=expected,
                    reported_instance_id=actual,
                    identity_correct=None
                    if expected is None or actual is None
                    else expected == actual,
                    position_correct=position,
                    joint_success=(
                        None
                        if expected is None or actual is None or position is None
                        else expected == actual and position
                    ),
                )
            )
    evaluation = dict(
        schema=SCHEMA,
        status="EVALUATED",
        arm=result["arm"],
        control=result["control"],
        replay_sha256=digest(replay_path),
        manifest_sha256=digest(manifest_path),
        task_slots=len(rows),
        identity_correct=sum(row["score"]["identity_correct"] is True for row in rows),
        position_correct=sum(row["score"]["position_correct"] is True for row in rows),
        joint_success=sum(row["score"]["joint_success"] is True for row in rows),
        rows=rows,
        track_rows=track_rows,
        anchor_truth=anchor_truth,
    )
    save(output, evaluation)
    return evaluation


def _first_accepted_control(result: dict[str, Any]) -> tuple[int, str]:
    accepted = []
    for step in result["steps"]:
        for track in step["record"]["tracks"]:
            detail = track.get("reidentification")
            if detail and detail.get("status") == "ACCEPTED_UNIQUE_REIDENTIFICATION":
                accepted.append((step["index"], detail["candidate_id"]))
    if not accepted:
        raise ValueError("natural replay has no accepted reidentification for ambiguity control")
    return accepted[0]


def diagnose(
    root: Path,
    manifest_path: Path,
    replay_path: Path,
    evaluation_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Measure SDK-instance composition of every accepted native detector mask."""
    if output.exists():
        raise ValueError("diagnostic output must be new")
    manifest, replay_result, evaluation = (
        load(manifest_path),
        load(replay_path),
        load(evaluation_path),
    )
    if (
        replay_result["status"] != "COMPLETED"
        or evaluation["status"] != "EVALUATED"
        or replay_result["manifest_sha256"] != digest(manifest_path)
        or evaluation["manifest_sha256"] != digest(manifest_path)
        or evaluation["replay_sha256"] != digest(replay_path)
    ):
        raise ValueError("diagnostic inputs do not share one completed frozen replay")
    accepted_rows = [
        row
        for row in evaluation["track_rows"]
        if row.get("reidentification")
        and row["reidentification"].get("status") == "ACCEPTED_UNIQUE_REIDENTIFICATION"
    ]
    rows = []
    for row in accepted_rows:
        frame = manifest["frames"][row["step_index"]]
        prediction = load(checked(root, frame["prediction"], frame["prediction_sha256"]))[
            "detector"
        ]
        candidates = [
            candidate
            for candidate in prediction["candidates"]
            if candidate["candidate_id"] == row["reidentification"]["candidate_id"]
        ]
        if len(candidates) != 1:
            raise ValueError("accepted candidate is absent or duplicated in frozen prediction")
        candidate = candidates[0]
        mask_bytes = _mask_bytes(checked(root, frame["masks"], frame["masks_sha256"]))
        probabilities = np.load(io.BytesIO(mask_bytes), allow_pickle=False)
        predicted_mask = probabilities[candidate["native_index"]] >= prediction["mask_threshold"]
        _event, ids, instance_masks = _sdk_bundle(root, frame)
        pixels = int(predicted_mask.sum())
        composition = []
        for object_id, instance_mask in zip(ids, instance_masks, strict=True):
            intersection = int((predicted_mask & instance_mask).sum())
            if intersection:
                composition.append(
                    dict(
                        instance_id=object_id,
                        intersection_pixels=intersection,
                        fraction_of_predicted_mask=intersection / pixels,
                    )
                )
        composition.sort(key=lambda item: (-item["intersection_pixels"], item["instance_id"]))
        selected_pixel = next(
            track["selected_pixel_uv"]
            for step in replay_result["steps"]
            if step["index"] == row["step_index"]
            for track in step["record"]["tracks"]
            if track["anchor_id"] == row["anchor_id"]
        )
        rows.append(
            dict(
                step_index=row["step_index"],
                anchor_id=row["anchor_id"],
                expected_instance_id=row["expected_instance_id"],
                reported_instance_id=row["reported_instance_id"],
                identity_correct=row["identity_correct"],
                position_correct=row["position_correct"],
                candidate_id=candidate["candidate_id"],
                candidate_category=candidate["category"],
                detector_score=candidate["detector_score"],
                selected_pixel_uv=selected_pixel,
                selected_pixel_instance_id=_instance_at(selected_pixel, ids, instance_masks),
                predicted_mask_pixels=pixels,
                instance_composition=composition,
                reidentification=row["reidentification"],
            )
        )
    result = dict(
        schema=SCHEMA,
        status="DIAGNOSED",
        truth_usage="offline evaluation only; no SDK value enters replay inference",
        manifest_sha256=digest(manifest_path),
        replay_sha256=digest(replay_path),
        evaluation_sha256=digest(evaluation_path),
        accepted_reidentifications=len(rows),
        rows=rows,
    )
    save(output, result)
    return result


def summarize(
    baseline_a: Path,
    baseline_b: Path,
    candidate_a: Path,
    candidate_b: Path,
    baseline_eval: Path,
    candidate_eval: Path,
    ambiguity_replay: Path,
    ambiguity_eval: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("summary output must be new")
    base, cand, ambiguity = load(baseline_a), load(candidate_a), load(ambiguity_replay)
    base_score, cand_score, ambiguity_score = (
        load(baseline_eval),
        load(candidate_eval),
        load(ambiguity_eval),
    )
    if not all(
        row["input_sha256"] == base["input_sha256"]
        and row["schedule"] == base["schedule"]
        and row["queries"] == base["queries"]
        and row["budget"] == base["budget"]
        for row in (cand, ambiguity)
    ):
        raise ValueError("arms do not share frozen inputs, tasks and action budget")
    deterministic = dict(
        baseline=digest(baseline_a) == digest(baseline_b),
        candidate=digest(candidate_a) == digest(candidate_b),
    )
    base_tracks = {(row["step_index"], row["anchor_id"]): row for row in base_score["track_rows"]}
    recoveries = []
    false_reidentifications = []
    unadjudicated_reidentifications = []
    for row in cand_score["track_rows"]:
        detail = row["reidentification"]
        if not detail or detail.get("status") != "ACCEPTED_UNIQUE_REIDENTIFICATION":
            continue
        previous = base_tracks.get((row["step_index"], row["anchor_id"]))
        item = dict(candidate=row, baseline=previous)
        if row["identity_correct"] is False:
            false_reidentifications.append(item)
        if row["identity_correct"] is None:
            unadjudicated_reidentifications.append(item)
        if (
            previous is not None
            and previous["status"] == "LOST_NO_REINITIALIZATION"
            and row["joint_success"] is True
        ):
            recoveries.append(item)
    base_query = {
        (row["step_index"], tuple(row["query"].items())): row for row in base_score["rows"]
    }
    regressions = [
        dict(candidate=row, baseline=base_query[(row["step_index"], tuple(row["query"].items()))])
        for row in cand_score["rows"]
        if base_query[(row["step_index"], tuple(row["query"].items()))]["score"]["joint_success"]
        is True
        and row["score"]["joint_success"] is not True
    ]
    late = [row for row in cand_score["track_rows"] if row["birth_frame"] > 0]
    late_anchors = {row["anchor_id"] for row in late}
    late_isolation = (
        bool(late)
        and all(not row["query_eligible"] for row in late)
        and not any(row["report"]["anchor_id"] in late_anchors for row in cand_score["rows"])
    )
    ambiguity_frame = ambiguity["control"]["duplicate_frame"]
    ambiguity_rows = [
        row
        for row in ambiguity_score["track_rows"]
        if row["step_index"] == ambiguity_frame
        and row["status"] == "UNKNOWN_AMBIGUOUS_REIDENTIFICATION"
    ]
    ambiguity_accepted = [
        row
        for row in ambiguity_score["track_rows"]
        if row["step_index"] == ambiguity_frame
        and row["reidentification"]
        and row["reidentification"].get("status") == "ACCEPTED_UNIQUE_REIDENTIFICATION"
    ]
    ambiguity_passed = bool(ambiguity_rows) and not ambiguity_accepted
    gates = dict(
        deterministic_replay=all(deterministic.values()),
        natural_joint_recovery=bool(recoveries),
        query_level_joint_gain=cand_score["joint_success"] > base_score["joint_success"],
        zero_false_reidentification=not false_reidentifications,
        all_reidentifications_adjudicated=not unadjudicated_reidentifications,
        zero_query_regression=not regressions,
        ambiguity_rejected=ambiguity_passed,
        late_birth_isolated=late_isolation,
    )
    summary = dict(
        schema=SCHEMA,
        status="PASS" if all(gates.values()) else "FAIL",
        gates=gates,
        deterministic=deterministic,
        matched_input_sha256=base["input_sha256"],
        action_budget=base["budget"],
        source_physical_dispatches=base["source_physical_dispatches"],
        task_score=dict(
            baseline={
                k: base_score[k]
                for k in ("task_slots", "identity_correct", "position_correct", "joint_success")
            },
            candidate={
                k: cand_score[k]
                for k in ("task_slots", "identity_correct", "position_correct", "joint_success")
            },
        ),
        natural_joint_recoveries=recoveries,
        false_reidentifications=false_reidentifications,
        unadjudicated_reidentifications=unadjudicated_reidentifications,
        query_regressions=regressions,
        late_birth_rows=late,
        ambiguity_rows=ambiguity_rows,
        scope="single-house matched transition death test; not general scientific acceptance",
    )
    save(output, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("capture", type=Path)
    command.add_argument("output", type=Path)
    command = commands.add_parser("replay")
    command.add_argument("root", type=Path)
    command.add_argument("manifest", type=Path)
    command.add_argument("output", type=Path)
    command.add_argument("--arm", required=True)
    command.add_argument("--expected-sha", required=True)
    command.add_argument("--ambiguity-from", type=Path)
    command = commands.add_parser("evaluate")
    command.add_argument("root", type=Path)
    command.add_argument("manifest", type=Path)
    command.add_argument("replay", type=Path)
    command.add_argument("targets", type=Path)
    command.add_argument("output", type=Path)
    command = commands.add_parser("diagnose")
    command.add_argument("root", type=Path)
    command.add_argument("manifest", type=Path)
    command.add_argument("replay", type=Path)
    command.add_argument("evaluation", type=Path)
    command.add_argument("output", type=Path)
    command = commands.add_parser("summarize")
    for name in (
        "baseline_a",
        "baseline_b",
        "candidate_a",
        "candidate_b",
        "baseline_eval",
        "candidate_eval",
        "ambiguity_replay",
        "ambiguity_eval",
        "output",
    ):
        command.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.capture, args.output)
    elif args.mode == "replay":
        duplicate_frame = duplicate_candidate = None
        if args.ambiguity_from:
            duplicate_frame, duplicate_candidate = _first_accepted_control(
                load(args.ambiguity_from)
            )
        replay(
            args.root,
            args.manifest,
            args.output,
            arm=args.arm,
            expected_sha=args.expected_sha,
            duplicate_frame=duplicate_frame,
            duplicate_candidate=duplicate_candidate,
        )
    elif args.mode == "evaluate":
        evaluate(args.root, args.manifest, args.replay, args.targets, args.output)
    elif args.mode == "diagnose":
        diagnose(args.root, args.manifest, args.replay, args.evaluation, args.output)
    else:
        summarize(
            args.baseline_a,
            args.baseline_b,
            args.candidate_a,
            args.candidate_b,
            args.baseline_eval,
            args.candidate_eval,
            args.ambiguity_replay,
            args.ambiguity_eval,
            args.output,
        )


if __name__ == "__main__":
    main()
