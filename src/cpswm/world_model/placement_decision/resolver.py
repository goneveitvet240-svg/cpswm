"""Route a placement question to the right §9 memory kind.

`项目结构一 §9` fixes one principle:

    "最可能在哪里找到" 与 "机器人应该放回哪里" 是两个不同的决策问题。

This resolver makes that principle executable.  Given an object and an intent,
it reads *only* the memory kind that intent is allowed to consult:

    FIND         → observed habit only.  A preference or a norm never changes
                   where an object actually is, so they are ignored here.
    PUT_BACK     → stated preference, constrained (and possibly overridden) by
                   norms.  It never falls back to the observed habit: using
                   "where it is" as "where it should go" is exactly the §9 error.
    SAFETY_CHECK → norms only, evaluated against a proposed location.

A disagreement between the observed habit and the put-back target is surfaced,
not silently resolved: it is the signal that the object is out of place and
should be tidied.

The resolver does not compute habits or learn preferences; it routes existing,
provenance-separated records.  Observed-habit input arrives as a plain location
distribution (e.g. ``MobilityProfile.location_distribution``) so this module
stays decoupled from how that habit was learned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cpswm.contracts.placement_memory import (
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    StatedPreferenceAssertion,
)


class PlacementIntent(StrEnum):
    """Why the placement question is being asked."""

    #: Where is the object likely to be found now?
    FIND = "find"
    #: Where should the robot put the object away?
    PUT_BACK = "put_back"
    #: Is a proposed location norm-compliant?
    SAFETY_CHECK = "safety_check"


class PlacementDecisionStatus(StrEnum):
    RESOLVED = "resolved"
    #: The required memory kind holds no applicable record.  Notably, PUT_BACK
    #: abstains rather than borrowing the observed habit.
    ABSTAIN = "abstain"
    #: Every candidate location is excluded by a hard norm.
    BLOCKED_BY_NORM = "blocked_by_norm"
    #: SAFETY_CHECK found the proposed location violates a hard norm.
    NORM_VIOLATION = "norm_violation"
    #: SAFETY_CHECK found no violated norm.
    COMPLIANT = "compliant"


@dataclass(frozen=True, slots=True)
class NormApplication:
    """One norm's effect on a decision, kept for explanation and audit."""

    norm_record_id: UUID
    norm_class: PlacementMemoryClass
    rule_kind: NormRuleKind
    is_hard_constraint: bool
    safety_priority: int
    effect: str
    location_id: UUID | None = None
    required_condition_key: str | None = None


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    """The routed answer, tagged with which memory kind governed it."""

    intent: PlacementIntent
    object_instance_id: UUID
    status: PlacementDecisionStatus
    governing_memory_class: PlacementMemoryClass | None
    target_location_id: UUID | None
    ranked_candidates: tuple[tuple[UUID, float], ...]
    applied_norms: tuple[NormApplication, ...]
    preference_habit_disagreement: bool
    rationale: str


def _norm_sort_key(norm: PlacementNormAssertion) -> tuple[int, int, int, str]:
    # Hard before soft; household before commonsense; higher priority first;
    # record_id last so ordering is deterministic for reproducible evaluation.
    household = norm.norm_class == PlacementMemoryClass.HOUSEHOLD_NORM
    return (
        0 if norm.is_hard_constraint else 1,
        0 if household else 1,
        -norm.safety_priority,
        str(norm.metadata.record_id),
    )


