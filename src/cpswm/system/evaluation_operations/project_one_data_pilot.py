"""Real-data pilot: adapter -> bindings -> arms -> auditable artifacts.

This is the composition layer.  Each piece below it is unit-tested on its own;
what this module owns is the promise that putting them together does not
quietly weaken any of their guarantees, and that what comes out can be read by
someone who does not have this machine.

Three properties it is responsible for.

**Nothing is silently skipped.**  Real logs contain entity triples no arm can
run on -- an object seen in exactly one place has nothing to discriminate
between.  Those are carried into the manifest with a reason, so a pilot that
evaluated four of forty objects can never be read as one that evaluated forty.

**State never crosses a binding.**  Arms are rebuilt per binding, and the
per-binding stream handed to the runner contains only that binding's records.

**``full_as_is`` and ``full_raw_clip`` are a live consistency check.**  Since
the 2026-08-24 source fix those two routes read the same RLS score by different
paths -- raw, versus sigmoid-then-inverted.  They must agree; if real data ever
makes them diverge, the head is not emitting what the harness believes it is,
and every number in the report is suspect.  The report says so explicitly
rather than leaving it to be noticed.

This round is fixed-parameter only.  Selecting per-arm parameters would need its
own sealing protocol, and running one without it is how a pilot turns into an
unfalsifiable result.
"""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cpswm.system.reproducibility import content_sha256

from .dataset_adapters import InMemoryAdapter
from .project_one_dataset import ProjectOneStream, ProjectOneTruthSet
from .project_one_evaluation_path import BYPASSED_MODULES, OFFLINE_METHOD_EVALUATION
from .project_one_llm_method import LLMClient, LLMMethodConfig, LLMProjectOneMethod, LLMUsage
from .project_one_methods import ProjectOneMethod, StepPrediction
from .project_one_metrics import ProjectOneMetrics, paired_step_differences
from .project_one_protocol import (
    PROTOCOL_VERSION,
    CategoricalBOCPDConfig,
    ContextFrequencyConfig,
    PersistenceConfig,
    ProjectOneProtocolConfig,
)
from .project_one_runner import ProjectOneRunner, RunFailure
from .project_one_stream_binding import (
    PILOT_ARM_NAMES,
    CandidatePolicy,
    ProjectOneBindingKey,
    ProjectOneMethodFactory,
    ProjectOneStreamBinding,
    bind_stream,
)

__all__ = [
    "DATA_PILOT_ARMS",
    "LLM_PILOT_ARMS",
    "REFERENCE_ARM",
    "DataPilotReport",
    "PilotArmResult",
    "binding_stream",
    "run_data_pilot",
    "write_pilot_outputs",
]

#: The seven fixed-parameter arms, in report order.
DATA_PILOT_ARMS: tuple[str, ...] = PILOT_ARM_NAMES

#: The LLM pilot is the data pilot plus one arm, so the two are directly
#: comparable on every shared arm.
LLM_PILOT_ARMS: tuple[str, ...] = (*DATA_PILOT_ARMS, "llm_direct")

#: Paired differences are taken against this arm.
REFERENCE_ARM = "full_as_is"

_AGREEMENT_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class PilotArmResult:
    """One arm's result on one binding."""

    binding_id: str
    stream_id: str
    method: str
    predictions: tuple[StepPrediction, ...]
    metrics: ProjectOneMetrics | None
    method_config: Mapping[str, object]
    method_config_hash: str
    elapsed_seconds: float
    peak_memory_bytes: int
    state_size_bytes: int
    snapshot: Mapping[str, object]
    failure: RunFailure | None = None


