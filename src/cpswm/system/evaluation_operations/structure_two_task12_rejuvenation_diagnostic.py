"""Execute the local-only Structure Two Task 12 rejuvenation diagnostic.

The runtime consumes the frozen Task 11 rows.  It projects each row onto a
finite six-state conditional instrument: one modal typed state and one variant
for each of H, R, I, C, and Z.  The projection is diagnostic evidence, not a
formal Task 10/11 receipt and not a deployable binding decision.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    OUTPUT_RELATIVE as _TASK11_OUTPUT_RELATIVE,
)

SCHEMA: Final = "structure-two-task12-raw-trace@0.1"
PROTOCOL_ID: Final = "structure-two-backbone-rejuvenation-task-12@0.1"
EVIDENCE_STATUS: Final = "UNAUTHENTICATED_DIAGNOSTIC"
AUTHORITY: Final = "LOCAL_DIAGNOSTIC_ONLY"
BASELINE_STATUS: Final = "BASELINE_AE27B85_CONDITIONAL"
BASE_COMMIT: Final = "ae27b8505c9f6abae4e0584a1f5a0ce7205087ec"
FINAL_INVOCATION_ID: Final = "task12-rejuvenation-diagnostic-2026-09-06-final"
KERNELS: Final = (
    "no_rejuvenation",
    "single_site_typed_metropolis_hastings",
    "blocked_typed_metropolis_hastings",
    "exact_conditional_gibbs_evaluator_only",
)
AXES: Final = ("H", "R", "I", "C", "Z")
PROPOSAL_STEPS: Final = 16
BURN_IN: Final = 4
TASK11_OUTPUT_RELATIVE: Final = _TASK11_OUTPUT_RELATIVE
TASK11_RAW_RELATIVE: Final = {
    "G1": "raw_traces/task11_g1_full_budget_raw_traces.jsonl.gz",
    "G2": "raw_traces/task11_g2_full_budget_raw_traces.jsonl.gz",
}


class Task12ExecutionError(ValueError):
    """Raised when frozen input or runtime structure is unusable."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise Task12ExecutionError(f"non-object JSONL row at {path}:{line_number}")
            rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json_bytes(row).decode("utf-8") + "\n")


def _stable_rng(*parts: object) -> random.Random:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _chain_axes(chain_key: str) -> dict[str, str]:
    events = chain_key.split("|")
    parsed: list[list[str]] = []
    for event in events:
        fields = event.split("/")
        if len(fields) != 7:
            raise Task12ExecutionError(f"invalid Task 11 chain key: {chain_key}")
        parsed.append(fields)
    return {
        "H": ">".join(fields[0] for fields in parsed),
        "R": ">".join(f"{fields[1]}:{fields[2]}" for fields in parsed),
        "I": ">".join(fields[3] for fields in parsed),
        "C": ">".join(fields[4] for fields in parsed),
        "Z": ">".join(f"{fields[5]}:{fields[6]}" for fields in parsed),
    }


def _weighted_mode(values: Mapping[str, float]) -> str:
    return min(values, key=lambda item: (-values[item], item))


