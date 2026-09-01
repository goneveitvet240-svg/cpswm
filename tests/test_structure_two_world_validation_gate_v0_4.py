"""Fail-closed boundary tests for fresh Structure-Two v0.4 validation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (
    load_frozen_validation_gate_design,
    verify_validation_manifest_against_train_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)


def test_unsigned_draft_cannot_generate_validation_worlds() -> None:
    with pytest.raises(ValueError, match="not frozen"):
        load_frozen_validation_gate_design(DRAFT, repository_root=ROOT)


def test_validation_gate_has_no_detector_binding() -> None:
    source = (
        ROOT / "src/cpswm/system/evaluation_operations/structure_two_world_validation_gate_v0_4.py"
    ).read_text(encoding="utf-8")
    assert "RegimeAdaptiveWitnessConfig" not in source
    assert "_WitnessEstimator" not in source
    assert "false_reset" not in source


def test_validation_draft_is_bound_to_train_selected_estimator_and_distribution() -> None:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    train = json.loads(
        (
            ROOT / "benchmarks/structure_two/structure_two_world_rolling_train_gate_v0_4.json"
        ).read_text(encoding="utf-8")
    )
    assert draft["status"] == "DRAFT-invalidated-recovered-custody-material-candidate-visible"
    assert draft["execution_policy"]["validation_gate_a_allowed"] is False
    assert draft["world_distribution"]["duration_days_inclusive"] == [320, 380]
    assert draft["rolling_visible_history_reference"]["window_days"] == 35
    tampered = copy.deepcopy(draft)
    tampered["rolling_visible_history_reference"]["window_days"] = 999
    with pytest.raises(ValueError, match="differs from train selection"):
        verify_validation_manifest_against_train_evidence(
            tampered,
            train,
            repository_root=ROOT,
        )


def test_validation_draft_freezes_exact_ten_nonoracle_arms() -> None:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    arms = draft["gate_b_contract"]["expected_arms"]
    assert len(arms) == len(set(arms)) == 10
    assert "full_rerun_oracle" not in arms
    assert draft["gate_b_contract"]["distinguishability_thresholds"] == {
        "min_pairwise_prediction_disagreement_rate": 0.01,
        "min_episode_fraction_with_multiple_arm_trajectories": 0.2,
    }


def test_validation_draft_rejects_a_different_arm_adapter_source_bundle() -> None:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    draft["gate_b_contract"]["producer_source_bundle_sha256"] = "e" * 64
    train = json.loads(
        (
            ROOT / "benchmarks/structure_two/structure_two_world_rolling_train_gate_v0_4.json"
        ).read_text(encoding="utf-8")
    )
    with pytest.raises(ValueError, match="sources differ from the frozen bundle"):
        verify_validation_manifest_against_train_evidence(
            draft,
            train,
            repository_root=ROOT,
        )


def test_validation_draft_rejects_post_hoc_gate_b_threshold_changes() -> None:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    draft["gate_b_contract"]["distinguishability_thresholds"][
        "min_pairwise_prediction_disagreement_rate"
    ] = 0.0
    train = json.loads(
        (
            ROOT / "benchmarks/structure_two/structure_two_world_rolling_train_gate_v0_4.json"
        ).read_text(encoding="utf-8")
    )
    with pytest.raises(ValueError, match="distinguishability thresholds"):
        verify_validation_manifest_against_train_evidence(
            draft,
            train,
            repository_root=ROOT,
        )
