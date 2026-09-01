"""Auditable language+vision+geometry+event+person+habit posterior baseline."""

from __future__ import annotations

from math import exp, log
from uuid import UUID

from cpswm.contracts.grounded_search import (
    CandidateKind,
    ChannelContribution,
    GroundedObjectCandidate,
    GroundedSearchResult,
    HardConstraintStatus,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ResolutionStatus,
    ResponsePolicy,
)
from cpswm.foundation.persistence_replay.contracts import content_hash


class JointPosteriorFusion:
    """Weighted log-opinion pool with explicit missing-channel semantics.

    This is a deterministic, replaceable baseline. Correlated channels are not
    assumed independent: channel weights are external calibration parameters,
    while availability and reliability gate each per-candidate contribution.
    """

    def fuse(self, request: JointPosteriorRequest) -> GroundedSearchResult:
        request = JointPosteriorRequest.model_validate(request.model_dump(mode="python"))
        raw_scores: list[tuple[JointCandidateEvidence, float, tuple[ChannelContribution, ...]]] = []
        for candidate in request.candidates:
            if candidate.kind == CandidateKind.OBJECT_INSTANCE and any(
                evaluation.status == HardConstraintStatus.VIOLATED
                for evaluation in candidate.hard_constraint_evaluations
            ):
                continue
            log_score = log(candidate.prior_probability)
            contributions: list[ChannelContribution] = []
            for channel, evidence in candidate.channel_evidence.items():
                effective_weight = (
                    request.channel_weights[channel] * evidence.reliability * evidence.availability
                )
                weighted_log_likelihood = effective_weight * log(
                    evidence.likelihood_given_candidate
                )
                log_score += weighted_log_likelihood
                contributions.append(
                    ChannelContribution(
                        channel=channel,
                        weighted_log_likelihood=weighted_log_likelihood,
                        effective_weight=effective_weight,
                    )
                )
            raw_scores.append((candidate, log_score, tuple(contributions)))

        maximum = max(item[1] for item in raw_scores)
        unnormalized = [exp(item[1] - maximum) for item in raw_scores]
        normalizer = sum(unnormalized)
        normalized = [item / normalizer for item in unnormalized]
        ranked = sorted(
            zip(raw_scores, normalized, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )

        unknown_probability = next(
            probability
            for ((candidate, _, _), probability) in ranked
            if candidate.kind == CandidateKind.UNKNOWN
        )
        object_ranked = [
            item for item in ranked if item[0][0].kind == CandidateKind.OBJECT_INSTANCE
        ]
        best_object_probability = object_ranked[0][1] if object_ranked else 0.0
        second_object_probability = object_ranked[1][1] if len(object_ranked) > 1 else 0.0
        margin = best_object_probability - second_object_probability
        best_object = object_ranked[0][0][0] if object_ranked else None
        best_has_unknown_hard_constraint = best_object is not None and any(
            evaluation.status == HardConstraintStatus.UNKNOWN
            for evaluation in best_object.hard_constraint_evaluations
        )

        if (
            unknown_probability >= request.unknown_threshold
            or unknown_probability >= best_object_probability
        ):
            status = ResolutionStatus.UNKNOWN
            policy = request.unknown_policy
            reasons: tuple[str, ...] = (
                "unknown_mass_high",
                "no_grounded_instance_is_safe_to_assert",
            )
        elif (
            best_has_unknown_hard_constraint
            or best_object_probability < request.resolution_threshold
            or margin < request.ambiguity_margin
        ):
            status = ResolutionStatus.AMBIGUOUS
            policy = request.ambiguity_policy
            reasons = (
                (
                    "hard_constraint_evidence_incomplete"
                    if best_has_unknown_hard_constraint
                    else "candidate_margin_small"
                ),
                "additional_grounded_evidence_required",
            )
        else:
            status = ResolutionStatus.RESOLVED
            policy = ResponsePolicy.RETURN_TOP_K
            reasons = ("posterior_threshold_and_margin_satisfied",)

        returned = ranked[: min(request.top_k, len(ranked))]
        candidates = tuple(
            GroundedObjectCandidate(
                rank=rank,
                candidate_id=source.candidate_id,
                kind=source.kind,
                entity=source.entity,
                location_id=source.location_id,
                posterior_probability=probability,
                contributions=contributions,
            )
            for rank, ((source, _, contributions), probability) in enumerate(returned, start=1)
        )
        posterior_mass_returned = min(
            1.0,
            sum(item.posterior_probability for item in candidates),
        )
        return GroundedSearchResult(
            metadata=request.metadata.model_copy(
                update={
                    "record_id": UUID(
                        bytes=bytes.fromhex(
                            content_hash(
                                {
                                    "kind": "grounded-search-result",
                                    "request": request.model_dump(mode="json"),
                                }
                            )[:32]
                        )
                    ),
                    "schema_name": "cpswm.GroundedSearchResult",
                }
            ),
            query_id=request.compiled_query.query_id,
            candidates=candidates,
            posterior_by_candidate_id={
                candidate.candidate_id: next(
                    (
                        probability
                        for ((source, _, _), probability) in ranked
                        if source.candidate_id == candidate.candidate_id
                    ),
                    0.0,
                )
                for candidate in request.candidates
            },
            hard_constraint_evaluations_by_candidate_id={
                candidate.candidate_id: candidate.hard_constraint_evaluations
                for candidate in request.candidates
            },
            posterior_mass_returned=posterior_mass_returned,
            unknown_probability=unknown_probability,
            resolution_status=status,
            response_policy=policy,
            explanation_codes=reasons,
            fusion_model_version=request.fusion_model_version,
        )
