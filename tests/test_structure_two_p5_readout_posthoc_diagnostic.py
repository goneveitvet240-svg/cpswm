from __future__ import annotations

from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    CLAIM_BOUNDARY,
    PROTOCOL_ID,
    _evaluate_posthoc_episode,
    _load_posthoc_config,
    selected_v0_6_action_readout,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _learned_training_material,
    _load_config,
    _validation_selection,
)
from cpswm.system.prototype_spine import ActionReadout

ROOT = Path(__file__).resolve().parents[1]


def test_posthoc_config_discloses_opened_test_and_forbids_positive_receipt() -> None:
    config = _load_posthoc_config(ROOT)
    disclosure = config["test_reuse_disclosure"]
    assert config["protocol_id"] == PROTOCOL_ID
    assert config["claim_boundary"] == CLAIM_BOUNDARY
    assert disclosure["test_split_previously_opened"] is True
    assert disclosure["fresh_preregistered_death_test"] is False
    assert disclosure["may_issue_positive_scientific_receipt"] is False


def test_corrected_readout_is_the_previously_selected_v0_6_configuration() -> None:
    readout = selected_v0_6_action_readout()
    assert readout.readout is ActionReadout.DUAL_TIMESCALE_REVERSIBLE
    assert readout.component_weights == {
        "hybrid_alpha": 0.0,
        "regime_local": 0.1,
        "surviving": 0.2,
        "fast_action": 0.7,
    }
    assert readout.owner_mass_floor == 0.5
    assert readout.fast_owner_mass_floor == 0.5
    assert readout.recency_half_life == 1.0


def test_one_episode_removes_uniform_readout_after_sequential_prior_fix() -> None:
    retained_config = _load_config(ROOT)
    dataset = (
        D0SyntheticReplayExperimentConfig.load(ROOT / Path(retained_config["dataset_source"]))
        .build_adapter()
        .build()
    )
    material = _learned_training_material(dataset)
    _selection, model, smoothing, amg_parameter = _validation_selection(
        dataset, retained_config, material
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[1]
    metrics, diagnostic = _evaluate_posthoc_episode(
        dataset,
        episode,
        learned_model=model,
        material=material,
        learned_smoothing=smoothing,
        amg_parameter=amg_parameter,
    )
    direct = next(item for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5)
    assert diagnostic["owner_habit_posterior_nonuniform_step_count"] > 0
    assert diagnostic["owner_habit_unique_distribution_count"] > 1
    assert diagnostic["corrected_put_back_choice_changes_from_v0_1_uniform_tie"] > 0
    assert direct.full_p5_transition_count == sum(step.after is not None for step in episode.steps)
    assert direct.full_p5_transition_count == direct.all_seven_primary_trace_count
