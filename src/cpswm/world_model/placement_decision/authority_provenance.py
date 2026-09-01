"""Trusted authority provenance for action-time placement preferences.

An LLM may extract that a person said something, but it may not grant that
person household-owner authority.  This module binds a stated preference to a
separate, scoped authority attestation and downgrades unsupported claims before
the v0.2 resolver sees them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)
from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.placement_memory import (
    PlacementMemoryClass,
    PlacementNormAssertion,
    StatedPreferenceAssertion,
)
from cpswm.system.attestation import (
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

from .authority_scoped_resolver import (
    AuthorityScopedPlacementDecisionResolver,
    AuthorityScopedPlacementResolution,
)
from .resolver import PlacementIntent
from .update_policy import AUTHORITY_RANK

AUTHORITY_PROVENANCE_VERSION = "placement-authority-provenance@0.1"
DOMAIN_HOUSEHOLD_TRUST_STORE = "cpswm.placement.household_trust_store.v1"


class HouseholdTrustStoreSnapshot(ContractModel):
    snapshot_id: UUID
    household_id: UUID
    version: int = Field(gt=0)
    previous_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    trusted_issuer_ids: tuple[UUID, ...] = Field(min_length=1)
    issued_at: datetime
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _trust_store_semantics(self) -> HouseholdTrustStoreSnapshot:
        if len(self.trusted_issuer_ids) != len(set(self.trusted_issuer_ids)):
            raise ValueError("trusted issuer ids must be unique")
        if self.version == 1 and self.previous_snapshot_sha256 is not None:
            raise ValueError("trust-store genesis cannot declare a previous snapshot")
        if self.version > 1 and self.previous_snapshot_sha256 is None:
            raise ValueError("trust-store updates must bind the previous snapshot")
        return self


class VerifiedHouseholdTrustStore(ContractModel):
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    household_id: UUID
    version: int = Field(gt=0)
    trusted_issuer_ids: frozenset[UUID] = Field(min_length=1)
    verifier_key_id: str = Field(min_length=1)


def issue_household_trust_store_snapshot(
    snapshot: HouseholdTrustStoreSnapshot,
    *,
    signer: Ed25519AttestationSigner,
) -> HouseholdTrustStoreSnapshot:
    unsigned = snapshot.model_copy(update={"attestation": None})
    return unsigned.model_copy(
        update={
            "attestation": signer.sign(
                DOMAIN_HOUSEHOLD_TRUST_STORE,
                attested_payload(unsigned),
            )
        }
    )


def verify_household_trust_store_snapshot(
    snapshot: HouseholdTrustStoreSnapshot,
    *,
    verifier: Ed25519AttestationVerifier,
) -> VerifiedHouseholdTrustStore:
    verifier.verify(
        DOMAIN_HOUSEHOLD_TRUST_STORE,
        attested_payload(snapshot),
        snapshot.attestation,
    )
    return VerifiedHouseholdTrustStore(
        snapshot_sha256=content_sha256(snapshot),
        household_id=snapshot.household_id,
        version=snapshot.version,
        trusted_issuer_ids=frozenset(snapshot.trusted_issuer_ids),
        verifier_key_id=verifier.key_id,
    )


class PlacementAuthorityAttestation(ContractModel):
    """A trusted grant of authority, separate from the preference content."""

    metadata: BaseRecordMetadata
    subject_person_id: UUID
    issuer: EntityRef
    granted_authority: AuthorityLevel
    valid_time: ValidTimeInterval
    authority_evidence_ref: EvidenceRef
    allowed_object_instance_ids: tuple[UUID, ...] = ()
    allowed_object_classes: tuple[str, ...] = ()
    revoked: bool = False

    @model_validator(mode="after")
    def _trusted_attestation_boundary(self) -> Self:
        if self.metadata.source_type not in {SourceType.USER, SourceType.IMPORT}:
            raise ValueError("authority attestations require user or imported trust provenance")
        if self.issuer.entity_type not in {EntityType.PERSON, EntityType.DEVICE}:
            raise ValueError("authority attestation issuer must be a person or trusted device")
        if len(self.allowed_object_instance_ids) != len(set(self.allowed_object_instance_ids)):
            raise ValueError("allowed object instance IDs must be unique")
        if len(self.allowed_object_classes) != len(set(self.allowed_object_classes)):
            raise ValueError("allowed object classes must be unique")
        return self

    def permits(
        self,
        *,
        household_id: UUID,
        person_id: UUID,
        object_instance_id: UUID,
        object_class: str | None,
        decision_time: datetime,
    ) -> bool:
        if self.revoked or self.metadata.household_id != household_id:
            return False
        if self.subject_person_id != person_id:
            return False
        if not self.valid_time.contains(decision_time):
            return False
        unrestricted = not self.allowed_object_instance_ids and not self.allowed_object_classes
        return (
            unrestricted
            or object_instance_id in self.allowed_object_instance_ids
            or (object_class is not None and object_class in self.allowed_object_classes)
        )


class AuthorityVerificationStatus(StrEnum):
    VERIFIED = "verified"
    DOWNGRADED_TO_ATTESTED_LEVEL = "downgraded_to_attested_level"
    DOWNGRADED_NO_VALID_ATTESTATION = "downgraded_no_valid_attestation"
    DOWNGRADED_UNTRUSTED_ISSUER = "downgraded_untrusted_issuer"
    REJECTED_CROSS_HOUSEHOLD = "rejected_cross_household"


class PlacementRetirementAuthorization(ContractModel):
    """Trusted ledger receipt authorizing one superseded placement record."""

    metadata: BaseRecordMetadata
    issuer: EntityRef
    retired_record_id: UUID
    replacement_record_id: UUID | None = None
    authority_level: AuthorityLevel
    safety_removal_acknowledged: bool = False
    update_policy_version: str = Field(min_length=1)
    authorization_evidence_ref: EvidenceRef

    @model_validator(mode="after")
    def _trusted_retirement_boundary(self) -> Self:
        if self.metadata.source_type not in {SourceType.ACTION, SourceType.IMPORT}:
            raise ValueError("retirement authorization requires action or import provenance")
        if self.issuer.entity_type not in {EntityType.PERSON, EntityType.DEVICE}:
            raise ValueError("retirement issuer must be a person or trusted device")
        if self.replacement_record_id == self.retired_record_id:
            raise ValueError("a retirement cannot replace a record with itself")
        return self


class PlacementAuthorityVerificationReceipt(ContractModel):
    preference_record_id: UUID
    person_id: UUID
    claimed_authority: AuthorityLevel
    effective_authority: AuthorityLevel
    status: AuthorityVerificationStatus
    matched_attestation_record_id: UUID | None = None
    reason: str = Field(min_length=1)
    policy_version: str = AUTHORITY_PROVENANCE_VERSION


class VerifiedPlacementPreferences(ContractModel):
    preferences: tuple[StatedPreferenceAssertion, ...]
    receipts: tuple[PlacementAuthorityVerificationReceipt, ...]
    policy_version: str = AUTHORITY_PROVENANCE_VERSION


class PlacementAuthorityVerifier:
    """Replace self-asserted authority with the strongest valid scoped grant."""

    def __init__(self, *, trust_store: VerifiedHouseholdTrustStore) -> None:
        self._trust_store = trust_store

    def verify(
        self,
        *,
        preferences: tuple[StatedPreferenceAssertion, ...],
        attestations: tuple[PlacementAuthorityAttestation, ...],
        decision_household_id: UUID,
        object_instance_id: UUID,
        object_class: str | None,
        decision_time: datetime,
    ) -> VerifiedPlacementPreferences:
        trust_store = self._trust_store
        if trust_store.household_id != decision_household_id:
            raise ValueError("trust-store household does not match the decision household")
        trusted_issuer_ids = trust_store.trusted_issuer_ids
        effective: list[StatedPreferenceAssertion] = []
        receipts: list[PlacementAuthorityVerificationReceipt] = []
        for preference in preferences:
            person_id = preference.stated_by.entity_id
            if preference.metadata.household_id != decision_household_id:
                receipts.append(
                    PlacementAuthorityVerificationReceipt(
                        preference_record_id=preference.metadata.record_id,
                        person_id=person_id,
                        claimed_authority=preference.authority_level,
                        effective_authority=AuthorityLevel.UNVERIFIED_REPORTER,
                        status=AuthorityVerificationStatus.REJECTED_CROSS_HOUSEHOLD,
                        reason="preference household does not match the decision household",
                    )
                )
                continue
            valid = tuple(
                attestation
                for attestation in attestations
                if attestation.issuer.entity_id in trusted_issuer_ids
                if attestation.permits(
                    household_id=decision_household_id,
                    person_id=person_id,
                    object_instance_id=object_instance_id,
                    object_class=object_class,
                    decision_time=decision_time,
                )
            )
            if not valid:
                effective_authority = AuthorityLevel.UNVERIFIED_REPORTER
                matched = None
                has_untrusted_match = any(
                    attestation.issuer.entity_id not in trusted_issuer_ids
                    and attestation.permits(
                        household_id=decision_household_id,
                        person_id=person_id,
                        object_instance_id=object_instance_id,
                        object_class=object_class,
                        decision_time=decision_time,
                    )
                    for attestation in attestations
                )
                if has_untrusted_match:
                    status = AuthorityVerificationStatus.DOWNGRADED_UNTRUSTED_ISSUER
                    reason = "matching authority claim was issued by an untrusted issuer"
                else:
                    status = AuthorityVerificationStatus.DOWNGRADED_NO_VALID_ATTESTATION
                    reason = "no active scoped authority attestation; fail-closed downgrade"
            else:
                strongest = max(
                    valid,
                    key=lambda item: (
                        AUTHORITY_RANK[item.granted_authority],
                        item.metadata.recorded_time,
                        str(item.metadata.record_id),
                    ),
                )
                matched = strongest.metadata.record_id
                if (
                    AUTHORITY_RANK[preference.authority_level]
                    <= AUTHORITY_RANK[strongest.granted_authority]
                ):
                    effective_authority = preference.authority_level
                    status = AuthorityVerificationStatus.VERIFIED
                    reason = "claimed authority is covered by an active scoped attestation"
                else:
                    effective_authority = strongest.granted_authority
                    status = AuthorityVerificationStatus.DOWNGRADED_TO_ATTESTED_LEVEL
                    reason = "claimed authority exceeded the active scoped attestation"
            effective.append(preference.model_copy(update={"authority_level": effective_authority}))
            receipts.append(
                PlacementAuthorityVerificationReceipt(
                    preference_record_id=preference.metadata.record_id,
                    person_id=person_id,
                    claimed_authority=preference.authority_level,
                    effective_authority=effective_authority,
                    status=status,
                    matched_attestation_record_id=matched,
                    reason=reason,
                )
            )
        return VerifiedPlacementPreferences(
            preferences=tuple(effective),
            receipts=tuple(receipts),
        )


class ProvenanceBoundPlacementResolution(ContractModel):
    placement: AuthorityScopedPlacementResolution
    authority_verification_receipts: tuple[PlacementAuthorityVerificationReceipt, ...]
    authorized_retired_record_ids: tuple[UUID, ...] = ()
    refused_retirement_record_ids: tuple[UUID, ...] = ()
    policy_version: str = AUTHORITY_PROVENANCE_VERSION


class ProvenanceBoundPlacementDecisionResolver:
    """Verify authority provenance, then invoke the v0.2 placement resolver."""

    def __init__(self, *, trust_store: VerifiedHouseholdTrustStore) -> None:
        self._trust_store = trust_store
        self._verifier = PlacementAuthorityVerifier(trust_store=trust_store)
        self._resolver = AuthorityScopedPlacementDecisionResolver()

    def resolve(
        self,
        *,
        intent: PlacementIntent,
        decision_household_id: UUID,
        object_instance_id: UUID,
        decision_time: datetime,
        object_class: str | None = None,
        observed_location_distribution: dict[UUID, float] | None = None,
        preferences: tuple[StatedPreferenceAssertion, ...] = (),
        attestations: tuple[PlacementAuthorityAttestation, ...] = (),
        norms: tuple[PlacementNormAssertion, ...] = (),
        retirement_authorizations: tuple[PlacementRetirementAuthorization, ...] = (),
        proposed_location_id: UUID | None = None,
    ) -> ProvenanceBoundPlacementResolution:
        trust_store = self._trust_store
        if trust_store.household_id != decision_household_id:
            raise ValueError("trust-store household does not match the decision household")
        sanitized_preferences, sanitized_norms, authorized, refused = _sanitize_retirements(
            preferences=preferences,
            norms=norms,
            authorizations=retirement_authorizations,
            decision_household_id=decision_household_id,
            trusted_issuer_ids=trust_store.trusted_issuer_ids,
        )
        verified = self._verifier.verify(
            preferences=sanitized_preferences,
            attestations=attestations,
            decision_household_id=decision_household_id,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
        )
        placement = self._resolver.resolve(
            intent=intent,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
            observed_location_distribution=observed_location_distribution,
            preferences=verified.preferences,
            norms=sanitized_norms,
            proposed_location_id=proposed_location_id,
        )
        return ProvenanceBoundPlacementResolution(
            placement=placement,
            authority_verification_receipts=verified.receipts,
            authorized_retired_record_ids=authorized,
            refused_retirement_record_ids=refused,
        )


def _sanitize_retirements(
    *,
    preferences: tuple[StatedPreferenceAssertion, ...],
    norms: tuple[PlacementNormAssertion, ...],
    authorizations: tuple[PlacementRetirementAuthorization, ...],
    decision_household_id: UUID,
    trusted_issuer_ids: frozenset[UUID],
) -> tuple[
    tuple[StatedPreferenceAssertion, ...],
    tuple[PlacementNormAssertion, ...],
    tuple[UUID, ...],
    tuple[UUID, ...],
]:
    authorized: list[UUID] = []
    refused: list[UUID] = []

    def matching(record_id: UUID) -> tuple[PlacementRetirementAuthorization, ...]:
        return tuple(
            item
            for item in authorizations
            if item.retired_record_id == record_id
            and item.metadata.household_id == decision_household_id
            and item.issuer.entity_id in trusted_issuer_ids
        )

    sanitized_preferences: list[StatedPreferenceAssertion] = []
    for preference in preferences:
        if not preference.superseded:
            sanitized_preferences.append(preference)
            continue
        allowed = any(
            AUTHORITY_RANK[item.authority_level] >= AUTHORITY_RANK[preference.authority_level]
            for item in matching(preference.metadata.record_id)
        )
        if allowed:
            authorized.append(preference.metadata.record_id)
            sanitized_preferences.append(preference)
        else:
            refused.append(preference.metadata.record_id)
            sanitized_preferences.append(preference.model_copy(update={"superseded": False}))

    sanitized_norms: list[PlacementNormAssertion] = []
    for norm in norms:
        if not norm.superseded:
            sanitized_norms.append(norm)
            continue
        candidates = matching(norm.metadata.record_id)
        allowed = any(
            AUTHORITY_RANK[item.authority_level]
            >= AUTHORITY_RANK[AuthorityLevel.AUTHORIZED_CORRECTOR]
            and (
                not norm.is_hard_constraint
                or (
                    item.safety_removal_acknowledged
                    and (
                        norm.norm_class is not PlacementMemoryClass.HOUSEHOLD_NORM
                        or AUTHORITY_RANK[item.authority_level]
                        >= AUTHORITY_RANK[AuthorityLevel.HOUSEHOLD_OWNER]
                    )
                )
            )
            for item in candidates
        )
        if allowed:
            authorized.append(norm.metadata.record_id)
            sanitized_norms.append(norm)
        else:
            refused.append(norm.metadata.record_id)
            sanitized_norms.append(norm.model_copy(update={"superseded": False}))
    return (
        tuple(sanitized_preferences),
        tuple(sanitized_norms),
        tuple(sorted(authorized, key=str)),
        tuple(sorted(refused, key=str)),
    )


__all__ = [
    "AUTHORITY_PROVENANCE_VERSION",
    "AuthorityVerificationStatus",
    "PlacementAuthorityAttestation",
    "PlacementAuthorityVerificationReceipt",
    "PlacementAuthorityVerifier",
    "PlacementRetirementAuthorization",
    "ProvenanceBoundPlacementDecisionResolver",
    "ProvenanceBoundPlacementResolution",
    "VerifiedPlacementPreferences",
]
