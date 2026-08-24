"""Run the project-one pilot with the ``llm_direct`` arm added.

    PYTHONPATH=src python apps/evaluation_runner/run_project_one_llm_pilot.py \
        --input /absolute/path/to/events.jsonl \
        --adapter jsonl \
        --llm-config configs/project_one/llm_baseline.yaml \
        --output artifacts/project_one/llm_pilot

Identical to the data pilot in every respect except the extra arm, so the seven
shared arms are directly comparable between the two runs.

**The only provider implemented today is ``offline_stub``**, a local
deterministic stand-in that answers with the empirical frequency of the history
it is shown.  It exists to prove the wiring -- prompt construction, schema
validation, caching, accounting, metrics -- before a real provider is attached.
A number produced with it is a wiring check, not a language-model baseline, and
the run says so in its own output.  Registering a real provider means adding a
class implementing ``LLMClient`` to ``PROVIDERS`` below.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path

import yaml

from cpswm.system.evaluation_operations.project_one_data_pilot import (
    binding_stream,
    run_data_pilot,
    write_pilot_outputs,
)
from cpswm.system.evaluation_operations.project_one_household_generator import (
    build_household_log,
)
from cpswm.system.evaluation_operations.project_one_llm_method import (
    LLMClient,
    LLMMethodConfig,
    OfflineStubLLMClient,
    OpenAICompatibleLLMClient,
)
from cpswm.system.evaluation_operations.project_one_semi_synthetic import (
    InjectionKind,
    inject_changes,
)
from cpswm.system.evaluation_operations.project_one_stream_binding import (
    OPEN_SET_LOCATION,
    bind_stream,
)
from cpswm.system.evaluation_operations.real_data_adapters import (
    JSONLAdapter,
    UnknownLocationPolicy,
)

ADAPTERS = ("jsonl",)

#: Providers that reach the network.  Running one sends household location
#: history to a third party, so the entry point requires an explicit opt-in and
#: this set is what it checks against.
NETWORK_PROVIDERS = frozenset({"openai_compatible"})

PROVIDER_NAMES = ("offline_stub", "openai_compatible")

#: Fields the config file may set on ``LLMMethodConfig``.  Anything else is a
#: typo or a stale key, and silently ignoring it would mean a run whose config
#: file and behaviour disagree.
_CONFIG_FIELDS = frozenset(
    {
        "model",
        "timeout_seconds",
        "max_attempts",
        "cache",
        "history_window",
        "temperature",
        "change_threshold",
        "prompt_cost_per_1k_usd",
        "completion_cost_per_1k_usd",
    }
)

#: Provider-only keys.  Kept out of ``LLMMethodConfig`` because they describe
#: *where* the model lives, not *what* it is asked -- and because an endpoint in
#: the method config would end up inside ``config_hash`` and therefore inside
#: every artifact, which is the wrong place for deployment detail.
_PROVIDER_FIELDS = frozenset({"endpoint", "api_key_env"})


def _load_llm_config(path: Path) -> tuple[str, LLMMethodConfig, dict[str, str]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a mapping")

    provider = str(payload.pop("provider", "")).strip()
    if provider not in PROVIDER_NAMES:
        raise SystemExit(
            f"unsupported provider {provider!r}; implemented: {sorted(PROVIDER_NAMES)}. "
            "Register a class implementing LLMClient to add one."
        )
    settings = {key: str(payload.pop(key)) for key in list(payload) if key in _PROVIDER_FIELDS}
    unknown = sorted(set(payload) - _CONFIG_FIELDS)
    if unknown:
        raise SystemExit(f"{path} sets unknown field(s) {unknown}")
    return provider, LLMMethodConfig(**payload), settings


def _build_client(provider: str, settings: Mapping[str, str], *, allow_network: bool) -> LLMClient:
    if provider in NETWORK_PROVIDERS and not allow_network:
        raise SystemExit(
            f"provider {provider!r} sends household location history to a third party. "
            "Re-run with --allow-network once that is a decision you have made."
        )

    if provider == "offline_stub":
        client: LLMClient = OfflineStubLLMClient()
    elif provider == "openai_compatible":
        endpoint = settings.get("endpoint", "").strip()
        variable = settings.get("api_key_env", "").strip()
        if not endpoint or not variable:
            raise SystemExit(
                "openai_compatible needs 'endpoint' and 'api_key_env' in the config file"
            )
        # Read from the environment, never from the config file: a key in a
        # config file ends up in git, in a manifest, and in a bug report.
        api_key = os.environ.get(variable, "")
        if not api_key.strip():
            raise SystemExit(
                f"environment variable {variable} is empty or unset. Export your API key "
                f"there (for example: export {variable}=...) and re-run; the key is never "
                "read from the config file and never written to any artifact."
            )
        client = OpenAICompatibleLLMClient(endpoint=endpoint, api_key=api_key)
    else:  # pragma: no cover - guarded by the name check above
        raise SystemExit(f"unhandled provider {provider!r}")

    if not isinstance(client, LLMClient):
        raise SystemExit(f"provider {provider!r} does not implement LLMClient")
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument(
        "--generated",
        action="store_true",
        help="build a multi-household synthetic log instead of reading --input",
    )
    parser.add_argument("--households", type=int, default=3)
    parser.add_argument("--residents", type=int, default=2)
    parser.add_argument("--objects", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--inject",
        nargs="*",
        default=[],
        choices=[item.value for item in InjectionKind],
        help="plant known changes -- this is what turns the run into track two",
    )
    parser.add_argument("--adapter", default="jsonl", choices=list(ADAPTERS))
    parser.add_argument("--truth", type=Path, default=None)
    parser.add_argument(
        "--unknown-location",
        default=UnknownLocationPolicy.REJECT.value,
        choices=[item.value for item in UnknownLocationPolicy],
    )
    parser.add_argument("--llm-config", type=Path, required=True)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help=(
            "permit a provider that sends household location history to a third "
            "party; required for every provider except offline_stub"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    if arguments.adapter != "jsonl":
        raise SystemExit(f"unsupported adapter {arguments.adapter!r}; available: {ADAPTERS}")

    provider, llm_config, settings = _load_llm_config(arguments.llm_config)
    client = _build_client(provider, settings, allow_network=arguments.allow_network)

    adapter = None
    declared_locations = None
    if arguments.generated:
        log = build_household_log(
            households=arguments.households,
            residents_per_household=arguments.residents,
            objects_per_resident=arguments.objects,
            seed=arguments.seed,
        )
        stream, truth = log.stream, log.truth
        declared_locations = dict(log.candidate_locations)
        summary = log.manifest_summary()
        print(f"generated {summary['events']} event(s) across {summary['bindings']} binding(s)")
    else:
        if arguments.input is None:
            raise SystemExit("either --input or --generated is required")
        adapter = JSONLAdapter(
            arguments.input,
            truth_path=arguments.truth,
            unknown_location=UnknownLocationPolicy(arguments.unknown_location),
        )
        stream, truth = adapter.load(stream_id=adapter.discover_stream_id(), split="pilot")

    streams = [(stream, truth)]
    injections: list[dict[str, object]] = []
    if arguments.inject:
        kinds = tuple(InjectionKind(name) for name in arguments.inject)
        planted_streams = []
        for binding in bind_stream(stream, candidate_locations=declared_locations):
            if not binding.is_evaluable:
                continue
            sub_stream, sub_truth = binding_stream(binding, truth)
            try:
                # Plant only inside the vocabulary the binding actually offers.
                # A location outside it is one the operator said does not exist,
                # and re-binding the injected stream would reject it.
                pool = tuple(
                    name for name in binding.candidate_locations if name != OPEN_SET_LOCATION
                )
                planted = inject_changes(
                    sub_stream,
                    sub_truth,
                    kinds=kinds,
                    seed=arguments.seed,
                    location_pool=pool,
                )
            except ValueError:
                planted_streams.append((sub_stream, sub_truth))
                continue
            planted_streams.append((planted.stream, planted.truth))
            injections.extend(
                {"binding_id": binding.binding_id, **item.as_dict()} for item in planted.injections
            )
        if not injections:
            raise SystemExit("no binding was long enough for the requested injection kinds")
        streams = planted_streams
        print(f"planted {len(injections)} change(s) across {len(planted_streams)} binding(s)")

    report = run_data_pilot(
        streams=streams,
        candidate_locations=declared_locations,
        llm_config=llm_config,
        llm_client=client,
    )
    written = write_pilot_outputs(report, arguments.output)

    output: Path = arguments.output
    if adapter is not None:
        (output / "adapter_report.json").write_text(
            json.dumps(adapter.report.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    (output / "llm_provider.json").write_text(
        json.dumps(
            {
                "provider": provider,
                "model": llm_config.model,
                "config_hash": llm_config.config_hash(),
                "is_language_model": provider != "offline_stub",
                "endpoint": settings.get("endpoint", ""),
                "api_key_env": settings.get("api_key_env", ""),
                "note": (
                    "offline_stub answers from history frequency and is a wiring check, "
                    "not a language-model baseline"
                    if provider == "offline_stub"
                    else ""
                ),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    usage = report.llm_usage or {}
    print(f"provider={provider} model={llm_config.model}")
    print(f"arms={len(report.arms)} results={len(report.results)}")
    print(
        f"llm calls={usage.get('calls')} cache_hits={usage.get('cache_hits')} "
        f"retries={usage.get('retries')} timeouts={usage.get('timeouts')} "
        f"schema_failures={usage.get('schema_failures')} fallbacks={usage.get('fallbacks')}"
    )
    print(
        f"llm tokens: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"cost=${usage.get('estimated_cost_usd', 0.0):.6f} "
        f"latency={usage.get('total_latency_seconds', 0.0):.3f}s"
    )
    print(f"predictions sha256 = {written['predictions_sha256']}")
    print(f"wrote {output}/predictions.jsonl, metrics.json, paired.json, manifest.json")
    if provider == "offline_stub":
        print(
            "NOTE: offline_stub is not a language model. These numbers verify the "
            "pipeline; they are not a baseline result and must not be reported as one."
        )
    if report.failures():
        print(f"FAILURES: {len(report.failures())}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
