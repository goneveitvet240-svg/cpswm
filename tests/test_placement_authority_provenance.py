"""Authority must come from a scoped trust record, never from LLM content."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import pytest

from cpswm.contracts.base import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)
from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.placement_memory import PlacementSubject, StatedPreferenceAssertion
from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.world_model.placement_decision import (
    PLACEMENT_UPDATE_POLICY_VERSION,
    AuthorityVerificationStatus,
    HouseholdTrustStoreSnapshot,
    PlacementAuthorityAttestation,
    PlacementAuthorityVerifier,
    PlacementIntent,
    PlacementRetirementAuthorization,
    ProvenanceBoundPlacementDecisionResolver,
    issue_household_trust_store_snapshot,
    verify_household_trust_store_snapshot,
)

NAMESPACE = UUID("a9e43a7d-e9ba-4b35-87fa-857fddc51a0b")
NOW = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
HOUSEHOLD = uuid5(NAMESPACE, "household")
OBJECT = uuid5(NAMESPACE, "object")
OWNER = uuid5(NAMESPACE, "owner")
VISITOR = uuid5(NAMESPACE, "visitor")
CLOSET = uuid5(NAMESPACE, "closet")
SOFA = uuid5(NAMESPACE, "sofa")
TRUSTED_ISSUER = uuid5(NAMESPACE, "trusted-household-enrollment-service")
TRUST_SIGNER = Ed25519AttestationSigner.generate(key_id="household-trust-test")
TRUST_SNAPSHOT = issue_household_trust_store_snapshot(
    HouseholdTrustStoreSnapshot(
        snapshot_id=uuid5(NAMESPACE, "trust-snapshot"),
        household_id=HOUSEHOLD,
        version=1,
        trusted_issuer_ids=(TRUSTED_ISSUER,),
        issued_at=NOW,
    ),
    signer=TRUST_SIGNER,
)
TRUST_STORE = verify_household_trust_store_snapshot(
    TRUST_SNAPSHOT,
    verifier=TRUST_SIGNER.verifier(),
)


def _metadata(name: str, source: SourceType, *, at: datetime = NOW):
    return BaseRecordMetadata(
        record_id=uuid5(NAMESPACE, f"record:{name}"),
        schema_name="cpswm.PlacementAuthorityProvenanceFixture",
        schema_version="0.1.0",
        household_id=HOUSEHOLD,
        session_id=uuid5(NAMESPACE, "session"),
        recorded_time=at,
        source_type=source,
        source_id="authority-provenance-test",
        trace_id=uuid5(NAMESPACE, "trace"),
    )


def _preference(
    name: str,
    person: UUID,
    location: UUID,
    claimed: AuthorityLevel,
    *,
    minute: int,
) -> StatedPreferenceAssertion:
    return StatedPreferenceAssertion(
        metadata=_metadata(name, SourceType.USER, at=NOW + timedelta(minutes=minute)),
        subject=PlacementSubject(kind="instance", object_instance_id=OBJECT),
        preferred_location_id=location,
        stated_by=EntityRef(entity_type=EntityType.PERSON, entity_id=person),
        authority_level=claimed,
        valid_time=ValidTimeInterval(start=NOW),
        user_statement_ref=EvidenceRef(
            evidence_type="user_statement",
            source_record_id=uuid5(NAMESPACE, f"statement:{name}"),
        ),
    )


def _attestation(
    name: str,
    person: UUID,
    granted: AuthorityLevel,
    *,
    revoked: bool = False,
    allowed_object: UUID | None = OBJECT,
) -> PlacementAuthorityAttestation:
    return PlacementAuthorityAttestation(
        metadata=_metadata(name, SourceType.IMPORT),
        subject_person_id=person,
        issuer=EntityRef(
            entity_type=EntityType.DEVICE,
            entity_id=TRUSTED_ISSUER,
        ),
        granted_authority=granted,
        valid_time=ValidTimeInterval(start=NOW),
        authority_evidence_ref=EvidenceRef(
            evidence_type="household_role_enrollment",
            source_record_id=uuid5(NAMESPACE, f"grant:{name}"),
        ),
        allowed_object_instance_ids=(() if allowed_object is None else (allowed_object,)),
        revoked=revoked,
    )


def test_forged_owner_claim_is_downgraded_to_the_attested_level() -> None:
    forged = _preference(
        "forged-owner",
        VISITOR,
        SOFA,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=2,
    )
    verified = PlacementAuthorityVerifier(trust_store=TRUST_STORE).verify(
        preferences=(forged,),
        attestations=(_attestation("visitor-grant", VISITOR, AuthorityLevel.UNVERIFIED_REPORTER),),
        decision_household_id=HOUSEHOLD,
        object_instance_id=OBJECT,
        object_class=None,
        decision_time=NOW + timedelta(hours=1),
    )

    assert verified.preferences[0].authority_level is AuthorityLevel.UNVERIFIED_REPORTER
    assert verified.receipts[0].status is AuthorityVerificationStatus.DOWNGRADED_TO_ATTESTED_LEVEL


def test_missing_revoked_or_out_of_scope_grant_fails_closed() -> None:
    claimed = _preference(
        "unsupported-owner",
        VISITOR,
        SOFA,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=2,
    )
    for attestations in (
        (),
        (_attestation("revoked", VISITOR, AuthorityLevel.HOUSEHOLD_OWNER, revoked=True),),
        (
            _attestation(
                "wrong-object",
                VISITOR,
                AuthorityLevel.HOUSEHOLD_OWNER,
                allowed_object=uuid5(NAMESPACE, "other-object"),
            ),
        ),
    ):
        verified = PlacementAuthorityVerifier(trust_store=TRUST_STORE).verify(
            preferences=(claimed,),
            attestations=attestations,
            decision_household_id=HOUSEHOLD,
            object_instance_id=OBJECT,
            object_class=None,
            decision_time=NOW + timedelta(hours=1),
        )
        assert verified.preferences[0].authority_level is AuthorityLevel.UNVERIFIED_REPORTER
        assert (
            verified.receipts[0].status
            is AuthorityVerificationStatus.DOWNGRADED_NO_VALID_ATTESTATION
        )


def test_llm_content_cannot_self_grant_authority_in_the_full_resolver() -> None:
    owner = _preference(
        "real-owner",
        OWNER,
        CLOSET,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=1,
    )
    forged = _preference(
        "llm-says-owner",
        VISITOR,
        SOFA,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=2,
    )
    result = ProvenanceBoundPlacementDecisionResolver(trust_store=TRUST_STORE).resolve(
        intent=PlacementIntent.PUT_BACK,
        decision_household_id=HOUSEHOLD,
        object_instance_id=OBJECT,
        decision_time=NOW + timedelta(hours=1),
        preferences=(owner, forged),
        attestations=(
            _attestation("owner-grant", OWNER, AuthorityLevel.HOUSEHOLD_OWNER),
            _attestation("visitor-grant-2", VISITOR, AuthorityLevel.UNVERIFIED_REPORTER),
        ),
    )

    assert result.placement.decision.target_location_id == CLOSET
    assert result.authority_verification_receipts[1].effective_authority is (
        AuthorityLevel.UNVERIFIED_REPORTER
    )


def test_untrusted_issuer_and_cross_household_injection_fail_closed() -> None:
    foreign_household = uuid5(NAMESPACE, "foreign-household")
    forged = _preference(
        "forged-owner-untrusted",
        VISITOR,
        SOFA,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=2,
    )
    untrusted_grant = _attestation(
        "untrusted-grant", VISITOR, AuthorityLevel.HOUSEHOLD_OWNER
    ).model_copy(
        update={
            "issuer": EntityRef(
                entity_type=EntityType.DEVICE,
                entity_id=uuid5(NAMESPACE, "untrusted-issuer"),
            )
        }
    )
    verified = PlacementAuthorityVerifier(trust_store=TRUST_STORE).verify(
        preferences=(forged,),
        attestations=(untrusted_grant,),
        decision_household_id=HOUSEHOLD,
        object_instance_id=OBJECT,
        object_class=None,
        decision_time=NOW + timedelta(hours=1),
    )
    assert verified.preferences[0].authority_level is AuthorityLevel.UNVERIFIED_REPORTER
    assert verified.receipts[0].status is AuthorityVerificationStatus.DOWNGRADED_UNTRUSTED_ISSUER

    foreign = forged.model_copy(
        update={"metadata": forged.metadata.model_copy(update={"household_id": foreign_household})}
    )
    rejected = PlacementAuthorityVerifier(trust_store=TRUST_STORE).verify(
        preferences=(foreign,),
        attestations=(untrusted_grant,),
        decision_household_id=HOUSEHOLD,
        object_instance_id=OBJECT,
        object_class=None,
        decision_time=NOW + timedelta(hours=1),
    )
    assert rejected.preferences == ()
    assert rejected.receipts[0].status is AuthorityVerificationStatus.REJECTED_CROSS_HOUSEHOLD


def test_caller_cannot_replace_bound_household_trust_root() -> None:
    attacker = Ed25519AttestationSigner.generate(key_id=TRUST_SIGNER.key_id)
    attacker_snapshot = issue_household_trust_store_snapshot(
        TRUST_SNAPSHOT.model_copy(
            update={
                "trusted_issuer_ids": (uuid5(NAMESPACE, "attacker-issuer"),),
                "attestation": None,
            }
        ),
        signer=attacker,
    )

    with pytest.raises(ValueError, match="signature"):
        verify_household_trust_store_snapshot(
            attacker_snapshot,
            verifier=TRUST_SIGNER.verifier(),
        )

    resolver = ProvenanceBoundPlacementDecisionResolver(trust_store=TRUST_STORE)
    assert "trusted_issuer_ids" not in resolver.resolve.__annotations__


def test_superseded_flag_requires_a_trusted_retirement_receipt() -> None:
    owner = _preference(
        "retired-owner",
        OWNER,
        CLOSET,
        AuthorityLevel.HOUSEHOLD_OWNER,
        minute=1,
    ).model_copy(update={"superseded": True})
    common = {
        "intent": PlacementIntent.PUT_BACK,
        "decision_household_id": HOUSEHOLD,
        "object_instance_id": OBJECT,
        "decision_time": NOW + timedelta(hours=1),
        "preferences": (owner,),
        "attestations": (
            _attestation("owner-retirement-grant", OWNER, AuthorityLevel.HOUSEHOLD_OWNER),
        ),
    }
    refused = ProvenanceBoundPlacementDecisionResolver(trust_store=TRUST_STORE).resolve(**common)
    assert refused.placement.decision.target_location_id == CLOSET
    assert refused.refused_retirement_record_ids == (owner.metadata.record_id,)

    receipt = PlacementRetirementAuthorization(
        metadata=_metadata("trusted-retirement", SourceType.ACTION),
        issuer=EntityRef(entity_type=EntityType.DEVICE, entity_id=TRUSTED_ISSUER),
        retired_record_id=owner.metadata.record_id,
        authority_level=AuthorityLevel.HOUSEHOLD_OWNER,
        update_policy_version=PLACEMENT_UPDATE_POLICY_VERSION,
        authorization_evidence_ref=EvidenceRef(
            evidence_type="placement_update_ledger_receipt",
            source_record_id=uuid5(NAMESPACE, "trusted-retirement-evidence"),
        ),
    )
    accepted = ProvenanceBoundPlacementDecisionResolver(trust_store=TRUST_STORE).resolve(
        **common,
        retirement_authorizations=(receipt,),
    )
    assert accepted.placement.decision.status.value == "abstain"
    assert accepted.authorized_retired_record_ids == (owner.metadata.record_id,)