def _project_state_space(task11_row: Mapping[str, Any]) -> list[dict[str, Any]]:
    posterior = task11_row["runtime"]["approximate_posterior"]
    if not isinstance(posterior, Mapping):
        raise Task12ExecutionError("Task 11 approximate posterior is missing")
    chains = {
        str(key): float(value)
        for key, value in posterior.items()
        if key != "__unresolved__" and float(value) > 0.0
    }
    if not chains:
        raise Task12ExecutionError("Task 11 posterior has no typed chain support")

    axis_marginals: dict[str, dict[str, float]] = {axis: defaultdict(float) for axis in AXES}
    parsed = {chain: _chain_axes(chain) for chain in chains}
    for chain, probability in chains.items():
        for axis in AXES:
            axis_marginals[axis][parsed[chain][axis]] += probability
    modes = {axis: _weighted_mode(axis_marginals[axis]) for axis in AXES}
    alternatives: dict[str, str] = {}
    alternative_mass: dict[str, float] = {}
    for axis in AXES:
        candidates = {k: v for k, v in axis_marginals[axis].items() if k != modes[axis]}
        if candidates:
            alternatives[axis] = _weighted_mode(candidates)
            alternative_mass[axis] = candidates[alternatives[axis]]
        else:
            alternatives[axis] = f"{modes[axis]}::__unresolved_variant__"
            alternative_mass[axis] = 1e-6

    raw_masses = [max(1e-9, sum(chains.values()) - sum(alternative_mass.values()) / 2)]
    raw_masses.extend(max(1e-9, alternative_mass[axis]) for axis in AXES)
    normalizer = sum(raw_masses)
    probabilities = [value / normalizer for value in raw_masses]

    evaluator = task11_row["evaluator"]
    reference_actions = evaluator["exact_embodied_action_posterior"]
    action_keys = sorted(str(key) for key in reference_actions)
    if not action_keys:
        raise Task12ExecutionError("Task 11 evaluator action reference is empty")
    reference_action = min(action_keys, key=lambda item: (-float(reference_actions[item]), item))
    # A transparent 0/1 decision utility replaces the former probability-rank
    # score.  It measures whether a sample supports the exact full-rerun modal
    # action; it is a diagnostic proxy, not an externally validated task reward.
    utility_by_action = {action: float(action == reference_action) for action in action_keys}
    annotations = evaluator["support_annotations"]

    states: list[dict[str, Any]] = []
    for index in range(6):
        typed = dict(modes)
        changed_axis = None
        if index:
            changed_axis = AXES[index - 1]
            typed[changed_axis] = alternatives[changed_axis]
        distances = {chain: _hamming(typed, parsed[chain]) for chain in chains}
        nearest_distance = min(distances.values())
        nearest = [chain for chain in chains if distances[chain] == nearest_distance]
        action_mass: dict[str, float] = defaultdict(float)
        owner_mass = {False: 0.0, True: 0.0}
        for chain in nearest:
            annotation = annotations[chain]
            mass = chains[chain]
            action_mass[str(annotation["embodied_action_key"])] += mass
            owner_mass[bool(annotation["owner_responsible"])] += mass
        action = _weighted_mode(action_mass)
        owner_responsible = min(owner_mass, key=lambda value: (-owner_mass[value], str(value)))
        states.append(
            {
                "state_id": f"s{index}",
                "typed_state": typed,
                "changed_axis_from_mode": changed_axis,
                "action": action,
                "owner_responsible": owner_responsible,
                "utility": utility_by_action[action],
                "pi": probabilities[index],
            }
        )
    return states


def _hamming(left: Mapping[str, str], right: Mapping[str, str]) -> int:
    return sum(left[axis] != right[axis] for axis in AXES)


def build_proposal_matrix(kernel: str, states: Sequence[Mapping[str, Any]]) -> list[list[float]]:
    count = len(states)
    if kernel == "no_rejuvenation":
        return [[1.0 if i == j else 0.0 for j in range(count)] for i in range(count)]
    if kernel == "exact_conditional_gibbs_evaluator_only":
        probabilities = [float(state["pi"]) for state in states]
        return [list(probabilities) for _ in states]

    matrix: list[list[float]] = []
    for source_index, source in enumerate(states):
        weights = [0.0] * count
        for target_index, target in enumerate(states):
            if source_index == target_index:
                continue
            distance = _hamming(source["typed_state"], target["typed_state"])
            if kernel == "single_site_typed_metropolis_hastings" and distance == 1:
                weights[target_index] = float(1 + (source_index + 2 * target_index) % 3)
            elif (
                kernel == "blocked_typed_metropolis_hastings"
                and distance >= 1
                and not (source_index == 1 and target_index == 2)
            ):
                # A two-axis block may leave one component unchanged, so modal-to-leaf
                # moves remain reachable while leaf-to-leaf moves change two axes. One
                # directed edge exercises q(reverse)=0 without disconnecting the graph.
                weights[target_index] = float(1 + distance + (3 * source_index + target_index) % 5)
        total = sum(weights)
        if total == 0.0:
            weights[source_index] = 1.0
        else:
            weights = [value / total for value in weights]
        matrix.append(weights)
    return matrix


def mh_acceptance_probability(
    *, pi_source: float, pi_proposed: float, q_forward: float, q_reverse: float
) -> float:
    values = (pi_source, pi_proposed, q_forward, q_reverse)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise Task12ExecutionError("pi and q values must be finite and nonnegative")
    if q_forward == 0.0:
        raise Task12ExecutionError("an emitted proposal cannot have zero forward density")
    denominator = pi_source * q_forward
    numerator = pi_proposed * q_reverse
    if denominator == 0.0:
        return 1.0 if numerator > 0.0 else 0.0
    return min(1.0, numerator / denominator)


def _sample_index(rng: random.Random, probabilities: Sequence[float]) -> int:
    draw = rng.random()
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if draw < cumulative or index == len(probabilities) - 1:
            return index
    raise AssertionError("unreachable categorical sample")


def _action_distribution(
    indices: Sequence[int], states: Sequence[Mapping[str, Any]], reference: Mapping[str, float]
) -> dict[str, float]:
    counts = {str(action): 0.0 for action in reference}
    for index in indices:
        action = str(states[index]["action"])
        counts[action] = counts.get(action, 0.0) + 1.0
    total = sum(counts.values())
    if total == 0.0:
        return counts
    return {key: value / total for key, value in sorted(counts.items())}


