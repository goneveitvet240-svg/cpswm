"""Development-readiness report for the Structure-Two v0.6 repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from cpswm.system.attestation import (
    Attestation,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_adapter_input_coverage_v0_6 import (
    run_adapter_input_coverage_gate,
)
from cpswm.system.evaluation_operations.structure_two_executor_conformance_v0_7 import (
    verify_executor_conformance_v0_7,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    ExternalEvidenceArtifactPaths,
    ExternalMethodEvidence,
    default_external_method_specifications_v0_2,
    external_artifact_sha256,
    run_external_fidelity_gate_v0_2,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    CompleteExternalAdaptationInputsV06,
)
from cpswm.system.evaluation_operations.structure_two_gate_a_v0_6 import (
    GateAArtifactPathsV06,
    verify_gate_a_report_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    CANONICAL_COMPONENT_IDS,
    validate_structure_two_gate_b_v0_6_draft,
)
from cpswm.system.evaluation_operations.structure_two_signed_gate_b_v0_6 import (
    run_signed_stratified_gate_b_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_six_arm_execution_v0_7 import (
    CANONICAL_SIX_ARMS,
    verify_six_arm_reference_execution_v0_7,
)
from cpswm.system.evaluation_operations.structure_two_source_acquisition_v0_6 import (
    verify_primary_source_acquisition_receipt_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    audit_v0_5_source_bundle_evidence,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-v0.6-development-readiness@0.2"
EVIDENCE_INDEX_FIELDS = frozenset(
    {
        "protocol",
        "status",
        "source_artifact_paths_by_arm",
        "source_acquisition_receipt_paths_by_arm",
        "complete_adaptation_input_bundle_path",
        "complete_adaptation_input_bundle_sha256",
        "external_evidence_paths_by_arm",
        "external_artifact_paths_by_arm",
        "reference_execution_report_path",
        "reference_execution_arm_result_paths_by_arm",
        "reference_execution_active_receipt_paths_by_scenario",
        "reference_execution_active_program_paths_by_scenario",
        "executor_conformance_report_path",
        "executor_conformance_test_artifact_path",
        "gate_a_report_path",
        "gate_a_validation_input_bundle_path",
        "gate_a_deterministic_execution_log_path",
        "externally_frozen_manifest_path",
        "signed_gate_b_trace_paths",
        "producer_source_bundle_sha256",
        "expected_arm_implementation_bundles",
        "trust_anchor_registry_path",
        "content_sha256",
    }
)
DEFAULT_DRAFT = Path("configs/project_two_experiments/structure_two_gate_b_v0_6_DRAFT.json")
DEFAULT_GATE_A_SPEC = Path("configs/project_two_experiments/structure_two_gate_a_v0_6_spec.json")
DEFAULT_LEGACY_RESULT = Path(
    "benchmarks/structure_two/structure_two_world_dual_gate_authorization_v0_5.json"
)
DEFAULT_SOURCE_REGISTER = Path(
    "configs/project_two_experiments/structure_two_external_method_sources_v0_2.json"
)
DEFAULT_REFERENCE_CORE_REGISTER = Path(
    "configs/project_two_experiments/structure_two_external_reference_cores_v0_6.json"
)
DEFAULT_OFFICIAL_COMPONENT_PARITY = Path(
    "benchmarks/structure_two/structure_two_official_component_parity_v0_6.json"
)
DEFAULT_EVIDENCE_INDEX = Path(
    "configs/project_two_experiments/structure_two_v0_6_evidence_index.json"
)
DEFAULT_OUTPUT = Path("benchmarks/structure_two/structure_two_v0_6_development_readiness.json")


def _verified_content_payload(path: Path, *, label: str) -> dict[str, Any]:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"{label} content hash mismatch")
    return payload


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _resolve_path(repository_root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def _path_mapping(repository_root: Path, value: object) -> dict[str, Path]:
    if not isinstance(value, dict):
        raise ValueError("v0.6 evidence-index path mapping is malformed")
    resolved: dict[str, Path] = {}
    for arm, raw_path in value.items():
        path = _resolve_path(repository_root, raw_path)
        if not isinstance(arm, str) or path is None:
            raise ValueError("v0.6 evidence-index path entry is malformed")
        resolved[arm] = path
    return resolved


def _load_external_evidence(path: Path) -> ExternalMethodEvidence:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    raw_attestation = payload.pop("attestation", None)
    if isinstance(raw_attestation, dict):
        payload["attestation"] = Attestation.model_validate(raw_attestation)
    elif raw_attestation is not None:
        raise ValueError("external-method evidence attestation is malformed")
    raw_components = payload.get("verified_native_components", ())
    if not isinstance(raw_components, (list, tuple)):
        raise ValueError("external-method verified component set is malformed")
    payload["verified_native_components"] = tuple(str(item) for item in raw_components)
    return ExternalMethodEvidence(**payload)


def _load_external_artifact_paths(
    repository_root: Path, value: object
) -> dict[str, ExternalEvidenceArtifactPaths]:
    if not isinstance(value, dict):
        raise ValueError("v0.6 external artifact-path mapping is malformed")
    required = (
        "primary_source",
        "implementation_bundle",
        "component_parity_receipt",
        "component_parity_execution_log",
        "native_protocol_recheck_receipt",
        "native_protocol_execution_log",
        "adaptation_contract",
        "adaptation_parity_receipt",
        "adaptation_parity_execution_log",
    )
    rows: dict[str, ExternalEvidenceArtifactPaths] = {}
    for arm, raw_row in value.items():
        if not isinstance(arm, str) or not isinstance(raw_row, dict):
            raise ValueError("v0.6 external artifact-path row is malformed")
        resolved = {key: _resolve_path(repository_root, raw_row.get(key)) for key in required}
        if any(path is None for path in resolved.values()):
            raise ValueError(f"v0.6 external artifact-path row is incomplete: {arm}")
        official = _resolve_path(repository_root, raw_row.get("official_code_checkout"))
        rows[arm] = ExternalEvidenceArtifactPaths(
            **cast(dict[str, Path], resolved),
            official_code_checkout=official,
        )
    return rows


def build_v0_6_development_readiness(
    repository_root: Path,
    *,
    evidence_index_path: Path | None = None,
    trusted_enrollment_authority: Ed25519AttestationVerifier | None = None,
) -> dict[str, Any]:
    draft_path = repository_root / DEFAULT_DRAFT
    gate_a_spec_path = repository_root / DEFAULT_GATE_A_SPEC
    legacy_path = repository_root / DEFAULT_LEGACY_RESULT
    source_register_path = repository_root / DEFAULT_SOURCE_REGISTER
    reference_core_register_path = repository_root / DEFAULT_REFERENCE_CORE_REGISTER
    official_component_parity_path = repository_root / DEFAULT_OFFICIAL_COMPONENT_PARITY
    resolved_evidence_index_path = evidence_index_path or (repository_root / DEFAULT_EVIDENCE_INDEX)
    if not resolved_evidence_index_path.is_absolute():
        resolved_evidence_index_path = repository_root / resolved_evidence_index_path
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    comparisons, requirements = validate_structure_two_gate_b_v0_6_draft(draft)
    gate_a_spec = _verified_content_payload(gate_a_spec_path, label="v0.6 Gate A specification")
    if gate_a_spec.get("protocol") != "structure-two-world-validation-gate-a-spec@0.6":
        raise ValueError("v0.6 Gate A specification protocol mismatch")
    evidence_index = _verified_content_payload(
        resolved_evidence_index_path, label="v0.6 evidence index"
    )
    if evidence_index.get("protocol") != "structure-two-v0.6-evidence-index@0.2":
        raise ValueError("v0.6 evidence-index protocol mismatch")
    if set(evidence_index) != EVIDENCE_INDEX_FIELDS:
        raise ValueError("v0.6 evidence-index field set is incomplete or contains extras")
    if evidence_index.get("status") not in {
        "DEVELOPMENT_EVIDENCE_NOT_COMPLETE",
        "DEVELOPMENT_EVIDENCE_STAGED",
    }:
        raise ValueError("v0.6 evidence-index status mismatch")
    trust_registry_path = _resolve_path(
        repository_root, evidence_index.get("trust_anchor_registry_path")
    )
    trust_registry: TrustAnchorRegistryV06 | None = None
    role_verifiers: dict[str, Ed25519AttestationVerifier] = {}
    trust_registry_validation_error: str | None = None
    if trust_registry_path is not None:
        if trusted_enrollment_authority is None:
            trust_registry_validation_error = (
                "out-of-band trusted enrollment authority was not supplied"
            )
        else:
            try:
                raw_registry = cast(
                    dict[str, Any],
                    json.loads(trust_registry_path.read_text(encoding="utf-8")),
                )
                trust_registry, role_verifiers = verify_trust_anchor_registry_v0_6(
                    raw_registry,
                    trusted_enrollment_authority=trusted_enrollment_authority,
                )
            except (OSError, ValueError) as exc:
                trust_registry_validation_error = str(exc)
    trust_anchors_enrolled = trust_registry is not None
    role_control_independence_attested = bool(
        trust_registry and trust_registry.role_control_independence_attested is True
    )

    source_register = _verified_content_payload(
        source_register_path, label="v0.6 external-method source register"
    )
    if source_register.get("protocol") != "structure-two-external-method-source-register@0.2":
        raise ValueError("v0.6 external-method source register protocol mismatch")
    source_register_content_sha256 = cast(str, source_register["content_sha256"])
    legacy = _verified_content_payload(legacy_path, label="historical v0.5 result")
    historical_v0_5_audit = audit_v0_5_source_bundle_evidence(repository_root)
    specifications = default_external_method_specifications_v0_2()
    expected_external_arms = {item.arm for item in specifications}
    source_rows = source_register.get("methods")
    if (
        not isinstance(source_rows, list)
        or len(source_rows) != len(expected_external_arms)
        or len({row.get("arm") for row in source_rows if isinstance(row, dict)})
        != len(expected_external_arms)
        or {row.get("arm") for row in source_rows if isinstance(row, dict)}
        != expected_external_arms
    ):
        raise ValueError("v0.6 external-method source register arm set mismatch")
    source_row_by_arm = {str(row["arm"]): row for row in source_rows if isinstance(row, dict)}
    source_artifact_paths = _path_mapping(
        repository_root, evidence_index.get("source_artifact_paths_by_arm", {})
    )
    if set(source_artifact_paths) - expected_external_arms:
        raise ValueError("v0.6 source artifacts contain an undeclared arm")
    source_receipt_paths = _path_mapping(
        repository_root,
        evidence_index.get("source_acquisition_receipt_paths_by_arm", {}),
    )
    if set(source_receipt_paths) - expected_external_arms:
        raise ValueError("v0.6 source receipts contain an undeclared arm")
    external_artifact_paths = _load_external_artifact_paths(
        repository_root, evidence_index.get("external_artifact_paths_by_arm", {})
    )
    if set(external_artifact_paths) - expected_external_arms:
        raise ValueError("v0.6 external artifacts contain an undeclared arm")
    source_identification_rows: list[dict[str, Any]] = []
    for specification in specifications:
        row = source_row_by_arm[specification.arm]
        source_path = source_artifact_paths.get(specification.arm)
        source_content_bound = False
        if source_path is not None and _is_sha256(row.get("primary_source_sha256")):
            try:
                source_content_bound = external_artifact_sha256(source_path) == row.get(
                    "primary_source_sha256"
                )
            except (OSError, ValueError):
                source_content_bound = False
        source_acquisition_receipt_verified = False
        source_acquisition_validation_error: str | None = None
        receipt_path = source_receipt_paths.get(specification.arm)
        reviewer_verifier = role_verifiers.get("reviewer")
        if source_path is not None and receipt_path is not None and reviewer_verifier:
            try:
                artifact_paths = external_artifact_paths.get(specification.arm)
                receipt_payload = cast(
                    dict[str, Any],
                    json.loads(receipt_path.read_text(encoding="utf-8")),
                )
                verify_primary_source_acquisition_receipt_v0_6(
                    receipt_payload,
                    expected_arm=specification.arm,
                    source_row=row,
                    source_artifact=source_path,
                    source_register_content_sha256=source_register_content_sha256,
                    trusted_acquirer=reviewer_verifier,
                    official_checkout=(
                        artifact_paths.official_code_checkout
                        if artifact_paths is not None
                        else None
                    ),
                )
                source_acquisition_receipt_verified = True
            except (OSError, ValueError) as exc:
                source_acquisition_validation_error = str(exc)
        checks = {
            "method_exact": row.get("method") == specification.method,
            "primary_source_url_exact": row.get("primary_source_url")
            == specification.primary_source_url,
            "primary_source_content_hash_present": _is_sha256(row.get("primary_source_sha256")),
            "primary_source_artifact_content_bound": source_content_bound,
            "signed_source_acquisition_receipt_verified": (source_acquisition_receipt_verified),
            "evidence_level_present": isinstance(row.get("evidence_level"), str)
            and bool(row.get("evidence_level")),
            "official_code_url_exact_if_required": (
                not specification.official_code_required
                or row.get("repository_url") == specification.official_code_url
            ),
            "official_code_commit_exact_if_required": (
                not specification.official_code_required
                or row.get("repository_commit") == specification.official_code_commit
            ),
        }
        source_identification_rows.append(
            {
                "arm": specification.arm,
                "checks": checks,
                "passed": all(checks.values()),
                "source_acquisition_validation_error": (source_acquisition_validation_error),
                "missing_or_mismatched": tuple(key for key, passed in checks.items() if not passed),
            }
        )
    source_identification_complete = all(bool(row["passed"]) for row in source_identification_rows)
    reference_core_register = json.loads(reference_core_register_path.read_text(encoding="utf-8"))
    if (
        reference_core_register.get("protocol")
        != "structure-two-external-reference-core-register@0.6"
        or reference_core_register.get("status") != "COMPONENT_CORES_ONLY_NOT_NATIVE_REPRODUCTIONS"
    ):
        raise ValueError("v0.6 external reference-core register protocol/status mismatch")
    reference_rows = reference_core_register.get("arms")
    if (
        not isinstance(reference_rows, list)
        or len(reference_rows) != len(expected_external_arms)
        or len({row.get("arm") for row in reference_rows if isinstance(row, dict)})
        != len(expected_external_arms)
        or {row.get("arm") for row in reference_rows if isinstance(row, dict)}
        != expected_external_arms
    ):
        raise ValueError("v0.6 external reference-core register arm set mismatch")
    official_component_parity = _verified_content_payload(
        official_component_parity_path,
        label="v0.6 official component parity",
    )
    if official_component_parity.get("protocol") != "structure-two-official-component-parity@0.6":
        raise ValueError("v0.6 official component parity protocol mismatch")
    complete_input_bundle_path = _resolve_path(
        repository_root, evidence_index.get("complete_adaptation_input_bundle_path")
    )
    complete_input_bundle_sha256 = evidence_index.get("complete_adaptation_input_bundle_sha256")
    complete_input_bundle_valid = False
    if (
        complete_input_bundle_path is not None
        and _is_sha256(complete_input_bundle_sha256)
        and complete_input_bundle_path.is_file()
    ):
        try:
            CompleteExternalAdaptationInputsV06.model_validate_json(
                complete_input_bundle_path.read_text(encoding="utf-8")
            )
            complete_input_bundle_valid = (
                external_artifact_sha256(complete_input_bundle_path) == complete_input_bundle_sha256
            )
        except (OSError, ValueError):
            complete_input_bundle_valid = False
    available_inputs = (
        {
            specification.arm: specification.required_adaptation_inputs
            for specification in specifications
        }
        if complete_input_bundle_valid
        else {}
    )
    input_bundle_paths = (
        {item.arm: complete_input_bundle_path for item in specifications}
        if complete_input_bundle_valid and complete_input_bundle_path is not None
        else {}
    )
    input_bundle_hashes = (
        {item.arm: cast(str, complete_input_bundle_sha256) for item in specifications}
        if complete_input_bundle_valid
        else {}
    )
    input_coverage = run_adapter_input_coverage_gate(
        specifications,
        available_inputs,
        input_bundle_paths_by_arm=input_bundle_paths,
        input_bundle_sha256_by_arm=input_bundle_hashes,
    )

    evidence_paths = _path_mapping(
        repository_root, evidence_index.get("external_evidence_paths_by_arm", {})
    )
    if set(evidence_paths) - expected_external_arms:
        raise ValueError("v0.6 external evidence contains an undeclared arm")
    external_evidence = {arm: _load_external_evidence(path) for arm, path in evidence_paths.items()}
    if any(evidence.arm != arm for arm, evidence in external_evidence.items()):
        raise ValueError("v0.6 external evidence arm binding mismatch")
    reviewer_verifier = role_verifiers.get("reviewer")
    executor_verifier = role_verifiers.get("executor")
    custodian_verifier = role_verifiers.get("custodian")
    fidelity = run_external_fidelity_gate_v0_2(
        specifications,
        external_evidence,
        artifact_paths_by_arm=external_artifact_paths,
        trusted_reviewer_key_id=(reviewer_verifier.key_id if reviewer_verifier else None),
        trusted_reviewer_public_key_sha256=(
            reviewer_verifier.public_key_sha256 if reviewer_verifier else None
        ),
        trusted_executor_key_id=(executor_verifier.key_id if executor_verifier else None),
        trusted_executor_public_key_sha256=(
            executor_verifier.public_key_sha256 if executor_verifier else None
        ),
    )

    producer_source_bundle_sha256 = evidence_index.get("producer_source_bundle_sha256")
    raw_implementation_bundles = evidence_index.get("expected_arm_implementation_bundles", {})
    if not isinstance(raw_implementation_bundles, dict) or any(
        not isinstance(arm, str) or not _is_sha256(value)
        for arm, value in raw_implementation_bundles.items()
    ):
        raise ValueError("v0.6 expected implementation-bundle mapping is malformed")
    expected_implementation_bundles = {
        str(arm): str(value) for arm, value in raw_implementation_bundles.items()
    }
    implementation_bundles_staged = set(
        external_artifact_paths
    ) == expected_external_arms and expected_external_arms <= set(expected_implementation_bundles)
    if implementation_bundles_staged:
        for arm, paths in external_artifact_paths.items():
            try:
                if (
                    external_artifact_sha256(paths.implementation_bundle)
                    != (expected_implementation_bundles[arm])
                ):
                    implementation_bundles_staged = False
                    break
            except (OSError, ValueError):
                implementation_bundles_staged = False
                break
    reference_execution_path = _resolve_path(
        repository_root, evidence_index.get("reference_execution_report_path")
    )
    reference_result_paths = _path_mapping(
        repository_root,
        evidence_index.get("reference_execution_arm_result_paths_by_arm", {}),
    )
    reference_active_receipt_paths = _path_mapping(
        repository_root,
        evidence_index.get("reference_execution_active_receipt_paths_by_scenario", {}),
    )
    reference_active_program_paths = _path_mapping(
        repository_root,
        evidence_index.get("reference_execution_active_program_paths_by_scenario", {}),
    )
    reference_execution: dict[str, Any] | None = None
    reference_execution_validation_error: str | None = None
    if reference_execution_path is not None:
        try:
            if (
                not complete_input_bundle_valid
                or executor_verifier is None
                or set(source_artifact_paths) != set(CANONICAL_SIX_ARMS)
                or not set(CANONICAL_SIX_ARMS) <= set(expected_implementation_bundles)
            ):
                raise ValueError("six-arm reference execution prerequisites are incomplete")
            expected_source_hashes = {
                arm: external_artifact_sha256(source_artifact_paths[arm])
                for arm in CANONICAL_SIX_ARMS
            }
            assert complete_input_bundle_path is not None
            raw_reference_execution = cast(
                dict[str, Any],
                json.loads(reference_execution_path.read_text(encoding="utf-8")),
            )
            reference_execution = verify_six_arm_reference_execution_v0_7(
                raw_reference_execution,
                expected_input_bundle_sha256=cast(str, complete_input_bundle_sha256),
                input_bundle_artifact_path=complete_input_bundle_path,
                expected_source_artifact_sha256_by_arm=expected_source_hashes,
                expected_implementation_bundle_sha256_by_arm=(
                    {arm: expected_implementation_bundles[arm] for arm in CANONICAL_SIX_ARMS}
                ),
                arm_result_artifact_paths_by_arm=reference_result_paths,
                active_scenario_receipt_paths=reference_active_receipt_paths,
                active_scenario_program_paths=reference_active_program_paths,
                trusted_executor=executor_verifier,
                trusted_scenario_executor=executor_verifier,
            )
        except (OSError, ValueError) as exc:
            reference_execution_validation_error = str(exc)

    conformance_path = _resolve_path(
        repository_root, evidence_index.get("executor_conformance_report_path")
    )
    conformance_test_artifact_path = _resolve_path(
        repository_root,
        evidence_index.get("executor_conformance_test_artifact_path"),
    )
    executor_conformance_report: dict[str, Any] | None = None
    executor_conformance_validation_error: str | None = None
    if conformance_path is not None:
        try:
            if (
                executor_verifier is None
                or reviewer_verifier is None
                or not _is_sha256(producer_source_bundle_sha256)
                or conformance_test_artifact_path is None
            ):
                raise ValueError("executor-conformance prerequisites are incomplete")
            raw_conformance = cast(
                dict[str, Any],
                json.loads(conformance_path.read_text(encoding="utf-8")),
            )
            executor_conformance_report, _ = verify_executor_conformance_v0_7(
                raw_conformance,
                test_artifact_path=conformance_test_artifact_path,
                repository_root=repository_root,
                producer_source_bundle_sha256=cast(str, producer_source_bundle_sha256),
                trusted_tester=reviewer_verifier,
                trusted_executor=executor_verifier,
            )
        except (OSError, ValueError) as exc:
            executor_conformance_validation_error = str(exc)

    gate_a_path = _resolve_path(repository_root, evidence_index.get("gate_a_report_path"))
    gate_a_report: dict[str, Any] | None = None
    gate_a_report_content_bound = False
    gate_a_protocol_exact = False
    gate_a_passed = False
    gate_a_validation_error: str | None = None
    gate_a_input_path = _resolve_path(
        repository_root, evidence_index.get("gate_a_validation_input_bundle_path")
    )
    gate_a_log_path = _resolve_path(
        repository_root,
        evidence_index.get("gate_a_deterministic_execution_log_path"),
    )

    frozen_manifest_path = _resolve_path(
        repository_root, evidence_index.get("externally_frozen_manifest_path")
    )
    frozen_manifest: FrozenGateBManifestV06 | None = None
    frozen_manifest_validation_error: str | None = None
    if frozen_manifest_path is not None:
        try:
            if (
                reviewer_verifier is None
                or custodian_verifier is None
                or trust_registry is None
                or trusted_enrollment_authority is None
            ):
                raise ValueError("frozen-manifest trust anchors are not externally enrolled")
            raw_frozen_manifest = cast(
                dict[str, Any],
                json.loads(frozen_manifest_path.read_text(encoding="utf-8")),
            )
            frozen_manifest = verify_frozen_gate_b_manifest_v0_6(
                raw_frozen_manifest,
                development_draft=draft,
                source_register=source_register,
                gate_a_spec=gate_a_spec,
                trust_anchor_registry=trust_registry,
                reviewer=reviewer_verifier,
                custodian=custodian_verifier,
                enrollment_authority=trusted_enrollment_authority,
            )
        except (OSError, ValueError) as exc:
            frozen_manifest_validation_error = str(exc)

    if gate_a_path is not None:
        try:
            if (
                frozen_manifest is None
                or trust_registry is None
                or executor_verifier is None
                or custodian_verifier is None
                or gate_a_input_path is None
                or gate_a_log_path is None
                or not _is_sha256(producer_source_bundle_sha256)
                or set(expected_implementation_bundles) != set(draft["expected_arms"])
            ):
                raise ValueError("Gate A artifact prerequisites are incomplete")
            raw_gate_a = cast(dict[str, Any], json.loads(gate_a_path.read_text(encoding="utf-8")))
            gate_a_record = verify_gate_a_report_v0_6(
                raw_gate_a,
                gate_a_spec=gate_a_spec,
                frozen_manifest=frozen_manifest,
                trust_anchor_registry=trust_registry,
                artifact_paths=GateAArtifactPathsV06(
                    validation_input_bundle=gate_a_input_path,
                    deterministic_execution_log=gate_a_log_path,
                ),
                producer_source_bundle_sha256=cast(str, producer_source_bundle_sha256),
                expected_arm_implementation_bundles=(expected_implementation_bundles),
                executor=executor_verifier,
                custodian=custodian_verifier,
            )
            gate_a_report = raw_gate_a
            gate_a_report_content_bound = True
            gate_a_protocol_exact = True
            gate_a_passed = gate_a_record.gate_a_passed
        except (OSError, ValueError) as exc:
            gate_a_validation_error = str(exc)

    raw_trace_paths = evidence_index.get("signed_gate_b_trace_paths", [])
    if not isinstance(raw_trace_paths, list):
        raise ValueError("v0.6 signed Gate B trace-path list is malformed")
    trace_paths = tuple(
        path
        for raw_path in raw_trace_paths
        if (path := _resolve_path(repository_root, raw_path)) is not None
    )
    if len(trace_paths) != len(raw_trace_paths):
        raise ValueError("v0.6 signed Gate B trace path is malformed")
    gate_b_report: dict[str, Any] | None = None
    gate_b_validation_error: str | None = None
    can_attempt_gate_b = all(
        (
            gate_a_report is not None,
            gate_a_protocol_exact,
            gate_a_passed,
            frozen_manifest is not None,
            len(trace_paths) == len(draft["expected_arms"]),
            _is_sha256(producer_source_bundle_sha256),
            set(expected_implementation_bundles) == set(draft["expected_arms"]),
            custodian_verifier is not None,
        )
    )
    if can_attempt_gate_b:
        assert gate_a_report is not None
        assert frozen_manifest is not None
        assert custodian_verifier is not None
        try:
            trace_payloads = tuple(
                cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
                for path in trace_paths
            )
            expected_event_component_ids = {
                requirement.arm: {
                    event: CANONICAL_COMPONENT_IDS[requirement.arm]
                    for event in requirement.required_events
                }
                for requirement in requirements
            }
            gate_b_report = run_signed_stratified_gate_b_v0_6(
                trace_payloads,
                expected_arms=tuple(draft["expected_arms"]),
                comparison_pairs=comparisons,
                mechanism_requirements=requirements,
                gate_a_content_sha256=str(gate_a_report["content_sha256"]),
                manifest_sha256=frozen_manifest.immutable_manifest_sha256,
                producer_source_bundle_sha256=cast(str, producer_source_bundle_sha256),
                expected_arm_implementation_bundles=expected_implementation_bundles,
                expected_event_component_ids=expected_event_component_ids,
                expected_producer_run_id=(frozen_manifest.preregistered_producer_run_id),
                trusted_custodian_key_id=custodian_verifier.key_id,
                trusted_custodian_public_key_sha256=(custodian_verifier.public_key_sha256),
            )
        except (OSError, ValueError) as exc:
            gate_b_validation_error = str(exc)

    gate_b_scored = gate_b_report is not None
    gate_b_passed = bool(gate_b_report and gate_b_report.get("gate_b_passed") is True)
    design_evidence_ready_for_external_freeze = all(
        (
            source_identification_complete,
            input_coverage["adapter_input_coverage_gate_passed"] is True,
            implementation_bundles_staged,
            trust_anchors_enrolled,
            role_control_independence_attested,
            draft["status"] == "DEVELOPMENT_NOT_FROZEN",
            frozen_manifest is None,
        )
    )
    combined_authorization_allowed = all(
        (
            gate_a_report_content_bound,
            gate_a_protocol_exact,
            gate_a_passed,
            executor_conformance_report is not None,
            reference_execution is not None,
            source_identification_complete,
            input_coverage["adapter_input_coverage_gate_passed"] is True,
            implementation_bundles_staged,
            gate_b_passed,
            fidelity["external_fidelity_gate_passed"] is True,
            trust_anchors_enrolled,
            role_control_independence_attested,
            frozen_manifest is not None,
        )
    )
    design_freeze_blockers: list[str] = []
    authorization_blockers: list[str] = []
    if not source_identification_complete:
        design_freeze_blockers.append(
            "six canonical primary-source artifacts lack registered-hash acquisition binding"
        )
    if input_coverage["adapter_input_coverage_gate_passed"] is not True:
        design_freeze_blockers.append(
            "method-specific adaptation input bundles are incomplete or unbound"
        )
    if not implementation_bundles_staged:
        design_freeze_blockers.append("six external implementation bundles are not staged")
    if fidelity["native_fidelity_gate_passed"] is not True:
        authorization_blockers.append(
            "six external arms lack complete signed native reproduction evidence"
        )
    if fidelity["adaptation_fidelity_gate_passed"] is not True:
        authorization_blockers.append(
            "six external arms lack complete signed adaptation parity evidence"
        )
    if not trust_anchors_enrolled or not role_control_independence_attested:
        design_freeze_blockers.append(
            "reviewer executor and custodian keys lack an externally rooted enrollment receipt"
        )
    if executor_conformance_report is None:
        authorization_blockers.append(
            "bounded-executor capabilities lack independently signed interpreted tests"
        )
    if reference_execution is None:
        authorization_blockers.append(
            "six-arm reference execution lacks verified result and Active Dreaming artifacts"
        )
    if not gate_a_report_content_bound or not gate_a_protocol_exact:
        authorization_blockers.append(
            "v0.6 Gate A lacks verified inputs, execution log, or dual signatures"
        )
    elif not gate_a_passed:
        authorization_blockers.append("v0.6 Gate A did not pass")
    if not gate_b_scored:
        authorization_blockers.append("v0.6 signed mechanism-action traces are missing or invalid")
    elif not gate_b_passed:
        authorization_blockers.append("v0.6 signed Gate B was scored and did not pass")
    if frozen_manifest is None:
        authorization_blockers.append(
            "v0.6 canonical design lacks authority-timestamped triple-signed external freeze"
        )
    blockers = [*design_freeze_blockers, *authorization_blockers]
    typed_input_schema_path = Path(__file__).with_name("structure_two_external_inputs_v0_6.py")
    typed_input_schema_source_sha256 = hashlib.sha256(
        typed_input_schema_path.read_bytes()
    ).hexdigest()
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_index_sha256": hashlib.sha256(
            resolved_evidence_index_path.read_bytes()
        ).hexdigest(),
        "evidence_index_status": evidence_index["status"],
        "v0_6_manifest_sha256": hashlib.sha256(draft_path.read_bytes()).hexdigest(),
        "v0_6_manifest_status": draft["status"],
        "external_method_source_register_sha256": hashlib.sha256(
            source_register_path.read_bytes()
        ).hexdigest(),
        "external_method_source_register_content_sha256": (source_register_content_sha256),
        "external_method_source_identification": source_identification_rows,
        "external_method_source_identification_complete": (source_identification_complete),
        "external_reference_core_register_sha256": hashlib.sha256(
            reference_core_register_path.read_bytes()
        ).hexdigest(),
        "typed_adaptation_input_schema_source_sha256": (typed_input_schema_source_sha256),
        "typed_adaptation_input_contract_verified_by_complete_bundle": (
            complete_input_bundle_valid
        ),
        "external_reference_component_core_count": len(reference_rows),
        "external_reference_cores_are_native_reproductions": False,
        "executor_capabilities_verified_by_signed_conformance": (
            executor_conformance_report is not None
        ),
        "executor_conformance_report": executor_conformance_report,
        "executor_conformance_validation_error": (executor_conformance_validation_error),
        "bounded_six_arm_execution_runner_implemented": (reference_execution is not None),
        "active_dreaming_content_bound_scenario_executor_implemented": (
            executor_conformance_report is not None
        ),
        "active_dreaming_executor_requires_independent_ed25519_receipt": (
            executor_conformance_report is not None
        ),
        "active_dreaming_zero_cluster_fails_closed": (executor_conformance_report is not None),
        "active_dreaming_cluster_failure_rule_binding_implemented": (
            executor_conformance_report is not None
        ),
        "active_dreaming_executor_resource_bounds_implemented": (
            executor_conformance_report is not None
        ),
        "active_dreaming_deterministic_failures_are_signed": (
            executor_conformance_report is not None
        ),
        "v0_7_six_arm_reference_execution_run": reference_execution is not None,
        "v0_7_six_arm_reference_execution": reference_execution,
        "v0_7_six_arm_reference_execution_validation_error": (reference_execution_validation_error),
        "bounded_execution_is_native_protocol_reproduction": False,
        "official_component_parity": official_component_parity,
        "historical_v0_5_current_copy_self_consistent": True,
        "historical_v0_5_inventory_recomputable": historical_v0_5_audit[
            "historical_inventory_recomputable"
        ],
        "historical_v0_5_external_immutability_verified": historical_v0_5_audit[
            "trust_anchor_externally_immutable"
        ],
        "historical_v0_5_evidence_authenticity_and_integrity_verified": (
            historical_v0_5_audit["historical_evidence_authenticity_and_integrity_verified"]
        ),
        "historical_v0_5_gate_b_passed": legacy.get("gate_b_passed"),
        "historical_v0_5_content_sha256": legacy.get("content_sha256"),
        "complete_adaptation_input_bundle_valid": complete_input_bundle_valid,
        "adapter_input_coverage": input_coverage,
        "external_implementation_bundles_content_bound": implementation_bundles_staged,
        "external_fidelity": fidelity,
        "trust_anchor_registry_externally_verified": trust_anchors_enrolled,
        "trust_anchor_registry_validation_error": trust_registry_validation_error,
        "trust_anchor_role_keys_cryptographically_distinct": trust_anchors_enrolled,
        "role_control_independence_attested": role_control_independence_attested,
        "role_control_independence_cryptographically_proven": False,
        "externally_frozen_manifest_verified": frozen_manifest is not None,
        "freeze_ordering_attested_by_enrollment_authority": (frozen_manifest is not None),
        "immutable_frozen_manifest_sha256": (
            frozen_manifest.immutable_manifest_sha256 if frozen_manifest else None
        ),
        "frozen_manifest_validation_error": frozen_manifest_validation_error,
        "gate_a_report_content_bound": gate_a_report_content_bound,
        "gate_a_protocol_exact": gate_a_protocol_exact,
        "gate_a_passed": gate_a_passed,
        "gate_a_validation_error": gate_a_validation_error,
        "signed_gate_b": gate_b_report,
        "gate_b_validation_error": gate_b_validation_error,
        "v0_6_gate_b_scored": gate_b_scored,
        "v0_6_gate_b_passed": gate_b_passed,
        "external_method_efficacy_comparison_allowed": combined_authorization_allowed,
        "design_evidence_ready_for_external_freeze": (design_evidence_ready_for_external_freeze),
        "ready_for_external_custodian_run": (
            frozen_manifest is not None
            and reference_execution is not None
            and executor_conformance_report is not None
            and gate_a_passed
            and fidelity["native_fidelity_gate_passed"] is True
            and fidelity["adaptation_fidelity_gate_passed"] is True
        ),
        "lifecycle_state": (
            "EFFICACY_AUTHORIZED"
            if combined_authorization_allowed
            else "GATE_B_SCORED_NOT_AUTHORIZED"
            if gate_b_scored
            else "EXTERNALLY_FROZEN_AWAITING_EXECUTION"
            if frozen_manifest is not None
            else "READY_TO_FREEZE_DESIGN"
            if design_evidence_ready_for_external_freeze
            else "DEVELOPMENT_EVIDENCE_INCOMPLETE"
        ),
        "design_freeze_blockers": design_freeze_blockers,
        "authorization_blockers": authorization_blockers,
        "blockers": blockers,
        "claim_boundary": (
            "This preflight accepts role keys only through an out-of-band-rooted enrollment "
            "authority, requires registered-hash source acquisition, interpreted signed "
            "executor tests and full six-arm result artifacts, and verifies dual-signed Gate A "
            "before Gate B scoring. Freeze ordering is an enrollment-authority attestation "
            "over a timestamp, ledger sequence, nonce, preregistered producer run, validation "
            "seed commitment, and holdout commitment; this repository cannot independently "
            "derive external time or human role-control independence. Historical v0.5 evidence "
            "remains self-consistent but not externally immutable or fully authenticatable."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "DEFAULT_DRAFT",
    "DEFAULT_EVIDENCE_INDEX",
    "DEFAULT_LEGACY_RESULT",
    "DEFAULT_OFFICIAL_COMPONENT_PARITY",
    "DEFAULT_OUTPUT",
    "DEFAULT_REFERENCE_CORE_REGISTER",
    "DEFAULT_SOURCE_REGISTER",
    "PROTOCOL_ID",
    "build_v0_6_development_readiness",
]
