"""Full native-state replay, actor scoring and recurrence conditional-target diagnosis."""

import argparse
import copy
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

from run_five_stage_synergy import NEW_SEEDS, bound_sources
from run_matched_value import (
    CONDITIONS,
    NATIVE,
    PublicCatalogueAdapter,
    action_payload,
    dataset_for,
    make_state,
    save,
    state_audit,
)
from run_research_pilot import conditional_reference, enumerate_update
from synergy_runtime import PosteriorParentRuntime

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.reproducibility import _canonical_value, content_sha256

ROOT = Path(__file__).resolve().parents[1]
RECURRENCE = {"a8d4d6c9": (27, 28), "a11287b6": (27, 28, 29)}


def recurrence(runtime, truth):
    summary = conditional_reference(runtime)
    before = copy.copy(runtime)
    before._restore_mutable_state(copy.deepcopy(runtime._current_before))
    before.step_index += 1
    obs = runtime._last_observation
    entries, logs, q, weights = enumerate_update(before, obs)
    i = list(map(str, obs.known_location_ids)).index(truth)
    totals = defaultdict(float)
    support = defaultdict(int)
    # Evaluator-labelled historical cell only; no truth supplied to candidate builder.
    for (parent, candidate), log_target, proposal, posterior in zip(
        entries, logs, q, weights, strict=True
    ):
        cell = parent.world.rb_cells.get((obs.owner_actor_key, candidate.active_regime_after))
        correct_old = (
            cell is not None
            and cell.observation_count > 0
            and cell.location_alpha[i] > 0.5
            and cell.location_alpha[i] == max(cell.location_alpha)
        )
        if correct_old:
            key = candidate.regime_decision.value
            support[key] += 1
            totals[key + "/q"] += proposal
            totals[key + "/target"] += posterior
            totals[key + "/finite_target_candidates"] += math.isfinite(log_target)
    return {
        "conditional": summary,
        "correct_historical_cell_candidate_counts": dict(support),
        "correct_historical_cell_candidate_mass": dict(totals),
        "observation": obs,
        "warning": "conditional on sampled parents; historical cell labels use evaluator truth",
    }


def run(primary, output):
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = {
        **bound_sources(),
        "tools/audit_synergy_posteriors.py": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    }
    manifest = json.loads((primary / "manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        assert hashlib.sha256((primary / name).read_bytes()).hexdigest() == expected
    previous = json.loads((primary / "points.json").read_text())
    lookup = {(p["cohort"], p["condition"], p["episode_id"], p["step"]): p for p in previous}
    rows = []
    for cohort in ("old", "new"):
        for condition in CONDITIONS:
            if condition not in ("complete32", "sparse32", "long64"):
                continue
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
                states = {
                    arm + "/" + proposal: make_state(episode, arm)
                    for arm in NATIVE
                    for proposal in ("original", "posterior_parent")
                }
                for name, state in states.items():
                    if name.endswith("posterior_parent"):
                        r = state.runtime
                        state.runtime = PosteriorParentRuntime(
                            arm=r.arm, config=r.config, neural_model=r.neural_model
                        )
                for index, step in enumerate(episode.steps):
                    predictions, margins = {}, {}
                    for name, state in states.items():
                        state.observe(step.model_copy(deep=True))
                        predictions[name] = action_payload(
                            state.predict(), episode.known_location_ids
                        )
                        actors = defaultdict(float)
                        for p in state.runtime.particles:
                            actors[p.world.placement_actor] += p.posterior_probability
                        actors["__unresolved__"] += state.runtime.unresolved_probability
                        margins[name] = dict(actors)
                    old = lookup[cohort, condition, str(episode.episode_id), index + 1]
                    assert content_sha256(step) == old["input_sha256"]
                    row = {
                        "cohort": cohort,
                        "condition": condition,
                        "episode": str(episode.episode_id),
                        "step": index + 1,
                        "methods": {},
                    }
                    for name, state in states.items():
                        assert predictions[name] == old["actions"][name]
                        record = {
                            "actor_distribution": margins[name],
                            "true_actor": old["true_actor"],
                            "true_actor_probability": margins[name].get(old["true_actor"], 0),
                            "actor_top1_correct": min(
                                margins[name], key=lambda k: (-margins[name][k], k)
                            )
                            == old["true_actor"],
                        }
                        if (
                            cohort == "old"
                            and condition == "sparse32"
                            and name.startswith("native_joint/")
                            and index + 1 in RECURRENCE.get(str(episode.episode_id)[:8], ())
                        ):
                            record["recurrence"] = recurrence(state.runtime, old["truth"])
                        state.feedback(step.model_copy(deep=True))
                        assert _canonical_value(state_audit(state)) == old["stats"][name]["audit"]
                        record["state_replay_match"] = True
                        row["methods"][name] = record
                    rows.append(row)
                save(output, {"rows": rows, "complete": False})
                print(cohort, condition, episode.episode_id, len(rows), flush=True)
    assert len(rows) == len(previous) == 768
    assert all(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        for name, digest in sources.items()
    )
    save(
        output,
        {
            "source_sha": code_sha,
            "sources": sources,
            "rows": rows,
            "complete": True,
            "primary_manifest_sha256": hashlib.sha256(
                (primary / "manifest.json").read_bytes()
            ).hexdigest(),
            "scientific_acceptance": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("primary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.primary, args.output)
