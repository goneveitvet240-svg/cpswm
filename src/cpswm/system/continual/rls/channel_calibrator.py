"""Channel reliability calibration with RLS."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .core import RecursiveLeastSquares, RLSConfig


@dataclass(frozen=True)
class ChannelSample:
    """One binary calibration sample for one channel."""

    channel: str
    features: np.ndarray
    success: bool
    gate: float = 1.0


class RLSChannelReliabilityCalibrator:
    """Maintain online calibrated channel reliabilities for structure-three fusion."""

    def __init__(
        self,
        *,
        channels: tuple[str, ...],
        feature_dim: int,
        forgetting_factor: float = 0.995,
        ridge: float = 1e-6,
        prior_scale: float = 1e4,
    ) -> None:
        if not channels:
            raise ValueError("channels must be non-empty")
        if feature_dim <= 0:
            raise ValueError("feature_dim must be positive")

        self.channels = tuple(channels)
        self._models = {
            channel: RecursiveLeastSquares(
                RLSConfig(
                    feature_dim=feature_dim,
                    forgetting_factor=forgetting_factor,
                    ridge=ridge,
                    prior_scale=prior_scale,
                )
            )
            for channel in self.channels
        }

    def score(self, channel: str, features: np.ndarray) -> float:
        model = self._models.get(channel)
        if model is None:
            raise ValueError(f"unknown channel: {channel}")
        raw = model.predict(features)
        return float(1.0 / (1.0 + np.exp(-raw)))

    def update(self, sample: ChannelSample) -> None:
        model = self._models.get(sample.channel)
        if model is None:
            raise ValueError(f"unknown channel: {sample.channel}")
        if sample.gate <= 0.0:
            return
        model.update(
            sample.features,
            1.0 if sample.success else 0.0,
            gate=sample.gate,
        )

    def all_scores(self, features: np.ndarray) -> dict[str, float]:
        return {channel: self.score(channel, features) for channel in self.channels}
