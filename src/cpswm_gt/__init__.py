"""Ground-truth-only nominal types.

Production world-model, language, and action packages must never import this
package. Only simulators, evaluators, and explicit oracle adapters may use it.
"""

from .models import GTEntity, GTEvent, GTRelationAssertion, GroundTruthWorldState
from .habit_trajectories import (
    GTHabitRegimeKind,
    GTPlacementEvent,
    GroundTruthHabitTrajectory,
)

__all__ = [
    "GTEntity",
    "GTEvent",
    "GTHabitRegimeKind",
    "GTPlacementEvent",
    "GTRelationAssertion",
    "GroundTruthHabitTrajectory",
    "GroundTruthWorldState",
]
