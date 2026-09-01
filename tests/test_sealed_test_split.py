"""B precondition 6: the frozen test split is unreadable before tuning."""

from __future__ import annotations

import pytest

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations.sealed_test_split import (
    ExternalSealedTestSplit,
    ExternalTestUnsealGrant,
    SealedSplitAccessError,
    SealedTestSplit,
    TuningCompletionReceipt,
    issue_external_test_unseal_grant,
)
from cpswm.system.reproducibility import content_sha256

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
    assert not split.formal_isolation
    with pytest.raises(SealedSplitAccessError):
        split.require_unsealed()


def test_self_issued_receipt_cannot_unseal_after_tuning():
    split = _sealed()
    receipt = TuningCompletionReceipt.issue(
        experiment_id="exp-1", validation_split_sha256=VAL, tuning_runs_completed=3
    )
    with pytest.raises(SealedSplitAccessError, match="self-issued legacy"):
        split.unseal(receipt)
    assert split.is_sealed


def test_receipt_for_wrong_validation_split_is_rejected():
    split = _sealed()
    receipt = TuningCompletionReceipt.issue(
        experiment_id="exp-1", validation_split_sha256="c" * 64, tuning_runs_completed=3
    )
    with pytest.raises(SealedSplitAccessError, match="self-issued legacy"):
        split.unseal(receipt)


def test_forged_receipt_is_rejected():
    split = _sealed()
    forged = TuningCompletionReceipt(
        experiment_id="exp-1",
        validation_split_sha256=VAL,
        tuning_runs_completed=99,
        receipt_hash="0" * 64,  # not a real hash of the fields
    )
    with pytest.raises(SealedSplitAccessError, match="self-issued legacy"):
        split.unseal(forged)


def test_receipt_requires_a_completed_tuning_run():
    with pytest.raises(ValueError, match="at least one tuning run"):
        TuningCompletionReceipt.issue(
            experiment_id="exp-1", validation_split_sha256=VAL, tuning_runs_completed=0
        )


def _external_grant(signer: Ed25519AttestationSigner) -> ExternalTestUnsealGrant:
    return issue_external_test_unseal_grant(
        ExternalTestUnsealGrant(
            experiment_id="exp-1",
            validation_split_sha256=VAL,
            test_split_sha256=content_sha256((1, 2, 3)),
            authority_receipt_sha256="c" * 64,
            custodian_run_id="custodian@test",
        ),
        signer=signer,
    )


def test_external_custodian_holds_no_test_cases_in_candidate_process() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="sealed-custodian")
    split = ExternalSealedTestSplit(
        (1, 2, 3),
        experiment_id="exp-1",
        test_split_sha256=content_sha256((1, 2, 3)),
        required_validation_split_sha256=VAL,
        verifier=signer.verifier(),
    )
    assert not hasattr(split, "_cases")
    assert split.formal_isolation
    assert split.unseal(_external_grant(signer)) == (1, 2, 3)


def test_external_custodian_rejects_attacker_signed_grant() -> None:
    trusted = Ed25519AttestationSigner.generate(key_id="sealed-custodian")
    attacker = Ed25519AttestationSigner.generate(key_id="sealed-custodian")
    split = ExternalSealedTestSplit(
        (1, 2, 3),
        experiment_id="exp-1",
        test_split_sha256=content_sha256((1, 2, 3)),
        required_validation_split_sha256=VAL,
        verifier=trusted.verifier(),
    )
    with pytest.raises(SealedSplitAccessError, match="rejected unseal"):
        split.unseal(_external_grant(attacker))
