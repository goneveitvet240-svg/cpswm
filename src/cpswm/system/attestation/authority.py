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

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from cpswm.contracts.base import ContractModel

#: The only MAC algorithm this slice implements.
ATTESTATION_ALGORITHM = "hmac-sha256"

#: Domain separators. A signature is only valid for the domain it was made for.
DOMAIN_CAPABILITY_GRANT = "cpswm.governance.capability_grant.v1"
DOMAIN_ORACLE_REQUEST = "cpswm.governance.oracle_request.v1"
DOMAIN_ORACLE_DECISION = "cpswm.governance.oracle_decision.v1"
DOMAIN_RUN_RECEIPT = "cpswm.ledger.run_receipt.v1"


class AttestationError(ValueError):
    """Raised when a record is unattested, mis-attested, or altered."""


class Attestation(ContractModel):
    """A MAC over one record's canonical content, in one domain."""

    key_id: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    mac: str = Field(pattern=r"^[0-9a-f]{64}$")


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


def attested_payload(record: BaseModel, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """The signable view of a pydantic record: everything but its attestation."""

    dumped: dict[str, Any] = record.model_dump(mode="json", exclude={"attestation", *exclude})
    return dumped


__all__ = [
    "ATTESTATION_ALGORITHM",
    "DOMAIN_CAPABILITY_GRANT",
    "DOMAIN_ORACLE_DECISION",
    "DOMAIN_ORACLE_REQUEST",
    "DOMAIN_RUN_RECEIPT",
    "Attestation",
    "AttestationAuthority",
    "AttestationError",
    "attested_payload",
    "canonical_bytes",
]
