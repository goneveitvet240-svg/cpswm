"""Contracts for the fresh-seed seven-operator factorial benchmark."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_factorial_benchmark import (
    Factor,
    OperatorArm,
    registered_factorial_cells,
    run_project_two_factorial_benchmark,
)


def test_registered_design_is_balanced_resolution_four() -> None:
    cells = registered_factorial_cells()
    assert len(cells) == 16
    assert len({cell.cell_id for cell in cells}) == 16
    for factor in Factor:
        assert sum(cell.levels[factor] == 1 for cell in cells) == 8
        assert sum(cell.levels[factor] == -1 for cell in cells) == 8
    for left_index, left in enumerate(Factor):
        for right in tuple(Factor)[left_index + 1 :]:
            assert sum(cell.levels[left] * cell.levels[right] for cell in cells) == 0


def test_factorial_splits_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        run_project_two_factorial_benchmark(
            validation_seeds=(33000,),
            holdout_seeds=(33000,),
            max_steps=12,
        )


def test_factorial_smoke_keeps_all_cells_arms_and_causal_signs() -> None:
    report = run_project_two_factorial_benchmark(
        validation_seeds=(33100,),
        holdout_seeds=(34100,),
        max_steps=12,
    )
    assert report["design"]["cell_count"] == 16
    assert report["design"]["main_effects_aliased_with_two_factor_interactions"] is False
    assert report["truth_access"] == "CIAV outcome simulator only, after action selection"
    assert report["search_budget_per_arm_per_cell"] == 3
    assert set(report["arms"]) == {arm.value for arm in OperatorArm}
    assert len(report["cells"]) == 16
    for cell in report["cells"].values():
        assert set(cell["holdout_results"]) == {arm.value for arm in OperatorArm}
        assert set(cell["operator_net_loss_contribution"]) == {
            "opceu",
            "orrer",
            "pchmp",
            "cf_bocpd",
            "rgrc",
            "ccrr",
            "ciav",
        }
    assert set(report["factor_main_effects"]) == {factor.value for factor in Factor}
