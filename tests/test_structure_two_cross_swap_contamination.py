"""Tests for the v0.6 belief/readout cross-swap diagnostic."""

from dataclasses import replace

from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_cross_swap_contamination import (
    BeliefSource,
    ReadoutSource,
    run_cross_swap_contamination_diagnostic,
)


def test_cross_swap_runs_all_four_arms_without_truth_at_the_belief_boundary():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(1101,),
        test_seeds=(6101,),
        max_steps_per_episode=12,
    ).build()
    report = run_cross_swap_contamination_diagnostic(dataset)

    assert len(report.metrics) == 4
    assert {(item.belief_source, item.readout_source) for item in report.metrics} == set(
        (belief, readout) for belief in BeliefSource for readout in ReadoutSource
    )
    assert all(item.step_count == 12 for item in report.metrics)
    assert "after all four" in report.evaluator_truth_access_boundary
    assert len(report.payload_sha256) == 64
    assert report.verify_payload_hash()
    assert report.put_back_readout_disagreement_count > 0
    assert report.causal_first_fault_claim_allowed is False
    assert sum(report.first_fault_counts.values()) == len(report.contamination_traces)
    assert all(
        item.selected_location_id == item.true_location_id for item in report.contamination_traces
    )
    tampered = replace(
        report,
        selected_amg_parameter=report.selected_amg_parameter + 0.1,
    )
    assert not tampered.verify_payload_hash()
