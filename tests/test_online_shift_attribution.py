from __future__ import annotations

from cpswm.system.evaluation_operations import (
    OnlineShiftAttributionCase,
    OnlineShiftEvaluator,
    OnlineShiftFamily,
    OnlineShiftPrediction,
    OnlineShiftSplit,
    OnlineShiftSuiteGenerator,
    ShiftCause,
)


def test_online_suite_is_single_stream_unknown_change_point_and_truth_free():
    suite = OnlineShiftSuiteGenerator().generate()

    assert len(suite.cases) == 30
    for case in suite.cases:
        serialized = case.model_input.model_dump_json()
        for forbidden in (
            "control_run",
            "change_time",
            "true_cause",
            "evaluator_truth",
            "factor_fingerprint",
            "ground_truth",
        ):
            assert forbidden not in serialized


def test_online_suite_varies_seeds_families_objects_and_heldout_splits():
    suite = OnlineShiftSuiteGenerator().generate()
    truths = tuple(case.evaluator_truth for case in suite.cases)

    assert len({truth.scenario_seed for truth in truths}) == 6
    assert {truth.family for truth in truths} == set(OnlineShiftFamily)
    assert len({truth.object_id for truth in truths}) == 6
    assert {truth.split for truth in truths} == set(OnlineShiftSplit)
    assert any(len(truth.true_causes) == 2 for truth in truths)


def test_online_case_ids_are_opaque_and_shuffled_not_cause_encoded():
    suite = OnlineShiftSuiteGenerator().generate()

    assert suite == OnlineShiftSuiteGenerator().generate()
    for case in suite.cases:
        rendered = str(case.model_input.case_id)
        assert case.evaluator_truth.family.value not in rendered
        assert all(cause.value not in rendered for cause in case.evaluator_truth.true_causes)


def test_online_evaluator_scores_change_time_and_multilabel_causes():
    suite = OnlineShiftSuiteGenerator().generate()
    bound = tuple(
        OnlineShiftAttributionCase(
            truth=case.evaluator_truth,
            prediction=OnlineShiftPrediction(
                case_id=case.model_input.case_id,
                predicted_change_time=case.evaluator_truth.change_time,
                cause_probabilities={cause: 1.0 for cause in case.evaluator_truth.true_causes},
                model_version="online-evaluator-oracle@0.1",
            ),
        )
        for case in suite.cases
    )

    report = OnlineShiftEvaluator().evaluate(bound)

    assert report.change_detection_rate == 1.0
    assert report.mean_absolute_change_time_error_hours == 0.0
    assert report.exact_cause_set_accuracy == 1.0
    assert report.cause_micro_f1 == 1.0
    assert report.false_owner_habit_change_rate == 0.0


def test_online_simultaneous_shift_cases_contain_both_causes():
    suite = OnlineShiftSuiteGenerator().generate()
    combinations = [
        case.evaluator_truth
        for case in suite.cases
        if case.evaluator_truth.family
        in {
            OnlineShiftFamily.OBSERVATION_ACTOR,
            OnlineShiftFamily.OBSERVATION_HABIT,
        }
    ]

    assert combinations
    assert all(ShiftCause.OBSERVATION_POLICY in truth.true_causes for truth in combinations)
    assert all(len(truth.true_causes) == 2 for truth in combinations)
