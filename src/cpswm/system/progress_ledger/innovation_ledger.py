"""Executable gate on what the seven structure-two operators may claim.

The unified-innovation charter already states the rule in prose: an operator may
not appear in a paper's contribution list until it reaches ``direct baseline
passed``, and until then the language must be "候选创新 / 工作方法 / 拟提出".
Prose does not survive a deadline.  This module makes the rule a function that
raises.

The state machine is the charter's, unchanged::

    innovation unresolved
    -> method specified
    -> closest prior art checked
    -> implementation complete
    -> direct baseline passed
    -> system ablation passed
    -> embodied utility passed
    -> external validity passed
    -> paper contribution supported

Two separate thresholds matter and are easy to conflate:

* ``CONTRIBUTION_THRESHOLD`` -- the point at which an operator may be listed as a
  contribution at all.  Below it the operator is still real work; it is simply
  not yet evidence.
* ``SUPERIORITY_THRESHOLD`` -- the point at which a comparative claim
  ("outperforms", "首次", "state of the art") is permitted.

Declared states live in :data:`CURRENT_STATES` and are updated by hand from
measured evidence.  Nothing here infers a state from code existing: an operator
with a full implementation and no matched comparison is exactly
``implementation complete``, which is the situation this module exists to keep
visible.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum


class InnovationState(StrEnum):
    INNOVATION_UNRESOLVED = "innovation unresolved"
    METHOD_SPECIFIED = "method specified"
    CLOSEST_PRIOR_ART_CHECKED = "closest prior art checked"
    IMPLEMENTATION_COMPLETE = "implementation complete"
    DIRECT_BASELINE_PASSED = "direct baseline passed"
    SYSTEM_ABLATION_PASSED = "system ablation passed"
    EMBODIED_UTILITY_PASSED = "embodied utility passed"
    EXTERNAL_VALIDITY_PASSED = "external validity passed"
    PAPER_CONTRIBUTION_SUPPORTED = "paper contribution supported"


STATE_ORDER: tuple[InnovationState, ...] = (
    InnovationState.INNOVATION_UNRESOLVED,
    InnovationState.METHOD_SPECIFIED,
    InnovationState.CLOSEST_PRIOR_ART_CHECKED,
    InnovationState.IMPLEMENTATION_COMPLETE,
    InnovationState.DIRECT_BASELINE_PASSED,
    InnovationState.SYSTEM_ABLATION_PASSED,
    InnovationState.EMBODIED_UTILITY_PASSED,
    InnovationState.EXTERNAL_VALIDITY_PASSED,
    InnovationState.PAPER_CONTRIBUTION_SUPPORTED,
)

STATE_RANK: Mapping[InnovationState, int] = {
    state: index for index, state in enumerate(STATE_ORDER)
}

#: An operator below this may not be listed as a paper contribution.
CONTRIBUTION_THRESHOLD = InnovationState.DIRECT_BASELINE_PASSED

#: A comparative or priority claim needs more than a direct comparison.
SUPERIORITY_THRESHOLD = InnovationState.EXTERNAL_VALIDITY_PASSED


class Operator(StrEnum):
    OPCEU = "OPCEU"
    CHEH = "CHEH"
    PCHMP = "PCHMP"
    CF_BOCPD = "CF-BOCPD"
    RGRC = "RGRC"
    CCRR = "CCRR"
    CIAV = "CIAV"


#: Declared, evidence-backed states.  Every entry names what would move it.
CURRENT_STATES: Mapping[Operator, InnovationState] = {
    # No observation-process model exists; the propensity corrector is an input
    # weight, not a learned observation-generation model.
    Operator.OPCEU: InnovationState.METHOD_SPECIFIED,
    # ORRER implements branch/revise/retract/rebuild, but the matched open-world
    # AMG control reached the same coverage on the same evidence.
    Operator.CHEH: InnovationState.IMPLEMENTATION_COMPLETE,
    # Actor-responsibility evidence interfaces exist; the provenance-constrained
    # message-passing algorithm itself does not.
    Operator.PCHMP: InnovationState.METHOD_SPECIFIED,
    # Joint p(r_t, C_t) with a cause-specific reset matrix is implemented, and
    # the four-arm matched comparison has now run.  It did not win: see
    # ``project_one_shift_four_arm``.
    Operator.CF_BOCPD: InnovationState.IMPLEMENTATION_COMPLETE,
    # Hybrid reversible sufficient statistics are implemented; the action-level
    # matched comparison against a full-rerun AMG control has not been won.
    Operator.RGRC: InnovationState.IMPLEMENTATION_COMPLETE,
    Operator.CCRR: InnovationState.METHOD_SPECIFIED,
    # Concurrent map/task core exists; no matched control has been run.
    Operator.CIAV: InnovationState.IMPLEMENTATION_COMPLETE,
}

#: Phrases that assert priority or superiority.  Checked case-insensitively.
FORBIDDEN_CLAIM_PHRASES: tuple[str, ...] = (
    "首次",
    "state of the art",
    "state-of-the-art",
    "outperforms all",
    "first to",
    "no prior work",
    "世界上没有",
)

#: Hedged wording that is always allowed for work below the threshold.
PERMITTED_HEDGES: tuple[str, ...] = ("候选创新", "工作方法", "拟提出", "candidate", "proposed")


class ContributionClaimError(RuntimeError):
    """Raised when a claim outruns the evidence behind it."""


def state_of(operator: Operator) -> InnovationState:
    return CURRENT_STATES[operator]


def may_be_listed_as_contribution(operator: Operator) -> bool:
    return STATE_RANK[state_of(operator)] >= STATE_RANK[CONTRIBUTION_THRESHOLD]


def may_claim_superiority(operator: Operator) -> bool:
    return STATE_RANK[state_of(operator)] >= STATE_RANK[SUPERIORITY_THRESHOLD]


def blocked_operators() -> tuple[Operator, ...]:
    """Operators that currently may not appear in a contribution list."""

    return tuple(operator for operator in Operator if not may_be_listed_as_contribution(operator))


def assert_contribution_list(operators: Iterable[Operator]) -> None:
    """Refuse a contribution list containing an under-evidenced operator."""

    offenders = [
        (operator, state_of(operator))
        for operator in operators
        if not may_be_listed_as_contribution(operator)
    ]
    if offenders:
        detail = "; ".join(
            f"{operator.value} is at '{state.value}', below '{CONTRIBUTION_THRESHOLD.value}'"
            for operator, state in offenders
        )
        raise ContributionClaimError(
            f"contribution list is not supported by the innovation ledger: {detail}"
        )


def assert_claim_text(text: str, operators: Iterable[Operator] = ()) -> None:
    """Refuse priority/superiority wording that the ledger does not support.

    The check is on the *effect* of the wording, not on a single vocabulary: a
    hedge elsewhere in the sentence does not license a "首次" in it.
    """

    lowered = text.lower()
    found = [phrase for phrase in FORBIDDEN_CLAIM_PHRASES if phrase.lower() in lowered]
    if found:
        unsupported = [operator for operator in operators if not may_claim_superiority(operator)]
        if unsupported or not tuple(operators):
            names = ", ".join(operator.value for operator in unsupported) or "any operator"
            raise ContributionClaimError(
                f"claim text uses {found!r}, which requires "
                f"'{SUPERIORITY_THRESHOLD.value}' for {names}"
            )
    assert_contribution_list(operators)


def ledger_summary() -> dict[str, dict[str, object]]:
    """Reporting view: state, and what each operator is currently allowed to say."""

    return {
        operator.value: {
            "state": state_of(operator).value,
            "may_be_listed_as_contribution": may_be_listed_as_contribution(operator),
            "may_claim_superiority": may_claim_superiority(operator),
        }
        for operator in Operator
    }
