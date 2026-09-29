"""Distinguish a replaced action from starting/stopping or a fresh command ID."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

pytest.importorskip("torch")
from run_history_action_loop import action_transition

from cpswm.system.structure_two_continuous_input import ObservationCommand


def command(action="Pass", degrees=0.0):
    return ObservationCommand(
        uuid4(),
        uuid4(),
        action,
        degrees,
        "reporting fixture",
        (),
        datetime(2026, 9, 30, tzinfo=UTC),
    )


def test_no_old_plan_cannot_claim_an_existing_action_was_replaced():
    report = action_transition(None, command())
    assert report == {
        "old_pending_action": None,
        "new_action": ["Pass", 0.0],
        "action_transition_kind": "action_started",
        "decision_changed_at_same_physical_history": True,
        "action_changed_at_same_physical_history": False,
    }


def test_stopping_and_not_acting_do_not_claim_replacement():
    assert action_transition(command(), None)["action_transition_kind"] == "action_stopped"
    assert action_transition(command(), None)["action_changed_at_same_physical_history"] is False
    report = action_transition(None, None)
    assert report["action_transition_kind"] == "no_action"
    assert report["decision_changed_at_same_physical_history"] is False


def test_new_command_and_snapshot_ids_are_not_a_new_physical_action():
    old = command("RotateLeft", 90.0)
    new = replace(old, action_id=uuid4(), snapshot_id=uuid4(), reason="new generation")
    report = action_transition(old, new)
    assert report["action_transition_kind"] == "action_unchanged"
    assert report["decision_changed_at_same_physical_history"] is False
    assert report["action_changed_at_same_physical_history"] is False


@pytest.mark.parametrize(
    "new", [command(), command("RotateLeft", 45.0), command("RotateRight", 90.0)]
)
def test_real_action_or_angle_change_is_retained(new):
    report = action_transition(command("RotateLeft", 90.0), new)
    assert report["action_transition_kind"] == "action_replaced"
    assert report["decision_changed_at_same_physical_history"] is True
    assert report["action_changed_at_same_physical_history"] is True
