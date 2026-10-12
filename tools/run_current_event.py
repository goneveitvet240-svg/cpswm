"""Matched full native current-event development and fresh heldout evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from verify_full_mechanism_value import CONDITIONS, ROOT, save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_current_event import (
    CurrentEventActionState,
    CurrentEventRuntime,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.evaluation_operations.structure_two_shared_location import (
    SharedLocationBelief,
    SharedLocationConfig,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    _runtime_audit_payload,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    build_task_separated_full_joint_state,
)
from cpswm.system.reproducibility import content_sha256


def dataset_for(condition, seeds):
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(7, 8),
        test_seeds=tuple(seeds),
        max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
        dataset_version="current-event-20261012:" + condition,
        sealed_secret="current-event-20261012:" + condition,
        **CONDITIONS[condition],
    ).build()


def build(
    dataset, episode, arm, profile="v06", consume_new=True, sampling_method="independent_strata_v1"
):
    original = build_task_separated_full_joint_state(
        repository_root=ROOT,
        dataset=dataset,
        episode=episode,
        arm=FullJointArm(arm),
        profile=profile,
    )
    runtime = CurrentEventRuntime(
        sampling_method=sampling_method,
        arm=original.runtime.arm,
        config=original.runtime.config,
        neural_model=original.runtime.neural_model,
    )
    locations = _locations(episode)
    head = SharedLocationBelief(
        locations, episode.resident_actor_keys, SharedLocationConfig("joint", 0.25, 0.9, 2.0, 2.0)
    )
    env = ExecutedD0SearchEnvironment(
        episode,
        locations,
        lambda sid: dataset.truth_for(episode.episode_id).truth_by_step[sid].true_location,
    )
    return CurrentEventActionState(
        original._state,
        episode,
        runtime,
        profile=original.habit_readout_profile,
        environment=env,
        head=head,
        consume_new=consume_new,
    )


def evaluate(
    dataset, episode, arm, profile="v06", consume_new=True, sampling_method="independent_strata_v1"
):
    state = build(dataset, episode, arm, profile, consume_new, sampling_method)
    start = perf_counter()
    evidence = []
    for index, step in enumerate(episode.steps):
        state.observe(step)
        before = state.runtime._state_sha256()
        state.predict()
        row = state.event_actions[-1]
        row["state_before_search"] = before
        # Save native weights and all factor terms for independent arithmetic.
        evidence.append(
            {
                "observation": asdict(state.runtime._last_observation),
                "weights": [p.posterior_probability for p in state.runtime.particles],
                "placement_actors": [p.world.placement_actor for p in state.runtime.particles],
                "receipts": [
                    r.model_dump(mode="json")
                    for r in state.runtime.importance_revision_receipts[-1]
                ],
                "unresolved": state.runtime.unresolved_probability,
                "fairness": asdict(state.runtime.fairness_receipts[-1]),
            }
        )
        state.feedback(step)
        assert state.runtime.step_index == index + 1
        state.runtime.verify_internal_contracts()
    # Truth opened here for scoring, never supplied to the controller.
    truth = dataset.truth_for(episode.episode_id).truth_by_step
    errors = sum(
        row["put_back"] != str(truth[step.step_id].true_owner_habit_location)
        for step, row in zip(episode.steps, state.event_actions, strict=True)
    )
    return {
        "arm": arm,
        "sampling_method": sampling_method,
        "sampling_receipts": state.runtime.sampling_receipts,
        "profile": profile,
        "consume_new": consume_new,
        "episode_sha256": content_sha256(episode),
        "actions": state.event_actions,
        "native_evidence": evidence,
        "location_revisions": state.runtime.location_revisions,
        "task_readout_actions": [
            {
                "prediction_index": r.prediction_index,
                "put_back": str(r.put_back),
                "search_order": list(map(str, r.search_order)),
            }
            for r in state.task_readout_receipts
        ],
        "location_sources": {str(k): v for k, v in state.runtime.location_sources.items()},
        "native_audit": _runtime_audit_payload(state.runtime, episode_id=episode.episode_id),
        "put_errors": errors,
        "wall_seconds": perf_counter() - start,
    }


def plain(obj):
    # Reuse the project's canonical converter for UUID/enum/dataclass content.
    from cpswm.system.reproducibility import _canonical_value

    return _canonical_value(obj)


def manifest():
    files = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        ROOT / "tools/score_current_event.py",
        ROOT / "tests/test_current_event.py",
        ROOT / "tests/test_current_event_adversarial.py",
        ROOT / "tests/test_current_event_task_receipt.py",
        ROOT / "tools/score_shared_location.py",
        ROOT / "tools/verify_full_mechanism_value.py",
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run(output, phase, freeze=None, seeds=None, conditions=("sparse32", "long64")):
    output.mkdir(parents=True, exist_ok=False)
    sources = manifest()
    save(
        output / "source.json",
        {
            "files": sources,
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        },
    )
    configs = {}
    joint, factor = tuple(a.value for a in FullJointArm)
    if phase == "dev":
        configs = {
            f"{a}-{p}": {"arm": a, "profile": p, "consume_new": True}
            for a in (joint, factor)
            for p in ("v06", "balanced")
        }
    else:
        selection = json.loads(freeze.read_text())["selected"]
        configs = {
            "joint": {"arm": joint, "profile": selection[joint], "consume_new": True},
            "factor": {"arm": factor, "profile": selection[factor], "consume_new": True},
            "matched_factor": {"arm": factor, "profile": selection[joint], "consume_new": True},
            "joint_no_new": {"arm": joint, "profile": selection[joint], "consume_new": False},
            "matched_factor_no_new": {
                "arm": factor,
                "profile": selection[joint],
                "consume_new": False,
            },
        }
    index = []
    totals = dict.fromkeys(configs, 0)
    actual = 0
    for condition in conditions:
        dataset = dataset_for(condition, seeds or (range(66001, 66005)))
        split = ProjectTwoDatasetSplit.VALIDATION if phase == "dev" else ProjectTwoDatasetSplit.TEST
        for i, episode in enumerate(dataset.visible_episodes(split)):
            key = f"{condition}-{i}"
            save(output / f"visible-{key}.json", episode.model_dump(mode="json"))
            save(
                output / f"truth-{key}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            cache = {}
            for label, config in configs.items():
                configkey = tuple(config.values())
                if configkey not in cache:
                    path = f"run-{key}-{label}.json"
                    result = evaluate(dataset, episode, **config)
                    save(output / path, plain(result))
                    cache[configkey] = (path, result["put_errors"])
                    actual += 1
                path, errors = cache[configkey]
                totals[label] += errors
                index.append(
                    {
                        "condition": condition,
                        "episode": i,
                        "label": label,
                        "file": path,
                        "visible": f"visible-{key}.json",
                        "truth": f"truth-{key}.json",
                        "config": config,
                    }
                )
            print(phase, key, "complete", flush=True)
    save(output / "index.json", index)
    save(output / "totals.json", totals)
    if phase == "dev":
        selected = {
            a: min(
                ("v06", "balanced"),
                key=lambda p: (totals[f"{a}-{p}"], ("v06", "balanced").index(p)),
            )
            for a in (joint, factor)
        }
        save(
            output / "freeze.json",
            {
                "selected": selected,
                "dev_totals": totals,
                "source_sha256": content_sha256(sources),
                "rule": "min put errors then v06 before balanced",
            },
        )
    assert sources == manifest()
    save(
        output / "completion.json",
        {"actual_runs": actual, "logical_rows": len(index), "source_unchanged": True},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=["dev", "test"], required=True)
    p.add_argument("--freeze", type=Path)
    p.add_argument("--seeds", type=int, nargs="+")
    p.add_argument("--conditions", nargs="+", default=["sparse32", "long64"])
    args = p.parse_args()
    run(args.output, args.phase, args.freeze, args.seeds, args.conditions)