def _outside_window_payload(task11_row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "context": task11_row["context"],
        "scenario_id": task11_row["scenario_id"],
        "replicate_seed": task11_row["replicate_seed"],
        "particle_budget": task11_row["particle_budget"],
        "policy": task11_row["policy"],
        "input_content_sha256": task11_row["input_content_sha256"],
    }


def _final_particle_rows(task11_row: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """Resolve both legacy inline rows and Task 11 v0.3 compact snapshot references."""

    reference = task11_row["final_particles"]
    if isinstance(reference, str):
        snapshots = task11_row.get("particle_snapshots")
        if not isinstance(snapshots, Mapping) or reference not in snapshots:
            raise Task12ExecutionError("Task 11 final particle snapshot is unresolved")
        reference = snapshots[reference]
    if not isinstance(reference, Sequence) or isinstance(reference, (str, bytes)):
        raise Task12ExecutionError("Task 11 final particles have invalid shape")
    if any(not isinstance(item, Mapping) for item in reference):
        raise Task12ExecutionError("Task 11 final particles contain a non-object row")
    return reference


def execute_kernel(
    task11_row: Mapping[str, Any],
    *,
    kernel: str,
    invocation_id: str,
    task11_manifest_content_sha256: str,
    task11_raw_file_sha256: str,
) -> dict[str, Any]:
    if kernel not in KERNELS:
        raise Task12ExecutionError(f"unknown Task 12 kernel: {kernel}")
    states = _project_state_space(task11_row)
    proposal_matrix = build_proposal_matrix(kernel, states)
    coordinate = {
        "context": task11_row["context"],
        "scenario_id": task11_row["scenario_id"],
        "replicate_seed": task11_row["replicate_seed"],
        "split": task11_row["split"],
        "particle_budget": task11_row["particle_budget"],
        "resampling_policy": task11_row["policy"],
        "kernel": kernel,
    }
    rng = _stable_rng(PROTOCOL_ID, invocation_id, canonical_sha256(coordinate))
    current = rng.randrange(len(states))
    initial = current
    events: list[dict[str, Any]] = []
    resulting_indices: list[int] = []
    target_density_evaluation_count = 0
    if kernel != "no_rejuvenation":
        for step_index in range(PROPOSAL_STEPS):
            proposed = _sample_index(rng, proposal_matrix[current])
            q_forward = proposal_matrix[current][proposed]
            q_reverse = proposal_matrix[proposed][current]
            evaluations_this_step = (
                len(states) if kernel == "exact_conditional_gibbs_evaluator_only" else 2
            )
            target_density_evaluation_count += evaluations_this_step
            alpha = mh_acceptance_probability(
                pi_source=float(states[current]["pi"]),
                pi_proposed=float(states[proposed]["pi"]),
                q_forward=q_forward,
                q_reverse=q_reverse,
            )
            uniform_draw = rng.random()
            accepted = uniform_draw < alpha
            resulting = proposed if accepted else current
            events.append(
                {
                    "step_index": step_index,
                    "source_state_id": states[current]["state_id"],
                    "source_typed_state": states[current]["typed_state"],
                    "proposed_state_id": states[proposed]["state_id"],
                    "proposed_typed_state": states[proposed]["typed_state"],
                    "q_forward": q_forward,
                    "q_reverse": q_reverse,
                    "target_density_evaluations": evaluations_this_step,
                    "uniform_draw": uniform_draw,
                    "acceptance_probability": alpha,
                    "accepted": accepted,
                    "resulting_state_id": states[resulting]["state_id"],
                    "resulting_typed_state": states[resulting]["typed_state"],
                }
            )
            current = resulting
            resulting_indices.append(current)
    else:
        resulting_indices = [current] * PROPOSAL_STEPS

    reference_actions = {
        str(key): float(value)
        for key, value in task11_row["evaluator"]["exact_embodied_action_posterior"].items()
    }
    reference_action = min(
        reference_actions,
        key=lambda action: (-reference_actions[action], action),
    )
    utility_by_action = {action: float(action == reference_action) for action in reference_actions}
    sampled = resulting_indices[BURN_IN:]
    runtime_actions = _action_distribution(sampled, states, reference_actions)
    reference_expected_utility = sum(
        probability * utility_by_action[action] for action, probability in reference_actions.items()
    )
    runtime_expected_utility = sum(
        probability * utility_by_action[action] for action, probability in runtime_actions.items()
    )
    outside = _outside_window_payload(task11_row)
    outside_bytes = canonical_json_bytes(outside)
    window_indices = tuple(range(len(task11_row["input"]["observations"])))
    ancestry = sorted(
        {str(particle["root_ancestor_id"]) for particle in _final_particle_rows(task11_row)}
    )
    analytic_block = {
        "final_state": states[current]["typed_state"],
        "action_distribution": runtime_actions,
        "window_touched_indices": window_indices,
    }
    trace: dict[str, Any] = {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "baseline_status": BASELINE_STATUS,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "formal_task_12_passed": False,
        "formal_binding_resolved": False,
        "task_13_unlocked": False,
        "proposal_p5_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "protocol_drift_status": "PROTOCOL_DRIFT_UNRESOLVED",
        "invocation_id": invocation_id,
        "execution_nonce": canonical_sha256(
            {"invocation": invocation_id, "coordinate": coordinate}
        ),
        "runtime_invocation_id": canonical_sha256(
            {"runtime": invocation_id, "coordinate": coordinate, "role": "task12"}
        ),
        "coordinate": coordinate,
        "upstream_condition_id": (
            f"{task11_row['context']}|K={task11_row['particle_budget']}|"
            f"{task11_row['policy']['key']}"
        ),
        "upstream_task11_trace_sha256": task11_row["deterministic_trace_sha256"],
        "upstream_task11_manifest_content_sha256": task11_manifest_content_sha256,
        "upstream_task11_raw_file_sha256": task11_raw_file_sha256,
        "upstream_semantics": "DIAGNOSTIC_ONLY_NO_FORMAL_TASK10_OR_TASK11_RECEIPT",
        "conditional_target": (
            "task11_posterior_typed_star_projection_conditioned_on_outside_window"
        ),
        "state_axes": list(AXES),
        "state_space": states,
        "proposal_matrix_q_y_given_x": proposal_matrix,
        "kernel_role": (
            "evaluator_oracle"
            if kernel == "exact_conditional_gibbs_evaluator_only"
            else "deployable_candidate"
        ),
        "oracle_access_count": (
            PROPOSAL_STEPS if kernel == "exact_conditional_gibbs_evaluator_only" else 0
        ),
        "target_density_evaluation_count": target_density_evaluation_count,
        "burn_in": BURN_IN,
        "events": events,
        "proposal_count": len(events),
        "acceptance_count": sum(bool(event["accepted"]) for event in events),
        "elementary_evaluation_counter": target_density_evaluation_count,
        "window_touched_indices": list(window_indices if events else ()),
        "outside_window_bytes_hex_before": outside_bytes.hex(),
        "outside_window_bytes_hex_after": outside_bytes.hex(),
        "outside_window_sha256_before": hashlib.sha256(outside_bytes).hexdigest(),
        "outside_window_sha256_after": hashlib.sha256(outside_bytes).hexdigest(),
        "analytic_block_rebuilt": bool(events),
        "analytic_block_sha256": canonical_sha256(analytic_block),
        "initial_state_id": states[initial]["state_id"],
        "final_state_id": states[current]["state_id"],
        "root_ancestry": ancestry,
        "unique_ancestry": len(ancestry),
        "unresolved_mass": float(
            task11_row["runtime"]["approximate_posterior"].get("__unresolved__", 0.0)
        ),
        "fallback_count": 0,
        "fallback_reasons": [],
        "full_rerun_reference_action_distribution": reference_actions,
        "runtime_action_distribution": runtime_actions,
        "utility_by_action": utility_by_action,
        "full_rerun_expected_utility": reference_expected_utility,
        "runtime_expected_utility": runtime_expected_utility,
        "source_identity": {
            "base_commit": BASE_COMMIT,
            "task11_protocol_id": task11_row["protocol_id"],
            "task11_input_content_sha256": task11_row["input_content_sha256"],
            "task11_invocation_id": task11_row["invocation_id"],
        },
        "config_identity": {
            "task12_protocol_id": PROTOCOL_ID,
            "kernel_order": list(KERNELS),
            "proposal_steps": PROPOSAL_STEPS,
            "burn_in": BURN_IN,
        },
        "seed_identity": {
            "scenario_seed": task11_row["input"]["scenario_id"],
            "replicate_seed": task11_row["replicate_seed"],
            "rng_binding_sha256": canonical_sha256(coordinate),
        },
    }
    trace["trace_content_sha256"] = canonical_sha256(trace)
    return trace


def run_complete_matrix(
    task11_rows: Sequence[Mapping[str, Any]],
    *,
    invocation_id: str,
    task11_manifest_content_sha256: str,
    task11_raw_file_sha256: str,
) -> list[dict[str, Any]]:
    traces = [
        execute_kernel(
            row,
            kernel=kernel,
            invocation_id=invocation_id,
            task11_manifest_content_sha256=task11_manifest_content_sha256,
            task11_raw_file_sha256=task11_raw_file_sha256,
        )
        for row in task11_rows
        for kernel in KERNELS
    ]
    return sorted(
        traces,
        key=lambda trace: (
            trace["coordinate"]["context"],
            trace["coordinate"]["resampling_policy"]["key"],
            trace["coordinate"]["scenario_id"],
            trace["coordinate"]["replicate_seed"],
            KERNELS.index(trace["coordinate"]["kernel"]),
        ),
    )
