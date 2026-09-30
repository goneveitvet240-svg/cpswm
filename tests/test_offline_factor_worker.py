"""Controlled SDK double: the full fixed path plus consequential schedule attacks."""

import json
from uuid import uuid4

import numpy as np
import pytest
from offline_factor_manifest import OBSERVATION_ACTIONS
from test_instance_correspondence import event_fixture
from unity_offline_factor_worker import OfflineFactorRecorder


class Controller:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail
        self.last_event = self.event("CreateHouse")

    def event(self, action):
        event = event_fixture()
        event.depth_frame = np.ones((4, 4), dtype=np.float32)
        event.metadata.update(lastAction=action, lastActionSuccess=action != self.fail)
        return event

    def step(self, **kw):
        self.calls.append(kw)
        self.last_event = self.event(kw["action"])
        return self.last_event


def request(action="Pass", degrees=0.0):
    return dict(action_id=str(uuid4()), action=action, degrees=degrees)


def test_full_fixed_path_preserves_all_events_and_invisible_instance(tmp_path):
    controller = Controller()
    recorder = OfflineFactorRecorder(controller, tmp_path, 4)
    recorder.prepare()
    for action, degrees in OBSERVATION_ACTIONS:
        recorder.observe(request(action, degrees))
    assert recorder.frames == 8 and len(recorder.events) == 12
    assert (
        controller.calls
        == [dict(action=a) for a in ("PausePhysicsAutoSim", "Pass", "Pass", "Pass")]
        + [dict(action="RotateRight", degrees=45.0)] * 7
    )
    assert len(list((tmp_path / "sdk-events").glob("*.json"))) == 12
    for index in range(12):
        catalog = json.loads((tmp_path / "instances" / f"{index:03d}.json").read_text())["catalog"]
        assert len(catalog) == 3
        assert any(row["object_id"] == "Bottle|absent" for row in catalog)
    with pytest.raises(ValueError, match="fixed schedule"):
        recorder.observe(request("RotateRight", 45.0))
    assert len(controller.calls) == 11


@pytest.mark.parametrize(
    "attack",
    [
        "before_prepare",
        "repeat_prepare",
        "target_view",
        "degree",
        "private_field",
        "duplicate",
        "failed_action",
        "resize",
    ],
)
def test_invalid_schedule_never_produces_an_accepted_frame(tmp_path, attack):
    controller = Controller(fail="RotateRight" if attack == "failed_action" else None)
    recorder = OfflineFactorRecorder(controller, tmp_path, 4)
    first = request()
    if attack != "before_prepare":
        recorder.prepare()
    if attack in ("duplicate", "failed_action"):
        recorder.observe(first)
    bad = request()
    if attack == "target_view":
        bad.update(action="RotateLeft", degrees=45.0)
    elif attack == "degree":
        bad.update(action="RotateRight", degrees=90.0)
    elif attack == "private_field":
        bad["target"] = "Apple|one"
    elif attack == "failed_action":
        bad.update(action="RotateRight", degrees=45.0)
    elif attack == "duplicate":
        bad = first
    elif attack == "resize":
        recorder.image_size = 320
    with pytest.raises(ValueError):
        recorder.prepare() if attack == "repeat_prepare" else recorder.observe(bad)
    assert recorder.frames == (1 if attack in ("duplicate", "failed_action") else 0)
    if attack == "failed_action":
        assert recorder.events[-1]["metadata"]["lastActionSuccess"] is False
        with pytest.raises(ValueError):
            recorder.observe(bad)
