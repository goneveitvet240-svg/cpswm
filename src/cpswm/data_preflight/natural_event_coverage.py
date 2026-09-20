"""Evaluator-only HO-Cap supervision inventory; never a semantic producer.

Joint proximity and object displacement are measurements, not contact labels.
One subject with two hands is not two actors. Missing annotations stay unknown.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from typing import Any

import numpy as np


def pinned_bytes(payload: bytes, expected: str) -> bytes:
    if len(expected) != 64 or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("source content differs from its external SHA256 pin")
    return payload


def inspect_annotation(payload: bytes, *, expected_sha256: str) -> dict[str, Any]:
    """Inventory author measurements, treating -1 hand/pose sentinels as absent."""
    pinned_bytes(payload, expected_sha256)
    if not 0 < len(payload) <= 4 * 1024 * 1024:
        raise ValueError("bounded annotation required")
    required = {
        "cam_K",
        "obj_poses",
        "hand_joints_3d",
        "hand_joints_2d",
        "seg_mask",
        "obj_class_inds",
        "obj_class_names",
    }
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len({m.filename for m in members}) != len(members):
            raise ValueError("duplicate annotation member")
        if sum(m.file_size for m in members) > 8 * 1024 * 1024:
            raise ValueError("annotation decompression exceeds budget")
        if not {k + ".npy" for k in required} <= {m.filename for m in members}:
            raise ValueError("required supervision fields missing")
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        names = data["obj_class_names"]
        poses = data["obj_poses"]
        hands = data["hand_joints_3d"]
        hands2d = data["hand_joints_2d"]
        mask = data["seg_mask"]
        camera = data["cam_K"]
        if names.ndim != 1 or names.dtype.kind != "U" or not 1 <= len(names) <= 255:
            raise ValueError("invalid class names")
        categories = names.tolist()
        if len(set(categories)) != len(categories) or any(not x for x in categories):
            raise ValueError("duplicate/empty class names")
        objects = [x for x in categories if x not in {"RIGHT_HAND", "LEFT_HAND"}]
        if categories[: len(objects)] != objects:
            raise ValueError("unverified pose-to-name ordering")
        if (
            poses.shape != (len(objects), 4, 4)
            or hands.shape != (2, 21, 3)
            or hands2d.shape != (2, 21, 2)
            or mask.shape != (480, 640)
            or mask.dtype != np.uint8
            or camera.shape != (3, 3)
            or int(mask.max()) > len(categories)
        ):
            raise ValueError("invalid author measurement shape/mapping")
        if not np.isfinite(camera).all() or camera[0, 0] <= 0 or camera[1, 1] <= 0:
            raise ValueError("invalid camera intrinsics")
        rows = []
        for i, name in enumerate(objects):
            pose = poses[i]
            missing = bool(np.all(pose == -1))
            if not missing and (
                not np.isfinite(pose).all()
                or not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-5)
                or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-4)
                or not np.isclose(np.linalg.det(pose[:3, :3]), 1, atol=1e-4)
            ):
                raise ValueError("invalid rigid object pose")
            rows.append(
                dict(
                    name=name,
                    visible_pixels=int(np.count_nonzero(mask == i + 1)),
                    pose_present=not missing,
                    camera_translation_m=None if missing else pose[:3, 3].tolist(),
                    rotation=None if missing else pose[:3, :3].tolist(),
                )
            )
        hand_rows = []
        for i, side in enumerate(("RIGHT_HAND", "LEFT_HAND")):
            valid = np.isfinite(hands[i]).all(axis=1) & ~(hands[i] == -1).all(axis=1)
            visible = (
                np.isfinite(hands2d[i]).all(axis=1)
                & (hands2d[i, :, 0] >= 0)
                & (hands2d[i, :, 0] < 640)
                & (hands2d[i, :, 1] >= 0)
                & (hands2d[i, :, 1] < 480)
            )
            hand_rows.append(
                dict(
                    side=side,
                    valid_3d_joints=int(valid.sum()),
                    in_image_2d_joints=int((visible & valid).sum()),
                    person_identity="NOT_PROVIDED_BY_HAND_SIDE",
                )
            )
        return dict(
            objects=rows,
            hands=hand_rows,
            annotation_fields=sorted(data.files),
            semantic_event_labels={
                k: "NOT_PROVIDED"
                for k in ("pickup", "move", "release", "interperson_handoff", "correction")
            },
            annotation_sha256=expected_sha256,
            evidence_lane="EVALUATOR_ONLY_NO_RUNTIME_AUTHORITY",
        )


def pose_pair_diagnostic(
    before: dict[str, Any], after: dict[str, Any], *, frame_gap: int
) -> dict[str, Any]:
    """Describe endpoint displacement; never infer a hidden event from its endpoints."""
    if type(frame_gap) is not int or frame_gap <= 0:
        raise ValueError("strictly forward frame indices required")
    old = {x["name"]: x for x in before["objects"]}
    if set(old) != {x["name"] for x in after["objects"]}:
        raise ValueError("object scope changed")
    rows = []
    for item in after["objects"]:
        prev = old[item["name"]]
        available = prev["pose_present"] and item["pose_present"]
        translation = angle = None
        if available:
            translation = float(
                np.linalg.norm(
                    np.asarray(item["camera_translation_m"]) - prev["camera_translation_m"]
                )
            )
            rotation = np.asarray(prev["rotation"]).T @ np.asarray(item["rotation"])
            angle = float(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1)))
        rows.append(
            dict(name=item["name"], endpoint_distance_m=translation, endpoint_angle_rad=angle)
        )
    return dict(
        frame_gap=frame_gap,
        contiguous=frame_gap == 1,
        objects=rows,
        event_classification="UNRESOLVED",
        physical_duration_seconds=None,
    )
