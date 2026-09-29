"""Positive correspondence and complete-but-wrong private evidence, synthetic only."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

pytest.importorskip("torch", reason="history diagnostic tools require optional perception runtime")
from history_visual_evidence import evaluate_frame
from test_instance_correspondence import event_fixture
from test_structure_two_adaptive_runtime import _adaptive_system_and_transition
from test_structure_two_continuous_input import raw_for
from unity_instance_audit_worker import export_instances
from unity_visual_history_worker import VisualHistoryCameraRecorder


@pytest.fixture
def case(tmp_path):
    event = event_fixture()
    # Controlled geometry, NOT actual simulator accuracy evidence.
    event.frame = np.zeros((320, 320, 3), dtype=np.uint8)
    event.instance_segmentation_frame = np.repeat(
        np.repeat(event.instance_segmentation_frame, 80, axis=0), 80, axis=1
    )
    event.instance_masks = {
        r["name"]: np.all(event.instance_segmentation_frame == r["color"], axis=2)
        for r in event.metadata["colors"]
    }
    action = uuid4()
    export_instances(event, tmp_path, 4, str(action))
    info = json.loads((tmp_path / "004.json").read_text())
    with np.load(tmp_path / "004-masks.npz", allow_pickle=False) as f:
        masks = {k: f[k].copy() for k in f.files}
    _, transition = _adaptive_system_and_transition()
    raw = raw_for(transition)
    candidate = dict(
        candidate_id=str(uuid4()),
        category="apple",
        detector_score=0.99,
        box_xyxy=[0, 0, 320, 160],
    )
    frame = dict(
        input_sha256=hashlib.sha256(raw.payload_bytes).hexdigest(),
        observation_id=str(raw.envelope().identity.observation_id),
        minimum_score=0.5,
        identity_status="UNRESOLVED",
        negative_observation_authorized=False,
        candidates=[candidate],
    )
    return dict(
        command=SimpleNamespace(action_id=action, action="Pass", degrees=0.0),
        delivery=SimpleNamespace(observations=(raw,)),
        row=dict(owner=str(action), index=4, metadata=event.metadata),
        frames=dict(ssdlite=deepcopy(frame), fasterrcnn=deepcopy(frame)),
        info=info,
        masks=masks,
        segmentation=event.instance_segmentation_frame,
        target_mask=event.instance_masks["Apple|one"],
        target="Apple|one",
    )


def test_target_positive_keeps_all_instances_without_identity_assignment(case):
    result = evaluate_frame(**case)
    assert result["target_pixels"] == 320 * 160
    assert len(result["candidate_instance_matrix"]) == 2
    for row in result["candidate_instance_matrix"]:
        by_id = {r["object_id"]: r for r in row["overlaps"]}
        assert len(by_id) == 3
        assert by_id["Apple|one"]["intersection_pixels"] == 320 * 160
        assert by_id["Apple|one"]["bbox_iou"] == 1
        assert by_id["Tomato|two"]["intersection_pixels"] == 0
    assert result["automatic_identity_assignment"] is False
    assert result["natural_identity_labels"] == 0


def test_wrong_object_positive_and_no_candidate_are_preserved(case):
    case["frames"]["ssdlite"]["candidates"] = []
    case["frames"]["fasterrcnn"]["candidates"][0]["box_xyxy"] = [0, 160, 320, 320]
    result = evaluate_frame(**case)
    assert result["target_pixels"] > 0
    (candidate,) = result["candidate_instance_matrix"]
    by_id = {r["object_id"]: r for r in candidate["overlaps"]}
    assert by_id["Tomato|two"]["intersection_pixels"] == 320 * 160
    assert by_id["Apple|one"]["intersection_pixels"] == 0
    assert result["automatic_identity_assignment"] is False


@pytest.mark.parametrize(
    "attack",
    ["owner", "input", "authority", "missing_arm", "omit_instance", "mask", "target", "box"],
)
def test_forged_complete_frame_rejected(case, attack):
    if attack == "owner":
        case["info"]["action_id"] = str(uuid4())
    elif attack == "input":
        case["frames"]["ssdlite"]["input_sha256"] = "e" * 64
    elif attack == "authority":
        case["frames"]["ssdlite"]["negative_observation_authorized"] = True
    elif attack == "missing_arm":
        del case["frames"]["ssdlite"]
    elif attack == "omit_instance":
        row = case["info"]["catalog"].pop()
        del case["masks"][row["array_key"]]
    elif attack == "mask":
        key = case["info"]["catalog"][0]["array_key"]
        case["masks"][key] = ~case["masks"][key]
    elif attack == "target":
        case["target_mask"] = ~case["target_mask"]
    else:
        case["frames"]["ssdlite"]["candidates"][0]["box_xyxy"][0] = float("nan")
    with pytest.raises(ValueError):
        evaluate_frame(**case)


def test_full_instance_recorder_covers_preparation_and_owned_command(tmp_path):
    class Controller:
        def __init__(self):
            self.last_event = self.event("CreateHouse")

        def event(self, action):
            e = event_fixture()
            e.metadata.update(lastAction=action, lastActionSuccess=True)
            return e

        def step(self, **kw):
            self.last_event = self.event(kw["action"])
            return self.last_event

    controller = Controller()
    rec = VisualHistoryCameraRecorder(controller, tmp_path, "Apple|one")
    rec.prepare()
    identity = str(uuid4())
    event = rec.observe(dict(action_id=identity, action="RotateRight", degrees=45))
    assert event is controller.last_event
    assert len(list((tmp_path / "instances").glob("*.json"))) == 5
    assert json.loads((tmp_path / "instances/004.json").read_text())["action_id"] == identity


def test_wrong_public_action_rejected_before_visual_inference(case):
    from history_visual_evidence import paired_predictions

    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    raw = case["delivery"].observations[0]
    delivery = ObservationDelivery(
        action_id=uuid4(),
        received_at=raw.envelope().arrival_time,
        observations=(raw,),
        success=True,
        error=None,
    )
    with pytest.raises(ValueError, match="invalid public delivery"):
        paired_predictions([(case["command"], delivery)], task="clarification", weights={})
    mismatched = replace(delivery, action_id=case["command"].action_id)
    case["command"].decision_time = raw.envelope().capture_time
    with pytest.raises(ValueError, match="public pixels or ownership"):
        paired_predictions([(case["command"], mismatched)], task="clarification", weights={})
