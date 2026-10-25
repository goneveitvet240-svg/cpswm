"""Fixed-public-evidence E1/E2 development comparison; no scientific gate claim."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from run_research_pilot import revision_stream
from verify_full_mechanism_value import CONDITIONS

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
    _CountMethod,
    _locations,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_current_event import (
    CurrentEventRuntime,
    missing_event_observation,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import _identity_probability
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    TaskSeparatedFullJointActionState,
    build_task_separated_full_joint_state,
)
from cpswm.system.reproducibility import _canonical_value, content_sha256

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "fixed-public-evidence-matched-value-v1"
NATIVE = {
    "native_joint": FullJointArm.STATEFUL_FULL_JOINT,
    "native_six_potential_ablation": FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
}
GRIDS = {
    "source_owner_counts": (1.0,),
    "latest_owner": (0.3, 0.5, 0.7),
    "recency": (0.5, 0.8, 0.95),
    "markov": (0.1, 0.5, 1.0),
    "matched_amg": (0.2, 0.33, 0.5),
}
SIMPLE = tuple(k for k in GRIDS if k != "matched_amg")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_canonical_value(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


class NoTruth:
    def truth_for(self, *_):
        raise RuntimeError("method attempted evaluator truth access")

    def visible_episodes(self, *_):
        raise RuntimeError("method attempted access to another episode")


class PublicCatalogueAdapter(D0SyntheticOracleReplayAdapter):
    """Carry the generator's pre-existing visible map, never future sightings."""

    def _convert(self, case, split, seed):
        episode, truth = super()._convert(case, split, seed)
        # Canonicalize IDs so the generator's role-based location order is not a prior.
        return episode.model_copy(
            update={"known_location_ids": tuple(sorted(case.visible.locations, key=str))}
        ), truth


def dataset_for(condition):
    return PublicCatalogueAdapter(
        validation_seeds=(7, 8, 9),
        test_seeds=(31, 32, 33),
        max_steps_per_episode=CONDITIONS[condition]["scenario_duration_days"],
        dataset_version="mechanism-value-development-20261011:" + condition,
        sealed_secret="mechanism-value-development-20261011:" + condition,
        **CONDITIONS[condition],
    ).build()


def public_header(episode):
    if not episode.known_location_ids:
        raise ValueError("explicit shared location catalogue required; no future-derived support")
    # Constructors need the target ID in steps[0], not future observations.
    return episode.model_copy(
        update={"steps": episode.steps[:1], "source_hash": content_sha256(episode.steps[:1])}
    )


class FixedEvidenceNative(TaskSeparatedFullJointActionState):
    def observe(self, step):
        old = self.runtime.step_index
        super().observe(step)
        if self.runtime.step_index == old:
            self.runtime.revise(missing_event_observation(self._state, self._episode, step))
        if self.runtime.step_index != old + 1:
            raise ValueError("each public event must produce one native update")


class OwnerHistory:
    """Public source-preserving weighted history, with no native posterior inputs."""

    def __init__(self, episode, mode, parameter):
        self.locations, self.owner = _locations(episode), episode.owner_actor_key
        self.actors = episode.resident_actor_keys
        self.mode, self.parameter = mode, parameter
        self.records = {}
        self.last = None
        self.latest_owner = None

    def observe(self, step):
        if step.step_id in self.records:
            raise ValueError("D0 repeated public event")
        if step.after is None or step.after.detected_location_id is None:
            self.records[step.step_id] = None
            return
        location = step.after.detected_location_id
        actors = (
            dict(step.actor_evidence.actor_posterior)
            if step.actor_evidence is not None
            else dict.fromkeys(self.actors, 1.0 / len(self.actors))
        )
        weight = actors.get(self.owner, 0) * _identity_probability(
            step, target_object_id=step.object_instance_id
        )
        self.records[step.step_id] = (location, weight)
        self.last = location
        if weight >= self.parameter:
            self.latest_owner = location

    def distribution(self):
        scores = dict.fromkeys(self.locations, 1.0)
        for item in self.records.values():
            if item is not None:
                scores[item[0]] += item[1]
        total = sum(scores.values())
        return {k: v / total for k, v in scores.items()}

    def predict(self):
        dist = self.distribution()
        # Match the existing simple baseline's public catalogue tie convention.
        order = tuple(sorted(self.locations, key=lambda k: -dist[k]))
        chosen = self.latest_owner if self.mode == "latest_owner" else None
        chosen = chosen or order[0]
        first = self.last or chosen
        return _Prediction(chosen, (first, *(k for k in order if k != first)))

    def feedback(self, step):
        # Supplied equally; this baseline models human history only.
        del step


