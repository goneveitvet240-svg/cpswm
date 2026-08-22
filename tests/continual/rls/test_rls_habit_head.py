"""Tests for the RLS habit score head."""

from __future__ import annotations

from uuid import UUID, uuid4

import numpy as np

from cpswm.system.continual.rls import (
    RLSHabitSample,
    RLSHabitScoreHead,
)


def _sample_payload(
    *,
    target_location_id: UUID,
    candidates: tuple[UUID, ...],
) -> tuple[RLSHabitSample, dict[UUID, np.ndarray], dict[UUID, np.ndarray]]:
    context_features = np.array([0.6], dtype=float)
    embeddings = {
        candidates[0]: np.array([0.9], dtype=float),
        candidates[1]: np.array([0.1], dtype=float),
    }
    sample = RLSHabitSample(
        object_instance_id=uuid4(),
        actor_id="alice",
        context_features=context_features,
        target_location_id=target_location_id,
        candidate_locations=candidates,
        gate=1.0,
    )
    return sample, embeddings, embeddings


def test_habit_head_updates_and_scores_candidates():
    head = RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=1)
    candidates = (uuid4(), uuid4())
    sample, embeddings, _ = _sample_payload(target_location_id=candidates[0], candidates=candidates)

    head.update(sample, embeddings)
    scores = head.score_candidates(
        object_instance_id=sample.object_instance_id,
        actor_id=sample.actor_id,
        regime_id=sample.regime_id,
        context_features=sample.context_features,
        candidate_locations=candidates,
        location_embeddings=embeddings,
        apply_sigmoid=True,
    )

    assert set(scores.keys()) == set(candidates)
    assert 0.0 <= scores[candidates[0]] <= 1.0
    assert 0.0 <= scores[candidates[1]] <= 1.0
    assert scores[candidates[0]] > scores[candidates[1]]


def test_habit_head_restore_roundtrips_model_state():
    head = RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=1)
    candidates = (uuid4(), uuid4())
    sample, embeddings, _ = _sample_payload(target_location_id=candidates[0], candidates=candidates)
    head.update(sample, embeddings)
    state = head.snapshot()

    after = RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=1)
    after.restore(state)
    scores_before = head.score_candidates(
        object_instance_id=sample.object_instance_id,
        actor_id=sample.actor_id,
        regime_id=sample.regime_id,
        context_features=sample.context_features,
        candidate_locations=candidates,
        location_embeddings=embeddings,
    )
    scores_after = after.score_candidates(
        object_instance_id=sample.object_instance_id,
        actor_id=sample.actor_id,
        regime_id=sample.regime_id,
        context_features=sample.context_features,
        candidate_locations=candidates,
        location_embeddings=embeddings,
    )

    assert scores_before == scores_after


def test_score_without_previous_updates_does_not_create_models():
    head = RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=1)
    candidate_a = uuid4()
    candidate_b = uuid4()
    context_features = np.array([0.4], dtype=float)
    embeddings = {
        candidate_a: np.array([0.8], dtype=float),
        candidate_b: np.array([0.2], dtype=float),
    }

    scores = head.score_candidates(
        object_instance_id=uuid4(),
        actor_id="alice",
        regime_id="stable",
        context_features=context_features,
        candidate_locations=(candidate_a, candidate_b),
        location_embeddings=embeddings,
        apply_sigmoid=True,
    )

    assert scores == {candidate_a: 0.5, candidate_b: 0.5}
    assert head.snapshot()["models"] == {}
