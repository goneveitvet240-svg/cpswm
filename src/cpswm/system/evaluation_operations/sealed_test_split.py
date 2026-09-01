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
import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt
from cpswm.system.attestation import (
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

DOMAIN_EXTERNAL_TEST_UNSEAL = "cpswm.evaluation.external_test_unseal.v1"


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

    def verify_test_unseal_proof(
        self,
        proof: object,
        report: object,
        *,
        experiment_id: str,
        validation_split_sha256: str,
        test_split_sha256: str,
    ) -> bool: ...


class ExternalTestUnsealGrant(ContractModel):
    experiment_id: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_run_id: str = Field(min_length=1)
    attestation: Attestation | None = None


def issue_external_test_unseal_grant(
    grant: ExternalTestUnsealGrant,
    *,
    signer: Ed25519AttestationSigner,
) -> ExternalTestUnsealGrant:
    unsigned = grant.model_copy(update={"attestation": None})
    return unsigned.model_copy(
        update={
            "attestation": signer.sign(
                DOMAIN_EXTERNAL_TEST_UNSEAL,
                attested_payload(unsigned),
            )
        }
    )


def _external_custodian_main(
    connection: Any,
    cases: tuple[Any, ...],
    *,
    experiment_id: str,
    validation_split_sha256: str,
    test_split_sha256: str,
    verifier_key_id: str,
    verifier_public_key_base64: str,
) -> None:
    """Own TEST cases in a separate process and verify grants independently."""

    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=verifier_key_id,
        public_key_base64=verifier_public_key_base64,
    )
    try:
        command, payload = connection.recv()
        if command != "UNSEAL":
            connection.send(("error", "custodian accepts only one UNSEAL command"))
            return
        grant = ExternalTestUnsealGrant.model_validate(payload)
        verifier.verify(
            DOMAIN_EXTERNAL_TEST_UNSEAL,
            attested_payload(grant),
            grant.attestation,
        )
        if (
            grant.experiment_id,
            grant.validation_split_sha256,
            grant.test_split_sha256,
        ) != (experiment_id, validation_split_sha256, test_split_sha256):
            raise ValueError("external unseal grant does not bind this sealed split")
        if content_sha256(cases) != test_split_sha256:
            raise ValueError("custodian TEST content hash changed")
        connection.send(("ok", cases))
    except Exception as exc:  # child boundary must return a closed failure
        connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


class ExternalSealedTestSplit[T]:
    """TEST custody process that exposes metadata only until a signed grant exists."""

    def __init__(
        self,
        cases: Sequence[T],
        *,
        experiment_id: str,
        test_split_sha256: str,
        required_validation_split_sha256: str,
        verifier: Ed25519AttestationVerifier,
    ) -> None:
        case_tuple = tuple(cases)
        if content_sha256(case_tuple) != test_split_sha256:
            raise ValueError("external custodian input does not match TEST hash")
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(
            target=_external_custodian_main,
            args=(child, case_tuple),
            kwargs={
                "experiment_id": experiment_id,
                "validation_split_sha256": required_validation_split_sha256,
                "test_split_sha256": test_split_sha256,
                "verifier_key_id": verifier.key_id,
                "verifier_public_key_base64": verifier.public_key_base64,
            },
            daemon=True,
        )
        process.start()
        child.close()
        self._connection = parent
        self._process = process
        self._experiment_id = experiment_id
        self._test_split_sha256 = test_split_sha256
        self._required_validation_split_sha256 = required_validation_split_sha256
        self._case_count = len(case_tuple)
        self._unsealed = False

    @property
    def test_split_sha256(self) -> str:
        return self._test_split_sha256

    @property
    def case_count(self) -> int:
        return self._case_count

    @property
    def is_sealed(self) -> bool:
        return not self._unsealed

    @property
    def formal_isolation(self) -> bool:
        return True

    def unseal(self, grant: ExternalTestUnsealGrant) -> tuple[T, ...]:
        if self._unsealed:
            raise SealedSplitAccessError("external TEST may be released only once")
        self._connection.send(("UNSEAL", grant.model_dump(mode="json")))
        status, payload = self._connection.recv()
        self._process.join(timeout=5.0)
        self._connection.close()
        if status != "ok":
            raise SealedSplitAccessError(f"external custodian rejected unseal: {payload}")
        self._unsealed = True
        return tuple(payload)

    def close(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5.0)
        self._connection.close()


class SealedTestSplit[T]:
    """Legacy development-only in-process split.

    It remains for deterministic replay compatibility, but it can never serve
    as evidence of formal process isolation. Formal runs must use
    :class:`ExternalSealedTestSplit` or an independently receipted evaluator.
    """

    def __init__(
        self,
        cases: Sequence[T],
        *,
        experiment_id: str,
        test_split_sha256: str,
        required_validation_split_sha256: str,
        required_receipt_scope: str | None = None,
        authority: ATG2ReportAuthority | None = None,
    ) -> None:
        if required_receipt_scope is not None and authority is None:
            raise ValueError("scope-protected TEST must bind its authority at construction")
        self._cases = tuple(cases)
        self._experiment_id = experiment_id
        self._test_split_sha256 = test_split_sha256
        self._required_validation_split_sha256 = required_validation_split_sha256
        self._required_receipt_scope = required_receipt_scope
        self._authority = authority
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
    def formal_isolation(self) -> bool:
        return False

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
            if authority is not self._authority:
                raise SealedSplitAccessError(
                    "scope-protected TEST rejects authority substitution after construction"
                )
            if authority is None or not hasattr(authority, "authorize_test_unseal"):
                raise SealedSplitAccessError(
                    "scope-protected TEST requires an independent ATG-2 report authority"
                )
            receipt = getattr(completion, "receipt", None)
            if receipt is None:
                raise SealedSplitAccessError(
                    "scope-protected TEST requires the complete ATG-2 report"
                )
            checked_authority = authority
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
            if not hasattr(checked_authority, "verify_test_unseal_proof") or not (
                checked_authority.verify_test_unseal_proof(
                    proof,
                    completion,
                    experiment_id=self._experiment_id,
                    validation_split_sha256=self._required_validation_split_sha256,
                    test_split_sha256=self._test_split_sha256,
                )
            ):
                raise SealedSplitAccessError(
                    "TEST_UNSEALED proof is not verifiable against the independent authority log"
                )
            self._unseal_authority_proof = proof
            self._unseal_receipt_hash = getattr(receipt, "authority_receipt_sha256", None)
            self._unsealed = True
            return self._cases

        raise SealedSplitAccessError(
            "self-issued legacy tuning receipts cannot unseal TEST; "
            "configure an independent receipt scope and authority"
        )

    def require_unsealed(self) -> tuple[T, ...]:
        if not self._unsealed:
            raise SealedSplitAccessError("the frozen test split is sealed until tuning completes")
        return self._cases
