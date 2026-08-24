"""``llm_direct``: an LLM asked to do the whole job, as a baseline arm.

This arm exists to answer one question honestly -- can a general model, shown
the same history, match the chain? -- and it is only an answer if the LLM is
held to exactly the constraints every other arm is held to.

The constraints, and why each is a test rather than a convention:

* **It sees strictly less than it is scored on.**  The prompt is built from
  events *before* the current one plus the current context.  The event's own
  ``observed_location`` never appears; if it did, the arm would be grading
  itself and its log-loss would be fiction.
* **It never sees truth.**  It is a method, and methods are handed
  :class:`ProjectOneDatasetRecord` only.  This is structural -- there is no
  parameter to pass truth through -- but the leakage test pins the prompt too.
* **Its output is validated, not trusted.**  A model that returns prose, extra
  locations, or probabilities summing to 1.4 must be caught by schema
  validation and retried, then fall back to a declared prior rather than
  crashing a 10-hour pilot.
* **Every call is accounted for.**  Tokens, latency, retries, cache hits,
  timeouts and cost are reported, because "the LLM did better" is not a result
  if it cost 400x the compute.

No test here touches the network.  The client arrives through a Protocol and
the double is :class:`FakeLLMClient`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_llm_method import (
    FakeLLMClient,
    LLMCompletion,
    LLMMethodConfig,
    LLMProjectOneMethod,
    LLMTimeoutError,
)
from cpswm.system.evaluation_operations.project_one_methods import ProjectOneMethod

LOCATIONS = ("table", "sink", "balcony")
EPOCH = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def _record(index: int, location: str, *, context: str = "morning") -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="llm",
        event_id=f"l{index:03d}",
        subject_id="alice",
        household_id="h1",
        object_id="cup",
        actor_id="alice",
        timestamp=EPOCH + timedelta(days=index),
        context_key=context,
        context_value=0.0 if context == "morning" else 1.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _reply(
    *,
    table: float = 0.7,
    sink: float = 0.2,
    balcony: float = 0.1,
    change: float = 0.1,
    cause: str = "stable",
    confidence: float = 0.8,
) -> str:
    return json.dumps(
        {
            "next_location_probabilities": {
                "table": table,
                "sink": sink,
                "balcony": balcony,
            },
            "change_probability": change,
            "cause": cause,
            "confidence": confidence,
        }
    )


def _method(client: FakeLLMClient, **overrides: object) -> LLMProjectOneMethod:
    config = LLMMethodConfig(model="fake-1", **overrides)  # type: ignore[arg-type]
    return LLMProjectOneMethod(locations=LOCATIONS, config=config, client=client)


# ---------------------------------------------------------------------------
# It is a method like any other
# ---------------------------------------------------------------------------


def test_it_satisfies_the_project_one_method_protocol() -> None:
    method = _method(FakeLLMClient(replies=[_reply()]))
    assert isinstance(method, ProjectOneMethod)
    assert method.name == "llm_direct"


def test_it_returns_a_well_formed_step_prediction() -> None:
    method = _method(FakeLLMClient(replies=[_reply()] * 4))
    prediction = method.observe(_record(0, "table"))

    assert prediction.event_id == "l000"
    assert sum(prediction.predicted_location_probabilities.values()) == pytest.approx(1.0)
    assert 0.0 <= prediction.change_probability <= 1.0
    assert prediction.rls_residual is None


def test_reset_clears_history_and_usage() -> None:
    client = FakeLLMClient(replies=[_reply()] * 8)
    method = _method(client)
    for index, location in enumerate(("table", "sink")):
        method.observe(_record(index, location))
    method.reset()
    assert method.usage().calls == 0
    assert method.snapshot()["history_length"] == 0


# ---------------------------------------------------------------------------
# It sees strictly less than it is scored on
# ---------------------------------------------------------------------------


def test_the_prompt_never_contains_the_event_being_scored() -> None:
    client = FakeLLMClient(replies=[_reply()] * 4)
    method = _method(client)
    method.observe(_record(0, "table"))
    method.observe(_record(1, "sink"))
    method.observe(_record(2, "balcony"))

    # The third prompt is built before "balcony" is absorbed, so the word must
    # not be in it -- neither as the answer nor as part of the history.
    third_prompt = client.prompts[2]
    assert "l002" not in third_prompt
    assert "balcony" not in third_prompt.split("CANDIDATE LOCATIONS")[-1].split("HISTORY")[-1]


def test_two_streams_differing_only_in_the_scored_event_get_the_same_prompt() -> None:
    """The general no-peek property, applied to the arm most able to cheat."""

    prompts = []
    for final in ("sink", "balcony"):
        client = FakeLLMClient(replies=[_reply()] * 4)
        method = _method(client)
        method.observe(_record(0, "table"))
        method.observe(_record(1, "table"))
        method.observe(_record(2, final))
        prompts.append(client.prompts[-1])
    assert prompts[0] == prompts[1]


def test_the_history_window_is_honoured() -> None:
    client = FakeLLMClient(replies=[_reply()] * 12)
    method = _method(client, history_window=3)
    for index in range(10):
        method.observe(_record(index, "table" if index % 2 == 0 else "sink"))
    assert client.prompts[-1].count("l0") <= 4


def test_the_current_context_is_available_to_the_model() -> None:
    """Context is known before the location is; withholding it would cripple the arm."""

    client = FakeLLMClient(replies=[_reply()] * 2)
    method = _method(client)
    method.observe(_record(0, "table", context="evening"))
    assert "evening" in client.prompts[0]


# ---------------------------------------------------------------------------
# Output is validated, not trusted
# ---------------------------------------------------------------------------


def test_probabilities_are_renormalized_when_the_model_is_sloppy() -> None:
    client = FakeLLMClient(replies=[_reply(table=0.6, sink=0.6, balcony=0.6)])
    method = _method(client)
    prediction = method.observe(_record(0, "table"))
    assert sum(prediction.predicted_location_probabilities.values()) == pytest.approx(1.0)
    assert prediction.predicted_location_probabilities["table"] == pytest.approx(1 / 3)


def test_a_location_outside_the_candidate_set_is_rejected() -> None:
    bad = json.dumps(
        {
            "next_location_probabilities": {"table": 0.5, "moon": 0.5},
            "change_probability": 0.1,
            "cause": "stable",
            "confidence": 0.5,
        }
    )
    client = FakeLLMClient(replies=[bad, _reply()])
    method = _method(client)
    method.observe(_record(0, "table"))
    assert method.usage().schema_failures == 1
    assert method.usage().retries == 1


def test_a_missing_candidate_is_filled_with_zero_not_dropped() -> None:
    partial = json.dumps(
        {
            "next_location_probabilities": {"table": 1.0},
            "change_probability": 0.1,
            "cause": "stable",
            "confidence": 0.5,
        }
    )
    client = FakeLLMClient(replies=[partial])
    method = _method(client)
    prediction = method.observe(_record(0, "table"))
    assert set(prediction.predicted_location_probabilities) == set(LOCATIONS)
    assert prediction.predicted_location_probabilities["balcony"] == pytest.approx(0.0)


def test_prose_instead_of_json_is_retried_then_falls_back() -> None:
    client = FakeLLMClient(replies=["I think the cup is on the table!"] * 3)
    method = _method(client, max_attempts=3)
    prediction = method.observe(_record(0, "table"))

    assert method.usage().schema_failures == 3
    assert method.usage().retries == 2
    # Fallback is a declared uniform prior, not a crash and not a guess.
    assert prediction.predicted_location_probabilities["table"] == pytest.approx(1 / 3)
    assert prediction.predicted_cause == "insufficient_evidence"


def test_json_wrapped_in_a_code_fence_is_accepted() -> None:
    client = FakeLLMClient(replies=[f"```json\n{_reply()}\n```"])
    method = _method(client)
    prediction = method.observe(_record(0, "table"))
    assert prediction.predicted_location_probabilities["table"] == pytest.approx(0.7)
    assert method.usage().schema_failures == 0


@pytest.mark.parametrize("value", [-0.2, 1.4, "high", None])
def test_an_out_of_range_change_probability_is_a_schema_failure(value: object) -> None:
    bad = json.dumps(
        {
            "next_location_probabilities": {"table": 1.0, "sink": 0.0, "balcony": 0.0},
            "change_probability": value,
            "cause": "stable",
            "confidence": 0.5,
        }
    )
    client = FakeLLMClient(replies=[bad, _reply()])
    method = _method(client)
    method.observe(_record(0, "table"))
    assert method.usage().schema_failures == 1


def test_a_missing_required_key_is_a_schema_failure() -> None:
    bad = json.dumps({"next_location_probabilities": {"table": 1.0}})
    client = FakeLLMClient(replies=[bad, _reply()])
    method = _method(client)
    method.observe(_record(0, "table"))
    assert method.usage().schema_failures == 1


def test_the_decision_label_stays_inside_the_frozen_four_class_space() -> None:
    client = FakeLLMClient(replies=[_reply(cause="the cat moved it", change=0.9)] * 2)
    method = _method(client)
    prediction = method.observe(_record(0, "table"))
    assert prediction.decision.value in {
        "stable",
        "insufficient_evidence",
        "short_term_disturbance",
        "habit_change",
    }


# ---------------------------------------------------------------------------
# Cache, timeout, retry
# ---------------------------------------------------------------------------


def test_an_identical_prompt_is_served_from_cache() -> None:
    client = FakeLLMClient(replies=[_reply()] * 6)
    method = _method(client, history_window=1)
    method.observe(_record(0, "table"))
    method.observe(_record(1, "table"))
    method.observe(_record(2, "table"))

    assert method.usage().cache_hits >= 1
    assert client.call_count < 3


def test_the_cache_can_be_switched_off() -> None:
    client = FakeLLMClient(replies=[_reply()] * 6)
    method = _method(client, history_window=1, cache=False)
    for index in range(3):
        method.observe(_record(index, "table"))
    assert client.call_count == 3
    assert method.usage().cache_hits == 0


def test_a_timeout_is_retried_and_counted() -> None:
    client = FakeLLMClient(replies=[LLMTimeoutError("slow"), _reply()])
    method = _method(client, max_attempts=3)
    method.observe(_record(0, "table"))
    assert method.usage().timeouts == 1
    assert method.usage().retries == 1


def test_exhausting_every_attempt_does_not_crash_the_pilot() -> None:
    client = FakeLLMClient(replies=[LLMTimeoutError("slow")] * 3)
    method = _method(client, max_attempts=3)
    prediction = method.observe(_record(0, "table"))
    assert prediction.predicted_cause == "insufficient_evidence"
    assert method.usage().timeouts == 3


def test_the_configured_timeout_reaches_the_client() -> None:
    client = FakeLLMClient(replies=[_reply()])
    method = _method(client, timeout_seconds=4.5)
    method.observe(_record(0, "table"))
    assert client.timeouts_seen == [4.5]


# ---------------------------------------------------------------------------
# Accounting
# ---------------------------------------------------------------------------


def test_tokens_latency_and_cost_are_reported() -> None:
    client = FakeLLMClient(
        replies=[LLMCompletion(text=_reply(), prompt_tokens=120, completion_tokens=40)] * 2
    )
    method = _method(
        client,
        cache=False,
        prompt_cost_per_1k_usd=0.003,
        completion_cost_per_1k_usd=0.015,
    )
    method.observe(_record(0, "table"))
    method.observe(_record(1, "sink"))

    usage = method.usage()
    assert usage.calls == 2
    assert usage.prompt_tokens == 240
    assert usage.completion_tokens == 80
    assert usage.total_latency_seconds >= 0.0
    assert usage.estimated_cost_usd == pytest.approx(240 / 1000 * 0.003 + 80 / 1000 * 0.015)


def test_usage_appears_in_the_snapshot() -> None:
    client = FakeLLMClient(replies=[_reply()] * 2)
    method = _method(client)
    method.observe(_record(0, "table"))
    snapshot = method.snapshot()
    assert snapshot["llm_calls"] == 1
    assert "estimated_cost_usd" in snapshot


# ---------------------------------------------------------------------------
# The execution config actually reaches the provider
# ---------------------------------------------------------------------------


def test_the_model_reaches_the_client() -> None:
    """It used to be declared, echoed, and never sent."""

    client = FakeLLMClient(replies=[_reply()])
    _method(client).observe(_record(0, "table"))
    assert client.requests[0].model == "fake-1"


def test_the_temperature_reaches_the_client() -> None:
    client = FakeLLMClient(replies=[_reply()])
    _method(client, temperature=0.7).observe(_record(0, "table"))
    assert client.requests[0].temperature == pytest.approx(0.7)


def test_the_candidate_set_reaches_the_client() -> None:
    """The answer space is part of the request, not context the model infers."""

    client = FakeLLMClient(replies=[_reply()])
    _method(client).observe(_record(0, "table"))
    assert client.requests[0].candidate_locations == LOCATIONS


def test_two_temperatures_do_not_share_a_cache_entry() -> None:
    """Keying the cache on the prompt alone would make the settings identical."""

    cold = FakeLLMClient(replies=[_reply()] * 4)
    hot = FakeLLMClient(replies=[_reply()] * 4)
    _method(cold, temperature=0.0).observe(_record(0, "table"))
    _method(hot, temperature=1.0).observe(_record(0, "table"))
    assert cold.requests[0].identity() != hot.requests[0].identity()


def test_two_models_do_not_share_a_cache_entry() -> None:
    client = FakeLLMClient(replies=[_reply()] * 4)
    first = _method(client).observe(_record(0, "table"))
    other = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="fake-2"),
        client=client,
    )
    other.observe(_record(0, "table"))
    assert first is not None
    assert client.requests[0].identity() != client.requests[1].identity()


def test_two_candidate_sets_do_not_share_a_cache_entry() -> None:
    client = FakeLLMClient(replies=[_reply()] * 4)
    _method(client).observe(_record(0, "table"))
    narrow = LLMProjectOneMethod(
        locations=("table", "sink"),
        config=LLMMethodConfig(model="fake-1"),
        client=client,
    )
    narrow.observe(_record(0, "table"))
    assert client.requests[0].identity() != client.requests[1].identity()


def test_the_config_hash_covers_the_candidate_set() -> None:
    """Two answer spaces are two experiments, whatever the settings say."""

    client = FakeLLMClient(replies=[_reply()] * 4)
    wide = LLMProjectOneMethod(
        locations=LOCATIONS, config=LLMMethodConfig(model="fake-1"), client=client
    )
    narrow = LLMProjectOneMethod(
        locations=("table", "sink"), config=LLMMethodConfig(model="fake-1"), client=client
    )
    assert wide.config_hash() != narrow.config_hash()


def test_the_config_hash_covers_the_temperature() -> None:
    client = FakeLLMClient(replies=[_reply()] * 4)
    assert (
        _method(client, temperature=0.0).config_hash()
        != _method(client, temperature=0.9).config_hash()
    )


def test_the_config_hash_covers_the_model_and_the_prompt_shape() -> None:
    client = FakeLLMClient(replies=[_reply()] * 4)
    first = _method(client, history_window=5).config_hash()
    second = _method(client, history_window=9).config_hash()
    third = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="fake-2", history_window=5),
        client=client,
    ).config_hash()
    assert len({first, second, third}) == 3


def test_the_config_payload_names_the_model() -> None:
    method = _method(FakeLLMClient(replies=[_reply()]))
    payload = method.config_payload()
    assert payload["kind"] == "llm_direct"
    assert payload["model"] == "fake-1"


# ---------------------------------------------------------------------------
# The LLM does not also produce labels
# ---------------------------------------------------------------------------


def test_the_method_has_no_way_to_receive_truth() -> None:
    """Structural: ``observe`` takes a record, and records carry no truth."""

    import inspect

    signature = inspect.signature(LLMProjectOneMethod.observe)
    assert list(signature.parameters) == ["self", "event"]


def test_the_prompt_never_asks_the_model_for_ground_truth() -> None:
    client = FakeLLMClient(replies=[_reply()])
    method = _method(client)
    method.observe(_record(0, "table"))
    lowered = client.prompts[0].lower()
    for forbidden in ("ground truth", "expected_location", "true_change_point", "label"):
        assert forbidden not in lowered


# ---------------------------------------------------------------------------
# Matched input: the arm must be asked the same question as the chain
# ---------------------------------------------------------------------------


def test_matched_input_is_the_default() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import PromptVariant

    assert LLMMethodConfig(model="m").prompt_variant is PromptVariant.MATCHED_INPUT


def test_matched_input_shows_the_actor_and_quality_the_chain_arms_read() -> None:
    """Withholding these makes ``llm_direct`` a weakened arm, not a baseline."""

    client = FakeLLMClient(replies=[_reply()] * 4)
    method = _method(client)
    method.observe(_record(0, "table"))
    method.observe(_record(1, "sink"))
    prompt = client.prompts[-1]
    assert "actor=" in prompt
    assert "quality=" in prompt
    assert "observation_quality=" in prompt


def test_the_minimal_variant_still_reproduces_the_earlier_prompt() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import PromptVariant

    client = FakeLLMClient(replies=[_reply()] * 4)
    method = _method(client, prompt_variant=PromptVariant.MINIMAL)
    method.observe(_record(0, "table"))
    method.observe(_record(1, "sink"))
    history = client.prompts[-1].split("deliberately not shown)", 1)[-1]
    assert "actor=" not in history
    assert "quality=" not in history


def test_the_prompt_variant_enters_the_config_hash() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import PromptVariant

    client = FakeLLMClient(replies=[_reply()] * 4)
    assert (
        _method(client).config_hash()
        != _method(client, prompt_variant=PromptVariant.MINIMAL).config_hash()
    )


def test_matched_input_still_hides_the_event_being_scored() -> None:
    """More fields must not become more leakage."""

    prompts = []
    for final in ("sink", "balcony"):
        client = FakeLLMClient(replies=[_reply()] * 4)
        method = _method(client)
        method.observe(_record(0, "table"))
        method.observe(_record(1, "table"))
        method.observe(_record(2, final))
        prompts.append(client.prompts[-1])
    assert prompts[0] == prompts[1]


# ---------------------------------------------------------------------------
# A real provider, exercised without a network
# ---------------------------------------------------------------------------


class _FakeTransport:
    """Stands in for the HTTPS transport.  No socket is ever opened."""

    def __init__(self, body: object = None, error: BaseException | None = None) -> None:
        self.body = body
        self.error = error
        self.calls: list[dict[str, object]] = []

    def complete(self, *, endpoint, api_key, payload, timeout_seconds):
        from cpswm.system.llm_evidence.adapter import ProviderHTTPResponse

        self.calls.append(
            {
                "endpoint": endpoint,
                "api_key": api_key,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return ProviderHTTPResponse(body=self.body, latency_ms=1.0)


def _openai_client(transport: _FakeTransport):
    from cpswm.system.evaluation_operations.project_one_llm_method import (
        OpenAICompatibleLLMClient,
    )

    return OpenAICompatibleLLMClient(
        endpoint="https://example.invalid/v1/chat/completions",
        api_key="secret-key",
        transport=transport,
    )


def _ok_body(text: str) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40},
    }


def test_the_real_provider_satisfies_the_client_protocol() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import LLMClient

    assert isinstance(_openai_client(_FakeTransport(_ok_body("{}"))), LLMClient)


def test_the_real_provider_sends_model_temperature_and_prompt() -> None:
    transport = _FakeTransport(_ok_body(_reply()))
    client = _openai_client(transport)
    method = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="real-model-v1", temperature=0.25),
        client=client,
    )
    method.observe(_record(0, "table"))

    payload = transport.calls[0]["payload"]
    assert payload["model"] == "real-model-v1"  # type: ignore[index]
    assert payload["temperature"] == pytest.approx(0.25)  # type: ignore[index]
    assert payload["response_format"] == {"type": "json_object"}  # type: ignore[index]
    messages = payload["messages"]  # type: ignore[index]
    assert messages[0]["role"] == "system"
    assert "CANDIDATE LOCATIONS" in messages[1]["content"]


def test_the_real_provider_reports_the_tokens_the_api_returned() -> None:
    transport = _FakeTransport(_ok_body(_reply()))
    client = _openai_client(transport)
    method = LLMProjectOneMethod(
        locations=LOCATIONS, config=LLMMethodConfig(model="m"), client=client
    )
    method.observe(_record(0, "table"))
    usage = method.usage()
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 40


def test_a_transport_timeout_becomes_a_retryable_llm_timeout() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import LLMRequest

    transport = _FakeTransport(error=TimeoutError("slow"))
    client = _openai_client(transport)
    request = LLMRequest(
        prompt="p", model="m", temperature=0.0, timeout_seconds=1.0, candidate_locations=("a",)
    )
    with pytest.raises(LLMTimeoutError):
        client.complete(request)


def test_a_wrapped_socket_timeout_is_also_a_timeout() -> None:
    from urllib.error import URLError

    from cpswm.system.evaluation_operations.project_one_llm_method import LLMRequest

    transport = _FakeTransport(error=URLError(TimeoutError("slow")))
    client = _openai_client(transport)
    request = LLMRequest(
        prompt="p", model="m", temperature=0.0, timeout_seconds=1.0, candidate_locations=("a",)
    )
    with pytest.raises(LLMTimeoutError):
        client.complete(request)


def test_an_unusable_envelope_does_not_kill_the_run() -> None:
    """A broken response is retried like a timeout, not raised through the pilot."""

    from cpswm.system.evaluation_operations.project_one_llm_method import LLMRequest

    transport = _FakeTransport({"unexpected": True})
    client = _openai_client(transport)
    request = LLMRequest(
        prompt="p", model="m", temperature=0.0, timeout_seconds=1.0, candidate_locations=("a",)
    )
    with pytest.raises(LLMTimeoutError, match="unusable envelope"):
        client.complete(request)


def test_the_provider_requires_an_endpoint_and_a_key() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import (
        OpenAICompatibleLLMClient,
    )

    with pytest.raises(ValueError, match="endpoint"):
        OpenAICompatibleLLMClient(endpoint="  ", api_key="k")
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleLLMClient(endpoint="https://x/y", api_key="  ")


def test_the_api_key_never_appears_in_the_prompt_or_the_payload_messages() -> None:
    transport = _FakeTransport(_ok_body(_reply()))
    client = _openai_client(transport)
    method = LLMProjectOneMethod(
        locations=LOCATIONS, config=LLMMethodConfig(model="m"), client=client
    )
    method.observe(_record(0, "table"))
    messages = transport.calls[0]["payload"]["messages"]  # type: ignore[index]
    assert "secret-key" not in json.dumps(messages)
    # It reaches the transport as a header argument, and nowhere else.
    assert transport.calls[0]["api_key"] == "secret-key"


def test_the_https_only_rule_lives_in_the_shared_transport() -> None:
    from cpswm.system.llm_evidence.adapter import UrllibLLMHTTPTransport

    with pytest.raises(ValueError, match="HTTPS"):
        UrllibLLMHTTPTransport().complete(
            endpoint="http://insecure.invalid/v1",
            api_key="k",
            payload={},
            timeout_seconds=1.0,
        )


# ---------------------------------------------------------------------------
# The offline stub: enough to prove the wiring, never enough to be a result
# ---------------------------------------------------------------------------


def test_the_offline_stub_answers_with_the_history_frequency() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import OfflineStubLLMClient

    client = OfflineStubLLMClient()
    method = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="offline-stub-1", cache=False),
        client=client,
    )
    for index, location in enumerate(("table", "table", "table", "sink")):
        prediction = method.observe(_record(index, location))

    # History before the last event was table x3, so the stub should have
    # answered with 1.0 on table -- a real, if weak, predictor.
    assert prediction.predicted_location_probabilities["table"] == pytest.approx(1.0)
    assert prediction.predicted_location_probabilities["sink"] == pytest.approx(0.0)


def test_the_offline_stub_starts_uniform_with_no_history() -> None:
    from cpswm.system.evaluation_operations.project_one_llm_method import OfflineStubLLMClient

    method = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="offline-stub-1"),
        client=OfflineStubLLMClient(),
    )
    prediction = method.observe(_record(0, "table"))
    for value in prediction.predicted_location_probabilities.values():
        assert value == pytest.approx(1 / 3)


def test_the_offline_stub_never_produces_a_schema_failure() -> None:
    """If the stub could not satisfy the contract, the contract would be untestable."""

    from cpswm.system.evaluation_operations.project_one_llm_method import OfflineStubLLMClient

    method = LLMProjectOneMethod(
        locations=LOCATIONS,
        config=LLMMethodConfig(model="offline-stub-1", cache=False),
        client=OfflineStubLLMClient(),
    )
    for index in range(8):
        method.observe(_record(index, LOCATIONS[index % len(LOCATIONS)]))
    assert method.usage().schema_failures == 0
    assert method.usage().fallbacks == 0
