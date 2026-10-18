"""Pinned LIBERO wrapper; object ground truth stays inside the evaluator."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

TASKS = {
    "table_center": "pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate",
    "between": "pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate",
    "drawer": (
        "pick_up_the_black_bowl_in_the_top_drawer_of_the_wooden_cabinet_and_place_it_on_the_plate"
    ),
}
PUBLIC_KEYS = (
    "agentview_image",
    "robot0_eye_in_hand_image",
    "robot0_eef_pos",
    "robot0_eef_quat",
    "robot0_gripper_qpos",
)


def configure_libero(repository: Path, config_dir: Path) -> None:
    """Avoid upstream interactive config creation in the user's home directory."""
    import yaml

    base = repository.resolve() / "libero" / "libero"
    if not (base / "bddl_files").is_dir():
        raise FileNotFoundError(f"not a LIBERO checkout: {repository}")
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "benchmark_root": str(base),
        "bddl_files": str(base / "bddl_files"),
        "init_states": str(base / "init_files"),
        "datasets": str(repository / "datasets"),
        "assets": str(base / "assets"),
    }
    (config_dir / "config.yaml").write_text(yaml.safe_dump(cfg))
    os.environ["LIBERO_CONFIG_PATH"] = str(config_dir.resolve())


def public_observation(obs: dict[str, Any]) -> dict[str, Any]:
    return {key: np.asarray(obs[key]).copy() for key in PUBLIC_KEYS}


class LiberoEnvironment:
    def __init__(self, task_key: str, initial_state: int = 0, seed: int = 7) -> None:
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv

        if task_key not in TASKS or initial_state < 0:
            raise ValueError("unknown declared task or initial state")
        np.random.seed(seed)
        suite = benchmark.get_benchmark_dict()["libero_spatial"]()
        matches = [i for i in range(suite.n_tasks) if suite.get_task(i).name == TASKS[task_key]]
        if len(matches) != 1:
            raise RuntimeError(f"pinned benchmark task not found: {TASKS[task_key]}")
        self.task_id = matches[0]
        task = suite.get_task(self.task_id)
        self.prompt = task.language
        # Trusted initialization artifact from the pinned official repository.
        # PyTorch 2.6 changed the default; upstream was written for older torch.
        import torch

        state_file = (
            Path(get_libero_path("init_states")) / task.problem_folder / task.init_states_file
        )
        states = torch.load(state_file, map_location="cpu", weights_only=False)
        if initial_state >= len(states):
            raise ValueError("initial-state index outside official state list")
        bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
        self.env = OffScreenRenderEnv(
            bddl_file_name=str(bddl), camera_heights=256, camera_widths=256
        )
        try:
            self.env.seed(seed)
            self.env.reset()
            obs = self.env.set_init_state(states[initial_state])
            for _ in range(10):
                obs, _, _, _ = self.env.step([0.0] * 6 + [-1.0])
            self.observation = public_observation(obs)
        except BaseException:
            self.env.close()
            raise
        self.steps = 0
        self.evaluator_success = False

    def step(self, action: np.ndarray) -> dict[str, Any]:
        if action.shape != (7,) or not np.isfinite(action).all():
            raise ValueError("expected finite 7-dimensional OSC_POSE action")
        obs, _, done, _ = self.env.step(action.tolist())
        self.steps += 1
        # Scoring flag is never passed into policy / SAM / native memory.
        self.evaluator_success = bool(done)
        self.observation = public_observation(obs)
        return self.observation

    def close(self) -> None:
        self.env.close()
