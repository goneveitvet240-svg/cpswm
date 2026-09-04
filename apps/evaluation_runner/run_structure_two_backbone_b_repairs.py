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
    MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE,
    MIN_MEASURABLE_FACTORIZATION_TV,
    MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE,
    RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
    TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE,
    TASK7_BELIEF_AXES,
    TASK7_BELIEF_AXIS_TV_TOLERANCE,
    TASK7_PROTOCOL_ID,
    TASK8_HANDOFF_ACTOR_SEVERITY,
    TASK8_PROTOCOL_ID,
    TASK8_REGIME_HABIT_SEVERITY,
    TASK8_UNRESOLVED_SEVERITY,
    TASK8_VERIFY_COST,
    ArmName,
    JointConsequenceAction,
    run_late_correction_study,
    run_relative_probability_soft_coupling_study,
    task8_endpoint_consumes_interaction,
)

ARTIFACT_PROTOCOL_ID: Final = "structure-two-backbone-b-repair-evidence@0.2"
OUTPUT_DIRECTORY: Final = REPOSITORY_ROOT / "benchmarks/structure_two/backbone_b_repairs_2026_09_04"
TASK_CONFIGS: Final = {
    "7": Path(
        "configs/project_two_experiments/structure_two_task7_windowed_rejuvenation_v0_3.json"
    ),
    "8": Path(
        "configs/project_two_experiments/structure_two_task8_relative_probability_coupling_v0_3.json"
    ),
}
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("apps/evaluation_runner/run_structure_two_backbone_b_repairs.py"),
)
OUTPUT_NAMES: Final = {
    "7": "task_7_windowed_rejuvenation_v0_3.json",
    "8": "task_8_relative_probability_soft_coupling_v0_3.json",
}
FROZEN_CONFIG_SHA256: Final = {
    "7": "a2fb032a4fc5f67d64f43a3ab946756092b9af3623b89e35ae31f93f9dd2e2dc",
    "8": "e89f4d8f25080843c20b526b5541d060071d4cd1e2dc227329a799dcfb962772",
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
    if config.get("status") != "FROZEN_FOR_RERUN":
        raise ValueError(f"Task-{task} frozen config status mismatch")
    return config


def run_registered_task(task: str) -> dict[str, Any]:
    """Execute only a frozen, task-specific design; arbitrary argv is forbidden."""

    if task not in TASK_CONFIGS:
        raise ValueError(f"unsupported repair task: {task}")
    config = _registered_config(task)
    if task == "7":
        design = cast(dict[str, Any], config["registered_design"])
        if config.get("protocol_id") != TASK7_PROTOCOL_ID:
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
        )
    if task == "8":
        design = cast(dict[str, Any], config["registered_rerun"])
        if config.get("protocol_id") != TASK8_PROTOCOL_ID:
            raise ValueError("Task-8 frozen config protocol mismatch")
        interaction = cast(dict[str, Any], config["interaction"])
        task8_expected_thresholds = (
            float(design["factorization_tv_threshold"]),
            float(design["consequential_action_distribution_tv_threshold"]),
            float(design["mean_consequential_cost_advantage_threshold"]),
            float(interaction["potential_nats"]),
        )
        task8_code_thresholds = (
            MIN_MEASURABLE_FACTORIZATION_TV,
            MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE,
            MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE,
            RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
        )
        if task8_expected_thresholds != task8_code_thresholds:
            raise ValueError("Task-8 frozen config and executable thresholds disagree")
        endpoint = cast(dict[str, Any], config["consequential_endpoint"])
        utility = cast(dict[str, Any], endpoint["utility"])
        severities = cast(dict[str, Any], endpoint["cross_cell_severity"])
        if (
            float(utility["verify_cost"]) != TASK8_VERIFY_COST
            or float(severities["unresolved"]) != TASK8_UNRESOLVED_SEVERITY
            or float(severities["cause_actor_and_mechanism_handoff_and_z_stay_or_unresolved"])
            != TASK8_HANDOFF_ACTOR_SEVERITY
            or float(severities["cause_habit_and_z_create_or_reactivate"])
            != TASK8_REGIME_HABIT_SEVERITY
        ):
            raise ValueError("Task-8 frozen consequential endpoint disagrees with code")
        if endpoint.get("endpoint_id") != "joint-cross-safety-policy@0.1" or endpoint.get(
            "actions"
        ) != [
            JointConsequenceAction.PROCEED.value,
            JointConsequenceAction.VERIFY.value,
        ]:
            raise ValueError("Task-8 frozen consequential action ontology mismatch")
        information = cast(dict[str, Any], config["information_contract"])
        if (
            information.get("truth_visible_to_action_policy") is not False
            or information.get("future_observations_visible") is not False
        ):
            raise ValueError("Task-8 action policy has forbidden information")
        return run_relative_probability_soft_coupling_study(
            gaps=int(design["gaps"]),
            scenario_seeds=tuple(int(value) for value in design["scenario_seeds"]),
            strengths_nats=tuple(float(value) for value in config["sensitivity_strengths_nats"]),
            state_budget=int(design["state_budget"]),
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
        if result.get("protocol_id") != TASK7_PROTOCOL_ID:
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
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Task-7 complexity counters malformed") from error
            derived_nonself &= proposals > 0 and proposals == nonself
            derived_zero_suffix &= suffix_operations == (0, 0, 0)
        if result.get("belief_equivalence_passed") is not derived_belief_equivalence:
            raise ValueError("Task-7 belief-equivalence state contradicts raw axes")
        if result.get("action_equivalence_passed") is not derived_action_equivalence:
            raise ValueError("Task-7 action-equivalence state contradicts raw actions")
        if result.get("nonself_move_passed") is not derived_nonself:
            raise ValueError("Task-7 non-self state contradicts proposal counters")
        expected_equivalence = derived_belief_equivalence and derived_action_equivalence
        if result.get("equivalence_passed") is not expected_equivalence:
            raise ValueError("Task-7 equivalence state contradicts belief/action gates")
        expected_instrument = (
            expected_equivalence
            and bool(result.get("local_cost_passed"))
            and bool(result.get("no_fallbacks_in_registered_run"))
            and derived_nonself
            and bool(result.get("strict_window_complexity_passed"))
        )
        if result.get("window_implementation_passed") is not expected_instrument:
            raise ValueError("Task-7 window implementation state contradicts its prerequisites")
        if result.get("task_7_instrument_passed") is not expected_instrument:
            raise ValueError("Task-7 gate state contradicts its three prerequisites")
        expected_task = expected_instrument and bool(result.get("contamination_not_expanded"))
        if result.get("task_7_passed") is not expected_task:
            raise ValueError("Task-7 instrument-only result was promoted to an overall pass")
        contract = result.get("window_contract")
        if not isinstance(contract, Mapping):
            raise ValueError("Task-7 window contract missing")
        if contract.get("full_suffix_replayed_by_local_kernel") is not False:
            raise ValueError("Task-7 local kernel replayed the fixed suffix")
        if contract.get("untouched_suffix_copy_scan_or_rehash") is not False:
            raise ValueError("Task-7 local kernel touched the fixed suffix")
        if int(cast(Any, contract.get("proposal_window_length", 0))) <= 1:
            raise ValueError("Task-7 registered result did not exercise W > 1")
        complexity = result.get("complexity_probe")
        if not isinstance(complexity, Mapping) or not _derive_task7_complexity_probe(complexity):
            raise ValueError("Task-7 registered long-suffix complexity probe failed")
        derived_strict_complexity = derived_zero_suffix
        if result.get("strict_window_complexity_passed") is not derived_strict_complexity:
            raise ValueError("Task-7 complexity state contradicts raw receipts")
    elif task == "8":
        if result.get("protocol_id") != TASK8_PROTOCOL_ID:
            raise ValueError("Task-8 protocol substitution")
        numeric_names = (
            "consequential_action_distribution_distance_primary",
            "min_measurable_consequential_action_distribution_distance",
            "mean_factorized_excess_consequential_cost",
            "min_measurable_mean_consequential_cost_advantage",
        )
        try:
            numeric = {name: float(cast(Any, result[name])) for name in numeric_names}
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Task-8 registered action/utility metrics are missing") from error
        if not all(math.isfinite(value) for value in numeric.values()):
            raise ValueError("Task-8 registered action/utility metrics must be finite")
        if (
            numeric["min_measurable_consequential_action_distribution_distance"]
            != MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE
            or numeric["min_measurable_mean_consequential_cost_advantage"]
            != MIN_MEASURABLE_MEAN_CONSEQUENTIAL_COST_ADVANTAGE
        ):
            raise ValueError("Task-8 result thresholds differ from frozen executable values")
        expected_endpoint = (
            numeric["consequential_action_distribution_distance_primary"]
            >= numeric["min_measurable_consequential_action_distribution_distance"]
        )
        expected_benefit = (
            numeric["mean_factorized_excess_consequential_cost"]
            >= numeric["min_measurable_mean_consequential_cost_advantage"]
        )
        if result.get("consequential_action_endpoint_passed") is not expected_endpoint:
            raise ValueError("Task-8 action endpoint state contradicts its registered threshold")
        if result.get("consequential_utility_benefit_passed") is not expected_benefit:
            raise ValueError(
                "Task-8 utility direction/benefit state contradicts its registered rule"
            )
        expected_consumption = task8_endpoint_consumes_interaction()
        if result.get("endpoint_consumes_interaction") is not expected_consumption:
            raise ValueError("Task-8 endpoint cross-term consumption was not recomputed")
        if result.get("consequential_endpoint_id") != "joint-cross-safety-policy@0.1":
            raise ValueError("Task-8 consequential endpoint substitution")
        expected_joint = (
            bool(result.get("belief_coupling_instrument_passed"))
            and expected_consumption
            and expected_endpoint
            and expected_benefit
        )
        if result.get("joint_action_utility_passed") is not expected_joint:
            raise ValueError("Task-8 joint action/utility state contradicts its prerequisites")
        if result.get("task_8_passed") is not expected_joint:
            raise ValueError("Task-8 instrument-only result was promoted to an overall pass")
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
