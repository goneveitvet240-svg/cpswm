"""Public pixel-pair features followed by separately bound private supervision.

The driver owns external input pins, complete 96-frame scheduling and train-only
fit order. This module never opens files, selects an instance or maps categories.
SDK masks describe rendered membership, not physical surface identity.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from dataclasses import asdict, fields, replace
from datetime import datetime
from uuid import UUID

import numpy as np
from offline_frontend_evaluation import _audit_rows, _xyz
from run_instance_correspondence_diagnostic import reconstruct_catalog

from cpswm.data_preflight.instance_affinity import grid_pixels, pair_features, pixel_pairs
from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame, decode_rgb
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd, surface_support
from cpswm.system.owned_visual_support import _frame_support
from cpswm.system.reproducibility import canonical_json, content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery

METHODS = ("fasterrcnn", "ssdlite")
# One exclusive pair reason, in this order. Point-level audit retains all members.
VOID_PRIORITY = ("invalid_depth", "ambiguous_membership", "unmapped_pixel", "ineligible_instance")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _plain(value):
    return json.loads(canonical_json(value))


def _visual_frame(value):
    _require(
        type(value) is dict and set(value) == {f.name for f in fields(VisualFrame)},
        "public VisualFrame fields differ",
    )
    row = copy.deepcopy(value)
    for key in ("observation_id", "household_id", "session_id", "trace_id"):
        row[key] = UUID(row[key])
    for key in ("capture_time", "arrival_time", "inference_cutoff"):
        row[key] = datetime.fromisoformat(row[key])
    _require(type(row["candidates"]) is list, "public candidates must be a list")
    candidates = []
    for candidate in row["candidates"]:
        _require(
            type(candidate) is dict
            and set(candidate) == {f.name for f in fields(DetectionCandidate)},
            "public candidate fields differ",
        )
        candidates.append(
            DetectionCandidate(
                UUID(candidate["candidate_id"]),
                candidate["category"],
                candidate["detector_score"],
                tuple(candidate["box_xyxy"]),
            )
        )
    row["candidates"] = tuple(candidates)
    result = VisualFrame(**row)
    _require(_plain(asdict(result)) == value, "public frame conversion changes input")
    return result


def public_frame(command, delivery, frontends: dict[str, dict]) -> dict:
    """Build all deduplicated public pairs; no labels or partition arguments.

    Returned command/delivery/frontends/camera are in-memory provenance only.
    Only X is the model input. candidates and public_metadata are JSON-compatible;
    public_metadata contains no house partition. pixel_count counts sampled grid
    pixels; box_pixel_count separately counts every image pixel inside the box.
    """
    _require(
        type(command) is ObservationCommand
        and type(delivery) is ObservationDelivery
        and delivery.success is True
        and delivery.error == ""
        and command.action_id == delivery.action_id,
        "invalid public command/delivery",
    )
    _require(
        type(frontends) is dict and set(frontends) == set(METHODS), "both fixed frontends required"
    )
    camera, depth = decode_unity_rgbd(delivery.observations, cutoff=delivery.received_at)
    _, rgb = decode_rgb(delivery.observations[0], cutoff=delivery.received_at)
    _require(
        camera.action_id == command.action_id
        and command.decision_time <= camera.capture_time <= delivery.received_at,
        "public camera ownership or chronology differs",
    )
    candidate_rows, pair_sources = [], set()
    source_records = {}
    for method in METHODS:
        entry = frontends[method]
        _require(
            type(entry) is dict and set(entry) == {"command", "frame", "decoder_binding"},
            "public frontend entry fields differ",
        )
        _require(entry["command"] == _plain(asdict(command)), "public frontend command differs")
        _require(
            type(entry["decoder_binding"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", entry["decoder_binding"]) is not None,
            "invalid frontend decoder binding",
        )
        _require(type(entry["frame"]) is dict and "frame" in entry["frame"], "missing public frame")
        visual = _visual_frame(entry["frame"]["frame"])
        support = replace(
            _frame_support(delivery.observations[0], visual, delivery.received_at),
            geometry=surface_support(delivery.observations, visual, cutoff=delivery.received_at),
        )
        _require(
            content_sha256(_plain(asdict(support))) == content_sha256(entry["frame"]),
            "public frontend support differs from actual RGB-D/camera",
        )
        for candidate, surface in zip(visual.candidates, support.geometry.candidates, strict=True):
            pixels = grid_pixels(candidate.box_xyxy, camera.width, camera.height)
            pairs = [tuple(int(v) for v in row) for row in pixel_pairs(pixels)]
            pair_sources.update(pairs)
            candidate_rows.append(
                dict(
                    method=method,
                    id=str(candidate.candidate_id),
                    box=list(candidate.box_xyxy),
                    pixel_count=len(pixels),
                    box_pixel_count=surface.box_pixel_count,
                    _pairs=pairs,
                )
            )
        source_records[method] = dict(
            entry_sha256=content_sha256(entry),
            decoder_binding=entry["decoder_binding"],
            model_id=visual.model_id,
            weights_sha256=visual.weights_sha256,
            torch_version=visual.torch_version,
            torchvision_version=visual.torchvision_version,
            minimum_score=visual.minimum_score,
        )
    ordered = sorted(pair_sources)
    pairs = np.asarray(ordered, dtype=np.int64).reshape((-1, 4))
    lookup = {pair: index for index, pair in enumerate(ordered)}
    for row in candidate_rows:
        row["pair_indices"] = [lookup[pair] for pair in row.pop("_pairs")]
    X, valid = pair_features(rgb, depth, camera, pairs)
    _require(
        X.dtype == np.float64
        and X.shape == (len(pairs), 8)
        and np.isfinite(X).all()
        and valid.dtype == np.bool_
        and valid.shape == (len(pairs),),
        "invalid public pair feature contract",
    )
    for array in (rgb, depth, X, pairs, valid):
        array.flags.writeable = False
    metadata = dict(
        action_id=str(command.action_id),
        command=_plain(asdict(command)),
        camera=camera.model_dump(mode="json"),
        observation_ids=[
            str(raw.envelope().identity.observation_id) for raw in delivery.observations
        ],
        payload_sha256=[raw.envelope().payload.payload_sha256 for raw in delivery.observations],
        receipt_sha256=delivery.observations[0].capture_receipt_sha256,
        sources=source_records,
        candidate_count=len(candidate_rows),
        pair_count=len(pairs),
        feature_columns=8,
        semantic_mapping=False,
        instance_labels_used=False,
    )
    return dict(
        action_id=str(command.action_id),
        command=command,
        delivery=delivery,
        frontends=copy.deepcopy(frontends),
        camera=camera,
        rgb=rgb,
        depth=depth,
        X=X,
        pairs=pairs,
        valid=valid,
        candidates=candidate_rows,
        public_metadata=metadata,
    )


def _recheck_public(record):
    fresh = public_frame(record["command"], record["delivery"], record["frontends"])
    _require(set(record) == set(fresh), "public record fields differ")
    for key in ("rgb", "depth", "X", "pairs", "valid"):
        actual, expected = record[key], fresh[key]
        _require(
            type(actual) is np.ndarray
            and actual.dtype == expected.dtype
            and np.array_equal(actual, expected),
            "public record " + key + " differs from reconstructed sensors/candidates",
        )
    for key in ("action_id", "camera", "candidates", "public_metadata"):
        _require(record[key] == fresh[key], "public record " + key + " differs")
    return fresh


def label_frame(
    public_record,
    sdk,
    info,
    masks,
    segmentation,
    eligibility,
    *,
    sdk_rgb_bytes: bytes,
    sdk_depth_bytes: bytes,
) -> dict:
    """Attach same=1/different=0 only to two uniquely eligible rendered members.

    Every other pair is VOID=-1. The exclusive reason priority is VOID_PRIORITY;
    counts sum to VOID. Whole SDK catalogs and point memberships remain auditable.
    Original same-event NPY bytes are mandatory, not a caller-provided digest.
    """
    public = _recheck_public(public_record)
    command, delivery, camera = public["command"], public["delivery"], public["camera"]
    _require(
        type(sdk_rgb_bytes) is bytes
        and type(sdk_depth_bytes) is bytes
        and sdk_rgb_bytes == delivery.observations[0].payload_bytes
        and sdk_depth_bytes == delivery.observations[1].payload_bytes,
        "private SDK RGB-D bytes differ from public capture",
    )
    metadata = sdk["metadata"]
    requested = dict(action=command.action)
    if command.action != "Pass":
        requested["degrees"] = command.degrees
    _require(
        info["action_id"] == sdk["owner"] == str(command.action_id)
        and sdk["requested"] == requested
        and metadata["lastAction"] == command.action
        and metadata["lastActionSuccess"] is True,
        "private SDK action ownership or result differs",
    )
    _require(
        camera.position_m == _xyz(metadata["cameraPosition"])
        and camera.yaw_degrees == metadata["agent"]["rotation"]["y"]
        and camera.pitch_degrees == metadata["agent"]["cameraHorizon"]
        and camera.vertical_fov_degrees == metadata["fov"]
        and segmentation.shape == (camera.height, camera.width, 3)
        and info["colors"] == metadata["colors"],
        "private SDK camera or segmentation source differs",
    )
    instances = reconstruct_catalog(
        info["catalog"], info["colors"], masks, segmentation, metadata["objects"]
    )
    objects = {row["objectId"]: row for row in metadata["objects"]}
    audits = _audit_rows(eligibility, objects)
    for row in instances:
        audit = audits[row["object_id"]]
        row.update(
            eligible=audit["eligible"],
            exclusion_reasons=copy.deepcopy(audit["exclusion_reasons"]),
            eligibility=copy.deepcopy(audit),
        )
    points = sorted(
        {tuple(int(v) for v in point) for pair in public["pairs"] for point in (pair[:2], pair[2:])}
    )
    point_members, point_lookup = [], {}
    for u, v in points:
        members = sorted(row["object_id"] for row in instances if masks[row["array_key"]][v, u])
        eligible_ids = [identity for identity in members if audits[identity]["eligible"]]
        point_lookup[(u, v)] = len(point_members)
        point_members.append(
            dict(pixel_uv=[u, v], object_ids=members, eligible_object_ids=eligible_ids)
        )
    pair_point_indices = np.asarray(
        [
            [point_lookup[tuple(pair[:2])], point_lookup[tuple(pair[2:])]]
            for pair in public["pairs"]
        ],
        dtype=np.int64,
    ).reshape((-1, 2))
    targets = np.full(len(public["pairs"]), -1, dtype=np.int8)
    reasons = Counter({key: 0 for key in VOID_PRIORITY})
    for index, (left_index, right_index) in enumerate(pair_point_indices):
        ends = [point_members[left_index], point_members[right_index]]
        if not public["valid"][index]:
            reason = "invalid_depth"
        elif any(len(end["object_ids"]) > 1 for end in ends):
            reason = "ambiguous_membership"
        elif any(not end["object_ids"] for end in ends):
            reason = "unmapped_pixel"
        elif any(not end["eligible_object_ids"] for end in ends):
            reason = "ineligible_instance"
        else:
            targets[index] = int(ends[0]["object_ids"] == ends[1]["object_ids"])
            continue
        reasons[reason] += 1
    _require(sum(reasons.values()) == int((targets == -1).sum()), "VOID accounting differs")
    targets.flags.writeable = False
    pair_point_indices.flags.writeable = False
    return dict(
        action_id=public["action_id"],
        targets=targets,
        pair_point_indices=pair_point_indices,
        point_members=point_members,
        void_reasons=dict(reasons),
        void_reason_priority=list(VOID_PRIORITY),
        instances=instances,
        supervision="unique_eligible_rendered_instance_membership",
        semantic_category_mapping=False,
        formal_position_reference_selected=False,
    )
