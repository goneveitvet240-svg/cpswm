"""Evidence-conditioned current-memory reliability baseline."""

from __future__ import annotations

from math import exp, log
from uuid import uuid4

from cpswm.contracts.grounded_search import (
    MemoryFactorContribution,
    MemoryLifecycleAction,
    MemoryReliabilityProjection,
    MemoryReliabilityRequest,
    MemoryReliabilityStatus,
)


class MemoryReliabilityProjector:
    """Update whether a historical claim remains current using likelihood ratios.

    Age is deliberately excluded from the posterior calculation. A calibrated
    person/object/activity-conditioned transition model may encode elapsed time
    through ``TRANSITION_SURVIVAL`` evidence, with an explicit model version.
    Raw elapsed seconds only distinguish fresh from stale presentation states.
    """

    def project(self, request: MemoryReliabilityRequest) -> MemoryReliabilityProjection:
        prior = request.prior_current_probability
        log_odds = log(prior / (1.0 - prior))
        contributions: list[MemoryFactorContribution] = []
        for factor, evidence in request.factor_evidence.items():
            effective_weight = evidence.reliability * evidence.independence_weight
            # Work in log space before subtraction. Forming p/q first may
            # overflow to infinity for otherwise valid subnormal probabilities.
            log_likelihood_ratio = log(evidence.p_evidence_given_current) - log(
                evidence.p_evidence_given_not_current
            )
            contribution = effective_weight * log_likelihood_ratio
            log_odds += contribution
            contributions.append(
                MemoryFactorContribution(
                    factor=factor,
                    log_likelihood_ratio=contribution,
                    effective_weight=effective_weight,
                )
            )
        # Stable logistic: exp(-x) overflows for large negative x even when all
        # input likelihoods are valid probabilities.
        if log_odds >= 0.0:
            posterior = 1.0 / (1.0 + exp(-log_odds))
        else:
            exp_log_odds = exp(log_odds)
            posterior = exp_log_odds / (1.0 + exp_log_odds)

        if request.superseded_by_record_id is not None:
            status = MemoryReliabilityStatus.SUPERSEDED
            action = MemoryLifecycleAction.FOLLOW_SUPERSEDING_RECORD
            reasons = ("superseding_record_exists", "original_record_remains_auditable")
        elif request.historical_only:
            status = MemoryReliabilityStatus.HISTORICAL
            action = MemoryLifecycleAction.KEEP_AS_HISTORICAL
            reasons = ("valid_as_history_not_asserted_as_current",)
        elif request.explicit_contradiction and posterior <= request.contradicted_threshold:
            status = MemoryReliabilityStatus.CONTRADICTED
            action = MemoryLifecycleAction.MARK_CONTRADICTED
            reasons = ("explicit_contradiction_supported_by_calibrated_evidence",)
        elif (
            posterior >= request.fresh_threshold
            and request.seconds_since_last_direct_observation <= request.stale_after_seconds
        ):
            status = MemoryReliabilityStatus.FRESH
            action = MemoryLifecycleAction.USE_WITH_CURRENT_POSTERIOR
            reasons = ("high_current_posterior_and_recent_direct_observation",)
        elif posterior >= request.usable_threshold:
            status = MemoryReliabilityStatus.STALE
            action = MemoryLifecycleAction.VERIFY_BEFORE_HIGH_RISK_USE
            reasons = ("memory_may_still_be_useful_but_requires_risk_conditioned_verification",)
        else:
            status = MemoryReliabilityStatus.UNCERTAIN
            action = MemoryLifecycleAction.VERIFY_BEFORE_HIGH_RISK_USE
            reasons = ("current_state_posterior_is_low_without_deletion_authority",)

        return MemoryReliabilityProjection(
            metadata=request.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    "schema_name": "cpswm.MemoryReliabilityProjection",
                }
            ),
            memory_record_id=request.memory_record_id,
            prior_current_probability=prior,
            posterior_current_probability=posterior,
            status=status,
            lifecycle_action=action,
            contributions=tuple(contributions),
            age_used_as_direct_reliability_evidence=False,
            explanation_codes=reasons,
            reliability_model_version=request.reliability_model_version,
        )
