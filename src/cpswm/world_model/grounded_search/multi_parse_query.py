"""S3-DG-09D multi-parse language posterior and grounded marginalization.

The query compiler is not allowed to collapse an ambiguous utterance into one
privileged parse.  Each groundable parse is fused independently by the frozen
six-channel posterior, then marginalized with the calibrated parse posterior.
Abstaining parse mass and explicitly unparsed mass flow to the existing
``unknown`` object candidate instead of disappearing.
"""

from __future__ import annotations

from math import isclose
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, EntityRef, Probability
from cpswm.contracts.grounded_search import (
    CandidateKind,
    CompiledSemanticQuery,
    GroundedSearchResult,
    HardConstraintStatus,
    JointPosteriorRequest,
    ResolutionStatus,
    ResponsePolicy,
)

from .joint_posterior import JointPosteriorFusion

StrictlyPositiveProbability = Annotated[float, Field(gt=0.0, le=1.0)]


class QueryParseHypothesis(ContractModel):
    """One semantically distinct interpretation of the same utterance."""

    parse_id: UUID = Field(default_factory=uuid4)
    semantic_signature: str = Field(min_length=1)
    probability: StrictlyPositiveProbability
    compiled_query: CompiledSemanticQuery


class MultiParseQueryPosterior(ContractModel):
    """Calibrated posterior over competing query parses plus unresolved mass."""

    utterance: str = Field(min_length=1)
    hypotheses: tuple[QueryParseHypothesis, ...] = Field(min_length=2)
    unparsed_probability: Probability
    compiler_ensemble_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)

    @model_validator(mode="after")
    def _posterior_semantics(self) -> MultiParseQueryPosterior:
        parse_ids = [item.parse_id for item in self.hypotheses]
        signatures = [item.semantic_signature for item in self.hypotheses]
        query_ids = [item.compiled_query.query_id for item in self.hypotheses]
        if len(parse_ids) != len(set(parse_ids)):
            raise ValueError("query parse IDs must be unique")
        if len(signatures) != len(set(signatures)):
            raise ValueError("query parse semantic signatures must be unique")
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("compiled query IDs must be unique across parse hypotheses")
        if any(item.compiled_query.utterance != self.utterance for item in self.hypotheses):
            raise ValueError("every parse hypothesis must compile the same utterance")
        total = self.unparsed_probability + sum(item.probability for item in self.hypotheses)
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("query parse posterior and unparsed mass must sum to one")
        return self


class MultiParseSemanticQueryCompiler(Protocol):
    """LLM boundary: compile language into a posterior, never a map mutation."""

    def compile(self, utterance: str) -> MultiParseQueryPosterior:
        """Return calibrated competing parses and explicit unresolved mass."""
        ...


class ParseGroundingRequest(ContractModel):
    parse_id: UUID
    request: JointPosteriorRequest


class MultiParseGroundingRequest(ContractModel):
    """Grounding inputs for every non-abstaining parse hypothesis."""

    parse_posterior: MultiParseQueryPosterior
    grounding_requests: tuple[ParseGroundingRequest, ...] = Field(min_length=1)
    marginalization_model_version: str = "multi-parse-marginalization@0.1"

    @model_validator(mode="after")
    def _grounding_semantics(self) -> MultiParseGroundingRequest:
        hypothesis_by_id = {item.parse_id: item for item in self.parse_posterior.hypotheses}
        request_by_id = {item.parse_id: item for item in self.grounding_requests}
        if len(request_by_id) != len(self.grounding_requests):
            raise ValueError("each query parse may have at most one grounding request")
        expected_groundable = {
            item.parse_id
            for item in self.parse_posterior.hypotheses
            if not item.compiled_query.abstain
        }
        if set(request_by_id) != expected_groundable:
            raise ValueError("grounding requests must cover exactly the non-abstaining parses")
        for parse_id, grounding in request_by_id.items():
            if grounding.request.compiled_query != hypothesis_by_id[parse_id].compiled_query:
                raise ValueError("grounding request is bound to a different compiled query")

        requests = [item.request for item in self.grounding_requests]
        first = requests[0]
        support = {
            candidate.candidate_id: (
                candidate.kind,
                candidate.entity,
                candidate.location_id,
            )
            for candidate in first.candidates
        }
        decision_fields = (
            "top_k",
            "resolution_threshold",
            "ambiguity_margin",
            "unknown_threshold",
            "ambiguity_policy",
            "unknown_policy",
        )
        for request in requests[1:]:
            current_support = {
                candidate.candidate_id: (
                    candidate.kind,
                    candidate.entity,
                    candidate.location_id,
                )
                for candidate in request.candidates
            }
            if current_support != support:
                raise ValueError(
                    "multi-parse marginalization requires the same grounded candidate support"
                )
            if any(getattr(request, field) != getattr(first, field) for field in decision_fields):
                raise ValueError("multi-parse requests must share one terminal decision policy")
        return self


class MarginalizedGroundedCandidate(ContractModel):
    rank: int = Field(gt=0)
    candidate_id: UUID
    kind: CandidateKind
    entity: EntityRef | None = None
    location_id: UUID | None = None
    posterior_probability: Probability


