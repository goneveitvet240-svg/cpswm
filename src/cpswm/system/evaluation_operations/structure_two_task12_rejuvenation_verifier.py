"""Independent recomputation for Structure Two Task 12 raw traces.

This verifier treats every caller-supplied metric, gate, disposition, selection,
and result hash as untrusted.  It derives the complete transition matrix and all
reported diagnostics from raw states, q matrices, proposal events, and the
frozen Task 11 inputs.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Final

from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    AUTHORITY as TASK11_AUTHORITY,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    EVIDENCE_STATUS as TASK11_EVIDENCE_STATUS,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    MANIFEST_SCHEMA as TASK11_MANIFEST_SCHEMA,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    deterministic_result_projection as task11_deterministic_result_projection,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    verify_raw_trace as verify_task11_raw_trace,
)
from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_diagnostic import (
    AUTHORITY,
    AXES,
    BASELINE_STATUS,
    BURN_IN,
    EVIDENCE_STATUS,
    FINAL_INVOCATION_ID,
    KERNELS,
    PROPOSAL_STEPS,
    PROTOCOL_ID,
    SCHEMA,
    TASK11_RAW_RELATIVE,
    _final_particle_rows,
    canonical_sha256,
    execute_kernel,
    mh_acceptance_probability,
)

JSON_THRESHOLD: Final = 1e-6
DOCUMENT_THRESHOLD: Final = 1e-9
DETAILED_BALANCE_THRESHOLD: Final = 1e-9
ACTOR_DISTANCE_THRESHOLD: Final = 0.05
OWNER_CONTAMINATION_THRESHOLD: Final = 0.05


class Task12VerificationError(ValueError):
    """Raised when raw evidence is incomplete, substituted, or inconsistent."""


def _close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task12VerificationError(message)


def _state_index(states: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    mapping = {str(state["state_id"]): index for index, state in enumerate(states)}
    _require(len(mapping) == len(states), "duplicate state id")
    return mapping


def _transition_matrix(
    states: Sequence[Mapping[str, Any]], proposal: Sequence[Sequence[float]]
) -> list[list[float]]:
    count = len(states)
    transition = [[0.0] * count for _ in range(count)]
    for source in range(count):
        for proposed in range(count):
            if proposed == source or proposal[source][proposed] == 0.0:
                continue
            alpha = mh_acceptance_probability(
                pi_source=float(states[source]["pi"]),
                pi_proposed=float(states[proposed]["pi"]),
                q_forward=float(proposal[source][proposed]),
                q_reverse=float(proposal[proposed][source]),
            )
            transition[source][proposed] = float(proposal[source][proposed]) * alpha
        transition[source][source] = 1.0 - sum(transition[source])
        _require(transition[source][source] >= -1e-12, "transition row exceeds one")
        transition[source][source] = max(0.0, transition[source][source])
    return transition


def _is_irreducible(transition: Sequence[Sequence[float]]) -> bool:
    count = len(transition)
    for start in range(count):
        reached = {start}
        frontier = [start]
        while frontier:
            source = frontier.pop()
            for target, probability in enumerate(transition[source]):
                if probability > 0.0 and target not in reached:
                    reached.add(target)
                    frontier.append(target)
        if len(reached) != count:
            return False
    return True


def _distribution_tv(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    return 0.5 * sum(
        abs(float(left.get(k, 0.0)) - float(right.get(k, 0.0))) for k in set(left) | set(right)
    )


def _lag_one_autocorrelation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator <= 1e-15:
        return 1.0
    numerator = sum((values[i] - mean) * (values[i - 1] - mean) for i in range(1, len(values)))
    return max(-1.0, min(1.0, numerator / denominator))


def _sample_distribution(
    indices: Sequence[int], states: Sequence[Mapping[str, Any]], field: str
) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for index in indices:
        if field == "action":
            key = str(states[index]["action"])
        else:
            key = str(states[index]["typed_state"][field])
        counts[key] += 1
    total = sum(counts.values())
    return {key: value / total for key, value in sorted(counts.items())} if total else {}


def _actor_from_action(action: str) -> str:
    parts = action.split("|", 1)
    _require(len(parts) == 2 and bool(parts[1]), "malformed embodied action actor")
    return parts[1]


def _actor_distribution(actions: Mapping[str, float]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for action, probability in actions.items():
        result[_actor_from_action(str(action))] += float(probability)
    return dict(sorted(result.items()))


def verify_task11_dependencies(
    *,
    task11_rows: Sequence[Mapping[str, Any]],
    task11_result: Mapping[str, Any],
    task11_manifest: Mapping[str, Any],
    task11_raw_hashes_by_context: Mapping[str, str],
) -> None:
    """Fail closed when an upstream object is merely self-consistent or relabelled."""

    unsigned_manifest = dict(task11_manifest)
    reported_manifest_hash = unsigned_manifest.pop("content_sha256", None)
    _require(
        reported_manifest_hash == canonical_sha256(unsigned_manifest),
        "Task 11 manifest self-hash mismatch",
    )
    _require(
        task11_manifest.get("schema") == TASK11_MANIFEST_SCHEMA,
        "Task 11 manifest schema substitution",
    )
    _require(
        task11_manifest.get("evidence_status") == TASK11_EVIDENCE_STATUS,
        "Task 11 evidence escalation",
    )
    _require(
        task11_manifest.get("authority") == TASK11_AUTHORITY,
        "Task 11 authority escalation",
    )
    for field in (
        "formal_binding_resolved",
        "task_12_unlocked",
        "seven_operator_ablation_authorized",
    ):
        _require(task11_manifest.get(field) is False, f"Task 11 manifest escalation: {field}")
    artifact_hashes = task11_manifest.get("artifact_hashes")
    _require(isinstance(artifact_hashes, Mapping), "Task 11 artifact hashes missing")
    assert isinstance(artifact_hashes, Mapping)
    for context, relative in TASK11_RAW_RELATIVE.items():
        _require(
            artifact_hashes.get(relative) == task11_raw_hashes_by_context.get(context),
            f"Task 11 {context} raw hash is not bound by its manifest",
        )

    _require(len(task11_rows) == 1872, "Task 11 K=24 slice row count substitution")
    coordinates: set[tuple[str, str, int, str]] = set()
    for trace in task11_rows:
        row = verify_task11_raw_trace(trace)
        _require(row["particle_budget"] == 24, "Task 11 non-K=24 row entered Task 12")
        coordinate = (
            str(row["context"]),
            str(row["scenario_id"]),
            int(row["replicate_seed"]),
            str(row["policy"]["key"]),
        )
        _require(coordinate not in coordinates, "duplicate Task 11 K=24 coordinate")
        coordinates.add(coordinate)
    projected = task11_deterministic_result_projection(task11_result)
    _require(
        task11_result.get("deterministic_result_sha256") == canonical_sha256(projected),
        "Task 11 deterministic result self-projection hash substitution",
    )


def _task11_fidelity_by_condition(task11_result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for condition in task11_result["conditions"]:
        metrics = condition["confirmatory"]
        gates = condition["gates"]
        passed = (
            all(bool(value) for value in gates.values())
            and float(metrics["posterior_total_variation"]) <= 0.05
            and float(metrics["owner_contamination"]) <= 0.05
            and abs(float(metrics["log_normalizer_bias"])) <= 0.05
        )
        condition_id = (
            f"{condition['context']}|K={condition['particle_budget']}|{condition['policy']['key']}"
        )
        output[condition_id] = {
            "fidelity_passed": passed,
            "posterior_total_variation": metrics["posterior_total_variation"],
            "owner_contamination": metrics["owner_contamination"],
            "absolute_log_normalizer_bias": abs(float(metrics["log_normalizer_bias"])),
            "all_task11_gates_passed": all(bool(value) for value in gates.values()),
        }
    return output


def verify_trace(
    trace: Mapping[str, Any],
    *,
    task11_row: Mapping[str, Any],
    expected_manifest_content_sha256: str,
    expected_task11_raw_file_sha256: str,
) -> dict[str, Any]:
    forbidden_caller_conclusions = {
        "selected_kernel",
        "reported_gates",
        "disposition",
        "deterministic_result_sha256",
        "caller_signing_key",
        "formal_receipt",
    }
    _require(
        not forbidden_caller_conclusions.intersection(trace),
        "raw trace contains a caller-selected conclusion or trust key",
    )
    caller = dict(trace)
    stored_trace_hash = caller.pop("trace_content_sha256", None)
    _require(stored_trace_hash == canonical_sha256(caller), "trace content hash mismatch")
    _require(trace.get("schema") == SCHEMA, "trace schema substitution")
    _require(trace.get("protocol_id") == PROTOCOL_ID, "trace protocol substitution")
    _require(trace.get("baseline_status") == BASELINE_STATUS, "baseline status substitution")
    _require(trace.get("evidence_status") == EVIDENCE_STATUS, "evidence status escalation")
    _require(trace.get("authority") == AUTHORITY, "authority escalation")
    for field in (
        "formal_task_12_passed",
        "formal_binding_resolved",
        "task_13_unlocked",
        "proposal_p5_unlocked",
        "seven_operator_ablation_authorized",
    ):
        _require(trace.get(field) is False, f"forbidden positive field: {field}")
    _require(
        trace.get("protocol_drift_status") == "PROTOCOL_DRIFT_UNRESOLVED",
        "protocol drift was hidden",
    )
    _require(trace.get("invocation_id") == FINAL_INVOCATION_ID, "invocation replay/substitution")
    coordinate = trace["coordinate"]
    kernel = str(coordinate["kernel"])
    _require(kernel in KERNELS, "kernel substitution")
    expected_coordinate = {
        "context": task11_row["context"],
        "scenario_id": task11_row["scenario_id"],
        "replicate_seed": task11_row["replicate_seed"],
        "split": task11_row["split"],
        "particle_budget": task11_row["particle_budget"],
        "resampling_policy": task11_row["policy"],
        "kernel": kernel,
    }
    _require(coordinate == expected_coordinate, "upstream coordinate substitution")
    expected_nonce = canonical_sha256({"invocation": FINAL_INVOCATION_ID, "coordinate": coordinate})
    expected_runtime_id = canonical_sha256(
        {"runtime": FINAL_INVOCATION_ID, "coordinate": coordinate, "role": "task12"}
    )
    _require(trace.get("execution_nonce") == expected_nonce, "execution nonce replay/substitution")
    _require(
        trace.get("runtime_invocation_id") == expected_runtime_id,
        "runtime invocation id substitution",
    )
    _require(
        trace.get("upstream_task11_trace_sha256") == task11_row["deterministic_trace_sha256"],
        "Task 11 trace substitution",
    )
    _require(
        trace.get("upstream_task11_manifest_content_sha256") == expected_manifest_content_sha256,
        "Task 11 manifest substitution",
    )
    _require(
        trace.get("upstream_task11_raw_file_sha256") == expected_task11_raw_file_sha256,
        "Task 11 raw shard substitution",
    )

    expected_trace = execute_kernel(
        task11_row,
        kernel=kernel,
        invocation_id=FINAL_INVOCATION_ID,
        task11_manifest_content_sha256=expected_manifest_content_sha256,
        task11_raw_file_sha256=expected_task11_raw_file_sha256,
    )
    expected_unsigned = dict(expected_trace)
    expected_unsigned.pop("trace_content_sha256")
    _require(caller == expected_unsigned, "deterministic raw field substitution")

    states = trace["state_space"]
    _require(
        isinstance(states, Sequence) and len(states) == 6,
        "finite state space must contain six states",
    )
    indices = _state_index(states)
    _require(tuple(trace.get("state_axes", ())) == AXES, "typed axes missing or reordered")
    probabilities = [float(state["pi"]) for state in states]
    _require(
        all(math.isfinite(value) and value > 0.0 for value in probabilities),
        "invalid target probability",
    )
    _require(_close(sum(probabilities), 1.0), "target distribution is not normalized")
    for state in states:
        _require(set(state["typed_state"]) == set(AXES), "state lacks an H/R/I/C/Z axis")

    proposal = trace["proposal_matrix_q_y_given_x"]
    _require(len(proposal) == len(states), "proposal matrix row count mismatch")
    for row in proposal:
        _require(len(row) == len(states), "proposal matrix column count mismatch")
        _require(
            all(math.isfinite(float(value)) and float(value) >= 0.0 for value in row),
            "invalid proposal density",
        )
        _require(_close(sum(float(value) for value in row), 1.0), "proposal row is not normalized")
    transition = _transition_matrix(states, proposal)
    detailed_balance_error = max(
        abs(probabilities[i] * transition[i][j] - probabilities[j] * transition[j][i])
        for i in range(len(states))
        for j in range(len(states))
    )
    stationary = [
        sum(probabilities[i] * transition[i][j] for i in range(len(states)))
        for j in range(len(states))
    ]
    stationary_error = max(abs(stationary[j] - probabilities[j]) for j in range(len(states)))
    state_machine_reachable = kernel == "no_rejuvenation" or _is_irreducible(transition)

    events = trace["events"]
    expected_events = 0 if kernel == "no_rejuvenation" else PROPOSAL_STEPS
    _require(len(events) == expected_events, "proposal event count mismatch")
    current = indices[str(trace["initial_state_id"])]
    resulting_indices: list[int] = []
    axis_jumps = {axis: 0.0 for axis in AXES}
    non_self_moves = 0
    zero_acceptance_paths = 0
    full_acceptance_paths = 0
    accepted_count = 0
    target_density_evaluation_count = 0
    for expected_step, event in enumerate(events):
        _require(event["step_index"] == expected_step, "event order substitution")
        source = indices[str(event["source_state_id"])]
        proposed = indices[str(event["proposed_state_id"])]
        _require(source == current, "event source is unreachable from previous result")
        _require(
            event["source_typed_state"] == states[source]["typed_state"],
            "source state label substitution",
        )
        _require(
            event["proposed_typed_state"] == states[proposed]["typed_state"],
            "proposed state label substitution",
        )
        q_forward = float(proposal[source][proposed])
        q_reverse = float(proposal[proposed][source])
        expected_step_cost = (
            len(states) if kernel == "exact_conditional_gibbs_evaluator_only" else 2
        )
        _require(
            int(event["target_density_evaluations"]) == expected_step_cost,
            "per-event evaluation counter substitution",
        )
        target_density_evaluation_count += expected_step_cost
        _require(
            _close(float(event["q_forward"]), q_forward), "forward proposal density substitution"
        )
        _require(
            _close(float(event["q_reverse"]), q_reverse), "reverse proposal density substitution"
        )
        alpha = mh_acceptance_probability(
            pi_source=probabilities[source],
            pi_proposed=probabilities[proposed],
            q_forward=q_forward,
            q_reverse=q_reverse,
        )
        _require(
            _close(float(event["acceptance_probability"]), alpha),
            "MH acceptance ratio substitution",
        )
        uniform = float(event["uniform_draw"])
        _require(math.isfinite(uniform) and 0.0 <= uniform < 1.0, "invalid uniform draw")
        accepted = uniform < alpha
        _require(bool(event["accepted"]) == accepted, "accepted path substitution")
        resulting = proposed if accepted else source
        _require(
            str(event["resulting_state_id"]) == str(states[resulting]["state_id"]),
            "result state substitution",
        )
        _require(
            event["resulting_typed_state"] == states[resulting]["typed_state"],
            "result typed state substitution",
        )
        if alpha == 0.0:
            zero_acceptance_paths += 1
        if alpha == 1.0:
            full_acceptance_paths += 1
        if accepted:
            accepted_count += 1
            if resulting != source:
                non_self_moves += 1
                for axis in AXES:
                    axis_jumps[axis] += float(
                        states[source]["typed_state"][axis]
                        != states[resulting]["typed_state"][axis]
                    )
        current = resulting
        resulting_indices.append(current)
    if not events:
        resulting_indices = [current] * PROPOSAL_STEPS

    _require(int(trace["proposal_count"]) == len(events), "caller proposal count substitution")
    _require(
        int(trace["acceptance_count"]) == accepted_count, "caller acceptance count substitution"
    )
    expected_cost = {
        "no_rejuvenation": 0,
        "single_site_typed_metropolis_hastings": 2 * PROPOSAL_STEPS,
        "blocked_typed_metropolis_hastings": 2 * PROPOSAL_STEPS,
        "exact_conditional_gibbs_evaluator_only": len(states) * PROPOSAL_STEPS,
    }[kernel]
    _require(
        int(trace["target_density_evaluation_count"])
        == target_density_evaluation_count
        == expected_cost,
        "target-density evaluation counter substitution",
    )
    _require(
        int(trace["elementary_evaluation_counter"]) == expected_cost,
        "evaluation counter substitution",
    )

    post_burn = resulting_indices[BURN_IN:]
    # State IDs are categorical.  Autocorrelation over their arbitrary integer
    # labels changes under a pure relabelling, so use log target density instead.
    autocorrelation = _lag_one_autocorrelation(
        [math.log(probabilities[value]) for value in post_burn]
    )
    lag_one_ess = (
        0.0
        if autocorrelation >= 1.0
        else len(post_burn) * max(0.0, (1.0 - autocorrelation) / (1.0 + autocorrelation))
    )
    action_empirical = _sample_distribution(post_burn, states, "action")
    reference_actions = {
        str(k): float(v)
        for k, v in task11_row["evaluator"]["exact_embodied_action_posterior"].items()
    }
    action_empirical = {
        action: action_empirical.get(action, 0.0)
        for action in sorted(set(reference_actions) | set(action_empirical))
    }
    actor_empirical = _actor_distribution(action_empirical)
    actor_reference = _actor_distribution(reference_actions)
    actor_distance = _distribution_tv(actor_empirical, actor_reference)
    _require(
        trace["full_rerun_reference_action_distribution"] == reference_actions,
        "full-rerun action reference substitution",
    )
    _require(
        trace["runtime_action_distribution"] == action_empirical,
        "runtime action distribution substitution",
    )
    action_tv = _distribution_tv(action_empirical, reference_actions)
    utilities = {str(k): float(v) for k, v in trace["utility_by_action"].items()}
    reference_utility = sum(
        reference_actions.get(action, 0.0) * utilities[action] for action in utilities
    )
    runtime_utility = sum(
        action_empirical.get(action, 0.0) * utilities[action] for action in utilities
    )
    _require(
        _close(float(trace["full_rerun_expected_utility"]), reference_utility),
        "reference utility substitution",
    )
    _require(
        _close(float(trace["runtime_expected_utility"]), runtime_utility),
        "runtime utility substitution",
    )
    initial_action = str(states[indices[str(trace["initial_state_id"])]]["action"])
    initial_tv = _distribution_tv({initial_action: 1.0}, reference_actions)
    late_recovery = max(0.0, (initial_tv - action_tv) / initial_tv) if initial_tv else 1.0

    outside_before = bytes.fromhex(str(trace["outside_window_bytes_hex_before"]))
    outside_after = bytes.fromhex(str(trace["outside_window_bytes_hex_after"]))
    outside_equal = outside_before == outside_after
    _require(
        hashlib.sha256(outside_before).hexdigest() == trace["outside_window_sha256_before"],
        "outside-window before hash mismatch",
    )
    _require(
        hashlib.sha256(outside_after).hexdigest() == trace["outside_window_sha256_after"],
        "outside-window after hash mismatch",
    )
    expected_window = list(range(len(task11_row["input"]["observations"]))) if events else []
    _require(
        trace["window_touched_indices"] == expected_window, "window touched-index substitution"
    )
    analytic_block = {
        "final_state": states[current]["typed_state"],
        "action_distribution": action_empirical,
        "window_touched_indices": tuple(range(len(task11_row["input"]["observations"]))),
    }
    analytic_ok = trace["analytic_block_sha256"] == canonical_sha256(analytic_block)
    if events:
        analytic_ok = analytic_ok and trace["analytic_block_rebuilt"] is True
    else:
        analytic_ok = analytic_ok and trace["analytic_block_rebuilt"] is False
    expected_oracle_count = (
        PROPOSAL_STEPS if kernel == "exact_conditional_gibbs_evaluator_only" else 0
    )
    oracle_confined = int(trace["oracle_access_count"]) == expected_oracle_count and (
        (kernel == "exact_conditional_gibbs_evaluator_only")
        == (trace["kernel_role"] == "evaluator_oracle")
    )
    ancestry = sorted({str(p["root_ancestor_id"]) for p in _final_particle_rows(task11_row)})
    _require(trace["root_ancestry"] == ancestry, "root ancestry substitution")
    _require(int(trace["unique_ancestry"]) == len(ancestry), "unique ancestry substitution")
    unresolved = float(task11_row["runtime"]["approximate_posterior"].get("__unresolved__", 0.0))
    _require(_close(float(trace["unresolved_mass"]), unresolved), "unresolved mass substitution")
    _require(
        int(trace["fallback_count"]) == len(trace["fallback_reasons"]),
        "fallback accounting mismatch",
    )
    runtime_owner_responsibility = sum(
        float(bool(states[index]["owner_responsible"])) for index in post_burn
    ) / len(post_burn)
    exact_owner_responsibility = float(task11_row["evaluator"]["exact_owner_responsibility"])
    owner_contamination = abs(runtime_owner_responsibility - exact_owner_responsibility)
    acceptance_rate = accepted_count / len(events) if events else 0.0
    metrics = {
        "detailed_balance_error": detailed_balance_error,
        "stationary_distribution_error": stationary_error,
        "proposal_count": len(events),
        "acceptance_count": accepted_count,
        "acceptance_rate": acceptance_rate,
        "elementary_evaluation_count": expected_cost,
        "axis_jump_distance_H_R_I_C_Z": axis_jumps,
        "autocorrelation": autocorrelation,
        "lag_one_effective_sample_size": lag_one_ess,
        "effective_sample_size_per_elementary_evaluation": lag_one_ess / expected_cost
        if expected_cost
        else 0.0,
        "unique_ancestry": len(ancestry),
        "full_rerun_actor_marginal_distance": actor_distance,
        "action_distribution_total_variation": action_tv,
        "expected_utility_difference": runtime_utility - reference_utility,
        "late_correction_recovery": late_recovery,
        "owner_contamination": owner_contamination,
        "unresolved_mass": unresolved,
        "fallback_count": int(trace["fallback_count"]),
        "fallback_reasons": list(trace["fallback_reasons"]),
        "outside_window_byte_equality": outside_equal,
        "zero_acceptance_path_count": zero_acceptance_paths,
        "full_acceptance_path_count": full_acceptance_paths,
        "non_self_move_count": non_self_moves,
        "complete_transition_matrix": transition,
    }
    gates = {
        "conditional_target_invariance": detailed_balance_error <= DETAILED_BALANCE_THRESHOLD,
        "forward_reverse_proposal_densities": True,
        "state_machine_reachability": state_machine_reachable,
        "outside_window_byte_equality": outside_equal,
        "analytic_block_rebuilt": analytic_ok,
        "oracle_confined_to_evaluator": oracle_confined,
        "acceptance_path_recomputation_complete": (
            zero_acceptance_paths + full_acceptance_paths <= len(events)
        ),
    }
    _require(all(gates.values()), "raw trace integrity gate failure")
    metrics["gates"] = gates
    return metrics


def _expected_key(row: Mapping[str, Any], kernel: str) -> tuple[Any, ...]:
    return (
        row["context"],
        row["scenario_id"],
        row["replicate_seed"],
        row["split"],
        row["particle_budget"],
        row["policy"]["key"],
        kernel,
    )


def _trace_key(trace: Mapping[str, Any]) -> tuple[Any, ...]:
    coordinate = trace["coordinate"]
    return (
        coordinate["context"],
        coordinate["scenario_id"],
        coordinate["replicate_seed"],
        coordinate["split"],
        coordinate["particle_budget"],
        coordinate["resampling_policy"]["key"],
        coordinate["kernel"],
    )


def recompute_results(
    traces: Sequence[Mapping[str, Any]],
    *,
    task11_rows: Sequence[Mapping[str, Any]],
    task11_result: Mapping[str, Any],
    task11_manifest: Mapping[str, Any],
    task11_raw_hashes_by_context: Mapping[str, str],
) -> dict[str, Any]:
    _require(task11_result.get("condition_count") == 130, "Task 11 condition count substitution")
    _require(task11_result.get("trace_count") == 11856, "Task 11 trace count substitution")
    _require(task11_result.get("task_12_unlocked") is False, "Task 11 illegally unlocked Task 12")
    expected = {_expected_key(row, kernel) for row in task11_rows for kernel in KERNELS}
    supplied = [_trace_key(trace) for trace in traces]
    _require(len(supplied) == len(set(supplied)), "duplicate Task 12 execution coordinate")
    _require(
        set(supplied) == expected, "missing, extra, or substituted Task 12 execution coordinate"
    )
    _require(len(traces) == 1872 * 4, "Task 12 raw trace matrix is incomplete")
    verify_task11_dependencies(
        task11_rows=task11_rows,
        task11_result=task11_result,
        task11_manifest=task11_manifest,
        task11_raw_hashes_by_context=task11_raw_hashes_by_context,
    )
    row_by_key = {_expected_key(row, kernel): row for row in task11_rows for kernel in KERNELS}
    manifest_content_sha256 = str(task11_manifest["content_sha256"])
    recomputed: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    nonces: set[str] = set()
    runtime_ids: set[str] = set()
    for trace in sorted(traces, key=_trace_key):
        key = _trace_key(trace)
        metrics = verify_trace(
            trace,
            task11_row=row_by_key[key],
            expected_manifest_content_sha256=manifest_content_sha256,
            expected_task11_raw_file_sha256=task11_raw_hashes_by_context[str(key[0])],
        )
        _require(str(trace["execution_nonce"]) not in nonces, "execution nonce replay")
        _require(
            str(trace["runtime_invocation_id"]) not in runtime_ids, "runtime invocation id replay"
        )
        nonces.add(str(trace["execution_nonce"]))
        runtime_ids.add(str(trace["runtime_invocation_id"]))
        recomputed.append((trace, metrics))

    global_zero_paths = sum(item[1]["zero_acceptance_path_count"] for item in recomputed)
    global_full_paths = sum(item[1]["full_acceptance_path_count"] for item in recomputed)
    global_non_self_moves = sum(item[1]["non_self_move_count"] for item in recomputed)
    _require(global_zero_paths > 0, "complete matrix did not exercise a zero-accept path")
    _require(global_full_paths > 0, "complete matrix did not exercise a full-accept path")
    _require(global_non_self_moves > 0, "complete matrix has no accepted non-self move")

    # Content-only relabelling cannot make the two MH kernels equivalent.
    by_upstream_execution: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for trace, _ in recomputed:
        coordinate = trace["coordinate"]
        base = (
            coordinate["context"],
            coordinate["scenario_id"],
            coordinate["replicate_seed"],
            coordinate["split"],
            coordinate["resampling_policy"]["key"],
        )
        by_upstream_execution[base][coordinate["kernel"]] = trace
    for arms in by_upstream_execution.values():
        _require(
            arms["single_site_typed_metropolis_hastings"]["proposal_matrix_q_y_given_x"]
            != arms["blocked_typed_metropolis_hastings"]["proposal_matrix_q_y_given_x"],
            "single-site and blocked MH are label-only duplicates",
        )

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trace, metrics in recomputed:
        buckets[(str(trace["upstream_condition_id"]), str(trace["coordinate"]["kernel"]))].append(
            metrics
        )
    upstream_condition_ids = {condition_id for condition_id, _kernel in buckets}
    _require(len(upstream_condition_ids) == 26, "Task 11 K=24 condition count substitution")
    full_fidelity = _task11_fidelity_by_condition(task11_result)
    _require(
        upstream_condition_ids <= set(full_fidelity),
        "Task 11 K=24 condition is absent from the full-budget summary",
    )
    fidelity = {
        condition_id: full_fidelity[condition_id] for condition_id in sorted(upstream_condition_ids)
    }
    condition_arms: list[dict[str, Any]] = []
    for condition_id in sorted(fidelity):
        for kernel in KERNELS:
            items = buckets[(condition_id, kernel)]
            _require(bool(items), f"empty condition/kernel bucket: {condition_id}/{kernel}")
            proposals = sum(item["proposal_count"] for item in items)
            acceptances = sum(item["acceptance_count"] for item in items)
            evaluations = sum(item["elementary_evaluation_count"] for item in items)
            lag_ess = sum(item["lag_one_effective_sample_size"] for item in items)
            axis = {
                name: sum(item["axis_jump_distance_H_R_I_C_Z"][name] for item in items)
                for name in AXES
            }
            all_gates = all(all(item["gates"].values()) for item in items)
            blocked = not fidelity[condition_id]["fidelity_passed"]
            condition_arms.append(
                {
                    "upstream_condition_id": condition_id,
                    "kernel": kernel,
                    "execution_count": len(items),
                    "upstream_fidelity": fidelity[condition_id],
                    "detailed_balance_error": max(item["detailed_balance_error"] for item in items),
                    "stationary_distribution_error": max(
                        item["stationary_distribution_error"] for item in items
                    ),
                    "proposal_count": proposals,
                    "acceptance_count": acceptances,
                    "acceptance_rate": acceptances / proposals if proposals else 0.0,
                    "axis_jump_distance_H_R_I_C_Z": axis,
                    "all_axes_jumped": all(value > 0.0 for value in axis.values()),
                    "autocorrelation": sum(item["autocorrelation"] for item in items) / len(items),
                    "effective_sample_size_per_elementary_evaluation": lag_ess / evaluations
                    if evaluations
                    else 0.0,
                    "unique_ancestry": sum(item["unique_ancestry"] for item in items) / len(items),
                    "full_rerun_actor_marginal_distance": sum(
                        item["full_rerun_actor_marginal_distance"] for item in items
                    )
                    / len(items),
                    "action_distribution_total_variation": sum(
                        item["action_distribution_total_variation"] for item in items
                    )
                    / len(items),
                    "expected_utility_difference": sum(
                        item["expected_utility_difference"] for item in items
                    )
                    / len(items),
                    "late_correction_recovery": sum(
                        item["late_correction_recovery"] for item in items
                    )
                    / len(items),
                    "owner_contamination": sum(item["owner_contamination"] for item in items)
                    / len(items),
                    "unresolved_mass": sum(item["unresolved_mass"] for item in items) / len(items),
                    "fallback_count": sum(item["fallback_count"] for item in items),
                    "fallback_reasons": sorted(
                        {reason for item in items for reason in item["fallback_reasons"]}
                    ),
                    "outside_window_byte_equality": all(
                        item["outside_window_byte_equality"] for item in items
                    ),
                    "zero_acceptance_path_count": sum(
                        item["zero_acceptance_path_count"] for item in items
                    ),
                    "full_acceptance_path_count": sum(
                        item["full_acceptance_path_count"] for item in items
                    ),
                    "non_self_move_count": sum(item["non_self_move_count"] for item in items),
                    "all_integrity_gates_passed": all_gates,
                    "evaluator_oracle_selectable": False,
                    "disposition": (
                        "CONDITIONAL_FALSIFICATION_UPSTREAM_FIDELITY_FAILED_AND_FORMAL_PARENTS_MISSING"
                        if blocked
                        else "DIAGNOSTIC_ONLY_BLOCKED_BY_MISSING_FORMAL_TASK10_TASK11_RECEIPTS"
                    ),
                }
            )

    threshold_interpretations: dict[str, Any] = {}
    for label, threshold in (
        ("json_python_1e-6", JSON_THRESHOLD),
        ("chinese_protocol_1e-9", DOCUMENT_THRESHOLD),
    ):
        rows = []
        for arm in condition_arms:
            passes = (
                arm["detailed_balance_error"] <= DETAILED_BALANCE_THRESHOLD
                and arm["stationary_distribution_error"] <= threshold
                and arm["full_rerun_actor_marginal_distance"] <= ACTOR_DISTANCE_THRESHOLD
                and arm["owner_contamination"] <= OWNER_CONTAMINATION_THRESHOLD
                and arm["all_axes_jumped"]
                and (arm["kernel"] == "no_rejuvenation" or arm["non_self_move_count"] > 0)
                and arm["all_integrity_gates_passed"]
            )
            rows.append(
                {
                    "upstream_condition_id": arm["upstream_condition_id"],
                    "kernel": arm["kernel"],
                    "stationarity_threshold": threshold,
                    "diagnostic_guardrails_passed": passes,
                    "formal_selection": None,
                }
            )
        threshold_interpretations[label] = {
            "threshold": threshold,
            "arm_results": rows,
            "formal_task_12_selection": None,
            "protocol_drift_status": "PROTOCOL_DRIFT_UNRESOLVED",
        }

    result: dict[str, Any] = {
        "schema": "structure-two-task12-recomputed-result@0.1",
        "protocol_id": PROTOCOL_ID,
        "baseline_status": BASELINE_STATUS,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "protocol_drift_status": "PROTOCOL_DRIFT_UNRESOLVED",
        "formal_task_12_passed": False,
        "formal_binding_resolved": False,
        "selected_kernel": None,
        "task_13_unlocked": False,
        "proposal_p5_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "upstream_condition_count": 26,
        "condition_kernel_count": len(condition_arms),
        "raw_trace_count": len(traces),
        "expected_raw_trace_count": 7488,
        "kernel_order": list(KERNELS),
        "condition_arms": condition_arms,
        "threshold_interpretations": threshold_interpretations,
        "global_path_coverage": {
            "zero_acceptance_path_count": global_zero_paths,
            "full_acceptance_path_count": global_full_paths,
            "non_self_move_count": global_non_self_moves,
        },
        "claim_boundary": (
            "This is a conditional local falsification/diagnostic over every frozen Task 11 "
            "condition. It cannot resolve Task 12 while Task 10/11 formal receipts, enrolled "
            "trust anchor, independent custody, freshness, replay registry, and the 1e-6/1e-9 "
            "protocol decision remain absent."
        ),
    }
    result["deterministic_result_sha256"] = canonical_sha256(result)
    return result
