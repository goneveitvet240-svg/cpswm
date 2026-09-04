"""Signed primary-source acquisition receipts for external-method evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    external_artifact_sha256,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-primary-source-acquisition-receipt@0.6"
ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.source_acquisition.v0.6"


class PrimarySourceAcquisitionReceiptV06(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-primary-source-acquisition-receipt@0\.6$")
    arm: str = Field(min_length=1)
    registered_source_url: str = Field(min_length=1)
    http_final_url: str = Field(min_length=1)
    acquired_at_utc: datetime
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_register_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_repository_url: str | None = None
    official_repository_commit: str | None = None
    official_checkout_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    acquirer_public_key_base64: str = Field(min_length=1)
    acquirer_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation: Attestation | None = None


def make_primary_source_acquisition_receipt_v0_6(
    *,
    arm: str,
    registered_source_url: str,
    http_final_url: str,
    acquired_at_utc: datetime,
    source_artifact: Path,
    source_register_content_sha256: str,
    acquirer: Ed25519AttestationSigner,
    official_repository_url: str | None = None,
    official_repository_commit: str | None = None,
    official_checkout: Path | None = None,
) -> dict[str, Any]:
    verifier = acquirer.verifier()
    unsigned = PrimarySourceAcquisitionReceiptV06(
        protocol=PROTOCOL_ID,
        arm=arm,
        registered_source_url=registered_source_url,
        http_final_url=http_final_url,
        acquired_at_utc=acquired_at_utc,
        source_artifact_sha256=external_artifact_sha256(source_artifact),
        source_register_content_sha256=source_register_content_sha256,
        official_repository_url=official_repository_url,
        official_repository_commit=official_repository_commit,
        official_checkout_tree_sha256=(
            external_artifact_sha256(official_checkout) if official_checkout is not None else None
        ),
        acquirer_public_key_base64=verifier.public_key_base64,
        acquirer_public_key_sha256=verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={"attestation": acquirer.sign(ATTESTATION_DOMAIN, attested_payload(unsigned))}
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_primary_source_acquisition_receipt_v0_6(
    payload: Mapping[str, Any],
    *,
    expected_arm: str,
    source_row: Mapping[str, Any],
    source_artifact: Path,
    source_register_content_sha256: str,
    trusted_acquirer: Ed25519AttestationVerifier,
    official_checkout: Path | None,
    not_before_utc: datetime,
    not_after_utc: datetime,
) -> PrimarySourceAcquisitionReceiptV06:
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("source-acquisition receipt content hash mismatch")
    record = PrimarySourceAcquisitionReceiptV06.model_validate(unsigned_payload)
    if record.arm != expected_arm:
        raise ValueError("source-acquisition receipt arm mismatch")
    if record.registered_source_url != source_row.get("primary_source_url"):
        raise ValueError("source-acquisition receipt URL mismatch")
    allowed_hosts = source_row.get("allowed_final_url_hosts")
    final_url = urlsplit(record.http_final_url)
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or any(not isinstance(host, str) or not host for host in allowed_hosts)
        or final_url.scheme != "https"
        or final_url.hostname not in allowed_hosts
    ):
        raise ValueError("source-acquisition final URL violates the frozen redirect policy")
    if (
        record.acquired_at_utc.utcoffset() is None
        or not_before_utc.utcoffset() is None
        or not_after_utc.utcoffset() is None
        or record.acquired_at_utc <= not_before_utc
        or record.acquired_at_utc > not_after_utc
    ):
        raise ValueError("source-acquisition timestamp is outside the authorized run window")
    if record.source_artifact_sha256 != external_artifact_sha256(source_artifact):
        raise ValueError("source-acquisition receipt artifact hash mismatch")
    registered_source_sha256 = source_row.get("primary_source_sha256")
    if (
        not isinstance(registered_source_sha256, str)
        or record.source_artifact_sha256 != registered_source_sha256
    ):
        raise ValueError(
            "source-acquisition artifact does not match the registered primary-source hash"
        )
    if record.source_register_content_sha256 != source_register_content_sha256:
        raise ValueError("source-acquisition receipt source-register binding mismatch")
    expected_repository_url = source_row.get("repository_url")
    expected_repository_commit = source_row.get("repository_commit")
    if expected_repository_url is not None:
        if (
            record.official_repository_url != expected_repository_url
            or record.official_repository_commit != expected_repository_commit
            or official_checkout is None
            or record.official_checkout_tree_sha256 != external_artifact_sha256(official_checkout)
        ):
            raise ValueError("source-acquisition receipt official-code binding mismatch")
    elif any(
        value is not None
        for value in (
            record.official_repository_url,
            record.official_repository_commit,
            record.official_checkout_tree_sha256,
        )
    ):
        raise ValueError("source-acquisition receipt added undeclared official code")
    if (
        record.acquirer_public_key_base64 != trusted_acquirer.public_key_base64
        or record.acquirer_public_key_sha256 != trusted_acquirer.public_key_sha256
    ):
        raise AttestationError("source-acquisition receipt used an untrusted acquirer")
    trusted_acquirer.verify(ATTESTATION_DOMAIN, attested_payload(record), record.attestation)
    return record


__all__ = [
    "ATTESTATION_DOMAIN",
    "PROTOCOL_ID",
    "PrimarySourceAcquisitionReceiptV06",
    "make_primary_source_acquisition_receipt_v0_6",
    "verify_primary_source_acquisition_receipt_v0_6",
]
