"""Executable local diagnostics for Structure-Two Task 13 and proposal P5.

The routines exercise every preregistered arm with deterministic toy problems.
They intentionally cannot mint formal binding receipts: Task 10--12 resolutions,
the sealed holdout, and independent custody are external prerequisites.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.evaluation_operations.structure_two_backbone_open_task_protocols import (
    P5_ARMS,
    P5_STAGES,
    TASK13_STRATEGIES,
    DifferentiabilityStrategy,
    P5ArmGateOutcomes,
    P5ArmResult,
    P5Diagnosis,
    P5StageHeadroom,
    P5StageRecall,
    ParticleAxis,
    ProposalHeadroomArm,
    ProposalOperation,
    _compute_p5_summary,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-task13-p5-local-diagnostic@0.1"


class Task13GradientObservation(ContractModel):
    strategy: DifferentiabilityStrategy
    elementary_gradient_evaluations: int = Field(gt=0)
    estimated_gradient: tuple[float, float, float]
    exact_action_expectation_gradient: tuple[float, float, float]
    finite_difference_gradient: tuple[float, float, float]
    max_finite_difference_error: float = Field(ge=0.0, allow_inf_nan=False)
    max_exact_expectation_error: float = Field(ge=0.0, allow_inf_nan=False)
    gradient_bias_l2: float = Field(ge=0.0, allow_inf_nan=False)
    gradient_variance: float = Field(ge=0.0, allow_inf_nan=False)
    nonfinite_gradient_count: int = Field(ge=0)
    hard_constraint_violations: int = Field(ge=0)
    runtime_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Task13LocalDiagnostic(ContractModel):
    status: Literal["COMPLETED_LOCAL_DIAGNOSTIC_FORMAL_BLOCKED"]
    arms: tuple[Task13GradientObservation, ...] = Field(min_length=3, max_length=3)
    equal_compute_budget: bool
    runtime_strategy_trace_changes: bool
    sealed_holdout_available: Literal[False]
    formal_upstream_receipts_available: Literal[False]
    formal_binding_resolved: Literal[False]
    selected_strategy: None = None
    deterministic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    blockers: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _derive_local_only_decision(self) -> Task13LocalDiagnostic:
        if tuple(item.strategy for item in self.arms) != TASK13_STRATEGIES:
            raise ValueError("Task 13 local diagnostic must retain every strategy in order")
        equal_budget = len({item.elementary_gradient_evaluations for item in self.arms}) == 1
        trace_changes = len({item.runtime_trace_sha256 for item in self.arms}) == len(self.arms)
        digest = content_sha256(
            {
                "protocol": PROTOCOL_ID,
                "arms": self.arms,
                "sealed_holdout_available": False,
                "formal_upstream_receipts_available": False,
            }
        )
        if (self.equal_compute_budget, self.runtime_strategy_trace_changes) != (
            equal_budget,
            trace_changes,
        ):
            raise ValueError("Task 13 local gates were not derived from arm traces")
        if self.deterministic_sha256 != digest:
            raise ValueError("Task 13 local diagnostic hash mismatch")
        return self


class P5LocalDiagnostic(ContractModel):
    status: Literal["COMPLETED_LOCAL_DIAGNOSTIC_FORMAL_BLOCKED"]
    arm_results: tuple[P5ArmResult, ...] = Field(min_length=4, max_length=4)
    stage_headroom: tuple[P5StageHeadroom, ...] = Field(min_length=5, max_length=5)
    primary_estimand_value: float = Field(ge=0.0, le=1.0)
    oracle_action_gain: float = Field(allow_inf_nan=False)
    diagnosis: P5Diagnosis
    formal_upstream_receipts_available: Literal[False]
    binding_resolution_authorized: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    deterministic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    blockers: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _derive_diagnosis(self) -> P5LocalDiagnostic:
        expected = _compute_p5_summary(self.arm_results)
        if (
            self.stage_headroom,
            self.primary_estimand_value,
            self.oracle_action_gain,
            self.diagnosis,
        ) != expected:
            raise ValueError("P5 local diagnosis was not recomputed from all arm stages")
        digest = content_sha256(
            {
                "protocol": PROTOCOL_ID,
                "arm_results": self.arm_results,
                "stage_headroom": self.stage_headroom,
                "diagnosis": self.diagnosis,
                "formal_upstream_receipts_available": False,
            }
        )
        if self.deterministic_sha256 != digest:
            raise ValueError("P5 local diagnostic hash mismatch")
        return self


def _softmax(logits: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    shifted = logits - np.max(logits)
    values = np.exp(shifted)
    return np.asarray(values / values.sum(), dtype=np.float64)


def _expected_loss(
    logits: npt.NDArray[np.float64],
    losses: npt.NDArray[np.float64],
    temperature: float = 1.0,
) -> float:
    return float(_softmax(logits / temperature) @ losses)


def _finite_difference(
    logits: npt.NDArray[np.float64],
    losses: npt.NDArray[np.float64],
    *,
    temperature: float = 1.0,
) -> npt.NDArray[np.float64]:
    epsilon = 1e-6
    output = np.zeros_like(logits)
    for index in range(len(logits)):
        plus = logits.copy()
        minus = logits.copy()
        plus[index] += epsilon
        minus[index] -= epsilon
        output[index] = (
            _expected_loss(plus, losses, temperature) - _expected_loss(minus, losses, temperature)
        ) / (2.0 * epsilon)
    return output


def _task13_observation(strategy: DifferentiabilityStrategy) -> Task13GradientObservation:
    logits = np.array([0.2, -0.1, 0.0], dtype=float)
    losses = np.array([0.8, 0.2, 1.0], dtype=float)
    probabilities = _softmax(logits)
    expected = float(probabilities @ losses)
    exact = probabilities * (losses - expected)
    finite = _finite_difference(logits, losses)
    per_category = np.stack(
        [losses[index] * (np.eye(3)[index] - probabilities) for index in range(3)]
    )
    if strategy is DifferentiabilityStrategy.STOP_GRADIENT_SUPERVISED:
        estimate = probabilities - np.eye(3)[int(np.argmin(losses))]
        estimator_variance = 0.0
    elif strategy is DifferentiabilityStrategy.SCORE_FUNCTION_UNBIASED:
        estimate = probabilities @ per_category
        centered = per_category - estimate
        estimator_variance = float(probabilities @ np.sum(centered * centered, axis=1))
    else:
        temperature = 0.7
        relaxed = _softmax(logits / temperature)
        relaxed_expected = float(relaxed @ losses)
        estimate = relaxed * (losses - relaxed_expected) / temperature
        estimator_variance = 0.0
    trace = {
        "strategy": strategy,
        "logits": logits.tolist(),
        "losses": losses.tolist(),
        "estimate": estimate.tolist(),
    }
    return Task13GradientObservation(
        strategy=strategy,
        elementary_gradient_evaluations=3,
        estimated_gradient=tuple(float(value) for value in estimate),
        exact_action_expectation_gradient=tuple(float(value) for value in exact),
        finite_difference_gradient=tuple(float(value) for value in finite),
        max_finite_difference_error=float(np.max(np.abs(estimate - finite))),
        max_exact_expectation_error=float(np.max(np.abs(estimate - exact))),
        gradient_bias_l2=float(np.linalg.norm(estimate - exact)),
        gradient_variance=estimator_variance,
        nonfinite_gradient_count=int(np.count_nonzero(~np.isfinite(estimate))),
        hard_constraint_violations=int(abs(float(estimate.sum())) > 1e-10),
        runtime_trace_sha256=content_sha256(trace),
    )


def run_task13_local_diagnostic() -> Task13LocalDiagnostic:
    arms = tuple(_task13_observation(strategy) for strategy in TASK13_STRATEGIES)
    equal_budget = len({item.elementary_gradient_evaluations for item in arms}) == 1
    trace_changes = len({item.runtime_trace_sha256 for item in arms}) == len(arms)
    payload = {
        "protocol": PROTOCOL_ID,
        "arms": arms,
        "sealed_holdout_available": False,
        "formal_upstream_receipts_available": False,
    }
    return Task13LocalDiagnostic(
        status="COMPLETED_LOCAL_DIAGNOSTIC_FORMAL_BLOCKED",
        arms=arms,
        equal_compute_budget=equal_budget,
        runtime_strategy_trace_changes=trace_changes,
        sealed_holdout_available=False,
        formal_upstream_receipts_available=False,
        formal_binding_resolved=False,
        deterministic_sha256=content_sha256(payload),
        blockers=(
            "Task 10, Task 11, and Task 12 have no independently issued resolution receipts.",
            "No custodian-sealed holdout exists for Task 13 selection.",
        ),
    )


def _p5_ranked_candidates(arm: ProposalHeadroomArm, case_index: int) -> list[int]:
    truth = case_index % 6
    base = list(range(6))
    if arm is ProposalHeadroomArm.BOOTSTRAP:
        shift = (case_index * 2 + 1) % 6
        return base[shift:] + base[:shift]
    if arm is ProposalHeadroomArm.DETERMINISTIC_TYPED:
        visible_proxy = (case_index * 5 + 1) % 6

        def distance(value: int) -> tuple[int, int]:
            return abs(value - visible_proxy), value

        return sorted(base, key=distance)
    if arm is ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE:
        neighbor = (truth + 1) % 6
        return [truth, neighbor] + [value for value in base if value not in {truth, neighbor}]
    return [truth] + [value for value in base if value != truth]


def _p5_arm(arm: ProposalHeadroomArm) -> P5ArmResult:
    oracle = arm in {
        ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE,
        ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE,
    }
    successes = [0] * len(P5_STAGES)
    case_count = 12
    for case_index in range(case_count):
        truth = case_index % 6
        ranked = _p5_ranked_candidates(arm, case_index)
        stage_sets = (
            set(ranked[:4]),
            {value for value in ranked[:4] if value != 5 or truth == 5},
            set(ranked[:3]),
            set(ranked[:2]),
            set(ranked[:1]),
        )
        for stage_index, candidates in enumerate(stage_sets):
            successes[stage_index] += int(truth in candidates)
    recalls = tuple(value / case_count for value in successes)
    final_recall = recalls[-1]
    return P5ArmResult(
        arm=arm,
        stage_recall=tuple(
            P5StageRecall(stage=stage, full_chain_truth_compatible_recall=value)
            for stage, value in zip(P5_STAGES, recalls, strict=True)
        ),
        posterior_mass_coverage=final_recall,
        axis_recall={axis: final_recall for axis in ParticleAxis},
        operation_recall={operation: final_recall for operation in ProposalOperation},
        unknown_support_retention=1.0,
        unresolved_mass_retention=1.0,
        action_loss=1.0 - final_recall,
        elementary_evaluations=case_count * 6,
        truth_read_count=(case_count if oracle else 0),
        exact_enumeration_count=(case_count if oracle else 0),
        oracle_used=oracle,
        wall_clock_seconds=0.0,
        gates=P5ArmGateOutcomes(
            same_visible_input=True,
            fixed_nuisance_bindings=True,
            stage_accounting_complete=True,
            oracle_access_role_enforced=True,
            truth_reads_logged=True,
        ),
    )


def run_p5_local_diagnostic() -> P5LocalDiagnostic:
    arms = tuple(_p5_arm(arm) for arm in P5_ARMS)
    stage_headroom, primary, action_gain, diagnosis = _compute_p5_summary(arms)
    payload = {
        "protocol": PROTOCOL_ID,
        "arm_results": arms,
        "stage_headroom": stage_headroom,
        "diagnosis": diagnosis,
        "formal_upstream_receipts_available": False,
    }
    return P5LocalDiagnostic(
        status="COMPLETED_LOCAL_DIAGNOSTIC_FORMAL_BLOCKED",
        arm_results=arms,
        stage_headroom=stage_headroom,
        primary_estimand_value=primary,
        oracle_action_gain=action_gain,
        diagnosis=diagnosis,
        formal_upstream_receipts_available=False,
        binding_resolution_authorized=False,
        seven_operator_ablation_authorized=False,
        deterministic_sha256=content_sha256(payload),
        blockers=(
            "Task 10 through Task 12 formal resolution receipts are absent.",
            "The local categorical fixture is not a custodian-sealed confirmatory workload.",
        ),
    )


__all__ = [
    "PROTOCOL_ID",
    "P5LocalDiagnostic",
    "Task13GradientObservation",
    "Task13LocalDiagnostic",
    "run_p5_local_diagnostic",
    "run_task13_local_diagnostic",
]
