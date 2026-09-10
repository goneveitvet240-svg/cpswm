from __future__ import annotations

from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_debt_replay_confirmation import (
    CLAIM_BOUNDARY,
    PROTOCOL_ID,
    _load_config,
    _new_system,
    compare_positive_transition,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _episode_schedule_commitment,
    _packet_for_step,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _load_config as _load_retained_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_replay_config_is_engineering_only_and_keeps_coverage_limits_explicit() -> None:
    config = _load_config(ROOT)
    assert config["protocol_id"] == PROTOCOL_ID
    assert config["claim_boundary"] == CLAIM_BOUNDARY
    assert config["test_reuse_disclosure"] == {
        "engineering_confirmation_only": True,
        "confirmatory": False,
        "fresh_preregistered_death_test": False,
        "may_issue_positive_scientific_receipt": False,
    }
    assert all(value is False for value in config["coverage_limits"].values())
    assert config["execution"]["evaluator_truth_accessed"] is False


def test_one_positive_transition_matches_direct_and_production_debt_replay() -> None:
    retained = _load_retained_config(ROOT)
    dataset = (
        D0SyntheticReplayExperimentConfig.load(ROOT / Path(retained["dataset_source"]))
        .build_adapter()
        .build()
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    index, step = next(
        (index, step) for index, step in enumerate(episode.steps) if step.after is not None
    )
    packet = _packet_for_step(
        episode,
        step,
        schedule_commitment_sha256=_episode_schedule_commitment(episode),
    )
    row = compare_positive_transition(
        direct_system=_new_system(episode),
        replay_system=_new_system(episode),
        episode=episode,
        step=step,
        original_step_index=index,
        packet=packet,
        absolute_tolerance=1e-12,
    )

    assert all(row["checks"].values())
    assert row["direct_put_back_location_id"] == row["replay_put_back_location_id"]
    assert (
        row["direct_owner_habit_location_distribution"]
        == row["replay_owner_habit_location_distribution"]
    )
