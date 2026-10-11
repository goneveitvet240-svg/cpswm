"""Frozen development selection and task-separated D0 held-out action comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from verify_full_mechanism_value import CONDITIONS, ROOT, RecordedState, make_state, save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    _fairness_comparison_payload,
    _metric_summary_from_rows,
    _runtime_audit_payload,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    HabitReadoutProfile,
    build_task_separated_full_joint_state,
)
from cpswm.system.reproducibility import content_sha256

GRIDS = {
    "joint": ["v06", "balanced", "slow"],
    "factorized": ["v06", "balanced", "slow"],
    "shared_spine_latest": [0.3, 0.5, 0.7],
    "matched_amg": [0.2, 0.33, 0.5],
}
LABELS = (
    "legacy_joint",
    "split_v06",
    "selected_joint",
    "matched_factorized",
    "selected_factorized",
    "latest",
    "amg",
)


def source_manifest():
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        ROOT / "tools/verify_full_mechanism_value.py",
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def dataset_for(condition, seeds):
    settings = CONDITIONS[condition]
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(7, 8, 9),
        test_seeds=tuple(seeds),
        max_steps_per_episode=settings["scenario_duration_days"],
        dataset_version="task-readout-development-20261011:" + condition,
        sealed_secret="task-readout-development-20261011:" + condition,
        **settings,
    ).build()


class TaskRecordedState(RecordedState):
    def predict(self):
        prediction = super().predict()
        if hasattr(self.state, "task_readout_receipts"):
            receipt = self.state.task_readout_receipts[-1]
            self.rows[-1]["task_readout"] = {
                "prediction_index": receipt.prediction_index,
                "source_snapshot_id": str(receipt.source_snapshot_id),
                "profile": receipt.profile.value,
                "habit_distribution": {str(k): v for k, v in receipt.habit_distribution},
                "put_back": str(receipt.put_back),
                "search_order": list(map(str, receipt.search_order)),
                "native_search_order": list(map(str, receipt.native_search_order)),
                "joint_cold_start": receipt.joint_cold_start,
            }
        return prediction


def evaluate(dataset, episode, engine, parameter):
    if engine in ("joint", "factorized"):
        state = build_task_separated_full_joint_state(
            repository_root=ROOT,
            dataset=dataset,
            episode=episode,
            arm=FullJointArm.STATEFUL_FULL_JOINT
            if engine == "joint"
            else FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
            profile=HabitReadoutProfile(parameter),
        )
    else:
        state = make_state(
            dataset, episode, "stateful_full_joint" if engine == "legacy" else engine, parameter
        )
    state = TaskRecordedState(state)
    started = perf_counter()
    metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, state)
    result = {
        "engine": engine,
        "parameter": parameter,
        "metric": metric.model_dump(mode="json"),
        "visible_input_sha256": content_sha256(episode),
        "actions": state.rows,
        "wall_seconds": perf_counter() - started,
    }
    if hasattr(state, "runtime"):
        runtime = state.runtime
        result.update(
            runtime_audit=_runtime_audit_payload(runtime, episode_id=episode.episode_id),
            ledger_operations=dict(Counter(r.operation for r in runtime.rgrc_ledger.records)),
            operator_changes=dict(
                Counter(r.operator.value for r in runtime.operator_flow_receipts if r.changed_state)
            ),
            particle_count=len(runtime.particles),
        )
    return result


def choose(trials):
    # Stable min retains the predeclared grid order on an exact tie.
    return min(trials, key=lambda row: row["cumulative_action_regret_per_step"])["parameter"]


def configurations(selected):
    return dict(
        zip(
            LABELS,
            [
                ("legacy", "v06"),
                ("joint", "v06"),
                ("joint", selected["joint"]),
                ("factorized", selected["joint"]),
                ("factorized", selected["factorized"]),
                ("shared_spine_latest", selected["shared_spine_latest"]),
                ("matched_amg", selected["matched_amg"]),
            ],
            strict=True,
        )
    )


def run(output, condition, phase, selection_dir=None, seeds=tuple(range(61001, 61011))):
    output.mkdir(parents=True, exist_ok=False)
    sources = source_manifest()
    save(
        output / "source.json",
        {
            "files": sources,
            "python": sys.version,
            "code_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        },
    )
    if phase == "dev":
        dataset = dataset_for(condition, (30,))
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected, tuning = {}, {}
        for engine, grid in GRIDS.items():
            trials = []
            for parameter in grid:
                results = [evaluate(dataset, e, engine, parameter) for e in episodes]
                save(output / f"dev-{engine}-{parameter}.json", results)
                trials.append(
                    {
                        "parameter": parameter,
                        **_metric_summary_from_rows([r["metric"] for r in results]),
                    }
                )
                print(
                    "dev",
                    condition,
                    engine,
                    parameter,
                    trials[-1]["cumulative_action_regret_per_step"],
                    flush=True,
                )
            tuning[engine] = trials
            selected[engine] = choose(trials)
        for i, episode in enumerate(episodes):
            save(output / f"dev-visible-{i}.json", episode.model_dump(mode="json"))
            save(
                output / f"dev-evaluator-truth-{i}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
        save(
            output / "selection.json",
            {
                "condition": condition,
                "development_seeds": [7, 8, 9],
                "selected": selected,
                "trials": tuning,
                "source_files": sources,
            },
        )
        completion = {"phase": phase, "condition": condition, "actual_runs": 36}
    else:
        selection = json.loads((selection_dir / "selection.json").read_text())
        assert selection["condition"] == condition and selection["source_files"] == sources
        assert json.loads((selection_dir / "completion.json").read_text())["source_unchanged"]
        assert all(choose(selection["trials"][e]) == selection["selected"][e] for e in GRIDS)
        save(output / "selection.json", selection)
        selection_hash = hashlib.sha256((output / "selection.json").read_bytes()).hexdigest()
        save(output / "evaluation_start.json", {"selection_sha256": selection_hash, "seeds": seeds})
        configs = configurations(selection["selected"])
        save(output / "configurations.json", configs)
        dataset = dataset_for(condition, seeds)
        summaries = {label: [] for label in LABELS}
        aliases, actual_runs = {}, 0
        comparisons = []
        for i, episode in enumerate(dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)):
            save(output / f"visible-{i}.json", episode.model_dump(mode="json"))
            cache, results = {}, {}
            for label, config in configs.items():
                if config not in cache:
                    result = evaluate(dataset, episode, *config)
                    cache[config] = (label, result)
                    save(output / f"test-{i}-{label}.json", result)
                    actual_runs += 1
                original, result = cache[config]
                aliases[label] = original
                results[label] = result
                summaries[label].append(result["metric"])
            joint, factor = (results[k] for k in ("selected_joint", "matched_factorized"))
            jf, ff = (r["runtime_audit"]["fairness_receipts"] for r in (joint, factor))
            assert len(jf) == len(ff) and all(
                _fairness_comparison_payload(a) == _fairness_comparison_payload(b)
                for a, b in zip(jf, ff, strict=True)
            )
            old, fixed = (results[k] for k in ("legacy_joint", "split_v06"))
            assert [r["put_back"] for r in old["actions"]] == [
                r["put_back"] for r in fixed["actions"]
            ]
            comparisons.append(
                {
                    "matched_fairness": True,
                    "split_preserves_put": True,
                    "joint_factor_put_disagreements": sum(
                        a["put_back"] != b["put_back"]
                        for a, b in zip(joint["actions"], factor["actions"], strict=True)
                    ),
                }
            )
            save(
                output / f"evaluator-truth-{i}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            print("eval", condition, i + 1, len(seeds), comparisons[-1], flush=True)
        save(output / "aliases.json", aliases)
        save(
            output / "summary.json",
            {
                "condition": condition,
                "settings": CONDITIONS[condition],
                "selection": selection["selected"],
                "metrics": {
                    label: _metric_summary_from_rows(rows) for label, rows in summaries.items()
                },
                "paired": comparisons,
            },
        )
        assert (
            hashlib.sha256((output / "selection.json").read_bytes()).hexdigest() == selection_hash
        )
        completion = {
            "phase": phase,
            "condition": condition,
            "test_seeds": seeds,
            "actual_runs": actual_runs,
            "logical_runs": len(LABELS) * len(seeds),
            "selection_sha256": selection_hash,
        }
    assert source_manifest() == sources
    save(
        output / "completion.json",
        {
            **completion,
            "source_unchanged": True,
            "boundary": "D0_DEVELOPMENT_NOT_EMPIRICAL_SENSOR_OR_PAPER_SUPERIORITY",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--phase", choices=("dev", "eval"), required=True)
    parser.add_argument("--selection-dir", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(61001, 61011)))
    args = parser.parse_args()
    if args.phase == "eval" and args.selection_dir is None:
        parser.error("eval requires a sealed --selection-dir")
    run(args.output, args.condition, args.phase, args.selection_dir, tuple(args.seeds))
