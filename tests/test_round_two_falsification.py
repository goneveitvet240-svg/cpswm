"""Round-2 direct-opponent experiment tests."""

from __future__ import annotations

from pathlib import Path

from cpswm.system.evaluation_operations.method_falsification import (
    FalsificationDecision,
    current_method_falsification_registry,
    evaluate_method_submission,
)
from cpswm.system.evaluation_operations.round_two_falsification import (
    run_structure_one_layered_habit_round_two,
    run_structure_one_placement_round_two,
    run_structure_three_multi_parse_round_two,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/method_falsification/round_two_v0_1.json"


def test_round_two_layered_habit_is_reproducible_and_bound_to_registry() -> None:
    first_report, first_submission = run_structure_one_layered_habit_round_two(CONFIG)
    second_report, second_submission = run_structure_one_layered_habit_round_two(CONFIG)

    assert first_report == second_report
    assert first_submission == second_submission
    spec = current_method_falsification_registry().by_id(first_submission.method_id)
    result = evaluate_method_submission(spec, first_submission)
    assert result.decision is FalsificationDecision.BLOCKED
    assert result.blockers == ("missing_formal_public_key_verifier",)


def test_round_two_uses_disjoint_tuning_and_sealed_households() -> None:
    report, submission = run_structure_one_layered_habit_round_two(CONFIG)

    assert report["validation_seed_count"] == 20
    assert report["sealed_test_seed_count"] == 100
    assert submission.independent_unit_count == 100
    assert submission.validation_split_sha256 != submission.sealed_test_split_sha256
    assert {item.opponent_id for item in submission.comparisons} == {
        "additive_hierarchical_dirichlet",
        "nested_backoff_habit",
    }


def test_round_two_multi_parse_faces_both_direct_language_opponents() -> None:
    report, submission = run_structure_three_multi_parse_round_two(CONFIG)

    assert report["episode_count"] == 300
    assert submission.independent_unit_count == 300
    assert {item.opponent_id for item in submission.comparisons} == {
        "top1_llm_parse",
        "llm_self_consistency_vote",
    }
    spec = current_method_falsification_registry().by_id(submission.method_id)
    result = evaluate_method_submission(spec, submission)
    assert result.decision is FalsificationDecision.BLOCKED
    assert result.blockers == ("missing_formal_public_key_verifier",)


def test_round_two_placement_can_falsify_the_current_authority_handling() -> None:
    report, submission = run_structure_one_placement_round_two(CONFIG)
    spec = current_method_falsification_registry().by_id(submission.method_id)
    result = evaluate_method_submission(spec, submission)

    assert report["episode_count"] == 300
    assert result.decision is FalsificationDecision.BLOCKED
    assert result.blockers == ("missing_formal_public_key_verifier",)
    assert report["mean_semantic_layer_violation"]["four_layer_placement_semantics"] > 0
