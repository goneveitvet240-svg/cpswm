"""Run the project-one fixed-threshold benchmark (阶段 4 + 阶段 6 entry point).

    PYTHONPATH=src python apps/evaluation_runner/run_project_one_benchmark.py \
        --output artifacts/project_one/ablation_fixed_threshold

Writes ``predictions.jsonl`` (one row per arm per event), ``metrics.json``
(the per-arm, per-scenario table) and ``paired.json`` (per-event differences
against the full arm, so 阶段 6 can report a paired interval rather than a
difference of averages).

No tuning happens here.  Every arm runs at the same fixed thresholds, which is
what makes the result a statement about the mechanism rather than about a
search budget.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from cpswm.system.evaluation_operations.project_one_methods import build_first_batch
from cpswm.system.evaluation_operations.project_one_metrics import paired_step_differences
from cpswm.system.evaluation_operations.project_one_protocol import (
    ProjectOneProtocolConfig,
    ResidualCalibration,
)
from cpswm.system.evaluation_operations.project_one_runner import (
    ProjectOneBenchmarkReport,
    ProjectOneRunner,
)
from cpswm.system.evaluation_operations.project_one_scenarios import (
    LOCATIONS,
    SCENARIO_NAMES,
    build_all_scenarios,
)

OWNER = "owner"
HOUSEHOLD = "household-1"
OBJECT = "cup-17"


def _build(calibration: ResidualCalibration):  # type: ignore[no-untyped-def]
    config = replace(ProjectOneProtocolConfig(), residual_calibration=calibration)
    return lambda: build_first_batch(
        locations=LOCATIONS,
        owner_id=OWNER,
        household_id=HOUSEHOLD,
        object_id=OBJECT,
        config=config,
    )


def _paired_rows(report: ProjectOneBenchmarkReport) -> list[dict[str, object]]:
    """Per-event differences of every arm against the full arm, per stream."""

    by_stream: dict[str, dict[str, object]] = {}
    for result in report.results:
        by_stream.setdefault(result.stream_id, {})[result.method] = result

    rows: list[dict[str, object]] = []
    for stream_id, arms in by_stream.items():
        reference = arms.get("full")
        if reference is None:
            continue
        for method, result in arms.items():
            if method == "full":
                continue
            try:
                differences = paired_step_differences(
                    reference.predictions,  # type: ignore[attr-defined]
                    result.predictions,  # type: ignore[attr-defined]
                )
            except ValueError:
                continue
            rows.append(
                {"stream_id": stream_id, "method": method, "differences": list(differences)}
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/project_one/ablation_fixed_threshold"),
        help="directory for predictions.jsonl, metrics.json and paired.json",
    )
    parser.add_argument(
        "--calibration",
        choices=[item.value for item in ResidualCalibration],
        default=ResidualCalibration.AS_IS.value,
        help=(
            "as_is reproduces the shipped RLS wiring; logit inverts the head's "
            "sigmoid inside the harness to measure what that wiring costs"
        ),
    )
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIO_NAMES))
    arguments = parser.parse_args()

    calibration = ResidualCalibration(arguments.calibration)
    streams = list(build_all_scenarios(arguments.scenarios))
    report = ProjectOneRunner().run(streams=streams, build_methods=_build(calibration))

    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    predictions_hash = ProjectOneRunner.write_predictions(report, output / "predictions.jsonl")

    metrics = {
        "protocol_version": report.protocol_version,
        "residual_calibration": calibration.value,
        "predictions_sha256": predictions_hash,
        "environment": dict(report.environment),
        "stream_manifests": [dict(manifest) for manifest in report.stream_manifests],
        "metrics": [dict(row) for row in report.metrics_table()],
        "arm_configs": {
            result.method: {
                "config_hash": result.method_config_hash,
                "config": dict(result.method_config),
            }
            for result in report.results
        },
        "cost": [
            {
                "method": result.method,
                "stream_id": result.stream_id,
                "method_config_hash": result.method_config_hash,
                "elapsed_seconds": result.elapsed_seconds,
                "peak_memory_bytes": result.peak_memory_bytes,
                "state_size_bytes": result.state_size_bytes,
            }
            for result in report.results
        ],
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

    failures = report.failures()
    print(f"scenarios={len(streams)} arms={len(report.results) // max(1, len(streams))}")
    print(f"predictions sha256 = {predictions_hash}")
    print(f"wrote {output}/predictions.jsonl, metrics.json, paired.json")
    if failures:
        print(f"FAILURES: {len(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
