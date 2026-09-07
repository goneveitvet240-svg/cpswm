from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    ForgedDecisionError,
    JointCauseFactorizedBOCPD,
    RegimeDecisionKind,
    RunLengthClock,
    UnifiedChangeCause,
    compose_joint_cause_regime_transition,
)

BASE = datetime(2026, 9, 6, tzinfo=UTC)


def _frame(index: int) -> CauseSignalFrame:
    return CauseSignalFrame(
        timestamp=BASE + timedelta(seconds=10 * index),
        opportunity_index=100 + index,
        elapsed_seconds=10.0,
        signals={
            ChangeCause.OBSERVATION: 0.2,
            ChangeCause.ACTOR: 0.1,
            ChangeCause.HABIT: 0.8 if index >= 2 else 0.2,
            ChangeCause.NOISE: 0.1,
        },
    )


def test_run_length_clock_is_effective_opportunity_not_wall_time() -> None:
    snapshots = (
        JointCauseFactorizedBOCPD()
        .run(tuple(_frame(index) for index in range(4)), warmup_steps=1)
        .snapshots
    )

    assert [snapshot.opportunity_index for snapshot in snapshots] == [100, 101, 102, 103]
    assert all(
        snapshot.run_length_clock is RunLengthClock.EFFECTIVE_OBSERVATION_OPPORTUNITY
        for snapshot in snapshots
    )
    assert all(snapshot.elapsed_seconds == 10.0 for snapshot in snapshots)


def test_online_filter_rejects_replayed_or_reordered_opportunity() -> None:
    model = JointCauseFactorizedBOCPD()
    model.observe_online(_frame(0))
    replay = CauseSignalFrame(
        timestamp=BASE + timedelta(seconds=11),
        opportunity_index=100,
        signals=_frame(1).signals,
    )
    with pytest.raises(ValueError, match="opportunity indices"):
        model.observe_online(replay)


def test_joint_c_r_z_composition_integrates_identity_without_second_likelihood() -> None:
    snapshot = (
        JointCauseFactorizedBOCPD()
        .run(tuple(_frame(index) for index in range(4)), warmup_steps=1)
        .snapshots[-1]
    )
    reactor = ContextConditionedRegimeReactivator()
    object_id = uuid4()
    view = reactor.view(object_instance_id=object_id, actor_id="owner")
    decision = reactor.score_decision(
        owner_actor_id="owner",
        snapshot=snapshot,
        context_features=(1.0, 0.0),
        identity_switch_probability=0.25,
        now=BASE + timedelta(seconds=41),
        view=view,
    )

    joint = compose_joint_cause_regime_transition(snapshot, decision, verifier=reactor)

    assert sum(item.probability for item in joint.masses) == pytest.approx(1.0)
    assert joint.cause_marginal()[UnifiedChangeCause.IDENTITY] == pytest.approx(0.25)
    assert all(
        item.run_length == 0 for item in joint.masses if item.cause is UnifiedChangeCause.IDENTITY
    )
    assert not any(
        item.destination in {RegimeDecisionKind.CREATE, RegimeDecisionKind.REACTIVATE}
        for item in joint.masses
        if item.cause is not UnifiedChangeCause.HABIT
    )
    assert (
        decision.distribution_semantics
        == "conditional_regime_transition_probability_not_observation_likelihood"
    )


def test_z_is_conditioned_on_run_length_and_stay_keeps_concrete_identity() -> None:
    snapshot = (
        JointCauseFactorizedBOCPD()
        .run(tuple(_frame(index) for index in range(6)), warmup_steps=1)
        .snapshots[-1]
    )
    reactor = ContextConditionedRegimeReactivator()
    object_id = uuid4()
    decision = reactor.score_decision(
        owner_actor_id="owner",
        snapshot=snapshot,
        context_features=(1.0, 0.0),
        identity_switch_probability=0.0,
        now=BASE + timedelta(seconds=61),
        view=reactor.view(object_instance_id=object_id, actor_id="owner"),
    )
    joint = compose_joint_cause_regime_transition(snapshot, decision, verifier=reactor)

    conditional: dict[tuple[UnifiedChangeCause, int], dict[RegimeDecisionKind, float]] = {}
    for item in joint.masses:
        conditional.setdefault((item.cause, item.run_length), {})[item.destination] = (
            item.probability
        )
        if item.destination is RegimeDecisionKind.STAY:
            assert item.destination_regime_id == decision.active_regime_id
            assert item.destination_regime_id != "current"
    comparable = [
        (key, values) for key, values in conditional.items() if key[0] is UnifiedChangeCause.HABIT
    ]
    assert len(comparable) >= 2
    normalized = []
    for key, values in comparable:
        total = sum(values.values())
        normalized.append(
            (
                key[1],
                tuple(values.get(kind, 0.0) / total for kind in RegimeDecisionKind),
            )
        )
    assert len({tuple(round(value, 12) for value in vector) for _, vector in normalized}) > 1


def test_composer_rejects_forged_decision_without_burning_authentic_token() -> None:
    snapshot = (
        JointCauseFactorizedBOCPD()
        .run(tuple(_frame(index) for index in range(4)), warmup_steps=1)
        .snapshots[-1]
    )
    reactor = ContextConditionedRegimeReactivator()
    decision = reactor.score_decision(
        owner_actor_id="owner",
        snapshot=snapshot,
        context_features=(1.0, 0.0),
        identity_switch_probability=0.2,
        now=BASE + timedelta(seconds=41),
        view=reactor.view(object_instance_id=uuid4(), actor_id="owner"),
    )
    tampered = dict(decision.decision_score)
    stay = tampered[RegimeDecisionKind.STAY]
    unresolved = tampered[RegimeDecisionKind.UNRESOLVED]
    tampered[RegimeDecisionKind.STAY] = unresolved
    tampered[RegimeDecisionKind.UNRESOLVED] = stay
    forged = decision.model_copy(update={"decision_score": tampered})

    with pytest.raises(ForgedDecisionError):
        compose_joint_cause_regime_transition(snapshot, forged, verifier=reactor)
    authentic = compose_joint_cause_regime_transition(snapshot, decision, verifier=reactor)
    assert sum(item.probability for item in authentic.masses) == pytest.approx(1.0)
