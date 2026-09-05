"""Raw-input external-confirmation chain for Structure Two v1.0.

The public verifier in this module never accepts an already constructed
``VerifiedExternalConfirmationChainV10``.  It starts from the signed artifacts,
live paths, and the authority-owned consumption store on every invocation.
Both semantic verifiers must have run as the exact live-byte implementations
frozen by :mod:`structure_two_external_verification_freeze_v1_0`, under a real
v0.9 isolation receipt signed by the corresponding delegated runner subkey.

This module is an authorization mechanism, not external evidence. Gate B v0.7
was invalidated on 2026-09-05 and its sealed receipt is historical only. The
current comparator-typed v0.8 protocol has no formal execution receipt, so all
combined positive paths fail closed until a future raw v0.8 formal verifier is
integrated and independently controlled evidence exists.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

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
    CanonicalPerEpisodeExecutionArtifactV09,
    VerifiedExecutionPrerequisitesV09,
    artifact_content_sha256_v0_9,
    recompute_sealed_visible_episode_inputs_v0_9,
    verify_canonical_per_episode_execution_artifact_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    default_external_method_specifications_v0_2,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v0_9 import (
    AuthoritativeLedgerStoreIdentityV09,
    FidelityArtifactPathsV09,
    FidelityArtifactSnapshotV09,
    FidelityIsolationReceiptVerificationV09,
    FileAuthoritativeOpeningConsumptionStoreV09,
    IndependentVerifierIdentityV09,
    OpeningConsumptionLedgerHeadV09,
    OpeningConsumptionStoreVerificationContextV09,
    VerifiedSixMethodFidelityV09,
    snapshot_fidelity_artifacts_v0_9,
    verify_verified_six_method_fidelity_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    TRUST_ROLES,
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
    ExternalVerificationFreezeLiveInputsV10,
    ExternalVerificationFreezeV10,
    FrozenPartyKeysV10,
    PublicKeyBindingV10,
    VerifierMaterialPathsV10,
    VerifierMaterialSnapshotV10,
    _verifier_material_snapshot,
    runner_verifiers_from_external_verification_freeze_v1_0,
    verify_external_verification_freeze_v1_0,
)
from cpswm.system.evaluation_operations.structure_two_gate_a_v0_6 import (
    GateAArtifactPathsV06,
    GateAReportV06,
    verify_gate_a_report_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    DEFAULT_RESOURCE_LIMITS,
    IsolationExecutionReceiptV09,
    verify_isolation_receipt_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_sealed_dual_gate_b_v1_0 import (
    CanonicalDualReadoutExecutionV10,
    DualReadoutIsolationVerificationInputsV10,
    SealedDualGateBReceiptV10,
    verify_canonical_dual_readout_execution_v1_0,
    verify_sealed_dual_gate_b_receipt_v1_0,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    SealedGateBOpeningV09,
    SealedGateBOpeningVerificationContextV09,
    VerifiedGateALifecycleCompletionV09,
    VerifiedSealedGateBCommitmentV09,
    build_sealed_gate_b_opening_context_v0_9,
    verify_gate_a_lifecycle_completion_record_v0_9,
    verify_sealed_gate_b_commitment_record_v0_9,
    verify_sealed_gate_b_opening_v0_9,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

PROTOCOL_ID = "structure-two-external-confirmation-authorization@1.0"
STATUS = "COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED"
BLOCKER_PROTOCOL_ID = "structure-two-external-confirmation-blocker@1.0"
VERIFIER_REQUEST_PROTOCOL_ID = "structure-two-isolated-verifier-request@1.0"
VERIFIER_EXECUTION_PROTOCOL_ID = "structure-two-isolated-verifier-execution-binding@1.0"
DETACHED_REQUEST_PROTOCOL_ID = "structure-two-combined-detached-signing-request@1.0"
FREEZE_COMMITMENT_LINK_PROTOCOL_ID = "structure-two-freeze-commitment-link@1.0"
FREEZE_COMMITMENT_LINK_REQUEST_PROTOCOL_ID = (
    "structure-two-freeze-commitment-link-detached-request@1.0"
)

COMBINED_REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.combined.reviewer.v1.0"
COMBINED_EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.combined.executor.v1.0"
COMBINED_CUSTODIAN_DOMAIN = "cpswm.evaluation.structure_two.combined.custodian.v1.0"
COMBINED_AUTHORITY_DOMAIN = "cpswm.evaluation.structure_two.combined.authority_witness.v1.0"
FREEZE_COMMITMENT_LINK_CUSTODIAN_DOMAIN = (
    "cpswm.evaluation.structure_two.freeze_commitment_link.custodian.v1.0"
)
FREEZE_COMMITMENT_LINK_AUTHORITY_DOMAIN = (
    "cpswm.evaluation.structure_two.freeze_commitment_link.authority_witness.v1.0"
)

FREEZE_COMMITMENT_LINK_CLAIM_BOUNDARY = (
    "This receipt is a custodian-and-authority signed cryptographic linkage from the exact "
    "external-verification freeze to the exact sealed commitment. It does not establish "
    "WORM storage, transparency-log inclusion, or anti-equivocation by either signer."
)

CANONICAL_SCOPE = "canonical_episode_executor"
FIDELITY_SCOPE = "six_method_fidelity_executor"
VERIFIER_REQUEST_FILENAME = "verifier-request.json"
VERIFIER_RESULT_FILENAME = "verifier-result.json"
CURRENT_GATE_B_PROTOCOL_ID = "structure-two-comparator-typed-dual-gate-b@0.8"
ZERO_SHA256 = "0" * 64

EXTERNAL_METHOD_SPECIFICATIONS = default_external_method_specifications_v0_2()
EXTERNAL_METHOD_ARMS = tuple(row.arm for row in EXTERNAL_METHOD_SPECIFICATIONS)
EXTERNAL_METHOD_NAMES = {row.arm: row.method for row in EXTERNAL_METHOD_SPECIFICATIONS}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_utc(value: datetime, *, label: str) -> None:
    require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


def _payload_content_hash(payload: Mapping[str, Any], *, label: str) -> str:
    materialized = dict(payload)
    stored = materialized.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(materialized) != stored:
        raise ValueError(f"{label} content hash mismatch")
    return stored


def _content_bound_payload(model: ContractModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _stable_file_bytes(path: Path, *, label: str) -> tuple[Path, bytes]:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = path.resolve(strict=True)
    before = resolved.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular file")
    raw = resolved.read_bytes()
    after = resolved.lstat()
    fingerprints = (
        (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ),
        (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ),
    )
    if fingerprints[0] != fingerprints[1] or len(raw) != after.st_size:
        raise ValueError(f"{label} changed while it was read")
    return resolved, raw


def _stable_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], str, str]:
    _, raw = _stable_file_bytes(path, label=label)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain one JSON object")
    stored = _payload_content_hash(payload, label=label)
    return payload, hashlib.sha256(raw).hexdigest(), stored


def _assert_verifier(
    binding: Any,
    verifier: Ed25519AttestationVerifier,
    *,
    label: str,
) -> None:
    if (
        binding.key_id != verifier.key_id
        or binding.public_key_base64 != verifier.public_key_base64
        or binding.public_key_sha256 != verifier.public_key_sha256
    ):
        raise AttestationError(f"{label} is outside the frozen enrollment")


def _frozen_verifier_identity(
    freeze: ExternalVerificationFreezeV10,
    *,
    scope: str,
) -> IndependentVerifierIdentityV09:
    snapshot = (
        freeze.body.canonical_verifier
        if scope == CANONICAL_SCOPE
        else freeze.body.fidelity_verifier
    )
    return IndependentVerifierIdentityV09(
        verifier_identifier=f"freeze:{freeze.freeze_body_sha256}:{scope}",
        implementation_executor_sha256=snapshot.bundle_content_sha256,
        verifier_configuration_sha256=snapshot.config_bytes_sha256,
    )


def _primary_source_hashes(source_register: Mapping[str, Any]) -> dict[str, str]:
    rows = source_register.get("methods")
    if not isinstance(rows, list):
        raise ValueError("source register lacks method rows")
    by_arm = {
        str(row.get("arm")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("arm"), str)
    }
    if tuple(arm for arm in EXTERNAL_METHOD_ARMS if arm in by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("source register lacks the ordered canonical six methods")
    if set(by_arm) != set(EXTERNAL_METHOD_ARMS):
        raise ValueError("source register contains an unexpected method")
    result: dict[str, str] = {}
    for specification in EXTERNAL_METHOD_SPECIFICATIONS:
        row = by_arm[specification.arm]
        digest = row.get("primary_source_sha256")
        if (
            row.get("method") != specification.method
            or row.get("primary_source_url") != specification.primary_source_url
            or not _is_sha256(digest)
        ):
            raise ValueError("source register method identity or source hash is invalid")
        result[specification.arm] = str(digest)
    return result


@dataclass(frozen=True, slots=True)
class IsolatedVerifierExecutionPathsV10:
    """Raw paths for one frozen verifier invocation; no executable callback."""

    request_path: Path
    result_path: Path
    isolation_receipt_path: Path
    working_directory: Path


class IsolatedVerifierRequestV10(ContractModel):
    protocol: Literal["structure-two-isolated-verifier-request@1.0"] = (
        "structure-two-isolated-verifier-request@1.0"
    )
    scope: Literal["canonical_episode_executor", "six_method_fidelity_executor"]
    freeze_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    verifier_material_snapshot: VerifierMaterialSnapshotV10
    isolation_code_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_bindings: dict[str, Any]

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.verifier_material_snapshot.scope != self.scope:
            raise ValueError("isolated verifier request material has the wrong scope")
        expected_isolation_hash = _isolation_bundle_sha256_from_snapshot(
            self.verifier_material_snapshot
        )
        if self.isolation_code_bundle_sha256 != expected_isolation_hash:
            raise ValueError("isolated verifier request code-bundle hash is inconsistent")
        if not self.evidence_bindings:
            raise ValueError("isolated verifier request has no evidence bindings")
        return self


class IsolatedVerifierExecutionBindingV10(ContractModel):
    protocol: Literal["structure-two-isolated-verifier-execution-binding@1.0"] = (
        "structure-two-isolated-verifier-execution-binding@1.0"
    )
    scope: Literal["canonical_episode_executor", "six_method_fidelity_executor"]
    freeze_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_bundle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_entrypoint_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_engine_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_config_bytes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_material_before: VerifierMaterialSnapshotV10
    verifier_material_after: VerifierMaterialSnapshotV10
    isolation_code_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    isolation_receipt_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    isolation_receipt_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runner_key_id: str = Field(min_length=1)
    runner_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at_utc: datetime
    finished_at_utc: datetime
    formal_isolation_verified: Literal[True]

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _validate_utc(self.started_at_utc, label="verifier execution start")
        _validate_utc(self.finished_at_utc, label="verifier execution finish")
        if self.finished_at_utc <= self.started_at_utc:
            raise ValueError("verifier execution finish must follow start")
        if (
            self.verifier_material_before.scope != self.scope
            or self.verifier_material_after.scope != self.scope
        ):
            raise ValueError("verifier execution material has the wrong scope")
        if self.verifier_material_before != self.verifier_material_after:
            raise ValueError("verifier material changed across receipt verification")
        snapshot = self.verifier_material_before
        if (
            self.verifier_bundle_content_sha256 != snapshot.bundle_content_sha256
            or self.verifier_entrypoint_bytes_sha256 != snapshot.entrypoint_bytes_sha256
            or self.verifier_engine_bytes_sha256 != snapshot.engine_bytes_sha256
            or self.verifier_config_bytes_sha256 != snapshot.config_bytes_sha256
            or self.isolation_code_bundle_sha256 != _isolation_bundle_sha256_from_snapshot(snapshot)
        ):
            raise ValueError("verifier execution hashes differ from measured material")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def _material_paths_for_scope(
    live: ExternalVerificationFreezeLiveInputsV10,
    *,
    scope: str,
) -> VerifierMaterialPathsV10:
    if scope == CANONICAL_SCOPE:
        return live.canonical_verifier
    if scope == FIDELITY_SCOPE:
        return live.fidelity_verifier
    raise ValueError("unknown frozen verifier scope")


def _isolation_bundle_sha256_from_snapshot(snapshot: VerifierMaterialSnapshotV10) -> str:
    """Re-express the freeze file list using the isolation receipt's tree hash."""

    bundle_root = PurePosixPath(snapshot.bundle_root_relative_path)
    rows: list[tuple[str, str]] = []
    for file in snapshot.files:
        try:
            relative = PurePosixPath(file.relative_path).relative_to(bundle_root)
        except ValueError as exc:
            raise ValueError("verifier snapshot file is outside its bundle root") from exc
        if not relative.parts or relative == PurePosixPath("."):
            raise ValueError("verifier snapshot contains a non-file bundle-root entry")
        rows.append((relative.as_posix(), file.bytes_sha256))
    if tuple(path for path, _ in rows) != tuple(sorted(path for path, _ in rows)):
        raise ValueError("verifier snapshot bundle-relative paths are not sorted")
    return content_sha256({"files": rows})


