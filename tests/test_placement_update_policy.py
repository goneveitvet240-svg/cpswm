"""RQ10 更新策略: 谁有资格撤销一条偏好或规范.

    RQ10 行为/偏好/规范 -- 接入前缺口: 独立 schema, 冲突规则, 授权来源和更新策略.

The first three were already implemented and are covered by
``tests/test_placement_memory_separation.py``; this file covers the fourth,
which was a bare boolean nobody checked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
from cpswm.contracts.placement_memory import (
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    PlacementSubject,
    StatedPreferenceAssertion,
)
from cpswm.world_model.placement_decision import (
    AUTHORITY_RANK,
    PlacementUpdateOutcome,
    PlacementUpdatePolicy,
    UnauthorizedSupersessionError,
)

HOUSEHOLD = uuid4()
SESSION = uuid4()
TRACE = uuid4()
COAT = uuid4()
WARDROBE = uuid4()
SOFA = uuid4()
HIGH_SHELF = uuid4()
MOMENT = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _metadata(source: SourceType, *, at: datetime = MOMENT):  # type: ignore[no-untyped-def]
    return BaseRecordMetadata(
        record_id=uuid4(),
        schema_name="cpswm.PlacementAssertion",
        schema_version="0.1.0",
        household_id=HOUSEHOLD,
        session_id=SESSION,
        recorded_time=at,
        source_type=source,
        source_id="rq10-test",
        trace_id=TRACE,
    )


def _subject(object_id=COAT):  # type: ignore[no-untyped-def]
    return PlacementSubject(kind="instance", object_instance_id=object_id)


def preference(
    *,
    location=WARDROBE,
    authority: AuthorityLevel = AuthorityLevel.HOUSEHOLD_OWNER,
    at: datetime = MOMENT,
    subject=None,
    superseded: bool = False,
) -> StatedPreferenceAssertion:
    return StatedPreferenceAssertion(
        metadata=_metadata(SourceType.USER, at=at),
        subject=subject or _subject(),
        preferred_location_id=location,
        stated_by=EntityRef(entity_type=EntityType.PERSON, entity_id=uuid4()),
        authority_level=authority,
        valid_time=ValidTimeInterval(start=at),
        user_statement_ref=EvidenceRef(evidence_type="user_statement", source_record_id=uuid4()),
        superseded=superseded,
    )


def norm(
    *,
    norm_class: PlacementMemoryClass = PlacementMemoryClass.HOUSEHOLD_NORM,
    rule_kind: NormRuleKind = NormRuleKind.MUST_BE_AT,
    target=HIGH_SHELF,
    hard: bool = True,
    priority: int = 10,
    at: datetime = MOMENT,
    superseded: bool = False,
    subject=None,
) -> PlacementNormAssertion:
    source = (
        SourceType.USER if norm_class is PlacementMemoryClass.HOUSEHOLD_NORM else SourceType.MODEL
    )
    return PlacementNormAssertion(
        metadata=_metadata(source, at=at),
        norm_class=norm_class,
        subject=subject or _subject(),
        rule_kind=rule_kind,
        target_location_id=target,
        safety_priority=priority,
        is_hard_constraint=hard,
        valid_time=ValidTimeInterval(start=at),
        superseded=superseded,
    )


POLICY = PlacementUpdatePolicy()
LATER = MOMENT + timedelta(days=1)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


def test_a_guest_cannot_retire_the_owners_standing_instruction() -> None:
    """The failure the bare ``superseded`` boolean allowed.

    Fails if authority stops gating supersession, at which point any statement
    can erase any other.
    """

    decision = POLICY.supersede_preference(
        existing=preference(authority=AuthorityLevel.HOUSEHOLD_OWNER),
        proposed=preference(location=SOFA, authority=AuthorityLevel.UNVERIFIED_REPORTER, at=LATER),
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert not decision.allowed
    with pytest.raises(UnauthorizedSupersessionError, match="cannot retire"):
        decision.raise_if_refused()


def test_the_owner_can_change_their_own_mind() -> None:
    decision = POLICY.supersede_preference(
        existing=preference(location=WARDROBE),
        proposed=preference(location=SOFA, at=LATER),
    )
    assert decision.outcome is PlacementUpdateOutcome.SUPERSEDED
    decision.raise_if_refused()


def test_equal_authority_is_enough() -> None:
    decision = POLICY.supersede_preference(
        existing=preference(authority=AuthorityLevel.AUTHORIZED_REPORTER),
        proposed=preference(location=SOFA, authority=AuthorityLevel.AUTHORIZED_REPORTER, at=LATER),
    )
    assert decision.outcome is PlacementUpdateOutcome.SUPERSEDED


def test_an_older_statement_cannot_retire_a_newer_one() -> None:
    """Otherwise a replayed log would undo a decision it already recorded."""

    decision = POLICY.supersede_preference(
        existing=preference(at=LATER),
        proposed=preference(location=SOFA, at=MOMENT),
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert "older or simultaneous" in decision.reason


def test_preferences_about_different_objects_do_not_conflict() -> None:
    """Retiring an unrelated instruction is the quietest possible data loss."""

    decision = POLICY.supersede_preference(
        existing=preference(),
        proposed=preference(subject=_subject(uuid4()), at=LATER),
    )
    assert decision.outcome is PlacementUpdateOutcome.COEXISTS


def test_an_already_retired_preference_is_left_alone() -> None:
    decision = POLICY.supersede_preference(
        existing=preference(superseded=True),
        proposed=preference(location=SOFA, at=LATER),
    )
    assert decision.outcome is PlacementUpdateOutcome.COEXISTS


# ---------------------------------------------------------------------------
# Norms
# ---------------------------------------------------------------------------


def test_a_commonsense_prior_cannot_retire_a_household_rule() -> None:
    """A model update must not be able to remove a household safety constraint.

    Fails if norm provenance stops being checked, which would make the
    household/commonsense split decorative.
    """

    decision = POLICY.supersede_norm(
        existing=norm(norm_class=PlacementMemoryClass.HOUSEHOLD_NORM),
        proposed=norm(norm_class=PlacementMemoryClass.COMMONSENSE_NORM, at=LATER),
        authority=AuthorityLevel.SYSTEM_ADMIN,
        acknowledges_safety_removal=True,
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert "commonsense prior" in decision.reason


def test_a_household_rule_may_retire_a_commonsense_prior() -> None:
    """The asymmetry has to run one way, not neither."""

    decision = POLICY.supersede_norm(
        existing=norm(norm_class=PlacementMemoryClass.COMMONSENSE_NORM, hard=False),
        proposed=norm(norm_class=PlacementMemoryClass.HOUSEHOLD_NORM, at=LATER, hard=False),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
    )
    assert decision.outcome is PlacementUpdateOutcome.SUPERSEDED


def test_retiring_a_hard_constraint_needs_an_explicit_acknowledgement() -> None:
    """Authority alone is not enough to remove a safety rule.

    Fails if the acknowledgement is dropped, which would let "put the medicine
    on the counter" silently delete "medicine stays out of reach".
    """

    decision = POLICY.supersede_norm(
        existing=norm(hard=True),
        proposed=norm(hard=False, at=LATER),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert decision.requires_safety_acknowledgement

    acknowledged = POLICY.supersede_norm(
        existing=norm(hard=True),
        proposed=norm(hard=False, at=LATER),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        acknowledges_safety_removal=True,
    )
    assert acknowledged.outcome is PlacementUpdateOutcome.SUPERSEDED


def test_only_the_owner_may_retire_a_hard_household_safety_norm() -> None:
    decision = POLICY.supersede_norm(
        existing=norm(hard=True, norm_class=PlacementMemoryClass.HOUSEHOLD_NORM),
        proposed=norm(hard=False, at=LATER),
        authority=AuthorityLevel.AUTHORIZED_CORRECTOR,
        acknowledges_safety_removal=True,
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert "household owner" in decision.reason


def test_an_unverified_reporter_cannot_touch_norms_at_all() -> None:
    decision = POLICY.supersede_norm(
        existing=norm(hard=False),
        proposed=norm(hard=False, at=LATER),
        authority=AuthorityLevel.UNVERIFIED_REPORTER,
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED
    assert "not authorised" in decision.reason


def test_norms_with_different_rule_kinds_do_not_conflict() -> None:
    decision = POLICY.supersede_norm(
        existing=norm(rule_kind=NormRuleKind.MUST_BE_AT, hard=False),
        proposed=norm(rule_kind=NormRuleKind.MUST_NOT_BE_AT, hard=False, at=LATER),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
    )
    assert decision.outcome is PlacementUpdateOutcome.COEXISTS


# ---------------------------------------------------------------------------
# Cross-class: §9's central distinction
# ---------------------------------------------------------------------------


def test_a_stated_preference_never_retires_a_hard_norm() -> None:
    """Wanting something is not authorisation to delete a safety rule.

    This is the concrete form of `§9`'s "最可能在哪里找到" ≠ "应该放回哪里":
    the two memories answer different questions, so one cannot overwrite the
    other.
    """

    decision = POLICY.preference_may_override_norm(
        norm=norm(hard=True),
        preference=preference(location=SOFA),
    )
    assert decision.outcome is PlacementUpdateOutcome.REFUSED


def test_a_stated_preference_and_a_soft_norm_coexist() -> None:
    decision = POLICY.preference_may_override_norm(
        norm=norm(hard=False),
        preference=preference(location=SOFA),
    )
    assert decision.outcome is PlacementUpdateOutcome.COEXISTS
    assert decision.allowed


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------


def test_every_authority_level_has_an_explicit_rank() -> None:
    """An unranked level would compare as an error, not as "lowest"."""

    assert set(AUTHORITY_RANK) == set(AuthorityLevel)
    assert len(set(AUTHORITY_RANK.values())) == len(AuthorityLevel)


def test_the_ladder_orders_owner_above_reporter_above_unverified() -> None:
    assert (
        AUTHORITY_RANK[AuthorityLevel.UNVERIFIED_REPORTER]
        < AUTHORITY_RANK[AuthorityLevel.AUTHORIZED_REPORTER]
        < AUTHORITY_RANK[AuthorityLevel.AUTHORIZED_CORRECTOR]
        < AUTHORITY_RANK[AuthorityLevel.HOUSEHOLD_OWNER]
        < AUTHORITY_RANK[AuthorityLevel.SYSTEM_ADMIN]
    )


def test_decision_payload_is_versioned_and_serialisable() -> None:
    payload = POLICY.supersede_preference(
        existing=preference(),
        proposed=preference(location=SOFA, at=LATER),
    ).payload()
    assert payload["outcome"] == "superseded"
    assert payload["policy_version"].startswith("placement-update-policy@")
