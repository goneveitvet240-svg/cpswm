"""Frozen-profile same-budget old/repaired sampling experiment."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from run_current_event import dataset_for, evaluate, manifest, plain
from verify_full_mechanism_value import ROOT, save

from cpswm.contracts import ProjectTwoDatasetSplit

METHODS = {"systematic": "systematic", "stratified": "independent_strata_v1"}
CONFIGS = {
    "joint": {"arm": "stateful_full_joint", "consume_new": True},
    "matched_factor": {"arm": "matched_full_state_factorized", "consume_new": True},
    "joint_no_new": {"arm": "stateful_full_joint", "consume_new": False},
    "matched_factor_no_new": {"arm": "matched_full_state_factorized", "consume_new": False},
}


def sources():
    result = manifest()
    for rel in [
        "tools/run_particle_support.py",
        "tools/score_particle_support.py",
        "tests/test_particle_support_sampling.py",
    ]:
        result[rel] = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    return result


def run(output, phase, sampler, seeds, conditions):
    output.mkdir(parents=True, exist_ok=False)
    source = sources()
    save(
        output / "source.json",
        {
            "files": source,
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        },
    )
    index = []
    for condition in conditions:
        dataset = dataset_for(condition, seeds)
        split = ProjectTwoDatasetSplit.VALIDATION if phase == "dev" else ProjectTwoDatasetSplit.TEST
        for i, episode in enumerate(dataset.visible_episodes(split)):
            key = f"{condition}-{i}"
            save(output / f"visible-{key}.json", episode.model_dump(mode="json"))
            save(
                output / f"truth-{key}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            for label, config in CONFIGS.items():
                full_config = {**config, "profile": "v06", "sampling_method": METHODS[sampler]}
                name = f"run-{key}-{label}.json"
                save(output / name, plain(evaluate(dataset, episode, **full_config)))
                index.append(
                    {
                        "condition": condition,
                        "episode": i,
                        "label": label,
                        "file": name,
                        "visible": f"visible-{key}.json",
                        "truth": f"truth-{key}.json",
                        "config": full_config,
                    }
                )
                print(phase, sampler, key, label, "complete", flush=True)
    save(output / "index.json", index)
    assert source == sources()
    save(
        output / "completion.json",
        {"actual_runs": len(index), "source_unchanged": True, "profile": "v06", "sampler": sampler},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=["dev", "test"], required=True)
    p.add_argument("--sampler", choices=list(METHODS), required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[67001, 67002, 67003, 67004])
    p.add_argument("--conditions", nargs="+", default=["sparse32", "long64"])
    a = p.parse_args()
    run(a.output, a.phase, a.sampler, a.seeds, a.conditions)
