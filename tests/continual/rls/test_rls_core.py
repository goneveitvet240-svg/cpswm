from __future__ import annotations

import numpy as np
import pytest

from cpswm.system.continual.rls import RecursiveLeastSquares, RLSConfig


def test_linear_recovery_has_reasonable_error_after_updates():
    estimator = RecursiveLeastSquares(
        RLSConfig(
            feature_dim=1,
            forgetting_factor=1.0,
        )
    )

    for x in [1.0, 2.0, 3.0, 4.0, 5.0]:
        estimator.update(np.array([x], dtype=float), y=2.0 * x, gate=1.0)

    assert estimator.predict(np.array([10.0], dtype=float)) == pytest.approx(20.0, rel=0.2)


def test_zero_gate_avoids_state_change():
    estimator = RecursiveLeastSquares(RLSConfig(feature_dim=2, forgetting_factor=1.0))
    state_before = estimator.snapshot()
    estimator.update(np.array([1.0, 0.0]), y=1.0, gate=0.0)
    assert estimator.snapshot() == state_before


def test_snapshot_restore_roundtrip():
    estimator = RecursiveLeastSquares(RLSConfig(feature_dim=1, forgetting_factor=0.99))
    estimator.update(np.array([2.0]), y=1.0)
    state = estimator.snapshot()

    estimator.update(np.array([1.0]), y=0.0)
    assert estimator.snapshot()["n_updates"] == 2

    estimator.restore(state)
    restored = estimator.snapshot()
    assert restored["n_updates"] == 1
    assert np.allclose(restored["theta"], state["theta"])


def test_fractional_gate_matches_weighted_least_squares_transform():
    gated = RecursiveLeastSquares(RLSConfig(feature_dim=1, forgetting_factor=1.0))
    transformed = RecursiveLeastSquares(RLSConfig(feature_dim=1, forgetting_factor=1.0))
    gate = 0.25

    gated.update(np.array([2.0]), y=3.0, gate=gate)
    transformed.update(
        np.array([2.0 * np.sqrt(gate)]),
        y=3.0 * np.sqrt(gate),
        gate=1.0,
    )

    assert np.allclose(gated.snapshot()["theta"], transformed.snapshot()["theta"])
    assert np.allclose(gated.snapshot()["covariance"], transformed.snapshot()["covariance"])