@dataclass(frozen=True, slots=True)
class DataPilotReport:
    """Everything needed to audit one pilot run."""

    protocol_version: str
    stream_manifests: tuple[Mapping[str, object], ...]
    bindings: tuple[ProjectOneStreamBinding, ...]
    results: tuple[PilotArmResult, ...]
    calibration_consistency: Mapping[str, object]
    arms: tuple[str, ...]
    evaluation_mode: str = OFFLINE_METHOD_EVALUATION
    claim_scope: str = "method_evaluation_only"
    formal_b1_claim_allowed: bool = False
    bypassed_modules: tuple[str, ...] = BYPASSED_MODULES
    llm_usage: Mapping[str, object] | None = None
    environment: Mapping[str, str] = field(default_factory=dict)

    def failures(self) -> tuple[RunFailure, ...]:
        return tuple(item.failure for item in self.results if item.failure is not None)

    def __post_init__(self) -> None:
        if self.evaluation_mode != OFFLINE_METHOD_EVALUATION:
            raise ValueError("the data pilot must be labelled offline_method_evaluation")
        if self.formal_b1_claim_allowed:
            raise ValueError("offline_method_evaluation cannot authorize a formal B1 claim")
        if self.bypassed_modules != BYPASSED_MODULES:
            raise ValueError("offline path must disclose the exact M05-M16 bypass")


def binding_stream(
    binding: ProjectOneStreamBinding, truth: ProjectOneTruthSet
) -> tuple[ProjectOneStream, ProjectOneTruthSet]:
    """Repackage one binding's records as a stream the runner can replay.

    Only this binding's truth travels with it, so an arm cannot be scored
    against another entity's events even if a metric were written carelessly.
    """

    truths = [
        entry for record in binding.records if (entry := truth.get(record.event_id)) is not None
    ]
    adapter = InMemoryAdapter(
        binding.records,
        truths,
        source="binding",
        source_version="0.1",
        preprocessing={"binding_id": binding.binding_id},
        # Carried through, not re-derived.  Dropping it here silently demoted
        # every semi-synthetic run to the habit-truth track: the planted changes
        # were still in the data, but the scorer had been told the stream was
        # unannotated and reported the whole tier as unavailable.
        change_labels=truth.carries_change_labels,
    )
    return adapter.load(stream_id=binding.stream_id, split="pilot")


def _consistency(results: Sequence[PilotArmResult]) -> dict[str, object]:
    """Do the two full-chain readings of the same score still agree?"""

    by_binding: dict[str, dict[str, PilotArmResult]] = {}
    for result in results:
        by_binding.setdefault(result.binding_id, {})[result.method] = result

    worst = 0.0
    compared = 0
    mismatched_decisions = 0
    for arms in by_binding.values():
        left = arms.get("full_as_is")
        right = arms.get("full_raw_clip")
        if left is None or right is None:
            continue
        for first, second in zip(left.predictions, right.predictions, strict=False):
            compared += 1
            worst = max(
                worst,
                abs(first.change_probability - second.change_probability),
                abs(first.habit_signal - second.habit_signal),
            )
            if first.decision is not second.decision:
                mismatched_decisions += 1
    return {
        "reference": "full_as_is",
        "compared_against": "full_raw_clip",
        "compared_steps": compared,
        "max_abs_difference": worst,
        "mismatched_decisions": mismatched_decisions,
        "agree": compared > 0 and worst <= _AGREEMENT_TOLERANCE and mismatched_decisions == 0,
        "note": (
            "Post source fix these two routes read the same RLS score. Divergence means "
            "the head is not emitting what the harness assumes."
        ),
    }


