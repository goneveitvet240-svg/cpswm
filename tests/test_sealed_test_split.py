"""B precondition 6: the frozen test split is unreadable before tuning."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.sealed_test_split import (
    SealedSplitAccessError,
    SealedTestSplit,
    TuningCompletionReceipt,
)

VAL = "a" * 64
TEST = "b" * 64


def _sealed():
    return SealedTestSplit(
        [1, 2, 3],
        experiment_id="exp-1",
        test_split_sha256=TEST,
        required_validation_split_sha256=VAL,
    )


def test_sealed_split_refuses_access_before_tuning():
    split = _sealed()
    assert split.is_sealed
    with pytest.raises(SealedSplitAccessError):
        split.require_unsealed()


def test_valid_receipt_unseals_after_tuning():
    split = _sealed()
    receipt = TuningCompletionReceipt.issue(
        experiment_id="exp-1", validation_split_sha256=VAL, tuning_runs_completed=3
    )
    cases = split.unseal(receipt)
    assert cases == (1, 2, 3)
    assert not split.is_sealed


def test_receipt_for_wrong_validation_split_is_rejected():
    split = _sealed()
    receipt = TuningCompletionReceipt.issue(
        experiment_id="exp-1", validation_split_sha256="c" * 64, tuning_runs_completed=3
    )
    with pytest.raises(SealedSplitAccessError, match="validation split"):
        split.unseal(receipt)


def test_forged_receipt_is_rejected():
    split = _sealed()
    forged = TuningCompletionReceipt(
        experiment_id="exp-1",
        validation_split_sha256=VAL,
        tuning_runs_completed=99,
        receipt_hash="0" * 64,  # not a real hash of the fields
    )
    with pytest.raises(SealedSplitAccessError, match="authentic"):
        split.unseal(forged)


def test_receipt_requires_a_completed_tuning_run():
    with pytest.raises(ValueError, match="at least one tuning run"):
        TuningCompletionReceipt.issue(
            experiment_id="exp-1", validation_split_sha256=VAL, tuning_runs_completed=0
        )
