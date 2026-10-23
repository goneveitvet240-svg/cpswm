"""Two-update enumeration of the native projection target, not a new generative model."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import platform
import subprocess
from collections import defaultdict
from contextlib import nullcontext
from pathlib import Path
from time import perf_counter

from run_current_event import build, dataset_for
from run_research_pilot import enumerate_update, marginal, normalize_logs, tv

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_current_event import CurrentEventRuntime
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    StatefulJointParticle,
)
from cpswm.system.reproducibility import canonical_json, content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]
AXES = (
    "placement_actor",
    "mechanism",
    "role_key",
    "instance_association_key",
    "change_cause",
    "regime_decision",
)


class BootstrapRuntime(CurrentEventRuntime):
    """Same native target/RB state, proposal proportional to parent prior * transition.

    Reuses the exhaustive native support builder; its neural q values are discarded.
    The production parent's uniform factor cancels in global q normalization.
    """

    def _candidates(self, observation, parent):
        support = super()._candidates(observation, parent)
        probabilities = normalize_logs([self._transition_raw(parent, c) for c, _ in support])
        parent_mass = 1.0 if parent is None else max(parent.posterior_probability, 1e-300)
        return tuple((c, parent_mass * p) for (c, _), p in zip(support, probabilities, strict=True))


def candidate_key_from_world(world):
    parts = world.event_chain[-1].split("|")
    if len(parts) != 4:
        raise ValueError("native event encoding changed")
    return "|".join(
        (
            *parts[:3],
            world.change_cause_history[-1].value,
            world.typed_state.regime_decision.value,
            world.typed_state.regime_id or "-",
        )
    )


def choose_action(distribution):
    return str(min(distribution, key=lambda location: (-distribution[location], str(location))))


def sampled_paths(runtime, previous_paths):
    paths, posterior = {}, defaultdict(float)
    for particle in runtime.particles:
        state = particle.world.typed_state
        prefix = (
            () if state.parent_particle_id is None else previous_paths[state.parent_particle_id]
        )
        path = (*prefix, candidate_key_from_world(particle.world))
        paths[state.particle_id] = path
        posterior[path] += particle.posterior_probability
    return paths, dict(posterior)


def path_comparison(reference, sampled, unresolved):
    if any(path not in reference for path in sampled):
        raise ValueError("sample contains a latent path outside exact support")
    overlap = math.fsum(min(p, reference[path]) for path, p in sampled.items())
    covered = math.fsum(reference[path] for path in sampled)
    return {
        "latent_path_tv": max(0.0, 1.0 - unresolved - overlap),
        "unrepresented_reference_mass": max(0.0, 1.0 - unresolved - covered),
        "distinct_sample_paths": len(sampled),
        "matched_paths": [
            {"path": path, "reference": reference[path], "sampled": p}
            for path, p in sorted(sampled.items())
        ],
    }


class ExactHistory:
    """Diagnostic model-state expansion. It is not a production receipt state machine."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.paths = {}
        self.terminal = False

    def advance(self, observation, *, terminal=False, output=None):
        if self.terminal or self.runtime.step_index >= 2:
            raise ValueError("reference is bounded to two updates")
        if self.runtime.step_index == 1 and not terminal:
            raise ValueError("second reference update must be terminal")
        started = perf_counter()
        observation.__post_init__()
        if observation.source_update_id in self.runtime._consumed_updates:
            raise ValueError("duplicate reference source")
        runtime = copy.deepcopy(self.runtime)
        runtime._consumed_updates.add(observation.source_update_id)
        runtime.step_index += 1  # native order: increment before regime support construction
        entries, logs, _, probabilities = enumerate_update(runtime, observation)
        unresolved = runtime.config.unresolved_prior
        snapshot = content_uuid("stateful-full-joint-snapshot", observation.source_update_id)
        posterior, retained, next_paths = {}, [], {}
        action_terms = {location: [] for location in observation.known_location_ids}
        readout = copy.copy(runtime)
        base_total = sum(observation.base_location_distribution.values())
        base = {k: v / base_total for k, v in observation.base_location_distribution.items()}
        manager = (
            nullcontext(None)
            if output is None
            else gzip.GzipFile(filename=str(output), mode="wb", mtime=0)
        )
        with manager as writer:
            for i, ((parent, candidate), log_target, probability) in enumerate(
                zip(entries, logs, probabilities, strict=True)
            ):
                prefix = () if parent is None else self.paths[parent.world.typed_state.particle_id]
                path = (*prefix, candidate.key)
                if path in posterior:
                    raise ValueError("duplicate exact latent path")
                posterior[path] = probability
                if writer is not None:
                    line = {
                        "path": path,
                        "log_target": log_target if math.isfinite(log_target) else None,
                        "probability": probability,
                    }
                    writer.write(
                        (json.dumps(line, separators=(",", ":"), allow_nan=False) + "\n").encode()
                    )
                # Keep zero-mass first-step states: the native parent floor may revive them.
                if probability > 0.0 or not terminal:
                    world = runtime._world_from_candidate(
                        parent=parent,
                        candidate=candidate,
                        observation=observation,
                        draw_index=i,
                        snapshot_id=snapshot,
                    )
                    if not terminal:
                        retained.append(StatefulJointParticle(world, probability))
                        next_paths[world.typed_state.particle_id] = path
                    if probability > 0.0:
                        # pre-ledger readout is a convex, affine mixture over particles.
                        # A unit-particle readout preserves all three RB blocks and strengths.
                        readout.particles = (StatefulJointParticle(world, 1.0),)
                        unit = readout._posterior_action_distribution(
                            observation, include_ledger=False
                        )
                        for location, value in unit.items():
                            action_terms[location].append(probability * value)
                if i and i % 50000 == 0:
                    print(f"exact depth={runtime.step_index} {i}/{len(entries)}", flush=True)
        action = {k: math.fsum(values) + unresolved * base[k] for k, values in action_terms.items()}
        action_total = math.fsum(action.values())
        action = {k: v / action_total for k, v in action.items()}
        if not math.isclose(math.fsum(probabilities) + unresolved, 1.0, abs_tol=1e-10):
            raise ValueError("exact target is not normalized")
        marginals = {axis: marginal(entries, probabilities, axis, unresolved) for axis in AXES}
        direct_difference = None
        if not terminal:
            runtime.particles = tuple(retained)
            runtime.unresolved_probability = unresolved
            runtime._last_observation = observation
            direct = runtime._posterior_action_distribution(observation, include_ledger=False)
            direct_difference = tv(direct, action)
            if direct_difference > 1e-10:
                raise ValueError("streamed readout differs from native convex mixture")
            if observation.observed_location_id is not None:
                runtime.rgrc_ledger.consider(
                    runtime.particles,
                    owner_key=observation.owner_actor_key,
                    action_distribution=action,
                )
            self.paths = next_paths
        self.terminal = terminal
        self.runtime = None if terminal else runtime
        if terminal:
            self.paths = {}
        file_hash = None
        if output is not None:
            with output.open("rb") as handle:
                file_hash = hashlib.file_digest(handle, "sha256").hexdigest()
        return {
            "posterior": posterior,
            "marginals": marginals,
            "action": action,
            "summary": {
                "depth": runtime.step_index,
                "support_paths": len(posterior),
                "target_evaluations": len(entries),
                "transition_evaluations": len(entries),
                "unresolved_probability": unresolved,
                "seconds_including_worlds_readout_and_trace": perf_counter() - started,
                "terminal": terminal,
                "streamed_vs_native_readout_tv": direct_difference,
                "numeric_zero_mass_paths": sum(p == 0.0 for p in probabilities),
                "posterior_trace": None if output is None else output.name,
                "posterior_trace_sha256": file_hash,
                "marginals": marginals,
                "action": {str(k): v for k, v in action.items()},
            },
        }