class MultiParseGroundingResult(ContractModel):
    utterance: str = Field(min_length=1)
    parse_results: dict[UUID, GroundedSearchResult]
    candidates: tuple[MarginalizedGroundedCandidate, ...] = Field(min_length=1)
    posterior_by_candidate_id: dict[UUID, Probability] = Field(min_length=2)
    unknown_candidate_id: UUID
    unknown_probability: Probability
    grounded_parse_probability: Probability
    unresolved_language_probability: Probability
    resolution_status: ResolutionStatus
    response_policy: ResponsePolicy
    explanation_codes: tuple[str, ...] = Field(min_length=1)
    marginalization_model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _result_semantics(self) -> MultiParseGroundingResult:
        if not isclose(
            sum(self.posterior_by_candidate_id.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("marginalized candidate posterior must sum to one")
        if not isclose(
            self.unknown_probability,
            self.posterior_by_candidate_id[self.unknown_candidate_id],
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("unknown probability must match the explicit unknown candidate")
        if [item.rank for item in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise ValueError("marginalized candidate ranks must be contiguous")
        return self


class MultiParseGroundingFusion:
    """Marginalize query uncertainty without granting the compiler map authority."""

    def __init__(self, base_fusion: JointPosteriorFusion | None = None) -> None:
        self._base_fusion = base_fusion or JointPosteriorFusion()

    def fuse(self, request: MultiParseGroundingRequest) -> MultiParseGroundingResult:
        request = MultiParseGroundingRequest.model_validate(request.model_dump(mode="python"))
        hypothesis_by_id = {item.parse_id: item for item in request.parse_posterior.hypotheses}
        grounding_by_id = {item.parse_id: item.request for item in request.grounding_requests}
        first_request = request.grounding_requests[0].request
        source_candidate_by_id = {item.candidate_id: item for item in first_request.candidates}
        unknown_candidate_id = next(
            item.candidate_id
            for item in first_request.candidates
            if item.kind is CandidateKind.UNKNOWN
        )

        parse_results: dict[UUID, GroundedSearchResult] = {}
        marginalized = {candidate_id: 0.0 for candidate_id in source_candidate_by_id}
        unresolved_language_probability = request.parse_posterior.unparsed_probability
        grounded_parse_probability = 0.0
        for hypothesis in request.parse_posterior.hypotheses:
            grounding = grounding_by_id.get(hypothesis.parse_id)
            if grounding is None:
                unresolved_language_probability += hypothesis.probability
                continue
            result = self._base_fusion.fuse(grounding)
            parse_results[hypothesis.parse_id] = result
            grounded_parse_probability += hypothesis.probability
            for candidate_id, probability in result.posterior_by_candidate_id.items():
                marginalized[candidate_id] += hypothesis.probability * probability
        marginalized[unknown_candidate_id] += unresolved_language_probability

        # Floating-point accumulation can differ by a few ulps. Normalize once,
        # without changing the semantics of where unresolved language mass went.
        normalizer = sum(marginalized.values())
        marginalized = {
            candidate_id: probability / normalizer
            for candidate_id, probability in marginalized.items()
        }
        ranked_ids = sorted(marginalized, key=lambda item: marginalized[item], reverse=True)
        unknown_probability = marginalized[unknown_candidate_id]
        object_ids = [
            candidate_id
            for candidate_id in ranked_ids
            if source_candidate_by_id[candidate_id].kind is CandidateKind.OBJECT_INSTANCE
        ]
        best_object_id = object_ids[0] if object_ids else None
        best_object_probability = (
            marginalized[best_object_id] if best_object_id is not None else 0.0
        )
        second_probability = marginalized[object_ids[1]] if len(object_ids) > 1 else 0.0
        margin = best_object_probability - second_probability

        best_has_incomplete_hard_constraint = False
        if best_object_id is not None:
            for parse_id, grounding in grounding_by_id.items():
                hypothesis = hypothesis_by_id[parse_id]
                if hypothesis.probability <= 0.0:
                    continue
                candidate = next(
                    item for item in grounding.candidates if item.candidate_id == best_object_id
                )
                if any(
                    item.status is HardConstraintStatus.UNKNOWN
                    for item in candidate.hard_constraint_evaluations
                ):
                    best_has_incomplete_hard_constraint = True
                    break

        explanation: tuple[str, ...]
        if (
            unknown_probability >= first_request.unknown_threshold
            or unknown_probability >= best_object_probability
        ):
            status = ResolutionStatus.UNKNOWN
            policy = first_request.unknown_policy
            explanation = (
                "language_marginal_unknown_mass_high",
                "no_grounded_instance_is_safe_to_assert",
            )
        elif (
            best_has_incomplete_hard_constraint
            or best_object_probability < first_request.resolution_threshold
            or margin < first_request.ambiguity_margin
        ):
            status = ResolutionStatus.AMBIGUOUS
            policy = first_request.ambiguity_policy
            explanation = (
                "language_parse_or_candidate_margin_ambiguous",
                "additional_grounded_evidence_required",
            )
        else:
            status = ResolutionStatus.RESOLVED
            policy = ResponsePolicy.RETURN_TOP_K
            explanation = ("language_marginal_posterior_resolved",)

        returned_ids = ranked_ids[: min(first_request.top_k, len(ranked_ids))]
        candidates = tuple(
            MarginalizedGroundedCandidate(
                rank=rank,
                candidate_id=candidate_id,
                kind=source_candidate_by_id[candidate_id].kind,
                entity=source_candidate_by_id[candidate_id].entity,
                location_id=source_candidate_by_id[candidate_id].location_id,
                posterior_probability=marginalized[candidate_id],
            )
            for rank, candidate_id in enumerate(returned_ids, start=1)
        )
        return MultiParseGroundingResult(
            utterance=request.parse_posterior.utterance,
            parse_results=parse_results,
            candidates=candidates,
            posterior_by_candidate_id=marginalized,
            unknown_candidate_id=unknown_candidate_id,
            unknown_probability=unknown_probability,
            grounded_parse_probability=grounded_parse_probability,
            unresolved_language_probability=unresolved_language_probability,
            resolution_status=status,
            response_policy=policy,
            explanation_codes=explanation,
            marginalization_model_version=request.marginalization_model_version,
        )