def run_data_pilot(
    *,
    streams: Sequence[tuple[ProjectOneStream, ProjectOneTruthSet]],
    config: ProjectOneProtocolConfig | None = None,
    bocpd_config: CategoricalBOCPDConfig | None = None,
    frequency_config: ContextFrequencyConfig | None = None,
    persistence_config: PersistenceConfig | None = None,
    candidate_locations: Mapping[ProjectOneBindingKey, Sequence[str]] | None = None,
    candidate_policy: CandidatePolicy | None = None,
    llm_config: LLMMethodConfig | None = None,
    llm_client: LLMClient | None = None,
    confirmation_window: int = 3,
    allow_leaky_observed_all: bool = False,
) -> DataPilotReport:
    """Replay every evaluable binding through every arm at fixed parameters.

    The ``llm_direct`` arm appears only when both a config and a client are
    supplied, so a run without model access is a complete seven-arm result
    rather than a partial eight-arm one.
    """

    factory = ProjectOneMethodFactory(
        config=config,
        bocpd_config=bocpd_config,
        frequency_config=frequency_config,
        persistence_config=persistence_config,
    )
    runner = ProjectOneRunner(confirmation_window=confirmation_window)
    with_llm = llm_config is not None and llm_client is not None

    manifests: list[Mapping[str, object]] = []
    all_bindings: list[ProjectOneStreamBinding] = []
    results: list[PilotArmResult] = []
    usage_total = LLMUsage()

    for stream, truth in streams:
        manifests.append(asdict(stream.manifest))
        bindings = bind_stream(
            stream,
            policy=candidate_policy,
            candidate_locations=candidate_locations,
            allow_leaky_observed_all=allow_leaky_observed_all,
        )
        all_bindings.extend(bindings)

        for binding in bindings:
            if not binding.is_evaluable:
                continue
            sub_stream, sub_truth = binding_stream(binding, truth)
            methods: list[ProjectOneMethod] = list(factory.build(binding))
            llm_arm: LLMProjectOneMethod | None = None
            if with_llm:
                assert llm_config is not None and llm_client is not None
                llm_arm = LLMProjectOneMethod(
                    locations=binding.candidate_locations,
                    config=llm_config,
                    client=llm_client,
                    # Same candidate policy as every other arm.  Without this the
                    # LLM arm alone raises on an unseen location and drops out of
                    # the comparison -- silently, as a per-arm failure.
                    open_set=binding.location_source == CandidatePolicy.OPEN_SET.value,
                )
                methods.append(llm_arm)

            for method in methods:
                outcome = runner.run_arm(method, sub_stream, sub_truth)
                results.append(
                    PilotArmResult(
                        binding_id=binding.binding_id,
                        stream_id=binding.stream_id,
                        method=outcome.method,
                        predictions=outcome.predictions,
                        metrics=outcome.metrics,
                        method_config=outcome.method_config,
                        method_config_hash=outcome.method_config_hash,
                        elapsed_seconds=outcome.elapsed_seconds,
                        peak_memory_bytes=outcome.peak_memory_bytes,
                        state_size_bytes=outcome.state_size_bytes,
                        snapshot=outcome.snapshot,
                        failure=outcome.failure,
                    )
                )
            if llm_arm is not None:
                usage_total = _add_usage(usage_total, llm_arm.usage())

    if not results:
        raise ValueError(
            "no evaluable binding in the supplied stream(s): every entity triple was "
            "observed at a single location, so no arm has anything to discriminate between"
        )

    return DataPilotReport(
        protocol_version=PROTOCOL_VERSION,
        stream_manifests=tuple(manifests),
        bindings=tuple(all_bindings),
        results=tuple(results),
        calibration_consistency=_consistency(results),
        arms=LLM_PILOT_ARMS if with_llm else DATA_PILOT_ARMS,
        llm_usage=usage_total.as_dict() if with_llm else None,
        environment={"python": sys.version.split()[0], "platform": platform.platform()},
    )


def _add_usage(left: LLMUsage, right: LLMUsage) -> LLMUsage:
    return LLMUsage(
        calls=left.calls + right.calls,
        cache_hits=left.cache_hits + right.cache_hits,
        retries=left.retries + right.retries,
        timeouts=left.timeouts + right.timeouts,
        schema_failures=left.schema_failures + right.schema_failures,
        fallbacks=left.fallbacks + right.fallbacks,
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_latency_seconds=left.total_latency_seconds + right.total_latency_seconds,
        estimated_cost_usd=left.estimated_cost_usd + right.estimated_cost_usd,
    )