class PlacementDecisionResolver:
    """Route a placement question to the §9 memory kind it is allowed to read."""

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
    ) -> PlacementDecision:
        applicable_norms = self._applicable_norms(
            norms,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
        )
        if intent == PlacementIntent.FIND:
            return self._resolve_find(
                object_instance_id=object_instance_id,
                distribution=observed_location_distribution,
            )
        if intent == PlacementIntent.PUT_BACK:
            return self._resolve_put_back(
                object_instance_id=object_instance_id,
                object_class=object_class,
                decision_time=decision_time,
                distribution=observed_location_distribution,
                preferences=preferences,
                norms=applicable_norms,
            )
        return self._resolve_safety_check(
            object_instance_id=object_instance_id,
            proposed_location_id=proposed_location_id,
            norms=applicable_norms,
        )

    def _applicable_norms(
        self,
        norms: tuple[PlacementNormAssertion, ...],
        *,
        object_instance_id: UUID,
        object_class: str | None,
        decision_time: datetime,
    ) -> tuple[PlacementNormAssertion, ...]:
        applicable = [
            norm
            for norm in norms
            if not norm.superseded
            and norm.valid_time.contains(decision_time)
            and norm.subject.applies_to(
                object_instance_id=object_instance_id, object_class=object_class
            )
        ]
        return tuple(sorted(applicable, key=_norm_sort_key))

    def _resolve_find(
        self, *, object_instance_id: UUID, distribution: dict[UUID, float] | None
    ) -> PlacementDecision:
        # FIND reads observed habit only.  Norms and preferences describe where
        # an object *should* be, which cannot move where it *is*.
        ranked = _rank(distribution)
        if not ranked:
            return PlacementDecision(
                intent=PlacementIntent.FIND,
                object_instance_id=object_instance_id,
                status=PlacementDecisionStatus.ABSTAIN,
                governing_memory_class=None,
                target_location_id=None,
                ranked_candidates=(),
                applied_norms=(),
                preference_habit_disagreement=False,
                rationale="no observed-habit evidence for this object",
            )
        return PlacementDecision(
            intent=PlacementIntent.FIND,
            object_instance_id=object_instance_id,
            status=PlacementDecisionStatus.RESOLVED,
            governing_memory_class=PlacementMemoryClass.OBSERVED_HABIT,
            target_location_id=ranked[0][0],
            ranked_candidates=ranked,
            applied_norms=(),
            preference_habit_disagreement=False,
            rationale="ranked by observed habit; preferences and norms not consulted",
        )

    def _resolve_put_back(
        self,
        *,
        object_instance_id: UUID,
        object_class: str | None,
        decision_time: datetime,
        distribution: dict[UUID, float] | None,
        preferences: tuple[StatedPreferenceAssertion, ...],
        norms: tuple[PlacementNormAssertion, ...],
    ) -> PlacementDecision:
        preferred = self._preferred_location(
            preferences,
            object_instance_id=object_instance_id,
            object_class=object_class,
            decision_time=decision_time,
        )
        applied: list[NormApplication] = []

        # A hard MUST_BE_AT norm overrides even a stated preference: the point of
        # a safety norm is that it wins.  The sort puts the strongest first.
        forced = next(
            (
                norm
                for norm in norms
                if norm.is_hard_constraint and norm.rule_kind == NormRuleKind.MUST_BE_AT
            ),
            None,
        )
        forbidden = {
            norm.target_location_id
            for norm in norms
            if norm.is_hard_constraint and norm.rule_kind == NormRuleKind.MUST_NOT_BE_AT
        }
        for norm in norms:
            if norm.rule_kind == NormRuleKind.REQUIRES_CONDITION:
                applied.append(_condition_application(norm))

        governing: PlacementMemoryClass
        target: UUID | None
        if forced is not None and (preferred is None or forced.target_location_id != preferred):
            target = forced.target_location_id
            governing = forced.norm_class
            applied.append(_norm_application(forced, "required_location"))
        elif preferred is not None:
            if preferred in forbidden:
                blocking = next(norm for norm in norms if norm.target_location_id == preferred)
                applied.append(_norm_application(blocking, "excluded_location"))
                return _blocked(object_instance_id, tuple(applied))
            target = preferred
            governing = PlacementMemoryClass.STATED_PREFERENCE
        elif forced is not None:
            target = forced.target_location_id
            governing = forced.norm_class
            applied.append(_norm_application(forced, "required_location"))
        else:
            # No stated preference and no forcing norm.  Do NOT fall back to the
            # observed habit: "where it is" is not "where it should go".
            return PlacementDecision(
                intent=PlacementIntent.PUT_BACK,
                object_instance_id=object_instance_id,
                status=PlacementDecisionStatus.ABSTAIN,
                governing_memory_class=None,
                target_location_id=None,
                ranked_candidates=(),
                applied_norms=tuple(applied),
                preference_habit_disagreement=False,
                rationale="no stated preference or forcing norm; observed habit not used",
            )

        observed_top = _argmax(distribution)
        disagreement = observed_top is not None and observed_top != target
        return PlacementDecision(
            intent=PlacementIntent.PUT_BACK,
            object_instance_id=object_instance_id,
            status=PlacementDecisionStatus.RESOLVED,
            governing_memory_class=governing,
            target_location_id=target,
            ranked_candidates=((target, 1.0),),
            applied_norms=tuple(applied),
            preference_habit_disagreement=disagreement,
            rationale=(
                "put-back target from "
                + governing.value
                + ("; disagrees with observed habit (tidy signal)" if disagreement else "")
            ),
        )

    def _resolve_safety_check(
        self,
        *,
        object_instance_id: UUID,
        proposed_location_id: UUID | None,
        norms: tuple[PlacementNormAssertion, ...],
    ) -> PlacementDecision:
        if proposed_location_id is None:
            raise ValueError("safety_check requires a proposed_location_id")
        applied: list[NormApplication] = []
        violated = False
        for norm in norms:
            if norm.rule_kind == NormRuleKind.MUST_NOT_BE_AT:
                if norm.target_location_id == proposed_location_id:
                    applied.append(_norm_application(norm, "violated_must_not_be_at"))
                    violated = violated or norm.is_hard_constraint
            elif norm.rule_kind == NormRuleKind.MUST_BE_AT:
                if norm.target_location_id != proposed_location_id:
                    applied.append(_norm_application(norm, "violated_must_be_at"))
                    violated = violated or norm.is_hard_constraint
            else:
                applied.append(_condition_application(norm))
        status = (
            PlacementDecisionStatus.NORM_VIOLATION
            if violated
            else PlacementDecisionStatus.COMPLIANT
        )
        return PlacementDecision(
            intent=PlacementIntent.SAFETY_CHECK,
            object_instance_id=object_instance_id,
            status=status,
            governing_memory_class=(applied[0].norm_class if applied else None),
            target_location_id=proposed_location_id,
            ranked_candidates=(),
            applied_norms=tuple(applied),
            preference_habit_disagreement=False,
            rationale=("hard norm violated" if violated else "no hard norm violated"),
        )

    def _preferred_location(
        self,
        preferences: tuple[StatedPreferenceAssertion, ...],
        *,
        object_instance_id: UUID,
        object_class: str | None,
        decision_time: datetime,
    ) -> UUID | None:
        active = [
            pref
            for pref in preferences
            if not pref.superseded
            and pref.valid_time.contains(decision_time)
            and pref.subject.applies_to(
                object_instance_id=object_instance_id, object_class=object_class
            )
        ]
        if not active:
            return None
        # Instance-specific preferences beat class-level ones; break ties on the
        # most recently recorded statement, then record_id for determinism.
        active.sort(
            key=lambda pref: (
                0 if pref.subject.kind == "instance" else 1,
                -pref.metadata.recorded_time.timestamp(),
                str(pref.metadata.record_id),
            )
        )
        return active[0].preferred_location_id


