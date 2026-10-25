"""Frozen fresh-seed replication; truth released only after all public decisions."""

import argparse
import gzip
import hashlib
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from multiprocessing import get_context
from pathlib import Path

from run_matched_value import (
    CONDITIONS,
    NATIVE,
    CommitBarrier,
    PublicCatalogueAdapter,
    action_payload,
    make_state,
    save,
    score,
    state_audit,
)
from run_memory_action import read_selection_archive
from synergy_runtime import PosteriorParentRuntime

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations.structure_two_memory_action import (
    MemoryActionRuntime,
    owner_habit_readout,
)
from cpswm.system.reproducibility import _canonical_value, content_sha256

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/reviews/pc_a/reliability_net_benefit_2026-10-25"


def owner_trace(runtime):
    obs = runtime._last_observation
    locations = obs.known_location_ids
    uniform = dict.fromkeys(locations, 1 / len(locations))
    particles = []
    for p in runtime.particles:
        w = p.world
        cells = []
        for (actor, regime), cell in sorted(w.rb_cells.items()):
            if actor != obs.owner_actor_key:
                continue
            cells.append(
                {
                    "regime": regime,
                    "active": regime == w.active_regime,
                    "retired": regime in w.retired_regimes,
                    "cell": asdict(cell),
                    "cell_sha256": content_sha256(cell),
                    "distribution": {
                        str(k): v
                        for k, v in cell.combined_location_distribution(locations, uniform).items()
                    },
                }
            )
        particles.append(
            {
                "particle": str(w.typed_state.particle_id),
                "weight": p.posterior_probability,
                "actor": w.placement_actor,
                "active_regime": w.active_regime,
                "cells": cells,
            }
        )
    return {
        "owner": obs.owner_actor_key,
        "locations": list(map(str, locations)),
        "regime_evidence_available": getattr(obs, "regime_evidence_available", None),
        "particles": particles,
    }


def build_dataset(condition, seeds):
    return PublicCatalogueAdapter(
        validation_seeds=(7, 8, 9),
        test_seeds=tuple(seeds),
        max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
        dataset_version="mechanism-value-development-20261011:" + condition,
        sealed_secret="mechanism-value-development-20261011:" + condition,
        **CONDITIONS[condition],
    ).build()


def states_for(episode, condition, archive):
    states = {}
    for arm in NATIVE:
        for mode in ("parent_only", "owner_missing"):
            state = make_state(episode, arm)
            r = state.runtime
            cls = PosteriorParentRuntime if mode == "parent_only" else MemoryActionRuntime
            state.runtime = cls(arm=r.arm, config=r.config, neural_model=r.neural_model)
            states[arm + "/" + mode] = state
    for name in ("latest_owner", "matched_amg"):
        choice = archive[condition + "/selection.json"]["methods"][name]
        parameter = choice["trials"][choice["selected_index"]]["parameter"]
        states[name] = make_state(episode, name, parameter)
    return states


def run_episode(dataset, episode, condition, seed, archive, limit=None):
    states = states_for(episode, condition, archive)
    for index, step in enumerate(episode.steps[:limit]):
        start = time.monotonic()
        barrier = CommitBarrier(states, content_sha256(step))
        actions, readouts, distributions, traces = {}, {}, {}, {}
        for name, state in states.items():
            state.observe(step.model_copy(deep=True))
            actions[name] = action_payload(state.predict(), episode.known_location_ids)
            barrier.commit(name, content_sha256(step), actions[name])
            if "/" in name:
                readouts[name] = owner_habit_readout(state.runtime)[1]
                distributions[name] = {
                    str(k): v for k, v in state.task_readout_receipts[-1].habit_distribution
                }
                traces[name] = owner_trace(state.runtime)
        committed = content_sha256(
            {
                "actions": actions,
                "readouts": readouts,
                "distributions": distributions,
                "traces": traces,
            }
        )
        truth = barrier.release(
            lambda sid=step.step_id: dataset.truth_for(episode.episode_id).truth_by_step[sid]
        )
        scores = {name: score(action, truth) for name, action in actions.items()}
        for state in states.values():
            state.feedback(step.model_copy(deep=True))
        budgets = {n: state_audit(s) for n, s in states.items() if "/" in n}
        for arm in NATIVE:
            a, b = budgets[arm + "/parent_only"], budgets[arm + "/owner_missing"]
            for key in (
                "target_evaluations",
                "particles",
                "extra_ciav_queries",
                "paid_location_sources",
            ):
                if a[key] != b[key]:
                    raise ValueError(f"budget mismatch {key}")
        yield {
            "seed": seed,
            "condition": condition,
            "episode": str(episode.episode_id),
            "step": index + 1,
            "input": step.model_dump(mode="json"),
            "input_sha256": content_sha256(step),
            "actions": actions,
            "readouts": readouts,
            "distributions": distributions,
            "traces": traces,
            "pre_truth_commitment": committed,
            "truth": truth.model_dump(mode="json"),
            "scores": scores,
            "budgets": budgets,
            "elapsed_seconds": time.monotonic() - start,
        }