def _measure_frozen_verifier_material(
    *,
    scope: str,
    repository_root: Path,
    material: VerifierMaterialPathsV10,
    frozen_snapshot: VerifierMaterialSnapshotV10,
    phase: str,
) -> VerifierMaterialSnapshotV10:
    try:
        measured = _verifier_material_snapshot(
            repository_root,
            material,
            scope=scope,
        )
    except RuntimeError as exc:
        raise ValueError(f"{scope} live verifier material was unstable at {phase}") from exc
    if measured != frozen_snapshot:
        raise ValueError(f"{scope} live verifier material differs from freeze snapshot at {phase}")
    return measured


def _assert_isolation_receipt_binds_frozen_material(
    isolation: IsolationExecutionReceiptV09,
    *,
    bundle_root: Path,
    frozen_snapshot: VerifierMaterialSnapshotV10,
    isolation_code_bundle_sha256: str,
) -> None:
    if (
        isolation.code_bundle.resolved_path != str(bundle_root)
        or isolation.code_bundle.artifact_kind != "directory"
        or isolation.code_bundle.content_sha256 != isolation_code_bundle_sha256
        or isolation.command_engine_path != frozen_snapshot.engine_absolute_path
        or isolation.command_engine_binary_sha256 != frozen_snapshot.engine_bytes_sha256
    ):
        raise ValueError("signed isolation receipt does not bind frozen verifier material")


def _verify_isolated_verifier_execution(
    *,
    scope: str,
    freeze: ExternalVerificationFreezeV10,
    live_inputs: ExternalVerificationFreezeLiveInputsV10,
    runner: Ed25519AttestationVerifier,
    paths: IsolatedVerifierExecutionPathsV10,
    expected_request: IsolatedVerifierRequestV10,
    verifier_input_paths: Mapping[str, Path],
) -> tuple[dict[str, Any], IsolatedVerifierExecutionBindingV10]:
    material = _material_paths_for_scope(live_inputs, scope=scope)
    frozen_snapshot = (
        freeze.body.canonical_verifier
        if scope == CANONICAL_SCOPE
        else freeze.body.fidelity_verifier
    )
    repository_root = live_inputs.repository_root.resolve(strict=True)

    def repository_path(path: Path) -> Path:
        return (path if path.is_absolute() else repository_root / path).resolve(strict=True)

    root = repository_path(material.bundle_root)
    entrypoint = repository_path(material.entrypoint_path)
    config = repository_path(material.config_path)
    engine = material.engine_path.resolve(strict=True)
    work = paths.working_directory.resolve(strict=True)
    request = paths.request_path.resolve(strict=True)
    result = paths.result_path.resolve(strict=True)
    if request.name != VERIFIER_REQUEST_FILENAME:
        raise ValueError("frozen verifier request uses a noncanonical filename")
    if result.parent != work or result.name != VERIFIER_RESULT_FILENAME:
        raise ValueError("frozen verifier result must use the fixed work-directory filename")

    admitted_material = _measure_frozen_verifier_material(
        scope=scope,
        repository_root=repository_root,
        material=material,
        frozen_snapshot=frozen_snapshot,
        phase="admission",
    )
    isolation_code_bundle_sha256 = _isolation_bundle_sha256_from_snapshot(admitted_material)
    if (
        expected_request.verifier_material_snapshot != admitted_material
        or expected_request.isolation_code_bundle_sha256 != isolation_code_bundle_sha256
    ):
        raise ValueError("isolated verifier request does not bind admitted live material")

    request_payload, request_artifact_hash, request_content_hash = _stable_json_object(
        request,
        label=f"{scope} verifier request",
    )
    expected_request_payload = _content_bound_payload(expected_request)
    if request_payload != expected_request_payload:
        raise ValueError("isolated verifier request differs from verifier-rebuilt raw inputs")
    expected_request_bytes = canonical_json(expected_request_payload).encode("utf-8")
    _, request_bytes_after = _stable_file_bytes(
        request,
        label=f"{scope} verifier request after decode",
    )
    if request_bytes_after != expected_request_bytes:
        raise ValueError("isolated verifier request is not canonically encoded")

    isolation_payload, isolation_artifact_hash, isolation_content_hash = _stable_json_object(
        paths.isolation_receipt_path,
        label=f"{scope} verifier isolation receipt",
    )
    arguments = (
        str(entrypoint),
        "--config",
        str(config),
        "--request",
        str(request),
        "--output",
        str(result),
    )
    inputs = {"verification_request": request, **dict(verifier_input_paths)}
    material_before = _measure_frozen_verifier_material(
        scope=scope,
        repository_root=repository_root,
        material=material,
        frozen_snapshot=frozen_snapshot,
        phase="immediately before isolation-receipt verification",
    )
    if material_before != admitted_material:
        raise ValueError("verifier material changed after admission")
    isolation = verify_isolation_receipt_v0_9(
        isolation_payload,
        trusted_executor=runner,
        command_engine_path=engine,
        arguments=arguments,
        code_bundle_path=root,
        input_artifact_paths=inputs,
        working_directory=work,
        expected_output_relative_paths={"verification_result": VERIFIER_RESULT_FILENAME},
        timeout_seconds=DEFAULT_RESOURCE_LIMITS.cpu_seconds,
        resource_limits=DEFAULT_RESOURCE_LIMITS,
    )
    material_after = _measure_frozen_verifier_material(
        scope=scope,
        repository_root=repository_root,
        material=material,
        frozen_snapshot=frozen_snapshot,
        phase="immediately after isolation-receipt verification",
    )
    if material_after != material_before:
        raise ValueError("verifier material changed across isolation-receipt verification")
    _assert_isolation_receipt_binds_frozen_material(
        isolation,
        bundle_root=root,
        frozen_snapshot=frozen_snapshot,
        isolation_code_bundle_sha256=isolation_code_bundle_sha256,
    )
    result_payload, result_artifact_hash, result_content_hash = _stable_json_object(
        result,
        label=f"{scope} verifier result",
    )
    if len(isolation.output_artifacts) != 1:
        raise ValueError("isolated verifier receipt must bind exactly one result")
    output = isolation.output_artifacts[0]
    if output.label != "verification_result" or output.content_sha256 != result_artifact_hash:
        raise ValueError("isolated verifier receipt does not bind the result bytes")
    request_after = _stable_json_object(
        request,
        label=f"{scope} verifier request after execution verification",
    )
    isolation_after = _stable_json_object(
        paths.isolation_receipt_path,
        label=f"{scope} verifier isolation receipt after execution verification",
    )
    result_after = _stable_json_object(
        result,
        label=f"{scope} verifier result after execution verification",
    )
    if request_after != (request_payload, request_artifact_hash, request_content_hash):
        raise ValueError("isolated verifier request changed during verification")
    if isolation_after != (
        isolation_payload,
        isolation_artifact_hash,
        isolation_content_hash,
    ):
        raise ValueError("isolated verifier receipt changed during verification")
    if result_after != (result_payload, result_artifact_hash, result_content_hash):
        raise ValueError("isolated verifier result changed during verification")
    binding = IsolatedVerifierExecutionBindingV10(
        scope=scope,
        freeze_body_sha256=freeze.freeze_body_sha256,
        verifier_bundle_content_sha256=frozen_snapshot.bundle_content_sha256,
        verifier_entrypoint_bytes_sha256=frozen_snapshot.entrypoint_bytes_sha256,
        verifier_engine_bytes_sha256=frozen_snapshot.engine_bytes_sha256,
        verifier_config_bytes_sha256=frozen_snapshot.config_bytes_sha256,
        verifier_material_before=material_before,
        verifier_material_after=material_after,
        isolation_code_bundle_sha256=isolation_code_bundle_sha256,
        request_artifact_sha256=request_artifact_hash,
        request_content_sha256=request_content_hash,
        result_artifact_sha256=result_artifact_hash,
        result_content_sha256=result_content_hash,
        isolation_receipt_artifact_sha256=isolation_artifact_hash,
        isolation_receipt_content_sha256=isolation_content_hash,
        runner_key_id=runner.key_id,
        runner_public_key_sha256=runner.public_key_sha256,
        started_at_utc=isolation.started_at_utc,
        finished_at_utc=isolation.finished_at_utc,
        formal_isolation_verified=True,
    )
    return result_payload, binding


