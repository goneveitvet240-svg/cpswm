"""Habitual location estimation head built from RLS updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import numpy as np

from .core import RecursiveLeastSquares, RLSConfig

LocationEmbedding = dict[UUID, np.ndarray]
LocationScores = dict[UUID, float]


@dataclass(frozen=True)
class RLSHabitSample:
    """One online habit-learning sample for one object."""

    object_instance_id: UUID
    actor_id: str
    context_features: np.ndarray
    target_location_id: UUID | None
    candidate_locations: tuple[UUID, ...]
    gate: float = 1.0
    forgetting_factor: float | None = None
    regime_id: str = "stable"


class _LocationSpecificRLS:
    """One binary RLS model per object-actor-regime-location tuple."""

    def __init__(
        self,
        *,
        feature_dim: int,
        forgetting_factor: float,
        ridge: float,
        prior_scale: float,
    ) -> None:
        self.model = RecursiveLeastSquares(
            RLSConfig(
                feature_dim=feature_dim,
                forgetting_factor=forgetting_factor,
                ridge=ridge,
                prior_scale=prior_scale,
            )
        )

    def update(
        self,
        x: np.ndarray,
        y: float,
        *,
        gate: float,
        forgetting_factor: float | None,
    ) -> None:
        self.model.update(x, y, gate=gate, forgetting_factor=forgetting_factor)


class RLSHabitScoreHead:
    """RLS-parameterized habit prior over locations.

    This module keeps online statistics and is designed to replace only part of the
    habit branch, while keeping full identity/event reasoning in upper layers.
    """

    def __init__(
        self,
        *,
        context_feature_dim: int,
        location_embedding_dim: int,
        forgetting_factor: float = 1.0,
        ridge: float = 1e-6,
        prior_scale: float = 1e4,
        model_version: str = "rls-habit-head@0.1",
    ) -> None:
        if context_feature_dim < 0:
            raise ValueError("context_feature_dim must be non-negative")
        if location_embedding_dim < 0:
            raise ValueError("location_embedding_dim must be non-negative")

        self.context_feature_dim = context_feature_dim
        self.location_embedding_dim = location_embedding_dim
        self.model_version = model_version
        self.forgetting_factor = forgetting_factor
        self.ridge = ridge
        self.prior_scale = prior_scale
        if self.context_feature_dim == 0 and self.location_embedding_dim == 0:
            raise ValueError("context_feature_dim and location_embedding_dim cannot both be zero")
        self._models: dict[tuple[UUID, str, str, UUID], _LocationSpecificRLS] = {}

    @property
    def feature_dim(self) -> int:
        return self.context_feature_dim + self.location_embedding_dim

    def _model_key(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        regime_id: str,
        location_id: UUID,
    ) -> tuple[UUID, str, str, UUID]:
        return (object_instance_id, actor_id, regime_id, location_id)

    def _build_features(
        self,
        context_features: np.ndarray,
        location_embedding: np.ndarray,
    ) -> np.ndarray:
        context = np.asarray(context_features, dtype=float)
        location = np.asarray(location_embedding, dtype=float)
        if context.ndim != 1 or location.ndim != 1:
            raise ValueError("context and location features must be vectors")
        if context.shape[0] != self.context_feature_dim:
            raise ValueError("context feature dimension mismatch")
        if location.shape[0] != self.location_embedding_dim:
            raise ValueError("location feature dimension mismatch")
        return np.concatenate([context, location], axis=0)

    def _get_model(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        regime_id: str,
        location_id: UUID,
        create: bool = True,
    ) -> _LocationSpecificRLS | None:
        key = self._model_key(
            object_instance_id=object_instance_id,
            actor_id=actor_id,
            regime_id=regime_id,
            location_id=location_id,
        )
        if not create:
            return self._models.get(key)
        model = self._models.get(key)
        if model is None:
            model = _LocationSpecificRLS(
                feature_dim=self.feature_dim,
                forgetting_factor=self.forgetting_factor,
                ridge=self.ridge,
                prior_scale=self.prior_scale,
            )
            self._models[key] = model
        return model

    def update(
        self,
        sample: RLSHabitSample,
        location_embeddings: LocationEmbedding,
        *,
        include_negative_locations: bool = True,
    ) -> None:
        """Apply one sample as one-vs-rest updates.

        Every candidate location is explicitly updated as positive/negative so
        the current model can separate multiple likely slots.
        """

        if not sample.candidate_locations:
            return
        if sample.target_location_id is None:
            return
        if sample.target_location_id not in sample.candidate_locations:
            raise ValueError("target location must be part of candidate set")

        gate = float(sample.gate)
        if gate <= 0.0:
            return

        candidate_locations = sample.candidate_locations
        if not include_negative_locations:
            candidate_locations = (sample.target_location_id,)

        for candidate_id in candidate_locations:
            if candidate_id not in location_embeddings:
                raise ValueError(f"missing embedding for location {candidate_id}")
            features = self._build_features(
                context_features=sample.context_features,
                location_embedding=location_embeddings[candidate_id],
            )
            target = 1.0 if candidate_id == sample.target_location_id else 0.0
            model = self._get_model(
                object_instance_id=sample.object_instance_id,
                actor_id=sample.actor_id,
                regime_id=sample.regime_id,
                location_id=candidate_id,
            )
            if model is None:
                raise RuntimeError("RLS model creation unexpectedly failed")
            model.update(
                features,
                target,
                gate=gate,
                forgetting_factor=sample.forgetting_factor,
            )

    def score_candidates(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        regime_id: str,
        context_features: np.ndarray,
        candidate_locations: tuple[UUID, ...],
        location_embeddings: LocationEmbedding,
        apply_sigmoid: bool = False,
    ) -> LocationScores:
        """Score each candidate location under current RLS state.

        The underlying model is a recursive least-squares regressor already
        fitted to ``{0, 1}`` targets, so its raw output *is* the calibrated
        score.  Squashing it again compresses a perfectly learned score from
        ``1.0`` to ``0.731`` and a perfectly rejected one from ``0.0`` to
        ``0.5``, which pins any residual read as ``1 - score`` inside
        ``[0.269, 0.5]`` -- a correctly predicted location can then never
        report zero error.  ``apply_sigmoid`` therefore defaults to ``False``.

        Pass ``apply_sigmoid=True`` only to reproduce the pre-fix wiring; it is
        kept so historical runs stay comparable, not because a second squash is
        ever the right readout.
        """

        if not candidate_locations:
            return {}

        scores: LocationScores = {}
        for candidate_id in candidate_locations:
            if candidate_id not in location_embeddings:
                raise ValueError(f"missing embedding for location {candidate_id}")
            features = self._build_features(
                context_features=context_features,
                location_embedding=location_embeddings[candidate_id],
            )
            model = self._get_model(
                object_instance_id=object_instance_id,
                actor_id=actor_id,
                regime_id=regime_id,
                location_id=candidate_id,
                create=False,
            )
            score = 0.0 if model is None else model.model.predict(features)
            if apply_sigmoid:
                score = 1.0 / (1.0 + np.exp(-score))
            scores[candidate_id] = float(score)
        return scores

    def snapshot(self) -> dict[str, Any]:
        state: dict[tuple[UUID, str, str, UUID], dict[str, Any]] = {}
        for key, model in self._models.items():
            state[key] = model.model.snapshot()
        return {
            "models": state,
            "context_feature_dim": self.context_feature_dim,
            "location_embedding_dim": self.location_embedding_dim,
            "model_version": self.model_version,
        }

    def restore(self, state: dict[str, Any]) -> None:
        if state.get("context_feature_dim") != self.context_feature_dim:
            raise ValueError("restore context_feature_dim mismatch")
        if state.get("location_embedding_dim") != self.location_embedding_dim:
            raise ValueError("restore location_embedding_dim mismatch")
        if state.get("model_version") != self.model_version:
            raise ValueError("restore model version mismatch")

        self._models.clear()
        model_snapshots = state["models"]
        if not isinstance(model_snapshots, dict):
            raise ValueError("restore models must be a dict")
        for key, model_state in model_snapshots.items():
            if not isinstance(key, tuple) or len(key) != 4:
                raise ValueError(
                    "restore expects model keys of "
                    "(object_instance_id, actor_id, regime_id, location_id)"
                )
            object_instance_id, actor_id, regime_id, location_id = key
            if not isinstance(object_instance_id, UUID):
                raise ValueError("restore key must contain UUID object_instance_id and location_id")
            if not isinstance(location_id, UUID):
                raise ValueError("restore key must contain UUID object_instance_id and location_id")
            if not isinstance(actor_id, str) or not isinstance(regime_id, str):
                raise ValueError("restore key must contain textual actor_id and regime_id")
            self._models[key] = _LocationSpecificRLS(
                feature_dim=self.feature_dim,
                forgetting_factor=self.forgetting_factor,
                ridge=self.ridge,
                prior_scale=self.prior_scale,
            )
            self._models[key].model.restore(model_state)