def make_state(episode, method, parameter=None):
    header = public_header(episode)
    if method in NATIVE:
        original = build_task_separated_full_joint_state(
            repository_root=ROOT,
            dataset=NoTruth(),
            episode=header,
            arm=NATIVE[method],
            profile="v06",
            ciav_enabled=False,
        )
        runtime = CurrentEventRuntime(
            arm=original.runtime.arm,
            config=original.runtime.config,
            neural_model=original.runtime.neural_model,
        )
        return FixedEvidenceNative(
            original._state, header, runtime, profile=original.habit_readout_profile
        )
    if method in {"source_owner_counts", "latest_owner"}:
        return OwnerHistory(header, method, parameter)
    if method == "matched_amg":
        return _AMGOpenWorldMethod(header, mode="amg", parameter=parameter)
    if method in {"recency", "markov"}:
        return _CountMethod(header, mode=method, parameter=parameter)
    raise ValueError("unknown registered diagnostic method")


def action_payload(prediction, locations):
    if set(prediction.search_order) != set(locations) or len(prediction.search_order) != len(
        locations
    ):
        raise ValueError("action search support mismatch")
    if prediction.put_back not in locations:
        raise ValueError("put-back outside shared support")
    return {
        "put_back": str(prediction.put_back),
        "search_order": list(map(str, prediction.search_order)),
        "unknown_probability": prediction.unknown_probability,
    }


class CommitBarrier:
    """Per-step execution-order check, not an authentication boundary."""

    def __init__(self, methods, step_hash):
        self.methods, self.step_hash = set(methods), step_hash
        self.records, self.released = {}, False

    def commit(self, method, received_hash, action):
        if (
            self.released
            or method not in self.methods
            or method in self.records
            or received_hash != self.step_hash
        ):
            raise ValueError("duplicate/foreign/late action or unequal public input")
        self.records[method] = copy.deepcopy(action)

    def release(self, lookup):
        if self.released or set(self.records) != self.methods:
            raise ValueError("all method actions must commit before scoring")
        self.released = True
        return lookup()


def score(action, truth):
    true_location = str(truth.true_location)
    if true_location not in action["search_order"]:
        raise ValueError("truth outside supported D0 task; do not silently score as known")
    return {
        "put_error": int(action["put_back"] != str(truth.true_owner_habit_location)),
        "search_error": int(action["search_order"][0] != true_location),
        "rank_checks": action["search_order"].index(true_location) + 1,
    }


def state_audit(state):
    if not isinstance(state, FixedEvidenceNative):
        return {"native": False}
    r = state.runtime
    return {
        "native": True,
        "steps": r.step_index,
        "particles": len(r.particles),
        "state_sha256": r._state_sha256(),
        "ledger_head": r.rgrc_ledger.head_hash,
        "rb_sha256": content_sha256(
            [
                {
                    "weight": p.posterior_probability,
                    "cells": [(list(k), asdict(v)) for k, v in sorted(p.world.rb_cells.items())],
                }
                for p in r.particles
            ]
        ),
        "target_evaluations": sum(x.target_score_evaluations for x in r.fairness_receipts),
        "extra_ciav_queries": state._state.verification_count,
        "paid_location_sources": len(r.location_sources),
        "operator_executions": dict(
            Counter(x.operator.value for x in r.operator_flow_receipts if x.executed)
        ),
    }


def run_episode(dataset, episode, configs, *, check_full_rerun=False):
    states = {
        name: make_state(episode, method, parameter)
        for name, (method, parameter) in configs.items()
    }
    rows = {name: [] for name in states}
    costs = dict.fromkeys(states, 0.0)
    checks = []
    locations = _locations(episode)
    for index, step in enumerate(episode.steps):
        visible_hash = content_sha256(step)
        barrier = CommitBarrier(states, visible_hash)
        for name, state in states.items():
            delivered = step.model_copy(deep=True)
            start = perf_counter()
            state.observe(delivered)
            action = action_payload(state.predict(), locations)
            elapsed = perf_counter() - start
            costs[name] += elapsed
            # Detect mutation of each arm's input, not merely identical declared hashes.
            barrier.commit(name, content_sha256(delivered), action)
            row = {
                "step_id": str(step.step_id),
                "input_sha256": visible_hash,
                "action": action,
                "seconds": elapsed,
            }
            if isinstance(state, FixedEvidenceNative):
                distribution = state.runtime.action_distribution()
                row["habit_distribution"] = {str(k): v for k, v in distribution.items()}
                row["native_input_sha256"] = content_sha256(state.runtime._last_observation)
            rows[name].append(row)
        truth = barrier.release(
            lambda step_id=step.step_id: dataset.truth_for(episode.episode_id).truth_by_step[
                step_id
            ]
        )
        for name, state in states.items():
            rows[name][-1]["score"] = score(barrier.records[name], truth)
            start = perf_counter()
            state.feedback(step.model_copy(deep=True))
            costs[name] += perf_counter() - start
            if isinstance(state, FixedEvidenceNative):
                state.runtime.verify_internal_contracts()
                audit = state_audit(state)
                assert audit["extra_ciav_queries"] == audit["paid_location_sources"] == 0
                rows[name][-1]["after_feedback"] = audit
        if check_full_rerun and index + 1 in {8, 16, 32, len(episode.steps)}:
            for name, (method, parameter) in configs.items():
                if method not in NATIVE:
                    continue
                reference = make_state(episode, method, parameter)
                start = perf_counter()
                for old in episode.steps[: index + 1]:
                    reference.observe(old.model_copy(deep=True))
                    ref_action = action_payload(reference.predict(), locations)
                    reference.feedback(old.model_copy(deep=True))
                expected, actual = state_audit(reference), state_audit(states[name])
                equivalent = (
                    expected == actual
                    and ref_action == rows[name][-1]["action"]
                    and reference.runtime.action_distribution()
                    == states[name].runtime.action_distribution()
                )
                checks.append(
                    {
                        "step": index + 1,
                        "method": name,
                        "equivalent": equivalent,
                        "reference": expected,
                        "actual": actual,
                        "seconds": perf_counter() - start,
                    }
                )
                if not equivalent:
                    raise ValueError("same-model prefix replay mismatch")
    return {
        "episode_id": str(episode.episode_id),
        "episode_sha256": content_sha256(episode),
        "steps": len(episode.steps),
        "configs": configs,
        "rows": rows,
        "seconds": costs,
        "full_rerun": checks,
        "final_audits": {name: state_audit(state) for name, state in states.items()},
    }


