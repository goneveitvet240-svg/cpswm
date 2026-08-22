"""ExecutionFeedbackProjector: likelihood-aware routing + dedup (review fix #4)."""

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
    ValidTimeInterval,
)
from cpswm.system.continual.execution_feedback_projector import (
    ExecutionFeedbackProjector,
    FeedbackRoute,
)

OBJ = UUID(int=5)
L2 = UUID(int=2)
T1 = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


def _feedback(action_type, outcomes):
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
        target_entity=EntityRef(entity_id=OBJ, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=L2,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=1)),
        outcome_distribution=outcomes,
        task_goal_satisfied_probability=min(outcomes.get(RobotActionOutcome.SUCCESS, 0.0), 0.9),
    )


def _binding(feedback):
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=T1,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=5)),
        staleness_budget_seconds=60.0,
        revisions=MapConsistencyRevisions(
            belief_snapshot_id=uuid4(),
            projection_id=uuid4(),
            projection_version=1,
            static_map_revision=1,
            dynamic_map_revision=1,
            event_history_revision=1,
            input_watermark=1,
        ),
        authorization_scope_id=uuid4(),
        habit_regime_model_version="m@1",
        model_versions=(("loop", "e2e@0.1"),),
        code_version="git:test",
        rationale="ctx",
    )
    return DecisionContextBinding(
        metadata=feedback.metadata.model_copy(update={"record_id": uuid4()}),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=feedback.metadata.household_id,
        subject_session_id=feedback.metadata.session_id,
        subject_trace_id=feedback.metadata.trace_id,
        decision_context=context,
    )


def _likelihood(action_type):
    return ActionOutcomeLikelihoodModel(
        action_type=action_type,
        p_outcome_given_target_present={
            RobotActionOutcome.SUCCESS: 0.8,
            RobotActionOutcome.UNKNOWN: 0.2,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.SUCCESS: 0.1,
            RobotActionOutcome.UNKNOWN: 0.9,
        },
        calibration_domain="fixture",
        model_version="likelihood@0.1",
    )


def test_search_found_routes_to_target_presence_not_habit():
    fb = _feedback(
        RobotActionType.SEARCH,
        {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1},
    )
    projected = ExecutionFeedbackProjector().project(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.SEARCH),
        prior_target_present=0.5,
    )
    assert projected.route is FeedbackRoute.TARGET_PRESENCE
    assert projected.updates_owner_habit_directly is False
    assert projected.requires_actor_responsibility is False
    # A "found" outcome raises target-presence belief.
    assert projected.target_presence_update.posterior_target_present > 0.5


def test_place_routes_to_location_transition_needing_actor_responsibility():
    fb = _feedback(
        RobotActionType.PLACE,
        {RobotActionOutcome.SUCCESS: 0.8, RobotActionOutcome.UNKNOWN: 0.2},
    )
    projected = ExecutionFeedbackProjector().project(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.PLACE),
        prior_target_present=0.5,
    )
    assert projected.route is FeedbackRoute.LOCATION_TRANSITION
    assert projected.requires_actor_responsibility is True
    # Even a place outcome does not write owner habit directly.
    assert projected.updates_owner_habit_directly is False
    assert projected.location_id == L2


def test_replaying_the_same_feedback_is_a_no_op():
    projector = ExecutionFeedbackProjector()
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    binding = _binding(fb)
    likelihood = _likelihood(RobotActionType.SEARCH)
    first = projector.project(
        feedback=fb, binding=binding, likelihood_model=likelihood, prior_target_present=0.5
    )
    second = projector.project(
        feedback=fb, binding=binding, likelihood_model=likelihood, prior_target_present=0.5
    )
    assert first.is_replay is False
    assert second.is_replay is True
    assert second.target_presence_update == first.target_presence_update


def test_mismatched_action_type_and_binding_are_rejected():
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    with pytest.raises(ValueError, match="action type"):
        ExecutionFeedbackProjector().project(
            feedback=fb,
            binding=_binding(fb),
            likelihood_model=_likelihood(RobotActionType.PLACE),
            prior_target_present=0.5,
        )
    other = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    with pytest.raises(ValueError, match="binding must reference"):
        ExecutionFeedbackProjector().project(
            feedback=fb,
            binding=_binding(other),  # references a different feedback record
            likelihood_model=_likelihood(RobotActionType.SEARCH),
            prior_target_present=0.5,
        )
