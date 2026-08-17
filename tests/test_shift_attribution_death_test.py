from __future__ import annotations

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations import (
    ShiftAttributionCase,
    ShiftAttributionEvaluator,
    ShiftCause,
    ShiftCausePrediction,
)


def prediction(
    case_id: str,
    cause: ShiftCause,
    *,
    confidence: float = 1.0,
) -> ShiftCausePrediction:
    posterior = {cause: confidence}
    if confidence < 1.0:
        posterior[ShiftCause.UNRESOLVED] = 1.0 - confidence
    return ShiftCausePrediction(
        case_id=case_id,
        posterior=posterior,
        model_version="d0-test-model@0.1",
    )


def test_shift_cause_prediction_requires_a_normalized_posterior():
    with pytest.raises(ValidationError, match="must sum to 1"):
        ShiftCausePrediction(
            case_id="d0-o",
            posterior={
                ShiftCause.OBSERVATION_POLICY: 0.7,
                ShiftCause.OWNER_HABIT_REGIME: 0.2,
            },
            model_version="invalid@0.1",
        )


def test_d0_perfect_separation_has_no_owner_habit_leakage():
    cases = (
        ShiftAttributionCase(
            case_id="d0-o",
            true_cause=ShiftCause.OBSERVATION_POLICY,
            prediction=prediction("d0-o", ShiftCause.OBSERVATION_POLICY),
        ),
        ShiftAttributionCase(
            case_id="d0-a",
            true_cause=ShiftCause.ACTOR_MIXTURE,
            prediction=prediction("d0-a", ShiftCause.ACTOR_MIXTURE),
        ),
        ShiftAttributionCase(
            case_id="d0-h",
            true_cause=ShiftCause.OWNER_HABIT_REGIME,
            prediction=prediction("d0-h", ShiftCause.OWNER_HABIT_REGIME),
        ),
    )

    report = ShiftAttributionEvaluator().evaluate(cases)

    assert report.shift_cause_accuracy == 1.0
    assert report.shift_cause_macro_f1 == 1.0
    assert report.false_owner_habit_change_rate == 0.0
    assert report.observation_to_habit_leakage == 0.0
    assert report.actor_mixture_to_owner_leakage == 0.0
    assert report.confusion_counts == {
        "observation_policy->observation_policy": 1,
        "actor_mixture->actor_mixture": 1,
        "owner_habit_regime->owner_habit_regime": 1,
    }


def test_d0_reports_false_owner_change_instead_of_hiding_it_in_accuracy():
    cases = (
        ShiftAttributionCase(
            case_id="d0-o",
            true_cause=ShiftCause.OBSERVATION_POLICY,
            prediction=prediction("d0-o", ShiftCause.OWNER_HABIT_REGIME),
        ),
        ShiftAttributionCase(
            case_id="d0-a",
            true_cause=ShiftCause.ACTOR_MIXTURE,
            prediction=prediction("d0-a", ShiftCause.OWNER_HABIT_REGIME),
        ),
        ShiftAttributionCase(
            case_id="d0-h",
            true_cause=ShiftCause.OWNER_HABIT_REGIME,
            prediction=prediction("d0-h", ShiftCause.OWNER_HABIT_REGIME),
        ),
    )

    report = ShiftAttributionEvaluator().evaluate(cases)

    assert report.shift_cause_accuracy == pytest.approx(1 / 3)
    assert report.false_owner_habit_change_rate == 1.0
    assert report.observation_to_habit_leakage == 1.0
    assert report.actor_mixture_to_owner_leakage == 1.0


def test_d0_preserves_explicit_abstention_as_unresolved():
    case = ShiftAttributionCase(
        case_id="d0-o-ambiguous",
        true_cause=ShiftCause.OBSERVATION_POLICY,
        prediction=prediction("d0-o-ambiguous", ShiftCause.UNRESOLVED),
    )

    report = ShiftAttributionEvaluator().evaluate((case,))

    assert report.shift_cause_accuracy == 0.0
    assert report.unresolved_rate == 1.0
    assert report.false_owner_habit_change_rate == 0.0


def test_d0_rejects_duplicate_case_ids():
    case = ShiftAttributionCase(
        case_id="duplicate",
        true_cause=ShiftCause.OBSERVATION_POLICY,
        prediction=prediction("duplicate", ShiftCause.OBSERVATION_POLICY),
    )

    with pytest.raises(ValueError, match="must be unique"):
        ShiftAttributionEvaluator().evaluate((case, case))