@dataclass(frozen=True, slots=True)
class CanonicalExecutionRawInputsV10:
    payload: Mapping[str, Any]
    bundle_paths_by_arm: Mapping[str, Path]
    visible_input_paths_by_episode: Mapping[str, Path]
    sealed_opening_artifact_path: Path
    frozen_manifest_artifact_path: Path
    producer_run_artifact_path: Path
    gate_a_report_artifact_path: Path
    isolation_working_directories_by_task: Mapping[tuple[str, str], Path]
    verifier_execution: IsolatedVerifierExecutionPathsV10


class _RecordedPrerequisiteVerifier:
    def __init__(self, record: VerifiedExecutionPrerequisitesV09, implementation: str) -> None:
        self._record = record
        self._implementation = implementation

    @property
    def implementation_sha256(self) -> str:
        return self._implementation

    def verify(self, **_: Any) -> VerifiedExecutionPrerequisitesV09:
        return self._record


def _canonical_verifier_inputs(
    inputs: CanonicalExecutionRawInputsV10,
) -> dict[str, Path]:
    result = {
        "frozen_manifest": inputs.frozen_manifest_artifact_path,
        "producer_run": inputs.producer_run_artifact_path,
        "gate_a_report": inputs.gate_a_report_artifact_path,
        "sealed_opening": inputs.sealed_opening_artifact_path,
    }
    result.update(
        {
            f"visible_{index:06d}": path
            for index, path in enumerate(inputs.visible_input_paths_by_episode.values())
        }
    )
    return result


def _verify_canonical_execution(
    *,
    inputs: CanonicalExecutionRawInputsV10,
    freeze: ExternalVerificationFreezeV10,
    live_inputs: ExternalVerificationFreezeLiveInputsV10,
    opening: SealedGateBOpeningV09,
    opening_content_sha256: str,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    gate_a_report_content_sha256: str,
    expected_frozen_bundles: Mapping[str, str],
    consumption_head: OpeningConsumptionLedgerHeadV09,
    canonical_runner: Ed25519AttestationVerifier,
    aggregate_executor: Ed25519AttestationVerifier,
) -> tuple[
    CanonicalPerEpisodeExecutionArtifactV09,
    str,
    IsolatedVerifierExecutionBindingV10,
]:
    raw = dict(inputs.payload)
    canonical_content_hash = raw.pop("content_sha256", None)
    if not isinstance(canonical_content_hash, str) or content_sha256(raw) != canonical_content_hash:
        raise ValueError("canonical execution content hash mismatch")
    preview = CanonicalPerEpisodeExecutionArtifactV09.model_validate(raw)
    sealed = recompute_sealed_visible_episode_inputs_v0_9(opening)
    if preview.episode_ids != sealed.episode_ids:
        raise ValueError("canonical execution episode ids differ from sealed holdout")
    if tuple(inputs.bundle_paths_by_arm) != EXPECTED_ARMS:
        raise ValueError("canonical bundle paths lack exact ordered arm coverage")
    if tuple(inputs.visible_input_paths_by_episode) != sealed.episode_ids:
        raise ValueError("canonical visible-input paths lack exact sealed episode order")
    expected_bundles = dict(expected_frozen_bundles)
    if tuple(expected_bundles) != EXPECTED_ARMS:
        raise ValueError("frozen implementation bundles lack exact ordered arm coverage")
    if preview.verified_prerequisites.arm_implementation_bundle_sha256 != expected_bundles:
        raise ValueError("canonical aggregate substituted the frozen implementation set")
    expected_manifests = {
        row.arm: row.manifest_content_sha256 for row in preview.arm_bundle_bindings
    }
    request = IsolatedVerifierRequestV10(
        scope=CANONICAL_SCOPE,
        freeze_body_sha256=freeze.freeze_body_sha256,
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        verifier_material_snapshot=freeze.body.canonical_verifier,
        isolation_code_bundle_sha256=_isolation_bundle_sha256_from_snapshot(
            freeze.body.canonical_verifier
        ),
        evidence_bindings={
            "gate_a_report_content_sha256": gate_a_report_content_sha256,
            "sealed_opening_content_sha256": opening_content_sha256,
            "opening_attempt_id": opening.opening_attempt_id,
            "opening_consumption_head_sha256": consumption_head.head_sha256,
            "execution_id": preview.execution_id,
            "episode_ids": preview.episode_ids,
            "arm_implementation_bundle_sha256": expected_bundles,
            "bundle_manifest_content_sha256_by_arm": expected_manifests,
            "sealed_visible_input_artifact_sha256_by_episode": dict(
                sealed.artifact_sha256_by_episode
            ),
            "sealed_visible_episode_content_sha256_by_episode": dict(
                sealed.episode_content_sha256_by_episode
            ),
        },
    )
    result_payload, execution_binding = _verify_isolated_verifier_execution(
        scope=CANONICAL_SCOPE,
        freeze=freeze,
        live_inputs=live_inputs,
        runner=canonical_runner,
        paths=inputs.verifier_execution,
        expected_request=request,
        verifier_input_paths=_canonical_verifier_inputs(inputs),
    )
    prerequisite_raw = dict(result_payload)
    prerequisite_content_hash = prerequisite_raw.pop("content_sha256", None)
    if (
        not isinstance(prerequisite_content_hash, str)
        or content_sha256(prerequisite_raw) != prerequisite_content_hash
    ):
        raise ValueError("canonical verifier result content hash mismatch")
    prerequisites = VerifiedExecutionPrerequisitesV09.model_validate(prerequisite_raw)
    if prerequisite_content_hash != prerequisites.content_sha256:
        raise ValueError("canonical verifier result uses a noncanonical envelope")
    frozen_implementation = freeze.body.canonical_verifier.bundle_content_sha256
    verified = verify_canonical_per_episode_execution_artifact_v0_9(
        inputs.payload,
        expected_execution_id=preview.execution_id,
        expected_episode_ids=sealed.episode_ids,
        bundle_paths_by_arm=inputs.bundle_paths_by_arm,
        expected_bundle_sha256_by_arm=expected_bundles,
        expected_bundle_manifest_content_sha256_by_arm=expected_manifests,
        visible_input_paths_by_episode=inputs.visible_input_paths_by_episode,
        expected_visible_input_sha256_by_episode=sealed.artifact_sha256_by_episode,
        sealed_opening_artifact_path=inputs.sealed_opening_artifact_path,
        expected_sealed_opening_artifact_sha256=artifact_content_sha256_v0_9(
            inputs.sealed_opening_artifact_path
        ),
        frozen_manifest_artifact_path=inputs.frozen_manifest_artifact_path,
        producer_run_artifact_path=inputs.producer_run_artifact_path,
        gate_a_report_artifact_path=inputs.gate_a_report_artifact_path,
        trusted_prerequisite_verifier=_RecordedPrerequisiteVerifier(
            prerequisites,
            frozen_implementation,
        ),
        trusted_prerequisite_verifier_identity=canonical_runner,
        expected_prerequisite_verifier_implementation_sha256=frozen_implementation,
        isolation_working_directories_by_task=inputs.isolation_working_directories_by_task,
        trusted_isolated_receipt_verifier=canonical_runner,
        isolation_receipt_verifier=verify_isolation_receipt_v0_9,
        trusted_enrolled_executor=aggregate_executor,
    )
    if (
        prerequisites.immutable_manifest_sha256 != immutable_manifest_sha256
        or prerequisites.producer_run_id != producer_run_id
        or prerequisites.gate_a_report_content_sha256 != gate_a_report_content_sha256
        or prerequisites.sealed_opening_content_sha256 != opening_content_sha256
        or prerequisites.opening_attempt_id != opening.opening_attempt_id
    ):
        raise ValueError("canonical prerequisites are stale, cross-run, or substituted")
    task_starts = tuple(row.isolation.receipt.started_at_utc for row in verified.task_receipts)
    task_finishes = tuple(row.isolation.receipt.finished_at_utc for row in verified.task_receipts)
    if (
        consumption_head.consumed_at_utc >= execution_binding.started_at_utc
        or execution_binding.finished_at_utc >= min(task_starts)
    ):
        raise ValueError("canonical execution did not follow consumption and prerequisite check")
    if max(task_finishes) <= min(task_starts):
        raise ValueError("canonical execution task timestamps are malformed")
    return verified, canonical_content_hash, execution_binding


@dataclass(frozen=True, slots=True)
class FidelityRawInputsV10:
    artifact_paths: FidelityArtifactPathsV09
    verifier_execution: IsolatedVerifierExecutionPathsV10


