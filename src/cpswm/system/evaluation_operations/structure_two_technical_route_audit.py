"""Claim evaluation for the seven coupled Structure Two routes.

This is the third layer of the evidence pipeline:

1. declarations only locate artifacts;
2. :mod:`structure_two_artifact_verifier` opens and verifies them;
3. this evaluator decides which causal and benefit claims the verified evidence
   supports.

It intentionally has no API that accepts raw hashes or caller-supplied pass
booleans.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import AttestationAuthority, AttestationError, attested_payload

from .structure_two_artifact_verifier import VerifiedStructureTwoEvidenceBundle
from .structure_two_evidence_artifacts import (
    DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE,
    REQUIRED_MATCHED_BASELINES,
    CrossModuleCouplingKind,
    MatchedBaselineKind,
    StructureTwoRoute,
)


class RouteEvidenceStatus(StrEnum):
    IMPLEMENTED_CAPABILITY = "implemented_capability"
    PARTIAL_METHOD = "partial_method"
    SPECIFICATION_ONLY = "specification_only"
    MATCHED_BASELINE_BLOCKED = "matched_baseline_blocked"
    ACTION_UTILITY_BLOCKED = "action_utility_blocked"


class StructureTwoRouteStatus(ContractModel):
    """Descriptive progress only; it cannot unlock a paper claim."""

    route: StructureTwoRoute
    status: RouteEvidenceStatus
    established: tuple[str, ...] = Field(min_length=1)
    unresolved: tuple[str, ...] = Field(min_length=1)


class StructureTwoClaimDecision(ContractModel):
    experiment_id: str = Field(min_length=1)
    causal_coupling_count: int = Field(ge=0)
    positive_benefit_coupling_count: int = Field(ge=0)
    baseline_benefit_count: int = Field(ge=0)
    causal_coupling_established: bool
    paper_benefit_claim_allowed: bool
    missing_causal_requirements: tuple[str, ...]
    missing_benefit_requirements: tuple[str, ...]


class StructureTwoClaimGateEvaluator:
    """Evaluate only an authentic bundle produced by the trusted verifier."""

    def __init__(self, *, authority: AttestationAuthority) -> None:
        self._authority = authority

    def evaluate(
        self,
        bundle: VerifiedStructureTwoEvidenceBundle,
    ) -> StructureTwoClaimDecision:
        try:
            self._authority.verify(
                DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE,
                attested_payload(bundle),
                bundle.attestation,
            )
        except AttestationError as error:
            raise ValueError("claim evaluator rejected an unauthentic verified bundle") from error

        verified_baselines = {item.baseline for item in bundle.baselines}
        missing_baselines = REQUIRED_MATCHED_BASELINES - verified_baselines
        causal_couplings = tuple(
            item for item in bundle.couplings if item.causal_coupling_established
        )
        benefit_couplings = tuple(
            item for item in bundle.couplings if item.positive_benefit_established
        )
        baseline_benefits = tuple(item for item in bundle.baselines if item.benefit_claim_passed)

        causal_missing: list[str] = []
        if missing_baselines:
            causal_missing.extend(
                f"verified_matched_baseline:{baseline.value}"
                for baseline in sorted(missing_baselines, key=str)
            )
        if not bundle.factorial.powered_factorial_established:
            causal_missing.append("verified_powered_factorial_design")
        if not bundle.noninterference_passed:
            causal_missing.append("verified_epistemic_noninterference")
        if not bundle.full_rerun_equivalent:
            causal_missing.append("verified_full_rerun_equivalence")
        if not bundle.numerical_downdate_stable:
            causal_missing.append("verified_numerical_downdate_stability")
        if len(causal_couplings) < 3:
            causal_missing.append("three_verified_causal_couplings")

        benefit_missing = list(causal_missing)
        failed_baseline_benefits = {
            item.baseline for item in bundle.baselines if not item.benefit_claim_passed
        }
        benefit_missing.extend(
            f"baseline_benefit:{baseline.value}"
            for baseline in sorted(failed_baseline_benefits, key=str)
        )
        if len(benefit_couplings) < 3:
            benefit_missing.append("three_positive_or_noninferior_utility_couplings")
        if not bundle.candidate_on_valid_pareto_frontier:
            benefit_missing.append("candidate_on_verified_contamination_recovery_pareto_frontier")

        return StructureTwoClaimDecision(
            experiment_id=bundle.experiment_id,
            causal_coupling_count=len(causal_couplings),
            positive_benefit_coupling_count=len(benefit_couplings),
            baseline_benefit_count=len(baseline_benefits),
            causal_coupling_established=len(causal_missing) == 0,
            paper_benefit_claim_allowed=len(benefit_missing) == 0,
            missing_causal_requirements=tuple(causal_missing),
            missing_benefit_requirements=tuple(benefit_missing),
        )


def current_structure_two_route_statuses() -> tuple[StructureTwoRouteStatus, ...]:
    """Current honest audit: implementation progress is not claim evidence."""

    return (
        StructureTwoRouteStatus(
            route=StructureTwoRoute.OPCEU,
            status=RouteEvidenceStatus.PARTIAL_METHOD,
            established=("propensity weighting and support diagnostics",),
            unresolved=(
                "passive-MNAR identification requires measured covariates or intervention",
            ),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.CHEH_ORRER,
            status=RouteEvidenceStatus.ACTION_UTILITY_BLOCKED,
            established=("open-world reversible multi-hypothesis event revision",),
            unresolved=("matched AMG ties capability and wins current action benchmark",),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.PCHMP,
            status=RouteEvidenceStatus.MATCHED_BASELINE_BLOCKED,
            established=(
                "permutation, canonical dedup, consumption, and cluster sensitivity contracts",
            ),
            unresolved=("independently tuned ordinary heterogeneous GNN comparison",),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.CF_BOCPD,
            status=RouteEvidenceStatus.MATCHED_BASELINE_BLOCKED,
            established=("joint cause posterior and cause-specific reset",),
            unresolved=("powered factorial test versus BOCPDMS and switching HMM",),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.RGRC,
            status=RouteEvidenceStatus.ACTION_UTILITY_BLOCKED,
            established=("append-only reversible ledger, numerical audit, and full-rerun receipt",),
            unresolved=("verified contamination-recovery Pareto and utility advantage",),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.CCRR,
            status=RouteEvidenceStatus.PARTIAL_METHOD,
            established=("normalized stay/create/reactivate/unresolved competition",),
            unresolved=("powered recovery accuracy and ledger-committed write benefit",),
        ),
        StructureTwoRouteStatus(
            route=StructureTwoRoute.CIAV,
            status=RouteEvidenceStatus.PARTIAL_METHOD,
            established=("cause-memory-task decision value, privacy gate, baselines, and OPE",),
            unresolved=("powered embodied outcome model and off-policy action-utility result",),
        ),
    )


__all__ = [
    "REQUIRED_MATCHED_BASELINES",
    "CrossModuleCouplingKind",
    "MatchedBaselineKind",
    "RouteEvidenceStatus",
    "StructureTwoClaimDecision",
    "StructureTwoClaimGateEvaluator",
    "StructureTwoRoute",
    "StructureTwoRouteStatus",
    "current_structure_two_route_statuses",
]
