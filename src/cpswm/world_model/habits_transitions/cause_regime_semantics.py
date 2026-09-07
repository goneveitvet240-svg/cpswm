"""Canonical CF-BOCPD x CCRR semantics for ``(C, r, Z)``.

CF-BOCPD supplies ``p(C, r | evidence)``.  CCRR supplies a conditional regime
transition ``p(Z | C, r, context, library)`` and must not consume the raw
evidence as another likelihood.  Identity association remains a separate
particle variable, but an identity-switch probability is lifted into the
change-cause axis explicitly instead of being an untracked side channel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from cpswm.system.reproducibility import content_sha256

from .context_conditioned_regime import (
    ContextConditionedRegimeReactivator,
    RegimeDecision,
    RegimeDecisionKind,
    _snapshot_payload,
)
from .joint_cause_bocpd import JointCauseSnapshot, RunLengthClock

SEMANTICS_VERSION: Final = "cf-bocpd-ccrr-c-r-z@0.2"


class UnifiedChangeCause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    IDENTITY = "identity"
    HABIT = "habit"
    NOISE = "noise"


@dataclass(frozen=True, slots=True)
class CauseRunDestinationMass:
    cause: UnifiedChangeCause
    run_length: int
    destination: RegimeDecisionKind
    destination_regime_id: str | None
    probability: float

    def __post_init__(self) -> None:
        if self.run_length < 0:
            raise ValueError("run length must be non-negative")
        if not math.isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ValueError("joint cause/run/destination mass must lie in [0, 1]")


@dataclass(frozen=True, slots=True)
class JointCauseRegimeTransition:
    semantics_version: str
    snapshot_sha256: str
    ccrr_model_version: str
    run_length_clock: RunLengthClock
    opportunity_index: int
    identity_switch_probability: float
    masses: tuple[CauseRunDestinationMass, ...]

    def __post_init__(self) -> None:
        if self.semantics_version != SEMANTICS_VERSION:
            raise ValueError("unknown CF-BOCPD/CCRR semantics version")
        if self.opportunity_index < 0:
            raise ValueError("opportunity index must be non-negative")
        if not 0.0 <= self.identity_switch_probability <= 1.0:
            raise ValueError("identity switch probability must lie in [0, 1]")
        if not self.masses or not math.isclose(
            sum(item.probability for item in self.masses),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("joint cause/run/destination masses must sum to one")

    def cause_marginal(self) -> dict[UnifiedChangeCause, float]:
        result = dict.fromkeys(UnifiedChangeCause, 0.0)
        for item in self.masses:
            result[item.cause] += item.probability
        return result

    def destination_marginal(self) -> dict[RegimeDecisionKind, float]:
        result = dict.fromkeys(RegimeDecisionKind, 0.0)
        for item in self.masses:
            result[item.destination] += item.probability
        return result


def _destination_id(decision: RegimeDecision, kind: RegimeDecisionKind) -> str | None:
    if kind is RegimeDecisionKind.STAY:
        return decision.active_regime_id
    if kind is RegimeDecisionKind.CREATE:
        return decision.created_regime_id
    if kind is RegimeDecisionKind.REACTIVATE:
        return decision.reactivated_regime_id
    return None


def _cause_run_conditioned_destination(
    cause: UnifiedChangeCause,
    run_length: int,
    decision: RegimeDecision,
) -> dict[RegimeDecisionKind, float]:
    probabilities = dict(decision.non_identity_decision_score)
    if cause is not UnifiedChangeCause.HABIT:
        displaced = (
            probabilities[RegimeDecisionKind.CREATE] + probabilities[RegimeDecisionKind.REACTIVATE]
        )
        probabilities[RegimeDecisionKind.CREATE] = 0.0
        probabilities[RegimeDecisionKind.REACTIVATE] = 0.0
        probabilities[RegimeDecisionKind.UNRESOLVED] += displaced
    # r is a real conditioning variable: persistent prefixes transfer a bounded
    # part of unresolved mass to STAY. This is a frozen transition potential,
    # not an observation likelihood or a calibration claim.
    persistence = run_length / (run_length + 5.0) if run_length else 0.0
    shift = min(probabilities[RegimeDecisionKind.UNRESOLVED], 0.15 * persistence)
    probabilities[RegimeDecisionKind.UNRESOLVED] -= shift
    probabilities[RegimeDecisionKind.STAY] += shift
    return probabilities


def compose_joint_cause_regime_transition(
    snapshot: JointCauseSnapshot,
    decision: RegimeDecision,
    *,
    verifier: ContextConditionedRegimeReactivator,
) -> JointCauseRegimeTransition:
    """Compose ``p(C,r) p(Z|C,r,context,library)`` without a second likelihood."""

    verifier.verify_decision(decision)
    if decision.scoring_envelope.snapshot_hash != content_sha256(_snapshot_payload(snapshot)):
        raise ValueError("CCRR decision and CF snapshot content hashes differ")
    identity_probability = decision.scoring_envelope.identity_switch_probability
    if decision.scoring_envelope.run_length_clock is not snapshot.run_length_clock:
        raise ValueError("CCRR decision and CF snapshot use different run-length clocks")
    if decision.scoring_envelope.opportunity_index != snapshot.opportunity_index:
        raise ValueError("CCRR decision and CF snapshot use different opportunities")
    entries: list[CauseRunDestinationMass] = []
    for (run_length, cause), probability in sorted(
        snapshot.joint_run_length_cause_posterior.items(),
        key=lambda item: (item[0][0], item[0][1].value),
    ):
        unified_cause = UnifiedChangeCause(cause.value)
        destination = _cause_run_conditioned_destination(unified_cause, run_length, decision)
        for kind in RegimeDecisionKind:
            mass = (1.0 - identity_probability) * probability * destination[kind]
            if mass > 0.0:
                entries.append(
                    CauseRunDestinationMass(
                        cause=unified_cause,
                        run_length=run_length,
                        destination=kind,
                        destination_regime_id=_destination_id(decision, kind),
                        probability=mass,
                    )
                )
    if identity_probability > 0.0:
        identity_destination = _cause_run_conditioned_destination(
            UnifiedChangeCause.IDENTITY, 0, decision
        )
        for kind in RegimeDecisionKind:
            mass = identity_probability * identity_destination[kind]
            if mass > 0.0:
                entries.append(
                    CauseRunDestinationMass(
                        cause=UnifiedChangeCause.IDENTITY,
                        run_length=0,
                        destination=kind,
                        destination_regime_id=_destination_id(decision, kind),
                        probability=mass,
                    )
                )
    snapshot_sha256 = content_sha256(
        {
            "timestamp": snapshot.timestamp,
            "opportunity_index": snapshot.opportunity_index,
            "clock": snapshot.run_length_clock.value,
            "joint": sorted(
                (
                    run_length,
                    cause.value,
                    probability,
                )
                for (run_length, cause), probability in (
                    snapshot.joint_run_length_cause_posterior.items()
                )
            ),
        }
    )
    return JointCauseRegimeTransition(
        semantics_version=SEMANTICS_VERSION,
        snapshot_sha256=snapshot_sha256,
        ccrr_model_version=decision.model_version,
        run_length_clock=snapshot.run_length_clock,
        opportunity_index=snapshot.opportunity_index,
        identity_switch_probability=identity_probability,
        masses=tuple(entries),
    )


__all__ = [
    "SEMANTICS_VERSION",
    "CauseRunDestinationMass",
    "JointCauseRegimeTransition",
    "UnifiedChangeCause",
    "compose_joint_cause_regime_transition",
]
