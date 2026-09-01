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
from uuid import UUID, uuid4

import pytest

from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    ForgedDecisionError,
    JointCauseFactorizedBOCPD,
    RegimeDecision,
    RegimeDecisionKind,
    RegimeLibraryEntry,
    StaleLibraryError,
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
    assert set(decision.decision_score) == set(RegimeDecisionKind)
    assert decision.authority == "ccrr_regime_destination_proposal"
    assert not decision.parameter_write_authorized


def test_ccrr_cannot_claim_rgrc_parameter_write_authority():
    decision = _score_stay_decision(ContextConditionedRegimeReactivator(), UUID(int=9201))
    payload = decision.model_dump(mode="python")
    payload["authority"] = "final_regime_and_statistic_write"
    with pytest.raises(ValueError, match="ccrr_regime_destination_proposal"):
        RegimeDecision.model_validate(payload)
    assert sum(decision.decision_score.values()) == pytest.approx(1.0, abs=1e-9)


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


def test_score_decision_is_pure_and_does_not_mutate_library():
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
    library_before = reactor.library(object_instance_id=obj, actor_id=OWNER)
    active_before = reactor.active_regime(object_instance_id=obj, actor_id=OWNER)
    version_before = reactor.library_version
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)

    reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )

    assert reactor.library(object_instance_id=obj, actor_id=OWNER) == library_before
    assert reactor.active_regime(object_instance_id=obj, actor_id=OWNER) == active_before
    assert reactor.library_version == version_before


def test_apply_decision_rejects_stale_library_version():
    from cpswm.world_model.habits_transitions import StaleLibraryError

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    # Mutate the library underneath the decision.
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="concurrent-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(0.5, 0.5),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
    )
    with pytest.raises(StaleLibraryError):
        reactor.apply_decision(decision)


def test_actor_origin_stage_is_not_reactivated_by_habit_change():
    """P0: a guest/actor stage must not masquerade as an owner habit stage."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    # An ACTOR-origin stage whose context fingerprint looks identical to an old
    # owner habit (same context, same actor stream).
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="guest-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.ACTOR,
            created_at=BASE,
        )
    )
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    assert decision.kind != RegimeDecisionKind.REACTIVATE


def test_reactivation_tiebreak_is_insertion_order_independent():
    """P1: two identical-context stages must reactivate the same one regardless
    of the order in which they were inserted."""

    def _reactivated_id(insert_first: str) -> str | None:
        reactor = ContextConditionedRegimeReactivator()
        obj = uuid4()
        stage_a = RegimeLibraryEntry(
            regime_id="stage-a",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
        stage_b = RegimeLibraryEntry(
            regime_id="stage-b",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
        for stage in (stage_a, stage_b) if insert_first == "a" else (stage_b, stage_a):
            reactor.add_regime(stage)
        view = reactor.view(object_instance_id=obj, actor_id=OWNER)
        decision = reactor.score_decision(
            owner_actor_id=OWNER,
            snapshot=_habit_change_snapshot(),
            context_features=(1.0, 0.0),
            now=BASE,
            view=view,
        )
        return decision.reactivated_regime_id

    assert _reactivated_id("a") == _reactivated_id("b")


def test_incompatible_stage_does_not_shadow_compatible_stage():
    """P0: a higher-similarity ACTOR stage must not shadow a compatible HABIT
    stage that still clears the similarity threshold."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    # A compatible HABIT stage with moderate similarity (0.8 on a 2-D context).
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="habit-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(0.8, 0.2),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
    )
    # An incompatible ACTOR stage with higher similarity.
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="actor-stage",
            actor_id=OWNER,
            object_instance_id=obj,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.ACTOR,
            created_at=BASE,
        )
    )
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    assert decision.kind == RegimeDecisionKind.REACTIVATE
    assert decision.reactivated_regime_id == "habit-stage"


