"""Tests for regimen routing of RLS habit heads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from cpswm.system.continual.rls import (
    RLSHabitSample,
    RLSHabitScoreHead,
    RLSRegimeBank,
    RLSRegimeSwitchEvent,
)


def _head_factory() -> RLSHabitScoreHead:
    return RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=1)


def _sample(*, object_id, actor_id, target_location_id, candidates):
    return RLSHabitSample(
        object_instance_id=object_id,
        actor_id=actor_id,
        context_features=np.array([0.5], dtype=float),
        target_location_id=target_location_id,
        candidate_locations=candidates,
        gate=1.0,
    )


def test_regime_switch_changes_active_path():
    object_id = uuid4()
    actor_id = "alice"
    head_regime_a = uuid4()
    head_regime_b = uuid4()
    context = np.array([0.2], dtype=float)
    location_embeddings = {
        head_regime_a: np.array([1.0], dtype=float),
        head_regime_b: np.array([0.0], dtype=float),
    }
    candidate_locations = (head_regime_a, head_regime_b)

    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    sample = _sample(
        object_id=object_id,
        actor_id=actor_id,
        target_location_id=head_regime_a,
        candidates=candidate_locations,
    )
    bank.update(sample, location_embeddings)

    before = bank.score_candidates(
        object_instance_id=object_id,
        actor_id=actor_id,
        context_features=context,
        candidate_locations=candidate_locations,
        location_embeddings=location_embeddings,
        regime_id="stable",
    )

    prev = bank.mark_regime_switch(
        event=RLSRegimeSwitchEvent(
            object_instance_id=object_id,
            actor_id=actor_id,
            from_regime_id="stable",
            to_regime_id="anomaly",
            event_time=datetime.now(tz=UTC),
        )
    )

    after = bank.score_candidates(
        object_instance_id=object_id,
        actor_id=actor_id,
        context_features=context,
        candidate_locations=candidate_locations,
        location_embeddings=location_embeddings,
        regime_id="anomaly",
    )

    assert prev == "stable"
    assert before != after
    assert bank.active_regime(object_instance_id=object_id, actor_id=actor_id) == "anomaly"


def test_set_regime_returns_previous_regime():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"

    previous = bank.set_regime(
        object_instance_id=object_id,
        actor_id=actor_id,
        regime_id="anomaly",
    )

    assert previous == "stable"


def test_set_regime_with_event_time_uses_same_monotonic_rule_as_marked_switch():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)

    bank.set_regime(
        object_instance_id=object_id,
        actor_id=actor_id,
        regime_id="anomaly",
        event_time=now,
        sequence=3,
    )
    assert bank.active_regime(object_instance_id=object_id, actor_id=actor_id) == "anomaly"

    with pytest.raises(ValueError, match="strictly increasing in time"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="recovery",
            event_time=now - timedelta(seconds=1),
            sequence=4,
        )

    with pytest.raises(ValueError, match="strictly increase"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="recovery",
            event_time=now,
            sequence=3,
        )


def test_set_regime_rejects_naive_event_time():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"

    with pytest.raises(ValueError, match="timezone-aware"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="anomaly",
            event_time=datetime(2026, 8, 1, 9, 0, 0),
        )


def test_set_regime_with_event_identity_enforces_replay_prevention():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
    source_event = RLSRegimeSwitchEvent(
        object_instance_id=object_id,
        actor_id=actor_id,
        from_regime_id="stable",
        to_regime_id="anomaly",
        event_time=now,
        sequence=1,
    )

    bank.set_regime(
        object_instance_id=object_id,
        actor_id=actor_id,
        regime_id="anomaly",
        event_time=now,
        sequence=1,
        event_id=source_event.event_id,
        event_signature=source_event.event_signature,
    )

    with pytest.raises(ValueError, match="event_id already processed"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="recovery",
            event_time=now,
            sequence=2,
            event_id=source_event.event_id,
            event_signature=source_event.event_signature,
        )


def test_set_regime_rejects_mutual_identity_params():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="must be provided together"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="anomaly",
            event_time=now,
            event_id=uuid4(),
        )


def test_set_regime_rejects_identity_without_event_time():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"

    with pytest.raises(ValueError, match="event_time is required"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="anomaly",
            event_id=uuid4(),
            event_signature="fake_signature",
        )


def test_set_regime_rejects_duplicate_event_signature():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
    source_event = RLSRegimeSwitchEvent(
        object_instance_id=object_id,
        actor_id=actor_id,
        from_regime_id="stable",
        to_regime_id="anomaly",
        event_time=now,
    )
    bank.set_regime(
        object_instance_id=object_id,
        actor_id=actor_id,
        regime_id="anomaly",
        event_time=now,
        sequence=1,
        event_id=source_event.event_id,
        event_signature=source_event.event_signature,
    )

    with pytest.raises(ValueError, match="event_signature already processed"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="recovery",
            event_time=now,
            sequence=2,
            event_id=uuid4(),
            event_signature=source_event.event_signature,
        )


def test_set_regime_rejects_non_adjacent_event_replay():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
    first = RLSRegimeSwitchEvent(
        object_instance_id=object_id,
        actor_id=actor_id,
        from_regime_id="stable",
        to_regime_id="anomaly",
        event_time=now,
        sequence=1,
    )
    second = RLSRegimeSwitchEvent(
        object_instance_id=object_id,
        actor_id=actor_id,
        from_regime_id="anomaly",
        to_regime_id="recovery",
        event_time=now + timedelta(seconds=1),
        sequence=2,
    )
    bank.mark_regime_switch(event=first)
    bank.mark_regime_switch(event=second)

    with pytest.raises(ValueError, match="event_id already processed"):
        bank.set_regime(
            object_instance_id=object_id,
            actor_id=actor_id,
            regime_id="anomaly",
            event_time=now + timedelta(seconds=2),
            sequence=3,
            event_id=first.event_id,
            event_signature=first.event_signature,
        )


def test_regime_switch_event_rejects_bad_signature():
    source = {
        "object_instance_id": uuid4(),
        "actor_id": "alice",
        "from_regime_id": "stable",
        "to_regime_id": "anomaly",
        "event_time": datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC),
        "sequence": 1,
        "event_signature": "0" * 64,
    }
    with pytest.raises(ValidationError, match="does not match"):
        RLSRegimeSwitchEvent.model_validate(source)


def test_regime_switch_event_rejects_naive_event_time():
    with pytest.raises(ValidationError, match="timezone-aware"):
        RLSRegimeSwitchEvent(
            object_instance_id=uuid4(),
            actor_id="alice",
            from_regime_id="stable",
            to_regime_id="anomaly",
            event_time=datetime(2026, 8, 1, 9, 0, 0),
        )


def test_mark_regime_switch_requires_matching_from_regime():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    bank.set_regime(
        object_instance_id=object_id,
        actor_id=actor_id,
        regime_id="anomaly",
    )

    with pytest.raises(ValueError, match="inconsistent with active regime"):
        bank.mark_regime_switch(
            event=RLSRegimeSwitchEvent(
                object_instance_id=object_id,
                actor_id=actor_id,
                from_regime_id="stable",
                to_regime_id="recovery",
                event_time=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
    assert bank.active_regime(object_instance_id=object_id, actor_id=actor_id) == "anomaly"


def test_mark_regime_switch_rejects_non_monotonic_event_time():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)

    bank.mark_regime_switch(
        event=RLSRegimeSwitchEvent(
            object_instance_id=object_id,
            actor_id=actor_id,
            from_regime_id="stable",
            to_regime_id="anomaly",
            event_time=now,
        )
    )

    with pytest.raises(ValueError, match="strictly increasing in time"):
        bank.mark_regime_switch(
            event=RLSRegimeSwitchEvent(
                object_instance_id=object_id,
                actor_id=actor_id,
                from_regime_id="anomaly",
                to_regime_id="recovery",
                event_time=now - timedelta(seconds=1),
            )
        )


def test_mark_regime_switch_rejects_naive_event_time():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"

    with pytest.raises(ValidationError, match="timezone-aware"):
        bank.mark_regime_switch(
            event=RLSRegimeSwitchEvent(
                object_instance_id=object_id,
                actor_id=actor_id,
                from_regime_id="stable",
                to_regime_id="anomaly",
                event_time=datetime(2026, 8, 1, 9, 0, 0),
            )
        )


def test_mark_regime_switch_rejects_non_increasing_sequence_at_same_time():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    now = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)

    bank.mark_regime_switch(
        event=RLSRegimeSwitchEvent(
            object_instance_id=object_id,
            actor_id=actor_id,
            from_regime_id="stable",
            to_regime_id="anomaly",
            event_time=now,
            sequence=7,
        )
    )

    with pytest.raises(ValueError, match="sequence must strictly increase"):
        bank.mark_regime_switch(
            event=RLSRegimeSwitchEvent(
                object_instance_id=object_id,
                actor_id=actor_id,
                from_regime_id="anomaly",
                to_regime_id="recovery",
                event_time=now,
                sequence=7,
            )
        )


def test_score_candidates_does_not_create_new_heads():
    bank = RLSRegimeBank(head_factory=_head_factory, default_regime="stable")
    object_id = uuid4()
    actor_id = "alice"
    a_location = uuid4()
    b_location = uuid4()
    context = np.array([0.2], dtype=float)
    location_embeddings = {
        a_location: np.array([0.1], dtype=float),
        b_location: np.array([0.2], dtype=float),
    }

    scores = bank.score_candidates(
        object_instance_id=object_id,
        actor_id=actor_id,
        context_features=context,
        candidate_locations=(a_location, b_location),
        location_embeddings=location_embeddings,
        regime_id="stable",
    )

    assert bank.regime_count() == 0
    assert scores == {a_location: 0.5, b_location: 0.5}
