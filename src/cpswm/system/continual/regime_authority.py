"""Frozen authority topology for CF-BOCPD, RGRC, CCRR, and the ledger.

The two proposal orders remain experimental alternatives.  They converge on
one invariant: only the reversible ledger may commit or retract long-term
statistics or the active regime pointer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RegimeComponent(StrEnum):
    CF_BOCPD = "cf_bocpd"
    RGRC = "rgrc"
    CCRR = "ccrr"
    REVERSIBLE_LEDGER = "reversible_ledger"


class RegimeAuthority(StrEnum):
    CHANGE_AND_CAUSE_POSTERIOR = "change_and_cause_posterior"
    EVIDENCE_ADMISSIBILITY_AND_REVERSAL = "evidence_admissibility_and_reversal"
    REGIME_DESTINATION_PROPOSAL = "regime_destination_proposal"
    FINAL_REGIME_AND_STATISTIC_WRITE = "final_regime_and_statistic_write"


class RegimeProposalOrder(StrEnum):
    RGRC_THEN_CCRR = "rgrc_then_ccrr"
    CCRR_THEN_RGRC = "ccrr_then_rgrc"


AUTHORITY_OWNER = {
    RegimeAuthority.CHANGE_AND_CAUSE_POSTERIOR: RegimeComponent.CF_BOCPD,
    RegimeAuthority.EVIDENCE_ADMISSIBILITY_AND_REVERSAL: RegimeComponent.RGRC,
    RegimeAuthority.REGIME_DESTINATION_PROPOSAL: RegimeComponent.CCRR,
    RegimeAuthority.FINAL_REGIME_AND_STATISTIC_WRITE: RegimeComponent.REVERSIBLE_LEDGER,
}


@dataclass(frozen=True, slots=True)
class RegimeAuthorityTopology:
    """One proposal ordering with a single final write authority."""

    proposal_order: RegimeProposalOrder
    final_writer: RegimeComponent = RegimeComponent.REVERSIBLE_LEDGER

    def __post_init__(self) -> None:
        if self.final_writer is not RegimeComponent.REVERSIBLE_LEDGER:
            raise ValueError("only the reversible ledger has final regime write authority")

    @property
    def proposal_sequence(self) -> tuple[RegimeComponent, ...]:
        middle = (
            (RegimeComponent.RGRC, RegimeComponent.CCRR)
            if self.proposal_order is RegimeProposalOrder.RGRC_THEN_CCRR
            else (RegimeComponent.CCRR, RegimeComponent.RGRC)
        )
        return (RegimeComponent.CF_BOCPD, *middle, RegimeComponent.REVERSIBLE_LEDGER)


__all__ = [
    "AUTHORITY_OWNER",
    "RegimeAuthority",
    "RegimeAuthorityTopology",
    "RegimeComponent",
    "RegimeProposalOrder",
]
