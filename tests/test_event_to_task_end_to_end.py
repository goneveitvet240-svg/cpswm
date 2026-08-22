"""End-to-end ORRER -> RGRC -> map -> task, driven by the real CHEH engine.

Proves the full causal chain 结构二 §1 asks for: a hidden event mis-attributed to
the owner contaminates the owner habit; ORRER re-attributes it to the guest; RGRC
reversibly retracts the contaminating update so the owner belief recovers; the map
projection revision advances; and a task pinned to the pre-revision snapshot is
told to REPLAN, with execution feedback bound to a consistent DecisionContext.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    DecisionContextBinding,
    DecisionSurface,
    ObservationDetectionResult,
    ObservationOutcome,
    RelevantChange,
    SourceType,
)
from cpswm.contracts.decision_context import MapConsistencyRevisions
from cpswm.system.continual import EventToTaskConsolidationLoop
from cpswm.system.counterfactual_event_hypergraph import CounterfactualEventHypergraphEngine

OWNER = "owner"
GUEST = "guest"
UNKNOWN = "unknown_actor"
OBJ = UUID(int=5)
L1 = UUID(int=1)  # where the object was
L2 = UUID(int=2)  # where it ended up (a guest moved it)
T0 = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)


def _base_metadata():
    return BaseRecordMetadata(
        schema_name="cpswm.ObservationDetectionResult",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        recorded_time=T0,
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


def _guest_actor_evidence(base, after):
    return ActorResponsibilityEvidence(
        metadata=base.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ActorResponsibilityEvidence",
                "source_type": SourceType.MODEL,
                "recorded_time": T1,
            }
        ),
        source_detection_result_id=after.metadata.record_id,  # destination endpoint
        object_instance_id=OBJ,
        evidence_time=T1,
        actor_posterior={OWNER: 0.05, GUEST: 0.9, UNKNOWN: 0.05},
        reference_actor_prior={OWNER: 0.7, GUEST: 0.2, UNKNOWN: 0.1},
        evidence_cluster_id=uuid4(),
        effective_sample_weight=1.0,
        evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
        evidence_model_id="orrer-actor-evidence@0.1",
    )


def _loop():
    base_revisions = MapConsistencyRevisions(
        belief_snapshot_id=uuid4(),
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=5,
        dynamic_map_revision=10,
        event_history_revision=3,
        input_watermark=0,
    )
    return EventToTaskConsolidationLoop(
        owner_key=OWNER,
        base_revisions=base_revisions,
        authorization_scope_id=uuid4(),
        model_version="hier-dirichlet@0.1",
        code_version="git:test",
    )


def test_end_to_end_orrer_rgrc_map_task():
    engine = CounterfactualEventHypergraphEngine()
    base = _base_metadata()
    before = _detection(base, location=L1, detection_time=T0)
    after = _detection(base, location=L2, detection_time=T1)

    # CHEH branch mis-attributes the move mostly to the owner (owner prior high).
    history0 = engine.branch(
        before=before, after=after, actor_prior={OWNER: 0.7, GUEST: 0.2, UNKNOWN: 0.1}
    )

    loop = _loop()
    contaminated = loop.ingest_event_history(history0)
    # The owner habit is contaminated at L2.
    assert contaminated.owner_mass > 0.3
    assert loop.owner_projection(object_instance_id=OBJ)[L2] == contaminated.owner_mass

    # A task planned now, pinned to the pre-revision map snapshot.
    pinned_context = loop.decision_context(
        decision_time=T1, rationale="fetch the object from its owner-habit location"
    )
    old_dynamic_revision = loop.revisions.dynamic_map_revision

    # ORRER re-attributes the hidden event to the guest.
    history1 = engine.revise_actor_responsibility(history0, _guest_actor_evidence(base, after))
    corrected = loop.apply_orrer_revision(
        history1, superseded_revision_id=history0.latest.revision_id
    )

    # RGRC recovered the owner belief: much less owner mass at L2 than before.
    assert corrected.owner_mass < contaminated.owner_mass
    recovered = loop.owner_projection(object_instance_id=OBJ)
    assert recovered.get(L2, 0.0) < contaminated.owner_mass
    # Ledger stays consistent end to end: cache == full from-log rebuild.
    rebuilt, _cost = loop.ledger.rebuild_projection_from_log(
        actor_key=OWNER, object_instance_id=OBJ, parameter_block="owner_habit_location"
    )
    assert recovered == rebuilt

    # The map projection advanced because the belief changed.
    assert loop.revisions.dynamic_map_revision == old_dynamic_revision + 1

    # The task pinned to the stale snapshot must REPLAN (target belief moved).
    decision = loop.task_decision(pinned_context, target_object_moved=True)
    assert decision is RelevantChange.REPLAN

    # A fresh task on the current snapshot with no relevant change may CONTINUE.
    fresh_context = loop.decision_context(decision_time=T1, rationale="fresh plan")
    assert loop.task_decision(fresh_context, target_object_moved=False) is RelevantChange.CONTINUE

    # Execution feedback is bound to a context consistent with this household/session/trace.
    feedback_meta = BaseRecordMetadata(
        schema_name="cpswm.DecisionContextBinding",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        recorded_time=T1,
        source_type=SourceType.ACTION,
        source_id="executor",
    )
    binding = DecisionContextBinding(
        metadata=feedback_meta,
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=uuid4(),
        subject_household_id=feedback_meta.household_id,
        subject_session_id=feedback_meta.session_id,
        subject_trace_id=feedback_meta.trace_id,
        decision_context=fresh_context,
    )
    assert binding.surface is DecisionSurface.EXECUTION_FEEDBACK
    assert binding.decision_context.verify_hash()
