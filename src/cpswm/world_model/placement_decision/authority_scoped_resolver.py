"""Authority-scoped placement resolution for the preregistered v0.2 route.

The legacy :class:`PlacementDecisionResolver` deliberately remains unchanged so
the Round-2 failure stays reproducible.  This module is the new candidate.  It
connects the authority already present on stated preferences to the action-time
decision and fails closed when equally decisive records conflict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.placement_memory import (
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    StatedPreferenceAssertion,
)

from .resolver import (
    PlacementDecision,
    PlacementDecisionResolver,
    PlacementDecisionStatus,
    PlacementIntent,
)
from .update_policy import AUTHORITY_RANK

AUTHORITY_SCOPED_RESOLVER_VERSION = "authority-scoped-placement-resolver@0.2"


class AuthorityAdjudicationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NO_APPLICABLE_PREFERENCE = "no_applicable_preference"
    SELECTED = "selected"
    CONFLICT_REQUIRES_VERIFICATION = "conflict_requires_verification"


@dataclass(frozen=True, slots=True)
class AuthorityAdjudicationReceipt:
    """Why a preference was selected, rejected, or sent for verification."""

    status: AuthorityAdjudicationStatus
    selected_record_id: UUID | None = None
    selected_authority: AuthorityLevel | None = None
    applicable_record_ids: tuple[UUID, ...] = ()
    rejected_lower_authority_record_ids: tuple[UUID, ...] = ()
    rejected_less_specific_record_ids: tuple[UUID, ...] = ()
    conflicting_record_ids: tuple[UUID, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AuthorityScopedPlacementResolution:
    """Placement answer plus an auditable action-time authority receipt."""

    decision: PlacementDecision
    authority_receipt: AuthorityAdjudicationReceipt
    policy_version: str = AUTHORITY_SCOPED_RESOLVER_VERSION


class AuthorityScopedPlacementDecisionResolver:
    """Resolve placement with safety-first and authority-scoped preferences.

    Frozen ordering for v0.2:

    1. contradictory applicable hard norms never resolve by record ID;
    2. preference authority outranks subject specificity;
    3. within equal authority, instance scope outranks class scope;
    4. within equal authority and scope, the newest statement wins;
    5. simultaneous top-ranked statements for different locations require
       verification instead of an arbitrary tie break.
    """

    def __init__(self) -> None:
        self._legacy_router = PlacementDecisionResolver()

    def resolve(
        self,
        *,
        intent: PlacementIntent,
        object_instance_id: UUID,
        object_class: str | None = None,
        decision_time: datetime,
        observed_location_distribution: dict[UUID, float] | None = None,
        preferences: tuple[StatedPreferenceAssertion, ...] = (),
        norms: tuple[PlacementNormAssertion, ...] = (),
        proposed_location_id: UUID | None = None,
    ) -> AuthorityScopedPlacementResolution:
        if intent is not PlacementIntent.PUT_BACK:
            decision = self._legacy_router.resolve(
                intent=intent,
                object_instance_id=object_instance_id,
                object_class=object_class,
                decision_time=decision_time,
                observed_location_distribution=observed_location_distribution,
                preferences=preferences,
                norms=norms,
                proposed_location_id=proposed_location_id,
            )
            return AuthorityScopedPlacementResolution(
                decision=decision,
                authority_receipt=AuthorityAdjudicationReceipt(
                    status=AuthorityAdjudicationStatus.NOT_APPLICABLE,
                    reason="authority adjudication applies only to put_back",
                ),
            )

        norm_conflicts = _hard_norm_conflicts(
            norms,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
        )
        if norm_conflicts:
            return AuthorityScopedPlacementResolution(
                decision=_conflict_decision(
                    object_instance_id,
                    "applicable hard placement norms are mutually inconsistent",
                    governing_memory_class=None,
                ),
                authority_receipt=AuthorityAdjudicationReceipt(
                    status=AuthorityAdjudicationStatus.CONFLICT_REQUIRES_VERIFICATION,
                    conflicting_record_ids=norm_conflicts,
                    reason="hard norm conflict must be verified before acting",
                ),
            )

        selected, receipt = _adjudicate_preferences(
            preferences,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
        )
        if receipt.status is AuthorityAdjudicationStatus.CONFLICT_REQUIRES_VERIFICATION:
            return AuthorityScopedPlacementResolution(
                decision=_conflict_decision(
                    object_instance_id,
                    "equally authoritative current preferences disagree",
                    governing_memory_class=PlacementMemoryClass.STATED_PREFERENCE,
                ),
                authority_receipt=receipt,
            )

        decision = self._legacy_router.resolve(
            intent=intent,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
            observed_location_distribution=observed_location_distribution,
            preferences=(() if selected is None else (selected,)),
            norms=norms,
        )
        return AuthorityScopedPlacementResolution(
            decision=decision,
            authority_receipt=receipt,
        )


def _adjudicate_preferences(
    preferences: tuple[StatedPreferenceAssertion, ...],
    *,
    object_instance_id: UUID,
    object_class: str | None,
    decision_time: datetime,
) -> tuple[StatedPreferenceAssertion | None, AuthorityAdjudicationReceipt]:
    applicable = tuple(
        preference
        for preference in preferences
        if not preference.superseded
        and preference.valid_time.contains(decision_time)
        and preference.subject.applies_to(
            object_instance_id=object_instance_id,
            object_class=object_class,
        )
    )
    applicable_ids = _record_ids(applicable)
    if not applicable:
        return None, AuthorityAdjudicationReceipt(
            status=AuthorityAdjudicationStatus.NO_APPLICABLE_PREFERENCE,
            applicable_record_ids=(),
            reason="no active stated preference applies to this object",
        )

    decisive_rank = max(AUTHORITY_RANK[item.authority_level] for item in applicable)
    authority_eligible = tuple(
        item for item in applicable if AUTHORITY_RANK[item.authority_level] == decisive_rank
    )
    rejected_authority = tuple(item for item in applicable if item not in authority_eligible)

    instance_available = any(item.subject.kind == "instance" for item in authority_eligible)
    specificity_eligible = tuple(
        item
        for item in authority_eligible
        if not instance_available or item.subject.kind == "instance"
    )
    rejected_specificity = tuple(
        item for item in authority_eligible if item not in specificity_eligible
    )

    newest = max(item.metadata.recorded_time for item in specificity_eligible)
    newest_records = tuple(
        item for item in specificity_eligible if item.metadata.recorded_time == newest
    )
    locations = {item.preferred_location_id for item in newest_records}
    if len(locations) > 1:
        return None, AuthorityAdjudicationReceipt(
            status=AuthorityAdjudicationStatus.CONFLICT_REQUIRES_VERIFICATION,
            selected_authority=newest_records[0].authority_level,
            applicable_record_ids=applicable_ids,
            rejected_lower_authority_record_ids=_record_ids(rejected_authority),
            rejected_less_specific_record_ids=_record_ids(rejected_specificity),
            conflicting_record_ids=_record_ids(newest_records),
            reason="top-ranked simultaneous preferences name different locations",
        )

    selected = min(newest_records, key=lambda item: str(item.metadata.record_id))
    return selected, AuthorityAdjudicationReceipt(
        status=AuthorityAdjudicationStatus.SELECTED,
        selected_record_id=selected.metadata.record_id,
        selected_authority=selected.authority_level,
        applicable_record_ids=applicable_ids,
        rejected_lower_authority_record_ids=_record_ids(rejected_authority),
        rejected_less_specific_record_ids=_record_ids(rejected_specificity),
        reason="authority, scope specificity, then recency selected the preference",
    )


def _hard_norm_conflicts(
    norms: tuple[PlacementNormAssertion, ...],
    *,
    object_instance_id: UUID,
    object_class: str | None,
    decision_time: datetime,
) -> tuple[UUID, ...]:
    hard = tuple(
        norm
        for norm in norms
        if norm.is_hard_constraint
        and not norm.superseded
        and norm.valid_time.contains(decision_time)
        and norm.subject.applies_to(
            object_instance_id=object_instance_id,
            object_class=object_class,
        )
    )
    forced = tuple(norm for norm in hard if norm.rule_kind is NormRuleKind.MUST_BE_AT)
    forced_locations = {norm.target_location_id for norm in forced}
    if len(forced_locations) > 1:
        return _record_ids(forced)
    if forced:
        target = forced[0].target_location_id
        forbidden = tuple(
            norm
            for norm in hard
            if norm.rule_kind is NormRuleKind.MUST_NOT_BE_AT and norm.target_location_id == target
        )
        if forbidden:
            return _record_ids((*forced, *forbidden))
    return ()


def _record_ids(
    records: tuple[StatedPreferenceAssertion | PlacementNormAssertion, ...],
) -> tuple[UUID, ...]:
    return tuple(sorted((item.metadata.record_id for item in records), key=str))


def _conflict_decision(
    object_instance_id: UUID,
    rationale: str,
    *,
    governing_memory_class: PlacementMemoryClass | None,
) -> PlacementDecision:
    return PlacementDecision(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=object_instance_id,
        status=PlacementDecisionStatus.CONFLICT_REQUIRES_VERIFICATION,
        governing_memory_class=governing_memory_class,
        target_location_id=None,
        ranked_candidates=(),
        applied_norms=(),
        preference_habit_disagreement=False,
        rationale=rationale,
    )


__all__ = [
    "AUTHORITY_SCOPED_RESOLVER_VERSION",
    "AuthorityAdjudicationReceipt",
    "AuthorityAdjudicationStatus",
    "AuthorityScopedPlacementDecisionResolver",
    "AuthorityScopedPlacementResolution",
]
