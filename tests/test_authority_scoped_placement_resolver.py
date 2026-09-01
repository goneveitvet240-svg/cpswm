"""Development-only mechanism tests for the preregistered v0.2 resolver."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from cpswm.contracts.base import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)
from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.placement_memory import (
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    PlacementSubject,
    StatedPreferenceAssertion,
)
from cpswm.world_model.placement_decision import (
    AUTHORITY_SCOPED_RESOLVER_VERSION,
    AuthorityAdjudicationStatus,
    AuthorityScopedPlacementDecisionResolver,
    PlacementDecisionResolver,
    PlacementDecisionStatus,
    PlacementIntent,
)

NAMESPACE = UUID("5478569f-b8e0-48ae-bc9f-92f08ac46f3f")
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)
HOUSEHOLD = uuid5(NAMESPACE, "household")
OBJECT = uuid5(NAMESPACE, "object")
OWNER = uuid5(NAMESPACE, "owner")
VISITOR = uuid5(NAMESPACE, "visitor")
CLOSET = uuid5(NAMESPACE, "closet")
SOFA = uuid5(NAMESPACE, "sofa")


def _metadata(name: str, at: datetime, source: SourceType) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        record_id=uuid5(NAMESPACE, f"record:{name}"),
        schema_name="cpswm.AuthorityScopedPlacementFixture",
        schema_version="0.2.0",
        household_id=HOUSEHOLD,
        session_id=uuid5(NAMESPACE, "session"),
        recorded_time=at,
        source_type=source,
        source_id="authority-scoped-development-fixture",
        trace_id=uuid5(NAMESPACE, "trace"),
    )


def _preference(
    name: str,
    *,
    location: UUID,
    authority: AuthorityLevel,
    actor: UUID,
    minute: int,
    object_class: str | None = None,
) -> StatedPreferenceAssertion:
    at = NOW + timedelta(minutes=minute)
    subject = (
        PlacementSubject(kind="class", object_class=object_class)
        if object_class is not None
        else PlacementSubject(kind="instance", object_instance_id=OBJECT)
    )
    return StatedPreferenceAssertion(
        metadata=_metadata(name, at, SourceType.USER),
        subject=subject,
        preferred_location_id=location,
        stated_by=EntityRef(entity_type=EntityType.PERSON, entity_id=actor),
        authority_level=authority,
        valid_time=ValidTimeInterval(start=NOW),
        user_statement_ref=EvidenceRef(
            evidence_type="user_statement",
            source_record_id=uuid5(NAMESPACE, f"evidence:{name}"),
        ),
    )


def _norm(name: str, kind: NormRuleKind, location: UUID) -> PlacementNormAssertion:
    return PlacementNormAssertion(
        metadata=_metadata(name, NOW, SourceType.USER),
        norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
        subject=PlacementSubject(kind="instance", object_instance_id=OBJECT),
        rule_kind=kind,
        target_location_id=location,
        safety_priority=10,
        is_hard_constraint=True,
        valid_time=ValidTimeInterval(start=NOW),
    )


def _resolve(
    preferences: tuple[StatedPreferenceAssertion, ...],
    norms: tuple[PlacementNormAssertion, ...] = (),
    *,
    object_class: str | None = None,
):  # type: ignore[no-untyped-def]
    return AuthorityScopedPlacementDecisionResolver().resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=OBJECT,
        object_class=object_class,
        decision_time=NOW + timedelta(hours=1),
        preferences=preferences,
        norms=norms,
    )


def test_newer_unverified_visitor_cannot_beat_owner() -> None:
    owner = _preference(
        "owner",
        location=CLOSET,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
    )
    visitor = _preference(
        "visitor",
        location=SOFA,
        authority=AuthorityLevel.UNVERIFIED_REPORTER,
        actor=VISITOR,
        minute=2,
    )

    result = _resolve((owner, visitor))

    assert result.decision.target_location_id == CLOSET
    assert result.authority_receipt.selected_record_id == owner.metadata.record_id
    assert result.authority_receipt.rejected_lower_authority_record_ids == (
        visitor.metadata.record_id,
    )
    assert result.policy_version == AUTHORITY_SCOPED_RESOLVER_VERSION


def test_authority_precedes_instance_specificity() -> None:
    owner_class = _preference(
        "owner-class",
        location=CLOSET,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
        object_class="coat",
    )
    visitor_instance = _preference(
        "visitor-instance",
        location=SOFA,
        authority=AuthorityLevel.UNVERIFIED_REPORTER,
        actor=VISITOR,
        minute=2,
    )

    result = _resolve((owner_class, visitor_instance), object_class="coat")

    assert result.decision.target_location_id == CLOSET
    assert result.authority_receipt.selected_record_id == owner_class.metadata.record_id


def test_equal_authority_uses_newer_statement() -> None:
    older = _preference(
        "older",
        location=CLOSET,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
    )
    newer = _preference(
        "newer",
        location=SOFA,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=2,
    )

    result = _resolve((older, newer))

    assert result.decision.target_location_id == SOFA
    assert result.authority_receipt.selected_record_id == newer.metadata.record_id


def test_simultaneous_equal_authority_disagreement_requires_verification() -> None:
    first = _preference(
        "simultaneous-a",
        location=CLOSET,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
    )
    second = _preference(
        "simultaneous-b",
        location=SOFA,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
    )

    result = _resolve((first, second))

    assert result.decision.status is PlacementDecisionStatus.CONFLICT_REQUIRES_VERIFICATION
    assert result.decision.target_location_id is None
    assert (
        result.authority_receipt.status
        is AuthorityAdjudicationStatus.CONFLICT_REQUIRES_VERIFICATION
    )
    assert set(result.authority_receipt.conflicting_record_ids) == {
        first.metadata.record_id,
        second.metadata.record_id,
    }


def test_contradictory_hard_norms_require_verification() -> None:
    result = _resolve(
        (),
        (
            _norm("must-closet", NormRuleKind.MUST_BE_AT, CLOSET),
            _norm("forbid-closet", NormRuleKind.MUST_NOT_BE_AT, CLOSET),
        ),
    )

    assert result.decision.status is PlacementDecisionStatus.CONFLICT_REQUIRES_VERIFICATION
    assert result.decision.target_location_id is None
    assert len(result.authority_receipt.conflicting_record_ids) == 2


def test_non_put_back_intents_keep_the_existing_memory_boundary() -> None:
    result = AuthorityScopedPlacementDecisionResolver().resolve(
        intent=PlacementIntent.FIND,
        object_instance_id=OBJECT,
        decision_time=NOW,
        observed_location_distribution={SOFA: 1.0},
        preferences=(
            _preference(
                "ignored-find-preference",
                location=CLOSET,
                authority=AuthorityLevel.HOUSEHOLD_OWNER,
                actor=OWNER,
                minute=1,
            ),
        ),
    )

    assert result.decision.target_location_id == SOFA
    assert result.authority_receipt.status is AuthorityAdjudicationStatus.NOT_APPLICABLE


def test_legacy_resolver_remains_available_to_reproduce_round_two_failure() -> None:
    owner = _preference(
        "legacy-owner",
        location=CLOSET,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        actor=OWNER,
        minute=1,
    )
    visitor = _preference(
        "legacy-visitor",
        location=SOFA,
        authority=AuthorityLevel.UNVERIFIED_REPORTER,
        actor=VISITOR,
        minute=2,
    )

    decision = PlacementDecisionResolver().resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=OBJECT,
        decision_time=NOW + timedelta(hours=1),
        preferences=(owner, visitor),
    )

    assert decision.target_location_id == SOFA
