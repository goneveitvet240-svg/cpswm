"""Runnable spine for the project-two feedback -> reversible-attribution loop.

Builds one open-world hidden-event branch (an object seen at L1, later at L2),
then folds two execution-feedback records back in as counterfactual evidence:

1. a *failed* search at L2 -> the responsible-actor posteriors fall (softly),
   unresolved/unknown mass rises, and an explicit project-one retract/correct
   request is emitted;
2. a *successful* search at L2 -> the corroborated chains are reinforced.

Run:  PYTHONPATH=src python apps/prototype_spine/run_project_two_feedback_demo.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
    ProjectTwoFeedbackRevisionLoop,
)
from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    UNKNOWN_ACTOR,
    EventRevisionOutcome,
)

OWNER = "owner"
GUEST = "guest"
OBJ = UUID(int=5)
L1 = UUID(int=1)
L2 = UUID(int=2)
# Shared household/session/trace so feedback binds to the same event context.
HH = UUID(int=100)
SS = UUID(int=101)
TT = UUID(int=102)
TA = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
TB = TA + timedelta(hours=1)
TF = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)

_SEARCH_LL = (
    {RobotActionOutcome.SUCCESS: 0.85, RobotActionOutcome.UNKNOWN: 0.15},
    {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9},
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
    base = BaseRecordMetadata(
        schema_name="cpswm.ObservationDetectionResult",
        schema_version="0.1.0",
        household_id=HH,
        session_id=SS,
        trace_id=TT,
        recorded_time=TA,
        source_type=SourceType.SIMULATION,
        source_id="sim",
    )
    return engine.branch(
        before=_detection(base, location=L1, detection_time=TA),
        after=_detection(base, location=L2, detection_time=TB),
        actor_prior={OWNER: 0.6, GUEST: 0.3, UNKNOWN_ACTOR: 0.1},
    )


def _feedback(outcomes):
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
        action_type=RobotActionType.SEARCH,
        target_entity=EntityRef(entity_id=OBJ, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=L2,
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
        object_instance_id=OBJ,
        location_id=L2,
        belief_node_id=f"habit:{OBJ}",
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
        code_version="git:demo",
        rationale="demo",
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


def _likelihood():
    return ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present=_SEARCH_LL[0],
        p_outcome_given_target_absent=_SEARCH_LL[1],
        calibration_domain="demo",
        model_version="likelihood@0.1",
    )


def _show(title: str, outcome: EventRevisionOutcome) -> None:
    print(f"\n=== {title} ===")
    print(f"  presence likelihood ratio : {outcome.presence_likelihood_ratio:.3f}")
    print(f"  actor posterior before    : {_fmt(outcome.actor_posterior_before)}")
    print(f"  actor posterior after     : {_fmt(outcome.actor_posterior_after)}")
    print(
        f"  unresolved  before/after  : {outcome.unresolved_before:.3f} -> "
        f"{outcome.unresolved_after:.3f}"
    )
    print(
        f"  unknown mech before/after : {outcome.unknown_mechanism_before:.3f} -> "
        f"{outcome.unknown_mechanism_after:.3f}"
    )
    print(
        f"  owner mass  before/after  : {outcome.owner_mass_before:.3f} -> "
        f"{outcome.owner_mass_after:.3f}"
    )
    print(
        f"  superseded -> corrected   : {outcome.superseded_revision_id} -> "
        f"{outcome.corrected_revision_id}"
    )
    for request in outcome.project_one_requests:
        print(
            f"  project-one request       : {request.kind.value} "
            f"owner_mass_delta={request.owner_mass_delta:+.3f} location={request.location_id}"
        )


def _fmt(distribution: dict) -> str:
    return "{" + ", ".join(f"{k}:{v:.3f}" for k, v in sorted(distribution.items())) + "}"


def main() -> None:
    loop = ProjectTwoFeedbackRevisionLoop(projector=ExecutionFeedbackProjector())
    history = _history()
    print(
        f"branched hidden-event set with {len(history.latest.hypotheses)} hypotheses; "
        f"unknown_mechanism={history.latest.unknown_mechanism_probability:.3f}; "
        f"unresolved={history.latest.unresolved_probability:.3f}"
    )

    failed = _feedback({RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.UNKNOWN: 0.9})
    history, outcome = loop.ingest_feedback(
        history=history,
        feedback=failed,
        binding=_binding(failed),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    _show("feedback 1: search FAILED at L2 (reversible down-weight)", outcome)

    found = _feedback({RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1})
    history, outcome = loop.ingest_feedback(
        history=history,
        feedback=found,
        binding=_binding(found),
        likelihood_model=_likelihood(),
        owner_key=OWNER,
    )
    _show("feedback 2: search SUCCEEDED at L2 (reinforce)", outcome)

    print(
        f"\nfinal history has {len(history.revisions)} reversible revisions "
        f"(branch + 2 feedback revisions); every prior revision remains traceable."
    )


if __name__ == "__main__":
    main()
