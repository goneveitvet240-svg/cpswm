"""Goal/command/feedback boundaries; real physics evidence is separate."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.simulation.contracts import Command, Observation, Visibility
from cpswm.simulation.goal_control import (
    GoalPlan,
    MemoryGoalController,
    fixture_observations,
    observation_from_payload,
)
from cpswm.simulation.integrations.bridge import NativeBridge

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "configs/simulation/libero_goal_fixture.json"
CONFIG = json.loads(FIXTURE.read_text())


def visual(tick=100, *, robot=False, lost=False):
    return Observation(
        CONFIG["episode_id"],
        f"sam:{tick}",
        f"visual:{tick}",
        tick,
        tick,
        "target",
        Visibility.LOST if lost else Visibility.PREDICTED if robot else Visibility.OBSERVED,
        None if lost else "image_center",
        origin="sam2.1_tiny_propagation" if robot else "sam2.1_tiny_operator_box",
        robot_generated=robot,
        identity_probability=0.0 if robot else 1.0,
    )


def ready(arm="source_replay"):
    controller = MemoryGoalController(CONFIG["episode_id"], CONFIG["catalogue"], arm)
    history, _ = fixture_observations(CONFIG)
    for obs in history:
        controller.observe_history(obs, obs.available_at)
    controller.observe_visual(visual(), 100)
    return controller


def plan(controller, tick=100):
    result = controller.plan(tick)
    assert result["status"] == "ready"
    return GoalPlan.from_payload(result["plan"])


@pytest.mark.parametrize(
    "arm", ["native_joint", "native_factorized", "source_replay", "ordinary_memory"]
)
def test_same_camera_delayed_attribution_changes_prompt_only_for_revising_arms(arm):
    corrected, control = ready(arm), ready(arm)
    first = plan(corrected)
    assert first.command.destination == "stove"
    _, corrections = fixture_observations(CONFIG)
    for obs in corrections:
        corrected.observe_history(obs, 102)
    if arm == "ordinary_memory":
        assert corrected.pending == first
        assert corrected.memory.destination() == "stove"
    else:
        with pytest.raises(ValueError, match="stale"):
            corrected.validate(first)
        second = plan(corrected, 102)
        assert second.command.destination == "plate"
        assert second.prompt == CONFIG["catalogue"]["plate"]
        assert second.visual_source_id == first.visual_source_id
    uncorrected = plan(control, 102)
    assert uncorrected.prompt == CONFIG["catalogue"]["stove"]
    if arm.startswith("native"):
        assert corrected.memory.audit()["particles"] == 24


def test_feedback_updates_visual_revision_without_teaching_owner_robot_habit():
    controller = ready("native_joint")
    before = controller.memory.audit()
    first = plan(controller)
    for tick in (101, 102):
        controller.record_step(first, tick)
    controller.feedback(first, visual(102, robot=True), 2)
    assert controller.memory.audit() == before
    assert controller.visual.current_location is None
    assert controller.visual.feedback[0]["status"] == "unknown"
    assert controller.queue.pending is None
    assert controller.revision != first.command.memory_revision
    _, corrections = fixture_observations(CONFIG)
    for obs in corrections:
        controller.observe_history(obs, 102)
    second = plan(controller, 102)
    assert second.prompt == CONFIG["catalogue"]["plate"]
    controller.record_step(second, 103)
    controller.feedback(second, visual(103, robot=True), 1)
    assert len(controller.queue.executed) == 2
    with pytest.raises(ValueError):
        controller.feedback(second, visual(103, robot=True), 1)


def test_fully_formed_but_unissued_plan_is_rejected():
    controller = ready()
    command = Command(
        CONFIG["episode_id"], "plausible", controller.revision, "target", "plate", 100
    )
    forged = GoalPlan(command, CONFIG["catalogue"]["plate"], controller.memory.revision, "sam:100")
    for operation in (
        lambda: controller.validate(forged),
        lambda: controller.record_step(forged, 101),
        lambda: controller.feedback(forged, visual(101, robot=True), 1),
    ):
        with pytest.raises(ValueError):
            operation()
    assert not controller.visual.feedback and not controller.queue.history


@pytest.mark.parametrize(
    "change", ["prompt", "destination", "goal_revision", "visual_source", "episode"]
)
def test_issued_plan_field_tampering_rejected(change):
    controller = ready()
    issued = plan(controller)
    forged = {
        "prompt": replace(issued, prompt=CONFIG["catalogue"]["plate"]),
        "destination": replace(issued, command=replace(issued.command, destination="plate")),
        "goal_revision": replace(issued, goal_memory_revision="forged"),
        "visual_source": replace(issued, visual_source_id="forged"),
        "episode": replace(issued, command=replace(issued.command, episode_id="foreign")),
    }[change]
    with pytest.raises(ValueError):
        controller.record_step(forged, 101)
    controller.validate(issued)
    assert controller.step_ticks == []


@pytest.mark.parametrize(
    "change", ["observed", "person", "identity", "human", "future", "foreign", "location", "count"]
)
def test_execution_feedback_cannot_promote_prediction_or_forge_binding(change):
    controller = ready()
    issued = plan(controller)
    controller.record_step(issued, 101)
    good = visual(101, robot=True)
    bad = {
        "observed": replace(good, visibility=Visibility.OBSERVED),
        "person": replace(good, actors=(("owner", 1.0),)),
        "identity": replace(good, identity_probability=1.0),
        "human": replace(good, robot_generated=False),
        "future": replace(good, available_at=102),
        "foreign": replace(good, episode_id="foreign"),
        "location": replace(good, location="plate"),
        "count": good,
    }[change]
    before = controller.audit()
    with pytest.raises(ValueError):
        controller.feedback(issued, bad, 2 if change == "count" else 1)
    assert controller.audit() == before
    controller.feedback(issued, good, 1)


def test_failed_feedback_admission_can_retry_without_reexecuting(monkeypatch):
    controller = ready()
    issued = plan(controller)
    controller.record_step(issued, 101)
    original = controller.visual.ingest

    def fail(*args):
        raise RuntimeError("injected memory admission failure")

    monkeypatch.setattr(controller.visual, "ingest", fail)
    with pytest.raises(RuntimeError, match="admission"):
        controller.feedback(issued, visual(101, robot=True), 1)
    assert controller.step_ticks == [101] and not controller.queue.executed
    monkeypatch.setattr(controller.visual, "ingest", original)
    controller.feedback(issued, visual(101, robot=True), 1)
    assert len(controller.queue.executed) == 1


def test_revision_cannot_erase_unsettled_execution():
    controller = ready()
    issued = plan(controller)
    controller.record_step(issued, 101)
    _, corrections = fixture_observations(CONFIG)
    with pytest.raises(ValueError, match="settle"):
        controller.observe_history(corrections[0], 102)
    controller.validate(issued)
    with pytest.raises(ValueError):
        controller.record_step(issued, 101)
    with pytest.raises(ValueError):
        controller.record_step(issued, 103)


def test_feedback_requires_steps_and_segment_cannot_exceed_five():
    controller = ready()
    issued = plan(controller)
    with pytest.raises(ValueError):
        controller.feedback(issued, visual(100, robot=True), 0)
    for tick in range(101, 106):
        controller.record_step(issued, tick)
    with pytest.raises(ValueError):
        controller.record_step(issued, 106)
    controller.feedback(issued, visual(105, robot=True), 5)


def test_missing_lost_track_and_tied_history_do_not_issue_actions():
    controller = MemoryGoalController(CONFIG["episode_id"], CONFIG["catalogue"], "source_replay")
    assert controller.plan(100)["status"] == "needs_visual_confirmation"
    controller.observe_visual(visual(), 100)
    assert controller.plan(100)["status"] == "needs_history_evidence"
    assert not controller.queue.history
    controller = ready()
    issued = plan(controller)
    controller.record_step(issued, 101)
    controller.feedback(issued, visual(101, robot=True, lost=True), 1)
    assert controller.plan(101)["status"] == "needs_visual_confirmation"
    assert controller.pending is None


def test_invalid_history_is_atomic_and_does_not_invalidate_issued_plan():
    controller = ready()
    issued = plan(controller)
    history, corrections = fixture_observations(CONFIG)
    before = controller.audit()
    for obs, now in (
        (history[0], 100),
        (corrections[0], 101),
        (replace(corrections[0], revises="unadmitted"), 102),
        (replace(corrections[0], location="image_left"), 102),
        (replace(corrections[0], robot_generated=True), 102),
    ):
        with pytest.raises(ValueError):
            controller.observe_history(obs, now)
        assert controller.audit() == before
    controller.validate(issued)


def test_round_trip_does_not_mutate_transport_payload():
    payload = visual().payload()
    original = json.dumps(payload)
    assert observation_from_payload(payload) == visual()
    assert json.dumps(payload) == original


def test_worker_roundtrip_and_errors_do_not_desynchronize():
    bridge = NativeBridge(
        sys.executable, ROOT, CONFIG["episode_id"], "source_replay", goal_fixture=FIXTURE
    )
    try:
        history, _ = fixture_observations(CONFIG)
        for obs in history:
            bridge.observe(
                {"operation": "history", "observation": obs.payload(), "now": obs.available_at}
            )
        bridge.observe({"operation": "visual", "observation": visual().payload(), "now": 100})
        selected = bridge.observe({"operation": "plan", "tick": 100})
        assert selected["plan"]["prompt"] == CONFIG["catalogue"]["stove"]
        with pytest.raises(RuntimeError):
            bridge.observe(
                {
                    "operation": "feedback",
                    "plan": selected["plan"],
                    "observation": visual(101, robot=True).payload(),
                    "control_steps": 1,
                }
            )
        bridge.observe({"operation": "step", "plan": selected["plan"], "completed_at": 101})
        reply = bridge.observe(
            {
                "operation": "feedback",
                "plan": selected["plan"],
                "observation": visual(101, robot=True).payload(),
                "control_steps": 1,
            }
        )
        assert reply["audit"]["feedback_status"] == "unknown"
    finally:
        bridge.close()
