"""Run the method-free benchmark-target gates across all three directions.

Gate A (trivial-rule ceiling) and Gate B (arm distinguishability) never execute
a research method, so this runner cannot move a verdict toward a preferred
result.  Gate B does replay the frozen Structure Two arms, but only to record
what they predict; no endpoint, cost model, or comparison is computed here.

The arm-trace stage is deliberately resumable.  Each arm writes its own cache
file, so a long replay can be run in pieces and finalised later without
recomputing arms that are already on disk.

Usage::

    python -m apps.evaluation_runner.run_task_nontriviality_gates --stage gate-a
    python -m apps.evaluation_runner.run_task_nontriviality_gates \
        --stage arm-traces --arm brainctl_matched
    python -m apps.evaluation_runner.run_task_nontriviality_gates --stage finalize
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations import structure_two_strongest_neighbor_gate as neighbor
from cpswm.system.evaluation_operations.direction_three_oracle_suite import (
    combination_oracle_scenarios,
    default_oracle_scenarios,
)
from cpswm.system.evaluation_operations.online_shift_attribution import (
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from cpswm.system.evaluation_operations.task_nontriviality_adapters import (
    PROJECT_ONE_SHIFT_CAUSE_TARGET,
    PROJECT_TWO_PUT_BACK_TARGET,
    PROJECT_TWO_SEARCH_TARGET,
    collect_arm_prediction_traces,
    project_one_shift_target_streams,
    project_two_target_streams,
)
from cpswm.system.evaluation_operations.task_nontriviality_gates import (
    ArmPredictionTrace,
    run_gate_a,
    run_gate_b,
    summarise_gate_reports,
)
from cpswm.system.reproducibility import content_sha256

CACHE_DIR = Path("tmp/task_nontriviality_gates")
ARTIFACT = Path("artifacts/project_two_v04_development/task_nontriviality_gates_v0_1.json")
PROJECT_ONE_SEEDS = tuple(1000 + 7 * index for index in range(40))


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _structure_two_streams(root: Path) -> dict[str, list[Any]]:
    design = neighbor.load_frozen_neighbor_design(root / neighbor.DEFAULT_MANIFEST)
    collected: dict[str, list[Any]] = {
        PROJECT_TWO_PUT_BACK_TARGET: [],
        PROJECT_TWO_SEARCH_TARGET: [],
    }
    for family in design.families:
        dataset = neighbor._dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(519991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        for target in collected:
            collected[target].extend(
                project_two_target_streams(dataset, target=target, stratum=family.family_id)
            )
    return collected


def _direction_three_signature_report() -> dict[str, Any]:
    """Gate A needs a sampled target; this suite is hand-authored, so report shape.

    The analogue that *is* meaningful for a conformance suite is whether every
    scenario makes a distinct demand.  Two scenarios with the same decision
    signature test the same thing twice.
    """

    scenarios = list(default_oracle_scenarios()) + list(combination_oracle_scenarios())

    def _value(item: Any) -> Any:
        return item.value if hasattr(item, "value") else (None if item is None else str(item))

    signatures: dict[str, list[str]] = {}
    coverage: Counter[str] = Counter()
    for scenario in scenarios:
        digest = content_sha256(
            {
                "decisive": _value(scenario.decisive_dimension),
                "additional": sorted(
                    _value(item) for item in (scenario.additional_decisive_dimensions or ())
                ),
                "initial_belief": _value(scenario.initial_belief),
                "verification": _value(scenario.verification_action),
                "terminal_action": _value(scenario.terminal_action),
                "terminal_outcome": _value(scenario.terminal_outcome),
                "unknown": bool(scenario.true_target_is_unknown),
                "replan": bool(scenario.replan_after_not_found),
                "termination": _value(scenario.expected_termination),
            }
        )
        signatures.setdefault(digest, []).append(scenario.scenario_id)
        if scenario.decisive_dimension is not None:
            coverage[_value(scenario.decisive_dimension)] += 1
        for item in scenario.additional_decisive_dimensions or ():
            coverage[_value(item)] += 1
    collisions = sorted(
        (sorted(ids) for ids in signatures.values() if len(ids) > 1), key=lambda ids: ids[0]
    )
    return {
        "gate": "conformance_suite_signature_report",
        "gate_a_applicable": False,
        "gate_a_inapplicable_reason": (
            "the direction-three oracle suite is a hand-authored deterministic conformance "
            "suite, not a sampled benchmark; trivial-rule error rates computed on it would "
            "have no sampling interpretation"
        ),
        "scenario_count": len(scenarios),
        "distinct_decision_signatures": len(signatures),
        "decisive_dimension_coverage": dict(sorted(coverage.items())),
        "colliding_scenario_groups": collisions,
        "signature_gate_passed": not collisions,
    }


def _run_gate_a_stage(root: Path) -> dict[str, Any]:
    streams = _structure_two_streams(root)
    suite = OnlineShiftSuiteGenerator().generate(OnlineShiftSuiteConfig(seeds=PROJECT_ONE_SEEDS))
    return {
        "structure_two_put_back": run_gate_a(
            streams[PROJECT_TWO_PUT_BACK_TARGET],
            target_name=PROJECT_TWO_PUT_BACK_TARGET,
            target_kind="state_tracking",
        ),
        "structure_two_search": run_gate_a(
            streams[PROJECT_TWO_SEARCH_TARGET],
            target_name=PROJECT_TWO_SEARCH_TARGET,
            target_kind="state_tracking",
        ),
        "structure_one_shift_cause": run_gate_a(
            project_one_shift_target_streams(list(suite.cases)),
            target_name=PROJECT_ONE_SHIFT_CAUSE_TARGET,
            target_kind="classification",
        ),
        "structure_one_generator_seeds": list(PROJECT_ONE_SEEDS),
        "structure_three": _direction_three_signature_report(),
    }


def _run_arm_stage(root: Path, arm_name: str, cache: Path) -> Path:
    design = neighbor.load_frozen_neighbor_design(root / neighbor.DEFAULT_MANIFEST)
    frozen = json.loads(
        (
            root
            / "artifacts/project_two_v04_development"
            / "structure_two_strongest_neighbor_gate_v0_1.json"
        ).read_text(encoding="utf-8")
    )["selected_parameters"]
    arm = neighbor.NeighborArm(arm_name)
    rows: list[tuple[str, tuple[str, ...]]] = []
    for family in design.families:
        dataset = neighbor._dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(519991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        pairs = [
            (
                f"{family.family_id}:{episode.episode_id}",
                (
                    episode,
                    neighbor._state_for_arm(
                        dataset,
                        episode,
                        family,
                        arm,
                        frozen[arm.value],
                        max_physical_verifications=(design.max_physical_verifications_per_episode),
                    ),
                ),
            )
            for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        ]
        rows.extend(collect_arm_prediction_traces([(arm.value, pairs)])[0].episode_predictions)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"arm_{arm.value}.json"
    path.write_text(
        json.dumps({"arm": arm.value, "episode_predictions": [[k, list(v)] for k, v in rows]}),
        encoding="utf-8",
    )
    return path


def _load_traces(cache: Path) -> list[ArmPredictionTrace]:
    traces = []
    for path in sorted(cache.glob("arm_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        traces.append(
            ArmPredictionTrace(
                arm=payload["arm"],
                episode_predictions=tuple(
                    (key, tuple(value)) for key, value in payload["episode_predictions"]
                ),
            )
        )
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("gate-a", "arm-traces", "finalize"), required=True)
    parser.add_argument("--arm", action="append", default=[])
    args = parser.parse_args()
    root = _repository_root()
    cache = root / CACHE_DIR

    if args.stage == "gate-a":
        report = _run_gate_a_stage(root)
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "gate_a.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items()}, indent=1)[:400])
        return

    if args.stage == "arm-traces":
        arms = args.arm or [item.value for item in neighbor.NeighborArm]
        for name in arms:
            print("wrote", _run_arm_stage(root, name, cache))
        return

    gate_a = json.loads((cache / "gate_a.json").read_text(encoding="utf-8"))
    gate_b = run_gate_b(_load_traces(cache))
    payload = summarise_gate_reports(
        {
            "evidence_status": (
                "method-free instrument diagnostic on existing repository targets; "
                "not a method result and not confirmatory evidence"
            ),
            "structure_two_split": "validation seeds only; no sealed holdout was opened",
            "gate_a": gate_a,
            "gate_b": gate_b,
        }
    )
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    (root / ARTIFACT).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("artifact:", ARTIFACT)
    print("content_sha256:", payload["content_sha256"])


if __name__ == "__main__":
    main()
