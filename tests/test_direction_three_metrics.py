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
        picked_object_candidate_id=(target if correct else distractor),
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

    assert report["retrieval"]["known_target_retrieval_recall"] == 1.0
    assert report["conditional_fusion"]["recall_at_1"] == pytest.approx(2 / 3)
    assert report["conditional_fusion"]["recall_at_2"] == 1.0
    assert report["conditional_fusion"]["mrr"] == pytest.approx(5 / 6)
    assert report["open_set"] == {"unknown_auroc": 1.0, "unknown_auprc": 1.0}
    assert report["decision"]["known_target_misidentification_rate"] == 0.5
    assert report["decision"]["unknown_target_false_pick_rate"] == 0.0
    assert report["decision"]["overall_unsafe_pick_rate"] == pytest.approx(1 / 3)
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


def test_known_out_of_support_is_retrieval_failure_not_true_unknown():
    missing_target = uuid4()
    distractor = uuid4()
    unknown = uuid4()
    support_miss = DirectionThreeMetricCase(
        case_id="support-miss",
        posterior_by_candidate_id={distractor: 0.2, unknown: 0.8},
        unknown_candidate_id=unknown,
        true_target_candidate_id=missing_target,
        target_is_unknown=False,
        known_target_out_of_support=True,
        resolution_status=ResolutionStatus.UNKNOWN,
        expected_resolution_status=ResolutionStatus.RESOLVED,
        selected_target_candidate_id=distractor,
        picked_object_candidate_id=distractor,
    )
    report = evaluate_direction_three_metrics((support_miss, _unknown_case()))

    assert report["retrieval"]["known_target_retrieval_recall"] == 0.0
    assert report["retrieval"]["known_out_of_support_count"] == 1
    assert report["conditional_fusion"]["case_count"] == 1
    assert report["open_set"]["unknown_auroc"] is None
    assert report["cases"][0]["support_status"] == "known_out_of_support"
    assert report["cases"][0]["top1_correct"] is None


def test_unknown_false_pick_and_known_misidentification_are_split():
    known_wrong = _known_case("known-wrong", correct=False, confidence=0.8)
    unknown = _unknown_case()
    known_candidate = next(
        candidate
        for candidate in unknown.posterior_by_candidate_id
        if candidate != unknown.unknown_candidate_id
    )
    unknown_false_pick = replace(
        unknown,
        selected_target_candidate_id=known_candidate,
        picked_object_candidate_id=known_candidate,
    )
    report = evaluate_direction_three_metrics((known_wrong, unknown_false_pick))

    assert report["decision"]["known_target_misidentification_rate"] == 1.0
    assert report["decision"]["unknown_target_false_pick_rate"] == 1.0
    assert report["decision"]["overall_unsafe_pick_rate"] == 1.0


def test_selecting_unknown_without_physical_pick_is_not_an_unsafe_pick():
    unknown = _unknown_case()
    report = evaluate_direction_three_metrics(
        (replace(unknown, selected_target_candidate_id=unknown.unknown_candidate_id),)
    )

    assert report["decision"]["unknown_target_false_pick_rate"] == 0.0
    assert report["decision"]["overall_unsafe_pick_rate"] == 0.0
