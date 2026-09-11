"""Read-only development audit of the already-opened P5 D0 comparison.

No production operators, selection rules, seed ranges, or historical artifacts are
changed. Private imports intentionally pin this diagnostic to the audited source.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import subprocess
import time
from collections import Counter, defaultdict
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean, median
from typing import Any, cast

import numpy as np

from cpswm.contracts import ProjectTwoDatasetSplit, reject_truth_leakage
from cpswm.system.evaluation_operations import structure_two_comparison_fairness as fairness
from cpswm.system.evaluation_operations import structure_two_p5_three_arm_death_test as base
from cpswm.system.evaluation_operations.project_two_dataset import enforce_project_two_replay_gate
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    ReadoutCorrectedDirectP5LocationAdapter,
    selected_v0_6_action_readout,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
    TypedLocationPosterior,
)
from cpswm.system.prototype_spine import ActionReadout
from cpswm.system.reproducibility import content_sha256, content_uuid

AUDIT_ID = "structure-two-comparison-window2@0.1-development-opened-D0"
BASE_COMMIT = "09eb4d48e1c11082e90ca18332d04333e6b5b47a"
DATA_CONFIG = Path("configs/project_two_datasets/d0_unseen_p5_holdout_v0_6.json")
HISTORY = Path("benchmarks/structure_two/structure_two_p5_unseen_d0_holdout_v0_1.json")
ARMS = tuple(arm.value for arm in P5ComparisonArm)
P5, LEARNED, AMG = ARMS
CATEGORIES = ("p5_wins", "p5_loses", "both_wrong", "both_correct")


def category(p5_error: int, amg_error: int) -> str:
    if p5_error not in (0, 1) or amg_error not in (0, 1):
        raise ValueError("step errors must be binary")
    return {(0, 1): "p5_wins", (1, 0): "p5_loses", (1, 1): "both_wrong", (0, 0): "both_correct"}[
        p5_error, amg_error
    ]


class CommitBarrier:
    """Local audit ordering guard, not a security or independent-custody boundary."""

    def __init__(self, episode_id: Any, step_id: Any) -> None:
        self.episode_id, self.step_id = episode_id, step_id
        self.actions: dict[str, Any] = {}
        self.released = False

    def commit(self, posterior: Any, action: Any) -> None:
        arm = posterior.arm.value
        if (
            self.released
            or arm in self.actions
            or arm not in ARMS
            or posterior.episode_id != self.episode_id
            or posterior.step_id != self.step_id
            or action.source_update_id != self.step_id
            or action.belief_state_sha256 != posterior.belief_state_sha256
        ):
            raise ValueError("duplicate, late, or mismatched action commit")
        self.actions[arm] = action

    def release(self, dataset: Any) -> Any:
        if set(self.actions) != set(ARMS) or self.released:
            raise ValueError("truth requires all three commits exactly once")
        self.released = True
        return dataset.truth_for(self.episode_id).truth_by_step[self.step_id]


def decode(posterior: Any, step: Any, index: int, run_id: Any) -> Any:
    return posterior.decode(
        step_index=index, run_execution_id=run_id, visible_observation=step.model_dump(mode="json")
    )


def with_distributions(posterior: Any, *, current: Any = None, habit: Any = None) -> Any:
    return TypedLocationPosterior.seal(
        arm=posterior.arm,
        episode_id=posterior.episode_id,
        step_id=posterior.step_id,
        target_object_id=posterior.target_object_id,
        source_visible_step_sha256=posterior.source_visible_step_sha256,
        belief_state_sha256=posterior.belief_state_sha256,
        location_support=posterior.location_support,
        current_location_distribution=current
        if current is not None
        else {v.location_id: v.probability for v in posterior.current_location_distribution},
        owner_habit_location_distribution=habit
        if habit is not None
        else {v.location_id: v.probability for v in posterior.owner_habit_location_distribution},
    )


def sensitivity(posterior: Any, step: Any, index: int, run_id: Any) -> dict[str, Any]:
    """Intervene only on legal distributions, keeping the actual observation fixed."""
    choices, puts = [], []
    for target in posterior.location_support[:2]:
        mass = {loc: float(loc == target) for loc in posterior.location_support}
        action = decode(with_distributions(posterior, current=mass), step, index, run_id)
        choices.append(str(action.search_plan[0].location_id))
        puts.append(str(action.put_back_action.location_id))
    if len(set(choices)) != 2 or len(set(puts)) != 1:
        raise AssertionError("public decoder lost SEARCH sensitivity or crossed task heads")
    return {
        "arm": posterior.arm.value,
        "search_choices": choices,
        "put_back_choices": puts,
        "visible_step_sha256": posterior.source_visible_step_sha256,
        "support": list(map(str, posterior.location_support)),
        "development_only": True,
        "search_changed": True,
        "put_back_unchanged": True,
    }


def make_states(
    episode: Any, model: Any, material: Any, smoothing: float, amg_parameter: float
) -> tuple[Any, ...]:
    return (
        ReadoutCorrectedDirectP5LocationAdapter(episode),
        base.LearnedTwoStageLocationAdapter(
            episode,
            model=model,
            location_successes=material.location_successes,
            location_totals=material.location_totals,
            smoothing=smoothing,
        ),
        base.AMGLocationAdapter(episode, parameter=amg_parameter),
    )


def score(action: Any, truth: Any) -> dict[str, Any]:
    order = [v.location_id for v in action.search_plan]
    inspected = order.index(truth.true_location) + 1 if truth.true_location in order else len(order)
    return {
        "search_error": int(order[0] != truth.true_location),
        "put_back_error": int(
            action.put_back_action.location_id != truth.true_owner_habit_location
        ),
        "normalized_search_regret": (inspected - 1) / max(1, len(order) - 1),
    }


def _distribution(values: Any) -> dict[str, float]:
    return {str(v.location_id): v.probability for v in values}


def _top(values: dict[Any, float]) -> str:
    return str(min(values, key=lambda key: (-values[key], str(key))))


def _p5_readouts(state: Any) -> dict[str, Any]:
    config = selected_v0_6_action_readout()
    result = {}
    for name, mode in (
        ("fast", ActionReadout.LATEST_OWNER_EVENT),
        ("surviving", ActionReadout.SURVIVING_OWNER_REVISIONS),
        ("regime", ActionReadout.REGIME_LOCAL),
        ("pooled", ActionReadout.HYBRID_ALPHA),
    ):
        dist = state.system.action_location_distribution(
            state.system.current_snapshot, readout=replace(config, readout=mode)
        )
        result[name] = {str(k): v for k, v in dist.items()}
    core = state.system.core
    result["state_counts"] = {
        name: len(getattr(core, name))
        for name in ("_fast_action_events", "_committed_events", "_observed_events")
    }
    return result


def evaluate_episode(
    dataset: Any, episode: Any, states: tuple[Any, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Truth is accessed only after committing all arms and alternative readouts."""
    reject_truth_leakage(episode.model_dump(mode="json"))
    schedule = base._episode_schedule_commitment(episode)
    run_id = content_uuid(AUDIT_ID, str(episode.episode_id))
    rows: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []
    prefix_support: set[Any] = set()
    last_habit = None
    habit_sequence = []
    phase = 0
    steps_since_change = 0
    last_seen_index = None
    for index, step in enumerate(episode.steps):
        packet = base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        receipts = [s.consume_matched_ciav_packet(packet, step, step_index=index) for s in states]
        base.verify_matched_consumption(receipts)
        barrier = CommitBarrier(episode.episode_id, step.step_id)
        outputs = {}
        posteriors = {}
        for state, receipt in zip(states, receipts, strict=True):
            posterior = state.predict_location_posteriors(packet)
            action = decode(posterior, step, index, run_id)
            fairness.check_decoded(posterior, action, step)
            barrier.commit(posterior, action)
            arm = state.arm.value
            posteriors[arm] = posterior
            outputs[arm] = {
                "current": _distribution(posterior.current_location_distribution),
                "habit": _distribution(posterior.owner_habit_location_distribution),
                "search_order": [str(v.location_id) for v in action.search_plan],
                "put_back": str(action.put_back_action.location_id),
                "closure": receipt.closure_kind,
                "state_changed": receipt.consumer_state_before_sha256
                != receipt.consumer_state_after_sha256,
                "provenance": {
                    "before": receipt.consumer_state_before_sha256,
                    "after": receipt.consumer_state_after_sha256,
                    "posterior": posterior.posterior_sha256,
                    "action": content_sha256(action),
                },
            }
        fairness.check_step(packet, step, list(posteriors.values()), receipts)
        raw = _p5_readouts(states[0])
        # Pure alternative reads use the same actual P5 state, never feed back into it.
        alternatives = {
            name: decode(
                with_distributions(
                    posteriors[P5], habit={loc: raw[name][str(loc)] for loc in states[0].locations}
                ),
                step,
                index,
                run_id,
            )
            for name in ("fast", "surviving", "regime", "pooled")
        }
        # AMG supplies a ranking, not a calibrated current-location posterior.
        amg_order = states[2].state.predict().search_order
        amg_rank_mass = base._normalise(
            {loc: float(len(amg_order) - rank) for rank, loc in enumerate(amg_order)},
            states[2].locations,
        )
        native_amg_action = decode(
            with_distributions(posteriors[AMG], current=amg_rank_mass), step, index, run_id
        )
        if packet.realized_detected_location_id is not None and not probes:
            probes = [sensitivity(p, step, index, run_id) for p in posteriors.values()]
        truth = barrier.release(dataset)
        for arm, action in barrier.actions.items():
            outputs[arm].update(score(action, truth))
        cause_label, event_label = base._truth_labels(episode, truth, last_habit)
        changed = last_habit is not None and truth.true_owner_habit_location != last_habit
        if changed:
            phase += 1
            steps_since_change = 0
        elif index:
            steps_since_change += 1
        recurrence = changed and truth.true_owner_habit_location in habit_sequence
        habit_sequence.append(truth.true_owner_habit_location)
        last_habit = truth.true_owner_habit_location
        prefix_support.update(
            loc
            for loc in (
                step.source_location_id,
                step.attempted_location_id,
                step.observed_destination_location_id,
            )
            if loc is not None
        )
        actor = dict(step.actor_evidence.actor_posterior) if step.actor_evidence else {}
        masses = sorted(actor.values(), reverse=True)
        gap = masses[0] - masses[1] if len(masses) > 1 else None
        observed = packet.realized_detected_location_id is not None
        if observed:
            last_seen_index = index
        tags = {
            "observation": "positive" if observed else "negative",
            "actor_evidence": "missing"
            if not masses
            else ("ambiguous_gap_le_0.2" if gap is not None and gap <= 0.2 else "clear_gap_gt_0.2"),
            "true_actor": "owner"
            if truth.true_actor == episode.owner_actor_key
            else ("unknown" if truth.true_actor == "unknown_actor" else "non_owner"),
            "mechanism": truth.true_mechanism.value,
            "phase": str(phase),
            "phase_boundary": "recurrence" if recurrence else ("change" if changed else "stable"),
            "since_change": "0-2" if steps_since_change <= 2 else "3+",
            "history_steps": f"{(index // 8) * 8}-{(index // 8) * 8 + 7}",
            "fast_surviving_agreement": str(_top(raw["fast"]) == _top(raw["surviving"])),
            "role_evidence": str(step.ordered_role_evidence is not None),
            "hidden_move_proxy": str(not observed),
        }
        rows.append(
            {
                "episode_id": str(episode.episode_id),
                "step_id": str(step.step_id),
                "step_index": index,
                "visible_step_sha256": content_sha256(step),
                "packet_sha256": packet.packet_sha256,
                "schedule_sha256": schedule,
                "truth_release": "after_all_three_and_alternative_action_commits",
                "support": list(map(str, states[0].locations)),
                "future_support_count": len(set(states[0].locations) - prefix_support),
                "detected_location": str(packet.realized_detected_location_id)
                if observed
                else None,
                "truth": truth.model_dump(mode="json"),
                "derived_cause_event_labels": [cause_label, event_label],
                "tags": tags,
                "actor_posterior": actor,
                "actor_top_two_gap": gap,
                "steps_since_change": steps_since_change,
                "observation_age": index - last_seen_index if last_seen_index is not None else None,
                "arms": outputs,
                "category": category(outputs[P5]["put_back_error"], outputs[AMG]["put_back_error"]),
                "fairness_step": {
                    "amg_owner_missing": states[2].state.amg_owner_location is None,
                    "costs": {
                        r.arm.value: {
                            k: getattr(r, k)
                            for k in (
                                "motion_cost",
                                "time_cost",
                                "interruption_cost",
                                "privacy_cost",
                                "safety_cost",
                                "privacy_budget_before",
                                "privacy_budget_after",
                            )
                        }
                        for r in receipts
                    },
                    "support_by_arm": {
                        p.arm.value: list(map(str, p.location_support)) for p in posteriors.values()
                    },
                },
                "raw_state": {
                    "p5_readouts": raw,
                    "learned_joint": states[1].last_joint.tolist(),
                    "learned_habit_counts": {str(k): v for k, v in states[1].habit_counts.items()},
                    "amg_native_search_order": list(map(str, amg_order)),
                },
                "alternative_readouts_development_only": {
                    **{
                        name: {"put_back": str(a.put_back_action.location_id), **score(a, truth)}
                        for name, a in alternatives.items()
                    },
                    "amg_native_rank": {
                        "search_order": [str(v.location_id) for v in native_amg_action.search_plan],
                        **score(native_amg_action, truth),
                    },
                },
            }
        )
    return rows, probes


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_episode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_episode[row["episode_id"]].append(row)
        for key, value in row["tags"].items():
            grouped[f"{key}={value}"].append(row)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(r["category"] for r in items)
        return {
            "steps": len(items),
            "episodes": len({r["episode_id"] for r in items}),
            "categories": {key: counts[key] for key in CATEGORIES},
            "errors": {arm: sum(r["arms"][arm]["put_back_error"] for r in items) for arm in ARMS},
            "p5_minus_amg_error": (counts["p5_loses"] - counts["p5_wins"]) / len(items),
        }

    episodes = []
    for key, items in by_episode.items():
        entry = {"episode_id": key, **summarize(items)}
        pe, ae = entry["errors"][P5], entry["errors"][AMG]
        entry["episode_comparison"] = "p5_wins" if pe < ae else ("p5_loses" if pe > ae else "tie")
        episodes.append(entry)
    return {
        "overall": summarize(rows),
        "groups": {k: summarize(v) for k, v in sorted(grouped.items())},
        "episodes": episodes,
        "episode_comparison_counts": dict(Counter(e["episode_comparison"] for e in episodes)),
        "episode_any_error_categories": dict(
            Counter(category(int(e["errors"][P5] > 0), int(e["errors"][AMG] > 0)) for e in episodes)
        ),
        "arm_metrics": {
            arm: {
                metric: mean(r["arms"][arm][metric] for r in rows)
                for metric in ("search_error", "put_back_error", "normalized_search_regret")
            }
            for arm in ARMS
        },
        "alternative_readouts_development_only": {
            name: {
                metric: mean(r["alternative_readouts_development_only"][name][metric] for r in rows)
                for metric in ("search_error", "put_back_error", "normalized_search_regret")
            }
            for name in rows[0]["alternative_readouts_development_only"]
        },
        "search_three_arm_distribution_equal_steps": sum(
            r["arms"][P5]["current"] == r["arms"][LEARNED]["current"] == r["arms"][AMG]["current"]
            for r in rows
        ),
        "future_support_exposed_steps": sum(r["future_support_count"] > 0 for r in rows),
        "known_detected_location_search_errors": sum(
            r["arms"][P5]["search_error"] for r in rows if r["detected_location"]
        ),
        "native_amg_full_rank_differs_steps": sum(
            r["arms"][AMG]["search_order"] != r["raw_state"]["amg_native_search_order"]
            for r in rows
        ),
    }


