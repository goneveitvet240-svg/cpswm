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


@dataclass(frozen=True, slots=True)
class SealedSplitMetadata:
    """Split identity metadata only -- never the cases themselves.

    This is the sole split input an ATG-1 topology-only runner may receive.  It
    carries hashes and counts so a manifest can bind split identity, but it has
    no cases, iterator, loader, unseal method, model input, or evaluator truth,
    so a runner holding it cannot read or generate any TEST data.
    """

    experiment_id: str
    artifact_manifest_sha256: str
    train_split_sha256: str
    validation_split_sha256: str
    test_split_sha256: str
    observation_trace_sha256: str
    train_case_count: int
    validation_case_count: int
    test_case_count: int


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


class SealedTestSplit[T]:
    """Test cases that can only be released after tuning, via a valid receipt."""

    def __init__(
        self,
        cases: Sequence[T],
        *,
        experiment_id: str,
        test_split_sha256: str,
        required_validation_split_sha256: str,
    ) -> None:
        self._cases = tuple(cases)
        self._experiment_id = experiment_id
        self._test_split_sha256 = test_split_sha256
        self._required_validation_split_sha256 = required_validation_split_sha256
        self._unsealed = False

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

    def unseal(self, receipt: TuningCompletionReceipt) -> tuple[T, ...]:
        if not receipt.is_authentic():
            raise SealedSplitAccessError("tuning-completion receipt is not authentic")
        if receipt.experiment_id != self._experiment_id:
            raise SealedSplitAccessError("receipt was issued for a different experiment")
        if receipt.validation_split_sha256 != self._required_validation_split_sha256:
            raise SealedSplitAccessError(
                "receipt validation split does not match the sealed split's requirement"
            )
        self._unsealed = True
        return self._cases

    def require_unsealed(self) -> tuple[T, ...]:
        if not self._unsealed:
            raise SealedSplitAccessError("the frozen test split is sealed until tuning completes")
        return self._cases