def totals(results, method):
    points = [p for run in results for p in run["rows"][method]]
    return {
        "points": len(points),
        **{
            key: sum(p["score"][key] for p in points)
            for key in ("put_error", "search_error", "rank_checks")
        },
    }


def select_configs(trials, grids=GRIDS):
    selected, selection = {}, {}
    for method, parameters in grids.items():
        entries = [(f"{method}:{index}", parameter) for index, parameter in enumerate(parameters)]
        scores = [
            {"label": label, "parameter": parameter, **totals(trials, label)}
            for label, parameter in entries
        ]
        winner = min(range(len(scores)), key=lambda i: scores[i]["put_error"])
        selected[method] = (method, parameters[winner])
        selection[method] = {
            "criterion": "validation_put_back_error_rate",
            "trials": scores,
            "selected_index": winner,
        }
    best = min(
        SIMPLE, key=lambda method: min(item["put_error"] for item in selection[method]["trials"])
    )
    return selected, {
        "methods": selection,
        "simple_champion": best,
        "simple_champion_tie_order": SIMPLE,
    }


def paired(results, baseline, candidate="native_joint", metric="put_error"):
    summary = []
    for run in results:
        counts = Counter()
        for a, b in zip(run["rows"][candidate], run["rows"][baseline], strict=True):
            if a["step_id"] != b["step_id"] or a["input_sha256"] != b["input_sha256"]:
                raise ValueError("pairing mismatch")
            ea, eb = a["score"][metric], b["score"][metric]
            counts[
                {(0, 1): "wins", (1, 0): "losses", (0, 0): "both_correct", (1, 1): "both_wrong"}[
                    ea, eb
                ]
            ] += 1
            counts["action_disagreements"] += a["action"]["put_back"] != b["action"]["put_back"]
        summary.append({"episode_id": run["episode_id"], **dict(counts)})
    return summary


class RevisionSimpleMemory(SimulationMemory):
    def __init__(self, episode, mode, parameter):
        super().__init__(episode, ("left", "center", "right"), "source_replay", ROOT)
        self.mode, self.parameter = mode, parameter

    def destination_distribution(self):
        ordered = sorted(self.records.values(), key=lambda x: (x.occurred_at, x.event_id))
        scores = dict.fromkeys(self.locations, 1.0)
        last = None
        for obs in ordered:
            if obs.robot_generated or obs.visibility != Visibility.OBSERVED:
                continue
            weight = dict(obs.actors).get("owner", 0) * obs.identity_probability
            if self.mode == "owner_recency":
                scores = {k: v * self.parameter for k, v in scores.items()}
            scores[obs.location] += weight
            if weight >= self.parameter:
                last = obs.location
        if self.mode == "latest_owner" and last is not None:
            return {k: float(k == last) for k in scores}
        total = sum(scores.values())
        return {k: v / total for k, v in scores.items()}


