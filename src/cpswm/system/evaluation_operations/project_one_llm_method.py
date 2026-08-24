"""``llm_direct``: a general model asked to do the whole job, as a baseline arm.

The question this arm exists to answer is narrow and worth answering: shown the
same history under the same budget, can a general model match the chain?  It is
only an answer if the model is held to the constraints every other arm is held
to, so all of them are enforced here rather than assumed.

**It sees strictly less than it is scored on.**  The prompt is built from events
*before* the current one, plus the current occasion's context -- which is known
before the location is.  The event's own ``observed_location`` never appears.
Inheriting :class:`~.project_one_methods._BaseMethod` makes that structural: the
template calls ``_predict`` before ``_step``, so the arm cannot learn from the
event it is being graded on even by accident.

**Its output is validated, not trusted.**  Models return prose, invent
locations, and emit probabilities summing to 1.4.  Each of those is a schema
failure that costs a retry and, once attempts run out, falls back to a declared
uniform prior.  A pilot that dies eight hours in because one reply was
malformed is not a pilot.

**Every call is accounted for.**  Tokens, latency, retries, cache hits, timeouts
and cost are reported.  "The LLM did better" is not a result if it cost four
hundred times the compute, and that comparison is impossible after the fact.

Two deliberate omissions, stated because they bound what the arm can show.
Absolute timestamps are not in the prompt -- the model sees the context bucket
and the ordered history, which keeps identical situations cache-identical but
denies it any notion of elapsed time.  And the history is truncated to a window,
so a habit that recurs on a longer cycle than the window is invisible to it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Any, Protocol, runtime_checkable
from urllib.error import URLError

from cpswm.system.llm_evidence.adapter import LLMHTTPTransport, UrllibLLMHTTPTransport

from .project_one_dataset import ProjectOneDatasetRecord
from .project_one_methods import StepPrediction, _BaseMethod
from .project_one_protocol import ProjectOneDecision, config_identity, payload_identity

__all__ = [
    "LLM_RESPONSE_SCHEMA",
    "REQUIRED_REPLY_KEYS",
    "FakeLLMClient",
    "LLMClient",
    "LLMCompletion",
    "LLMMethodConfig",
    "LLMProjectOneMethod",
    "LLMRequest",
    "LLMTimeoutError",
    "LLMUsage",
    "OfflineStubLLMClient",
    "OpenAICompatibleLLMClient",
    "PromptVariant",
]


class LLMTimeoutError(RuntimeError):
    """The client gave up waiting.  Retryable, and counted separately."""


@dataclass(frozen=True, slots=True)
class LLMCompletion:
    """One reply, plus what it cost to get."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Everything that determines what the model is asked and how it answers.

    A single object rather than a handful of keyword arguments, because the
    previous signature took only ``prompt`` and ``timeout_seconds``: ``model``
    and ``temperature`` were declared on the config, echoed into
    ``config_payload``, and **never reached the provider**.  Two runs recorded as
    different temperatures were the same run.  Bundling the fields makes that
    class of omission a type error instead of a silent one.

    ``candidate_locations`` travels too.  It is not decoration -- it is the
    answer space, so a run over three candidates and a run over eight are
    different experiments even at identical settings.
    """

    prompt: str
    model: str
    temperature: float
    timeout_seconds: float
    candidate_locations: tuple[str, ...]

    def identity(self) -> str:
        """Content identity, used as the cache key.

        Keyed on every field, not on the prompt alone: caching by prompt would
        serve a temperature-0 answer to a temperature-1 request and make the
        two settings indistinguishable in the results.
        """

        return sha256(
            "\x1f".join(
                (
                    self.model,
                    f"{self.temperature:.6f}",
                    ",".join(self.candidate_locations),
                    self.prompt,
                )
            ).encode("utf-8")
        ).hexdigest()


@runtime_checkable
class LLMClient(Protocol):
    """The only surface the arm touches.

    Injected rather than constructed, so tests never reach the network and a
    provider swap never touches the method.
    """

    def complete(self, request: LLMRequest) -> LLMCompletion: ...


#: Keys a reply must carry.  Named separately from the schema below because the
#: validator iterates them and a ``Mapping[str, object]`` lookup is not iterable
#: to a type checker -- and a cast there would let the two drift apart silently.
REQUIRED_REPLY_KEYS: tuple[str, ...] = (
    "next_location_probabilities",
    "change_probability",
    "cause",
    "confidence",
)

#: The reply contract, kept as data so the prompt and the validator cannot drift
#: apart.  Validation is hand-rolled below rather than pulled from a schema
#: library: the shape is small, and one fewer dependency in the evaluation path
#: is one fewer thing that can change a result between runs.
LLM_RESPONSE_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "required": list(REQUIRED_REPLY_KEYS),
    "properties": {
        "next_location_probabilities": {
            "type": "object",
            "additionalProperties": {"type": "number", "minimum": 0.0},
        },
        "change_probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "cause": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}

_DISTURBANCE_WORDS = ("disturb", "one-off", "one off", "outlier", "temporary", "transient")


class PromptVariant(StrEnum):
    """How much of each event the prompt shows the model.

    ``MINIMAL`` was the first shape: context bucket and location, nothing else.
    It is a weakened arm, and a weakened arm is not a baseline -- the chain arms
    also read ``actor_id`` (which decides whether an event counts toward the
    owner's habit at all) and ``observation_quality`` (which weights it).  An
    LLM denied both is being asked a harder question and then compared as if it
    had been asked the same one.

    ``MATCHED_INPUT`` shows every field the chain arms consume, and nothing they
    do not.  It is the default because the comparison is only meaningful there;
    ``MINIMAL`` is kept so the earlier prompt stays reproducible.
    """

    MINIMAL = "minimal"
    MATCHED_INPUT = "matched_input"


@dataclass(frozen=True, slots=True)
class LLMMethodConfig:
    """Everything that changes what the model is asked, or what it costs."""

    model: str
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    cache: bool = True
    history_window: int = 20
    prompt_variant: PromptVariant = PromptVariant.MATCHED_INPUT
    temperature: float = 0.0
    change_threshold: float = 0.5
    prompt_cost_per_1k_usd: float = 0.0
    completion_cost_per_1k_usd: float = 0.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must be a non-empty identifier")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.history_window < 0:
            raise ValueError("history_window must be non-negative")
        if self.timeout_seconds <= 0.0 or not isfinite(self.timeout_seconds):
            raise ValueError("timeout_seconds must be finite and positive")
        if not 0.0 <= self.change_threshold <= 1.0:
            raise ValueError("change_threshold must be in [0, 1]")

    def config_hash(self) -> str:
        return config_identity(self)


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """What the arm actually spent.  Reported whether or not it won."""

    calls: int = 0
    cache_hits: int = 0
    retries: int = 0
    timeouts: int = 0
    schema_failures: int = 0
    fallbacks: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency_seconds: float = 0.0
    estimated_cost_usd: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "timeouts": self.timeouts,
            "schema_failures": self.schema_failures,
            "fallbacks": self.fallbacks,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_latency_seconds": self.total_latency_seconds,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class _Reply:
    """A validated reply, already restricted to the candidate set."""

    probabilities: dict[str, float]
    change_probability: float
    cause: str
    confidence: float
    is_fallback: bool = False


class FakeLLMClient:
    """Deterministic test double.  Never touches the network.

    ``replies`` may hold strings, :class:`LLMCompletion` objects, or exceptions
    to raise.  The last entry repeats once exhausted, so a test that only cares
    about the first two calls does not have to pad the list.
    """

    def __init__(
        self,
        replies: Sequence[str | LLMCompletion | BaseException],
        *,
        model: str = "fake-1",
    ) -> None:
        if not replies:
            raise ValueError("FakeLLMClient needs at least one reply")
        self.model = model
        self._replies = list(replies)
        self.prompts: list[str] = []
        self.timeouts_seen: list[float] = []
        self.requests: list[LLMRequest] = []
        self.call_count = 0

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        self.prompts.append(request.prompt)
        self.timeouts_seen.append(request.timeout_seconds)
        index = min(self.call_count, len(self._replies) - 1)
        self.call_count += 1
        reply = self._replies[index]
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, LLMCompletion):
            return reply
        return LLMCompletion(text=reply)


class OpenAICompatibleLLMClient:
    """A real provider: any OpenAI-compatible ``/chat/completions`` endpoint.

    The HTTP transport is injected and defaults to the project's existing
    stdlib one, which refuses anything that is not HTTPS.  Tests supply a fake
    transport, so the suite never opens a socket and never needs a key.

    **The API key is passed in, never read from here and never logged.**  The
    caller (the pilot entry point) resolves it from the environment, so a key
    cannot end up in a config file, a manifest, a cache key or a prompt.

    Invoking this sends household location history to a third party.  That is a
    privacy decision belonging to whoever runs the pilot, which is why nothing
    in this repository calls it by default and the entry point requires an
    explicit opt-in.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        transport: LLMHTTPTransport | None = None,
        system_prompt: str = (
            "You predict where a household object will be next. "
            "Reply with one JSON object and nothing else."
        ),
    ) -> None:
        if not endpoint.strip():
            raise ValueError("endpoint is required")
        if not api_key.strip():
            raise ValueError("api_key is required")
        self.endpoint = endpoint
        self._api_key = api_key
        self.transport = transport or UrllibLLMHTTPTransport()
        self.system_prompt = system_prompt

    def complete(self, request: LLMRequest) -> LLMCompletion:
        payload: dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": request.prompt},
            ],
        }
        try:
            response = self.transport.complete(
                endpoint=self.endpoint,
                api_key=self._api_key,
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TimeoutError as error:
            raise LLMTimeoutError(str(error)) from error
        except URLError as error:
            # urllib wraps a socket timeout rather than raising it directly.
            if isinstance(error.reason, TimeoutError):
                raise LLMTimeoutError(str(error)) from error
            raise

        body = response.body
        try:
            text = str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            # A malformed envelope is not a schema failure of the *reply* -- the
            # reply never arrived.  Surfacing it as an empty completion lets the
            # arm's own validation count it and retry, rather than killing a run.
            raise LLMTimeoutError(f"provider returned an unusable envelope: {error}") from error

        usage = body.get("usage") or {}
        return LLMCompletion(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        )


class OfflineStubLLMClient:
    """A local stand-in that lets the LLM pilot run with no provider configured.

    It parses the same prompt a real model would receive and answers with the
    empirical frequency of each location in the shown history.  That makes it a
    *real if weak* predictor rather than noise, so an end-to-end pilot exercises
    the whole path -- validation, caching, accounting, metrics -- and produces
    numbers that are internally consistent.

    It is emphatically **not** a language-model baseline, and any report built
    on it has to say so.  Its purpose is to prove the wiring before a provider
    is wired in, not to answer "can a general model match the chain?".
    """

    model = "offline-stub-1"

    def __init__(self, *, change_probability: float = 0.2) -> None:
        if not 0.0 <= change_probability <= 1.0:
            raise ValueError("change_probability must be in [0, 1]")
        self.change_probability = change_probability
        self.call_count = 0

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.call_count += 1
        prompt = request.prompt
        candidates = [
            line[2:].strip()
            for line in prompt.split("CANDIDATE LOCATIONS", 1)[-1]
            .split("CURRENT CONTEXT", 1)[0]
            .splitlines()
            if line.startswith("- ")
        ]
        history_block = prompt.split("deliberately not shown)", 1)[-1].split("RESPONSE FORMAT", 1)[
            0
        ]
        counts = dict.fromkeys(candidates, 0.0)
        for line in history_block.splitlines():
            parts = line.strip().rsplit(" ", 1)
            if len(parts) == 2 and parts[1] in counts:
                counts[parts[1]] += 1.0

        total = sum(counts.values())
        if total <= 0.0 and candidates:
            counts = dict.fromkeys(candidates, 1.0)
            total = float(len(candidates))
        probabilities = {name: value / total for name, value in counts.items()} if total else {}
        text = json.dumps(
            {
                "next_location_probabilities": probabilities,
                "change_probability": self.change_probability,
                "cause": "stable",
                "confidence": 0.5,
            }
        )
        return LLMCompletion(
            text=text,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
        )


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[-1]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")]
    return body.strip()


class LLMProjectOneMethod(_BaseMethod):
    """One LLM call per event, held to the same rules as every other arm."""

    def __init__(
        self,
        *,
        locations: Sequence[str],
        config: LLMMethodConfig,
        client: LLMClient,
        open_set: bool = False,
    ) -> None:
        super().__init__("llm_direct", locations, open_set=open_set)
        self.config = config
        self.client = client
        self._reset_state()

    # -- lifecycle ---------------------------------------------------------

    def _reset_state(self) -> None:
        self._history: list[tuple[str, str, str, float, datetime]] = []
        self._cache: dict[str, _Reply] = {}
        self._pending: _Reply | None = None
        self._usage = LLMUsage()

    def usage(self) -> LLMUsage:
        return self._usage

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "llm_direct",
            "model": self.config.model,
            "history_window": self.config.history_window,
            "prompt_variant": self.config.prompt_variant.value,
            "max_attempts": self.config.max_attempts,
            "timeout_seconds": self.config.timeout_seconds,
            "temperature": self.config.temperature,
            "change_threshold": self.config.change_threshold,
            "cache": self.config.cache,
            "locations": list(self.locations),
        }

    def config_hash(self) -> str:
        """Identity of :meth:`config_payload`, candidate set included.

        Returning ``self.config.config_hash()`` -- as this did -- omits the
        candidate locations, so two bindings with different answer spaces
        reported the same identity.  Under the candidate-policy work that is no
        longer a nicety: the policy changes the answer space, and a hash that
        cannot see it would let two different experiments collide.
        """

        return payload_identity(self.config_payload())

    def snapshot(self) -> Mapping[str, object]:
        return {
            **super().snapshot(),
            "history_length": len(self._history),
            "cache_entries": len(self._cache),
            "llm_calls": self._usage.calls,
            "llm_cache_hits": self._usage.cache_hits,
            "llm_schema_failures": self._usage.schema_failures,
            "estimated_cost_usd": self._usage.estimated_cost_usd,
        }

    # -- prompting ---------------------------------------------------------

    def _prompt(self, event: ProjectOneDatasetRecord) -> str:
        window = self._history[-self.config.history_window :] if self.config.history_window else []
        if self.config.prompt_variant is PromptVariant.MATCHED_INPUT:
            # Relative, never absolute: the chain arms consume elapsed time (the
            # router is handed each event's timestamp), but an absolute date
            # would also make every prompt unique and defeat the cache without
            # telling the model anything it can use.
            lines = []
            previous: datetime | None = None
            for context, location, actor, quality, stamp in window:
                gap = 0.0 if previous is None else (stamp - previous).total_seconds() / 86400.0
                previous = stamp
                lines.append(
                    f"+{gap:.2f}d {context} actor={actor} quality={quality:.2f} {location}"
                )
            history = "\n".join(lines)
            since_last = (
                0.0 if previous is None else (event.timestamp - previous).total_seconds() / 86400.0
            )
            current_extra: tuple[str, ...] = (
                f"observation_quality={event.observation_quality:.2f}",
                f"days_since_previous_observation={since_last:.2f}",
            )
        else:
            history = "\n".join(f"{context} {location}" for context, location, _a, _q, _t in window)
            current_extra = ()
        return "\n".join(
            (
                "TASK",
                "You track where one household object usually ends up. Given the ordered",
                "history of past occasions and the context of the next occasion, predict",
                "where the object will be, and how likely it is that the underlying habit",
                "has changed.",
                "",
                "CANDIDATE LOCATIONS",
                *(f"- {name}" for name in self.locations),
                "",
                "CURRENT CONTEXT",
                f"context_key={event.context_key}",
                f"context_value={event.context_value:.4f}",
                f"actor={event.actor_id}",
                f"object={event.object_id}",
                *current_extra,
                "",
                f"HISTORY (oldest first, at most {self.config.history_window} past occasions;",
                "the current occasion is deliberately not shown)",
                history if history else "(none yet)",
                "",
                "RESPONSE FORMAT",
                "Reply with one JSON object and nothing else:",
                '{"next_location_probabilities": {"<location>": <number>, ...},',
                ' "change_probability": <number between 0 and 1>,',
                ' "cause": "stable" | "short_term_disturbance" | "habit_change"'
                ' | "insufficient_evidence",',
                ' "confidence": <number between 0 and 1>}',
                "Cover every candidate location above; the probabilities must sum to 1.",
            )
        )

    # -- validation --------------------------------------------------------

    def _validate(self, text: str) -> _Reply:
        """Parse and check one reply, or raise :class:`ValueError`."""

        payload = json.loads(_strip_fence(text))
        if not isinstance(payload, dict):
            raise ValueError("reply is not a JSON object")
        for name in REQUIRED_REPLY_KEYS:
            if name not in payload:
                raise ValueError(f"reply is missing {name!r}")

        raw = payload["next_location_probabilities"]
        if not isinstance(raw, dict):
            raise ValueError("next_location_probabilities must be an object")
        unknown = sorted(set(raw) - set(self.locations))
        if unknown:
            raise ValueError(f"reply invents location(s) {unknown}")

        probabilities: dict[str, float] = {}
        for name in self.locations:
            value = raw.get(name, 0.0)
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"probability for {name!r} is not a number")
            if not isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"probability for {name!r} must be finite and non-negative")
            probabilities[name] = float(value)

        for name in ("change_probability", "confidence"):
            value = payload[name]
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{name} is not a number")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")

        cause = payload["cause"]
        if not isinstance(cause, str) or not cause.strip():
            raise ValueError("cause must be a non-empty string")

        return _Reply(
            probabilities=_normalize(probabilities),
            change_probability=float(payload["change_probability"]),
            cause=cause,
            confidence=float(payload["confidence"]),
        )

    def _fallback(self) -> _Reply:
        """A declared uniform prior, so an exhausted arm still reports honestly."""

        uniform = 1.0 / len(self.locations)
        return _Reply(
            probabilities=dict.fromkeys(self.locations, uniform),
            change_probability=0.0,
            cause=ProjectOneDecision.INSUFFICIENT_EVIDENCE.value,
            confidence=0.0,
            is_fallback=True,
        )

    # -- the call ----------------------------------------------------------

    def _ask(self, prompt: str) -> _Reply:
        request = LLMRequest(
            prompt=prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            timeout_seconds=self.config.timeout_seconds,
            candidate_locations=self.locations,
        )
        key = request.identity()
        if self.config.cache and key in self._cache:
            self._usage = replace_usage(self._usage, cache_hits=self._usage.cache_hits + 1)
            return self._cache[key]

        for attempt in range(self.config.max_attempts):
            if attempt:
                self._usage = replace_usage(self._usage, retries=self._usage.retries + 1)
            started = time.perf_counter()
            try:
                completion = self.client.complete(request)
            except LLMTimeoutError:
                self._usage = replace_usage(
                    self._usage,
                    calls=self._usage.calls + 1,
                    timeouts=self._usage.timeouts + 1,
                    total_latency_seconds=(
                        self._usage.total_latency_seconds + (time.perf_counter() - started)
                    ),
                )
                continue
            self._account(completion, time.perf_counter() - started)
            try:
                reply = self._validate(completion.text)
            except (ValueError, json.JSONDecodeError):
                self._usage = replace_usage(
                    self._usage, schema_failures=self._usage.schema_failures + 1
                )
                continue
            if self.config.cache:
                self._cache[key] = reply
            return reply

        self._usage = replace_usage(self._usage, fallbacks=self._usage.fallbacks + 1)
        return self._fallback()

    def _account(self, completion: LLMCompletion, elapsed: float) -> None:
        prompt_tokens = self._usage.prompt_tokens + completion.prompt_tokens
        completion_tokens = self._usage.completion_tokens + completion.completion_tokens
        self._usage = replace_usage(
            self._usage,
            calls=self._usage.calls + 1,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_latency_seconds=self._usage.total_latency_seconds + elapsed,
            estimated_cost_usd=(
                prompt_tokens / 1000.0 * self.config.prompt_cost_per_1k_usd
                + completion_tokens / 1000.0 * self.config.completion_cost_per_1k_usd
            ),
        )

    # -- method surface ----------------------------------------------------

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        self._pending = self._ask(self._prompt(event))
        return dict(self._pending.probabilities)

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        reply = self._pending or self._fallback()
        self._pending = None
        decision = self._decide(reply)
        self._history.append(
            (
                event.context_key,
                event.observed_location,
                event.actor_id,
                event.observation_quality,
                event.timestamp,
            )
        )
        return StepPrediction(
            event_id=event.event_id,
            predicted_location_probabilities=dict(prior),
            change_probability=reply.change_probability,
            predicted_cause=decision.value,
            predicted_regime_id=None,
            habit_signal=reply.change_probability,
            rls_residual=None,
            decision=decision,
        )

    def _decide(self, reply: _Reply) -> ProjectOneDecision:
        """Project a free-text cause onto the frozen four-class space.

        The model is allowed to say anything; the protocol is not.  Anything
        that does not clearly read as a transient episode becomes a habit change
        once the threshold is crossed, which is the conservative reading -- it
        counts against the arm on the false-alarm metrics rather than for it.
        """

        if reply.is_fallback:
            return ProjectOneDecision.INSUFFICIENT_EVIDENCE
        if reply.change_probability < self.config.change_threshold:
            return ProjectOneDecision.STABLE
        lowered = reply.cause.strip().lower()
        if lowered == ProjectOneDecision.INSUFFICIENT_EVIDENCE.value:
            return ProjectOneDecision.INSUFFICIENT_EVIDENCE
        if lowered == ProjectOneDecision.SHORT_TERM_DISTURBANCE.value or any(
            word in lowered for word in _DISTURBANCE_WORDS
        ):
            return ProjectOneDecision.SHORT_TERM_DISTURBANCE
        return ProjectOneDecision.HABIT_CHANGE


