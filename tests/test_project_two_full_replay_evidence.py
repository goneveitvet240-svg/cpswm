from __future__ import annotations

from cpswm.contracts import ProjectOneRequestApplicationStatus
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_multiseed_evidence import (
    run_project_two_replay_evidence,
)


def test_full_replay_outputs_episode_and_event_traces_with_frozen_chain():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101, 102),
        test_seeds=(211, 212),
        max_steps_per_episode=8,
        dataset_version="project-two-full-loop-test@0.1",
        object_family_bucket_count=2,
    ).build()
    report = run_project_two_replay_evidence(dataset, bootstrap_samples=100)
    assert len(report["episode_reports"]) == 4
    assert all(item["step_traces"] for item in report["episode_reports"])
    assert all("action_metrics" in item for item in report["episode_reports"])
    assert report["inference_chain"][:4] == [
        "ObservationDetectionResult",
        "CHEH",
        "ORRER",
        "PCHMP",
    ]
    assert report["configuration_selection"]["tuned"] is False
    assert report["configuration_selection"]["test_truth_used"] is False


def test_full_replay_reports_actor_mechanism_strata_and_bootstrap_groups():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101, 102, 103),
        test_seeds=(211, 212, 213),
        max_steps_per_episode=12,
        dataset_version="project-two-strata-test@0.1",
        object_family_bucket_count=3,
    ).build()
    report = run_project_two_replay_evidence(dataset, bootstrap_samples=100)
    for key in ("owner", "guest", "unknown_actor"):
        assert key in report["strata"]["actor"]
    for key in ("direct_relocation", "handoff_relocation", "unknown_mechanism"):
        assert key in report["strata"]["mechanism"]
    assert report["groups"]["household"]
    assert report["groups"]["object_family"]
    assert report["metric_semantics"]["action_utility_evidence"]
    assert report["metric_semantics"]["diagnostic_only"]


def test_ccrr_rejected_correction_has_atomic_rejected_receipt_not_runtime_error():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(1013,),
        test_seeds=(9999,),
        max_steps_per_episode=12,
        dataset_version="project-two-ccrr-rejection-regression@0.1",
        sealed_secret="project-two-d0-multiseed-development-v0.3",
    ).build()
    state = _FullProjectTwoMethod(dataset.episodes[0], owner_threshold=0.5)
    for step in dataset.episodes[0].steps:
        state.observe(step)
        state.predict()
        state.feedback(step)
    rejected = [
        trace
        for trace in state.revision_action_traces
        if trace.request_application_status is ProjectOneRequestApplicationStatus.REJECTED
    ]
    assert rejected
    receipts = [
        receipt
        for trace in rejected
        for receipt in state.spine.application_receipts_for_feedback(trace.feedback_record_id)
        if receipt.status is ProjectOneRequestApplicationStatus.REJECTED
    ]
    assert receipts
    assert all(
        receipt.old_belief_snapshot_id == receipt.new_belief_snapshot_id for receipt in receipts
    )
    assert all(
        not receipt.dirichlet_deltas and not receipt.rls_deltas and not receipt.hybrid_rgrc_deltas
        for receipt in receipts
    )