def run_e2():
    rows = []
    configs = {name: (name, None) for name in sorted(SimulationMemory.ARMS)}
    for method, parameters in (
        ("latest_owner", (0.3, 0.5, 0.7)),
        ("owner_recency", (0.5, 0.8, 0.95)),
    ):
        configs.update({f"{method}:{p}": (method, p) for p in parameters})
    for condition in ("delayed_attribution", "identity_correction"):
        for trajectory in ("no_revision", "correct_late", "wrong_revision", "wrong_then_recorrect"):
            scenario, stream = revision_stream(condition, trajectory)
            stream.extend(
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
            methods = {
                name: (
                    SimulationMemory(scenario.episode_id, ("left", "center", "right"), method, ROOT)
                    if method in SimulationMemory.ARMS
                    else RevisionSimpleMemory(scenario.episode_id, method, p)
                )
                for name, (method, p) in configs.items()
            }
            points = {name: [] for name in methods}
            for obs in stream:
                actions = {}
                for name, memory in methods.items():
                    memory.ingest(obs, obs.available_at)
                    actions[name] = memory.destination()
                for name, memory in methods.items():
                    points[name].append(
                        {
                            "input_sha256": content_sha256(obs),
                            "destination": actions[name],
                            "distribution": memory.destination_distribution(),
                            "error": int(actions[name] != scenario.expected_destination),
                        }
                    )
            rows.append(
                {
                    "condition": condition,
                    "trajectory": trajectory,
                    "inputs": stream,
                    "expected_destination_evaluator_only": scenario.expected_destination,
                    "rows": points,
                    "followup_errors": {
                        k: sum(p["error"] for p in v[-3:]) for k, v in points.items()
                    },
                }
            )
    return {
        "configs": configs,
        "rows": rows,
        "scope": (
            "two controlled fixtures; all six simple configs reported; "
            "no test selection or AMG claim"
        ),
    }


def sources():
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        ROOT / "tools/run_research_pilot.py",
        ROOT / "tools/verify_full_mechanism_value.py",
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
        ROOT / "docs/reviews/pc_a/matched_value_2026-10-24/PROTOCOL.md",
        ROOT / "tools/verify_matched_value.py",
        ROOT / "uv.lock",
        ROOT / "pyproject.toml",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(output, conditions, *, quick=False):
    output.mkdir(parents=True, exist_ok=False)
    start = perf_counter()
    manifest = {
        "protocol": PROTOCOL,
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "files": sources(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "quick_development": quick,
        "scientific_acceptance": False,
    }
    if manifest["git_status"].strip() and not quick:
        raise RuntimeError("formal development run requires clean committed source")
    save(output / "manifest.json", manifest)
    summaries = {}
    for condition in conditions:
        dataset = dataset_for(condition)
        save(output / condition / "dataset-manifest.json", dataset.manifest)
        trials = []
        configs = {f"{m}:{i}": (m, p) for m, grid in GRIDS.items() for i, p in enumerate(grid)}
        for episode in dataset.visible_episodes(Split.VALIDATION):
            if quick:
                episode = episode.model_copy(update={"steps": episode.steps[:4]})
            result = run_episode(dataset, episode, configs)
            trials.append(result)
            save(output / condition / f"visible-{episode.episode_id}.json", episode)
            save(output / condition / f"validation-{episode.episode_id}.json", result)
        selected, selection = select_configs(trials)
        save(output / condition / "selection.json", selection)
        configs = {**{name: (name, None) for name in NATIVE}, **selected}
        results = []
        for episode in dataset.visible_episodes(Split.TEST):
            if quick:
                episode = episode.model_copy(update={"steps": episode.steps[:4]})
            save(
                output / condition / f"visible-{episode.episode_id}.json",
                episode.model_dump(mode="json"),
            )
            result = run_episode(dataset, episode, configs, check_full_rerun=True)
            results.append(result)
            save(output / condition / f"evaluation-{episode.episode_id}.json", result)
            save(
                output / condition / f"truth-{episode.episode_id}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            print(condition, episode.episode_id, "completed", flush=True)
        summaries[condition] = {
            "selection": selection,
            "totals": {m: totals(results, m) for m in configs},
            "paired_vs_joint": {m: paired(results, m) for m in configs if m != "native_joint"},
            "search_paired_vs_joint": {
                m: paired(results, m, metric="search_error") for m in configs if m != "native_joint"
            },
            "method_seconds": {m: sum(r["seconds"][m] for r in results) for m in configs},
            "full_rerun_checks": sum(len(r["full_rerun"]) for r in results),
        }
        save(output / "summary.json", summaries)
    save(output / "e2.json", run_e2())
    if sources() != manifest["files"]:
        raise RuntimeError("bound source changed during diagnostic")
    save(
        output / "completion.json",
        {
            "source_unchanged": True,
            "seconds": perf_counter() - start,
            "conditions": conditions,
            "quick_development": quick,
            "scope": (
                "opened D0 descriptive comparison, not confirmatory significance "
                "or full E1-E6 acceptance"
            ),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--conditions", nargs="+", choices=tuple(CONDITIONS), default=list(CONDITIONS)
    )
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    run(args.output, args.conditions, quick=args.quick)
