"""Unified project-one evaluation runner (阶段 4).

The runner's whole job is to remove every excuse for a difference between arms
except the arm itself.  It therefore:

* replays one stream through each method in the **same order**, event by event;
* gives every method a **fresh instance** and calls :meth:`reset` before the
  first event, so no state leaks between streams;
* saves **every step**, not just an aggregate, into ``predictions.jsonl``;
* records wall-clock time, peak traced memory and a serialized state size per
  arm, so a "win" that costs ten times the compute is visible as such;
* never hands a method the :class:`ProjectOneTruthSet`, and never lets one
  method see another's state;
* on failure, saves the offending event and the arm's snapshot instead of
  discarding the run.
"""

from __future__ import annotations

import json
import platform
import sys
import time
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cpswm.system.reproducibility import content_sha256

from .project_one_dataset import ProjectOneStream, ProjectOneTruthSet
from .project_one_methods import ProjectOneMethod, StepPrediction
from .project_one_metrics import ProjectOneMetrics, compute_metrics
from .project_one_protocol import PROTOCOL_VERSION

__all__ = [
    "ArmRunResult",
    "ProjectOneBenchmarkReport",
    "ProjectOneRunner",
    "RunFailure",
]


@dataclass(frozen=True, slots=True)
class RunFailure:
    """What went wrong, on which event, with the arm's state at that moment."""

    method: str
    stream_id: str
    event_id: str
    error_type: str
    message: str
    snapshot: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ArmRunResult:
    """One arm's complete result on one stream."""

    method: str
    stream_id: str
    predictions: tuple[StepPrediction, ...]
    metrics: ProjectOneMetrics | None
    elapsed_seconds: float
    peak_memory_bytes: int
    state_size_bytes: int
    snapshot: Mapping[str, object]
    #: The exact parameters this arm ran with, and their content identity.
    #: Recorded per arm, not per run, because 阶段 7 tunes each arm separately.
    method_config: Mapping[str, object]
    method_config_hash: str
    failure: RunFailure | None = None


@dataclass(frozen=True, slots=True)
class ProjectOneBenchmarkReport:
    """Everything needed to reproduce and audit one benchmark run."""

    protocol_version: str
    stream_manifests: tuple[Mapping[str, object], ...]
    results: tuple[ArmRunResult, ...]
    environment: Mapping[str, str] = field(default_factory=dict)

    def metrics_table(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            result.metrics.as_dict() for result in self.results if result.metrics is not None
        )

    def failures(self) -> tuple[RunFailure, ...]:
        return tuple(result.failure for result in self.results if result.failure is not None)


def _state_size(snapshot: Mapping[str, object]) -> int:
    return len(json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8"))


def _prediction_row(
    method: str, stream_id: str, prediction: StepPrediction, config_hash: str
) -> Mapping[str, object]:
    row: dict[str, object] = {
        "method": method,
        "stream_id": stream_id,
        "event_id": prediction.event_id,
        "change_probability": prediction.change_probability,
        "predicted_cause": prediction.predicted_cause,
        "predicted_regime_id": prediction.predicted_regime_id,
        "habit_signal": prediction.habit_signal,
        "rls_residual": prediction.rls_residual,
        "decision": prediction.decision.value,
        "predicted_location_probabilities": dict(prediction.predicted_location_probabilities),
        "method_config_hash": config_hash,
    }
    if prediction.trace is not None:
        row["trace"] = asdict(prediction.trace)
    return row


class ProjectOneRunner:
    """Replay streams through arms under identical conditions."""

    def __init__(self, *, confirmation_window: int = 3) -> None:
        self._confirmation_window = confirmation_window

    def run_arm(
        self,
        method: ProjectOneMethod,
        stream: ProjectOneStream,
        truth: ProjectOneTruthSet,
    ) -> ArmRunResult:
        """Replay one stream through one arm, measuring cost as we go."""

        method.reset()
        predictions: list[StepPrediction] = []
        failure: RunFailure | None = None

        tracemalloc.start()
        started = time.perf_counter()
        try:
            for record in stream:
                predictions.append(method.observe(record))
        except Exception as error:
            # A failed arm must be recorded with its context, never silently lost.
            failed_event = (
                stream.records[len(predictions)].event_id
                if len(predictions) < len(stream.records)
                else "<unknown>"
            )
            failure = RunFailure(
                method=method.name,
                stream_id=stream.manifest.stream_id,
                event_id=failed_event,
                error_type=type(error).__name__,
                message=str(error),
                snapshot=dict(method.snapshot()),
            )
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        snapshot = dict(method.snapshot())
        metrics = (
            compute_metrics(
                method=method.name,
                stream_id=stream.manifest.stream_id,
                predictions=predictions,
                truth=truth,
                confirmation_window=self._confirmation_window,
            )
            if predictions and failure is None
            else None
        )
        return ArmRunResult(
            method=method.name,
            stream_id=stream.manifest.stream_id,
            predictions=tuple(predictions),
            metrics=metrics,
            elapsed_seconds=elapsed,
            peak_memory_bytes=peak,
            state_size_bytes=_state_size(snapshot),
            snapshot=snapshot,
            method_config=dict(method.config_payload()),
            method_config_hash=method.config_hash(),
            failure=failure,
        )

    def run(
        self,
        *,
        streams: Sequence[tuple[ProjectOneStream, ProjectOneTruthSet]],
        build_methods: Callable[[], Sequence[ProjectOneMethod]],
    ) -> ProjectOneBenchmarkReport:
        """Replay every stream through a freshly built set of arms.

        ``build_methods`` is a zero-argument callable returning the arms.  It is
        called once per stream so that no arm can carry state across streams,
        which is the cheapest way to make cross-stream leakage impossible rather
        than merely discouraged.
        """

        results: list[ArmRunResult] = []
        manifests: list[Mapping[str, object]] = []
        for stream, truth in streams:
            manifests.append(asdict(stream.manifest))
            for method in build_methods():
                results.append(self.run_arm(method, stream, truth))
        return ProjectOneBenchmarkReport(
            protocol_version=PROTOCOL_VERSION,
            stream_manifests=tuple(manifests),
            results=tuple(results),
            environment={
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            },
        )

    @staticmethod
    def write_predictions(report: ProjectOneBenchmarkReport, path: Path) -> str:
        """Write ``predictions.jsonl`` and return its content hash."""

        path.parent.mkdir(parents=True, exist_ok=True)
        rows: list[Mapping[str, object]] = []
        for result in report.results:
            for prediction in result.predictions:
                rows.append(
                    _prediction_row(
                        result.method,
                        result.stream_id,
                        prediction,
                        result.method_config_hash,
                    )
                )
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
                handle.write("\n")
        return content_sha256(rows)
