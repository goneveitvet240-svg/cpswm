from __future__ import annotations

from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_p5_readout_prior_factorial import (
    CELL_ORDER,
    _load_config,
    factorial_effects,
    verify_p5_readout_prior_factorial,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _semantic_action_chain_sha256,
    _semantic_ciav_receipt_chain_sha256,
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


def test_semantic_chains_exclude_run_local_ids_but_bind_consequential_fields() -> None:
    first_action = {
        "posterior_sha256": "a" * 64,
        "information_set_sha256": "b" * 64,
        "search_location_id": "search",
        "put_back_location_id": "put-back",
    }
    second_action = {
        **first_action,
        "posterior_sha256": "c" * 64,
        "information_set_sha256": "d" * 64,
    }
    receipt = {
        "arm": "direct_p5_full_eager",
        "episode_id": "episode",
        "step_id": "step",
        "packet_sha256": "1" * 64,
        "schedule_commitment_sha256": "2" * 64,
        "candidate_set_sha256": "3" * 64,
        "selected_action_id": "action",
        "realized_observation_sha256": "4" * 64,
        "motion_cost": 0.0,
        "time_cost": 0.0,
        "interruption_cost": 0.0,
        "privacy_cost": 0.0,
        "safety_cost": 0.0,
        "privacy_budget_before": 1.0,
        "privacy_budget_after": 1.0,
        "observation_release_phase": "before_typed_actions_committed",
        "evaluator_truth_release_phase": "after_typed_actions_committed",
        "closure_kind": "full_p5:full_transition",
        "consumer_state_before_sha256": "5" * 64,
        "consumer_state_after_sha256": "6" * 64,
        "receipt_sha256": "7" * 64,
    }
    second_receipt = {
        **receipt,
        "consumer_state_before_sha256": "8" * 64,
        "consumer_state_after_sha256": "9" * 64,
        "receipt_sha256": "0" * 64,
    }

    assert _semantic_action_chain_sha256([first_action]) == _semantic_action_chain_sha256(
        [second_action]
    )
    assert _semantic_ciav_receipt_chain_sha256([receipt]) == _semantic_ciav_receipt_chain_sha256(
        [second_receipt]
    )
    assert _semantic_action_chain_sha256([first_action]) != _semantic_action_chain_sha256(
        [{**first_action, "put_back_location_id": "other"}]
    )
