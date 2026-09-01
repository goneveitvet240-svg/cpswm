from __future__ import annotations

from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.care_wm_exact_counterfactual import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    CareArm,
    GeneratedCareCase,
    HiddenCareTruth,
    SignedMemoryLedger,
    VisibleCareCase,
    _load_and_verify_holdout_seeds,
    _serialized_report_discloses_seed,
    choose_care_decision,
    counterfactual_sensitivity_audit,
    evaluate_care_case,
    load_frozen_care_design,
)

ROOT = Path(__file__).resolve().parents[1]


def _visible(*, predicted_cost: float) -> VisibleCareCase:
    return VisibleCareCase(
        case_id="care-test",
        family_id="care-test-family",
        habit_posterior=0.70,
        horizon=12,
        feedback_step=10,
        predicted_action_cost=predicted_cost,
        repair_cost=0.30,
        verification_cost=0.80,
        immediate_action_cost=0.10,
    )


def test_design_freezes_eight_arms_five_families_and_sealed_seeds() -> None:
    design = load_frozen_care_design(ROOT / DEFAULT_MANIFEST)

    assert len(design.families) == 5
    assert len(design.holdout_seed_commitments) == 24
    assert set(design.search_spaces) == {arm.value for arm in CareArm}
    assert set(design.validation_seeds).isdisjoint(
        _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)
    )


def test_care_uses_future_consequence_while_current_voi_does_not() -> None:
    high = _visible(predicted_cost=1.0)
    low = _visible(predicted_cost=0.05)

    care_high = choose_care_decision(CareArm.CARE_WM, high, 1.0)
    care_low = choose_care_decision(CareArm.CARE_WM, low, 1.0)
    current_high = choose_care_decision(CareArm.CURRENT_TASK_VOI, high, 0.65)
    current_low = choose_care_decision(CareArm.CURRENT_TASK_VOI, low, 0.65)

    assert care_high.verify_first
    assert not care_low.verify_first
    assert current_high.verify_first == current_low.verify_first
    assert counterfactual_sensitivity_audit() == {
        "equal_entropy_confidence_invariant": True,
        "same_immediate_voi_invariant": True,
        "care_responds_to_long_horizon_consequence": True,
    }


def test_non_oracle_policy_api_rejects_oracle_truth_access() -> None:
    with pytest.raises(ValueError, match="evaluator-owned"):
        choose_care_decision(CareArm.FULL_RERUN_ORACLE, _visible(predicted_cost=1.0), None)


def test_signed_ledger_retraction_matches_leave_one_cluster_out() -> None:
    ledger = SignedMemoryLedger()
    ledger.initialize(True)
    changed = ledger.correct(False)

    assert changed
    assert ledger.value == 0
    assert ledger.operations == ["promote", "retract"]


def test_care_verification_avoids_high_consequence_false_commit() -> None:
    generated = GeneratedCareCase(
        visible=_visible(predicted_cost=1.0),
        truth=HiddenCareTruth(
            habit_truth=False,
            actual_action_cost=1.0,
            decoy_evidence=True,
        ),
    )

    care = evaluate_care_case(generated, CareArm.CARE_WM, 1.0)
    confidence = evaluate_care_case(generated, CareArm.CONFIDENCE, 0.65)

    assert care.operation_counts["verify"] == 1
    assert care.contamination_auc_per_step == 0.0
    assert care.net_action_loss_per_step < confidence.net_action_loss_per_step
    assert care.decision_receipt["truth_fields_present"] is False


def test_care_exactly_rolls_back_nonverified_wrong_commit() -> None:
    visible = VisibleCareCase(
        case_id="care-rollback-test",
        family_id="care-rollback-family",
        habit_posterior=0.90,
        horizon=10,
        feedback_step=4,
        predicted_action_cost=0.05,
        repair_cost=0.10,
        verification_cost=1.00,
        immediate_action_cost=0.05,
    )
    generated = GeneratedCareCase(
        visible=visible,
        truth=HiddenCareTruth(
            habit_truth=False,
            actual_action_cost=0.2,
            decoy_evidence=True,
        ),
    )

    reading = evaluate_care_case(generated, CareArm.CARE_WM, 1.0)

    assert not reading.decision_receipt["verify_first"]
    assert reading.operation_counts["retract"] == 1
    assert reading.rollback_equivalence_applicable
    assert reading.rollback_equivalent
    assert reading.post_correction_regret_per_step == 0.0


def test_seed_leak_detector_uses_tokens_not_arbitrary_digit_substrings() -> None:
    seeds = (220216,)

    assert not _serialized_report_discloses_seed({"legitimate_metric": 1.052202166551396}, seeds)
    assert _serialized_report_discloses_seed({"raw_seed": 220216}, seeds)
    assert _serialized_report_discloses_seed({"raw_seed_text": "seed=220216"}, seeds)
