from __future__ import annotations

from cpswm.system.evaluation_operations import D0SyntheticOracleReplayAdapter
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionMethod,
)
from cpswm.system.evaluation_operations.structure_two_per_arm_resource_meter import (
    PerArmResourceReport,
    run_per_arm_resource_meter,
)


def test_per_arm_meter_proves_logical_fairness_without_claiming_native_fidelity() -> None:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,),
        test_seeds=(211,),
        max_steps_per_episode=4,
    ).build()
    report = run_per_arm_resource_meter(dataset)
    assert tuple(item.method for item in report.logical_receipts) == tuple(ProjectTwoActionMethod)
    assert report.same_visible_inputs
    assert report.same_replay_step_budget
    assert report.same_action_budget
    assert report.all_nonoracle_truth_isolated
    assert report.comparison_environment_ready_for_engineering
    assert not report.comparison_environment_ready_for_paper_claim
    assert not report.all_native_reproductions_available
    PerArmResourceReport.model_validate(report.model_dump(mode="python"))


def test_resource_receipt_rejects_a_forged_paper_ready_flag() -> None:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,),
        test_seeds=(211,),
        max_steps_per_episode=3,
    ).build()
    report = run_per_arm_resource_meter(dataset)
    payload = report.model_dump(mode="python")
    payload["comparison_environment_ready_for_paper_claim"] = True
    try:
        PerArmResourceReport.model_validate(payload)
    except ValueError as error:
        assert "paper comparison readiness" in str(error)
    else:
        raise AssertionError("forged paper-ready resource report was accepted")
