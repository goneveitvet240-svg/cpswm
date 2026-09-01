"""Development-only runner for the preregistered placement-authority v0.2 route.

Only the 30 validation households are accessible here.  The sealed test range
is read solely to assert that no executed seed belongs to it.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import cache
from pathlib import Path
from statistics import fmean
from typing import Any
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
from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations.placement_authority_preregistration import (
    PlacementAuthorityPreregistration,
    file_sha256,
    load_placement_authority_preregistration,
)
from cpswm.world_model.placement_decision import (
    AUTHORITY_RANK,
    PLACEMENT_UPDATE_POLICY_VERSION,
    HouseholdTrustStoreSnapshot,
    PlacementAuthorityAttestation,
    PlacementAuthorityVerifier,
    PlacementDecisionResolver,
    PlacementDecisionStatus,
    PlacementIntent,
    PlacementRetirementAuthorization,
    ProvenanceBoundPlacementDecisionResolver,
    issue_household_trust_store_snapshot,
    verify_household_trust_store_snapshot,
)

_NAMESPACE = UUID("7399849b-bdb2-4641-ae22-f4b893309a9c")
_START = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
_CANDIDATE = "authority_scoped_v0_2"
_COLLAPSED = "collapsed_placement_memory"
_AGNOSTIC = "authority_agnostic_rule_resolver"

_ORACLE_DEFINITIONS: dict[str, dict[str, str]] = {
    "behavior_preference_conflict": {
        "correct_action": "place_at_verified_owner_preference",
        "failure": "uses_observed_habit_as_put_back_target",
    },
    "visitor_owner_conflict": {
        "correct_action": "place_at_verified_owner_preference",
        "failure": "lower_authority_visitor_overrides_owner",
    },
    "authorized_reporter_owner_conflict": {
        "correct_action": "place_at_verified_owner_preference",
        "failure": "authorized_reporter_overrides_owner",
    },
    "same_authority_recency": {
        "correct_action": "place_at_newer_equal_authority_preference",
        "failure": "older_equal_authority_preference_remains_active",
    },
    "same_authority_simultaneous_conflict": {
        "correct_action": "verify",
        "failure": "auto_resolves_equal_authority_simultaneous_conflict",
    },
    "low_authority_instance_high_authority_class": {
        "correct_action": "place_at_high_authority_class_preference",
        "failure": "specificity_is_allowed_to_beat_authority",
    },
    "hard_must_vs_forbid_conflict": {
        "correct_action": "verify",
        "failure": "auto_resolves_mutually_inconsistent_hard_norms",
    },
    "multiple_hard_required_locations": {
        "correct_action": "verify",
        "failure": "auto_selects_one_of_multiple_hard_required_locations",
    },
    "hard_safety_retraction": {
        "correct_action": "place_at_surviving_current_hard_rule",
        "failure": "uses_superseded_hard_rule_or_ignores_current_hard_rule",
    },
    "no_preference_abstention": {
        "correct_action": "abstain",
        "failure": "promotes_observed_habit_to_normative_put_back_target",
    },
}


class PlacementActionKind(StrEnum):
    PLACE = "place"
    VERIFY = "verify"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class PlacementAction:
    kind: PlacementActionKind
    location_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PlacementOracleCase:
    seed: int
    family: str
    household_id: UUID
    object_instance_id: UUID
    object_class: str | None
    decision_time: datetime
    observed_distribution: dict[UUID, float]
    preferences: tuple[StatedPreferenceAssertion, ...]
    attestations: tuple[PlacementAuthorityAttestation, ...]
    norms: tuple[PlacementNormAssertion, ...]
    expected_action: PlacementAction
    retirement_authorizations: tuple[PlacementRetirementAuthorization, ...] = ()
    unauthorized_location_ids: frozenset[UUID] = frozenset()
    hard_forbidden_location_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class PlacementOutcome:
    action: PlacementAction
    wrong_placement_cost: float
    semantic_layer_violation: float
    hard_safety_violation: float
    unauthorized_override: float
    unnecessary_verification: float
    unnecessary_abstention: float
    total_costs: tuple[float, ...]


def _stable_uuid(label: str) -> UUID:
    return uuid5(_NAMESPACE, label)


def _trusted_issuer_ids(household_id: UUID) -> frozenset[UUID]:
    return frozenset({_stable_uuid(f"{household_id}:trusted-enrollment-service")})


@cache
def _verified_trust_store(household_id: UUID):  # type: ignore[no-untyped-def]
    signer = Ed25519AttestationSigner.generate(key_id=f"placement-development:{household_id}")
    snapshot = issue_household_trust_store_snapshot(
        HouseholdTrustStoreSnapshot(
            snapshot_id=_stable_uuid(f"{household_id}:trust-store:v1"),
            household_id=household_id,
            version=1,
            trusted_issuer_ids=tuple(sorted(_trusted_issuer_ids(household_id), key=str)),
            issued_at=_START,
        ),
        signer=signer,
    )
    return verify_household_trust_store_snapshot(snapshot, verifier=signer.verifier())


def _metadata(
    *,
    seed: int,
    family: str,
    name: str,
    household_id: UUID,
    source: SourceType,
    minute: int,
    record_suffix: str = "",
) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        record_id=_stable_uuid(f"{seed}:{family}:{name}:record:{record_suffix}"),
        schema_name="cpswm.PlacementAuthorityDevelopmentFixture",
        schema_version="0.2.0",
        household_id=household_id,
        session_id=_stable_uuid(f"{seed}:{family}:session"),
        recorded_time=_START + timedelta(minutes=minute),
        source_type=source,
        source_id="placement-authority-v0.2-development",
        trace_id=_stable_uuid(f"{seed}:{family}:trace"),
    )


def _preference(
    *,
    seed: int,
    family: str,
    name: str,
    household_id: UUID,
    object_instance_id: UUID,
    object_class: str | None,
    actor_id: UUID,
    location_id: UUID,
    authority: AuthorityLevel,
    minute: int,
    class_scope: bool = False,
    valid_to_minute: int | None = None,
    record_suffix: str = "",
) -> StatedPreferenceAssertion:
    subject = (
        PlacementSubject(kind="class", object_class=object_class)
        if class_scope
        else PlacementSubject(kind="instance", object_instance_id=object_instance_id)
    )
    return StatedPreferenceAssertion(
        metadata=_metadata(
            seed=seed,
            family=family,
            name=name,
            household_id=household_id,
            source=SourceType.USER,
            minute=minute,
            record_suffix=record_suffix,
        ),
        subject=subject,
        preferred_location_id=location_id,
        stated_by=EntityRef(entity_type=EntityType.PERSON, entity_id=actor_id),
        authority_level=authority,
        valid_time=ValidTimeInterval(
            start=_START,
            end=(None if valid_to_minute is None else _START + timedelta(minutes=valid_to_minute)),
        ),
        user_statement_ref=EvidenceRef(
            evidence_type="user_statement",
            source_record_id=_stable_uuid(f"{seed}:{family}:{name}:statement"),
        ),
    )


def _attestation(
    *,
    seed: int,
    family: str,
    name: str,
    household_id: UUID,
    actor_id: UUID,
    authority: AuthorityLevel,
    object_instance_id: UUID,
    valid_to_minute: int | None = None,
    revoked: bool = False,
) -> PlacementAuthorityAttestation:
    return PlacementAuthorityAttestation(
        metadata=_metadata(
            seed=seed,
            family=family,
            name=f"{name}:attestation",
            household_id=household_id,
            source=SourceType.IMPORT,
            minute=0,
        ),
        subject_person_id=actor_id,
        issuer=EntityRef(
            entity_type=EntityType.DEVICE,
            entity_id=_stable_uuid(f"{household_id}:trusted-enrollment-service"),
        ),
        granted_authority=authority,
        valid_time=ValidTimeInterval(
            start=_START,
            end=(None if valid_to_minute is None else _START + timedelta(minutes=valid_to_minute)),
        ),
        authority_evidence_ref=EvidenceRef(
            evidence_type="household_role_enrollment",
            source_record_id=_stable_uuid(f"{seed}:{family}:{name}:grant"),
        ),
        allowed_object_instance_ids=(object_instance_id,),
        revoked=revoked,
    )


def _norm(
    *,
    seed: int,
    family: str,
    name: str,
    household_id: UUID,
    object_instance_id: UUID,
    kind: NormRuleKind,
    location_id: UUID,
    superseded: bool = False,
) -> PlacementNormAssertion:
    return PlacementNormAssertion(
        metadata=_metadata(
            seed=seed,
            family=family,
            name=name,
            household_id=household_id,
            source=SourceType.USER,
            minute=0,
        ),
        norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
        subject=PlacementSubject(kind="instance", object_instance_id=object_instance_id),
        rule_kind=kind,
        target_location_id=location_id,
        safety_priority=10,
        is_hard_constraint=True,
        valid_time=ValidTimeInterval(start=_START),
        superseded=superseded,
    )


def _retirement_authorization(
    *,
    seed: int,
    family: str,
    household_id: UUID,
    retired_record_id: UUID,
    replacement_record_id: UUID | None,
    authority: AuthorityLevel = AuthorityLevel.HOUSEHOLD_OWNER,
    safety_removal_acknowledged: bool = True,
) -> PlacementRetirementAuthorization:
    return PlacementRetirementAuthorization(
        metadata=_metadata(
            seed=seed,
            family=family,
            name="retirement-authorization",
            household_id=household_id,
            source=SourceType.ACTION,
            minute=3,
        ),
        issuer=EntityRef(
            entity_type=EntityType.DEVICE,
            entity_id=next(iter(_trusted_issuer_ids(household_id))),
        ),
        retired_record_id=retired_record_id,
        replacement_record_id=replacement_record_id,
        authority_level=authority,
        safety_removal_acknowledged=safety_removal_acknowledged,
        update_policy_version=PLACEMENT_UPDATE_POLICY_VERSION,
        authorization_evidence_ref=EvidenceRef(
            evidence_type="placement_update_ledger_receipt",
            source_record_id=_stable_uuid(f"{seed}:{family}:retirement-receipt"),
        ),
    )


def build_development_case(seed: int, family: str) -> PlacementOracleCase:
    household = _stable_uuid(f"{seed}:household")
    object_id = _stable_uuid(f"{seed}:object")
    object_class = "coat"
    owner = _stable_uuid(f"{seed}:owner")
    co_owner = _stable_uuid(f"{seed}:co-owner")
    visitor = _stable_uuid(f"{seed}:visitor")
    reporter = _stable_uuid(f"{seed}:reporter")
    habit, owner_location, alternative = (
        _stable_uuid(f"{seed}:location:{index}") for index in range(3)
    )
    decision_time = _START + timedelta(hours=1)
    observed = {habit: 0.90, owner_location: 0.08, alternative: 0.02}
    preferences: tuple[StatedPreferenceAssertion, ...] = ()
    attestations: tuple[PlacementAuthorityAttestation, ...] = ()
    norms: tuple[PlacementNormAssertion, ...] = ()
    retirement_authorizations: tuple[PlacementRetirementAuthorization, ...] = ()
    expected = PlacementAction(PlacementActionKind.PLACE, owner_location)
    unauthorized: frozenset[UUID] = frozenset()
    forbidden: frozenset[UUID] = frozenset()

    def pref(
        name: str,
        actor: UUID,
        location: UUID,
        authority: AuthorityLevel,
        minute: int,
        *,
        class_scope: bool = False,
        valid_to_minute: int | None = None,
    ) -> StatedPreferenceAssertion:
        return _preference(
            seed=seed,
            family=family,
            name=name,
            household_id=household,
            object_instance_id=object_id,
            object_class=object_class,
            actor_id=actor,
            location_id=location,
            authority=authority,
            minute=minute,
            class_scope=class_scope,
            valid_to_minute=valid_to_minute,
        )

    def grant(name: str, actor: UUID, authority: AuthorityLevel) -> PlacementAuthorityAttestation:
        return _attestation(
            seed=seed,
            family=family,
            name=name,
            household_id=household,
            actor_id=actor,
            authority=authority,
            object_instance_id=object_id,
        )

    if family == "behavior_preference_conflict":
        preferences = (pref("owner", owner, owner_location, AuthorityLevel.HOUSEHOLD_OWNER, 1),)
        attestations = (grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),)
    elif family == "visitor_owner_conflict":
        preferences = (
            pref("owner", owner, owner_location, AuthorityLevel.HOUSEHOLD_OWNER, 1),
            pref("visitor", visitor, habit, AuthorityLevel.UNVERIFIED_REPORTER, 2),
        )
        attestations = (
            grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),
            grant("visitor", visitor, AuthorityLevel.UNVERIFIED_REPORTER),
        )
        unauthorized = frozenset({habit})
    elif family == "authorized_reporter_owner_conflict":
        preferences = (
            pref("owner", owner, owner_location, AuthorityLevel.HOUSEHOLD_OWNER, 1),
            pref("reporter", reporter, habit, AuthorityLevel.AUTHORIZED_REPORTER, 2),
        )
        attestations = (
            grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),
            grant("reporter", reporter, AuthorityLevel.AUTHORIZED_REPORTER),
        )
        unauthorized = frozenset({habit})
    elif family == "same_authority_recency":
        preferences = (
            pref("owner-old", owner, owner_location, AuthorityLevel.HOUSEHOLD_OWNER, 1),
            pref("owner-new", owner, alternative, AuthorityLevel.HOUSEHOLD_OWNER, 2),
        )
        attestations = (grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),)
        expected = PlacementAction(PlacementActionKind.PLACE, alternative)
    elif family == "same_authority_simultaneous_conflict":
        preferences = (
            pref("owner-a", owner, owner_location, AuthorityLevel.HOUSEHOLD_OWNER, 1),
            pref("owner-b", co_owner, alternative, AuthorityLevel.HOUSEHOLD_OWNER, 1),
        )
        attestations = (
            grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),
            grant("co-owner", co_owner, AuthorityLevel.HOUSEHOLD_OWNER),
        )
        expected = PlacementAction(PlacementActionKind.VERIFY)
    elif family == "low_authority_instance_high_authority_class":
        preferences = (
            pref(
                "owner-class",
                owner,
                owner_location,
                AuthorityLevel.HOUSEHOLD_OWNER,
                1,
                class_scope=True,
            ),
            pref("visitor-instance", visitor, habit, AuthorityLevel.UNVERIFIED_REPORTER, 2),
        )
        attestations = (
            grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),
            grant("visitor", visitor, AuthorityLevel.UNVERIFIED_REPORTER),
        )
        unauthorized = frozenset({habit})
    elif family == "hard_must_vs_forbid_conflict":
        norms = (
            _norm(
                seed=seed,
                family=family,
                name="must",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_BE_AT,
                location_id=owner_location,
            ),
            _norm(
                seed=seed,
                family=family,
                name="forbid",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_NOT_BE_AT,
                location_id=owner_location,
            ),
        )
        expected = PlacementAction(PlacementActionKind.VERIFY)
        forbidden = frozenset({owner_location})
    elif family == "multiple_hard_required_locations":
        norms = (
            _norm(
                seed=seed,
                family=family,
                name="must-a",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_BE_AT,
                location_id=owner_location,
            ),
            _norm(
                seed=seed,
                family=family,
                name="must-b",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_BE_AT,
                location_id=alternative,
            ),
        )
        expected = PlacementAction(PlacementActionKind.VERIFY)
    elif family == "hard_safety_retraction":
        preferences = (pref("owner", owner, alternative, AuthorityLevel.HOUSEHOLD_OWNER, 2),)
        attestations = (grant("owner", owner, AuthorityLevel.HOUSEHOLD_OWNER),)
        norms = (
            _norm(
                seed=seed,
                family=family,
                name="retired-must",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_BE_AT,
                location_id=owner_location,
                superseded=True,
            ),
            _norm(
                seed=seed,
                family=family,
                name="current-must",
                household_id=household,
                object_instance_id=object_id,
                kind=NormRuleKind.MUST_BE_AT,
                location_id=alternative,
            ),
        )
        retirement_authorizations = (
            _retirement_authorization(
                seed=seed,
                family=family,
                household_id=household,
                retired_record_id=norms[0].metadata.record_id,
                replacement_record_id=norms[1].metadata.record_id,
            ),
        )
        expected = PlacementAction(PlacementActionKind.PLACE, alternative)
    elif family == "no_preference_abstention":
        expected = PlacementAction(PlacementActionKind.ABSTAIN)
    else:
        raise ValueError(f"unknown preregistered placement family: {family}")

    return PlacementOracleCase(
        seed=seed,
        family=family,
        household_id=household,
        object_instance_id=object_id,
        object_class=object_class,
        decision_time=decision_time,
        observed_distribution=observed,
        preferences=preferences,
        attestations=attestations,
        norms=norms,
        expected_action=expected,
        retirement_authorizations=retirement_authorizations,
        unauthorized_location_ids=unauthorized,
        hard_forbidden_location_ids=forbidden,
    )


def _hard_conflict(case: PlacementOracleCase) -> bool:
    active = tuple(
        norm
        for norm in _active_norms(case)
        if norm.is_hard_constraint and norm.valid_time.contains(case.decision_time)
    )
    forced = tuple(norm for norm in active if norm.rule_kind is NormRuleKind.MUST_BE_AT)
    forced_locations = {norm.target_location_id for norm in forced}
    if len(forced_locations) > 1:
        return True
    return bool(
        forced
        and any(
            norm.rule_kind is NormRuleKind.MUST_NOT_BE_AT
            and norm.target_location_id == forced[0].target_location_id
            for norm in active
        )
    )


def _authorized_retirement_ids(case: PlacementOracleCase) -> frozenset[UUID]:
    trusted = _trusted_issuer_ids(case.household_id)
    return frozenset(
        receipt.retired_record_id
        for receipt in case.retirement_authorizations
        if receipt.metadata.household_id == case.household_id
        and receipt.issuer.entity_id in trusted
    )


def _active_norms(case: PlacementOracleCase) -> tuple[PlacementNormAssertion, ...]:
    authorized = _authorized_retirement_ids(case)
    return tuple(
        norm
        for norm in case.norms
        if (not norm.superseded or norm.metadata.record_id not in authorized)
        and norm.valid_time.contains(case.decision_time)
    )


def _verified_preferences(case: PlacementOracleCase) -> tuple[StatedPreferenceAssertion, ...]:
    return (
        PlacementAuthorityVerifier(trust_store=_verified_trust_store(case.household_id))
        .verify(
            preferences=case.preferences,
            attestations=case.attestations,
            decision_household_id=case.household_id,
            object_instance_id=case.object_instance_id,
            object_class=case.object_class,
            decision_time=case.decision_time,
        )
        .preferences
    )


def _candidate_resolution(case: PlacementOracleCase):  # type: ignore[no-untyped-def]
    return ProvenanceBoundPlacementDecisionResolver(
        trust_store=_verified_trust_store(case.household_id)
    ).resolve(
        intent=PlacementIntent.PUT_BACK,
        decision_household_id=case.household_id,
        object_instance_id=case.object_instance_id,
        object_class=case.object_class,
        decision_time=case.decision_time,
        observed_location_distribution=case.observed_distribution,
        preferences=case.preferences,
        attestations=case.attestations,
        norms=case.norms,
        retirement_authorizations=case.retirement_authorizations,
    )


def _candidate_action(case: PlacementOracleCase) -> PlacementAction:
    result = _candidate_resolution(case)
    decision = result.placement.decision
    if decision.status is PlacementDecisionStatus.CONFLICT_REQUIRES_VERIFICATION:
        return PlacementAction(PlacementActionKind.VERIFY)
    if decision.status in {
        PlacementDecisionStatus.ABSTAIN,
        PlacementDecisionStatus.BLOCKED_BY_NORM,
    }:
        return PlacementAction(PlacementActionKind.ABSTAIN)
    return PlacementAction(PlacementActionKind.PLACE, decision.target_location_id)


def _collapsed_action(case: PlacementOracleCase, weight: float) -> PlacementAction:
    if _hard_conflict(case):
        return PlacementAction(PlacementActionKind.VERIFY)
    active_norms = _active_norms(case)
    forced = next(
        (
            norm.target_location_id
            for norm in active_norms
            if norm.is_hard_constraint and norm.rule_kind is NormRuleKind.MUST_BE_AT
        ),
        None,
    )
    if forced is not None:
        return PlacementAction(PlacementActionKind.PLACE, forced)
    scores = {
        location: weight * probability
        for location, probability in case.observed_distribution.items()
    }
    max_authority = max(AUTHORITY_RANK.values())
    for preference in _verified_preferences(case):
        if preference.valid_time.contains(case.decision_time) and not preference.superseded:
            authority_factor = 1.0 + AUTHORITY_RANK[preference.authority_level] / max_authority
            scores[preference.preferred_location_id] = (
                scores.get(preference.preferred_location_id, 0.0)
                + (1.0 - weight) * authority_factor
            )
    forbidden = {
        norm.target_location_id
        for norm in active_norms
        if norm.is_hard_constraint and norm.rule_kind is NormRuleKind.MUST_NOT_BE_AT
    }
    eligible = {location: score for location, score in scores.items() if location not in forbidden}
    if not eligible:
        return PlacementAction(PlacementActionKind.ABSTAIN)
    selected = min(eligible, key=lambda location: (-eligible[location], str(location)))
    return PlacementAction(PlacementActionKind.PLACE, selected)


def _agnostic_action(case: PlacementOracleCase, mode: str) -> PlacementAction:
    if _hard_conflict(case):
        return PlacementAction(PlacementActionKind.VERIFY)
    if mode == "specificity_then_recency":
        active = tuple(
            preference
            for preference in case.preferences
            if not preference.superseded
            and preference.valid_time.contains(case.decision_time)
            and preference.subject.applies_to(
                object_instance_id=case.object_instance_id,
                object_class=case.object_class,
            )
        )
        if active:
            most_specific = max(1 if item.subject.kind == "instance" else 0 for item in active)
            peers = tuple(
                item
                for item in active
                if (1 if item.subject.kind == "instance" else 0) == most_specific
            )
            latest = max(item.metadata.recorded_time for item in peers)
            simultaneous = {
                item.preferred_location_id
                for item in peers
                if item.metadata.recorded_time == latest
            }
            if len(simultaneous) > 1:
                return PlacementAction(PlacementActionKind.VERIFY)
        decision = PlacementDecisionResolver().resolve(
            intent=PlacementIntent.PUT_BACK,
            object_instance_id=case.object_instance_id,
            object_class=case.object_class,
            decision_time=case.decision_time,
            observed_location_distribution=case.observed_distribution,
            preferences=case.preferences,
            norms=case.norms,
        )
        if decision.status in {
            PlacementDecisionStatus.ABSTAIN,
            PlacementDecisionStatus.BLOCKED_BY_NORM,
        }:
            return PlacementAction(PlacementActionKind.ABSTAIN)
        return PlacementAction(PlacementActionKind.PLACE, decision.target_location_id)
    if mode != "recency_first":
        raise ValueError(f"unknown authority-agnostic mode: {mode}")
    active = tuple(
        preference
        for preference in case.preferences
        if not preference.superseded
        and preference.valid_time.contains(case.decision_time)
        and preference.subject.applies_to(
            object_instance_id=case.object_instance_id,
            object_class=case.object_class,
        )
    )
    if not active:
        return _agnostic_action(case, "specificity_then_recency")
    latest = max(item.metadata.recorded_time for item in active)
    simultaneous = {
        item.preferred_location_id for item in active if item.metadata.recorded_time == latest
    }
    if len(simultaneous) > 1:
        return PlacementAction(PlacementActionKind.VERIFY)
    selected = min(
        active,
        key=lambda preference: (
            -preference.metadata.recorded_time.timestamp(),
            str(preference.metadata.record_id),
        ),
    )
    return PlacementAction(PlacementActionKind.PLACE, selected.preferred_location_id)


def _score_action(
    case: PlacementOracleCase,
    action: PlacementAction,
    cost_grid: tuple[dict[str, float], ...],
) -> PlacementOutcome:
    wrong = float(action != case.expected_action)
    unauthorized = float(
        action.kind is PlacementActionKind.PLACE
        and action.location_id in case.unauthorized_location_ids
    )
    hard = float(
        action.kind is PlacementActionKind.PLACE
        and (
            action.location_id in case.hard_forbidden_location_ids
            or (case.expected_action.kind is PlacementActionKind.VERIFY and _hard_conflict(case))
        )
    )
    conflict_auto_resolved = float(
        case.expected_action.kind is PlacementActionKind.VERIFY
        and action.kind is PlacementActionKind.PLACE
    )
    semantic = max(unauthorized, conflict_auto_resolved)
    unnecessary_verification = float(
        action.kind is PlacementActionKind.VERIFY
        and case.expected_action.kind is not PlacementActionKind.VERIFY
    )
    unnecessary_abstention = float(
        action.kind is PlacementActionKind.ABSTAIN
        and case.expected_action.kind is not PlacementActionKind.ABSTAIN
    )
    total_costs = tuple(
        wrong * point["wrong_placement"]
        + hard * point["hard_safety_violation"]
        + float(action.kind is PlacementActionKind.VERIFY) * point["verification"]
        + unnecessary_abstention * point["unnecessary_abstention"]
        for point in cost_grid
    )
    return PlacementOutcome(
        action=action,
        wrong_placement_cost=wrong,
        semantic_layer_violation=semantic,
        hard_safety_violation=hard,
        unauthorized_override=unauthorized,
        unnecessary_verification=unnecessary_verification,
        unnecessary_abstention=unnecessary_abstention,
        total_costs=total_costs,
    )


def _cost_grid(protocol: PlacementAuthorityPreregistration) -> tuple[dict[str, float], ...]:
    return tuple(
        point.model_dump(mode="python") for point in protocol.endpoints.cost_sensitivity_grid
    )


def _outcome(
    case: PlacementOracleCase,
    method: str,
    parameter: float | str | None,
    cost_grid: tuple[dict[str, float], ...],
) -> PlacementOutcome:
    if method == _CANDIDATE:
        action = _candidate_action(case)
    elif method == _COLLAPSED:
        if not isinstance(parameter, float):
            raise TypeError("collapsed placement weight must be a float")
        action = _collapsed_action(case, parameter)
    elif method == _AGNOSTIC:
        if not isinstance(parameter, str):
            raise TypeError("authority-agnostic mode must be a string")
        action = _agnostic_action(case, parameter)
    else:
        raise ValueError(f"unknown placement method: {method}")
    return _score_action(case, action, cost_grid)


def _tune_opponent(
    *,
    method: str,
    grid: tuple[float | str, ...],
    cases: tuple[PlacementOracleCase, ...],
    cost_grid: tuple[dict[str, float], ...],
) -> tuple[float | str, list[dict[str, Any]]]:
    trials = []
    for parameter in grid:
        outcomes = tuple(_outcome(case, method, parameter, cost_grid) for case in cases)
        trials.append(
            {
                "parameter": parameter,
                "mean_wrong_placement_cost": fmean(item.wrong_placement_cost for item in outcomes),
                "mean_middle_sensitivity_total_cost": fmean(
                    item.total_costs[1] for item in outcomes
                ),
            }
        )
    selected = min(
        trials,
        key=lambda item: (
            item["mean_wrong_placement_cost"],
            item["mean_middle_sensitivity_total_cost"],
            str(item["parameter"]),
        ),
    )["parameter"]
    return selected, trials


def _aggregate(outcomes: tuple[PlacementOutcome, ...]) -> dict[str, Any]:
    return {
        "episode_count": len(outcomes),
        "mean_wrong_placement_cost": fmean(item.wrong_placement_cost for item in outcomes),
        "mean_semantic_layer_violation": fmean(item.semantic_layer_violation for item in outcomes),
        "hard_safety_violation_rate": fmean(item.hard_safety_violation for item in outcomes),
        "unauthorized_override_rate": fmean(item.unauthorized_override for item in outcomes),
        "unnecessary_verification_rate": fmean(item.unnecessary_verification for item in outcomes),
        "unnecessary_abstention_rate": fmean(item.unnecessary_abstention for item in outcomes),
        "mean_total_cost_by_sensitivity_point": [
            fmean(item.total_costs[index] for item in outcomes)
            for index in range(len(outcomes[0].total_costs))
        ],
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _household_interval(
    cases: tuple[PlacementOracleCase, ...],
    outcomes: tuple[PlacementOutcome, ...],
    *,
    field: str,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, float]:
    by_household: dict[int, list[float]] = {}
    for case, outcome in zip(cases, outcomes, strict=True):
        by_household.setdefault(case.seed, []).append(float(getattr(outcome, field)))
    household_means = tuple(fmean(values) for values in by_household.values())
    rng = random.Random(seed)
    replicates = [
        fmean(rng.choice(household_means) for _ in household_means)
        for _ in range(bootstrap_samples)
    ]
    return {
        "estimate": fmean(household_means),
        "confidence_interval_low": _percentile(replicates, 0.025),
        "confidence_interval_high": _percentile(replicates, 0.975),
        "confidence_level": 0.95,
    }


def _paired_household_interval(
    cases: tuple[PlacementOracleCase, ...],
    candidate: tuple[PlacementOutcome, ...],
    opponent: tuple[PlacementOutcome, ...],
    *,
    field: str,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, float]:
    # Cost endpoints are oriented as opponent minus candidate: larger favors v0.2.
    by_household: dict[int, list[float]] = {}
    for case, candidate_outcome, opponent_outcome in zip(cases, candidate, opponent, strict=True):
        by_household.setdefault(case.seed, []).append(
            float(getattr(opponent_outcome, field)) - float(getattr(candidate_outcome, field))
        )
    household_effects = tuple(fmean(values) for values in by_household.values())
    rng = random.Random(seed)
    replicates = [
        fmean(rng.choice(household_effects) for _ in household_effects)
        for _ in range(bootstrap_samples)
    ]
    return {
        "estimate": fmean(household_effects),
        "confidence_interval_low": _percentile(replicates, 0.025),
        "confidence_interval_high": _percentile(replicates, 0.975),
        "confidence_level": 0.95,
    }


def _semantic_action(action: PlacementAction) -> tuple[str, str | None]:
    return action.kind.value, None if action.location_id is None else str(action.location_id)


def _attack_audit(seed: int, base: PlacementOracleCase) -> dict[str, bool]:
    owner_preference = base.preferences[0]
    owner_attestation = base.attestations[0]
    visitor = _stable_uuid(f"{seed}:attack:visitor")
    forged = _preference(
        seed=seed,
        family="attack",
        name="forged-owner",
        household_id=base.household_id,
        object_instance_id=base.object_instance_id,
        object_class=base.object_class,
        actor_id=visitor,
        location_id=next(iter(base.observed_distribution)),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        minute=2,
    )
    visitor_grant = _attestation(
        seed=seed,
        family="attack",
        name="visitor",
        household_id=base.household_id,
        actor_id=visitor,
        authority=AuthorityLevel.UNVERIFIED_REPORTER,
        object_instance_id=base.object_instance_id,
    )
    attacked = replace(
        base,
        preferences=(owner_preference, forged),
        attestations=(owner_attestation, visitor_grant),
    )
    forged_pass = _candidate_action(attacked) == base.expected_action

    revoked_owner_claim = _attestation(
        seed=seed,
        family="attack",
        name="revoked-forged-owner",
        household_id=base.household_id,
        actor_id=visitor,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        object_instance_id=base.object_instance_id,
        revoked=True,
    )
    revoked_attestation_pass = (
        _candidate_action(replace(attacked, attestations=(owner_attestation, revoked_owner_claim)))
        == base.expected_action
    )
    expired_owner_claim = revoked_owner_claim.model_copy(
        update={
            "metadata": revoked_owner_claim.metadata.model_copy(
                update={"record_id": _stable_uuid(f"{seed}:attack:expired-grant")}
            ),
            "valid_time": ValidTimeInterval(start=_START, end=_START + timedelta(minutes=30)),
            "revoked": False,
        }
    )
    expired_attestation_pass = (
        _candidate_action(replace(attacked, attestations=(owner_attestation, expired_owner_claim)))
        == base.expected_action
    )

    expired = _preference(
        seed=seed,
        family="attack",
        name="expired-owner",
        household_id=base.household_id,
        object_instance_id=base.object_instance_id,
        object_class=base.object_class,
        actor_id=visitor,
        location_id=next(iter(base.observed_distribution)),
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        minute=0,
        valid_to_minute=30,
    )
    expired_pass = (
        _candidate_action(replace(base, preferences=(owner_preference, expired)))
        == base.expected_action
    )

    preferences = (owner_preference, forged)
    permutation_actions = {
        _semantic_action(_candidate_action(replace(attacked, preferences=permutation)))
        for permutation in itertools.permutations(preferences)
    }
    permutation_pass = len(permutation_actions) == 1

    relabeled_owner = owner_preference.model_copy(
        update={
            "metadata": owner_preference.metadata.model_copy(
                update={"record_id": _stable_uuid(f"{seed}:attack:relabeled-owner")}
            )
        }
    )
    record_id_pass = (
        _candidate_action(replace(base, preferences=(relabeled_owner,))) == base.expected_action
    )

    duplicate_forged = forged.model_copy(
        update={
            "metadata": forged.metadata.model_copy(
                update={"record_id": _stable_uuid(f"{seed}:attack:duplicate-forged")}
            )
        }
    )
    duplicate_pass = (
        _candidate_action(
            replace(attacked, preferences=(owner_preference, forged, duplicate_forged))
        )
        == base.expected_action
    )

    untrusted_owner_grant = _attestation(
        seed=seed,
        family="attack",
        name="untrusted-owner",
        household_id=base.household_id,
        actor_id=visitor,
        authority=AuthorityLevel.HOUSEHOLD_OWNER,
        object_instance_id=base.object_instance_id,
    ).model_copy(
        update={
            "issuer": EntityRef(
                entity_type=EntityType.DEVICE,
                entity_id=_stable_uuid(f"{seed}:attack:untrusted-issuer"),
            )
        }
    )
    untrusted_issuer_pass = (
        _candidate_action(
            replace(
                attacked,
                attestations=(owner_attestation, visitor_grant, untrusted_owner_grant),
            )
        )
        == base.expected_action
    )

    other_household = _stable_uuid(f"{seed}:attack:other-household")
    cross_household_forged = forged.model_copy(
        update={
            "metadata": forged.metadata.model_copy(
                update={
                    "record_id": _stable_uuid(f"{seed}:attack:cross-household-record"),
                    "household_id": other_household,
                }
            )
        }
    )
    cross_household_pass = (
        _candidate_action(replace(base, preferences=(owner_preference, cross_household_forged)))
        == base.expected_action
    )

    unauthorized_retired_owner = owner_preference.model_copy(update={"superseded": True})
    unauthorized_preference_retirement_case = replace(
        base,
        preferences=(unauthorized_retired_owner, base.preferences[1]),
    )
    unauthorized_preference_resolution = _candidate_resolution(
        unauthorized_preference_retirement_case
    )
    unauthorized_preference_retirement_pass = (
        _candidate_action(unauthorized_preference_retirement_case) == base.expected_action
        and owner_preference.metadata.record_id
        in unauthorized_preference_resolution.refused_retirement_record_ids
    )

    simultaneous_pass = (
        _candidate_action(build_development_case(seed, "same_authority_simultaneous_conflict")).kind
        is PlacementActionKind.VERIFY
    )
    hard_conflict_pass = (
        _candidate_action(build_development_case(seed, "hard_must_vs_forbid_conflict")).kind
        is PlacementActionKind.VERIFY
    )
    visitor_specific_pass = (
        _candidate_action(
            build_development_case(seed, "low_authority_instance_high_authority_class")
        ).location_id
        == base.expected_action.location_id
    )
    retraction_case = build_development_case(seed, "hard_safety_retraction")
    retired, current = retraction_case.norms
    missing_retraction = retired.model_copy(update={"superseded": False})
    missing_retraction_pass = (
        _candidate_action(replace(retraction_case, norms=(missing_retraction, current))).kind
        is PlacementActionKind.VERIFY
    )
    hard_conflict_case = build_development_case(seed, "hard_must_vs_forbid_conflict")
    must, forbid = hard_conflict_case.norms
    forged_retired_forbid = forbid.model_copy(update={"superseded": True})
    unauthorized_hard_case = replace(
        hard_conflict_case,
        norms=(must, forged_retired_forbid),
        retirement_authorizations=(),
    )
    unauthorized_hard_resolution = _candidate_resolution(unauthorized_hard_case)
    unauthorized_hard_retirement_pass = (
        _candidate_action(unauthorized_hard_case).kind is PlacementActionKind.VERIFY
        and forbid.metadata.record_id in unauthorized_hard_resolution.refused_retirement_record_ids
    )
    trusted_retirement_resolution = _candidate_resolution(retraction_case)
    trusted_retirement_pass = (
        _candidate_action(retraction_case) == retraction_case.expected_action
        and retired.metadata.record_id
        in trusted_retirement_resolution.authorized_retired_record_ids
    )

    return {
        "forged_high_authority": forged_pass,
        "revoked_authority_attestation": revoked_attestation_pass,
        "expired_authority_attestation": expired_attestation_pass,
        "expired_preference_replay": expired_pass,
        "simultaneous_equal_authority_conflict": simultaneous_pass,
        "visitor_instance_specificity_attack": visitor_specific_pass,
        "hard_norm_conflict": hard_conflict_pass,
        "missing_retraction_record": missing_retraction_pass,
        "input_permutation": permutation_pass,
        "record_uuid_relabel": record_id_pass,
        "semantic_duplicate_new_id": duplicate_pass,
        "untrusted_issuer_forgery": untrusted_issuer_pass,
        "cross_household_injection": cross_household_pass,
        "unauthorized_preference_retirement": unauthorized_preference_retirement_pass,
        "unauthorized_hard_norm_retirement": unauthorized_hard_retirement_pass,
        "trusted_retirement_receipt": trusted_retirement_pass,
    }


def run_placement_authority_development(
    config_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    protocol = load_placement_authority_preregistration(
        config_path,
        repository_root=repository_root,
    )
    validation_seeds = tuple(
        range(
            protocol.validation_split.seed_start,
            protocol.validation_split.seed_start + protocol.validation_split.seed_count,
        )
    )
    sealed_seeds = set(
        range(
            protocol.sealed_test_split.seed_start,
            protocol.sealed_test_split.seed_start + protocol.sealed_test_split.seed_count,
        )
    )
    if set(validation_seeds) & sealed_seeds:
        raise RuntimeError("development runner attempted to access sealed household seeds")
    tuning_seeds = validation_seeds[:20]
    diagnostic_seeds = validation_seeds[20:]
    families = protocol.scenario_families
    tuning_cases = tuple(
        build_development_case(seed, family) for seed in tuning_seeds for family in families
    )
    diagnostic_cases = tuple(
        build_development_case(seed, family) for seed in diagnostic_seeds for family in families
    )
    cost_grid = _cost_grid(protocol)
    opponent_by_id = {item.opponent_id: item for item in protocol.opponents}
    collapsed_parameter, collapsed_trials = _tune_opponent(
        method=_COLLAPSED,
        grid=opponent_by_id[_COLLAPSED].tuning_grid,
        cases=tuning_cases,
        cost_grid=cost_grid,
    )
    agnostic_parameter, agnostic_trials = _tune_opponent(
        method=_AGNOSTIC,
        grid=opponent_by_id[_AGNOSTIC].tuning_grid,
        cases=tuning_cases,
        cost_grid=cost_grid,
    )
    parameters: dict[str, float | str | None] = {
        _CANDIDATE: None,
        _COLLAPSED: collapsed_parameter,
        _AGNOSTIC: agnostic_parameter,
    }
    outcomes: dict[str, tuple[PlacementOutcome, ...]] = {
        method: tuple(_outcome(case, method, parameter, cost_grid) for case in diagnostic_cases)
        for method, parameter in parameters.items()
    }
    by_family = {
        family: {
            method: _aggregate(
                tuple(
                    outcome
                    for case, outcome in zip(diagnostic_cases, method_outcomes, strict=True)
                    if case.family == family
                )
            )
            for method, method_outcomes in outcomes.items()
        }
        for family in families
    }
    attack_results = {
        seed: _attack_audit(
            seed,
            build_development_case(seed, "visitor_owner_conflict"),
        )
        for seed in validation_seeds
    }
    attack_names = tuple(next(iter(attack_results.values())))
    attack_summary = {
        name: {
            "household_count": len(validation_seeds),
            "pass_count": sum(result[name] for result in attack_results.values()),
            "failure_count": sum(not result[name] for result in attack_results.values()),
        }
        for name in attack_names
    }
    executed_seeds = set(validation_seeds)
    if executed_seeds & sealed_seeds:
        raise RuntimeError("sealed household seed accessed during development execution")
    interval_fields = (
        "wrong_placement_cost",
        "semantic_layer_violation",
        "hard_safety_violation",
        "unauthorized_override",
    )
    cluster_intervals = {
        method: {
            field: _household_interval(
                diagnostic_cases,
                method_outcomes,
                field=field,
                bootstrap_samples=protocol.decision_rule.bootstrap_samples,
                seed=58_000 + method_index * 10 + field_index,
            )
            for field_index, field in enumerate(interval_fields)
        }
        for method_index, (method, method_outcomes) in enumerate(outcomes.items())
    }
    paired_effects = {
        opponent: {
            "wrong_placement_cost_oriented_opponent_minus_candidate": (
                _paired_household_interval(
                    diagnostic_cases,
                    outcomes[_CANDIDATE],
                    outcomes[opponent],
                    field="wrong_placement_cost",
                    bootstrap_samples=protocol.decision_rule.bootstrap_samples,
                    seed=59_000 + opponent_index * 10,
                )
            ),
            "semantic_layer_violation_oriented_opponent_minus_candidate": (
                _paired_household_interval(
                    diagnostic_cases,
                    outcomes[_CANDIDATE],
                    outcomes[opponent],
                    field="semantic_layer_violation",
                    bootstrap_samples=protocol.decision_rule.bootstrap_samples,
                    seed=59_001 + opponent_index * 10,
                )
            ),
        }
        for opponent_index, opponent in enumerate((_COLLAPSED, _AGNOSTIC))
    }
    provenance_case = next(
        case for case in diagnostic_cases if case.family == "visitor_owner_conflict"
    )
    provenance_resolution = ProvenanceBoundPlacementDecisionResolver(
        trust_store=_verified_trust_store(provenance_case.household_id)
    ).resolve(
        intent=PlacementIntent.PUT_BACK,
        decision_household_id=provenance_case.household_id,
        object_instance_id=provenance_case.object_instance_id,
        object_class=provenance_case.object_class,
        decision_time=provenance_case.decision_time,
        observed_location_distribution=provenance_case.observed_distribution,
        preferences=provenance_case.preferences,
        attestations=provenance_case.attestations,
        norms=provenance_case.norms,
        retirement_authorizations=provenance_case.retirement_authorizations,
    )
    authority_receipt = provenance_resolution.placement.authority_receipt
    provenance_sample = {
        "household_id": str(provenance_case.household_id),
        "object_instance_id": str(provenance_case.object_instance_id),
        "identity_to_role_receipts": [
            item.model_dump(mode="json")
            for item in provenance_resolution.authority_verification_receipts
        ],
        "role_to_decision_receipt": {
            "status": authority_receipt.status.value,
            "selected_record_id": (
                None
                if authority_receipt.selected_record_id is None
                else str(authority_receipt.selected_record_id)
            ),
            "selected_authority": (
                None
                if authority_receipt.selected_authority is None
                else authority_receipt.selected_authority.value
            ),
            "rejected_lower_authority_record_ids": [
                str(item) for item in authority_receipt.rejected_lower_authority_record_ids
            ],
            "conflicting_record_ids": [
                str(item) for item in authority_receipt.conflicting_record_ids
            ],
            "reason": authority_receipt.reason,
        },
        "final_action": {
            "status": provenance_resolution.placement.decision.status.value,
            "target_location_id": str(provenance_resolution.placement.decision.target_location_id),
        },
    }
    return {
        "schema_name": "cpswm.PlacementAuthorityDevelopmentReport",
        "schema_version": "0.2.0",
        "scientific_status": "development_only_not_formal_evidence",
        "preregistration_sha256": file_sha256(config_path),
        "development_household_count": len(validation_seeds),
        "tuning_household_count": len(tuning_seeds),
        "diagnostic_household_count": len(diagnostic_seeds),
        "scenario_family_count": len(families),
        "diagnostic_episode_count": len(diagnostic_cases),
        "effective_structural_scenario_count": len(families),
        "inference_validity": "deterministic_fixture_variants_not_population_inference",
        "confidence_intervals_valid_for_external_claim": False,
        "executed_seed_sha256": hashlib.sha256(
            json.dumps(validation_seeds).encode("utf-8")
        ).hexdigest(),
        "max_executed_seed": max(executed_seeds),
        "sealed_test_seed_start": protocol.sealed_test_split.seed_start,
        "sealed_test_access_count": 0,
        "sealed_test_execution_status": protocol.sealed_test_split.execution_status,
        "split_receipts": {
            "opponent_tuning_seed_sha256": hashlib.sha256(
                json.dumps(tuning_seeds).encode("utf-8")
            ).hexdigest(),
            "development_diagnostic_seed_sha256": hashlib.sha256(
                json.dumps(diagnostic_seeds).encode("utf-8")
            ).hexdigest(),
            "disjoint": set(tuning_seeds).isdisjoint(diagnostic_seeds),
        },
        "oracle_definitions": _ORACLE_DEFINITIONS,
        "opponent_fairness_receipts": {
            _COLLAPSED: {
                "independently_tuned": True,
                "same_visible_records": True,
                "same_action_budget": True,
                "shared_hard_conflict_verification": True,
            },
            _AGNOSTIC: {
                "independently_tuned": True,
                "same_visible_records": True,
                "same_action_budget": True,
                "shared_hard_conflict_verification": True,
            },
        },
        "selected_parameters": parameters,
        "tuning_trials": {
            _COLLAPSED: collapsed_trials,
            _AGNOSTIC: agnostic_trials,
        },
        "aggregate_metrics": {
            method: _aggregate(method_outcomes) for method, method_outcomes in outcomes.items()
        },
        "household_cluster_intervals": cluster_intervals,
        "paired_development_effects": paired_effects,
        "authority_provenance_sample": provenance_sample,
        "scenario_metrics": by_family,
        "attack_summary": attack_summary,
        "all_candidate_attacks_passed": all(
            item["failure_count"] == 0 for item in attack_summary.values()
        ),
        "paper_claim_allowed": False,
        "formal_decision": "not_evaluated",
        "limitations": [
            "Only preregistered validation households were used.",
            "Opponent tuning used 20 development households; diagnostics used the other 10.",
            "No sealed-test, real-perception, hosted-LLM, or external-validity evidence was run.",
            "Household seeds instantiate ten deterministic templates; bootstrap intervals "
            "are diagnostic stability summaries, not population inference.",
        ],
    }


__all__ = [
    "PlacementAction",
    "PlacementActionKind",
    "PlacementOracleCase",
    "PlacementOutcome",
    "build_development_case",
    "run_placement_authority_development",
]
