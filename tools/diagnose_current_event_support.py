"""Read-only proposal support diagnostic on a fixed development prefix."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from run_current_event import build, dataset_for
from verify_full_mechanism_value import save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def diagnose():
    dataset = dataset_for("sparse32", [66001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    state = build(dataset, episode, FullJointArm.STATEFUL_FULL_JOINT, sampling_method="systematic")
    for step in episode.steps[:3]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    state.observe(episode.steps[3])
    runtime = state.runtime
    o = runtime._last_observation
    parents = runtime._current_before["particles"]
    rows = []
    probabilities = []
    all_actors = []
    seed = runtime.fairness_receipts[-1].common_random_number_sha256
    u = int(seed[:16], 16) / float(16**16)
    for i, parent in enumerate(parents):
        candidates = runtime._candidates(o, parent)
        mass = Counter()
        cumulative = 0.0
        selected = None
        for candidate, p in candidates:
            mass[candidate.placement_actor] += p
            cumulative += p
            if selected is None and cumulative >= u:
                selected = candidate.placement_actor
            probabilities.append(p / len(parents))
            all_actors.append(candidate.placement_actor)
        rows.append(
            {
                "parent": i,
                "actor_proposal_mass": dict(mass),
                "actor_at_shared_local_quantile": selected,
                "candidate_count": len(candidates),
            }
        )
    total = sum(probabilities)
    draws = runtime._systematic_draw_indices(
        [p / total for p in probabilities], runtime.config.particle_budget, seed
    )
    actors = [all_actors[i] for i in draws]
    assert actors == [p.world.placement_actor for p in runtime.particles]
    return {
        "scope": (
            "one fixed development prefix; explains an inherited proposal "
            "sampling failure mode, no method change"
        ),
        "actual_observed_steps": 4,
        "actual_completed_search_steps": 3,
        "source_event_id": str(o.source_update_id),
        "step_id": str(episode.steps[3].step_id),
        "parent_count": len(parents),
        "particle_budget": runtime.config.particle_budget,
        "equal_parent_proposal_mass": 1 / len(parents),
        "shared_local_quantile": u,
        "parents": rows,
        "drawn_actor_counts": dict(Counter(actors)),
        "mechanism": (
            "with N equal parent blocks and N systematic draws, "
            "every block is sampled at the same local quantile; "
            "identical local proposals then choose identical children"
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    save(a.output, diagnose())
