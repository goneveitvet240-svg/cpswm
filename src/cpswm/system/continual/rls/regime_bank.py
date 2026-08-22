"""Regime-partitioned banks for RLS habit models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

import numpy as np
from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.reproducibility import content_sha256

from .habit_head import RLSHabitSample, RLSHabitScoreHead

RegimeHeadFactory = Callable[[], RLSHabitScoreHead]


class RLSRegimeSwitchEvent(ContractModel):
    """Record a detected habit-regime switch for one object / actor pair."""

    object_instance_id: UUID
    actor_id: str = Field(min_length=1)
    from_regime_id: str = Field(min_length=1)
    to_regime_id: str = Field(min_length=1)
    event_time: datetime
    sequence: int = Field(default=0, ge=0)
    event_id: UUID = Field(default_factory=uuid4)
    event_signature: str | None = Field(default=None, min_length=1)

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def bind_signature(self) -> RLSRegimeSwitchEvent:
        payload = self.model_dump(mode="python", exclude={"event_signature"})
        expected_signature = content_sha256(payload)
        if self.event_signature is None:
            object.__setattr__(self, "event_signature", expected_signature)
            return self
        if self.event_signature != expected_signature:
            raise ValueError("RLSRegimeSwitchEvent.event_signature does not match event payload")
        return self


class RLSRegimeBank:
    """Route samples and queries to regime-specific RLS heads."""

    def __init__(
        self,
        head_factory: RegimeHeadFactory,
        *,
        default_regime: str = "stable",
    ) -> None:
        if not default_regime.strip():
            raise ValueError("default_regime must be non-empty")

        self._head_factory = head_factory
        self._default_regime = default_regime
        self._heads: dict[str, RLSHabitScoreHead] = {}
        self._active_regime: dict[tuple[UUID, str], str] = {}
        self._last_switch_time: dict[tuple[UUID, str], tuple[datetime, int]] = {}
        self._processed_switch_event_ids: dict[tuple[UUID, str], set[UUID]] = {}
        self._processed_switch_signatures: dict[tuple[UUID, str], set[str]] = {}

    def _head(self, regime_id: str) -> RLSHabitScoreHead:
        head = self._heads.get(regime_id)
        if head is None:
            head = self._head_factory()
            self._heads[regime_id] = head
        return head

    def _head_if_exists(self, regime_id: str) -> RLSHabitScoreHead | None:
        return self._heads.get(regime_id)

    def _validate_regime_switch_time(
        self,
        *,
        stream_key: tuple[UUID, str],
        event_time: datetime,
        sequence: int,
    ) -> None:
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("regime switch event_time must be timezone-aware")
        if sequence < 0:
            raise ValueError("regime switch sequence must be non-negative")
        last_switch_time = self._last_switch_time.get(stream_key)
        if last_switch_time is None:
            return
        previous_time, previous_sequence = last_switch_time
        if event_time < previous_time:
            raise ValueError(
                "regime switch events must be strictly increasing in time "
                f"(last={previous_time.isoformat()}, event={event_time.isoformat()})"
            )
        if event_time == previous_time and sequence <= previous_sequence:
            raise ValueError(
                "regime switch sequence must strictly increase when event time is identical "
                f"(last_sequence={previous_sequence}, event_sequence={sequence})"
            )

    def _validate_regime_switch_identity(
        self,
        *,
        stream_key: tuple[UUID, str],
        event_id: UUID,
        event_signature: str,
    ) -> None:
        processed_event_ids = self._processed_switch_event_ids.get(stream_key, set())
        processed_signatures = self._processed_switch_signatures.get(stream_key, set())
        if event_id in processed_event_ids:
            raise ValueError("regime switch event_id already processed")
        if event_signature in processed_signatures:
            raise ValueError("regime switch event_signature already processed")

    def active_regime(self, *, object_instance_id: UUID, actor_id: str) -> str:
        return self._active_regime.get((object_instance_id, actor_id), self._default_regime)

    def set_regime(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        regime_id: str,
        event_time: datetime | None = None,
        sequence: int = 0,
        event_id: UUID | None = None,
        event_signature: str | None = None,
    ) -> str:
        """Set or update current regime for one object / actor stream."""

        if not regime_id.strip():
            raise ValueError("regime_id must be non-empty")
        key = (object_instance_id, actor_id)
        if (event_id is not None) != (event_signature is not None):
            raise ValueError("event_id and event_signature must be provided together")
        if event_id is not None and event_time is None:
            raise ValueError(
                "event_time is required when event_id and event_signature are provided"
            )
        if event_time is not None:
            self._validate_regime_switch_time(
                stream_key=key,
                event_time=event_time,
                sequence=sequence,
            )
        if event_id is not None:
            self._validate_regime_switch_identity(
                stream_key=key,
                event_id=event_id,
                event_signature=event_signature,
            )
        previous = self.active_regime(object_instance_id=object_instance_id, actor_id=actor_id)
        self._active_regime[key] = regime_id
        if event_time is not None:
            self._last_switch_time[key] = (event_time, sequence)
            if event_id is not None:
                self._processed_switch_event_ids.setdefault(key, set()).add(event_id)
                self._processed_switch_signatures.setdefault(key, set()).add(event_signature)
        return previous

    def mark_regime_switch(
        self,
        *,
        event: RLSRegimeSwitchEvent,
    ) -> str:
        current_regime = self.active_regime(
            object_instance_id=event.object_instance_id,
            actor_id=event.actor_id,
        )
        if current_regime != event.from_regime_id:
            raise ValueError(
                "regime switch event is inconsistent with active regime "
                f"(active={current_regime}, event.from={event.from_regime_id})"
            )
        previous = self.set_regime(
            object_instance_id=event.object_instance_id,
            actor_id=event.actor_id,
            regime_id=event.to_regime_id,
            event_time=event.event_time,
            sequence=event.sequence,
            event_id=event.event_id,
            event_signature=event.event_signature,
        )
        return previous

    def update(self, sample: RLSHabitSample, location_embeddings: dict[UUID, np.ndarray]) -> None:
        regime_id = sample.regime_id or self.active_regime(
            object_instance_id=sample.object_instance_id,
            actor_id=sample.actor_id,
        )
        sample = RLSHabitSample(
            object_instance_id=sample.object_instance_id,
            actor_id=sample.actor_id,
            context_features=sample.context_features,
            target_location_id=sample.target_location_id,
            candidate_locations=sample.candidate_locations,
            gate=sample.gate,
            forgetting_factor=sample.forgetting_factor,
            regime_id=regime_id,
        )
        self._head(regime_id).update(sample, location_embeddings)

    def score_candidates(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        context_features: np.ndarray,
        candidate_locations: tuple[UUID, ...],
        location_embeddings: dict[UUID, np.ndarray],
        regime_id: str | None = None,
    ) -> dict[UUID, float]:
        active_regime = regime_id or self.active_regime(
            object_instance_id=object_instance_id,
            actor_id=actor_id,
        )
        head = self._head_if_exists(active_regime)
        if head is None:
            if not candidate_locations:
                return {}
            uniform_score = 1.0 / len(candidate_locations)
            return {location_id: uniform_score for location_id in candidate_locations}
        return head.score_candidates(
            object_instance_id=object_instance_id,
            actor_id=actor_id,
            regime_id=active_regime,
            context_features=context_features,
            candidate_locations=candidate_locations,
            location_embeddings=location_embeddings,
        )

    def regime_count(self) -> int:
        return len(self._heads)
