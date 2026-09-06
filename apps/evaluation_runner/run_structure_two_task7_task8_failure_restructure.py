#!/usr/bin/env python3
"""Run the frozen failure-driven Task-7/8 development restructuring study."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
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
)
from cpswm.system.evaluation_operations.structure_two_task7_task8_method_restructure import (  # noqa: E402
    TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID,
    TASK7_GUARDED_REWEIGHT_ESS_RATIO,
    TASK8_IDENTIFIABILITY_PROTOCOL_ID,
    run_task7_guarded_restructure_study,
    run_task8_identifiability_audit,
)

CONFIG_PATH: Final = Path(
    "configs/project_two_experiments/structure_two_task7_task8_failure_restructure_v0_1.json"
)
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_task7_task8_method_restructure.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_task8_matched_confirmatory.py"),
    Path("apps/evaluation_runner/run_structure_two_task7_task8_failure_restructure.py"),
)
ARTIFACT_PROTOCOL_ID: Final = "structure-two-task7-task8-restructure-evidence@0.2-development"
ARTIFACT_RUN_DATE: Final = "2026-09-05"
FROZEN_CONFIG_SHA256: Final = "61d2cecd50dcf7c0516875263dde6c54be847fb7156bdc7f1209afeb84fb175a"
TRUST_CHAIN_DESCRIPTION: Final = (
    "artifact_content+current_source_bundle+frozen_development_config+"
    "semantic_derivation_from_raw_rows+fresh_independent_execution"
)
ARTIFACT_CLAIM_BOUNDARY: Final = (
    "Failure-driven D0 development evidence only; no independent custody, no external validity, "
    "no replacement of either v0.4 failure, and no seven-operator authorization."
)
TASK7_FACTOR_NAMES: Final = (
    "high_attribution_ambiguity",
    "adverse_delayed_feedback",
    "open_world_actor",
    "short_regime",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_config() -> dict[str, Any]:
    path = REPOSITORY_ROOT / CONFIG_PATH
    if _file_sha256(path) != FROZEN_CONFIG_SHA256:
        raise ValueError("restructure frozen config content drift")
    raw: object = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )
    if not isinstance(raw, dict):
        raise ValueError("restructure config must be an object")
    config = {str(key): value for key, value in raw.items()}
    if config.get("status") != "FROZEN_BEFORE_HOLDOUT_EXECUTION":
        raise ValueError("restructure config is not frozen")
    if config.get("protocol_id") != "structure-two-task7-task8-failure-restructure@0.1-development":
        raise ValueError("restructure config protocol substitution")
    task7 = config.get("task_7")
    task8 = config.get("task_8")
    if not isinstance(task7, Mapping) or not isinstance(task8, Mapping):
        raise ValueError("restructure frozen task config is malformed")
    if (
        float(task7.get("belief_axis_tv_tolerance", math.nan)) != TASK7_BELIEF_AXIS_TV_TOLERANCE
        or float(task7.get("action_distribution_tv_tolerance", math.nan))
        != TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        or task7.get("selected_action_must_match") is not True
        or task7.get("contamination_non_expansion_required") is not True
        or task7.get("both_routes_must_execute") is not True
        or task7.get("mean_marginal_work_must_be_below_full_replay") is not True
    ):
        raise ValueError("Task-7 frozen decision semantics drift")
    if (
        float(task8.get("numeric_equivalence_tolerance", math.nan)) != 1e-12
        or float(task8.get("identity_temperature", math.nan)) != 1.0
        or task8.get("post_hoc_temperature_or_endpoint_changes_allowed") is not False
        or task8.get("next_method_axis_requires_project_owner_choice") is not True
    ):
        raise ValueError("Task-8 frozen decision semantics drift")
    return config


def run_frozen_study() -> dict[str, Any]:
    config = _load_config()
    task7_config = cast(Mapping[str, Any], config["task_7"])
    task8_config = cast(Mapping[str, Any], config["task_8"])
    threshold = float(task7_config["pre_rejuvenation_ess_ratio_threshold"])
    if threshold != TASK7_GUARDED_REWEIGHT_ESS_RATIO:
        raise ValueError("Task-7 executable and frozen ESS thresholds disagree")
    task7_result = run_task7_guarded_restructure_study(
        scenario_seeds=tuple(int(value) for value in task7_config["scenario_seeds"]),
        replicate_seeds=tuple(int(value) for value in task7_config["replicate_seeds"]),
        gaps=int(task7_config["gaps"]),
        correction_index=int(task7_config["correction_index"]),
        budget=int(task7_config["particle_budget"]),
        ess_ratio_threshold=threshold,
    )
    task8_result = run_task8_identifiability_audit(
        seeds=tuple(int(value) for value in task8_config["seeds"])
    )
    if task7_result["protocol_id"] != TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID:
        raise AssertionError("Task-7 restructure protocol mismatch")
    if task8_result["protocol_id"] != TASK8_IDENTIFIABILITY_PROTOCOL_ID:
        raise AssertionError("Task-8 restructure protocol mismatch")
    return {"task_7": task7_result, "task_8": task8_result}


def make_artifact(result: Mapping[str, Any]) -> dict[str, Any]:
    config_path = REPOSITORY_ROOT / CONFIG_PATH
    files = [
        {"path": path.as_posix(), "sha256": _file_sha256(REPOSITORY_ROOT / path)}
        for path in (*SOURCE_PATHS, CONFIG_PATH)
    ]
    recomputation = {
        "deterministic_result_sha256": _sha256(result),
        "fresh_recomputation_required": True,
    }
    positive_claims = {"result": dict(result), "recomputation": recomputation}
    unsigned = {
        "artifact_protocol_id": ARTIFACT_PROTOCOL_ID,
        "run_date": ARTIFACT_RUN_DATE,
        "config": {"path": CONFIG_PATH.as_posix(), "sha256": _file_sha256(config_path)},
        "source_bundle": {"files": files, "content_sha256": _sha256(files)},
        "result": dict(result),
        "recomputation": recomputation,
        "positive_output_trust_chain": {
            path: TRUST_CHAIN_DESCRIPTION for path in _positive_boolean_paths(positive_claims)
        },
        "claim_boundary": ARTIFACT_CLAIM_BOUNDARY,
    }
    return {**unsigned, "content_sha256": _sha256(unsigned)}


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are missing, duplicated by alias, or unknown")


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a JSON number, not a boolean or string")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _finite_probability(value: object, label: str) -> float:
    numeric = _finite_number(value, label)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{label} must be a finite value in [0, 1]")
    return numeric


def _strict_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a JSON integer")
    return value


def _verify_task7(result: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    _require_exact_keys(
        result,
        {
            "protocol_id",
            "evidence_status",
            "design",
            "method",
            "route_counts",
            "belief_guardrail_passed",
            "action_guardrail_passed",
            "contamination_guardrail_passed",
            "mean_guarded_owner_contamination",
            "mean_full_rerun_owner_contamination",
            "mean_guarded_marginal_elementary_evaluations",
            "mean_full_rerun_marginal_elementary_evaluations",
            "mixed_route_nontriviality_passed",
            "candidate_passed",
            "failed_guard_rows",
            "failure_diagnosis",
            "required_next_state_change",
            "claim_boundary",
            "rows",
        },
        "Task-7 result",
    )
    if result.get("protocol_id") != TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID:
        raise ValueError("Task-7 restructure protocol substitution")
    design = result.get("design")
    if not isinstance(design, Mapping):
        raise ValueError("Task-7 design is missing")
    scenario_seeds = [int(seed) for seed in config["scenario_seeds"]]
    replicate_seeds = [int(seed) for seed in config["replicate_seeds"]]
    gaps = int(config["gaps"])
    threshold = float(config["pre_rejuvenation_ess_ratio_threshold"])
    expected_design: dict[str, object] = {
        "gaps": gaps,
        "correction_index": int(config["correction_index"]),
        "scenario_seeds": scenario_seeds,
        "replicate_seeds": replicate_seeds,
        "factor_cells_per_scenario_seed": 16,
        "particle_budget": int(config["particle_budget"]),
        "guarded_reweight_ess_ratio": threshold,
        "threshold_origin": (
            "frozen after diagnosing v0.4 and before evaluating the new holdout seeds"
        ),
    }
    if dict(design) != expected_design:
        raise ValueError("Task-7 result design does not match the frozen config")
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Task-7 restructure rows are missing")
    row_fields = {
        "scenario_id",
        "scenario_factors",
        "replicate_seed",
        "route",
        "fallback_required",
        "fallback_reasons",
        "pre_rejuvenation_ess_ratio",
        "belief_axis_distances_to_full_rerun",
        "max_belief_axis_distance_to_full_rerun",
        "action_distribution_distance_to_full_rerun",
        "selected_action_matches_full_rerun",
        "guarded_owner_contamination",
        "full_rerun_owner_contamination",
        "guarded_marginal_elementary_evaluations",
        "full_rerun_marginal_elementary_evaluations",
    }
    expected_units: set[tuple[str, int]] = set()
    expected_factors: dict[str, dict[str, bool]] = {}
    for seed in scenario_seeds:
        for ambiguity in (False, True):
            for delayed in (False, True):
                for open_world in (False, True):
                    for short_regime in (False, True):
                        flags = "".join(
                            str(int(value))
                            for value in (ambiguity, delayed, open_world, short_regime)
                        )
                        scenario_id = f"G{gaps}-S{seed}-{flags}"
                        expected_factors[scenario_id] = dict(
                            zip(
                                TASK7_FACTOR_NAMES,
                                (ambiguity, delayed, open_world, short_regime),
                                strict=True,
                            )
                        )
                        expected_units.update(
                            (scenario_id, replicate_seed) for replicate_seed in replicate_seeds
                        )
    observed_units: set[tuple[str, int]] = set()
    for item in rows:
        if not isinstance(item, Mapping):
            raise ValueError("Task-7 raw row must be an object")
        _require_exact_keys(item, row_fields, "Task-7 raw row")
        if not isinstance(item["scenario_id"], str):
            raise ValueError("Task-7 scenario identity must be a string")
        scenario_id = item["scenario_id"]
        replicate_seed = _strict_int(item["replicate_seed"], "Task-7 replicate seed")
        unit = (scenario_id, replicate_seed)
        if unit in observed_units:
            raise ValueError("Task-7 duplicate scenario/replicate unit")
        observed_units.add(unit)
        factors = item["scenario_factors"]
        if (
            not isinstance(factors, Mapping)
            or any(type(value) is not bool for value in factors.values())
            or dict(factors) != expected_factors.get(scenario_id)
        ):
            raise ValueError("Task-7 scenario factors or identity do not match the frozen matrix")
        distances = item["belief_axis_distances_to_full_rerun"]
        if not isinstance(distances, Mapping) or set(distances) != set(TASK7_BELIEF_AXES):
            raise ValueError("Task-7 belief-axis coverage is incomplete")
        belief_distances = [
            _finite_probability(distance, f"Task-7 {axis} distance")
            for axis, distance in distances.items()
        ]
        if not math.isclose(
            _finite_probability(
                item["max_belief_axis_distance_to_full_rerun"], "Task-7 max belief distance"
            ),
            max(belief_distances),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("Task-7 max belief distance is not derived from all belief axes")
        _finite_probability(
            item["action_distribution_distance_to_full_rerun"], "Task-7 action distance"
        )
        _finite_probability(item["guarded_owner_contamination"], "Task-7 contamination")
        _finite_probability(item["full_rerun_owner_contamination"], "Task-7 full contamination")
        ess_ratio = _finite_probability(item["pre_rejuvenation_ess_ratio"], "Task-7 ESS ratio")
        if type(item["selected_action_matches_full_rerun"]) is not bool:
            raise ValueError("Task-7 selected-action match must be a boolean")
        for field in (
            "guarded_marginal_elementary_evaluations",
            "full_rerun_marginal_elementary_evaluations",
        ):
            if isinstance(item[field], bool) or not isinstance(item[field], int) or item[field] < 0:
                raise ValueError("Task-7 work counters must be non-negative integers")
        route = item["route"]
        if route == "guarded_reweight":
            if (
                item["fallback_required"] is not False
                or item["fallback_reasons"] != ""
                or ess_ratio < threshold
            ):
                raise ValueError("Task-7 guarded-reweight route contradicts its ESS state")
        elif route == "guarded_full_replay":
            if (
                item["fallback_required"] is not True
                or item["fallback_reasons"] != "reweight_support_collapse"
                or ess_ratio >= threshold
            ):
                raise ValueError("Task-7 fallback route contradicts its ESS state")
        else:
            raise ValueError("Task-7 raw row names an unknown repair route")
    if observed_units != expected_units:
        raise ValueError("Task-7 rows do not exactly cover the frozen factor-by-seed design")
    routes = ("guarded_reweight", "guarded_full_replay")
    route_counts = {route: sum(1 for row in rows if row.get("route") == route) for route in routes}
    recorded_route_counts = result.get("route_counts")
    if (
        not isinstance(recorded_route_counts, Mapping)
        or any(type(value) is not int for value in recorded_route_counts.values())
        or dict(recorded_route_counts) != route_counts
    ):
        raise ValueError("Task-7 route counts do not derive from raw rows")
    belief_guardrail = all(
        float(row["max_belief_axis_distance_to_full_rerun"]) <= TASK7_BELIEF_AXIS_TV_TOLERANCE
        for row in rows
    )
    action_guardrail = all(
        float(row["action_distribution_distance_to_full_rerun"])
        <= TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        and row["selected_action_matches_full_rerun"] is True
        for row in rows
    )
    guarded_contamination = sum(float(row["guarded_owner_contamination"]) for row in rows)
    full_contamination = sum(float(row["full_rerun_owner_contamination"]) for row in rows)
    contamination_guardrail = guarded_contamination <= full_contamination
    guarded_work = sum(int(row["guarded_marginal_elementary_evaluations"]) for row in rows)
    full_work = sum(int(row["full_rerun_marginal_elementary_evaluations"]) for row in rows)
    mixed = all(count > 0 for count in route_counts.values())
    candidate = (
        belief_guardrail
        and action_guardrail
        and contamination_guardrail
        and guarded_work < full_work
        and mixed
    )
    derived = {
        "belief_guardrail_passed": belief_guardrail,
        "action_guardrail_passed": action_guardrail,
        "contamination_guardrail_passed": contamination_guardrail,
        "mixed_route_nontriviality_passed": mixed,
        "candidate_passed": candidate,
    }
    if any(result.get(key) is not value for key, value in derived.items()):
        raise ValueError("Task-7 positive or consequential verdict is not derived from raw rows")
    count = len(rows)
    numeric = {
        "mean_guarded_owner_contamination": guarded_contamination / count,
        "mean_full_rerun_owner_contamination": full_contamination / count,
        "mean_guarded_marginal_elementary_evaluations": guarded_work / count,
        "mean_full_rerun_marginal_elementary_evaluations": full_work / count,
    }
    if any(
        not math.isclose(
            _finite_number(result.get(key), f"Task-7 {key}"),
            value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        for key, value in numeric.items()
    ):
        raise ValueError("Task-7 aggregate metric is not derived from raw rows")

    expected_failed_rows = [
        {
            "scenario_id": row["scenario_id"],
            "replicate_seed": row["replicate_seed"],
            "route": row["route"],
            "pre_rejuvenation_ess_ratio": row["pre_rejuvenation_ess_ratio"],
            "max_belief_axis_distance_to_full_rerun": row["max_belief_axis_distance_to_full_rerun"],
            "action_distribution_distance_to_full_rerun": row[
                "action_distribution_distance_to_full_rerun"
            ],
            "guarded_owner_contamination": row["guarded_owner_contamination"],
            "full_rerun_owner_contamination": row["full_rerun_owner_contamination"],
        }
        for row in rows
        if float(row["max_belief_axis_distance_to_full_rerun"]) > TASK7_BELIEF_AXIS_TV_TOLERANCE
        or float(row["action_distribution_distance_to_full_rerun"])
        > TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        or row["selected_action_matches_full_rerun"] is not True
        or float(row["guarded_owner_contamination"]) > float(row["full_rerun_owner_contamination"])
    ]
    failed_rows = result.get("failed_guard_rows")
    if not isinstance(failed_rows, list) or sorted(
        _canonical_bytes(row) for row in failed_rows
    ) != sorted(_canonical_bytes(row) for row in expected_failed_rows):
        raise ValueError("Task-7 failed-guard rows are not derived from raw rows")
    if candidate:
        if (
            result.get("failure_diagnosis") is not None
            or result.get("required_next_state_change") is not None
        ):
            raise ValueError("Task-7 passing candidate cannot carry a failure diagnosis")
    elif not result.get("failure_diagnosis") or not result.get("required_next_state_change"):
        raise ValueError("Task-7 failed candidate must retain its method-level diagnosis")


def _verify_task8(result: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    _require_exact_keys(
        result,
        {
            "protocol_id",
            "evidence_status",
            "seeds",
            "factor_units",
            "identity_temperature",
            "max_posterior_l1",
            "max_policy_l1",
            "max_absolute_expected_cost_difference",
            "matched_two_stage_representation_equivalent",
            "joint_representation_superiority_identifiable",
            "diagnosis",
            "redesign_options_requiring_owner_choice",
            "seven_operator_efficacy_authorized",
            "rows",
        },
        "Task-8 result",
    )
    if result.get("protocol_id") != TASK8_IDENTIFIABILITY_PROTOCOL_ID:
        raise ValueError("Task-8 identifiability protocol substitution")
    expected_seeds = [int(seed) for seed in config["seeds"]]
    identity_temperature = _finite_number(
        result.get("identity_temperature"), "Task-8 identity temperature"
    )
    if result.get("seeds") != expected_seeds or identity_temperature != float(
        config["identity_temperature"]
    ):
        raise ValueError("Task-8 result design does not match the frozen config")
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Task-8 identifiability rows are missing")
    row_fields = {
        "unit_id",
        "cluster_seed",
        "posterior_l1",
        "policy_l1",
        "matched_two_stage_cost_minus_joint_cost",
    }
    expected_units = {
        (f"G1-S{seed}-{factor:03b}1-RPC1.5", seed) for seed in expected_seeds for factor in range(8)
    }
    observed_units: set[tuple[str, int]] = set()
    for item in rows:
        if not isinstance(item, Mapping):
            raise ValueError("Task-8 identifiability row must be an object")
        _require_exact_keys(item, row_fields, "Task-8 identifiability row")
        if not isinstance(item["unit_id"], str):
            raise ValueError("Task-8 factor-unit identity must be a string")
        unit = (
            item["unit_id"],
            _strict_int(item["cluster_seed"], "Task-8 cluster seed"),
        )
        if unit in observed_units:
            raise ValueError("Task-8 duplicate factor unit")
        observed_units.add(unit)
        for field in ("posterior_l1", "policy_l1"):
            value = _finite_number(item[field], f"Task-8 {field}")
            if not math.isfinite(value) or not 0.0 <= value <= 2.0:
                raise ValueError("Task-8 L1 distances must be finite and lie in [0, 2]")
        _finite_number(item["matched_two_stage_cost_minus_joint_cost"], "Task-8 cost difference")
    if observed_units != expected_units:
        raise ValueError("Task-8 rows do not exactly cover the frozen seed-by-factor design")
    maxima = {
        "max_posterior_l1": max(float(row["posterior_l1"]) for row in rows),
        "max_policy_l1": max(float(row["policy_l1"]) for row in rows),
        "max_absolute_expected_cost_difference": max(
            abs(float(row["matched_two_stage_cost_minus_joint_cost"])) for row in rows
        ),
    }
    if _strict_int(result.get("factor_units"), "Task-8 factor-unit count") != len(rows) or any(
        not math.isclose(
            _finite_number(result.get(key), f"Task-8 {key}"),
            value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        for key, value in maxima.items()
    ):
        raise ValueError("Task-8 identifiability aggregate is not derived from raw rows")
    equivalent = all(value <= 1e-12 for value in maxima.values())
    if result.get("matched_two_stage_representation_equivalent") is not equivalent:
        raise ValueError("Task-8 equivalence verdict is not derived from raw rows")
    if result.get("joint_representation_superiority_identifiable") is equivalent:
        raise ValueError("Task-8 identifiability verdict contradicts exact equivalence")
    if result.get("seven_operator_efficacy_authorized") is not False:
        raise ValueError("Task-8 development audit cannot authorize seven-operator efficacy")


def verify_artifact(
    payload: Mapping[str, Any], *, fresh_result: Mapping[str, Any] | None = None
) -> None:
    _require_exact_keys(
        payload,
        {
            "artifact_protocol_id",
            "run_date",
            "config",
            "source_bundle",
            "result",
            "recomputation",
            "positive_output_trust_chain",
            "claim_boundary",
            "content_sha256",
        },
        "restructure artifact",
    )
    unsigned = dict(payload)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _sha256(unsigned):
        raise ValueError("restructure artifact content hash mismatch")
    if payload.get("artifact_protocol_id") != ARTIFACT_PROTOCOL_ID:
        raise ValueError("restructure artifact protocol substitution")
    if payload.get("run_date") != ARTIFACT_RUN_DATE:
        raise ValueError("restructure artifact run-date substitution")
    if payload.get("claim_boundary") != ARTIFACT_CLAIM_BOUNDARY:
        raise ValueError("restructure artifact claim-boundary substitution")
    frozen_config = _load_config()
    config = payload.get("config")
    if not isinstance(config, Mapping) or config.get("path") != CONFIG_PATH.as_posix():
        raise ValueError("restructure artifact config path mismatch")
    _require_exact_keys(config, {"path", "sha256"}, "restructure artifact config")
    if config.get("sha256") != _file_sha256(REPOSITORY_ROOT / CONFIG_PATH):
        raise ValueError("restructure artifact config drift")
    source_bundle = payload.get("source_bundle")
    if not isinstance(source_bundle, Mapping):
        raise ValueError("restructure source bundle is missing")
    _require_exact_keys(source_bundle, {"files", "content_sha256"}, "restructure source bundle")
    expected_files = [
        {"path": path.as_posix(), "sha256": _file_sha256(REPOSITORY_ROOT / path)}
        for path in (*SOURCE_PATHS, CONFIG_PATH)
    ]
    if source_bundle.get("files") != expected_files or source_bundle.get(
        "content_sha256"
    ) != _sha256(expected_files):
        raise ValueError("restructure artifact source bundle drift")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("restructure result is missing")
    _require_exact_keys(result, {"task_7", "task_8"}, "restructure task result bundle")
    trust_chain = payload.get("positive_output_trust_chain")
    recomputation = payload.get("recomputation")
    expected_recomputation = {
        "deterministic_result_sha256": _sha256(result),
        "fresh_recomputation_required": True,
    }
    if recomputation != expected_recomputation:
        raise ValueError("restructure deterministic recomputation binding is malformed")
    positive_claims = {"result": result, "recomputation": expected_recomputation}
    expected_trust_chain = {
        path: TRUST_CHAIN_DESCRIPTION for path in _positive_boolean_paths(positive_claims)
    }
    if trust_chain != expected_trust_chain:
        raise ValueError("restructure positive-output trust chain is incomplete")
    task7_result = result.get("task_7")
    task8_result = result.get("task_8")
    if not isinstance(task7_result, Mapping) or not isinstance(task8_result, Mapping):
        raise ValueError("restructure task result is malformed")
    task7_config = frozen_config.get("task_7")
    task8_config = frozen_config.get("task_8")
    if not isinstance(task7_config, Mapping) or not isinstance(task8_config, Mapping):
        raise ValueError("restructure frozen task config is malformed")
    _verify_task7(task7_result, task7_config)
    _verify_task8(task8_result, task8_config)
    if fresh_result is None:
        raise ValueError("fresh independent restructure recomputation is required")
    if dict(fresh_result) != dict(result):
        raise ValueError("fresh restructure recomputation does not match the stored result")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_frozen_study()
    artifact = make_artifact(result)
    verify_artifact(artifact, fresh_result=run_frozen_study())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "content_sha256": artifact["content_sha256"],
                "task_7_candidate_passed": result["task_7"]["candidate_passed"],
                "task_8_joint_superiority_identifiable": result["task_8"][
                    "joint_representation_superiority_identifiable"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
