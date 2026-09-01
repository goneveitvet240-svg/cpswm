"""Interactive CIAV acts only through a shared, costed verification interface."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_ciav_interactive_development import (
    SEARCH_SPACE,
    InteractiveVerificationPolicy,
    run_ciav_interactive_development,
)


def test_every_interactive_policy_has_the_same_registered_tuning_budget() -> None:
    assert set(SEARCH_SPACE) == set(InteractiveVerificationPolicy)
    assert {len(space) for space in SEARCH_SPACE.values()} == {3}


def test_interactive_development_splits_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        run_ciav_interactive_development(
            validation_seeds=(14000,),
            holdout_seeds=(14000,),
            max_steps=4,
        )


def test_interactive_smoke_keeps_shared_actions_costs_and_privacy_explicit() -> None:
    report = run_ciav_interactive_development(
        validation_seeds=(14000,),
        holdout_seeds=(15000,),
        max_steps=4,
    )
    assert report["same_action_set_and_outcome_model"] is True
    assert report["truth_released_only_after_selected_action"] is True
    assert report["search_budget_per_policy_per_cell"] == 3
    assert report["privacy_budget_per_episode"] == pytest.approx(0.5)
    for cell in report["cells"].values():
        assert set(cell["selected_parameters"]) == {
            policy.value for policy in InteractiveVerificationPolicy
        }
        assert set(cell["holdout_results"]) == {
            policy.value for policy in InteractiveVerificationPolicy
        }
        never = cell["holdout_results"][InteractiveVerificationPolicy.NEVER_ACT.value]
        assert never["verification_count"] == 0
        assert never["verification_total_cost"] == 0.0
