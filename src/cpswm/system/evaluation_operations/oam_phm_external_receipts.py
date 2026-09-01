"""Authority receipts for OAM-PHM external reproduction evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware, utc_now
from cpswm.system.attestation import (
    DOMAIN_OAM_EXTERNAL_EVIDENCE_RECEIPT,
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

from .independent_test_process import (
    IndependentTestProcessReceipt,
    verify_independent_test_process_receipt,
)
from .oam_phm_external_evidence import ExternalReproductionManifest

OAM_EXTERNAL_EVIDENCE_RECEIPT_VERSION = "oam-external-evidence-receipt@0.1"

CANONICAL_EXTERNAL_REQUIREMENT_IDS = {
    "o_star": frozenset(
        {
            "primary-source-frozen",
            "semantic-prior",
            "geometric-grounding",
            "dirichlet-update-core",
            "relaxed-transition-inference",
            "cost-aware-active-search",
            "opportunistic-multi-target-perception",
            "published-result-recheck",
        }
    ),
    "streak": frozenset(
        {
            "primary-source-frozen",
            "gtm-architecture",
            "streaming-graph-update",
            "three-part-model-loss",
            "fisher-consolidation",
            "mean-feature-rehearsal",
            "independent-hyperparameter-search",
            "homer-sequential-recheck",
        }
    ),
}


class OAMExternalEvidenceVerdict(StrEnum):
    ACCEPTED_FOR_MATCHED_COMPARISON = "accepted_for_matched_comparison"
    BLOCKED = "blocked"


class OAMExternalEvidenceReceipt(ContractModel):
    receipt_version: str = OAM_EXTERNAL_EVIDENCE_RECEIPT_VERSION
    reproduction_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method: str = Field(min_length=1)
    primary_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_dataset_signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_process_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independently_tuned_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_artifact_sha256s: tuple[str, ...] = Field(min_length=1)
    verdict: OAMExternalEvidenceVerdict
    issued_at: datetime = Field(default_factory=utc_now)
    attestation: Attestation | None = None

    @field_validator("issued_at")
    @classmethod
    def _aware_time(cls, value: datetime) -> datetime:
        return require_aware(value, "issued_at")

    @model_validator(mode="after")
    def _receipt_semantics(self) -> Self:
        if self.receipt_version != OAM_EXTERNAL_EVIDENCE_RECEIPT_VERSION:
            raise ValueError("unsupported OAM external-evidence receipt version")
        if len(self.result_artifact_sha256s) != len(set(self.result_artifact_sha256s)):
            raise ValueError("OAM external evidence artifacts must be unique")
        return self

    def attested_content(self) -> dict[str, object]:
        return attested_payload(self)

    @property
    def receipt_sha256(self) -> str:
        return content_sha256(self)


def issue_oam_external_evidence_receipt(
    *,
    reproduction_manifest: ExternalReproductionManifest,
    raw_dataset_signature_sha256: str,
    frame_source_manifest_sha256: str,
    process_receipt: IndependentTestProcessReceipt,
    independently_tuned_selection_sha256: str,
    result_artifact_sha256s: tuple[str, ...],
    process_verifier: Ed25519AttestationVerifier,
    signer: Ed25519AttestationSigner,
) -> OAMExternalEvidenceReceipt:
    if not reproduction_manifest.has_canonical_fidelity_requirements:
        raise ValueError("external reproduction lacks canonical fidelity requirements")
    if not reproduction_manifest.eligible_for_formal_competition:
        raise ValueError("incomplete external reproduction cannot receive an accepted receipt")
    required_ids = CANONICAL_EXTERNAL_REQUIREMENT_IDS[reproduction_manifest.method.value]
    submitted_ids = {item.requirement_id for item in reproduction_manifest.requirements}
    if submitted_ids != required_ids:
        raise ValueError("external reproduction does not cover canonical fidelity requirements")
    verify_independent_test_process_receipt(
        process_receipt,
        verifier=process_verifier,
        require_passed=True,
    )
    expected_role = f"oam_external:{reproduction_manifest.method.value}"
    if process_receipt.process_role != expected_role:
        raise ValueError("independent process role does not match the external method")
    process_artifacts = set(process_receipt.output_artifact_sha256s.values())
    if not result_artifact_sha256s or not set(result_artifact_sha256s) <= process_artifacts:
        raise ValueError("OAM result artifacts must be outputs of the independent process")
    unsigned = OAMExternalEvidenceReceipt(
        reproduction_manifest_sha256=reproduction_manifest.content_sha256,
        method=reproduction_manifest.method.value,
        primary_source_sha256=reproduction_manifest.primary_source_sha256,
        raw_dataset_signature_sha256=raw_dataset_signature_sha256,
        frame_source_manifest_sha256=frame_source_manifest_sha256,
        independent_process_receipt_sha256=process_receipt.receipt_sha256,
        independently_tuned_selection_sha256=independently_tuned_selection_sha256,
        result_artifact_sha256s=result_artifact_sha256s,
        verdict=OAMExternalEvidenceVerdict.ACCEPTED_FOR_MATCHED_COMPARISON,
    )
    signature = signer.sign(
        DOMAIN_OAM_EXTERNAL_EVIDENCE_RECEIPT,
        unsigned.attested_content(),
    )
    return unsigned.model_copy(update={"attestation": signature})


def verify_oam_external_evidence_receipt(
    receipt: OAMExternalEvidenceReceipt,
    *,
    reproduction_manifest: ExternalReproductionManifest,
    process_receipt: IndependentTestProcessReceipt,
    raw_dataset_signature_sha256: str,
    frame_source_manifest_sha256: str,
    independently_tuned_selection_sha256: str,
    process_verifier: Ed25519AttestationVerifier,
    verifier: Ed25519AttestationVerifier,
) -> OAMExternalEvidenceReceipt:
    receipt = OAMExternalEvidenceReceipt.model_validate(receipt.model_dump(mode="python"))
    verifier.verify(
        DOMAIN_OAM_EXTERNAL_EVIDENCE_RECEIPT,
        receipt.attested_content(),
        receipt.attestation,
    )
    if not reproduction_manifest.has_canonical_fidelity_requirements:
        raise ValueError("external reproduction lacks canonical fidelity requirements")
    if not reproduction_manifest.eligible_for_formal_competition:
        raise ValueError("external reproduction is no longer eligible for formal competition")
    required_ids = CANONICAL_EXTERNAL_REQUIREMENT_IDS[reproduction_manifest.method.value]
    submitted_ids = {item.requirement_id for item in reproduction_manifest.requirements}
    if submitted_ids != required_ids:
        raise ValueError("external reproduction does not cover canonical fidelity requirements")
    if receipt.verdict is not OAMExternalEvidenceVerdict.ACCEPTED_FOR_MATCHED_COMPARISON:
        raise ValueError("OAM receipt is not accepted for matched comparison")
    if receipt.reproduction_manifest_sha256 != reproduction_manifest.content_sha256:
        raise ValueError("OAM receipt does not match the reproduction manifest")
    if receipt.primary_source_sha256 != reproduction_manifest.primary_source_sha256:
        raise ValueError("OAM receipt does not match the primary source")
    if receipt.method != reproduction_manifest.method.value:
        raise ValueError("OAM receipt does not match the external method")
    if receipt.raw_dataset_signature_sha256 != raw_dataset_signature_sha256:
        raise ValueError("OAM receipt does not match the signed raw dataset")
    if receipt.frame_source_manifest_sha256 != frame_source_manifest_sha256:
        raise ValueError("OAM receipt does not match the frame-source manifest")
    if receipt.independently_tuned_selection_sha256 != independently_tuned_selection_sha256:
        raise ValueError("OAM receipt does not match the independent tuning selection")
    verify_independent_test_process_receipt(
        process_receipt,
        verifier=process_verifier,
        require_passed=True,
    )
    if process_receipt.process_role != f"oam_external:{reproduction_manifest.method.value}":
        raise ValueError("independent process role does not match the external method")
    if receipt.independent_process_receipt_sha256 != process_receipt.receipt_sha256:
        raise ValueError("OAM receipt does not match the independent process")
    if not set(receipt.result_artifact_sha256s) <= set(
        process_receipt.output_artifact_sha256s.values()
    ):
        raise ValueError("OAM receipt result is absent from the independent process outputs")
    return receipt


__all__ = [
    "OAM_EXTERNAL_EVIDENCE_RECEIPT_VERSION",
    "OAMExternalEvidenceReceipt",
    "OAMExternalEvidenceVerdict",
    "issue_oam_external_evidence_receipt",
    "verify_oam_external_evidence_receipt",
]
