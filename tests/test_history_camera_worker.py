import pytest
from test_simulator_timing import FakeController, request
from unity_history_loop_worker import HistoryCameraRecorder


def test_freeze_and_fixed_preparation_precede_actual_bounded_rotations(tmp_path):
    controller = FakeController()
    rec = HistoryCameraRecorder(controller, tmp_path, "target")
    rec.prepare()
    command = request()
    command.update(action="RotateLeft", degrees=45)
    event = rec.observe(command)
    assert event.metadata["lastAction"] == "RotateLeft"
    assert controller.calls == [
        dict(action="PausePhysicsAutoSim"),
        dict(action="Pass"),
        dict(action="Pass"),
        dict(action="RotateLeft", degrees=45),
    ]
    assert len(rec.events) == 5 and rec.events[-1]["owner"] == command["action_id"]
    with pytest.raises(ValueError, match="redispatch"):
        rec.observe(command)
    assert len(controller.calls) == 4


@pytest.mark.parametrize("mode", ["before_prepare", "repeat_prepare", "failed_rotation"])
def test_invalid_preparation_and_failed_action_do_not_return_success(tmp_path, mode):
    controller = FakeController(fail="RotateRight" if mode == "failed_rotation" else None)
    rec = HistoryCameraRecorder(controller, tmp_path, "target")
    command = request()
    command.update(action="RotateRight", degrees=45)
    if mode != "before_prepare":
        rec.prepare()
    with pytest.raises(ValueError):
        rec.prepare() if mode == "repeat_prepare" else rec.observe(command)
    if mode == "failed_rotation":
        assert rec.events[-1]["metadata"]["lastActionSuccess"] is False