def _fidelity_paths_with_frozen_runner(
    paths: FidelityArtifactPathsV09,
    *,
    runner: Ed25519AttestationVerifier,
) -> FidelityArtifactPathsV09:
    if tuple(paths.method_evidence_artifacts_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("fidelity method paths lack exact ordered six-method coverage")
    if tuple(paths.isolation_receipt_verifications_by_arm) != EXTERNAL_METHOD_ARMS:
        raise ValueError("fidelity isolation paths lack exact ordered six-method coverage")
    normalized: dict[str, tuple[FidelityIsolationReceiptVerificationV09, ...]] = {}
    for arm in EXTERNAL_METHOD_ARMS:
        rows: list[FidelityIsolationReceiptVerificationV09] = []
        for row in paths.isolation_receipt_verifications_by_arm[arm]:
            if (
                row.trusted_executor.key_id != runner.key_id
                or row.trusted_executor.public_key_base64 != runner.public_key_base64
                or row.trusted_executor.public_key_sha256 != runner.public_key_sha256
            ):
                raise AttestationError("fidelity receipt uses a caller-selected runner")
            rows.append(row)
        normalized[arm] = tuple(rows)
    return FidelityArtifactPathsV09(
        raw_fidelity_report=paths.raw_fidelity_report,
        method_evidence_artifacts_by_arm=dict(paths.method_evidence_artifacts_by_arm),
        isolation_receipt_verifications_by_arm=normalized,
    )


def _fidelity_verifier_inputs(paths: FidelityArtifactPathsV09) -> dict[str, Path]:
    result: dict[str, Path] = {"raw_fidelity_report": paths.raw_fidelity_report}
    for index, arm in enumerate(EXTERNAL_METHOD_ARMS):
        result[f"method_{index:02d}"] = paths.method_evidence_artifacts_by_arm[arm]
        for receipt_index, row in enumerate(paths.isolation_receipt_verifications_by_arm[arm]):
            result[f"receipt_{index:02d}_{receipt_index:04d}"] = row.receipt_path
    return result


def _verify_fidelity(
    *,
    inputs: FidelityRawInputsV10,
    freeze: ExternalVerificationFreezeV10,
    live_inputs: ExternalVerificationFreezeLiveInputsV10,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    expected_implementation_bundles: Mapping[str, str],
    expected_primary_sources: Mapping[str, str],
    fidelity_runner: Ed25519AttestationVerifier,
) -> tuple[
    VerifiedSixMethodFidelityV09,
    str,
    FidelityArtifactSnapshotV09,
    IsolatedVerifierExecutionBindingV10,
]:
    paths = _fidelity_paths_with_frozen_runner(
        inputs.artifact_paths,
        runner=fidelity_runner,
    )
    _stable_json_object(paths.raw_fidelity_report, label="raw fidelity report")
    before = snapshot_fidelity_artifacts_v0_9(paths)
    identity = _frozen_verifier_identity(freeze, scope=FIDELITY_SCOPE)
    request = IsolatedVerifierRequestV10(
        scope=FIDELITY_SCOPE,
        freeze_body_sha256=freeze.freeze_body_sha256,
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        verifier_material_snapshot=freeze.body.fidelity_verifier,
        isolation_code_bundle_sha256=_isolation_bundle_sha256_from_snapshot(
            freeze.body.fidelity_verifier
        ),
        evidence_bindings={
            "artifact_snapshot": before.model_dump(mode="json"),
            "implementation_bundle_sha256_by_arm": dict(expected_implementation_bundles),
            "primary_source_sha256_by_arm": dict(expected_primary_sources),
            "verifier_identity": identity.model_dump(mode="json"),
        },
    )
    result_payload, execution_binding = _verify_isolated_verifier_execution(
        scope=FIDELITY_SCOPE,
        freeze=freeze,
        live_inputs=live_inputs,
        runner=fidelity_runner,
        paths=inputs.verifier_execution,
        expected_request=request,
        verifier_input_paths=_fidelity_verifier_inputs(paths),
    )
    after = snapshot_fidelity_artifacts_v0_9(paths)
    if after != before:
        raise ValueError("fidelity raw evidence changed during isolated verification")
    for arm in EXTERNAL_METHOD_ARMS:
        for index, row in enumerate(paths.isolation_receipt_verifications_by_arm[arm]):
            receipt_payload, _, _ = _stable_json_object(
                row.receipt_path,
                label=f"{arm} fidelity isolation receipt {index}",
            )
            receipt_raw = dict(receipt_payload)
            receipt_raw.pop("content_sha256")
            receipt = IsolationExecutionReceiptV09.model_validate(receipt_raw)
            if (
                receipt.started_at_utc <= freeze.body.frozen_at_utc
                or receipt.finished_at_utc > execution_binding.started_at_utc
            ):
                raise ValueError(
                    "native/adaptation isolation evidence was not produced after freeze "
                    "and before fidelity verification"
                )
    record = verify_verified_six_method_fidelity_v0_9(
        result_payload,
        expected_snapshot=before,
        expected_immutable_manifest_sha256=immutable_manifest_sha256,
        expected_producer_run_id=producer_run_id,
        expected_implementation_bundle_sha256_by_arm=expected_implementation_bundles,
        expected_primary_source_sha256_by_arm=expected_primary_sources,
        expected_verifier_identity=identity,
        trusted_reviewer=fidelity_runner,
    )
    result_content_hash = _payload_content_hash(
        result_payload,
        label="six-method fidelity verifier result",
    )
    if not (
        execution_binding.started_at_utc
        <= record.verified_at_utc
        <= execution_binding.finished_at_utc
    ):
        raise ValueError("fidelity decision timestamp is outside its isolated execution")
    return record, result_content_hash, before, execution_binding


class ExternalConfirmationBlockerReportV10(ContractModel):
    protocol: Literal["structure-two-external-confirmation-blocker@1.0"] = (
        "structure-two-external-confirmation-blocker@1.0"
    )
    status: Literal["BLOCKED_FAIL_CLOSED"] = "BLOCKED_FAIL_CLOSED"
    stage: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    external_method_efficacy_comparison_allowed: Literal[False] = False


class ExternalConfirmationBlockedError(ValueError):
    def __init__(self, *, stage: str, reason: str) -> None:
        self.report = ExternalConfirmationBlockerReportV10(stage=stage, reason=reason)
        super().__init__(f"{stage}: {reason}")


def _require_current_formal_gate_b(record: Any) -> None:
    if (
        getattr(record, "gate_b_protocol_id", None) != CURRENT_GATE_B_PROTOCOL_ID
        or getattr(record, "formal_gate_b_passed", False) is not True
        or getattr(record, "protocol_invalidated", False) is True
    ):
        raise ExternalConfirmationBlockedError(
            stage="sealed_dual_gate_b",
            reason=(
                "Gate B v0.7 is invalidated and comparator-typed v0.8 has no formal "
                "raw execution receipt; combined authorization remains closed"
            ),
        )


class FreezeCommitmentLinkV10(ContractModel):
    """Signed hash edge missing from the legacy v0.9 commitment schema."""

    protocol: Literal["structure-two-freeze-commitment-link@1.0"] = (
        "structure-two-freeze-commitment-link@1.0"
    )
    status: Literal["FREEZE_COMMITMENT_CRYPTOGRAPHICALLY_LINKED"] = (
        "FREEZE_COMMITMENT_CRYPTOGRAPHICALLY_LINKED"
    )
    external_verification_freeze_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_verification_freeze_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_verification_freeze_ledger_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_commitment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: StrictInt = Field(ge=0)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    frozen_at_utc: datetime
    committed_at_utc: datetime
    custodian: PublicKeyBindingV10
    enrollment_authority: PublicKeyBindingV10
    custodian_attestation: Attestation | None = None
    authority_attestation: Attestation | None = None
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_link(self) -> Self:
        _validate_utc(self.frozen_at_utc, label="linked freeze time")
        _validate_utc(self.committed_at_utc, label="linked commitment time")
        if self.commitment_ledger_sequence != self.freeze_ledger_sequence + 1:
            raise ValueError("linked commitment must immediately extend the freeze")
        if self.committed_at_utc <= self.frozen_at_utc:
            raise ValueError("linked commitment time must follow the freeze")
        if self.custodian.public_key_sha256 == self.enrollment_authority.public_key_sha256:
            raise ValueError("link custodian and enrollment authority must be independent")
        if self.claim_boundary != FREEZE_COMMITMENT_LINK_CLAIM_BOUNDARY:
            raise ValueError("freeze-commitment link claim boundary was changed")
        return self


class FreezeCommitmentLinkSigningRequestV10(ContractModel):
    protocol: Literal["structure-two-freeze-commitment-link-detached-request@1.0"] = (
        "structure-two-freeze-commitment-link-detached-request@1.0"
    )
    artifact_protocol: Literal["structure-two-freeze-commitment-link@1.0"] = (
        "structure-two-freeze-commitment-link@1.0"
    )
    role: Literal["custodian", "enrollment_authority"]
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
            raise ValueError("freeze-commitment request key hash mismatch")
        if content_sha256(self.payload) != self.payload_sha256:
            raise ValueError("freeze-commitment request payload hash mismatch")
        return self


def _freeze_commitment_role_payload(record: FreezeCommitmentLinkV10) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset({"custodian_attestation", "authority_attestation"}),
    )


def _freeze_commitment_authority_payload(
    record: FreezeCommitmentLinkV10,
) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"authority_attestation"}))


def _freeze_commitment_request(
    *,
    role: Literal["custodian", "enrollment_authority"],
    domain: str,
    binding: PublicKeyBindingV10,
    payload: Mapping[str, Any],
) -> FreezeCommitmentLinkSigningRequestV10:
    materialized = dict(payload)
    return FreezeCommitmentLinkSigningRequestV10(
        role=role,
        domain=domain,
        expected_key_id=binding.key_id,
        expected_public_key_base64=binding.public_key_base64,
        expected_public_key_sha256=binding.public_key_sha256,
        payload=materialized,
        payload_sha256=content_sha256(materialized),
    )


def prepare_freeze_commitment_link_v1_0(
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
) -> FreezeCommitmentLinkV10:
    recomputed_freeze_hash = content_sha256(external_verification_freeze.model_dump(mode="json"))
    if external_verification_freeze_content_sha256 != recomputed_freeze_hash:
        raise ValueError("freeze-commitment link received a mutated external freeze")
    recomputed_commitment_hash = content_sha256(verified_commitment.record.model_dump(mode="json"))
    if verified_commitment.content_sha256 != recomputed_commitment_hash:
        raise ValueError("freeze-commitment link received a mutated commitment")
    freeze = external_verification_freeze.body
    commitment = verified_commitment.record
    if (
        commitment.ledger_identifier != freeze.freeze_ledger_identifier
        or commitment.freeze_ledger_sequence != freeze.freeze_ledger_sequence
        or commitment.commitment_ledger_sequence != freeze.freeze_ledger_sequence + 1
        or commitment.freeze_completed_at_utc != freeze.frozen_at_utc
        or commitment.committed_at_utc <= freeze.frozen_at_utc
    ):
        raise ValueError("sealed commitment does not immediately follow the exact freeze context")
    return FreezeCommitmentLinkV10(
        external_verification_freeze_content_sha256=recomputed_freeze_hash,
        external_verification_freeze_body_sha256=(external_verification_freeze.freeze_body_sha256),
        external_verification_freeze_ledger_head_sha256=(
            external_verification_freeze.freeze_ledger_head_sha256
        ),
        sealed_commitment_content_sha256=recomputed_commitment_hash,
        immutable_manifest_sha256=commitment.immutable_manifest_sha256,
        producer_run_id=commitment.producer_run_id,
        ledger_identifier=commitment.ledger_identifier,
        freeze_ledger_sequence=commitment.freeze_ledger_sequence,
        commitment_ledger_sequence=commitment.commitment_ledger_sequence,
        frozen_at_utc=freeze.frozen_at_utc,
        committed_at_utc=commitment.committed_at_utc,
        custodian=freeze.party_keys.custodian,
        enrollment_authority=freeze.party_keys.enrollment_authority,
        claim_boundary=FREEZE_COMMITMENT_LINK_CLAIM_BOUNDARY,
    )


def freeze_commitment_link_custodian_signing_request_v1_0(
    prepared: FreezeCommitmentLinkV10,
) -> FreezeCommitmentLinkSigningRequestV10:
    if prepared.custodian_attestation is not None or prepared.authority_attestation is not None:
        raise ValueError("freeze-commitment link signing requires an unsigned record")
    return _freeze_commitment_request(
        role="custodian",
        domain=FREEZE_COMMITMENT_LINK_CUSTODIAN_DOMAIN,
        binding=prepared.custodian,
        payload=_freeze_commitment_role_payload(prepared),
    )


