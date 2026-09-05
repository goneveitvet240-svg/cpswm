"""Task-8 v0.4 matched three-arm confirmatory protocol.

The historical v0.3 run compared joint inference only with a factorized arm.
It remains immutable evidence for that narrower question, but cannot answer the
current joint-vs-matched-two-stage claim.  This module performs validation-only
independent tuning for all three arms and freezes those selections before any
confirmatory unit is evaluated.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .structure_two_backbone_falsifier import (
    TASK8_HANDOFF_ACTOR_SEVERITY,
    TASK8_REGIME_HABIT_SEVERITY,
    TASK8_UNRESOLVED_SEVERITY,
    TASK8_VERIFY_COST,
    UNRESOLVED_KEY,
    ArmName,
    BackboneScenario,
    CostMeter,
    InferenceCoupling,
    JointConsequenceAction,
    _coupling_table,
    _CouplingRow,
    _decouple,
    _joint_cross_severity,
    consequential_action_policy,
    consequential_expected_cost,
    registered_scenarios,
    task8_endpoint_consumes_interaction,
)

TASK8_MATCHED_PROTOCOL_ID: Final = "structure-two-relative-probability-joint-coupling@0.4"
TASK8_MATCHED_ENDPOINT_ID: Final = "joint-cross-safety-policy@0.1"
TASK8_MATCHED_COUPLING_NATS: Final = 1.5
TASK8_PAIRED_COST_CI_THRESHOLD: Final = 0.001
TASK8_PAIRED_CI_CONFIDENCE: Final = 0.95
TASK8_PAIRED_BOOTSTRAP_REPLICATES: Final = 10_000
TASK8_PAIRED_BOOTSTRAP_SEED: Final = "task8-v0.4-ci-20260905"
TASK8_TUNING_CANDIDATES: Final = (0.75, 1.0, 1.25)
TASK8_ARM_NAMES: Final = ("joint", "factorized", "matched_two_stage")
TASK8_REGISTERED_GAPS: Final = 1
TASK8_REGISTERED_VALIDATION_SEEDS: Final = (101, 103, 107)
TASK8_REGISTERED_CONFIRMATORY_SEEDS: Final = (211, 223, 227, 229, 233)
TASK8_REGISTERED_STATE_BUDGET: Final = 2_000_000


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _temper_fixed_unresolved(belief: Mapping[str, float], temperature: float) -> dict[str, float]:
    if temperature <= 0.0 or not math.isfinite(temperature):
        raise ValueError("Task-8 posterior temperature must be finite and positive")
    unresolved = float(belief.get(UNRESOLVED_KEY, 0.0))
    resolved_target = max(0.0, 1.0 - unresolved)
    exponent = 1.0 / temperature
    powered = {
        key: probability**exponent
        for key, probability in belief.items()
        if key != UNRESOLVED_KEY and probability > 0.0
    }
    normalizer = sum(powered.values())
    if normalizer <= 0.0:
        return {UNRESOLVED_KEY: 1.0}
    output = {
        key: resolved_target * probability / normalizer for key, probability in powered.items()
    }
    output[UNRESOLVED_KEY] = unresolved
    return output


def _matched_two_stage_belief(
    exact: Mapping[str, float],
    rows: Sequence[_CouplingRow],
    *,
    cause_temperature: float,
    conditional_temperature: float,
) -> dict[str, float]:
    """Sequentially compose tuned ``p(C)`` and tuned ``p(H+Z|C)``.

    Both stages receive the complete exact posterior table.  At temperatures
    ``(1, 1)`` this is exactly the joint posterior, making the two-stage arm a
    strong matched comparator instead of the historical hard-argmax collapse.
    """

    if cause_temperature <= 0.0 or conditional_temperature <= 0.0:
        raise ValueError("Task-8 two-stage temperatures must be positive")
    unresolved = float(exact.get(UNRESOLVED_KEY, 0.0))
    resolved_target = max(0.0, 1.0 - unresolved)
    by_cause: dict[str, list[_CouplingRow]] = {}
    cause_mass: dict[str, float] = {}
    for row in rows:
        probability = float(exact.get(row.key, 0.0))
        if probability <= 0.0:
            continue
        by_cause.setdefault(row.cause, []).append(row)
        cause_mass[row.cause] = cause_mass.get(row.cause, 0.0) + probability
    cause_power = {cause: mass ** (1.0 / cause_temperature) for cause, mass in cause_mass.items()}
    cause_normalizer = sum(cause_power.values())
    if cause_normalizer <= 0.0:
        return {UNRESOLVED_KEY: 1.0}
    output: dict[str, float] = {}
    for cause, cause_rows in by_cause.items():
        stage_one_mass = resolved_target * cause_power[cause] / cause_normalizer
        source_mass = cause_mass[cause]
        conditional_power = {
            row.key: (float(exact[row.key]) / source_mass) ** (1.0 / conditional_temperature)
            for row in cause_rows
        }
        conditional_normalizer = sum(conditional_power.values())
        for key, mass in conditional_power.items():
            output[key] = stage_one_mass * mass / conditional_normalizer
    output[UNRESOLVED_KEY] = unresolved
    return output


def _arm_belief(
    arm: str,
    exact: Mapping[str, float],
    rows: Sequence[_CouplingRow],
    temperature: float,
) -> dict[str, float]:
    if arm == "joint":
        return _temper_fixed_unresolved(exact, temperature)
    if arm == "factorized":
        factorized = _decouple(exact, rows, InferenceCoupling.FACTORIZED)
        return _temper_fixed_unresolved(factorized, temperature)
    if arm == "matched_two_stage":
        return _matched_two_stage_belief(
            exact,
            rows,
            cause_temperature=temperature,
            conditional_temperature=temperature,
        )
    raise ValueError(f"unknown Task-8 arm: {arm}")


def _observation_payload(scenario: BackboneScenario) -> list[dict[str, object]]:
    return [
        {
            "observed_mechanism": observation.observed_mechanism.value,
            "observed_giver": observation.observed_giver.value,
            "observed_receiver": observation.observed_receiver.value,
            "observed_instance": observation.observed_instance.value,
            "observed_cause": observation.observed_cause.value,
            "observed_regime_change": observation.observed_regime_change,
            "placement_bin": observation.placement_bin,
            "placement_value": observation.placement_value,
            "mechanism_reliability": observation.mechanism_reliability,
            "actor_reliability": observation.actor_reliability,
            "instance_reliability": observation.instance_reliability,
            "cause_reliability": observation.cause_reliability,
            "regime_reliability": observation.regime_reliability,
        }
        for observation in scenario.observations
    ]


@dataclass(frozen=True, slots=True)
class _PreparedUnit:
    unit_id: str
    cluster_seed: int
    scenario: BackboneScenario
    exact: Mapping[str, float]
    rows: tuple[_CouplingRow, ...]
    truth_severity: float
    information_sha256: str
    enumerated_states: int
    state_budget: int


def _prepare_unit(
    scenario: BackboneScenario, state_budget: int, *, cluster_seed: int
) -> _PreparedUnit:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, rows = _coupling_table(
        scenario,
        meter,
        state_budget,
        include_regime=True,
    )
    truth_row = next(row for row in rows if row.key == scenario.truth.key)
    information_sha256 = _sha256(
        {
            "scenario_id": scenario.scenario_id,
            "observations": _observation_payload(scenario),
            "posterior": sorted(exact.items()),
            "row_keys": [row.key for row in rows],
        }
    )
    return _PreparedUnit(
        unit_id=scenario.scenario_id,
        cluster_seed=cluster_seed,
        scenario=scenario,
        exact=exact,
        rows=tuple(rows),
        truth_severity=_joint_cross_severity(truth_row),
        information_sha256=information_sha256,
        enumerated_states=len(rows),
        state_budget=state_budget,
    )


def _evaluate_candidate(unit: _PreparedUnit, arm: str, temperature: float) -> dict[str, Any]:
    belief = _arm_belief(arm, unit.exact, unit.rows, temperature)
    policy = consequential_action_policy(belief, unit.rows)
    return {
        "unit_id": unit.unit_id,
        "cluster_seed": unit.cluster_seed,
        "arm": arm,
        "temperature": temperature,
        "shared_information_sha256": unit.information_sha256,
        "state_budget": unit.state_budget,
        "enumerated_states": unit.enumerated_states,
        "posterior_cells_visible": len(unit.rows) + 1,
        "truth_visible_to_arm": False,
        "truth_cross_cell_severity": unit.truth_severity,
        "consequential_action_policy": policy,
        "selected_consequential_action": max(
            policy,
            key=lambda name: (policy[name], name),
        ),
        "consequential_expected_cost": consequential_expected_cost(policy, unit.truth_severity),
    }


def _freeze_validation_selections(
    validation_rows: Sequence[Mapping[str, Any]], validation_unit_ids: Sequence[str]
) -> dict[str, Any]:
    selections: dict[str, dict[str, Any]] = {}
    for arm in TASK8_ARM_NAMES:
        candidates: list[dict[str, Any]] = []
        for temperature in TASK8_TUNING_CANDIDATES:
            subset = [
                row
                for row in validation_rows
                if row["arm"] == arm and float(row["temperature"]) == temperature
            ]
            if len(subset) != len(validation_unit_ids):
                raise ValueError("Task-8 validation tuning has incomplete arm x unit coverage")
            candidates.append(
                {
                    "temperature": temperature,
                    "validation_mean_cost": sum(
                        float(row["consequential_expected_cost"]) for row in subset
                    )
                    / len(subset),
                }
            )
        selected = min(
            candidates,
            key=lambda candidate: (
                float(candidate["validation_mean_cost"]),
                abs(float(candidate["temperature"]) - 1.0),
                float(candidate["temperature"]),
            ),
        )
        selections[arm] = dict(selected)
    unsigned = {
        "receipt_type": "task8-validation-only-arm-selection@0.1",
        "protocol_id": TASK8_MATCHED_PROTOCOL_ID,
        "validation_unit_ids": list(validation_unit_ids),
        "candidate_temperatures": list(TASK8_TUNING_CANDIDATES),
        "selection_rule": (
            "minimum validation mean cost; ties prefer temperature nearest 1 then lower"
        ),
        "selections": selections,
        "confirmatory_units_read_before_freeze": False,
        "frozen_before_confirmatory_execution": True,
    }
    return {**unsigned, "content_sha256": _sha256(unsigned)}


def _verify_selection_receipt(
    receipt: Mapping[str, Any], validation_unit_ids: Sequence[str]
) -> None:
    unsigned = dict(receipt)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _sha256(unsigned):
        raise ValueError("Task-8 tuning-selection receipt hash mismatch")
    if receipt.get("protocol_id") != TASK8_MATCHED_PROTOCOL_ID:
        raise ValueError("Task-8 tuning-selection receipt protocol mismatch")
    if receipt.get("validation_unit_ids") != list(validation_unit_ids):
        raise ValueError("Task-8 tuning-selection receipt unit substitution")
    if receipt.get("candidate_temperatures") != list(TASK8_TUNING_CANDIDATES):
        raise ValueError("Task-8 tuning candidate substitution")
    if receipt.get("confirmatory_units_read_before_freeze") is not False:
        raise ValueError("Task-8 confirmatory leakage into tuning")
    if receipt.get("frozen_before_confirmatory_execution") is not True:
        raise ValueError("Task-8 selections were not frozen before confirmation")
    selections = receipt.get("selections")
    if not isinstance(selections, Mapping) or set(selections) != set(TASK8_ARM_NAMES):
        raise ValueError("Task-8 tuning receipt does not bind exactly three arms")
    for selection in selections.values():
        if not isinstance(selection, Mapping):
            raise ValueError("Task-8 selected hyperparameters are malformed")
        if float(selection.get("temperature", math.nan)) not in TASK8_TUNING_CANDIDATES:
            raise ValueError("Task-8 selected an unregistered hyperparameter")


def _paired_bootstrap_lower_bound(differences: Sequence[float]) -> float:
    if not differences or any(not math.isfinite(value) for value in differences):
        raise ValueError("Task-8 paired differences must be finite and non-empty")
    rng = random.Random(TASK8_PAIRED_BOOTSTRAP_SEED)
    count = len(differences)
    means = sorted(
        sum(differences[rng.randrange(count)] for _ in range(count)) / count
        for _ in range(TASK8_PAIRED_BOOTSTRAP_REPLICATES)
    )
    alpha = 1.0 - TASK8_PAIRED_CI_CONFIDENCE
    index = max(0, min(len(means) - 1, math.floor(alpha * len(means))))
    return means[index]


def _scenario_set(gaps: int, seeds: Sequence[int]) -> tuple[tuple[int, BackboneScenario], ...]:
    return tuple(
        (seed, scenario)
        for seed in seeds
        for scenario in registered_scenarios(
            gaps,
            (seed,),
            relative_probability_coupling_nats=TASK8_MATCHED_COUPLING_NATS,
            relative_probability_truth_model=True,
        )
    )


def run_task8_matched_confirmatory_study(
    *,
    gaps: int,
    validation_seeds: Sequence[int],
    confirmatory_seeds: Sequence[int],
    state_budget: int,
) -> dict[str, Any]:
    """Tune on validation only, freeze, then execute paired confirmation."""

    validation_seeds_tuple = tuple(int(seed) for seed in validation_seeds)
    confirmatory_seeds_tuple = tuple(int(seed) for seed in confirmatory_seeds)
    if (
        gaps != TASK8_REGISTERED_GAPS
        or validation_seeds_tuple != TASK8_REGISTERED_VALIDATION_SEEDS
        or confirmatory_seeds_tuple != TASK8_REGISTERED_CONFIRMATORY_SEEDS
        or state_budget != TASK8_REGISTERED_STATE_BUDGET
    ):
        raise ValueError("Task-8 v0.4 formal execution accepts only the frozen registered design")
    if not validation_seeds_tuple or not confirmatory_seeds_tuple:
        raise ValueError("Task-8 requires non-empty validation and confirmatory seeds")
    if set(validation_seeds_tuple) & set(confirmatory_seeds_tuple):
        raise ValueError("Task-8 validation and confirmatory seeds must be disjoint")
    if len(set(validation_seeds_tuple)) != len(validation_seeds_tuple):
        raise ValueError("Task-8 validation seeds must be unique")
    if len(set(confirmatory_seeds_tuple)) != len(confirmatory_seeds_tuple):
        raise ValueError("Task-8 confirmatory seeds must be unique")
    if state_budget <= 0:
        raise ValueError("Task-8 state budget must be positive")

    validation_units = tuple(
        _prepare_unit(scenario, state_budget, cluster_seed=cluster_seed)
        for cluster_seed, scenario in _scenario_set(gaps, validation_seeds_tuple)
    )
    validation_unit_ids = tuple(unit.unit_id for unit in validation_units)
    validation_rows = [
        _evaluate_candidate(unit, arm, temperature)
        for unit in validation_units
        for arm in TASK8_ARM_NAMES
        for temperature in TASK8_TUNING_CANDIDATES
    ]
    selection_receipt = _freeze_validation_selections(validation_rows, validation_unit_ids)
    _verify_selection_receipt(selection_receipt, validation_unit_ids)

    confirmatory_units = tuple(
        _prepare_unit(scenario, state_budget, cluster_seed=cluster_seed)
        for cluster_seed, scenario in _scenario_set(gaps, confirmatory_seeds_tuple)
    )
    confirmatory_unit_ids = tuple(unit.unit_id for unit in confirmatory_units)
    if set(validation_unit_ids) & set(confirmatory_unit_ids):
        raise ValueError("Task-8 validation and confirmatory unit IDs overlap")
    selections = selection_receipt["selections"]
    assert isinstance(selections, Mapping)
    confirmatory_rows: list[dict[str, Any]] = []
    for unit in confirmatory_units:
        unit_rows = []
        for arm in TASK8_ARM_NAMES:
            selection = selections[arm]
            assert isinstance(selection, Mapping)
            unit_rows.append(_evaluate_candidate(unit, arm, float(selection["temperature"])))
        information_hashes = {row["shared_information_sha256"] for row in unit_rows}
        budgets = {int(row["state_budget"]) for row in unit_rows}
        visible_cells = {int(row["posterior_cells_visible"]) for row in unit_rows}
        if len(information_hashes) != 1 or len(budgets) != 1 or len(visible_cells) != 1:
            raise AssertionError("Task-8 arms did not receive matched information and budget")
        confirmatory_rows.extend(unit_rows)

    by_unit: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in confirmatory_rows:
        by_unit.setdefault(str(row["unit_id"]), {})[str(row["arm"])] = row
    paired_rows: list[dict[str, Any]] = []
    for unit_id in confirmatory_unit_ids:
        arms = by_unit.get(unit_id, {})
        if set(arms) != set(TASK8_ARM_NAMES):
            raise AssertionError("Task-8 confirmatory arm x unit coverage is incomplete")
        joint_cost = float(arms["joint"]["consequential_expected_cost"])
        factorized_cost = float(arms["factorized"]["consequential_expected_cost"])
        two_stage_cost = float(arms["matched_two_stage"]["consequential_expected_cost"])
        paired_rows.append(
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
    cluster_rows: list[dict[str, Any]] = []
    for cluster_seed in confirmatory_seeds_tuple:
        subset = [row for row in paired_rows if int(row["cluster_seed"]) == cluster_seed]
        if len(subset) != 8:
            raise AssertionError("Task-8 confirmatory seed must contain all eight factor cells")
        cluster_rows.append(
            {
                "cluster_seed": cluster_seed,
                "factor_cells": len(subset),
                "mean_two_stage_cost_minus_joint_cost": sum(
                    float(row["two_stage_cost_minus_joint_cost"]) for row in subset
                )
                / len(subset),
            }
        )
    paired_differences = [
        float(row["mean_two_stage_cost_minus_joint_cost"]) for row in cluster_rows
    ]
    paired_mean = sum(paired_differences) / len(paired_differences)
    paired_lower_bound = _paired_bootstrap_lower_bound(paired_differences)
    ci_gate_passed = paired_lower_bound > TASK8_PAIRED_COST_CI_THRESHOLD
    endpoint_consumes_interaction = task8_endpoint_consumes_interaction()
    exact_coverage = len(confirmatory_rows) == len(confirmatory_unit_ids) * len(TASK8_ARM_NAMES)
    preregistration_matched = True
    task_passed = (
        preregistration_matched
        and endpoint_consumes_interaction
        and exact_coverage
        and ci_gate_passed
    )

    return {
        "protocol_id": TASK8_MATCHED_PROTOCOL_ID,
        "task": "task-8-matched-three-arm-confirmatory",
        "historical_v0_3_status": "FAILED_FOR_CURRENT_MATCHED_THREE_ARM_CLAIM",
        "evidence_status": (
            "D0 synthetic validation-plus-confirmatory execution; no formal independent-custody "
            "receipt and no external-validity claim"
        ),
        "design": {
            "gaps": gaps,
            "interaction_partition": "(H+Z,C)",
            "coupling_strength_nats": TASK8_MATCHED_COUPLING_NATS,
            "validation_seeds": list(validation_seeds_tuple),
            "confirmatory_seeds": list(confirmatory_seeds_tuple),
            "validation_independent_seed_clusters": len(validation_seeds_tuple),
            "validation_factor_cells": len(validation_unit_ids),
            "confirmatory_independent_seed_clusters": len(confirmatory_seeds_tuple),
            "confirmatory_factor_cells": len(confirmatory_unit_ids),
            "state_budget_per_arm_per_unit": state_budget,
            "validation_candidates_per_arm": len(TASK8_TUNING_CANDIDATES),
            "confirmatory_selected_configs_per_arm": 1,
            "same_observations_information_and_total_budget": True,
            "truth_visible_to_arm": False,
        },
        "endpoint": {
            "endpoint_id": TASK8_MATCHED_ENDPOINT_ID,
            "actions": [
                JointConsequenceAction.PROCEED.value,
                JointConsequenceAction.VERIFY.value,
            ],
            "verify_cost": TASK8_VERIFY_COST,
            "unresolved_severity": TASK8_UNRESOLVED_SEVERITY,
            "handoff_actor_severity": TASK8_HANDOFF_ACTOR_SEVERITY,
            "regime_habit_severity": TASK8_REGIME_HABIT_SEVERITY,
            "consumes_interaction": endpoint_consumes_interaction,
        },
        "selection_receipt": selection_receipt,
        "validation_only_independent_tuning_passed": True,
        "preregistered_design_matched": preregistration_matched,
        "validation_rows": validation_rows,
        "confirmatory_exact_arm_by_unit_coverage": exact_coverage,
        "confirmatory_rows": confirmatory_rows,
        "paired_rows": paired_rows,
        "paired_seed_cluster_rows": cluster_rows,
        "paired_inference": {
            "estimand": "matched_two_stage_cost - joint_cost",
            "independent_unit": "scenario RNG seed cluster; eight factorial cells averaged first",
            "method": "paired deterministic percentile bootstrap over seed-cluster means",
            "confidence": TASK8_PAIRED_CI_CONFIDENCE,
            "bootstrap_replicates": TASK8_PAIRED_BOOTSTRAP_REPLICATES,
            "bootstrap_seed": TASK8_PAIRED_BOOTSTRAP_SEED,
            "preregistered_strict_lower_bound_threshold": TASK8_PAIRED_COST_CI_THRESHOLD,
            "paired_mean": paired_mean,
            "paired_lower_confidence_bound": paired_lower_bound,
            "strict_lower_bound_gate_passed": ci_gate_passed,
        },
        "task_8_passed": task_passed,
        "task_8_verdict": "PASS" if task_passed else "FAIL",
        "seven_operator_efficacy_authorized": False,
        "claim_boundary": (
            "A pass would establish only a paired D0 advantage over an independently tuned "
            "matched two-stage comparator. A failure remains FAIL; neither outcome authorizes "
            "the trusted seven-operator ablation."
        ),
    }


__all__ = [
    "TASK8_ARM_NAMES",
    "TASK8_MATCHED_COUPLING_NATS",
    "TASK8_MATCHED_ENDPOINT_ID",
    "TASK8_MATCHED_PROTOCOL_ID",
    "TASK8_PAIRED_BOOTSTRAP_REPLICATES",
    "TASK8_PAIRED_BOOTSTRAP_SEED",
    "TASK8_PAIRED_CI_CONFIDENCE",
    "TASK8_PAIRED_COST_CI_THRESHOLD",
    "TASK8_REGISTERED_CONFIRMATORY_SEEDS",
    "TASK8_REGISTERED_GAPS",
    "TASK8_REGISTERED_STATE_BUDGET",
    "TASK8_REGISTERED_VALIDATION_SEEDS",
    "TASK8_TUNING_CANDIDATES",
    "run_task8_matched_confirmatory_study",
]
