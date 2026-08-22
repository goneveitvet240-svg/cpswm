"""Recursive least squares (RLS) utilities used by continual modules."""

from .channel_calibrator import ChannelSample, RLSChannelReliabilityCalibrator
from .core import RecursiveLeastSquares, RLSConfig
from .habit_head import RLSHabitSample, RLSHabitScoreHead
from .regime_bank import RLSRegimeBank, RLSRegimeSwitchEvent

__all__ = [
    "ChannelSample",
    "RLSChannelReliabilityCalibrator",
    "RLSConfig",
    "RLSHabitSample",
    "RLSHabitScoreHead",
    "RLSRegimeBank",
    "RLSRegimeSwitchEvent",
    "RecursiveLeastSquares",
]
