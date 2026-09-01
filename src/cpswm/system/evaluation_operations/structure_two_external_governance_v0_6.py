"""Externally rooted governance records for Structure-Two v0.6.

Repository self-hashes are useful integrity checks, but they are not roots of
trust.  This module therefore requires an out-of-band Ed25519 verifier for the
enrollment authority before role keys or a frozen design can be trusted.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
    validate_structure_two_gate_b_v0_6_draft,
)
from cpswm.system.reproducibility import content_sha256

TRUST_REGISTRY_PROTOCOL_ID = "structure-two-trust-anchor-registry@0.6"
FROZEN_MANIFEST_PROTOCOL_ID = "structure-two-externally-frozen-manifest@0.6"
TRUST_REGISTRY_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.trust_anchor_registry.v0.6"
FREEZE_REVIEWER_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_freeze.reviewer.v0.6"
FREEZE_CUSTODIAN_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.external_freeze.custodian.v0.6"
)
FREEZE_AUTHORITY_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.external_freeze.authority.v0.6"
)
TRUST_ROLES = ("reviewer", "executor", "custodian")


class EnrolledRoleKeyV06(ContractModel):
    role: str = Field(pattern=r"^(reviewer|executor|custodian)$")
    controller_identifier: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enrolled_at_utc: datetime


class TrustAnchorRegistryV06(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-trust-anchor-registry@0\.6$")
    status: str = Field(pattern=r"^EXTERNALLY_ATTESTED_BEFORE_EVIDENCE$")
    registry_identifier: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    enrollment_authority_key_id: str = Field(min_length=1)
    enrollment_authority_public_key_base64: str = Field(min_length=1)
    enrollment_authority_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    role_keys: tuple[EnrolledRoleKeyV06, ...]
    configured_before_evidence_production_attested: bool
    role_control_independence_attested: bool
    authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_exact_roles(self) -> TrustAnchorRegistryV06:
        roles = tuple(row.role for row in self.role_keys)
        if roles != TRUST_ROLES:
            raise ValueError("trust-anchor registry must contain the ordered exact role set")
        if len({row.key_id for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role key IDs must be pairwise distinct")
        if len({row.public_key_sha256 for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role public keys must be pairwise distinct")
        if len({row.controller_identifier for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role controllers must be pairwise distinct")
        return self


class FrozenGateBManifestV06(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-externally-frozen-manifest@0\.6$")
    status: str = Field(pattern=r"^EXTERNALLY_FROZEN$")
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_draft_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_register_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_spec_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_anchor_registry_identifier: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    enrollment_authority_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_at_utc: datetime
    freeze_ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: int = Field(ge=0)
    authority_nonce_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_challenge_unpredictability_attested: bool
    freeze_completed_before_evidence_production_attested: bool
    preregistered_producer_run_id: str = Field(min_length=1)
    validation_seed_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_implementation_bundle_sha256: dict[str, str]
    expected_arms: tuple[str, ...]
    reviewer_key_id: str = Field(min_length=1)
    reviewer_public_key_base64: str = Field(min_length=1)
    reviewer_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_arm_set(self) -> FrozenGateBManifestV06:
        if self.expected_arms != EXPECTED_ARMS:
            raise ValueError("frozen manifest changed the canonical ten-arm set")
        if self.frozen_at_utc.utcoffset() is None:
            raise ValueError("frozen manifest timestamp must be timezone-aware")
        if (
            self.authority_challenge_unpredictability_attested is not True
            or self.freeze_completed_before_evidence_production_attested is not True
        ):
            raise ValueError("frozen manifest lacks authority-attested sequencing")
        if tuple(self.arm_implementation_bundle_sha256) != EXPECTED_ARMS:
            raise ValueError("frozen manifest lacks the ordered ten-arm implementation set")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.arm_implementation_bundle_sha256.values()
        ):
            raise ValueError("frozen manifest contains a malformed implementation digest")
        return self


def _registry_payload(record: TrustAnchorRegistryV06) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"authority_attestation"})


def _freeze_payload(record: FrozenGateBManifestV06) -> dict[str, Any]:
    return record.model_dump(
        mode="json",
        exclude={
            "reviewer_attestation",
            "custodian_attestation",
            "authority_attestation",
        },
    )


def _role_verifier(row: EnrolledRoleKeyV06) -> Ed25519AttestationVerifier:
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=row.key_id, public_key_base64=row.public_key_base64
    )
    if verifier.public_key_sha256 != row.public_key_sha256:
        raise AttestationError("enrolled role public-key hash mismatch")
    return verifier


def make_trust_anchor_registry_v0_6(
    *,
    role_signers: Mapping[str, Ed25519AttestationSigner],
    controller_identifiers: Mapping[str, str],
    enrolled_at_utc: datetime,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    if tuple(role_signers) != TRUST_ROLES or tuple(controller_identifiers) != TRUST_ROLES:
        raise ValueError("trust-anchor enrollment requires the ordered exact role set")
    authority_verifier = enrollment_authority.verifier()
    rows = tuple(
        EnrolledRoleKeyV06(
            role=role,
            controller_identifier=controller_identifiers[role],
            key_id=role_signers[role].key_id,
            public_key_base64=role_signers[role].verifier().public_key_base64,
            public_key_sha256=role_signers[role].verifier().public_key_sha256,
            enrolled_at_utc=enrolled_at_utc,
        )
        for role in TRUST_ROLES
    )
    identifier_payload = {
        "protocol": TRUST_REGISTRY_PROTOCOL_ID,
        "role_keys": [row.model_dump(mode="json") for row in rows],
        "enrollment_authority_public_key_sha256": authority_verifier.public_key_sha256,
    }
    unsigned = TrustAnchorRegistryV06(
        protocol=TRUST_REGISTRY_PROTOCOL_ID,
        status="EXTERNALLY_ATTESTED_BEFORE_EVIDENCE",
        registry_identifier=f"sha256:{content_sha256(identifier_payload)}",
        enrollment_authority_key_id=authority_verifier.key_id,
        enrollment_authority_public_key_base64=authority_verifier.public_key_base64,
        enrollment_authority_public_key_sha256=authority_verifier.public_key_sha256,
        role_keys=rows,
        configured_before_evidence_production_attested=True,
        role_control_independence_attested=True,
    )
    signed = unsigned.model_copy(
        update={
            "authority_attestation": enrollment_authority.sign(
                TRUST_REGISTRY_ATTESTATION_DOMAIN, _registry_payload(unsigned)
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_trust_anchor_registry_v0_6(
    payload: Mapping[str, Any],
    *,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> tuple[TrustAnchorRegistryV06, dict[str, Ed25519AttestationVerifier]]:
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("trust-anchor registry content hash mismatch")
    record = TrustAnchorRegistryV06.model_validate(unsigned_payload)
    if (
        record.enrollment_authority_key_id != trusted_enrollment_authority.key_id
        or record.enrollment_authority_public_key_sha256
        != trusted_enrollment_authority.public_key_sha256
        or record.enrollment_authority_public_key_base64
        != trusted_enrollment_authority.public_key_base64
    ):
        raise AttestationError("trust-anchor registry used an attacker-selected authority")
    if (
        record.configured_before_evidence_production_attested is not True
        or record.role_control_independence_attested is not True
    ):
        raise ValueError("trust-anchor registry lacks required governance attestations")
    identifier_payload = {
        "protocol": TRUST_REGISTRY_PROTOCOL_ID,
        "role_keys": [row.model_dump(mode="json") for row in record.role_keys],
        "enrollment_authority_public_key_sha256": (record.enrollment_authority_public_key_sha256),
    }
    if record.registry_identifier != f"sha256:{content_sha256(identifier_payload)}":
        raise ValueError("trust-anchor registry identifier mismatch")
    trusted_enrollment_authority.verify(
        TRUST_REGISTRY_ATTESTATION_DOMAIN,
        _registry_payload(record),
        record.authority_attestation,
    )
    verifiers = {row.role: _role_verifier(row) for row in record.role_keys}
    return record, verifiers


def make_frozen_gate_b_manifest_v0_6(
    *,
    development_draft: Mapping[str, Any],
    gate_a_spec: Mapping[str, Any],
    trust_anchor_registry: Mapping[str, Any],
    source_register_content_sha256: str,
    frozen_at_utc: datetime,
    freeze_ledger_identifier: str,
    freeze_ledger_sequence: int,
    authority_nonce_sha256: str,
    preregistered_producer_run_id: str,
    validation_seed_commitment_sha256: str,
    holdout_commitment_sha256: str,
    producer_source_bundle_sha256: str,
    arm_implementation_bundle_sha256: Mapping[str, str],
    enrollment_authority: Ed25519AttestationSigner,
    reviewer: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
) -> dict[str, Any]:
    validate_structure_two_gate_b_v0_6_draft(development_draft)
    gate_a_spec_unsigned = dict(gate_a_spec)
    gate_a_spec_stored = gate_a_spec_unsigned.pop("content_sha256", None)
    if (
        not isinstance(gate_a_spec_stored, str)
        or content_sha256(gate_a_spec_unsigned) != gate_a_spec_stored
    ):
        raise ValueError("Gate A specification content hash mismatch")
    registry, role_verifiers = verify_trust_anchor_registry_v0_6(
        trust_anchor_registry,
        trusted_enrollment_authority=enrollment_authority.verifier(),
    )
    draft_sha256 = content_sha256(development_draft)
    reviewer_verifier = reviewer.verifier()
    custodian_verifier = custodian.verifier()
    if (
        reviewer_verifier.public_key_sha256 != role_verifiers["reviewer"].public_key_sha256
        or custodian_verifier.public_key_sha256 != role_verifiers["custodian"].public_key_sha256
    ):
        raise AttestationError("freeze signers are outside the enrolled registry")
    if frozen_at_utc.utcoffset() is None or frozen_at_utc <= max(
        row.enrolled_at_utc for row in registry.role_keys
    ):
        raise ValueError("freeze timestamp must follow role-key enrollment")
    identifier_payload = {
        "protocol": FROZEN_MANIFEST_PROTOCOL_ID,
        "status": "EXTERNALLY_FROZEN",
        "development_draft_content_sha256": draft_sha256,
        "source_register_content_sha256": source_register_content_sha256,
        "gate_a_spec_content_sha256": gate_a_spec_stored,
        "trust_anchor_registry_identifier": registry.registry_identifier,
        "enrollment_authority_public_key_sha256": (registry.enrollment_authority_public_key_sha256),
        "frozen_at_utc": frozen_at_utc,
        "freeze_ledger_identifier": freeze_ledger_identifier,
        "freeze_ledger_sequence": freeze_ledger_sequence,
        "authority_nonce_sha256": authority_nonce_sha256,
        "authority_challenge_unpredictability_attested": True,
        "freeze_completed_before_evidence_production_attested": True,
        "preregistered_producer_run_id": preregistered_producer_run_id,
        "validation_seed_commitment_sha256": validation_seed_commitment_sha256,
        "holdout_commitment_sha256": holdout_commitment_sha256,
        "producer_source_bundle_sha256": producer_source_bundle_sha256,
        "arm_implementation_bundle_sha256": dict(arm_implementation_bundle_sha256),
        "expected_arms": EXPECTED_ARMS,
        "reviewer_public_key_sha256": reviewer_verifier.public_key_sha256,
        "custodian_public_key_sha256": custodian_verifier.public_key_sha256,
    }
    unsigned = FrozenGateBManifestV06(
        protocol=FROZEN_MANIFEST_PROTOCOL_ID,
        status="EXTERNALLY_FROZEN",
        immutable_manifest_sha256=content_sha256(identifier_payload),
        development_draft_content_sha256=draft_sha256,
        source_register_content_sha256=source_register_content_sha256,
        gate_a_spec_content_sha256=gate_a_spec_stored,
        trust_anchor_registry_identifier=registry.registry_identifier,
        enrollment_authority_public_key_sha256=(registry.enrollment_authority_public_key_sha256),
        frozen_at_utc=frozen_at_utc,
        freeze_ledger_identifier=freeze_ledger_identifier,
        freeze_ledger_sequence=freeze_ledger_sequence,
        authority_nonce_sha256=authority_nonce_sha256,
        authority_challenge_unpredictability_attested=True,
        freeze_completed_before_evidence_production_attested=True,
        preregistered_producer_run_id=preregistered_producer_run_id,
        validation_seed_commitment_sha256=validation_seed_commitment_sha256,
        holdout_commitment_sha256=holdout_commitment_sha256,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        arm_implementation_bundle_sha256=dict(arm_implementation_bundle_sha256),
        expected_arms=EXPECTED_ARMS,
        reviewer_key_id=reviewer_verifier.key_id,
        reviewer_public_key_base64=reviewer_verifier.public_key_base64,
        reviewer_public_key_sha256=reviewer_verifier.public_key_sha256,
        custodian_key_id=custodian_verifier.key_id,
        custodian_public_key_base64=custodian_verifier.public_key_base64,
        custodian_public_key_sha256=custodian_verifier.public_key_sha256,
    )
    signable = _freeze_payload(unsigned)
    signed = unsigned.model_copy(
        update={
            "reviewer_attestation": reviewer.sign(FREEZE_REVIEWER_ATTESTATION_DOMAIN, signable),
            "custodian_attestation": custodian.sign(FREEZE_CUSTODIAN_ATTESTATION_DOMAIN, signable),
            "authority_attestation": enrollment_authority.sign(
                FREEZE_AUTHORITY_ATTESTATION_DOMAIN, signable
            ),
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_frozen_gate_b_manifest_v0_6(
    payload: Mapping[str, Any],
    *,
    development_draft: Mapping[str, Any],
    source_register: Mapping[str, Any],
    gate_a_spec: Mapping[str, Any],
    trust_anchor_registry: TrustAnchorRegistryV06,
    reviewer: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> FrozenGateBManifestV06:
    validate_structure_two_gate_b_v0_6_draft(development_draft)
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("externally frozen manifest content hash mismatch")
    record = FrozenGateBManifestV06.model_validate(unsigned_payload)
    source_unsigned = dict(source_register)
    source_stored = source_unsigned.pop("content_sha256", None)
    if not isinstance(source_stored, str) or content_sha256(source_unsigned) != source_stored:
        raise ValueError("source register content hash mismatch")
    if record.development_draft_content_sha256 != content_sha256(development_draft):
        raise ValueError("frozen manifest does not bind the canonical development draft")
    if record.source_register_content_sha256 != source_stored:
        raise ValueError("frozen manifest does not bind the source register")
    gate_a_spec_unsigned = dict(gate_a_spec)
    gate_a_spec_stored = gate_a_spec_unsigned.pop("content_sha256", None)
    if (
        not isinstance(gate_a_spec_stored, str)
        or content_sha256(gate_a_spec_unsigned) != gate_a_spec_stored
    ):
        raise ValueError("Gate A specification content hash mismatch")
    if record.gate_a_spec_content_sha256 != gate_a_spec_stored:
        raise ValueError("frozen manifest does not bind the Gate A specification")
    if (
        record.trust_anchor_registry_identifier != trust_anchor_registry.registry_identifier
        or record.enrollment_authority_public_key_sha256
        != trust_anchor_registry.enrollment_authority_public_key_sha256
        or record.enrollment_authority_public_key_sha256 != enrollment_authority.public_key_sha256
    ):
        raise AttestationError("frozen manifest governance registry binding mismatch")
    if record.frozen_at_utc <= max(row.enrolled_at_utc for row in trust_anchor_registry.role_keys):
        raise ValueError("frozen manifest predates or equals role-key enrollment")
    if (
        record.reviewer_key_id != reviewer.key_id
        or record.reviewer_public_key_sha256 != reviewer.public_key_sha256
        or record.reviewer_public_key_base64 != reviewer.public_key_base64
        or record.custodian_key_id != custodian.key_id
        or record.custodian_public_key_sha256 != custodian.public_key_sha256
        or record.custodian_public_key_base64 != custodian.public_key_base64
    ):
        raise AttestationError("frozen manifest is outside the enrolled role keys")
    identifier_payload = {
        "protocol": FROZEN_MANIFEST_PROTOCOL_ID,
        "status": "EXTERNALLY_FROZEN",
        "development_draft_content_sha256": record.development_draft_content_sha256,
        "source_register_content_sha256": record.source_register_content_sha256,
        "gate_a_spec_content_sha256": record.gate_a_spec_content_sha256,
        "trust_anchor_registry_identifier": record.trust_anchor_registry_identifier,
        "enrollment_authority_public_key_sha256": (record.enrollment_authority_public_key_sha256),
        "frozen_at_utc": record.frozen_at_utc,
        "freeze_ledger_identifier": record.freeze_ledger_identifier,
        "freeze_ledger_sequence": record.freeze_ledger_sequence,
        "authority_nonce_sha256": record.authority_nonce_sha256,
        "authority_challenge_unpredictability_attested": (
            record.authority_challenge_unpredictability_attested
        ),
        "freeze_completed_before_evidence_production_attested": (
            record.freeze_completed_before_evidence_production_attested
        ),
        "preregistered_producer_run_id": record.preregistered_producer_run_id,
        "validation_seed_commitment_sha256": (record.validation_seed_commitment_sha256),
        "holdout_commitment_sha256": record.holdout_commitment_sha256,
        "producer_source_bundle_sha256": record.producer_source_bundle_sha256,
        "arm_implementation_bundle_sha256": (record.arm_implementation_bundle_sha256),
        "expected_arms": EXPECTED_ARMS,
        "reviewer_public_key_sha256": record.reviewer_public_key_sha256,
        "custodian_public_key_sha256": record.custodian_public_key_sha256,
    }
    if record.immutable_manifest_sha256 != content_sha256(identifier_payload):
        raise ValueError("immutable frozen-manifest identifier mismatch")
    signable = _freeze_payload(record)
    reviewer.verify(FREEZE_REVIEWER_ATTESTATION_DOMAIN, signable, record.reviewer_attestation)
    custodian.verify(FREEZE_CUSTODIAN_ATTESTATION_DOMAIN, signable, record.custodian_attestation)
    enrollment_authority.verify(
        FREEZE_AUTHORITY_ATTESTATION_DOMAIN, signable, record.authority_attestation
    )
    return record


__all__ = [
    "FROZEN_MANIFEST_PROTOCOL_ID",
    "TRUST_REGISTRY_PROTOCOL_ID",
    "TRUST_ROLES",
    "FrozenGateBManifestV06",
    "TrustAnchorRegistryV06",
    "make_frozen_gate_b_manifest_v0_6",
    "make_trust_anchor_registry_v0_6",
    "verify_frozen_gate_b_manifest_v0_6",
    "verify_trust_anchor_registry_v0_6",
]
