"""Independent external-verification freeze for Structure Two v1.0.

This module freezes *live bytes*, not caller-declared digests. It is intended
to run before the independent sealed Gate-B commitment record is created. Raw
v0.6 manifests may already contain preregistered validation/holdout commitment
hashes; those hashes are inputs to this freeze, not the later sealed record.
The ceremony is deliberately staged:

1. snapshot the producer, both verifier implementations, and the three raw
   seed-bearing JSON artifacts twice;
2. derive the complete forbidden-seed union in this process;
3. have each runner prove possession and the enrolled top-level executor
   countersign each narrowly scoped runner subkey;
4. collect detached reviewer, executor, and custodian signatures over one
   identical payload; and
5. let the independently trusted enrollment authority witness the exact three
   role signatures only after they exist.

The resulting artifact is an integrity and governance prerequisite.  It does
not assert that six native reproductions exist, that a formal evaluation ran,
or that any efficacy gate passed. The caller-supplied previous head and record
absence flag are not an authority-owned atomic/WORM ledger operation, and the
producer snapshot does not close over the interpreter, dependency lock, native
libraries, or imported runtime data; those remain release blockers.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    TRUST_ROLES,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    ForbiddenSeedNamespacesV09,
    derive_forbidden_seed_namespaces_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    SOURCE_BUNDLE_PROTOCOL,
    compute_producer_source_bundle,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-verification-freeze@1.0"
STATUS = "EXTERNALLY_FROZEN_BEFORE_SEALED_GATE_B_COMMITMENT_RECORD"
DETACHED_REQUEST_PROTOCOL_ID = "structure-two-detached-signing-request@1.0"
VERIFIER_BUNDLE_SNAPSHOT_PROTOCOL_ID = "structure-two-verifier-live-bundle@1.0"
LEDGER_ENTRY_PROTOCOL_ID = "structure-two-external-verification-freeze-ledger-entry@1.0"

RUNNER_POSSESSION_DOMAIN_PREFIX = (
    "cpswm.evaluation.structure_two.external_verification_freeze.runner_possession.v1.0"
)
RUNNER_EXECUTOR_DOMAIN_PREFIX = (
    "cpswm.evaluation.structure_two.external_verification_freeze.executor_delegation.v1.0"
)
ROLE_DOMAIN_PREFIX = "cpswm.evaluation.structure_two.external_verification_freeze.role.v1.0"
AUTHORITY_DOMAIN = (
    "cpswm.evaluation.structure_two.external_verification_freeze.authority_witness.v1.0"
)

RUNNER_SCOPES = ("canonical_episode_executor", "six_method_fidelity_executor")
ZERO_SHA256 = "0" * 64


@dataclass(frozen=True, slots=True)
class VerifierMaterialPathsV10:
    """Actual on-disk material that defines one verifier."""

    bundle_root: Path
    entrypoint_path: Path
    engine_path: Path
    config_path: Path


@dataclass(frozen=True, slots=True)
class ExternalVerificationFreezeLiveInputsV10:
    """All live paths whose bytes must be frozen and later re-verified."""

    repository_root: Path
    canonical_verifier: VerifierMaterialPathsV10
    fidelity_verifier: VerifierMaterialPathsV10
    world_manifest_path: Path
    gate_a_spec_path: Path
    training_split_path: Path


class FileDigestV10(ContractModel):
    relative_path: str = Field(min_length=1)
    bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProducerSourceSnapshotV10(ContractModel):
    protocol: Literal["structure-two-world-arm-producer-source-bundle@0.4"] = (
        "structure-two-world-arm-producer-source-bundle@0.4"
    )
    files: tuple[FileDigestV10, ...] = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        paths = tuple(row.relative_path for row in self.files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("producer source paths must be sorted and unique")
        rows = tuple((row.relative_path, row.bytes_sha256) for row in self.files)
        if content_sha256({"protocol": self.protocol, "files": rows}) != self.content_sha256:
            raise ValueError("producer source bundle content hash mismatch")
        return self


class VerifierMaterialSnapshotV10(ContractModel):
    protocol: Literal["structure-two-verifier-live-bundle@1.0"] = (
        "structure-two-verifier-live-bundle@1.0"
    )
    scope: str = Field(pattern=r"^(canonical_episode_executor|six_method_fidelity_executor)$")
    bundle_root_relative_path: str = Field(min_length=1)
    files: tuple[FileDigestV10, ...] = Field(min_length=1)
    bundle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entrypoint_relative_path: str = Field(min_length=1)
    entrypoint_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    engine_absolute_path: str = Field(pattern=r"^/.*")
    engine_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_relative_path: str = Field(min_length=1)
    config_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        paths = tuple(row.relative_path for row in self.files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("verifier bundle paths must be sorted and unique")
        if self.entrypoint_relative_path == self.config_relative_path:
            raise ValueError("verifier entrypoint and config must be distinct files")
        digest_by_path = {row.relative_path: row.bytes_sha256 for row in self.files}
        required = {
            self.entrypoint_relative_path: self.entrypoint_bytes_sha256,
            self.config_relative_path: self.config_bytes_sha256,
        }
        if any(digest_by_path.get(path) != digest for path, digest in required.items()):
            raise ValueError("verifier special-file digest is outside the frozen bundle")
        rows = tuple((row.relative_path, row.bytes_sha256) for row in self.files)
        expected = content_sha256(
            {
                "protocol": self.protocol,
                "scope": self.scope,
                "bundle_root_relative_path": self.bundle_root_relative_path,
                "files": rows,
            }
        )
        if expected != self.bundle_content_sha256:
            raise ValueError("verifier bundle content hash mismatch")
        return self


class JsonArtifactSnapshotV10(ContractModel):
    artifact_role: str = Field(pattern=r"^(world_manifest|gate_a_spec|training_split)$")
    relative_path: str = Field(min_length=1)
    raw_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stable_json_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicKeyBindingV10(ContractModel):
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_key(self) -> Self:
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id,
            public_key_base64=self.public_key_base64,
        )
        if verifier.public_key_sha256 != self.public_key_sha256:
            raise ValueError("public-key binding hash mismatch")
        return self


class FrozenPartyKeysV10(ContractModel):
    reviewer: PublicKeyBindingV10
    executor: PublicKeyBindingV10
    custodian: PublicKeyBindingV10
    enrollment_authority: PublicKeyBindingV10

    @model_validator(mode="after")
    def validate_independence(self) -> Self:
        rows = (self.reviewer, self.executor, self.custodian, self.enrollment_authority)
        if len({row.key_id for row in rows}) != 4:
            raise ValueError("role and authority key IDs must be pairwise distinct")
        if len({row.public_key_sha256 for row in rows}) != 4:
            raise ValueError("role and authority public keys must be pairwise distinct")
        return self


class RunnerSubkeyBindingV10(ContractModel):
    scope: str = Field(pattern=r"^(canonical_episode_executor|six_method_fidelity_executor)$")
    parent_executor_key_id: str = Field(min_length=1)
    parent_executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runner: PublicKeyBindingV10


class RunnerSubkeyAuthorizationV10(ContractModel):
    scope: str = Field(pattern=r"^(canonical_episode_executor|six_method_fidelity_executor)$")
    runner_possession_attestation: Attestation | None = None
    executor_countersignature: Attestation | None = None


class ExternalVerificationFreezeBodyV10(ContractModel):
    protocol: Literal["structure-two-external-verification-freeze@1.0"] = (
        "structure-two-external-verification-freeze@1.0"
    )
    status: Literal["EXTERNALLY_FROZEN_BEFORE_SEALED_GATE_B_COMMITMENT_RECORD"] = (
        "EXTERNALLY_FROZEN_BEFORE_SEALED_GATE_B_COMMITMENT_RECORD"
    )
    trust_anchor_registry_identifier: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    party_keys: FrozenPartyKeysV10
    producer_source: ProducerSourceSnapshotV10
    canonical_verifier: VerifierMaterialSnapshotV10
    fidelity_verifier: VerifierMaterialSnapshotV10
    world_manifest: JsonArtifactSnapshotV10
    gate_a_spec: JsonArtifactSnapshotV10
    training_split: JsonArtifactSnapshotV10
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09
    forbidden_seed_namespaces_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runner_subkeys: tuple[RunnerSubkeyBindingV10, ...]
    frozen_at_utc: datetime
    freeze_ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: int = Field(ge=1)
    previous_ledger_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_nonce_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_gate_b_commitment_record_state_at_freeze: Literal["NOT_CREATED"] = "NOT_CREATED"
    sealed_gate_b_commitment_record_absence_checked_at_utc: datetime
    freeze_precedes_sealed_gate_b_commitment_record_attested: Literal[True] = True

    @model_validator(mode="after")
    def validate_body(self) -> Self:
        _validate_utc(self.frozen_at_utc, label="frozen_at_utc")
        _validate_utc(
            self.sealed_gate_b_commitment_record_absence_checked_at_utc,
            label="sealed_gate_b_commitment_record_absence_checked_at_utc",
        )
        if self.sealed_gate_b_commitment_record_absence_checked_at_utc != self.frozen_at_utc:
            raise ValueError("sealed Gate-B commitment-record absence check must occur at freeze")
        if (
            not self.freeze_ledger_identifier.strip()
            or self.freeze_ledger_identifier != self.freeze_ledger_identifier.strip()
        ):
            raise ValueError("freeze ledger identifier is malformed")
        if self.canonical_verifier.scope != RUNNER_SCOPES[0]:
            raise ValueError("canonical verifier has the wrong scope")
        if self.fidelity_verifier.scope != RUNNER_SCOPES[1]:
            raise ValueError("fidelity verifier has the wrong scope")
        if tuple(
            row.artifact_role
            for row in (
                self.world_manifest,
                self.gate_a_spec,
                self.training_split,
            )
        ) != ("world_manifest", "gate_a_spec", "training_split"):
            raise ValueError("raw seed artifact roles are incomplete or reordered")
        forbidden = self.forbidden_seed_namespaces
        if forbidden.content_sha256 != self.forbidden_seed_namespaces_sha256:
            raise ValueError("forbidden-seed namespace content hash mismatch")
        if (
            forbidden.world_manifest_content_sha256
            != self.world_manifest.stable_json_content_sha256
            or forbidden.gate_a_spec_content_sha256 != self.gate_a_spec.stable_json_content_sha256
            or forbidden.training_split_content_sha256
            != self.training_split.stable_json_content_sha256
        ):
            raise ValueError("forbidden-seed union is not bound to all three raw artifacts")
        if tuple(row.scope for row in self.runner_subkeys) != RUNNER_SCOPES:
            raise ValueError("freeze requires the ordered exact runner-subkey scopes")
        executor = self.party_keys.executor
        for row in self.runner_subkeys:
            if (
                row.parent_executor_key_id != executor.key_id
                or row.parent_executor_public_key_sha256 != executor.public_key_sha256
            ):
                raise ValueError("runner subkey is outside the enrolled executor scope")
        all_keys = (
            self.party_keys.reviewer,
            self.party_keys.executor,
            self.party_keys.custodian,
            self.party_keys.enrollment_authority,
            *(row.runner for row in self.runner_subkeys),
        )
        if len({row.key_id for row in all_keys}) != 6:
            raise ValueError("role, authority, and runner key IDs must all be distinct")
        if len({row.public_key_sha256 for row in all_keys}) != 6:
            raise ValueError("role, authority, and runner public keys must all be distinct")
        return self


class ExternalVerificationFreezeV10(ContractModel):
    body: ExternalVerificationFreezeBodyV10
    freeze_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_ledger_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runner_authorizations: tuple[RunnerSubkeyAuthorizationV10, ...]
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_derived_hashes(self) -> Self:
        if content_sha256(self.body.model_dump(mode="json")) != self.freeze_body_sha256:
            raise ValueError("external verification freeze body hash mismatch")
        if _ledger_head(self.body, self.freeze_body_sha256) != self.freeze_ledger_head_sha256:
            raise ValueError("external verification freeze ledger head mismatch")
        if tuple(row.scope for row in self.runner_authorizations) != RUNNER_SCOPES:
            raise ValueError("runner authorizations are incomplete or reordered")
        return self


class DetachedSigningRequestV10(ContractModel):
    protocol: Literal["structure-two-detached-signing-request@1.0"] = (
        "structure-two-detached-signing-request@1.0"
    )
    artifact_protocol: Literal["structure-two-external-verification-freeze@1.0"] = (
        "structure-two-external-verification-freeze@1.0"
    )
    role: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    expected_key_id: str = Field(min_length=1)
    expected_public_key_base64: str = Field(min_length=1)
    expected_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.expected_key_id,
            public_key_base64=self.expected_public_key_base64,
        )
        if verifier.public_key_sha256 != self.expected_public_key_sha256:
            raise ValueError("detached signing request key hash mismatch")
        if content_sha256(self.payload) != self.payload_sha256:
            raise ValueError("detached signing request payload hash mismatch")
        return self


@dataclass(frozen=True, slots=True)
class _CapturedLiveInputs:
    producer_source: ProducerSourceSnapshotV10
    canonical_verifier: VerifierMaterialSnapshotV10
    fidelity_verifier: VerifierMaterialSnapshotV10
    world_manifest: JsonArtifactSnapshotV10
    gate_a_spec: JsonArtifactSnapshotV10
    training_split: JsonArtifactSnapshotV10
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09


def _validate_utc(value: datetime, *, label: str) -> None:
    require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


def _key_binding(verifier: Ed25519AttestationVerifier) -> PublicKeyBindingV10:
    return PublicKeyBindingV10(
        key_id=verifier.key_id,
        public_key_base64=verifier.public_key_base64,
        public_key_sha256=verifier.public_key_sha256,
    )


def _verifier(binding: PublicKeyBindingV10) -> Ed25519AttestationVerifier:
    return Ed25519AttestationVerifier.from_public_key_base64(
        key_id=binding.key_id,
        public_key_base64=binding.public_key_base64,
    )


def _resolve_regular_file(repository_root: Path, path: Path, *, label: str) -> Path:
    root = repository_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside repository_root") from exc
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escaped repository_root") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _resolve_directory(repository_root: Path, path: Path, *, label: str) -> Path:
    root = repository_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside repository_root") from exc
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _resolve_external_engine(path: Path, *, label: str) -> Path:
    """Resolve a real executable while rejecting every symlink in its path."""

    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise ValueError(f"{label} must use its canonical absolute path")
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if not os.access(resolved, os.X_OK):
        raise ValueError(f"{label} must be executable")
    return resolved


def _stable_read_bytes(path: Path, *, label: str) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a nonsymlink regular file")
    payload = path.read_bytes()
    after = path.lstat()
    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if fingerprint_before != fingerprint_after or len(payload) != after.st_size:
        raise RuntimeError(f"TOCTOU detected while reading {label}")
    return payload


def _snapshot_paths(
    repository_root: Path,
    paths: tuple[Path, ...],
    *,
    label: str,
) -> tuple[FileDigestV10, ...]:
    root = repository_root.resolve(strict=True)
    rows: list[FileDigestV10] = []
    for path in sorted(set(paths)):
        resolved = _resolve_regular_file(root, path, label=label)
        rows.append(
            FileDigestV10(
                relative_path=resolved.relative_to(root).as_posix(),
                bytes_sha256=hashlib.sha256(
                    _stable_read_bytes(resolved, label=f"{label}:{resolved}")
                ).hexdigest(),
            )
        )
    return tuple(rows)


def _producer_source_snapshot(repository_root: Path) -> ProducerSourceSnapshotV10:
    root = repository_root.resolve(strict=True)
    source_root = _resolve_directory(root, Path("src/cpswm"), label="producer source root")
    source_paths = tuple(source_root.rglob("*.py"))
    app_paths = (
        root / "apps/evaluation_runner/run_structure_two_world_arm_traces_v0_4.py",
        root / "apps/evaluation_runner/attest_structure_two_arm_trace_v0_4.py",
    )
    first = _snapshot_paths(root, source_paths + app_paths, label="producer source")
    official = compute_producer_source_bundle(root)
    second_source_paths = tuple(source_root.rglob("*.py"))
    second = _snapshot_paths(root, second_source_paths + app_paths, label="producer source")
    if first != second:
        raise RuntimeError("TOCTOU detected across producer source-bundle snapshots")
    official_rows = tuple(
        FileDigestV10(relative_path=path, bytes_sha256=digest) for path, digest in official.files
    )
    if second != official_rows:
        raise RuntimeError("producer source changed during official source-bundle computation")
    return ProducerSourceSnapshotV10(
        protocol=SOURCE_BUNDLE_PROTOCOL,
        files=second,
        content_sha256=official.content_sha256,
    )


def _verifier_material_snapshot(
    repository_root: Path,
    material: VerifierMaterialPathsV10,
    *,
    scope: str,
) -> VerifierMaterialSnapshotV10:
    root = repository_root.resolve(strict=True)
    bundle_root = _resolve_directory(root, material.bundle_root, label=f"{scope} bundle root")
    engine = _resolve_external_engine(material.engine_path, label=f"{scope} engine")
    engine_first = _stable_read_bytes(engine, label=f"{scope} engine")
    first_paths = tuple(path for path in bundle_root.rglob("*") if path.is_file())
    first = _snapshot_paths(root, first_paths, label=f"{scope} verifier bundle")
    second_paths = tuple(path for path in bundle_root.rglob("*") if path.is_file())
    second = _snapshot_paths(root, second_paths, label=f"{scope} verifier bundle")
    if first != second:
        raise RuntimeError(f"TOCTOU detected across {scope} verifier-bundle snapshots")
    engine_second = _stable_read_bytes(engine, label=f"{scope} engine")
    if engine_first != engine_second:
        raise RuntimeError(f"TOCTOU detected across {scope} engine snapshots")
    special_paths = tuple(
        _resolve_regular_file(root, path, label=f"{scope} verifier material")
        for path in (material.entrypoint_path, material.config_path)
    )
    if len(set(special_paths)) != 2:
        raise ValueError("verifier entrypoint and config must be distinct files")
    if any(bundle_root not in path.parents for path in special_paths):
        raise ValueError("verifier entrypoint and config must be inside bundle_root")
    digest_by_path = {row.relative_path: row.bytes_sha256 for row in second}
    relative_special = tuple(path.relative_to(root).as_posix() for path in special_paths)
    try:
        special_digests = tuple(digest_by_path[path] for path in relative_special)
    except KeyError as exc:
        raise RuntimeError("verifier special file disappeared during snapshot") from exc
    rows = tuple((row.relative_path, row.bytes_sha256) for row in second)
    bundle_root_relative = bundle_root.relative_to(root).as_posix()
    return VerifierMaterialSnapshotV10(
        scope=scope,
        bundle_root_relative_path=bundle_root_relative,
        files=second,
        bundle_content_sha256=content_sha256(
            {
                "protocol": VERIFIER_BUNDLE_SNAPSHOT_PROTOCOL_ID,
                "scope": scope,
                "bundle_root_relative_path": bundle_root_relative,
                "files": rows,
            }
        ),
        entrypoint_relative_path=relative_special[0],
        entrypoint_bytes_sha256=special_digests[0],
        engine_absolute_path=str(engine),
        engine_bytes_sha256=hashlib.sha256(engine_second).hexdigest(),
        config_relative_path=relative_special[1],
        config_bytes_sha256=special_digests[1],
    )


def _json_object_no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON artifact contains duplicate key {key!r}")
        result[key] = value
    return result


def _json_artifact_snapshot(
    repository_root: Path,
    path: Path,
    *,
    artifact_role: str,
) -> tuple[JsonArtifactSnapshotV10, dict[str, Any]]:
    root = repository_root.resolve(strict=True)
    resolved = _resolve_regular_file(root, path, label=artifact_role)
    first = _stable_read_bytes(resolved, label=artifact_role)
    second = _stable_read_bytes(resolved, label=artifact_role)
    if first != second:
        raise RuntimeError(f"TOCTOU detected across {artifact_role} snapshots")
    try:
        loaded = json.loads(second, object_pairs_hook=_json_object_no_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{artifact_role} is not valid UTF-8 JSON") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{artifact_role} must be a JSON object")
    materialized = dict(loaded)
    embedded = materialized.pop("content_sha256", None)
    stable_hash = content_sha256(materialized if embedded is not None else loaded)
    if embedded is not None and embedded != stable_hash:
        raise ValueError(f"{artifact_role} embedded content hash mismatch")
    return (
        JsonArtifactSnapshotV10(
            artifact_role=artifact_role,
            relative_path=resolved.relative_to(root).as_posix(),
            raw_bytes_sha256=hashlib.sha256(second).hexdigest(),
            stable_json_content_sha256=stable_hash,
        ),
        loaded,
    )


def _capture_live_inputs(live: ExternalVerificationFreezeLiveInputsV10) -> _CapturedLiveInputs:
    root = live.repository_root.resolve(strict=True)
    producer = _producer_source_snapshot(root)
    canonical = _verifier_material_snapshot(
        root,
        live.canonical_verifier,
        scope=RUNNER_SCOPES[0],
    )
    fidelity = _verifier_material_snapshot(
        root,
        live.fidelity_verifier,
        scope=RUNNER_SCOPES[1],
    )
    world_snapshot, world = _json_artifact_snapshot(
        root,
        live.world_manifest_path,
        artifact_role="world_manifest",
    )
    gate_snapshot, gate = _json_artifact_snapshot(
        root,
        live.gate_a_spec_path,
        artifact_role="gate_a_spec",
    )
    training_snapshot, training = _json_artifact_snapshot(
        root,
        live.training_split_path,
        artifact_role="training_split",
    )
    forbidden = derive_forbidden_seed_namespaces_v0_9(
        world_manifest=world,
        expected_world_manifest_content_sha256=world_snapshot.stable_json_content_sha256,
        gate_a_spec=gate,
        expected_gate_a_spec_content_sha256=gate_snapshot.stable_json_content_sha256,
        training_split=training,
        expected_training_split_content_sha256=training_snapshot.stable_json_content_sha256,
    )
    return _CapturedLiveInputs(
        producer_source=producer,
        canonical_verifier=canonical,
        fidelity_verifier=fidelity,
        world_manifest=world_snapshot,
        gate_a_spec=gate_snapshot,
        training_split=training_snapshot,
        forbidden_seed_namespaces=forbidden,
    )


def _stable_capture(live: ExternalVerificationFreezeLiveInputsV10) -> _CapturedLiveInputs:
    first = _capture_live_inputs(live)
    second = _capture_live_inputs(live)
    if first != second:
        raise RuntimeError("TOCTOU detected across complete external-verification snapshots")
    return second


def _ledger_head(body: ExternalVerificationFreezeBodyV10, body_sha256: str) -> str:
    return content_sha256(
        {
            "protocol": LEDGER_ENTRY_PROTOCOL_ID,
            "freeze_ledger_identifier": body.freeze_ledger_identifier,
            "freeze_ledger_sequence": body.freeze_ledger_sequence,
            "previous_ledger_head_sha256": body.previous_ledger_head_sha256,
            "frozen_at_utc": body.frozen_at_utc,
            "freeze_body_sha256": body_sha256,
        }
    )


def _runner_authorization_payload(
    record: ExternalVerificationFreezeV10,
    binding: RunnerSubkeyBindingV10,
) -> dict[str, Any]:
    return {
        "artifact_protocol": PROTOCOL_ID,
        "freeze_body_sha256": record.freeze_body_sha256,
        "freeze_ledger_head_sha256": record.freeze_ledger_head_sha256,
        "runner_subkey": binding.model_dump(mode="json"),
    }


def _role_payload(record: ExternalVerificationFreezeV10) -> dict[str, Any]:
    return record.model_dump(
        mode="json",
        exclude={
            "reviewer_attestation",
            "executor_attestation",
            "custodian_attestation",
            "authority_attestation",
        },
    )


def _authority_payload(record: ExternalVerificationFreezeV10) -> dict[str, Any]:
    role_attestations = {
        role: getattr(record, f"{role}_attestation").model_dump(mode="json") for role in TRUST_ROLES
    }
    return {
        "freeze": _role_payload(record),
        "role_attestations": role_attestations,
        "role_attestations_sha256": content_sha256(role_attestations),
    }


def _request(
    *,
    role: str,
    domain: str,
    verifier: Ed25519AttestationVerifier,
    payload: Mapping[str, Any],
) -> DetachedSigningRequestV10:
    materialized = dict(payload)
    return DetachedSigningRequestV10(
        role=role,
        domain=domain,
        expected_key_id=verifier.key_id,
        expected_public_key_base64=verifier.public_key_base64,
        expected_public_key_sha256=verifier.public_key_sha256,
        payload=materialized,
        payload_sha256=content_sha256(materialized),
    )


def sign_detached_request_v1_0(
    request: DetachedSigningRequestV10,
    *,
    signer: Ed25519AttestationSigner,
) -> Attestation:
    verifier = signer.verifier()
    if (
        verifier.key_id != request.expected_key_id
        or verifier.public_key_base64 != request.expected_public_key_base64
        or verifier.public_key_sha256 != request.expected_public_key_sha256
    ):
        raise AttestationError("detached request was delivered to the wrong signer")
    if content_sha256(request.payload) != request.payload_sha256:
        raise ValueError("detached request payload changed before signing")
    return signer.sign(request.domain, request.payload)


def prepare_external_verification_freeze_v1_0(
    *,
    live_inputs: ExternalVerificationFreezeLiveInputsV10,
    trust_anchor_registry: Mapping[str, Any],
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    canonical_runner: Ed25519AttestationVerifier,
    fidelity_runner: Ed25519AttestationVerifier,
    frozen_at_utc: datetime,
    freeze_ledger_identifier: str,
    freeze_ledger_sequence: int,
    previous_ledger_head_sha256: str,
    authority_nonce_sha256: str,
    sealed_gate_b_commitment_record_exists: bool,
) -> ExternalVerificationFreezeV10:
    """Prepare a wholly unsigned freeze before the sealed Gate-B record."""

    if sealed_gate_b_commitment_record_exists:
        raise ValueError(
            "external verification freeze must precede sealed Gate-B commitment creation"
        )
    _validate_utc(frozen_at_utc, label="frozen_at_utc")
    registry, role_verifiers = verify_trust_anchor_registry_v0_6(
        trust_anchor_registry,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    if frozen_at_utc <= max(row.enrolled_at_utc for row in registry.role_keys):
        raise ValueError("external verification freeze must follow role enrollment")
    captured = _stable_capture(live_inputs)
    parties = FrozenPartyKeysV10(
        reviewer=_key_binding(role_verifiers["reviewer"]),
        executor=_key_binding(role_verifiers["executor"]),
        custodian=_key_binding(role_verifiers["custodian"]),
        enrollment_authority=_key_binding(trusted_enrollment_authority),
    )
    runners = (
        RunnerSubkeyBindingV10(
            scope=RUNNER_SCOPES[0],
            parent_executor_key_id=parties.executor.key_id,
            parent_executor_public_key_sha256=parties.executor.public_key_sha256,
            runner=_key_binding(canonical_runner),
        ),
        RunnerSubkeyBindingV10(
            scope=RUNNER_SCOPES[1],
            parent_executor_key_id=parties.executor.key_id,
            parent_executor_public_key_sha256=parties.executor.public_key_sha256,
            runner=_key_binding(fidelity_runner),
        ),
    )
    body = ExternalVerificationFreezeBodyV10(
        trust_anchor_registry_identifier=registry.registry_identifier,
        party_keys=parties,
        producer_source=captured.producer_source,
        canonical_verifier=captured.canonical_verifier,
        fidelity_verifier=captured.fidelity_verifier,
        world_manifest=captured.world_manifest,
        gate_a_spec=captured.gate_a_spec,
        training_split=captured.training_split,
        forbidden_seed_namespaces=captured.forbidden_seed_namespaces,
        forbidden_seed_namespaces_sha256=captured.forbidden_seed_namespaces.content_sha256,
        runner_subkeys=runners,
        frozen_at_utc=frozen_at_utc,
        freeze_ledger_identifier=freeze_ledger_identifier,
        freeze_ledger_sequence=freeze_ledger_sequence,
        previous_ledger_head_sha256=previous_ledger_head_sha256,
        authority_nonce_sha256=authority_nonce_sha256,
        sealed_gate_b_commitment_record_absence_checked_at_utc=frozen_at_utc,
    )
    body_sha256 = content_sha256(body.model_dump(mode="json"))
    return ExternalVerificationFreezeV10(
        body=body,
        freeze_body_sha256=body_sha256,
        freeze_ledger_head_sha256=_ledger_head(body, body_sha256),
        runner_authorizations=tuple(
            RunnerSubkeyAuthorizationV10(scope=scope) for scope in RUNNER_SCOPES
        ),
    )


def runner_subkey_signing_requests_v1_0(
    record: ExternalVerificationFreezeV10,
) -> dict[str, DetachedSigningRequestV10]:
    if any(
        value is not None
        for authorization in record.runner_authorizations
        for value in (
            authorization.runner_possession_attestation,
            authorization.executor_countersignature,
        )
    ) or any(
        getattr(record, f"{role}_attestation") is not None for role in (*TRUST_ROLES, "authority")
    ):
        raise ValueError("runner requests require a wholly unsigned freeze")
    executor = _verifier(record.body.party_keys.executor)
    requests: dict[str, DetachedSigningRequestV10] = {}
    for binding in record.body.runner_subkeys:
        runner = _verifier(binding.runner)
        payload = _runner_authorization_payload(record, binding)
        requests[f"{binding.scope}:runner"] = _request(
            role=f"{binding.scope}:runner",
            domain=f"{RUNNER_POSSESSION_DOMAIN_PREFIX}.{binding.scope}",
            verifier=runner,
            payload=payload,
        )
        requests[f"{binding.scope}:executor"] = _request(
            role=f"{binding.scope}:executor",
            domain=f"{RUNNER_EXECUTOR_DOMAIN_PREFIX}.{binding.scope}",
            verifier=executor,
            payload=payload,
        )
    return requests


def attach_runner_subkey_attestations_v1_0(
    *,
    record: ExternalVerificationFreezeV10,
    attestations: Mapping[str, Attestation],
    canonical_runner: Ed25519AttestationVerifier,
    fidelity_runner: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
) -> ExternalVerificationFreezeV10:
    expected_keys = tuple(
        f"{scope}:{role}" for scope in RUNNER_SCOPES for role in ("runner", "executor")
    )
    if tuple(attestations) != expected_keys:
        raise ValueError("runner attestation set is incomplete or reordered")
    requests = runner_subkey_signing_requests_v1_0(record)
    supplied_runners = {
        RUNNER_SCOPES[0]: canonical_runner,
        RUNNER_SCOPES[1]: fidelity_runner,
    }
    if executor.public_key_sha256 != record.body.party_keys.executor.public_key_sha256:
        raise AttestationError("runner delegation used an unregistered top-level executor")
    authorizations: list[RunnerSubkeyAuthorizationV10] = []
    for binding in record.body.runner_subkeys:
        runner = supplied_runners[binding.scope]
        if (
            runner.key_id != binding.runner.key_id
            or runner.public_key_base64 != binding.runner.public_key_base64
            or runner.public_key_sha256 != binding.runner.public_key_sha256
        ):
            raise AttestationError("runner possession signature used an unregistered runner")
        runner_request = requests[f"{binding.scope}:runner"]
        executor_request = requests[f"{binding.scope}:executor"]
        runner.verify(
            runner_request.domain, runner_request.payload, attestations[runner_request.role]
        )
        executor.verify(
            executor_request.domain,
            executor_request.payload,
            attestations[executor_request.role],
        )
        authorizations.append(
            RunnerSubkeyAuthorizationV10(
                scope=binding.scope,
                runner_possession_attestation=attestations[runner_request.role],
                executor_countersignature=attestations[executor_request.role],
            )
        )
    return record.model_copy(update={"runner_authorizations": tuple(authorizations)})


def external_verification_freeze_signing_requests_v1_0(
    record: ExternalVerificationFreezeV10,
) -> dict[str, DetachedSigningRequestV10]:
    _verify_runner_authorizations(record)
    if any(
        getattr(record, f"{role}_attestation") is not None for role in (*TRUST_ROLES, "authority")
    ):
        raise ValueError("role requests require a freeze without role or authority signatures")
    payload = _role_payload(record)
    parties = record.body.party_keys
    return {
        role: _request(
            role=role,
            domain=f"{ROLE_DOMAIN_PREFIX}.{role}",
            verifier=_verifier(getattr(parties, role)),
            payload=payload,
        )
        for role in TRUST_ROLES
    }


def attach_external_verification_freeze_role_attestations_v1_0(
    *,
    record: ExternalVerificationFreezeV10,
    attestations: Mapping[str, Attestation],
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> ExternalVerificationFreezeV10:
    if tuple(attestations) != TRUST_ROLES:
        raise ValueError("freeze requires the ordered exact three-role attestation set")
    requests = external_verification_freeze_signing_requests_v1_0(record)
    supplied = {"reviewer": reviewer, "executor": executor, "custodian": custodian}
    for role in TRUST_ROLES:
        binding = getattr(record.body.party_keys, role)
        verifier = supplied[role]
        if (
            verifier.key_id != binding.key_id
            or verifier.public_key_base64 != binding.public_key_base64
            or verifier.public_key_sha256 != binding.public_key_sha256
        ):
            raise AttestationError(f"{role} freeze signature used an unregistered key")
        verifier.verify(requests[role].domain, requests[role].payload, attestations[role])
    return record.model_copy(
        update={f"{role}_attestation": attestations[role] for role in TRUST_ROLES}
    )


def external_verification_freeze_authority_signing_request_v1_0(
    record: ExternalVerificationFreezeV10,
    *,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> DetachedSigningRequestV10:
    if record.authority_attestation is not None:
        raise ValueError("authority already witnessed this freeze")
    _verify_role_attestations(
        record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
    )
    authority_binding = record.body.party_keys.enrollment_authority
    if (
        enrollment_authority.key_id != authority_binding.key_id
        or enrollment_authority.public_key_base64 != authority_binding.public_key_base64
        or enrollment_authority.public_key_sha256 != authority_binding.public_key_sha256
    ):
        raise AttestationError("freeze used an attacker-selected enrollment authority")
    return _request(
        role="authority",
        domain=AUTHORITY_DOMAIN,
        verifier=enrollment_authority,
        payload=_authority_payload(record),
    )


def finalize_external_verification_freeze_v1_0(
    *,
    record: ExternalVerificationFreezeV10,
    authority_attestation: Attestation,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    request = external_verification_freeze_authority_signing_request_v1_0(
        record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
        enrollment_authority=enrollment_authority,
    )
    enrollment_authority.verify(request.domain, request.payload, authority_attestation)
    signed = record.model_copy(update={"authority_attestation": authority_attestation})
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _verify_runner_authorizations(record: ExternalVerificationFreezeV10) -> None:
    executor = _verifier(record.body.party_keys.executor)
    if len(record.runner_authorizations) != len(record.body.runner_subkeys):
        raise AttestationError("runner authorization count mismatch")
    for binding, authorization in zip(
        record.body.runner_subkeys,
        record.runner_authorizations,
        strict=True,
    ):
        if binding.scope != authorization.scope:
            raise AttestationError("runner authorization scope mismatch")
        payload = _runner_authorization_payload(record, binding)
        runner = _verifier(binding.runner)
        runner.verify(
            f"{RUNNER_POSSESSION_DOMAIN_PREFIX}.{binding.scope}",
            payload,
            authorization.runner_possession_attestation,
        )
        executor.verify(
            f"{RUNNER_EXECUTOR_DOMAIN_PREFIX}.{binding.scope}",
            payload,
            authorization.executor_countersignature,
        )


def _verify_role_attestations(
    record: ExternalVerificationFreezeV10,
    *,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> None:
    _verify_runner_authorizations(record)
    supplied = {"reviewer": reviewer, "executor": executor, "custodian": custodian}
    payload = _role_payload(record)
    for role in TRUST_ROLES:
        binding = getattr(record.body.party_keys, role)
        verifier = supplied[role]
        if (
            verifier.key_id != binding.key_id
            or verifier.public_key_base64 != binding.public_key_base64
            or verifier.public_key_sha256 != binding.public_key_sha256
        ):
            raise AttestationError(f"{role} verifier is outside the frozen registry")
        verifier.verify(
            f"{ROLE_DOMAIN_PREFIX}.{role}",
            payload,
            getattr(record, f"{role}_attestation"),
        )


def verify_external_verification_freeze_v1_0(
    payload: Mapping[str, Any],
    *,
    live_inputs: ExternalVerificationFreezeLiveInputsV10,
    trust_anchor_registry: Mapping[str, Any],
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    expected_previous_ledger_head_sha256: str,
    expected_freeze_ledger_sequence: int,
    verification_time_utc: datetime,
    sealed_gate_b_commitment_record_created_at_utc: datetime | None = None,
) -> ExternalVerificationFreezeV10:
    """Verify signatures, live bytes, raw seeds, ordering, and ledger context."""

    _validate_utc(verification_time_utc, label="verification_time_utc")
    materialized = dict(payload)
    stored = materialized.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(materialized) != stored:
        raise ValueError("external verification freeze content hash mismatch")
    record = ExternalVerificationFreezeV10.model_validate(materialized)
    if materialized != record.model_dump(mode="json"):
        raise ValueError("external verification freeze encoding is noncanonical")
    registry, role_verifiers = verify_trust_anchor_registry_v0_6(
        trust_anchor_registry,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    if record.body.trust_anchor_registry_identifier != registry.registry_identifier:
        raise AttestationError("freeze is bound to a different trust-anchor registry")
    if record.body.frozen_at_utc <= max(row.enrolled_at_utc for row in registry.role_keys):
        raise ValueError("freeze timestamp does not follow role enrollment")
    if record.body.frozen_at_utc > verification_time_utc:
        raise ValueError("freeze timestamp is in the verifier's future")
    if (
        record.body.previous_ledger_head_sha256 != expected_previous_ledger_head_sha256
        or record.body.freeze_ledger_sequence != expected_freeze_ledger_sequence
    ):
        raise ValueError("freeze ledger head or sequence does not match external ledger state")
    expected_parties = FrozenPartyKeysV10(
        reviewer=_key_binding(role_verifiers["reviewer"]),
        executor=_key_binding(role_verifiers["executor"]),
        custodian=_key_binding(role_verifiers["custodian"]),
        enrollment_authority=_key_binding(trusted_enrollment_authority),
    )
    if record.body.party_keys != expected_parties:
        raise AttestationError("freeze party keys do not match the externally trusted registry")
    captured = _stable_capture(live_inputs)
    expected_live = (
        captured.producer_source,
        captured.canonical_verifier,
        captured.fidelity_verifier,
        captured.world_manifest,
        captured.gate_a_spec,
        captured.training_split,
        captured.forbidden_seed_namespaces,
    )
    frozen_live = (
        record.body.producer_source,
        record.body.canonical_verifier,
        record.body.fidelity_verifier,
        record.body.world_manifest,
        record.body.gate_a_spec,
        record.body.training_split,
        record.body.forbidden_seed_namespaces,
    )
    if frozen_live != expected_live:
        raise ValueError("live source, verifier, raw JSON, or forbidden-seed material changed")
    _verify_role_attestations(
        record,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
    )
    authority_request = _request(
        role="authority",
        domain=AUTHORITY_DOMAIN,
        verifier=trusted_enrollment_authority,
        payload=_authority_payload(record),
    )
    trusted_enrollment_authority.verify(
        authority_request.domain,
        authority_request.payload,
        record.authority_attestation,
    )
    if sealed_gate_b_commitment_record_created_at_utc is not None:
        _validate_utc(
            sealed_gate_b_commitment_record_created_at_utc,
            label="sealed_gate_b_commitment_record_created_at_utc",
        )
        if sealed_gate_b_commitment_record_created_at_utc <= record.body.frozen_at_utc:
            raise ValueError(
                "sealed Gate-B commitment record did not follow external verification freeze"
            )
    return record


def runner_verifiers_from_external_verification_freeze_v1_0(
    record: ExternalVerificationFreezeV10,
) -> dict[str, Ed25519AttestationVerifier]:
    """Return only executor-delegated runner keys from an already verified freeze."""

    _verify_runner_authorizations(record)
    return {row.scope: _verifier(row.runner) for row in record.body.runner_subkeys}


__all__ = [
    "AUTHORITY_DOMAIN",
    "DETACHED_REQUEST_PROTOCOL_ID",
    "PROTOCOL_ID",
    "RUNNER_SCOPES",
    "ExternalVerificationFreezeBodyV10",
    "ExternalVerificationFreezeLiveInputsV10",
    "ExternalVerificationFreezeV10",
    "VerifierMaterialPathsV10",
    "attach_external_verification_freeze_role_attestations_v1_0",
    "attach_runner_subkey_attestations_v1_0",
    "external_verification_freeze_authority_signing_request_v1_0",
    "external_verification_freeze_signing_requests_v1_0",
    "finalize_external_verification_freeze_v1_0",
    "prepare_external_verification_freeze_v1_0",
    "runner_subkey_signing_requests_v1_0",
    "runner_verifiers_from_external_verification_freeze_v1_0",
    "sign_detached_request_v1_0",
    "verify_external_verification_freeze_v1_0",
]
