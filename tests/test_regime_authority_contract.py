from __future__ import annotations

import pytest

from cpswm.system.continual import (
    AUTHORITY_OWNER,
    RegimeAuthority,
    RegimeAuthorityTopology,
    RegimeComponent,
    RegimeProposalOrder,
)


def test_every_regime_authority_has_exactly_one_owner() -> None:
    assert set(AUTHORITY_OWNER) == set(RegimeAuthority)
    assert len(set(AUTHORITY_OWNER.values())) == len(RegimeAuthority)
    assert (
        AUTHORITY_OWNER[RegimeAuthority.FINAL_REGIME_AND_STATISTIC_WRITE]
        is RegimeComponent.REVERSIBLE_LEDGER
    )


@pytest.mark.parametrize("order", list(RegimeProposalOrder))
def test_both_proposal_orders_end_at_the_only_final_writer(order: RegimeProposalOrder) -> None:
    topology = RegimeAuthorityTopology(proposal_order=order)
    assert topology.proposal_sequence[0] is RegimeComponent.CF_BOCPD
    assert topology.proposal_sequence[-1] is RegimeComponent.REVERSIBLE_LEDGER
    assert set(topology.proposal_sequence[1:3]) == {
        RegimeComponent.RGRC,
        RegimeComponent.CCRR,
    }


def test_ccrr_or_rgrc_cannot_be_declared_final_writer() -> None:
    with pytest.raises(ValueError, match="only the reversible ledger"):
        RegimeAuthorityTopology(
            proposal_order=RegimeProposalOrder.CCRR_THEN_RGRC,
            final_writer=RegimeComponent.CCRR,
        )
