"""Interchangeable event and MuJoCo integration worlds.

The MuJoCo backend uses a two-axis actuator-driven puck, NOT a robot grasp
controller. Both currently expose a declared controlled semantic sensor.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cpswm.simulation.contracts import Command, ExecutionFeedback, Observation, Visibility

REGIONS = {"left": (-0.28, 0.0), "center": (0.0, 0.0), "right": (0.28, 0.0)}


class SimulationWorld(Protocol):
    episode_id: str

    def inspect(self, location: str, tick: int) -> Observation: ...
    def execute(self, command: Command, tick: int, *, fail: bool = False) -> ExecutionFeedback: ...
    def validate_feedback(self, command: Command, feedback: ExecutionFeedback) -> None: ...
    def close(self) -> None: ...


@dataclass
class EventWorld:
    episode_id: str
    initial_location: str = "center"

    def __post_init__(self) -> None:
        if self.initial_location not in REGIONS:
            raise ValueError("unknown initial region")
        self._location = self.initial_location
        self.executed: set[str] = set()
        self.inspections = 0
        self.control_steps = 0
        self.receipts: dict[str, tuple[Command, ExecutionFeedback]] = {}

    def _sensed_location(self) -> str | None:
        return self._location

    def inspect(self, location: str, tick: int) -> Observation:
        if location not in REGIONS or type(tick) is not int or tick < 0:
            raise ValueError("unknown inspection region")
        self.inspections += 1
        found = location == self._sensed_location()
        key = f"{self.episode_id}:inspect:{self.inspections}"
        return Observation(
            self.episode_id,
            key,
            key,
            tick,
            tick,
            "target",
            Visibility.OBSERVED if found else Visibility.LOST,
            location if found else None,
            robot_generated=True,
        )

    def _move(self, destination: str, fail: bool) -> int:
        if not fail:
            self._location = destination
        self.control_steps += 1
        return 1

    def execute(self, command: Command, tick: int, *, fail: bool = False) -> ExecutionFeedback:
        if (
            command.episode_id != self.episode_id
            or command.object_id != "target"
            or command.destination not in REGIONS
            or command.command_id in self.executed
            or type(tick) is not int
            or tick < command.issued_at
        ):
            raise ValueError("invalid or duplicate simulation command")
        steps = self._move(command.destination, fail)
        self.executed.add(command.command_id)
        location = self._sensed_location()
        status = (
            "unknown"
            if location is None
            else "succeeded"
            if location == command.destination
            else "failed"
        )
        key = f"{self.episode_id}:execution:{command.command_id}"
        observation = Observation(
            self.episode_id,
            key,
            key,
            tick,
            tick,
            "target",
            Visibility.LOST if location is None else Visibility.OBSERVED,
            location,
            robot_generated=True,
        )
        feedback = ExecutionFeedback(command.command_id, observation, status, steps)
        self.receipts[command.command_id] = (command, feedback)
        return feedback

    def validate_feedback(self, command: Command, feedback: ExecutionFeedback) -> None:
        if self.receipts.get(command.command_id) != (command, feedback):
            raise ValueError("feedback is not the executor-owned receipt")

    def close(self) -> None:
        pass


class MujocoWorld(EventWorld):
    """Minimal actual dynamics backend with replaceable execution, headless by default."""

    def __init__(
        self, episode_id: str, initial_location: str = "center", video_path: Path | None = None
    ) -> None:
        mujoco = importlib.import_module("mujoco")

        super().__init__(episode_id, initial_location)
        self.mujoco = mujoco
        pads = "".join(
            f'<geom name="{name}" type="cylinder" pos="{x} {y} 0.006" '
            'size="0.075 0.005" rgba="0.3 0.5 0.7 0.5" contype="0" conaffinity="0"/>'
            for name, (x, y) in REGIONS.items()
        )
        self.xml = f"""<mujoco model="CPSWM integration puck">
          <option timestep="0.004" gravity="0 0 -9.81"/>
          <visual><global offwidth="640" offheight="480"/></visual>
          <worldbody>
            <light pos="0 -1 2"/>
            <camera name="overview" pos="0 -1.25 1.2" xyaxes="1 0 0 0 0.69 0.72"/>
            <geom type="plane" size="0.65 0.45 0.02" rgba="0.92 0.91 0.87 1"/>
            {pads}
            <body name="payload" pos="0 0 0.04">
              <joint name="x" type="slide" axis="1 0 0" damping="4"/>
              <joint name="y" type="slide" axis="0 1 0" damping="4"/>
              <geom type="cylinder" size="0.035 0.025" mass="0.15" rgba="0.85 0.15 0.08 1"/>
            </body>
          </worldbody>
          <actuator>
            <position joint="x" kp="80" ctrlrange="-0.4 0.4"/>
            <position joint="y" kp="80" ctrlrange="-0.3 0.3"/>
          </actuator>
        </mujoco>"""
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.data.qpos[:] = REGIONS[initial_location]
        self.data.ctrl[:] = REGIONS[initial_location]
        mujoco.mj_forward(self.model, self.data)
        self.renderer = self.writer = None
        self.trajectory: list[dict[str, Any]] = []
        if video_path is not None:
            imageio = importlib.import_module("imageio.v2")

            self.renderer = mujoco.Renderer(self.model, height=480, width=640)
            self.writer = imageio.get_writer(str(video_path), fps=25, codec="libx264")
            self._frame()

    def _frame(self) -> None:
        if self.renderer is not None and self.writer is not None:
            self.renderer.update_scene(self.data, camera="overview")
            self.writer.append_data(self.renderer.render())

    def _sensed_location(self) -> str | None:
        import numpy as np

        distances = {k: float(np.linalg.norm(self.data.qpos[:2] - p)) for k, p in REGIONS.items()}
        best = min(distances, key=lambda k: distances[k])
        return best if distances[best] < 0.06 else None

    def _move(self, destination: str, fail: bool) -> int:
        if not fail:
            self.data.ctrl[:] = REGIONS[destination]
        # One second of real MuJoCo integration, with raw state retained for audit.
        for i in range(250):
            self.mujoco.mj_step(self.model, self.data)
            if i % 10 == 0:
                self.trajectory.append(
                    {
                        "time": float(self.data.time),
                        "qpos": self.data.qpos.tolist(),
                        "control": self.data.ctrl.tolist(),
                    }
                )
                self._frame()
        self.control_steps += 250
        return 250

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
        if self.renderer is not None:
            self.renderer.close()
