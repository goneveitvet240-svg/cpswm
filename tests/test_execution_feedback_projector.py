"""ExecutionFeedbackProjector: P0-hardened likelihood-aware routing (review fix #4)."""

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
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    TargetPresenceBeliefRef,
    ValidTimeInterval,
)
from cpswm.system.continual.execution_feedback_projector import (
    ExecutionFeedbackProjector,
    FeedbackRoute,
    ProjectionInputConflictError,
    TransitionCandidate,
)

OBJ = UUID(int=5)
OTHER_OBJ = UUID(int=6)
L2 = UUID(int=2)
T1 = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


def _feedback(action_type, outcomes, *, target=OBJ, location=L2):
    meta = BaseRecordMetadata(
        schema_name="cpswm.ExecutionFeedbackRecord",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        recorded_time=T1,
        source_type=SourceType.ACTION,
        source_id="executor",
    )
    return ExecutionFeedbackRecord(
        metadata=meta,
        action_id=uuid4(),
        action_type=action_type,
        target_entity=EntityRef(entity_id=target, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=location,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=1)),
        outcome_distribution=outcomes,
        task_goal_satisfied_probability=min(outcomes.get(RobotActionOutcome.SUCCESS, 0.0), 0.9),
    )


def _binding(feedback, *, prior=0.5, belief_object=None, belief_location=None, snapshot_id=None):
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
        object_instance_id=belief_object or feedback.target_entity.entity_id,
        location_id=belief_location or feedback.attempted_location_id,
        belief_node_id=f"habit:{feedback.target_entity.entity_id}",
        belief_snapshot_id=snapshot_id or revisions.belief_snapshot_id,
        node_content_hash="a" * 64,
        prior_probability=prior,
    )
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=T1,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=5)),
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


def _likelihood(action_type, outcomes):
    return ActionOutcomeLikelihoodModel(
        action_type=action_type,
        p_outcome_given_target_present=outcomes[0],
        p_outcome_given_target_absent=outcomes[1],
        calibration_domain="fixture",
        model_version="likelihood@0.1",
    )


_SEARCH_LL = (
    {RobotActionOutcome.SUCCESS: 0.8, RobotActionOutcome.UNKNOWN: 0.2},
    {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
)
_PLACE_LL = (
    {RobotActionOutcome.SUCCESS: 0.8, RobotActionOutcome.OBJECT_SLIPPED: 0.2},
    {RobotActionOutcome.SUCCESS: 0.3, RobotActionOutcome.OBJECT_SLIPPED: 0.7},
)


def test_search_found_routes_to_target_presence_not_habit():
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.SEARCH, _SEARCH_LL),
    )
    assert projected.route is FeedbackRoute.TARGET_PRESENCE
    assert projected.updates_owner_habit_directly is False
    assert projected.location_transition is None
    assert projected.target_presence_update.posterior_target_present > 0.5


def test_prior_is_bound_to_the_snapshot_node_and_object():
    # P0-1 probe: a belief ref for a DIFFERENT object cannot be reused here.
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    with pytest.raises(ValueError, match="belief object does not match"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=fb,
            binding=_binding(fb, belief_object=OTHER_OBJ),
            likelihood_model=_likelihood(
                RobotActionType.SEARCH,
                ({RobotActionOutcome.SUCCESS: 1.0}, {RobotActionOutcome.SUCCESS: 1.0}),
            ),
        )


def test_prior_snapshot_id_must_match_the_decision_snapshot():
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    with pytest.raises(ValueError, match="belief snapshot does not match"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=fb,
            binding=_binding(fb, snapshot_id=uuid4()),
            likelihood_model=_likelihood(
                RobotActionType.SEARCH,
                ({RobotActionOutcome.SUCCESS: 1.0}, {RobotActionOutcome.SUCCESS: 1.0}),
            ),
        )


def test_prior_value_comes_from_the_bound_ref():
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb, prior=0.2),
        likelihood_model=_likelihood(RobotActionType.SEARCH, _SEARCH_LL),
    )
    assert projected.target_presence_update.prior_target_present == 0.2


