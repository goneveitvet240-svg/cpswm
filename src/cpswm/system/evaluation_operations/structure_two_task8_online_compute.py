"""Task-8 vNext learned online-compute development falsifier.

The historical v0.4 comparison operated on an already available exact posterior.
At identity temperature, a chain-rule two-stage factorization reconstructs that
posterior exactly, so the experiment cannot identify a learned representation or
online-compute advantage.  This module instead trains three deployable predictors
from robot-visible observations only:

* a direct joint ``p(C_group, E_group | x)`` model;
* a matched conditional two-stage ``p(C_group | x) p(E_group | C_group, x)`` model;
* an information-restricted ``p(C_group | x) p(E_group | x)`` diagnostic.

The joint and conditional two-stage arms have exactly the same active parameter
count and inference multiply-add count at every registered frontier point.  Their
training multiply-add counts are also equal: the conditional arm receives twice
as many epochs because each example updates only one conditional head.  The
factorized diagnostic uses twice the feature width, which equalises its total
parameter and compute budget while preserving its no-cross-cell restriction.

This is deliberately a D0 development falsifier.  It does not measure owner-memory
contamination, recovery, safety, privacy, ProcTHOR performance, or D2 PCT.  A
positive result can justify integration into the full-system guardrail experiment;
it can never rewrite Task-8 v0.4 or authorize a paper claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from .structure_two_backbone_falsifier import (
    ACTORS,
    CAUSES,
    INSTANCES,
    MECHANISMS,
    PLACEMENT_BINS,
    TASK8_HANDOFF_ACTOR_SEVERITY,
    TASK8_REGIME_HABIT_SEVERITY,
    TASK8_VERIFY_COST,
    BackboneScenario,
    Cause,
    Mechanism,
    RegimeMove,
    registered_scenarios,
)

PROTOCOL_ID: Final = "structure-two-task8-learned-online-compute@0.1-development"
ARM_JOINT: Final = "learned_joint"
ARM_TWO_STAGE: Final = "learned_matched_two_stage"
ARM_FACTORIZED: Final = "information_restricted_factorized"
ARM_ORDER: Final = (ARM_JOINT, ARM_TWO_STAGE, ARM_FACTORIZED)
CAUSE_GROUPS: Final = ("actor", "habit", "other")
EVENT_GROUPS: Final = ("handoff_stay", "regime_change", "other")
JOINT_CLASS_COUNT: Final = len(CAUSE_GROUPS) * len(EVENT_GROUPS)
FREE_JOINT_LOGITS: Final = JOINT_CLASS_COUNT - 1
BASE_EPOCHS: Final = 60
BOOTSTRAP_REPLICATES: Final = 10_000
BOOTSTRAP_SEED: Final = "task8-online-compute-v0.1-20260907"
FAMILY_ALPHA: Final = 0.05

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def content_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _one_hot(value: object, support: Sequence[object]) -> list[float]:
    return [1.0 if value == candidate else 0.0 for candidate in support]


def _raw_features(scenario: BackboneScenario) -> tuple[float, ...]:
    """Robot-visible features only; scenario flags and latent truth are excluded."""

    values: list[float] = []
    for observation in scenario.observations:
        values.extend(_one_hot(observation.observed_mechanism, MECHANISMS))
        values.extend(_one_hot(observation.observed_giver, ACTORS))
        values.extend(_one_hot(observation.observed_receiver, ACTORS))
        values.extend(_one_hot(observation.observed_instance, INSTANCES))
        values.extend(_one_hot(observation.observed_cause, CAUSES))
        values.extend([1.0 if observation.observed_regime_change else 0.0])
        values.extend(_one_hot(observation.placement_bin, tuple(range(PLACEMENT_BINS))))
        values.extend(
            [
                observation.placement_value,
                observation.mechanism_reliability,
                observation.actor_reliability,
                observation.instance_reliability,
                observation.cause_reliability,
                observation.regime_reliability,
            ]
        )
    return tuple(values)


def _cause_group(cause: Cause) -> int:
    if cause is Cause.ACTOR:
        return 0
    if cause is Cause.HABIT:
        return 1
    return 2


def _event_group(mechanism: Mechanism, move: RegimeMove) -> int:
    if mechanism is Mechanism.HANDOFF and move in {RegimeMove.STAY, RegimeMove.UNRESOLVED}:
        return 0
    if move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}:
        return 1
    return 2


def _labels_and_truth_severity(scenario: BackboneScenario) -> tuple[int, int, float]:
    gap = scenario.truth.gaps[scenario.corrupt_index]
    cause = _cause_group(gap.cause)
    event = _event_group(gap.mechanism, gap.regime_move)
    severity = 0.0
    if cause == 0 and event == 0:
        severity = TASK8_HANDOFF_ACTOR_SEVERITY
    elif cause == 1 and event == 1:
        severity = TASK8_REGIME_HABIT_SEVERITY
    return cause, event, severity


@dataclass(frozen=True, slots=True)
class _Example:
    unit_id: str
    cluster_seed: int
    high_attribution_ambiguity: bool
    adverse_delayed_feedback: bool
    open_world_actor: bool
    raw_features: tuple[float, ...]
    cause: int
    event: int
    truth_severity: float


def _examples(seeds: Sequence[int], *, gaps: int) -> tuple[_Example, ...]:
    output: list[_Example] = []
    for cluster_seed in seeds:
        for scenario in registered_scenarios(
            gaps,
            (int(cluster_seed),),
            relative_probability_coupling_nats=1.5,
            relative_probability_truth_model=True,
        ):
            cause, event, severity = _labels_and_truth_severity(scenario)
            output.append(
                _Example(
                    unit_id=scenario.scenario_id,
                    cluster_seed=int(cluster_seed),
                    high_attribution_ambiguity=scenario.high_attribution_ambiguity,
                    adverse_delayed_feedback=scenario.adverse_delayed_feedback,
                    open_world_actor=scenario.open_world_actor,
                    raw_features=_raw_features(scenario),
                    cause=cause,
                    event=event,
                    truth_severity=severity,
                )
            )
    return tuple(output)


def _hashed_projection(raw: FloatArray, width: int) -> FloatArray:
    if width < 2:
        raise ValueError("Task-8 projected feature width must include data and bias")
    projected = np.zeros((raw.shape[0], width - 1), dtype=np.float64)
    for index in range(raw.shape[1]):
        bucket = (index * 17 + 3) % (width - 1)
        sign = 1.0 if (index * 37 + 11) % 2 else -1.0
        projected[:, bucket] += sign * raw[:, index]
    projected /= math.sqrt(max(1, raw.shape[1] / (width - 1)))
    return projected


@dataclass(frozen=True, slots=True)
class _Projection:
    width: int
    mean: FloatArray
    scale: FloatArray

    @classmethod
    def fit(cls, raw: FloatArray, width: int) -> _Projection:
        projected = _hashed_projection(raw, width)
        mean = projected.mean(axis=0)
        scale = projected.std(axis=0)
        scale = np.where(scale < 1e-9, 1.0, scale)
        return cls(width=width, mean=mean, scale=scale)

    def transform(self, raw: FloatArray) -> FloatArray:
        projected = (_hashed_projection(raw, self.width) - self.mean) / self.scale
        return np.concatenate(
            [projected, np.ones((projected.shape[0], 1), dtype=np.float64)], axis=1
        )


def _softmax_reference(logits_without_reference: FloatArray) -> FloatArray:
    logits = np.concatenate(
        [
            logits_without_reference,
            np.zeros((logits_without_reference.shape[0], 1), dtype=np.float64),
        ],
        axis=1,
    )
    logits -= logits.max(axis=1, keepdims=True)
    exponential = np.exp(logits)
    return exponential / exponential.sum(axis=1, keepdims=True)


def _fit_multinomial(
    features: FloatArray,
    labels: IntArray,
    *,
    classes: int,
    epochs: int,
    learning_rate: float,
    l2: float,
) -> FloatArray:
    if features.shape[0] != labels.shape[0] or features.shape[0] == 0:
        raise ValueError("Task-8 training rows and labels must be non-empty and aligned")
    weights = np.zeros((features.shape[1], classes - 1), dtype=np.float64)
    target = np.zeros((features.shape[0], classes - 1), dtype=np.float64)
    for row, label in enumerate(labels.tolist()):
        if not 0 <= label < classes:
            raise ValueError("Task-8 label lies outside the registered class support")
        if label < classes - 1:
            target[row, label] = 1.0
    for _ in range(epochs):
        probabilities = _softmax_reference(features @ weights)
        gradient = features.T @ (probabilities[:, : classes - 1] - target)
        gradient /= features.shape[0]
        gradient += l2 * weights
        weights -= learning_rate * gradient
    return weights


@dataclass(frozen=True, slots=True)
class _LearnedModel:
    arm: str
    projection: _Projection
    weights: tuple[FloatArray, ...]
    active_parameter_count: int
    training_multiply_adds: int
    inference_multiply_adds_per_unit: int

    def predict_joint(self, raw: FloatArray) -> FloatArray:
        features = self.projection.transform(raw)
        if self.arm == ARM_JOINT:
            return _softmax_reference(features @ self.weights[0])
        if self.arm == ARM_TWO_STAGE:
            cause_probability = _softmax_reference(features @ self.weights[0])
            conditionals = [
                _softmax_reference(features @ conditional) for conditional in self.weights[1:]
            ]
            output = np.zeros((features.shape[0], JOINT_CLASS_COUNT), dtype=np.float64)
            for cause in range(len(CAUSE_GROUPS)):
                for event in range(len(EVENT_GROUPS)):
                    output[:, cause * len(EVENT_GROUPS) + event] = (
                        cause_probability[:, cause] * conditionals[cause][:, event]
                    )
            return output
        if self.arm == ARM_FACTORIZED:
            cause_probability = _softmax_reference(features @ self.weights[0])
            event_probability = _softmax_reference(features @ self.weights[1])
            return np.einsum("ni,nj->nij", cause_probability, event_probability).reshape(
                features.shape[0], JOINT_CLASS_COUNT
            )
        raise ValueError(f"unknown Task-8 arm {self.arm}")


def _fit_arm(
    arm: str,
    raw: FloatArray,
    cause_labels: IntArray,
    event_labels: IntArray,
    *,
    base_width: int,
    learning_rate: float,
    l2: float,
) -> _LearnedModel:
    if arm not in ARM_ORDER:
        raise ValueError(f"unknown Task-8 arm {arm}")
    projection_width = base_width * 2 if arm == ARM_FACTORIZED else base_width
    projection = _Projection.fit(raw, projection_width)
    features = projection.transform(raw)
    joint_labels = cause_labels * len(EVENT_GROUPS) + event_labels
    if arm == ARM_JOINT:
        weights = (
            _fit_multinomial(
                features,
                joint_labels,
                classes=JOINT_CLASS_COUNT,
                epochs=BASE_EPOCHS,
                learning_rate=learning_rate,
                l2=l2,
            ),
        )
        training_multiply_adds = raw.shape[0] * base_width * 8 * BASE_EPOCHS
    elif arm == ARM_TWO_STAGE:
        cause_weights = _fit_multinomial(
            features,
            cause_labels,
            classes=len(CAUSE_GROUPS),
            epochs=BASE_EPOCHS * 2,
            learning_rate=learning_rate,
            l2=l2,
        )
        conditional_weights: list[FloatArray] = []
        for cause in range(len(CAUSE_GROUPS)):
            mask = cause_labels == cause
            conditional_weights.append(
                _fit_multinomial(
                    features[mask],
                    event_labels[mask],
                    classes=len(EVENT_GROUPS),
                    epochs=BASE_EPOCHS * 2,
                    learning_rate=learning_rate,
                    l2=l2,
                )
            )
        weights = (cause_weights, *conditional_weights)
        training_multiply_adds = raw.shape[0] * base_width * 8 * BASE_EPOCHS
    else:
        weights = (
            _fit_multinomial(
                features,
                cause_labels,
                classes=len(CAUSE_GROUPS),
                epochs=BASE_EPOCHS,
                learning_rate=learning_rate,
                l2=l2,
            ),
            _fit_multinomial(
                features,
                event_labels,
                classes=len(EVENT_GROUPS),
                epochs=BASE_EPOCHS,
                learning_rate=learning_rate,
                l2=l2,
            ),
        )
        training_multiply_adds = raw.shape[0] * base_width * 8 * BASE_EPOCHS
    active_parameters = sum(weight.size for weight in weights)
    expected_parameters = base_width * 8
    if active_parameters != expected_parameters:
        raise AssertionError("Task-8 arms do not have an exactly matched active parameter count")
    return _LearnedModel(
        arm=arm,
        projection=projection,
        weights=tuple(weights),
        active_parameter_count=active_parameters,
        training_multiply_adds=training_multiply_adds,
        inference_multiply_adds_per_unit=expected_parameters,
    )


def _matrix(examples: Sequence[_Example]) -> tuple[FloatArray, IntArray, IntArray]:
    raw = np.asarray([item.raw_features for item in examples], dtype=np.float64)
    cause = np.asarray([item.cause for item in examples], dtype=np.int64)
    event = np.asarray([item.event for item in examples], dtype=np.int64)
    return raw, cause, event


def _prediction_rows(
    model: _LearnedModel,
    examples: Sequence[_Example],
    raw: FloatArray,
) -> list[dict[str, Any]]:
    joint = model.predict_joint(raw)
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(examples):
        probabilities = joint[index]
        verify_probability = (
            probabilities[0 * len(EVENT_GROUPS) + 0] * TASK8_HANDOFF_ACTOR_SEVERITY
            + probabilities[1 * len(EVENT_GROUPS) + 1] * TASK8_REGIME_HABIT_SEVERITY
        )
        verify_probability = min(1.0, max(0.0, float(verify_probability)))
        expected_cost = (
            verify_probability * TASK8_VERIFY_COST
            + (1.0 - verify_probability) * item.truth_severity
        )
        oracle_cost = min(TASK8_VERIFY_COST, item.truth_severity)
        rows.append(
            {
                "unit_id": item.unit_id,
                "cluster_seed": item.cluster_seed,
                "high_attribution_ambiguity": item.high_attribution_ambiguity,
                "adverse_delayed_feedback": item.adverse_delayed_feedback,
                "open_world_actor": item.open_world_actor,
                "arm": model.arm,
                "verify_probability": verify_probability,
                "selected_action": "verify" if verify_probability >= 0.5 else "proceed",
                "truth_severity": item.truth_severity,
                "consequential_expected_cost": expected_cost,
                "action_regret": expected_cost - oracle_cost,
                "truth_visible_to_arm": False,
            }
        )
    return rows


def _mean_cost(rows: Sequence[Mapping[str, Any]]) -> float:
    return sum(float(item["consequential_expected_cost"]) for item in rows) / len(rows)


def _freeze_validation_selection(
    candidates: Sequence[Mapping[str, Any]],
    *,
    budgets: Sequence[int],
    learning_rates: Sequence[float],
    l2_values: Sequence[float],
    validation_unit_ids: Sequence[str],
) -> dict[str, Any]:
    selections: dict[str, dict[str, Any]] = {}
    for base_width in budgets:
        for arm in ARM_ORDER:
            subset = [
                item
                for item in candidates
                if item["arm"] == arm and int(item["base_width"]) == base_width
            ]
            if len(subset) != len(learning_rates) * len(l2_values):
                raise AssertionError("Task-8 validation candidate grid is incomplete")
            selected = min(
                subset,
                key=lambda item: (
                    float(item["validation_mean_cost"]),
                    float(item["l2"]),
                    float(item["learning_rate"]),
                ),
            )
            selections[f"width={base_width}|arm={arm}"] = dict(selected)
    unsigned = {
        "receipt_type": "task8-online-compute-validation-selection@0.1",
        "protocol_id": PROTOCOL_ID,
        "validation_unit_ids": list(validation_unit_ids),
        "base_widths": list(budgets),
        "learning_rates": list(learning_rates),
        "l2_values": list(l2_values),
        "selection_rule": "minimum validation mean consequential cost with frozen tie break",
        "confirmatory_data_read_before_freeze": False,
        "selections": selections,
    }
    return {**unsigned, "content_sha256": content_sha256(unsigned)}


def _bootstrap_lower_bound(
    differences: Sequence[float], *, confidence: float, seed_suffix: str
) -> float:
    if not differences or any(not math.isfinite(value) for value in differences):
        raise ValueError("Task-8 paired cluster differences must be finite and non-empty")
    rng = random.Random(f"{BOOTSTRAP_SEED}:{seed_suffix}")
    size = len(differences)
    means = sorted(
        sum(differences[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(BOOTSTRAP_REPLICATES)
    )
    index = max(0, min(len(means) - 1, math.floor((1.0 - confidence) * len(means))))
    return means[index]


def run_task8_online_compute_study(
    *,
    gaps: int,
    training_seeds: Sequence[int],
    validation_seeds: Sequence[int],
    confirmatory_seeds: Sequence[int],
    base_widths: Sequence[int],
    learning_rates: Sequence[float],
    l2_values: Sequence[float],
    minimum_relative_improvement: float,
) -> dict[str, Any]:
    """Run the frozen train/validation/confirmatory development study."""

    seed_sets = [
        tuple(int(seed) for seed in values)
        for values in (training_seeds, validation_seeds, confirmatory_seeds)
    ]
    if any(not values or len(set(values)) != len(values) for values in seed_sets):
        raise ValueError("Task-8 seed blocks must be non-empty and internally unique")
    if any(
        set(seed_sets[left]) & set(seed_sets[right])
        for left in range(3)
        for right in range(left + 1, 3)
    ):
        raise ValueError("Task-8 train, validation, and confirmatory seeds must be disjoint")
    widths = tuple(int(value) for value in base_widths)
    if not widths or len(set(widths)) != len(widths) or any(value < 2 for value in widths):
        raise ValueError("Task-8 base widths must be unique and at least two")
    if minimum_relative_improvement <= 0.0:
        raise ValueError("Task-8 relative improvement threshold must be positive")

    training_examples = _examples(seed_sets[0], gaps=gaps)
    validation_examples = _examples(seed_sets[1], gaps=gaps)
    training_raw, training_cause, training_event = _matrix(training_examples)
    validation_raw, _, _ = _matrix(validation_examples)

    candidate_rows: list[dict[str, Any]] = []
    for width in widths:
        for arm in ARM_ORDER:
            for learning_rate in learning_rates:
                for l2 in l2_values:
                    model = _fit_arm(
                        arm,
                        training_raw,
                        training_cause,
                        training_event,
                        base_width=width,
                        learning_rate=float(learning_rate),
                        l2=float(l2),
                    )
                    predictions = _prediction_rows(model, validation_examples, validation_raw)
                    candidate_rows.append(
                        {
                            "arm": arm,
                            "base_width": width,
                            "learning_rate": float(learning_rate),
                            "l2": float(l2),
                            "validation_mean_cost": _mean_cost(predictions),
                            "active_parameter_count": model.active_parameter_count,
                            "training_multiply_adds": model.training_multiply_adds,
                            "inference_multiply_adds_per_unit": (
                                model.inference_multiply_adds_per_unit
                            ),
                        }
                    )

    selection_receipt = _freeze_validation_selection(
        candidate_rows,
        budgets=widths,
        learning_rates=learning_rates,
        l2_values=l2_values,
        validation_unit_ids=[item.unit_id for item in validation_examples],
    )

    confirmatory_examples = _examples(seed_sets[2], gaps=gaps)
    confirmatory_raw, _, _ = _matrix(confirmatory_examples)
    confirmatory_rows: list[dict[str, Any]] = []
    budget_receipts: list[dict[str, Any]] = []
    selections = selection_receipt["selections"]
    assert isinstance(selections, Mapping)
    for width in widths:
        models: dict[str, _LearnedModel] = {}
        for arm in ARM_ORDER:
            selection = selections[f"width={width}|arm={arm}"]
            assert isinstance(selection, Mapping)
            model = _fit_arm(
                arm,
                training_raw,
                training_cause,
                training_event,
                base_width=width,
                learning_rate=float(selection["learning_rate"]),
                l2=float(selection["l2"]),
            )
            models[arm] = model
            rows = _prediction_rows(model, confirmatory_examples, confirmatory_raw)
            for row in rows:
                row["base_width"] = width
            confirmatory_rows.extend(rows)
        parameter_counts = {model.active_parameter_count for model in models.values()}
        training_counts = {model.training_multiply_adds for model in models.values()}
        inference_counts = {model.inference_multiply_adds_per_unit for model in models.values()}
        budget_receipts.append(
            {
                "base_width": width,
                "active_parameter_count_by_arm": {
                    arm: model.active_parameter_count for arm, model in models.items()
                },
                "training_multiply_adds_by_arm": {
                    arm: model.training_multiply_adds for arm, model in models.items()
                },
                "inference_multiply_adds_per_unit_by_arm": {
                    arm: model.inference_multiply_adds_per_unit for arm, model in models.items()
                },
                "exact_parameter_match": len(parameter_counts) == 1,
                "exact_training_compute_match": len(training_counts) == 1,
                "exact_inference_compute_match": len(inference_counts) == 1,
            }
        )

    confidence = 1.0 - FAMILY_ALPHA / len(widths)
    frontier: list[dict[str, Any]] = []
    for width in widths:
        width_rows = [item for item in confirmatory_rows if int(item["base_width"]) == width]
        by_key = {(str(item["unit_id"]), str(item["arm"])): item for item in width_rows}
        cluster_differences: list[float] = []
        cluster_factorized_differences: list[float] = []
        for cluster_seed in seed_sets[2]:
            units = [item for item in confirmatory_examples if item.cluster_seed == cluster_seed]
            cluster_differences.append(
                sum(
                    float(by_key[(unit.unit_id, ARM_TWO_STAGE)]["consequential_expected_cost"])
                    - float(by_key[(unit.unit_id, ARM_JOINT)]["consequential_expected_cost"])
                    for unit in units
                )
                / len(units)
            )
            cluster_factorized_differences.append(
                sum(
                    float(by_key[(unit.unit_id, ARM_FACTORIZED)]["consequential_expected_cost"])
                    - float(by_key[(unit.unit_id, ARM_JOINT)]["consequential_expected_cost"])
                    for unit in units
                )
                / len(units)
            )
        mean_joint = _mean_cost([item for item in width_rows if item["arm"] == ARM_JOINT])
        mean_two_stage = _mean_cost([item for item in width_rows if item["arm"] == ARM_TWO_STAGE])
        mean_factorized = _mean_cost([item for item in width_rows if item["arm"] == ARM_FACTORIZED])
        mean_difference = sum(cluster_differences) / len(cluster_differences)
        lower = _bootstrap_lower_bound(
            cluster_differences,
            confidence=confidence,
            seed_suffix=f"primary-width-{width}",
        )
        relative = mean_difference / max(abs(mean_two_stage), 1e-12)
        frontier.append(
            {
                "base_width": width,
                "active_parameter_count": width * 8,
                "training_multiply_adds_per_tuned_candidate": (
                    len(training_examples) * width * 8 * BASE_EPOCHS
                ),
                "inference_multiply_adds_per_unit": width * 8,
                "joint_mean_cost": mean_joint,
                "matched_two_stage_mean_cost": mean_two_stage,
                "information_restricted_factorized_mean_cost": mean_factorized,
                "matched_two_stage_minus_joint_mean": mean_difference,
                "matched_two_stage_minus_joint_lower_bound": lower,
                "family_adjusted_one_sided_confidence": confidence,
                "relative_improvement": relative,
                "joint_pareto_better_at_equal_compute": mean_difference > 0.0,
                "strict_development_signal": (
                    lower > 0.0 and relative >= minimum_relative_improvement
                ),
                "information_restriction_diagnostic_mean": (
                    sum(cluster_factorized_differences) / len(cluster_factorized_differences)
                ),
            }
        )

    shift_rows = [
        item
        for item in confirmatory_rows
        if item["high_attribution_ambiguity"]
        and item["adverse_delayed_feedback"]
        and item["open_world_actor"]
    ]
    shift_diagnostic = []
    for width in widths:
        subset = [item for item in shift_rows if int(item["base_width"]) == width]
        shift_diagnostic.append(
            {
                "base_width": width,
                "joint_mean_cost": _mean_cost(
                    [item for item in subset if item["arm"] == ARM_JOINT]
                ),
                "matched_two_stage_mean_cost": _mean_cost(
                    [item for item in subset if item["arm"] == ARM_TWO_STAGE]
                ),
                "secondary_axis_only": True,
            }
        )

    any_signal = any(item["strict_development_signal"] for item in frontier)
    fairness_passed = all(
        item["exact_parameter_match"]
        and item["exact_training_compute_match"]
        and item["exact_inference_compute_match"]
        for item in budget_receipts
    )
    return {
        "protocol_id": PROTOCOL_ID,
        "evidence_status": "D0_DEVELOPMENT_PRE_DEATH_TEST_ONLY",
        "historical_task8_v0_4_status": "IMMUTABLE_FAIL",
        "design": {
            "gaps": gaps,
            "training_seeds": list(seed_sets[0]),
            "validation_seeds": list(seed_sets[1]),
            "confirmatory_seeds": list(seed_sets[2]),
            "factor_cells_per_seed": 8,
            "base_widths": list(widths),
            "learning_rates": [float(value) for value in learning_rates],
            "l2_values": [float(value) for value in l2_values],
            "minimum_relative_improvement": minimum_relative_improvement,
            "familywise_alpha": FAMILY_ALPHA,
            "primary_axis": "online_compute",
            "secondary_axes": ["distribution_shift", "information_restriction"],
            "same_robot_visible_raw_input": True,
            "truth_visible_to_arm": False,
        },
        "model_contract": {
            "joint": "p(C_group,E_group|x)",
            "matched_two_stage": "p(C_group|x)*p(E_group|C_group,x)",
            "information_restricted": "p(C_group|x)*p(E_group|x)",
            "cause_groups": list(CAUSE_GROUPS),
            "event_groups": list(EVENT_GROUPS),
            "active_parameter_formula": "8*base_width for every arm",
            "training_compute_formula": "N_train*8*base_width*60 for every tuned candidate",
            "inference_compute_formula": "8*base_width multiply-adds per unit for every arm",
        },
        "selection_receipt": selection_receipt,
        "validation_candidate_rows": candidate_rows,
        "budget_fairness_receipts": budget_receipts,
        "fairness_gate_passed": fairness_passed,
        "confirmatory_rows": confirmatory_rows,
        "primary_online_compute_frontier": frontier,
        "distribution_shift_diagnostic": shift_diagnostic,
        "information_restriction_diagnostic_only": True,
        "any_strict_development_signal": any_signal and fairness_passed,
        "task_8_formal_passed": False,
        "full_system_guardrails_measured": False,
        "external_validity_established": False,
        "seven_operator_ablation_authorized": False,
        "next_disposition": (
            "PROCEED_TO_FULL_SYSTEM_GUARDRAIL_INTEGRATION_BEFORE_EXTERNAL_SCALEUP"
            if any_signal and fairness_passed
            else "DEFAULT_METHOD_REDESIGN_BEFORE_EXPENSIVE_EXTERNAL_SCALEUP"
        ),
        "claim_boundary": (
            "This reduced D0 learned-inference study is the cheapest online-compute falsifier. "
            "A positive signal cannot pass Task 8 because owner contamination, recovery, safety, "
            "privacy, D1/D2 PCT, native baselines, and independent custody are not measured. A "
            "negative result supports redesigning the joint mechanism while retaining the full "
            "seven-operator Structure-Two scope."
        ),
    }


def _require_close(actual: object, expected: float, *, field: str) -> None:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        raise ValueError(f"Task-8 {field} must be numeric")
    if not math.isfinite(float(actual)) or not math.isclose(
        float(actual), expected, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValueError(f"Task-8 {field} is not derived from registered evidence")


def _verify_validation_selection(
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    training_count: int,
    validation_unit_ids: Sequence[str],
) -> None:
    candidates = result.get("validation_candidate_rows")
    if not isinstance(candidates, list):
        raise ValueError("Task-8 validation candidate rows are missing")
    expected_keys = {
        (arm, int(width), float(learning_rate), float(l2))
        for width in config["base_widths"]
        for arm in ARM_ORDER
        for learning_rate in config["learning_rates"]
        for l2 in config["l2_values"]
    }
    keyed_candidates: dict[tuple[str, int, float, float], Mapping[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, Mapping):
            raise ValueError("Task-8 validation candidate row is malformed")
        key = (
            str(item.get("arm")),
            int(item.get("base_width", -1)),
            float(item.get("learning_rate", math.nan)),
            float(item.get("l2", math.nan)),
        )
        if key in keyed_candidates:
            raise ValueError("Task-8 validation candidate grid contains duplicates")
        keyed_candidates[key] = item
        width = key[1]
        expected_budget = width * FREE_JOINT_LOGITS
        expected_training = training_count * expected_budget * BASE_EPOCHS
        _require_close(
            item.get("validation_mean_cost"),
            float(item.get("validation_mean_cost", math.nan)),
            field="validation mean cost",
        )
        if item.get("active_parameter_count") != expected_budget:
            raise ValueError("Task-8 validation parameter budget is not matched")
        if item.get("training_multiply_adds") != expected_training:
            raise ValueError("Task-8 validation training-compute budget is not matched")
        if item.get("inference_multiply_adds_per_unit") != expected_budget:
            raise ValueError("Task-8 validation inference-compute budget is not matched")
    if set(keyed_candidates) != expected_keys:
        raise ValueError("Task-8 validation candidate grid is incomplete or substituted")

    receipt = result.get("selection_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("Task-8 validation selection receipt is missing")
    unsigned_receipt = dict(receipt)
    stored_receipt_hash = unsigned_receipt.pop("content_sha256", None)
    if stored_receipt_hash != content_sha256(unsigned_receipt):
        raise ValueError("Task-8 validation selection receipt hash mismatch")
    if receipt.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Task-8 validation receipt protocol substitution")
    if receipt.get("validation_unit_ids") != list(validation_unit_ids):
        raise ValueError("Task-8 validation receipt does not bind the registered units")
    if receipt.get("confirmatory_data_read_before_freeze") is not False:
        raise ValueError("Task-8 selection was not frozen before confirmation")
    selections = receipt.get("selections")
    if not isinstance(selections, Mapping):
        raise ValueError("Task-8 frozen selections are missing")
    expected_selection_keys = {
        f"width={width}|arm={arm}" for width in config["base_widths"] for arm in ARM_ORDER
    }
    if set(selections) != expected_selection_keys:
        raise ValueError("Task-8 frozen selection coverage is incomplete")
    for width in config["base_widths"]:
        for arm in ARM_ORDER:
            subset = [
                item
                for key, item in keyed_candidates.items()
                if key[0] == arm and key[1] == int(width)
            ]
            expected = min(
                subset,
                key=lambda item: (
                    float(item["validation_mean_cost"]),
                    float(item["l2"]),
                    float(item["learning_rate"]),
                ),
            )
            if selections[f"width={width}|arm={arm}"] != expected:
                raise ValueError("Task-8 frozen selection is not the registered validation winner")


def _verify_budget_receipts(
    result: Mapping[str, Any], config: Mapping[str, Any], *, training_count: int
) -> bool:
    fairness = result.get("budget_fairness_receipts")
    if not isinstance(fairness, list):
        raise ValueError("Task-8 budget fairness receipts are missing")
    keyed: dict[int, Mapping[str, Any]] = {}
    for item in fairness:
        if not isinstance(item, Mapping):
            raise ValueError("Task-8 budget fairness receipt is malformed")
        width = int(item.get("base_width", -1))
        if width in keyed:
            raise ValueError("Task-8 budget fairness receipts contain duplicate widths")
        keyed[width] = item
        expected_parameters = width * FREE_JOINT_LOGITS
        expected_training = training_count * expected_parameters * BASE_EPOCHS
        expected_parameter_map = {arm: expected_parameters for arm in ARM_ORDER}
        expected_training_map = {arm: expected_training for arm in ARM_ORDER}
        if item.get("active_parameter_count_by_arm") != expected_parameter_map:
            raise ValueError("Task-8 per-arm parameter counts are not exactly matched")
        if item.get("training_multiply_adds_by_arm") != expected_training_map:
            raise ValueError("Task-8 per-arm training compute is not exactly matched")
        if item.get("inference_multiply_adds_per_unit_by_arm") != expected_parameter_map:
            raise ValueError("Task-8 per-arm inference compute is not exactly matched")
        if any(
            item.get(field) is not True
            for field in (
                "exact_parameter_match",
                "exact_training_compute_match",
                "exact_inference_compute_match",
            )
        ):
            raise ValueError("Task-8 fairness receipt contradicts its budget maps")
    if set(keyed) != {int(width) for width in config["base_widths"]}:
        raise ValueError("Task-8 budget fairness coverage is incomplete")
    return True


def _verify_confirmatory_rows(
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    examples: Sequence[_Example],
) -> dict[tuple[int, str, str], Mapping[str, Any]]:
    rows = result.get("confirmatory_rows")
    if not isinstance(rows, list):
        raise ValueError("Task-8 confirmatory rows are missing")
    example_by_id = {item.unit_id: item for item in examples}
    expected_keys = {
        (int(width), item.unit_id, arm)
        for width in config["base_widths"]
        for item in examples
        for arm in ARM_ORDER
    }
    keyed: dict[tuple[int, str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Task-8 confirmatory row is malformed")
        key = (
            int(row.get("base_width", -1)),
            str(row.get("unit_id")),
            str(row.get("arm")),
        )
        if key in keyed:
            raise ValueError("Task-8 confirmatory rows contain duplicate units")
        keyed[key] = row
        example = example_by_id.get(key[1])
        if example is None:
            raise ValueError("Task-8 confirmatory row uses an unregistered unit")
        if row.get("cluster_seed") != example.cluster_seed:
            raise ValueError("Task-8 confirmatory cluster binding is invalid")
        for field in (
            "high_attribution_ambiguity",
            "adverse_delayed_feedback",
            "open_world_actor",
        ):
            if row.get(field) is not getattr(example, field):
                raise ValueError("Task-8 confirmatory factor binding is invalid")
        _require_close(row.get("truth_severity"), example.truth_severity, field="truth severity")
        probability = row.get("verify_probability")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError("Task-8 verification probability must be numeric")
        probability = float(probability)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("Task-8 verification probability is outside [0,1]")
        expected_action = "verify" if probability >= 0.5 else "proceed"
        if row.get("selected_action") != expected_action:
            raise ValueError("Task-8 action is not derived from its probability")
        expected_cost = (
            probability * TASK8_VERIFY_COST + (1.0 - probability) * example.truth_severity
        )
        _require_close(row.get("consequential_expected_cost"), expected_cost, field="expected cost")
        expected_oracle = min(TASK8_VERIFY_COST, example.truth_severity)
        _require_close(
            row.get("action_regret"), expected_cost - expected_oracle, field="action regret"
        )
        if row.get("truth_visible_to_arm") is not False:
            raise ValueError("Task-8 learned arm cannot receive confirmatory truth")
    if set(keyed) != expected_keys:
        raise ValueError("Task-8 confirmatory coverage is incomplete or substituted")
    return keyed


def _verify_frontier(
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    examples: Sequence[_Example],
    rows: Mapping[tuple[int, str, str], Mapping[str, Any]],
    *,
    training_count: int,
) -> bool:
    frontier = result.get("primary_online_compute_frontier")
    if not isinstance(frontier, list):
        raise ValueError("Task-8 online-compute frontier is missing")
    keyed_frontier: dict[int, Mapping[str, Any]] = {}
    confidence = 1.0 - FAMILY_ALPHA / len(config["base_widths"])
    threshold = float(config["minimum_relative_improvement"])
    any_signal = False
    for item in frontier:
        if not isinstance(item, Mapping):
            raise ValueError("Task-8 online-compute frontier row is malformed")
        width = int(item.get("base_width", -1))
        if width in keyed_frontier:
            raise ValueError("Task-8 online-compute frontier contains duplicate widths")
        keyed_frontier[width] = item
        arm_costs = {
            arm: [
                float(rows[(width, example.unit_id, arm)]["consequential_expected_cost"])
                for example in examples
            ]
            for arm in ARM_ORDER
        }
        means = {arm: sum(values) / len(values) for arm, values in arm_costs.items()}
        cluster_differences: list[float] = []
        factorized_differences: list[float] = []
        for seed in config["confirmatory_seeds"]:
            units = [example for example in examples if example.cluster_seed == int(seed)]
            cluster_differences.append(
                sum(
                    float(rows[(width, unit.unit_id, ARM_TWO_STAGE)]["consequential_expected_cost"])
                    - float(rows[(width, unit.unit_id, ARM_JOINT)]["consequential_expected_cost"])
                    for unit in units
                )
                / len(units)
            )
            factorized_differences.append(
                sum(
                    float(
                        rows[(width, unit.unit_id, ARM_FACTORIZED)]["consequential_expected_cost"]
                    )
                    - float(rows[(width, unit.unit_id, ARM_JOINT)]["consequential_expected_cost"])
                    for unit in units
                )
                / len(units)
            )
        mean_difference = sum(cluster_differences) / len(cluster_differences)
        lower = _bootstrap_lower_bound(
            cluster_differences,
            confidence=confidence,
            seed_suffix=f"primary-width-{width}",
        )
        relative = mean_difference / max(abs(means[ARM_TWO_STAGE]), 1e-12)
        signal = lower > 0.0 and relative >= threshold
        expected_budget = width * FREE_JOINT_LOGITS
        expected_values = {
            "active_parameter_count": expected_budget,
            "training_multiply_adds_per_tuned_candidate": (
                training_count * expected_budget * BASE_EPOCHS
            ),
            "inference_multiply_adds_per_unit": expected_budget,
            "joint_mean_cost": means[ARM_JOINT],
            "matched_two_stage_mean_cost": means[ARM_TWO_STAGE],
            "information_restricted_factorized_mean_cost": means[ARM_FACTORIZED],
            "matched_two_stage_minus_joint_mean": mean_difference,
            "matched_two_stage_minus_joint_lower_bound": lower,
            "family_adjusted_one_sided_confidence": confidence,
            "relative_improvement": relative,
            "information_restriction_diagnostic_mean": (
                sum(factorized_differences) / len(factorized_differences)
            ),
        }
        for field, expected in expected_values.items():
            _require_close(item.get(field), expected, field=field)
        if item.get("joint_pareto_better_at_equal_compute") is not (mean_difference > 0.0):
            raise ValueError("Task-8 Pareto verdict is not derived from confirmatory rows")
        if item.get("strict_development_signal") is not signal:
            raise ValueError("Task-8 strict signal is not derived from confirmatory rows")
        any_signal = any_signal or signal
    if set(keyed_frontier) != {int(width) for width in config["base_widths"]}:
        raise ValueError("Task-8 online-compute frontier coverage is incomplete")
    return any_signal


def _verify_shift_diagnostic(
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    examples: Sequence[_Example],
    rows: Mapping[tuple[int, str, str], Mapping[str, Any]],
) -> None:
    diagnostics = result.get("distribution_shift_diagnostic")
    if not isinstance(diagnostics, list):
        raise ValueError("Task-8 distribution-shift diagnostic is missing")
    keyed: dict[int, Mapping[str, Any]] = {}
    shifted = [
        item
        for item in examples
        if item.high_attribution_ambiguity
        and item.adverse_delayed_feedback
        and item.open_world_actor
    ]
    if not shifted:
        raise ValueError("Task-8 registered shift cell is empty")
    for item in diagnostics:
        if not isinstance(item, Mapping):
            raise ValueError("Task-8 distribution-shift row is malformed")
        width = int(item.get("base_width", -1))
        if width in keyed:
            raise ValueError("Task-8 distribution-shift rows contain duplicate widths")
        keyed[width] = item
        for arm, field in (
            (ARM_JOINT, "joint_mean_cost"),
            (ARM_TWO_STAGE, "matched_two_stage_mean_cost"),
        ):
            values = [
                float(rows[(width, example.unit_id, arm)]["consequential_expected_cost"])
                for example in shifted
            ]
            _require_close(item.get(field), sum(values) / len(values), field=field)
        if item.get("secondary_axis_only") is not True:
            raise ValueError("Task-8 shift diagnostic cannot become the primary axis")
    if set(keyed) != {int(width) for width in config["base_widths"]}:
        raise ValueError("Task-8 distribution-shift coverage is incomplete")


def verify_result(result: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    """Recompute every consequential positive output from registered unit rows."""

    if result.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("Task-8 online-compute protocol substitution")
    if result.get("evidence_status") != "D0_DEVELOPMENT_PRE_DEATH_TEST_ONLY":
        raise ValueError("Task-8 evidence tier was overstated")
    if result.get("historical_task8_v0_4_status") != "IMMUTABLE_FAIL":
        raise ValueError("Task-8 historical failure was rewritten")
    design = result.get("design")
    if not isinstance(design, Mapping):
        raise ValueError("Task-8 design is missing")
    expected_design = {
        "gaps": config["gaps"],
        "training_seeds": config["training_seeds"],
        "validation_seeds": config["validation_seeds"],
        "confirmatory_seeds": config["confirmatory_seeds"],
        "base_widths": config["base_widths"],
        "learning_rates": config["learning_rates"],
        "l2_values": config["l2_values"],
        "minimum_relative_improvement": config["minimum_relative_improvement"],
    }
    if any(design.get(key) != value for key, value in expected_design.items()):
        raise ValueError("Task-8 result does not match the frozen design")
    expected_static_design = {
        "primary_axis": "online_compute",
        "secondary_axes": ["distribution_shift", "information_restriction"],
        "same_robot_visible_raw_input": True,
        "truth_visible_to_arm": False,
        "familywise_alpha": FAMILY_ALPHA,
    }
    if any(design.get(key) != value for key, value in expected_static_design.items()):
        raise ValueError("Task-8 result substituted a registered design boundary")

    seed_sets = [
        tuple(int(seed) for seed in config[field])
        for field in ("training_seeds", "validation_seeds", "confirmatory_seeds")
    ]
    if any(not values or len(values) != len(set(values)) for values in seed_sets):
        raise ValueError("Task-8 frozen seed blocks are malformed")
    if any(
        set(seed_sets[left]) & set(seed_sets[right])
        for left in range(3)
        for right in range(left + 1, 3)
    ):
        raise ValueError("Task-8 frozen seed blocks are not disjoint")
    training_examples = _examples(seed_sets[0], gaps=int(config["gaps"]))
    validation_examples = _examples(seed_sets[1], gaps=int(config["gaps"]))
    confirmatory_examples = _examples(seed_sets[2], gaps=int(config["gaps"]))
    factor_cells = len(training_examples) // len(seed_sets[0])
    if design.get("factor_cells_per_seed") != factor_cells:
        raise ValueError("Task-8 factor-cell coverage is not derived from the registered suite")

    _verify_validation_selection(
        result,
        config,
        training_count=len(training_examples),
        validation_unit_ids=[item.unit_id for item in validation_examples],
    )
    fairness_passed = _verify_budget_receipts(result, config, training_count=len(training_examples))
    if result.get("fairness_gate_passed") is not fairness_passed:
        raise ValueError("Task-8 fairness verdict is not derived from receipts")
    confirmatory_rows = _verify_confirmatory_rows(result, config, confirmatory_examples)
    any_signal = _verify_frontier(
        result,
        config,
        confirmatory_examples,
        confirmatory_rows,
        training_count=len(training_examples),
    )
    _verify_shift_diagnostic(result, config, confirmatory_examples, confirmatory_rows)
    expected_signal = fairness_passed and any_signal
    if result.get("any_strict_development_signal") is not expected_signal:
        raise ValueError("Task-8 development signal is not derived from the frontier")
    if result.get("information_restriction_diagnostic_only") is not True:
        raise ValueError("Task-8 information-restricted arm cannot become a claim arm")
    expected_disposition = (
        "PROCEED_TO_FULL_SYSTEM_GUARDRAIL_INTEGRATION_BEFORE_EXTERNAL_SCALEUP"
        if expected_signal
        else "DEFAULT_METHOD_REDESIGN_BEFORE_EXPENSIVE_EXTERNAL_SCALEUP"
    )
    if result.get("next_disposition") != expected_disposition:
        raise ValueError("Task-8 disposition is not derived from the registered result")
    for forbidden_positive in (
        "task_8_formal_passed",
        "full_system_guardrails_measured",
        "external_validity_established",
        "seven_operator_ablation_authorized",
    ):
        if result.get(forbidden_positive) is not False:
            raise ValueError(f"Task-8 development result cannot assert {forbidden_positive}")


__all__ = [
    "ARM_FACTORIZED",
    "ARM_JOINT",
    "ARM_ORDER",
    "ARM_TWO_STAGE",
    "PROTOCOL_ID",
    "content_sha256",
    "run_task8_online_compute_study",
    "verify_result",
]