def _semantic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "arms": {
                arm: {k: v for k, v in values.items() if k != "provenance"}
                for arm, values in row["arms"].items()
            },
        }
        for row in rows
    ]


def hardware_info() -> dict[str, Any]:
    hardware = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    if platform.system() == "Darwin":
        for key in ("machdep.cpu.brand_string", "hw.memsize"):
            try:
                hardware[key] = subprocess.check_output(
                    ["sysctl", "-n", key], text=True, stderr=subprocess.PIPE
                ).strip()
            except (OSError, subprocess.SubprocessError) as error:
                hardware[key] = f"unavailable: {type(error).__name__}"

    return hardware


def resource_diagnostic(
    episodes: Any, model: Any, material: Any, smoothing: float, parameter: float, repeats: int
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("timing repeats must be positive")
    records = []
    # Rotate order, fresh episode state each time. No retained scientific metric is changed.
    for repeat in range(repeats):
        for episode in episodes:
            states = make_states(episode, model, material, smoothing, parameter)
            schedule = base._episode_schedule_commitment(episode)
            packets = [
                base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
                for step in episode.steps
            ]
            for offset in range(3):
                state = states[(repeat + offset) % 3]
                for index, (step, packet) in enumerate(zip(episode.steps, packets, strict=True)):
                    wall_start, cpu_start = time.perf_counter_ns(), time.process_time_ns()
                    state.consume_matched_ciav_packet(packet, step, step_index=index)
                    posterior = state.predict_location_posteriors(packet)
                    decode(posterior, step, index, content_uuid(AUDIT_ID, "cost"))
                    cpu_ns = time.process_time_ns() - cpu_start
                    wall_ns = time.perf_counter_ns() - wall_start
                    records.append(
                        {
                            "repeat": repeat,
                            "episode_id": str(episode.episode_id),
                            "step_index": index,
                            "arm": state.arm.value,
                            "wall_ns": wall_ns,
                            "cpu_ns": cpu_ns,
                        }
                    )
    summaries = {}
    for arm in ARMS:
        values = [r for r in records if r["arm"] == arm]
        summaries[arm] = {
            "samples": len(values),
            **{
                metric: {
                    "median_ms": median(r[metric] for r in values) / 1e6,
                    "mean_ms": mean(r[metric] for r in values) / 1e6,
                    "p95_ms": float(np.quantile([r[metric] for r in values], 0.95)) / 1e6,
                }
                for metric in ("wall_ns", "cpu_ns")
            },
        }
    hardware = hardware_info()
    return {
        "development_only": True,
        "performance_superiority_claim_allowed": False,
        "host_exclusive": False,
        "contention_boundary": "Other processes are not controlled; wall time cannot rank methods.",
        "hardware": hardware,
        "repeats": repeats,
        "episode_count": len(episodes),
        "scope": (
            "consume+state hashing+trace validation+posterior+public decode; CPU process; no GPU"
        ),
        "excluded": (
            "initialization, packet creation, training, data load, truth, scoring, disk IO, "
            "physical observation and robot execution"
        ),
        "warmup": (
            "full development diagnostic ran first; fresh per-episode state, "
            "no discarded warmup steps"
        ),
        "order": (
            "rotating arm order by repeat; first fixed test episodes; no seed selection by score"
        ),
        "summaries": summaries,
        "raw_measurements": records,
    }


@dataclass(frozen=True)
class BundleSnapshot:
    """Read once before replay; conclusions never reopen mutable bundle files."""

    payload: dict[str, Any]
    rows: list[dict[str, Any]]
    attribution: dict[str, Any] | None = None


def strict_json(raw: str | bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"DUPLICATE_JSON_KEY: {key}")
            result[key] = value
        return result

    def invalid(value: str) -> Any:
        raise ValueError(f"NONFINITE_JSON_NUMBER: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def load_bundle(output: Path, *, with_attribution: bool = False) -> BundleSnapshot:
    payload = strict_json((output / "audit.json").read_bytes())
    rows = [
        strict_json(line)
        for line in gzip.decompress((output / "steps.jsonl.gz").read_bytes()).splitlines()
    ]
    attribution = (
        strict_json((output / "attribution.json").read_bytes()) if with_attribution else None
    )
    if not isinstance(payload, dict) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("INVALID_BUNDLE_SHAPE: audit object and step objects required")
    if with_attribution and not isinstance(attribution, dict):
        raise ValueError("INVALID_ATTRIBUTION_SHAPE: object required")
    return BundleSnapshot(payload, rows, attribution)


def source_bindings(root: Path) -> dict[str, str]:
    # Bind the real CLI as well as every local source/config dependency. This is
    # a drift check, never a substitute for running those sources.
    paths = {
        HISTORY,
        DATA_CONFIG,
        base.DEFAULT_CONFIG,
        Path("apps/evaluation_runner/run_structure_two_comparison_audit.py"),
        Path("apps/evaluation_runner/_structure_two_audit_source.py"),
        Path("apps/evaluation_runner/summarize_structure_two_comparison_audit.py"),
    }
    for directory, pattern in (("src", "*.py"), ("configs", "*.json")):
        paths.update(p.relative_to(root) for p in (root / directory).rglob(pattern))
    return {
        p.as_posix(): hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(paths)
    }


def first_difference(actual: Any, expected: Any, path: str = "$") -> str | None:
    """Return a precise path, preserving sequence order, multiplicity and types."""
    if type(actual) is not type(expected):
        return f"{path} (type)"
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            return f"{path} (keys: {sorted(set(actual) ^ set(expected))[:5]})"
        for key in sorted(expected):
            difference = first_difference(actual[key], expected[key], f"{path}.{key}")
            if difference:
                return difference
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            return f"{path}.length ({len(actual)} != {len(expected)})"
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
    elif actual != expected:
        return path
    return None


def check_source_binding(snapshot: BundleSnapshot, root: Path) -> None:
    difference = first_difference(
        snapshot.payload.get("source_bindings"), source_bindings(root), "audit.source_bindings"
    )
    if difference:
        raise ValueError(f"SOURCE_BINDING_MISMATCH: {difference}")


def compare_snapshot(
    snapshot: BundleSnapshot, payload: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Low-level comparison, NOT proof if a caller supplies its own reference.

    Official CLI verification obtains the reference by run_audit in the same
    process. It exposes no cached-reference or expected-payload argument.
    """
    actual_rows = _semantic_rows(snapshot.rows)
    if content_sha256(actual_rows) != snapshot.payload["semantic_steps_sha256"]:
        raise ValueError("retained step bundle differs from its semantic commitment")
    difference = first_difference(actual_rows, _semantic_rows(rows), "steps")
    if difference:
        raise ValueError(f"FRESH_REPLAY_STEP_MISMATCH: {difference}")
    difference = first_difference(snapshot.payload, payload, "audit")
    if difference:
        raise ValueError(f"fresh diagnostic differs at {difference}")
    if content_sha256(_semantic_rows(rows)) != payload["semantic_steps_sha256"]:
        raise ValueError("fresh step bundle differs from its commitment")


def run_audit(
    root: Path, *, timing_repeats: int = 3, timing_episodes: int = 2
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    bindings = source_bindings(root)
    config = base._load_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(root / DATA_CONFIG)
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    split_episodes = {s.value: dataset.visible_episodes(s) for s in ProjectTwoDatasetSplit}
    sets = {s: {str(e.episode_id) for e in eps} for s, eps in split_episodes.items()}
    if any(sets[a] & sets[b] for a in sets for b in sets if a != b):
        raise AssertionError("split episode overlap")
    training_start = time.perf_counter()
    train_access = fairness.SplitAccess(dataset, ProjectTwoDatasetSplit.TRAIN)
    material = base._learned_training_material(cast(Any, train_access))
    selection, model, smoothing, parameter, selection_evidence = fairness.validation_selection(
        dataset, config, material
    )
    training_elapsed = time.perf_counter() - training_start
    rows: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []
    test = split_episodes[ProjectTwoDatasetSplit.TEST.value]
    consumer_probe = fairness.ConsumerProbe()
    for ordinal, episode in enumerate(test):
        with consumer_probe if ordinal == 0 else nullcontext():
            part, examples = evaluate_episode(
                dataset, episode, make_states(episode, model, material, smoothing, parameter)
            )
        rows.extend(part)
        if not probes:
            probes = examples
        if (ordinal + 1) % 10 == 0:
            print(f"audited {ordinal + 1}/{len(test)} episodes", flush=True)
    summary = aggregate(rows)
    history = json.loads((root / HISTORY).read_text())
    retained = {(r["episode_id"], r["arm"]): r for r in history["holdout_episode_metrics"]}
    parity = []
    for episode in summary["episodes"]:
        subset = [r for r in rows if r["episode_id"] == episode["episode_id"]]
        for arm in ARMS:
            old = retained[(episode["episode_id"], arm)]
            search = sum(r["arms"][arm]["search_error"] for r in subset)
            put = sum(r["arms"][arm]["put_back_error"] for r in subset)
            if (search, put) != (old["search_errors"], old["put_back_errors"]):
                parity.append(
                    {
                        "episode_id": episode["episode_id"],
                        "arm": arm,
                        "new": [search, put],
                        "retained": [old["search_errors"], old["put_back_errors"]],
                    }
                )
    if source_bindings(root) != bindings:
        raise ValueError("SOURCE_CHANGED_DURING_REPLAY")
    payload = {
        "audit_id": AUDIT_ID,
        "verification_schema_version": 4,
        "base_commit": BASE_COMMIT,
        "data_status": "already_opened_development_only",
        "source_bindings": bindings,
        "selection": selection,
        "fairness": fairness.findings(rows),
        "fairness_execution": {
            "train_access": train_access.events,
            "selection": selection_evidence,
            "consumer_probe": consumer_probe.result(),
        },
        "summary": summary,
        "search_sensitivity_counterexamples": probes,
        "retained_score_mismatches": parity,
        "split_episode_ids": {s: sorted(ids) for s, ids in sets.items()},
        "training": {
            "rows": len(material.raw),
            "raw_features": material.raw.shape[1],
            "active_logit_parameters": model.active_parameter_count,
            "projection_width": model.projection.width,
            "conditional_location_cells": model.last_joint.size
            if hasattr(model, "last_joint")
            else 9,
            "location_successes": material.location_successes.tolist(),
            "location_totals": material.location_totals.tolist(),
            "inference_multiply_adds_head_only": model.inference_multiply_adds_per_unit,
            "selected_model_training_multiply_adds_head_only": model.training_multiply_adds,
        },
        "signal_gate_retained_not_reselected": history["signal_gate"],
        "paired_episode_results_retained": history["paired_episode_results"],
        "semantic_steps_sha256": content_sha256(_semantic_rows(rows)),
        "coverage_limits": [
            "No new seeds or tests opened",
            "No external custody proof",
            "No true delayed counterevidence challenge",
            "No action-contingent environment",
            "32-step horizon only",
            "Feature-gap bins are descriptive, not causal effects",
            "No operator-removal intervention; invocation is not contribution",
            "No native P5/learned SEARCH model head is exposed by these adapters",
        ],
    }
    timing = resource_diagnostic(
        test[:timing_episodes], model, material, smoothing, parameter, timing_repeats
    )
    timing["training_and_validation_seconds_single_run"] = training_elapsed
    if source_bindings(root) != bindings:
        raise ValueError("SOURCE_CHANGED_DURING_REPLAY")
    return payload, rows, timing


def save(
    output: Path, payload: dict[str, Any], rows: list[dict[str, Any]], timing: dict[str, Any]
) -> None:
    """Create only a new audit bundle, refusing to overwrite any retained output."""
    output.mkdir(parents=True, exist_ok=True)
    for name in ("audit.json", "steps.jsonl.gz", "timing.json"):
        if (output / name).exists():
            raise FileExistsError(
                f"refusing to overwrite {output / name}; use --verify or a new directory"
            )
    for name, value in (("audit.json", payload), ("timing.json", timing)):
        (output / name).write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
    raw = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows).encode()
    (output / "steps.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))


def verify(output: Path, payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Compatibility comparator for unit tests; not an independent verification entrypoint."""
    compare_snapshot(load_bundle(output), payload, rows)
