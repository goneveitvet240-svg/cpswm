"""RQ10's fourth gap: who may supersede a stated preference or a norm.

The audit line lists four things for RQ10:

    RQ10 行为/偏好/规范 -- 分层思想很好, 但未实现 -- 接入前缺口: 独立 schema,
    冲突规则, 授权来源和更新策略.

Three of the four turned out to be present after all, and are covered by
existing tests:

* 独立 schema — :class:`PlacementMemoryClass` keeps the four `§9` kinds apart,
  and :class:`StatedPreferenceAssertion` / :class:`PlacementNormAssertion` are
  separate record types with no training weight, so neither can leak into the
  observed-habit statistics.
* 冲突规则 — :class:`PlacementDecisionResolver` ranks norms by hardness and
  safety priority, lets a hard ``MUST_BE_AT`` beat a stated preference, blocks
  on a hard ``MUST_NOT_BE_AT``, and abstains rather than falling back to the
  observed habit.
* 授权来源 — ``source_type`` is firewalled per class (a stated preference must
  come from a user, a commonsense norm may not), and ``stated_by`` must be a
  person.

The fourth is genuinely missing.  ``superseded`` is a plain boolean the
producer sets, and nothing checks who set it.  As it stands a guest's
unverified remark can retire the household owner's standing instruction, and a
model-sourced commonsense prior can retire a household safety norm — silently,
because retiring an assertion looks exactly like writing one.

This module is that missing check.  Three rules, in the order they bind:

1. **Only a same-or-higher authority may supersede.**  Authority is the ordered
   :class:`AuthorityLevel` ladder that already exists for corrections.
2. **A norm class may only be superseded within its own provenance.**  A
   commonsense prior cannot retire a household rule; a household rule can
   retire a commonsense one, because the household is the more specific
   authority on its own home.
3. **A hard safety constraint needs an explicit acknowledgement to retire.**
   Not a higher authority alone: the retiring assertion must say, in a field,
   that it knows it is removing a safety constraint.  Safety norms exist
   precisely for the case where the person giving the instruction has not
   thought about the consequence.

Nothing here decides placement.  It decides whether a *write that removes an
existing rule* is allowed, which is the one operation the resolver cannot
recover from after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.placement_memory import (
    PlacementMemoryClass,
    PlacementNormAssertion,
    StatedPreferenceAssertion,
)

__all__ = [
    "AUTHORITY_RANK",
    "PLACEMENT_UPDATE_POLICY_VERSION",
    "PlacementUpdateDecision",
    "PlacementUpdateOutcome",
    "PlacementUpdatePolicy",
    "UnauthorizedSupersessionError",
]

PLACEMENT_UPDATE_POLICY_VERSION = "placement-update-policy@0.1"

#: The existing correction ladder, given a total order.  Declared here rather
#: than on the enum so that adding a level is a deliberate ranking decision
#: instead of an alphabetical accident.
AUTHORITY_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.UNVERIFIED_REPORTER: 0,
    AuthorityLevel.AUTHORIZED_REPORTER: 1,
    AuthorityLevel.AUTHORIZED_CORRECTOR: 2,
    AuthorityLevel.HOUSEHOLD_OWNER: 3,
    AuthorityLevel.SYSTEM_ADMIN: 4,
}


class PlacementUpdateOutcome(StrEnum):
    """What a proposed supersession is permitted to do."""

    #: The existing assertion is retired and the new one governs.
    SUPERSEDED = "superseded"
    #: Both stand; the resolver's conflict rules decide between them.
    COEXISTS = "coexists"
    #: The proposal is refused and the existing assertion is untouched.
    REFUSED = "refused"


class UnauthorizedSupersessionError(RuntimeError):
    """Raised when a write would retire a rule it has no standing to retire."""


@dataclass(frozen=True, slots=True)
class PlacementUpdateDecision:
    """One supersession proposal, with the reason it was allowed or refused."""

    outcome: PlacementUpdateOutcome
    reason: str
    existing_authority: AuthorityLevel | None = None
    proposed_authority: AuthorityLevel | None = None
    requires_safety_acknowledgement: bool = False
    policy_version: str = PLACEMENT_UPDATE_POLICY_VERSION

    @property
    def allowed(self) -> bool:
        return self.outcome is not PlacementUpdateOutcome.REFUSED

    def raise_if_refused(self) -> None:
        if not self.allowed:
            raise UnauthorizedSupersessionError(self.reason)

    def payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "existing_authority": (
                None if self.existing_authority is None else self.existing_authority.value
            ),
            "proposed_authority": (
                None if self.proposed_authority is None else self.proposed_authority.value
            ),
            "requires_safety_acknowledgement": self.requires_safety_acknowledgement,
            "policy_version": self.policy_version,
        }


class PlacementUpdatePolicy:
    """Decides whether one placement assertion may retire another."""

    def __init__(self, *, policy_version: str = PLACEMENT_UPDATE_POLICY_VERSION) -> None:
        self._policy_version = policy_version

    # -- stated preferences --------------------------------------------------

    def supersede_preference(
        self,
        *,
        existing: StatedPreferenceAssertion,
        proposed: StatedPreferenceAssertion,
    ) -> PlacementUpdateDecision:
        """A newer statement about the same subject retires an older one.

        Same subject is required: two preferences about different objects are
        not in conflict, and treating them as such would let one instruction
        silently erase an unrelated one.
        """

        if existing.superseded:
            return self._decision(
                PlacementUpdateOutcome.COEXISTS,
                "the existing preference is already superseded",
            )
        if not _same_subject(existing, proposed):
            return self._decision(
                PlacementUpdateOutcome.COEXISTS,
                "preferences about different subjects do not conflict",
            )
        if proposed.metadata.recorded_time <= existing.metadata.recorded_time:
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                "a preference cannot be retired by an older or simultaneous statement",
                existing_authority=existing.authority_level,
                proposed_authority=proposed.authority_level,
            )
        if _rank(proposed.authority_level) < _rank(existing.authority_level):
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                (
                    f"{proposed.authority_level.value} cannot retire a preference stated by "
                    f"{existing.authority_level.value}"
                ),
                existing_authority=existing.authority_level,
                proposed_authority=proposed.authority_level,
            )
        return self._decision(
            PlacementUpdateOutcome.SUPERSEDED,
            "a later statement of equal or higher authority replaces the earlier one",
            existing_authority=existing.authority_level,
            proposed_authority=proposed.authority_level,
        )

    # -- norms ---------------------------------------------------------------

    def supersede_norm(
        self,
        *,
        existing: PlacementNormAssertion,
        proposed: PlacementNormAssertion,
        authority: AuthorityLevel,
        acknowledges_safety_removal: bool = False,
    ) -> PlacementUpdateDecision:
        """Retire a norm.  Norms carry no authority field, so it is passed in.

        The asymmetry between the two norm classes is deliberate.  A household
        rule may retire a commonsense prior — the household is the authority on
        its own home.  A commonsense prior may not retire a household rule: a
        general model has no standing to overrule a specific instruction about
        a specific home, and letting it would mean a model update could quietly
        remove a safety constraint.
        """

        if existing.superseded:
            return self._decision(
                PlacementUpdateOutcome.COEXISTS, "the existing norm is already superseded"
            )
        if not _same_norm_target(existing, proposed):
            return self._decision(
                PlacementUpdateOutcome.COEXISTS,
                "norms with different subjects or rule kinds do not conflict",
            )
        if (
            existing.norm_class is PlacementMemoryClass.HOUSEHOLD_NORM
            and proposed.norm_class is PlacementMemoryClass.COMMONSENSE_NORM
        ):
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                "a commonsense prior cannot retire a household norm",
            )
        if _rank(authority) < _rank(AuthorityLevel.AUTHORIZED_CORRECTOR):
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                f"{authority.value} is not authorised to retire a placement norm",
                proposed_authority=authority,
            )
        if existing.is_hard_constraint and not acknowledges_safety_removal:
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                (
                    "retiring a hard safety constraint requires an explicit "
                    "acknowledgement that it is being removed"
                ),
                proposed_authority=authority,
                requires_safety_acknowledgement=True,
            )
        if (
            existing.is_hard_constraint
            and existing.norm_class is PlacementMemoryClass.HOUSEHOLD_NORM
            and _rank(authority) < _rank(AuthorityLevel.HOUSEHOLD_OWNER)
        ):
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                "only the household owner may retire a hard household safety norm",
                proposed_authority=authority,
                requires_safety_acknowledgement=True,
            )
        return self._decision(
            PlacementUpdateOutcome.SUPERSEDED,
            "an authorised update replaces the earlier norm",
            proposed_authority=authority,
        )

    # -- cross-class ---------------------------------------------------------

    def preference_may_override_norm(
        self,
        *,
        norm: PlacementNormAssertion,
        preference: StatedPreferenceAssertion,
    ) -> PlacementUpdateDecision:
        """A stated preference never *retires* a norm; it may only coexist.

        `§9` keeps 偏好 and 规范 as different kinds of memory for exactly this
        reason.  Wanting the medicine on the counter does not delete the rule
        that it must be out of a child's reach; it produces a conflict the
        resolver settles, in favour of the hard constraint.
        """

        if norm.is_hard_constraint:
            return self._decision(
                PlacementUpdateOutcome.REFUSED,
                "a stated preference cannot retire a hard placement norm",
                proposed_authority=preference.authority_level,
            )
        return self._decision(
            PlacementUpdateOutcome.COEXISTS,
            "a stated preference and a soft norm coexist; the resolver ranks them",
            proposed_authority=preference.authority_level,
        )

    # -- helpers -------------------------------------------------------------

    def _decision(
        self,
        outcome: PlacementUpdateOutcome,
        reason: str,
        *,
        existing_authority: AuthorityLevel | None = None,
        proposed_authority: AuthorityLevel | None = None,
        requires_safety_acknowledgement: bool = False,
    ) -> PlacementUpdateDecision:
        return PlacementUpdateDecision(
            outcome=outcome,
            reason=reason,
            existing_authority=existing_authority,
            proposed_authority=proposed_authority,
            requires_safety_acknowledgement=requires_safety_acknowledgement,
            policy_version=self._policy_version,
        )


def _rank(level: AuthorityLevel) -> int:
    return AUTHORITY_RANK[level]


def _same_subject(
    existing: StatedPreferenceAssertion,
    proposed: StatedPreferenceAssertion,
) -> bool:
    return existing.subject.model_dump(mode="python") == proposed.subject.model_dump(mode="python")


def _same_norm_target(
    existing: PlacementNormAssertion,
    proposed: PlacementNormAssertion,
) -> bool:
    return (
        existing.subject.model_dump(mode="python") == proposed.subject.model_dump(mode="python")
        and existing.rule_kind == proposed.rule_kind
    )


def _is_current(start: datetime, valid_to: datetime | None, moment: datetime) -> bool:
    return start <= moment and (valid_to is None or moment < valid_to)
