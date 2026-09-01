from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    EVIDENCE_ATTESTATION_DOMAIN,
    EXECUTION_ATTESTATION_DOMAIN,
    ExternalEvidenceArtifactPaths,
    ExternalMethodEvidence,
    ExternalMethodSpecification,
    attested_external_method_evidence_payload,
    default_external_method_specifications_v0_2,
    external_artifact_sha256,
    run_external_fidelity_gate_v0_2,
)

HASH = "a" * 64
SIGNER = Ed25519AttestationSigner.generate(key_id="external-reviewer")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-executor")


def _spec(*, code_required: bool = False) -> ExternalMethodSpecification:
    return ExternalMethodSpecification(
        arm="external",
        method="External Method",
        native_domain="native task",
        primary_source_url="https://example.org/paper",
        required_native_components=("component-a", "component-b"),
        required_adaptation_inputs=("input-a",),
        official_code_required=code_required,
    )


def _artifact_paths(tmp_path: Path) -> ExternalEvidenceArtifactPaths:
    paths = ExternalEvidenceArtifactPaths(
        primary_source=tmp_path / "paper.pdf",
        implementation_bundle=tmp_path / "implementation.py",
        component_parity_receipt=tmp_path / "component.json",
        component_parity_execution_log=tmp_path / "component.log",
        native_protocol_recheck_receipt=tmp_path / "native.json",
        native_protocol_execution_log=tmp_path / "native.log",
        adaptation_contract=tmp_path / "adaptation.json",
        adaptation_parity_receipt=tmp_path / "adaptation-parity.json",
        adaptation_parity_execution_log=tmp_path / "adaptation-parity.log",
    )
    paths.primary_source.write_bytes(b"paper")
    paths.implementation_bundle.write_text("implementation", encoding="utf-8")
    for log_path in (
        paths.component_parity_execution_log,
        paths.native_protocol_execution_log,
        paths.adaptation_parity_execution_log,
    ):
        log_path.write_text("1 passed\n", encoding="utf-8")
    implementation_sha256 = external_artifact_sha256(paths.implementation_bundle)

    def execution(log_path: Path) -> dict[str, object]:
        return {
            "command": ["pytest", "-q"],
            "exit_code": 0,
            "log_sha256": external_artifact_sha256(log_path),
            "implementation_bundle_sha256": implementation_sha256,
        }

    receipts = (
        (
            paths.component_parity_receipt,
            {
                "protocol": "structure-two-component-parity-receipt@0.6",
                "arm": "external",
                "component_parity_passed": True,
                "execution": execution(paths.component_parity_execution_log),
            },
        ),
        (
            paths.native_protocol_recheck_receipt,
            {
                "protocol": "structure-two-native-protocol-recheck@0.6",
                "arm": "external",
                "native_protocol_reproduction_passed": True,
                "execution": execution(paths.native_protocol_execution_log),
            },
        ),
        (
            paths.adaptation_contract,
            {
                "protocol": "structure-two-external-adaptation-contract@0.6",
                "arm": "external",
            },
        ),
        (
            paths.adaptation_parity_receipt,
            {
                "protocol": "structure-two-adaptation-parity-receipt@0.6",
                "arm": "external",
                "adaptation_parity_passed": True,
                "execution": execution(paths.adaptation_parity_execution_log),
            },
        ),
    )
    executor_verifier = EXECUTOR.verifier()
    for path, payload in receipts:
        if "execution" in payload:
            payload = {
                **payload,
                "executor_key_id": executor_verifier.key_id,
                "executor_public_key_base64": executor_verifier.public_key_base64,
                "executor_public_key_sha256": executor_verifier.public_key_sha256,
                "executor_attestation": EXECUTOR.sign(
                    EXECUTION_ATTESTATION_DOMAIN,
                    payload,
                ).model_dump(mode="json"),
            }
        path.write_text(json.dumps(payload), encoding="utf-8")
    return paths


