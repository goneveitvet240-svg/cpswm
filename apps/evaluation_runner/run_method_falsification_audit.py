"""Run the frozen cross-structure method falsification gate.

The default run is intentionally useful even before formal submissions exist:
it emits the complete opponent registry, blocks every unsupported paper claim,
and summarizes nearby diagnostic artifacts without promoting them to formal
head-to-head evidence.  A later run may ingest sealed ``MethodEvidenceSubmission``
records through ``--submissions``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.method_falsification import (  # noqa: E402
    MethodEvidenceSubmission,
    current_method_falsification_registry,
    evaluate_registry,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402

DEFAULT_OUTPUT = REPOSITORY_ROOT / "output/method_falsification/current_method_audit_v0_1.json"
DEFAULT_STRUCTURE_TWO = (
    REPOSITORY_ROOT / "output/method_falsification/structure_two_d0_multiseed_v0_3.json"
)
DEFAULT_STRUCTURE_THREE = (
    REPOSITORY_ROOT
    / "output/method_falsification/structure_three_controlled_noise_30seed_v0_1.json"
)
DEFAULT_OAM_PHM = REPOSITORY_ROOT / "output/method_falsification/oam_phm_wp0_floor_v0_1.json"
DEFAULT_STRUCTURE_ONE = (
    REPOSITORY_ROOT / "output/method_falsification/structure_one_mechanism_tests_v0_1.xml"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _structure_two_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    benchmark = payload["benchmark"]
    wanted_methods = {
        "project_two_full_feedback_loop",
        "damen_hogg_amg_matched_open_world",
        "full_rerun_without_reversible_revision",
    }
    wanted_metrics = {
        "cumulative_action_regret",
        "owner_habit_contamination",
        "incorrect_statistic_recovery_cost",
    }
    metrics = [
        item
        for item in benchmark["aggregate_metrics"]
        if item["method"] in wanted_methods and item["metric"] in wanted_metrics
    ]
    amg_regret = next(
        item
        for item in metrics
        if item["method"] == "damen_hogg_amg_matched_open_world"
        and item["metric"] == "cumulative_action_regret"
    )
    return {
        "scope": "structure_two",
        "artifact_path": str(path.relative_to(REPOSITORY_ROOT)),
        "artifact_sha256": _sha256(path),
        "evidence_role": "adverse_development_evidence_not_formal_registry_submission",
        "episode_count": payload["data_quality"]["episode_count"],
        "validation_episode_count": len(benchmark["validation_episode_ids"]),
        "sealed_test_episode_count": len(benchmark["sealed_test_episode_ids"]),
        "metrics": metrics,
        "adverse_findings": (
            {
                "candidate": "project_two_full_feedback_loop",
                "opponent": "damen_hogg_amg_matched_open_world",
                "metric": "cumulative_action_regret",
                "oriented_candidate_minus_opponent_effect": amg_regret[
                    "paired_difference_vs_project_two"
                ],
                "confidence_interval_95": amg_regret["confidence_interval_95"],
                "interpretation": "candidate_is_clearly_worse_on_this_development_run",
            },
        ),
        "scientific_status": benchmark["scientific_status"],
        "superiority_supported": benchmark["superiority_supported"],
        "formal_blockers": benchmark["paper_level_gate_failures"],
        "why_not_promoted": (
            "The run predates a complete per-route sealed submission and does not cover "
            "every frozen route-specific scenario and strongest opponent. Its AMG loss is "
            "still reported as adverse evidence."
        ),
    }


def _structure_one_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = root.findall("testsuite")
    return {
        "scope": "structure_one",
        "artifact_path": str(path.relative_to(REPOSITORY_ROOT)),
        "artifact_sha256": _sha256(path),
        "evidence_role": "mechanism_regression_not_seeded_action_comparison",
        "test_count": sum(int(item.attrib.get("tests", "0")) for item in suites),
        "failure_count": sum(int(item.attrib.get("failures", "0")) for item in suites),
        "error_count": sum(int(item.attrib.get("errors", "0")) for item in suites),
        "mechanism_finding": {
            "candidate_evidence_multiplicity": 1.0,
            "additive_baseline_evidence_multiplicity": 3.0,
            "action_claim": "not_measured",
        },
        "why_not_promoted": (
            "The regression establishes contract behavior, including evidence "
            "multiplicity, mobility axes, and placement authority. It has no sealed "
            "household-level action comparison against every registered opponent."
        ),
    }


def _structure_three_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    selected = [
        item
        for item in payload["aggregates"]
        if item["arm_id"] in {"combined_sensing_noise", "visual_missing"}
        and item["severity"] in {0.5, 0.75}
    ]
    identity_strata = [
        item
        for item in payload["scenario_strata"]
        if item["arm_id"] == "visual_missing"
        and item["scenario_id"] == "identity_truth_probe"
        and item["severity"] in {0.5, 0.75}
    ]
    return {
        "scope": "structure_three",
        "artifact_path": str(path.relative_to(REPOSITORY_ROOT)),
        "artifact_sha256": _sha256(path),
        "evidence_role": "robustness_diagnostic_not_direct_opponent_comparison",
        "case_count": payload["case_count"],
        "stochastic_seeds": payload["stochastic_seed_values"],
        "selected_aggregates": selected,
        "identity_visual_missing_strata": identity_strata,
        "why_not_promoted": (
            "Controlled noise attacks the observation channels but does not run the "
            "registered top-1 parse, self-consistency, state-estimation, conformal, "
            "hazard, or learned-unknown direct opponents on embodied action utility."
        ),
    }


def _oam_phm_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    return {
        "scope": "oam_phm",
        "artifact_path": str(path.relative_to(REPOSITORY_ROOT)),
        "artifact_sha256": _sha256(path),
        "evidence_role": "baseline_floor_not_full_method_comparison",
        "query_count": payload["expanded_query_grid"]["query_count"],
        "independent_cluster_counts": {
            key: payload["expanded_query_grid"][key]
            for key in (
                "episode_cluster_count",
                "household_cluster_count",
                "object_cluster_count",
                "event_cluster_count",
            )
        },
        "dual_distribution_scores": payload["dual_distribution_scores"],
        "formal_competition_status": payload["formal_competition_status"],
        "external_reproduction_readiness": [
            {
                "method": item["method"],
                "readiness": item["readiness"],
                "eligible_for_formal_competition": item["eligible_for_formal_competition"],
            }
            for item in payload["external_reproduction_readiness"]
        ],
        "why_not_promoted": payload["scope"],
    }


def _supporting_runs() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for path, loader in (
        (DEFAULT_STRUCTURE_ONE, _structure_one_summary),
        (DEFAULT_STRUCTURE_TWO, _structure_two_summary),
        (DEFAULT_STRUCTURE_THREE, _structure_three_summary),
        (DEFAULT_OAM_PHM, _oam_phm_summary),
    ):
        if path.exists():
            summaries.append(loader(path))
    return summaries


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submissions",
        type=Path,
        help="JSON array of sealed MethodEvidenceSubmission records",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    registry = current_method_falsification_registry()
    submissions: tuple[MethodEvidenceSubmission, ...] = ()
    if args.submissions is not None:
        raw = json.loads(args.submissions.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("submissions file must contain a JSON array")
        submissions = tuple(MethodEvidenceSubmission.model_validate(item) for item in raw)
    audit = evaluate_registry(registry, submissions)
    report = {
        "schema_name": "cpswm.MethodFalsificationExecutionReport",
        "schema_version": "0.1.0",
        "registry": {
            **registry.model_dump(mode="json"),
            "registry_sha256": registry.registry_sha256,
        },
        "formal_audit": {
            **audit.model_dump(mode="json"),
            "decision_counts": {
                decision.value: count for decision, count in audit.decision_counts.items()
            },
        },
        "supporting_runs": _supporting_runs(),
        "interpretation_rule": (
            "Supporting runs are never promoted automatically. Only a sealed submission "
            "bound to the preregistration hash can change a method decision."
        ),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    write_report_atomic(
        rendered + "\n",
        output_path=args.output,
        config_path=args.submissions or Path(__file__),
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "registry_sha256": registry.registry_sha256,
                "decision_counts": report["formal_audit"]["decision_counts"],
                "supporting_run_count": len(report["supporting_runs"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
