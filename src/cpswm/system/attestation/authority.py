"""Independent attestation authority for governance and evidence records.

Both the M28 governance log and the progress-ledger run receipts had the same
structural hole: every field was written by the candidate implementation and
checked only against other fields the candidate also wrote.  Internal
consistency is not authenticity, so a coherent forged chain verified.

This module supplies the missing half.  A record is attested by an authority
that holds a key the candidate code does not, and verification recomputes the
MAC over the record's canonical content.

Deliberate limits, stated because a MAC is easy to over-read:

* **HMAC is symmetric.**  Whoever can verify can also sign.  This separates the
  *candidate implementation* from the *authority*, which is the threat the
  reviews demonstrated; it does not protect against an attacker who obtains the
  key.  An asymmetric signature would be needed for that.
* **Domain separation is mandatory.**  A grant attestation must not verify as a
  decision attestation, so the domain string is part of the signed content.
* **The canonical form is the whole record minus the attestation.**  Signing a
  subset would leave the unsigned fields free.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field

from cpswm.contracts.base import ContractModel

#: The only MAC algorithm this slice implements.
ATTESTATION_ALGORITHM = "hmac-sha256"
FORMAL_ATTESTATION_ALGORITHM = "ed25519"

#: Domain separators. A signature is only valid for the domain it was made for.
DOMAIN_CAPABILITY_GRANT = "cpswm.governance.capability_grant.v1"
DOMAIN_ORACLE_REQUEST = "cpswm.governance.oracle_request.v1"
DOMAIN_ORACLE_DECISION = "cpswm.governance.oracle_decision.v1"
DOMAIN_RUN_RECEIPT = "cpswm.ledger.run_receipt.v1"
DOMAIN_RAW_DATA_SIGNATURE = "cpswm.evidence.raw_data_signature.v1"
DOMAIN_INDEPENDENT_PROCESS_RECEIPT = "cpswm.evidence.independent_process_receipt.v1"
DOMAIN_OAM_EXTERNAL_EVIDENCE_RECEIPT = "cpswm.oam.external_evidence_receipt.v1"


class AttestationError(ValueError):
    """Raised when a record is unattested, mis-attested, or altered."""


class Attestation(ContractModel):
    """A MAC over one record's canonical content, in one domain."""

    key_id: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    mac: str = Field(pattern=r"^(?:[0-9a-f]{64}|[0-9a-f]{128})$")


class AttestationVerifier(Protocol):
    """Verification-only interface; it deliberately exposes no signing API."""

    @property
    def key_id(self) -> str: ...

    @property
    def formal_grade(self) -> bool: ...

    def verify(
        self,
        domain: str,
        payload: Mapping[str, Any],
        attestation: Attestation | None,
    ) -> None: ...


def canonical_bytes(domain: str, payload: Mapping[str, Any]) -> bytes:
    """Deterministic bytes for ``payload`` inside ``domain``.

    The domain is length-prefixed so no payload can shift bytes across the
    boundary and impersonate another domain.
    """

    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{len(domain)}:{domain}|{body}".encode()


class AttestationAuthority:
    """Holds the key. Signing requires this object; verifying does not mint."""

    def __init__(self, *, key_id: str, secret: bytes) -> None:
        if not key_id.strip():
            raise ValueError("key_id must be a non-empty identifier")
        if len(secret) < 32:
            # A short key makes the MAC decorative.
            raise ValueError("attestation secret must be at least 32 bytes")
        self._key_id = key_id
        self._secret = bytes(secret)

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def formal_grade(self) -> bool:
        return False

    def sign(self, domain: str, payload: Mapping[str, Any]) -> Attestation:
        digest = hmac.new(
            self._secret, canonical_bytes(domain, payload), hashlib.sha256
        ).hexdigest()
        return Attestation(
            key_id=self._key_id,
            algorithm=ATTESTATION_ALGORITHM,
            domain=domain,
            mac=digest,
        )

    def verify(
        self,
        domain: str,
        payload: Mapping[str, Any],
        attestation: Attestation | None,
    ) -> None:
        """Raise :class:`AttestationError` unless the record is authentic."""

        if attestation is None:
            raise AttestationError(f"record in domain {domain!r} carries no attestation")
        if attestation.algorithm != ATTESTATION_ALGORITHM:
            raise AttestationError(f"unsupported attestation algorithm {attestation.algorithm!r}")
        if attestation.domain != domain:
            raise AttestationError(
                f"attestation domain {attestation.domain!r} does not match {domain!r}"
            )
        if attestation.key_id != self._key_id:
            raise AttestationError(
                f"attestation key {attestation.key_id!r} is not this authority's key"
            )
        expected = hmac.new(
            self._secret, canonical_bytes(domain, payload), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, attestation.mac):
            raise AttestationError(
                f"attestation MAC does not match the record content in domain {domain!r}"
            )


