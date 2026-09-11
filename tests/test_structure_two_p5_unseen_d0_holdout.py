from __future__ import annotations

from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_unseen_d0_holdout import (
    _load_config,
    verify_p5_unseen_d0_holdout,
)

ROOT = Path(__file__).resolve().parents[1]


def test_unseen_d0_choice_is_frozen_without_false_independent_custody() -> None:
    config = _load_config(ROOT)
    dataset = D0SyntheticReplayExperimentConfig.load(ROOT / config["dataset_source"])

    assert config["choice"] == "unseen_D0_holdout"
    assert dataset.test_seeds == tuple(range(12001, 12061))
    assert set(dataset.test_seeds).isdisjoint(range(6001, 6061))
    assert config["holdout_custody"]["independent_custodian"] is False
    assert config["holdout_custody"]["confirmatory"] is False


def test_unseen_d0_verifier_refuses_hash_only_mode() -> None:
    with pytest.raises(ValueError, match="requires fresh recomputation"):
        verify_p5_unseen_d0_holdout(
            {},
            repository_root=ROOT,
            fresh_recompute=False,
        )
