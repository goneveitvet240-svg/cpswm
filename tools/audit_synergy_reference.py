"""Compare optional parent proposal against source-verified prior exact path targets."""

import argparse
import copy
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

from run_matched_value import save
from run_research_pilot import marginal, tv
from run_short_history_reference import (
    AXES,
    candidate_key_from_world,
    fixed_inputs,
    path_comparison,
    sampled_paths,
)
from synergy_runtime import PosteriorParentRuntime

from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs/reviews/pc_a/joint_three_questions_2026-10-25"


def run():
    manifest = json.loads((OLD / "MANIFEST.json").read_text())

    def verified(name):
        data = (OLD / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == manifest["files"][name]["sha256"]
        return data

    previous = json.loads(verified("evidence/q1/reference.json"))
    bound = json.loads(verified("evidence/manifest.json"))
    for name, digest in bound["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    rows = []
    for episode, config, model, observations, _ in fixed_inputs():
        for arm in FullJointArm:
            runtime = PosteriorParentRuntime(arm=arm, config=config, neural_model=model)
            histories = {}
            for index, observation in enumerate(observations):
                old = next(
                    r
                    for r in previous["rows"]
                    if r["episode_id"] == episode
                    and r["arm"] == arm.value
                    and r["depth"] == index + 1
                )
                assert content_sha256(observation) == old["observation_sha256"]
                reference = old["reference"]
                data = verified("evidence/q1/" + reference["posterior_trace"])
                exact = {}
                for line in gzip.decompress(data).splitlines():
                    row = json.loads(line)
                    exact[tuple(row["path"])] = row["probability"]
                runtime.revise(copy.deepcopy(observation))
                runtime.verify_internal_contracts()
                histories, posterior = sampled_paths(runtime, histories)
                lookup = {}
                parents = runtime._current_before["particles"] or (None,)
                for parent in parents:
                    lookup.update({c.key: c for c, _ in runtime._candidates(observation, parent)})
                candidates = [
                    (None, lookup[candidate_key_from_world(p.world)]) for p in runtime.particles
                ]
                weights = [p.posterior_probability for p in runtime.particles]
                margins = {
                    axis: marginal(candidates, weights, axis, runtime.unresolved_probability)
                    for axis in AXES
                }
                action = {
                    str(k): v
                    for k, v in runtime._posterior_action_distribution(
                        observation, include_ledger=False
                    ).items()
                }
                baseline = next(m for m in old["methods"] if m["method"] == "independent_strata_v1")
                rows.append(
                    {
                        "episode": episode,
                        "arm": arm.value,
                        "depth": index + 1,
                        "original": baseline,
                        "posterior_parent": {
                            "marginals": margins,
                            "marginal_tv": {
                                axis: tv(margins[axis], reference["marginals"][axis])
                                for axis in AXES
                            },
                            "ess": sum(weights) ** 2 / sum(w * w for w in weights),
                            "action": action,
                            "action_tv": tv(action, reference["action"]),
                            "target_evaluations": runtime.fairness_receipts[
                                -1
                            ].target_score_evaluations,
                            **path_comparison(exact, posterior, runtime.unresolved_probability),
                        },
                        "reference": reference,
                    }
                )
    return {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "rows": rows,
        "scientific_acceptance": False,
        "reference_scope": "complete native two-step model projection; not generative truth",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, run())
