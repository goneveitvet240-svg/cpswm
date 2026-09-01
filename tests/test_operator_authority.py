"""RQ9 权限矩阵: CF-BOCPD / CCRR / RGRC 各自能写什么, 由测试而非文档保证.

RQ9 非平稳阶段 -- 正确 -- 接入前缺口: 明确 CF-BOCPD/RGRC/CCRR 权限, 补强公平基线.
"""

from __future__ import annotations

import pytest

from cpswm.system.continual.operator_authority import (
    OPERATOR_AUTHORITY,
    PROMOTION_GATED_TARGETS,
    AuthorityProfile,
    HabitOperator,
    OperatorAuthorityLedger,
    UnauthorizedOperatorWriteError,
    UnmatchedAuthorityError,
    WriteTarget,
    assert_matched_authority,
)

# ---------------------------------------------------------------------------
# The three rows the audit named
# ---------------------------------------------------------------------------


def test_cf_bocpd_may_only_propose_a_change_candidate() -> None:
    """ "仅提出变化候选" -- one target, and it is a proposal.

    Fails if the detector is ever given write access to memory, which would
    make "the detector fired" and "the habit moved" the same event and would
    make the confirmation window decorative.
    """

    assert OPERATOR_AUTHORITY[HabitOperator.CF_BOCPD] == frozenset({WriteTarget.CHANGE_CANDIDATE})


def test_ccrr_routes_regimes_but_cannot_write_memory() -> None:
    """Choosing which regime an event belongs to is not deciding it is admissible."""

    authority = OPERATOR_AUTHORITY[HabitOperator.CCRR]
    assert authority == frozenset({WriteTarget.REGIME_ROUTE, WriteTarget.REGIME_LIBRARY})
    assert WriteTarget.LONG_TERM_STATISTIC not in authority


def test_rgrc_is_the_only_long_term_writer() -> None:
    """One place to look when 访客污染 happens.

    Fails if a second operator gains long-term write access, at which point the
    contamination audit has to become a search.
    """

    writers = {
        operator
        for operator, targets in OPERATOR_AUTHORITY.items()
        if WriteTarget.LONG_TERM_STATISTIC in targets
    }
    assert writers == {HabitOperator.RGRC}


def test_no_operator_may_edit_an_actor_posterior_it_is_judged_on() -> None:
    """RQ8 carried into the authority matrix.

    ``PCHMP`` is the exception and is meant to be: producing the posterior *is*
    its job.  Everything that consumes the posterior is barred.
    """

    editors = {
        operator
        for operator, targets in OPERATOR_AUTHORITY.items()
        if WriteTarget.ACTOR_POSTERIOR in targets
    }
    assert editors == {HabitOperator.PCHMP, HabitOperator.EVIDENCE_CHANNEL}
    for operator in (HabitOperator.CF_BOCPD, HabitOperator.CCRR, HabitOperator.RGRC):
        assert WriteTarget.ACTOR_POSTERIOR not in OPERATOR_AUTHORITY[operator]


def test_every_operator_has_an_explicit_row() -> None:
    """An operator with no row has no authority, which must be deliberate."""

    assert set(OPERATOR_AUTHORITY) == set(HabitOperator)


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def test_a_detector_write_to_memory_raises() -> None:
    ledger = OperatorAuthorityLedger()
    with pytest.raises(UnauthorizedOperatorWriteError, match="outside this operator"):
        ledger.write(
            HabitOperator.CF_BOCPD,
            WriteTarget.LONG_TERM_STATISTIC,
            candidate_id="c1",
        )