def worker_episode(condition, seed, output, limit):
    dataset = build_dataset(condition, [seed])
    episode = dataset.visible_episodes(Split.TEST)[0]
    count = 0
    with gzip.open(output, "wt") as stream:
        for row in run_episode(dataset, episode, condition, seed, read_selection_archive(), limit):
            stream.write(json.dumps(_canonical_value(row), allow_nan=False, sort_keys=True) + "\n")
            count += 1
    print("shard", condition, seed, count, flush=True)
    return str(output)


def parallel_rows(output, conditions, seeds, limit, workers):
    shards = output / "shards"
    shards.mkdir()
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        futures = [
            pool.submit(
                worker_episode, condition, seed, shards / f"{condition}-{seed}.jsonl.gz", limit
            )
            for condition in conditions
            for seed in seeds
        ]
        # Preserve frozen condition/seed order regardless of process completion order.
        for future in futures:
            with gzip.open(future.result(), "rt") as stream:
                for line in stream:
                    yield json.loads(line)


def run(output, prefix_only=False, smoke=False, workers=1):
    if output.exists():
        raise ValueError("new output directory required")
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    if status and not smoke:
        raise ValueError("committed clean source required")
    frozen = json.loads((PROTOCOL / "FROZEN.json").read_text())
    archive = read_selection_archive()
    sources = [
        *ROOT.glob("src/**/*.py"),
        *ROOT.glob("tools/*.py"),
        *ROOT.glob("configs/**/*.json"),
        *PROTOCOL.glob("*.*"),
    ]
    source = {
        "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "status": status,
        "prefix_only": prefix_only,
        "workers": workers,
        "smoke": smoke,
        "frozen": frozen,
        "files": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
            if p.is_file()
        },
    }
    save(output / "source.json", source)
    seeds = [31] if smoke else frozen["test_seeds"]
    conditions = ["complete32"] if smoke else frozen["conditions"]
    records, inputs = 0, []
    with gzip.open(output / "points.jsonl.gz", "wt") as stream:
        if workers > 1:
            for row in parallel_rows(
                output, conditions, seeds, 2 if prefix_only or smoke else None, workers
            ):
                stream.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
                stream.flush()
                records += 1
                inputs.append(row["input_sha256"])
        else:
            for condition in conditions:
                dataset = build_dataset(condition, seeds)
                episodes = dataset.visible_episodes(Split.TEST)
                if len(episodes) != len(seeds):
                    raise ValueError("episode inventory mismatch")
                for seed, episode in zip(seeds, episodes, strict=True):
                    for row in run_episode(
                        dataset,
                        episode,
                        condition,
                        seed,
                        archive,
                        2 if prefix_only or smoke else None,
                    ):
                        stream.write(
                            json.dumps(_canonical_value(row), allow_nan=False, sort_keys=True)
                            + "\n"
                        )
                        stream.flush()
                        records += 1
                        inputs.append(row["input_sha256"])
                    print(condition, seed, str(episode.episode_id), records, flush=True)
    if not smoke:
        assert subprocess.check_output(["git", "status", "--porcelain"], text=True) == ""
        for name, digest in source["files"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    save(
        output / "completion.json",
        {
            "points": records,
            "input_sequence_sha256": content_sha256(inputs),
            "source_unchanged": not smoke,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--prefix-only", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--workers", type=int, choices=(1, 2, 4), default=1)
    a = p.parse_args()
    run(a.output, a.prefix_only, a.smoke, a.workers)
