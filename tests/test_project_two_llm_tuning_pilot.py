from __future__ import annotations

from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_llm_experiment import (
    ProjectTwoLLMExperimentPilot,
)
from cpswm.system.evaluation_operations.project_two_tuning import ProjectTwoExperimentalTrack


def test_four_track_pilot_uses_same_replay_and_sealed_test_once():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=4
    ).build()
    report = ProjectTwoLLMExperimentPilot(search_budget=1).run(dataset)
    tracks = {item.arm_id for item in report.cases}
    assert tracks == {item.value for item in ProjectTwoExperimentalTrack}
    assert report.held_out_run_count == 1
    assert len({item.action.visible_input_hash for item in report.cases}) == 1
    assert all(not item.held_out_episode_ids_seen for item in report.tuning_receipts)


def test_llm_evidence_track_reaches_full_feedback_revision_loop():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=5
    ).build()
    report = ProjectTwoLLMExperimentPilot(search_budget=1).run(dataset)
    llm = next(
        item
        for item in report.cases
        if item.arm_id == ProjectTwoExperimentalTrack.LLM_AS_EVIDENCE.value
    )
    direct = next(
        item
        for item in report.cases
        if item.arm_id == ProjectTwoExperimentalTrack.LLM_DIRECT_DECISION.value
    )
    assert llm.action.full_feedback_revision_calls > 0
    assert direct.action.full_feedback_revision_calls == 0
    assert llm.llm_tokens > 0


def test_all_runtime_ablations_execute_and_report_action_deltas():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=3
    ).build()
    report = ProjectTwoLLMExperimentPilot(search_budget=1).run(dataset)
    assert len(report.ablation_impacts) == 19
    assert all(item.topology_cut_verified for item in report.ablation_impacts)
    assert all(
        item.runtime_status == "executed_on_d0_evaluator_sandbox"
        for item in report.ablation_impacts
    )
    assert all(
        item.put_back_error_delta_vs_llm_evidence is not None
        and item.action_regret_delta_vs_llm_evidence is not None
        for item in report.ablation_impacts
    )
