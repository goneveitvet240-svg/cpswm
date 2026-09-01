"""Combined external-method efficacy authorization for Structure Two v0.6."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cpswm.system.attestation import Ed25519AttestationVerifier
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
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_reference_cores_v0_6 import (
    ReferenceCoreResult,
    execution_log_entries_from_reference_core,
)
from cpswm.system.evaluation_operations.structure_two_frozen_run_v0_8 import (
    load_frozen_holdout_opening_v0_8,
    recompute_frozen_holdout_v0_8,
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
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    compute_producer_source_bundle,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-efficacy-authorization@0.6"


def run_external_efficacy_authorization_v0_6(
    *,
    canonical_gate_b_draft: Mapping[str, Any],
    gate_a_spec: Mapping[str, Any],
    externally_frozen_manifest: Mapping[str, Any],
    source_register: Mapping[str, Any],
    trust_anchor_registry: Mapping[str, Any],
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    gate_a_report: Mapping[str, Any],
    gate_a_artifact_paths: GateAArtifactPathsV06,
    available_inputs_by_arm: Mapping[str, Sequence[str]],
    input_bundle_paths_by_arm: Mapping[str, Path],
    input_bundle_sha256_by_arm: Mapping[str, str],
    external_evidence_by_arm: Mapping[str, ExternalMethodEvidence],
    external_artifact_paths_by_arm: Mapping[str, ExternalEvidenceArtifactPaths],
    source_acquisition_receipts_by_arm: Mapping[str, Mapping[str, Any]],
    signed_gate_b_payloads: Sequence[Mapping[str, Any]],
    producer_source_bundle_sha256: str,
    expected_arm_implementation_bundles: Mapping[str, str],
    repository_root: Path,
    executor_conformance_report: Mapping[str, Any] | None = None,
    executor_conformance_test_artifact_path: Path | None = None,
    six_arm_reference_execution_report: Mapping[str, Any] | None = None,
    six_arm_result_artifact_paths_by_arm: Mapping[str, Path] | None = None,
    active_scenario_receipt_paths: Mapping[str, Path] | None = None,
    active_scenario_program_paths: Mapping[str, Path] | None = None,
    gate_b_execution_artifact_path: Path | None = None,
) -> dict[str, Any]:
    comparisons, requirements = validate_structure_two_gate_b_v0_6_draft(canonical_gate_b_draft)
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
        custodian=role_verifiers["custodian"],
        enrollment_authority=trusted_enrollment_authority,
    )
    current_source_bundle = compute_producer_source_bundle(repository_root)
    if (
        producer_source_bundle_sha256 != current_source_bundle.content_sha256
        or frozen_manifest.producer_source_bundle_sha256 != current_source_bundle.content_sha256
    ):
        raise ValueError("authorization producer source differs from current frozen source")
    if dict(expected_arm_implementation_bundles) != (
        frozen_manifest.arm_implementation_bundle_sha256
    ):
        raise ValueError("authorization implementation identities differ from the freeze")
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
    gate_a_content_sha256 = gate_a_report.get("content_sha256")
    assert isinstance(gate_a_content_sha256, str)
    opening = load_frozen_holdout_opening_v0_8(
        gate_a_artifact_paths.frozen_holdout_opening,
        expected_manifest_sha256=frozen_manifest.immutable_manifest_sha256,
        expected_producer_run_id=frozen_manifest.preregistered_producer_run_id,
        expected_validation_seed_commitment_sha256=(
            frozen_manifest.validation_seed_commitment_sha256
        ),
        expected_holdout_commitment_sha256=frozen_manifest.holdout_commitment_sha256,
    )
    recomputed_holdout = recompute_frozen_holdout_v0_8(opening)
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
        raise ValueError("combined authorization source-register arm set mismatch")
    source_row_by_arm = {str(row["arm"]): row for row in source_rows if isinstance(row, dict)}
    for specification in specifications:
        row = source_row_by_arm[specification.arm]
        if (
            row.get("method") != specification.method
            or row.get("primary_source_url") != specification.primary_source_url
            or not isinstance(row.get("primary_source_sha256"), str)
            or len(str(row["primary_source_sha256"])) != 64
            or any(char not in "0123456789abcdef" for char in str(row["primary_source_sha256"]))
            or not isinstance(row.get("evidence_level"), str)
            or not row.get("evidence_level")
            or (
                specification.official_code_required
                and (
                    row.get("repository_url") != specification.official_code_url
                    or row.get("repository_commit") != specification.official_code_commit
                )
            )
        ):
            raise ValueError("combined authorization source-register row is noncanonical")
    source_acquisition_errors: dict[str, str] = {}
    source_acquisition_verified = (
        set(source_acquisition_receipts_by_arm) == expected_external_arms
        and set(external_artifact_paths_by_arm) == expected_external_arms
    )
    if source_acquisition_verified:
        for specification in specifications:
            try:
                paths = external_artifact_paths_by_arm[specification.arm]
                verify_primary_source_acquisition_receipt_v0_6(
                    source_acquisition_receipts_by_arm[specification.arm],
                    expected_arm=specification.arm,
                    source_row=source_row_by_arm[specification.arm],
                    source_artifact=paths.primary_source,
                    source_register_content_sha256=(frozen_manifest.source_register_content_sha256),
                    trusted_acquirer=role_verifiers["reviewer"],
                    official_checkout=paths.official_code_checkout,
                )
            except (OSError, ValueError) as exc:
                source_acquisition_errors[specification.arm] = str(exc)
        source_acquisition_verified = not source_acquisition_errors
    input_coverage = run_adapter_input_coverage_gate(
        specifications,
        available_inputs_by_arm,
        input_bundle_paths_by_arm=input_bundle_paths_by_arm,
        input_bundle_sha256_by_arm=input_bundle_sha256_by_arm,
    )
    fidelity = run_external_fidelity_gate_v0_2(
        specifications,
        external_evidence_by_arm,
        artifact_paths_by_arm=external_artifact_paths_by_arm,
        trusted_reviewer_key_id=role_verifiers["reviewer"].key_id,
        trusted_reviewer_public_key_sha256=(role_verifiers["reviewer"].public_key_sha256),
        trusted_executor_key_id=role_verifiers["executor"].key_id,
        trusted_executor_public_key_sha256=(role_verifiers["executor"].public_key_sha256),
    )
    implementation_identity_aligned = set(
        external_evidence_by_arm
    ) == expected_external_arms and all(
        external_evidence_by_arm[arm].implementation_bundle_sha256
        == expected_arm_implementation_bundles[arm]
        for arm in expected_external_arms
    )
    conformance_verified = False
    conformance_validation_error: str | None = None
    if (
        executor_conformance_report is not None
        and executor_conformance_test_artifact_path is not None
    ):
        try:
            verify_executor_conformance_v0_7(
                executor_conformance_report,
                test_artifact_path=executor_conformance_test_artifact_path,
                repository_root=repository_root,
                producer_source_bundle_sha256=producer_source_bundle_sha256,
                trusted_tester=role_verifiers["reviewer"],
                trusted_executor=role_verifiers["executor"],
            )
            conformance_verified = True
        except (OSError, ValueError) as exc:
            conformance_validation_error = str(exc)
    six_arm_execution_verified = False
    six_arm_execution_validation_error: str | None = None
    if (
        six_arm_reference_execution_report is not None
        and six_arm_result_artifact_paths_by_arm is not None
        and active_scenario_receipt_paths is not None
        and active_scenario_program_paths is not None
    ):
        try:
            six_input_hashes = {input_bundle_sha256_by_arm[arm] for arm in CANONICAL_SIX_ARMS}
            six_input_paths = {input_bundle_paths_by_arm[arm] for arm in CANONICAL_SIX_ARMS}
            if len(six_input_hashes) != 1 or len(six_input_paths) != 1:
                raise ValueError("six-arm execution input-bundle artifact is not unique")
            expected_source_hashes = {
                arm: external_artifact_sha256(external_artifact_paths_by_arm[arm].primary_source)
                for arm in CANONICAL_SIX_ARMS
            }
            verify_six_arm_reference_execution_v0_7(
                six_arm_reference_execution_report,
                expected_input_bundle_sha256=next(iter(six_input_hashes)),
                input_bundle_artifact_path=next(iter(six_input_paths)),
                expected_source_artifact_sha256_by_arm=expected_source_hashes,
                expected_implementation_bundle_sha256_by_arm={
                    arm: expected_arm_implementation_bundles[arm] for arm in CANONICAL_SIX_ARMS
                },
                arm_result_artifact_paths_by_arm=(six_arm_result_artifact_paths_by_arm),
                active_scenario_receipt_paths=active_scenario_receipt_paths,
                active_scenario_program_paths=active_scenario_program_paths,
                trusted_executor=role_verifiers["executor"],
                trusted_scenario_executor=role_verifiers["executor"],
                expected_immutable_manifest_sha256=(frozen_manifest.immutable_manifest_sha256),
                expected_producer_run_id=(frozen_manifest.preregistered_producer_run_id),
                expected_producer_source_bundle_sha256=(producer_source_bundle_sha256),
            )
            six_arm_execution_verified = True
        except (KeyError, OSError, ValueError) as exc:
            six_arm_execution_validation_error = str(exc)
    expected_event_component_ids = {
        requirement.arm: {
            event: CANONICAL_COMPONENT_IDS[requirement.arm] for event in requirement.required_events
        }
        for requirement in requirements
    }
    gate_b_prerequisites_present = (
        conformance_verified
        and six_arm_execution_verified
        and gate_b_execution_artifact_path is not None
        and six_arm_reference_execution_report is not None
        and six_arm_result_artifact_paths_by_arm is not None
    )
    if gate_b_prerequisites_present:
        expected_external_logs = {}
        assert six_arm_result_artifact_paths_by_arm is not None
        assert six_arm_reference_execution_report is not None
        for arm in CANONICAL_SIX_ARMS:
            result_payload = json.loads(six_arm_result_artifact_paths_by_arm[arm].read_bytes())
            if not isinstance(result_payload, dict):
                raise ValueError("six-arm result artifact is not a JSON object")
            result_payload.pop("content_sha256", None)
            result = ReferenceCoreResult.model_validate(result_payload)
            expected_external_logs[arm] = execution_log_entries_from_reference_core(
                result,
                invocation_prefix=(
                    f"{frozen_manifest.immutable_manifest_sha256}:"
                    f"{frozen_manifest.preregistered_producer_run_id}:{arm}"
                ),
                implementation_bundle_sha256=(expected_arm_implementation_bundles[arm]),
            )
        six_arm_content_sha256 = six_arm_reference_execution_report.get("content_sha256")
        if not isinstance(six_arm_content_sha256, str):
            raise ValueError("six-arm reference execution lacks a content hash")
        assert gate_b_execution_artifact_path is not None
        signed_gate_b = run_signed_stratified_gate_b_v0_6(
            signed_gate_b_payloads,
            expected_arms=tuple(canonical_gate_b_draft["expected_arms"]),
            comparison_pairs=comparisons,
            mechanism_requirements=requirements,
            gate_a_content_sha256=gate_a_content_sha256,
            manifest_sha256=frozen_manifest.immutable_manifest_sha256,
            producer_source_bundle_sha256=producer_source_bundle_sha256,
            expected_arm_implementation_bundles=expected_arm_implementation_bundles,
            expected_event_component_ids=expected_event_component_ids,
            expected_producer_run_id=frozen_manifest.preregistered_producer_run_id,
            trusted_custodian_key_id=role_verifiers["custodian"].key_id,
            trusted_custodian_public_key_sha256=(role_verifiers["custodian"].public_key_sha256),
            canonical_execution_artifact_path=gate_b_execution_artifact_path,
            recomputed_holdout=recomputed_holdout,
            expected_six_arm_reference_execution_content_sha256=(six_arm_content_sha256),
            expected_holdout_opening_artifact_file_sha256=(
                external_artifact_sha256(gate_a_artifact_paths.frozen_holdout_opening)
            ),
            trusted_executor=role_verifiers["executor"],
            expected_external_execution_log_entries_by_arm=(expected_external_logs),
        )
        gate_b_execution_verified = True
    else:
        signed_gate_b = {
            "protocol": "structure-two-signed-stratified-gate-b@0.6",
            "status": "NOT_SCORED_MISSING_EXECUTION_EVIDENCE",
            "gate_b_passed": False,
            "external_method_efficacy_comparison_allowed": False,
            "claim_boundary": (
                "No Gate B score exists until conformance, six-arm result artifacts, "
                "and a deterministically recomputed ten-arm execution artifact are verified."
            ),
        }
        signed_gate_b["content_sha256"] = content_sha256(signed_gate_b)
        gate_b_execution_verified = False
    checks = {
        "trust_anchor_registry_externally_attested": True,
        "role_control_independence_attested": (registry.role_control_independence_attested is True),
        "externally_frozen_manifest_dual_signature_verified": True,
        "immutable_frozen_manifest_identifier_verified": True,
        "gate_a_report_content_bound": True,
        "gate_a_protocol_exact": True,
        "gate_a_passed": True,
        "executor_conformance_artifact_verified": conformance_verified,
        "six_arm_reference_execution_artifacts_verified": (six_arm_execution_verified),
        "implementation_identity_chain_aligned": implementation_identity_aligned,
        "gate_b_execution_artifact_verified": gate_b_execution_verified,
        "canonical_six_arm_input_coverage_passed": input_coverage[
            "adapter_input_coverage_gate_passed"
        ]
        is True,
        "six_signed_source_acquisition_receipts_verified": (source_acquisition_verified),
        "canonical_signed_gate_b_passed": signed_gate_b["gate_b_passed"] is True,
        "canonical_artifact_verified_fidelity_passed": fidelity["external_fidelity_gate_passed"]
        is True,
    }
    allowed = all(checks.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "checks": checks,
        "trust_anchor_registry_identifier": registry.registry_identifier,
        "immutable_frozen_manifest_sha256": (frozen_manifest.immutable_manifest_sha256),
        "adapter_input_coverage": input_coverage,
        "source_acquisition_receipts_verified": source_acquisition_verified,
        "source_acquisition_validation_errors": source_acquisition_errors,
        "executor_conformance_verified": conformance_verified,
        "executor_conformance_validation_error": conformance_validation_error,
        "six_arm_reference_execution_verified": six_arm_execution_verified,
        "six_arm_reference_execution_validation_error": (six_arm_execution_validation_error),
        "signed_gate_b": signed_gate_b,
        "external_fidelity": fidelity,
        "external_method_efficacy_comparison_allowed": allowed,
        "claim_boundary": (
            "Authorization recomputes the exact canonical six-arm input and fidelity gates "
            "and the signed ten-arm Gate B from raw evidence. Gate A is recomputed from "
            "dual-signed input and execution artifacts before Gate B scoring. Final efficacy "
            "also requires independently tested executor conformance and six real arm-result "
            "artifacts with verified Active Dreaming receipts. Traces must use the producer "
            "run preregistered in the authority-timestamped frozen manifest."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = ["PROTOCOL_ID", "run_external_efficacy_authorization_v0_6"]
