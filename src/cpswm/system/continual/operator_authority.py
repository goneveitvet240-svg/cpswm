"""RQ9: which operator is allowed to write what, enforced instead of documented.

The audit line:

    RQ9 非平稳阶段 -- 正确 -- 接入前缺口: 明确 CF-BOCPD/RGRC/CCRR 权限, 补强公平基线.

The permissions already exist as prose, spread across three documents.
``项目一二_核心架构与相关工作对照`` §2.1 says CF-BOCPD *"仅提出变化候选"*; the
same section says a candidate is quarantined and *"不写任何长期统计"* until CCRR
routes it; ``方向结构二`` assigns the ``quarantine / promote / retract /
reactivate`` decision to RGRC.  Nothing in the code says any of that.  A future
edit that lets the detector write a long-term count would pass every test, and
the resulting numbers would look like a better detector rather than a broken
firewall.

Two things are declared here.

**Write authority.**  :data:`OPERATOR_AUTHORITY` is the matrix.  The
load-bearing rows:

``CF_BOCPD``
    May propose a change candidate.  Nothing else.  In particular it may not
    write a long-term statistic, because "the detector fired" is not "the
    habit moved" — that gap is the entire reason the confirmation window
    exists.
``CCRR``
    May route between regimes and may write the regime library.  It may not
    write long-term statistics either: choosing *which* regime an event
    belongs to is not the same authority as deciding the event is admissible.
``RGRC``
    The only operator that may write a long-term statistic, and it may do so
    only through ``quarantine → promote``.  Concentrating that authority in
    one operator is what makes 访客污染 auditable: there is exactly one place
    to look.

No operator may write an actor posterior.  That value arrives on the evidence
channel (RQ8) and an operator that could edit it could manufacture the very
attribution it is supposed to be judged on.

**Matched authority.**  ``补强公平基线`` is the second half.  A baseline that
cannot promote to long-term memory is not a weaker method, it is a different
experiment; comparing it to a candidate that can is the authority-shaped
version of the information asymmetry RQ8 found in the actor channel.
:func:`assert_matched_authority` refuses a comparison whose arms hold different
authority unless the difference is declared as the thing under study.

This module is a guard, not a scheduler.  It does not run operators and it does
not decide anything; it answers "was that write allowed" and refuses when the
answer is no.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "OPERATOR_AUTHORITY",
    "OPERATOR_AUTHORITY_VERSION",
    "AuthorityProfile",
    "AuthorityViolation",
    "HabitOperator",
    "OperatorAuthorityLedger",
    "UnauthorizedOperatorWriteError",
    "UnmatchedAuthorityError",
    "WriteTarget",
    "assert_matched_authority",
    "authority_of",
]

OPERATOR_AUTHORITY_VERSION = "operator-authority@0.1"


class HabitOperator(StrEnum):
    """The seven candidate operators, plus the two non-operator writers."""

    OPCEU = "opceu"
    CHEH = "cheh"
    PCHMP = "pchmp"
    CF_BOCPD = "cf_bocpd"
    RGRC = "rgrc"
    CCRR = "ccrr"
    CIAV = "ciav"
    #: The evaluator-side channel that supplies actor posteriors (RQ8).
    EVIDENCE_CHANNEL = "evidence_channel"
    #: The planner-side readout that turns beliefs into the next action.
    ACTION_READOUT = "action_readout"


class WriteTarget(StrEnum):
    """Everything a project-one operator can mutate."""

    #: "A change may have happened here."  A proposal, not a fact.
    CHANGE_CANDIDATE = "change_candidate"
    #: Which regime head is active for an object/actor pair.
    REGIME_ROUTE = "regime_route"
    #: The isolation buffer a candidate sits in before confirmation.
    QUARANTINE = "quarantine"
    #: Dirichlet counts, RLS sufficient statistics, hybrid ledger deltas.
    LONG_TERM_STATISTIC = "long_term_statistic"
    #: Stored historical regimes available for reactivation.
    REGIME_LIBRARY = "regime_library"
    #: Mutually exclusive hidden-event hypotheses.
    EVENT_HYPOTHESIS = "event_hypothesis"
    #: Posterior over who caused a transition.
    ACTOR_POSTERIOR = "actor_posterior"
    #: The distribution the planner reads to choose the next action.
    ACTION_DISTRIBUTION = "action_distribution"
    #: A request for an active verification action.
    VERIFICATION_REQUEST = "verification_request"


#: The matrix.  Deliberately restrictive: an operator that needs a target it
#: does not have should have that argued for and added here, where the change
#: is visible in a diff, rather than acquired silently at a call site.
OPERATOR_AUTHORITY: Mapping[HabitOperator, frozenset[WriteTarget]] = {
    # Observation-process correction reweights evidence before it is counted;
    # it never decides admissibility itself.
    HabitOperator.OPCEU: frozenset({WriteTarget.CHANGE_CANDIDATE}),
    HabitOperator.CHEH: frozenset({WriteTarget.EVENT_HYPOTHESIS}),
    HabitOperator.PCHMP: frozenset({WriteTarget.EVENT_HYPOTHESIS, WriteTarget.ACTOR_POSTERIOR}),
    # "仅提出变化候选" -- one target, and it is a proposal.
    HabitOperator.CF_BOCPD: frozenset({WriteTarget.CHANGE_CANDIDATE}),
    # The only long-term writer, and the only quarantine owner.
    HabitOperator.RGRC: frozenset({WriteTarget.QUARANTINE, WriteTarget.LONG_TERM_STATISTIC}),
    HabitOperator.CCRR: frozenset({WriteTarget.REGIME_ROUTE, WriteTarget.REGIME_LIBRARY}),
    HabitOperator.CIAV: frozenset({WriteTarget.VERIFICATION_REQUEST}),
    HabitOperator.EVIDENCE_CHANNEL: frozenset({WriteTarget.ACTOR_POSTERIOR}),
    HabitOperator.ACTION_READOUT: frozenset({WriteTarget.ACTION_DISTRIBUTION}),
}

#: Targets no operator may reach without passing through RGRC's quarantine.
#: Stated separately because it is the invariant, not a consequence of the
#: table: if the table is ever edited, this is the line that should have to be
#: edited too.
PROMOTION_GATED_TARGETS: frozenset[WriteTarget] = frozenset({WriteTarget.LONG_TERM_STATISTIC})


def authority_of(operator: HabitOperator) -> frozenset[WriteTarget]:
    """What this operator may write.  Unknown operators have no authority."""

    return OPERATOR_AUTHORITY.get(operator, frozenset())


class UnauthorizedOperatorWriteError(RuntimeError):
    """Raised when an operator writes outside its declared authority."""


class UnmatchedAuthorityError(RuntimeError):
    """Raised when arms in one comparison do not hold the same authority."""


@dataclass(frozen=True, slots=True)
class AuthorityViolation:
    """One refused write, kept so a run can report them all at once."""

    operator: HabitOperator
    target: WriteTarget
    reason: str
    detail: str = ""

    def message(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.operator.value} may not write {self.target.value}: {self.reason}{suffix}"


@dataclass(frozen=True, slots=True)
class AuthorityProfile:
    """The authority one arm holds, for matched-comparison checks."""

    arm_name: str
    operators: frozenset[HabitOperator]

    @property
    def targets(self) -> frozenset[WriteTarget]:
        result: set[WriteTarget] = set()
        for operator in self.operators:
            result |= authority_of(operator)
        return frozenset(result)

    def payload(self) -> dict[str, object]:
        return {
            "arm_name": self.arm_name,
            "operators": sorted(item.value for item in self.operators),
            "targets": sorted(item.value for item in self.targets),
            "authority_version": OPERATOR_AUTHORITY_VERSION,
        }


@dataclass
class OperatorAuthorityLedger:
    """Records every operator write and refuses the ones outside authority.

    ``strict`` raises on the first violation, which is what a production path
    wants.  ``strict=False`` collects them, which is what an audit of an
    existing run wants: one violation is a bug report, but the *set* of
    violations is the finding.
    """

    strict: bool = True
    _writes: list[tuple[HabitOperator, WriteTarget]] = field(default_factory=list)
    _violations: list[AuthorityViolation] = field(default_factory=list)
    _promoted: set[str] = field(default_factory=set)

    @property
    def writes(self) -> tuple[tuple[HabitOperator, WriteTarget], ...]:
        return tuple(self._writes)

    @property
    def violations(self) -> tuple[AuthorityViolation, ...]:
        return tuple(self._violations)

    @property
    def clean(self) -> bool:
        return not self._violations

    def record_promotion(self, candidate_id: str) -> None:
        """Note that RGRC promoted this candidate out of quarantine.

        Only a promoted candidate may reach a long-term statistic; the
        confirmation window is meaningless otherwise.
        """

        if not candidate_id.strip():
            raise ValueError("promotion requires a candidate id")
        self._promoted.add(candidate_id)

    def write(
        self,
        operator: HabitOperator,
        target: WriteTarget,
        *,
        candidate_id: str | None = None,
        detail: str = "",
    ) -> bool:
        """Attempt one write.  Returns ``True`` when it was allowed."""

        violation: AuthorityViolation | None = None
        if target not in authority_of(operator):
            violation = AuthorityViolation(
                operator=operator,
                target=target,
                reason="target is outside this operator's declared authority",
                detail=detail,
            )
        elif target in PROMOTION_GATED_TARGETS:
            if candidate_id is None:
                violation = AuthorityViolation(
                    operator=operator,
                    target=target,
                    reason="a promotion-gated write must cite the candidate it promotes",
                    detail=detail,
                )
            elif candidate_id not in self._promoted:
                violation = AuthorityViolation(
                    operator=operator,
                    target=target,
                    reason="candidate was never promoted out of quarantine",
                    detail=detail or candidate_id,
                )
        if violation is not None:
            self._violations.append(violation)
            if self.strict:
                raise UnauthorizedOperatorWriteError(violation.message())
            return False
        self._writes.append((operator, target))
        return True

    def summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for operator, target in self._writes:
            key = f"{operator.value}->{target.value}"
            counts[key] = counts.get(key, 0) + 1
        return {
            "authority_version": OPERATOR_AUTHORITY_VERSION,
            "writes": counts,
            "promotions": len(self._promoted),
            "violations": [item.message() for item in self._violations],
            "clean": self.clean,
        }


def assert_matched_authority(
    profiles: Sequence[AuthorityProfile],
    *,
    declared_difference: Iterable[WriteTarget] = (),
) -> None:
    """Refuse a comparison whose arms do not hold the same write authority.

    ``declared_difference`` names the targets a comparison is *about*.  An
    ablation that removes RGRC is a legitimate experiment, but it has to say so
    here, so that a reader of the result knows the arms were not matched and
    knows on which axis.
    """

    if len(profiles) < 2:
        raise ValueError("a matched-authority check needs at least two arms")
    declared = frozenset(declared_difference)
    reference = profiles[0]
    reference_targets = reference.targets
    for profile in profiles[1:]:
        difference = reference_targets ^ profile.targets
        undeclared = difference - declared
        if undeclared:
            names = ", ".join(sorted(item.value for item in undeclared))
            raise UnmatchedAuthorityError(
                f"arms {reference.arm_name!r} and {profile.arm_name!r} differ on undeclared "
                f"authority: {names}"
            )
