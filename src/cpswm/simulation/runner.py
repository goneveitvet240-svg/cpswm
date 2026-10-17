"""Observation -> native memory -> command -> simulator -> observed outcome."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
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
from cpswm.simulation.scenarios import CONDITIONS, Scenario, make_scenario
from cpswm.simulation.world import REGIONS, EventWorld, MujocoWorld, SimulationWorld


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


class SimulationController:
    """Policy only receives public observations and executor outcomes, never Scenario."""

    def __init__(self, episode_id: str, arm: str, root: Path | None = None) -> None:
        self.memory = SimulationMemory(episode_id, tuple(REGIONS), arm, root)
        self.queue = CommandQueue(episode_id)
        self.journal: list[dict[str, Any]] = []
        self.pending_outcome: tuple[Command, ExecutionFeedback, str] | None = None

    def observe(self, observation: Observation, tick: int) -> None:
        if self.pending_outcome is not None:
            raise ValueError("recover executed feedback before admitting another observation")
        changed = self.memory.ingest(observation, tick)
        self.queue.invalidate(self.memory.revision)
        self.journal.append(
            {
                "event": "observation",
                "tick": tick,
                "observation": observation.payload(),
                "changed": changed,
                "memory": self.memory.audit(),
            }
        )

    def plan(self) -> Command:
        command = self.queue.submit(
            "target", self.memory.destination(), self.memory.revision, max(0, self.memory.now)
        )
        self.journal.append(
            {
                "event": "plan",
                "command": asdict(command),
                "distribution": self.memory.destination_distribution(),
            }
        )
        return command

    def execute(
        self, world: SimulationWorld, tick: int, *, fail: bool = False
    ) -> ExecutionFeedback:
        if type(tick) is not int or tick < self.memory.now:
            raise ValueError("execution time must not precede admitted evidence")
        if self.pending_outcome is None:
            command = self.queue.pending or self.plan()
            revision = self.memory.revision
            self.queue.validate(command, revision)
            feedback = world.execute(command, tick, fail=fail)
            self.pending_outcome = (command, feedback, revision)
        command, feedback, revision = self.pending_outcome
        world.validate_feedback(command, feedback)
        self.queue.validate_completion(command, feedback, revision)
        # A failed memory update leaves the owned result pending. Retry consumes
        # the same result without issuing the physical command a second time.
        self.memory.observe_execution(feedback, tick)
        self.queue.complete(command, feedback, revision)
        self.pending_outcome = None
        self.queue.invalidate(self.memory.revision)
        self.journal.append(
            {"event": "feedback", "feedback": asdict(feedback), "memory": self.memory.audit()}
        )
        return feedback


def run_episode(
    scenario: Scenario,
    arm: str,
    backend: str = "event",
    output: Path | None = None,
    video: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    if backend not in {"event", "mujoco"}:
        raise ValueError("only simulation backends are allowed")
    if video and (backend != "mujoco" or output is None):
        raise ValueError("video requires MuJoCo and a unique output directory")
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    world = (
        EventWorld(scenario.episode_id, scenario.initial_location)
        if backend == "event"
        else MujocoWorld(
            scenario.episode_id,
            scenario.initial_location,
            output / "simulation.mp4" if video and output is not None else None,
        )
    )
    controller = SimulationController(scenario.episode_id, arm, root)
    try:
        for observation in scenario.history:
            controller.observe(observation, observation.available_at)
        original = controller.plan()
        for observation in scenario.corrections:
            controller.observe(observation, observation.available_at)
        corrected_destination = controller.memory.destination()
        # Every check costs one unit. Controller chooses using its public state;
        # same catalogue, budget and sensor are offered to all arms.
        suggested = controller.memory.current_location
        order = ([suggested] if suggested else []) + [k for k in REGIONS if k != suggested]
        found = False
        for index, location in enumerate(order):
            observation = world.inspect(location, 20 + index)
            controller.observe(observation, 20 + index)
            if observation.visibility == Visibility.OBSERVED:
                found = True
                break
        outcomes = []
        if found:
            for attempt in range(2):
                feedback = controller.execute(
                    world, 50 + attempt, fail=scenario.fail_first and attempt == 0
                )
                outcomes.append(feedback.status)
                if feedback.status == "succeeded":
                    break
        final = controller.memory.current_location
        result = {
            "episode_id": scenario.episode_id,
            "condition": scenario.condition,
            "arm": arm,
            "backend": backend,
            "evidence_level": "controlled_semantic_integration_fixture",
            "executor": "discrete_transport" if backend == "event" else "mujoco_2d_actuated_puck",
            "initial_destination": original.destination,
            "post_correction_destination": corrected_destination,
            "correction_changed_destination": original.destination != corrected_destination,
            "final_observed_location": final,
            "inspection_count": world.inspections,
            "execution_outcomes": outcomes,
            "control_steps": world.control_steps,
            "command_history": controller.queue.history,
            "journal": controller.journal,
            "memory": controller.memory.audit(),
            # Evaluator-only scoring, never fed into controller/world decisions.
            "evaluation": {
                "expected_destination": scenario.expected_destination,
                "task_success": bool(outcomes)
                and outcomes[-1] == "succeeded"
                and final == scenario.expected_destination,
                "wrong_destination": bool(outcomes) and final != scenario.expected_destination,
            },
            "limitations": [
                "synthetic_sensor_no_SAM",
                "no_VLA_or_robot_grasp",
                "six_engineering_fixtures_not_independent_holdout",
                "source_replay_adapter_not_native_global_retraction",
                "fixture_base_readout_not_frozen_v06",
                "no_joint_active_perception_claim",
            ],
        }
        if output is not None:
            save(output / "run.json", result)
            if isinstance(world, MujocoWorld):
                save(output / "trajectory.json", world.trajectory)
                (output / "scene.xml").write_text(world.xml)
        return result
    finally:
        world.close()


def run_suite(
    output: Path,
    backend: str = "event",
    arms: Sequence[str] | None = None,
    conditions: Sequence[str] | None = None,
    seed: int = 7,
    video: bool = False,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[3]
    files = [
        *sorted((root / "src/cpswm").rglob("*.py")),
        root / "tools/run_small_sim.py",
        root / "uv.lock",
        root / "configs/project_two_experiments/structure_two_stateful_full_joint_v0_1.json",
        root
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    import hashlib

    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    save(
        output / "manifest.json",
        {
            "code_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "working_tree": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ),
            "source_sha256": sources,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "backend": backend,
            "seed": seed,
            "seed_role": "identity_only_not_independent_dynamics",
            "packages": {p.metadata["Name"]: p.version for p in importlib.metadata.distributions()},
        },
    )
    rows = []
    for condition in conditions or CONDITIONS:
        scenario = make_scenario(condition, seed)
        for arm in arms or sorted(SimulationMemory.ARMS):
            directory = output / f"{condition}--{arm}"
            try:
                result = run_episode(scenario, arm, backend, directory, video, root)
            except Exception as exc:
                save(
                    output / "failure.json",
                    {
                        "condition": condition,
                        "arm": arm,
                        "status": "FAILED",
                        "error": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                raise
            rows.append(
                {
                    k: result[k]
                    for k in (
                        "condition",
                        "arm",
                        "evaluation",
                        "execution_outcomes",
                        "inspection_count",
                        "correction_changed_destination",
                        "control_steps",
                    )
                }
            )
            print(condition, arm, result["evaluation"], flush=True)
    summary = {
        "status": "ENGINEERING_RUN_COMPLETE",
        "scientific_acceptance": False,
        "backend": backend,
        "runs": len(rows),
        "results": rows,
        "manifest_digest": digest(sources),
        "source_unchanged": all(
            hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
            for name, expected in sources.items()
        ),
    }
    if not summary["source_unchanged"]:
        save(output / "failure.json", {"status": "FAILED", "error": "source_changed_during_run"})
        raise RuntimeError("source changed during simulation; results are not frozen")
    save(output / "summary.json", summary)
    return summary