def _complete_evidence(
    tmp_path: Path,
) -> tuple[ExternalMethodEvidence, ExternalEvidenceArtifactPaths]:
    verifier = SIGNER.verifier()
    paths = _artifact_paths(tmp_path)
    unsigned = ExternalMethodEvidence(
        arm="external",
        primary_source_sha256=external_artifact_sha256(paths.primary_source),
        implementation_bundle_sha256=external_artifact_sha256(paths.implementation_bundle),
        verified_native_components=("component-a", "component-b"),
        component_parity_receipt_sha256=external_artifact_sha256(paths.component_parity_receipt),
        native_protocol_recheck_receipt_sha256=external_artifact_sha256(
            paths.native_protocol_recheck_receipt
        ),
        adaptation_contract_sha256=external_artifact_sha256(paths.adaptation_contract),
        adaptation_parity_receipt_sha256=external_artifact_sha256(paths.adaptation_parity_receipt),
        reviewer_key_id=verifier.key_id,
        reviewer_public_key_base64=verifier.public_key_base64,
        reviewer_public_key_sha256=verifier.public_key_sha256,
    )
    return (
        replace(
            unsigned,
            attestation=SIGNER.sign(
                EVIDENCE_ATTESTATION_DOMAIN,
                attested_external_method_evidence_payload(unsigned),
            ),
        ),
        paths,
    )


def _run(
    evidence: ExternalMethodEvidence,
    paths: ExternalEvidenceArtifactPaths,
) -> dict[str, object]:
    verifier = SIGNER.verifier()
    executor_verifier = EXECUTOR.verifier()
    return run_external_fidelity_gate_v0_2(
        (_spec(),),
        {"external": evidence},
        artifact_paths_by_arm={"external": paths},
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
        trusted_executor_key_id=executor_verifier.key_id,
        trusted_executor_public_key_sha256=executor_verifier.public_key_sha256,
        enforce_canonical_catalog=False,
    )


def test_missing_evidence_fails_closed_with_machine_readable_gaps() -> None:
    report = run_external_fidelity_gate_v0_2((_spec(),), {}, enforce_canonical_catalog=False)
    row = report["method_results"][0]
    assert report["external_fidelity_gate_passed"] is False
    assert row["native_fidelity_passed"] is False
    assert row["adaptation_fidelity_passed"] is False
    assert "native_published_protocol_rechecked" in row["missing_requirements"]