def _rank(distribution: dict[UUID, float] | None) -> tuple[tuple[UUID, float], ...]:
    if not distribution:
        return ()
    return tuple(sorted(distribution.items(), key=lambda item: (-item[1], str(item[0]))))


def _argmax(distribution: dict[UUID, float] | None) -> UUID | None:
    ranked = _rank(distribution)
    return ranked[0][0] if ranked else None


def _norm_application(norm: PlacementNormAssertion, effect: str) -> NormApplication:
    return NormApplication(
        norm_record_id=norm.metadata.record_id,
        norm_class=norm.norm_class,
        rule_kind=norm.rule_kind,
        is_hard_constraint=norm.is_hard_constraint,
        safety_priority=norm.safety_priority,
        effect=effect,
        location_id=norm.target_location_id,
    )


def _condition_application(norm: PlacementNormAssertion) -> NormApplication:
    return NormApplication(
        norm_record_id=norm.metadata.record_id,
        norm_class=norm.norm_class,
        rule_kind=norm.rule_kind,
        is_hard_constraint=norm.is_hard_constraint,
        safety_priority=norm.safety_priority,
        effect="condition_required",
        required_condition_key=norm.required_condition_key,
    )


def _blocked(object_instance_id: UUID, applied: tuple[NormApplication, ...]) -> PlacementDecision:
    return PlacementDecision(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=object_instance_id,
        status=PlacementDecisionStatus.BLOCKED_BY_NORM,
        governing_memory_class=applied[-1].norm_class if applied else None,
        target_location_id=None,
        ranked_candidates=(),
        applied_norms=applied,
        preference_habit_disagreement=False,
        rationale="stated preference excluded by a hard norm",
    )