def test_place_success_is_positive_candidate_needing_actor():
    fb = _feedback(
        RobotActionType.PLACE,
        {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.OBJECT_SLIPPED: 0.1},
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.PLACE, _PLACE_LL),
    )
    assert projected.route is FeedbackRoute.LOCATION_TRANSITION
    assert projected.requires_actor_responsibility is True
    assert projected.updates_owner_habit_directly is False
    assert projected.location_transition.candidate is TransitionCandidate.POSITIVE_CANDIDATE
    assert projected.location_transition.candidate_likelihood_ratio > 1.0


def test_slip_is_a_negative_candidate():
    fb = _feedback(
        RobotActionType.PLACE,
        {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.OBJECT_SLIPPED: 0.9},
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.PLACE, _PLACE_LL),
    )
    assert projected.location_transition.candidate is TransitionCandidate.NEGATIVE_CANDIDATE
    assert projected.location_transition.candidate_likelihood_ratio < 1.0


def test_replay_is_noop_but_forged_content_and_changed_inputs_are_rejected():
    projector = ExecutionFeedbackProjector()
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    binding = _binding(fb)
    ll = _likelihood(RobotActionType.SEARCH, _SEARCH_LL)
    first = projector.project_execution_feedback(feedback=fb, binding=binding, likelihood_model=ll)
    assert first.is_replay is False
    assert projector.project_execution_feedback(
        feedback=fb, binding=binding, likelihood_model=ll
    ).is_replay
    # Same record id, different feedback content -> collision.
    forged = fb.model_copy(update={"action_id": uuid4()})
    with pytest.raises(ValueError, match="collision"):
        projector.project_execution_feedback(
            feedback=forged, binding=_binding(forged), likelihood_model=ll
        )
    # Same feedback, different projection inputs (a different likelihood) -> hard reject.
    other_ll = _likelihood(
        RobotActionType.SEARCH,
        (
            {RobotActionOutcome.SUCCESS: 0.6, RobotActionOutcome.UNKNOWN: 0.4},
            {RobotActionOutcome.SUCCESS: 0.2, RobotActionOutcome.UNKNOWN: 0.8},
        ),
    )
    with pytest.raises(ProjectionInputConflictError):
        projector.project_execution_feedback(
            feedback=fb, binding=binding, likelihood_model=other_ll
        )


def test_canonical_hash_ignores_outcome_dict_order():
    projector = ExecutionFeedbackProjector()
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    binding = _binding(fb)
    ll = _likelihood(RobotActionType.SEARCH, _SEARCH_LL)
    projector.project_execution_feedback(feedback=fb, binding=binding, likelihood_model=ll)
    # Same record, outcomes re-inserted in a different order -> canonical hash
    # matches, so this is a no-op replay, not a false collision.
    reordered = fb.model_copy(
        update={
            "outcome_distribution": {
                RobotActionOutcome.UNKNOWN: 0.1,
                RobotActionOutcome.SUCCESS: 0.9,
            }
        }
    )
    assert projector.project_execution_feedback(
        feedback=reordered, binding=binding, likelihood_model=ll
    ).is_replay


def test_schema_and_surface_are_enforced():
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    ll = _likelihood(
        RobotActionType.SEARCH,
        ({RobotActionOutcome.SUCCESS: 1.0}, {RobotActionOutcome.SUCCESS: 1.0}),
    )
    wrong_surface = _binding(fb).model_copy(update={"surface": DecisionSurface.MAP_SNAPSHOT})
    with pytest.raises(ValueError, match="surface"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=fb, binding=wrong_surface, likelihood_model=ll
        )
    bad_schema = fb.model_copy(
        update={"metadata": fb.metadata.model_copy(update={"schema_name": "cpswm.Wrong"})}
    )
    with pytest.raises(ValueError, match="schema_name"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=bad_schema, binding=_binding(bad_schema), likelihood_model=ll
        )


def test_feedback_interval_must_lie_within_context_validity():
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    fb = fb.model_copy(
        update={"valid_time": ValidTimeInterval(start=T1, end=T1 + timedelta(hours=6))}
    )
    ll = _likelihood(
        RobotActionType.SEARCH,
        ({RobotActionOutcome.SUCCESS: 1.0}, {RobotActionOutcome.SUCCESS: 1.0}),
    )
    with pytest.raises(ValueError, match="valid time"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=fb, binding=_binding(fb), likelihood_model=ll
        )
