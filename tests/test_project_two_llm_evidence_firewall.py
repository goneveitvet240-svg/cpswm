from __future__ import annotations

import json

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.llm_evidence import (
    DeterministicEvidenceProvider,
    LLMEvidenceAdapter,
    LLMEvidenceCache,
    LLMEvidenceRequest,
    LLMProviderIdentity,
    LocalModelEvidenceProvider,
    OpenAICompatibleEvidenceProvider,
    ProviderHTTPResponse,
    TruthLeakageError,
)


def _episode():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=3
    ).build()
    return dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]


def _request(**updates):
    episode = _episode()
    step = next(item for item in episode.steps if item.after is not None)
    base = LLMEvidenceRequest.from_replay_step(
        episode=episode,
        step=step,
        identity=LLMProviderIdentity(provider="fixture", model="evidence-fixture", version="1.0"),
        prompt_template_version="project-two-evidence@1",
        temperature=0.0,
        candidate_count=4,
    )
    return base.model_copy(update=updates)


def test_truth_leakage_is_rejected_before_provider_invocation():
    provider = DeterministicEvidenceProvider()
    adapter = LLMEvidenceAdapter(provider=provider, cache=LLMEvidenceCache())
    request = _request(visible_payload={"true_actor": "owner"})
    with pytest.raises(TruthLeakageError):
        adapter.generate(request)
    assert provider.invocation_count == 0


def test_same_cache_key_replays_identical_result_without_second_call():
    provider = DeterministicEvidenceProvider()
    adapter = LLMEvidenceAdapter(provider=provider, cache=LLMEvidenceCache())
    request = _request()
    first = adapter.generate(request)
    second = adapter.generate(request)
    assert first.output == second.output
    assert first.output.cache_key == request.cache_key
    assert first.from_cache is False
    assert second.from_cache is True
    assert provider.invocation_count == 1


def test_cache_poisoning_is_rejected_before_typed_evidence_projection():
    provider = DeterministicEvidenceProvider()
    cache = LLMEvidenceCache()
    adapter = LLMEvidenceAdapter(provider=provider, cache=cache)
    request = _request()
    valid = adapter.generate(request).output
    cache._values[request.cache_key] = valid.model_copy(update={"content_hash": "0" * 64})
    with pytest.raises(ValueError, match="content hash"):
        adapter.generate(request)


def test_local_model_uses_same_typed_provider_contract():
    fixture = DeterministicEvidenceProvider()
    provider = LocalModelEvidenceProvider(fixture.invoke)
    result = LLMEvidenceAdapter(provider=provider, cache=LLMEvidenceCache()).generate(_request())
    assert provider.invocation_count == 1
    assert result.typed_evidence.orrer_required is True


def test_prompt_or_model_change_produces_new_cache_and_provenance():
    provider = DeterministicEvidenceProvider()
    adapter = LLMEvidenceAdapter(provider=provider, cache=LLMEvidenceCache())
    base = _request()
    prompt_changed = base.model_copy(update={"prompt_template_version": "project-two-evidence@2"})
    model_changed = base.model_copy(
        update={
            "identity": LLMProviderIdentity(
                provider="fixture", model="evidence-fixture", version="2.0"
            )
        }
    )
    provider_changed = base.model_copy(
        update={
            "identity": LLMProviderIdentity(
                provider="second-fixture", model="evidence-fixture", version="1.0"
            )
        }
    )
    outputs = [
        adapter.generate(item).output
        for item in (base, prompt_changed, model_changed, provider_changed)
    ]
    assert len({item.cache_key for item in outputs}) == 4
    assert len({item.provenance_id for item in outputs}) == 4


def test_unknown_and_abstain_reach_open_world_typed_evidence():
    adapter = LLMEvidenceAdapter(
        provider=DeterministicEvidenceProvider(force_abstain=True),
        cache=LLMEvidenceCache(),
    )
    bundle = adapter.generate(_request()).typed_evidence
    assert bundle.unresolved_probability > 0.0
    assert bundle.actor.actor_posterior["unknown_actor"] > 0.0
    assert bundle.mechanism.mechanism_posterior["unknown_mechanism"] > 0.0
    assert max(bundle.actor.actor_posterior.values()) < 1.0


def test_adapter_only_returns_typed_evidence_and_cannot_mutate_history():
    adapter = LLMEvidenceAdapter(provider=DeterministicEvidenceProvider(), cache=LLMEvidenceCache())
    result = adapter.generate(_request())
    assert result.typed_evidence.actor.metadata.source_type.value == "model"
    assert not hasattr(adapter, "write_event_history")
    assert not hasattr(adapter, "write_project_one_statistics")
    assert result.typed_evidence.orrer_required is True


def test_openai_compatible_provider_parses_typed_json_and_accounts_usage():
    request = _request()

    class StubTransport:
        def complete(self, *, endpoint, api_key, payload, timeout_seconds):
            assert endpoint == "https://llm.invalid/v1/chat/completions"
            assert api_key == "test-only"
            assert "true_actor" not in repr(payload)
            return ProviderHTTPResponse(
                body={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "candidates": [
                                            {
                                                "kind": "actor",
                                                "value": "unknown_actor",
                                                "score": 0.4,
                                            },
                                            {"kind": "actor", "value": "owner", "score": 0.3},
                                            {"kind": "actor", "value": "guest", "score": 0.3},
                                            {
                                                "kind": "mechanism",
                                                "value": "direct_relocation",
                                                "score": 0.3,
                                            },
                                            {
                                                "kind": "mechanism",
                                                "value": "handoff_relocation",
                                                "score": 0.3,
                                            },
                                            {
                                                "kind": "mechanism",
                                                "value": "unknown_mechanism",
                                                "score": 0.4,
                                            },
                                            {
                                                "kind": "ordered_role",
                                                "value": "owner=>guest",
                                                "score": 0.5,
                                            },
                                            {
                                                "kind": "ordered_role",
                                                "value": "guest=>owner",
                                                "score": 0.5,
                                            },
                                        ],
                                        "confidence": 0.6,
                                        "abstain": True,
                                        "unknown_probability": 0.4,
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 20},
                },
                latency_ms=12.5,
            )

    provider = OpenAICompatibleEvidenceProvider(
        transport=StubTransport(),
        endpoint="https://llm.invalid/v1/chat/completions",
        api_key="test-only",
        input_cost_per_million_tokens=1.0,
        output_cost_per_million_tokens=2.0,
    )
    result = LLMEvidenceAdapter(provider=provider, cache=LLMEvidenceCache()).generate(request)
    assert result.output.accounting.input_tokens == 30
    assert result.output.accounting.output_tokens == 20
    assert result.output.accounting.latency_ms == 12.5
    assert result.output.accounting.cost_usd == pytest.approx(0.00007)
    assert result.typed_evidence.actor.actor_posterior["unknown_actor"] == 0.4
