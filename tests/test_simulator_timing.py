import copy
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from run_simulator_timing import configured_house, plan, summarize
from unity_timing_worker import TimingRecorder, schedule


def test_plan_has_all_modes_and_fixed_windows_without_detector_choices():
    cells = plan()
    assert len(cells) == len({c["name"] for c in cells}) == 24
    assert [c["mode"] for c in cells[:6]] == [
        "auto",
        "frozen",
        "stepped",
        "stepped",
        "frozen",
        "auto",
    ]
    assert {c["site"] for c in cells} == {"north", "south"}
    assert {c["size"] for c in cells} == {320, 640}
    rows = [dict(cell=c, frames=[None] * 16) for c in cells]
    assert summarize(rows)["frames"] == 384
    for bad in (rows[:-1], rows[:-1] + rows[:1]):
        with pytest.raises(ValueError, match="matrix"):
            summarize(bad)
    changed = copy.deepcopy(rows)
    changed[0]["frames"].pop()
    with pytest.raises(ValueError, match="matrix"):
        summarize(changed)


def test_modes_only_change_explicit_control_field_of_same_house():
    cells = plan()[:3]
    houses = [configured_house(c) for c in cells]
    for h, c in zip(houses, cells, strict=True):
        assert h["metadata"].pop("cpswm_timing_mode") == c["mode"]
    assert houses[0] == houses[1] == houses[2]


class FakeController:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.last_event = self.event("CreateHouse")

    def event(self, action):
        return SimpleNamespace(
            frame=np.zeros((2, 2, 3), dtype=np.uint8),
            instance_masks={},
            metadata=dict(
                lastAction=action,
                lastActionSuccess=action != self.fail,
                errorMessage="failure" if action == self.fail else "",
            ),
        )

    def step(self, **kwargs):
        self.calls.append(kwargs)
        self.last_event = self.event(kwargs["action"])
        return self.last_event


def request():
    return dict(action_id=str(uuid4()), action="Pass", degrees=0.0)


@pytest.mark.parametrize(
    "mode,prepare,clock",
    [
        ("auto", "Pass", dict(action="Pass")),
        ("frozen", "PausePhysicsAutoSim", dict(action="Pass")),
        ("stepped", "PausePhysicsAutoSim", dict(action="AdvancePhysicsStep", timeStep=0.01)),
    ],
)
def test_public_image_is_from_actual_final_pass_with_matched_sdk_calls(
    tmp_path, mode, prepare, clock
):
    controller = FakeController()
    rec = TimingRecorder(controller, tmp_path, "target", mode)
    rec.prepare()
    for _ in range(16):
        event = rec.observe(request())
        assert event is controller.last_event and event.metadata["lastAction"] == "Pass"
    assert controller.calls == [dict(action=prepare)] + [
        item for _ in range(16) for item in (clock, dict(action="Pass"))
    ]
    assert len(rec.events) == 34
    with pytest.raises(ValueError, match="outside fixed"):
        rec.observe(request())
    assert len(controller.calls) == 33


@pytest.mark.parametrize("phase", ["before_prepare", "repeat_prepare", "duplicate", "rotation"])
def test_invalid_transition_rejected_before_another_sdk_call(tmp_path, phase):
    controller = FakeController()
    rec = TimingRecorder(controller, tmp_path, "target", "frozen")
    command = request()
    if phase != "before_prepare":
        rec.prepare()
    if phase == "duplicate":
        rec.observe(command)
    if phase == "rotation":
        command.update(action="RotateRight", degrees=45)
    before = len(controller.calls)
    with pytest.raises(ValueError):
        rec.prepare() if phase == "repeat_prepare" else rec.observe(command)
    assert len(controller.calls) == before


@pytest.mark.parametrize("failure", ["PausePhysicsAutoSim", "AdvancePhysicsStep", "Pass"])
def test_actual_control_failure_retains_receipt_and_does_not_return_success(tmp_path, failure):
    controller = FakeController(fail=failure)
    rec = TimingRecorder(controller, tmp_path, "target", "stepped")
    with pytest.raises(ValueError, match="SDK action failed"):
        rec.prepare()
        rec.observe(request())
    assert rec.events[-1]["metadata"]["lastActionSuccess"] is False
    assert (tmp_path / "sdk-events" / f"{len(rec.events) - 1:03d}.json").exists()
    assert rec.frames == 0


def test_undeclared_control_does_not_silently_fallback():
    with pytest.raises(ValueError, match="undeclared"):
        schedule("unknown", "clock")
