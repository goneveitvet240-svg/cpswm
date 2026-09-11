from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    ProjectTwoDataMaturity,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
    ReplayContractCompatibility,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    ProjectTwoReplayGateError,
    audit_project_two_replay,
    enforce_project_two_replay_gate,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
    D1SimulatorAnnotatedReplayAdapter,
    D2RealPerceptionReplayAdapter,
)
from cpswm.system.reproducibility import content_sha256


def _dataset():
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=5
    ).build()


def test_d0_contract_supports_disjoint_train_validation_and_test_splits():
    dataset = D0SyntheticOracleReplayAdapter(
        train_seeds=(7,),
        validation_seeds=(101,),
        test_seeds=(211,),
        max_steps_per_episode=2,
    ).build()

    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)) == 1
    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)) == 1
    assert len(dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)) == 1


def test_d0_contract_rejects_overlapping_learning_splits():
    with pytest.raises(ValueError, match="train and validation seeds must be disjoint"):
        D0SyntheticOracleReplayAdapter(
            train_seeds=(101,), validation_seeds=(101,), test_seeds=(211,)
        )


def test_d0_contract_keeps_truth_in_separate_store():
    dataset = _dataset()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    assert not hasattr(episode, "truth_by_step")
    assert dataset.truth_for(episode.episode_id).truth_by_step
    assert "true_actor" not in episode.model_dump_json()


def test_d0_d1_d2_use_same_replay_contract_evaluator_and_metric_definition():
    d0 = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=2
    ).build()
    scorer = ProjectTwoActionBenchmarkV02()
    adapters = (
        (D1SimulatorAnnotatedReplayAdapter, ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY),
        (D2RealPerceptionReplayAdapter, ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY),
    )
    metric_definitions = []
    for adapter_type, maturity in adapters:
        version = f"typed-fixture-{maturity.value}@0.2"
        episodes = tuple(
            item.model_copy(
                update={
                    "maturity": maturity,
                    "source_evidence_maturity": maturity,
                    "contract_compatibility": ReplayContractCompatibility.FULL_REPLAY_CONTRACT,
                    "dataset_version": version,
                }
            )
            for item in d0.episodes
        )
        evaluator_store = []
        for item in episodes:
            envelope = d0.truth_for(item.episode_id).model_copy(update={"dataset_version": version})
            payload = envelope.model_dump(mode="python", exclude={"evaluator_content_hash"})
            evaluator_store.append(
                envelope.model_copy(update={"evaluator_content_hash": content_sha256(payload)})
            )
        dataset = adapter_type(
            dataset_version=version,
            episodes=episodes,
            evaluator_store=tuple(evaluator_store),
            adapter_provenance="test typed replay; not an external dataset claim",
        ).build()
        assert all(type(item) is type(d0.episodes[0]) for item in dataset.episodes)
        metric = scorer._evaluate_episode(
            dataset,
            dataset.episodes[0],
            ProjectTwoActionMethod.ORACLE,
            {},
        )
        metric_definitions.append(tuple(type(metric).model_fields))
    assert len(set(metric_definitions)) == 1


def test_contract_compatibility_cannot_promote_d0_source_to_d1_evidence():
    episode = _dataset().episodes[0]
    with pytest.raises(ValidationError, match="transition is not allowed"):
        type(episode).model_validate(
            {
                **episode.model_dump(),
                "maturity": ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
                "source_evidence_maturity": ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
                "contract_compatibility": ReplayContractCompatibility.FULL_REPLAY_CONTRACT,
            }
        )


def test_d0_development_fixture_cannot_be_relabelled_as_synthetic_oracle():
    episode = _dataset().episodes[0]
    with pytest.raises(ValidationError, match="transition is not allowed"):
        ProjectTwoReplayEpisode.model_validate(
            {
                **episode.model_dump(mode="python"),
                "source_evidence_maturity": ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
                "maturity": ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
            }
        )


