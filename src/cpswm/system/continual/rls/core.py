"""Recursive least squares core used by multiple continual-learning components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

ArrayLike = np.ndarray | list[float] | tuple[float, ...]


@dataclass(frozen=True)
class RLSConfig:
    """Configuration for :class:`RecursiveLeastSquares`."""

    feature_dim: int
    forgetting_factor: float = 1.0
    ridge: float = 1e-6
    prior_scale: float = 1e4
    clip_theta: float = 10.0
    min_denominator: float = 1e-12


class RecursiveLeastSquares:
    """A numerically compact RLS state with gate-aware updates.

    The class keeps only sufficient statistics (`theta` and `covariance`) and
    is designed for online continual updates where full history replay is not
    possible or not desired.
    """

    def __init__(self, config: RLSConfig):
        if config.feature_dim <= 0:
            raise ValueError("feature_dim must be positive")
        if not (0.0 < config.forgetting_factor <= 1.0):
            raise ValueError("forgetting_factor must be in (0, 1]")
        if config.ridge < 0.0:
            raise ValueError("ridge must be non-negative")
        if config.prior_scale <= 0.0:
            raise ValueError("prior_scale must be positive")
        if config.min_denominator <= 0.0:
            raise ValueError("min_denominator must be positive")

        self._config = config
        self.theta = np.zeros(config.feature_dim, dtype=float)
        self.covariance = config.prior_scale * np.eye(config.feature_dim, dtype=float)
        self._n_updates = 0

    @property
    def feature_dim(self) -> int:
        return self._config.feature_dim

    @property
    def config(self) -> RLSConfig:
        return self._config

    @property
    def n_updates(self) -> int:
        return self._n_updates

    def _validate_x(self, x: ArrayLike) -> np.ndarray:
        vector = np.asarray(x, dtype=float)
        if vector.ndim != 1:
            raise ValueError("feature vector must be one-dimensional")
        if vector.shape[0] != self.feature_dim:
            raise ValueError("feature vector dimension mismatch")
        if np.any(~np.isfinite(vector)):
            raise ValueError("feature vector must be finite")
        return vector

    def predict(self, x: ArrayLike) -> float:
        vector = self._validate_x(x)
        return float(self.theta @ vector)

    def update(
        self,
        x: ArrayLike,
        y: float,
        *,
        gate: float = 1.0,
        forgetting_factor: float | None = None,
    ) -> dict[str, Any]:
        """Update parameters with one gated sample.

        Args:
            x: feature vector.
            y: target scalar label.
            gate: update weight in ``[0, 1]``. A gate of ``0`` disables update.
            forgetting_factor: optional override of ``config.forgetting_factor``.
        """

        update_gate = float(gate)
        if not np.isfinite(update_gate):
            raise ValueError("gate must be finite")
        if update_gate <= 0.0:
            return self.snapshot()
        update_gate = min(1.0, max(0.0, update_gate))

        lam = (
            self._config.forgetting_factor
            if forgetting_factor is None
            else float(forgetting_factor)
        )
        if not np.isfinite(lam) or not 0.0 < lam <= 1.0:
            raise ValueError("forgetting_factor must be finite and in (0, 1]")

        vector = self._validate_x(x)
        sqrt_gate = update_gate**0.5
        y_float = float(y) * sqrt_gate
        if not np.isfinite(y_float):
            raise ValueError("target label must be finite")
        vector = vector * sqrt_gate

        denominator = lam + (vector @ self.covariance @ vector) + self._config.ridge
        if denominator < self._config.min_denominator:
            return self.snapshot()

        gain = (self.covariance @ vector) / denominator
        error = y_float - float(self.theta @ vector)
        self.theta = self.theta + gain * error
        self.theta = np.clip(self.theta, -self._config.clip_theta, self._config.clip_theta)

        self.covariance = (self.covariance - np.outer(gain, vector) @ self.covariance) / lam
        self._n_updates += 1
        self._make_symmetric_if_needed()
        return self.snapshot()

    def _make_symmetric_if_needed(self) -> None:
        # Numerical drift can make the covariance matrix slightly unsymmetric;
        # enforce explicit symmetry to avoid downstream jitter.
        self.covariance = 0.5 * (self.covariance + self.covariance.T)

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of sufficient statistics for replay/rollback."""

        return {
            "theta": self.theta.tolist(),
            "covariance": self.covariance.tolist(),
            "n_updates": self._n_updates,
        }

    def restore(self, state: dict[str, Any]) -> None:
        theta = state.get("theta")
        covariance = state.get("covariance")
        n_updates = state.get("n_updates")

        if theta is None or covariance is None or n_updates is None:
            raise ValueError("restore requires theta, covariance, and n_updates")

        theta_arr = np.asarray(theta, dtype=float)
        covariance_arr = np.asarray(covariance, dtype=float)
        if theta_arr.shape != (self.feature_dim,):
            raise ValueError("restored theta has wrong shape")
        if covariance_arr.shape != (self.feature_dim, self.feature_dim):
            raise ValueError("restored covariance has wrong shape")
        if int(n_updates) < 0:
            raise ValueError("restored n_updates must be non-negative")

        self.theta = theta_arr
        self.covariance = covariance_arr
        self._n_updates = int(n_updates)
