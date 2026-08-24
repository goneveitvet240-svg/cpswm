"""Typed, provenance-complete LLM/VLM evidence contracts for project two."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import ContractModel, ProjectTwoReplayEpisode, ProjectTwoReplayStep
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


class LLMProviderIdentity(ContractModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)


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
    identity: LLMProviderIdentity
    prompt_template_version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    candidate_count: int = Field(gt=0)
    capabilities: tuple[LLMEvidenceCapability, ...]
    input_evidence_refs: tuple[UUID, ...] = Field(min_length=1)
    visible_payload: dict[str, Any]

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()

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
    ) -> LLMEvidenceRequest:
        refs = tuple(
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
        }
        return cls(
            episode_id=episode.episode_id,
            step_id=step.step_id,
            household_id=episode.household_id,
            session_id=episode.session_id,
            trace_id=episode.trace_id,
            identity=identity,
            prompt_template_version=prompt_template_version,
            temperature=temperature,
            candidate_count=candidate_count,
            capabilities=tuple(LLMEvidenceCapability),
            input_evidence_refs=refs or (step.step_id,),
            visible_payload=payload,
        )


class LLMEvidenceOutput(ContractModel):
    identity: LLMProviderIdentity
    prompt_template_version: str
    input_evidence_refs: tuple[UUID, ...]
    generated_candidates: tuple[LLMGeneratedCandidate, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool
    unknown_probability: float = Field(ge=0.0, le=1.0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    accounting: LLMInvocationAccounting
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @staticmethod
    def content_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical(payload)).hexdigest()

    @model_validator(mode="after")
    def _open_world(self) -> LLMEvidenceOutput:
        if self.abstain and self.unknown_probability <= 0.0:
            raise ValueError("abstention must retain non-zero unknown probability")
        return self


def enforce_no_truth(payload: Any) -> None:
    try:
        reject_truth_leakage(payload)
    except ValueError as exc:
        raise TruthLeakageError(str(exc)) from exc
