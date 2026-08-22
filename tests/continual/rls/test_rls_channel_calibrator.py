"""Tests for RLS channel calibration modules."""

from __future__ import annotations

import numpy as np
import pytest

from cpswm.system.continual.rls import ChannelSample, RLSChannelReliabilityCalibrator


def test_channel_calibrator_updates_and_scores():
    calibrator = RLSChannelReliabilityCalibrator(
        channels=("rgb", "depth"),
        feature_dim=2,
        forgetting_factor=0.99,
    )
    features = np.array([1.0, 0.0], dtype=float)
    assert calibrator.score("rgb", features) == pytest.approx(0.5, abs=1e-6)

    calibrator.update(ChannelSample(channel="rgb", features=features, success=True, gate=1.0))
    rgb_score = calibrator.score("rgb", features)
    depth_score = calibrator.score("depth", features)

    assert 0.5 < rgb_score < 1.0
    assert depth_score == pytest.approx(0.5, abs=1e-6)


def test_channel_calibrator_rejects_unknown_channel():
    calibrator = RLSChannelReliabilityCalibrator(channels=("rgb",), feature_dim=1)
    unknown = "lidar"
    features = np.array([0.1], dtype=float)
    with pytest.raises(ValueError, match="unknown channel"):
        calibrator.score(unknown, features)