def test_a_long_term_write_requires_a_promotion_first() -> None:
    """The confirmation window, enforced rather than assumed.

    Fails if RGRC can write a count for a candidate still in quarantine, which
    is exactly the "one anomaly permanently contaminates memory" failure the
    OAM-PHM floor measured on ``last-seen``.
    """

    ledger = OperatorAuthorityLedger()
    with pytest.raises(UnauthorizedOperatorWriteError, match="never promoted"):
        ledger.write(HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c1")

    ledger.record_promotion("c1")
    assert ledger.write(HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c1")
    # The refused attempt stays on the record.  ``clean`` reports whether any
    # write was ever refused, not whether the last one succeeded -- an audit
    # that forgets the refusal cannot tell a well-behaved run from one that
    # was stopped mid-way.
    assert not ledger.clean
    assert len(ledger.violations) == 1
    assert ledger.writes == ((HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC),)


def test_a_long_term_write_must_name_the_candidate_it_promotes() -> None:
    ledger = OperatorAuthorityLedger()
    ledger.record_promotion("c1")
    with pytest.raises(UnauthorizedOperatorWriteError, match="must cite the candidate"):
        ledger.write(HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC)


def test_promotion_gating_covers_exactly_the_memory_targets() -> None:
    assert frozenset({WriteTarget.LONG_TERM_STATISTIC}) == PROMOTION_GATED_TARGETS


def test_non_strict_mode_collects_the_whole_violation_set() -> None:
    """One violation is a bug report; the set is the finding."""

    ledger = OperatorAuthorityLedger(strict=False)
    ledger.write(HabitOperator.CF_BOCPD, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c1")
    ledger.write(HabitOperator.CCRR, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c1")
    ledger.write(HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c2")
    assert len(ledger.violations) == 3
    assert not ledger.clean
    assert all("may not write" in item.message() for item in ledger.violations)


def test_a_legal_pipeline_run_is_clean() -> None:
    """The intended order: propose, quarantine, route, promote, write."""

    ledger = OperatorAuthorityLedger()
    assert ledger.write(HabitOperator.CF_BOCPD, WriteTarget.CHANGE_CANDIDATE)
    assert ledger.write(HabitOperator.RGRC, WriteTarget.QUARANTINE)
    assert ledger.write(HabitOperator.CCRR, WriteTarget.REGIME_ROUTE)
    ledger.record_promotion("c1")
    assert ledger.write(HabitOperator.RGRC, WriteTarget.LONG_TERM_STATISTIC, candidate_id="c1")
    assert ledger.clean
    assert ledger.summary()["promotions"] == 1


def test_summary_names_every_edge_that_was_taken() -> None:
    ledger = OperatorAuthorityLedger()
    ledger.write(HabitOperator.CF_BOCPD, WriteTarget.CHANGE_CANDIDATE)
    ledger.write(HabitOperator.CF_BOCPD, WriteTarget.CHANGE_CANDIDATE)
    assert ledger.summary()["writes"] == {"cf_bocpd->change_candidate": 2}


def test_an_unknown_operator_has_no_authority() -> None:
    ledger = OperatorAuthorityLedger(strict=False)
    assert not ledger.write(HabitOperator.CIAV, WriteTarget.LONG_TERM_STATISTIC)


# ---------------------------------------------------------------------------
# 补强公平基线: matched authority
# ---------------------------------------------------------------------------


def _profile(name: str, *operators: HabitOperator) -> AuthorityProfile:
    return AuthorityProfile(arm_name=name, operators=frozenset(operators))


def test_arms_with_different_authority_cannot_be_compared_silently() -> None:
    """An arm that can promote and one that cannot are running different experiments.

    Fails if the check is dropped, which is the authority-shaped version of the
    information asymmetry RQ8 found in the actor channel.
    """

    candidate = _profile("full", HabitOperator.CF_BOCPD, HabitOperator.CCRR, HabitOperator.RGRC)
    baseline = _profile("categorical_bocpd", HabitOperator.CF_BOCPD)
    with pytest.raises(UnmatchedAuthorityError, match="undeclared authority"):
        assert_matched_authority([candidate, baseline])


def test_a_declared_difference_is_a_legitimate_ablation() -> None:
    candidate = _profile("full", HabitOperator.CF_BOCPD, HabitOperator.CCRR, HabitOperator.RGRC)
    no_rgrc = _profile("no_rgrc", HabitOperator.CF_BOCPD, HabitOperator.CCRR)
    assert_matched_authority(
        [candidate, no_rgrc],
        declared_difference=(WriteTarget.QUARANTINE, WriteTarget.LONG_TERM_STATISTIC),
    )


def test_matched_arms_pass() -> None:
    left = _profile("full", HabitOperator.CF_BOCPD, HabitOperator.RGRC)
    right = _profile("shuffled", HabitOperator.CF_BOCPD, HabitOperator.RGRC)
    assert_matched_authority([left, right])


def test_a_comparison_needs_at_least_two_arms() -> None:
    with pytest.raises(ValueError, match="at least two arms"):
        assert_matched_authority([_profile("only", HabitOperator.RGRC)])


def test_profile_payload_is_deterministic_and_versioned() -> None:
    profile = _profile("full", HabitOperator.RGRC, HabitOperator.CCRR)
    payload = profile.payload()
    assert payload["operators"] == ["ccrr", "rgrc"]
    assert payload["authority_version"].startswith("operator-authority@")
    assert profile.payload() == _profile("full", HabitOperator.CCRR, HabitOperator.RGRC).payload()