def test_decision_cannot_be_replayed_onto_a_different_stream():
    """P0-1: a decision scored for object A / owner must not apply to
    object B / guest even when the per-stream versions collide."""

    from cpswm.world_model.habits_transitions import StaleLibraryError

    reactor = ContextConditionedRegimeReactivator()
    obj_a = uuid4()
    obj_b = uuid4()
    # Align both streams at the same per-stream version but different contents.
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="owner-stage",
            actor_id=OWNER,
            object_instance_id=obj_a,
            context_fingerprint=(1.0, 0.0),
            cause_origin=ChangeCause.HABIT,
            created_at=BASE,
        )
    )
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="guest-stage",
            actor_id=GUEST,
            object_instance_id=obj_b,
            context_fingerprint=(0.0, 1.0),
            cause_origin=ChangeCause.ACTOR,
            created_at=BASE,
        )
    )
    view = reactor.view(object_instance_id=obj_a, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    assert decision.object_instance_id == obj_a
    assert decision.actor_id == OWNER

    # Re-point the decision at the other stream: same per-stream version (1),
    # but a different live content hash, so it must be rejected.
    tampered = decision.model_copy(update={"object_instance_id": obj_b, "actor_id": GUEST})
    with pytest.raises(StaleLibraryError):
        reactor.apply_decision(tampered)


def test_decision_context_cannot_be_swapped_at_apply_time():
    """P0-1: the scored context is frozen in the decision; a caller cannot
    substitute different context features at apply time."""

    from pydantic import ValidationError

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    assert decision.context_features == (1.0, 0.0)
    # Swapping the context breaks the context_hash binding.
    from cpswm.world_model.habits_transitions import RegimeDecision

    with pytest.raises(ValidationError):
        RegimeDecision.model_validate(
            decision.model_dump(mode="python") | {"context_features": (0.0, 1.0)}
        )


def test_unrelated_stream_mutation_does_not_invalidate_owner_decision():
    """P0-1: a mutation on another stream must not falsely stale an owner
    decision (per-stream versions, not one global version)."""

    reactor = ContextConditionedRegimeReactivator()
    obj_a = uuid4()
    obj_b = uuid4()
    view = reactor.view(object_instance_id=obj_a, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    # An unrelated guest-stream mutation.
    reactor.add_regime(
        RegimeLibraryEntry(
            regime_id="guest-stage",
            actor_id=GUEST,
            object_instance_id=obj_b,
            context_fingerprint=(0.0, 1.0),
            cause_origin=ChangeCause.ACTOR,
            created_at=BASE,
        )
    )
    # The owner decision must still apply cleanly.
    applied_version = reactor.apply_decision(decision)
    assert applied_version >= 1
    assert reactor.active_regime(object_instance_id=obj_a, actor_id=OWNER) == (
        decision.created_regime_id
        if decision.kind == RegimeDecisionKind.CREATE
        else reactor.default_regime_id
    )


def test_create_stamps_the_dominant_cause_not_always_habit():
    """P1: a guest stream's actor-mixture change must create an ACTOR-origin
    stage (the first guest stage), not a HABIT-origin one."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = reactor.decide(
        object_instance_id=obj,
        actor_id=GUEST,
        owner_actor_id=OWNER,
        snapshot=_actor_change_snapshot(),
        context_features=(0.0, 1.0),
        now=BASE,
    )
    assert decision.kind == RegimeDecisionKind.CREATE
    assert decision.created_cause_origin == ChangeCause.ACTOR
    entry = reactor.library(object_instance_id=obj, actor_id=GUEST)[0]
    assert entry.cause_origin == ChangeCause.ACTOR


def _score_stay_decision(reactor: ContextConditionedRegimeReactivator, obj) -> RegimeDecision:
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    return reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_observation_change_snapshot(),
        context_features=(0.0, 1.0),
        now=BASE,
        view=view,
    )


def test_forged_stay_to_create_is_rejected():
    """A STAY decision rewired to CREATE must not apply: re-scoring disagrees."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = _score_stay_decision(reactor, obj)
    assert decision.kind == RegimeDecisionKind.STAY
    forged = RegimeDecision.model_validate(
        decision.model_dump(mode="python")
        | {
            "kind": RegimeDecisionKind.CREATE,
            "created_regime_id": "forged-stage",
            "created_cause_origin": ChangeCause.HABIT,
            "decision_score": {
                RegimeDecisionKind.STAY: 0.1,
                RegimeDecisionKind.CREATE: 0.7,
                RegimeDecisionKind.REACTIVATE: 0.1,
                RegimeDecisionKind.UNRESOLVED: 0.1,
            },
        }
    )
    with pytest.raises(ForgedDecisionError):
        reactor.apply_decision(forged)


def test_forged_habit_to_actor_cause_is_rejected():
    """A HABIT create rewritten to ACTOR must not apply."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    assert decision.kind == RegimeDecisionKind.CREATE
    assert decision.created_cause_origin == ChangeCause.HABIT
    forged = RegimeDecision.model_validate(
        decision.model_dump(mode="python") | {"created_cause_origin": ChangeCause.ACTOR}
    )
    with pytest.raises(ForgedDecisionError):
        reactor.apply_decision(forged)


def test_cross_config_replay_is_rejected():
    """A decision scored under one config must not apply under another."""

    reactor = ContextConditionedRegimeReactivator(change_threshold=0.5)
    obj = uuid4()
    view = reactor.view(object_instance_id=obj, actor_id=OWNER)
    decision = reactor.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    other = ContextConditionedRegimeReactivator(change_threshold=0.9)
    with pytest.raises(StaleLibraryError):
        other.apply_decision(decision)


def test_cross_instance_replay_is_rejected():
    """A decision scored on one instance must not apply on a fresh instance:
    the single-use token is reactor-private."""

    first = ContextConditionedRegimeReactivator()
    obj = uuid4()
    view = first.view(object_instance_id=obj, actor_id=OWNER)
    decision = first.score_decision(
        owner_actor_id=OWNER,
        snapshot=_habit_change_snapshot(),
        context_features=(1.0, 0.0),
        now=BASE,
        view=view,
    )
    second = ContextConditionedRegimeReactivator()
    with pytest.raises(ForgedDecisionError):
        second.apply_decision(decision)


def test_tampered_score_is_rejected():
    """A decision whose score vector is tampered (kind unchanged) must not apply."""

    reactor = ContextConditionedRegimeReactivator()
    obj = uuid4()
    decision = _score_stay_decision(reactor, obj)
    tampered_scores = dict(decision.decision_score)
    tampered_scores[RegimeDecisionKind.STAY] = min(
        0.99, tampered_scores[RegimeDecisionKind.STAY] + 0.01
    )
    tampered_scores[RegimeDecisionKind.UNRESOLVED] = max(
        0.0, tampered_scores[RegimeDecisionKind.UNRESOLVED] - 0.01
    )
    tampered = RegimeDecision.model_validate(
        decision.model_dump(mode="python") | {"decision_score": tampered_scores}
    )
    with pytest.raises(ForgedDecisionError):
        reactor.apply_decision(tampered)
