from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    AMGLocationAdapter,
    CIAVConsumptionReceipt,
    DirectP5LocationAdapter,
    LearnedTwoStageLocationAdapter,
    _episode_schedule_commitment,
    _evaluate_matched_test_episode,
    _learned_training_material,
    _load_config,
    _packet_for_step,
    _validation_selection,
    verify_matched_consumption,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fitted_case() -> tuple:
    config = _load_config(ROOT)
    dataset_config = D0SyntheticReplayExperimentConfig.load(ROOT / Path(config["dataset_source"]))
    dataset = dataset_config.build_adapter().build()
    material = _learned_training_material(dataset)
    selection, model, smoothing, amg_parameter = _validation_selection(dataset, config, material)
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    return dataset, material, selection, model, smoothing, amg_parameter, episode


def test_a1_schedule_commitment_excludes_realized_outcomes(fitted_case: tuple) -> None:
    _dataset, _material, _selection, _model, _smoothing, _amg, episode = fitted_case
    commitment = _episode_schedule_commitment(episode)
    assert len(commitment) == 64
    step = episode.steps[0]
    packet = _packet_for_step(episode, step, schedule_commitment_sha256=commitment)
    assert packet.schedule_commitment_sha256 == commitment
    assert packet.evaluator_truth_release_phase == "after_typed_actions_committed"


def test_all_three_adapters_consume_identical_packet_and_emit_typed_posteriors(
    fitted_case: tuple,
) -> None:
    dataset, material, _selection, model, smoothing, amg_parameter, episode = fitted_case
    del dataset
    states = (
        DirectP5LocationAdapter(episode),
        LearnedTwoStageLocationAdapter(
            episode,
            model=model,
            location_successes=material.location_successes,
            location_totals=material.location_totals,
            smoothing=smoothing,
        ),
        AMGLocationAdapter(episode, parameter=amg_parameter),
    )
    observed_index, observed_step = next(
        (index, step) for index, step in enumerate(episode.steps) if step.after is not None
    )
    commitment = _episode_schedule_commitment(episode)
    packet = _packet_for_step(episode, observed_step, schedule_commitment_sha256=commitment)
    receipts = tuple(
        state.consume_matched_ciav_packet(packet, observed_step, step_index=observed_index)
        for state in states
    )
    verify_matched_consumption(receipts)
    assert tuple(receipt.arm for receipt in receipts) == tuple(P5ComparisonArm)
    for state in states:
        posterior = state.predict_location_posteriors(packet)
        assert posterior.source_visible_step_sha256 == packet.visible_step_sha256
        assert posterior.truth_visible_before_action_commit is False


def test_resigned_cross_arm_packet_substitution_is_rejected(fitted_case: tuple) -> None:
    _dataset, material, _selection, model, smoothing, amg_parameter, episode = fitted_case
    states = (
        DirectP5LocationAdapter(episode),
        LearnedTwoStageLocationAdapter(
            episode,
            model=model,
            location_successes=material.location_successes,
            location_totals=material.location_totals,
            smoothing=smoothing,
        ),
        AMGLocationAdapter(episode, parameter=amg_parameter),
    )
    observed_index, step = next(
        (index, item) for index, item in enumerate(episode.steps) if item.after is not None
    )
    packet = _packet_for_step(
        episode,
        step,
        schedule_commitment_sha256=_episode_schedule_commitment(episode),
    )
    receipts = [
        state.consume_matched_ciav_packet(packet, step, step_index=observed_index)
        for state in states
    ]
    forged = receipts[1].model_dump(mode="python")
    forged["realized_observation_sha256"] = "0" * 64
    unsigned = {key: value for key, value in forged.items() if key != "receipt_sha256"}
    forged["receipt_sha256"] = content_sha256(unsigned)
    receipts[1] = CIAVConsumptionReceipt.model_validate(forged)
    with pytest.raises(ValueError, match="differs"):
        verify_matched_consumption(receipts)


def test_negative_observations_are_consumed_without_fabricating_transitions(
    fitted_case: tuple,
) -> None:
    dataset, material, _selection, model, smoothing, amg_parameter, episode = fitted_case
    metrics = _evaluate_matched_test_episode(
        dataset,
        episode,
        learned_model=model,
        material=material,
        learned_smoothing=smoothing,
        amg_parameter=amg_parameter,
    )
    direct = next(item for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5)
    observed = sum(step.after is not None for step in episode.steps)
    missing = len(episode.steps) - observed
    assert direct.full_p5_transition_count == observed
    assert direct.all_seven_primary_trace_count == observed
    assert direct.negative_ciav_opceu_closure_count == missing
    assert direct.transition_dependent_no_new_transition_count == missing
    assert direct.full_p5_transition_count + direct.negative_ciav_opceu_closure_count == 32


def test_validation_selection_never_reads_test_episode_ids(fitted_case: tuple) -> None:
    dataset, _material, selection, _model, _smoothing, _amg, _episode = fitted_case
    assert selection["test_episode_ids_seen"] == []
    validation_ids = {
        str(item.episode_id) for item in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    }
    test_ids = {
        str(item.episode_id) for item in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    }
    assert set(selection["validation_episode_ids"]) == validation_ids
    assert not set(selection["validation_episode_ids"]) & test_ids


def test_packet_tampering_fails_even_when_outer_result_is_copied(fitted_case: tuple) -> None:
    _dataset, _material, _selection, _model, _smoothing, _amg, episode = fitted_case
    step = episode.steps[0]
    packet = _packet_for_step(
        episode,
        step,
        schedule_commitment_sha256=_episode_schedule_commitment(episode),
    )
    forged = copy.deepcopy(packet.model_dump(mode="python"))
    forged["visible_step_sha256"] = "0" * 64
    unsigned = {key: value for key, value in forged.items() if key != "packet_sha256"}
    forged["packet_sha256"] = content_sha256(unsigned)
    with pytest.raises(ValueError, match="realized observation hash mismatch"):
        type(packet).model_validate(forged)
