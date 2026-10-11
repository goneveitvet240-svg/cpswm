"""Prequential current-location development, heldout and full-adapter validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
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
from cpswm.system.evaluation_operations.structure_two_current_location import (
    CurrentLocationActionState,
    CurrentLocationBelief,
    LocationModelConfig,
    execute_current_search,
    project_search_input,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    _runtime_audit_payload,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    build_task_separated_full_joint_state,
)
from cpswm.system.reproducibility import content_sha256

VIEWS = ("native", "cue_only")
GRID = [(a, d) for a in (0.25, 1.0) for d in (0.9, 1.0)]


def dataset_for(condition, *, dev=False, seeds=None):
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(7, 8, 9),
        test_seeds=tuple(seeds or range(64001, 64011)),
        max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
        dataset_version="current-location-20261011:" + condition,
        sealed_secret="current-location-20261011:" + condition,
        **CONDITIONS[condition],
    ).build()


def source_manifest():
    files = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        ROOT / "tools/score_current_location.py",
        ROOT / "tests/test_current_location.py",
        ROOT / "tools/verify_full_mechanism_value.py",
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def evaluate(dataset, episode, config, view, *, integrate=False):
    head = CurrentLocationBelief(_locations(episode), episode.resident_actor_keys, config)
    environment = ExecutedD0SearchEnvironment(
        episode,
        _locations(episode),
        lambda sid: dataset.truth_for(episode.episode_id).truth_by_step[sid].true_location,
    )
    started = perf_counter()
    extra = {}
    if integrate:
        base = build_task_separated_full_joint_state(
            repository_root=ROOT,
            dataset=dataset,
            episode=episode,
            arm=FullJointArm.STATEFUL_FULL_JOINT,
        )
        state = CurrentLocationActionState(base, environment, head, view=view)
        recorded = RecordedState(state)
        metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, recorded)
        extra = {
            "framework_actions": recorded.rows,
            "framework_metric_pre_execution": metric.model_dump(mode="json"),
            "runtime_audit": _runtime_audit_payload(base.runtime, episode_id=episode.episode_id),
        }
    else:
        for step in episode.steps:
            execute_current_search(
                head, project_search_input(step, head.actors, view=view), environment
            )
    return {
        "config": asdict(config),
        "view": view,
        "integrated": integrate,
        "locations": head.locations,
        "actors": head.actors,
        "visible_sha256": content_sha256(episode),
        "actions": head.records,
        "wall_seconds": perf_counter() - started,
        **extra,
    }


def run(output, phase, freeze=None, seeds=None, conditions=None):
    output.mkdir(parents=True, exist_ok=False)
    manifest = source_manifest()
    save(
        output / "source.json",
        {
            "files": manifest,
            "code_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        },
    )
    configurations = {}
    if phase == "dev":
        for view in VIEWS:
            configurations[view] = {"recent": LocationModelConfig("recent")}
            for kind in ("markov", "joint", "factor"):
                for alpha, decay in GRID:
                    configurations[view][f"{kind}-a{alpha}-d{decay}"] = LocationModelConfig(
                        kind, alpha, decay
                    )
    else:
        frozen = json.loads(freeze.read_text())
        save(output / "freeze.json", frozen)
        for view in VIEWS:
            configurations[view] = {
                k: LocationModelConfig(**v) for k, v in frozen["selected"][view].items()
            }
    index, totals = [], {view: {k: 0 for k in configs} for view, configs in configurations.items()}
    for condition in conditions or CONDITIONS:
        dataset = dataset_for(condition, seeds=seeds)
        split = ProjectTwoDatasetSplit.VALIDATION if phase == "dev" else ProjectTwoDatasetSplit.TEST
        for ep_index, episode in enumerate(dataset.visible_episodes(split)):
            key = f"{condition}-{ep_index}"
            save(output / f"visible-{key}.json", episode.model_dump(mode="json"))
            for view, configs in configurations.items():
                for arm, config in configs.items():
                    result = evaluate(
                        dataset, episode, config, view, integrate=phase == "integrate"
                    )
                    path = f"run-{key}-{view}-{arm}.json"
                    save(output / path, result)
                    totals[view][arm] += sum(row["paid_checks"] for row in result["actions"])
                    index.append(
                        {
                            "condition": condition,
                            "episode": ep_index,
                            "view": view,
                            "arm": arm,
                            "file": path,
                            "visible": f"visible-{key}.json",
                            "truth": f"truth-{key}.json",
                        }
                    )
            save(
                output / f"truth-{key}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            print(phase, condition, ep_index + 1, "completed", flush=True)
    assert source_manifest() == manifest
    save(output / "index.json", index)
    save(output / "totals.json", totals)
    if phase == "dev":
        selected = {}
        for view in VIEWS:
            chosen = {"recent": asdict(LocationModelConfig("recent"))}
            for kind in ("markov", "joint", "factor"):
                keys = [k for k in totals[view] if k.startswith(kind + "-")]
                winner = min(
                    keys,
                    key=lambda k: (
                        totals[view][k],
                        configurations[view][k].alpha,
                        configurations[view][k].decay,
                    ),
                )
                chosen[kind] = asdict(configurations[view][winner])
            chosen["matched_factor"] = {**chosen["joint"], "kind": "factor"}
            selected[view] = chosen
        save(
            output / "freeze.json",
            {
                "selected": selected,
                "dev_totals": totals,
                "source_files_sha256": content_sha256(manifest),
                "seeds": [7, 8, 9],
                "rule": "min actual checks, tie alpha then decay ascending",
            },
        )
    save(
        output / "completion.json",
        {
            "phase": phase,
            "actual_runs": len(index),
            "source_unchanged": True,
            "full_framework": phase == "integrate",
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=("dev", "test", "integrate"), required=True)
    p.add_argument("--freeze", type=Path)
    p.add_argument("--seeds", type=int, nargs="+")
    p.add_argument("--conditions", choices=CONDITIONS, nargs="+")
    args = p.parse_args()
    if args.phase != "dev" and args.freeze is None:
        p.error("test/integrate requires --freeze")
    run(args.output, args.phase, args.freeze, args.seeds, args.conditions)
