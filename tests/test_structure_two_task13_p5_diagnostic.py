from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.structure_two_backbone_open_task_protocols import (
    DifferentiabilityStrategy,
    ProposalHeadroomArm,
)
from cpswm.system.evaluation_operations.structure_two_task13_p5_diagnostic import (
    P5LocalDiagnostic,
    Task13LocalDiagnostic,
    run_p5_local_diagnostic,
    run_task13_local_diagnostic,
)


def test_task13_executes_all_strategies_without_promoting_a_binding() -> None:
    report = run_task13_local_diagnostic()
    assert tuple(item.strategy for item in report.arms) == tuple(DifferentiabilityStrategy)
    assert report.equal_compute_budget
    assert report.runtime_strategy_trace_changes
    assert report.formal_binding_resolved is False
    assert report.selected_strategy is None
    score = next(
        item
        for item in report.arms
        if item.strategy is DifferentiabilityStrategy.SCORE_FUNCTION_UNBIASED
    )
    assert score.max_exact_expectation_error < 1e-12


def test_task13_rejects_forged_formal_state() -> None:
    payload = run_task13_local_diagnostic().model_dump(mode="python")
    payload["formal_binding_resolved"] = True
    with pytest.raises(ValueError):
        Task13LocalDiagnostic.model_validate(payload)


def test_p5_executes_four_arms_and_logs_oracle_truth_reads() -> None:
    report = run_p5_local_diagnostic()
    assert tuple(item.arm for item in report.arm_results) == tuple(ProposalHeadroomArm)
    for item in report.arm_results:
        if item.oracle_used:
            assert item.truth_read_count > 0
        else:
            assert item.truth_read_count == 0
    assert report.binding_resolution_authorized is False
    assert report.seven_operator_ablation_authorized is False


def test_p5_rejects_rehashed_but_forged_diagnosis() -> None:
    payload = run_p5_local_diagnostic().model_dump(mode="python")
    payload["stage_headroom"][0]["headroom"] = 0.123456
    with pytest.raises(ValueError, match="headroom"):
        P5LocalDiagnostic.model_validate(payload)
