"""End-to-end ORRER -> Hybrid RGRC -> real snapshot -> MapTaskCoordinator -> feedback.

The successor path to the legacy happy-path loop: it drives the *real* Hybrid
RGRC ledger, the versioned belief map, and the map/task coordinator, all from a
real CHEH/ORRER revision.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    ObservationDetectionResult,
    ObservationOutcome,
    SourceType,
)
from cpswm.system.continual.event_to_task_loop import owner_placement
from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridEventToTaskCoordinatorLoop,
    OwnerPlacementInput,
)
from cpswm.system.counterfactual_event_hypergraph import CounterfactualEventHypergraphEngine
from cpswm.world_model.grounded_search.concurrent_map_task import (
    BayesianRisk,
    BeliefSnapshot,
    TaskAction,
    TaskActionGraph,
    VersionSwitchKind,
)

OWNER = "owner"
GUEST = "guest"
UNKNOWN = "unknown_actor"
OBJ = UUID(int=5)
L1 = UUID(int=1)
L2 = UUID(int=2)
T0 = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)


class _UncertaintyRiskVerifier:
    """Exact-verifier stub: an action's risk rises with its read nodes' uncertainty."""

    def assess(self, action: TaskAction, snapshot: BeliefSnapshot) -> BayesianRisk:
        nodes = {node.node_id: node for node in snapshot.nodes}
        penalty = sum(
            nodes[node_id].uncertainty for node_id in action.hard_read_nodes if node_id in nodes
        )
        return BayesianRisk(expected_task_loss=0.0, uncertainty_penalty=penalty)


def _base():
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


def _placement_input(history):
    placement = owner_placement(history.latest, OWNER)
    revision = history.latest
    return OwnerPlacementInput(
        event_hypothesis_id=history.hypothesis_set_id,
        revision_id=revision.revision_id,
        destination_location_id=revision.destination_location_id,
        owner_mass=placement.owner_mass,
        source_record_id=revision.source_detection_result_ids[-1],
        parent_revision_id=revision.parent_revision_id,
    )


def test_hybrid_end_to_end_orrer_rgrc_snapshot_coordinator_feedback():
    engine = CounterfactualEventHypergraphEngine()
    base = _base()
    before = _detection(base, location=L1, detection_time=T0)
    after = _detection(base, location=L2, detection_time=T1)
    history0 = engine.branch(
        before=before, after=after, actor_prior={OWNER: 0.7, GUEST: 0.2, UNKNOWN: 0.1}
    )

    loop_auth = uuid4()
    loop = HybridEventToTaskCoordinatorLoop(
        owner_key=OWNER,
        object_instance_id=OBJ,
        authorization_scope_id=loop_auth,
        model_version="hier-dirichlet@0.1",
        code_version="git:test",
    )

    # Contamination consolidated into the real Hybrid RGRC ledger.
    loop.ingest_owner_placement(_placement_input(history0))
    contaminated_snapshot = loop.publish_snapshot(changed_locations={L2})
    contaminated_alpha = loop.ledger.projection(loop._key(L2)).alpha
    assert contaminated_alpha > 0.3

    # A task that reads the L2 habit node, pinned to the contaminated snapshot.
    task = TaskActionGraph(
        task_id=uuid4(),
        actions=(
            TaskAction(action_id="fetch", order=0, hard_read_nodes=frozenset({loop.node_id(L2)})),
        ),
    )

    # ORRER re-attributes the move to the guest.
    evidence = ActorResponsibilityEvidence(
        metadata=base.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ActorResponsibilityEvidence",
                "source_type": SourceType.MODEL,
                "recorded_time": T1,
            }
        ),
        source_detection_result_id=after.metadata.record_id,
        object_instance_id=OBJ,
        evidence_time=T1,
        actor_posterior={OWNER: 0.05, GUEST: 0.9, UNKNOWN: 0.05},
        reference_actor_prior={OWNER: 0.7, GUEST: 0.2, UNKNOWN: 0.1},
        evidence_cluster_id=uuid4(),
        effective_sample_weight=1.0,
        evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
        evidence_model_id="orrer-actor-evidence@0.1",
    )
    history1 = engine.revise_actor_responsibility(history0, evidence)

    new_snapshot = loop.apply_orrer_revision(
        superseded_revision_id=history0.latest.revision_id,
        corrected=_placement_input(history1),
    )

    # RGRC recovered the owner belief at L2 (Hybrid ledger projection dropped).
    recovered_alpha = loop.ledger.projection(loop._key(L2)).alpha
    assert recovered_alpha < contaminated_alpha
    # Hybrid ledger stays consistent: cached projection == from-log rebuild.
    assert loop.ledger.projection(loop._key(L2)).alpha == (
        loop.ledger.rebuild_projection(loop._key(L2)).alpha
    )

    # A new atomic map version was published; the L2 habit node changed.
    assert new_snapshot.map_version > contaminated_snapshot.map_version
    assert loop.node_id(L2) in contaminated_snapshot.changed_nodes(new_snapshot)

    # The MapTaskCoordinator switches the pinned task because its read node changed.
    decision = loop.evaluate_task(
        task=task,
        current_action_order=0,
        old_snapshot=contaminated_snapshot,
        new_snapshot=new_snapshot,
        verifier=_UncertaintyRiskVerifier(),
    )
    assert decision.kind in {VersionSwitchKind.REPLAN_SUFFIX, VersionSwitchKind.CANCEL}
    assert loop.node_id(L2) in decision.changed_belief_nodes

    # Feedback backflow (review fix #4): a SEARCH "found the object" outcome
    # updates target presence only and must NOT inflate the owner habit.
    before_feedback = loop.ledger.projection(loop._key(L2)).alpha
    feedback, binding, likelihood = _search_found_feedback(base, loop_auth)
    projected = loop.project_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood
    )
    after_feedback = loop.ledger.projection(loop._key(L2)).alpha
    assert after_feedback == before_feedback  # found != owner-habit increase
    assert projected.route.value == "target_presence"
    assert projected.updates_owner_habit_directly is False
    assert projected.target_presence_update.posterior_target_present > 0.5
    # Replaying the same feedback record is a no-op.
    assert loop.project_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood
    ).is_replay


def _search_found_feedback(base, loop_auth):
    from cpswm.contracts import (
        ActionOutcomeLikelihoodModel,
        DecisionContextBinding,
        DecisionSurface,
        MapConsistencyRevisions,
        RobotActionOutcome,
        RobotActionType,
    )
    from cpswm.contracts.base import ValidTimeInterval
    from cpswm.contracts.decision_context import DecisionContext

    fb_meta = base.model_copy(
        update={
            "record_id": uuid4(),
            "schema_name": "cpswm.ExecutionFeedbackRecord",
            "source_type": SourceType.ACTION,
            "recorded_time": T1,
        }
    )
    from cpswm.contracts import EntityRef, EntityType, ExecutionFeedbackRecord

    feedback = ExecutionFeedbackRecord(
        metadata=fb_meta,
        action_id=uuid4(),
        action_type=RobotActionType.SEARCH,
        target_entity=EntityRef(entity_id=OBJ, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=L2,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=1)),
        outcome_distribution={RobotActionOutcome.SUCCESS: 0.9, RobotActionOutcome.UNKNOWN: 0.1},
        task_goal_satisfied_probability=0.9,
    )
    revisions = MapConsistencyRevisions(
        belief_snapshot_id=uuid4(),
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=1,
        dynamic_map_revision=1,
        event_history_revision=1,
        input_watermark=1,
    )
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=T1,
        valid_time=ValidTimeInterval(start=T1, end=T1 + timedelta(minutes=5)),
        staleness_budget_seconds=60.0,
        revisions=revisions,
        target_presence_prior=0.5,
        authorization_scope_id=loop_auth,
        habit_regime_model_version="m@1",
        model_versions=(("loop", "e2e@0.1"),),
        code_version="git:test",
        rationale="feedback context",
    )
    binding = DecisionContextBinding(
        metadata=fb_meta.model_copy(update={"record_id": uuid4()}),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=fb_meta.household_id,
        subject_session_id=fb_meta.session_id,
        subject_trace_id=fb_meta.trace_id,
        decision_context=context,
    )
    likelihood = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={
            RobotActionOutcome.SUCCESS: 0.8,
            RobotActionOutcome.UNKNOWN: 0.2,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.SUCCESS: 0.1,
            RobotActionOutcome.UNKNOWN: 0.9,
        },
        calibration_domain="fixture",
        model_version="search-likelihood@0.1",
    )
    return feedback, binding, likelihood


def test_irrelevant_map_change_lets_task_continue():
    loop = HybridEventToTaskCoordinatorLoop(
        owner_key=OWNER,
        object_instance_id=OBJ,
        authorization_scope_id=uuid4(),
        model_version="m@1",
        code_version="git:test",
    )
    loop.ingest_owner_placement(
        OwnerPlacementInput(
            event_hypothesis_id=uuid4(),
            revision_id=uuid4(),
            destination_location_id=L1,
            owner_mass=1.0,
            source_record_id=uuid4(),
        )
    )
    old_snapshot = loop.publish_snapshot(changed_locations={L1})
    # An unrelated location changes; the task only reads L1.
    loop.ingest_owner_placement(
        OwnerPlacementInput(
            event_hypothesis_id=uuid4(),
            revision_id=uuid4(),
            destination_location_id=L2,
            owner_mass=1.0,
            source_record_id=uuid4(),
        )
    )
    new_snapshot = loop.publish_snapshot(changed_locations={L2})
    task = TaskActionGraph(
        task_id=uuid4(),
        actions=(
            TaskAction(action_id="fetch", order=0, hard_read_nodes=frozenset({loop.node_id(L1)})),
        ),
    )
    decision = loop.evaluate_task(
        task=task,
        current_action_order=0,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        verifier=_UncertaintyRiskVerifier(),
    )
    assert decision.kind is VersionSwitchKind.CONTINUE
