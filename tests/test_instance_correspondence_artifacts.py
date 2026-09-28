"""Second review with actual simulator masks and actual model re-inference."""

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from run_instance_correspondence_diagnostic import analyze, evaluate, load_public


@pytest.fixture(scope="module")
def actual():
    return Path(os.environ["CPSWM_INSTANCE_FIXTURE"]), {
        "ssdlite": Path(os.environ["CPSWM_SSDLITE_WEIGHTS"]),
        "fasterrcnn": Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
    }


def test_actual_complete_snapshot_and_unassigned_matrix_are_recomputed(actual):
    directory, weights = actual
    result = analyze(directory, site="north", size=640, weights=weights, verify=True)
    assert result["sdk_instances"] > result["visible_instances"] > 0
    assert result["target_pixels"] == 0
    assert (
        result["automatic_identity_assignment"] is False and result["natural_identity_labels"] == 0
    )
    assert all(
        len(r["overlaps"]) == result["sdk_instances"] for r in result["candidate_instance_matrix"]
    )


@pytest.mark.parametrize(
    "attack",
    ["omit_instance", "same_count_mask", "category", "false_identity_claim", "full_positive"],
)
def test_complete_instance_and_prediction_forgeries_rejected(tmp_path, actual, attack):
    directory, weights = actual
    forged = tmp_path / "forged"
    shutil.copytree(directory, forged)
    private = forged / "unity-logs/evaluator_only/instances"
    info = json.loads((private / "000.json").read_text())
    errors = {
        "omit_instance": "catalog omits",
        "same_count_mask": "mask differs",
        "category": "category or asset",
        "false_identity_claim": "correspondence differs",
        "full_positive": "fresh predictions differ",
    }
    if attack in ("omit_instance", "same_count_mask"):
        with np.load(private / "000-masks.npz", allow_pickle=False) as saved:
            masks = {k: saved[k].copy() for k in saved.files}
        index = next(
            i for i, r in enumerate(info["catalog"]) if 0 < masks[r["array_key"]].sum() < 640 * 640
        )
        key = info["catalog"][index]["array_key"]
        if attack == "omit_instance":
            info["catalog"].pop(index)
            masks.pop(key)
        else:
            mask = masks[key]
            inside = np.argwhere(mask)[0]
            outside = np.argwhere(~mask)[0]
            mask[tuple(inside)] = False
            mask[tuple(outside)] = True
        np.savez_compressed(private / "000-masks.npz", **masks)
    elif attack == "category":
        info["catalog"][0]["object_type"] = "invented-object-class"
    elif attack == "false_identity_claim":
        path = forged / "correspondence.json"
        result = json.loads(path.read_text())
        result["automatic_identity_assignment"] = True
        result["natural_identity_labels"] = 1
        path.write_text(json.dumps(result))
    else:
        path = forged / "predictions.json"
        predictions = json.loads(path.read_text())
        predictions["measurements"]["ssdlite"][0]["candidates"] = [
            dict(
                candidate_id=str(uuid4()),
                category="apple",
                detector_score=0.99,
                box_xyxy=[0, 0, 640, 640],
            )
        ]
        command, delivery = load_public(forged, "north", 640)
        consistent = evaluate(forged, command, delivery, predictions, "north", 640)
        path.write_text(json.dumps(predictions))
        (forged / "correspondence.json").write_text(json.dumps(consistent))
    (private / "000.json").write_text(json.dumps(info))
    with pytest.raises(ValueError, match=errors[attack]):
        analyze(forged, site="north", size=640, weights=weights, verify=True)
