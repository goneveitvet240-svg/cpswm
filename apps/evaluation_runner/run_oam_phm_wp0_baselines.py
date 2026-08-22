"""Run the OAM-PHM WP0 baseline floor on the checked-in F0 slice.

WP0 exists so that every later OAM-PHM claim has something to clear.  This
entry point produces that floor as a reproducible artifact, bound to the code
that computed it by the same measured provenance the F0 evaluator records.

Baselines see only the robot-visible ``SymbolicSimulationResult``.  Ground
truth is read here, on the evaluator side, behind the benchmark capability.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    SECTION_9_1_REGISTRY,
    BaselineStatus,
    EvaluationProvenance,
    LocationQuery,
    compare_baselines,
    default_baselines,
)
from cpswm.system.household_memory_benchmark import BenchmarkManifest  # noqa: E402
from cpswm.system.synthetic_routines import (  # noqa: E402
    RoutineGenerationConfig,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (  # noqa: E402
    IncidentalObservationPolicy,
    SymbolicWorldModelSimulator,
)
from cpswm.system.world_model_simulator.benchmark_access import (  # noqa: E402
    issue_benchmark_ground_truth_capability,
)

DEFAULT_BENCHMARK_DIR = REPOSITORY_ROOT / "benchmarks" / "oam_phm_f0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OAM-PHM WP0 baseline floor.")
    parser.add_argument("--benchmark-dir", type=Path, default=DEFAULT_BENCHMARK_DIR)
    parser.add_argument(
        "--lead-hours",
        type=float,
        default=1.0,
        help=(
            "how long after each placement to ask. Detection history is strictly "
            "earlier than the query, so a baseline must predict, not read off."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = args.benchmark_dir.resolve()
    covered_root = (REPOSITORY_ROOT / "benchmarks").resolve()
    if not benchmark_dir.is_relative_to(covered_root):
        raise SystemExit(f"refusing to evaluate assets outside {covered_root}: {benchmark_dir}")

    manifest = BenchmarkManifest.model_validate_json(
        (benchmark_dir / "book_on_sofa_manifest_v0.4.json").read_text(encoding="utf-8")
    )
    routine_config = RoutineGenerationConfig.model_validate_json(
        (benchmark_dir / "book_on_sofa_routine_v0.2.json").read_text(encoding="utf-8")
    )
    policy = IncidentalObservationPolicy.model_validate_json(
        (benchmark_dir / "book_on_sofa_policy_v0.3.json").read_text(encoding="utf-8")
    )

    plan = SyntheticRoutineGenerator().generate(routine_config)
    view = SymbolicWorldModelSimulator().run_privileged(
        plan, policy, capability=issue_benchmark_ground_truth_capability()
    )
    run = view.visible_result

    target = run.scheduled_observation_object_id
    queries: list[LocationQuery] = []
    truth: list[UUID] = []
    for event in view.ground_truth.events:
        if event.object_gt_entity_id != target:
            continue
        queries.append(
            LocationQuery(
                object_instance_id=target,
                query_time=event.event_time + timedelta(hours=args.lead_hours),
            )
        )
        truth.append(event.destination_location_gt_entity_id)

    scores = compare_baselines(default_baselines(), run, tuple(queries), tuple(truth))
    provenance = EvaluationProvenance.measure()

    report = {
        "artifact": "oam-phm-wp0-baseline-floor",
        "benchmark_manifest_id": manifest.manifest_id,
        "benchmark_manifest_sha256": manifest.manifest_sha256,
        "simulation_run_id": str(run.simulation_run_id),
        "simulation_content_sha256": run.simulation_content_sha256,
        "query_count": len(queries),
        "lead_hours": args.lead_hours,
        "scores": [score.model_dump(mode="json") for score in scores],
        "section_9_1_registry": [entry.model_dump(mode="json") for entry in SECTION_9_1_REGISTRY],
        "registry_summary": {
            status.value: sum(1 for entry in SECTION_9_1_REGISTRY if entry.status == status)
            for status in BaselineStatus
        },
        "provenance": provenance.model_dump(mode="json"),
        "scope": (
            "Floor only. No OAM-PHM method is compared here; entries marked "
            "gated_by_review or external_reimplementation_required are not run, "
            "so this artifact must never be read as a completed §9.1 comparison."
        ),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
