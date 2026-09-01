from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_datasets/d0_multiseed_evidence_v0_3.json"


def test_registered_multiseed_config_binds_the_declared_20_60_design():
    config = D0SyntheticReplayExperimentConfig.load(CONFIG)
    assert not config.train_seeds
    assert len(config.validation_seeds) == 20
    assert len(config.test_seeds) == 60
    assert set(config.validation_seeds).isdisjoint(config.test_seeds)
    assert config.steps_per_episode == 32
    assert not config.confirmatory


def test_config_builds_the_same_typed_replay_boundary_without_truth_leakage():
    registered = D0SyntheticReplayExperimentConfig.load(CONFIG)
    config = registered.model_copy(
        update={
            "dataset_version": "project-two-d0-config-smoke@0.1",
            "train_seed_start": 11,
            "train_seed_count": 1,
            "validation_seed_count": 1,
            "test_seed_count": 1,
            "steps_per_episode": 4,
        }
    )
    dataset = config.build_adapter().build()
    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)) == 1
    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)) == 1
    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)) == 1
    assert all(len(episode.steps) == 4 for episode in dataset.episodes)
    assert all(not hasattr(episode, "truth_by_step") for episode in dataset.episodes)


def test_config_rejects_overlap_and_scope_narrowing():
    payload = D0SyntheticReplayExperimentConfig.load(CONFIG).model_dump(mode="python")
    with pytest.raises(ValidationError, match="overlap"):
        D0SyntheticReplayExperimentConfig.model_validate(
            {
                **payload,
                "test_seed_start": payload["validation_seed_start"],
            }
        )
    with pytest.raises(ValidationError, match="narrows"):
        D0SyntheticReplayExperimentConfig.model_validate(
            {
                **payload,
                "retained_capabilities": ("hidden_event_inference",),
            }
        )


def test_confirmatory_config_requires_a_training_split():
    payload = D0SyntheticReplayExperimentConfig.load(CONFIG).model_dump(mode="python")
    with pytest.raises(ValidationError, match="training split"):
        D0SyntheticReplayExperimentConfig.model_validate({**payload, "confirmatory": True})
