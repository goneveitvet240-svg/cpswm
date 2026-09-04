"""Artifact-backed, dual-signed Structure-Two Gate A v0.6."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
)
from cpswm.system.evaluation_operations.structure_two_frozen_run_v0_8 import (
    RecomputedFrozenHoldoutV08,
    load_frozen_holdout_opening_v0_8,
    recompute_frozen_holdout_v0_8,
    validate_canonical_holdout_opening_v0_8,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-validation-gate-a@0.6"
EXECUTOR_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.gate_a.executor.v0.6"
CUSTODIAN_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.gate_a.custodian.v0.6"
INPUT_PROTOCOL_ID = "structure-two-gate-a-validation-input@0.6"
EXECUTION_LOG_PROTOCOL_ID = "structure-two-gate-a-execution-log@0.6"


@dataclass(frozen=True, slots=True)
class GateAArtifactPathsV06:
    validation_input_bundle: Path
    deterministic_execution_log: Path
    frozen_holdout_opening: Path


class GateAReportV06(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-world-validation-gate-a@0\.6$")
    status: str = Field(pattern=r"^EXECUTED_PUBLIC_PREREGISTERED_VALIDATION_AFTER_EXTERNAL_FREEZE$")
    evaluation_set_role: Literal["public_preregistered_validation"]
    sealed_gate_b_holdout_verified: Literal[False]
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_anchor_registry_identifier: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    freeze_ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: int = Field(ge=0)
    authority_nonce_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_seed_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_input_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_execution_log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_implementation_bundle_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_rollout_ids: tuple[str, ...] = Field(min_length=1)
    metrics: dict[str, float]
    criteria: dict[str, bool]
    exit_code: int
    gate_a_passed: bool
    gate_b_allowed: Literal[False]
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> GateAReportV06:
        expected = self.exit_code == 0 and bool(self.criteria) and all(self.criteria.values())
        if self.gate_a_passed is not expected:
            raise ValueError("Gate A stored decision does not follow its criteria and exit code")
        if len(set(self.ordered_rollout_ids)) != len(self.ordered_rollout_ids):
            raise ValueError("Gate A rollout IDs must be unique")
        return self


def _attested_payload(record: GateAReportV06) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"executor_attestation", "custodian_attestation"})


def _verified_json_artifact(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"{label} content hash mismatch")
    return payload


def _criteria_from_spec(
    gate_a_spec: Mapping[str, Any], metrics: Mapping[str, float]
) -> dict[str, bool]:
    rows = gate_a_spec.get("criteria")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("Gate A specification criteria are missing")
    required_metrics = {str(row.get("metric")) for row in rows.values() if isinstance(row, dict)}
    if len(required_metrics) != len(rows) or set(metrics) != required_metrics:
        raise ValueError("Gate A metric set does not exactly match the frozen specification")
    result: dict[str, bool] = {}
    for name, raw_row in rows.items():
        if not isinstance(name, str) or not isinstance(raw_row, dict):
            raise ValueError("Gate A specification criterion row is malformed")
        metric = str(raw_row.get("metric"))
        operator = raw_row.get("operator")
        raw_threshold = raw_row.get("threshold")
        if not isinstance(raw_threshold, (int, float)):
            raise ValueError("Gate A specification threshold is malformed")
        threshold = float(raw_threshold)
        value = float(metrics[metric])
        if not math.isfinite(value) or not math.isfinite(threshold):
            raise ValueError("Gate A metric or threshold is non-finite")
        if operator == "ge":
            result[name] = value >= threshold
        elif operator == "le":
            result[name] = value <= threshold
        else:
            raise ValueError("Gate A specification contains an unsupported operator")
    return result


def _validate_input_and_log(
    *,
    paths: GateAArtifactPathsV06,
    frozen_manifest: FrozenGateBManifestV06,
    gate_a_spec: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, float],
    RecomputedFrozenHoldoutV08,
]:
    input_payload = _verified_json_artifact(
        paths.validation_input_bundle, label="Gate A validation input"
    )
    log_payload = _verified_json_artifact(
        paths.deterministic_execution_log, label="Gate A deterministic execution log"
    )
    if input_payload.get("protocol") != INPUT_PROTOCOL_ID:
        raise ValueError("Gate A validation-input protocol mismatch")
    if log_payload.get("protocol") != EXECUTION_LOG_PROTOCOL_ID:
        raise ValueError("Gate A execution-log protocol mismatch")
    required_context = {
        "immutable_manifest_sha256": frozen_manifest.immutable_manifest_sha256,
        "producer_run_id": frozen_manifest.preregistered_producer_run_id,
        "freeze_ledger_identifier": frozen_manifest.freeze_ledger_identifier,
        "freeze_ledger_sequence": frozen_manifest.freeze_ledger_sequence,
        "authority_nonce_sha256": frozen_manifest.authority_nonce_sha256,
        "validation_seed_commitment_sha256": (frozen_manifest.validation_seed_commitment_sha256),
        "holdout_commitment_sha256": frozen_manifest.holdout_commitment_sha256,
    }
    for key, value in required_context.items():
        if input_payload.get(key) != value or log_payload.get(key) != value:
            raise ValueError(f"Gate A artifact frozen-context mismatch: {key}")
    opening = load_frozen_holdout_opening_v0_8(
        paths.frozen_holdout_opening,
        expected_manifest_sha256=frozen_manifest.immutable_manifest_sha256,
        expected_producer_run_id=frozen_manifest.preregistered_producer_run_id,
        expected_validation_seed_commitment_sha256=(
            frozen_manifest.validation_seed_commitment_sha256
        ),
        expected_holdout_commitment_sha256=(frozen_manifest.holdout_commitment_sha256),
    )
    validate_canonical_holdout_opening_v0_8(opening, gate_a_spec)
    if input_payload.get("frozen_holdout_opening_artifact_file_sha256") != (
        external_artifact_sha256(paths.frozen_holdout_opening)
    ):
        raise ValueError("Gate A input does not bind the frozen holdout opening")
    recomputed = recompute_frozen_holdout_v0_8(opening)
    if log_payload.get("validation_input_bundle_sha256") != external_artifact_sha256(
        paths.validation_input_bundle
    ):
        raise ValueError("Gate A execution log does not bind its validation input")
    rollout_ids = log_payload.get("ordered_rollout_ids")
    if (
        not isinstance(rollout_ids, list)
        or not rollout_ids
        or len(set(rollout_ids)) != len(rollout_ids)
    ):
        raise ValueError("Gate A execution log rollout set is empty or duplicated")
    if input_payload.get("ordered_rollout_ids") != rollout_ids:
        raise ValueError("Gate A input and execution-log rollout order differ")
    recomputed_rollout_ids = [row["rollout_id"] for row in recomputed.rollout_rows]
    if rollout_ids != recomputed_rollout_ids:
        raise ValueError("Gate A rollout IDs differ from regenerated holdout rollouts")
    if not isinstance(log_payload.get("metrics"), dict) or not isinstance(
        log_payload.get("exit_code"), int
    ):
        raise ValueError("Gate A execution log lacks metrics or exit code")
    criteria_rows = gate_a_spec.get("criteria")
    if not isinstance(criteria_rows, dict):
        raise ValueError("Gate A specification criteria are missing")
    required_metrics = {
        str(row.get("metric")) for row in criteria_rows.values() if isinstance(row, dict)
    }
    if tuple(log_payload.get("world_rows", ())) != recomputed.world_rows:
        raise ValueError("Gate A world artifacts differ from deterministic regeneration")
    if tuple(log_payload.get("rollout_rows", ())) != recomputed.rollout_rows:
        raise ValueError("Gate A rollout artifacts differ from deterministic regeneration")
    derived_metrics = recomputed.metrics
    if set(derived_metrics) != required_metrics:
        raise ValueError("Gate A recomputed metric set differs from the frozen specification")
    stored_metrics = log_payload["metrics"]
    if set(stored_metrics) != required_metrics or any(
        isinstance(stored_metrics[metric], bool)
        or not isinstance(stored_metrics[metric], (int, float))
        or not math.isfinite(float(stored_metrics[metric]))
        or float(stored_metrics[metric]) != derived_metrics[metric]
        for metric in required_metrics
    ):
        raise ValueError("Gate A aggregate metrics do not match deterministic replay")
    return input_payload, log_payload, derived_metrics, recomputed


def make_gate_a_report_v0_6(
    *,
    gate_a_spec: Mapping[str, Any],
    frozen_manifest: FrozenGateBManifestV06,
    trust_anchor_registry: TrustAnchorRegistryV06,
    artifact_paths: GateAArtifactPathsV06,
    producer_source_bundle_sha256: str,
    expected_arm_implementation_bundles: Mapping[str, str],
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
) -> dict[str, Any]:
    if producer_source_bundle_sha256 != frozen_manifest.producer_source_bundle_sha256:
        raise ValueError("Gate A producer source differs from the frozen manifest")
    if dict(expected_arm_implementation_bundles) != (
        frozen_manifest.arm_implementation_bundle_sha256
    ):
        raise ValueError("Gate A implementation identities differ from the frozen manifest")
    _, log_payload, metrics, _ = _validate_input_and_log(
        paths=artifact_paths,
        frozen_manifest=frozen_manifest,
        gate_a_spec=gate_a_spec,
    )
    criteria = _criteria_from_spec(gate_a_spec, metrics)
    executor_verifier = executor.verifier()
    custodian_verifier = custodian.verifier()
    role_by_name = {row.role: row for row in trust_anchor_registry.role_keys}
    if (
        executor_verifier.public_key_sha256 != role_by_name["executor"].public_key_sha256
        or custodian_verifier.public_key_sha256 != role_by_name["custodian"].public_key_sha256
    ):
        raise AttestationError("Gate A signers are outside the enrolled registry")
    exit_code = int(log_payload["exit_code"])
    passed = exit_code == 0 and all(criteria.values())
    unsigned = GateAReportV06(
        protocol=PROTOCOL_ID,
        status="EXECUTED_PUBLIC_PREREGISTERED_VALIDATION_AFTER_EXTERNAL_FREEZE",
        evaluation_set_role="public_preregistered_validation",
        sealed_gate_b_holdout_verified=False,
        immutable_manifest_sha256=frozen_manifest.immutable_manifest_sha256,
        trust_anchor_registry_identifier=trust_anchor_registry.registry_identifier,
        producer_run_id=frozen_manifest.preregistered_producer_run_id,
        freeze_ledger_identifier=frozen_manifest.freeze_ledger_identifier,
        freeze_ledger_sequence=frozen_manifest.freeze_ledger_sequence,
        authority_nonce_sha256=frozen_manifest.authority_nonce_sha256,
        validation_seed_commitment_sha256=(frozen_manifest.validation_seed_commitment_sha256),
        holdout_commitment_sha256=frozen_manifest.holdout_commitment_sha256,
        validation_input_bundle_sha256=external_artifact_sha256(
            artifact_paths.validation_input_bundle
        ),
        deterministic_execution_log_sha256=external_artifact_sha256(
            artifact_paths.deterministic_execution_log
        ),
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        arm_implementation_bundle_set_sha256=content_sha256(
            dict(sorted(expected_arm_implementation_bundles.items()))
        ),
        ordered_rollout_ids=tuple(str(item) for item in log_payload["ordered_rollout_ids"]),
        metrics=metrics,
        criteria=criteria,
        exit_code=exit_code,
        gate_a_passed=passed,
        gate_b_allowed=False,
        executor_key_id=executor_verifier.key_id,
        executor_public_key_base64=executor_verifier.public_key_base64,
        executor_public_key_sha256=executor_verifier.public_key_sha256,
        custodian_key_id=custodian_verifier.key_id,
        custodian_public_key_base64=custodian_verifier.public_key_base64,
        custodian_public_key_sha256=custodian_verifier.public_key_sha256,
        claim_boundary=(
            "Gate A evaluates a public preregistered validation set. Its seeds are visible "
            "before implementation freeze, so it does not verify a sealed confirmatory "
            "holdout and cannot authorize Gate B, external fidelity, or efficacy."
        ),
    )
    signable = _attested_payload(unsigned)
    signed = unsigned.model_copy(
        update={
            "executor_attestation": executor.sign(EXECUTOR_ATTESTATION_DOMAIN, signable),
            "custodian_attestation": custodian.sign(CUSTODIAN_ATTESTATION_DOMAIN, signable),
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_gate_a_report_v0_6(
    report: Mapping[str, Any],
    *,
    gate_a_spec: Mapping[str, Any],
    frozen_manifest: FrozenGateBManifestV06,
    trust_anchor_registry: TrustAnchorRegistryV06,
    artifact_paths: GateAArtifactPathsV06,
    producer_source_bundle_sha256: str,
    expected_arm_implementation_bundles: Mapping[str, str],
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> GateAReportV06:
    if producer_source_bundle_sha256 != frozen_manifest.producer_source_bundle_sha256:
        raise ValueError("Gate A producer source differs from the frozen manifest")
    if dict(expected_arm_implementation_bundles) != (
        frozen_manifest.arm_implementation_bundle_sha256
    ):
        raise ValueError("Gate A implementation identities differ from the frozen manifest")
    unsigned_payload = dict(report)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("Gate A report content hash mismatch")
    record = GateAReportV06.model_validate(unsigned_payload)
    _, log_payload, metrics, _ = _validate_input_and_log(
        paths=artifact_paths,
        frozen_manifest=frozen_manifest,
        gate_a_spec=gate_a_spec,
    )
    criteria = _criteria_from_spec(gate_a_spec, metrics)
    expected_bindings = {
        "immutable_manifest_sha256": frozen_manifest.immutable_manifest_sha256,
        "trust_anchor_registry_identifier": trust_anchor_registry.registry_identifier,
        "producer_run_id": frozen_manifest.preregistered_producer_run_id,
        "freeze_ledger_identifier": frozen_manifest.freeze_ledger_identifier,
        "freeze_ledger_sequence": frozen_manifest.freeze_ledger_sequence,
        "authority_nonce_sha256": frozen_manifest.authority_nonce_sha256,
        "validation_seed_commitment_sha256": (frozen_manifest.validation_seed_commitment_sha256),
        "holdout_commitment_sha256": frozen_manifest.holdout_commitment_sha256,
        "validation_input_bundle_sha256": external_artifact_sha256(
            artifact_paths.validation_input_bundle
        ),
        "deterministic_execution_log_sha256": external_artifact_sha256(
            artifact_paths.deterministic_execution_log
        ),
        "producer_source_bundle_sha256": producer_source_bundle_sha256,
        "arm_implementation_bundle_set_sha256": content_sha256(
            dict(sorted(expected_arm_implementation_bundles.items()))
        ),
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[key] != value for key, value in expected_bindings.items()):
        raise ValueError("Gate A report provenance or frozen-context binding mismatch")
    if (
        record.metrics != metrics
        or record.criteria != criteria
        or record.ordered_rollout_ids
        != tuple(str(item) for item in log_payload["ordered_rollout_ids"])
        or record.exit_code != log_payload["exit_code"]
    ):
        raise ValueError("Gate A report differs from deterministic execution artifacts")
    if record.gate_a_passed is not True:
        raise ValueError("failed Gate A forbids Gate B scoring")
    if (
        record.executor_key_id != executor.key_id
        or record.executor_public_key_base64 != executor.public_key_base64
        or record.executor_public_key_sha256 != executor.public_key_sha256
        or record.custodian_key_id != custodian.key_id
        or record.custodian_public_key_base64 != custodian.public_key_base64
        or record.custodian_public_key_sha256 != custodian.public_key_sha256
    ):
        raise AttestationError("Gate A report is outside enrolled signer keys")
    signable = _attested_payload(record)
    executor.verify(EXECUTOR_ATTESTATION_DOMAIN, signable, record.executor_attestation)
    custodian.verify(CUSTODIAN_ATTESTATION_DOMAIN, signable, record.custodian_attestation)
    return record


__all__ = [
    "CUSTODIAN_ATTESTATION_DOMAIN",
    "EXECUTION_LOG_PROTOCOL_ID",
    "EXECUTOR_ATTESTATION_DOMAIN",
    "INPUT_PROTOCOL_ID",
    "PROTOCOL_ID",
    "GateAArtifactPathsV06",
    "GateAReportV06",
    "make_gate_a_report_v0_6",
    "verify_gate_a_report_v0_6",
]
