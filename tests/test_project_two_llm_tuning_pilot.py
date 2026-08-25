from __future__ import annotations

import pytest
from pydantic import ValidationError

from cpswm.contracts import LLMIntegrationRole
from cpswm.system.evaluation_operations.project_two_ablation import ProjectTwoAblation
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_llm_experiment import (
    LLMMechanismProgressionGate,
    PoweredMechanismCompletionReceipt,
    PoweredMechanismStage,
    ProjectTwoLLMAggregate,
    ProjectTwoLLMExperimentPilot,
)
from cpswm.system.evaluation_operations.project_two_tuning import (
    ProjectTwoExperimentalTrack,
    ProjectTwoTuningCandidate,
)
from cpswm.system.llm_evidence import LLMCacheStatus


def test_explicit_role_tracks_use_same_replay_and_sealed_test_once():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=4
    ).build()
    report = ProjectTwoLLMExperimentPilot(search_budget=1).run(dataset)
    tracks = {item.arm_id for item in report.cases}
    assert tracks == {item.value for item in ProjectTwoExperimentalTrack}
    assert report.held_out_run_count == 1
    assert len({item.action.visible_input_hash for item in report.cases}) == 1
    assert all(not item.held_out_episode_ids_seen for item in report.tuning_receipts)
    assert set(report.role_comparison) == {
        "no_llm",
        "llm_prior_only",
        "llm_evidence",
        "llm_direct",
    }
    assert report.receipt_metric_policy.semantics_validated
    assert not report.receipt_metric_policy.paper_result_eligible
    assert not (
        {item.metric for item in report.aggregates}
        & set(report.receipt_metric_policy.operational_metrics)
    )
    assert not report.progression_gate.d2_allowed
    assert report.progression_gate.powered_d0_receipt is None
    assert report.progression_gate.powered_d1_receipt is None


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
    assert llm.llm_provenance
    assert all(
        item.role is LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER
        for item in llm.llm_provenance
    )
    assert direct.llm_provenance
    assert all(
        item.role is LLMIntegrationRole.LLM_DIRECT_BASELINE for item in direct.llm_provenance
    )
    assert len(llm.llm_call_audits) >= len(llm.llm_provenance)
    assert any(item.cache_status is LLMCacheStatus.HIT for item in llm.llm_call_audits)
    assert all(item.cache_status is LLMCacheStatus.MISS for item in direct.llm_call_audits)


def _completion(stage: PoweredMechanismStage) -> PoweredMechanismCompletionReceipt:
    return PoweredMechanismCompletionReceipt(
        stage=stage,
        artifact_uri=f"artifact://{stage.value}/mechanism-report.json",
        artifact_sha256=("a" if stage is PoweredMechanismStage.D0 else "b") * 64,
        power_analysis_uri=f"artifact://{stage.value}/power-analysis.json",
        power_analysis_sha256=("c" if stage is PoweredMechanismStage.D0 else "d") * 64,
        protocol_version="project-two-powered-mechanism@0.1",
        completion_authority="powered-mechanism-verifier@0.1",
        observed_sample_size=120,
        required_sample_size=100,
    )


def test_d2_gate_is_computed_from_artifact_bound_completion_receipts_only():
    with pytest.raises(ValidationError, match=r"[Ee]xtra inputs are not permitted"):
        LLMMechanismProgressionGate(d2_allowed=True)

    d0 = _completion(PoweredMechanismStage.D0)
    d1 = _completion(PoweredMechanismStage.D1)
    gate = LLMMechanismProgressionGate(
        powered_d0_receipt=d0,
        powered_d1_receipt=d1,
    )
    assert gate.d2_allowed
    assert len(d0.receipt_sha256) == 64
    assert len(d1.receipt_sha256) == 64
    assert gate.model_dump(mode="json")["d2_allowed"] is True

    underpowered = {
        **d0.model_dump(exclude={"receipt_sha256"}),
        "observed_sample_size": 99,
    }
    with pytest.raises(ValidationError, match="underpowered"):
        PoweredMechanismCompletionReceipt(**underpowered)
    with pytest.raises(ValidationError, match="must bind a D0 artifact"):
        LLMMechanismProgressionGate(powered_d0_receipt=d1)


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


def test_llm_prior_only_still_executes_full_project_two_and_direct_writes_nothing():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=4
    ).build()
    pilot = ProjectTwoLLMExperimentPilot(search_budget=1)
    episode = dataset.episodes[0]
    candidate = ProjectTwoTuningCandidate.pilot(0)
    prior = pilot._run_case(dataset, episode, ProjectTwoAblation.LLM_PRIOR_ONLY.value, candidate)
    explicit_prior = pilot._run_case(
        dataset, episode, ProjectTwoExperimentalTrack.LLM_PRIOR_ONLY.value, candidate
    )
    direct = pilot._run_case(
        dataset, episode, ProjectTwoAblation.LLM_DIRECT_DECISION.value, candidate
    )
    assert prior.action.full_feedback_revision_calls > 0
    assert explicit_prior.action.full_feedback_revision_calls > 0
    assert "LLM_prior_only:executed_full_project_two" in prior.runtime_module_trace
    assert "LLM_prior_only:executed_full_project_two" in explicit_prior.runtime_module_trace
    assert direct.action.full_feedback_revision_calls == 0
    assert direct.action.project_one_stat_requests == 0
    assert "ProjectOne_statistics:skipped" in direct.runtime_module_trace


def test_holm_cannot_be_marked_executed_without_valid_p_values():
    with pytest.raises(ValidationError, match="Holm correction requires"):
        ProjectTwoLLMAggregate(
            arm_id="arm",
            metric="regret",
            value=0.0,
            confidence_interval_95=(0.0, 0.0),
            worst_group_value=0.0,
            paired_difference_vs_no_llm=0.0,
            effect_size=0.0,
            holm_correction_executed=True,
        )
