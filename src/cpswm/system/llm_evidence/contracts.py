"""Typed, provenance-complete LLM/VLM evidence contracts for project two."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from math import isclose
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    LLM_ROLE_AUTHORITY,
    ContractModel,
    LLMIntegrationRole,
    LLMInvocationProvenance,
    LLMProviderIdentity,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
)
from cpswm.contracts.project_two_replay import reject_truth_leakage


class TruthLeakageError(ValueError):
    """Raised before a provider sees evaluator-only information."""


class LLMEvidenceCapability(StrEnum):
    CANDIDATE_GENERATION = "candidate_generation"
    SEMANTIC_LOCATION_PRIOR = "semantic_location_prior"
    MECHANISM_ROLE_EXTRACTION = "mechanism_role_evidence_extraction"
    NATURAL_LANGUAGE_INTERACTION = "natural_language_interaction_evidence"
    SEARCH_ACTION_PROPOSAL = "search_action_proposal"


class LLMCandidateKind(StrEnum):
    ACTOR = "actor"
    MECHANISM = "mechanism"
    ORDERED_ROLE = "ordered_role"
    LOCATION = "location"
    ACTION = "action"


class LLMProbabilitySemantics(StrEnum):
    PROPOSAL_ONLY = "proposal_only"
    CALIBRATED_LIKELIHOOD = "calibrated_likelihood"
    POSTERIOR_RELATIVE_TO_REFERENCE_PRIOR = "posterior_relative_to_reference_prior"


class LLMFusionPermission(StrEnum):
    CANDIDATE_GENERATION_ONLY = "candidate_generation_only"
    DIRECT_LIKELIHOOD_FACTOR = "direct_likelihood_factor"
    REFERENCE_PRIOR_LIKELIHOOD_RATIO = "reference_prior_likelihood_ratio"


SEMANTICS_PERMISSION = {
    LLMProbabilitySemantics.PROPOSAL_ONLY: LLMFusionPermission.CANDIDATE_GENERATION_ONLY,
    LLMProbabilitySemantics.CALIBRATED_LIKELIHOOD: LLMFusionPermission.DIRECT_LIKELIHOOD_FACTOR,
    LLMProbabilitySemantics.POSTERIOR_RELATIVE_TO_REFERENCE_PRIOR: (
        LLMFusionPermission.REFERENCE_PRIOR_LIKELIHOOD_RATIO
    ),
}


class LLMCalibrationReceipt(ContractModel):
    receipt_id: UUID
    calibration_domain: str = Field(min_length=1)
    calibration_method: str = Field(min_length=1)
    calibration_dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_identity: LLMProviderIdentity


ROLE_CAPABILITIES = {
    LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER: (
        LLMEvidenceCapability.CANDIDATE_GENERATION,
        LLMEvidenceCapability.SEMANTIC_LOCATION_PRIOR,
        LLMEvidenceCapability.MECHANISM_ROLE_EXTRACTION,
        LLMEvidenceCapability.NATURAL_LANGUAGE_INTERACTION,
    ),
    LLMIntegrationRole.LLM_DIRECT_BASELINE: (
        LLMEvidenceCapability.CANDIDATE_GENERATION,
        LLMEvidenceCapability.SEMANTIC_LOCATION_PRIOR,
        LLMEvidenceCapability.SEARCH_ACTION_PROPOSAL,
    ),
}

ROLE_CANDIDATE_KINDS = {
    LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER: frozenset(
        {
            LLMCandidateKind.ACTOR,
            LLMCandidateKind.MECHANISM,
            LLMCandidateKind.ORDERED_ROLE,
            LLMCandidateKind.LOCATION,
        }
    ),
    LLMIntegrationRole.LLM_DIRECT_BASELINE: frozenset(
        {LLMCandidateKind.LOCATION, LLMCandidateKind.ACTION}
    ),
}

ROLE_PROMPTS = {
    LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER: (
        "Return only actor, mechanism, ordered-role, or location candidate evidence. "
        "Preserve unknown and abstain, cite supplied evidence records, and never emit "
        "actions, world facts, evaluator labels, or state-write instructions."
    ),
    LLMIntegrationRole.LLM_DIRECT_BASELINE: (
        "Under the declared candidate set and action budget, directly predict the next "
        "put-back/search action. Preserve unknown and abstain, cite supplied evidence "
        "records, and never request or perform a world-model write."
    ),
}


class LLMGeneratedCandidate(ContractModel):
    kind: LLMCandidateKind
    value: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[UUID, ...] = Field(min_length=1)


class LLMInvocationAccounting(ContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(ge=0.0)


class LLMCacheStatus(StrEnum):
    MISS = "miss"
    HIT = "hit"


class LLMCallAuditReceipt(ContractModel):
    """One audit record per adapter call, including successful cache hits."""

    audit_id: UUID
    call_sequence: int = Field(gt=0)
    role: LLMIntegrationRole
    cache_status: LLMCacheStatus
    provider_invoked: bool
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_provenance_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_evidence_refs: tuple[UUID, ...] = Field(min_length=1)
    source_invocation_provenance: LLMInvocationProvenance
    call_accounting: LLMInvocationAccounting

    @model_validator(mode="after")
    def _cache_semantics(self) -> LLMCallAuditReceipt:
        expected_invocation = self.cache_status is LLMCacheStatus.MISS
        if self.provider_invoked is not expected_invocation:
            raise ValueError("provider_invoked must agree with cache hit/miss status")
        accounting = self.call_accounting
        if self.cache_status is LLMCacheStatus.HIT and any(
            (
                accounting.input_tokens,
                accounting.output_tokens,
                accounting.latency_ms,
                accounting.cost_usd,
            )
        ):
            raise ValueError("cache-hit call accounting must be zero")
        if self.source_invocation_provenance.cache_key != self.cache_key:
            raise ValueError("call audit must bind the source invocation cache key")
        if self.source_invocation_provenance.role is not self.role:
            raise ValueError("call audit role must match source invocation provenance")
        if self.source_invocation_provenance.prompt_sha256 != self.prompt_sha256:
            raise ValueError("call audit must bind the source invocation prompt hash")
        if self.source_invocation_provenance.input_evidence_refs != self.input_evidence_refs:
            raise ValueError("call audit must bind the source invocation evidence references")
        return self


def _canonical(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class LLMEvidenceRequest(ContractModel):
    episode_id: UUID
    step_id: UUID
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    role: LLMIntegrationRole = LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER
    identity: LLMProviderIdentity
    prompt_template_version: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    candidate_count: int = Field(gt=0)
    capabilities: tuple[LLMEvidenceCapability, ...]
    expected_probability_semantics: LLMProbabilitySemantics
    authorized_fusion_permission: LLMFusionPermission
    reference_actor_prior: dict[str, float] | None = None
    reference_mechanism_prior: dict[str, float] | None = None
    reference_ordered_role_prior: dict[str, float] | None = None
    reference_prior_snapshot_id: UUID | None = None
    calibration_receipt: LLMCalibrationReceipt | None = None
    input_evidence_refs: tuple[UUID, ...] = Field(min_length=1)
    visible_payload: dict[str, Any]

    @model_validator(mode="after")
    def _role_and_prompt_boundary(self) -> LLMEvidenceRequest:
        if self.role not in ROLE_CAPABILITIES:
            raise ValueError("M21 query compilation must use CompiledSemanticQuery")
        if set(self.capabilities) != set(ROLE_CAPABILITIES[self.role]):
            raise ValueError("LLM request capabilities do not match its declared role")
        if (
            self.authorized_fusion_permission
            is not SEMANTICS_PERMISSION[self.expected_probability_semantics]
        ):
            raise ValueError("fusion permission does not match requested probability semantics")
        priors = (
            self.reference_actor_prior,
            self.reference_mechanism_prior,
            self.reference_ordered_role_prior,
        )
        if self.expected_probability_semantics is LLMProbabilitySemantics.PROPOSAL_ONLY:
            if any(item is not None for item in priors) or self.calibration_receipt is not None:
                raise ValueError("proposal requests cannot carry fusion priors or calibration")
        elif self.expected_probability_semantics is LLMProbabilitySemantics.CALIBRATED_LIKELIHOOD:
            if self.calibration_receipt is None:
                raise ValueError("calibrated likelihood requires a caller-authorized receipt")
            if self.calibration_receipt.provider_identity != self.identity:
                raise ValueError("calibration receipt provider does not match request")
            if any(item is not None for item in priors):
                raise ValueError("calibrated likelihood requests cannot carry reference priors")
        else:
            if any(item is None for item in priors):
                raise ValueError("referenced posterior requires caller-supplied frozen priors")
            if self.reference_prior_snapshot_id is None:
                raise ValueError("referenced posterior requires a frozen belief snapshot id")
            for prior in priors:
                assert prior is not None
                if not isclose(sum(prior.values()), 1.0, abs_tol=1e-6):
                    raise ValueError("each frozen reference prior must sum to one")
                if any(value <= 0.0 for value in prior.values()):
                    raise ValueError("frozen reference priors must be strictly positive")
        enforce_no_truth(self.visible_payload)
        enforce_no_prompt_truth(self.prompt)
        return self

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(
            _canonical({"prompt": self.prompt, "visible_payload": self.visible_payload})
        ).hexdigest()

    @classmethod
    def from_replay_step(
        cls,
        *,
        episode: ProjectTwoReplayEpisode,
        step: ProjectTwoReplayStep,
        identity: LLMProviderIdentity,
        prompt_template_version: str,
        temperature: float,
        candidate_count: int,
        expected_probability_semantics: LLMProbabilitySemantics,
        authorized_fusion_permission: LLMFusionPermission,
        reference_actor_prior: dict[str, float] | None = None,
        reference_mechanism_prior: dict[str, float] | None = None,
        reference_ordered_role_prior: dict[str, float] | None = None,
        reference_prior_snapshot_id: UUID | None = None,
        calibration_receipt: LLMCalibrationReceipt | None = None,
        role: LLMIntegrationRole = LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER,
    ) -> LLMEvidenceRequest:
        current_refs = tuple(
            item.metadata.record_id
            for item in (
                step.after,
                step.before,
                step.actor_evidence,
                step.mechanism_evidence,
                step.ordered_role_evidence,
            )
            if item is not None
        )
        position = next(
            index
            for index, candidate in enumerate(episode.steps)
            if candidate.step_id == step.step_id
        )
        visible_prefix = episode.steps[: position + 1]
        history_refs = tuple(
            record.metadata.record_id
            for item in visible_prefix
            for record in (
                item.after,
                item.before,
                item.actor_evidence,
                item.mechanism_evidence,
                item.ordered_role_evidence,
            )
            if record is not None
        )
        refs = tuple(dict.fromkeys((*current_refs, *history_refs)))
        candidate_locations = tuple(
            dict.fromkeys(
                str(value)
                for item in visible_prefix
                for value in (
                    item.source_location_id,
                    item.attempted_location_id,
                    item.observed_destination_location_id,
                )
                if value is not None
            )
        )
        visible_history = tuple(
            {
                "step_id": str(item.step_id),
                "timestamp": item.timestamp.isoformat(),
                "source_location_id": (
                    str(item.source_location_id) if item.source_location_id else None
                ),
                "attempted_location_id": (
                    str(item.attempted_location_id) if item.attempted_location_id else None
                ),
                "observed_destination_location_id": (
                    str(item.observed_destination_location_id)
                    if item.observed_destination_location_id
                    else None
                ),
                "detected_location_id": (
                    str(item.after.detected_location_id)
                    if item.after is not None and item.after.detected_location_id is not None
                    else None
                ),
                "visibility_probability": item.visibility_probability,
                "occlusion_state": item.occlusion_state.value,
                "detection_confidence": item.detection_confidence,
            }
            for item in visible_prefix
        )
        payload = {
            "object_instance_id": str(step.object_instance_id),
            "object_category": step.object_category,
            "resident_actor_keys": episode.resident_actor_keys,
            "source_location_id": str(step.source_location_id) if step.source_location_id else None,
            "attempted_location_id": (
                str(step.attempted_location_id) if step.attempted_location_id else None
            ),
            "observed_destination_location_id": (
                str(step.observed_destination_location_id)
                if step.observed_destination_location_id
                else None
            ),
            "visibility_probability": step.visibility_probability,
            "occlusion_state": step.occlusion_state.value,
            "detection_confidence": step.detection_confidence,
            "timestamp": step.timestamp.isoformat(),
            "visible_history": visible_history,
            "candidate_location_ids": candidate_locations,
            "action_budget": len(episode.steps),
        }
        return cls(
            episode_id=episode.episode_id,
            step_id=step.step_id,
            household_id=episode.household_id,
            session_id=episode.session_id,
            trace_id=episode.trace_id,
            role=role,
            identity=identity,
            prompt_template_version=prompt_template_version,
            prompt=ROLE_PROMPTS[role],
            temperature=temperature,
            candidate_count=candidate_count,
            capabilities=ROLE_CAPABILITIES[role],
            expected_probability_semantics=expected_probability_semantics,
            authorized_fusion_permission=authorized_fusion_permission,
            reference_actor_prior=reference_actor_prior,
            reference_mechanism_prior=reference_mechanism_prior,
            reference_ordered_role_prior=reference_ordered_role_prior,
            reference_prior_snapshot_id=reference_prior_snapshot_id,
            calibration_receipt=calibration_receipt,
            input_evidence_refs=refs or (step.step_id,),
            visible_payload=payload,
        )


class LLMEvidenceOutput(ContractModel):
    role: LLMIntegrationRole
    identity: LLMProviderIdentity
    prompt_template_version: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    temperature: float = Field(ge=0.0, le=2.0)
    input_evidence_refs: tuple[UUID, ...] = Field(min_length=1)
    generated_candidates: tuple[LLMGeneratedCandidate, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool
    unknown_actor_mass: float = Field(ge=0.0, le=1.0)
    unknown_mechanism_mass: float = Field(ge=0.0, le=1.0)
    unresolved_event_mass: float = Field(ge=0.0, le=1.0)
    abstention_probability: float = Field(ge=0.0, le=1.0)
    probability_semantics: LLMProbabilitySemantics
    reference_actor_prior: dict[str, float] | None = None
    reference_mechanism_prior: dict[str, float] | None = None
    reference_ordered_role_prior: dict[str, float] | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    accounting: LLMInvocationAccounting
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def fusion_permission(self) -> LLMFusionPermission:
        return {
            LLMProbabilitySemantics.PROPOSAL_ONLY: (LLMFusionPermission.CANDIDATE_GENERATION_ONLY),
            LLMProbabilitySemantics.CALIBRATED_LIKELIHOOD: (
                LLMFusionPermission.DIRECT_LIKELIHOOD_FACTOR
            ),
            LLMProbabilitySemantics.POSTERIOR_RELATIVE_TO_REFERENCE_PRIOR: (
                LLMFusionPermission.REFERENCE_PRIOR_LIKELIHOOD_RATIO
            ),
        }[self.probability_semantics]

    @property
    def invocation_provenance(self) -> LLMInvocationProvenance:
        return LLMInvocationProvenance(
            role=self.role,
            authority=LLM_ROLE_AUTHORITY[self.role],
            provider=self.identity.provider,
            model=self.identity.model,
            version=self.identity.version,
            temperature=self.temperature,
            prompt_template_version=self.prompt_template_version,
            prompt_sha256=self.prompt_sha256,
            input_tokens=self.accounting.input_tokens,
            output_tokens=self.accounting.output_tokens,
            latency_ms=self.accounting.latency_ms,
            cost_usd=self.accounting.cost_usd,
            cache_key=self.cache_key,
            input_evidence_refs=self.input_evidence_refs,
        )

    @staticmethod
    def content_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical(payload)).hexdigest()

    @model_validator(mode="after")
    def _open_world(self) -> LLMEvidenceOutput:
        if self.role not in ROLE_CANDIDATE_KINDS:
            raise ValueError("M21 query output cannot use LLMEvidenceOutput")
        candidate_keys = [(item.kind, item.value) for item in self.generated_candidates]
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("duplicate candidate kind/value pairs are forbidden")
        if any(
            item.kind not in ROLE_CANDIDATE_KINDS[self.role] for item in self.generated_candidates
        ):
            raise ValueError("LLM output candidate kind exceeds declared role authority")
        if self.abstain and self.abstention_probability <= 0.0:
            raise ValueError("abstention must retain non-zero abstention probability")
        priors = (
            self.reference_actor_prior,
            self.reference_mechanism_prior,
            self.reference_ordered_role_prior,
        )
        if (
            self.probability_semantics
            is LLMProbabilitySemantics.POSTERIOR_RELATIVE_TO_REFERENCE_PRIOR
        ):
            if self.reference_actor_prior is None or self.reference_mechanism_prior is None:
                raise ValueError("posterior semantics require explicit actor and mechanism priors")
            for prior in (self.reference_actor_prior, self.reference_mechanism_prior):
                if (
                    any(value <= 0.0 for value in prior.values())
                    or not abs(sum(prior.values()) - 1.0) <= 1e-6
                ):
                    raise ValueError("reference priors must be positive and normalized")
            candidate_support = {
                kind: {item.value for item in self.generated_candidates if item.kind is kind}
                for kind in (
                    LLMCandidateKind.ACTOR,
                    LLMCandidateKind.MECHANISM,
                    LLMCandidateKind.ORDERED_ROLE,
                )
            }
            if set(self.reference_actor_prior) != candidate_support[LLMCandidateKind.ACTOR]:
                raise ValueError("reference actor prior must match actor candidate support")
            if set(self.reference_mechanism_prior) != candidate_support[LLMCandidateKind.MECHANISM]:
                raise ValueError("reference mechanism prior must match mechanism candidate support")
            role_support = candidate_support[LLMCandidateKind.ORDERED_ROLE]
            if role_support and (
                self.reference_ordered_role_prior is None
                or set(self.reference_ordered_role_prior) != role_support
            ):
                raise ValueError("reference role prior must match ordered-role candidate support")
            actor_unknown = next(
                (
                    item.score
                    for item in self.generated_candidates
                    if item.kind is LLMCandidateKind.ACTOR and item.value == "unknown_actor"
                ),
                None,
            )
            mechanism_unknown = next(
                (
                    item.score
                    for item in self.generated_candidates
                    if item.kind is LLMCandidateKind.MECHANISM and item.value == "unknown_mechanism"
                ),
                None,
            )
            if actor_unknown is None or not isclose(
                actor_unknown, self.unknown_actor_mass, abs_tol=1e-6
            ):
                raise ValueError("unknown_actor_mass must match the actor posterior candidate")
            if mechanism_unknown is None or not isclose(
                mechanism_unknown, self.unknown_mechanism_mass, abs_tol=1e-6
            ):
                raise ValueError(
                    "unknown_mechanism_mass must match the mechanism posterior candidate"
                )
            for kind in (
                LLMCandidateKind.ACTOR,
                LLMCandidateKind.MECHANISM,
                LLMCandidateKind.ORDERED_ROLE,
            ):
                axis = [item.score for item in self.generated_candidates if item.kind is kind]
                if axis and not isclose(sum(axis), 1.0, abs_tol=1e-6):
                    raise ValueError(f"{kind.value} posterior candidates must sum to one")
        elif any(prior is not None for prior in priors):
            raise ValueError("proposal/likelihood outputs cannot carry posterior reference priors")
        return self


def enforce_no_truth(payload: Any) -> None:
    try:
        reject_truth_leakage(payload)
    except ValueError as exc:
        raise TruthLeakageError(str(exc)) from exc


def enforce_no_prompt_truth(prompt: str) -> None:
    lowered = prompt.lower()
    forbidden = (
        "true_actor",
        "true_mechanism",
        "true_location",
        "evaluator_truth",
        "oracle_truth",
        "ground_truth",
        "event_chain_truth",
    )
    if any(token in lowered for token in forbidden):
        raise TruthLeakageError("prompt contains evaluator-only truth aliases")
