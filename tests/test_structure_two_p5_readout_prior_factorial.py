from __future__ import annotations

from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_p5_readout_prior_factorial import (
    CELL_ORDER,
    _load_config,
    factorial_effects,
    verify_p5_readout_prior_factorial,
)

ROOT = Path(__file__).resolve().parents[1]


def test_factorial_protocol_is_explicitly_previously_opened_and_complete() -> None:
    config = _load_config(ROOT)
    assert tuple(config["cells"]) == CELL_ORDER
    assert config["data_status"] == "previously_opened_development_split"
    assert config["test_reuse_disclosure"]["confirmatory"] is False


def test_factorial_effects_separate_both_fixes_and_interaction() -> None:
    summaries = {
        "old_readout__old_prior": {
            "search_error_rate": 0.8,
            "put_back_error_rate": 0.7,
            "normalized_search_regret": 0.6,
        },
        "new_readout__old_prior": {
            "search_error_rate": 0.7,
            "put_back_error_rate": 0.5,
            "normalized_search_regret": 0.5,
        },
        "old_readout__new_prior": {
            "search_error_rate": 0.6,
            "put_back_error_rate": 0.6,
            "normalized_search_regret": 0.4,
        },
        "new_readout__new_prior": {
            "search_error_rate": 0.4,
            "put_back_error_rate": 0.2,
            "normalized_search_regret": 0.1,
        },
    }
    effects = factorial_effects(summaries)

    assert effects["put_back_error_rate"]["readout_fix_improvement_at_old_prior"] == pytest.approx(
        0.2
    )
    assert effects["put_back_error_rate"]["prior_fix_improvement_at_old_readout"] == pytest.approx(
        0.1
    )
    assert effects["put_back_error_rate"]["combined_improvement_from_old_old"] == pytest.approx(0.5)
    assert effects["put_back_error_rate"]["interaction_synergy_improvement"] == pytest.approx(0.2)


def test_factorial_verifier_refuses_hash_only_mode() -> None:
    with pytest.raises(ValueError, match="requires fresh recomputation"):
        verify_p5_readout_prior_factorial(
            {},
            repository_root=ROOT,
            fresh_recompute=False,
        )
