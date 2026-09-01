"""Integrity tests for the detector-free Structure-Two v0.4 train gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations import structure_two_world_rolling_gate_v0_4 as rolling
from cpswm.system.evaluation_operations.structure_two_world_gate_v0_3 import (
    RegimeAdaptiveWitnessConfig,
    ShrunkEstimatorConfig,
    evaluate_rollout_v0_3,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4 import (
    DEFAULT_DESIGN,
    DEFAULT_OUTPUT,
    _config_id,
    _select_config,
    evaluate_rolling_rollout,
    load_rolling_train_gate_design,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def design():
    return load_rolling_train_gate_design(
        ROOT / DEFAULT_DESIGN,
        repository_root=ROOT,
    )


def test_design_uses_true_world_level_outer_cv(design) -> None:
    flattened = [seed for fold in design.folds for seed in fold]
    assert design.duration_days == (320, 380)
    assert design.world_seeds == tuple(range(410001, 410025))
    assert len(flattened) == len(set(flattened)) == 24
    assert set(flattened) == set(design.world_seeds)
    assert {len(fold) for fold in design.folds} == {6}
    assert len(design.candidates()) == 20
    assert design.minimum_mean_search_gain == pytest.approx(0.020)
    assert design.minimum_worst_fold_search_gain == pytest.approx(0.018)


def test_train_design_is_explicitly_retrospective() -> None:
    payload = json.loads((ROOT / DEFAULT_DESIGN).read_text(encoding="utf-8"))
    assert payload["status"] == "retrospective-train-design-after-exploratory-probes"
    assert "not preregistered" in payload["retrospective_disclosure"]


def test_candidate_validation_seeds_are_prereserved_but_not_train_data(design) -> None:
    assert design.validation_world_seed_candidates == tuple(range(440001, 440013))
    assert set(design.validation_world_seed_candidates).isdisjoint(design.world_seeds)
    assert design.validation_trajectory_seeds == (17, 31, 43)
    assert design.validation_observation_seeds == (107, 227)


def test_outer_selection_cannot_be_changed_by_held_out_results() -> None:
    left = ShrunkEstimatorConfig(35, 1.0, 0.5)
    right = ShrunkEstimatorConfig(60, 2.0, 0.5)
    train_folds = ((1, 2), (3, 4), (5, 6))
    metrics = {
        _config_id(left): {seed: {"search_top1_gain": 0.03} for seed in range(1, 9)},
        _config_id(right): {seed: {"search_top1_gain": 0.02} for seed in range(1, 9)},
    }
    # Seeds 7 and 8 stand in for the held-out fold.  Give the otherwise weaker
    # candidate arbitrarily good held-out values: selection must not move.
    metrics[_config_id(right)][7]["search_top1_gain"] = 1.0
    metrics[_config_id(right)][8]["search_top1_gain"] = 1.0
    assert _select_config((left, right), metrics, train_folds) == left


def test_visible_history_reference_reports_put_back_and_context_sample_sizes(design) -> None:
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    world = generator.sample_world(design.world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=design.trajectory_seeds[0],
        observation_seed=design.observation_seeds[0],
    )
    reading = evaluate_rolling_rollout(
        rollout,
        world,
        design.distribution,
        ShrunkEstimatorConfig(60, 2.0, 0.5),
    )
    assert 0.0 <= reading.put_back_visible_history_error <= 1.0
    assert reading.admitted_weekday_count > reading.admitted_weekend_count > 0
    assert reading.active_weekday_context_sample_sum > 0
    assert reading.active_weekend_context_sample_sum > 0
    assert reading.search_last_observed_normalised_path_cost > 0.0
    assert reading.search_visible_history_normalised_path_cost > 0.0


def test_formal_pooled_tail_path_cost_matches_full_reader(design) -> None:
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    world = generator.sample_world(design.world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=design.trajectory_seeds[0],
        observation_seed=design.observation_seeds[0],
    )
    frozen = ShrunkEstimatorConfig(60, 2.0, 0.5)
    slim = evaluate_rolling_rollout(
        rollout,
        world,
        design.distribution,
        frozen,
    )
    full = evaluate_rollout_v0_3(
        rollout,
        world,
        design.distribution,
        frozen=frozen,
        witness=RegimeAdaptiveWitnessConfig(
            recent_window=6,
            divergence_threshold=0.55,
            minimum_reference_observations=8,
            context_shrinkage_pseudocounts=4.0,
            owner_probability_threshold=0.5,
        ),
    )
    assert slim.search_last_observed_normalised_path_cost == pytest.approx(
        full.search_last_observed_normalised_path_cost
    )
    assert slim.search_visible_history_normalised_path_cost == pytest.approx(
        full.search_frozen_context_normalised_path_cost
    )


def test_causal_prefix_tie_break_is_available_as_report_only_sensitivity(design) -> None:
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    world = generator.sample_world(design.world_seeds[0])
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=design.trajectory_seeds[0],
        observation_seed=design.observation_seeds[0],
    )
    config = ShrunkEstimatorConfig(35, 0.0, 0.5)
    formal = evaluate_rolling_rollout(
        rollout,
        world,
        design.distribution,
        config,
    )
    causal = evaluate_rolling_rollout(
        rollout,
        world,
        design.distribution,
        config,
        tie_break_scope="causal_prefix",
    )
    assert formal.rollout_id == causal.rollout_id
    assert 0.0 <= causal.search_visible_history_error <= 1.0


def test_new_gate_module_has_no_detector_binding() -> None:
    source = (
        ROOT / "src/cpswm/system/evaluation_operations/structure_two_world_rolling_gate_v0_4.py"
    ).read_text(encoding="utf-8")
    assert "RegimeAdaptiveWitnessConfig" not in source
    assert "_WitnessEstimator" not in source
    assert "false_reset" not in source


def test_failed_detector_artifact_keeps_its_exact_execution_source() -> None:
    artifact = json.loads(
        (
            ROOT
            / "artifacts/project_two_v04_development/structure_two_world_horizon_probe_v0_3.json"
        ).read_text(encoding="utf-8")
    )
    archived = ROOT / (
        "artifacts/project_two_v04_development/source_snapshots/"
        "structure_two_world_gate_v0_3_at_horizon_probe.py"
    )
    assert (
        hashlib.sha256(archived.read_bytes()).hexdigest()
        == artifact["provenance"]["gate_source_sha256"]
    )


def test_self_rehashed_train_artifact_forgery_is_rejected_by_recomputation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authentic = json.loads((ROOT / DEFAULT_OUTPUT).read_text(encoding="utf-8"))
    forged = json.loads(json.dumps(authentic))
    forged["outer_cv_overall_world_weighted_metrics"]["search_top1_gain"] = 999.0
    unsigned = dict(forged)
    unsigned.pop("content_sha256", None)
    forged["content_sha256"] = content_sha256(unsigned)
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged), encoding="utf-8")
    monkeypatch.setattr(
        rolling,
        "run_rolling_train_outer_cv_gate",
        lambda *, repository_root: authentic,
    )
    with pytest.raises(ValueError, match="deterministic recomputation"):
        rolling.verify_rolling_train_gate_report(
            path,
            repository_root=ROOT,
        )
