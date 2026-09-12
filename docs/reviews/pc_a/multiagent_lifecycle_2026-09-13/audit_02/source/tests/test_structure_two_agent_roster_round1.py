"""Round 1: synthetic SDK-contract attacks, not real multi-human evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from cpswm.data_preflight.agent_roster import AgentRosterError, require_agent_roster


def event(count=2, active=0, action="Initialize"):
    items = [
        SimpleNamespace(
            metadata={
                "agentId": i,
                "sceneName": "FloorPlan1",
                "lastAction": action,
                "lastActionSuccess": True,
                "errorMessage": "",
                "agent": {
                    "position": {"x": float(i), "y": 1.0, "z": 0.0},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                },
            }
        )
        for i in range(count)
    ]
    return SimpleNamespace(events=items, metadata=items[active].metadata)


def check(value):
    return require_agent_roster(value, count=2, action="Initialize", active_id=0)


def test_legal_rosters():
    for count in range(1, 7):
        assert require_agent_roster(
            event(count), count=count, action="Initialize", active_id=0
        ) == tuple(range(count))


@pytest.mark.parametrize("count", [0, -1, True, 2.0, 7, None])
def test_bad_count(count):
    with pytest.raises(ValueError):
        require_agent_roster(event(), count=count, action="Initialize", active_id=0)


@pytest.mark.parametrize("identity", [True, "1", 0, -1, 4, None])
def test_bad_or_duplicate_id(identity):
    value = event()
    value.events[1].metadata["agentId"] = identity
    with pytest.raises(AgentRosterError):
        check(value)


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("lastActionSuccess", False),
        ("lastActionSuccess", 1),
        ("lastAction", "CreateHouse"),
        ("errorMessage", "NotImplemented"),
        ("sceneName", ""),
        ("sceneName", None),
        ("agent", None),
    ],
)
def test_false_success_and_bad_metadata(field, replacement):
    value = event()
    value.metadata[field] = replacement
    with pytest.raises(AgentRosterError):
        check(value)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), True, "0"])
def test_invalid_pose(coordinate):
    value = event()
    value.events[1].metadata["agent"]["position"]["x"] = coordinate
    with pytest.raises(AgentRosterError):
        check(value)


def test_successful_singleton_not_two_agents():
    with pytest.raises(AgentRosterError):
        check(event(1))


def test_duplicate_pose():
    value = event()
    value.events[1].metadata["agent"] = deepcopy(value.metadata["agent"])
    with pytest.raises(AgentRosterError):
        check(value)


def test_active_alias_and_foreign_scene():
    with pytest.raises(AgentRosterError):
        check(event(active=1))
    value = event()
    value.events[1].metadata["sceneName"] = "Procedural"
    with pytest.raises(AgentRosterError):
        check(value)


def test_wrong_container():
    with pytest.raises(AgentRosterError):
        check(SimpleNamespace(metadata=event().metadata))


def test_permuted_events_keep_exact_roster():
    value = event()
    value.events.reverse()
    assert check(value) == (0, 1)
