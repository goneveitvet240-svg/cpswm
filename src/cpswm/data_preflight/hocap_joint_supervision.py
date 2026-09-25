"""Source-bound author pose supervision, kept outside the runtime input lane.

Checks the published per-image poses against independently stored sequence pose
arrays and camera calibration. This verifies correspondence, not annotation
accuracy, contact truth, an observation noise model, or full proposal labels.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import yaml  # type: ignore[import-untyped]
from PIL import Image
from scipy.spatial.transform import Rotation  # type: ignore[import-untyped]

NUMERICAL_TOLERANCE = 1e-5  # float32 serialization check, not a scientific gate
AUTHOR_REVISION = "576c63ebf3b84dfec8744ba0f021234213bf0dab"


def strict_json(data: bytes) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out

    return json.loads(data, object_pairs_hook=pairs)


def pinned_bytes(root: Path, name: str, expected: str | None = None) -> bytes:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("missing or escaping source path")
    data = path.read_bytes()
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("source SHA256 mismatch: " + name)
    return data


def checked_transform(value: Any) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (4, 4) or not np.isfinite(result).all():
        raise ValueError("invalid pose shape or values")
    rotation = result[:3, :3]
    if (
        np.max(np.abs(result[3] - [0, 0, 0, 1])) > NUMERICAL_TOLERANCE
        or np.max(np.abs(rotation.T @ rotation - np.eye(3))) > NUMERICAL_TOLERANCE
        or abs(np.linalg.det(rotation) - 1) > NUMERICAL_TOLERANCE
    ):
        raise ValueError("non-rigid pose; do not repair author truth silently")
    return result


def pose_supervision(
    label: bytes,
    *,
    metadata: dict[str, Any],
    intrinsics: dict[str, Any],
    extrinsics: dict[str, Any],
    sequence_poses: np.ndarray,
    frame: int,
    camera: str,
) -> dict[str, Any]:
    if type(frame) is not int or not 0 <= frame < metadata["num_frames"]:
        raise ValueError("invalid frame index")
    if camera not in metadata["realsense"]["serials"] or intrinsics["serial"] != camera:
        raise ValueError("camera identity differs from metadata")
    names = metadata["object_ids"]
    if not names or len(names) != len(set(names)):
        raise ValueError("object support must be unique")
    if sequence_poses.shape != (len(names), metadata["num_frames"], 7):
        raise ValueError("sequence pose array does not cover object/frame domain")
    with zipfile.ZipFile(io.BytesIO(label)) as archive:
        infos = archive.infolist()
        if (
            len({i.filename for i in infos}) != len(infos)
            or any(i.file_size > 4 * 1024 * 1024 for i in infos)
            or sum(i.file_size for i in infos) > 16 * 1024 * 1024
        ):
            raise ValueError("duplicate or oversized label arrays")
    with np.load(io.BytesIO(label), allow_pickle=False) as data:
        poses = np.asarray(data["obj_poses"], dtype=float)
        mask = data["seg_mask"]
        class_names, ids = data["obj_class_names"], data["obj_class_inds"]
        color = intrinsics["color"]
        expected_k = np.array(
            [[color["fx"], 0, color["ppx"]], [0, color["fy"], color["ppy"]], [0, 0, 1]]
        )
        if (
            poses.shape != (len(names), 4, 4)
            or class_names.ndim != 1
            or class_names.dtype.kind != "U"
            or list(class_names[: len(names)]) != names
            or any(n not in {"LEFT_HAND", "RIGHT_HAND"} for n in class_names[len(names) :])
            or ids.shape != class_names.shape
            or ids.dtype.kind not in "iu"
            or len(set(class_names.tolist())) != len(class_names)
            or len(set(ids.tolist())) != len(ids)
            or mask.dtype != np.uint8
            or mask.shape != (color["height"], color["width"])
            or int(mask.max()) > len(class_names)
            or data["cam_K"].shape != (3, 3)
            or not np.isfinite(data["cam_K"]).all()
            or not np.allclose(data["cam_K"], expected_k, atol=NUMERICAL_TOLERANCE, rtol=0)
        ):
            raise ValueError("label object order, mask or camera intrinsics mismatch")
        visible = [int(np.count_nonzero(mask == i + 1)) for i in range(len(names))]
    values = extrinsics["extrinsics"]

    def extrinsic(key: str) -> np.ndarray:
        return checked_transform(np.vstack([np.asarray(values[key]).reshape(3, 4), [0, 0, 0, 1]]))

    # Author SequenceLoader: camera_to_world = inverse(tag_1) @ camera_to_master.
    world_to_camera = np.linalg.inv(extrinsic(camera)) @ extrinsic("tag_1")
    output = []
    for i, name in enumerate(names):
        q = np.asarray(sequence_poses[i, frame], dtype=float)
        if not np.isfinite(q).all() or abs(np.linalg.norm(q[:4]) - 1) > NUMERICAL_TOLERANCE:
            raise ValueError("invalid author quaternion; no inferred orientation")
        world = np.eye(4)
        world[:3, :3], world[:3, 3] = Rotation.from_quat(q[:4]).as_matrix(), q[4:]
        observed = checked_transform(poses[i])
        discrepancy = float(np.max(np.abs(world_to_camera @ world - observed)))
        if discrepancy > NUMERICAL_TOLERANCE:
            raise ValueError("per-image pose differs from sequence frame/object/calibration")
        output.append(
            {
                "object_id": name,
                "class_index": int(ids[i]),
                "pose_object_to_camera": observed.tolist(),
                "pose_object_to_author_world": world.tolist(),
                "quaternion_xyzw_world": q[:4].tolist(),
                "position_m_world": q[4:].tolist(),
                "visible_mask_pixels": visible[i],
                "cross_file_max_abs": discrepancy,
            }
        )
    return {
        "objects": output,
        "coordinate_rule": "inverse(camera_to_master) @ tag_1 @ pose_world",
        "annotation_kind": "author_optimized_pose_not_independent_mocap",
        "contact_gold": False,
        "actor_world_identity": None,
        "measurement_noise_calibrated": False,
        "native_operation_labels": [],
    }


def assemble_subset(
    root: Path, *, raw_sha256: str, annotation_sha256: str, receipts_sha256: str
) -> dict[str, Any]:
    raw = strict_json(pinned_bytes(root, "raw_manifest.json", raw_sha256))
    annotations = strict_json(pinned_bytes(root, "annotation_manifest.json", annotation_sha256))
    receipts = strict_json(pinned_bytes(root, "download_receipts.json", receipts_sha256))
    by_member: dict[str, str] = {}
    exact_receipts: dict[str, dict[str, Any]] = {}
    redundant_receipts = 0
    for receipt in receipts:
        name = receipt["member"]
        if name in by_member:
            if exact_receipts[name] != receipt:
                raise ValueError("conflicting receipt member")
            redundant_receipts += 1
            continue
        by_member[name] = receipt["sha256"]
        exact_receipts[name] = receipt

    def key(row: dict[str, Any]) -> tuple[str, str, int]:
        s, c, f = row["sequence_id"], row["camera_id"], row["frame_index"]
        if not re.fullmatch(r"subject_\d+/\d{8}_\d{6}", s) or not re.fullmatch(r"\d{12}", c):
            raise ValueError("invalid sequence or camera identifier")
        if type(f) is not int or f < 0:
            raise ValueError("invalid frame index")
        return s, c, f

    labels = {key(row): row for row in annotations}
    if len(labels) != len(annotations) or len({key(r) for r in raw}) != len(raw):
        raise ValueError("duplicate frame identity")
    if not raw or set(labels) != {key(r) for r in raw}:
        raise ValueError("complete raw/annotation frame closure required")
    files: dict[str, str] = {
        "raw_manifest.json": raw_sha256,
        "annotation_manifest.json": annotation_sha256,
        "download_receipts.json": receipts_sha256,
    }

    def read(name: str, digest: str | None = None) -> bytes:
        data = pinned_bytes(root, name, digest)
        files[name] = hashlib.sha256(data).hexdigest()
        return data

    contexts, evaluation = [], []
    sequence_cache: dict[str, tuple[Any, Any, Any, Any]] = {}
    for row in raw:
        seq, camera, frame = key(row)
        prefix = f"{seq}/{camera}"
        label_member = f"{prefix}/label_{frame:06d}.npz"
        anno = labels[key(row)]
        if anno["member"] != label_member or anno["annotation_sha256"] != by_member[label_member]:
            raise ValueError("cross-file label receipt mismatch")
        pointers = {}
        for kind, ext, digest_name in (
            ("color", "jpg", "rgb_sha256"),
            ("depth", "png", "depth_sha256"),
        ):
            member = f"{prefix}/{kind}_{frame:06d}.{ext}"
            if row[digest_name] != by_member[member]:
                raise ValueError("cross-file raw receipt mismatch")
            data = read("raw/" + member, row[digest_name])
            with Image.open(io.BytesIO(data)) as image:
                if image.size != (640, 480):
                    raise ValueError("unexpected raw image dimensions")
                image.load()
            pointers[kind] = {"path": "raw/" + member, "sha256": row[digest_name]}
        cache_key = seq + "/" + camera
        if cache_key not in sequence_cache:
            meta_name, pose_name = seq + "/meta.yaml", seq + "/poses_o.npy"
            meta = yaml.safe_load(read("evaluator/" + meta_name, by_member[meta_name]))
            poses = np.load(
                io.BytesIO(read("evaluator/" + pose_name, by_member[pose_name])), allow_pickle=False
            )
            intrinsic = yaml.safe_load(read(f"calibration/intrinsics/{camera}.yaml"))
            extrinsic = yaml.safe_load(read("calibration/extrinsics/" + meta["extrinsics"]))
            sequence_cache[cache_key] = meta, poses, intrinsic, extrinsic
        meta, poses, intrinsic, extrinsic = sequence_cache[cache_key]
        supervision = pose_supervision(
            read("evaluator/" + label_member, anno["annotation_sha256"]),
            metadata=meta,
            intrinsics=intrinsic,
            extrinsics=extrinsic,
            sequence_poses=poses,
            frame=frame,
            camera=camera,
        )
        contexts.append(
            {
                "sequence_id": seq,
                "camera_id": camera,
                "frame_index": frame,
                "inputs": pointers,
                "partition": "spent_development",
            }
        )
        evaluation.append(
            {
                "sequence_id": seq,
                "camera_id": camera,
                "frame_index": frame,
                "label_sha256": anno["annotation_sha256"],
                **supervision,
            }
        )
    if any(hashlib.sha256(pinned_bytes(root, n)).hexdigest() != h for n, h in files.items()):
        raise ValueError("source changed during package preparation")
    return {
        "model_inputs": contexts,
        "evaluator_only": evaluation,
        "source_files": files,
        "manifest_sha256s": {
            "raw": raw_sha256,
            "annotation": annotation_sha256,
            "receipts": receipts_sha256,
        },
        "author_revision": AUTHOR_REVISION,
        "identical_repeated_download_receipts": redundant_receipts,
        "source_unchanged": True,
        "full_proposal_training_ready": False,
        "blockers": [
            "independent_review",
            "native_six_operation_lineage",
            "full_H_R_I_C_Z_r_V_compatible_targets",
            "predicted_pose_and_noise_calibration",
            "separate_unspent_validation_and_confirmation",
        ],
    }
