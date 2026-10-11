"""Task-separated current Route-C entry, with explicit development readout profiles.

The historical Route-C entry remains reproducible. This entry uses the existing
current-object SEARCH plan and the complete joint habit PUT_BACK distribution.
Profiles change readout weights, never priors or write authority. The resulting
base distribution also feeds the existing joint update and ledger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from cpswm.contracts import ProjectTwoReplayEpisode
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    StatefulFullJointActionState,
    StatefulFullJointRuntime,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
)
from cpswm.system.prototype_spine import ActionReadoutConfig
from cpswm.system.runtime_readout import current_action_readout


class HabitReadoutProfile(StrEnum):
    V06 = "v06"
    BALANCED = "balanced"
    SLOW = "slow"


def habit_readout_profile(profile: HabitReadoutProfile | str) -> ActionReadoutConfig:
    """Opt-in candidates; selecting one does not change the production default."""
    profile = HabitReadoutProfile(profile)
    base = current_action_readout()
    if profile is HabitReadoutProfile.V06:
        return base
    fast, surviving, regime = {
        HabitReadoutProfile.BALANCED: (0.4, 0.4, 0.2),
        HabitReadoutProfile.SLOW: (0.2, 0.5, 0.3),
    }[profile]
    return replace(
        base,
        fast_action_weight=fast,
        surviving_revision_weight=surviving,
        regime_local_weight=regime,
    )


def task_separated_prediction(
    habit_distribution: dict[UUID, float], native: _Prediction, *, unknown_probability: float
) -> _Prediction:
    """Keep current-location search evidence distinct from owner habit evidence."""
    if (
        not habit_distribution
        or any(not math.isfinite(value) or value < 0 for value in habit_distribution.values())
        or sum(habit_distribution.values()) <= 0
    ):
        raise ValueError("habit readout requires finite nonnegative mass")
    if (
        not native.search_order
        or len(set(native.search_order)) != len(native.search_order)
        or set(native.search_order) != set(habit_distribution)
    ):
        raise ValueError("current-location search plan has invalid support")
    if not math.isfinite(unknown_probability) or not 0 <= unknown_probability <= 1:
        raise ValueError("unknown actor probability must lie in [0, 1]")
    selected = min(habit_distribution, key=lambda key: (-habit_distribution[key], str(key)))
    return _Prediction(selected, native.search_order, unknown_probability)


@dataclass(frozen=True, slots=True)
class TaskReadoutReceipt:
    prediction_index: int
    source_snapshot_id: UUID
    profile: HabitReadoutProfile
    habit_distribution: tuple[tuple[UUID, float], ...]
    put_back: UUID
    search_order: tuple[UUID, ...]
    native_search_order: tuple[UUID, ...]
    joint_cold_start: bool


class TaskSeparatedFullJointActionState(StatefulFullJointActionState):
    """Full existing state and feedback loop, with task-specific action heads."""

    def __init__(self, state, episode, runtime, *, profile: HabitReadoutProfile):
        super().__init__(state, episode, runtime)
        self.habit_readout_profile = profile
        self.task_readout_receipts: list[TaskReadoutReceipt] = []

    def predict(self) -> _Prediction:
        native = self._state.predict()
        cold = not self.runtime.particles
        if cold:
            distribution = self.spine.action_location_distribution(
                self.spine.current_snapshot, readout=self._state.action_readout
            )
            prediction = native
        else:
            distribution = self.runtime.action_distribution()
            self.runtime.action_readout_traces.append(dict(distribution))
            prediction = task_separated_prediction(
                distribution, native, unknown_probability=self.runtime.unknown_actor_probability
            )
        index = self._state._prediction_index - 1
        # A direct caller, as well as the evaluator, must see the final task heads
        # in the causal feedback trace. Rebinding the same index is idempotent.
        self._state.bind_prediction_trace(prediction, index)
        self.task_readout_receipts.append(
            TaskReadoutReceipt(
                prediction_index=index,
                source_snapshot_id=self.spine.current_snapshot.snapshot_id,
                profile=self.habit_readout_profile,
                habit_distribution=tuple(distribution.items()),
                put_back=prediction.put_back,
                search_order=prediction.search_order,
                native_search_order=native.search_order,
                joint_cold_start=cold,
            )
        )
        return prediction


def build_task_separated_full_joint_state(
    *,
    repository_root: Path,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    arm: FullJointArm,
    profile: HabitReadoutProfile | str = HabitReadoutProfile.V06,
    ciav_enabled: bool = True,
) -> TaskSeparatedFullJointActionState:
    profile = HabitReadoutProfile(profile)
    config = load_stateful_full_joint_config(repository_root)
    neural = load_neural_proposal_model(config.neural_proposal_model_path)
    base = _FullProjectTwoMethod(
        episode, owner_threshold=0.4, action_readout=habit_readout_profile(profile)
    )
    state = _CIAVState(base, dataset, episode, enabled=ciav_enabled, cost_multiplier=1.0)
    runtime = StatefulFullJointRuntime(arm=arm, config=config, neural_model=neural)
    return TaskSeparatedFullJointActionState(state, episode, runtime, profile=profile)
