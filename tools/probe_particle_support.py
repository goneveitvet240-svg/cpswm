"""Enumerated proposal checks and fixed native development-prefix replay."""

from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

from run_current_event import build, dataset_for
from verify_full_mechanism_value import save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    StatefulFullJointRuntime,
)
from cpswm.system.evaluation_operations.structure_two_stratified_sampling import (
    stratified_draw_indices,
)


def offsets(seed, count, method):
    if method == "systematic":
        return [int(seed[:16], 16) / 16**16] * count
    return [
        (
            int(hashlib.sha256(f"independent_strata_v1:{seed}:{i}".encode()).hexdigest()[:16], 16)
            // 2048
        )
        / 2**53
        for i in range(count)
    ]


def reference(q, seed, count, method):
    total = math.fsum(q) if method != "systematic" else 1.0
    output = []
    for i, u in enumerate(offsets(seed, count, method)):
        point = (i + u) / count
        cumulative = 0.0
        for j, p in enumerate(q):
            cumulative += p / total
            if point < cumulative or j == len(q) - 1:
                output.append(j)
                break
    return output


def probe():
    likelihood = [9.0, 2.0, 1.0]
    prior = [0.2, 0.3, 0.5]
    exact = [p * value / 2.9 for p, value in zip(prior, likelihood, strict=True)]
    q = [p / 24 for _ in range(24) for p in prior]
    synthetic = {}
    for method in ["systematic", "independent_strata_v1"]:
        counts = Counter()
        means = [0.0] * 3
        l1 = 0.0
        collapsed = 0
        for i in range(2048):
            seed = hashlib.sha256(f"enumerated-support:{i}".encode()).hexdigest()
            fn = (
                StatefulFullJointRuntime._systematic_draw_indices
                if method == "systematic"
                else stratified_draw_indices
            )
            actual = list(fn(q, 24, seed))
            assert actual == reference(q, seed, 24, method)
            c = Counter(j % 3 for j in actual)
            counts.update(c)
            collapsed += len(c) == 1
            weighted = [c[a] * likelihood[a] for a in range(3)]
            posterior = [v / sum(weighted) for v in weighted]
            means = [a + b / 2048 for a, b in zip(means, posterior, strict=True)]
            l1 += sum(abs(a - b) for a, b in zip(posterior, exact, strict=True)) / 2048
        synthetic[method] = {
            "draw_count": 24,
            "seeds": 2048,
            "single_actor_seeds": collapsed,
            "mean_posterior": means,
            "mean_l1_error": l1,
            "proposal_frequencies": [counts[a] / (2048 * 24) for a in range(3)],
        }
    finite_mean = [0.0] * 3
    for a in range(25):
        for b in range(25 - a):
            c = 24 - a - b
            mass = math.comb(24, a) * math.comb(24 - a, b) * 0.2**a * 0.3**b * 0.5**c
            weighted = [a * 9.0, b * 2.0, float(c)]
            for j in range(3):
                finite_mean[j] += mass * weighted[j] / sum(weighted)
    native = []
    dataset = dataset_for("sparse32", [67001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    for method in ["systematic", "independent_strata_v1"]:
        for arm in FullJointArm:
            state = build(dataset, episode, arm, sampling_method=method)
            for step in episode.steps[:3]:
                state.observe(step)
                state.predict()
                state.feedback(step)
            state.observe(episode.steps[3])
            runtime = state.runtime
            parents = runtime._current_before["particles"]
            candidates = [
                pair
                for parent in parents
                for pair in runtime._candidates(runtime._last_observation, parent)
            ]
            q = [p / len(parents) for _, p in candidates]
            total = sum(q)
            q = [p / total for p in q]
            receipt = runtime.sampling_receipts[-1]
            indices = reference(q, receipt["seed_sha256"], 24, method)
            assert indices == receipt["indices"]
            actors = [candidates[i][0].placement_actor for i in indices]
            assert actors == [p.world.placement_actor for p in runtime.particles]
            native.append(
                {
                    "method": method,
                    "arm": arm.value,
                    "enumerated_candidates": len(candidates),
                    "particle_budget": 24,
                    "drawn_actor_counts": dict(Counter(actors)),
                    "full_cdf_reference_matches_actual_native_draws": True,
                }
            )
    return {
        "exact_toy_target": exact,
        "exact_finite_24_iid_self_normalized_mean": finite_mean,
        "synthetic": synthetic,
        "native": native,
        "native_observed_steps": 16,
        "native_completed_search_steps": 12,
        "scope": (
            "Toy exact posterior and actual full native proposal CDF; "
            "not exact inference of the full native target"
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    save(a.output, probe())
