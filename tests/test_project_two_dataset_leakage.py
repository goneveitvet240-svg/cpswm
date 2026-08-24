from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    ProjectTwoReplayDatasetManifest,
    reject_truth_leakage,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)


def test_truth_leakage_aliases_are_rejected_recursively():
    for key in ("true_actor", "true_mechanism", "true_location", "latent_state", "oracle_actor"):
        with pytest.raises(ValueError, match="truth leakage"):
            reject_truth_leakage({"visible": {key: "forbidden"}})


def test_cross_split_household_scene_and_family_leakage_are_rejected():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=2
    ).build()
    first, second = dataset.manifest.entries
    leaked = second.model_copy(update={"household_id": first.household_id})
    with pytest.raises(ValidationError, match="household_id leakage"):
        ProjectTwoReplayDatasetManifest(
            dataset_id=uuid4(),
            dataset_version="x@1",
            created_at=datetime.now(UTC),
            entries=(first, leaked),
        )


def test_unknown_actor_and_mechanism_are_not_forced_to_known_labels():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    steps = [step for episode in dataset.episodes for step in episode.steps]
    assert any(
        step.actor_evidence is None or "unknown_actor" in step.actor_evidence.actor_posterior
        for step in steps
    )
    assert any(step.mechanism_evidence is None for step in steps)


def test_same_visible_replay_can_be_dispatched_without_truth():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=3
    ).build()
    episode = dataset.episodes[0]
    payloads = [episode.model_dump(mode="python") for _method in range(8)]
    assert all(payload == payloads[0] for payload in payloads)
    assert "true_actor" not in repr(payloads)


def test_visible_content_hash_rejects_post_adapter_tampering():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=3
    ).build()
    episode = dataset.episodes[0]
    step = episode.steps[0].model_copy(update={"object_category": "tampered"})
    changed = episode.model_copy(update={"steps": (step, *episode.steps[1:])})
    with pytest.raises(ValidationError, match="visible replay content hash"):
        ProjectTwoReplayDataset(
            manifest=dataset.manifest,
            episodes=(changed, *dataset.episodes[1:]),
            evaluator_store=dataset.evaluator_store,
        )
