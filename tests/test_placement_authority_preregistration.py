"""Fail-closed checks for the v0.2 placement-authority preregistration."""

from __future__ import annotations

from pathlib import Path

from cpswm.system.evaluation_operations.placement_authority_preregistration import (
    REQUIRED_OPPONENTS,
    REQUIRED_SCENARIOS,
    build_preregistration_receipt,
    load_placement_authority_preregistration,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/method_falsification/placement_authority_v0_2_preregistration.json"


def test_preregistration_is_bound_to_the_preserved_round_two_failure() -> None:
    protocol = load_placement_authority_preregistration(CONFIG, repository_root=ROOT)

    assert protocol.parent_failure.decision == "falsified"
    assert protocol.legacy_reproducibility.legacy_result_must_not_be_overwritten
    assert protocol.sealed_test_split.execution_status == "not_executed"


def test_preregistration_freezes_every_direct_opponent_and_scenario() -> None:
    protocol = load_placement_authority_preregistration(CONFIG, repository_root=ROOT)

    assert {item.opponent_id for item in protocol.opponents} == REQUIRED_OPPONENTS
    assert set(protocol.scenario_families) == REQUIRED_SCENARIOS
    validation = set(
        range(
            protocol.validation_split.seed_start,
            protocol.validation_split.seed_start + protocol.validation_split.seed_count,
        )
    )
    sealed = set(
        range(
            protocol.sealed_test_split.seed_start,
            protocol.sealed_test_split.seed_start + protocol.sealed_test_split.seed_count,
        )
    )
    assert validation.isdisjoint(sealed)


def test_receipt_binds_candidate_code_without_opening_the_test_split() -> None:
    receipt = build_preregistration_receipt(CONFIG, repository_root=ROOT)

    assert receipt["claim_status"] == "preregistered_not_tested"
    assert receipt["sealed_test_results_present"] is False
    assert receipt["sealed_test_execution_status"] == "not_executed"
    assert len(receipt["preregistration_sha256"]) == 64
    assert len(receipt["candidate_source_sha256"]) == 64
    assert len(receipt["authority_provenance_source_sha256"]) == 64
    assert len(receipt["development_runner_source_sha256"]) == 64
    assert len(receipt["candidate_bundle_sha256"]) == 64
