"""Method-free profiling of the explicitly spent rolling-train world set only."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def audit_train_worlds(root: Path) -> dict[str, Any]:
    # No validation/holdout generation, no method execution, no labels exported.
    from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
        StructureTwoWorldGeneratorV02,
        WorldDistributionConfig,
    )

    design_path = (
        root / "configs/project_two_experiments/structure_two_world_rolling_train_gate_v0_4.json"
    )
    design = json.loads(design_path.read_text(encoding="utf-8"))
    base_path = root / design["base_manifest"]
    base_bytes = base_path.read_bytes()
    if hashlib.sha256(base_bytes).hexdigest() != design["base_manifest_sha256"]:
        raise ValueError("base manifest source binding mismatch")
    base = json.loads(base_bytes)
    distribution = dict(base["world_distribution"])
    distribution["duration_days_inclusive"] = design["world_change_under_test"][
        "duration_days_inclusive"
    ]
    sample = design["train_sampling"]
    seeds = sample["world_seeds"]
    if len(seeds) != len(set(seeds)) or not seeds:
        raise ValueError("training world seeds must be nonempty and unique")
    if set(seeds) != {s for fold in design["outer_world_folds"] for s in fold}:
        raise ValueError("training world/fold mismatch")
    reserved = design["downstream_prereservation_not_authorized_for_use"][
        "validation_world_seed_candidates"
    ]
    if set(seeds) & set(reserved):
        raise ValueError("training overlaps reserved validation worlds")
    generator = StructureTwoWorldGeneratorV02(WorldDistributionConfig.from_manifest(distribution))
    counts: Counter[str] = Counter()
    contexts: Counter[str] = Counter()
    regimes: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    mechanisms: Counter[str] = Counter()
    chains: Counter[str] = Counter()
    rollout_ids, keys = set(), set()
    for seed in seeds:
        world = generator.sample_world(seed)
        for trajectory in sample["trajectory_seeds"]:
            for observation in sample["observation_seeds"]:
                run = generator.generate_rollout(
                    world, trajectory_seed=trajectory, observation_seed=observation
                )
                if run.rollout_id in rollout_ids:
                    raise ValueError("duplicate rollout")
                rollout_ids.add(run.rollout_id)
                for step in run.steps:
                    key = (seed, trajectory, observation, step.day)
                    if key in keys:
                        raise ValueError("duplicate world/trajectory/observation/day")
                    keys.add(key)
                    counts["steps"] += 1
                    counts["observed" if step.observed else "not_observed"] += 1
                    counts["unknown_actor_truth"] += int(step.true_actor == "unknown_actor")
                    counts["perceived_location_mismatch"] += int(
                        step.observed and step.observed_location != step.true_location
                    )
                    counts["true_identity_match_false"] += int(not step.true_identity_match)
                    contexts[step.context] += 1
                    regimes[step.regime] += 1
                    causes[step.true_cause] += 1
                    mechanisms[step.true_mechanism] += 1
                    chains["->".join(step.event_chain)] += 1
    axis = {
        "H": "partial: constant pick_up/carry/place chain, not full hidden-event revision support",
        "R": "missing: one true_actor and handoff label, no ordered role assignment chain",
        "I": "missing: no competing instance IDs or unknown_instance; match truth is constant",
        "C": "partial: generator causes, not the frozen six-way cause support",
        "Z": "partial: regime labels, not stay/create/reactivate/unresolved decisions",
        "r": "missing: no explicit particle-conditioned run length field",
        "V": "missing: no event/particle/ledger revision lineage",
    }
    return {
        "scope": "method-free spent train worlds; NOT training authorization or confirmation",
        "grain": "world_seed / trajectory_seed / observation_seed / day",
        "world_count": len(seeds),
        "rollout_count": len(rollout_ids),
        "counts": dict(counts),
        "contexts": dict(contexts),
        "regimes": dict(regimes),
        "causes": dict(causes),
        "mechanisms": dict(mechanisms),
        "event_chains": dict(chains),
        "axes": axis,
        "proposal_operation_labels": {
            x: 0
            for x in (
                "branch",
                "revise",
                "retract",
                "reactivate",
                "rejuvenate",
                "preserve_unresolved",
            )
        },
        "not_represented": [
            "verified_absence",
            "unknown_location",
            "late_arrival_time",
            "execution_feedback",
            "continuous_measurement_and_noise_model",
        ],
        "not_observed_is_not_verified_absence": True,
        "full_scope_training_ready": False,
        "sources": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                design_path,
                base_path,
                Path(__file__),
                root
                / "src/cpswm/system/evaluation_operations/structure_two_world_generator_v0_2.py",
            )
        },
    }
