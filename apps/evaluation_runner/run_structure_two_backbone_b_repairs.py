#!/usr/bin/env python3
"""Run and independently verify the Structure-Two Task-7/8 repair evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (  # noqa: E402
    TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE,
    TASK7_BELIEF_AXES,
    TASK7_BELIEF_AXIS_TV_TOLERANCE,
    TASK7_CONDITIONAL_PROTOCOL_ID,
    TASK7_SCENARIO_FACTOR_NAMES,
    TASK8_HANDOFF_ACTOR_SEVERITY,
    TASK8_REGIME_HABIT_SEVERITY,
    TASK8_UNRESOLVED_SEVERITY,
    TASK8_VERIFY_COST,
    ArmName,
    JointConsequenceAction,
    run_late_correction_study,
    task8_endpoint_consumes_interaction,
    validate_task7_conditional_target_contract,
)
from cpswm.system.evaluation_operations.structure_two_task8_matched_confirmatory import (  # noqa: E402
    TASK8_ARM_NAMES,
    TASK8_MATCHED_COUPLING_NATS,
    TASK8_MATCHED_ENDPOINT_ID,
    TASK8_MATCHED_PROTOCOL_ID,
    TASK8_PAIRED_BOOTSTRAP_REPLICATES,
    TASK8_PAIRED_BOOTSTRAP_SEED,
    TASK8_PAIRED_CI_CONFIDENCE,
    TASK8_PAIRED_COST_CI_THRESHOLD,
    TASK8_TUNING_CANDIDATES,
    _paired_bootstrap_lower_bound,
    _verify_selection_receipt,
    run_task8_matched_confirmatory_study,
)

ARTIFACT_PROTOCOL_ID: Final = "structure-two-backbone-b-repair-evidence@0.2"
OUTPUT_DIRECTORY: Final = REPOSITORY_ROOT / "benchmarks/structure_two/backbone_b_repairs_2026_09_04"
TASK_CONFIGS: Final = {
    "7": Path(
        "configs/project_two_experiments/structure_two_task7_windowed_rejuvenation_v0_4.json"
    ),
    "8": Path(
        "configs/project_two_experiments/structure_two_task8_relative_probability_coupling_v0_4.json"
    ),
}
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_task8_matched_confirmatory.py"),
    Path("apps/evaluation_runner/run_structure_two_backbone_b_repairs.py"),
)
OUTPUT_NAMES: Final = {
    "7": "task_7_windowed_rejuvenation_v0_4.json",
    "8": "task_8_matched_three_arm_confirmatory_v0_4.json",
}
FROZEN_CONFIG_SHA256: Final = {
    "7": "b3d2e5b6cb0e531b2b918ac51958834a2dd0805727132794356e785449b94159",
    "8": "fa5888a5acd341675a1284a72b2c7653779459caf87e08b9a89c05ea0b8e3f9a",
}
TIMING_FIELDS: Final = frozenset(
    {
        "elapsed_seconds",
        "initial_wall_clock_seconds",
        "marginal_wall_clock_seconds",
        "mean_wall_clock_seconds",
        "seconds",
        "wall_clock_seconds",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_projection(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): deterministic_projection(item)
            for key, item in value.items()
            if key not in TIMING_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [deterministic_projection(item) for item in value]
    return value


def _positive_boolean_paths(value: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{escaped}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{index}"))
    elif value is True:
        paths.append(prefix or "/")
    return paths


def _source_bundle(task: str) -> dict[str, object]:
    paths = (*SOURCE_PATHS, TASK_CONFIGS[task])
    files = [
        {"path": path.as_posix(), "sha256": _file_sha256(REPOSITORY_ROOT / path)} for path in paths
    ]
    return {
        "protocol_id": "structure-two-backbone-b-source-bundle@0.1",
        "files": files,
        "content_sha256": _canonical_sha256(files),
    }


def _registered_config(task: str) -> dict[str, Any]:
    path = REPOSITORY_ROOT / TASK_CONFIGS[task]
    if _file_sha256(path) != FROZEN_CONFIG_SHA256[task]:
        raise ValueError(f"Task-{task} frozen config drift")
    raw: object = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ValueError(f"Task-{task} frozen config must be a JSON object")
    config = {str(key): value for key, value in raw.items()}
    if config.get("status") != "FROZEN_BEFORE_EXECUTION":
        raise ValueError(f"Task-{task} frozen config status mismatch")
    return config


def run_registered_task(task: str) -> dict[str, Any]:
    """Execute only a frozen, task-specific design; arbitrary argv is forbidden."""

    if task not in TASK_CONFIGS:
        raise ValueError(f"unsupported repair task: {task}")
    config = _registered_config(task)
    if task == "7":
        design = cast(dict[str, Any], config["registered_design"])
        if config.get("protocol_id") != TASK7_CONDITIONAL_PROTOCOL_ID:
            raise ValueError("Task-7 frozen config protocol mismatch")
        task7_expected_thresholds = (
            float(design["belief_axis_tv_tolerance"]),
            float(design["action_distribution_tv_tolerance"]),
        )
        task7_code_thresholds = (
            TASK7_BELIEF_AXIS_TV_TOLERANCE,
            TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE,
        )
        if task7_expected_thresholds != task7_code_thresholds:
            raise ValueError("Task-7 frozen config and executable thresholds disagree")
        if tuple(config.get("belief_axes", ())) != TASK7_BELIEF_AXES:
            raise ValueError("Task-7 frozen belief-axis ontology mismatch")
        if int(design["window_length"]) <= 1:
            raise ValueError("Task-7 registered rerun must exercise W > 1")
        conditional = cast(dict[str, Any], config["conditional_target_contract"])
        if (
            conditional.get("validation_id") != "task-7-same-conditional-target@0.1"
            or float(conditional.get("absolute_tolerance", math.nan)) != 1e-10
            or conditional.get("reference_uses_same_corrected_observations") is not True
        ):
            raise ValueError("Task-7 conditional-target contract mismatch")
        factor_matrix = cast(list[dict[str, bool | int]], design["scenario_factor_matrix"])
        return run_late_correction_study(
            gaps=int(design["gaps"]),
            correction_index=int(design["correction_index"]),
            scenario_seeds=tuple(int(value) for value in design["scenario_seeds"]),
            arm=ArmName(str(design["arm"])),
            budget=int(design["particles"]),
            replicate_seeds=tuple(int(value) for value in design["replicate_seeds"]),
            rejuvenation_window_length=int(design["window_length"]),
            rejuvenation_sweeps=int(design["rejuvenation_sweeps"]),
            complexity_probe_suffix_lengths=tuple(
                int(value) for value in design["complexity_probe_suffix_lengths"]
            ),
            scenario_factor_matrix=tuple(factor_matrix),
            protocol_id=TASK7_CONDITIONAL_PROTOCOL_ID,
        )
    if task == "8":
        confirmatory = cast(dict[str, Any], config["confirmatory_execution"])
        if config.get("protocol_id") != TASK8_MATCHED_PROTOCOL_ID:
            raise ValueError("Task-8 frozen config protocol mismatch")
        interaction = cast(dict[str, Any], config["interaction"])
        tuning = cast(dict[str, Any], config["validation_only_tuning"])
        budget = cast(dict[str, Any], config["information_and_budget_contract"])
        paired = cast(dict[str, Any], confirmatory["paired_confidence_interval"])
        if (
            float(interaction["potential_nats"]) != TASK8_MATCHED_COUPLING_NATS
            or tuple(float(value) for value in tuning["candidate_temperatures_for_each_arm"])
            != TASK8_TUNING_CANDIDATES
            or float(paired["confidence"]) != TASK8_PAIRED_CI_CONFIDENCE
            or int(paired["bootstrap_replicates"]) != TASK8_PAIRED_BOOTSTRAP_REPLICATES
            or paired["bootstrap_seed"] != TASK8_PAIRED_BOOTSTRAP_SEED
            or float(paired["strict_lower_bound_threshold"]) != TASK8_PAIRED_COST_CI_THRESHOLD
            or paired["pass_operator"] != ">"
        ):
            raise ValueError("Task-8 frozen config and executable confirmatory contract disagree")
        if budget.get("same_full_posterior_table_visible_to_each_arm") is not True:
            raise ValueError("Task-8 arms do not share the same information contract")
        if int(budget["same_validation_candidate_count_per_arm"]) != len(TASK8_TUNING_CANDIDATES):
            raise ValueError("Task-8 validation tuning budgets differ by arm")
        endpoint = cast(dict[str, Any], config["consequential_endpoint"])
        if (
            endpoint.get("endpoint_id") != TASK8_MATCHED_ENDPOINT_ID
            or endpoint.get("actions")
            != [
                JointConsequenceAction.PROCEED.value,
                JointConsequenceAction.VERIFY.value,
            ]
            or float(endpoint.get("verify_cost", math.nan)) != TASK8_VERIFY_COST
            or float(endpoint.get("unresolved_severity", math.nan)) != TASK8_UNRESOLVED_SEVERITY
            or float(endpoint.get("handoff_actor_severity", math.nan))
            != TASK8_HANDOFF_ACTOR_SEVERITY
            or float(endpoint.get("regime_habit_severity", math.nan)) != TASK8_REGIME_HABIT_SEVERITY
            or endpoint.get("post_hoc_threshold_changes_allowed") is not False
        ):
            raise ValueError("Task-8 frozen consequential endpoint disagrees with code")
        return run_task8_matched_confirmatory_study(
            gaps=int(confirmatory["gaps"]),
            validation_seeds=tuple(int(value) for value in tuning["validation_seeds"]),
            confirmatory_seeds=tuple(int(value) for value in confirmatory["confirmatory_seeds"]),
            state_budget=int(budget["same_state_budget_per_arm_per_unit"]),
        )
    raise ValueError(f"unsupported repair task: {task}")


def _derive_task7_complexity_probe(probe: Mapping[str, object]) -> bool:
    rows = probe.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        return False
    work: set[int] = set()
    live_items: set[int] = set()
    reachable_bytes: set[int] = set()
    for untyped_row in rows:
        if not isinstance(untyped_row, Mapping):
            return False
        row = untyped_row
        try:
            work.add(int(cast(Any, row["marginal_window_gap_target_evaluations"])))
            live_items.add(int(cast(Any, row["marginal_max_repair_live_window_items"])))
            reachable_bytes.add(int(cast(Any, row["reachable_persistent_overlay_bytes"])))
            suffix_operations = (
                int(cast(Any, row["marginal_untouched_suffix_items_read"])),
                int(cast(Any, row["marginal_untouched_suffix_items_copied"])),
                int(cast(Any, row["marginal_untouched_suffix_items_rehashed"])),
            )
        except (KeyError, TypeError, ValueError):
            return False
        if suffix_operations != (0, 0, 0) or row.get("fallback_required") is not False:
            return False
    derived = len(work) == len(live_items) == len(reachable_bytes) == 1
    return (
        derived
        and probe.get("window_target_work_invariant_to_suffix_length") is True
        and probe.get("persistent_live_items_invariant_to_suffix_length") is True
        and probe.get("reachable_overlay_bytes_invariant_to_suffix_length") is True
        and probe.get("zero_untouched_suffix_operations") is True
        and probe.get("passed") is True
    )


def _validate_task_semantics(task: str, result: Mapping[str, object]) -> None:
    """Reject contradictory positive states, not merely malformed hashes."""

    if result.get("seven_operator_efficacy_authorized") is not False:
        raise ValueError("a Task-7/8 D0 artifact may not authorize seven-operator efficacy")
    if task == "7":
        if result.get("protocol_id") != TASK7_CONDITIONAL_PROTOCOL_ID:
            raise ValueError("Task-7 protocol substitution")
        rows = result.get("rows")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError("Task-7 registered comparison rows missing")
        local_rows = [
            row
            for row in rows
            if isinstance(row, Mapping) and row.get("treatment") == "local_rejuvenation"
        ]
        if not local_rows:
            raise ValueError("Task-7 local comparison rows missing")
        derived_belief_equivalence = True
        derived_action_equivalence = True
        derived_nonself = True
        derived_zero_suffix = True
        derived_conditional_target_runtime = True
        for row in local_rows:
            distances = row.get("belief_axis_distances_to_full_rerun")
            cost = row.get("cost")
            if not isinstance(distances, Mapping) or set(distances) != set(TASK7_BELIEF_AXES):
                raise ValueError("Task-7 frozen multi-axis belief comparison missing")
            try:
                belief_values = [float(cast(Any, distances[axis])) for axis in TASK7_BELIEF_AXES]
                action_distance = float(
                    cast(Any, row["action_distribution_distance_to_full_rerun"])
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Task-7 equivalence metrics malformed") from error
            if not all(math.isfinite(value) for value in (*belief_values, action_distance)):
                raise ValueError("Task-7 equivalence metrics must be finite")
            derived_belief_equivalence &= all(
                value <= TASK7_BELIEF_AXIS_TV_TOLERANCE for value in belief_values
            )
            derived_action_equivalence &= (
                action_distance <= TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
                and row.get("selected_action_matches_full_rerun") is True
            )
            if not isinstance(cost, Mapping):
                raise ValueError("Task-7 local cost receipt missing")
            try:
                proposals = int(cast(Any, cost["marginal_rejuvenation_proposals"]))
                nonself = int(cast(Any, cost["marginal_nonself_rejuvenation_proposals"]))
                suffix_operations = (
                    int(cast(Any, cost["marginal_untouched_suffix_items_read"])),
                    int(cast(Any, cost["marginal_untouched_suffix_items_copied"])),
                    int(cast(Any, cost["marginal_untouched_suffix_items_rehashed"])),
                )
                conditional_checks = int(cast(Any, cost["marginal_conditional_target_checks"]))
                conditional_mismatches = int(
                    cast(Any, cost["marginal_conditional_target_mismatches"])
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Task-7 complexity counters malformed") from error
            derived_nonself &= proposals > 0 and proposals == nonself
            derived_zero_suffix &= suffix_operations == (0, 0, 0)
            derived_conditional_target_runtime &= (
                conditional_checks > 0 and conditional_mismatches == 0
            )
        if result.get("belief_equivalence_passed") is not derived_belief_equivalence:
            raise ValueError("Task-7 belief-equivalence state contradicts raw axes")
        if result.get("action_equivalence_passed") is not derived_action_equivalence:
            raise ValueError("Task-7 action-equivalence state contradicts raw actions")
        if result.get("nonself_move_passed") is not derived_nonself:
            raise ValueError("Task-7 non-self state contradicts proposal counters")
        if (
            result.get("conditional_target_runtime_passed")
            is not derived_conditional_target_runtime
        ):
            raise ValueError("Task-7 conditional-target state contradicts runtime counters")
        expected_equivalence = derived_belief_equivalence and derived_action_equivalence
        if result.get("equivalence_passed") is not expected_equivalence:
            raise ValueError("Task-7 equivalence state contradicts belief/action gates")
        conditional_validation = result.get("conditional_target_validation")
        expected_validation = validate_task7_conditional_target_contract()
        if conditional_validation != expected_validation:
            raise ValueError("Task-7 conditional-target reference validation mismatch")
        if result.get("complete_2x2x2x2_scenario_factor_matrix") is not True:
            raise ValueError("Task-7 complete factor-matrix coverage is absent")
        expected_factor_combinations = {
            (ambiguity, delayed, open_world, short_regime)
            for ambiguity in (False, True)
            for delayed in (False, True)
            for open_world in (False, True)
            for short_regime in (False, True)
        }
        actual_factor_combinations = {
            tuple(
                bool(cast(Any, cast(Mapping[str, object], row["scenario_factors"])[name]))
                for name in TASK7_SCENARIO_FACTOR_NAMES
            )
            for row in local_rows
        }
        if actual_factor_combinations != expected_factor_combinations:
            raise ValueError("Task-7 raw rows do not cover the full factor matrix")
        coverage: dict[tuple[str, int], set[str]] = {}
        for raw_row in rows:
            if not isinstance(raw_row, Mapping):
                raise ValueError("Task-7 comparison row is malformed")
            try:
                coverage.setdefault(
                    (str(raw_row["scenario_id"]), int(cast(Any, raw_row["replicate_seed"]))),
                    set(),
                ).add(str(raw_row["treatment"]))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Task-7 comparison coverage key is malformed") from error
        expected_treatments = {
            "full_rerun",
            "local_rejuvenation",
            "reweight_only",
            "append_only",
        }
        if len(coverage) != 16 or any(
            treatments != expected_treatments for treatments in coverage.values()
        ):
            raise ValueError("Task-7 exact treatment x episode coverage is incomplete")
        expected_instrument = (
            expected_equivalence
            and bool(result.get("local_cost_passed"))
            and bool(result.get("no_fallbacks_in_registered_run"))
            and derived_nonself
            and bool(result.get("strict_window_complexity_passed"))
            and derived_conditional_target_runtime
            and bool(expected_validation["passed"])
        )
        if result.get("window_implementation_passed") is not expected_instrument:
            raise ValueError("Task-7 window implementation state contradicts its prerequisites")
        if result.get("task_7_instrument_passed") is not expected_instrument:
            raise ValueError("Task-7 gate state contradicts its three prerequisites")
        full_rows = [
            row for row in rows if isinstance(row, Mapping) and row.get("treatment") == "full_rerun"
        ]
        local_contamination = sum(
            float(cast(Any, row["owner_contamination"])) for row in local_rows
        ) / len(local_rows)
        full_contamination = sum(
            float(cast(Any, row["owner_contamination"])) for row in full_rows
        ) / len(full_rows)
        expected_contamination = local_contamination <= full_contamination
        if result.get("contamination_not_expanded") is not expected_contamination:
            raise ValueError("Task-7 contamination gate contradicts raw comparison rows")
        expected_task = expected_instrument and expected_contamination
        if result.get("task_7_passed") is not expected_task:
            raise ValueError("Task-7 instrument-only result was promoted to an overall pass")
        if result.get("task_7_verdict") != ("PASS" if expected_task else "FAIL"):
            raise ValueError("Task-7 FAIL verdict was hidden or rewritten")
        if result.get("explicit_full_replay_fallback_implemented") is not True:
            raise ValueError("Task-7 full-replay fallback implementation receipt is absent")
        contract = result.get("window_contract")
        if not isinstance(contract, Mapping):
            raise ValueError("Task-7 window contract missing")
        if contract.get("full_suffix_replayed_by_local_kernel") is not False:
            raise ValueError("Task-7 local kernel replayed the fixed suffix")
        if contract.get("untouched_suffix_copy_scan_or_rehash") is not False:
            raise ValueError("Task-7 local kernel touched the fixed suffix")
        if contract.get("terminal_responsible_actor_cached") is not True:
            raise ValueError("Task-7 terminal responsible-actor cache contract is absent")
        if contract.get("fallback_policy") != "explicit_full_replay":
            raise ValueError("Task-7 explicit full-replay fallback contract is absent")
        if int(cast(Any, contract.get("proposal_window_length", 0))) <= 1:
            raise ValueError("Task-7 registered result did not exercise W > 1")
        complexity = result.get("complexity_probe")
        if not isinstance(complexity, Mapping) or not _derive_task7_complexity_probe(complexity):
            raise ValueError("Task-7 registered long-suffix complexity probe failed")
        derived_strict_complexity = derived_zero_suffix
        if result.get("strict_window_complexity_passed") is not derived_strict_complexity:
            raise ValueError("Task-7 complexity state contradicts raw receipts")
    elif task == "8":
        if result.get("protocol_id") != TASK8_MATCHED_PROTOCOL_ID:
            raise ValueError("Task-8 protocol substitution")
        if result.get("historical_v0_3_status") != ("FAILED_FOR_CURRENT_MATCHED_THREE_ARM_CLAIM"):
            raise ValueError("Task-8 v0.3 failed-history boundary was rewritten")
        design = result.get("design")
        endpoint = result.get("endpoint")
        if not isinstance(design, Mapping) or not isinstance(endpoint, Mapping):
            raise ValueError("Task-8 design or endpoint receipt is missing")
        if design.get("same_observations_information_and_total_budget") is not True:
            raise ValueError("Task-8 matched information/budget contract is absent")
        if endpoint.get("endpoint_id") != TASK8_MATCHED_ENDPOINT_ID:
            raise ValueError("Task-8 consequential endpoint substitution")
        if endpoint.get("consumes_interaction") is not task8_endpoint_consumes_interaction():
            raise ValueError("Task-8 endpoint does not consume the registered interaction")

        validation_rows = result.get("validation_rows")
        confirmatory_rows = result.get("confirmatory_rows")
        paired_rows = result.get("paired_rows")
        cluster_rows = result.get("paired_seed_cluster_rows")
        if any(
            not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            for value in (validation_rows, confirmatory_rows, paired_rows, cluster_rows)
        ):
            raise ValueError("Task-8 raw validation or confirmatory rows are missing")
        validation_rows = cast(Sequence[Mapping[str, Any]], validation_rows)
        confirmatory_rows = cast(Sequence[Mapping[str, Any]], confirmatory_rows)
        paired_rows = cast(Sequence[Mapping[str, Any]], paired_rows)
        cluster_rows = cast(Sequence[Mapping[str, Any]], cluster_rows)
        validation_ids = list(dict.fromkeys(str(row["unit_id"]) for row in validation_rows))
        expected_validation_rows = (
            len(validation_ids) * len(TASK8_ARM_NAMES) * len(TASK8_TUNING_CANDIDATES)
        )
        if len(validation_rows) != expected_validation_rows:
            raise ValueError("Task-8 validation arm x candidate x unit coverage is incomplete")
        validation_keys = {
            (str(row["unit_id"]), str(row["arm"]), float(row["temperature"]))
            for row in validation_rows
        }
        expected_validation_keys = {
            (unit_id, arm, temperature)
            for unit_id in validation_ids
            for arm in TASK8_ARM_NAMES
            for temperature in TASK8_TUNING_CANDIDATES
        }
        if validation_keys != expected_validation_keys:
            raise ValueError("Task-8 validation coverage contains substitution or duplication")

        selection_receipt = result.get("selection_receipt")
        if not isinstance(selection_receipt, Mapping):
            raise ValueError("Task-8 validation-only selection receipt is missing")
        _verify_selection_receipt(selection_receipt, validation_ids)
        selections = cast(Mapping[str, Mapping[str, Any]], selection_receipt["selections"])
        for arm in TASK8_ARM_NAMES:
            candidate_means = []
            for temperature in TASK8_TUNING_CANDIDATES:
                subset = [
                    row
                    for row in validation_rows
                    if row["arm"] == arm and float(row["temperature"]) == temperature
                ]
                candidate_means.append(
                    (
                        sum(float(row["consequential_expected_cost"]) for row in subset)
                        / len(subset),
                        abs(temperature - 1.0),
                        temperature,
                    )
                )
            expected_selected = min(candidate_means)
            if float(selections[arm]["temperature"]) != expected_selected[2] or not math.isclose(
                float(selections[arm]["validation_mean_cost"]),
                expected_selected[0],
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError("Task-8 arm selection was not derived from validation only")

        confirmatory_ids = list(dict.fromkeys(str(row["unit_id"]) for row in confirmatory_rows))
        if len(confirmatory_rows) != len(confirmatory_ids) * len(TASK8_ARM_NAMES):
            raise ValueError("Task-8 confirmatory arm x unit coverage is incomplete")
        by_unit: dict[str, dict[str, Mapping[str, Any]]] = {}
        for row in confirmatory_rows:
            arm = str(row["arm"])
            unit_id = str(row["unit_id"])
            if arm not in TASK8_ARM_NAMES or arm in by_unit.setdefault(unit_id, {}):
                raise ValueError("Task-8 confirmatory arm substitution or duplication")
            if float(row["temperature"]) != float(selections[arm]["temperature"]):
                raise ValueError("Task-8 confirmatory data retuned a frozen arm")
            by_unit[unit_id][arm] = row
        recomputed_paired: list[dict[str, Any]] = []
        for unit_id in confirmatory_ids:
            arms = by_unit[unit_id]
            if set(arms) != set(TASK8_ARM_NAMES):
                raise ValueError("Task-8 confirmatory unit lacks one of three arms")
            hashes = {str(row["shared_information_sha256"]) for row in arms.values()}
            budgets = {int(row["state_budget"]) for row in arms.values()}
            visible = {int(row["posterior_cells_visible"]) for row in arms.values()}
            if len(hashes) != 1 or len(budgets) != 1 or len(visible) != 1:
                raise ValueError("Task-8 arm information or budget mismatch")
            joint_cost = float(arms["joint"]["consequential_expected_cost"])
            factorized_cost = float(arms["factorized"]["consequential_expected_cost"])
            two_stage_cost = float(arms["matched_two_stage"]["consequential_expected_cost"])
            recomputed_paired.append(
                {
                    "unit_id": unit_id,
                    "cluster_seed": int(arms["joint"]["cluster_seed"]),
                    "shared_information_sha256": arms["joint"]["shared_information_sha256"],
                    "joint_cost": joint_cost,
                    "factorized_cost": factorized_cost,
                    "matched_two_stage_cost": two_stage_cost,
                    "factorized_cost_minus_joint_cost": factorized_cost - joint_cost,
                    "two_stage_cost_minus_joint_cost": two_stage_cost - joint_cost,
                }
            )
        if list(paired_rows) != recomputed_paired:
            raise ValueError("Task-8 paired costs contradict confirmatory arm rows")

        expected_cluster_rows: list[dict[str, Any]] = []
        for cluster_seed in sorted({int(row["cluster_seed"]) for row in recomputed_paired}):
            subset = [row for row in recomputed_paired if int(row["cluster_seed"]) == cluster_seed]
            if len(subset) != 8:
                raise ValueError("Task-8 seed cluster lacks eight factorial cells")
            expected_cluster_rows.append(
                {
                    "cluster_seed": cluster_seed,
                    "factor_cells": 8,
                    "mean_two_stage_cost_minus_joint_cost": sum(
                        float(row["two_stage_cost_minus_joint_cost"]) for row in subset
                    )
                    / 8.0,
                }
            )
        if list(cluster_rows) != expected_cluster_rows:
            raise ValueError("Task-8 seed-cluster paired aggregation mismatch")
        paired = result.get("paired_inference")
        if not isinstance(paired, Mapping):
            raise ValueError("Task-8 paired inference receipt is absent")
        differences = [
            float(row["mean_two_stage_cost_minus_joint_cost"]) for row in expected_cluster_rows
        ]
        expected_mean = sum(differences) / len(differences)
        expected_lower = _paired_bootstrap_lower_bound(differences)
        if not math.isclose(float(paired.get("paired_mean", math.nan)), expected_mean):
            raise ValueError("Task-8 paired mean contradicts seed-cluster rows")
        if not math.isclose(
            float(paired.get("paired_lower_confidence_bound", math.nan)), expected_lower
        ):
            raise ValueError("Task-8 paired confidence bound was not recomputed")
        threshold = float(paired.get("preregistered_strict_lower_bound_threshold", math.nan))
        if threshold != TASK8_PAIRED_COST_CI_THRESHOLD:
            raise ValueError("Task-8 preregistered paired threshold changed")
        expected_gate = expected_lower > threshold
        if paired.get("strict_lower_bound_gate_passed") is not expected_gate:
            raise ValueError("Task-8 strict lower-bound gate contradicts raw pairs")
        expected_task = (
            expected_gate
            and endpoint.get("consumes_interaction") is True
            and result.get("confirmatory_exact_arm_by_unit_coverage") is True
            and result.get("validation_only_independent_tuning_passed") is True
            and result.get("preregistered_design_matched") is True
        )
        if result.get("task_8_passed") is not expected_task:
            raise ValueError("Task-8 paired failure was promoted to an overall pass")
        if result.get("task_8_verdict") != ("PASS" if expected_task else "FAIL"):
            raise ValueError("Task-8 FAIL verdict was hidden or rewritten")
    else:  # pragma: no cover - caller validates the task first
        raise ValueError(f"unsupported repair task: {task}")


def make_artifact(task: str, result: dict[str, Any]) -> dict[str, object]:
    if task not in TASK_CONFIGS:
        raise ValueError(f"unsupported repair task: {task}")
    _registered_config(task)
    _validate_task_semantics(task, result)
    deterministic = deterministic_projection(result)
    payload: dict[str, object] = {
        "artifact_protocol_id": ARTIFACT_PROTOCOL_ID,
        "task": task,
        "run_date": "2026-09-05",
        "evidence_level": "D0_SYNTHETIC_DEVELOPMENT",
        "source_bundle": _source_bundle(task),
        "config": {
            "path": TASK_CONFIGS[task].as_posix(),
            "sha256": _file_sha256(REPOSITORY_ROOT / TASK_CONFIGS[task]),
        },
        "recomputation": {
            "runner": Path(__file__).relative_to(REPOSITORY_ROOT).as_posix(),
            "registered_task": task,
            "deterministic_result_sha256": _canonical_sha256(deterministic),
        },
        "positive_output_trust_chain": {
            path: (
                "artifact_content+task_specific_source_bundle+frozen_config+"
                "semantic_derivation_from_raw_metrics+fresh_task_specific_recomputation"
            )
            for path in _positive_boolean_paths(result)
        },
        "claim_boundary": (
            "Fresh recomputation authenticates current D0 synthetic evidence only. "
            "It does not establish external validity or authorize seven-operator efficacy."
        ),
        "result": result,
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def verify_artifact(
    payload: Mapping[str, object],
    *,
    recompute: bool = True,
    task_runner: Callable[[str], dict[str, Any]] = run_registered_task,
) -> None:
    unsigned = dict(payload)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _canonical_sha256(unsigned):
        raise ValueError("repair artifact content hash mismatch")
    if payload.get("artifact_protocol_id") != ARTIFACT_PROTOCOL_ID:
        raise ValueError("repair artifact protocol mismatch")
    task = payload.get("task")
    if not isinstance(task, str) or task not in TASK_CONFIGS:
        raise ValueError("repair artifact has an unsupported task binding")
    _registered_config(task)
    if payload.get("source_bundle") != _source_bundle(task):
        raise ValueError("repair artifact source bundle drift")
    expected_config = {
        "path": TASK_CONFIGS[task].as_posix(),
        "sha256": _file_sha256(REPOSITORY_ROOT / TASK_CONFIGS[task]),
    }
    if payload.get("config") != expected_config:
        raise ValueError("repair artifact config substitution or drift")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("repair artifact result missing")
    _validate_task_semantics(task, result)
    recomputation = payload.get("recomputation")
    if not isinstance(recomputation, Mapping):
        raise ValueError("repair artifact recomputation binding missing")
    stored_result_hash = recomputation.get("deterministic_result_sha256")
    if stored_result_hash != _canonical_sha256(deterministic_projection(result)):
        raise ValueError("repair artifact deterministic result hash mismatch")
    expected_positive_chain = {
        path: (
            "artifact_content+task_specific_source_bundle+frozen_config+"
            "semantic_derivation_from_raw_metrics+fresh_task_specific_recomputation"
        )
        for path in _positive_boolean_paths(result)
    }
    if payload.get("positive_output_trust_chain") != expected_positive_chain:
        raise ValueError("repair artifact positive-output trust chain is incomplete")
    if recompute:
        fresh = task_runner(task)
        _validate_task_semantics(task, fresh)
        if deterministic_projection(fresh) != deterministic_projection(result):
            raise ValueError("fresh task-specific recomputation does not match the artifact")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_artifact(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError("repair artifact root must be an object")
    return value


def _write_artifact(task: str, output_directory: Path, *, replace: bool) -> Path:
    result = run_registered_task(task)
    payload = make_artifact(task, result)
    # The second execution is intentionally independent of the producer result.
    verify_artifact(payload, recompute=True)
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / OUTPUT_NAMES[task]
    mode = "w" if replace else "x"
    with path.open(mode, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("7", "8", "all"), default="all")
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        verify_artifact(load_artifact(args.verify), recompute=True)
        print(args.verify)
        return 0
    tasks = ("7", "8") if args.task == "all" else (args.task,)
    for task in tasks:
        print(_write_artifact(task, args.output_directory, replace=args.replace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