class Ed25519AttestationVerifier:
    """Public-key-only verifier for formal evidence.

    The object contains no private key and has no ``sign`` method. A candidate
    process may safely receive it without gaining the ability to mint evidence.
    """

    def __init__(self, *, key_id: str, public_key: Ed25519PublicKey) -> None:
        if not key_id.strip():
            raise ValueError("key_id must be a non-empty identifier")
        self._key_id = key_id
        self._public_key = public_key

    @classmethod
    def from_public_key_pem(
        cls, *, key_id: str, public_key_pem: bytes
    ) -> Ed25519AttestationVerifier:
        loaded = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("formal verifier requires an Ed25519 public key")
        return cls(key_id=key_id, public_key=loaded)

    @classmethod
    def from_public_key_base64(
        cls, *, key_id: str, public_key_base64: str
    ) -> Ed25519AttestationVerifier:
        try:
            raw = base64.b64decode(public_key_base64, validate=True)
            public_key = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid Ed25519 public key encoding") from exc
        return cls(key_id=key_id, public_key=public_key)

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def formal_grade(self) -> bool:
        return True

    @property
    def public_key_base64(self) -> str:
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    @property
    def public_key_sha256(self) -> str:
        return hashlib.sha256(base64.b64decode(self.public_key_base64)).hexdigest()

    def verify(
        self,
        domain: str,
        payload: Mapping[str, Any],
        attestation: Attestation | None,
    ) -> None:
        if attestation is None:
            raise AttestationError(f"record in domain {domain!r} carries no attestation")
        if attestation.algorithm != FORMAL_ATTESTATION_ALGORITHM:
            raise AttestationError("formal evidence requires Ed25519")
        if attestation.domain != domain:
            raise AttestationError(
                f"attestation domain {attestation.domain!r} does not match {domain!r}"
            )
        if attestation.key_id != self._key_id:
            raise AttestationError(
                f"attestation key {attestation.key_id!r} is not this verifier's key"
            )
        try:
            self._public_key.verify(
                bytes.fromhex(attestation.mac), canonical_bytes(domain, payload)
            )
        except (InvalidSignature, ValueError) as exc:
            raise AttestationError(
                f"Ed25519 signature does not match record content in domain {domain!r}"
            ) from exc


class Ed25519AttestationSigner:
    """Private signing capability kept outside candidate/evaluator processes."""

    def __init__(self, *, key_id: str, private_key: Ed25519PrivateKey) -> None:
        if not key_id.strip():
            raise ValueError("key_id must be a non-empty identifier")
        self._key_id = key_id
        self._private_key = private_key

    @classmethod
    def generate(cls, *, key_id: str) -> Ed25519AttestationSigner:
        return cls(key_id=key_id, private_key=Ed25519PrivateKey.generate())

    @classmethod
    def from_private_key_pem(
        cls, *, key_id: str, private_key_pem: bytes
    ) -> Ed25519AttestationSigner:
        loaded = serialization.load_pem_private_key(private_key_pem, password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("formal signer requires an Ed25519 private key")
        return cls(key_id=key_id, private_key=loaded)

    @property
    def key_id(self) -> str:
        return self._key_id

    def verifier(self) -> Ed25519AttestationVerifier:
        return Ed25519AttestationVerifier(
            key_id=self._key_id,
            public_key=self._private_key.public_key(),
        )

    def private_key_pem(self) -> bytes:
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def sign(self, domain: str, payload: Mapping[str, Any]) -> Attestation:
        signature = self._private_key.sign(canonical_bytes(domain, payload))
        return Attestation(
            key_id=self._key_id,
            algorithm=FORMAL_ATTESTATION_ALGORITHM,
            domain=domain,
            mac=signature.hex(),
        )


def attested_payload(record: BaseModel, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """The signable view of a pydantic record: everything but its attestation."""

    dumped: dict[str, Any] = record.model_dump(mode="json", exclude={"attestation", *exclude})
    return dumped


__all__ = [
    "ATTESTATION_ALGORITHM",
    "DOMAIN_CAPABILITY_GRANT",
    "DOMAIN_INDEPENDENT_PROCESS_RECEIPT",
    "DOMAIN_OAM_EXTERNAL_EVIDENCE_RECEIPT",
    "DOMAIN_ORACLE_DECISION",
    "DOMAIN_ORACLE_REQUEST",
    "DOMAIN_RAW_DATA_SIGNATURE",
    "DOMAIN_RUN_RECEIPT",
    "FORMAL_ATTESTATION_ALGORITHM",
    "Attestation",
    "AttestationAuthority",
    "AttestationError",
    "AttestationVerifier",
    "Ed25519AttestationSigner",
    "Ed25519AttestationVerifier",
    "attested_payload",
    "canonical_bytes",
]