def test_full_contract_compatibility_cannot_be_self_declared_without_unified_evidence():
    episode = _dataset().episodes[0]
    legacy_steps = tuple(
        step.model_copy(update={"unified_evidence": None}) for step in episode.steps
    )
    with pytest.raises(ValidationError, match="must be derived"):
        ProjectTwoReplayEpisode.model_validate(
            {
                **episode.model_dump(mode="python"),
                "steps": legacy_steps,
                "contract_compatibility": ReplayContractCompatibility.FULL_REPLAY_CONTRACT,
            }
        )


def test_manifest_full_contract_requires_bound_formal_evidence_ids():
    entry = _dataset().manifest.entries[0]
    with pytest.raises(ValidationError, match="derived from formal evidence ids"):
        type(entry).model_validate(
            {
                **entry.model_dump(mode="python"),
                "unified_evidence_record_ids": (),
                "contract_compatibility": ReplayContractCompatibility.FULL_REPLAY_CONTRACT,
            }
        )


def test_attempted_and_observed_destination_are_not_interchangeable():
    step = _dataset().episodes[0].steps[0]
    other = uuid4()
    with pytest.raises(ValidationError, match="observed destination"):
        ProjectTwoReplayStep.model_validate(
            {**step.model_dump(), "observed_destination_location_id": other}
        )


def test_duplicate_feedback_record_is_rejected():
    dataset = _dataset()
    episode = dataset.episodes[0]
    source = next(step for step in episode.steps if step.execution_feedback)
    duplicate = source.model_copy(
        update={
            "step_id": episode.steps[-1].step_id,
            "timestamp": episode.steps[-1].timestamp,
            "valid_time": episode.steps[-1].valid_time,
            "unified_evidence": episode.steps[-1].unified_evidence,
            "observation_opportunity": episode.steps[-1].observation_opportunity,
        }
    )
    with pytest.raises(ValidationError, match="duplicate execution feedback"):
        type(episode).model_validate(
            {**episode.model_dump(), "steps": (*episode.steps[:-1], duplicate)}
        )


def test_delayed_feedback_keeps_original_time_order():
    dataset = _dataset()
    episode = dataset.episodes[0]
    timestamps = [step.timestamp for step in episode.steps]
    assert timestamps == sorted(timestamps)
    assert any(
        feedback.metadata.recorded_time > step.timestamp
        for step in episode.steps
        for feedback in step.execution_feedback
    )


def test_quality_report_declares_missing_real_fields_without_deleting_capability():
    report = audit_project_two_replay(_dataset())
    assert report.missingness_counts["real_sensor_calibration"] > 0
    assert report.delayed_feedback_count > 0
    assert "source_label_leakage" in report.checks_passed


def test_d0_replay_passes_hard_safety_and_content_gate():
    report = enforce_project_two_replay_gate(_dataset())
    assert report.ready
    assert not report.failures
    assert "visible_content_integrity" in report.checks_passed
    assert "evaluator_content_integrity" in report.checks_passed


def test_quality_gate_is_not_a_cosmetic_list_of_check_names():
    dataset = _dataset()
    episode = dataset.episodes[0]
    broken = episode.model_copy(update={"field_availability": {}})
    tampered = dataset.model_copy(update={"episodes": (broken, *dataset.episodes[1:])})
    with pytest.raises(
        ProjectTwoReplayGateError,
        match=r"visible replay content hash mismatch|missingness declaration",
    ):
        enforce_project_two_replay_gate(tampered)


def test_dataset_gate_revalidates_model_copy_forgery() -> None:
    dataset = _dataset()
    entry = dataset.manifest.entries[0]
    forged_entry = entry.model_copy(update={"visible_content_hash": "0" * 64})
    forged_manifest = dataset.manifest.model_copy(
        update={"entries": (forged_entry, *dataset.manifest.entries[1:])}
    )
    forged = dataset.model_copy(update={"manifest": forged_manifest})

    with pytest.raises(
        ProjectTwoReplayGateError,
        match="visible replay content hash mismatch",
    ):
        enforce_project_two_replay_gate(forged)
