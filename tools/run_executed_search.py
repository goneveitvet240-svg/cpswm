"""Execute every terminal location check and retain its feedback across steps."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from verify_full_mechanism_value import CONDITIONS, ROOT, RecordedState, save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
    _locations,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
    ExecutedLocationSearchState,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    _fairness_comparison_payload,
    _runtime_audit_payload,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    build_task_separated_full_joint_state,
)
from cpswm.system.reproducibility import content_sha256

ARMS = {
    "terminal_only": ("joint", "passive"),
    "current_no_carry": ("joint", "current_rank"),
    "current_rank": ("joint", "current_rank"),
    "joint_habit": ("joint", "habit_rank"),
    "factor_habit": ("factorized", "habit_rank"),
    "recent_id": ("joint", "recent_id"),
}


def dataset_for(condition, seeds):
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(7, 8, 9),
        test_seeds=tuple(seeds),
        max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
        dataset_version="executed-search-feedback-20261011:" + condition,
        sealed_secret="executed-search-feedback-20261011:" + condition,
        **CONDITIONS[condition],
    ).build()


def sources():
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        ROOT / "tools/verify_full_mechanism_value.py",
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def evaluate(dataset, episode, arm):
    engine, policy = ARMS[arm]
    base = build_task_separated_full_joint_state(
        repository_root=ROOT,
        dataset=dataset,
        episode=episode,
        arm=FullJointArm.STATEFUL_FULL_JOINT
        if engine == "joint"
        else FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
    )
    environment = ExecutedD0SearchEnvironment(
        episode,
        _locations(episode),
        lambda step_id: dataset.truth_for(episode.episode_id).truth_by_step[step_id].true_location,
    )
    state = ExecutedLocationSearchState(
        base, environment, policy=policy, carry_terminal_memory=arm != "current_no_carry"
    )
    recorded = RecordedState(state)
    started = perf_counter()
    metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, recorded)
    for row, receipt in zip(recorded.rows, state.search_receipts, strict=True):
        row["active_search"] = receipt
    for row, receipt in zip(recorded.rows, state.execution_receipts, strict=True):
        row["search_execution"] = receipt
    runtime = state.runtime
    return {
        "arm": arm,
        "engine": engine,
        "policy": policy,
        "budget": 2,
        "carry_terminal_memory": arm != "current_no_carry",
        "actions": recorded.rows,
        "metric_pre_completion_uncharged": metric.model_dump(mode="json"),
        "visible_input_sha256": content_sha256(episode),
        "wall_seconds": perf_counter() - started,
        "runtime_audit": _runtime_audit_payload(runtime, episode_id=episode.episode_id),
        "ledger_operations": dict(Counter(r.operation for r in runtime.rgrc_ledger.records)),
        "operator_changes": dict(
            Counter(r.operator.value for r in runtime.operator_flow_receipts if r.changed_state)
        ),
    }


def run(output, condition, phase, seeds):
    output.mkdir(parents=True, exist_ok=False)
    manifest = sources()
    save(
        output / "source.json",
        {
            "files": manifest,
            "python": sys.version,
            "code_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        },
    )
    dataset = dataset_for(condition, seeds)
    split = ProjectTwoDatasetSplit.VALIDATION if phase == "dev" else ProjectTwoDatasetSplit.TEST
    episodes = dataset.visible_episodes(split)
    for i, episode in enumerate(episodes):
        save(output / f"visible-{i}.json", episode.model_dump(mode="json"))
        results = {}
        for arm in ARMS:
            results[arm] = evaluate(dataset, episode, arm)
            save(output / f"run-{i}-{arm}.json", results[arm])
        j, f = (
            results[k]["runtime_audit"]["fairness_receipts"]
            for k in ("joint_habit", "factor_habit")
        )
        assert len(j) == len(f) > 0
        assert all(
            _fairness_comparison_payload(a) == _fairness_comparison_payload(b)
            for a, b in zip(j, f, strict=True)
        )
        puts = [[a["put_back"] for a in results[k]["actions"]] for k in ARMS if k != "factor_habit"]
        assert all(p == puts[0] for p in puts)
        save(
            output / f"truth-{i}.json",
            dataset.truth_for(episode.episode_id).model_dump(mode="json"),
        )
        print(phase, condition, i + 1, "/", len(episodes), "fairness/put checks passed", flush=True)
    assert sources() == manifest
    save(
        output / "completion.json",
        {
            "condition": condition,
            "phase": phase,
            "episode_count": len(episodes),
            "seeds": [7, 8, 9] if phase == "dev" else seeds,
            "actual_runs": len(episodes) * len(ARMS),
            "source_unchanged": True,
            "settings": CONDITIONS[condition],
            "per_missing_step_budget": 2,
            "claim_boundary": "D0_EXECUTED_RETRIEVAL_EXOGENOUS_WORLD_NOT_PHYSICAL_ROBOT",
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--condition", choices=CONDITIONS, required=True)
    p.add_argument("--phase", choices=("dev", "test"), required=True)
    p.add_argument("--seeds", nargs="+", type=int, default=list(range(63001, 63011)))
    args = p.parse_args()
    run(args.output, args.condition, args.phase, args.seeds)
