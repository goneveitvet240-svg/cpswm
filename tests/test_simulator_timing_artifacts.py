import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from run_simulator_timing import analyze, plan, sha

from cpswm.system.continuous_state_codec import StateCodec


@pytest.fixture(scope="module")
def actual():
    return Path(os.environ["CPSWM_TIMING_FIXTURE"]), dict(
        ssdlite=Path(os.environ["CPSWM_SSDLITE_WEIGHTS"]),
        fasterrcnn=Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
    )


@pytest.mark.parametrize("mode", ["auto", "frozen", "stepped"])
def test_all_three_actual_legal_control_sequences_recompute(actual, mode):
    directory, weights = actual
    cell = next(c for c in plan() if c["name"] == f"south-320-{mode}-0")
    result = analyze(directory / cell["name"], cell, weights=weights, verify=True)
    assert len(result["frames"]) == 16 and result["calibration_fitted"] is False


@pytest.mark.parametrize(
    "attack",
    [
        "positive",
        "physical_step",
        "returned_action",
        "missing_sdk_event",
        "private_pose",
        "missing_owned_frame",
    ],
)
def test_coherent_positive_and_hidden_clock_forgery_are_rejected(tmp_path, actual, attack):
    root, weights = actual
    cell = next(c for c in plan() if c["name"] == "south-320-stepped-0")
    forged = tmp_path / "forged"
    shutil.copytree(root / cell["name"], forged)
    private = forged / "unity-logs/evaluator_only"
    reason = {
        "positive": "fresh timing predictions",
        "physical_step": "SDK requested timing",
        "returned_action": "SDK executed timing",
        "missing_sdk_event": "SDK event coverage",
        "private_pose": "SDK/public geometry",
        "missing_owned_frame": "timing record count",
    }[attack]
    if attack == "positive":
        p = forged / "predictions.json"
        data = json.loads(p.read_text())
        data["measurements"]["ssdlite"][0]["candidates"] = [
            dict(
                candidate_id=str(uuid4()),
                category="apple",
                detector_score=0.99,
                box_xyxy=[0, 0, 320, 320],
            )
        ]
        p.write_text(json.dumps(data))
        p = forged / "analysis.json"
        data = json.loads(p.read_text())
        box = json.loads((private / "actions.json").read_text())[0]["target_bbox"]
        iou = 0.0 if box is None else (box[2] - box[0]) * (box[3] - box[1]) / 102400
        data["frames"][0]["frontends"]["ssdlite"] = dict(scores=[0.99], target_bbox_ious=[iou])
        p.write_text(json.dumps(data))
    elif attack in ("physical_step", "returned_action"):
        p = private / "sdk-events/002.json"
        data = json.loads(p.read_text())
        if attack == "physical_step":
            data["requested"]["timeStep"] = 0.02
        else:
            data["metadata"]["lastAction"] = "Pass"
        p.write_text(json.dumps(data))
    elif attack == "missing_sdk_event":
        (private / "sdk-events/002.json").unlink()
    elif attack == "private_pose":
        p = private / "sdk-events/003.json"
        data = json.loads(p.read_text())
        data["metadata"]["agent"]["rotation"]["y"] = 90
        p.write_text(json.dumps(data))
    else:
        p = forged / "capture-state.json"
        records = StateCodec().loads(p.read_text())
        text = StateCodec().dumps(records[:-1])
        p.write_text(text)
        p = forged / "capture.json"
        data = json.loads(p.read_text())
        data["state_sha256"] = sha(text.encode())
        p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=reason):
        analyze(forged, cell, weights=weights, verify=True)