def _prediction_rows(report: DataPilotReport) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for result in report.results:
        for prediction in result.predictions:
            row: dict[str, object] = {
                "binding_id": result.binding_id,
                "stream_id": result.stream_id,
                "method": result.method,
                "method_config_hash": result.method_config_hash,
                "event_id": prediction.event_id,
                "change_probability": prediction.change_probability,
                "predicted_cause": prediction.predicted_cause,
                "predicted_regime_id": prediction.predicted_regime_id,
                "habit_signal": prediction.habit_signal,
                "rls_residual": prediction.rls_residual,
                "decision": prediction.decision.value,
                "predicted_location_probabilities": dict(
                    prediction.predicted_location_probabilities
                ),
            }
            if prediction.trace is not None:
                row["trace"] = asdict(prediction.trace)
            rows.append(row)
    return rows


def _paired_rows(report: DataPilotReport) -> list[Mapping[str, object]]:
    by_binding: dict[str, dict[str, PilotArmResult]] = {}
    for result in report.results:
        by_binding.setdefault(result.binding_id, {})[result.method] = result

    rows: list[Mapping[str, object]] = []
    for binding_id, arms in by_binding.items():
        reference = arms.get(REFERENCE_ARM)
        if reference is None:
            continue
        for method, result in arms.items():
            if method == REFERENCE_ARM:
                continue
            try:
                differences = paired_step_differences(reference.predictions, result.predictions)
            except ValueError:
                continue
            rows.append(
                {
                    "binding_id": binding_id,
                    "stream_id": result.stream_id,
                    "reference": REFERENCE_ARM,
                    "method": method,
                    "differences": [dict(item) for item in differences],
                }
            )
    return rows


def write_pilot_outputs(report: DataPilotReport, output_dir: Path | str) -> dict[str, str]:
    """Write the four artifacts and return their content identities."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    rows = _prediction_rows(report)
    with (output / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
            handle.write("\n")
    predictions_hash = content_sha256(rows)

    arm_configs = {
        result.method: {
            "config_hash": result.method_config_hash,
            "config": dict(result.method_config),
        }
        for result in report.results
    }
    metrics = {
        "protocol_version": report.protocol_version,
        "evaluation_mode": report.evaluation_mode,
        "claim_scope": report.claim_scope,
        "formal_b1_claim_allowed": report.formal_b1_claim_allowed,
        "bypassed_modules": list(report.bypassed_modules),
        "arms": list(report.arms),
        "predictions_sha256": predictions_hash,
        "environment": dict(report.environment),
        "calibration_consistency": dict(report.calibration_consistency),
        "metrics": [
            {**result.metrics.as_dict(), "binding_id": result.binding_id}
            for result in report.results
            if result.metrics is not None
        ],
        "arm_configs": arm_configs,
        "cost": [
            {
                "binding_id": result.binding_id,
                "method": result.method,
                "method_config_hash": result.method_config_hash,
                "elapsed_seconds": result.elapsed_seconds,
                "peak_memory_bytes": result.peak_memory_bytes,
                "state_size_bytes": result.state_size_bytes,
            }
            for result in report.results
        ],
        "llm_usage": dict(report.llm_usage) if report.llm_usage is not None else None,
        "failures": [asdict(failure) for failure in report.failures()],
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (output / "paired.json").write_text(
        json.dumps(_paired_rows(report), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    manifest = {
        "protocol_version": report.protocol_version,
        "evaluation_mode": report.evaluation_mode,
        "claim_scope": report.claim_scope,
        "formal_b1_claim_allowed": report.formal_b1_claim_allowed,
        "bypassed_modules": list(report.bypassed_modules),
        "arms": list(report.arms),
        "environment": dict(report.environment),
        "stream_manifests": [dict(item) for item in report.stream_manifests],
        "bindings": [binding.summary() for binding in report.bindings],
        "evaluated_bindings": sorted({result.binding_id for result in report.results}),
        "predictions_sha256": predictions_hash,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return {
        "predictions_sha256": predictions_hash,
        "manifest_sha256": content_sha256(manifest),
    }
