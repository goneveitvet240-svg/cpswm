"""Public project-two LLM/VLM evidence adapter surface."""

from .adapter import (
    DeterministicEvidenceProvider,
    LLMEvidenceAdapter,
    LLMEvidenceAdapterResult,
    LLMEvidenceCache,
    LLMEvidenceProvider,
    LLMStructuredEvidenceBundle,
    LocalModelEvidenceProvider,
    OpenAICompatibleEvidenceProvider,
    ProviderHTTPResponse,
    UrllibLLMHTTPTransport,
)
from .contracts import (
    LLMCandidateKind,
    LLMEvidenceCapability,
    LLMEvidenceOutput,
    LLMEvidenceRequest,
    LLMGeneratedCandidate,
    LLMInvocationAccounting,
    LLMProviderIdentity,
    TruthLeakageError,
)

__all__ = [
    "DeterministicEvidenceProvider",
    "LLMCandidateKind",
    "LLMEvidenceAdapter",
    "LLMEvidenceAdapterResult",
    "LLMEvidenceCache",
    "LLMEvidenceCapability",
    "LLMEvidenceOutput",
    "LLMEvidenceProvider",
    "LLMEvidenceRequest",
    "LLMGeneratedCandidate",
    "LLMInvocationAccounting",
    "LLMProviderIdentity",
    "LLMStructuredEvidenceBundle",
    "LocalModelEvidenceProvider",
    "OpenAICompatibleEvidenceProvider",
    "ProviderHTTPResponse",
    "TruthLeakageError",
    "UrllibLLMHTTPTransport",
]
