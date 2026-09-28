"""Second audit uses actual live positive and negative episodes, then complete forgeries."""

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_neural_pixel_camera_loop import ARMS, METHODS
from verify_neural_camera_comparison import FRONTENDS, SITES, verify_episode, verify_matrix


@pytest.fixture(scope="module")
def live_configuration():
    keys = (
        "CPSWM_COMPARISON_FIXTURES",
        "CPSWM_CHECKPOINTS",
        "CPSWM_SSDLITE_WEIGHTS",
        "CPSWM_FASTERRCNN_WEIGHTS",
    )
    if not all(os.environ.get(k) for k in keys):
        pytest.skip("explicit live diagnostic artifacts and official checkpoints required")
    return {k: Path(os.environ[k]) for k in keys}


def arguments(config, frontend):
    return dict(
        weights=config[
            "CPSWM_SSDLITE_WEIGHTS" if frontend == "ssdlite" else "CPSWM_FASTERRCNN_WEIGHTS"
        ],
        checkpoint=config["CPSWM_CHECKPOINTS"] / ARMS[0] / "checkpoint",
        method=ARMS[0],
        frontend=frontend,
        site="north",
    )


@pytest.mark.parametrize("frontend", FRONTENDS)
def test_recompute_actual_owned_episode_including_live_pixel_inference(
    live_configuration, frontend
):
    result = verify_episode(
        live_configuration["CPSWM_COMPARISON_FIXTURES"] / frontend,
        **arguments(live_configuration, frontend),
    )
    assert result["verified"] and result["all_actions_succeeded"]
    assert result["rotation_count"] in (1, 2)
    assert any(f["target_pixels"] > 0 for f in result["frames"])
    if frontend == "fasterrcnn":
        assert result["any_category_positive"] and result["any_bbox_overlap"]
    else:
        assert not result["any_category_positive"]


@pytest.mark.parametrize(
    "attack",
    [
        "posterior",
        "outcome",
        "complete_positive",
        "degrees",
        "missing_action",
        "duplicate_action",
        "wrong_treatment",
        "rgb",
        "mask_summary",
        "target_pose",
        "wrong_budget",
    ],
)
def test_forged_complete_result_cannot_override_owned_state_or_actual_pixels(
    tmp_path, live_configuration, attack
):
    source = live_configuration["CPSWM_COMPARISON_FIXTURES"] / "ssdlite"
    destination = tmp_path / "forged"
    shutil.copytree(source, destination)
    report_path = destination / "result.json"
    report = json.loads(report_path.read_text())
    private = destination / "unity-logs/evaluator_only"
    if attack == "posterior":
        report["final_joint_probabilities"] = report["initial_joint_probabilities"]
    elif attack == "outcome":
        report["actions"][0]["outcome"] = "category_candidate"
    elif attack == "complete_positive":
        first = report["actions"][0]
        first["outcome"] = "category_candidate"
        first["pixel_measurements"][0]["candidates"] = [
            {
                "candidate_id": first["action_id"],
                "category": "apple",
                "detector_score": 0.99,
                "box_xyxy": [0, 0, 320, 320],
            }
        ]
        first["update"]["outcome"] = "category_candidate"
        report["actions"][-1]["stop_reason"] = "category_candidate"
    elif attack == "degrees":
        report["actions"][0]["degrees"] = 90
        report["actions"][0]["command"]["degrees"] = 90
    elif attack == "missing_action":
        del report["actions"][1]
    elif attack == "duplicate_action":
        report["actions"][1] = report["actions"][0]
    elif attack == "wrong_treatment":
        report["feedback_enabled"] = False
    elif attack == "wrong_budget":
        report["max_actions"] = 2
    elif attack == "rgb":
        p = private / "001-rgb.npy"
        data = np.load(p, allow_pickle=False)
        data[0, 0, 0] ^= 1
        np.save(p, data, allow_pickle=False)
    else:
        p = private / "actions.json"
        data = json.loads(p.read_text())
        if attack == "mask_summary":
            data[1]["target_pixels"] = 0
            data[1]["target_bbox"] = None
        else:
            data[1]["target_position"]["x"] += 1
        p.write_text(json.dumps(data))
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        verify_episode(destination, **arguments(live_configuration, "ssdlite"))


@pytest.mark.parametrize("attack", ["missing", "duplicate", "redirected", "failed"])
def test_matrix_cannot_omit_failures_or_duplicate_an_easy_cell(tmp_path, attack):
    plan = [
        {"frontend": f, "site": s, "method": m, "directory": f"{f}/{s}/{m}", "exit_code": 0}
        for f in FRONTENDS
        for s in SITES
        for m in METHODS
    ]
    if attack == "missing":
        plan.pop()
    if attack == "duplicate":
        plan[1] = plan[0]
    if attack == "redirected":
        plan[0]["directory"] = "different_easy_case"
    if attack == "failed":
        plan[0]["exit_code"] = 1
    (tmp_path / "matrix.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        verify_matrix(tmp_path, {}, tmp_path)
