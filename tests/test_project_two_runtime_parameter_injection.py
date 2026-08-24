from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_llm_experiment import (
    ProjectTwoLLMExperimentPilot,
)
from cpswm.system.evaluation_operations.project_two_tuning import (
    ProjectTwoExperimentalTrack,
    ProjectTwoFairTuner,
    ProjectTwoTuningCandidate,
    UnusedRuntimeParameterError,
    build_runtime_parameter_receipt,
    reject_unused_parameter_changes,
)


def test_every_declared_parameter_enters_llm_evidence_runtime():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=3
    ).build()
    report = ProjectTwoLLMExperimentPilot(search_budget=1).run(dataset)
    case = next(
        item
        for item in report.cases
        if item.arm_id == ProjectTwoExperimentalTrack.LLM_AS_EVIDENCE.value
    )
    receipt = case.runtime_parameter_receipt
    assert receipt is not None
    expected = set(ProjectTwoTuningCandidate.model_fields) - {"index"}
    assert {item.parameter for item in receipt.bindings} == expected
    assert all(item.target_component and item.runtime_trace_hash for item in receipt.bindings)
    assert all(
        item.runtime_parameter_status == "not_applicable_fixed_oracle"
        or (
            item.runtime_parameter_status == "injected"
            and len(item.runtime_candidate_receipt_ids) == item.search_budget
        )
        for item in report.tuning_receipts
    )


def test_unused_changed_parameter_causes_tuning_failure():
    before = ProjectTwoTuningCandidate.pilot(0)
    after = ProjectTwoTuningCandidate.pilot(1)
    names = set(ProjectTwoTuningCandidate.model_fields) - {"index"}
    deliberately_unused = {
        name: ("unchanged-component", "same-config", "same-trace") for name in names
    }
    before_receipt = build_runtime_parameter_receipt(
        arm_id="arm", candidate=before, bindings=deliberately_unused
    )
    after_receipt = build_runtime_parameter_receipt(
        arm_id="arm", candidate=after, bindings=deliberately_unused
    )
    with pytest.raises(UnusedRuntimeParameterError, match="altered neither"):
        reject_unused_parameter_changes(
            before_candidate=before,
            after_candidate=after,
            before_receipt=before_receipt,
            after_receipt=after_receipt,
        )


def test_joint_candidate_is_rejected_until_module_groups_run_first():
    tuner = ProjectTwoFairTuner(search_budget=2)
    with pytest.raises(ValueError, match="every module group first"):
        tuner.tune_all(
            arm_ids=("arm",),
            candidates=(
                ProjectTwoTuningCandidate.pilot(0),
                ProjectTwoTuningCandidate.pilot(7),
            ),
            validation_episode_ids=("validation",),
            evaluator=lambda _arm, candidate: (candidate.index,),
        )
