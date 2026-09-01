"""Preregistered CIAV accuracy--cost surface contract."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_ciav_break_even import (
    ACCURACY_LEVELS,
    COST_MULTIPLIERS,
    run_ciav_accuracy_cost_break_even,
)


def test_surface_is_frozen_and_excludes_a_zero_cost_corner() -> None:
    assert ACCURACY_LEVELS == (0.75, 0.85, 0.95)
    assert COST_MULTIPLIERS == (0.25, 0.50, 0.75, 1.00)
    assert min(COST_MULTIPLIERS) > 0.0


def test_surface_requires_nonempty_evaluation_seeds() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        run_ciav_accuracy_cost_break_even(evaluation_seeds=(), max_steps=4)


def test_surface_smoke_reports_every_point_and_frozen_gate() -> None:
    report = run_ciav_accuracy_cost_break_even(
        evaluation_seeds=(18000,),
        max_steps=4,
    )
    assert len(report["points"]) == len(ACCURACY_LEVELS) * len(COST_MULTIPLIERS)
    assert report["frozen_ciav"] == {
        "max_verifications": 4,
        "minimum_attribution_shift": 0.75,
    }
    assert report["decision"] in {
        "continue_to_larger_confirmation",
        "do_not_scale_ciav_confirmation",
    }
    assert all(point["cost_multiplier"] > 0.0 for point in report["points"])
