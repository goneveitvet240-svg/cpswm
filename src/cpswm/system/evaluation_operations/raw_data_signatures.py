"""Authority-attested signatures for immutable raw data artifacts.

A digest detects byte drift but does not identify who approved the bytes.  This
module binds the complete file digest, ordered chunk digests, pinned dataset
revision, split and locator, then authenticates that record with the existing
independent attestation authority.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware, utc_now
from cpswm.system.attestation import (
    DOMAIN_RAW_DATA_SIGNATURE,
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

RAW_DATA_SIGNATURE_VERSION = "raw-data-signature@0.1"


class RawDataArtifactSignature(ContractModel):
    signature_version: str = RAW_DATA_SIGNATURE_VERSION
    dataset_id: str = Field(min_length=1)
    dataset_revision: str = Field(min_length=1)
    source_split: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    byte_length: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_size_bytes: int = Field(gt=0)
    chunk_sha256s: tuple[str, ...]
    signed_at: datetime = Field(default_factory=utc_now)
    attestation: Attestation | None = None

    @field_validator("signed_at")
    @classmethod
    def _aware_time(cls, value: datetime) -> datetime:
        return require_aware(value, "signed_at")

    @model_validator(mode="after")
    def _signature_semantics(self) -> Self:
        if self.signature_version != RAW_DATA_SIGNATURE_VERSION:
            raise ValueError("unsupported raw-data signature version")
        expected_chunks = (
            0
            if self.byte_length == 0
            else (self.byte_length + self.chunk_size_bytes - 1) // self.chunk_size_bytes
        )
        if len(self.chunk_sha256s) != expected_chunks:
            raise ValueError("raw-data signature chunk count does not match byte length")
        if any(
            len(value) != 64 or set(value) - set("0123456789abcdef") for value in self.chunk_sha256s
        ):
            raise ValueError("raw-data chunk signatures must be lowercase SHA-256 digests")
        return self

    def attested_content(self) -> dict[str, object]:
        return attested_payload(self)

    @property
    def signature_sha256(self) -> str:
        return content_sha256(self)


def _hash_file(path: Path, chunk_size_bytes: int) -> tuple[int, str, tuple[str, ...]]:
    total = 0
    aggregate = hashlib.sha256()
    chunks: list[str] = []
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        while block := handle.read(chunk_size_bytes):
            total += len(block)
            aggregate.update(block)
            chunks.append(hashlib.sha256(block).hexdigest())
        after = os.fstat(handle.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("raw-data source changed while it was being hashed")
    return total, aggregate.hexdigest(), tuple(chunks)


def sign_raw_data_file(
    path: Path | str,
    *,
    dataset_id: str,
    dataset_revision: str,
    source_split: str,
    media_type: str,
    signer: Ed25519AttestationSigner,
    chunk_size_bytes: int = 4 * 1024 * 1024,
) -> RawDataArtifactSignature:
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("raw-data signature source must be a regular file")
    if chunk_size_bytes <= 0:
        raise ValueError("raw-data signature chunk size must be positive")
    size, digest, chunk_digests = _hash_file(source, chunk_size_bytes)
    unsigned = RawDataArtifactSignature(
        dataset_id=dataset_id,
        dataset_revision=dataset_revision,
        source_split=source_split,
        source_locator=str(source),
        media_type=media_type,
        byte_length=size,
        content_sha256=digest,
        chunk_size_bytes=chunk_size_bytes,
        chunk_sha256s=chunk_digests,
    )
    signature = signer.sign(DOMAIN_RAW_DATA_SIGNATURE, unsigned.attested_content())
    return unsigned.model_copy(update={"attestation": signature})


def verify_raw_data_file(
    path: Path | str,
    signature: RawDataArtifactSignature,
    *,
    verifier: Ed25519AttestationVerifier,
) -> RawDataArtifactSignature:
    signature = RawDataArtifactSignature.model_validate(signature.model_dump(mode="python"))
    verifier.verify(
        DOMAIN_RAW_DATA_SIGNATURE,
        signature.attested_content(),
        signature.attestation,
    )
    source = Path(path).resolve(strict=True)
    if str(source) != signature.source_locator:
        raise ValueError("raw-data source locator does not match the signed file")
    size, digest, chunks = _hash_file(source, signature.chunk_size_bytes)
    if size != signature.byte_length:
        raise ValueError("raw-data byte length does not match the signature")
    if digest != signature.content_sha256:
        raise ValueError("raw-data content digest does not match the signature")
    if chunks != signature.chunk_sha256s:
        raise ValueError("raw-data chunk digest does not match the signature")
    return signature


__all__ = [
    "RAW_DATA_SIGNATURE_VERSION",
    "RawDataArtifactSignature",
    "sign_raw_data_file",
    "verify_raw_data_file",
]
