from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from cpswm.contracts import ResolutionStatus
from cpswm.system.evaluation_operations.direction_three_metrics import (
    DirectionThreeMetricCase,
    evaluate_direction_three_metrics,
)


def _known_case(case_id: str, *, correct: bool, confidence: float):
    target = uuid4()
    distractor = uuid4()
    unknown = uuid4()
    if correct:
        posterior = {
            target: confidence,
            distractor: 1.0 - confidence - 0.05,
            unknown: 0.05,
        }
    else:
        posterior = {
            target: 1.0 - confidence - 0.05,
            distractor: confidence,
            unknown: 0.05,
        }
    return DirectionThreeMetricCase(
        case_id=case_id,
        posterior_by_candidate_id=posterior,
        unknown_candidate_id=unknown,
        true_target_candidate_id=target,
        target_is_unknown=False,
        resolution_status=ResolutionStatus.RESOLVED,
        expected_resolution_status=ResolutionStatus.RESOLVED,
        selected_target_candidate_id=(target if correct else distractor),
        task_success=correct,
    )


def _unknown_case():
    known = uuid4()
    unknown = uuid4()
    return DirectionThreeMetricCase(
        case_id="unknown",
        posterior_by_candidate_id={known: 0.1, unknown: 0.9},
        unknown_candidate_id=unknown,
        true_target_candidate_id=None,
        target_is_unknown=True,
        resolution_status=ResolutionStatus.UNKNOWN,
        expected_resolution_status=ResolutionStatus.UNKNOWN,
    )


def test_direction_three_metrics_report_retrieval_open_set_and_action_metrics():
    cases = (
        _known_case("correct", correct=True, confidence=0.9),
        _known_case("wrong", correct=False, confidence=0.8),
        _unknown_case(),
    )
    report = evaluate_direction_three_metrics(cases, recall_k=2)

    assert report["retrieval"]["recall_at_1"] == pytest.approx(2 / 3)
    assert report["retrieval"]["recall_at_2"] == 1.0
    assert report["retrieval"]["mrr"] == pytest.approx(5 / 6)
    assert report["open_set"] == {"unknown_auroc": 1.0, "unknown_auprc": 1.0}
    assert report["decision"]["wrong_object_pickup_rate"] == 0.5
    assert report["task"]["task_success_rate"] == pytest.approx(1 / 3)


def test_selective_risk_curve_keeps_empty_high_threshold_explicit():
    report = evaluate_direction_three_metrics(
        (_known_case("correct", correct=True, confidence=0.8),),
        selective_thresholds=(0.0, 0.9),
    )

    assert report["decision"]["selective_risk_coverage"] == [
        {"confidence_threshold": 0.0, "coverage": 1.0, "risk": 0.0},
        {"confidence_threshold": 0.9, "coverage": 0.0, "risk": None},
    ]


def test_unnecessary_clarification_is_scored_against_expected_resolution():
    case = _known_case("ask", correct=True, confidence=0.9)
    case = replace(case, asked_user=True)
    report = evaluate_direction_three_metrics((case,))
    assert report["decision"]["clarification_rate"] == 1.0
    assert report["decision"]["unnecessary_clarification_rate"] == 1.0


def test_recovery_success_requires_a_recovery_case():
    case = _known_case("recovery", correct=True, confidence=0.9)
    with pytest.raises(ValueError, match="recovery-required"):
        replace(case, recovery_success=True)


def test_metric_case_requires_explicit_unknown_support():
    target = uuid4()
    unknown = uuid4()
    with pytest.raises(ValueError, match="explicit unknown"):
        DirectionThreeMetricCase(
            case_id="missing-unknown",
            posterior_by_candidate_id={target: 1.0},
            unknown_candidate_id=unknown,
            true_target_candidate_id=target,
            target_is_unknown=False,
            resolution_status=ResolutionStatus.RESOLVED,
            expected_resolution_status=ResolutionStatus.RESOLVED,
        )
