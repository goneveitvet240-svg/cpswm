"""CF-BOCPD direct-baseline gate: the BOCPDMS control and the four-arm verdict.

The point of these assertions is that the *control* is strong.  A comparison
whose baseline cannot fire, cannot be tuned, or cannot see the same evidence
proves nothing about the candidate, so most of what is pinned here is the
baseline's strength and the fairness of the comparison -- not the candidate's
score.
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from cpswm.system.evaluation_operations.online_shift_attribution import (
    OnlineShiftSplit,
    ShiftCause,
)
from cpswm.system.evaluation_operations.project_one_shift_four_arm import (
    CANDIDATE_ARM,
    CONTROL_ARMS,
    GUARDRAIL_METRIC,
    PRIMARY_METRIC,
    REPORTED_METRICS,
    run_four_arm_comparison,
    scaled_seed_partition,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import (
    _SEARCH_SPACES,
    SHIFT_FOUR_ARMS,
    SHIFT_THREE_ARMS,
    FrozenShiftSuiteConfig,
    _model_factory,
    generate_frozen_shift_suite,
)
from cpswm.system.evaluation_operations.shift_baselines import (
    OnlineBOCPDMSBaseline,
    OnlineCauseFactorizedBOCPDBaseline,
)


@lru_cache(maxsize=1)
def _suite():
    return generate_frozen_shift_suite(FrozenShiftSuiteConfig())


def _cases(split: OnlineShiftSplit):
    return [case for case in _suite().cases if case.evaluator_truth.split is split]


@lru_cache(maxsize=1)
def _frozen_comparison():
    return run_four_arm_comparison()


# --------------------------------------------------------------------------
# the control must be well-posed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"warmup_days": 0},
        {"hazard_probability": 0.0},
        {"hazard_probability": 1.0},
        {"detection_threshold_hazard_fraction": 1.5},
        {"detection_threshold_hazard_fraction": 0.0},
        {"maximum_run_length": 0},
        {"model_switch_weight": 1.0},
        {"model_switch_weight": -0.1},
    ],
)
def test_an_ill_posed_bocpdms_configuration_is_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        OnlineBOCPDMSBaseline(**kwargs)


def test_bocpdms_emits_a_proper_model_posterior() -> None:
    """Model selection returns a distribution, not four independent scores."""

    model = OnlineBOCPDMSBaseline(hazard_probability=0.1, detection_threshold_hazard_fraction=0.2)
    for case in _cases(OnlineShiftSplit.TEST):
        prediction = model.predict(case.model_input)
        total = sum(prediction.cause_probabilities.values())
        assert total == pytest.approx(1.0, abs=1e-6)
        assert all(0.0 <= value <= 1.0 for value in prediction.cause_probabilities.values())


def test_bocpdms_actually_fires_on_the_tuned_grid() -> None:
    """A control that never declares a change point is not evidence.

    This is the failure the first version of this arm had: it was squeezed onto
    the other arms' threshold scale, never detected anything, and would have
    handed the candidate a free win.
    """

    payload = _frozen_comparison()
    detection = payload["arms"]["bocpdms-model-selection"]["test"]["change_detection_rate"]
    assert detection > 0.0, "the BOCPDMS control never fired; the comparison is vacuous"


def test_bocpdms_carries_model_identity_through_a_change_point() -> None:
    """With no switch weight, the channel that paid for the change owns it.

    Otherwise the r=0 branch is filled from the model prior and the model index
    is bookkeeping rather than a cause label.  The claim asserted here is the
    mechanism, not a particular label: the selected channel must be one that
    actually carries change evidence, and the switch weight must visibly move the
    posterior back toward the prior.
    """

    case = _cases(OnlineShiftSplit.TEST)[0]
    frames = OnlineCauseFactorizedBOCPDBaseline(warmup_days=2).evidence_frames(case.model_input)
    evidential = {
        OnlineCauseFactorizedBOCPDBaseline._CAUSE_MAP[cause]
        for frame in frames
        for cause in frame.changepoint_likelihoods
        if frame.changepoint_likelihoods[cause] > frame.continuation_likelihoods[cause]
    }
    assert evidential, "this stream carries no channel-level change evidence at all"

    identity = OnlineBOCPDMSBaseline(
        hazard_probability=0.1,
        detection_threshold_hazard_fraction=0.2,
        model_switch_weight=0.0,
    ).predict(case.model_input)
    top = max(identity.cause_probabilities.items(), key=lambda item: item[1])[0]
    assert top in evidential, "model identity did not follow the channel that paid for the change"

    prior_driven = OnlineBOCPDMSBaseline(
        hazard_probability=0.1,
        detection_threshold_hazard_fraction=0.2,
        model_switch_weight=0.99,
    ).predict(case.model_input)
    assert max(identity.cause_probabilities.values()) > max(
        prior_driven.cause_probabilities.values()
    ), "the switch weight does not reach the posterior"


def test_bocpdms_reports_a_cause_for_every_shift_cause_channel() -> None:
    model = OnlineBOCPDMSBaseline(hazard_probability=0.1, detection_threshold_hazard_fraction=0.2)
    prediction = model.predict(_cases(OnlineShiftSplit.TEST)[0].model_input)
    assert set(prediction.cause_probabilities) == {
        ShiftCause.OBSERVATION_POLICY,
        ShiftCause.ACTOR_MIXTURE,
        ShiftCause.OWNER_HABIT_REGIME,
        ShiftCause.TRANSIENT_NOISE,
    }


# --------------------------------------------------------------------------
# the comparison must be fair
# --------------------------------------------------------------------------


def test_the_frozen_three_arm_scope_is_untouched_by_the_new_arm() -> None:
    """Existing ATG2/ATG3 artifacts must keep validating."""

    assert tuple(SHIFT_FOUR_ARMS[:3]) == SHIFT_THREE_ARMS
    assert len(SHIFT_FOUR_ARMS) == 4


def test_every_arm_gets_the_same_tuning_budget() -> None:
    budgets = {arm: len(_SEARCH_SPACES[arm]) for arm in SHIFT_FOUR_ARMS}
    assert len(set(budgets.values())) == 1, budgets


def test_every_arm_is_constructible_from_every_point_in_its_own_grid() -> None:
    for arm in SHIFT_FOUR_ARMS:
        for params in _SEARCH_SPACES[arm]:
            assert _model_factory(arm, dict(params)) is not None


def test_the_candidate_and_controls_partition_the_four_arms() -> None:
    assert CANDIDATE_ARM not in CONTROL_ARMS
    assert {CANDIDATE_ARM, *CONTROL_ARMS} == set(SHIFT_FOUR_ARMS)


def test_the_scaled_partition_never_reuses_a_frozen_seed() -> None:
    frozen = FrozenShiftSuiteConfig()
    frozen_seeds = {
        *frozen.train_seeds,
        *frozen.validation_seeds,
        *frozen.test_seeds,
    }
    for count in (2, 5, 8):
        scaled = scaled_seed_partition(count)
        scaled_seeds = {
            *scaled.train_seeds,
            *scaled.validation_seeds,
            *scaled.test_seeds,
        }
        assert not (scaled_seeds & frozen_seeds)
        assert len(scaled_seeds) == 3 * count
        assert not (set(scaled.test_seeds) & set(scaled.validation_seeds))


def test_a_scaled_partition_needs_at_least_two_seeds_per_split() -> None:
    with pytest.raises(ValueError):
        scaled_seed_partition(1)


# --------------------------------------------------------------------------
# the verdict must be honest
# --------------------------------------------------------------------------


def test_the_verdict_is_exactly_the_conjunction_of_its_findings() -> None:
    payload = _frozen_comparison()
    comparisons = payload["comparisons_vs_candidate"]
    expected = all(item["primary_candidate_wins"] for item in comparisons.values()) and not any(
        item["guardrail_candidate_loses"] for item in comparisons.values()
    )
    assert payload["direct_baseline_passed"] is expected
    assert bool(payload["blocking_findings"]) is not expected
    assert payload["ledger_transition"] == (
        "direct baseline passed" if expected else "implementation complete (unchanged)"
    )


def test_the_comparison_reports_every_metric_for_every_arm() -> None:
    payload = _frozen_comparison()
    for arm in SHIFT_FOUR_ARMS:
        outcome = payload["arms"][arm.value]
        assert set(outcome["test"]) == set(REPORTED_METRICS)
        assert set(outcome["validation"]) == set(REPORTED_METRICS)
        assert outcome["selected_parameters"]


def test_the_intervals_resample_seeds_not_cases() -> None:
    """The unit matters: cases inside one seed share a stream and a change time.

    If this ever reports more paired units than there are test seeds, someone has
    switched the resampling unit back to the case and every interval in the
    report is too narrow.
    """

    payload = _frozen_comparison()
    test_seeds = len(payload["suite"]["test_seeds"])
    for comparison in payload["comparisons_vs_candidate"].values():
        assert comparison["paired_seeds"] == test_seeds


def test_the_comparison_states_its_limitations_rather_than_implying_generality() -> None:
    payload = _frozen_comparison()
    assert payload["limitations"]
    assert PRIMARY_METRIC in REPORTED_METRICS
    assert GUARDRAIL_METRIC in REPORTED_METRICS
