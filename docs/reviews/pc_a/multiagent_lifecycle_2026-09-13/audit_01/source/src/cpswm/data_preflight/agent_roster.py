"""Fail-closed SDK agent checks, not authentication or a humanoid capability gate.

The runtime owner supplies the real controller. Never infer an agent from a
schedule actor, a requested count, a success flag alone, or a synthetic event.
"""

from __future__ import annotations

import math
from typing import Any


class AgentRosterError(RuntimeError):
    """The observed runtime does not satisfy the requested agent contract."""


def require_agent_roster(
    event: Any,
    *,
    count: int,
    action: str,
    active_id: int,
    scene_name: str | None = None,
) -> tuple[int, ...]:
    """Validate actual SDK metadata. This does not prove independent movement."""
    if type(count) is not int or not 1 <= count <= 6:
        raise ValueError("agent count must be an integer in the supported probe range 1..6")
    if type(active_id) is not int or not 0 <= active_id < count:
        raise ValueError("active agent outside expected roster")
    if not isinstance(action, str) or not action:
        raise ValueError("expected action is required")
    events = getattr(event, "events", None)
    if not isinstance(events, (list, tuple)) or len(events) != count:
        observed = len(events) if isinstance(events, (list, tuple)) else None
        raise AgentRosterError(f"requested {count} agents, observed {observed}; stop acquisition")
    ids = []
    poses = []
    scenes = []
    active = None
    for item in events:
        metadata = getattr(item, "metadata", None)
        if not isinstance(metadata, dict):
            raise AgentRosterError("missing agent metadata")
        identity = metadata.get("agentId")
        if type(identity) is not int:
            raise AgentRosterError("agent identity must be an integer, not bool or an alias")
        ids.append(identity)
        scene = metadata.get("sceneName")
        if (
            not isinstance(scene, str)
            or not scene
            or (scene_name is not None and scene != scene_name)
        ):
            raise AgentRosterError("missing or changed scene identity")
        scenes.append(scene)
        agent = metadata.get("agent")
        if not isinstance(agent, dict):
            raise AgentRosterError("missing physical agent pose")
        for key in ("position", "rotation"):
            point = agent.get(key)
            if not isinstance(point, dict) or set(point) != {"x", "y", "z"}:
                raise AgentRosterError("missing xyz pose")
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in point.values()):
                raise AgentRosterError("nonfinite or nonnumeric pose")
        poses.append(tuple(agent["position"][k] for k in ("x", "y", "z")))
        if identity == active_id:
            active = metadata
    if sorted(ids) != list(range(count)) or len(set(scenes)) != 1:
        raise AgentRosterError("duplicate, missing or foreign agent/scene identity")
    if len(set(poses)) != count:
        raise AgentRosterError("different agents alias the same physical position")
    selected = getattr(event, "metadata", None)
    if not isinstance(selected, dict) or selected != active:
        raise AgentRosterError("active event does not match addressed agent")
    if (
        active is None
        or active.get("lastAction") != action
        or active.get("lastActionSuccess") is not True
    ):
        raise AgentRosterError("missing, failed or stale action acknowledgement")
    if active.get("errorMessage") not in ("", None):
        raise AgentRosterError("success acknowledgement also contains an error")
    return tuple(sorted(ids))


class VerifiedAgentSession:
    """Serial checked actions; no reset/reinitialization or reuse after uncertainty.

    This is a roster/dispatch guard only. It cannot authenticate caller-provided
    controllers, certify humanoids, or prove that interactions obey physics.
    """

    def __init__(self, controller: Any, *, count: int, initial_action: str) -> None:
        require_agent_roster(controller.last_event, count=count, action=initial_action, active_id=0)
        self._controller = controller
        self._count = count
        self._scene = controller.last_event.metadata["sceneName"]
        self._poisoned = False

    def step(self, *, action: str, agentId: int, **kwargs: Any) -> Any:
        if self._poisoned:
            raise AgentRosterError("uncertain prior action; this session cannot continue")
        if (
            not isinstance(action, str)
            or not action
            or action in {"Reset", "Initialize", "CreateHouse"}
        ):
            raise ValueError("lifecycle mutation requires a fresh verified session")
        if type(agentId) is not int or not 0 <= agentId < self._count:
            raise ValueError("agent outside verified roster")
        self._poisoned = True
        # Recheck before dispatch so an external reset cannot silently change the roster.
        current = self._controller.last_event
        require_agent_roster(
            current,
            count=self._count,
            action=current.metadata.get("lastAction"),
            active_id=current.metadata.get("agentId"),
            scene_name=self._scene,
        )
        event = self._controller.step(action=action, agentId=agentId, **kwargs)
        require_agent_roster(
            event, count=self._count, action=action, active_id=agentId, scene_name=self._scene
        )
        self._poisoned = False
        return event
