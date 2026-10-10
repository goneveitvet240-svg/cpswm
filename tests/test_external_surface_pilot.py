"""Opt-in component checks. Full owner/lifecycle acceptance is out of scope."""

# ruff: noqa: E402 -- external component is intentionally an optional dependency

from __future__ import annotations

import ast
import os
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

COMPONENT_PYTHON = os.environ.get("CPSWM_COMPONENT_PYTHON")
pytestmark = pytest.mark.skipif(
    not COMPONENT_PYTHON, reason="explicit isolated component runtime required"
)

from external_components.surface_denoise_adapter import (
    cluster_support,
    external_denoise,
    filtered_readout,
)
from run_matched_transition_death_test import load, raw_rows

from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd


@pytest.mark.parametrize("points", [[], [[0, 0, 0]], [[0, 0, 0], [5, 5, 5]]])
def test_upstream_empty_and_all_noise_preserve_points(points):
    original = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    actual, metadata = external_denoise(original, Path(COMPONENT_PYTHON))
    assert metadata["open3d"] == "0.19.0"
    np.testing.assert_array_equal(actual, original)


def test_upstream_keeps_largest_cluster_and_exact_coordinates():
    large = [[i * 0.001, 0, 0] for i in range(15)]
    small = [[2 + i * 0.001, 0, 0] for i in range(11)]
    points = np.asarray(large + small + [[8, 0, 0]], dtype=np.float64)
    actual, _ = external_denoise(points, Path(COMPONENT_PYTHON))
    np.testing.assert_array_equal(actual, large)


@pytest.fixture
def frame():
    from datetime import datetime

    root = Path(__file__).resolve().parents[1]
    path = (
        root
        / "docs/reviews/pc_a/matched_transition_death_test_2026-10-09/evidence"
        / "natural-30-5-5/public/000/raw.json"
    )
    raw = load(path)
    return decode_unity_rgbd(raw_rows(raw), cutoff=datetime.fromisoformat(raw["received_at"]))


def test_adapter_empty_mask_returns_unknown(frame):
    camera, depth = frame
    probability = np.zeros_like(depth)
    support, counts = cluster_support(camera, depth, probability, Path(COMPONENT_PYTHON))
    assert support == () and counts["input_points"] == 0
    result = filtered_readout(camera, depth, probability, support, None)
    assert result["world_point_m"] is None


def test_filter_cannot_escape_original_support(frame):
    camera, depth = frame
    probability = np.ones_like(depth)
    result = filtered_readout(camera, depth, probability, ((81, 143),), ((218, 173),))
    assert result["status"] == "UNKNOWN_NO_VALID_SUPPORTED_DEPTH"
    assert result["world_point_m"] is None


@pytest.mark.parametrize("bad", ["nan", "shape", "dtype", "over_one"])
def test_adapter_rejects_forged_probability(frame, bad):
    camera, depth = frame
    probability = np.ones_like(depth)
    if bad == "nan":
        probability[0, 0] = np.nan
    elif bad == "shape":
        probability = probability[:-1]
    elif bad == "dtype":
        probability = probability.astype(np.float64)
    else:
        probability[0, 0] = 1.1
    with pytest.raises(ValueError):
        cluster_support(camera, depth, probability, Path(COMPONENT_PYTHON))


def test_vendor_matches_pinned_upstream_function():
    path = Path(__file__).resolve().parents[1] / "tools/external_components/conceptgraph_denoise.py"
    source = path.read_text()
    functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)]
    assert [n.name for n in functions] == ["pcd_denoise_dbscan"]
    assert sha256(ast.get_source_segment(source, functions[0]).encode()).hexdigest() == (
        "770d0ae936cac8440d6698c9cb65ccc159dc02333b62df71bfdb3f30f4574fde"
    )
