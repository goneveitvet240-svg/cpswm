import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from run_simulator_repeatability import analyze, plan, sha

from cpswm.system.continuous_state_codec import StateCodec


@pytest.fixture(scope="module")
def actual():
    return Path(os.environ["CPSWM_REPETITION_FIXTURE"]), dict(
        ssdlite=Path(os.environ["CPSWM_SSDLITE_WEIGHTS"]),
        fasterrcnn=Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
    )


def test_actual_eight_frame_sequence_recomputes_completely(actual):
    directory, weights = actual
    result = analyze(directory, plan()[0], weights=weights, verify=True)
    assert len(result["frames"]) == 8 and result["cell"]["route"] == "direct"
    assert all(r["target_pixels"] == 0 for r in result["frames"])


@pytest.mark.parametrize(
    "attack", ["full_positive", "mask_summary", "missing_owned_frame", "full_metadata_drift"]
)
def test_consistent_positive_and_sequence_corruption_rejected(tmp_path, actual, attack):
    directory, weights = actual
    forged = tmp_path / "forged"
    shutil.copytree(directory, forged)
    reason = {
        "full_positive": "fresh inference",
        "mask_summary": "mask statistics",
        "missing_owned_frame": "repetition count",
        "full_metadata_drift": "full metadata pose",
    }[attack]
    if attack == "full_positive":
        path = forged / "predictions.json"
        pred = json.loads(path.read_text())
        pred["measurements"]["ssdlite"][0]["candidates"] = [
            dict(
                candidate_id=str(uuid4()),
                category="apple",
                detector_score=0.99,
                box_xyxy=[0, 0, 320, 320],
            )
        ]
        path.write_text(json.dumps(pred))
        p = forged / "analysis.json"
        a = json.loads(p.read_text())
        a["frames"][0]["frontends"]["ssdlite"] = dict(scores=[0.99], target_bbox_ious=[0.0])
        p.write_text(json.dumps(a))
    elif attack == "missing_owned_frame":
        path = forged / "capture-state.json"
        records = StateCodec().loads(path.read_text())
        text = StateCodec().dumps(records[:-1])
        path.write_text(text)
        path = forged / "capture.json"
        info = json.loads(path.read_text())
        info["state_sha256"] = sha(text.encode())
        path.write_text(json.dumps(info))
    elif attack == "mask_summary":
        path = forged / "unity-logs/evaluator_only/actions.json"
        rows = json.loads(path.read_text())
        rows[0]["target_pixels"] = 123
        path.write_text(json.dumps(rows))
    else:
        path = forged / "unity-logs/evaluator_only/full_metadata/000.json"
        info = json.loads(path.read_text())
        info["metadata"]["agent"]["rotation"]["y"] = 90
        path.write_text(json.dumps(info))
    with pytest.raises(ValueError, match=reason):
        analyze(forged, plan()[0], weights=weights, verify=True)
