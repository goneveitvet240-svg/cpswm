"""Run the OAM-PHM WP0 baseline floor on the checked-in F0 slice.

WP0 exists so that every later OAM-PHM claim has something to clear.  This
entry point produces that floor as a reproducible artifact, bound to the code
that computed it by the same measured provenance the F0 evaluator records.

Baselines see only the robot-visible ``SymbolicSimulationResult``.  Ground
truth is read here, on the evaluator side, behind the benchmark capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    SECTION_9_1_REGISTRY,
    BaselinePerformanceBudget,
    BaselineStatus,
    EvaluationProvenance,
    IdentityKind,
    IdentityMappingContract,
    IdentityMappingEntry,
    LocationQuery,
    LocationTruthChange,
    QueryGridSpec,
    build_expanded_location_query_grid,
    compare_baselines,
    current_o_star_reproduction_manifest,
    current_streak_reproduction_manifest,
    default_baseline_adapters,
    default_baselines,
    score_baseline_distributions,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402
from cpswm.system.household_memory_benchmark import BenchmarkManifest  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402
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
    parser.add_argument(
        "--query-cadence-hours",
        type=float,
        default=1.0,
        help="cadence of the expanded temporal query grid",
    )
    parser.add_argument("--max-queries", type=int, default=10_000)
    parser.add_argument("--max-wall-seconds-per-baseline", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
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

    location_gt_ids = sorted(
        {event.destination_location_gt_entity_id for event in view.ground_truth.events}
    )
    identity_mapping = IdentityMappingContract(
        mapping_version="f0-explicit-shared-namespace@0.1",
        entries=(
            IdentityMappingEntry(
                identity_kind=IdentityKind.OBJECT,
                gt_entity_id=target,
                perceived_track_id=target,
            ),
            *(
                IdentityMappingEntry(
                    identity_kind=IdentityKind.LOCATION,
                    gt_entity_id=location_id,
                    perceived_track_id=location_id,
                )
                for location_id in location_gt_ids
            ),
        ),
    )
    expanded_queries = build_expanded_location_query_grid(
        truth_changes=tuple(
            LocationTruthChange(
                event_time=event.event_time,
                event_group_id=event.gt_event_id,
                object_gt_entity_id=event.object_gt_entity_id,
                location_gt_entity_id=event.destination_location_gt_entity_id,
            )
            for event in view.ground_truth.events
        ),
        object_gt_entity_id=target,
        identity_mapping=identity_mapping,
        split_id="oam-phm-f0-development-grid@0.1",
        source_dataset_sha256=run.simulation_content_sha256,
        truth_source_manifest_sha256=content_sha256(view.ground_truth),
        episode_group_id=run.simulation_run_id,
        household_group_id=run.observation_opportunities[0].metadata.household_id,
        end_time=run.start_time + timedelta(days=run.duration_days),
        spec=QueryGridSpec(
            cadence=timedelta(hours=args.query_cadence_hours),
            lead_time=timedelta(hours=args.lead_hours),
            max_queries=args.max_queries,
        ),
    )
    performance_budget = BaselinePerformanceBudget(
        max_queries=args.max_queries,
        compute_unit="adapter_invocation",
        max_compute_units=args.max_queries,
        wall_time_compliance_seconds=args.max_wall_seconds_per_baseline,
        hardware_profile="local-cpu-unspecified-development-only",
    )
    dual_scores = [
        score_baseline_distributions(
            baseline,
            run,
            expanded_queries,
            identity_mapping,
            performance_budget=performance_budget,
        )
        for baseline in default_baselines()
    ]
    development_search_records = []
    for adapter in default_baseline_adapters():
        trials = []
        for candidate in adapter.candidates():
            score = score_baseline_distributions(
                adapter.build(candidate),
                run,
                expanded_queries,
                identity_mapping,
                performance_budget=performance_budget,
            )
            trials.append((candidate, score.current_mean_negative_log_likelihood))
        selected_candidate, selected_value = min(
            trials, key=lambda item: (item[1], item[0].candidate_id)
        )
        development_search_records.append(
            {
                "status": "development_search_not_split_safe_not_formal_tuning",
                "adapter_version": adapter.adapter_version,
                "objective": "current_nll",
                "selected_candidate": selected_candidate.model_dump(mode="json"),
                "selected_objective_value": selected_value,
                "trials": [
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "objective_value": objective_value,
                    }
                    for candidate, objective_value in trials
                ],
            }
        )
    provenance = EvaluationProvenance.measure()
    external_evidence_module = (
        REPOSITORY_ROOT / "src/cpswm/system/evaluation_operations/oam_phm_external_evidence.py"
    )
    equation_core_sha256 = hashlib.sha256(external_evidence_module.read_bytes()).hexdigest()
    external_manifests = (
        current_o_star_reproduction_manifest(core_artifact_sha256=equation_core_sha256),
        current_streak_reproduction_manifest(reference_core_artifact_sha256=equation_core_sha256),
    )

    report = {
        "artifact": "oam-phm-wp0-baseline-floor",
        "benchmark_manifest_id": manifest.manifest_id,
        "benchmark_manifest_sha256": manifest.manifest_sha256,
        "simulation_run_id": str(run.simulation_run_id),
        "simulation_content_sha256": run.simulation_content_sha256,
        "query_count": len(queries),
        "lead_hours": args.lead_hours,
        "scores": [score.model_dump(mode="json") for score in scores],
        "expanded_query_grid": {
            "query_count": len(expanded_queries.queries),
            "cadence_hours": args.query_cadence_hours,
            "statistical_independence_claim": False,
            "habitual_truth_target": expanded_queries.habitual_truth_target.value,
            "dataset_content_sha256": expanded_queries.dataset_content_sha256,
            "truth_manifest_sha256": expanded_queries.truth_manifest_sha256,
            "group_manifest_sha256": expanded_queries.group_manifest_sha256,
            "episode_cluster_count": len(
                {item.episode_group_id for item in expanded_queries.group_bindings}
            ),
            "household_cluster_count": len(
                {item.household_group_id for item in expanded_queries.group_bindings}
            ),
            "object_cluster_count": len(
                {item.object_group_id for item in expanded_queries.group_bindings}
            ),
            "event_cluster_count": len(
                {item.event_group_id for item in expanded_queries.group_bindings}
            ),
        },
        "identity_mapping": identity_mapping.model_dump(mode="json"),
        "identity_mapping_contract_kind": "f0_exact_bijection_not_b1_d2_identity_resolution",
        "performance_budget": performance_budget.model_dump(mode="json"),
        "dual_distribution_scores": [
            score.model_dump(mode="json", exclude={"resource_usage": {"wall_seconds"}})
            for score in dual_scores
        ],
        "independent_tuning": [],
        "formal_protocol_status": "not_issued_no_disjoint_evaluation_dataset",
        "external_reproduction_readiness": [
            {
                **item.model_dump(mode="json"),
                "manifest_sha256": item.content_sha256,
                "eligible_for_formal_competition": item.eligible_for_formal_competition,
            }
            for item in external_manifests
        ],
        "formal_competition_status": (
            "blocked_external_reproductions_and_full_method_not_complete"
        ),
        "development_parameter_search": development_search_records,
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
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output is not None:
        write_report_atomic(
            rendered + "\n",
            output_path=args.output,
            config_path=benchmark_dir / "book_on_sofa_manifest_v0.4.json",
            repository_root=REPOSITORY_ROOT,
            force=args.force,
        )
    print(rendered)


if __name__ == "__main__":
    main()
