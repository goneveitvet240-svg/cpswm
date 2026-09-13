"""Round 2: forged-complete responses, stale transport and session consequences.

All controllers in this file are explicit unit fixtures, not simulator evidence.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from cpswm.data_preflight.agent_roster import AgentRosterError, VerifiedAgentSession
from test_structure_two_agent_roster_round1 import event


class FixtureController:
    def __init__(self):
        self.last_event = event()
        self.calls = []
        self.server = SimpleNamespace(raw_metadata={}, sequence_id=10)
        self.sync(10)
        self.mode = "ok"

    def sync(self, sequence):
        self.server.sequence_id = sequence
        self.server.raw_metadata = {
            "sequenceId": sequence, "activeAgentId": self.last_event.metadata["agentId"],
            "agents": [deepcopy(e.metadata) for e in self.last_event.events],
        }

    def step(self, action, agentId, **kwargs):
        self.calls.append((action, agentId))
        if self.mode == "timeout":
            raise TimeoutError("fixture timeout")
        old_sequence = self.server.sequence_id
        self.last_event = event(active=agentId, action=action)
        if self.mode == "dropped":
            self.last_event.events.pop()
        self.sync(old_sequence + (0 if self.mode == "stale" else 1))
        if self.mode == "raw_foreign":
            self.server.raw_metadata["activeAgentId"] = 99
        if self.mode == "raw_dropped":
            self.server.raw_metadata["agents"].pop()
        return self.last_event


def session(controller):
    return VerifiedAgentSession(controller, count=2, initial_action="Initialize")


def test_legal_serial_addressing():
    controller = FixtureController()
    checked = session(controller)
    for i in (0, 1, 0):
        assert checked.step(action="Pass", agentId=i).metadata["agentId"] == i
    assert controller.calls == [("Pass", 0), ("Pass", 1), ("Pass", 0)]


@pytest.mark.parametrize("action", ["Reset", "CreateHouse", "Initialize"])
def test_no_lifecycle_mutation(action):
    controller = FixtureController()
    with pytest.raises(ValueError):
        session(controller).step(action=action, agentId=0)
    assert controller.calls == []


@pytest.mark.parametrize("identity", [True, -1, 2, "1"])
def test_invalid_address_no_dispatch(identity):
    controller = FixtureController()
    with pytest.raises(ValueError):
        session(controller).step(action="Pass", agentId=identity)
    assert controller.calls == []


@pytest.mark.parametrize("mode", ["timeout", "dropped", "stale", "raw_foreign", "raw_dropped"])
def test_uncertain_or_forged_complete_response_poisoned(mode):
    controller = FixtureController()
    checked = session(controller)
    controller.mode = mode
    with pytest.raises((AgentRosterError, TimeoutError)):
        checked.step(action="Pass", agentId=0)
    controller.mode = "ok"
    with pytest.raises(AgentRosterError):
        checked.step(action="Pass", agentId=1)
    assert len(controller.calls) == 1


def test_out_of_band_reset_before_dispatch():
    controller = FixtureController()
    checked = session(controller)
    controller.last_event = event(1)
    controller.sync(0)
    with pytest.raises(AgentRosterError):
        checked.step(action="Pass", agentId=0)
    assert controller.calls == []


def test_replayed_complete_external_state_before_dispatch():
    controller = FixtureController()
    checked = session(controller)
    controller.sync(11)
    with pytest.raises(AgentRosterError):
        checked.step(action="Pass", agentId=0)
    assert controller.calls == []
