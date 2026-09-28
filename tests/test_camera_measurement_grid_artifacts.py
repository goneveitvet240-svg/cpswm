"""Actual 11-view positive path and full result/source/geometry attacks."""

import hashlib
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_camera_measurement_grid import analyze_case

from cpswm.system.continuous_state_codec import StateCodec


@pytest.fixture(scope="module")
def configured():
    if not all(
        os.environ.get(k)
        for k in ("CPSWM_GRID_FIXTURE", "CPSWM_SSDLITE_WEIGHTS", "CPSWM_FASTERRCNN_WEIGHTS")
    ):
        pytest.skip("explicit actual live grid fixture and pinned model paths required")
    return Path(os.environ["CPSWM_GRID_FIXTURE"]), {
        "ssdlite": Path(os.environ["CPSWM_SSDLITE_WEIGHTS"]),
        "fasterrcnn": Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
    }


def test_actual_grid_recomputes_every_frame_and_both_models_on_same_pixels(configured):
    directory, weights = configured
    result = analyze_case(directory, weights=weights, site="north", x=1.25, verify=True)
    assert result["frame_count"] == 11
    assert any(f["target_pixels"] == 0 for f in result["frames"])
    assert any(f["target_pixels"] > 0 for f in result["frames"])
    assert any(
        any(i > 0.9 for i in f["frontends"]["fasterrcnn"]["bbox_ious"]) for f in result["frames"]
    )


@pytest.mark.parametrize(
    "attack",
    [
        "drop",
        "duplicate",
        "wrong_action",
        "wrong_source",
        "metadata",
        "rgb",
        "mask",
        "fake_detection",
        "summary",
        "camera_height",
        "camera_x",
        "pitch",
        "fov",
        "target",
        "missing_arm",
    ],
)
def test_complete_forgeries_rejected_for_their_specific_reason(tmp_path, configured, attack):
    directory, weights = configured
    output = tmp_path / "forged"
    shutil.copytree(directory, output)
    manifest = json.loads((output / "capture.json").read_text())
    private = output / "unity-logs/evaluator_only"
    errors = {
        "drop": "frame count differs",
        "duplicate": "fixed schedule|duplicated",
        "wrong_action": "fixed schedule",
        "wrong_source": "capture source differs",
        "metadata": "capture differs from declared",
        "rgb": "evaluator RGB differs",
        "mask": "visibility differs",
        "fake_detection": "predictions differ",
        "summary": "evaluation differs",
        "camera_height": "camera geometry drifted",
        "camera_x": "camera geometry drifted",
        "pitch": "camera geometry drifted",
        "fov": "camera geometry drifted",
        "target": "target moved",
        "missing_arm": "predictions differ",
    }
    if attack in ("drop", "duplicate", "wrong_action"):
        records = list(StateCodec().loads((output / "capture-state.json").read_text()))
        if attack == "drop":
            records.pop()
        elif attack == "duplicate":
            records[1] = records[0]
        else:
            records[1] = (replace(records[1][0], degrees=30), records[1][1])
        document = StateCodec().dumps(tuple(records))
        (output / "capture-state.json").write_text(document)
        manifest["state_sha256"] = hashlib.sha256(document.encode()).hexdigest()
    elif attack == "wrong_source":
        manifest["source_sha256"] = "f" * 64
    elif attack == "metadata":
        manifest["camera_x"] = 1.45
    elif attack == "rgb":
        p = private / "001-rgb.npy"
        a = np.load(p, allow_pickle=False)
        a[0, 0, 0] ^= 1
        np.save(p, a, allow_pickle=False)
    elif attack == "mask":
        p = private / "000-mask.npy"
        a = np.load(p, allow_pickle=False)
        a[0, 0] ^= True
        np.save(p, a, allow_pickle=False)
    elif attack in ("fake_detection", "missing_arm"):
        p = output / "predictions.json"
        a = json.loads(p.read_text())
        if attack == "missing_arm":
            del a["measurements"]["ssdlite"]
        else:
            a["measurements"]["ssdlite"][0]["candidates"] = [
                {
                    "candidate_id": "fake-complete-id",
                    "category": "apple",
                    "detector_score": 0.99,
                    "box_xyxy": [0, 0, 320, 320],
                }
            ]
        p.write_text(json.dumps(a))
    elif attack == "summary":
        p = output / "evaluation.json"
        a = json.loads(p.read_text())
        a["frames"][0]["target_pixels"] += 1
        p.write_text(json.dumps(a))
    else:
        p = private / "actions.json"
        a = json.loads(p.read_text())
        if attack == "camera_height":
            a[1]["camera_position"]["y"] += 0.1
        if attack == "camera_x":
            a[1]["agent"]["position"]["x"] += 0.1
        if attack == "pitch":
            a[1]["agent"]["cameraHorizon"] = 0
        if attack == "fov":
            a[1]["fov"] = 90
        if attack == "target":
            a[1]["target_position"]["z"] += 1
        p.write_text(json.dumps(a))
    (output / "capture.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=errors[attack]):
        analyze_case(output, weights=weights, site="north", x=1.25, verify=True)
