"""Ground-truth-only nominal types.

Production world-model, language, and action packages must never import this
package. Only simulators, evaluators, and explicit oracle adapters may use it.
"""

from .habit_trajectories import (
    GroundTruthHabitTrajectory,
    GTHabitRegimeKind,
    GTPlacementEvent,
)
from .models import GroundTruthWorldState, GTEntity, GTEvent, GTRelationAssertion

__all__ = [
    "GTEntity",
    "GTEvent",
    "GTHabitRegimeKind",
    "GTPlacementEvent",
    "GTRelationAssertion",
    "GroundTruthHabitTrajectory",
    "GroundTruthWorldState",
]
