"""The contribution gate must refuse claims the evidence does not support.

Written against the failure mode it exists to prevent: a deadline arrives, the
七算子 all have code, and "implemented" quietly becomes "contribution".
"""

from __future__ import annotations

import pytest

from cpswm.system.progress_ledger import (
    CONTRIBUTION_THRESHOLD,
    CURRENT_STATES,
    SUPERIORITY_THRESHOLD,
    ContributionClaimError,
    InnovationState,
    Operator,
    assert_claim_text,
    assert_contribution_list,
    blocked_operators,
    ledger_summary,
    may_be_listed_as_contribution,
    may_claim_superiority,
    state_of,
)
from cpswm.system.progress_ledger.innovation_ledger import STATE_ORDER, STATE_RANK


def test_every_operator_has_a_declared_state() -> None:
    assert set(CURRENT_STATES) == set(Operator)
    assert all(state in STATE_ORDER for state in CURRENT_STATES.values())


def test_the_state_machine_is_the_charter_order() -> None:
    assert STATE_ORDER[0] is InnovationState.INNOVATION_UNRESOLVED
    assert STATE_ORDER[-1] is InnovationState.PAPER_CONTRIBUTION_SUPPORTED
    assert STATE_RANK[CONTRIBUTION_THRESHOLD] < STATE_RANK[SUPERIORITY_THRESHOLD]


def test_no_operator_may_currently_be_listed_as_a_contribution() -> None:
    """The honest current state, pinned so that changing it is deliberate.

    If this test starts failing, an operator's state was raised.  That is
    allowed -- but only together with the measured comparison that earned it.
    """

    assert set(blocked_operators()) == set(Operator)
    for operator in Operator:
        assert not may_be_listed_as_contribution(operator), operator.value
        assert not may_claim_superiority(operator), operator.value


@pytest.mark.parametrize("operator", list(Operator))
def test_listing_an_under_evidenced_operator_raises(operator: Operator) -> None:
    with pytest.raises(ContributionClaimError) as error:
        assert_contribution_list([operator])
    assert operator.value in str(error.value)
    assert state_of(operator).value in str(error.value)


def test_the_specification_only_operators_are_named_explicitly() -> None:
    """OPCEU / PCHMP / CCRR are specifications, not implementations."""

    for operator in (Operator.OPCEU, Operator.PCHMP, Operator.CCRR):
        assert state_of(operator) is InnovationState.METHOD_SPECIFIED


@pytest.mark.parametrize(
    "text",
    [
        "本方法首次联合建模隐藏事件与人物责任",
        "our observation-process-aware update is state of the art",
        "we are the first to learn household relocation habits",
        "世界上没有人研究多人非平稳家庭习惯",
    ],
)
def test_priority_wording_is_refused(text: str) -> None:
    with pytest.raises(ContributionClaimError):
        assert_claim_text(text, [Operator.CF_BOCPD])


def test_a_hedge_elsewhere_does_not_license_a_priority_phrase() -> None:
    """Judge the effect of the wording, not the presence of a softener."""

    with pytest.raises(ContributionClaimError):
        assert_claim_text(
            "as a candidate contribution we are the first to propose cause-factorized detection",
            [Operator.CF_BOCPD],
        )


def test_hedged_wording_without_a_priority_phrase_is_allowed() -> None:
    assert_claim_text("我们拟提出一个候选创新 - 原因因子化的在线变化点检测")


def test_an_empty_contribution_list_is_always_allowed() -> None:
    assert_contribution_list([])


def test_the_summary_reports_state_and_permission_for_every_operator() -> None:
    summary = ledger_summary()
    assert set(summary) == {operator.value for operator in Operator}
    for entry in summary.values():
        assert entry["state"] in {state.value for state in InnovationState}
        assert entry["may_be_listed_as_contribution"] is False
        assert entry["may_claim_superiority"] is False