def sign_freeze_commitment_link_request_v1_0(
    request: FreezeCommitmentLinkSigningRequestV10,
    *,
    signer: Ed25519AttestationSigner,
) -> Attestation:
    verifier = signer.verifier()
    if (
        verifier.key_id != request.expected_key_id
        or verifier.public_key_base64 != request.expected_public_key_base64
        or verifier.public_key_sha256 != request.expected_public_key_sha256
    ):
        raise AttestationError("freeze-commitment request reached the wrong signer")
    if content_sha256(request.payload) != request.payload_sha256:
        raise ValueError("freeze-commitment request changed before signing")
    return signer.sign(request.domain, request.payload)


def freeze_commitment_link_authority_signing_request_v1_0(
    prepared: FreezeCommitmentLinkV10,
    *,
    custodian_attestation: Attestation,
) -> FreezeCommitmentLinkSigningRequestV10:
    if prepared.custodian_attestation is not None or prepared.authority_attestation is not None:
        raise ValueError("freeze-commitment authority request requires an unsigned record")
    custodian = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=prepared.custodian.key_id,
        public_key_base64=prepared.custodian.public_key_base64,
    )
    if custodian.public_key_sha256 != prepared.custodian.public_key_sha256:
        raise AttestationError("freeze-commitment custodian key binding is malformed")
    custodian.verify(
        FREEZE_COMMITMENT_LINK_CUSTODIAN_DOMAIN,
        _freeze_commitment_role_payload(prepared),
        custodian_attestation,
    )
    custodian_signed = prepared.model_copy(update={"custodian_attestation": custodian_attestation})
    return _freeze_commitment_request(
        role="enrollment_authority",
        domain=FREEZE_COMMITMENT_LINK_AUTHORITY_DOMAIN,
        binding=prepared.enrollment_authority,
        payload=_freeze_commitment_authority_payload(custodian_signed),
    )


def verify_freeze_commitment_link_v1_0(
    payload: Mapping[str, Any],
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
) -> FreezeCommitmentLinkV10:
    _validate_utc(verification_time_utc, label="freeze-commitment verification time")
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("freeze-commitment link content hash mismatch")
    record = FreezeCommitmentLinkV10.model_validate(raw)
    if raw != record.model_dump(mode="json"):
        raise ValueError("freeze-commitment link encoding is noncanonical")
    if record.committed_at_utc > verification_time_utc:
        raise ValueError("freeze-commitment link is in the verifier's future")
    expected = prepare_freeze_commitment_link_v1_0(
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        verified_commitment=verified_commitment,
    )
    excluded = {"custodian_attestation", "authority_attestation"}
    if record.model_dump(mode="python", exclude=excluded) != expected.model_dump(
        mode="python", exclude=excluded
    ):
        raise ValueError("freeze-commitment link substituted one side of the hash edge")
    _assert_verifier(record.custodian, trusted_custodian, label="link custodian")
    _assert_verifier(
        record.enrollment_authority,
        trusted_enrollment_authority,
        label="link enrollment authority",
    )
    trusted_custodian.verify(
        FREEZE_COMMITMENT_LINK_CUSTODIAN_DOMAIN,
        _freeze_commitment_role_payload(record),
        record.custodian_attestation,
    )
    trusted_enrollment_authority.verify(
        FREEZE_COMMITMENT_LINK_AUTHORITY_DOMAIN,
        _freeze_commitment_authority_payload(record),
        record.authority_attestation,
    )
    return record


def finalize_freeze_commitment_link_v1_0(
    prepared: FreezeCommitmentLinkV10,
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    custodian_attestation: Attestation,
    authority_attestation: Attestation,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
) -> dict[str, Any]:
    if prepared.custodian_attestation is not None or prepared.authority_attestation is not None:
        raise ValueError("freeze-commitment finalization requires the unsigned record")
    signed = prepared.model_copy(
        update={
            "custodian_attestation": custodian_attestation,
            "authority_attestation": authority_attestation,
        }
    )
    payload = _content_bound_payload(signed)
    verify_freeze_commitment_link_v1_0(
        payload,
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        verified_commitment=verified_commitment,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
        verification_time_utc=verification_time_utc,
    )
    return payload


def _dual_gate_b_canonical_sequence(record: Any) -> int:
    value = record.canonical_execution_ledger_sequence
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("dual Gate-B canonical ledger sequence is malformed")
    return value


def _dual_gate_b_sequence(record: Any) -> int:
    value = record.gate_b_ledger_sequence
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("dual Gate-B ledger sequence is malformed")
    return value


def _dual_gate_b_time(record: Any) -> datetime:
    value = record.gate_b_scored_at_utc
    if not isinstance(value, datetime):
        raise ValueError("dual Gate-B completion time is malformed")
    _validate_utc(value, label="dual Gate-B completion")
    return value


@dataclass(frozen=True, slots=True)
class ExternalConfirmationVerificationInputsV10:
    """Only raw artifacts, live paths, and externally rooted verifier state."""

    canonical_gate_b_draft: Mapping[str, Any]
    gate_a_spec: Mapping[str, Any]
    source_register: Mapping[str, Any]
    trust_anchor_registry: Mapping[str, Any]
    externally_frozen_manifest: Mapping[str, Any]
    external_verification_freeze_payload: Mapping[str, Any]
    external_verification_live_inputs: ExternalVerificationFreezeLiveInputsV10
    trusted_enrollment_authority: Ed25519AttestationVerifier
    verification_time_utc: datetime
    gate_a_report: Mapping[str, Any]
    gate_a_artifact_paths: GateAArtifactPathsV06
    sealed_commitment_payload: Mapping[str, Any]
    freeze_commitment_link_payload: Mapping[str, Any]
    gate_a_lifecycle_payload: Mapping[str, Any]
    sealed_opening_payload: Mapping[str, Any]
    opening_consumption_payload: Mapping[str, Any]
    opening_consumption_store: FileAuthoritativeOpeningConsumptionStoreV09
    expected_opening_consumption_store_identity: AuthoritativeLedgerStoreIdentityV09
    canonical_execution: CanonicalExecutionRawInputsV10
    fidelity: FidelityRawInputsV10
    frozen_dual_gate_b_config: Mapping[str, Any]
    canonical_dual_readout_execution_payload: Mapping[str, Any]
    dual_readout_isolation_verification_inputs_by_task: Mapping[
        tuple[str, str], DualReadoutIsolationVerificationInputsV10
    ]
    sealed_dual_gate_b_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedExternalConfirmationChainV10:
    registry: TrustAnchorRegistryV06
    role_verifiers: Mapping[str, Ed25519AttestationVerifier]
    frozen_manifest: FrozenGateBManifestV06
    frozen_manifest_content_sha256: str
    external_verification_freeze: ExternalVerificationFreezeV10
    external_verification_freeze_content_sha256: str
    gate_a_report: GateAReportV06
    gate_a_report_content_sha256: str
    verified_commitment: VerifiedSealedGateBCommitmentV09
    freeze_commitment_link: FreezeCommitmentLinkV10
    freeze_commitment_link_content_sha256: str
    verified_gate_a_lifecycle: VerifiedGateALifecycleCompletionV09
    gate_a_lifecycle_content_sha256: str
    opening_context: SealedGateBOpeningVerificationContextV09
    opening: SealedGateBOpeningV09
    opening_content_sha256: str
    authoritative_ledger_store_identity: AuthoritativeLedgerStoreIdentityV09
    consumption_head: OpeningConsumptionLedgerHeadV09
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09
    canonical_execution_content_sha256: str
    canonical_verifier_execution: IsolatedVerifierExecutionBindingV10
    fidelity: VerifiedSixMethodFidelityV09
    fidelity_content_sha256: str
    fidelity_snapshot: FidelityArtifactSnapshotV09
    fidelity_verifier_execution: IsolatedVerifierExecutionBindingV10
    canonical_dual_readout_execution: CanonicalDualReadoutExecutionV10
    canonical_dual_readout_execution_content_sha256: str
    sealed_dual_gate_b: SealedDualGateBReceiptV10
    sealed_dual_gate_b_content_sha256: str
    trust_anchor_registry_content_sha256: str


