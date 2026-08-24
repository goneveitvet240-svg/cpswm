from __future__ import annotations

from cpswm.system.evaluation_operations import (
    D0SyntheticOracleReplayAdapter,
    enforce_project_two_replay_gate,
    summarize_project_two_evidence_coverage,
)


def _multiseed_dataset():
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(101, 102, 103, 104),
        test_seeds=(201, 202, 203, 204, 205, 206),
        max_steps_per_episode=32,
        dataset_version="project-two-test-multiseed@0.3",
        object_family_bucket_count=2,
        sealed_secret="project-two-test-multiseed-secret",
    ).build()


def test_multiseed_batch_repeats_families_without_cross_split_leakage():
    dataset = _multiseed_dataset()
    report = enforce_project_two_replay_gate(dataset)
    assert report.ready
    validation_families = {
        item.object_family for item in dataset.episodes if item.split.value == "validation"
    }
    test_families = {item.object_family for item in dataset.episodes if item.split.value == "test"}
    assert validation_families.isdisjoint(test_families)
    assert max(report.family_counts.values()) > 1


def test_multiseed_evidence_inventory_covers_open_world_and_feedback_outcomes():
    coverage = summarize_project_two_evidence_coverage(_multiseed_dataset())
    assert coverage.split_episode_counts == {"validation": 4, "test": 6}
    assert coverage.unique_household_count == 10
    assert coverage.true_actor_counts["unknown_actor"] > 0
    assert coverage.true_actor_counts["owner"] > 0
    assert coverage.true_actor_counts["guest"] > 0
    assert coverage.true_mechanism_counts["unknown_mechanism"] > 0
    assert coverage.true_mechanism_counts["direct_relocation"] > 0
    assert coverage.true_mechanism_counts["handoff_relocation"] > 0
    assert coverage.dominant_feedback_outcome_counts["success"] > 0
    assert coverage.dominant_feedback_outcome_counts["object_slipped"] > 0
    assert coverage.observed_step_count > 0
    assert coverage.missing_observation_step_count > 0


def test_multiseed_materialization_is_content_reproducible():
    first = _multiseed_dataset()
    second = _multiseed_dataset()
    assert first.manifest.model_dump(mode="json") == second.manifest.model_dump(mode="json")
    assert [item.model_dump(mode="json") for item in first.episodes] == [
        item.model_dump(mode="json") for item in second.episodes
    ]
    assert [item.model_dump(mode="json") for item in first.evaluator_store] == [
        item.model_dump(mode="json") for item in second.evaluator_store
    ]