def fixed_inputs():
    dataset = dataset_for("sparse32", [67001])
    result = []
    for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
        state = build(dataset, episode, FullJointArm.STATEFUL_FULL_JOINT)
        observations = []
        for step in episode.steps[:2]:
            state.observe(step)
            state.predict()
            observations.append(copy.deepcopy(state.runtime._last_observation))
            state.feedback(step)
        result.append(
            (
                str(episode.episode_id),
                state.runtime.config,
                state.runtime.neural_model,
                observations,
                copy.deepcopy(state.runtime.location_sources),
            )
        )
    return result


def run(output):
    rows, source_inputs = [], []
    for episode, config, model, observations, sources in fixed_inputs():
        source_inputs.append(
            json.loads(
                canonical_json(
                    {
                        "episode_id": episode,
                        "observations": observations,
                        "paid_location_sources": sources,
                    }
                )
            )
        )
        for arm in FullJointArm:
            exact = ExactHistory(CurrentEventRuntime(arm=arm, config=config, neural_model=model))
            methods = {
                "systematic": CurrentEventRuntime(
                    arm=arm, config=config, neural_model=model, sampling_method="systematic"
                ),
                "independent_strata_v1": CurrentEventRuntime(
                    arm=arm, config=config, neural_model=model
                ),
                "bootstrap_transition": BootstrapRuntime(
                    arm=arm, config=config, neural_model=model
                ),
            }
            histories = {name: {} for name in methods}
            for index, observation in enumerate(observations):
                trace = output / f"exact-{episode}-{arm.value}-{index + 1}.jsonl.gz"
                reference = exact.advance(observation, terminal=index == 1, output=trace)
                readings = []
                for name, runtime in methods.items():
                    start = perf_counter()
                    runtime.revise(copy.deepcopy(observation))
                    runtime.verify_internal_contracts()
                    elapsed = perf_counter() - start
                    histories[name], posterior = sampled_paths(runtime, histories[name])
                    # Recover current candidate fields from the declared full support.
                    lookup = {c.key: c for c, _ in runtime._candidates(observation, None)}
                    # Regime reactivation needs the actual candidate's typed state at later depth.
                    candidates = []
                    for p in runtime.particles:
                        key = candidate_key_from_world(p.world)
                        if key not in lookup:
                            for parent in runtime._current_before["particles"]:
                                lookup.update(
                                    {c.key: c for c, _ in runtime._candidates(observation, parent)}
                                )
                        candidates.append((None, lookup[key]))
                    weights = [p.posterior_probability for p in runtime.particles]
                    margins = {}
                    for axis in AXES:
                        sampled = marginal(
                            candidates, weights, axis, runtime.unresolved_probability
                        )
                        margins[axis] = {
                            "sampled": sampled,
                            "tv": tv(reference["marginals"][axis], sampled),
                        }
                    action = runtime._posterior_action_distribution(
                        observation, include_ledger=False
                    )
                    reading = {
                        "method": name,
                        "seconds": elapsed,
                        "ess": sum(weights) ** 2 / sum(w * w for w in weights),
                        "target_evaluations": runtime.fairness_receipts[
                            -1
                        ].target_score_evaluations,
                        "candidate_support": runtime.sampling_receipts[-1]["support_size"],
                        "proposal_sha256": runtime.sampling_receipts[-1]["proposal_sha256"],
                        "sampling_seed": runtime.sampling_receipts[-1]["seed_sha256"],
                        "marginals": margins,
                        "action": {str(k): v for k, v in action.items()},
                        "action_tv": tv(reference["action"], action),
                        "reference_choice": choose_action(reference["action"]),
                        "sample_choice": choose_action(action),
                        **path_comparison(
                            reference["posterior"], posterior, runtime.unresolved_probability
                        ),
                    }
                    readings.append(reading)
                    print(
                        f"{episode} {arm.value} depth={index + 1} {name} "
                        f"actorTV={margins['placement_actor']['tv']:.4f}",
                        flush=True,
                    )
                rows.append(
                    {
                        "episode_id": episode,
                        "arm": arm.value,
                        "depth": index + 1,
                        "observation_sha256": content_sha256(observation),
                        "reference": reference["summary"],
                        "methods": readings,
                    }
                )
    return {"inputs": source_inputs, "rows": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": "native-two-step-projection-reference-v1",
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "evidence_level": "bounded_native_projection_target_not_generative_model_validation",
        "run": run(args.output),
    }
    report["content_sha256"] = content_sha256(report)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
