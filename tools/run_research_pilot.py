"""E0/E2 development diagnostics; no production model or decision rule changes."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

from run_current_event import build, dataset_for

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.simulation.contracts import CommandQueue, Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.simulation.scenarios import make_scenario
from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    run_exact_enumeration_falsifier,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    StatefulJointParticle,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]


def normalize_logs(values):
    peak = max(values)
    if not math.isfinite(peak):
        raise ValueError("no finite reference target")
    masses = [math.exp(x - peak) for x in values]
    total = math.fsum(masses)
    return [x / total for x in masses]


def enumerate_update(runtime, observation):
    """Enumerate represented parent/candidate support, without importance division.

    Caller supplies the PRE-update runtime. Zero parent mass follows the existing
    production 1e-300 log floor; this is a model-conformance reference, not a new prior.
    """
    parents = runtime.particles or (None,)
    entries, logs, proposal = [], [], []
    for parent in parents:
        local = runtime._candidates(observation, parent)
        transitions = [runtime._transition_raw(parent, c) for c, _ in local]
        peak = max(transitions)
        log_z = peak + math.log(math.fsum(math.exp(t - peak) for t in transitions))
        prior = 0.0 if parent is None else math.log(max(parent.posterior_probability, 1e-300))
        for (candidate, q), transition in zip(local, transitions, strict=True):
            constraints = runtime._constraints(candidate)
            score = (
                math.fsum(
                    [
                        prior,
                        transition - log_z,
                        runtime._observation_log_likelihood(observation, candidate),
                        runtime._main_log_factor(observation, candidate),
                        runtime._interaction_log_factor(observation, candidate),
                        *(c.log_potential for c in constraints),
                    ]
                )
                if all(c.accepted for c in constraints)
                else -math.inf
            )
            entries.append((parent, candidate))
            logs.append(score)
            proposal.append((1.0 / len(parents)) * q)
    q_total = sum(proposal)  # same normalization convention as the production sampler
    proposal = [q / q_total for q in proposal]
    mass = 1.0 - runtime.config.unresolved_prior
    posterior = [p * mass for p in normalize_logs(logs)]
    return entries, logs, proposal, posterior


def tv(a, b):
    return 0.5 * math.fsum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in a.keys() | b.keys())


def marginal(entries, weights, axis, unresolved):
    values = defaultdict(float)
    for (_, candidate), p in zip(entries, weights, strict=True):
        values[str(getattr(candidate, axis))] += p
    values["__unresolved__"] += unresolved
    return dict(values)


def conditional_reference(runtime):
    """Compare completed update to enumeration of exactly its incoming state."""
    before_digest = runtime._state_sha256()
    observation = runtime._last_observation
    reference = copy.copy(runtime)
    reference._restore_mutable_state(copy.deepcopy(runtime._current_before))
    incoming_digest = reference._state_sha256()
    # Production increments the event index before constructing regime candidates.
    reference.step_index += 1
    started = perf_counter()
    entries, logs, q, weights = enumerate_update(reference, observation)
    indices = runtime.sampling_receipts[-1]["indices"]
    if len(entries) != runtime.sampling_receipts[-1]["support_size"]:
        raise ValueError("reference support does not match the sampled update")
    if content_sha256(q) != runtime.sampling_receipts[-1]["proposal_sha256"]:
        raise ValueError("reference proposal does not match the sampled update")
    sample_entries = [entries[i] for i in indices]
    sample_logs = [logs[i] - math.log(q[i]) for i in indices]
    expected_sample = [
        p * (1.0 - reference.config.unresolved_prior) for p in normalize_logs(sample_logs)
    ]
    actual_sample = [p.posterior_probability for p in runtime.particles]
    weight_error = max(abs(a - b) for a, b in zip(expected_sample, actual_sample, strict=True))
    receipt_error = max(
        abs(a - b.unnormalized_log_weight)
        for a, b in zip(sample_logs, runtime.importance_revision_receipts[-1], strict=True)
    )
    axes = (
        "placement_actor",
        "mechanism",
        "role_key",
        "instance_association_key",
        "change_cause",
        "regime_decision",
    )
    marginals = {}
    for axis in axes:
        exact = marginal(entries, weights, axis, reference.config.unresolved_prior)
        sampled = marginal(sample_entries, actual_sample, axis, runtime.unresolved_probability)
        marginals[axis] = {"reference": exact, "sampled": sampled, "tv": tv(exact, sampled)}
    snapshot = content_uuid("stateful-full-joint-snapshot", observation.source_update_id)
    reference.particles = tuple(
        StatefulJointParticle(
            reference._world_from_candidate(
                parent=parent,
                candidate=candidate,
                observation=observation,
                draw_index=i,
                snapshot_id=snapshot,
            ),
            p,
        )
        for i, ((parent, candidate), p) in enumerate(zip(entries, weights, strict=True))
    )
    exact_action = reference._posterior_action_distribution(observation, include_ledger=False)
    actual_action = runtime._posterior_action_distribution(observation, include_ledger=False)

    def choose(d):
        return str(min(d, key=lambda k: (-d[k], str(k))))

    sampled_support = set(indices)
    elapsed = perf_counter() - started
    if runtime._state_sha256() != before_digest:
        raise ValueError("diagnostic mutated runtime")
    return {
        "source_id": str(observation.source_update_id),
        "incoming_state_sha256": incoming_digest,
        "visible_input_sha256": runtime.fairness_receipts[-1].robot_visible_input_sha256,
        "proposal_sha256": content_sha256(q),
        "reference_scope": "one_step_given_sampled_parents_within_candidate_support",
        "parent_count": len(runtime._current_before["particles"]),
        "reference_target_evaluations": len(entries),
        "sample_target_evaluations": runtime.fairness_receipts[-1].target_score_evaluations,
        "transition_evaluations_each": len(entries),
        "shared_model_and_readout": True,
        "reference_seconds_including_worlds_and_readout": elapsed,
        "unresolved_probability": reference.config.unresolved_prior,
        "marginals": marginals,
        "unsampled_parent_candidate_reference_mass": math.fsum(
            p for i, p in enumerate(weights) if i not in sampled_support
        ),
        "max_importance_weight_error": weight_error,
        "max_log_receipt_error": receipt_error,
        "ess": sum(actual_sample) ** 2 / sum(p * p for p in actual_sample),
        "pre_ledger_reference_action": {str(k): v for k, v in exact_action.items()},
        "pre_ledger_sample_action": {str(k): v for k, v in actual_action.items()},
        "action_tv": tv(exact_action, actual_action),
        "reference_choice": choose(exact_action),
        "sample_choice": choose(actual_action),
        "same_choice": choose(exact_action) == choose(actual_action),
    }


def run_e0():
    dataset = dataset_for("sparse32", [67001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    rows = []
    for method in ("systematic", "independent_strata_v1"):
        for arm in FullJointArm:
            state = build(dataset, episode, arm, sampling_method=method)
            for index, step in enumerate(episode.steps[:4]):
                started = perf_counter()
                state.observe(step)
                observe_seconds = perf_counter() - started
                row = conditional_reference(state.runtime)
                row.update(
                    method=method, arm=arm.value, step=index, observe_seconds=observe_seconds
                )
                rows.append(row)
                print(
                    f"E0 {method} {arm.value} step {index}: actor TV "
                    f"{row['marginals']['placement_actor']['tv']:.4f}",
                    flush=True,
                )
                state.predict()
                state.feedback(step)
    return {"episode_id": str(episode.episode_id), "split": "existing_validation", "rows": rows}


def revision_stream(condition, trajectory):
    scenario = make_scenario(condition)
    history = scenario.history
    correct = scenario.corrections
    if trajectory == "no_revision":
        return scenario, list(history)
    if trajectory == "correct_late":
        return scenario, [*history, *correct]
    # Start from the same fixture's correct attribution, then inject the old wrong values.
    initial = [history[0], *(replace(c, revises=None, available_at=c.occurred_at) for c in correct)]
    wrong = [
        replace(old, source_id=old.source_id + ":wrong", revises=c.source_id, available_at=10 + i)
        for i, (old, c) in enumerate(zip(history[1:], correct, strict=True))
    ]
    stream = [*initial, *wrong]
    if trajectory == "wrong_then_recorrect":
        stream.extend(
            replace(
                c, source_id=c.source_id + ":restored", revises=w.source_id, available_at=20 + i
            )
            for i, (c, w) in enumerate(zip(correct, wrong, strict=True))
        )
    elif trajectory != "wrong_revision":
        raise ValueError("unknown revision trajectory")
    return scenario, stream


def reference_memory(memory, active):
    """One full rebuild, using a separately maintained input-event map."""
    ref = SimulationMemory(memory.episode_id, memory.locations, memory.arm, ROOT)
    ref.records = dict(active)
    ordered = sorted(active.values(), key=lambda o: (o.occurred_at, o.event_id))
    latest = ordered[-1]
    ref.current_location = latest.location if latest.visibility == Visibility.OBSERVED else None
    if memory.arm.startswith("native"):
        ref._native_config, ref._native_model = memory._native_config, memory._native_model
        ref.runtime = ref._rebuild_native(ordered)
    return ref


def rb_digest(memory):
    if memory.runtime is None:
        return None
    return content_sha256(
        [
            {
                "weight": p.posterior_probability,
                "cells": [
                    (list(key), asdict(value)) for key, value in sorted(p.world.rb_cells.items())
                ],
            }
            for p in memory.runtime.particles
        ]
    )


def run_e2():
    rows = []
    for condition in ("delayed_attribution", "identity_correction"):
        for trajectory in ("no_revision", "correct_late", "wrong_revision", "wrong_then_recorrect"):
            scenario, inputs = revision_stream(condition, trajectory)
            # Shared follow-up evidence for trajectory retention; no robot success claim.
            inputs.extend(
                Observation(
                    scenario.episode_id,
                    f"follow:{i}",
                    f"follow:{i}",
                    30 + i,
                    30 + i,
                    "target",
                    Visibility.OBSERVED,
                    "center",
                    (("guest", 1.0),),
                )
                for i in range(3)
            )
            for arm in sorted(SimulationMemory.ARMS):
                memory = SimulationMemory(
                    scenario.episode_id, ("left", "center", "right"), arm, ROOT
                )
                active, checkpoints = {}, []
                queue = CommandQueue(scenario.episode_id)
                for obs in inputs:
                    old_revision = memory.revision
                    old_scores = memory.native_target_scores
                    pending = queue.pending
                    started = perf_counter()
                    memory.ingest(obs, obs.available_at)
                    ingest_seconds = perf_counter() - started
                    if obs.event_id not in active or arm != "ordinary_memory":
                        active[obs.event_id] = obs
                    started = perf_counter()
                    ref = reference_memory(memory, active)
                    reference_seconds = perf_counter() - started
                    a, b = memory.audit(), ref.audit()
                    queue.invalidate(memory.revision)
                    stale_rejected = None
                    if pending is not None and old_revision != memory.revision:
                        try:
                            queue.validate(pending, memory.revision)
                        except ValueError:
                            stale_rejected = True
                        else:
                            stale_rejected = False
                    if queue.pending is None:
                        queue.submit(
                            "target", memory.destination(), memory.revision, obs.available_at
                        )
                    checkpoints.append(
                        {
                            "input": obs.payload(),
                            "audit": a,
                            "reference_state": b["native_state"],
                            "same_state": a["native_state"] == b["native_state"],
                            "same_ledger": a["ledger_head"] == b["ledger_head"],
                            "rb_digest": rb_digest(memory),
                            "reference_rb_digest": rb_digest(ref),
                            "same_rb": rb_digest(memory) == rb_digest(ref),
                            "same_current_location": memory.current_location
                            == ref.current_location,
                            "distribution_tv": tv(
                                memory.destination_distribution(), ref.destination_distribution()
                            ),
                            "ingest_seconds": ingest_seconds,
                            "full_rebuild_seconds": reference_seconds,
                            "native_target_scores_delta": memory.native_target_scores - old_scores,
                            "reference_target_scores": 0
                            if ref.runtime is None
                            else sum(
                                r.target_score_evaluations for r in ref.runtime.fairness_receipts
                            ),
                            "stale_command_rejected": stale_rejected,
                            "destination": memory.destination(),
                            "matches_fixture_expected_destination": memory.destination()
                            == scenario.expected_destination,
                        }
                    )
                rows.append(
                    {
                        "condition": condition,
                        "trajectory": trajectory,
                        "arm": arm,
                        "checkpoints": checkpoints,
                        "queue_history": queue.history,
                    }
                )
                print(f"E2 {condition} {trajectory} {arm}: {memory.destination()}", flush=True)
    return {"evidence_level": "controlled_fixture_not_robot_execution", "rows": rows}


def validate_readings(report):
    """Fail closed on measured conformance failures, not on scientific negative results."""
    for row in report.get("e0", {}).get("rows", []):
        for key in ("max_importance_weight_error", "max_log_receipt_error"):
            if not math.isfinite(row[key]) or row[key] > 1e-10:
                raise ValueError(f"E0 arithmetic mismatch: {key}")
        for reading in row["marginals"].values():
            for field in ("reference", "sampled"):
                values = reading[field].values()
                if any(not math.isfinite(p) or p < 0 for p in values):
                    raise ValueError("invalid E0 marginal")
                if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
                    raise ValueError("unnormalized E0 marginal")
    for row in report.get("e2", {}).get("rows", []):
        for point in row["checkpoints"]:
            if not all(
                point[k] for k in ("same_state", "same_ledger", "same_rb", "same_current_location")
            ):
                raise ValueError("E2 full-rebuild equivalence failed")
            if point["rb_digest"] != point["reference_rb_digest"]:
                raise ValueError("E2 RB digest mismatch")
            if point["audit"]["native_state"] != point["reference_state"]:
                raise ValueError("E2 state digest mismatch")
            if not math.isfinite(point["distribution_tv"]) or point["distribution_tv"] > 1e-10:
                raise ValueError("E2 distribution mismatch")
            if point["stale_command_rejected"] is False:
                raise ValueError("E2 stale command remained executable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part", choices=("e0", "e2", "finite", "all"), default="all")
    args = parser.parse_args()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    report = {
        "protocol": "cpswm-research-pilot-20261023-v1",
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": status,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/reviews/pc_a/research_pilot_2026-10-23/PROTOCOL.md").read_bytes()
        ).hexdigest(),
        "evidence_level": "development_only_no_scientific_acceptance",
    }
    for name, runner in (
        ("finite", run_exact_enumeration_falsifier),
        ("e0", run_e0),
        ("e2", run_e2),
    ):
        if args.part in (name, "all"):
            report[name] = runner()
    # Always preserve measured failures; a nonzero exit follows artifact publication.
    report["content_sha256"] = content_sha256(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(args.output, flush=True)
    validate_readings(report)


if __name__ == "__main__":
    main()