def _assert_file_equals_payload(
    path: Path,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> None:
    loaded, _, _ = _stable_json_object(path, label=label)
    if loaded != dict(payload):
        raise ValueError(f"{label} path differs from supplied signed artifact")


def _verify_chain_prefix(
    inputs: ExternalConfirmationVerificationInputsV10,
) -> tuple[
    TrustAnchorRegistryV06,
    Mapping[str, Ed25519AttestationVerifier],
    FrozenGateBManifestV06,
    str,
    ExternalVerificationFreezeV10,
    str,
]:
    _validate_utc(inputs.verification_time_utc, label="verification time")
    registry, role_verifiers = verify_trust_anchor_registry_v0_6(
        inputs.trust_anchor_registry,
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
    )
    registry_hash = _payload_content_hash(
        inputs.trust_anchor_registry,
        label="trust-anchor registry",
    )
    frozen = verify_frozen_gate_b_manifest_v0_6(
        inputs.externally_frozen_manifest,
        development_draft=inputs.canonical_gate_b_draft,
        source_register=inputs.source_register,
        gate_a_spec=inputs.gate_a_spec,
        trust_anchor_registry=registry,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=inputs.trusted_enrollment_authority,
    )
    frozen_hash = _payload_content_hash(
        inputs.externally_frozen_manifest,
        label="externally frozen v0.6 manifest",
    )
    expected_freeze_sequence = frozen.freeze_ledger_sequence + 1
    freeze = verify_external_verification_freeze_v1_0(
        inputs.external_verification_freeze_payload,
        live_inputs=inputs.external_verification_live_inputs,
        trust_anchor_registry=inputs.trust_anchor_registry,
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
        expected_previous_ledger_head_sha256=frozen_hash,
        expected_freeze_ledger_sequence=expected_freeze_sequence,
        verification_time_utc=inputs.verification_time_utc,
    )
    if (
        freeze.body.freeze_ledger_identifier != frozen.freeze_ledger_identifier
        or freeze.body.freeze_ledger_sequence != expected_freeze_sequence
        or freeze.body.previous_ledger_head_sha256 != frozen_hash
        or freeze.body.frozen_at_utc <= frozen.frozen_at_utc
    ):
        raise ValueError("v1.0 freeze does not immediately extend the v0.6 frozen manifest")
    if freeze.body.trust_anchor_registry_identifier != registry.registry_identifier:
        raise AttestationError("v1.0 freeze substituted the v0.6 trust registry")
    if freeze.body.producer_source.content_sha256 != frozen.producer_source_bundle_sha256:
        raise ValueError("v0.6 manifest and live-byte freeze disagree on producer source")
    if freeze.body.gate_a_spec.stable_json_content_sha256 != frozen.gate_a_spec_content_sha256:
        raise ValueError("v0.6 manifest and live-byte freeze disagree on Gate-A spec")
    return registry, role_verifiers, frozen, frozen_hash, freeze, registry_hash


def _verify_external_confirmation_chain_impl_v1_0(
    inputs: ExternalConfirmationVerificationInputsV10,
) -> VerifiedExternalConfirmationChainV10:
    (
        registry,
        role_verifiers,
        frozen,
        frozen_hash,
        freeze,
        registry_hash,
    ) = _verify_chain_prefix(inputs)
    freeze_hash = _payload_content_hash(
        inputs.external_verification_freeze_payload,
        label="external verification freeze",
    )
    runners = runner_verifiers_from_external_verification_freeze_v1_0(freeze)
    canonical_runner = runners[CANONICAL_SCOPE]
    fidelity_runner = runners[FIDELITY_SCOPE]

    commitment = verify_sealed_gate_b_commitment_record_v0_9(
        inputs.sealed_commitment_payload,
        expected_immutable_manifest_sha256=frozen.immutable_manifest_sha256,
        expected_producer_run_id=frozen.preregistered_producer_run_id,
        expected_arm_implementation_bundle_sha256=frozen.arm_implementation_bundle_sha256,
        expected_ledger_identifier=freeze.body.freeze_ledger_identifier,
        expected_freeze_ledger_sequence=freeze.body.freeze_ledger_sequence,
        expected_freeze_completed_at_utc=freeze.body.frozen_at_utc,
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
        verification_time_utc=inputs.verification_time_utc,
    )
    if commitment.record.commitment_ledger_sequence != freeze.body.freeze_ledger_sequence + 1:
        raise ValueError("sealed commitment must immediately follow the v1.0 freeze")
    freeze_commitment_link = verify_freeze_commitment_link_v1_0(
        inputs.freeze_commitment_link_payload,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        verified_commitment=commitment,
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
        verification_time_utc=inputs.verification_time_utc,
    )
    freeze_commitment_link_hash = _payload_content_hash(
        inputs.freeze_commitment_link_payload,
        label="freeze-commitment link",
    )

    gate_a = verify_gate_a_report_v0_6(
        inputs.gate_a_report,
        gate_a_spec=inputs.gate_a_spec,
        frozen_manifest=frozen,
        trust_anchor_registry=registry,
        artifact_paths=inputs.gate_a_artifact_paths,
        producer_source_bundle_sha256=freeze.body.producer_source.content_sha256,
        expected_arm_implementation_bundles=frozen.arm_implementation_bundle_sha256,
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
    )
    gate_a_hash = _payload_content_hash(inputs.gate_a_report, label="Gate-A report")

    gate_a_lifecycle = verify_gate_a_lifecycle_completion_record_v0_9(
        inputs.gate_a_lifecycle_payload,
        verified_commitment=commitment,
        expected_verified_gate_a_report_content_sha256=gate_a_hash,
        expected_forbidden_seed_namespaces=freeze.body.forbidden_seed_namespaces,
        trusted_executor=role_verifiers["executor"],
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
    )
    if gate_a_lifecycle.record.gate_a_ledger_sequence != (
        commitment.record.commitment_ledger_sequence + 1
    ):
        raise ValueError("Gate A must immediately follow the sealed commitment")

    opening_raw = dict(inputs.sealed_opening_payload)
    opening_hash = opening_raw.pop("content_sha256", None)
    if not isinstance(opening_hash, str) or content_sha256(opening_raw) != opening_hash:
        raise ValueError("sealed Gate-B opening content hash mismatch")
    opening_preview = SealedGateBOpeningV09.model_validate(opening_raw)
    opening_context = build_sealed_gate_b_opening_context_v0_9(
        verified_commitment=commitment,
        verified_gate_a_lifecycle=gate_a_lifecycle,
        opening_ledger_sequence=opening_preview.opening_ledger_sequence,
        opened_at_utc=opening_preview.opened_at_utc,
    )
    opening = verify_sealed_gate_b_opening_v0_9(
        inputs.sealed_opening_payload,
        context=opening_context,
        trusted_custodian=role_verifiers["custodian"],
    )
    if opening.opening_ledger_sequence != gate_a_lifecycle.record.gate_a_ledger_sequence + 1:
        raise ValueError("sealed opening must immediately follow Gate A")

    if not isinstance(
        inputs.opening_consumption_store,
        FileAuthoritativeOpeningConsumptionStoreV09,
    ):
        raise TypeError("formal chain requires the concrete durable authoritative store")
    store = inputs.opening_consumption_store
    store_identity = store.identity
    if store_identity != inputs.expected_opening_consumption_store_identity:
        raise ValueError("authoritative consumption store identity was substituted")
    if (
        store_identity.ledger_identifier != opening.ledger_identifier
        or store_identity.authority_identifier != inputs.trusted_enrollment_authority.key_id
    ):
        raise ValueError("authoritative consumption store is cross-ledger or cross-authority")
    store_context = OpeningConsumptionStoreVerificationContextV09(
        opening_payload=inputs.sealed_opening_payload,
        opening_context=opening_context,
        trusted_opening_custodian=role_verifiers["custodian"],
        trusted_reviewer=role_verifiers["reviewer"],
        trusted_executor=role_verifiers["executor"],
        trusted_consumption_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
    )
    consumption_head = store.read_verified_current_consumption_head(
        inputs.opening_consumption_payload,
        verification=store_context,
    )
    if consumption_head.ledger_sequence != opening.opening_ledger_sequence + 1:
        raise ValueError("opening consumption must immediately follow the sealed opening")
    if consumption_head.consumed_at_utc <= opening.opened_at_utc:
        raise ValueError("opening consumption timestamp does not follow the opening")

    _assert_file_equals_payload(
        inputs.canonical_execution.frozen_manifest_artifact_path,
        inputs.externally_frozen_manifest,
        label="canonical frozen-manifest artifact",
    )
    _assert_file_equals_payload(
        inputs.canonical_execution.gate_a_report_artifact_path,
        inputs.gate_a_report,
        label="canonical Gate-A artifact",
    )
    _assert_file_equals_payload(
        inputs.canonical_execution.sealed_opening_artifact_path,
        inputs.sealed_opening_payload,
        label="canonical sealed-opening artifact",
    )
    canonical, canonical_hash, canonical_verifier_execution = _verify_canonical_execution(
        inputs=inputs.canonical_execution,
        freeze=freeze,
        live_inputs=inputs.external_verification_live_inputs,
        opening=opening,
        opening_content_sha256=opening_hash,
        immutable_manifest_sha256=frozen.immutable_manifest_sha256,
        producer_run_id=frozen.preregistered_producer_run_id,
        gate_a_report_content_sha256=gate_a_hash,
        expected_frozen_bundles=frozen.arm_implementation_bundle_sha256,
        consumption_head=consumption_head,
        canonical_runner=canonical_runner,
        aggregate_executor=role_verifiers["executor"],
    )

    source_hashes = _primary_source_hashes(inputs.source_register)
    fidelity_bundles = {
        arm: frozen.arm_implementation_bundle_sha256[arm] for arm in EXTERNAL_METHOD_ARMS
    }
    fidelity, fidelity_hash, fidelity_snapshot, fidelity_verifier_execution = _verify_fidelity(
        inputs=inputs.fidelity,
        freeze=freeze,
        live_inputs=inputs.external_verification_live_inputs,
        immutable_manifest_sha256=frozen.immutable_manifest_sha256,
        producer_run_id=frozen.preregistered_producer_run_id,
        expected_implementation_bundles=fidelity_bundles,
        expected_primary_sources=source_hashes,
        fidelity_runner=fidelity_runner,
    )
    if not (
        freeze.body.frozen_at_utc
        < fidelity_verifier_execution.started_at_utc
        <= fidelity.verified_at_utc
        <= fidelity_verifier_execution.finished_at_utc
        < commitment.record.committed_at_utc
    ):
        raise ValueError("six-method fidelity was not isolated after freeze and before commitment")

    # Rebuild the dual-readout execution from its content-bound raw payload and
    # verifier-owned per-task isolation paths before asking the formal Gate-B
    # verifier to rebuild it again.  No typed execution supplied by the caller
    # can cross this boundary.
    dual_execution = verify_canonical_dual_readout_execution_v1_0(
        inputs.canonical_dual_readout_execution_payload,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        canonical_execution=canonical,
        sealed_opening=opening,
        opening_consumption_head=consumption_head,
        frozen_v0_7_config=inputs.frozen_dual_gate_b_config,
        isolation_inputs_by_task=(inputs.dual_readout_isolation_verification_inputs_by_task),
        trusted_reviewer=role_verifiers["reviewer"],
        trusted_executor=role_verifiers["executor"],
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
    )
    dual_execution_hash = _payload_content_hash(
        inputs.canonical_dual_readout_execution_payload,
        label="canonical dual-readout execution",
    )
    dual_record = verify_sealed_dual_gate_b_receipt_v1_0(
        inputs.sealed_dual_gate_b_payload,
        canonical_dual_readout_execution_payload=(inputs.canonical_dual_readout_execution_payload),
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        canonical_execution=canonical,
        sealed_opening=opening,
        opening_consumption_head=consumption_head,
        frozen_v0_7_config=inputs.frozen_dual_gate_b_config,
        isolation_inputs_by_task=(inputs.dual_readout_isolation_verification_inputs_by_task),
        trusted_reviewer=role_verifiers["reviewer"],
        trusted_executor=role_verifiers["executor"],
        trusted_custodian=role_verifiers["custodian"],
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
        verification_time_utc=inputs.verification_time_utc,
    )
    _require_current_formal_gate_b(dual_record)
    dual_hash = _payload_content_hash(
        inputs.sealed_dual_gate_b_payload,
        label="formal sealed dual Gate-B receipt",
    )
    task_finish = max(row.isolation.receipt.finished_at_utc for row in canonical.task_receipts)
    dual_time = _dual_gate_b_time(dual_record)
    canonical_sequence = _dual_gate_b_canonical_sequence(dual_record)
    dual_sequence = _dual_gate_b_sequence(dual_record)
    if task_finish >= dual_execution.canonical_execution_completed_at_utc:
        raise ValueError("dual-readout canonical execution predates a canonical task")
    if dual_execution.canonical_execution_completed_at_utc >= dual_time:
        raise ValueError("sealed dual Gate B did not follow canonical execution")
    if dual_time > inputs.verification_time_utc:
        raise ValueError("sealed dual Gate B is in the verifier's future")
    if canonical_sequence != consumption_head.ledger_sequence + 1:
        raise ValueError("canonical execution ledger must immediately extend consumption")
    if dual_sequence != canonical_sequence + 1:
        raise ValueError("sealed dual Gate B must immediately follow canonical execution")

    # Durable state and all frozen live bytes are checked again after every
    # downstream verifier.  This closes stale-head and start/end TOCTOU paths.
    current_head = store.read_verified_current_consumption_head(
        inputs.opening_consumption_payload,
        verification=store_context,
    )
    if current_head != consumption_head:
        raise ValueError("authoritative consumption head changed during chain verification")
    freeze_after = verify_external_verification_freeze_v1_0(
        inputs.external_verification_freeze_payload,
        live_inputs=inputs.external_verification_live_inputs,
        trust_anchor_registry=inputs.trust_anchor_registry,
        trusted_enrollment_authority=inputs.trusted_enrollment_authority,
        expected_previous_ledger_head_sha256=frozen_hash,
        expected_freeze_ledger_sequence=frozen.freeze_ledger_sequence + 1,
        verification_time_utc=inputs.verification_time_utc,
        sealed_gate_b_commitment_record_created_at_utc=commitment.record.committed_at_utc,
    )
    if freeze_after != freeze:
        raise ValueError("external verification freeze changed during full-chain verification")
    return VerifiedExternalConfirmationChainV10(
        registry=registry,
        role_verifiers=role_verifiers,
        frozen_manifest=frozen,
        frozen_manifest_content_sha256=frozen_hash,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        gate_a_report=gate_a,
        gate_a_report_content_sha256=gate_a_hash,
        verified_commitment=commitment,
        freeze_commitment_link=freeze_commitment_link,
        freeze_commitment_link_content_sha256=freeze_commitment_link_hash,
        verified_gate_a_lifecycle=gate_a_lifecycle,
        gate_a_lifecycle_content_sha256=gate_a_lifecycle.content_sha256,
        opening_context=opening_context,
        opening=opening,
        opening_content_sha256=opening_hash,
        authoritative_ledger_store_identity=store_identity,
        consumption_head=consumption_head,
        canonical_execution=canonical,
        canonical_execution_content_sha256=canonical_hash,
        canonical_verifier_execution=canonical_verifier_execution,
        fidelity=fidelity,
        fidelity_content_sha256=fidelity_hash,
        fidelity_snapshot=fidelity_snapshot,
        fidelity_verifier_execution=fidelity_verifier_execution,
        canonical_dual_readout_execution=dual_execution,
        canonical_dual_readout_execution_content_sha256=dual_execution_hash,
        sealed_dual_gate_b=dual_record,
        sealed_dual_gate_b_content_sha256=dual_hash,
        trust_anchor_registry_content_sha256=registry_hash,
    )


def verify_external_confirmation_chain_v1_0(
    inputs: ExternalConfirmationVerificationInputsV10,
) -> VerifiedExternalConfirmationChainV10:
    """Rebuild the complete chain from raw inputs or return a false blocker."""

    try:
        return _verify_external_confirmation_chain_impl_v1_0(inputs)
    except ExternalConfirmationBlockedError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttestationError) as exc:
        raise ExternalConfirmationBlockedError(
            stage="external_confirmation_prerequisites",
            reason=str(exc),
        ) from exc


