"""Memory-selected manipulation goals for the bounded LIBERO integration.

Semantic history and camera tracks have separate vocabularies and memories.
The existing controlled-fixture readout is unchanged. A propagated mask can
close an execution segment as UNKNOWN, never certify semantic task success.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from cpswm.simulation.contracts import (
    Command,
    CommandQueue,
    ExecutionFeedback,
    Observation,
    Visibility,
    digest,
)
from cpswm.simulation.memory import SimulationMemory


def observation_from_payload(body: dict[str, Any]) -> Observation:
    values = dict(body)
    values["visibility"] = Visibility(values["visibility"])
    values["actors"] = tuple(tuple(pair) for pair in values["actors"])
    return Observation(**values)


def fixture_observations(
    fixture: dict[str, Any],
) -> tuple[tuple[Observation, ...], tuple[Observation, ...]]:
    """Reuse the existing delayed-attribution fixture; no new readout/prior."""
    from cpswm.simulation.scenarios import make_scenario

    scenario = make_scenario(fixture["scenario"], fixture["history_seed"])
    correction_tick = fixture["initial_visual_tick"] + fixture["correction_after_control_steps"]

    def mapped(obs: Observation, correction: bool) -> Observation:
        return replace(
            obs,
            episode_id=fixture["episode_id"],
            location=None if obs.location is None else fixture["location_mapping"][obs.location],
            available_at=correction_tick if correction else obs.available_at,
        )

    return (
        tuple(mapped(obs, False) for obs in scenario.history),
        tuple(mapped(obs, True) for obs in scenario.corrections),
    )


@dataclass(frozen=True)
class GoalPlan:
    command: Command
    prompt: str
    goal_memory_revision: str
    visual_source_id: str

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, body: dict[str, Any]) -> GoalPlan:
        values = dict(body)
        values["command"] = Command(**values["command"])
        return cls(**values)


class MemoryGoalController:
    """Trusted local executor protocol, not an authenticated remote service.

    The adapter calls record_step only after a real simulator step returns. Step
    receipts establish sequence/binding here; physics is independently audited in
    the run artifacts. They are not cryptographic proof of physical execution.
    """

    def __init__(
        self,
        episode: str,
        catalogue: dict[str, str],
        arm: str = "native_joint",
        root: Path | None = None,
        *,
        memory_replay: str = "full",
    ) -> None:
        if len(catalogue) < 2 or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in catalogue.items()
        ):
            raise ValueError("at least two explicit destination-to-prompt entries required")
        if len(set(catalogue.values())) != len(catalogue):
            raise ValueError("distinct destinations require distinct prompts")
        if memory_replay not in {"full", "suffix"}:
            raise ValueError("unknown memory replay implementation")
        memory_class: type[SimulationMemory] = SimulationMemory
        if memory_replay == "suffix":
            from cpswm.simulation.suffix_memory import SuffixReplayMemory

            memory_class = SuffixReplayMemory
        self._catalogue = dict(catalogue)
        self.memory = memory_class(episode, tuple(catalogue), arm, root)
        self.visual = memory_class(
            episode, ("image_left", "image_center", "image_right"), arm, root
        )
        self.queue = CommandQueue(episode)
        self.pending: GoalPlan | None = None
        self.last_visual: Observation | None = None
        self.step_ticks: list[int] = []
        self.now = -1

    @property
    def revision(self) -> str:
        return digest([self.memory.revision, self.visual.revision, self._catalogue])

    def _time(self, now: int) -> None:
        if type(now) is not int or now < 0 or now < self.now:
            raise ValueError("goal-loop time must be monotone integer ticks")

    def _admit_new_evidence(self, now: int) -> None:
        self._time(now)
        if self.step_ticks:
            raise ValueError("settle executed segment before revising evidence")

    def _refresh(self, now: int) -> None:
        self.now = now
        self.queue.invalidate(self.revision)
        if self.pending is not None and self.pending.command != self.queue.pending:
            self.pending = None

    def observe_history(self, obs: Observation, now: int) -> None:
        self._admit_new_evidence(now)
        if obs.origin != "controlled_semantic_sensor" or obs.robot_generated:
            raise ValueError("semantic history requires explicit controlled provenance")
        self.memory.ingest(obs, now)
        self._refresh(now)

    @staticmethod
    def _visual_contract(obs: Observation, *, feedback: bool) -> None:
        if obs.actors != (("unknown_actor", 1.0),) or obs.revises is not None:
            raise ValueError("SAM provides no person attribution or semantic correction")
        if feedback:
            if (
                not obs.robot_generated
                or obs.origin != "sam2.1_tiny_propagation"
                or obs.identity_probability != 0.0
                or obs.visibility == Visibility.OBSERVED
            ):
                raise ValueError(
                    "propagation feedback must remain prediction/loss with no identity"
                )
        elif (
            obs.robot_generated
            or obs.origin != "sam2.1_tiny_operator_box"
            or obs.identity_probability != 1.0
            or obs.visibility == Visibility.PREDICTED
        ):
            raise ValueError("initial track requires explicit operator initialization")

    def observe_visual(self, obs: Observation, now: int) -> None:
        self._admit_new_evidence(now)
        if self.last_visual is not None:
            raise ValueError("track already initialized; use execution feedback")
        self._visual_contract(obs, feedback=False)
        self.visual.ingest(obs, now)
        self.last_visual = obs
        self._refresh(now)

    def plan(self, tick: int) -> dict[str, Any]:
        self._time(tick)
        if self.pending is not None:
            raise ValueError("a goal plan is already pending")
        distribution = self.memory.destination_distribution()
        if self.last_visual is None or self.last_visual.visibility == Visibility.LOST:
            return {"status": "needs_visual_confirmation", "distribution": distribution}
        best = max(distribution.values())
        winners = [key for key, value in distribution.items() if abs(value - best) < 1e-12]
        if len(winners) != 1:
            return {"status": "needs_history_evidence", "distribution": distribution}
        destination = winners[0]
        command = self.queue.submit("target", destination, self.revision, tick)
        self.pending = GoalPlan(
            command, self._catalogue[destination], self.memory.revision, self.last_visual.source_id
        )
        self.now = tick
        return {"status": "ready", "plan": self.pending.payload(), "distribution": distribution}

    def validate(self, plan: GoalPlan) -> None:
        if plan != self.pending:
            raise ValueError("unissued, changed or stale goal plan")
        self.queue.validate(plan.command, self.revision)

    def record_step(self, plan: GoalPlan, completed_at: int) -> None:
        self.validate(plan)
        expected = (self.step_ticks[-1] if self.step_ticks else plan.command.issued_at) + 1
        if type(completed_at) is not int or completed_at != expected or len(self.step_ticks) >= 5:
            raise ValueError("execution receipts must be contiguous, at most five per segment")
        self.step_ticks.append(completed_at)
        self.now = completed_at

    def feedback(self, plan: GoalPlan, obs: Observation, control_steps: int) -> None:
        self.validate(plan)
        self._visual_contract(obs, feedback=True)
        if (
            type(control_steps) is not int
            or not self.step_ticks
            or control_steps != len(self.step_ticks)
            or obs.occurred_at != self.step_ticks[-1]
            or obs.available_at != obs.occurred_at
        ):
            raise ValueError("feedback must describe the recorded executed segment")
        feedback = ExecutionFeedback(plan.command.command_id, obs, "unknown", control_steps)
        before = self.revision
        self.queue.validate_completion(plan.command, feedback, before)
        # Build/admit first. On failure the pending plan/step receipts survive so
        # the SAME feedback can be retried without repeating physical actions.
        self.visual.observe_execution(feedback, obs.available_at)
        self.queue.complete(plan.command, feedback, before)
        self.last_visual = obs
        self.step_ticks = []
        self.pending = None
        self._refresh(obs.available_at)

    def audit(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "semantic_memory": self.memory.audit(),
            "visual_memory": self.visual.audit(),
            "queue_history": self.queue.history,
            "pending_plan": None if self.pending is None else self.pending.payload(),
            "recorded_step_ticks": list(self.step_ticks),
            "feedback_status": "unknown" if self.visual.feedback else "not_executed",
            "evidence_level": "controlled semantic history + separately admitted camera track",
            "scientific_acceptance": False,
        }
