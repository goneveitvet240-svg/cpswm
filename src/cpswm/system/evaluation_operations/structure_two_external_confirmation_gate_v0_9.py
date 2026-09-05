"""Fail-closed external confirmation gate for Structure Two v0.9.

This module closes three boundaries which cannot be represented by the legacy
v0.6 authorization report:

* a persistent, append-only consumption head for a one-use sealed opening;
* Gate-B scoring derived exclusively from verified canonical task receipts;
* a four-party witnessed combined authorization which re-verifies every prior
  artifact and a typed six-method fidelity decision.

The helpers named ``make_*`` are test/convenience ceremonies.  Production use
should keep private keys in four independently controlled processes and use the
``prepare_*``, ``*_signing_requests_*`` and ``finalize_*`` APIs instead.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Iterator, Mapping, Sequence, Set
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, Self

from pydantic import Field, StrictInt, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    AGGREGATE_ATTESTATION_DOMAIN,
    RECEIPT_ATTESTATION_DOMAIN,
    CanonicalPerEpisodeExecutionArtifactV09,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    default_external_method_specifications_v0_2,
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_a_v0_6 import (
    GateAArtifactPathsV06,
    verify_gate_a_report_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
    validate_structure_two_gate_b_v0_6_draft,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    ATTESTATION_DOMAIN as ISOLATION_ATTESTATION_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    DEFAULT_RESOURCE_LIMITS,
    IsolationResourceLimitsV09,
    verify_isolation_receipt_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    DetachedSigningRequestV09,
    ForbiddenSeedNamespacesV09,
    SealedGateBOpeningV09,
    SealedGateBOpeningVerificationContextV09,
    VerifiedGateALifecycleCompletionV09,
    VerifiedSealedGateBCommitmentV09,
    build_sealed_gate_b_opening_context_v0_9,
    sign_detached_request_v0_9,
    verify_gate_a_lifecycle_completion_record_v0_9,
    verify_sealed_gate_b_commitment_record_v0_9,
    verify_sealed_gate_b_opening_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_stratified_gate_b_v0_6 import (
    ComparisonPair,
    MechanismRequirement,
    StratifiedArmTrace,
    run_stratified_gate_b,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

OPENING_CONSUMPTION_PROTOCOL_ID = "structure-two-opening-consumption-ledger-record@0.9"
OPENING_CONSUMPTION_HEAD_PROTOCOL_ID = "structure-two-opening-consumption-ledger-head@0.9"
AUTHORITATIVE_LEDGER_STORE_IDENTITY_PROTOCOL_ID = (
    "structure-two-authoritative-opening-ledger-store-identity@0.9"
)
AUTHORITATIVE_LEDGER_ANCHOR_PROTOCOL_ID = "structure-two-authoritative-opening-ledger-anchor@0.9"
AUTHORITATIVE_LEDGER_ENTRY_PROTOCOL_ID = "structure-two-authoritative-opening-ledger-entry@0.9"
AUTHORITATIVE_LEDGER_CHECKPOINT_PROTOCOL_ID = (
    "structure-two-authoritative-opening-ledger-checkpoint@0.9"
)
SEALED_GATE_B_SCORE_PROTOCOL_ID = "structure-two-sealed-stratified-gate-b-score@0.9"
VERIFIER_IDENTITY_PROTOCOL_ID = "structure-two-independent-verifier-identity@0.9"
FIDELITY_SNAPSHOT_PROTOCOL_ID = "structure-two-six-method-fidelity-snapshot@0.9"
FIDELITY_EVIDENCE_PROTOCOL_ID = "structure-two-verified-six-method-fidelity@0.9"
COMBINED_AUTHORIZATION_PROTOCOL_ID = "structure-two-external-confirmation-authorization@0.9"
BLOCKER_PROTOCOL_ID = "structure-two-external-confirmation-blocker@0.9"

# Gate B v0.7 replaced the action-only v0.6 semantics for every future run.
# This module is retained so historical v0.6 artifacts remain inspectable, but
# none of its old positive paths may mint a current external authorization.
LEGACY_GATE_B_V0_6_SUPERSEDED_REASON = (
    "Gate B v0.6 external confirmation is historical and was superseded by "
    "structure-two-stratified-mechanism-dual-readout-gate-b@0.7; a separately "
    "implemented and independently attested v0.7 belief AND action AND mechanism "
    "receipt is required"
)

CONSUMPTION_REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.opening_consumption.reviewer.v0.9"
CONSUMPTION_EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.opening_consumption.executor.v0.9"
CONSUMPTION_CUSTODIAN_DOMAIN = "cpswm.evaluation.structure_two.opening_consumption.custodian.v0.9"
CONSUMPTION_AUTHORITY_DOMAIN = (
    "cpswm.evaluation.structure_two.opening_consumption.authority_witness.v0.9"
)
SEALED_SCORE_REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.sealed_gate_b.reviewer.v0.9"
SEALED_SCORE_EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.sealed_gate_b.executor.v0.9"
SEALED_SCORE_CUSTODIAN_DOMAIN = "cpswm.evaluation.structure_two.sealed_gate_b.custodian.v0.9"
SEALED_SCORE_AUTHORITY_DOMAIN = (
    "cpswm.evaluation.structure_two.sealed_gate_b.authority_witness.v0.9"
)
FIDELITY_REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.six_method_fidelity.reviewer.v0.9"
COMBINED_REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.combined.reviewer.v0.9"
COMBINED_EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.combined.executor.v0.9"
COMBINED_CUSTODIAN_DOMAIN = "cpswm.evaluation.structure_two.combined.custodian.v0.9"
COMBINED_AUTHORITY_DOMAIN = "cpswm.evaluation.structure_two.combined.authority_witness.v0.9"

ZERO_SHA256 = "0" * 64
EXTERNAL_METHOD_SPECIFICATIONS = default_external_method_specifications_v0_2()
EXTERNAL_METHOD_ARMS = tuple(row.arm for row in EXTERNAL_METHOD_SPECIFICATIONS)
EXTERNAL_METHOD_NAMES = {row.arm: row.method for row in EXTERNAL_METHOD_SPECIFICATIONS}

# This is deliberately a claim boundary, not a marketing label.  The file
# backend below gives durable process-restart replay protection and detects a
# stale/forked log against its separately atomically replaced checkpoint.  A
# same-owner administrator can still replace *both* files.  Formal external
# confirmation therefore requires this root to be held by the enrollment
# authority on WORM storage or mirrored into an independently witnessed
# transparency log; a repository-local directory is not external immutable
# custody.
AUTHORITATIVE_LEDGER_CLAIM_BOUNDARY = (
    "The POSIX file backend is durable and fail-closed but is not, by itself, "
    "external immutable custody. Formal runs require an enrollment-authority-owned "
    "storage root backed by WORM storage or an independently witnessed transparency log."
)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_identifier(value: str, *, label: str, minimum_length: int = 1) -> None:
    if (
        len(value) < minimum_length
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{label} is malformed")


def _validate_utc(value: datetime, *, label: str) -> None:
    require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


def _content_bound_record(
    payload: Mapping[str, Any],
    model: type[ContractModel],
    *,
    label: str,
) -> tuple[ContractModel, str]:
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"{label} content hash mismatch")
    record = model.model_validate(unsigned)
    if unsigned != record.model_dump(mode="json"):
        raise ValueError(f"{label} encoding is noncanonical")
    return record, stored


class PublicKeyBindingV09(ContractModel):
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_public_key(self) -> Self:
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id,
            public_key_base64=self.public_key_base64,
        )
        if verifier.public_key_sha256 != self.public_key_sha256:
            raise ValueError("public-key binding hash mismatch")
        return self


class FourPartySigningKeysV09(ContractModel):
    reviewer: PublicKeyBindingV09
    executor: PublicKeyBindingV09
    custodian: PublicKeyBindingV09
    enrollment_authority: PublicKeyBindingV09

    @model_validator(mode="after")
    def validate_independence(self) -> Self:
        rows = (self.reviewer, self.executor, self.custodian, self.enrollment_authority)
        if len({row.key_id for row in rows}) != 4:
            raise ValueError("four-party key IDs must be pairwise distinct")
        if len({row.public_key_sha256 for row in rows}) != 4:
            raise ValueError("four-party public keys must be pairwise distinct")
        return self


def _key_binding(verifier: Ed25519AttestationVerifier) -> PublicKeyBindingV09:
    return PublicKeyBindingV09(
        key_id=verifier.key_id,
        public_key_base64=verifier.public_key_base64,
        public_key_sha256=verifier.public_key_sha256,
    )


def _signing_keys(
    *,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> FourPartySigningKeysV09:
    return FourPartySigningKeysV09(
        reviewer=_key_binding(reviewer),
        executor=_key_binding(executor),
        custodian=_key_binding(custodian),
        enrollment_authority=_key_binding(enrollment_authority),
    )


def _verifier(binding: PublicKeyBindingV09) -> Ed25519AttestationVerifier:
    return Ed25519AttestationVerifier.from_public_key_base64(
        key_id=binding.key_id,
        public_key_base64=binding.public_key_base64,
    )


def _detached_request(
    *,
    artifact_protocol: str,
    role: str,
    domain: str,
    binding: PublicKeyBindingV09,
    payload: Mapping[str, Any],
) -> DetachedSigningRequestV09:
    materialized = dict(payload)
    return DetachedSigningRequestV09(
        artifact_protocol=artifact_protocol,
        role=role,
        domain=domain,
        expected_key_id=binding.key_id,
        expected_public_key_base64=binding.public_key_base64,
        expected_public_key_sha256=binding.public_key_sha256,
        payload=materialized,
        payload_sha256=content_sha256(materialized),
    )


def _assert_verifier(binding: PublicKeyBindingV09, trusted: Ed25519AttestationVerifier) -> None:
    if (
        binding.key_id != trusted.key_id
        or binding.public_key_base64 != trusted.public_key_base64
        or binding.public_key_sha256 != trusted.public_key_sha256
    ):
        raise AttestationError("record uses a key outside the enrolled trust registry")


class OpeningConsumptionLedgerRecordV09(ContractModel):
    """One append-only transition from an opening head to a consumed head."""

    protocol: Literal["structure-two-opening-consumption-ledger-record@0.9"] = (
        "structure-two-opening-consumption-ledger-record@0.9"
    )
    status: Literal["SEALED_OPENING_CONSUMED_ONCE"] = "SEALED_OPENING_CONSUMED_ONCE"
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    opening_ledger_sequence: StrictInt = Field(ge=0)
    previous_ledger_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_ledger_sequence: StrictInt = Field(ge=0)
    consumption_ledger_sequence: StrictInt = Field(ge=0)
    opened_at_utc: datetime
    consumed_at_utc: datetime
    signing_keys: FourPartySigningKeysV09
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    enrollment_authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(self.ledger_identifier, label="ledger identifier")
        _validate_identifier(
            self.opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        _validate_utc(self.opened_at_utc, label="opening time")
        _validate_utc(self.consumed_at_utc, label="consumption time")
        if self.previous_ledger_sequence != self.opening_ledger_sequence:
            raise ValueError("consumption must extend the exact signed opening sequence")
        if self.consumption_ledger_sequence != self.previous_ledger_sequence + 1:
            raise ValueError("consumption ledger sequence must append exactly one record")
        if self.consumed_at_utc <= self.opened_at_utc:
            raise ValueError("opening consumption timestamp must follow opening")
        return self


@dataclass(frozen=True, slots=True)
class OpeningConsumptionLedgerHeadV09:
    ledger_identifier: str
    immutable_manifest_sha256: str
    producer_run_id: str
    ledger_sequence: int
    previous_head_sha256: str
    record_content_sha256: str
    opening_content_sha256: str
    opening_attempt_id: str
    consumed_at_utc: datetime
    consumed_attempt_ids: frozenset[str]

    @property
    def protocol(self) -> str:
        return OPENING_CONSUMPTION_HEAD_PROTOCOL_ID

    @property
    def head_sha256(self) -> str:
        # The signed record's content hash is the append-only head.
        return self.record_content_sha256


class AuthoritativeLedgerStoreIdentityV09(ContractModel):
    """Externally supplied identity of the authority-owned ledger root."""

    protocol: Literal["structure-two-authoritative-opening-ledger-store-identity@0.9"] = (
        "structure-two-authoritative-opening-ledger-store-identity@0.9"
    )
    backend: Literal["posix-flock-canonical-jsonl-cas"] = "posix-flock-canonical-jsonl-cas"
    authority_identifier: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    canonical_root_path: str = Field(min_length=1)
    root_device: StrictInt = Field(ge=0)
    root_inode: StrictInt = Field(ge=1)
    root_owner_uid: StrictInt = Field(ge=0)
    root_mode: StrictInt = Field(ge=0, le=0o7777)
    ledger_filename: str = Field(pattern=r"^opening-consumption-[0-9a-f]{24}\.jsonl$")
    checkpoint_filename: str = Field(pattern=r"^opening-consumption-[0-9a-f]{24}\.head\.json$")
    lock_filename: str = Field(pattern=r"^opening-consumption-[0-9a-f]{24}\.lock$")

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        _validate_identifier(self.authority_identifier, label="ledger authority identifier")
        _validate_identifier(self.ledger_identifier, label="ledger identifier")
        if not Path(self.canonical_root_path).is_absolute():
            raise ValueError("authoritative ledger root path must be absolute")
        if self.root_mode & 0o077:
            raise ValueError("authoritative ledger root must deny group/world access")
        suffix = hashlib.sha256(self.ledger_identifier.encode("utf-8")).hexdigest()[:24]
        expected_names = (
            f"opening-consumption-{suffix}.jsonl",
            f"opening-consumption-{suffix}.head.json",
            f"opening-consumption-{suffix}.lock",
        )
        if (
            self.ledger_filename,
            self.checkpoint_filename,
            self.lock_filename,
        ) != expected_names:
            raise ValueError("authoritative ledger filenames are not identifier-derived")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


class AuthoritativeOpeningLedgerAnchorV09(ContractModel):
    protocol: Literal["structure-two-authoritative-opening-ledger-anchor@0.9"] = (
        "structure-two-authoritative-opening-ledger-anchor@0.9"
    )
    store_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_identifier: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    opening_ledger_sequence: StrictInt = Field(ge=0)
    opening_payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_anchor(self) -> Self:
        _validate_identifier(self.authority_identifier, label="ledger authority identifier")
        _validate_identifier(self.ledger_identifier, label="ledger identifier")
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        if self.opening_payload.get("content_sha256") != self.opening_content_sha256:
            raise ValueError("authoritative ledger anchor opening hash mismatch")
        return self


class AuthoritativeOpeningConsumptionEntryV09(ContractModel):
    protocol: Literal["structure-two-authoritative-opening-ledger-entry@0.9"] = (
        "structure-two-authoritative-opening-ledger-entry@0.9"
    )
    store_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_identifier: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    previous_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_ledger_sequence: StrictInt = Field(ge=0)
    record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_sequence: StrictInt = Field(ge=0)
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    consumption_record_payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        _validate_identifier(self.authority_identifier, label="ledger authority identifier")
        _validate_identifier(self.ledger_identifier, label="ledger identifier")
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        if self.ledger_sequence != self.previous_ledger_sequence + 1:
            raise ValueError("authoritative ledger entry does not append exactly one record")
        if self.consumption_record_payload.get("content_sha256") != (self.record_content_sha256):
            raise ValueError("authoritative ledger entry record hash mismatch")
        return self


class AuthoritativeOpeningLedgerCheckpointV09(ContractModel):
    protocol: Literal["structure-two-authoritative-opening-ledger-checkpoint@0.9"] = (
        "structure-two-authoritative-opening-ledger-checkpoint@0.9"
    )
    store_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_identifier: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_ledger_sequence: StrictInt = Field(ge=0)
    consumed_attempt_ids: tuple[str, ...]
    log_entry_content_sha256: tuple[str, ...] = Field(min_length=1)
    log_chain_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_checkpoint(self) -> Self:
        _validate_identifier(self.authority_identifier, label="ledger authority identifier")
        _validate_identifier(self.ledger_identifier, label="ledger identifier")
        _validate_identifier(self.producer_run_id, label="producer run ID")
        if self.consumed_attempt_ids != tuple(sorted(set(self.consumed_attempt_ids))):
            raise ValueError("authoritative ledger consumed-attempt set is noncanonical")
        if self.log_chain_sha256 != content_sha256(self.log_entry_content_sha256):
            raise ValueError("authoritative ledger checkpoint log-chain hash mismatch")
        return self


@dataclass(frozen=True, slots=True)
class OpeningConsumptionStoreVerificationContextV09:
    opening_payload: Mapping[str, Any]
    opening_context: SealedGateBOpeningVerificationContextV09
    trusted_opening_custodian: Ed25519AttestationVerifier
    trusted_reviewer: Ed25519AttestationVerifier
    trusted_executor: Ed25519AttestationVerifier
    trusted_consumption_custodian: Ed25519AttestationVerifier
    trusted_enrollment_authority: Ed25519AttestationVerifier


class AuthoritativeOpeningConsumptionStoreV09(Protocol):
    """Trusted durable state boundary supplied by the external verifier."""

    @property
    def identity(self) -> AuthoritativeLedgerStoreIdentityV09: ...

    def initialize_verified_opening(
        self,
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> None: ...

    def append_verified_consumption(
        self,
        consumption_payload: Mapping[str, Any],
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> OpeningConsumptionLedgerHeadV09: ...

    def read_verified_current_consumption_head(
        self,
        expected_consumption_payload: Mapping[str, Any],
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> OpeningConsumptionLedgerHeadV09: ...


@dataclass(frozen=True, slots=True)
class _ReplayedAuthoritativeLedgerV09:
    anchor: AuthoritativeOpeningLedgerAnchorV09
    anchor_content_sha256: str
    current_head_sha256: str
    current_ledger_sequence: int
    consumed_attempt_ids: frozenset[str]
    entry_content_sha256: tuple[str, ...]
    current_consumption_head: OpeningConsumptionLedgerHeadV09 | None
    current_consumption_payload: dict[str, Any] | None
    raw_log: bytes
    log_device: int
    log_inode: int


def _absolute_unresolved_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_symlink_components(path: Path) -> None:
    absolute = _absolute_unresolved_path(path)
    components = absolute.parts
    current = Path(components[0])
    for component in components[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError as exc:
            raise ValueError("authoritative ledger root must already exist") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("authoritative ledger path must not contain symlinks")


def inspect_authoritative_ledger_store_identity_v0_9(
    *,
    ledger_root: Path,
    ledger_identifier: str,
    authority_identifier: str,
    expected_owner_uid: int,
) -> AuthoritativeLedgerStoreIdentityV09:
    """Inspect a pre-provisioned external root without creating ledger state."""

    root = _absolute_unresolved_path(ledger_root)
    _assert_no_symlink_components(root)
    metadata = os.lstat(root)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("authoritative ledger root is not a directory")
    if metadata.st_uid != expected_owner_uid:
        raise ValueError("authoritative ledger root owner differs from expected authority")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o077:
        raise ValueError("authoritative ledger root must deny group/world access")
    _validate_identifier(authority_identifier, label="ledger authority identifier")
    _validate_identifier(ledger_identifier, label="ledger identifier")
    suffix = hashlib.sha256(ledger_identifier.encode("utf-8")).hexdigest()[:24]
    return AuthoritativeLedgerStoreIdentityV09(
        authority_identifier=authority_identifier,
        ledger_identifier=ledger_identifier,
        canonical_root_path=str(root),
        root_device=metadata.st_dev,
        root_inode=metadata.st_ino,
        root_owner_uid=metadata.st_uid,
        root_mode=mode,
        ledger_filename=f"opening-consumption-{suffix}.jsonl",
        checkpoint_filename=f"opening-consumption-{suffix}.head.json",
        lock_filename=f"opening-consumption-{suffix}.lock",
    )


def _materialize_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    materialized = json.loads(canonical_json(dict(payload)))
    if not isinstance(materialized, dict):  # pragma: no cover - mapping guarantees this
        raise TypeError("ledger payload must be a JSON object")
    return materialized


def _canonical_line(payload: Mapping[str, Any]) -> bytes:
    return canonical_json(dict(payload)).encode("utf-8") + b"\n"


def _parse_canonical_lines(raw: bytes, *, label: str) -> tuple[dict[str, Any], ...]:
    if not raw or not raw.endswith(b"\n"):
        raise ValueError(f"{label} is empty, truncated, or lacks a durable record boundary")
    result: list[dict[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} contains invalid JSON") from exc
        if not isinstance(decoded, dict) or _canonical_line(decoded) != line:
            raise ValueError(f"{label} contains noncanonical JSON")
        result.append(decoded)
    return tuple(result)


def _content_bound_payload(model: ContractModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


class FileAuthoritativeOpeningConsumptionStoreV09:
    """POSIX durable store with flock, append-only JSONL, and atomic checkpoint CAS.

    The expected identity must be obtained and supplied by the external verifier;
    this class never silently enrolls whichever directory happens to be present.
    See :data:`AUTHORITATIVE_LEDGER_CLAIM_BOUNDARY` for the custody boundary.
    """

    _MAX_LEDGER_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        *,
        ledger_root: Path,
        expected_identity: AuthoritativeLedgerStoreIdentityV09,
    ) -> None:
        self._ledger_root = _absolute_unresolved_path(ledger_root)
        self._expected_identity = expected_identity
        self._validate_root_identity()

    @property
    def identity(self) -> AuthoritativeLedgerStoreIdentityV09:
        return self._validate_root_identity()

    @property
    def ledger_path(self) -> Path:
        return self._ledger_root / self._expected_identity.ledger_filename

    @property
    def checkpoint_path(self) -> Path:
        return self._ledger_root / self._expected_identity.checkpoint_filename

    def _validate_root_identity(self) -> AuthoritativeLedgerStoreIdentityV09:
        actual = inspect_authoritative_ledger_store_identity_v0_9(
            ledger_root=self._ledger_root,
            ledger_identifier=self._expected_identity.ledger_identifier,
            authority_identifier=self._expected_identity.authority_identifier,
            expected_owner_uid=self._expected_identity.root_owner_uid,
        )
        if actual != self._expected_identity:
            raise ValueError("authoritative ledger root identity changed")
        return actual

    @staticmethod
    def _validate_regular_file(
        metadata: os.stat_result,
        *,
        identity: AuthoritativeLedgerStoreIdentityV09,
        label: str,
    ) -> None:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} is not a regular file")
        if metadata.st_uid != identity.root_owner_uid:
            raise ValueError(f"{label} is not owned by the enrolled authority identity")
        if metadata.st_dev != identity.root_device:
            raise ValueError(f"{label} is outside the enrolled authority filesystem")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError(f"{label} permissions must be exactly 0600")
        if metadata.st_nlink != 1:
            raise ValueError(f"{label} must not be hard-linked")

    def _open_regular_at(
        self,
        root_fd: int,
        name: str,
        *,
        flags: int,
        create: bool = False,
        label: str,
    ) -> int:
        open_flags = flags | os.O_CLOEXEC | os.O_NOFOLLOW
        if create:
            open_flags |= os.O_CREAT
        descriptor = os.open(name, open_flags, 0o600, dir_fd=root_fd)
        try:
            self._validate_regular_file(
                os.fstat(descriptor),
                identity=self._expected_identity,
                label=label,
            )
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    @contextmanager
    def _locked_root(self) -> Iterator[int]:
        identity = self._validate_root_identity()
        root_fd = os.open(
            self._ledger_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        lock_fd: int | None = None
        try:
            root_metadata = os.fstat(root_fd)
            if (
                root_metadata.st_dev != identity.root_device
                or root_metadata.st_ino != identity.root_inode
                or root_metadata.st_uid != identity.root_owner_uid
                or stat.S_IMODE(root_metadata.st_mode) != identity.root_mode
            ):
                raise ValueError("authoritative ledger root changed during open")
            lock_fd = self._open_regular_at(
                root_fd,
                identity.lock_filename,
                flags=os.O_RDWR,
                create=True,
                label="authoritative ledger lock",
            )
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            # Recheck after the potentially blocking lock acquisition.
            if self._validate_root_identity() != identity:
                raise ValueError("authoritative ledger root changed while awaiting lock")
            yield root_fd
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            os.close(root_fd)

    def _read_named_file(
        self,
        root_fd: int,
        name: str,
        *,
        label: str,
        missing_ok: bool = False,
    ) -> tuple[bytes, os.stat_result] | None:
        try:
            descriptor = self._open_regular_at(
                root_fd,
                name,
                flags=os.O_RDONLY,
                label=label,
            )
        except FileNotFoundError:
            if missing_ok:
                return None
            raise ValueError(f"{label} is missing") from None
        try:
            chunks: list[bytes] = []
            length = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                length += len(chunk)
                if length > self._MAX_LEDGER_BYTES:
                    raise ValueError(f"{label} exceeds the verification size limit")
                chunks.append(chunk)
            return b"".join(chunks), os.fstat(descriptor)
        finally:
            os.close(descriptor)

    def _create_log(self, root_fd: int, raw: bytes) -> os.stat_result:
        identity = self._expected_identity
        try:
            descriptor = self._open_regular_at(
                root_fd,
                identity.ledger_filename,
                flags=os.O_WRONLY | os.O_EXCL,
                create=True,
                label="authoritative ledger log",
            )
        except FileExistsError as exc:
            raise ValueError("authoritative ledger already exists") from exc
        try:
            written = os.write(descriptor, raw)
            if written != len(raw):
                raise OSError("short write while creating authoritative ledger")
            os.fsync(descriptor)
            return os.fstat(descriptor)
        finally:
            os.close(descriptor)

    def _atomic_checkpoint(self, root_fd: int, payload: Mapping[str, Any]) -> None:
        identity = self._expected_identity
        existing = self._read_named_file(
            root_fd,
            identity.checkpoint_filename,
            label="authoritative ledger checkpoint",
            missing_ok=True,
        )
        if existing is not None:
            _parse_canonical_lines(existing[0], label="authoritative ledger checkpoint")
        temporary_name = (
            f".{identity.checkpoint_filename}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
        )
        descriptor: int | None = None
        try:
            descriptor = self._open_regular_at(
                root_fd,
                temporary_name,
                flags=os.O_WRONLY | os.O_EXCL,
                create=True,
                label="authoritative ledger checkpoint temporary file",
            )
            raw = _canonical_line(payload)
            written = os.write(descriptor, raw)
            if written != len(raw):
                raise OSError("short write while writing authoritative ledger checkpoint")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(
                temporary_name,
                identity.checkpoint_filename,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
            os.fsync(root_fd)
            replaced = self._read_named_file(
                root_fd,
                identity.checkpoint_filename,
                label="authoritative ledger checkpoint",
            )
            assert replaced is not None
            if replaced[0] != raw:
                raise ValueError("authoritative ledger checkpoint replacement was not atomic")
        finally:
            if descriptor is not None:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=root_fd)

    @staticmethod
    def _checkpoint_for_state(
        *,
        identity: AuthoritativeLedgerStoreIdentityV09,
        anchor: AuthoritativeOpeningLedgerAnchorV09,
        current_head_sha256: str,
        current_ledger_sequence: int,
        consumed_attempt_ids: frozenset[str],
        entry_content_sha256: tuple[str, ...],
    ) -> dict[str, Any]:
        return _content_bound_payload(
            AuthoritativeOpeningLedgerCheckpointV09(
                store_identity_sha256=identity.content_sha256,
                authority_identifier=identity.authority_identifier,
                ledger_identifier=identity.ledger_identifier,
                immutable_manifest_sha256=anchor.immutable_manifest_sha256,
                producer_run_id=anchor.producer_run_id,
                opening_content_sha256=anchor.opening_content_sha256,
                opening_attempt_id=anchor.opening_attempt_id,
                current_head_sha256=current_head_sha256,
                current_ledger_sequence=current_ledger_sequence,
                consumed_attempt_ids=tuple(sorted(consumed_attempt_ids)),
                log_entry_content_sha256=entry_content_sha256,
                log_chain_sha256=content_sha256(entry_content_sha256),
            )
        )

    def _verified_opening(
        self,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> tuple[dict[str, Any], SealedGateBOpeningV09, str]:
        payload = _materialize_mapping(verification.opening_payload)
        opening = verify_sealed_gate_b_opening_v0_9(
            payload,
            context=verification.opening_context,
            trusted_custodian=verification.trusted_opening_custodian,
        )
        stored = payload.get("content_sha256")
        if not _is_sha256(stored):
            raise ValueError("verified opening has no canonical content hash")
        assert isinstance(stored, str)
        if opening.ledger_identifier != self._expected_identity.ledger_identifier:
            raise ValueError("verified opening belongs to another authoritative ledger")
        return payload, opening, stored

    def initialize_verified_opening(
        self,
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> None:
        opening_payload, opening, opening_hash = self._verified_opening(verification)
        identity = self.identity
        anchor = AuthoritativeOpeningLedgerAnchorV09(
            store_identity_sha256=identity.content_sha256,
            authority_identifier=identity.authority_identifier,
            ledger_identifier=opening.ledger_identifier,
            immutable_manifest_sha256=opening.immutable_manifest_sha256,
            producer_run_id=opening.producer_run_id,
            opening_content_sha256=opening_hash,
            opening_attempt_id=opening.opening_attempt_id,
            opening_ledger_sequence=opening.opening_ledger_sequence,
            opening_payload=opening_payload,
        )
        anchor_payload = _content_bound_payload(anchor)
        raw_anchor = _canonical_line(anchor_payload)
        checkpoint = self._checkpoint_for_state(
            identity=identity,
            anchor=anchor,
            current_head_sha256=opening_hash,
            current_ledger_sequence=opening.opening_ledger_sequence,
            consumed_attempt_ids=frozenset(),
            entry_content_sha256=(str(anchor_payload["content_sha256"]),),
        )
        with self._locked_root() as root_fd:
            existing = self._read_named_file(
                root_fd,
                identity.ledger_filename,
                label="authoritative ledger log",
                missing_ok=True,
            )
            if existing is not None:
                # Initialization is idempotent only for the exact verified anchor and
                # exact checkpoint.  It never rolls a consumed head back to opening.
                if existing[0] != raw_anchor:
                    raise ValueError("authoritative ledger is already initialized or consumed")
                stored_checkpoint = self._read_named_file(
                    root_fd,
                    identity.checkpoint_filename,
                    label="authoritative ledger checkpoint",
                )
                assert stored_checkpoint is not None
                if stored_checkpoint[0] != _canonical_line(checkpoint):
                    raise ValueError("authoritative ledger initialization checkpoint differs")
                return
            metadata = self._create_log(root_fd, raw_anchor)
            if metadata.st_dev != identity.root_device:
                raise ValueError("authoritative ledger was created on an unexpected filesystem")
            self._atomic_checkpoint(root_fd, checkpoint)
            os.fsync(root_fd)

    def _load_verified_state(
        self,
        root_fd: int,
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> _ReplayedAuthoritativeLedgerV09:
        identity = self._expected_identity
        opening_payload, opening, opening_hash = self._verified_opening(verification)
        stored_log = self._read_named_file(
            root_fd,
            identity.ledger_filename,
            label="authoritative ledger log",
        )
        assert stored_log is not None
        raw_log, log_metadata = stored_log
        rows = _parse_canonical_lines(raw_log, label="authoritative ledger log")
        raw_anchor, anchor_hash = _content_bound_record(
            rows[0],
            AuthoritativeOpeningLedgerAnchorV09,
            label="authoritative ledger anchor",
        )
        anchor = AuthoritativeOpeningLedgerAnchorV09.model_validate(raw_anchor)
        expected_anchor = {
            "store_identity_sha256": identity.content_sha256,
            "authority_identifier": identity.authority_identifier,
            "ledger_identifier": opening.ledger_identifier,
            "immutable_manifest_sha256": opening.immutable_manifest_sha256,
            "producer_run_id": opening.producer_run_id,
            "opening_content_sha256": opening_hash,
            "opening_attempt_id": opening.opening_attempt_id,
            "opening_ledger_sequence": opening.opening_ledger_sequence,
            "opening_payload": opening_payload,
        }
        dumped_anchor = anchor.model_dump(mode="json")
        if any(dumped_anchor[name] != value for name, value in expected_anchor.items()):
            raise ValueError("authoritative ledger anchor differs from verified opening")
        current_head = opening_hash
        current_sequence = opening.opening_ledger_sequence
        consumed: frozenset[str] = frozenset()
        entry_hashes = [anchor_hash]
        current_consumption_head: OpeningConsumptionLedgerHeadV09 | None = None
        current_consumption_payload: dict[str, Any] | None = None
        for row in rows[1:]:
            raw_entry, entry_hash = _content_bound_record(
                row,
                AuthoritativeOpeningConsumptionEntryV09,
                label="authoritative ledger consumption entry",
            )
            entry = AuthoritativeOpeningConsumptionEntryV09.model_validate(raw_entry)
            expected_entry = {
                "store_identity_sha256": identity.content_sha256,
                "authority_identifier": identity.authority_identifier,
                "ledger_identifier": opening.ledger_identifier,
                "immutable_manifest_sha256": opening.immutable_manifest_sha256,
                "producer_run_id": opening.producer_run_id,
                "previous_head_sha256": current_head,
                "previous_ledger_sequence": current_sequence,
                "opening_attempt_id": anchor.opening_attempt_id,
            }
            dumped_entry = entry.model_dump(mode="python")
            if any(dumped_entry[name] != value for name, value in expected_entry.items()):
                raise ValueError("authoritative ledger contains a forked or rolled-back entry")
            head = verify_opening_consumption_record_v0_9(
                entry.consumption_record_payload,
                expected_opening_content_sha256=opening_hash,
                expected_opening_attempt_id=anchor.opening_attempt_id,
                expected_immutable_manifest_sha256=opening.immutable_manifest_sha256,
                expected_producer_run_id=opening.producer_run_id,
                expected_ledger_identifier=opening.ledger_identifier,
                expected_previous_ledger_head_sha256=current_head,
                expected_previous_ledger_sequence=current_sequence,
                expected_consumption_ledger_sequence=entry.ledger_sequence,
                already_consumed_attempt_ids=consumed,
                trusted_reviewer=verification.trusted_reviewer,
                trusted_executor=verification.trusted_executor,
                trusted_custodian=verification.trusted_consumption_custodian,
                trusted_enrollment_authority=verification.trusted_enrollment_authority,
            )
            if (
                head.record_content_sha256 != entry.record_content_sha256
                or head.opening_attempt_id != entry.opening_attempt_id
            ):
                raise ValueError("authoritative ledger wrapper differs from signed consumption")
            current_head = head.head_sha256
            current_sequence = head.ledger_sequence
            consumed = head.consumed_attempt_ids
            entry_hashes.append(entry_hash)
            current_consumption_head = head
            current_consumption_payload = entry.consumption_record_payload
        expected_checkpoint = self._checkpoint_for_state(
            identity=identity,
            anchor=anchor,
            current_head_sha256=current_head,
            current_ledger_sequence=current_sequence,
            consumed_attempt_ids=consumed,
            entry_content_sha256=tuple(entry_hashes),
        )
        stored_checkpoint = self._read_named_file(
            root_fd,
            identity.checkpoint_filename,
            label="authoritative ledger checkpoint",
        )
        assert stored_checkpoint is not None
        checkpoint_rows = _parse_canonical_lines(
            stored_checkpoint[0],
            label="authoritative ledger checkpoint",
        )
        if len(checkpoint_rows) != 1:
            raise ValueError("authoritative ledger checkpoint must contain exactly one record")
        _content_bound_record(
            checkpoint_rows[0],
            AuthoritativeOpeningLedgerCheckpointV09,
            label="authoritative ledger checkpoint",
        )
        if stored_checkpoint[0] != _canonical_line(expected_checkpoint):
            raise ValueError("authoritative ledger log and current-head checkpoint disagree")
        return _ReplayedAuthoritativeLedgerV09(
            anchor=anchor,
            anchor_content_sha256=anchor_hash,
            current_head_sha256=current_head,
            current_ledger_sequence=current_sequence,
            consumed_attempt_ids=consumed,
            entry_content_sha256=tuple(entry_hashes),
            current_consumption_head=current_consumption_head,
            current_consumption_payload=current_consumption_payload,
            raw_log=raw_log,
            log_device=log_metadata.st_dev,
            log_inode=log_metadata.st_ino,
        )

    def append_verified_consumption(
        self,
        consumption_payload: Mapping[str, Any],
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> OpeningConsumptionLedgerHeadV09:
        materialized_consumption = _materialize_mapping(consumption_payload)
        identity = self.identity
        with self._locked_root() as root_fd:
            state = self._load_verified_state(root_fd, verification=verification)
            record_raw, record_hash = _content_bound_record(
                materialized_consumption,
                OpeningConsumptionLedgerRecordV09,
                label="opening-consumption record",
            )
            record = OpeningConsumptionLedgerRecordV09.model_validate(record_raw)
            if record.opening_attempt_id in state.consumed_attempt_ids:
                raise ValueError("sealed opening attempt has already been consumed")
            head = verify_opening_consumption_record_v0_9(
                materialized_consumption,
                expected_opening_content_sha256=state.anchor.opening_content_sha256,
                expected_opening_attempt_id=state.anchor.opening_attempt_id,
                expected_immutable_manifest_sha256=state.anchor.immutable_manifest_sha256,
                expected_producer_run_id=state.anchor.producer_run_id,
                expected_ledger_identifier=state.anchor.ledger_identifier,
                expected_previous_ledger_head_sha256=state.current_head_sha256,
                expected_previous_ledger_sequence=state.current_ledger_sequence,
                expected_consumption_ledger_sequence=state.current_ledger_sequence + 1,
                already_consumed_attempt_ids=state.consumed_attempt_ids,
                trusted_reviewer=verification.trusted_reviewer,
                trusted_executor=verification.trusted_executor,
                trusted_custodian=verification.trusted_consumption_custodian,
                trusted_enrollment_authority=verification.trusted_enrollment_authority,
            )
            entry = AuthoritativeOpeningConsumptionEntryV09(
                store_identity_sha256=identity.content_sha256,
                authority_identifier=identity.authority_identifier,
                ledger_identifier=state.anchor.ledger_identifier,
                immutable_manifest_sha256=state.anchor.immutable_manifest_sha256,
                producer_run_id=state.anchor.producer_run_id,
                previous_head_sha256=state.current_head_sha256,
                previous_ledger_sequence=state.current_ledger_sequence,
                record_content_sha256=record_hash,
                ledger_sequence=head.ledger_sequence,
                opening_attempt_id=head.opening_attempt_id,
                consumption_record_payload=materialized_consumption,
            )
            entry_payload = _content_bound_payload(entry)
            entry_raw = _canonical_line(entry_payload)
            descriptor = self._open_regular_at(
                root_fd,
                identity.ledger_filename,
                flags=os.O_WRONLY | os.O_APPEND,
                label="authoritative ledger log",
            )
            try:
                metadata = os.fstat(descriptor)
                if metadata.st_dev != state.log_device or metadata.st_ino != state.log_inode:
                    raise ValueError("authoritative ledger changed before compare-and-swap")
                written = os.write(descriptor, entry_raw)
                if written != len(entry_raw):
                    raise OSError("short append to authoritative ledger")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            expected_raw_log = state.raw_log + entry_raw
            appended = self._read_named_file(
                root_fd,
                identity.ledger_filename,
                label="authoritative ledger log",
            )
            assert appended is not None
            if (
                appended[0] != expected_raw_log
                or appended[1].st_dev != state.log_device
                or appended[1].st_ino != state.log_inode
            ):
                raise ValueError("authoritative ledger append lost CAS or forked")
            new_entry_hashes = (
                *state.entry_content_sha256,
                str(entry_payload["content_sha256"]),
            )
            checkpoint = self._checkpoint_for_state(
                identity=identity,
                anchor=state.anchor,
                current_head_sha256=head.head_sha256,
                current_ledger_sequence=head.ledger_sequence,
                consumed_attempt_ids=head.consumed_attempt_ids,
                entry_content_sha256=new_entry_hashes,
            )
            self._atomic_checkpoint(root_fd, checkpoint)
            os.fsync(root_fd)
            return head

    def read_verified_current_consumption_head(
        self,
        expected_consumption_payload: Mapping[str, Any],
        *,
        verification: OpeningConsumptionStoreVerificationContextV09,
    ) -> OpeningConsumptionLedgerHeadV09:
        expected = _materialize_mapping(expected_consumption_payload)
        with self._locked_root() as root_fd:
            state = self._load_verified_state(root_fd, verification=verification)
            if state.current_consumption_head is None or state.current_consumption_payload is None:
                raise ValueError("verified opening has not been durably consumed")
            if state.current_consumption_payload != expected:
                raise ValueError("authoritative current head differs from supplied consumption")
            return state.current_consumption_head


def _consumption_role_payload(record: OpeningConsumptionLedgerRecordV09) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "enrollment_authority_attestation",
            }
        ),
    )


def _consumption_authority_payload(record: OpeningConsumptionLedgerRecordV09) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"enrollment_authority_attestation"}))


def prepare_opening_consumption_record_v0_9(
    *,
    opening_payload: Mapping[str, Any],
    opening_context: SealedGateBOpeningVerificationContextV09,
    trusted_opening_custodian: Ed25519AttestationVerifier,
    previous_ledger_head_sha256: str,
    previous_ledger_sequence: int,
    consumption_ledger_sequence: int,
    consumed_at_utc: datetime,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> OpeningConsumptionLedgerRecordV09:
    """Verify an opening and prepare its one-use append-only consumption."""

    opening = verify_sealed_gate_b_opening_v0_9(
        opening_payload,
        context=opening_context,
        trusted_custodian=trusted_opening_custodian,
    )
    opening_content_sha256 = opening_payload.get("content_sha256")
    if not _is_sha256(opening_content_sha256):
        raise ValueError("sealed opening lacks a valid content hash")
    if previous_ledger_head_sha256 != opening_content_sha256:
        raise ValueError("consumption ledger does not extend the verified opening head")
    if previous_ledger_sequence != opening.opening_ledger_sequence:
        raise ValueError("consumption ledger previous sequence is stale or forked")
    return OpeningConsumptionLedgerRecordV09(
        immutable_manifest_sha256=opening.immutable_manifest_sha256,
        producer_run_id=opening.producer_run_id,
        ledger_identifier=opening.ledger_identifier,
        opening_content_sha256=opening_content_sha256,
        opening_attempt_id=opening.opening_attempt_id,
        opening_ledger_sequence=opening.opening_ledger_sequence,
        previous_ledger_head_sha256=previous_ledger_head_sha256,
        previous_ledger_sequence=previous_ledger_sequence,
        consumption_ledger_sequence=consumption_ledger_sequence,
        opened_at_utc=opening.opened_at_utc,
        consumed_at_utc=consumed_at_utc,
        signing_keys=_signing_keys(
            reviewer=reviewer,
            executor=executor,
            custodian=custodian,
            enrollment_authority=enrollment_authority,
        ),
    )


def opening_consumption_role_signing_requests_v0_9(
    prepared: OpeningConsumptionLedgerRecordV09,
) -> dict[str, DetachedSigningRequestV09]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("consumption role signing requires a wholly unsigned record")
    payload = _consumption_role_payload(prepared)
    return {
        "reviewer": _detached_request(
            artifact_protocol=prepared.protocol,
            role="reviewer",
            domain=CONSUMPTION_REVIEWER_DOMAIN,
            binding=prepared.signing_keys.reviewer,
            payload=payload,
        ),
        "executor": _detached_request(
            artifact_protocol=prepared.protocol,
            role="executor",
            domain=CONSUMPTION_EXECUTOR_DOMAIN,
            binding=prepared.signing_keys.executor,
            payload=payload,
        ),
        "custodian": _detached_request(
            artifact_protocol=prepared.protocol,
            role="custodian",
            domain=CONSUMPTION_CUSTODIAN_DOMAIN,
            binding=prepared.signing_keys.custodian,
            payload=payload,
        ),
    }


def opening_consumption_authority_signing_request_v0_9(
    prepared: OpeningConsumptionLedgerRecordV09,
    *,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
) -> DetachedSigningRequestV09:
    """Validate all role signatures before exposing the authority request."""

    role_payload = _consumption_role_payload(prepared)
    _verifier(prepared.signing_keys.reviewer).verify(
        CONSUMPTION_REVIEWER_DOMAIN,
        role_payload,
        reviewer_attestation,
    )
    _verifier(prepared.signing_keys.executor).verify(
        CONSUMPTION_EXECUTOR_DOMAIN,
        role_payload,
        executor_attestation,
    )
    _verifier(prepared.signing_keys.custodian).verify(
        CONSUMPTION_CUSTODIAN_DOMAIN,
        role_payload,
        custodian_attestation,
    )
    role_signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    return _detached_request(
        artifact_protocol=prepared.protocol,
        role="enrollment_authority",
        domain=CONSUMPTION_AUTHORITY_DOMAIN,
        binding=prepared.signing_keys.enrollment_authority,
        payload=_consumption_authority_payload(role_signed),
    )


def finalize_opening_consumption_record_v0_9(
    prepared: OpeningConsumptionLedgerRecordV09,
    *,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
    enrollment_authority_attestation: Attestation | None,
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("consumption finalization requires the prepared unsigned record")
    signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
            "enrollment_authority_attestation": enrollment_authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_opening_consumption_record_v0_9(
        payload,
        expected_opening_content_sha256=prepared.opening_content_sha256,
        expected_opening_attempt_id=prepared.opening_attempt_id,
        expected_immutable_manifest_sha256=prepared.immutable_manifest_sha256,
        expected_producer_run_id=prepared.producer_run_id,
        expected_ledger_identifier=prepared.ledger_identifier,
        expected_previous_ledger_head_sha256=prepared.previous_ledger_head_sha256,
        expected_previous_ledger_sequence=prepared.previous_ledger_sequence,
        expected_consumption_ledger_sequence=prepared.consumption_ledger_sequence,
        already_consumed_attempt_ids=frozenset(),
        trusted_reviewer=trusted_reviewer,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return payload


def make_opening_consumption_record_v0_9(
    *,
    opening_payload: Mapping[str, Any],
    opening_context: SealedGateBOpeningVerificationContextV09,
    previous_ledger_head_sha256: str,
    previous_ledger_sequence: int,
    consumption_ledger_sequence: int,
    consumed_at_utc: datetime,
    reviewer: Ed25519AttestationSigner,
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    prepared = prepare_opening_consumption_record_v0_9(
        opening_payload=opening_payload,
        opening_context=opening_context,
        trusted_opening_custodian=custodian.verifier(),
        previous_ledger_head_sha256=previous_ledger_head_sha256,
        previous_ledger_sequence=previous_ledger_sequence,
        consumption_ledger_sequence=consumption_ledger_sequence,
        consumed_at_utc=consumed_at_utc,
        reviewer=reviewer.verifier(),
        executor=executor.verifier(),
        custodian=custodian.verifier(),
        enrollment_authority=enrollment_authority.verifier(),
    )
    requests = opening_consumption_role_signing_requests_v0_9(prepared)
    reviewer_attestation = sign_detached_request_v0_9(requests["reviewer"], signer=reviewer)
    executor_attestation = sign_detached_request_v0_9(requests["executor"], signer=executor)
    custodian_attestation = sign_detached_request_v0_9(requests["custodian"], signer=custodian)
    authority_request = opening_consumption_authority_signing_request_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
    )
    return finalize_opening_consumption_record_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
        enrollment_authority_attestation=sign_detached_request_v0_9(
            authority_request,
            signer=enrollment_authority,
        ),
        trusted_reviewer=reviewer.verifier(),
        trusted_executor=executor.verifier(),
        trusted_custodian=custodian.verifier(),
        trusted_enrollment_authority=enrollment_authority.verifier(),
    )


def verify_opening_consumption_record_v0_9(
    payload: Mapping[str, Any],
    *,
    expected_opening_content_sha256: str,
    expected_opening_attempt_id: str,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_ledger_identifier: str,
    expected_previous_ledger_head_sha256: str,
    expected_previous_ledger_sequence: int,
    expected_consumption_ledger_sequence: int,
    already_consumed_attempt_ids: Set[str],
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> OpeningConsumptionLedgerHeadV09:
    raw_record, stored = _content_bound_record(
        payload,
        OpeningConsumptionLedgerRecordV09,
        label="opening-consumption record",
    )
    record = OpeningConsumptionLedgerRecordV09.model_validate(raw_record)
    expected = {
        "opening_content_sha256": expected_opening_content_sha256,
        "opening_attempt_id": expected_opening_attempt_id,
        "immutable_manifest_sha256": expected_immutable_manifest_sha256,
        "producer_run_id": expected_producer_run_id,
        "ledger_identifier": expected_ledger_identifier,
        "previous_ledger_head_sha256": expected_previous_ledger_head_sha256,
        "previous_ledger_sequence": expected_previous_ledger_sequence,
        "consumption_ledger_sequence": expected_consumption_ledger_sequence,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("opening-consumption record is replayed, stale, forked, or cross-run")
    if record.opening_attempt_id in already_consumed_attempt_ids:
        raise ValueError("sealed opening attempt has already been consumed")
    trusted = (
        (record.signing_keys.reviewer, trusted_reviewer),
        (record.signing_keys.executor, trusted_executor),
        (record.signing_keys.custodian, trusted_custodian),
        (record.signing_keys.enrollment_authority, trusted_enrollment_authority),
    )
    for binding, verifier in trusted:
        _assert_verifier(binding, verifier)
    role_payload = _consumption_role_payload(record)
    trusted_reviewer.verify(
        CONSUMPTION_REVIEWER_DOMAIN,
        role_payload,
        record.reviewer_attestation,
    )
    trusted_executor.verify(
        CONSUMPTION_EXECUTOR_DOMAIN,
        role_payload,
        record.executor_attestation,
    )
    trusted_custodian.verify(
        CONSUMPTION_CUSTODIAN_DOMAIN,
        role_payload,
        record.custodian_attestation,
    )
    # The authority signs the record *including* all three role signatures.
    trusted_enrollment_authority.verify(
        CONSUMPTION_AUTHORITY_DOMAIN,
        _consumption_authority_payload(record),
        record.enrollment_authority_attestation,
    )
    return OpeningConsumptionLedgerHeadV09(
        ledger_identifier=record.ledger_identifier,
        immutable_manifest_sha256=record.immutable_manifest_sha256,
        producer_run_id=record.producer_run_id,
        ledger_sequence=record.consumption_ledger_sequence,
        previous_head_sha256=record.previous_ledger_head_sha256,
        record_content_sha256=stored,
        opening_content_sha256=record.opening_content_sha256,
        opening_attempt_id=record.opening_attempt_id,
        consumed_at_utc=record.consumed_at_utc,
        consumed_attempt_ids=frozenset((*already_consumed_attempt_ids, record.opening_attempt_id)),
    )


def _comparison_protocol_payload(
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
) -> dict[str, Any]:
    return {
        "expected_arms": EXPECTED_ARMS,
        "comparison_pairs": tuple(asdict(row) for row in comparison_pairs),
        "mechanism_requirements": tuple(asdict(row) for row in mechanism_requirements),
    }


def derive_stratified_traces_from_canonical_execution_v0_9(
    artifact: CanonicalPerEpisodeExecutionArtifactV09,
) -> tuple[StratifiedArmTrace, ...]:
    """Derive scorer input from receipts; there is no caller-trace parameter."""

    if artifact.canonical_arms != EXPECTED_ARMS:
        raise ValueError("canonical execution changed the exact ten-arm set")
    traces: list[StratifiedArmTrace] = []
    for arm in EXPECTED_ARMS:
        receipts = tuple(
            bound.receipt for bound in artifact.task_receipts if bound.receipt.arm == arm
        )
        if tuple(row.episode_id for row in receipts) != artifact.episode_ids:
            raise ValueError("canonical receipts lack exact ordered arm-by-episode coverage")
        traces.append(
            StratifiedArmTrace(
                arm=arm,
                episode_actions=tuple((row.episode_id, row.action_sequence) for row in receipts),
                episode_mechanism_events=tuple(
                    (
                        row.episode_id,
                        tuple(step.mechanism_events for step in row.mechanism_steps),
                    )
                    for row in receipts
                ),
            )
        )
    return tuple(traces)


def _verified_canonical_execution(
    payload: Mapping[str, Any],
    *,
    verified_artifact: CanonicalPerEpisodeExecutionArtifactV09,
    trusted_executor: Ed25519AttestationVerifier,
    expected_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_gate_a_content_sha256: str,
    expected_opening_content_sha256: str,
    expected_opening_attempt_id: str,
) -> tuple[CanonicalPerEpisodeExecutionArtifactV09, str]:
    raw_record, stored = _content_bound_record(
        payload,
        CanonicalPerEpisodeExecutionArtifactV09,
        label="canonical execution artifact",
    )
    record = CanonicalPerEpisodeExecutionArtifactV09.model_validate(raw_record)
    if record != verified_artifact:
        raise ValueError("canonical execution differs from trusted semantic re-verification")
    binding = PublicKeyBindingV09(
        key_id=record.executor_key_id,
        public_key_base64=record.executor_public_key_base64,
        public_key_sha256=record.executor_public_key_sha256,
    )
    _assert_verifier(binding, trusted_executor)
    trusted_executor.verify(
        AGGREGATE_ATTESTATION_DOMAIN,
        attested_payload(record),
        record.attestation,
    )
    prerequisites = record.verified_prerequisites
    if (
        prerequisites.immutable_manifest_sha256 != expected_manifest_sha256
        or prerequisites.producer_run_id != expected_producer_run_id
        or prerequisites.gate_a_report_content_sha256 != expected_gate_a_content_sha256
        or prerequisites.sealed_opening_content_sha256 != expected_opening_content_sha256
        or prerequisites.opening_attempt_id != expected_opening_attempt_id
    ):
        raise ValueError("canonical execution prerequisite chain is cross-run or substituted")
    if any(
        bound.isolation.receipt.formal_isolation_verified is not True
        or bound.isolation.receipt.status != "ISOLATION_PASSED"
        for bound in record.task_receipts
    ):
        raise ValueError("canonical execution contains nonformal isolation evidence")
    for bound in record.task_receipts:
        runner = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=bound.receipt.runner_key_id,
            public_key_base64=bound.receipt.runner_public_key_base64,
        )
        if (
            runner.public_key_sha256 != bound.receipt.runner_public_key_sha256
            or runner.public_key_sha256 != bound.isolation.receipt.executor_public_key_sha256
            or runner.key_id != bound.isolation.receipt.executor_key_id
        ):
            raise AttestationError("canonical task runner/isolation signer binding mismatch")
        runner.verify(
            RECEIPT_ATTESTATION_DOMAIN,
            attested_payload(bound.receipt),
            bound.receipt.attestation,
        )
        runner.verify(
            ISOLATION_ATTESTATION_DOMAIN,
            bound.isolation.receipt.model_dump(
                mode="json",
                exclude={"executor_attestation"},
            ),
            bound.isolation.receipt.executor_attestation,
        )
    return record, stored


class SealedGateBScoreV09(ContractModel):
    protocol: Literal["structure-two-sealed-stratified-gate-b-score@0.9"] = (
        "structure-two-sealed-stratified-gate-b-score@0.9"
    )
    status: Literal["SCORED_FROM_CANONICAL_ISOLATED_RECEIPTS"] = (
        "SCORED_FROM_CANONICAL_ISOLATED_RECEIPTS"
    )
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    opening_consumption_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consumption_ledger_sequence: StrictInt = Field(ge=0)
    canonical_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_execution_id: str = Field(min_length=16)
    episode_ids: tuple[str, ...] = Field(min_length=1)
    isolation_receipt_content_sha256: tuple[str, ...] = Field(min_length=1)
    comparison_protocol_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_b_result: dict[str, Any]
    gate_b_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_b_passed: bool
    execution_ledger_sequence: StrictInt = Field(ge=0)
    gate_b_ledger_sequence: StrictInt = Field(ge=0)
    opening_consumed_at_utc: datetime
    execution_completed_at_utc: datetime
    gate_b_scored_at_utc: datetime
    signing_keys: FourPartySigningKeysV09
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    enrollment_authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.canonical_execution_id,
            label="canonical execution ID",
            minimum_length=16,
        )
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("sealed Gate B contains duplicate episode IDs")
        if len(set(self.isolation_receipt_content_sha256)) != len(
            self.isolation_receipt_content_sha256
        ):
            raise ValueError("sealed Gate B contains duplicate isolation receipts")
        if any(not _is_sha256(value) for value in self.isolation_receipt_content_sha256):
            raise ValueError("sealed Gate B contains malformed isolation receipt hashes")
        if self.gate_b_result.get("content_sha256") != self.gate_b_result_content_sha256:
            raise ValueError("sealed Gate-B nested result hash mismatch")
        if self.gate_b_result.get("gate_b_passed") is not self.gate_b_passed:
            raise ValueError("sealed Gate-B stored decision differs from canonical scorer")
        nested = dict(self.gate_b_result)
        nested_stored = nested.pop("content_sha256", None)
        if not isinstance(nested_stored, str) or content_sha256(nested) != nested_stored:
            raise ValueError("sealed Gate-B nested result is not content-bound")
        if self.execution_ledger_sequence != self.consumption_ledger_sequence + 1:
            raise ValueError("canonical execution sequence must immediately follow consumption")
        if self.gate_b_ledger_sequence != self.execution_ledger_sequence + 1:
            raise ValueError("sealed Gate-B score sequence must immediately follow execution")
        for label, value in (
            ("opening consumption", self.opening_consumed_at_utc),
            ("canonical execution completion", self.execution_completed_at_utc),
            ("Gate-B scoring", self.gate_b_scored_at_utc),
        ):
            _validate_utc(value, label=label)
        if not (
            self.opening_consumed_at_utc
            < self.execution_completed_at_utc
            < self.gate_b_scored_at_utc
        ):
            raise ValueError("sealed Gate-B lifecycle timestamps are not strictly increasing")
        return self


def _score_role_payload(record: SealedGateBScoreV09) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "enrollment_authority_attestation",
            }
        ),
    )


def _score_authority_payload(record: SealedGateBScoreV09) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"enrollment_authority_attestation"}))


def prepare_sealed_gate_b_score_v0_9(
    *,
    canonical_execution_payload: Mapping[str, Any],
    verified_canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    trusted_canonical_executor: Ed25519AttestationVerifier,
    opening: SealedGateBOpeningV09,
    consumption_head: OpeningConsumptionLedgerHeadV09,
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
    execution_ledger_sequence: int,
    gate_b_ledger_sequence: int,
    execution_completed_at_utc: datetime,
    gate_b_scored_at_utc: datetime,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> SealedGateBScoreV09:
    if (
        consumption_head.immutable_manifest_sha256 != opening.immutable_manifest_sha256
        or consumption_head.producer_run_id != opening.producer_run_id
        or consumption_head.opening_attempt_id != opening.opening_attempt_id
    ):
        raise ValueError("consumption head and sealed opening are cross-run")
    artifact, artifact_hash = _verified_canonical_execution(
        canonical_execution_payload,
        verified_artifact=verified_canonical_execution,
        trusted_executor=trusted_canonical_executor,
        expected_manifest_sha256=opening.immutable_manifest_sha256,
        expected_producer_run_id=opening.producer_run_id,
        expected_gate_a_content_sha256=opening.gate_a_report_content_sha256,
        expected_opening_content_sha256=consumption_head.opening_content_sha256,
        expected_opening_attempt_id=opening.opening_attempt_id,
    )
    traces = derive_stratified_traces_from_canonical_execution_v0_9(artifact)
    result = run_stratified_gate_b(
        traces,
        expected_arms=EXPECTED_ARMS,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
    )
    result_hash = result.get("content_sha256")
    if not _is_sha256(result_hash):
        raise ValueError("canonical Gate-B scorer omitted its content hash")
    isolation_hashes = tuple(
        bound.isolation.isolation_receipt_content_sha256 for bound in artifact.task_receipts
    )
    return SealedGateBScoreV09(
        immutable_manifest_sha256=opening.immutable_manifest_sha256,
        producer_run_id=opening.producer_run_id,
        gate_a_report_content_sha256=opening.gate_a_report_content_sha256,
        sealed_opening_content_sha256=consumption_head.opening_content_sha256,
        opening_attempt_id=opening.opening_attempt_id,
        opening_consumption_head_sha256=consumption_head.head_sha256,
        consumption_ledger_sequence=consumption_head.ledger_sequence,
        canonical_execution_content_sha256=artifact_hash,
        canonical_execution_id=artifact.execution_id,
        episode_ids=artifact.episode_ids,
        isolation_receipt_content_sha256=isolation_hashes,
        comparison_protocol_content_sha256=content_sha256(
            _comparison_protocol_payload(comparison_pairs, mechanism_requirements)
        ),
        gate_b_result=result,
        gate_b_result_content_sha256=result_hash,
        gate_b_passed=bool(result["gate_b_passed"]),
        execution_ledger_sequence=execution_ledger_sequence,
        gate_b_ledger_sequence=gate_b_ledger_sequence,
        opening_consumed_at_utc=consumption_head.consumed_at_utc,
        execution_completed_at_utc=execution_completed_at_utc,
        gate_b_scored_at_utc=gate_b_scored_at_utc,
        signing_keys=_signing_keys(
            reviewer=reviewer,
            executor=executor,
            custodian=custodian,
            enrollment_authority=enrollment_authority,
        ),
    )


def sealed_gate_b_score_role_signing_requests_v0_9(
    prepared: SealedGateBScoreV09,
) -> dict[str, DetachedSigningRequestV09]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("sealed Gate-B role signing requires a wholly unsigned record")
    payload = _score_role_payload(prepared)
    return {
        "reviewer": _detached_request(
            artifact_protocol=prepared.protocol,
            role="reviewer",
            domain=SEALED_SCORE_REVIEWER_DOMAIN,
            binding=prepared.signing_keys.reviewer,
            payload=payload,
        ),
        "executor": _detached_request(
            artifact_protocol=prepared.protocol,
            role="executor",
            domain=SEALED_SCORE_EXECUTOR_DOMAIN,
            binding=prepared.signing_keys.executor,
            payload=payload,
        ),
        "custodian": _detached_request(
            artifact_protocol=prepared.protocol,
            role="custodian",
            domain=SEALED_SCORE_CUSTODIAN_DOMAIN,
            binding=prepared.signing_keys.custodian,
            payload=payload,
        ),
    }


def sealed_gate_b_score_authority_signing_request_v0_9(
    prepared: SealedGateBScoreV09,
    *,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
) -> DetachedSigningRequestV09:
    role_payload = _score_role_payload(prepared)
    _verifier(prepared.signing_keys.reviewer).verify(
        SEALED_SCORE_REVIEWER_DOMAIN,
        role_payload,
        reviewer_attestation,
    )
    _verifier(prepared.signing_keys.executor).verify(
        SEALED_SCORE_EXECUTOR_DOMAIN,
        role_payload,
        executor_attestation,
    )
    _verifier(prepared.signing_keys.custodian).verify(
        SEALED_SCORE_CUSTODIAN_DOMAIN,
        role_payload,
        custodian_attestation,
    )
    role_signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    return _detached_request(
        artifact_protocol=prepared.protocol,
        role="enrollment_authority",
        domain=SEALED_SCORE_AUTHORITY_DOMAIN,
        binding=prepared.signing_keys.enrollment_authority,
        payload=_score_authority_payload(role_signed),
    )


def finalize_sealed_gate_b_score_v0_9(
    prepared: SealedGateBScoreV09,
    *,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
    enrollment_authority_attestation: Attestation | None,
    canonical_execution_payload: Mapping[str, Any],
    verified_canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    opening: SealedGateBOpeningV09,
    consumption_head: OpeningConsumptionLedgerHeadV09,
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
) -> dict[str, Any]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("sealed Gate-B finalization requires the prepared unsigned record")
    signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
            "enrollment_authority_attestation": enrollment_authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_sealed_gate_b_score_v0_9(
        payload,
        canonical_execution_payload=canonical_execution_payload,
        verified_canonical_execution=verified_canonical_execution,
        trusted_canonical_executor=trusted_executor,
        opening=opening,
        consumption_head=consumption_head,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
        trusted_reviewer=trusted_reviewer,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return payload


def make_sealed_gate_b_score_v0_9(
    *,
    canonical_execution_payload: Mapping[str, Any],
    verified_canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    opening: SealedGateBOpeningV09,
    consumption_head: OpeningConsumptionLedgerHeadV09,
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
    execution_ledger_sequence: int,
    gate_b_ledger_sequence: int,
    execution_completed_at_utc: datetime,
    gate_b_scored_at_utc: datetime,
    reviewer: Ed25519AttestationSigner,
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    prepared = prepare_sealed_gate_b_score_v0_9(
        canonical_execution_payload=canonical_execution_payload,
        verified_canonical_execution=verified_canonical_execution,
        trusted_canonical_executor=executor.verifier(),
        opening=opening,
        consumption_head=consumption_head,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
        execution_ledger_sequence=execution_ledger_sequence,
        gate_b_ledger_sequence=gate_b_ledger_sequence,
        execution_completed_at_utc=execution_completed_at_utc,
        gate_b_scored_at_utc=gate_b_scored_at_utc,
        reviewer=reviewer.verifier(),
        executor=executor.verifier(),
        custodian=custodian.verifier(),
        enrollment_authority=enrollment_authority.verifier(),
    )
    requests = sealed_gate_b_score_role_signing_requests_v0_9(prepared)
    reviewer_attestation = sign_detached_request_v0_9(requests["reviewer"], signer=reviewer)
    executor_attestation = sign_detached_request_v0_9(requests["executor"], signer=executor)
    custodian_attestation = sign_detached_request_v0_9(requests["custodian"], signer=custodian)
    authority_request = sealed_gate_b_score_authority_signing_request_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
    )
    return finalize_sealed_gate_b_score_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
        enrollment_authority_attestation=sign_detached_request_v0_9(
            authority_request,
            signer=enrollment_authority,
        ),
        canonical_execution_payload=canonical_execution_payload,
        verified_canonical_execution=verified_canonical_execution,
        trusted_reviewer=reviewer.verifier(),
        trusted_executor=executor.verifier(),
        trusted_custodian=custodian.verifier(),
        trusted_enrollment_authority=enrollment_authority.verifier(),
        opening=opening,
        consumption_head=consumption_head,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
    )


def verify_sealed_gate_b_score_v0_9(
    payload: Mapping[str, Any],
    *,
    canonical_execution_payload: Mapping[str, Any],
    verified_canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    trusted_canonical_executor: Ed25519AttestationVerifier,
    opening: SealedGateBOpeningV09,
    consumption_head: OpeningConsumptionLedgerHeadV09,
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> SealedGateBScoreV09:
    raw_record, _ = _content_bound_record(
        payload,
        SealedGateBScoreV09,
        label="sealed Gate-B score",
    )
    record = SealedGateBScoreV09.model_validate(raw_record)
    artifact, artifact_hash = _verified_canonical_execution(
        canonical_execution_payload,
        verified_artifact=verified_canonical_execution,
        trusted_executor=trusted_canonical_executor,
        expected_manifest_sha256=opening.immutable_manifest_sha256,
        expected_producer_run_id=opening.producer_run_id,
        expected_gate_a_content_sha256=opening.gate_a_report_content_sha256,
        expected_opening_content_sha256=consumption_head.opening_content_sha256,
        expected_opening_attempt_id=opening.opening_attempt_id,
    )
    traces = derive_stratified_traces_from_canonical_execution_v0_9(artifact)
    expected_result = run_stratified_gate_b(
        traces,
        expected_arms=EXPECTED_ARMS,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
    )
    expected = {
        "immutable_manifest_sha256": opening.immutable_manifest_sha256,
        "producer_run_id": opening.producer_run_id,
        "gate_a_report_content_sha256": opening.gate_a_report_content_sha256,
        "sealed_opening_content_sha256": consumption_head.opening_content_sha256,
        "opening_attempt_id": opening.opening_attempt_id,
        "opening_consumption_head_sha256": consumption_head.head_sha256,
        "consumption_ledger_sequence": consumption_head.ledger_sequence,
        "canonical_execution_content_sha256": artifact_hash,
        "canonical_execution_id": artifact.execution_id,
        "episode_ids": artifact.episode_ids,
        "isolation_receipt_content_sha256": tuple(
            bound.isolation.isolation_receipt_content_sha256 for bound in artifact.task_receipts
        ),
        "comparison_protocol_content_sha256": content_sha256(
            _comparison_protocol_payload(comparison_pairs, mechanism_requirements)
        ),
        "gate_b_result": expected_result,
        "gate_b_result_content_sha256": expected_result["content_sha256"],
        "gate_b_passed": bool(expected_result["gate_b_passed"]),
        "opening_consumed_at_utc": consumption_head.consumed_at_utc,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("sealed Gate-B score differs from canonical execution evidence")
    for binding, verifier in (
        (record.signing_keys.reviewer, trusted_reviewer),
        (record.signing_keys.executor, trusted_executor),
        (record.signing_keys.custodian, trusted_custodian),
        (record.signing_keys.enrollment_authority, trusted_enrollment_authority),
    ):
        _assert_verifier(binding, verifier)
    role_payload = _score_role_payload(record)
    trusted_reviewer.verify(
        SEALED_SCORE_REVIEWER_DOMAIN,
        role_payload,
        record.reviewer_attestation,
    )
    trusted_executor.verify(
        SEALED_SCORE_EXECUTOR_DOMAIN,
        role_payload,
        record.executor_attestation,
    )
    trusted_custodian.verify(
        SEALED_SCORE_CUSTODIAN_DOMAIN,
        role_payload,
        record.custodian_attestation,
    )
    trusted_enrollment_authority.verify(
        SEALED_SCORE_AUTHORITY_DOMAIN,
        _score_authority_payload(record),
        record.enrollment_authority_attestation,
    )
    return record


class IndependentVerifierIdentityV09(ContractModel):
    protocol: Literal["structure-two-independent-verifier-identity@0.9"] = (
        "structure-two-independent-verifier-identity@0.9"
    )
    verifier_identifier: str = Field(min_length=1)
    implementation_executor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        _validate_identifier(self.verifier_identifier, label="verifier identifier")
        return self


class IsolationReceiptArtifactBindingV09(ContractModel):
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    formal_isolation_verified: Literal[True]


class FidelityArtifactSnapshotV09(ContractModel):
    """Live hashes for every raw report, method artifact, and isolation receipt."""

    protocol: Literal["structure-two-six-method-fidelity-snapshot@0.9"] = (
        "structure-two-six-method-fidelity-snapshot@0.9"
    )
    raw_fidelity_report_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_fidelity_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_evidence_artifact_sha256_by_arm: dict[str, str]
    isolation_receipts_by_arm: dict[str, tuple[IsolationReceiptArtifactBindingV09, ...]]

    @model_validator(mode="after")
    def validate_exact_catalog(self) -> Self:
        if tuple(self.method_evidence_artifact_sha256_by_arm) != EXTERNAL_METHOD_ARMS:
            raise ValueError("fidelity snapshot lacks the ordered canonical six-method catalog")
        if tuple(self.isolation_receipts_by_arm) != EXTERNAL_METHOD_ARMS:
            raise ValueError("fidelity snapshot lacks isolation evidence for all six methods")
        if any(
            not _is_sha256(value) for value in self.method_evidence_artifact_sha256_by_arm.values()
        ):
            raise ValueError("fidelity snapshot contains malformed method-evidence hashes")
        if len(set(self.method_evidence_artifact_sha256_by_arm.values())) != len(
            EXTERNAL_METHOD_ARMS
        ):
            raise ValueError("one method-evidence artifact cannot be reused across methods")
        for arm, receipts in self.isolation_receipts_by_arm.items():
            if not receipts:
                raise ValueError(f"fidelity snapshot has no isolation receipts for {arm}")
            if len({row.artifact_sha256 for row in receipts}) != len(receipts):
                raise ValueError(f"fidelity snapshot duplicates isolation receipts for {arm}")
        all_receipt_hashes = tuple(
            receipt.artifact_sha256
            for arm in EXTERNAL_METHOD_ARMS
            for receipt in self.isolation_receipts_by_arm[arm]
        )
        if len(set(all_receipt_hashes)) != len(all_receipt_hashes):
            raise ValueError("one isolation receipt cannot be reused across fidelity methods")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


@dataclass(frozen=True, slots=True)
class FidelityIsolationReceiptVerificationV09:
    receipt_path: Path
    trusted_executor: Ed25519AttestationVerifier
    command_engine_path: Path
    arguments: Sequence[str]
    code_bundle_path: Path
    input_artifact_paths: Mapping[str, Path]
    working_directory: Path
    expected_output_relative_paths: Mapping[str, str | Path]
    timeout_seconds: int
    resource_limits: IsolationResourceLimitsV09 = DEFAULT_RESOURCE_LIMITS


@dataclass(frozen=True, slots=True)
class FidelityArtifactPathsV09:
    raw_fidelity_report: Path
    method_evidence_artifacts_by_arm: Mapping[str, Path]
    isolation_receipt_verifications_by_arm: Mapping[
        str,
        Sequence[FidelityIsolationReceiptVerificationV09],
    ]


def _stable_json_envelope(path: Path, *, label: str) -> tuple[dict[str, Any], str, str]:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a real file")
    before = resolved.stat()
    raw = resolved.read_bytes()
    after = resolved.stat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        stat.S_IMODE(before.st_mode),
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        stat.S_IMODE(after.st_mode),
    )
    if before_identity != after_identity:
        raise ValueError(f"{label} changed while it was read")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    unsigned = dict(parsed)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"{label} content hash mismatch")
    return parsed, hashlib.sha256(raw).hexdigest(), stored


def snapshot_fidelity_artifacts_v0_9(
    paths: FidelityArtifactPathsV09,
) -> FidelityArtifactSnapshotV09:
    """Snapshot raw evidence twice-safe enough to detect in-call substitution."""

    if tuple(paths.method_evidence_artifacts_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("method evidence paths lack the ordered canonical six arms")
    if tuple(paths.isolation_receipt_verifications_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("isolation evidence paths lack the ordered canonical six arms")
    _, raw_artifact_hash, raw_content_hash = _stable_json_envelope(
        paths.raw_fidelity_report,
        label="raw fidelity report",
    )
    method_hashes: dict[str, str] = {}
    isolation_rows: dict[str, tuple[IsolationReceiptArtifactBindingV09, ...]] = {}
    for arm in EXTERNAL_METHOD_ARMS:
        method_path = paths.method_evidence_artifacts_by_arm[arm]
        first = external_artifact_sha256(method_path)
        second = external_artifact_sha256(method_path)
        if first != second:
            raise ValueError(f"method evidence for {arm} changed while it was hashed")
        method_hashes[arm] = first
        arm_receipts: list[IsolationReceiptArtifactBindingV09] = []
        for index, verification in enumerate(paths.isolation_receipt_verifications_by_arm[arm]):
            raw, artifact_hash, receipt_hash = _stable_json_envelope(
                verification.receipt_path,
                label=f"{arm} isolation receipt {index}",
            )
            receipt = verify_isolation_receipt_v0_9(
                raw,
                trusted_executor=verification.trusted_executor,
                command_engine_path=verification.command_engine_path,
                arguments=verification.arguments,
                code_bundle_path=verification.code_bundle_path,
                input_artifact_paths=verification.input_artifact_paths,
                working_directory=verification.working_directory,
                expected_output_relative_paths=(verification.expected_output_relative_paths),
                timeout_seconds=verification.timeout_seconds,
                resource_limits=verification.resource_limits,
            )
            if (
                receipt.formal_isolation_verified is not True
                or receipt.status != "ISOLATION_PASSED"
            ):
                raise ValueError(f"{arm} has a failed or nonformal isolation receipt")
            context_hash = content_sha256(
                {
                    "trusted_executor_key_id": verification.trusted_executor.key_id,
                    "trusted_executor_public_key_sha256": (
                        verification.trusted_executor.public_key_sha256
                    ),
                    "command_engine_path": str(
                        verification.command_engine_path.resolve(strict=True)
                    ),
                    "arguments": tuple(str(item) for item in verification.arguments),
                    "code_bundle_path": str(verification.code_bundle_path.resolve(strict=True)),
                    "input_artifact_paths": {
                        label: str(path.resolve(strict=True))
                        for label, path in sorted(verification.input_artifact_paths.items())
                    },
                    "working_directory": str(verification.working_directory.resolve(strict=True)),
                    "expected_output_relative_paths": {
                        label: Path(relative).as_posix()
                        for label, relative in sorted(
                            verification.expected_output_relative_paths.items()
                        )
                    },
                    "timeout_seconds": verification.timeout_seconds,
                    "resource_limits": verification.resource_limits.model_dump(mode="json"),
                }
            )
            arm_receipts.append(
                IsolationReceiptArtifactBindingV09(
                    artifact_sha256=artifact_hash,
                    content_sha256=receipt_hash,
                    executor_public_key_sha256=receipt.executor_public_key_sha256,
                    policy_template_sha256=receipt.policy_template_sha256,
                    rendered_profile_sha256=receipt.rendered_profile_sha256,
                    verification_context_sha256=context_hash,
                    formal_isolation_verified=True,
                )
            )
        isolation_rows[arm] = tuple(arm_receipts)
    return FidelityArtifactSnapshotV09(
        raw_fidelity_report_artifact_sha256=raw_artifact_hash,
        raw_fidelity_report_content_sha256=raw_content_hash,
        method_evidence_artifact_sha256_by_arm=method_hashes,
        isolation_receipts_by_arm=isolation_rows,
    )


class VerifiedMethodFidelityV09(ContractModel):
    arm: str = Field(min_length=1)
    method: str = Field(min_length=1)
    primary_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_evidence_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    isolation_receipts: tuple[IsolationReceiptArtifactBindingV09, ...] = Field(min_length=1)
    native_reproduction_verified: Literal[True]
    native_protocol_recheck_verified: Literal[True]
    cross_domain_adaptation_verified: Literal[True]
    adaptation_parity_recheck_verified: Literal[True]
    isolation_receipts_semantically_verified: Literal[True]


class VerifiedSixMethodFidelityV09(ContractModel):
    protocol: Literal["structure-two-verified-six-method-fidelity@0.9"] = (
        "structure-two-verified-six-method-fidelity@0.9"
    )
    status: Literal["SIX_NATIVE_AND_ADAPTATION_REPRODUCTIONS_VERIFIED"] = (
        "SIX_NATIVE_AND_ADAPTATION_REPRODUCTIONS_VERIFIED"
    )
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    artifact_snapshot: FidelityArtifactSnapshotV09
    method_results: tuple[VerifiedMethodFidelityV09, ...]
    verifier_identity: IndependentVerifierIdentityV09
    verifier_reexecuted_raw_evidence: Literal[True]
    verified_at_utc: datetime
    reviewer_key: PublicKeyBindingV09
    reviewer_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_fidelity(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_utc(self.verified_at_utc, label="fidelity verification")
        if tuple(row.arm for row in self.method_results) != EXTERNAL_METHOD_ARMS:
            raise ValueError("fidelity evidence lacks the ordered canonical six methods")
        expected_methods = tuple(EXTERNAL_METHOD_NAMES[arm] for arm in EXTERNAL_METHOD_ARMS)
        if tuple(row.method for row in self.method_results) != expected_methods:
            raise ValueError("fidelity evidence changed a canonical method identity")
        for row in self.method_results:
            if (
                row.method_evidence_artifact_sha256
                != self.artifact_snapshot.method_evidence_artifact_sha256_by_arm[row.arm]
                or row.isolation_receipts
                != self.artifact_snapshot.isolation_receipts_by_arm[row.arm]
            ):
                raise ValueError("fidelity decision is detached from its raw artifacts")
        return self


def _fidelity_attested_payload(record: VerifiedSixMethodFidelityV09) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"reviewer_attestation"}))


def prepare_verified_six_method_fidelity_v0_9(
    *,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    artifact_snapshot: FidelityArtifactSnapshotV09,
    method_results: Sequence[VerifiedMethodFidelityV09],
    verifier_identity: IndependentVerifierIdentityV09,
    verified_at_utc: datetime,
    reviewer: Ed25519AttestationVerifier,
) -> VerifiedSixMethodFidelityV09:
    return VerifiedSixMethodFidelityV09(
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        artifact_snapshot=artifact_snapshot,
        method_results=tuple(method_results),
        verifier_identity=verifier_identity,
        verifier_reexecuted_raw_evidence=True,
        verified_at_utc=verified_at_utc,
        reviewer_key=_key_binding(reviewer),
    )


def verified_six_method_fidelity_signing_request_v0_9(
    prepared: VerifiedSixMethodFidelityV09,
) -> DetachedSigningRequestV09:
    if prepared.reviewer_attestation is not None:
        raise ValueError("fidelity signing request requires an unsigned record")
    return _detached_request(
        artifact_protocol=prepared.protocol,
        role="reviewer",
        domain=FIDELITY_REVIEWER_DOMAIN,
        binding=prepared.reviewer_key,
        payload=_fidelity_attested_payload(prepared),
    )


def finalize_verified_six_method_fidelity_v0_9(
    prepared: VerifiedSixMethodFidelityV09,
    *,
    reviewer_attestation: Attestation | None,
    expected_snapshot: FidelityArtifactSnapshotV09,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_implementation_bundle_sha256_by_arm: Mapping[str, str],
    expected_primary_source_sha256_by_arm: Mapping[str, str],
    expected_verifier_identity: IndependentVerifierIdentityV09,
    trusted_reviewer: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    if prepared.reviewer_attestation is not None:
        raise ValueError("fidelity finalization requires the prepared unsigned record")
    signed = prepared.model_copy(update={"reviewer_attestation": reviewer_attestation})
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_verified_six_method_fidelity_v0_9(
        payload,
        expected_snapshot=expected_snapshot,
        expected_immutable_manifest_sha256=expected_immutable_manifest_sha256,
        expected_producer_run_id=expected_producer_run_id,
        expected_implementation_bundle_sha256_by_arm=(expected_implementation_bundle_sha256_by_arm),
        expected_primary_source_sha256_by_arm=expected_primary_source_sha256_by_arm,
        expected_verifier_identity=expected_verifier_identity,
        trusted_reviewer=trusted_reviewer,
    )
    return payload


def make_verified_six_method_fidelity_v0_9(
    *,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    artifact_snapshot: FidelityArtifactSnapshotV09,
    method_results: Sequence[VerifiedMethodFidelityV09],
    verifier_identity: IndependentVerifierIdentityV09,
    verified_at_utc: datetime,
    reviewer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    prepared = prepare_verified_six_method_fidelity_v0_9(
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        artifact_snapshot=artifact_snapshot,
        method_results=method_results,
        verifier_identity=verifier_identity,
        verified_at_utc=verified_at_utc,
        reviewer=reviewer.verifier(),
    )
    request = verified_six_method_fidelity_signing_request_v0_9(prepared)
    expected_bundles = {row.arm: row.implementation_bundle_sha256 for row in method_results}
    expected_sources = {row.arm: row.primary_source_sha256 for row in method_results}
    return finalize_verified_six_method_fidelity_v0_9(
        prepared,
        reviewer_attestation=sign_detached_request_v0_9(request, signer=reviewer),
        expected_snapshot=artifact_snapshot,
        expected_immutable_manifest_sha256=immutable_manifest_sha256,
        expected_producer_run_id=producer_run_id,
        expected_implementation_bundle_sha256_by_arm=expected_bundles,
        expected_primary_source_sha256_by_arm=expected_sources,
        expected_verifier_identity=verifier_identity,
        trusted_reviewer=reviewer.verifier(),
    )


def verify_verified_six_method_fidelity_v0_9(
    payload: Mapping[str, Any],
    *,
    expected_snapshot: FidelityArtifactSnapshotV09,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_implementation_bundle_sha256_by_arm: Mapping[str, str],
    expected_primary_source_sha256_by_arm: Mapping[str, str],
    expected_verifier_identity: IndependentVerifierIdentityV09,
    trusted_reviewer: Ed25519AttestationVerifier,
) -> VerifiedSixMethodFidelityV09:
    raw_record, _ = _content_bound_record(
        payload,
        VerifiedSixMethodFidelityV09,
        label="verified six-method fidelity evidence",
    )
    record = VerifiedSixMethodFidelityV09.model_validate(raw_record)
    if tuple(expected_implementation_bundle_sha256_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("expected fidelity implementation set is not the canonical six")
    if tuple(expected_primary_source_sha256_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("expected fidelity source set is not the canonical six")
    if (
        record.immutable_manifest_sha256 != expected_immutable_manifest_sha256
        or record.producer_run_id != expected_producer_run_id
        or record.artifact_snapshot != expected_snapshot
        or record.verifier_identity != expected_verifier_identity
    ):
        raise ValueError("fidelity evidence is stale, substituted, or cross-run")
    for row in record.method_results:
        if (
            row.implementation_bundle_sha256
            != expected_implementation_bundle_sha256_by_arm[row.arm]
            or row.primary_source_sha256 != expected_primary_source_sha256_by_arm[row.arm]
        ):
            raise ValueError("fidelity result differs from the frozen implementation/source set")
    _assert_verifier(record.reviewer_key, trusted_reviewer)
    trusted_reviewer.verify(
        FIDELITY_REVIEWER_DOMAIN,
        _fidelity_attested_payload(record),
        record.reviewer_attestation,
    )
    return record


class TrustedSixMethodFidelityVerifierV09(Protocol):
    """Trusted adapter which must re-run native, adaptation, and isolation checks."""

    @property
    def identity(self) -> IndependentVerifierIdentityV09: ...

    def verify(
        self,
        *,
        artifact_paths: FidelityArtifactPathsV09,
        artifact_snapshot: FidelityArtifactSnapshotV09,
        expected_immutable_manifest_sha256: str,
        expected_producer_run_id: str,
        expected_implementation_bundle_sha256_by_arm: Mapping[str, str],
        expected_primary_source_sha256_by_arm: Mapping[str, str],
        trusted_reviewer: Ed25519AttestationVerifier,
    ) -> Mapping[str, Any]: ...


def run_trusted_six_method_fidelity_verifier_v0_9(
    *,
    verifier: TrustedSixMethodFidelityVerifierV09,
    expected_verifier_identity: IndependentVerifierIdentityV09,
    artifact_paths: FidelityArtifactPathsV09,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_implementation_bundle_sha256_by_arm: Mapping[str, str],
    expected_primary_source_sha256_by_arm: Mapping[str, str],
    trusted_reviewer: Ed25519AttestationVerifier,
) -> tuple[VerifiedSixMethodFidelityV09, str]:
    if verifier.identity != expected_verifier_identity:
        raise AttestationError("fidelity verifier identity is not the enrolled implementation")
    before = snapshot_fidelity_artifacts_v0_9(artifact_paths)
    payload = verifier.verify(
        artifact_paths=artifact_paths,
        artifact_snapshot=before,
        expected_immutable_manifest_sha256=expected_immutable_manifest_sha256,
        expected_producer_run_id=expected_producer_run_id,
        expected_implementation_bundle_sha256_by_arm=(expected_implementation_bundle_sha256_by_arm),
        expected_primary_source_sha256_by_arm=expected_primary_source_sha256_by_arm,
        trusted_reviewer=trusted_reviewer,
    )
    after = snapshot_fidelity_artifacts_v0_9(artifact_paths)
    if after != before:
        raise ValueError("fidelity evidence changed during trusted verification (TOCTOU)")
    record = verify_verified_six_method_fidelity_v0_9(
        payload,
        expected_snapshot=before,
        expected_immutable_manifest_sha256=expected_immutable_manifest_sha256,
        expected_producer_run_id=expected_producer_run_id,
        expected_implementation_bundle_sha256_by_arm=(expected_implementation_bundle_sha256_by_arm),
        expected_primary_source_sha256_by_arm=expected_primary_source_sha256_by_arm,
        expected_verifier_identity=expected_verifier_identity,
        trusted_reviewer=trusted_reviewer,
    )
    stored = payload.get("content_sha256")
    if not _is_sha256(stored):
        raise ValueError("trusted fidelity verifier returned an unbound record")
    assert isinstance(stored, str)
    return record, stored


class TrustedCanonicalExecutionVerifierV09(Protocol):
    """Closure around the full canonical executor verifier and its live paths."""

    @property
    def identity(self) -> IndependentVerifierIdentityV09: ...

    def verify(
        self,
        payload: Mapping[str, Any],
    ) -> CanonicalPerEpisodeExecutionArtifactV09: ...


@dataclass(frozen=True, slots=True)
class VerifiedExternalConfirmationChainV09:
    registry: TrustAnchorRegistryV06
    role_verifiers: Mapping[str, Ed25519AttestationVerifier]
    frozen_manifest: FrozenGateBManifestV06
    gate_a_report_content_sha256: str
    verified_commitment: VerifiedSealedGateBCommitmentV09
    verified_gate_a_lifecycle: VerifiedGateALifecycleCompletionV09
    opening_context: SealedGateBOpeningVerificationContextV09
    opening: SealedGateBOpeningV09
    opening_content_sha256: str
    authoritative_ledger_store_identity: AuthoritativeLedgerStoreIdentityV09
    consumption_head: OpeningConsumptionLedgerHeadV09
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09
    canonical_execution_content_sha256: str
    sealed_gate_b_score: SealedGateBScoreV09
    sealed_gate_b_score_content_sha256: str
    fidelity: VerifiedSixMethodFidelityV09
    fidelity_content_sha256: str
    canonical_verifier_identity: IndependentVerifierIdentityV09
    fidelity_verifier_identity: IndependentVerifierIdentityV09
    trust_anchor_registry_content_sha256: str
    frozen_manifest_content_sha256: str
    gate_a_lifecycle_content_sha256: str


class ExternalConfirmationBlockerReportV09(ContractModel):
    protocol: Literal["structure-two-external-confirmation-blocker@0.9"] = (
        "structure-two-external-confirmation-blocker@0.9"
    )
    status: Literal["BLOCKED_FAIL_CLOSED"] = "BLOCKED_FAIL_CLOSED"
    stage: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    external_method_efficacy_comparison_allowed: Literal[False] = False


class ExternalConfirmationBlockedError(ValueError):
    """Raised with a machine-readable false authorization decision."""

    def __init__(self, *, stage: str, reason: str) -> None:
        self.report = ExternalConfirmationBlockerReportV09(stage=stage, reason=reason)
        super().__init__(f"{stage}: {reason}")


def _payload_content_hash(payload: Mapping[str, Any], *, label: str) -> str:
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"{label} content hash mismatch")
    return stored


def _primary_source_hashes(source_register: Mapping[str, Any]) -> dict[str, str]:
    rows = source_register.get("methods")
    if not isinstance(rows, list):
        raise ValueError("source register lacks method rows")
    by_arm = {
        str(row.get("arm")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("arm"), str)
    }
    if set(by_arm) != set(EXTERNAL_METHOD_ARMS) or len(by_arm) != len(EXTERNAL_METHOD_ARMS):
        raise ValueError("source register does not contain the exact canonical six methods")
    result: dict[str, str] = {}
    for specification in EXTERNAL_METHOD_SPECIFICATIONS:
        row = by_arm[specification.arm]
        digest = row.get("primary_source_sha256")
        if (
            row.get("method") != specification.method
            or row.get("primary_source_url") != specification.primary_source_url
            or not _is_sha256(digest)
        ):
            raise ValueError("source register method identity or primary-source hash is invalid")
        result[specification.arm] = str(digest)
    return result


def validate_fidelity_freeze_commitment_sequence_v0_9(
    *,
    frozen_at_utc: datetime,
    fidelity_verified_at_utc: datetime,
    sealed_commitment_at_utc: datetime,
) -> None:
    """Prevent a post-Gate-A fidelity record from completing a forged chain."""

    for label, value in (
        ("external freeze", frozen_at_utc),
        ("six-method fidelity verification", fidelity_verified_at_utc),
        ("sealed Gate-B commitment", sealed_commitment_at_utc),
    ):
        _validate_utc(value, label=label)
    if not frozen_at_utc < fidelity_verified_at_utc < sealed_commitment_at_utc:
        raise ValueError(
            "six-method fidelity must be verified after the implementation freeze and "
            "before the sealed Gate-B commitment/Gate A lifecycle"
        )


def _verify_external_confirmation_chain_impl_v0_9(
    *,
    canonical_gate_b_draft: Mapping[str, Any],
    gate_a_spec: Mapping[str, Any],
    externally_frozen_manifest: Mapping[str, Any],
    source_register: Mapping[str, Any],
    trust_anchor_registry: Mapping[str, Any],
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
    gate_a_report: Mapping[str, Any],
    gate_a_artifact_paths: GateAArtifactPathsV06,
    producer_source_bundle_sha256: str,
    expected_arm_implementation_bundles: Mapping[str, str],
    sealed_commitment_payload: Mapping[str, Any],
    gate_a_lifecycle_payload: Mapping[str, Any],
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    sealed_opening_payload: Mapping[str, Any],
    opening_consumption_payload: Mapping[str, Any],
    opening_consumption_store: AuthoritativeOpeningConsumptionStoreV09,
    expected_opening_consumption_store_identity: AuthoritativeLedgerStoreIdentityV09,
    canonical_execution_payload: Mapping[str, Any],
    canonical_execution_verifier: TrustedCanonicalExecutionVerifierV09,
    expected_canonical_verifier_identity: IndependentVerifierIdentityV09,
    sealed_gate_b_score_payload: Mapping[str, Any],
    fidelity_artifact_paths: FidelityArtifactPathsV09,
    fidelity_verifier: TrustedSixMethodFidelityVerifierV09,
    expected_fidelity_verifier_identity: IndependentVerifierIdentityV09,
) -> VerifiedExternalConfirmationChainV09:
    comparison_pairs, mechanism_requirements = validate_structure_two_gate_b_v0_6_draft(
        canonical_gate_b_draft
    )
    registry, role_verifiers = verify_trust_anchor_registry_v0_6(
        trust_anchor_registry,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    frozen_manifest = verify_frozen_gate_b_manifest_v0_6(
        externally_frozen_manifest,
        development_draft=canonical_gate_b_draft,
        source_register=source_register,
        gate_a_spec=gate_a_spec,
        trust_anchor_registry=registry,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=trusted_enrollment_authority,
    )
    if dict(expected_arm_implementation_bundles) != (
        frozen_manifest.arm_implementation_bundle_sha256
    ):
        raise ValueError("combined authorization implementation set differs from freeze")
    verify_gate_a_report_v0_6(
        gate_a_report,
        gate_a_spec=gate_a_spec,
        frozen_manifest=frozen_manifest,
        trust_anchor_registry=registry,
        artifact_paths=gate_a_artifact_paths,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        expected_arm_implementation_bundles=expected_arm_implementation_bundles,
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
    )
    gate_a_content_hash = _payload_content_hash(gate_a_report, label="Gate-A report")
    verified_commitment = verify_sealed_gate_b_commitment_record_v0_9(
        sealed_commitment_payload,
        expected_immutable_manifest_sha256=frozen_manifest.immutable_manifest_sha256,
        expected_producer_run_id=frozen_manifest.preregistered_producer_run_id,
        expected_arm_implementation_bundle_sha256=expected_arm_implementation_bundles,
        expected_ledger_identifier=frozen_manifest.freeze_ledger_identifier,
        expected_freeze_ledger_sequence=frozen_manifest.freeze_ledger_sequence,
        expected_freeze_completed_at_utc=frozen_manifest.frozen_at_utc,
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=trusted_enrollment_authority,
        verification_time_utc=verification_time_utc,
    )
    verified_gate_a_lifecycle = verify_gate_a_lifecycle_completion_record_v0_9(
        gate_a_lifecycle_payload,
        verified_commitment=verified_commitment,
        expected_verified_gate_a_report_content_sha256=gate_a_content_hash,
        expected_forbidden_seed_namespaces=forbidden_seed_namespaces,
        trusted_executor=role_verifiers["executor"],
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    preview_raw, opening_content_hash = _content_bound_record(
        sealed_opening_payload,
        SealedGateBOpeningV09,
        label="sealed Gate-B opening",
    )
    opening_preview = SealedGateBOpeningV09.model_validate(preview_raw)
    opening_context = build_sealed_gate_b_opening_context_v0_9(
        verified_commitment=verified_commitment,
        verified_gate_a_lifecycle=verified_gate_a_lifecycle,
        opening_ledger_sequence=opening_preview.opening_ledger_sequence,
        opened_at_utc=opening_preview.opened_at_utc,
    )
    opening = verify_sealed_gate_b_opening_v0_9(
        sealed_opening_payload,
        context=opening_context,
        trusted_custodian=role_verifiers["custodian"],
    )
    store_identity = opening_consumption_store.identity
    if store_identity != expected_opening_consumption_store_identity:
        raise ValueError("authoritative opening-consumption store identity is not trusted")
    if (
        store_identity.ledger_identifier != opening.ledger_identifier
        or store_identity.authority_identifier != trusted_enrollment_authority.key_id
    ):
        raise ValueError(
            "authoritative opening-consumption store is cross-ledger or cross-authority"
        )
    consumption_head = opening_consumption_store.read_verified_current_consumption_head(
        opening_consumption_payload,
        verification=OpeningConsumptionStoreVerificationContextV09(
            opening_payload=sealed_opening_payload,
            opening_context=opening_context,
            trusted_opening_custodian=role_verifiers["custodian"],
            trusted_reviewer=role_verifiers["reviewer"],
            trusted_executor=role_verifiers["executor"],
            trusted_consumption_custodian=role_verifiers["custodian"],
            trusted_enrollment_authority=trusted_enrollment_authority,
        ),
    )
    if canonical_execution_verifier.identity != expected_canonical_verifier_identity:
        raise AttestationError("canonical executor verifier identity is not trusted")
    canonical_execution = canonical_execution_verifier.verify(canonical_execution_payload)
    canonical_execution, canonical_content_hash = _verified_canonical_execution(
        canonical_execution_payload,
        verified_artifact=canonical_execution,
        trusted_executor=role_verifiers["executor"],
        expected_manifest_sha256=opening.immutable_manifest_sha256,
        expected_producer_run_id=opening.producer_run_id,
        expected_gate_a_content_sha256=gate_a_content_hash,
        expected_opening_content_sha256=opening_content_hash,
        expected_opening_attempt_id=opening.opening_attempt_id,
    )
    sealed_score = verify_sealed_gate_b_score_v0_9(
        sealed_gate_b_score_payload,
        canonical_execution_payload=canonical_execution_payload,
        verified_canonical_execution=canonical_execution,
        trusted_canonical_executor=role_verifiers["executor"],
        opening=opening,
        consumption_head=consumption_head,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
        trusted_reviewer=role_verifiers["reviewer"],
        trusted_executor=role_verifiers["executor"],
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    if sealed_score.gate_b_passed is not True:
        raise ValueError("failed sealed Gate B forbids combined authorization")
    source_hashes = _primary_source_hashes(source_register)
    fidelity, fidelity_content_hash = run_trusted_six_method_fidelity_verifier_v0_9(
        verifier=fidelity_verifier,
        expected_verifier_identity=expected_fidelity_verifier_identity,
        artifact_paths=fidelity_artifact_paths,
        expected_immutable_manifest_sha256=frozen_manifest.immutable_manifest_sha256,
        expected_producer_run_id=frozen_manifest.preregistered_producer_run_id,
        expected_implementation_bundle_sha256_by_arm={
            arm: expected_arm_implementation_bundles[arm] for arm in EXTERNAL_METHOD_ARMS
        },
        expected_primary_source_sha256_by_arm=source_hashes,
        trusted_reviewer=role_verifiers["reviewer"],
    )
    validate_fidelity_freeze_commitment_sequence_v0_9(
        frozen_at_utc=frozen_manifest.frozen_at_utc,
        fidelity_verified_at_utc=fidelity.verified_at_utc,
        sealed_commitment_at_utc=verified_commitment.record.committed_at_utc,
    )
    return VerifiedExternalConfirmationChainV09(
        registry=registry,
        role_verifiers=role_verifiers,
        frozen_manifest=frozen_manifest,
        gate_a_report_content_sha256=gate_a_content_hash,
        verified_commitment=verified_commitment,
        verified_gate_a_lifecycle=verified_gate_a_lifecycle,
        opening_context=opening_context,
        opening=opening,
        opening_content_sha256=opening_content_hash,
        authoritative_ledger_store_identity=store_identity,
        consumption_head=consumption_head,
        canonical_execution=canonical_execution,
        canonical_execution_content_sha256=canonical_content_hash,
        sealed_gate_b_score=sealed_score,
        sealed_gate_b_score_content_sha256=_payload_content_hash(
            sealed_gate_b_score_payload,
            label="sealed Gate-B score",
        ),
        fidelity=fidelity,
        fidelity_content_sha256=fidelity_content_hash,
        canonical_verifier_identity=expected_canonical_verifier_identity,
        fidelity_verifier_identity=expected_fidelity_verifier_identity,
        trust_anchor_registry_content_sha256=_payload_content_hash(
            trust_anchor_registry,
            label="trust-anchor registry",
        ),
        frozen_manifest_content_sha256=_payload_content_hash(
            externally_frozen_manifest,
            label="externally frozen manifest",
        ),
        gate_a_lifecycle_content_sha256=verified_gate_a_lifecycle.content_sha256,
    )


@dataclass(frozen=True, slots=True)
class ExternalConfirmationVerificationInputsV09:
    canonical_gate_b_draft: Mapping[str, Any]
    gate_a_spec: Mapping[str, Any]
    externally_frozen_manifest: Mapping[str, Any]
    source_register: Mapping[str, Any]
    trust_anchor_registry: Mapping[str, Any]
    trusted_enrollment_authority: Ed25519AttestationVerifier
    verification_time_utc: datetime
    gate_a_report: Mapping[str, Any]
    gate_a_artifact_paths: GateAArtifactPathsV06
    producer_source_bundle_sha256: str
    expected_arm_implementation_bundles: Mapping[str, str]
    sealed_commitment_payload: Mapping[str, Any]
    gate_a_lifecycle_payload: Mapping[str, Any]
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09
    sealed_opening_payload: Mapping[str, Any]
    opening_consumption_payload: Mapping[str, Any]
    opening_consumption_store: AuthoritativeOpeningConsumptionStoreV09
    expected_opening_consumption_store_identity: AuthoritativeLedgerStoreIdentityV09
    canonical_execution_payload: Mapping[str, Any]
    canonical_execution_verifier: TrustedCanonicalExecutionVerifierV09
    expected_canonical_verifier_identity: IndependentVerifierIdentityV09
    sealed_gate_b_score_payload: Mapping[str, Any]
    fidelity_artifact_paths: FidelityArtifactPathsV09
    fidelity_verifier: TrustedSixMethodFidelityVerifierV09
    expected_fidelity_verifier_identity: IndependentVerifierIdentityV09


def verify_external_confirmation_chain_v0_9(
    inputs: ExternalConfirmationVerificationInputsV09,
) -> VerifiedExternalConfirmationChainV09:
    """Re-verify every raw stage, or raise a blocker carrying ``allowed=False``."""

    # Fail before consulting any v0.6 score.  Without this state-machine guard,
    # a perfectly signed historical action-only chain could be mistaken for the
    # current dual-readout Gate B and regain generic authorization.
    raise ExternalConfirmationBlockedError(
        stage="gate_b_v0_7_receipt_required",
        reason=LEGACY_GATE_B_V0_6_SUPERSEDED_REASON,
    )

    # Historical verifier retained below for forensic replay only.  It is
    # intentionally unreachable from the public authorization API.
    try:
        return _verify_external_confirmation_chain_impl_v0_9(
            canonical_gate_b_draft=inputs.canonical_gate_b_draft,
            gate_a_spec=inputs.gate_a_spec,
            externally_frozen_manifest=inputs.externally_frozen_manifest,
            source_register=inputs.source_register,
            trust_anchor_registry=inputs.trust_anchor_registry,
            trusted_enrollment_authority=inputs.trusted_enrollment_authority,
            verification_time_utc=inputs.verification_time_utc,
            gate_a_report=inputs.gate_a_report,
            gate_a_artifact_paths=inputs.gate_a_artifact_paths,
            producer_source_bundle_sha256=inputs.producer_source_bundle_sha256,
            expected_arm_implementation_bundles=inputs.expected_arm_implementation_bundles,
            sealed_commitment_payload=inputs.sealed_commitment_payload,
            gate_a_lifecycle_payload=inputs.gate_a_lifecycle_payload,
            forbidden_seed_namespaces=inputs.forbidden_seed_namespaces,
            sealed_opening_payload=inputs.sealed_opening_payload,
            opening_consumption_payload=inputs.opening_consumption_payload,
            opening_consumption_store=inputs.opening_consumption_store,
            expected_opening_consumption_store_identity=(
                inputs.expected_opening_consumption_store_identity
            ),
            canonical_execution_payload=inputs.canonical_execution_payload,
            canonical_execution_verifier=inputs.canonical_execution_verifier,
            expected_canonical_verifier_identity=(inputs.expected_canonical_verifier_identity),
            sealed_gate_b_score_payload=inputs.sealed_gate_b_score_payload,
            fidelity_artifact_paths=inputs.fidelity_artifact_paths,
            fidelity_verifier=inputs.fidelity_verifier,
            expected_fidelity_verifier_identity=(inputs.expected_fidelity_verifier_identity),
        )
    except ExternalConfirmationBlockedError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttestationError) as exc:
        raise ExternalConfirmationBlockedError(
            stage="external_confirmation_prerequisites",
            reason=str(exc),
        ) from exc


class CombinedExternalConfirmationAuthorizationV09(ContractModel):
    protocol: Literal["structure-two-external-confirmation-authorization@0.9"] = (
        "structure-two-external-confirmation-authorization@0.9"
    )
    status: Literal["COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED"] = (
        "COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED"
    )
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    trust_anchor_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_manifest_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_commitment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_lifecycle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative_ledger_store_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_consumption_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_gate_b_score_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    six_method_fidelity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_verifier_identity: IndependentVerifierIdentityV09
    fidelity_verifier_identity: IndependentVerifierIdentityV09
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    gate_b_passed: Literal[True]
    six_native_reproductions_verified: Literal[True]
    six_adaptation_fidelity_checks_verified: Literal[True]
    real_isolation_evidence_verified: Literal[True]
    combined_authorization_ledger_sequence: StrictInt = Field(ge=0)
    sealed_gate_b_ledger_sequence: StrictInt = Field(ge=0)
    sealed_gate_b_scored_at_utc: datetime
    authorized_at_utc: datetime
    signing_keys: FourPartySigningKeysV09
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    enrollment_authority_attestation: Attestation | None = None
    external_method_efficacy_comparison_allowed: Literal[True] = True

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        if self.status == "COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED":
            raise ValueError(LEGACY_GATE_B_V0_6_SUPERSEDED_REASON)
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_utc(self.sealed_gate_b_scored_at_utc, label="sealed Gate-B score")
        _validate_utc(self.authorized_at_utc, label="combined authorization")
        if self.combined_authorization_ledger_sequence != self.sealed_gate_b_ledger_sequence + 1:
            raise ValueError("combined authorization must immediately follow sealed Gate B")
        if self.authorized_at_utc <= self.sealed_gate_b_scored_at_utc:
            raise ValueError("combined authorization timestamp must follow sealed Gate B")
        return self


def _combined_role_payload(
    record: CombinedExternalConfirmationAuthorizationV09,
) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "enrollment_authority_attestation",
            }
        ),
    )


def _combined_authority_payload(
    record: CombinedExternalConfirmationAuthorizationV09,
) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"enrollment_authority_attestation"}))


def _combined_expected_fields(chain: VerifiedExternalConfirmationChainV09) -> dict[str, Any]:
    return {
        "immutable_manifest_sha256": chain.frozen_manifest.immutable_manifest_sha256,
        "producer_run_id": chain.frozen_manifest.preregistered_producer_run_id,
        "trust_anchor_registry_content_sha256": (chain.trust_anchor_registry_content_sha256),
        "frozen_manifest_content_sha256": chain.frozen_manifest_content_sha256,
        "gate_a_report_content_sha256": chain.gate_a_report_content_sha256,
        "sealed_commitment_content_sha256": chain.verified_commitment.content_sha256,
        "gate_a_lifecycle_content_sha256": chain.gate_a_lifecycle_content_sha256,
        "sealed_opening_content_sha256": chain.opening_content_sha256,
        "authoritative_ledger_store_identity_sha256": (
            chain.authoritative_ledger_store_identity.content_sha256
        ),
        "opening_consumption_head_sha256": chain.consumption_head.head_sha256,
        "canonical_execution_content_sha256": (chain.canonical_execution_content_sha256),
        "sealed_gate_b_score_content_sha256": (chain.sealed_gate_b_score_content_sha256),
        "six_method_fidelity_content_sha256": chain.fidelity_content_sha256,
        "canonical_verifier_identity": chain.canonical_verifier_identity,
        "fidelity_verifier_identity": chain.fidelity_verifier_identity,
        "opening_attempt_id": chain.opening.opening_attempt_id,
        "sealed_gate_b_ledger_sequence": chain.sealed_gate_b_score.gate_b_ledger_sequence,
        "sealed_gate_b_scored_at_utc": chain.sealed_gate_b_score.gate_b_scored_at_utc,
    }


def prepare_combined_external_confirmation_authorization_v0_9(
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV09,
    combined_authorization_ledger_sequence: int,
    authorized_at_utc: datetime,
) -> tuple[
    CombinedExternalConfirmationAuthorizationV09,
    VerifiedExternalConfirmationChainV09,
]:
    """Reverify the full chain, then prepare (but do not sign) authorization."""

    chain = verify_external_confirmation_chain_v0_9(verification_inputs)
    if authorized_at_utc <= chain.fidelity.verified_at_utc:
        raise ExternalConfirmationBlockedError(
            stage="combined_authorization_sequence",
            reason="combined authorization predates or equals fidelity verification",
        )
    role_verifiers = chain.role_verifiers
    prepared = CombinedExternalConfirmationAuthorizationV09(
        **_combined_expected_fields(chain),
        gate_b_passed=True,
        six_native_reproductions_verified=True,
        six_adaptation_fidelity_checks_verified=True,
        real_isolation_evidence_verified=True,
        combined_authorization_ledger_sequence=(combined_authorization_ledger_sequence),
        authorized_at_utc=authorized_at_utc,
        signing_keys=_signing_keys(
            reviewer=role_verifiers["reviewer"],
            executor=role_verifiers["executor"],
            custodian=role_verifiers["custodian"],
            enrollment_authority=verification_inputs.trusted_enrollment_authority,
        ),
    )
    return prepared, chain


def combined_authorization_role_signing_requests_v0_9(
    prepared: CombinedExternalConfirmationAuthorizationV09,
) -> dict[str, DetachedSigningRequestV09]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("combined authorization signing requires a wholly unsigned record")
    payload = _combined_role_payload(prepared)
    return {
        "reviewer": _detached_request(
            artifact_protocol=prepared.protocol,
            role="reviewer",
            domain=COMBINED_REVIEWER_DOMAIN,
            binding=prepared.signing_keys.reviewer,
            payload=payload,
        ),
        "executor": _detached_request(
            artifact_protocol=prepared.protocol,
            role="executor",
            domain=COMBINED_EXECUTOR_DOMAIN,
            binding=prepared.signing_keys.executor,
            payload=payload,
        ),
        "custodian": _detached_request(
            artifact_protocol=prepared.protocol,
            role="custodian",
            domain=COMBINED_CUSTODIAN_DOMAIN,
            binding=prepared.signing_keys.custodian,
            payload=payload,
        ),
    }


def combined_authorization_authority_signing_request_v0_9(
    prepared: CombinedExternalConfirmationAuthorizationV09,
    *,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
) -> DetachedSigningRequestV09:
    role_payload = _combined_role_payload(prepared)
    _verifier(prepared.signing_keys.reviewer).verify(
        COMBINED_REVIEWER_DOMAIN,
        role_payload,
        reviewer_attestation,
    )
    _verifier(prepared.signing_keys.executor).verify(
        COMBINED_EXECUTOR_DOMAIN,
        role_payload,
        executor_attestation,
    )
    _verifier(prepared.signing_keys.custodian).verify(
        COMBINED_CUSTODIAN_DOMAIN,
        role_payload,
        custodian_attestation,
    )
    role_signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    return _detached_request(
        artifact_protocol=prepared.protocol,
        role="enrollment_authority",
        domain=COMBINED_AUTHORITY_DOMAIN,
        binding=prepared.signing_keys.enrollment_authority,
        payload=_combined_authority_payload(role_signed),
    )


def finalize_combined_external_confirmation_authorization_v0_9(
    prepared: CombinedExternalConfirmationAuthorizationV09,
    *,
    chain: VerifiedExternalConfirmationChainV09,
    reviewer_attestation: Attestation | None,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
    enrollment_authority_attestation: Attestation | None,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    if any(
        signature is not None
        for signature in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("combined finalization requires the prepared unsigned record")
    signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
            "enrollment_authority_attestation": enrollment_authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_combined_external_confirmation_authorization_v0_9(
        payload,
        chain=chain,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return payload


def verify_combined_external_confirmation_authorization_v0_9(
    payload: Mapping[str, Any],
    *,
    chain: VerifiedExternalConfirmationChainV09,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> CombinedExternalConfirmationAuthorizationV09:
    # A caller-constructed historical chain must not bypass the public chain
    # verifier above.  v0.6 combined records are permanently non-authoritative
    # after the v0.7 semantic freeze.
    raise ExternalConfirmationBlockedError(
        stage="gate_b_v0_7_receipt_required",
        reason=LEGACY_GATE_B_V0_6_SUPERSEDED_REASON,
    )

    # Historical verifier retained below for forensic replay only.
    raw_record, _ = _content_bound_record(
        payload,
        CombinedExternalConfirmationAuthorizationV09,
        label="combined external confirmation authorization",
    )
    record = CombinedExternalConfirmationAuthorizationV09.model_validate(raw_record)
    expected = _combined_expected_fields(chain)
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("combined authorization differs from the reverified evidence chain")
    if record.combined_authorization_ledger_sequence != (
        chain.sealed_gate_b_score.gate_b_ledger_sequence + 1
    ):
        raise ValueError("combined authorization is premature or uses a stale ledger head")
    if record.authorized_at_utc <= chain.fidelity.verified_at_utc:
        raise ValueError("combined authorization predates or equals fidelity verification")
    reviewer = chain.role_verifiers["reviewer"]
    executor = chain.role_verifiers["executor"]
    custodian = chain.role_verifiers["custodian"]
    for binding, verifier in (
        (record.signing_keys.reviewer, reviewer),
        (record.signing_keys.executor, executor),
        (record.signing_keys.custodian, custodian),
        (record.signing_keys.enrollment_authority, trusted_enrollment_authority),
    ):
        _assert_verifier(binding, verifier)
    role_payload = _combined_role_payload(record)
    reviewer.verify(COMBINED_REVIEWER_DOMAIN, role_payload, record.reviewer_attestation)
    executor.verify(COMBINED_EXECUTOR_DOMAIN, role_payload, record.executor_attestation)
    custodian.verify(COMBINED_CUSTODIAN_DOMAIN, role_payload, record.custodian_attestation)
    trusted_enrollment_authority.verify(
        COMBINED_AUTHORITY_DOMAIN,
        _combined_authority_payload(record),
        record.enrollment_authority_attestation,
    )
    return record


def make_combined_external_confirmation_authorization_v0_9(
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV09,
    combined_authorization_ledger_sequence: int,
    authorized_at_utc: datetime,
    reviewer: Ed25519AttestationSigner,
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    prepared, chain = prepare_combined_external_confirmation_authorization_v0_9(
        verification_inputs=verification_inputs,
        combined_authorization_ledger_sequence=combined_authorization_ledger_sequence,
        authorized_at_utc=authorized_at_utc,
    )
    supplied = {
        "reviewer": reviewer.verifier(),
        "executor": executor.verifier(),
        "custodian": custodian.verifier(),
    }
    if any(
        supplied[role].public_key_sha256 != chain.role_verifiers[role].public_key_sha256
        for role in ("reviewer", "executor", "custodian")
    ) or (
        enrollment_authority.verifier().public_key_sha256
        != verification_inputs.trusted_enrollment_authority.public_key_sha256
    ):
        raise AttestationError("combined authorization signers are outside the registry")
    requests = combined_authorization_role_signing_requests_v0_9(prepared)
    reviewer_attestation = sign_detached_request_v0_9(requests["reviewer"], signer=reviewer)
    executor_attestation = sign_detached_request_v0_9(requests["executor"], signer=executor)
    custodian_attestation = sign_detached_request_v0_9(requests["custodian"], signer=custodian)
    authority_request = combined_authorization_authority_signing_request_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
    )
    return finalize_combined_external_confirmation_authorization_v0_9(
        prepared,
        chain=chain,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
        enrollment_authority_attestation=sign_detached_request_v0_9(
            authority_request,
            signer=enrollment_authority,
        ),
        trusted_enrollment_authority=verification_inputs.trusted_enrollment_authority,
    )


__all__ = [
    "AUTHORITATIVE_LEDGER_ANCHOR_PROTOCOL_ID",
    "AUTHORITATIVE_LEDGER_CHECKPOINT_PROTOCOL_ID",
    "AUTHORITATIVE_LEDGER_CLAIM_BOUNDARY",
    "AUTHORITATIVE_LEDGER_ENTRY_PROTOCOL_ID",
    "AUTHORITATIVE_LEDGER_STORE_IDENTITY_PROTOCOL_ID",
    "BLOCKER_PROTOCOL_ID",
    "COMBINED_AUTHORIZATION_PROTOCOL_ID",
    "EXTERNAL_METHOD_ARMS",
    "FIDELITY_EVIDENCE_PROTOCOL_ID",
    "FIDELITY_SNAPSHOT_PROTOCOL_ID",
    "LEGACY_GATE_B_V0_6_SUPERSEDED_REASON",
    "OPENING_CONSUMPTION_HEAD_PROTOCOL_ID",
    "OPENING_CONSUMPTION_PROTOCOL_ID",
    "SEALED_GATE_B_SCORE_PROTOCOL_ID",
    "VERIFIER_IDENTITY_PROTOCOL_ID",
    "AuthoritativeLedgerStoreIdentityV09",
    "AuthoritativeOpeningConsumptionEntryV09",
    "AuthoritativeOpeningConsumptionStoreV09",
    "AuthoritativeOpeningLedgerAnchorV09",
    "AuthoritativeOpeningLedgerCheckpointV09",
    "CombinedExternalConfirmationAuthorizationV09",
    "ExternalConfirmationBlockedError",
    "ExternalConfirmationBlockerReportV09",
    "ExternalConfirmationVerificationInputsV09",
    "FidelityArtifactPathsV09",
    "FidelityArtifactSnapshotV09",
    "FileAuthoritativeOpeningConsumptionStoreV09",
    "FourPartySigningKeysV09",
    "IndependentVerifierIdentityV09",
    "IsolationReceiptArtifactBindingV09",
    "OpeningConsumptionLedgerHeadV09",
    "OpeningConsumptionLedgerRecordV09",
    "OpeningConsumptionStoreVerificationContextV09",
    "PublicKeyBindingV09",
    "SealedGateBScoreV09",
    "TrustedCanonicalExecutionVerifierV09",
    "TrustedSixMethodFidelityVerifierV09",
    "VerifiedExternalConfirmationChainV09",
    "VerifiedMethodFidelityV09",
    "VerifiedSixMethodFidelityV09",
    "combined_authorization_authority_signing_request_v0_9",
    "combined_authorization_role_signing_requests_v0_9",
    "derive_stratified_traces_from_canonical_execution_v0_9",
    "finalize_combined_external_confirmation_authorization_v0_9",
    "finalize_opening_consumption_record_v0_9",
    "finalize_sealed_gate_b_score_v0_9",
    "finalize_verified_six_method_fidelity_v0_9",
    "inspect_authoritative_ledger_store_identity_v0_9",
    "make_combined_external_confirmation_authorization_v0_9",
    "make_opening_consumption_record_v0_9",
    "make_sealed_gate_b_score_v0_9",
    "make_verified_six_method_fidelity_v0_9",
    "opening_consumption_authority_signing_request_v0_9",
    "opening_consumption_role_signing_requests_v0_9",
    "prepare_combined_external_confirmation_authorization_v0_9",
    "prepare_opening_consumption_record_v0_9",
    "prepare_sealed_gate_b_score_v0_9",
    "prepare_verified_six_method_fidelity_v0_9",
    "run_trusted_six_method_fidelity_verifier_v0_9",
    "sealed_gate_b_score_authority_signing_request_v0_9",
    "sealed_gate_b_score_role_signing_requests_v0_9",
    "snapshot_fidelity_artifacts_v0_9",
    "validate_fidelity_freeze_commitment_sequence_v0_9",
    "verified_six_method_fidelity_signing_request_v0_9",
    "verify_combined_external_confirmation_authorization_v0_9",
    "verify_external_confirmation_chain_v0_9",
    "verify_opening_consumption_record_v0_9",
    "verify_sealed_gate_b_score_v0_9",
    "verify_verified_six_method_fidelity_v0_9",
]
