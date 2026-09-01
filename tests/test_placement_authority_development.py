"""Development runner tests; sealed household execution is forbidden."""

from __future__ import annotations

from pathlib import Path

from cpswm.system.evaluation_operations.placement_authority_development import (
    build_development_case,
    run_placement_authority_development,
)
from cpswm.system.evaluation_operations.placement_authority_preregistration import (
    REQUIRED_SCENARIOS,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/method_falsification/placement_authority_v0_2_preregistration.json"


def _report():  # type: ignore[no-untyped-def]
    return run_placement_authority_development(CONFIG, repository_root=ROOT)


def test_every_preregistered_family_has_an_explicit_oracle_case() -> None:
    cases = tuple(build_development_case(51001, family) for family in REQUIRED_SCENARIOS)

    assert {case.family for case in cases} == REQUIRED_SCENARIOS
    assert all(case.expected_action.kind.value in {"place", "verify", "abstain"} for case in cases)
    report = _report()
    assert set(report["oracle_definitions"]) == REQUIRED_SCENARIOS
    assert all(
        definition["correct_action"] and definition["failure"]
        for definition in report["oracle_definitions"].values()
    )


def test_development_runner_uses_20_tuning_and_10_diagnostic_households_only() -> None:
    report = _report()

    assert report["development_household_count"] == 30
    assert report["tuning_household_count"] == 20
    assert report["diagnostic_household_count"] == 10
    assert report["diagnostic_episode_count"] == 100
    assert report["max_executed_seed"] == 51030
    assert report["sealed_test_seed_start"] == 52001
    assert report["sealed_test_access_count"] == 0
    assert report["sealed_test_execution_status"] == "not_executed"
    assert report["split_receipts"]["disjoint"] is True


def test_both_direct_opponents_are_independently_tuned() -> None:
    report = _report()

    assert len(report["tuning_trials"]["collapsed_placement_memory"]) == 5
    assert len(report["tuning_trials"]["authority_agnostic_rule_resolver"]) == 2
    assert report["selected_parameters"]["authority_scoped_v0_2"] is None
    assert report["selected_parameters"]["collapsed_placement_memory"] in {
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    }
    assert report["selected_parameters"]["authority_agnostic_rule_resolver"] in {
        "recency_first",
        "specificity_then_recency",
    }
    assert all(
        receipt
        == {
            "independently_tuned": True,
            "same_visible_records": True,
            "same_action_budget": True,
            "shared_hard_conflict_verification": True,
        }
        for receipt in report["opponent_fairness_receipts"].values()
    )


def test_candidate_passes_every_frozen_development_attack() -> None:
    report = _report()

    assert report["all_candidate_attacks_passed"]
    assert len(report["attack_summary"]) == 16
    assert all(item["pass_count"] == 30 for item in report["attack_summary"].values())
    assert all(item["failure_count"] == 0 for item in report["attack_summary"].values())


def test_development_report_is_reproducible_and_never_a_formal_claim() -> None:
    first = _report()
    second = _report()

    assert first == second
    assert first["scientific_status"] == "development_only_not_formal_evidence"
    assert first["paper_claim_allowed"] is False
    assert first["formal_decision"] == "not_evaluated"
    assert first["confidence_intervals_valid_for_external_claim"] is False
    assert first["effective_structural_scenario_count"] == 10
    assert set(first["paired_development_effects"]) == {
        "collapsed_placement_memory",
        "authority_agnostic_rule_resolver",
    }
    provenance = first["authority_provenance_sample"]
    assert len(provenance["identity_to_role_receipts"]) == 2
    assert all(
        item["matched_attestation_record_id"] is not None
        for item in provenance["identity_to_role_receipts"]
    )
    assert provenance["role_to_decision_receipt"]["selected_authority"] == ("household_owner")
    assert len(provenance["role_to_decision_receipt"]["rejected_lower_authority_record_ids"]) == 1
    assert provenance["final_action"]["status"] == "resolved"
