"""Provider-neutral adapter that can emit evidence, never state mutations."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    EventMechanismEvidence,
    HiddenEventEvidenceTrack,
    LLMIntegrationRole,
    LLMInvocationProvenance,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
)

from .contracts import (
    LLMCacheStatus,
    LLMCallAuditReceipt,
    LLMCandidateKind,
    LLMEvidenceOutput,
    LLMEvidenceRequest,
    LLMGeneratedCandidate,
    LLMInvocationAccounting,
    LLMProbabilitySemantics,
    enforce_no_prompt_truth,
    enforce_no_truth,
)


class LLMEvidenceProvider(Protocol):
    def invoke(self, request: LLMEvidenceRequest) -> LLMEvidenceOutput: ...


@dataclass(frozen=True, slots=True)
class ProviderHTTPResponse:
    body: dict[str, Any]
    latency_ms: float


class LLMHTTPTransport(Protocol):
    def complete(
        self,
        *,
        endpoint: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> ProviderHTTPResponse: ...


class UrllibLLMHTTPTransport:
    """Minimal real HTTP transport; secrets never enter cache/provenance."""

    def complete(
        self,
        *,
        endpoint: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> ProviderHTTPResponse:
        if not endpoint.startswith("https://"):
            raise ValueError("real provider endpoint must use HTTPS")
        encoded = json.dumps(payload).encode()
        request = urllib.request.Request(
            endpoint,
            data=encoded,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode())
        return ProviderHTTPResponse(
            body=body,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


class OpenAICompatibleEvidenceProvider:
    """Provider adapter for schema-constrained OpenAI-compatible chat APIs."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        transport: LLMHTTPTransport | None = None,
        timeout_seconds: float = 60.0,
        input_cost_per_million_tokens: float = 0.0,
        output_cost_per_million_tokens: float = 0.0,
    ) -> None:
        if not endpoint.strip() or not api_key.strip():
            raise ValueError("provider endpoint and API key are required")
        self.endpoint = endpoint
        self._api_key = api_key
        self.transport = transport or UrllibLLMHTTPTransport()
        self.timeout_seconds = timeout_seconds
        self.input_cost = input_cost_per_million_tokens
        self.output_cost = output_cost_per_million_tokens

    def invoke(self, request: LLMEvidenceRequest) -> LLMEvidenceOutput:
        payload = {
            "model": request.identity.model,
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": request.prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(request.visible_payload, sort_keys=True),
                },
            ],
        }
        response = self.transport.complete(
            endpoint=self.endpoint,
            api_key=self._api_key,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            content = response.body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("provider response is not valid typed evidence JSON") from exc
        enforce_no_truth(parsed)
        candidates = tuple(
            LLMGeneratedCandidate(
                kind=item["kind"],
                value=item["value"],
                score=item["score"],
                evidence_refs=request.input_evidence_refs,
            )
            for item in parsed.get("candidates", ())
        )
        result_payload = {
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "confidence": parsed["confidence"],
            "abstain": parsed["abstain"],
            "unknown_actor_mass": parsed["unknown_actor_mass"],
            "unknown_mechanism_mass": parsed["unknown_mechanism_mass"],
            "unresolved_event_mass": parsed["unresolved_event_mass"],
            "abstention_probability": parsed["abstention_probability"],
            "probability_semantics": request.expected_probability_semantics.value,
            "reference_actor_prior": request.reference_actor_prior,
            "reference_mechanism_prior": request.reference_mechanism_prior,
            "reference_ordered_role_prior": request.reference_ordered_role_prior,
        }
        digest = LLMEvidenceOutput.content_digest(result_payload)
        provenance_id = hashlib.sha256(f"{request.cache_key}|{digest}".encode()).hexdigest()
        usage = response.body.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        return LLMEvidenceOutput(
            role=request.role,
            identity=request.identity,
            prompt_template_version=request.prompt_template_version,
            prompt_sha256=request.prompt_sha256,
            temperature=request.temperature,
            input_evidence_refs=request.input_evidence_refs,
            generated_candidates=candidates,
            confidence=parsed["confidence"],
            abstain=parsed["abstain"],
            unknown_actor_mass=parsed["unknown_actor_mass"],
            unknown_mechanism_mass=parsed["unknown_mechanism_mass"],
            unresolved_event_mass=parsed["unresolved_event_mass"],
            abstention_probability=parsed["abstention_probability"],
            probability_semantics=request.expected_probability_semantics,
            reference_actor_prior=request.reference_actor_prior,
            reference_mechanism_prior=request.reference_mechanism_prior,
            reference_ordered_role_prior=request.reference_ordered_role_prior,
            content_hash=digest,
            accounting=LLMInvocationAccounting(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=response.latency_ms,
                cost_usd=(input_tokens * self.input_cost + output_tokens * self.output_cost)
                / 1_000_000.0,
            ),
            cache_key=request.cache_key,
            provenance_id=provenance_id,
        )


class LLMEvidenceCache:
    def __init__(self) -> None:
        self._values: dict[str, LLMEvidenceOutput] = {}

    def get(self, key: str) -> LLMEvidenceOutput | None:
        return self._values.get(key)

    def put(self, key: str, output: LLMEvidenceOutput) -> None:
        if key != output.cache_key:
            raise ValueError("cache key does not match output provenance")
        existing = self._values.get(key)
        if existing is not None and existing != output:
            raise ValueError("non-deterministic output for an existing cache key")
        self._values[key] = output


class DeterministicEvidenceProvider:
    """Offline D0 fixture provider; it is not represented as a real LLM result."""

    def __init__(self, *, force_abstain: bool = False) -> None:
        self.force_abstain = force_abstain
        self.invocation_count = 0

    def invoke(self, request: LLMEvidenceRequest) -> LLMEvidenceOutput:
        self.invocation_count += 1
        actors = tuple(request.visible_payload.get("resident_actor_keys", ("unknown_actor",)))
        known = tuple(item for item in actors if item != "unknown_actor")
        unknown = 0.55 if self.force_abstain else 0.15
        remaining = 1.0 - unknown
        candidates: list[LLMGeneratedCandidate] = []
        if request.role is LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER:
            for actor in actors:
                score = unknown if actor == "unknown_actor" else remaining / max(len(known), 1)
                candidates.append(
                    LLMGeneratedCandidate(
                        kind=LLMCandidateKind.ACTOR,
                        value=actor,
                        score=score,
                        evidence_refs=request.input_evidence_refs,
                    )
                )
            mechanism_scores = {
                EventMechanism.DIRECT_RELOCATION.value: 0.45 * remaining,
                EventMechanism.HANDOFF_RELOCATION.value: 0.55 * remaining,
                EventMechanism.UNKNOWN_MECHANISM.value: unknown,
            }
            for value, score in mechanism_scores.items():
                candidates.append(
                    LLMGeneratedCandidate(
                        kind=LLMCandidateKind.MECHANISM,
                        value=value,
                        score=score,
                        evidence_refs=request.input_evidence_refs,
                    )
                )
            pairs = tuple(permutations(known[:2], 2))
            for left, right in pairs:
                candidates.append(
                    LLMGeneratedCandidate(
                        kind=LLMCandidateKind.ORDERED_ROLE,
                        value=ordered_role_key(left, right),
                        score=1.0 / len(pairs),
                        evidence_refs=request.input_evidence_refs,
                    )
                )
        visible_locations = tuple(request.visible_payload.get("candidate_location_ids", ()))
        preferred = next(
            (
                request.visible_payload.get(field)
                for field in (
                    "observed_destination_location_id",
                    "attempted_location_id",
                    "source_location_id",
                )
                if request.visible_payload.get(field)
            ),
            None,
        )
        for value in visible_locations:
            score = 0.6 if value == preferred else 0.4 / max(len(visible_locations) - 1, 1)
            candidates.append(
                LLMGeneratedCandidate(
                    kind=LLMCandidateKind.LOCATION,
                    value=value,
                    score=score,
                    evidence_refs=request.input_evidence_refs,
                )
            )
            if request.role is LLMIntegrationRole.LLM_DIRECT_BASELINE:
                candidates.append(
                    LLMGeneratedCandidate(
                        kind=LLMCandidateKind.ACTION,
                        value=f"put_back:{value}",
                        score=score,
                        evidence_refs=request.input_evidence_refs,
                    )
                )
        selected_candidates = tuple(candidates[: request.candidate_count * 4])
        payload = {
            "candidates": [item.model_dump(mode="json") for item in selected_candidates],
            "confidence": 1.0 - unknown,
            "abstain": self.force_abstain,
            "unknown_actor_mass": unknown,
            "unknown_mechanism_mass": unknown,
            "unresolved_event_mass": unknown,
            "abstention_probability": unknown if self.force_abstain else 0.0,
            "probability_semantics": request.expected_probability_semantics.value,
            "reference_actor_prior": request.reference_actor_prior,
            "reference_mechanism_prior": request.reference_mechanism_prior,
            "reference_ordered_role_prior": request.reference_ordered_role_prior,
        }
        content_hash = LLMEvidenceOutput.content_digest(payload)
        provenance_id = hashlib.sha256(f"{request.cache_key}|{content_hash}".encode()).hexdigest()
        return LLMEvidenceOutput(
            role=request.role,
            identity=request.identity,
            prompt_template_version=request.prompt_template_version,
            prompt_sha256=request.prompt_sha256,
            temperature=request.temperature,
            input_evidence_refs=request.input_evidence_refs,
            generated_candidates=selected_candidates,
            confidence=1.0 - unknown,
            abstain=self.force_abstain,
            unknown_actor_mass=unknown,
            unknown_mechanism_mass=unknown,
            unresolved_event_mass=unknown,
            abstention_probability=unknown if self.force_abstain else 0.0,
            probability_semantics=request.expected_probability_semantics,
            reference_actor_prior=request.reference_actor_prior,
            reference_mechanism_prior=request.reference_mechanism_prior,
            reference_ordered_role_prior=request.reference_ordered_role_prior,
            content_hash=content_hash,
            accounting=LLMInvocationAccounting(
                input_tokens=len(str(request.visible_payload).split()),
                output_tokens=len(candidates) * 4,
                latency_ms=0.0,
                cost_usd=0.0,
            ),
            cache_key=request.cache_key,
            provenance_id=provenance_id,
        )


class LocalModelEvidenceProvider:
    """Provider-neutral local-model seam using the same typed request/output."""

    def __init__(self, inference: Callable[[LLMEvidenceRequest], LLMEvidenceOutput]) -> None:
        self._inference = inference
        self.invocation_count = 0

    def invoke(self, request: LLMEvidenceRequest) -> LLMEvidenceOutput:
        self.invocation_count += 1
        output = self._inference(request)
        if not isinstance(output, LLMEvidenceOutput):
            raise TypeError("local inference must return LLMEvidenceOutput")
        return output


@dataclass(frozen=True, slots=True)
class CandidateProposalItem:
    kind: LLMCandidateKind
    value: str
    evidence_refs: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CandidateProposalBundle:
    candidates: tuple[CandidateProposalItem, ...]
    fusion_permission: str = "candidate_generation_only"


@dataclass(frozen=True, slots=True)
class CalibratedLikelihoodBundle:
    likelihood_factors: dict[LLMCandidateKind, dict[str, float]]
    calibration_receipt_id: UUID
    calibration_domain: str
    fusion_permission: str = "direct_likelihood_factor"


@dataclass(frozen=True, slots=True)
class ReferencedPosteriorBundle:
    actor: ActorResponsibilityEvidence
    mechanism: EventMechanismEvidence
    role: RoleBindingEvidence
    location_prior: dict[str, float]
    action_proposals: tuple[str, ...]
    unresolved_probability: float
    orrer_required: bool = True


@dataclass(frozen=True, slots=True)
class LLMEvidenceAdapterResult:
    typed_bundle: CandidateProposalBundle | CalibratedLikelihoodBundle | ReferencedPosteriorBundle
    from_cache: bool
    call_audit: LLMCallAuditReceipt
    invocation_provenance: LLMInvocationProvenance
    accounting: LLMInvocationAccounting
    unresolved_event_mass: float
    abstention_probability: float

    @property
    def typed_evidence(self) -> ReferencedPosteriorBundle | None:
        return (
            self.typed_bundle if isinstance(self.typed_bundle, ReferencedPosteriorBundle) else None
        )


class LLMEvidenceAdapter:
    def __init__(
        self,
        *,
        provider: LLMEvidenceProvider,
        cache: LLMEvidenceCache,
        audit_session_id: UUID | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.audit_session_id = audit_session_id or uuid4()
        self._call_audits: list[LLMCallAuditReceipt] = []

    @property
    def call_audits(self) -> tuple[LLMCallAuditReceipt, ...]:
        return tuple(self._call_audits)

    def generate(self, request: LLMEvidenceRequest) -> LLMEvidenceAdapterResult:
        enforce_no_truth(request.visible_payload)
        enforce_no_prompt_truth(request.prompt)
        output = self.cache.get(request.cache_key)
        from_cache = output is not None
        if output is None:
            output = self.provider.invoke(request)
            self._validate_output(request, output)
            self.cache.put(request.cache_key, output)
        else:
            # Cache contents cross the same trust boundary as provider output.
            # This rejects disk/cache poisoning before typed evidence is built.
            self._validate_output(request, output)
        typed_bundle = self._to_capability_bundle(request, output)
        call_sequence = len(self._call_audits) + 1
        call_audit = LLMCallAuditReceipt(
            audit_id=uuid5(
                NAMESPACE_URL,
                f"{self.audit_session_id}:{request.cache_key}:call:{call_sequence}:"
                f"{'hit' if from_cache else 'miss'}",
            ),
            call_sequence=call_sequence,
            role=request.role,
            cache_status=LLMCacheStatus.HIT if from_cache else LLMCacheStatus.MISS,
            provider_invoked=not from_cache,
            cache_key=request.cache_key,
            output_provenance_id=output.provenance_id,
            prompt_sha256=request.prompt_sha256,
            input_evidence_refs=request.input_evidence_refs,
            source_invocation_provenance=output.invocation_provenance,
            call_accounting=(
                LLMInvocationAccounting(
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0.0,
                    cost_usd=0.0,
                )
                if from_cache
                else output.accounting
            ),
        )
        self._call_audits.append(call_audit)
        return LLMEvidenceAdapterResult(
            typed_bundle=typed_bundle,
            from_cache=from_cache,
            call_audit=call_audit,
            invocation_provenance=output.invocation_provenance,
            accounting=output.accounting,
            unresolved_event_mass=output.unresolved_event_mass,
            abstention_probability=output.abstention_probability,
        )

    @staticmethod
    def _validate_output(request: LLMEvidenceRequest, output: LLMEvidenceOutput) -> None:
        enforce_no_truth(output.model_dump(mode="python"))
        if output.cache_key != request.cache_key:
            raise ValueError("provider returned a mismatched deterministic cache key")
        if (
            output.role != request.role
            or output.temperature != request.temperature
            or output.prompt_sha256 != request.prompt_sha256
            or output.identity != request.identity
            or output.prompt_template_version != request.prompt_template_version
        ):
            raise ValueError("provider provenance does not match request")
        if output.input_evidence_refs != request.input_evidence_refs:
            raise ValueError("provider changed input evidence references")
        if output.probability_semantics is not request.expected_probability_semantics:
            raise ValueError("provider probability semantics exceed request authority")
        if output.fusion_permission is not request.authorized_fusion_permission:
            raise ValueError("provider fusion permission exceeds request authority")
        if (
            output.reference_actor_prior != request.reference_actor_prior
            or output.reference_mechanism_prior != request.reference_mechanism_prior
            or output.reference_ordered_role_prior != request.reference_ordered_role_prior
        ):
            raise ValueError("provider changed the caller-frozen reference prior")
        payload = {
            "candidates": [item.model_dump(mode="json") for item in output.generated_candidates],
            "confidence": output.confidence,
            "abstain": output.abstain,
            "unknown_actor_mass": output.unknown_actor_mass,
            "unknown_mechanism_mass": output.unknown_mechanism_mass,
            "unresolved_event_mass": output.unresolved_event_mass,
            "abstention_probability": output.abstention_probability,
            "probability_semantics": output.probability_semantics.value,
            "reference_actor_prior": output.reference_actor_prior,
            "reference_mechanism_prior": output.reference_mechanism_prior,
            "reference_ordered_role_prior": output.reference_ordered_role_prior,
        }
        if output.content_hash != LLMEvidenceOutput.content_digest(payload):
            raise ValueError("provider content hash does not match typed output")

    @staticmethod
    def _to_capability_bundle(
        request: LLMEvidenceRequest, output: LLMEvidenceOutput
    ) -> CandidateProposalBundle | CalibratedLikelihoodBundle | ReferencedPosteriorBundle:
        if request.expected_probability_semantics is LLMProbabilitySemantics.PROPOSAL_ONLY:
            return CandidateProposalBundle(
                candidates=tuple(
                    CandidateProposalItem(
                        kind=item.kind,
                        value=item.value,
                        evidence_refs=item.evidence_refs,
                    )
                    for item in output.generated_candidates
                )
            )
        if request.expected_probability_semantics is LLMProbabilitySemantics.CALIBRATED_LIKELIHOOD:
            receipt = request.calibration_receipt
            assert receipt is not None
            factors = {
                kind: {
                    item.value: item.score
                    for item in output.generated_candidates
                    if item.kind is kind
                }
                for kind in LLMCandidateKind
            }
            return CalibratedLikelihoodBundle(
                likelihood_factors=factors,
                calibration_receipt_id=receipt.receipt_id,
                calibration_domain=receipt.calibration_domain,
            )
        return LLMEvidenceAdapter._to_typed(request, output)

    @staticmethod
    def _to_typed(
        request: LLMEvidenceRequest, output: LLMEvidenceOutput
    ) -> ReferencedPosteriorBundle:
        by_kind: dict[LLMCandidateKind, list[LLMGeneratedCandidate]] = {
            kind: [] for kind in LLMCandidateKind
        }
        for item in output.generated_candidates:
            by_kind[item.kind].append(item)

        actors = {item.value: item.score for item in by_kind[LLMCandidateKind.ACTOR]}
        mechanisms_raw = {item.value: item.score for item in by_kind[LLMCandidateKind.MECHANISM]}
        mechanisms = {EventMechanism(key): value for key, value in mechanisms_raw.items()}
        roles = {item.value: item.score for item in by_kind[LLMCandidateKind.ORDERED_ROLE]}
        if not actors or not mechanisms or not roles:
            raise ValueError("referenced posterior requires complete actor/mechanism/role axes")
        evidence_time = datetime.fromisoformat(request.visible_payload["timestamp"])
        metadata = BaseRecordMetadata(
            record_id=uuid5(NAMESPACE_URL, f"{output.provenance_id}:metadata"),
            schema_name="cpswm.LLMStructuredEvidence",
            schema_version="0.1.0",
            household_id=request.household_id,
            session_id=request.session_id,
            recorded_time=evidence_time,
            source_type=SourceType.MODEL,
            source_id=f"{output.identity.provider}/{output.identity.model}",
            model_version=output.identity.version,
            trace_id=request.trace_id,
        )
        source_detection = request.input_evidence_refs[0]
        if output.reference_actor_prior is None or output.reference_mechanism_prior is None:
            raise ValueError("posterior projection requires caller-frozen reference priors")
        prior_actor = output.reference_actor_prior
        prior_mechanism = {
            EventMechanism(key): value for key, value in output.reference_mechanism_prior.items()
        }
        prior_roles = output.reference_ordered_role_prior
        if prior_roles is None:
            raise ValueError("posterior role projection requires a caller-frozen reference prior")
        model_id = (
            f"{output.identity.provider}:{output.identity.model}:{output.identity.version}:"
            f"{output.prompt_template_version}:{output.provenance_id}"
        )
        actor = ActorResponsibilityEvidence(
            metadata=metadata.model_copy(
                update={"record_id": uuid5(NAMESPACE_URL, f"{output.provenance_id}:actor")}
            ),
            source_detection_result_id=source_detection,
            object_instance_id=UUID(str(request.visible_payload["object_instance_id"])),
            evidence_time=metadata.recorded_time,
            actor_posterior=actors,
            reference_actor_prior=prior_actor,
            evidence_cluster_id=uuid5(NAMESPACE_URL, f"{output.provenance_id}:actor-cluster"),
            evidence_track=ActorEvidenceTrack.MODEL,
            evidence_model_id=model_id,
        )
        mechanism = EventMechanismEvidence(
            metadata=metadata.model_copy(
                update={"record_id": uuid5(NAMESPACE_URL, f"{output.provenance_id}:mechanism")}
            ),
            source_detection_result_id=source_detection,
            object_instance_id=actor.object_instance_id,
            evidence_time=metadata.recorded_time,
            mechanism_posterior=mechanisms,
            reference_mechanism_prior=prior_mechanism,
            evidence_cluster_id=uuid5(NAMESPACE_URL, f"{output.provenance_id}:mechanism-cluster"),
            evidence_track=HiddenEventEvidenceTrack.MODEL,
            evidence_model_id=model_id,
        )
        role = RoleBindingEvidence(
            metadata=metadata.model_copy(
                update={"record_id": uuid5(NAMESPACE_URL, f"{output.provenance_id}:role")}
            ),
            source_detection_result_id=source_detection,
            object_instance_id=actor.object_instance_id,
            evidence_time=metadata.recorded_time,
            ordered_role_posterior=roles,
            reference_ordered_role_prior=prior_roles,
            evidence_cluster_id=uuid5(NAMESPACE_URL, f"{output.provenance_id}:role-cluster"),
            evidence_track=HiddenEventEvidenceTrack.MODEL,
            evidence_model_id=model_id,
        )
        return ReferencedPosteriorBundle(
            actor=actor,
            mechanism=mechanism,
            role=role,
            location_prior={item.value: item.score for item in by_kind[LLMCandidateKind.LOCATION]},
            action_proposals=tuple(item.value for item in by_kind[LLMCandidateKind.ACTION]),
            unresolved_probability=output.unresolved_event_mass,
        )
