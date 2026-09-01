from __future__ import annotations

from cpswm.contracts import ProjectTwoDataMaturity
from cpswm.system.evaluation_operations.project_two_d1_development import (
    build_d1_development_batch,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    enforce_project_two_replay_gate,
    summarize_project_two_evidence_coverage,
)


def test_d1_development_batch_has_required_scale_scenes_families_and_seeds():
    dataset = build_d1_development_batch(max_steps_per_episode=4)
    assert len(dataset.episodes) == 30
    assert {item.split.value for item in dataset.episodes} == {"validation", "test"}
    assert len({item.household_id for item in dataset.episodes}) == 30
    assert len({item.scene_id.rsplit("-", 1)[-1] for item in dataset.episodes}) >= 3
    assert len({item.object_family for item in dataset.episodes}) >= 5
    assert all(
        item.maturity is ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE
        and item.source_evidence_maturity is ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE
        for item in dataset.episodes
    )
    assert (
        len(
            {
                entry
                for item in dataset.episodes
                for entry in item.provenance
                if entry.startswith("development_seed:")
            }
        )
        == 30
    )


def test_d1_batch_preserves_open_world_feedback_and_split_firewall():
    dataset = build_d1_development_batch(max_steps_per_episode=8)
    assert enforce_project_two_replay_gate(dataset).ready
    coverage = summarize_project_two_evidence_coverage(dataset)
    assert coverage.true_actor_counts["unknown_actor"] > 0
    assert coverage.true_mechanism_counts["unknown_mechanism"] > 0
    assert coverage.dominant_feedback_outcome_counts["success"] > 0
    assert coverage.dominant_feedback_outcome_counts["object_slipped"] > 0