class CombinedExternalConfirmationAuthorizationV10(ContractModel):
    protocol: Literal["structure-two-external-confirmation-authorization@1.0"] = (
        "structure-two-external-confirmation-authorization@1.0"
    )
    status: Literal["COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED"] = (
        "COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED"
    )
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    trust_anchor_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_manifest_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_verification_freeze_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_verification_freeze_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    forbidden_seed_namespaces_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_commitment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_commitment_link_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_lifecycle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_opening_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative_ledger_store_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_consumption_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_verifier_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    six_method_fidelity_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fidelity_verifier_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_dual_readout_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_dual_gate_b_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    gate_a_passed: Literal[True]
    dual_gate_b_passed: Literal[True]
    six_native_reproductions_verified: Literal[True]
    six_adaptation_fidelity_checks_verified: Literal[True]
    real_isolation_evidence_verified: Literal[True]
    freeze_ledger_sequence: StrictInt = Field(ge=0)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    gate_a_ledger_sequence: StrictInt = Field(ge=0)
    opening_ledger_sequence: StrictInt = Field(ge=0)
    consumption_ledger_sequence: StrictInt = Field(ge=0)
    canonical_execution_ledger_sequence: StrictInt = Field(ge=0)
    sealed_dual_gate_b_ledger_sequence: StrictInt = Field(ge=0)
    combined_authorization_ledger_sequence: StrictInt = Field(ge=0)
    sealed_dual_gate_b_scored_at_utc: datetime
    authorized_at_utc: datetime
    signing_keys: FrozenPartyKeysV10
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    authority_attestation: Attestation | None = None
    external_method_efficacy_comparison_allowed: Literal[True] = True

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        _validate_utc(
            self.sealed_dual_gate_b_scored_at_utc,
            label="sealed dual Gate-B score",
        )
        _validate_utc(self.authorized_at_utc, label="combined authorization")
        if not (
            self.freeze_ledger_sequence + 1 == self.commitment_ledger_sequence
            and self.commitment_ledger_sequence + 1 == self.gate_a_ledger_sequence
            and self.gate_a_ledger_sequence + 1 == self.opening_ledger_sequence
            and self.opening_ledger_sequence + 1 == self.consumption_ledger_sequence
            and self.consumption_ledger_sequence + 1 == self.canonical_execution_ledger_sequence
            and self.canonical_execution_ledger_sequence + 1
            == self.sealed_dual_gate_b_ledger_sequence
            and self.sealed_dual_gate_b_ledger_sequence + 1
            == self.combined_authorization_ledger_sequence
        ):
            raise ValueError("combined authorization ledger is not an immediate chain")
        if self.authorized_at_utc <= self.sealed_dual_gate_b_scored_at_utc:
            raise ValueError("combined authorization must follow sealed dual Gate B")
        return self


class CombinedDetachedSigningRequestV10(ContractModel):
    protocol: Literal["structure-two-combined-detached-signing-request@1.0"] = (
        "structure-two-combined-detached-signing-request@1.0"
    )
    artifact_protocol: Literal["structure-two-external-confirmation-authorization@1.0"] = (
        "structure-two-external-confirmation-authorization@1.0"
    )
    role: str = Field(pattern=r"^(reviewer|executor|custodian|enrollment_authority)$")
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
            raise ValueError("combined detached request key hash mismatch")
        if content_sha256(self.payload) != self.payload_sha256:
            raise ValueError("combined detached request payload hash mismatch")
        return self


def _combined_role_payload(record: CombinedExternalConfirmationAuthorizationV10) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "authority_attestation",
            }
        ),
    )


def _combined_authority_payload(
    record: CombinedExternalConfirmationAuthorizationV10,
) -> dict[str, Any]:
    roles = {
        role: getattr(record, f"{role}_attestation").model_dump(mode="json") for role in TRUST_ROLES
    }
    return {
        "authorization": _combined_role_payload(record),
        "role_attestations": roles,
        "role_attestations_sha256": content_sha256(roles),
    }


def _combined_request(
    *,
    role: str,
    domain: str,
    binding: Any,
    payload: Mapping[str, Any],
) -> CombinedDetachedSigningRequestV10:
    materialized = dict(payload)
    return CombinedDetachedSigningRequestV10(
        role=role,
        domain=domain,
        expected_key_id=binding.key_id,
        expected_public_key_base64=binding.public_key_base64,
        expected_public_key_sha256=binding.public_key_sha256,
        payload=materialized,
        payload_sha256=content_sha256(materialized),
    )


def sign_combined_detached_request_v1_0(
    request: CombinedDetachedSigningRequestV10,
    *,
    signer: Ed25519AttestationSigner,
) -> Attestation:
    verifier = signer.verifier()
    if (
        verifier.key_id != request.expected_key_id
        or verifier.public_key_base64 != request.expected_public_key_base64
        or verifier.public_key_sha256 != request.expected_public_key_sha256
    ):
        raise AttestationError("combined detached request was delivered to the wrong signer")
    if content_sha256(request.payload) != request.payload_sha256:
        raise ValueError("combined detached request changed before signing")
    return signer.sign(request.domain, request.payload)


def _combined_expected_fields(chain: VerifiedExternalConfirmationChainV10) -> dict[str, Any]:
    freeze = chain.external_verification_freeze
    commitment = chain.verified_commitment.record
    gate_a_lifecycle = chain.verified_gate_a_lifecycle.record
    opening = chain.opening
    dual = chain.sealed_dual_gate_b
    return {
        "immutable_manifest_sha256": chain.frozen_manifest.immutable_manifest_sha256,
        "producer_run_id": chain.frozen_manifest.preregistered_producer_run_id,
        "trust_anchor_registry_content_sha256": chain.trust_anchor_registry_content_sha256,
        "frozen_manifest_content_sha256": chain.frozen_manifest_content_sha256,
        "external_verification_freeze_content_sha256": (
            chain.external_verification_freeze_content_sha256
        ),
        "external_verification_freeze_body_sha256": freeze.freeze_body_sha256,
        "forbidden_seed_namespaces_sha256": freeze.body.forbidden_seed_namespaces_sha256,
        "gate_a_report_content_sha256": chain.gate_a_report_content_sha256,
        "sealed_commitment_content_sha256": chain.verified_commitment.content_sha256,
        "freeze_commitment_link_content_sha256": (chain.freeze_commitment_link_content_sha256),
        "gate_a_lifecycle_content_sha256": chain.gate_a_lifecycle_content_sha256,
        "sealed_opening_content_sha256": chain.opening_content_sha256,
        "authoritative_ledger_store_identity_sha256": (
            chain.authoritative_ledger_store_identity.content_sha256
        ),
        "opening_consumption_head_sha256": chain.consumption_head.head_sha256,
        "canonical_execution_content_sha256": chain.canonical_execution_content_sha256,
        "canonical_verifier_execution_content_sha256": (
            chain.canonical_verifier_execution.content_sha256
        ),
        "six_method_fidelity_content_sha256": chain.fidelity_content_sha256,
        "fidelity_verifier_execution_content_sha256": (
            chain.fidelity_verifier_execution.content_sha256
        ),
        "canonical_dual_readout_execution_content_sha256": (
            chain.canonical_dual_readout_execution_content_sha256
        ),
        "sealed_dual_gate_b_content_sha256": chain.sealed_dual_gate_b_content_sha256,
        "opening_attempt_id": opening.opening_attempt_id,
        "freeze_ledger_sequence": freeze.body.freeze_ledger_sequence,
        "commitment_ledger_sequence": commitment.commitment_ledger_sequence,
        "gate_a_ledger_sequence": gate_a_lifecycle.gate_a_ledger_sequence,
        "opening_ledger_sequence": opening.opening_ledger_sequence,
        "consumption_ledger_sequence": chain.consumption_head.ledger_sequence,
        "canonical_execution_ledger_sequence": _dual_gate_b_canonical_sequence(dual),
        "sealed_dual_gate_b_ledger_sequence": _dual_gate_b_sequence(dual),
        "sealed_dual_gate_b_scored_at_utc": _dual_gate_b_time(dual),
        "signing_keys": freeze.body.party_keys.model_dump(mode="python"),
    }


