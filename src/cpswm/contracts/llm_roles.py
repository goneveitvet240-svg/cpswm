"""Shared authority and provenance contracts for every LLM/VLM role.

The role is part of the request/output contract, not a label added to a report
after execution.  None of these contracts is a world-model record and none
exposes a write method for M13--M19.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel


class LLMIntegrationRole(StrEnum):
    M21_QUERY_COMPILER = "m21_query_compiler"
    STRUCTURE_TWO_EVIDENCE_PROVIDER = "structure_two_evidence_provider"
    LLM_DIRECT_BASELINE = "llm_direct_baseline"


class LLMOutputAuthority(StrEnum):
    STRUCTURED_QUERY_ONLY = "structured_query_only"
    CANDIDATE_EVIDENCE_ONLY = "candidate_evidence_only"
    DIRECT_PREDICTION_ONLY = "direct_prediction_only"


class LLMInvocationProvenance(ContractModel):
    """Complete, replay-addressable accounting for one model invocation."""

    role: LLMIntegrationRole
    authority: LLMOutputAuthority
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    prompt_template_version: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(ge=0.0)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_evidence_refs: tuple[UUID, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _role_authority(self) -> LLMInvocationProvenance:
        require_role_authority(self.role, self.authority)
        return self


LLM_ROLE_AUTHORITY = {
    LLMIntegrationRole.M21_QUERY_COMPILER: LLMOutputAuthority.STRUCTURED_QUERY_ONLY,
    LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER: (
        LLMOutputAuthority.CANDIDATE_EVIDENCE_ONLY
    ),
    LLMIntegrationRole.LLM_DIRECT_BASELINE: LLMOutputAuthority.DIRECT_PREDICTION_ONLY,
}

FORBIDDEN_LLM_WORLD_MODEL_TARGETS = tuple(f"M{index}" for index in range(13, 20))


def require_role_authority(role: LLMIntegrationRole, authority: LLMOutputAuthority) -> None:
    if LLM_ROLE_AUTHORITY[role] is not authority:
        raise ValueError(f"{role.value} cannot claim {authority.value} authority")


def build_query_compiler_provenance(
    *,
    provider: str,
    model: str,
    version: str,
    temperature: float,
    prompt_template_version: str,
    prompt: str,
    input_evidence_refs: tuple[UUID, ...],
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: float = 0.0,
    cost_usd: float = 0.0,
) -> LLMInvocationProvenance:
    """Build the mandatory M21 provenance block from the exact compiler prompt."""

    prompt_sha256 = hashlib.sha256(prompt.encode()).hexdigest()
    cache_payload = {
        "role": LLMIntegrationRole.M21_QUERY_COMPILER.value,
        "provider": provider,
        "model": model,
        "version": version,
        "temperature": temperature,
        "prompt_template_version": prompt_template_version,
        "prompt_sha256": prompt_sha256,
        "input_evidence_refs": [str(item) for item in input_evidence_refs],
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return LLMInvocationProvenance(
        role=LLMIntegrationRole.M21_QUERY_COMPILER,
        authority=LLMOutputAuthority.STRUCTURED_QUERY_ONLY,
        provider=provider,
        model=model,
        version=version,
        temperature=temperature,
        prompt_template_version=prompt_template_version,
        prompt_sha256=prompt_sha256,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        cache_key=cache_key,
        input_evidence_refs=input_evidence_refs,
    )


__all__ = [
    "FORBIDDEN_LLM_WORLD_MODEL_TARGETS",
    "LLM_ROLE_AUTHORITY",
    "LLMIntegrationRole",
    "LLMInvocationProvenance",
    "LLMOutputAuthority",
    "build_query_compiler_provenance",
    "require_role_authority",
]
