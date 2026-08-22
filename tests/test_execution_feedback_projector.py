"""ExecutionFeedbackProjector: hardened likelihood-aware routing (review fix #4)."""

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


def _feedback(action_type, outcomes, *, record_id=None):
    meta = BaseRecordMetadata(
        record_id=record_id or uuid4(),
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


def _binding(feedback, *, prior=0.5):
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
        target_presence_prior=prior,
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


def test_place_success_is_a_positive_location_transition_needing_actor():
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
    assert projected.location_transition.is_positive_transition is True
    assert projected.location_transition.location_id == L2


def test_slip_is_never_a_positive_transition():
    fb = _feedback(
        RobotActionType.PLACE,
        {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.OBJECT_SLIPPED: 0.9},
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb),
        likelihood_model=_likelihood(RobotActionType.PLACE, _PLACE_LL),
    )
    assert projected.location_transition.is_positive_transition is False
    assert projected.location_transition.slipped_probability == 0.9


def test_prior_comes_from_the_bound_snapshot_not_the_caller():
    fb = _feedback(
        RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1}
    )
    projected = ExecutionFeedbackProjector().project_execution_feedback(
        feedback=fb,
        binding=_binding(fb, prior=0.2),
        likelihood_model=_likelihood(RobotActionType.SEARCH, _SEARCH_LL),
    )
    assert projected.target_presence_update.prior_target_present == 0.2


def test_missing_prior_in_context_is_rejected():
    fb = _feedback(RobotActionType.SEARCH, {RobotActionOutcome.SUCCESS: 1.0})
    binding = _binding(fb)
    stripped = binding.decision_context.model_dump()
    stripped["target_presence_prior"] = None
    stripped["context_hash"] = ""  # recompute
    binding = binding.model_copy(
        update={"decision_context": DecisionContext.model_validate(stripped)}
    )
    only_success = ({RobotActionOutcome.SUCCESS: 1.0}, {RobotActionOutcome.SUCCESS: 1.0})
    with pytest.raises(ValueError, match="target_presence_prior"):
        ExecutionFeedbackProjector().project_execution_feedback(
            feedback=fb,
            binding=binding,
            likelihood_model=_likelihood(RobotActionType.SEARCH, only_success),
        )


def test_replay_same_record_is_noop_but_forged_content_is_rejected():
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
    # Same record id, different content (a different action id) -> collision rejected.
    forged = fb.model_copy(update={"action_id": uuid4()})
    with pytest.raises(ValueError, match="collision"):
        projector.project_execution_feedback(
            feedback=forged, binding=_binding(forged), likelihood_model=ll
        )


def test_wrong_surface_and_tampered_context_are_rejected():
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