def prepare_combined_external_confirmation_authorization_v1_0(
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV10,
    authorized_at_utc: datetime,
) -> CombinedExternalConfirmationAuthorizationV10:
    chain = verify_external_confirmation_chain_v1_0(verification_inputs)
    _require_current_formal_gate_b(chain.sealed_dual_gate_b)
    _validate_utc(authorized_at_utc, label="combined authorization")
    if authorized_at_utc > verification_inputs.verification_time_utc:
        raise ValueError("combined authorization time is in the verifier's future")
    dual_sequence = _dual_gate_b_sequence(chain.sealed_dual_gate_b)
    return CombinedExternalConfirmationAuthorizationV10(
        **_combined_expected_fields(chain),
        gate_a_passed=True,
        dual_gate_b_passed=True,
        six_native_reproductions_verified=True,
        six_adaptation_fidelity_checks_verified=True,
        real_isolation_evidence_verified=True,
        combined_authorization_ledger_sequence=dual_sequence + 1,
        authorized_at_utc=authorized_at_utc,
    )


def combined_authorization_role_signing_requests_v1_0(
    prepared: CombinedExternalConfirmationAuthorizationV10,
) -> dict[str, CombinedDetachedSigningRequestV10]:
    if any(
        getattr(prepared, f"{role}_attestation") is not None for role in (*TRUST_ROLES, "authority")
    ):
        raise ValueError("combined role signing requires a wholly unsigned record")
    payload = _combined_role_payload(prepared)
    domains = {
        "reviewer": COMBINED_REVIEWER_DOMAIN,
        "executor": COMBINED_EXECUTOR_DOMAIN,
        "custodian": COMBINED_CUSTODIAN_DOMAIN,
    }
    return {
        role: _combined_request(
            role=role,
            domain=domains[role],
            binding=getattr(prepared.signing_keys, role),
            payload=payload,
        )
        for role in TRUST_ROLES
    }


def combined_authorization_authority_signing_request_v1_0(
    prepared: CombinedExternalConfirmationAuthorizationV10,
    *,
    reviewer_attestation: Attestation,
    executor_attestation: Attestation,
    custodian_attestation: Attestation,
) -> CombinedDetachedSigningRequestV10:
    if prepared.authority_attestation is not None:
        raise ValueError("combined authorization was already authority witnessed")
    role_payload = _combined_role_payload(prepared)
    supplied = {
        "reviewer": reviewer_attestation,
        "executor": executor_attestation,
        "custodian": custodian_attestation,
    }
    domains = {
        "reviewer": COMBINED_REVIEWER_DOMAIN,
        "executor": COMBINED_EXECUTOR_DOMAIN,
        "custodian": COMBINED_CUSTODIAN_DOMAIN,
    }
    for role in TRUST_ROLES:
        binding = getattr(prepared.signing_keys, role)
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=binding.key_id,
            public_key_base64=binding.public_key_base64,
        )
        verifier.verify(domains[role], role_payload, supplied[role])
    role_signed = prepared.model_copy(
        update={f"{role}_attestation": supplied[role] for role in TRUST_ROLES}
    )
    return _combined_request(
        role="enrollment_authority",
        domain=COMBINED_AUTHORITY_DOMAIN,
        binding=prepared.signing_keys.enrollment_authority,
        payload=_combined_authority_payload(role_signed),
    )


def verify_combined_external_confirmation_authorization_v1_0(
    payload: Mapping[str, Any],
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV10,
) -> CombinedExternalConfirmationAuthorizationV10:
    """Rebuild the raw chain, then verify the four-party combined artifact."""

    chain = verify_external_confirmation_chain_v1_0(verification_inputs)
    _require_current_formal_gate_b(chain.sealed_dual_gate_b)
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("combined authorization content hash mismatch")
    record = CombinedExternalConfirmationAuthorizationV10.model_validate(raw)
    if raw != record.model_dump(mode="json"):
        raise ValueError("combined authorization encoding is noncanonical")
    expected = _combined_expected_fields(chain)
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("combined authorization differs from the raw-reverified chain")
    if record.combined_authorization_ledger_sequence != (
        _dual_gate_b_sequence(chain.sealed_dual_gate_b) + 1
    ):
        raise ValueError("combined authorization uses a stale or skipped ledger head")
    if record.authorized_at_utc > verification_inputs.verification_time_utc:
        raise ValueError("combined authorization is in the verifier's future")
    parties = chain.external_verification_freeze.body.party_keys
    role_payload = _combined_role_payload(record)
    domains = {
        "reviewer": COMBINED_REVIEWER_DOMAIN,
        "executor": COMBINED_EXECUTOR_DOMAIN,
        "custodian": COMBINED_CUSTODIAN_DOMAIN,
    }
    for role in TRUST_ROLES:
        verifier = chain.role_verifiers[role]
        _assert_verifier(getattr(parties, role), verifier, label=f"combined {role}")
        verifier.verify(domains[role], role_payload, getattr(record, f"{role}_attestation"))
    _assert_verifier(
        parties.enrollment_authority,
        verification_inputs.trusted_enrollment_authority,
        label="combined enrollment authority",
    )
    verification_inputs.trusted_enrollment_authority.verify(
        COMBINED_AUTHORITY_DOMAIN,
        _combined_authority_payload(record),
        record.authority_attestation,
    )
    return record


def finalize_combined_external_confirmation_authorization_v1_0(
    prepared: CombinedExternalConfirmationAuthorizationV10,
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV10,
    reviewer_attestation: Attestation,
    executor_attestation: Attestation,
    custodian_attestation: Attestation,
    authority_attestation: Attestation,
) -> dict[str, Any]:
    if any(
        getattr(prepared, f"{role}_attestation") is not None for role in (*TRUST_ROLES, "authority")
    ):
        raise ValueError("combined finalization requires the unsigned prepared record")
    signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
            "authority_attestation": authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_combined_external_confirmation_authorization_v1_0(
        payload,
        verification_inputs=verification_inputs,
    )
    return payload


def make_combined_external_confirmation_authorization_v1_0(
    *,
    verification_inputs: ExternalConfirmationVerificationInputsV10,
    authorized_at_utc: datetime,
    reviewer: Ed25519AttestationSigner,
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    prepared = prepare_combined_external_confirmation_authorization_v1_0(
        verification_inputs=verification_inputs,
        authorized_at_utc=authorized_at_utc,
    )
    signers = {"reviewer": reviewer, "executor": executor, "custodian": custodian}
    requests = combined_authorization_role_signing_requests_v1_0(prepared)
    role_attestations = {
        role: sign_combined_detached_request_v1_0(requests[role], signer=signers[role])
        for role in TRUST_ROLES
    }
    authority_request = combined_authorization_authority_signing_request_v1_0(
        prepared,
        reviewer_attestation=role_attestations["reviewer"],
        executor_attestation=role_attestations["executor"],
        custodian_attestation=role_attestations["custodian"],
    )
    return finalize_combined_external_confirmation_authorization_v1_0(
        prepared,
        verification_inputs=verification_inputs,
        reviewer_attestation=role_attestations["reviewer"],
        executor_attestation=role_attestations["executor"],
        custodian_attestation=role_attestations["custodian"],
        authority_attestation=sign_combined_detached_request_v1_0(
            authority_request,
            signer=enrollment_authority,
        ),
    )


__all__ = [
    "BLOCKER_PROTOCOL_ID",
    "CANONICAL_SCOPE",
    "COMBINED_AUTHORITY_DOMAIN",
    "COMBINED_CUSTODIAN_DOMAIN",
    "COMBINED_EXECUTOR_DOMAIN",
    "COMBINED_REVIEWER_DOMAIN",
    "CURRENT_GATE_B_PROTOCOL_ID",
    "DETACHED_REQUEST_PROTOCOL_ID",
    "FIDELITY_SCOPE",
    "FREEZE_COMMITMENT_LINK_AUTHORITY_DOMAIN",
    "FREEZE_COMMITMENT_LINK_CLAIM_BOUNDARY",
    "FREEZE_COMMITMENT_LINK_CUSTODIAN_DOMAIN",
    "FREEZE_COMMITMENT_LINK_PROTOCOL_ID",
    "FREEZE_COMMITMENT_LINK_REQUEST_PROTOCOL_ID",
    "PROTOCOL_ID",
    "VERIFIER_EXECUTION_PROTOCOL_ID",
    "VERIFIER_REQUEST_FILENAME",
    "VERIFIER_REQUEST_PROTOCOL_ID",
    "VERIFIER_RESULT_FILENAME",
    "CanonicalExecutionRawInputsV10",
    "CombinedDetachedSigningRequestV10",
    "CombinedExternalConfirmationAuthorizationV10",
    "ExternalConfirmationBlockedError",
    "ExternalConfirmationBlockerReportV10",
    "ExternalConfirmationVerificationInputsV10",
    "FidelityRawInputsV10",
    "FreezeCommitmentLinkSigningRequestV10",
    "FreezeCommitmentLinkV10",
    "IsolatedVerifierExecutionBindingV10",
    "IsolatedVerifierExecutionPathsV10",
    "IsolatedVerifierRequestV10",
    "VerifiedExternalConfirmationChainV10",
    "combined_authorization_authority_signing_request_v1_0",
    "combined_authorization_role_signing_requests_v1_0",
    "finalize_combined_external_confirmation_authorization_v1_0",
    "finalize_freeze_commitment_link_v1_0",
    "freeze_commitment_link_authority_signing_request_v1_0",
    "freeze_commitment_link_custodian_signing_request_v1_0",
    "make_combined_external_confirmation_authorization_v1_0",
    "prepare_combined_external_confirmation_authorization_v1_0",
    "prepare_freeze_commitment_link_v1_0",
    "sign_combined_detached_request_v1_0",
    "sign_freeze_commitment_link_request_v1_0",
    "verify_combined_external_confirmation_authorization_v1_0",
    "verify_external_confirmation_chain_v1_0",
    "verify_freeze_commitment_link_v1_0",
]
