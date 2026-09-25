"""Inspect external author evidence without promoting it to runtime authority.

Pose residuals below describe an author demo against author optimized labels.
They are not a calibrated noise model for our front end, nor held-out evidence.
RPL force channels remain measurements: no unreviewed contact threshold is added.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import PurePosixPath
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation  # type: ignore[import-untyped]

from cpswm.data_preflight.hocap_joint_supervision import checked_transform


def pose_residuals(
    truth: dict[str, Any], prediction: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not truth or not prediction:
        raise ValueError("nonempty author poses and predictions required")
    rows = []
    for obj, frames in sorted(prediction.items()):
        if obj not in truth or not frames:
            raise ValueError("prediction object has no author truth")
        for key, pred in sorted(frames.items()):
            parts = key.split("/")
            if len(parts) != 4 or not parts[-1].isdigit() or key not in truth[obj]:
                raise ValueError("prediction has no exact subject/sequence/camera/frame match")
            target = checked_transform(truth[obj][key])
            estimate = checked_transform(pred)
            translation = estimate[:3, 3] - target[:3, 3]
            # Left rotation error, expressed in camera coordinates. No symmetry
            # minimization and no assertion that orientations are identifiable.
            rotation = Rotation.from_matrix(estimate[:3, :3] @ target[:3, :3].T).as_rotvec()
            rows.append(
                {
                    "object": obj,
                    "frame_key": key,
                    "translation_camera_m": translation.tolist(),
                    "rotation_camera_rad": rotation.tolist(),
                    "translation_norm_m": float(np.linalg.norm(translation)),
                    "rotation_angle_deg": float(np.rad2deg(np.linalg.norm(rotation))),
                }
            )
    vectors = np.array([r["translation_camera_m"] + r["rotation_camera_rad"] for r in rows])
    groups = sorted({"/".join(r["frame_key"].split("/")[:3]) for r in rows})
    summary = {
        "matched_object_pose_pairs": len(rows),
        "objects": sorted(prediction),
        "subject_sequence_camera_groups": groups,
        "units": ["m", "m", "m", "rad", "rad", "rad"],
        "residual_definition": "t_pred-t_gt; Log(R_pred R_gt^T), camera frame",
        "mean_residual": vectors.mean(axis=0).tolist(),
        "sample_covariance_descriptive_only": np.cov(vectors, rowvar=False, ddof=1).tolist()
        if len(rows) > 1
        else None,
        "translation_norm_quantiles_m": np.quantile(
            [r["translation_norm_m"] for r in rows], [0.5, 0.9, 0.95, 1]
        ).tolist(),
        "rotation_angle_quantiles_deg": np.quantile(
            [r["rotation_angle_deg"] for r in rows], [0.5, 0.9, 0.95, 1]
        ).tolist(),
        "quantile_levels": [0.5, 0.9, 0.95, 1],
        "prediction_identity": "author ope_demo; exact generating model/checkpoint unverified",
        "ground_truth_kind": "author optimized labels, not independent physical mocap",
        "correlated_frames_and_cameras": True,
        "object_symmetry_adjusted": False,
        "partition": "spent_external_development_diagnostic",
        "runtime_noise_calibrated": False,
        "runtime_covariance_authority": False,
        "independent_confirmation": False,
    }
    return rows, summary


def inspect_rpl_archive(payload: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    arrays, receipts = {}, []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names
        ):
            raise ValueError("duplicate or unsafe archive paths")
        for name in names:
            if not name.endswith(".csv"):
                continue
            if archive.getinfo(name).file_size > 1024 * 1024:
                raise ValueError("CSV member exceeds bounded sample size")
            raw = archive.read(name)  # CRC checked before any numeric parsing.
            reader = csv.reader(io.StringIO(raw.decode()))
            header = next(reader)
            expected = (
                ["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]
                if PurePosixPath(name).name.startswith("Wrench_")
                else ["x", "y", "z", "q0", "q1", "q2", "q3"]
            )
            if header != expected:
                raise ValueError("unexpected author CSV columns")
            values = np.array([[float(c) for c in row] for row in reader], dtype=float)
            if (
                values.ndim != 2
                or values.shape[1] != len(expected)
                or not np.isfinite(values).all()
            ):
                raise ValueError("malformed or nonfinite sensor samples")
            key = PurePosixPath(name).name
            if key in arrays:
                raise ValueError("ambiguous duplicated channel basename")
            arrays[key] = values
            receipts.append({"member": name, "sha256": hashlib.sha256(raw).hexdigest()})
    required = {f"Wrench_{role}_saved.csv" for role in ("giver", "taker", "interaction")}
    required.add("baton_pose_saved.csv")
    body = (
        "hip",
        "ab",
        "chest",
        "neck",
        "head",
        "LShoulder",
        "LUArm",
        "LFArm",
        "LHand",
        "RShoulder",
        "RUArm",
        "RFArm",
        "RHand",
    )
    required.update(
        f"{role}_{joint}_pose_saved.csv" for role in ("giver", "taker") for joint in body
    )
    if set(arrays) != required:
        raise ValueError("complete 30-channel author sample required")
    lengths = {len(a) for a in arrays.values()}
    if len(lengths) != 1 or next(iter(lengths)) < 2:
        raise ValueError("sensor channel alignment mismatch")
    rows = [
        {
            "sample_index": i,
            "nominal_time_seconds": i / 120,
            "giver_grip_force_n": float(-arrays["Wrench_giver_saved.csv"][i, 2]),
            "taker_grip_force_n": float(-arrays["Wrench_taker_saved.csv"][i, 2]),
            "interaction_wrench": arrays["Wrench_interaction_saved.csv"][i].tolist(),
            "baton_pose_author_xy_z_q0_q1_q2_q3": arrays["baton_pose_saved.csv"][i].tolist(),
            "contact_label": None,
            "release_label": None,
        }
        for i in range(next(iter(lengths)))
    ]
    return rows, {
        "samples": len(rows),
        "csv_channels": len(arrays),
        "nominal_hz_author": 120,
        "actual_sensor_timestamps_available": False,
        "roles": ["giver", "taker"],
        "global_participant_ids_available": False,
        "rgb_available": False,
        "author_sensor_kind": "three force torque sensors plus optical motion capture",
        "max_quaternion_norm_error": max(
            float(np.max(np.abs(np.linalg.norm(a[:, 3:], axis=1) - 1)))
            for n, a in arrays.items()
            if not n.startswith("Wrench_")
        ),
        "quaternion_component_convention_verified": False,
        "contact_release_threshold_selected": False,
        "independent_physical_contact_gold": False,
        "native_operation_labels": [],
        "full_proposal_training_ready": False,
        "source_members": receipts,
    }


def inspect_hfd_trial(
    arrays: dict[str, np.ndarray], metadata: dict[str, Any], outcome: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate frame alignment, retaining author boundary ambiguity explicitly."""
    for name, value in arrays.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite sensor or label data: " + name)
    time = arrays["head_cam_ts"]
    raw_time = arrays["wrench_ts"]
    human, robot = arrays["human_activity"], arrays["robot_actions"]
    raw, resampled = arrays["wrench"], arrays["wrench_resampled"]
    if (
        time.ndim != 1
        or raw_time.ndim != 1
        or len(time) < 2
        or len(raw_time) < 2
        or np.any(np.diff(time) <= 0)
        or np.any(np.diff(raw_time) <= 0)
        or human.shape != time.shape
        or robot.shape != time.shape
        or raw.shape != (len(raw_time), 6)
        or resampled.shape != (len(time), 6)
    ):
        raise ValueError("unaligned timestamps, labels or wrench channels")
    if (
        human.dtype.kind not in "iu"
        or robot.dtype.kind not in "iu"
        or not set(human.tolist()) <= set(range(7))
        or not set(robot.tolist()) <= set(range(5))
        or metadata.get("robot") not in {"Toyota HSR", "Kinova Gen3"}
        or metadata.get("task") not in {"human to robot handover", "robot to human handover"}
        or any(outcome.get(k) != metadata[k] for k in ("task", "robot"))
        or type(outcome.get("outcome")) is not int
        or outcome["outcome"] not in range(4)
    ):
        raise ValueError("invalid or conflicting author label schema")
    label_names = (
        "idle",
        "approach",
        "interact",
        "retract",
        "post_idle",
        "not_released",
        "dropped",
    )
    changes = np.flatnonzero(np.diff(human) != 0) + 1
    rows = [
        {
            "frame_index": i,
            "timestamp_seconds": float(time[i]),
            "human_action_id": int(human[i]),
            "human_action": label_names[int(human[i])],
            "robot_action_id": int(robot[i]),
            "wrench_resampled": resampled[i].tolist(),
            "actor_identity": None,
            "exact_contact_release_gold": False,
        }
        for i in range(len(time))
    ]
    return rows, {
        "frames": len(time),
        "raw_wrench_samples": len(raw_time),
        "metadata": metadata,
        "outcome": outcome["outcome"],
        "human_class_counts": {
            label_names[int(k)]: int(v)
            for k, v in zip(*np.unique(human, return_counts=True), strict=True)
        },
        "human_phase_boundaries": [
            {
                "frame_index": int(i),
                "bracket_seconds": [float(time[i - 1]), float(time[i])],
                "from": label_names[int(human[i - 1])],
                "to": label_names[int(human[i])],
                "bracket_is_sampling_interval_not_annotation_error_bound": True,
            }
            for i in changes
        ],
        "wrench_kind": "wrist force torque sensor"
        if metadata["robot"] == "Toyota HSR"
        else "estimated wrist wrench from sensed joint torques",
        "zero_raw_wrench_rows": int(np.sum(np.all(raw == 0, axis=1))),
        "zero_resampled_wrench_rows": int(np.sum(np.all(resampled == 0, axis=1))),
        "frame_times_outside_raw_wrench_range": int(
            np.sum((time < raw_time[0]) | (time > raw_time[-1]))
        ),
        "human_label_provenance": "single external human annotator using video and force torque",
        "robot_label_provenance": "extracted from joint data",
        "independent_second_human_review": False,
        "temporal_boundary_ambiguity": True,
        "actor_identity_labels_available": False,
        "contact_release_gold": False,
        "partition": "author_train_spent_development_here",
        "full_proposal_training_ready": False,
    }
