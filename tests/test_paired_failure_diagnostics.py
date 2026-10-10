"""Guard diagnostic accounting and reject mismatched evaluator truth."""

from types import SimpleNamespace

import numpy as np
import pytest
from diagnose_surface_failures import box_gap, distribution, failure_class, project
from score_correction_mechanisms import score_case


def test_projection_analytic_plane_and_yaw():
    camera = SimpleNamespace(
        width=2,
        height=2,
        vertical_fov_degrees=90,
        pitch_degrees=0,
        yaw_degrees=0,
        position_m=(1, 2, 3),
        near_plane_m=0.1,
        far_plane_m=20,
    )
    points = project(camera, np.full((2, 2), 1.99))
    assert points[0, 0] == pytest.approx((0, 3, 5))
    camera.yaw_degrees = 90
    assert project(camera, np.full((2, 2), 1.99))[0, 0] == pytest.approx((3, 3, 4))


def test_identity_error_cannot_be_hidden_by_position_success():
    report = {"status": "reported", "world_point_m": [0, 0, 0]}
    assert failure_class(report, "other", "target", 0) == "wrong_or_unresolved_instance"
    assert failure_class(report, "target", "target", 0.001) == "correct_instance_outside_aabb"
    report.update(status="unknown", world_point_m=None)
    assert failure_class(report, None, "target", None) == "no_report"


def test_geometry_counts_do_not_drop_outside_pixels_or_expand_box():
    points = np.array([[[0, 0, 0], [1.001, 0, 0]]])
    mask = np.ones((1, 2), dtype=bool)
    result = distribution(points, mask, [-1, -1, -1], [1, 1, 1])
    assert result["pixels"] == 2 and result["inside_aabb"] == 1
    assert box_gap(points[0, 1], [-1, -1, -1], [1, 1, 1]) == pytest.approx(0.001)
    assert distribution(points, ~mask, [-1, -1, -1], [1, 1, 1])["median_outside_mm"] is None


def test_truth_must_match_full_visible_runtime_case():
    with pytest.raises(ValueError, match="does not bind"):
        score_case({"seed": 7, "visible_case_sha256": "0" * 64})
