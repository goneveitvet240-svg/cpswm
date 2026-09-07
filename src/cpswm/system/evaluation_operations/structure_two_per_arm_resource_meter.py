"""Per-arm logical-budget and measured-resource receipts for Structure Two.

Timing and allocator peaks are deliberately kept out of the deterministic
fairness digest.  The receipt therefore proves both the exact replay/action
budget presented to each arm and records machine-local cost observations
without pretending that wall clock is byte-reproducible evidence.
"""

from __future__ import annotations

import json
import time
import tracemalloc
from collections.abc import Mapping
from statistics import mean
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.contracts.project_two_replay import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    FIDELITY,
    PARAMETER_SPACE,
    BenchmarkFidelity,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _visible_hash,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Literal["structure-two-per-arm-resource-meter@0.1"] = (
    "structure-two-per-arm-resource-meter@0.1"
)


class ArmLogicalBudgetReceipt(ContractModel):
    method: ProjectTwoActionMethod
    fidelity: BenchmarkFidelity
    episode_ids: tuple[UUID, ...] = Field(min_length=1)
    visible_input_sha256_by_episode: dict[UUID, str]
    visible_input_bytes: int = Field(gt=0)
    replay_step_count: int = Field(gt=0)
    observation_call_count: int = Field(gt=0)
    prediction_call_count: int = Field(gt=0)
    feedback_call_count: int = Field(gt=0)
    feedback_record_count: int = Field(ge=0)
    action_decision_count: int = Field(gt=0)
    action_budget_per_episode: int = Field(gt=0)
    tuning_search_points: int = Field(ge=0)
    evaluator_truth_access: bool
    output_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _logical_counts_are_closed(self) -> ArmLogicalBudgetReceipt:
        if set(self.visible_input_sha256_by_episode) != set(self.episode_ids):
            raise ValueError("logical budget omits or adds an episode input hash")
        if not (
            self.replay_step_count
            == self.observation_call_count
            == self.prediction_call_count
            == self.feedback_call_count
            == self.action_decision_count
        ):
            raise ValueError("logical observe/predict/feedback/action counts disagree")
        if self.evaluator_truth_access != (self.method is ProjectTwoActionMethod.ORACLE):
            raise ValueError("only the explicit oracle arm may record evaluator-truth access")
        return self


class ArmMeasuredResourceReceipt(ContractModel):
    method: ProjectTwoActionMethod
    measurement_scope: Literal["fresh_tracemalloc_window_same_process"] = (
        "fresh_tracemalloc_window_same_process"
    )
    wall_clock_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    process_cpu_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    peak_python_traced_bytes: int = Field(ge=0)
    mean_wall_clock_seconds_per_step: float = Field(ge=0.0, allow_inf_nan=False)
    mean_process_cpu_seconds_per_step: float = Field(ge=0.0, allow_inf_nan=False)


class PerArmResourceReport(ContractModel):
    protocol: Literal["structure-two-per-arm-resource-meter@0.1"] = PROTOCOL_ID
    dataset_version: str = Field(min_length=1)
    logical_receipts: tuple[ArmLogicalBudgetReceipt, ...] = Field(min_length=1)
    measured_receipts: tuple[ArmMeasuredResourceReceipt, ...] = Field(min_length=1)
    same_visible_inputs: bool
    same_replay_step_budget: bool
    same_action_budget: bool
    all_nonoracle_truth_isolated: bool
    all_native_reproductions_available: bool
    comparison_environment_ready_for_engineering: bool
    comparison_environment_ready_for_paper_claim: bool
    deterministic_fairness_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def _recompute_decisions(self) -> PerArmResourceReport:
        methods = tuple(ProjectTwoActionMethod)
        if tuple(item.method for item in self.logical_receipts) != methods:
            raise ValueError("logical resource receipts must cover every arm in enum order")
        if tuple(item.method for item in self.measured_receipts) != methods:
            raise ValueError("measured resource receipts must cover every arm in enum order")
        visible_sets = {
            tuple(
                sorted(
                    (str(key), value) for key, value in item.visible_input_sha256_by_episode.items()
                )
            )
            for item in self.logical_receipts
        }
        expected_visible = len(visible_sets) == 1
        expected_steps = len({item.replay_step_count for item in self.logical_receipts}) == 1
        expected_actions = (
            len(
                {
                    (item.action_decision_count, item.action_budget_per_episode)
                    for item in self.logical_receipts
                }
            )
            == 1
        )
        expected_truth = all(
            not item.evaluator_truth_access
            for item in self.logical_receipts
            if item.method is not ProjectTwoActionMethod.ORACLE
        )
        deterministic_payload = {
            "protocol": self.protocol,
            "dataset_version": self.dataset_version,
            "logical_receipts": self.logical_receipts,
        }
        expected_hash = content_sha256(deterministic_payload)
        if (
            self.same_visible_inputs,
            self.same_replay_step_budget,
            self.same_action_budget,
            self.all_nonoracle_truth_isolated,
            self.deterministic_fairness_sha256,
        ) != (expected_visible, expected_steps, expected_actions, expected_truth, expected_hash):
            raise ValueError("resource fairness decision is not derived from per-arm receipts")
        engineering_ready = (
            expected_visible and expected_steps and expected_actions and expected_truth
        )
        if self.comparison_environment_ready_for_engineering != engineering_ready:
            raise ValueError("engineering comparison readiness was not recomputed")
        paper_ready = engineering_ready and self.all_native_reproductions_available
        if self.comparison_environment_ready_for_paper_claim != paper_ready:
            raise ValueError("paper comparison readiness ignored native-reproduction status")
        return self


