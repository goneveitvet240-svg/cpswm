"""Sealed frozen test split (B precondition 6).

The frozen test split must not be loadable by a runner until independent tuning
has finished.  This module makes that structural: the test cases are hidden
behind :meth:`SealedTestSplit.unseal`, which only releases them against a valid
:class:`TuningCompletionReceipt` bound to the same experiment and validation
split.  There is no other accessor, so a runner cannot read test cases early.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt
from cpswm.system.reproducibility import content_sha256


def split_artifact_manifest_sha256(
    *,
    experiment_id: str,
    train_split_sha256: str,
    validation_split_sha256: str,
    test_split_sha256: str,
    observation_trace_sha256: str,
    train_case_count: int,
    validation_case_count: int,
    test_case_count: int,
) -> str:
    """Hash the complete split-manifest payload represented by metadata."""

    return content_sha256(
        {
            "experiment_id": experiment_id,
            "train_split_sha256": train_split_sha256,
            "validation_split_sha256": validation_split_sha256,
            "test_split_sha256": test_split_sha256,
            "observation_trace_sha256": observation_trace_sha256,
            "train_case_count": train_case_count,
            "validation_case_count": validation_case_count,
            "test_case_count": test_case_count,
        }
    )


def _receipt_hash(
    experiment_id: str, validation_split_sha256: str, tuning_runs_completed: int
) -> str:
    payload = json.dumps(
        {
            "experiment_id": experiment_id,
            "validation_split_sha256": validation_split_sha256,
            "tuning_runs_completed": tuning_runs_completed,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SealedSplitMetadata(ContractModel):
    """Split identity metadata only -- never the cases themselves.

    This is the sole split input an ATG-1 topology-only runner may receive.  It
    carries hashes and counts so a manifest can bind split identity, but it has
    no cases, iterator, loader, unseal method, model input, or evaluator truth,
    so a runner holding it cannot read or generate any TEST data.
    """

    experiment_id: str = Field(min_length=1)
    artifact_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_manifest_case_count: NonNegativeInt
    train_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_case_count: NonNegativeInt
    validation_case_count: NonNegativeInt
    test_case_count: NonNegativeInt

    @model_validator(mode="after")
    def counts_match_artifact_manifest(self) -> SealedSplitMetadata:
        split_total = self.train_case_count + self.validation_case_count + self.test_case_count
        if split_total != self.artifact_manifest_case_count:
            raise ValueError("train/validation/test counts must equal artifact manifest case count")
        expected_hash = split_artifact_manifest_sha256(
            experiment_id=self.experiment_id,
            train_split_sha256=self.train_split_sha256,
            validation_split_sha256=self.validation_split_sha256,
            test_split_sha256=self.test_split_sha256,
            observation_trace_sha256=self.observation_trace_sha256,
            train_case_count=self.train_case_count,
            validation_case_count=self.validation_case_count,
            test_case_count=self.test_case_count,
        )
        if self.artifact_manifest_sha256 != expected_hash:
            raise ValueError("artifact manifest hash does not match split identities and counts")
        return self


@dataclass(frozen=True, slots=True)
class TuningCompletionReceipt:
    """Evidence that independent tuning finished on the validation split."""

    experiment_id: str
    validation_split_sha256: str
    tuning_runs_completed: int
    receipt_hash: str

    @classmethod
    def issue(
        cls, *, experiment_id: str, validation_split_sha256: str, tuning_runs_completed: int
    ) -> TuningCompletionReceipt:
        if tuning_runs_completed < 1:
            raise ValueError("a tuning-completion receipt requires at least one tuning run")
        return cls(
            experiment_id=experiment_id,
            validation_split_sha256=validation_split_sha256,
            tuning_runs_completed=tuning_runs_completed,
            receipt_hash=_receipt_hash(
                experiment_id, validation_split_sha256, tuning_runs_completed
            ),
        )

    def is_authentic(self) -> bool:
        return self.receipt_hash == _receipt_hash(
            self.experiment_id, self.validation_split_sha256, self.tuning_runs_completed
        )


class SealedSplitAccessError(RuntimeError):
    """Raised when a runner tries to read the test split before tuning is done."""


class AuthenticTuningReceipt(Protocol):
    """Minimum receipt interface accepted by a sealed split."""

    experiment_id: str
    validation_split_sha256: str
    receipt_hash: str

    def is_authentic(self) -> bool: ...


class ATG2ReportAuthority(Protocol):
    """Independent authority that validates and commits a complete ATG-2 report."""

    def authorize_test_unseal(
        self,
        report: object,
        *,
        experiment_id: str,
        validation_split_sha256: str,
        test_split_sha256: str,
    ) -> object: ...


class SealedTestSplit[T]:
    """Test cases that can only be released after tuning, via a valid receipt."""

    def __init__(
        self,
        cases: Sequence[T],
        *,
        experiment_id: str,
        test_split_sha256: str,
        required_validation_split_sha256: str,
        required_receipt_scope: str | None = None,
    ) -> None:
        self._cases = tuple(cases)
        self._experiment_id = experiment_id
        self._test_split_sha256 = test_split_sha256
        self._required_validation_split_sha256 = required_validation_split_sha256
        self._required_receipt_scope = required_receipt_scope
        self._unsealed = False
        self._unseal_receipt_hash: str | None = None
        self._unseal_authority_proof: object | None = None

    @property
    def test_split_sha256(self) -> str:
        return self._test_split_sha256

    @property
    def is_sealed(self) -> bool:
        return not self._unsealed

    @property
    def case_count(self) -> int:
        # Count is metadata, not the cases themselves, so it is safe pre-unseal.
        return len(self._cases)

    @property
    def required_receipt_scope(self) -> str | None:
        return self._required_receipt_scope

    @property
    def unseal_receipt_hash(self) -> str | None:
        return self._unseal_receipt_hash

    @property
    def unseal_authority_proof(self) -> object:
        if self._unseal_authority_proof is None:
            raise SealedSplitAccessError("no authority proof exists before TEST unseal")
        return self._unseal_authority_proof

    def unseal(
        self,
        completion: AuthenticTuningReceipt | object,
        *,
        authority: ATG2ReportAuthority | object | None = None,
    ) -> tuple[T, ...]:
        if self._unsealed:
            raise SealedSplitAccessError("the frozen test split has already been unsealed")
        if self._required_receipt_scope is not None:
            if authority is None or not hasattr(authority, "authorize_test_unseal"):
                raise SealedSplitAccessError(
                    "scope-protected TEST requires an independent ATG-2 report authority"
                )
            receipt = getattr(completion, "receipt", None)
            if receipt is None:
                raise SealedSplitAccessError(
                    "scope-protected TEST requires the complete ATG-2 report"
                )
            checked_authority = cast(ATG2ReportAuthority, authority)
            proof = checked_authority.authorize_test_unseal(
                completion,
                experiment_id=self._experiment_id,
                validation_split_sha256=self._required_validation_split_sha256,
                test_split_sha256=self._test_split_sha256,
            )
            if (
                getattr(proof, "event_type", None) != "TEST_UNSEALED"
                or getattr(proof, "transaction_id", None) is None
                or getattr(proof, "log_head_sha256", None) is None
            ):
                raise SealedSplitAccessError(
                    "authority did not return a committed TEST_UNSEALED proof"
                )
            self._unseal_authority_proof = proof
            self._unseal_receipt_hash = getattr(receipt, "authority_receipt_sha256", None)
            self._unsealed = True
            return self._cases

        receipt = cast(AuthenticTuningReceipt, completion)
        if not hasattr(receipt, "is_authentic"):
            raise SealedSplitAccessError("legacy sealed split requires a tuning receipt")
        if not receipt.is_authentic():
            raise SealedSplitAccessError("tuning-completion receipt is not authentic")
        if receipt.experiment_id != self._experiment_id:
            raise SealedSplitAccessError("receipt was issued for a different experiment")
        if receipt.validation_split_sha256 != self._required_validation_split_sha256:
            raise SealedSplitAccessError(
                "receipt validation split does not match the sealed split's requirement"
            )
        self._unsealed = True
        self._unseal_receipt_hash = receipt.receipt_hash
        return self._cases

    def require_unsealed(self) -> tuple[T, ...]:
        if not self._unsealed:
            raise SealedSplitAccessError("the frozen test split is sealed until tuning completes")
        return self._cases
