"""Provider-neutral adapter that can emit evidence, never state mutations."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    EventMechanismEvidence,
    HiddenEventEvidenceTrack,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
)

from .contracts import (
    LLMCandidateKind,
    LLMEvidenceOutput,
    LLMEvidenceRequest,
    LLMGeneratedCandidate,
    LLMInvocationAccounting,
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

    def complete(self, *, endpoint, api_key, payload, timeout_seconds):
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
                    "content": (
                        "Return only candidate evidence JSON. Preserve unknown/abstain. "
                        "Never assert evaluator truth or request state writes."
                    ),
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
            "unknown_probability": parsed["unknown_probability"],
        }
        digest = LLMEvidenceOutput.content_digest(result_payload)
        provenance_id = hashlib.sha256(f"{request.cache_key}|{digest}".encode()).hexdigest()
        usage = response.body.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        return LLMEvidenceOutput(
            identity=request.identity,
            prompt_template_version=request.prompt_template_version,
            input_evidence_refs=request.input_evidence_refs,
            generated_candidates=candidates,
            confidence=parsed["confidence"],
            abstain=parsed["abstain"],
            unknown_probability=parsed["unknown_probability"],
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
        for field in (
            "observed_destination_location_id",
            "attempted_location_id",
            "source_location_id",
        ):
            value = request.visible_payload.get(field)
            if value:
                candidates.append(
                    LLMGeneratedCandidate(
                        kind=LLMCandidateKind.LOCATION,
                        value=value,
                        score=0.6,
                        evidence_refs=request.input_evidence_refs,
                    )
                )
                break
        selected_candidates = tuple(candidates[: request.candidate_count * 4])
        payload = {
            "candidates": [item.model_dump(mode="json") for item in selected_candidates],
            "confidence": 1.0 - unknown,
            "abstain": self.force_abstain,
            "unknown_probability": unknown,
        }
        content_hash = LLMEvidenceOutput.content_digest(payload)
        provenance_id = hashlib.sha256(f"{request.cache_key}|{content_hash}".encode()).hexdigest()
        return LLMEvidenceOutput(
            identity=request.identity,
            prompt_template_version=request.prompt_template_version,
            input_evidence_refs=request.input_evidence_refs,
            generated_candidates=selected_candidates,
            confidence=1.0 - unknown,
            abstain=self.force_abstain,
            unknown_probability=unknown,
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


@dataclass(frozen=True, slots=True)
class LLMStructuredEvidenceBundle:
    actor: ActorResponsibilityEvidence
    mechanism: EventMechanismEvidence
    role: RoleBindingEvidence
    location_prior: dict[str, float]
    action_proposals: tuple[str, ...]
    unresolved_probability: float
    orrer_required: bool = True


@dataclass(frozen=True, slots=True)
class LLMEvidenceAdapterResult:
    output: LLMEvidenceOutput
    typed_evidence: LLMStructuredEvidenceBundle
    from_cache: bool


class LLMEvidenceAdapter:
    def __init__(self, *, provider: LLMEvidenceProvider, cache: LLMEvidenceCache) -> None:
        self.provider = provider
        self.cache = cache

    def generate(self, request: LLMEvidenceRequest) -> LLMEvidenceAdapterResult:
        enforce_no_truth(request.visible_payload)
        output = self.cache.get(request.cache_key)
        from_cache = output is not None
        if output is None:
            output = self.provider.invoke(request)
            self._validate_output(request, output)
            self.cache.put(request.cache_key, output)
        return LLMEvidenceAdapterResult(output, self._to_typed(request, output), from_cache)

    @staticmethod
    def _validate_output(request: LLMEvidenceRequest, output: LLMEvidenceOutput) -> None:
        enforce_no_truth(output.model_dump(mode="python"))
        if output.cache_key != request.cache_key:
            raise ValueError("provider returned a mismatched deterministic cache key")
        if (
            output.identity != request.identity
            or output.prompt_template_version != request.prompt_template_version
        ):
            raise ValueError("provider provenance does not match request")
        if output.input_evidence_refs != request.input_evidence_refs:
            raise ValueError("provider changed input evidence references")
        payload = {
            "candidates": [item.model_dump(mode="json") for item in output.generated_candidates],
            "confidence": output.confidence,
            "abstain": output.abstain,
            "unknown_probability": output.unknown_probability,
        }
        if output.content_hash != LLMEvidenceOutput.content_digest(payload):
            raise ValueError("provider content hash does not match typed output")

    @staticmethod
    def _to_typed(
        request: LLMEvidenceRequest, output: LLMEvidenceOutput
    ) -> LLMStructuredEvidenceBundle:
        by_kind: dict[LLMCandidateKind, list[LLMGeneratedCandidate]] = {
            kind: [] for kind in LLMCandidateKind
        }
        for item in output.generated_candidates:
            by_kind[item.kind].append(item)

        def normalized(items, fallback):
            values = {item.value: item.score for item in items}
            if not values:
                values = fallback
            total = sum(values.values())
            return {key: value / total for key, value in values.items()}

        actors = normalized(by_kind[LLMCandidateKind.ACTOR], {"unknown_actor": 1.0})
        actors.setdefault("unknown_actor", output.unknown_probability)
        actors = normalized([], actors)
        mechanisms_raw = normalized(
            by_kind[LLMCandidateKind.MECHANISM],
            {
                EventMechanism.DIRECT_RELOCATION.value: 0.4,
                EventMechanism.HANDOFF_RELOCATION.value: 0.4,
                EventMechanism.UNKNOWN_MECHANISM.value: 0.2,
            },
        )
        mechanisms = {EventMechanism(key): value for key, value in mechanisms_raw.items()}
        roles = normalized(by_kind[LLMCandidateKind.ORDERED_ROLE], {})
        if len(roles) < 2:
            known = [key for key in actors if key != "unknown_actor"]
            if len(known) < 2:
                known.extend(["actor_a", "actor_b"])
            roles = {
                ordered_role_key(known[0], known[1]): 0.5,
                ordered_role_key(known[1], known[0]): 0.5,
            }
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
        prior_actor = {key: 1.0 / len(actors) for key in actors}
        prior_mechanism = {key: 1.0 / len(mechanisms) for key in mechanisms}
        prior_roles = {key: 1.0 / len(roles) for key in roles}
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
            evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
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
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
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
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id=model_id,
        )
        return LLMStructuredEvidenceBundle(
            actor=actor,
            mechanism=mechanism,
            role=role,
            location_prior={item.value: item.score for item in by_kind[LLMCandidateKind.LOCATION]},
            action_proposals=tuple(item.value for item in by_kind[LLMCandidateKind.ACTION]),
            unresolved_probability=output.unknown_probability
            if output.abstain
            else output.unknown_probability * 0.5,
        )
