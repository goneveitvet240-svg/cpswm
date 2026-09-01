from __future__ import annotations

from cpswm.contracts import ProjectOneRequestApplicationStatus
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
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
    for metric in (
        "hidden_event_hypothesis_accuracy",
        "revision_accuracy",
        "mean_unresolved_mass",
    ):
        interval = report["aggregate_metrics"][metric]
        assert interval["resampling_unit"] == "episode_id"
        assert interval["cluster_n"] == len(dataset.episodes)
    sensitivity = report["aggregate_metrics"]["diagnostic_cluster_sensitivity"]
    assert all(
        item["resampling_unit"] == "household_id" for item in sensitivity["household"].values()
    )
    assert all(
        item["resampling_unit"] == "object_family" for item in sensitivity["object_family"].values()
    )
    assert report["metric_semantics"]["action_utility_evidence"]
    assert report["metric_semantics"]["diagnostic_only"]
    assert report["metric_semantics"]["operational_not_paper_outcomes"] == [
        "project_one_stat_applications",
        "project_one_stat_rejections",
        "project_one_stat_deferred",
        "project_one_stat_replay_noops",
    ]


def test_ccrr_rejected_correction_has_atomic_rejected_receipt_not_runtime_error():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(10,),
        test_seeds=(9999,),
        max_steps_per_episode=12,
        dataset_version="project-two-ccrr-rejection-regression@0.2",
        sealed_secret="project-two-d0-multiseed-development-v0.3",
    ).build()
    state = _FullProjectTwoMethod(
        dataset.episodes[0],
        owner_threshold=0.5,
        loop_config=PrototypeLoopConfig(
            habit_change_probability_threshold=0.05,
            transient_disturbance_probability_threshold=0.5,
        ),
    )
    # Materialize the complete visible prefix first.  The rejected transaction
    # is specifically a delayed correction to an earlier event: during the
    # prefix replay CCRR can quarantine that corrected event and a later
    # incompatible observation can then discard it.  Applying every feedback
    # immediately after its own step never creates this semantic precondition.
    episode = dataset.episodes[0]
    for step in episode.steps:
        state.observe(step)
        state.predict()
    delayed_step = episode.steps[7]
    assert delayed_step.execution_feedback
    state.feedback(delayed_step)
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
        "CCRR/RGRC rejected the corrected event" in receipt.rationale for receipt in receipts
    )
    assert all(
        receipt.old_belief_snapshot_id == receipt.new_belief_snapshot_id for receipt in receipts
    )
    assert all(
        not receipt.dirichlet_deltas and not receipt.rls_deltas and not receipt.hybrid_rgrc_deltas
        for receipt in receipts
    )
    assert state.project_one_requests == (
        state.project_one_applications
        + state.project_one_deferred
        + state.project_one_rejections
        + state.project_one_replay_noops
    )
