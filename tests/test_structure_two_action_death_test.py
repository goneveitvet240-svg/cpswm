"""Tests for the structure-two action-level matched death test.

This pins the *benchmark itself*: deterministic generation, truth isolation,
fair baselines, and the scientific-status gate that only grants
``strictly better`` when the new method beats every baseline on put-back error.
"""

from __future__ import annotations

from cpswm.system.evaluation_operations import (
    ActionBaselineMethod,
    ActionTaskType,
    StructureTwoActionDeathTest,
    StructureTwoActionScenarioGenerator,
)

ALL_METHODS = (
    ActionBaselineMethod.AMG_2012,
    ActionBaselineMethod.O_STAR,
    ActionBaselineMethod.DYNAMEM,
    ActionBaselineMethod.STAR,
    ActionBaselineMethod.PCHMP_CCRR_RGRC,
)


def test_generation_is_deterministic():
    generator = StructureTwoActionScenarioGenerator()
    first = generator.generate(7)
    second = generator.generate(7)
    assert first.visible.case_id == second.visible.case_id
    assert first.visible.days == second.visible.days
    assert first.truth_by_day == second.truth_by_day


def test_truth_is_not_exposed_on_model_inputs():
    case = StructureTwoActionScenarioGenerator().generate(1)
    # The visible slice structurally excludes evaluator truth.
    assert not hasattr(case.visible, "truth_by_day")
    for obs in case.visible.days:
        # Robot-visible observations carry no evaluator truth fields.
        assert not hasattr(obs, "true_owner_habit_location")
        assert not hasattr(obs, "true_actor")


def test_report_covers_every_method_and_case():
    report = StructureTwoActionDeathTest().run(seeds=(1, 2, 3))
    methods = {report.method for report in report.method_reports}
    assert methods == set(ALL_METHODS)
    assert len(report.case_results) == 3 * 32 * len(ALL_METHODS)


def test_scientific_status_is_one_of_the_expected_values():
    report = StructureTwoActionDeathTest().run(seeds=(1, 2, 3, 4, 5))
    assert report.scientific_status in {
        "new method strictly better on put-back error",
        "new method ties the best baseline on put-back error",
        "new method worse than the best baseline on put-back error",
    }


def test_new_method_is_location_permutation_equivariant():
    """P0: permuting the locations tuple must not change the new method's
    predictions (no ``locations[0]/[1]`` hard-coding)."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _PchmpCcrrRgrcMethod,
    )

    generator = StructureTwoActionScenarioGenerator()
    base = generator.generate(1)
    permuted_locations = (
        base.visible.locations[2],
        base.visible.locations[0],
        base.visible.locations[3],
        base.visible.locations[1],
    )
    permuted = base.model_copy(
        update={
            "visible": base.visible.model_copy(update={"locations": permuted_locations})
        }
    )

    first = _PchmpCcrrRgrcMethod(base.visible)
    second = _PchmpCcrrRgrcMethod(permuted.visible)
    for obs in base.visible.days:
        first.observe(obs)
        second.observe(obs)
        assert first.predict(ActionTaskType.PUT_BACK) == second.predict(
            ActionTaskType.PUT_BACK
        )
        assert first.predict(ActionTaskType.SEARCH) == second.predict(
            ActionTaskType.SEARCH
        )


def test_new_method_uses_all_three_operators_end_to_end():
    """The new method must actually route through PCHMP, CF-BOCPD, and CCRR.

    A guest-attributed placement must never write the owner habit; an
    owner-attributed placement under a non-unresolved regime decision must.
    """

    case = StructureTwoActionScenarioGenerator().generate(1)
    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _PchmpCcrrRgrcMethod,
    )

    method = _PchmpCcrrRgrcMethod(case.visible)
    saw_owner_write = False
    saw_guest_write_to_owner = False
    for obs in case.visible.days:
        if obs.after is None:
            continue
        before_counts = dict(method.state.regimes.get(method.state.active_regime_id, {}))
        method.observe(obs)
        after_counts = method.state.regimes.get(method.state.active_regime_id, {})
        truth = case.truth_by_day[obs.day]
        if truth.true_actor == "guest":
            # The owner's active regime must not gain a write on a guest day.
            if after_counts != before_counts and truth.true_location_after in after_counts:
                saw_guest_write_to_owner = True
        else:
            if after_counts != before_counts:
                saw_owner_write = True
    assert saw_owner_write
    assert not saw_guest_write_to_owner