def test_native_pass_does_not_authorize_cross_domain_adaptation(tmp_path: Path) -> None:
    complete, paths = _complete_evidence(tmp_path)
    evidence = replace(
        complete,
        adaptation_contract_sha256=None,
        adaptation_parity_receipt_sha256=None,
    )
    unsigned = replace(evidence, attestation=None)
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    row = report["method_results"][0]
    assert row["native_fidelity_passed"] is True
    assert row["adaptation_fidelity_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_complete_content_bound_evidence_is_only_a_combined_gate_precondition(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    report = _run(evidence, paths)
    assert report["native_fidelity_gate_passed"] is True
    assert report["adaptation_fidelity_gate_passed"] is True
    assert report["fidelity_precondition_for_combined_authorization_passed"] is True
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_reviewer_signature_without_independent_executor_anchor_cannot_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    report = run_external_fidelity_gate_v0_2(
        (_spec(),),
        {"external": evidence},
        artifact_paths_by_arm={"external": paths},
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
        enforce_canonical_catalog=False,
    )
    assert report["external_fidelity_gate_passed"] is False


def test_reviewer_and_executor_cannot_reuse_one_trust_key(tmp_path: Path) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    with pytest.raises(ValueError, match="must be independent keys"):
        run_external_fidelity_gate_v0_2(
            (_spec(),),
            {"external": evidence},
            artifact_paths_by_arm={"external": paths},
            trusted_reviewer_key_id=verifier.key_id,
            trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
            enforce_canonical_catalog=False,
        )


def test_component_subset_cannot_be_mislabeled_as_complete(tmp_path: Path) -> None:
    complete, paths = _complete_evidence(tmp_path)
    evidence = replace(complete, verified_native_components=("component-a",))
    unsigned = replace(evidence, attestation=None)
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    assert report["method_results"][0]["native_fidelity_passed"] is False


def test_candidate_self_signed_evidence_cannot_impersonate_reviewer(tmp_path: Path) -> None:
    attacker = Ed25519AttestationSigner.generate(key_id=SIGNER.key_id)
    evidence, paths = _complete_evidence(tmp_path)
    attacker_verifier = attacker.verifier()
    unsigned = replace(
        evidence,
        reviewer_public_key_base64=attacker_verifier.public_key_base64,
        reviewer_public_key_sha256=attacker_verifier.public_key_sha256,
        attestation=None,
    )
    forged = replace(
        unsigned,
        attestation=attacker.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    with pytest.raises(AttestationError, match="trust-anchor mismatch"):
        _run(forged, paths)


def test_modifying_reviewed_evidence_breaks_signature(tmp_path: Path) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    modified = replace(evidence, adaptation_contract_sha256="b" * 64)
    with pytest.raises(AttestationError, match="signature does not match"):
        _run(modified, paths)


def test_default_catalog_retains_all_six_external_arms_and_has_no_empty_specs() -> None:
    specifications = default_external_method_specifications_v0_2()
    assert {item.arm for item in specifications} == {
        "corrected_amg",
        "o_star_matched",
        "active_dreaming_matched",
        "auto_dreamer_matched",
        "trustmem_matched",
        "brainctl_matched",
    }
    assert all(item.required_native_components for item in specifications)
    assert all(item.required_adaptation_inputs for item in specifications)


def test_one_arm_catalog_cannot_pass_the_formal_fidelity_gate() -> None:
    with pytest.raises(ValueError, match="canonical six-arm catalog"):
        run_external_fidelity_gate_v0_2((_spec(),), {})


def test_signed_fictional_hashes_do_not_verify_real_artifacts(tmp_path: Path) -> None:
    _complete, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    unsigned = ExternalMethodEvidence(
        arm="external",
        primary_source_sha256=HASH,
        implementation_bundle_sha256=HASH,
        verified_native_components=("component-a", "component-b"),
        component_parity_receipt_sha256=HASH,
        native_protocol_recheck_receipt_sha256=HASH,
        adaptation_contract_sha256=HASH,
        adaptation_parity_receipt_sha256=HASH,
        reviewer_key_id=verifier.key_id,
        reviewer_public_key_base64=verifier.public_key_base64,
        reviewer_public_key_sha256=verifier.public_key_sha256,
    )
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    assert report["external_fidelity_gate_passed"] is False
    assert report["method_results"][0]["checks"]["primary_source_content_bound"] is False


def test_trusted_signature_over_six_arms_of_fictional_artifacts_still_fails() -> None:
    verifier = SIGNER.verifier()
    evidence_by_arm: dict[str, ExternalMethodEvidence] = {}
    for specification in default_external_method_specifications_v0_2():
        unsigned = ExternalMethodEvidence(
            arm=specification.arm,
            primary_source_sha256=HASH,
            official_code_url="x",
            official_code_commit="x",
            implementation_bundle_sha256=HASH,
            verified_native_components=specification.required_native_components,
            component_parity_receipt_sha256=HASH,
            native_protocol_recheck_receipt_sha256=HASH,
            adaptation_contract_sha256=HASH,
            adaptation_parity_receipt_sha256=HASH,
            reviewer_key_id=verifier.key_id,
            reviewer_public_key_base64=verifier.public_key_base64,
            reviewer_public_key_sha256=verifier.public_key_sha256,
        )
        evidence_by_arm[specification.arm] = replace(
            unsigned,
            attestation=SIGNER.sign(
                EVIDENCE_ATTESTATION_DOMAIN,
                attested_external_method_evidence_payload(unsigned),
            ),
        )
    report = run_external_fidelity_gate_v0_2(
        default_external_method_specifications_v0_2(),
        evidence_by_arm,
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
    )
    assert report["external_fidelity_gate_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_receipt_hash_with_failed_execution_semantics_does_not_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    failed = {
        "protocol": "structure-two-adaptation-parity-receipt@0.6",
        "arm": "external",
        "adaptation_parity_passed": False,
        "execution": {
            "command": ["pytest", "-q"],
            "exit_code": 0,
            "log_sha256": external_artifact_sha256(paths.adaptation_parity_execution_log),
            "implementation_bundle_sha256": evidence.implementation_bundle_sha256,
        },
    }
    paths.adaptation_parity_receipt.write_text(json.dumps(failed), encoding="utf-8")
    unsigned = replace(
        evidence,
        adaptation_parity_receipt_sha256=external_artifact_sha256(paths.adaptation_parity_receipt),
        attestation=None,
    )
    resigned = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(resigned, paths)
    assert report["method_results"][0]["adaptation_fidelity_passed"] is False


def test_receipt_with_missing_execution_log_or_nonzero_exit_does_not_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    receipt = json.loads(paths.component_parity_receipt.read_text(encoding="utf-8"))
    receipt["execution"]["exit_code"] = 1
    paths.component_parity_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    unsigned = replace(
        evidence,
        component_parity_receipt_sha256=external_artifact_sha256(paths.component_parity_receipt),
        attestation=None,
    )
    resigned = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(resigned, paths)
    assert report["method_results"][0]["native_fidelity_passed"] is False
