"""Public, time-aware observations and revision-bound simulation commands."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


class Visibility(StrEnum):
    OBSERVED = "observed"
    PREDICTED = "predicted"
    LOST = "lost"


@dataclass(frozen=True)
class Observation:
    episode_id: str
    source_id: str
    event_id: str
    occurred_at: int
    available_at: int
    object_id: str
    visibility: Visibility
    location: str | None
    # Synthetic annotations in v0.1, never claimed to be visual person recognition.
    actors: tuple[tuple[str, float], ...] = (("unknown_actor", 1.0),)
    revises: str | None = None
    origin: str = "controlled_semantic_sensor"
    robot_generated: bool = False
    identity_probability: float = 1.0

    def __post_init__(self) -> None:
        if not all(
            isinstance(x, str) and x.strip()
            for x in (self.episode_id, self.source_id, self.event_id, self.object_id, self.origin)
        ):
            raise ValueError("observation identifiers must be nonempty")
        if type(self.robot_generated) is not bool:
            raise ValueError("robot_generated must be a boolean")
        if type(self.actors) is not tuple or any(type(pair) is not tuple for pair in self.actors):
            raise ValueError("actor evidence must be immutable")
        if any(type(t) is not int or t < 0 for t in (self.occurred_at, self.available_at)):
            raise ValueError("timestamps must be nonnegative integer ticks")
        if self.available_at < self.occurred_at:
            raise ValueError("evidence cannot arrive before the event")
        if not isinstance(self.visibility, Visibility):
            raise ValueError("visibility must be an explicit enum")
        if (self.visibility == Visibility.LOST) != (self.location is None):
            raise ValueError("lost has no location; observed/predicted requires a location")
        values = dict(self.actors)
        if (
            len(values) != len(self.actors)
            or not values
            or any(not key or not math.isfinite(v) or not 0 <= v <= 1 for key, v in self.actors)
            or not math.isclose(sum(values.values()), 1.0, abs_tol=1e-9)
        ):
            raise ValueError("actor probabilities must be unique, finite and normalized")
        if self.revises == self.source_id:
            raise ValueError("a source cannot revise itself")
        if not math.isfinite(self.identity_probability) or not 0 <= self.identity_probability <= 1:
            raise ValueError("identity probability must be finite and in [0, 1]")

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Command:
    episode_id: str
    command_id: str
    memory_revision: str
    object_id: str
    destination: str
    issued_at: int = 0


@dataclass(frozen=True)
class ExecutionFeedback:
    command_id: str
    observation: Observation
    status: str  # succeeded, failed, unknown; issued is never succeeded
    control_steps: int


class CommandQueue:
    """Single-flight commands; changed evidence invalidates an unexecuted plan."""

    def __init__(self, episode_id: str) -> None:
        self.episode_id = episode_id
        self.pending: Command | None = None
        self.executed: set[str] = set()
        self.history: list[dict[str, Any]] = []
        self.current_revision: str | None = None

    def invalidate(self, revision: str) -> None:
        if self.pending is not None and self.pending.memory_revision != revision:
            self.history.append({"event": "cancelled", "command": asdict(self.pending)})
            self.pending = None
        self.current_revision = revision

    def submit(self, object_id: str, destination: str, revision: str, tick: int = 0) -> Command:
        if type(tick) is not int or tick < 0:
            raise ValueError("command time must be a nonnegative tick")
        self.invalidate(revision)
        if self.pending is not None:
            raise ValueError("a command is already pending")
        token = digest([self.episode_id, revision, object_id, destination, tick, len(self.history)])
        self.pending = Command(self.episode_id, token, revision, object_id, destination, tick)
        self.history.append({"event": "issued", "command": asdict(self.pending)})
        return self.pending

    def validate(self, command: Command, revision: str) -> None:
        if (
            command != self.pending
            or command.episode_id != self.episode_id
            or command.memory_revision != revision
            or self.current_revision != revision
            or command.command_id in self.executed
        ):
            raise ValueError("stale, foreign, replaced or already executed command")

    def validate_completion(
        self, command: Command, feedback: ExecutionFeedback, revision: str
    ) -> None:
        self.validate(command, revision)
        obs = feedback.observation
        obs.__post_init__()
        if (
            feedback.command_id != command.command_id
            or obs.episode_id != self.episode_id
            or obs.object_id != command.object_id
            or not obs.robot_generated
            or feedback.status not in {"succeeded", "failed", "unknown"}
            or type(feedback.control_steps) is not int
            or feedback.control_steps < 0
            or obs.occurred_at < command.issued_at
        ):
            raise ValueError("feedback is not bound to the issued command")
        visible = obs.visibility == Visibility.OBSERVED
        if feedback.status == "succeeded" and (not visible or obs.location != command.destination):
            raise ValueError("success requires a fresh destination observation")
        if feedback.status == "failed" and (not visible or obs.location == command.destination):
            raise ValueError("failure requires an observed destination mismatch")
        if feedback.status == "unknown" and visible:
            raise ValueError("visible outcome must be resolved")

    def complete(self, command: Command, feedback: ExecutionFeedback, revision: str) -> None:
        self.validate_completion(command, feedback, revision)
        self.executed.add(command.command_id)
        self.pending = None
        self.history.append({"event": "completed", "feedback": asdict(feedback)})
