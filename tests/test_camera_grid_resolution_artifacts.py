"""Second review on actual 640 frames, dimensions and fully resealed positive results."""

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from run_camera_measurement_grid import analyze_case, configuration, load_public_capture
from verify_neural_camera_comparison import plain


@pytest.fixture(scope="module")
def actual():
    return Path(os.environ["CPSWM_GRID_640_FIXTURE"]), {
        "ssdlite": Path(os.environ["CPSWM_SSDLITE_WEIGHTS"]),
        "fasterrcnn": Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
    }


def test_actual_640_complete_legal_path_recomputes_both_models(actual):
    directory, weights = actual
    evaluated = analyze_case(
        directory, weights=weights, site="north", x=1.25, verify=True, image_size=640
    )
    assert evaluated["image_size"] == 640 and evaluated["frame_count"] == 11
    assert any(f["target_pixels"] == 0 for f in evaluated["frames"])
    assert any(f["target_pixels"] > 0 for f in evaluated["frames"])


def test_640_cannot_enter_320_condition_by_resealing_metadata(tmp_path, actual):
    directory, _ = actual
    forged = tmp_path / "forged"
    shutil.copytree(directory, forged)
    path = forged / "capture.json"
    manifest = json.loads(path.read_text())
    manifest["grid"] = plain(configuration(320))
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="capture resolution changed"):
        load_public_capture(forged, site="north", x=1.25, image_size=320)


def test_actual_resolution_cannot_be_changed_only_in_evaluator(tmp_path, actual):
    directory, weights = actual
    forged = tmp_path / "forged"
    shutil.copytree(directory, forged)
    path = forged / "unity-logs/evaluator_only/actions.json"
    rows = json.loads(path.read_text())
    rows[0]["image_size"] = [320, 320]
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="actual evaluator image size differs"):
        analyze_case(forged, weights=weights, site="north", x=1.25, verify=True, image_size=640)


def test_valid_uuid_complete_positive_forgery_is_rejected_by_actual_inference(tmp_path, actual):
    directory, weights = actual
    forged = tmp_path / "forged"
    shutil.copytree(directory, forged)
    predictions = json.loads((forged / "predictions.json").read_text())
    evaluation = json.loads((forged / "evaluation.json").read_text())
    truth = json.loads((forged / "unity-logs/evaluator_only/actions.json").read_text())
    index = next(i for i, row in enumerate(evaluation["frames"]) if row["target_pixels"] > 0)
    # All real scope/input/model fields remain; this is a legal-shape positive
    # candidate and a corresponding favorable evaluation, not a malformed ID.
    candidate = dict(
        candidate_id=str(uuid4()),
        category="apple",
        detector_score=0.99999937,
        box_xyxy=truth[index]["target_bbox"],
    )
    predictions["measurements"]["ssdlite"][index]["candidates"] = [candidate]
    evaluation["frames"][index]["frontends"]["ssdlite"] = {
        "scores": [0.99999937],
        "bbox_ious": [1.0],
    }
    (forged / "predictions.json").write_text(json.dumps(predictions))
    (forged / "evaluation.json").write_text(json.dumps(evaluation))
    with pytest.raises(ValueError, match="predictions differ from fresh actual inference"):
        analyze_case(forged, weights=weights, site="north", x=1.25, verify=True, image_size=640)
