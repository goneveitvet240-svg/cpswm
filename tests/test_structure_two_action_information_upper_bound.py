from __future__ import annotations

import json
from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.evaluation_operations.structure_two_action_information_upper_bound import (
    FIXED_OPERATOR_ARMS,
    InformationArm,
    _collect_trace,
    _full_action_oracle,
    _instantaneous_regret,
    _operator_selector_oracle,
    _top2_readout_oracle,
    _transition_state,
    verify_action_information_upper_bound,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    DEFAULT_MANIFEST,
    _dataset,
    load_frozen_neighbor_design,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]


def test_top2_oracle_cannot_recover_target_outside_top2() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(619991,),
        max_steps=design.max_steps,
        split_label="action-information-top2-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    truths = tuple(
        dataset.truth_for(episode.episode_id).truth_by_step[step.step_id] for step in episode.steps
    )
    locations = tuple(
        dict.fromkeys(
            (
                truths[0].true_location,
                truths[0].true_owner_habit_location,
                *(step.source_location_id for step in episode.steps if step.source_location_id),
                content_uuid("action-information-test", "outside-top2"),
            )
        )
    )
    assert len(locations) >= 3
    outside = locations[2]
    base = (
        _Prediction(
            put_back=locations[0],
            search_order=(locations[0], locations[1], outside),
            unknown_probability=0.0,
        ),
    )
    truth = truths[0].model_copy(
        update={"true_location": outside, "true_owner_habit_location": outside}
    )

    predictions, interventions, support = _top2_readout_oracle(base, (truth,))

    assert predictions[0] == base[0]
    assert interventions == 0
    assert not support


def test_operator_selector_uses_fixed_tie_priority_and_lowest_regret() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(619992,),
        max_steps=design.max_steps,
        split_label="action-information-selector-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    truth = dataset.truth_for(episode.episode_id).truth_by_step[episode.steps[0].step_id]
    wrong = next(
        step.source_location_id
        for step in episode.steps
        if step.source_location_id not in {truth.true_location, truth.true_owner_habit_location}
    )
    correct = _Prediction(
        put_back=truth.true_owner_habit_location,
        search_order=(truth.true_location,),
        unknown_probability=0.0,
    )
    bad = _Prediction(put_back=wrong, search_order=(wrong,), unknown_probability=0.0)
    traces = {arm: (bad,) for arm in FIXED_OPERATOR_ARMS}
    traces[InformationArm.SEQUENTIAL] = (correct,)

    selected, counts, interventions = _operator_selector_oracle(traces, (truth,))

    assert selected == (correct,)
    assert counts == {InformationArm.SEQUENTIAL.value: 1}
    assert interventions == 1
    assert _instantaneous_regret(selected[0], truth) == 0

    tie_selected, tie_counts, tie_interventions = _operator_selector_oracle(
        {arm: (correct,) for arm in FIXED_OPERATOR_ARMS},
        (truth,),
    )
    assert tie_selected == (correct,)
    assert tie_counts == {InformationArm.DETERMINISTIC_TRANSITION.value: 1}
    assert tie_interventions == 0


def test_true_actor_oracle_shares_visible_stream_and_reads_only_per_step_actor_truth() -> None:
    design = load_frozen_neighbor_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(619993,),
        max_steps=design.max_steps,
        split_label="action-information-actor-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    ordinary = _collect_trace(
        _transition_state(
            dataset,
            episode,
            family,
            profile="responsive",
            conflict_transition=True,
            ledger="none",
        ),
        episode,
    )
    actor_oracle = _collect_trace(
        _transition_state(
            dataset,
            episode,
            family,
            profile="responsive",
            conflict_transition=True,
            ledger="none",
            true_actor_oracle=True,
        ),
        episode,
    )

    assert actor_oracle.consumed_visible_stream_hash == ordinary.consumed_visible_stream_hash
    assert 0 < actor_oracle.truth_read_count <= len(episode.steps)
    truths = tuple(
        dataset.truth_for(episode.episode_id).truth_by_step[step.step_id] for step in episode.steps
    )
    full_oracle = _full_action_oracle(truths)
    assert all(
        _instantaneous_regret(prediction, truth) == 0
        for prediction, truth in zip(full_oracle, truths, strict=True)
    )


def test_verifier_accepts_json_list_form_of_tuple_payload(tmp_path: Path) -> None:
    payload = {
        "protocol": "structure-two-action-information-upper-bound@0.1",
        "sealed_holdout_opened": False,
        "confidence_interval_95": (-0.2, -0.1),
    }
    payload["content_sha256"] = content_sha256(payload)
    artifact = tmp_path / "diagnostic.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    verified = verify_action_information_upper_bound(
        artifact,
        repository_root=ROOT,
        recompute=False,
    )

    assert verified["confidence_interval_95"] == [-0.2, -0.1]
