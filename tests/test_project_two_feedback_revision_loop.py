"""Project-two core loop: feedback as reversible counterfactual evidence.

Focused failing-first assertions (written before the implementation) fixing the
open-world reversible-attribution contract:

* a failed search lowers the relevant hypotheses but never zeroes them,
* a successful action reinforces the matching hypotheses,
* every feedback produces a new revision while the old one stays traceable,
* unexplained feedback grows unresolved/unknown mass instead of inventing a culprit,
* an actor-posterior revision emits a project-one-consumable retract request,
* a replayed feedback record is idempotent,
* a provenance-firewall-rejected feedback cannot move any posterior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    BaseRecordMetadata,
    DecisionContext,
    DecisionContextBinding,
    DecisionSurface,
    EntityRef,
    EntityType,
    ExecutionFeedbackRecord,
    MapConsistencyRevisions,
    ObservationDetectionResult,
    ObservationOutcome,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    TargetPresenceBeliefRef,
    ValidTimeInterval,
)
from cpswm.system.continual.execution_feedback_projector import ExecutionFeedbackProjector
from cpswm.system.counterfactual_event_hypergraph import (
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProjectOneRequestKind,
    ProjectTwoFeedbackRevisionLoop,
)
from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    UNKNOWN_ACTOR,
    FeedbackProvenanceError,
    UnsupportedFeedbackRouteError,
    apply_project_one_request,
)

OWNER = "owner"
GUEST = "guest"
OBJ = UUID(int=5)
OTHER_OBJ = UUID(int=6)
L1 = UUID(int=1)
L2 = UUID(int=2)
L3 = UUID(int=3)
# Shared household/session/trace: the feedback must belong to the same context as
# the hidden event it revises.
HH = UUID(int=100)
SS = UUID(int=101)
TT = UUID(int=102)
TA = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
TB = TA + timedelta(hours=1)
TF = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)

# Search likelihood: present -> usually found; absent -> usually not found.
_SEARCH_LL = (
    {RobotActionOutcome.SUCCESS: 0.85, RobotActionOutcome.UNKNOWN: 0.15},
    {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
)


def _base():
    return BaseRecordMetadata(
        schema_name="cpswm.ObservationDetectionResult",
        schema_version="0.1.0",
        household_id=HH,
        session_id=SS,
        trace_id=TT,
        recorded_time=TA,
        source_type=SourceType.SIMULATION,
        source_id="sim",
    )


def _detection(base, *, location, detection_time):
    return ObservationDetectionResult(
        metadata=base.model_copy(update={"record_id": uuid4(), "recorded_time": detection_time}),
        observation_opportunity_id=uuid4(),
        outcome=ObservationOutcome.DETECTED,
        detected_object_instance_id=OBJ,
        detected_location_id=location,
        detection_time=detection_time,
    )


def _history():
    engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
    base = _base()
    before = _detection(base, location=L1, detection_time=TA)
    after = _detection(base, location=L2, detection_time=TB)
    return engine.branch(
        before=before,
        after=after,
        actor_prior={OWNER: 0.6, GUEST: 0.3, UNKNOWN_ACTOR: 0.1},
    )


def _feedback(action_type, outcomes, *, target=OBJ, location=L2):
    meta = BaseRecordMetadata(
        schema_name="cpswm.ExecutionFeedbackRecord",
        schema_version="0.1.0",
        household_id=HH,
        session_id=SS,
        trace_id=TT,
        recorded_time=TF,
        source_type=SourceType.ACTION,
        source_id="executor",
    )
    return ExecutionFeedbackRecord(
        metadata=meta,
        action_id=uuid4(),
        action_type=action_type,
        target_entity=EntityRef(entity_id=target, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=location,
        valid_time=ValidTimeInterval(start=TF, end=TF + timedelta(minutes=1)),
        outcome_distribution=outcomes,
        task_goal_satisfied_probability=min(outcomes.get(RobotActionOutcome.SUCCESS, 0.0), 0.9),
    )


def _binding(feedback, *, prior=0.6):
    revisions = MapConsistencyRevisions(
        belief_snapshot_id=uuid4(),
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=1,
        dynamic_map_revision=1,
        event_history_revision=1,
        input_watermark=1,
    )
    belief = TargetPresenceBeliefRef(
        object_instance_id=feedback.target_entity.entity_id,
        location_id=feedback.attempted_location_id,
        belief_node_id=f"habit:{feedback.target_entity.entity_id}",
        belief_snapshot_id=revisions.belief_snapshot_id,
        node_content_hash="a" * 64,
        prior_probability=prior,
    )
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=TF,
        valid_time=ValidTimeInterval(start=TF, end=TF + timedelta(minutes=5)),
        staleness_budget_seconds=60.0,
        revisions=revisions,
        target_presence_belief=belief,
        authorization_scope_id=uuid4(),
        habit_regime_model_version="m@1",
        model_versions=(("loop", "e2e@0.1"),),
        code_version="git:test",
        rationale="ctx",
    )
    return DecisionContextBinding(
        metadata=feedback.metadata.model_copy(
            update={"record_id": uuid4(), "schema_name": "cpswm.DecisionContextBinding"}
        ),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=feedback.metadata.household_id,
        subject_session_id=feedback.metadata.session_id,
        subject_trace_id=feedback.metadata.trace_id,
        decision_context=context,
    )


def _likelihood(outcomes=_SEARCH_LL):
    return ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present=outcomes[0],
        p_outcome_given_target_absent=outcomes[1],
        calibration_domain="fixture",
        model_version="likelihood@0.1",
    )


def _loop():
    return ProjectTwoFeedbackRevisionLoop(projector=ExecutionFeedbackProjector())


def _search_failed():
    return _feedback(
        RobotActionType.SEARCH,
        {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
    )


def _search_found():
    return _feedback(
        RobotActionType.SEARCH,
        {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1},
    )


def _owner_hypotheses(revision):
    return [h for h in revision.hypotheses if h.responsible_actor_key == OWNER]


def test_search_failure_lowers_hypothesis_posterior_without_zeroing():
    history = _history()
    loop = _loop()
    fb = _search_failed()
    new_history, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    assert outcome.presence_likelihood_ratio < 1.0  # failure is evidence, r < 1
    # Every owner hypothesis dropped but none was zeroed to a hard fact.
    before = {h.hypothesis_id: h.posterior_probability for h in _owner_hypotheses(history.latest)}
    after = {
        h.hypothesis_id: h.posterior_probability for h in _owner_hypotheses(new_history.latest)
    }
    assert before  # sanity: owner does own some hypotheses
    for hid, prior_mass in before.items():
        assert 0.0 < after[hid] < prior_mass


def test_action_success_reinforces_matching_hypotheses():
    history = _history()
    loop = _loop()
    fb = _search_found()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    assert outcome.presence_likelihood_ratio > 1.0  # success is corroborating evidence
    # Resolved chains gain mass; the unresolved bucket shrinks.
    assert outcome.unresolved_after < outcome.unresolved_before
    assert outcome.owner_mass_after > outcome.owner_mass_before


def test_feedback_creates_new_revision_and_keeps_old_traceable():
    history = _history()
    loop = _loop()
    fb = _search_failed()
    new_history, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    assert len(new_history.revisions) == len(history.revisions) + 1
    assert new_history.latest.parent_revision_id == history.latest.revision_id
    assert outcome.superseded_revision_id == history.latest.revision_id
    assert outcome.corrected_revision_id == new_history.latest.revision_id
    # The superseded revision is still present and unchanged in the history.
    assert new_history.revisions[-2] == history.latest


def test_unexplainable_feedback_grows_unresolved_not_a_fake_actor():
    history = _history()
    loop = _loop()
    fb = _search_failed()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    # Open-world mass grows; no known actor is fabricated into near-certainty.
    assert outcome.unresolved_after > outcome.unresolved_before
    known_after = {
        actor: mass
        for actor, mass in outcome.actor_posterior_after.items()
        if actor != UNKNOWN_ACTOR
    }
    assert max(known_after.values()) < 0.9
    assert outcome.actor_posterior_after[OWNER] < outcome.actor_posterior_before[OWNER]


def test_actor_revision_emits_project_one_retract_request():
    history = _history()
    loop = _loop()
    fb = _search_failed()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    assert outcome.project_one_requests, "a dropped owner mass must request a project-one revision"
    request = outcome.project_one_requests[0]
    assert request.kind in {ProjectOneRequestKind.RETRACT, ProjectOneRequestKind.CORRECT}
    assert request.owner_key == OWNER
    assert request.object_instance_id == OBJ
    assert request.location_id == L2
    assert request.owner_mass_delta < 0.0
    assert request.superseded_revision_id == history.latest.revision_id
    assert request.corrected_revision_id == outcome.corrected_revision_id
    assert request.source_feedback_record_id == fb.metadata.record_id


def test_duplicate_feedback_is_idempotent():
    history = _history()
    loop = _loop()
    fb = _search_failed()
    binding = _binding(fb)
    new_history, first = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=binding,
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    replay_history, replay = loop.ingest_feedback(
        history=new_history,
        feedback=fb,
        binding=binding,
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    assert replay.is_replay is True
    assert first.is_replay is False
    # No second revision is appended for the same feedback record.
    assert len(replay_history.revisions) == len(new_history.revisions)
    assert replay.corrected_revision_id == first.corrected_revision_id


def test_provenance_firewall_rejected_feedback_does_not_change_posterior():
    history = _history()
    loop = _loop()
    # Feedback about a *different* object cannot be bound to this hidden event.
    fb = _feedback(
        RobotActionType.SEARCH,
        {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
        target=OTHER_OBJ,
    )
    with pytest.raises(FeedbackProvenanceError):
        loop.ingest_feedback(
            history=history,
            feedback=fb,
            binding=_binding(fb),
            likelihood_model=_likelihood(),
            owner_key=OWNER,
        )
    # History and posteriors are untouched.
    assert len(history.revisions) == 1


# --- review round 2: fixes #1..#6 ---------------------------------------------


def test_actor_discriminating_evidence_changes_owner_vs_guest_odds():
    # Fix #1: with a per-actor likelihood channel, owner/guest *relative* odds move
    # (true actor-responsibility revision, not only event-existence confidence).
    history = _history()
    loop = _loop()
    fb = _search_found()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
        actor_likelihood_ratios={OWNER: 0.2, GUEST: 3.0},
    )
    before = outcome.actor_posterior_before
    after = outcome.actor_posterior_after
    odds_before = before[OWNER] / before[GUEST]
    odds_after = after[OWNER] / after[GUEST]
    assert odds_after < odds_before * 0.5  # the odds genuinely shifted toward guest


def test_presence_only_feedback_keeps_owner_guest_odds_fixed():
    # The honest complement of #1: a presence-only search revises event-existence
    # confidence and leaves owner/guest relative odds essentially unchanged.
    history = _history()
    loop = _loop()
    fb = _search_failed()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    before = outcome.actor_posterior_before
    after = outcome.actor_posterior_after
    assert (after[OWNER] / after[GUEST]) == pytest.approx(before[OWNER] / before[GUEST], rel=1e-6)


def test_place_feedback_route_is_isolated_not_folded_to_presence():
    # Fix #2: place/transfer must not be silently folded into a presence ratio.
    history = _history()
    loop = _loop()
    fb = _feedback(
        RobotActionType.PLACE,
        {RobotActionOutcome.SUCCESS: 0.2, RobotActionOutcome.OBJECT_SLIPPED: 0.8},
    )
    place_ll = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.PLACE,
        p_outcome_given_target_present={
            RobotActionOutcome.SUCCESS: 0.8,
            RobotActionOutcome.OBJECT_SLIPPED: 0.2,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.SUCCESS: 0.3,
            RobotActionOutcome.OBJECT_SLIPPED: 0.7,
        },
        calibration_domain="fixture",
        model_version="likelihood@0.1",
    )
    with pytest.raises(UnsupportedFeedbackRouteError):
        loop.ingest_feedback(
            history=history,
            feedback=fb,
            binding=_binding(fb),
            likelihood_model=place_ll,
            owner_key=OWNER,
        )
    assert len(history.revisions) == 1


def test_forged_replay_with_different_content_is_rejected():
    # Fix #3: same record id + different content must be caught by the projector,
    # never short-circuited by a loop-side cache.
    history = _history()
    loop = _loop()
    fb = _search_failed()
    binding = _binding(fb)
    new_history, _ = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=binding,
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    forged = fb.model_copy(
        update={
            "outcome_distribution": {
                RobotActionOutcome.SUCCESS: 0.9,
                RobotActionOutcome.UNKNOWN: 0.1,
            }
        }
    )
    assert forged.metadata.record_id == fb.metadata.record_id
    with pytest.raises(ValueError, match="collision/forgery"):
        loop.ingest_feedback(
            history=new_history,
            feedback=forged,
            binding=binding,
            likelihood_model=_likelihood(),
            owner_key=OWNER,
        )


def test_feedback_wrong_location_is_rejected():
    # Fix #4: feedback must concern the event's destination location.
    history = _history()
    loop = _loop()
    fb = _feedback(
        RobotActionType.SEARCH,
        {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
        location=L3,
    )
    with pytest.raises(FeedbackProvenanceError, match="location"):
        loop.ingest_feedback(
            history=history,
            feedback=fb,
            binding=_binding(fb),
            likelihood_model=_likelihood(),
            owner_key=OWNER,
        )
    assert len(history.revisions) == 1


def test_feedback_before_event_end_is_rejected():
    # Fix #4: a pre-event observation cannot be back-filled as post-event evidence.
    history = _history()
    loop = _loop()
    fb = _search_failed()
    early = fb.model_copy(
        update={"valid_time": ValidTimeInterval(start=TA, end=TA + timedelta(minutes=1))}
    )
    with pytest.raises(FeedbackProvenanceError, match="precedes the hidden-event end"):
        loop.ingest_feedback(
            history=history,
            feedback=early,
            binding=_binding(early),
            likelihood_model=_likelihood(),
            owner_key=OWNER,
        )


def test_feedback_foreign_household_is_rejected():
    # Fix #4: feedback from another household/session/trace cannot revise this event.
    history = _history()
    loop = _loop()
    fb = _search_failed()
    foreign = fb.model_copy(
        update={"metadata": fb.metadata.model_copy(update={"household_id": uuid4()})}
    )
    with pytest.raises(FeedbackProvenanceError, match="household_id"):
        loop.ingest_feedback(
            history=history,
            feedback=foreign,
            binding=_binding(foreign),
            likelihood_model=_likelihood(),
            owner_key=OWNER,
        )


def test_pchmp_and_orrer_posteriors_agree():
    # Fix #6: the re-propagated PCHMP posterior equals the ORRER revision posterior.
    history = _history()
    loop = _loop()
    fb = _search_failed()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    for hid, mass in outcome.repropagated_posterior.items():
        assert outcome.hypothesis_posterior_after[hid] == pytest.approx(mass, abs=1e-9)


def test_project_one_consumes_a_correct_request():
    # Fix #5: the emitted request actually changes project-one owner-habit stats.
    from cpswm.system.continual.hybrid_event_to_task_loop import (
        HybridEventToTaskCoordinatorLoop,
        OwnerPlacementInput,
    )

    history = _history()
    superseded_id = history.latest.revision_id
    p1 = HybridEventToTaskCoordinatorLoop(
        owner_key=OWNER,
        object_instance_id=OBJ,
        authorization_scope_id=uuid4(),
        model_version="m@1",
        code_version="git:test",
    )
    p1.ingest_owner_placement(
        OwnerPlacementInput(
            event_hypothesis_id=history.hypothesis_set_id,
            revision_id=superseded_id,
            destination_location_id=L2,
            owner_mass=0.6,
            source_record_id=uuid4(),
        )
    )
    alpha_before = p1.ledger.projection(p1._key(L2)).alpha
    assert alpha_before == pytest.approx(0.6)

    loop = _loop()
    fb = _search_failed()
    _, outcome = loop.ingest_feedback(
        history=history,
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    request = outcome.project_one_requests[0]
    changed = apply_project_one_request(request, p1)
    assert changed is True
    alpha_after = p1.ledger.projection(p1._key(L2)).alpha
    assert alpha_after == pytest.approx(outcome.owner_mass_after)
    assert alpha_after < alpha_before  # project one really consumed the correction