def _selected_parameters(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    method: ProjectTwoActionMethod,
) -> Mapping[str, Any]:
    if method is ProjectTwoActionMethod.ORACLE:
        return {}
    validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    scored = []
    for parameters in PARAMETER_SPACE[method]:
        values = [
            evaluator._evaluate_episode(
                dataset, episode, method, parameters
            ).cumulative_action_regret
            for episode in validation
        ]
        scored.append((mean(values), json.dumps(parameters, sort_keys=True), parameters))
    return min(scored, key=lambda item: (item[0], item[1]))[2]


def run_per_arm_resource_meter(
    dataset: ProjectTwoReplayDataset,
    *,
    all_native_reproductions_available: bool = False,
) -> PerArmResourceReport:
    evaluator = ProjectTwoActionBenchmarkV02()
    test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    if not test:
        raise ValueError("resource meter requires at least one test episode")
    visible_hashes = {episode.episode_id: _visible_hash(episode) for episode in test}
    visible_bytes = sum(
        len(json.dumps(episode.model_dump(mode="json"), sort_keys=True).encode("utf-8"))
        for episode in test
    )
    steps = sum(len(episode.steps) for episode in test)
    feedback_records = sum(
        len(step.execution_feedback) for episode in test for step in episode.steps
    )
    action_budget = max(len(episode.steps) for episode in test)
    logical: list[ArmLogicalBudgetReceipt] = []
    measured: list[ArmMeasuredResourceReceipt] = []
    for method in ProjectTwoActionMethod:
        parameters = _selected_parameters(evaluator, dataset, method)
        tracemalloc.start()
        cpu_start = time.process_time_ns()
        wall_start = time.perf_counter_ns()
        cases = [
            evaluator._evaluate_episode(dataset, episode, method, parameters) for episode in test
        ]
        wall_seconds = (time.perf_counter_ns() - wall_start) / 1_000_000_000
        cpu_seconds = (time.process_time_ns() - cpu_start) / 1_000_000_000
        _current, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        logical.append(
            ArmLogicalBudgetReceipt(
                method=method,
                fidelity=FIDELITY[method],
                episode_ids=tuple(episode.episode_id for episode in test),
                visible_input_sha256_by_episode=visible_hashes,
                visible_input_bytes=visible_bytes,
                replay_step_count=steps,
                observation_call_count=steps,
                prediction_call_count=steps,
                feedback_call_count=steps,
                feedback_record_count=feedback_records,
                action_decision_count=steps,
                action_budget_per_episode=action_budget,
                tuning_search_points=(
                    0 if method is ProjectTwoActionMethod.ORACLE else len(PARAMETER_SPACE[method])
                ),
                evaluator_truth_access=method is ProjectTwoActionMethod.ORACLE,
                output_content_sha256=content_sha256(cases),
            )
        )
        measured.append(
            ArmMeasuredResourceReceipt(
                method=method,
                wall_clock_seconds=wall_seconds,
                process_cpu_seconds=cpu_seconds,
                peak_python_traced_bytes=peak_bytes,
                mean_wall_clock_seconds_per_step=wall_seconds / steps,
                mean_process_cpu_seconds_per_step=cpu_seconds / steps,
            )
        )
    deterministic_hash = content_sha256(
        {
            "protocol": PROTOCOL_ID,
            "dataset_version": dataset.manifest.dataset_version,
            "logical_receipts": tuple(logical),
        }
    )
    same_visible_inputs = (
        len(
            {
                tuple(
                    sorted(
                        (str(key), value)
                        for key, value in item.visible_input_sha256_by_episode.items()
                    )
                )
                for item in logical
            }
        )
        == 1
    )
    same_replay_step_budget = len({item.replay_step_count for item in logical}) == 1
    same_action_budget = (
        len({(item.action_decision_count, item.action_budget_per_episode) for item in logical}) == 1
    )
    all_nonoracle_truth_isolated = all(
        not item.evaluator_truth_access
        for item in logical
        if item.method is not ProjectTwoActionMethod.ORACLE
    )
    engineering_ready = (
        same_visible_inputs
        and same_replay_step_budget
        and same_action_budget
        and all_nonoracle_truth_isolated
    )
    return PerArmResourceReport(
        dataset_version=dataset.manifest.dataset_version,
        logical_receipts=tuple(logical),
        measured_receipts=tuple(measured),
        same_visible_inputs=same_visible_inputs,
        same_replay_step_budget=same_replay_step_budget,
        same_action_budget=same_action_budget,
        all_nonoracle_truth_isolated=all_nonoracle_truth_isolated,
        all_native_reproductions_available=all_native_reproductions_available,
        comparison_environment_ready_for_engineering=engineering_ready,
        comparison_environment_ready_for_paper_claim=(
            engineering_ready and all_native_reproductions_available
        ),
        deterministic_fairness_sha256=deterministic_hash,
        limitations=(
            "CPU, wall-clock, and Python allocator peaks are host-local observations.",
            "O-STaR, DynaMem, STAR and AMG remain matched adapters in this benchmark.",
            "A fair engineering replay does not by itself establish native-method fidelity.",
        ),
    )


__all__ = [
    "PROTOCOL_ID",
    "ArmLogicalBudgetReceipt",
    "ArmMeasuredResourceReceipt",
    "PerArmResourceReport",
    "run_per_arm_resource_meter",
]
