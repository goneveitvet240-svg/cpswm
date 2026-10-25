"""Matched development comparison of typed owner-memory readout, never holdout."""

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

from analyze_matched_readout import ARCHIVE
from run_five_stage_synergy import NEW_SEEDS
from run_joint_three_questions import paired_counts
from run_matched_value import (
    CONDITIONS,
    NATIVE,
    CommitBarrier,
    PublicCatalogueAdapter,
    action_payload,
    dataset_for,
    make_state,
    save,
    state_audit,
)
from synergy_runtime import PosteriorParentRuntime

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations.structure_two_memory_action import (
    MemoryActionRuntime,
    owner_habit_readout,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def read_selection_archive():
    manifest = json.loads((ARCHIVE / "MANIFEST.json").read_text())["primary"]
    path = ARCHIVE / "evidence/primary.tar.gz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("baseline archive mismatch")
    result = {}
    with tarfile.open(path, "r:gz") as archive:
        if set(archive.getnames()) != set(manifest["members"]):
            raise ValueError("archive member inventory mismatch")
        for member in archive.getmembers():
            data = archive.extractfile(member).read()
            expected = manifest["members"][member.name]
            if (
                len(data) != expected["bytes"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError("baseline member mismatch")
            result[member.name] = json.loads(data)
    # The new live-native goal adapter is intentionally changed and does not
    # generate D0 data or select baseline parameters. All other inherited files
    # must match. New implementation files are bound in this run's source.json.
    for name, expected in result["manifest.json"]["files"].items():
        if name == "src/cpswm/simulation/goal_control.py":
            continue
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("inherited input/baseline source differs: " + name)
    return result


def run(output, quick=False):
    if output.exists():
        raise ValueError("output must be new")
    output.mkdir(parents=True)
    archive = read_selection_archive()
    points = []
    sources = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tools/*.py"), *ROOT.glob("configs/**/*.json")]
    save(
        output / "source.json",
        {
            "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "status": subprocess.check_output(["git", "status", "--porcelain"], text=True),
            "files": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources
            },
            "quick": quick,
        },
    )
    for cohort in ("old", "new"):
        for condition in ("complete32", "sparse32", "long64"):
            dataset = (
                dataset_for(condition)
                if cohort == "old"
                else PublicCatalogueAdapter(
                    validation_seeds=(7, 8, 9),
                    test_seeds=NEW_SEEDS,
                    max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
                    dataset_version="mechanism-value-development-20261011:" + condition,
                    sealed_secret="mechanism-value-development-20261011:" + condition,
                    **CONDITIONS[condition],
                ).build()
            )
            for episode in dataset.visible_episodes(Split.TEST):
                states = {}
                for arm in NATIVE:
                    for mode in ("parent_only", "owner_only", "owner_missing"):
                        state = make_state(episode, arm)
                        r = state.runtime
                        cls = (
                            PosteriorParentRuntime if mode == "parent_only" else MemoryActionRuntime
                        )
                        kwargs = (
                            {}
                            if mode == "parent_only"
                            else {"missing_evidence": mode == "owner_missing"}
                        )
                        state.runtime = cls(
                            arm=r.arm, config=r.config, neural_model=r.neural_model, **kwargs
                        )
                        states[arm + "/" + mode] = state
                for method in ("latest_owner", "matched_amg"):
                    choice = archive[condition + "/selection.json"]["methods"][method]
                    parameter = choice["trials"][choice["selected_index"]]["parameter"]
                    states[method] = make_state(episode, method, parameter)
                for index, step in enumerate(episode.steps[:2] if quick else episode.steps):
                    barrier = CommitBarrier(states, content_sha256(step))
                    actions, receipts, actors = {}, {}, {}
                    for name, state in states.items():
                        state.observe(step.model_copy(deep=True))
                        actions[name] = action_payload(state.predict(), episode.known_location_ids)
                        barrier.commit(name, content_sha256(step), actions[name])
                        if "/" in name:
                            receipts[name] = owner_habit_readout(state.runtime)[1]
                            actors[name] = {}
                            for p in state.runtime.particles:
                                actor = p.world.placement_actor
                                actors[name][actor] = (
                                    actors[name].get(actor, 0) + p.posterior_probability
                                )
                    truth = barrier.release(
                        lambda ds=dataset, eid=episode.episode_id, sid=step.step_id: ds.truth_for(
                            eid
                        ).truth_by_step[sid]
                    )
                    for state in states.values():
                        state.feedback(step.model_copy(deep=True))
                    budgets = {n: state_audit(s) for n, s in states.items() if "/" in n}
                    for arm in NATIVE:
                        base = budgets[arm + "/parent_only"]
                        for mode in ("owner_only", "owner_missing"):
                            other = budgets[arm + "/" + mode]
                            for key in (
                                "target_evaluations",
                                "particles",
                                "extra_ciav_queries",
                                "paid_location_sources",
                            ):
                                if base[key] != other[key]:
                                    raise ValueError(f"budget mismatch: {key}")
                    points.append(
                        {
                            "cohort": cohort,
                            "condition": condition,
                            "episode": str(episode.episode_id),
                            "step": index + 1,
                            "input_sha256": content_sha256(step),
                            "actions": actions,
                            "readouts": receipts,
                            "actors": actors,
                            "truth": str(truth.true_owner_habit_location),
                            "budgets": budgets,
                        }
                    )
                save(output / "points.json", points)
                print(cohort, condition, episode.episode_id, len(points), flush=True)
    summary = {}
    for cohort in ("old", "new"):
        rows = [p for p in points if p["cohort"] == cohort]
        summary[cohort] = {
            name: {
                "errors": sum(p["actions"][name]["put_back"] != p["truth"] for p in rows),
                "versus_latest": paired_counts(
                    [p["actions"]["latest_owner"]["put_back"] for p in rows],
                    [p["actions"][name]["put_back"] for p in rows],
                    [p["truth"] for p in rows],
                ),
            }
            for name in rows[0]["actions"]
        }
    save(
        output / "summary.json",
        {"points": len(points), "development_only": True, "results": summary},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--quick", action="store_true")
    a = p.parse_args()
    run(a.output, a.quick)
