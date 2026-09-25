"""External evidence alignment and authority boundaries, including valid forgeries."""

import io
import zipfile

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from cpswm.data_preflight.public_handover_evidence import (
    inspect_hfd_trial,
    inspect_rpl_archive,
    pose_residuals,
)


@pytest.mark.parametrize("degrees", [0, 30, 179.9])
def test_pose_residual_has_camera_units_and_no_calibration_authority(degrees):
    truth = np.eye(4)
    pred = truth.copy()
    pred[:3, :3] = Rotation.from_euler("z", degrees, degrees=True).as_matrix()
    pred[0, 3] = 0.02
    key = "subject/sequence/camera/000001"
    rows, report = pose_residuals({"obj": {key: truth}}, {"obj": {key: pred}})
    assert rows[0]["translation_norm_m"] == pytest.approx(0.02)
    assert rows[0]["rotation_angle_deg"] == pytest.approx(degrees)
    assert not report["runtime_noise_calibrated"] and not report["runtime_covariance_authority"]
    assert report["sample_covariance_descriptive_only"] is None
    pred[0, 0] = 12
    with pytest.raises(ValueError, match="non-rigid"):
        pose_residuals({"obj": {key: truth}}, {"obj": {key: pred}})
    with pytest.raises(ValueError, match=r"exact.*match"):
        pose_residuals({"obj": {key: truth}}, {"obj": {key + "2": truth}})


def arrays():
    return {
        "head_cam_ts": np.arange(5) / 30,
        "wrench_ts": np.arange(20) / 120,
        "human_activity": np.array([0, 1, 2, 3, 4]),
        "robot_actions": np.array([0, 1, 2, 3, 4]),
        "wrench": np.ones((20, 6)),
        "wrench_resampled": np.ones((5, 6)),
    }


def test_complete_plausible_human_labels_cannot_claim_independent_review_or_contact_gold():
    info = {"robot": "Toyota HSR", "task": "robot to human handover"}
    rows, report = inspect_hfd_trial(arrays(), info, {**info, "outcome": 0})
    assert len(rows) == 5 and len(report["human_phase_boundaries"]) == 4
    assert not report["independent_second_human_review"]
    assert not report["contact_release_gold"] and not report["full_proposal_training_ready"]
    assert all(r["actor_identity"] is None for r in rows)


@pytest.mark.parametrize("attack", ["time", "length", "class", "float_class", "nan", "outcome"])
def test_human_annotation_alignment_and_schema_attacks(attack):
    data = arrays()
    info = {"robot": "Toyota HSR", "task": "robot to human handover"}
    outcome = {**info, "outcome": 0}
    if attack == "time":
        data["head_cam_ts"][2] = 0
    elif attack == "length":
        data["wrench_resampled"] = np.ones((4, 6))
    elif attack == "class":
        data["human_activity"][2] = 77
    elif attack == "float_class":
        data["human_activity"] = data["human_activity"].astype(float)
    elif attack == "nan":
        data["wrench"][0, 1] = np.nan
    else:
        outcome["robot"] = "Kinova Gen3"
    with pytest.raises(ValueError):
        inspect_hfd_trial(data, info, outcome)


def test_complete_forged_sensor_archive_retains_unknown_contact_and_global_identity():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for role in ["giver", "taker", "interaction"]:
            z.writestr(f"Wrench_{role}_saved.csv", "Fx,Fy,Fz,Tx,Ty,Tz\n" + "0,0,-4,0,0,0\n" * 3)
        for name in ["baton"] + [
            f"{role}_{joint}"
            for role in ["giver", "taker"]
            for joint in [
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
            ]
        ]:
            z.writestr(f"{name}_pose_saved.csv", "x,y,z,q0,q1,q2,q3\n" + "0,0,0,1,0,0,0\n" * 3)
    rows, report = inspect_rpl_archive(buffer.getvalue())
    assert len(rows) == 3 and rows[0]["giver_grip_force_n"] == 4
    assert rows[0]["release_label"] is None and rows[0]["contact_label"] is None
    assert not report["global_participant_ids_available"]
    assert not report["independent_physical_contact_gold"]
    assert not report["full_proposal_training_ready"]
