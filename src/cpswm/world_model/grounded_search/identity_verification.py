"""Multi-view and optional tactile identity confirmation baseline."""

from __future__ import annotations

from math import exp, log

from cpswm.contracts.grounded_search import (
    IdentityVerificationRequest,
    IdentityVerificationResult,
    ResolutionStatus,
    VerificationModality,
)


class MultiViewIdentityVerifier:
    """Fuse independent evidence clusters without counting video frames twice."""

    def verify(self, request: IdentityVerificationRequest) -> IdentityVerificationResult:
        request = IdentityVerificationRequest.model_validate(
            request.model_dump(mode="python")
        )
        best_by_cluster = {}
        for evidence in request.view_evidence:
            previous = best_by_cluster.get(evidence.evidence_cluster_id)
            if previous is None or evidence.quality > previous.quality:
                best_by_cluster[evidence.evidence_cluster_id] = evidence

        log_scores = {
            candidate_id: log(request.prior_probabilities[candidate_id])
            for candidate_id in request.candidate_ids
        }
        used_modalities = set()
        for evidence in best_by_cluster.values():
            used_modalities.add(evidence.modality)
            for candidate_id, likelihood in evidence.candidate_likelihoods.items():
                log_scores[candidate_id] += evidence.quality * log(likelihood)

        maximum = max(log_scores.values())
        exponentials = {
            candidate_id: exp(score - maximum)
            for candidate_id, score in log_scores.items()
        }
        normalizer = sum(exponentials.values())
        posteriors = {
            candidate_id: value / normalizer
            for candidate_id, value in exponentials.items()
        }
        ranked = sorted(posteriors.items(), key=lambda item: item[1], reverse=True)
        best_id, best_probability = ranked[0]
        margin = best_probability - ranked[1][1]
        independent_view_count = len(best_by_cluster)

        sufficient_views = independent_view_count >= request.required_independent_views
        if (
            sufficient_views
            and best_probability >= request.confirmation_threshold
            and margin >= request.ambiguity_margin
        ):
            return IdentityVerificationResult(
                posterior_probabilities=posteriors,
                confirmed_candidate_id=best_id,
                independent_view_count=independent_view_count,
                status=ResolutionStatus.RESOLVED,
                explanation_codes=("independent_multiview_confirmation",),
            )

        tactile_already_used = VerificationModality.TACTILE in used_modalities
        if request.allow_tactile and request.tactile_safe and not tactile_already_used:
            recommended = VerificationModality.TACTILE
            reason = "safe_tactile_confirmation_recommended"
        else:
            recommended = VerificationModality.RGBD
            reason = "additional_independent_view_required"
        return IdentityVerificationResult(
            posterior_probabilities=posteriors,
            independent_view_count=max(1, independent_view_count),
            status=ResolutionStatus.AMBIGUOUS,
            recommended_modality=recommended,
            explanation_codes=(reason,),
        )
