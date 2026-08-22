"""Tests for the Context-Conditioned Regime Reactivator (CCRR, 结构二 §4.7 #6).

These pin the four behaviours the specification requires:

* a normalized ``stay / create / reactivate / unresolved`` posterior;
* observation-policy recurrence is ruled out (stay, not reactivate);
* guest recurrence reactivates the guest stage without touching the owner habit;
* identity switching vetoes a reactivation / create;
* an old habit recurrence reactivates the matching archived stage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    JointCauseFactorizedBOCPD,
    RegimeDecisionKind,
    RegimeLibraryEntry,
)

BASE = datetime(2026, 8, 1, tzinfo=UTC)
OWNER = "owner"
GUEST = "guest"


def _frames(habit_levels, *, actor=0.1):
    return tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.3,
                ChangeCause.ACTOR: actor,
                ChangeCause.HABIT: level,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index, level in enumerate(habit_levels)
    )


def _change_snapshot(snapshots):
    """Return the snapshot at the moment a segment change is detected."""

    return max(snapshots, key=lambda snapshot: snapshot.segment_change_probability)


def _habit_change_snapshot():
    model = JointCauseFactorizedBOCPD()
    result = model.run(_frames([0.0, 0.0, 0.0, 1.0, 1.0]), warmup_steps=2)
    return _change_snapshot(result.snapshots)


def _observation_change_snapshot():
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.1 if index < 3 else 0.9,
                ChangeCause.ACTOR: 0.1,
                ChangeCause.HABIT: 0.3,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )
    model = JointCauseFactorizedBOCPD()
    result = model.run(frames, warmup_steps=2)
    return _change_snapshot(result.snapshots)


def _actor_change_snapshot():
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.3,
                ChangeCause.ACTOR: 0.1 if index < 3 else 0.9,
                ChangeCause.HABIT: 0.3,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )
    model = JointCauseFactorizedBOCPD()
    result = model.run(frames, warmup_steps=2)
    return _change_snapshot(result.snapshots)


def test_posterior_is_normalized_and_covers_all_kinds():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
    )
    assert set(decision.posterior) == set(RegimeDecisionKind)
    assert sum(decision.posterior.values()) == pytest.approx(1.0, abs=1e-9)


def test_habit_change_without_match_creates_a_new_regime():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.CREATE
    assert decision.created_regime_id is not None


def test_habit_recurrence_reactivates_the_matching_stage():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="old-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
    )
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.REACTIVATE
    assert decision.reactivated_regime_id == "old-stage"


def test_observation_change_stays_and_rules_out_policy_recurrence():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_observation_change_snapshot(),
        context_features=(0.0, 1.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.STAY
    assert "observation_policy_recurrence" in decision.alternative_causes_ruled_out


def test_identity_switch_vetoes_reactivation():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="old-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
    )
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        identity_switch_probability=0.9,
        now=BASE,
    )
    assert decision.kind != RegimeDecisionKind.REACTIVATE
    assert "identity_switch" in decision.alternative_causes_ruled_out


def test_guest_recurrence_reactivates_guest_stage_on_guest_stream():
    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="guest-stage",
            actor_id=GUEST,
            object_instance_id=obj,
            context_fingerprint=(0.0, 1.0),
            cause_origin=ChangeCause.ACTOR,
            created_at=BASE,
        )
    )
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=GUEST,
        owner_actor_id=OWNER,
        snapshot=_actor_change_snapshot(),
        context_features=(0.0, 1.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.REACTIVATE
    assert decision.reactivated_regime_id == "guest-stage"


def test_actor_change_on_owner_stream_stays():
    """An actor-mixture change must not rewrite the owner habit stage."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=OWNER,
        owner_actor_id=OWNER,
        snapshot=_actor_change_snapshot(),
        context_features=(0.0, 1.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.STAY
