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
FREEZE_EXECUTOR_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_freeze.executor.v0.6"
FREEZE_CUSTODIAN_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.external_freeze.custodian.v0.6"
)
FREEZE_AUTHORITY_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.external_freeze.authority.v0.6"
)
TRUST_ROLES = ("reviewer", "executor", "custodian")
ROLE_ENROLLMENT_ATTESTATION_DOMAIN_PREFIX = "cpswm.evaluation.structure_two.role_enrollment.v0.6"


class EnrolledRoleKeyV06(ContractModel):
    role: str = Field(pattern=r"^(reviewer|executor|custodian)$")
    controller_identifier: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enrollment_authority_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enrolled_at_utc: datetime
    role_attestation: Attestation | None = None


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
        if any(row.enrolled_at_utc.utcoffset() is None for row in self.role_keys):
            raise ValueError("trust-anchor enrollment timestamps must be timezone-aware")
        if len({row.key_id for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role key IDs must be pairwise distinct")
        if len({row.public_key_sha256 for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role public keys must be pairwise distinct")
        if len({row.controller_identifier for row in self.role_keys}) != len(TRUST_ROLES):
            raise ValueError("trust-anchor role controllers must be pairwise distinct")
        if self.enrollment_authority_public_key_sha256 in {
            row.public_key_sha256 for row in self.role_keys
        }:
            raise ValueError(
                "enrollment authority and the three role controllers must use independent keys"
            )
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
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
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
            "executor_attestation",
            "custodian_attestation",
            "authority_attestation",
        },
    )


def _freeze_authority_witness_payload(record: FrozenGateBManifestV06) -> dict[str, Any]:
    """Bind the authority witness to the already-verified three-role freeze.

    The authority does not sign the same base payload as the three roles.  Its
    payload contains every role attestation plus a digest of that exact set, so
    an authority signature made before the three-role ceremony cannot be
    attached afterwards.
    """

    role_attestations = {
        "reviewer": (
            None
            if record.reviewer_attestation is None
            else record.reviewer_attestation.model_dump(mode="json")
        ),
        "executor": (
            None
            if record.executor_attestation is None
            else record.executor_attestation.model_dump(mode="json")
        ),
        "custodian": (
            None
            if record.custodian_attestation is None
            else record.custodian_attestation.model_dump(mode="json")
        ),
    }
    return {
        "freeze_manifest": _freeze_payload(record),
        "role_attestations": role_attestations,
        "role_attestations_sha256": content_sha256(role_attestations),
    }


def _role_enrollment_payload(row: EnrolledRoleKeyV06) -> dict[str, Any]:
    return row.model_dump(mode="json", exclude={"role_attestation"})


def _role_enrollment_domain(role: str) -> str:
    return f"{ROLE_ENROLLMENT_ATTESTATION_DOMAIN_PREFIX}.{role}"


def _role_verifier(
    row: EnrolledRoleKeyV06,
    *,
    enrollment_authority_public_key_sha256: str,
) -> Ed25519AttestationVerifier:
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=row.key_id, public_key_base64=row.public_key_base64
    )
    if verifier.public_key_sha256 != row.public_key_sha256:
        raise AttestationError("enrolled role public-key hash mismatch")
    if row.enrollment_authority_public_key_sha256 != enrollment_authority_public_key_sha256:
        raise AttestationError("role enrollment is bound to the wrong authority")
    verifier.verify(
        _role_enrollment_domain(row.role),
        _role_enrollment_payload(row),
        row.role_attestation,
    )
    return verifier


def prepare_enrolled_role_key_v0_6(
    *,
    role: str,
    controller_identifier: str,
    role_verifier: Ed25519AttestationVerifier,
    enrolled_at_utc: datetime,
    enrollment_authority: Ed25519AttestationVerifier,
) -> EnrolledRoleKeyV06:
    """Build one unsigned role-enrollment statement for detached signing."""

    return EnrolledRoleKeyV06(
        role=role,
        controller_identifier=controller_identifier,
        key_id=role_verifier.key_id,
        public_key_base64=role_verifier.public_key_base64,
        public_key_sha256=role_verifier.public_key_sha256,
        enrollment_authority_public_key_sha256=(enrollment_authority.public_key_sha256),
        enrolled_at_utc=enrolled_at_utc,
    )


def role_enrollment_signing_request_v0_6(
    row: EnrolledRoleKeyV06,
) -> tuple[str, dict[str, Any]]:
    """Return the exact domain and payload a role controller must sign."""

    if row.role_attestation is not None:
        raise ValueError("role-enrollment signing request must be unsigned")
    return _role_enrollment_domain(row.role), _role_enrollment_payload(row)


def attach_role_enrollment_attestation_v0_6(
    row: EnrolledRoleKeyV06,
    attestation: Attestation,
) -> EnrolledRoleKeyV06:
    """Attach and verify a detached role-controller countersignature."""

    if row.role_attestation is not None:
        raise ValueError("role enrollment was already signed")
    signed = row.model_copy(update={"role_attestation": attestation})
    _role_verifier(
        signed,
        enrollment_authority_public_key_sha256=(row.enrollment_authority_public_key_sha256),
    )
    return signed


def prepare_trust_anchor_registry_v0_6(
    *,
    role_keys: tuple[EnrolledRoleKeyV06, ...],
    enrollment_authority: Ed25519AttestationVerifier,
) -> TrustAnchorRegistryV06:
    """Assemble a role-countersigned registry for detached authority signing."""

    if tuple(row.role for row in role_keys) != TRUST_ROLES:
        raise ValueError("trust-anchor enrollment requires the ordered exact role set")
    for row in role_keys:
        _role_verifier(
            row,
            enrollment_authority_public_key_sha256=(enrollment_authority.public_key_sha256),
        )
    identifier_payload = {
        "protocol": TRUST_REGISTRY_PROTOCOL_ID,
        "role_keys": [row.model_dump(mode="json") for row in role_keys],
        "enrollment_authority_public_key_sha256": (enrollment_authority.public_key_sha256),
    }
    return TrustAnchorRegistryV06(
        protocol=TRUST_REGISTRY_PROTOCOL_ID,
        status="EXTERNALLY_ATTESTED_BEFORE_EVIDENCE",
        registry_identifier=f"sha256:{content_sha256(identifier_payload)}",
        enrollment_authority_key_id=enrollment_authority.key_id,
        enrollment_authority_public_key_base64=(enrollment_authority.public_key_base64),
        enrollment_authority_public_key_sha256=(enrollment_authority.public_key_sha256),
        role_keys=role_keys,
        configured_before_evidence_production_attested=True,
        role_control_independence_attested=True,
    )


def trust_anchor_registry_signing_request_v0_6(
    registry: TrustAnchorRegistryV06,
) -> tuple[str, dict[str, Any]]:
    """Return the authority's exact detached registry-signing request."""

    if registry.authority_attestation is not None:
        raise ValueError("trust-anchor registry signing request must be unsigned")
    return TRUST_REGISTRY_ATTESTATION_DOMAIN, _registry_payload(registry)


def finalize_trust_anchor_registry_v0_6(
    *,
    registry: TrustAnchorRegistryV06,
    authority_attestation: Attestation,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    """Attach an externally produced authority signature and verify the registry."""

    if registry.authority_attestation is not None:
        raise ValueError("trust-anchor registry was already signed")
    signed = registry.model_copy(update={"authority_attestation": authority_attestation})
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_trust_anchor_registry_v0_6(
        payload,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return payload


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
    rows: list[EnrolledRoleKeyV06] = []
    for role in TRUST_ROLES:
        signer = role_signers[role]
        unsigned_row = EnrolledRoleKeyV06(
            role=role,
            controller_identifier=controller_identifiers[role],
            key_id=signer.key_id,
            public_key_base64=signer.verifier().public_key_base64,
            public_key_sha256=signer.verifier().public_key_sha256,
            enrollment_authority_public_key_sha256=authority_verifier.public_key_sha256,
            enrolled_at_utc=enrolled_at_utc,
        )
        rows.append(
            unsigned_row.model_copy(
                update={
                    "role_attestation": signer.sign(
                        _role_enrollment_domain(role),
                        _role_enrollment_payload(unsigned_row),
                    )
                }
            )
        )
    enrolled_rows = tuple(rows)
    identifier_payload = {
        "protocol": TRUST_REGISTRY_PROTOCOL_ID,
        "role_keys": [row.model_dump(mode="json") for row in enrolled_rows],
        "enrollment_authority_public_key_sha256": authority_verifier.public_key_sha256,
    }
    unsigned = TrustAnchorRegistryV06(
        protocol=TRUST_REGISTRY_PROTOCOL_ID,
        status="EXTERNALLY_ATTESTED_BEFORE_EVIDENCE",
        registry_identifier=f"sha256:{content_sha256(identifier_payload)}",
        enrollment_authority_key_id=authority_verifier.key_id,
        enrollment_authority_public_key_base64=authority_verifier.public_key_base64,
        enrollment_authority_public_key_sha256=authority_verifier.public_key_sha256,
        role_keys=enrolled_rows,
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
    verifiers = {
        row.role: _role_verifier(
            row,
            enrollment_authority_public_key_sha256=(record.enrollment_authority_public_key_sha256),
        )
        for row in record.role_keys
    }
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
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
) -> dict[str, Any]:
    unsigned = prepare_frozen_gate_b_manifest_v0_6(
        development_draft=development_draft,
        gate_a_spec=gate_a_spec,
        trust_anchor_registry=trust_anchor_registry,
        source_register_content_sha256=source_register_content_sha256,
        frozen_at_utc=frozen_at_utc,
        freeze_ledger_identifier=freeze_ledger_identifier,
        freeze_ledger_sequence=freeze_ledger_sequence,
        authority_nonce_sha256=authority_nonce_sha256,
        preregistered_producer_run_id=preregistered_producer_run_id,
        validation_seed_commitment_sha256=validation_seed_commitment_sha256,
        holdout_commitment_sha256=holdout_commitment_sha256,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        arm_implementation_bundle_sha256=arm_implementation_bundle_sha256,
        trusted_enrollment_authority=enrollment_authority.verifier(),
    )
    _, role_verifiers = verify_trust_anchor_registry_v0_6(
        trust_anchor_registry,
        trusted_enrollment_authority=enrollment_authority.verifier(),
    )
    supplied_verifiers = {
        "reviewer": reviewer.verifier(),
        "executor": executor.verifier(),
        "custodian": custodian.verifier(),
    }
    if any(
        supplied_verifiers[role].public_key_sha256 != role_verifiers[role].public_key_sha256
        for role in TRUST_ROLES
    ):
        raise AttestationError("freeze signers are outside the enrolled registry")
    role_requests = frozen_gate_b_manifest_signing_requests_v0_6(unsigned)
    role_signed = attach_frozen_gate_b_role_attestations_v0_6(
        record=unsigned,
        reviewer_attestation=reviewer.sign(*role_requests["reviewer"]),
        executor_attestation=executor.sign(*role_requests["executor"]),
        custodian_attestation=custodian.sign(*role_requests["custodian"]),
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
    )
    authority_request = frozen_gate_b_manifest_authority_signing_request_v0_6(
        role_signed,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=enrollment_authority.verifier(),
    )
    return finalize_frozen_gate_b_manifest_v0_6(
        record=role_signed,
        authority_attestation=enrollment_authority.sign(*authority_request),
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=enrollment_authority.verifier(),
    )


def prepare_frozen_gate_b_manifest_v0_6(
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
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> FrozenGateBManifestV06:
    """Prepare the immutable freeze statement without receiving private keys.

    The returned record is intentionally unsigned.  Each enrolled role can
    obtain the identical signable request and sign it in a separately
    controlled environment before the authority witnesses the completed
    three-role freeze.
    """

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
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    draft_sha256 = content_sha256(development_draft)
    reviewer_verifier = role_verifiers["reviewer"]
    executor_verifier = role_verifiers["executor"]
    custodian_verifier = role_verifiers["custodian"]
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
        "executor_public_key_sha256": executor_verifier.public_key_sha256,
        "custodian_public_key_sha256": custodian_verifier.public_key_sha256,
    }
    return FrozenGateBManifestV06(
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
        executor_key_id=executor_verifier.key_id,
        executor_public_key_base64=executor_verifier.public_key_base64,
        executor_public_key_sha256=executor_verifier.public_key_sha256,
        custodian_key_id=custodian_verifier.key_id,
        custodian_public_key_base64=custodian_verifier.public_key_base64,
        custodian_public_key_sha256=custodian_verifier.public_key_sha256,
    )


def frozen_gate_b_manifest_signing_requests_v0_6(
    record: FrozenGateBManifestV06,
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return the detached base-payload requests for the three roles only."""

    if any(
        attestation is not None
        for attestation in (
            record.reviewer_attestation,
            record.executor_attestation,
            record.custodian_attestation,
            record.authority_attestation,
        )
    ):
        raise ValueError("freeze signing requests require a wholly unsigned record")
    signable = _freeze_payload(record)
    return {
        "reviewer": (FREEZE_REVIEWER_ATTESTATION_DOMAIN, signable),
        "executor": (FREEZE_EXECUTOR_ATTESTATION_DOMAIN, signable),
        "custodian": (FREEZE_CUSTODIAN_ATTESTATION_DOMAIN, signable),
    }


def _verify_freeze_role_bindings_v0_6(
    *,
    record: FrozenGateBManifestV06,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> None:
    if (
        record.reviewer_key_id != reviewer.key_id
        or record.reviewer_public_key_base64 != reviewer.public_key_base64
        or record.reviewer_public_key_sha256 != reviewer.public_key_sha256
        or record.executor_key_id != executor.key_id
        or record.executor_public_key_base64 != executor.public_key_base64
        or record.executor_public_key_sha256 != executor.public_key_sha256
        or record.custodian_key_id != custodian.key_id
        or record.custodian_public_key_base64 != custodian.public_key_base64
        or record.custodian_public_key_sha256 != custodian.public_key_sha256
    ):
        raise AttestationError("detached freeze signer is outside the immutable manifest")


def _verify_attached_freeze_role_attestations_v0_6(
    *,
    record: FrozenGateBManifestV06,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> None:
    _verify_freeze_role_bindings_v0_6(
        record=record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
    )
    signable = _freeze_payload(record)
    reviewer.verify(FREEZE_REVIEWER_ATTESTATION_DOMAIN, signable, record.reviewer_attestation)
    executor.verify(FREEZE_EXECUTOR_ATTESTATION_DOMAIN, signable, record.executor_attestation)
    custodian.verify(FREEZE_CUSTODIAN_ATTESTATION_DOMAIN, signable, record.custodian_attestation)


def attach_frozen_gate_b_role_attestations_v0_6(
    *,
    record: FrozenGateBManifestV06,
    reviewer_attestation: Attestation,
    executor_attestation: Attestation,
    custodian_attestation: Attestation,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
) -> FrozenGateBManifestV06:
    """Verify and attach the three role signatures before authority witnessing."""

    if any(
        attestation is not None
        for attestation in (
            record.reviewer_attestation,
            record.executor_attestation,
            record.custodian_attestation,
            record.authority_attestation,
        )
    ):
        raise ValueError("role signing requires a wholly unsigned frozen manifest")
    role_signed = record.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    _verify_attached_freeze_role_attestations_v0_6(
        record=role_signed,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
    )
    return role_signed


def frozen_gate_b_manifest_authority_signing_request_v0_6(
    record: FrozenGateBManifestV06,
    *,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> tuple[str, dict[str, Any]]:
    """Return an authority witness request only after all three role checks pass."""

    if record.authority_attestation is not None:
        raise ValueError("authority already witnessed this frozen manifest")
    if record.enrollment_authority_public_key_sha256 != enrollment_authority.public_key_sha256:
        raise AttestationError("detached freeze authority is outside the immutable manifest")
    _verify_attached_freeze_role_attestations_v0_6(
        record=record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
    )
    return FREEZE_AUTHORITY_ATTESTATION_DOMAIN, _freeze_authority_witness_payload(record)


def finalize_frozen_gate_b_manifest_v0_6(
    *,
    record: FrozenGateBManifestV06,
    authority_attestation: Attestation,
    reviewer: Ed25519AttestationVerifier,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    """Attach the authority witness after verifying the completed three-role freeze."""

    authority_request = frozen_gate_b_manifest_authority_signing_request_v0_6(
        record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
        enrollment_authority=enrollment_authority,
    )
    enrollment_authority.verify(authority_request[0], authority_request[1], authority_attestation)
    signed = record.model_copy(
        update={
            "authority_attestation": authority_attestation,
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
    executor: Ed25519AttestationVerifier,
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
        or record.executor_key_id != executor.key_id
        or record.executor_public_key_sha256 != executor.public_key_sha256
        or record.executor_public_key_base64 != executor.public_key_base64
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
        "executor_public_key_sha256": record.executor_public_key_sha256,
        "custodian_public_key_sha256": record.custodian_public_key_sha256,
    }
    if record.immutable_manifest_sha256 != content_sha256(identifier_payload):
        raise ValueError("immutable frozen-manifest identifier mismatch")
    _verify_attached_freeze_role_attestations_v0_6(
        record=record,
        reviewer=reviewer,
        executor=executor,
        custodian=custodian,
    )
    enrollment_authority.verify(
        FREEZE_AUTHORITY_ATTESTATION_DOMAIN,
        _freeze_authority_witness_payload(record),
        record.authority_attestation,
    )
    return record


__all__ = [
    "FREEZE_EXECUTOR_ATTESTATION_DOMAIN",
    "FROZEN_MANIFEST_PROTOCOL_ID",
    "ROLE_ENROLLMENT_ATTESTATION_DOMAIN_PREFIX",
    "TRUST_REGISTRY_PROTOCOL_ID",
    "TRUST_ROLES",
    "FrozenGateBManifestV06",
    "TrustAnchorRegistryV06",
    "attach_frozen_gate_b_role_attestations_v0_6",
    "attach_role_enrollment_attestation_v0_6",
    "finalize_frozen_gate_b_manifest_v0_6",
    "finalize_trust_anchor_registry_v0_6",
    "frozen_gate_b_manifest_authority_signing_request_v0_6",
    "frozen_gate_b_manifest_signing_requests_v0_6",
    "make_frozen_gate_b_manifest_v0_6",
    "make_trust_anchor_registry_v0_6",
    "prepare_enrolled_role_key_v0_6",
    "prepare_frozen_gate_b_manifest_v0_6",
    "prepare_trust_anchor_registry_v0_6",
    "role_enrollment_signing_request_v0_6",
    "trust_anchor_registry_signing_request_v0_6",
    "verify_frozen_gate_b_manifest_v0_6",
    "verify_trust_anchor_registry_v0_6",
]