def _normalize(probabilities: Mapping[str, float]) -> dict[str, float]:
    """Rescale to sum 1, falling back to uniform when the model gave all zeros."""

    total = sum(probabilities.values())
    if total <= 0.0:
        uniform = 1.0 / len(probabilities)
        return dict.fromkeys(probabilities, uniform)
    return {name: value / total for name, value in probabilities.items()}


def replace_usage(
    usage: LLMUsage,
    *,
    calls: int | None = None,
    cache_hits: int | None = None,
    retries: int | None = None,
    timeouts: int | None = None,
    schema_failures: int | None = None,
    fallbacks: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_latency_seconds: float | None = None,
    estimated_cost_usd: float | None = None,
) -> LLMUsage:
    """Return ``usage`` with the named counters replaced.

    Spelled out rather than routed through ``**kwargs`` so a typo in a counter
    name is a type error here instead of a silently dropped increment in the
    cost report.
    """

    return LLMUsage(
        calls=usage.calls if calls is None else calls,
        cache_hits=usage.cache_hits if cache_hits is None else cache_hits,
        retries=usage.retries if retries is None else retries,
        timeouts=usage.timeouts if timeouts is None else timeouts,
        schema_failures=(usage.schema_failures if schema_failures is None else schema_failures),
        fallbacks=usage.fallbacks if fallbacks is None else fallbacks,
        prompt_tokens=usage.prompt_tokens if prompt_tokens is None else prompt_tokens,
        completion_tokens=(
            usage.completion_tokens if completion_tokens is None else completion_tokens
        ),
        total_latency_seconds=(
            usage.total_latency_seconds if total_latency_seconds is None else total_latency_seconds
        ),
        estimated_cost_usd=(
            usage.estimated_cost_usd if estimated_cost_usd is None else estimated_cost_usd
        ),
    )
