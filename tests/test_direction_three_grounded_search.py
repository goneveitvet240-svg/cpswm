import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    DynamicObjectState,
    EntityType,
    EvidenceChannel,
    EvidenceRef,
    ExecutionFeedbackRecord,
    HardConstraintEvaluation,
    HardConstraintStatus,
    IdentityVerificationRequest,
    IdentityViewEvidence,
    JointCandidateEvidence,
    JointPosteriorRequest,
    MemoryEvidenceFactor,
    MemoryFactorEvidence,
    MemoryLifecycleAction,
    MemoryReliabilityRequest,
    MemoryReliabilityStatus,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    ObservationSafetyApproval,
    Pose3D,
    ResolutionStatus,
    ResponsePolicy,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    StaticGeometryAnchor,
    VerificationModality,
    VerificationObservation,
    build_query_compiler_provenance,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.world_model.grounded_search import (
    DirectionThreePipeline,
    ExecutionFeedbackProjector,
    GroundedTaskExecution,
    InformationGainPlanner,
    JointPosteriorFusion,
    LayeredSemanticMap,
    MemoryReliabilityProjector,
    MultiViewIdentityVerifier,
    OracleActionOutcomeModelProvider,
    OracleGroundedTaskExecutor,
    OracleObservationActionProvider,
    OracleVerificationObservationProvider,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def pose(x=0.0, y=0.0, z=1.0):
    return Pose3D(frame_id="map", x=x, y=y, z=z, qx=0.0, qy=0.0, qz=0.0, qw=1.0)


def query():
    utterance = "找我晚上经常放在床边用的那个东西"
    source_record_id = uuid4()
    return CompiledSemanticQuery(
        utterance=utterance,
        category_candidates=("phone", "glasses", "cup"),
        relations=("used_by", "usually_located_at"),
        time_expression="night",
        soft_constraints=("bedside", "frequently_used"),
        compiler_model_version="structured-llm@0.1",
        input_evidence_refs=(
            EvidenceRef(evidence_type="query_utterance", source_record_id=source_record_id),
        ),
        invocation_provenance=build_query_compiler_provenance(
            provider="test-fixture",
            model="structured-llm",
            version="0.1",
            temperature=0.0,
            prompt_template_version="grounded-search-test@0.1",
            prompt=utterance,
            input_evidence_refs=(source_record_id,),
        ),
    )


def channels(likelihoods):
    return {
        channel: ChannelEvidence(
            likelihood_given_candidate=likelihood,
            model_version=f"{channel.value}@0.1",
            calibration_domain="symbolic-household-v0",
        )
        for channel, likelihood in zip(EvidenceChannel, likelihoods, strict=True)
    }


def joint_request(metadata_factory, entity_factory, *, ambiguous=False, top_k=3):
    phone = entity_factory(EntityType.OBJECT_INSTANCE)
    glasses = entity_factory(EntityType.OBJECT_INSTANCE)
    phone_scores = (0.91, 0.88, 0.82, 0.90, 0.93, 0.89)
    glasses_scores = (
        (0.90, 0.87, 0.81, 0.89, 0.92, 0.88) if ambiguous else (0.45, 0.40, 0.55, 0.35, 0.50, 0.42)
    )
    candidates = (
        JointCandidateEvidence(
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=phone,
            location_id=uuid4(),
            prior_probability=0.45,
            channel_evidence=channels(phone_scores),
        ),
        JointCandidateEvidence(
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=glasses,
            location_id=uuid4(),
            prior_probability=0.40,
            channel_evidence=channels(glasses_scores),
        ),
        JointCandidateEvidence(
            kind=CandidateKind.UNKNOWN,
            prior_probability=0.15,
            channel_evidence=channels((0.20, 0.20, 0.20, 0.20, 0.20, 0.20)),
        ),
    )
    return JointPosteriorRequest(
        metadata=metadata_factory(schema_name="cpswm.JointPosteriorRequest"),
        compiled_query=query(),
        candidates=candidates,
        top_k=top_k,
        resolution_threshold=0.65,
        ambiguity_margin=0.12,
        unknown_threshold=0.45,
    )


def test_joint_posterior_uses_all_six_channels_and_retains_unknown(
    metadata_factory, entity_factory
):
    request = joint_request(metadata_factory, entity_factory)
    result = JointPosteriorFusion().fuse(request)

    assert result.resolution_status == ResolutionStatus.RESOLVED
    assert result.response_policy == ResponsePolicy.RETURN_TOP_K
    assert result.candidates[0].kind == CandidateKind.OBJECT_INSTANCE
    assert {item.channel for item in result.candidates[0].contributions} == set(EvidenceChannel)
    unknown_id = next(
        item.candidate_id for item in request.candidates if item.kind == CandidateKind.UNKNOWN
    )
    assert result.unknown_probability == pytest.approx(result.posterior_by_candidate_id[unknown_id])
    assert sum(result.posterior_by_candidate_id.values()) == pytest.approx(1.0)
    assert result.metadata.record_id != request.metadata.record_id


def test_joint_posterior_preserves_ambiguous_and_requests_verification(
    metadata_factory, entity_factory
):
    result = JointPosteriorFusion().fuse(
        joint_request(metadata_factory, entity_factory, ambiguous=True)
    )
    assert result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert result.response_policy == ResponsePolicy.ACTIVE_VERIFY
    assert len(result.candidates) == 3


def test_ambiguous_policy_can_ask_user_instead_of_moving(metadata_factory, entity_factory):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True).model_copy(
        update={"ambiguity_policy": ResponsePolicy.ASK_USER}
    )
    result = JointPosteriorFusion().fuse(request)
    assert result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert result.response_policy == ResponsePolicy.ASK_USER


def test_unknown_candidate_can_trigger_abstention(metadata_factory, entity_factory):
    request = joint_request(metadata_factory, entity_factory)
    candidates = []
    for item in request.candidates:
        if item.kind == CandidateKind.UNKNOWN:
            candidates.append(
                item.model_copy(
                    update={
                        "prior_probability": 0.70,
                        "channel_evidence": channels((0.95, 0.95, 0.95, 0.95, 0.95, 0.95)),
                    }
                )
            )
        else:
            candidates.append(item.model_copy(update={"prior_probability": 0.15}))
    result = JointPosteriorFusion().fuse(
        request.model_copy(
            update={
                "candidates": tuple(candidates),
                "unknown_policy": ResponsePolicy.ABSTAIN,
            }
        )
    )
    assert result.resolution_status == ResolutionStatus.UNKNOWN
    assert result.response_policy == ResponsePolicy.ABSTAIN
    assert result.candidates[0].kind == CandidateKind.UNKNOWN


def test_joint_contract_rejects_missing_modalities(metadata_factory, entity_factory):
    incomplete = channels((0.8, 0.8, 0.8, 0.8, 0.8, 0.8))
    incomplete.pop(EvidenceChannel.HABIT)
    with pytest.raises(ValidationError, match="all six joint channels"):
        JointCandidateEvidence(
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=entity_factory(EntityType.OBJECT_INSTANCE),
            prior_probability=1.0,
            channel_evidence=incomplete,
        )


def test_top_k_does_not_renormalize_or_hide_unreturned_mass(metadata_factory, entity_factory):
    result = JointPosteriorFusion().fuse(joint_request(metadata_factory, entity_factory, top_k=1))
    assert len(result.candidates) == 1
    assert result.posterior_mass_returned < 1.0
    assert sum(result.posterior_by_candidate_id.values()) == pytest.approx(1.0)


def test_full_top_k_tolerates_machine_epsilon_probability_overshoot(
    metadata_factory, entity_factory
):
    request = JointPosteriorRequest(
        metadata=metadata_factory(schema_name="cpswm.JointPosteriorRequest"),
        compiled_query=query(),
        candidates=(
            JointCandidateEvidence(
                kind=CandidateKind.OBJECT_INSTANCE,
                entity=entity_factory(EntityType.OBJECT_INSTANCE),
                location_id=uuid4(),
                prior_probability=0.14955852889334198,
                channel_evidence=channels((1.0,) * len(EvidenceChannel)),
            ),
            JointCandidateEvidence(
                kind=CandidateKind.OBJECT_INSTANCE,
                entity=entity_factory(EntityType.OBJECT_INSTANCE),
                location_id=uuid4(),
                prior_probability=0.7579993673819516,
                channel_evidence=channels((1.0,) * len(EvidenceChannel)),
            ),
            JointCandidateEvidence(
                kind=CandidateKind.UNKNOWN,
                prior_probability=0.09244210372470638,
                channel_evidence=channels((1.0,) * len(EvidenceChannel)),
            ),
        ),
        top_k=3,
    )

    result = JointPosteriorFusion().fuse(request)

    assert len(result.candidates) == 3
    assert result.posterior_mass_returned <= 1.0
    assert sum(item.posterior_probability for item in result.candidates) > 1.0
    assert result.posterior_mass_returned == pytest.approx(
        sum(item.posterior_probability for item in result.candidates)
    )


def test_multiview_identity_requires_independent_evidence_and_can_recommend_touch():
    first, second = uuid4(), uuid4()
    same_video_cluster = uuid4()
    base = IdentityViewEvidence(
        evidence_cluster_id=same_video_cluster,
        modality=VerificationModality.RGBD,
        viewpoint_pose=pose(),
        candidate_likelihoods={first: 0.9, second: 0.1},
        quality=1.0,
    )
    duplicate_frame = base.model_copy(update={"view_id": uuid4(), "quality": 0.8})
    request = IdentityVerificationRequest(
        candidate_ids=(first, second),
        prior_probabilities={first: 0.5, second: 0.5},
        view_evidence=(base, duplicate_frame),
        required_independent_views=2,
        allow_tactile=True,
        tactile_safe=True,
    )
    ambiguous = MultiViewIdentityVerifier().verify(request)
    assert ambiguous.status == ResolutionStatus.AMBIGUOUS
    assert ambiguous.independent_view_count == 1
    assert ambiguous.recommended_modality == VerificationModality.TACTILE

    independent_view = IdentityViewEvidence(
        evidence_cluster_id=uuid4(),
        modality=VerificationModality.POINT_CLOUD,
        viewpoint_pose=pose(x=0.4),
        candidate_likelihoods={first: 0.92, second: 0.08},
        quality=1.0,
    )
    resolved = MultiViewIdentityVerifier().verify(
        request.model_copy(update={"view_evidence": (base, independent_view)})
    )
    assert resolved.status == ResolutionStatus.RESOLVED
    assert resolved.confirmed_candidate_id == first


def test_tactile_identity_evidence_requires_authorization_and_safety():
    first, second = uuid4(), uuid4()
    tactile = IdentityViewEvidence(
        evidence_cluster_id=uuid4(),
        modality=VerificationModality.TACTILE,
        candidate_likelihoods={first: 0.99, second: 0.01},
        quality=1.0,
    )
    with pytest.raises(ValidationError, match="explicit authorization"):
        IdentityVerificationRequest(
            candidate_ids=(first, second),
            prior_probabilities={first: 0.5, second: 0.5},
            view_evidence=(tactile,),
            required_independent_views=1,
            allow_tactile=False,
            tactile_safe=False,
        )
    with pytest.raises(ValidationError, match="positive safety gate"):
        IdentityVerificationRequest(
            candidate_ids=(first, second),
            prior_probabilities={first: 0.5, second: 0.5},
            view_evidence=(tactile,),
            required_independent_views=1,
            allow_tactile=True,
            tactile_safe=False,
        )


def test_hard_constraint_violation_cannot_be_resolved(metadata_factory, entity_factory):
    base = joint_request(metadata_factory, entity_factory)
    constrained_query = base.compiled_query.model_copy(update={"hard_constraints": ("color=red",)})
    candidates = []
    best_candidate_id = JointPosteriorFusion().fuse(base).candidates[0].candidate_id
    for candidate in base.candidates:
        status = (
            HardConstraintStatus.UNKNOWN
            if candidate.kind == CandidateKind.UNKNOWN
            else (
                HardConstraintStatus.VIOLATED
                if candidate.candidate_id == best_candidate_id
                else HardConstraintStatus.SATISFIED
            )
        )
        candidates.append(
            candidate.model_copy(
                update={
                    "hard_constraint_evaluations": (
                        HardConstraintEvaluation(
                            constraint="color=red",
                            status=status,
                            evaluator_model_version="oracle-constraint@0.1",
                        ),
                    )
                }
            )
        )
    request = base.model_copy(
        update={"compiled_query": constrained_query, "candidates": tuple(candidates)}
    )

    result = JointPosteriorFusion().fuse(request)

    assert result.posterior_by_candidate_id[best_candidate_id] == 0.0
    assert all(item.candidate_id != best_candidate_id for item in result.candidates)
    assert (
        result.hard_constraint_evaluations_by_candidate_id[best_candidate_id][0].status
        == HardConstraintStatus.VIOLATED
    )


def test_hard_constraint_requires_explicit_candidate_evaluations(metadata_factory, entity_factory):
    base = joint_request(metadata_factory, entity_factory)
    with pytest.raises(ValidationError, match="explicitly evaluate every hard constraint"):
        JointPosteriorRequest(
            **base.model_dump(exclude={"compiled_query"}),
            compiled_query=base.compiled_query.model_copy(
                update={"hard_constraints": ("color=red",)}
            ),
        )


def test_unknown_hard_constraint_preserves_candidate_but_prevents_resolution(
    metadata_factory, entity_factory
):
    base = joint_request(metadata_factory, entity_factory)
    constrained_query = base.compiled_query.model_copy(
        update={"hard_constraints": ("owner=current_user",)}
    )
    candidates = tuple(
        candidate.model_copy(
            update={
                "hard_constraint_evaluations": (
                    HardConstraintEvaluation(
                        constraint="owner=current_user",
                        status=HardConstraintStatus.UNKNOWN,
                        evaluator_model_version="oracle-constraint@0.1",
                    ),
                )
            }
        )
        for candidate in base.candidates
    )
    request = base.model_copy(
        update={"compiled_query": constrained_query, "candidates": candidates}
    )

    result = JointPosteriorFusion().fuse(request)

    assert result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert result.response_policy == ResponsePolicy.ACTIVE_VERIFY
    assert "hard_constraint_evidence_incomplete" in result.explanation_codes


def test_dynamic_object_moves_without_rebuilding_static_geometry(entity_factory):
    layered_map = LayeredSemanticMap()
    room = StaticGeometryAnchor(
        semantic_label="bedroom", geometry_ref="mesh://bedroom-v1", frame_id="map"
    )
    table = StaticGeometryAnchor(
        parent_anchor_id=room.anchor_id,
        semantic_label="bedside-table",
        geometry_ref="mesh://table-v1",
        frame_id="map",
    )
    layered_map.add_static_anchor(room)
    layered_map.add_static_anchor(table)
    object_instance = entity_factory(EntityType.OBJECT_INSTANCE)
    state = DynamicObjectState(
        object_instance=object_instance,
        anchor_id=table.anchor_id,
        pose=pose(),
        point_cloud_ref="pointcloud://object-view-1",
        state_probability=0.8,
    )
    layered_map.upsert_dynamic_object(state)
    static_revision = layered_map.static_revision
    layered_map.move_dynamic_object(
        state.model_copy(update={"pose": pose(x=0.7), "state_probability": 0.9})
    )

    assert layered_map.static_revision == static_revision
    assert layered_map.dynamic_revision == 2
    assert layered_map.dynamic_object(object_instance.entity_id).pose.x == 0.7


def test_dynamic_object_rejects_unregistered_pose_frame(entity_factory):
    layered_map = LayeredSemanticMap()
    room = StaticGeometryAnchor(
        semantic_label="bedroom", geometry_ref="mesh://bedroom-v1", frame_id="map"
    )
    layered_map.add_static_anchor(room)
    state = DynamicObjectState(
        object_instance=entity_factory(EntityType.OBJECT_INSTANCE),
        anchor_id=room.anchor_id,
        pose=Pose3D(
            frame_id="unregistered-camera",
            x=0.0,
            y=0.0,
            z=1.0,
            qx=0.0,
            qy=0.0,
            qz=0.0,
            qw=1.0,
        ),
        state_probability=0.8,
    )

    with pytest.raises(ValueError, match="pose frame must match"):
        layered_map.upsert_dynamic_object(state)


def action_candidate(hypotheses, *, informative, cost=0.01):
    if informative:
        outcomes = {
            "phone_seen": {
                hypotheses[0]: 0.9,
                hypotheses[1]: 0.1,
                hypotheses[2]: 0.2,
            },
            "phone_not_seen": {
                hypotheses[0]: 0.1,
                hypotheses[1]: 0.9,
                hypotheses[2]: 0.8,
            },
        }
    else:
        outcomes = {
            "uninformative_a": {item: 0.5 for item in hypotheses},
            "uninformative_b": {item: 0.5 for item in hypotheses},
        }
    return ObservationActionCandidate(
        action_type=ObservationActionType.MOVE_VIEWPOINT,
        label="inspect bedside from a new view",
        viewpoint_pose=pose(x=0.5),
        observation_likelihood_model_id="oracle-rgbd@0.1",
        calibration_domain="symbolic-household-v0",
        outcome_likelihoods=outcomes,
        motion_cost=cost,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )


def execution_opportunity(metadata, action_id):
    return ObservationOpportunityRecord(
        metadata=metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ObservationOpportunityRecord",
                "source_type": SourceType.SENSOR,
            }
        ),
        observation_action_id=action_id,
        opportunity_time=metadata.recorded_time,
        selected=True,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        likelihood_model_id="search-observation@0.1",
    )


def task_execution(target, feedback, *, opportunities=(), **updates):
    execution = GroundedTaskExecution(
        selected_target_candidate_id=target.candidate_id,
        target_entity=target.entity,
        target_location_id=target.location_id,
        executed_action_id=feedback.action_id,
        executed_action_type=feedback.action_type,
        action_outcome_model_version=(
            "oracle-search-outcome@0.1" if feedback.action_type == RobotActionType.SEARCH else None
        ),
        action_outcome_calibration_domain=(
            "symbolic-household-v0" if feedback.action_type == RobotActionType.SEARCH else None
        ),
        observation_opportunities=tuple(opportunities),
        feedback_records=(feedback,),
    )
    return execution.model_copy(update=updates) if updates else execution


class StaticActionProvider:
    def __init__(self, actions):
        self.actions = tuple(actions)

    def propose(self, belief):
        del belief
        return self.actions


class StaticObservationProvider:
    def __init__(self, observation):
        self.observation = observation

    def observe(self, action, belief):
        del action, belief
        return self.observation


def run_observation_only(request, action, observation, log):
    return DirectionThreePipeline().run_closed_loop(
        request,
        action_provider=StaticActionProvider((action,)),
        observation_provider=StaticObservationProvider(observation),
        task_executor=OracleGroundedTaskExecutor({}),
        outcome_model_provider=OracleActionOutcomeModelProvider({}),
        canonical_log=log,
        max_cycles=1,
    )


@pytest.mark.parametrize("entrypoint", ("decide", "run_closed_loop"))
@pytest.mark.parametrize("extra_path", ("request", "metadata"))
def test_direction_three_rejects_recursive_live_extras_on_input(
    metadata_factory, entity_factory, entrypoint, extra_path
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    if extra_path == "request":
        request = request.model_copy(update={"forged_input": True})
    else:
        request = request.model_copy(
            update={"metadata": request.metadata.model_copy(update={"forged_input": True})}
        )
    log = AppendOnlyTransactionLog()
    pipeline = DirectionThreePipeline()

    with pytest.raises(ValueError, match="fields outside its contract"):
        if entrypoint == "decide":
            pipeline.decide(request)
        else:
            pipeline.run_closed_loop(
                request,
                action_provider=OracleObservationActionProvider(()),
                observation_provider=OracleVerificationObservationProvider({}),
                task_executor=OracleGroundedTaskExecutor({}),
                outcome_model_provider=OracleActionOutcomeModelProvider({}),
                canonical_log=log,
                max_cycles=1,
            )

    assert log.latest_watermark().global_commit_seq == 0


def test_closed_loop_round_trip_revalidates_forged_request_without_a_write(
    metadata_factory, entity_factory
):
    request = joint_request(metadata_factory, entity_factory)
    candidates = list(request.candidates)
    candidates[0] = candidates[0].model_copy(update={"prior_probability": 0.9})
    forged = request.model_copy(update={"candidates": tuple(candidates)})
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match="prior probabilities must sum to 1"):
        DirectionThreePipeline().run_closed_loop(
            forged,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=log,
            max_cycles=1,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize("entrypoint", ("decide", "run_closed_loop"))
@pytest.mark.parametrize("mutation", ("name", "version"))
def test_direction_three_request_requires_canonical_schema_label(
    metadata_factory, entity_factory, entrypoint, mutation
):
    request = joint_request(metadata_factory, entity_factory)
    metadata_update = (
        {"schema_name": "cpswm.VerificationObservation"}
        if mutation == "name"
        else {"schema_version": "9.9.9"}
    )
    request = request.model_copy(
        update={"metadata": request.metadata.model_copy(update=metadata_update)}
    )
    log = AppendOnlyTransactionLog()
    pipeline = DirectionThreePipeline()

    with pytest.raises(ValueError, match=f"schema {mutation}"):
        if entrypoint == "decide":
            pipeline.decide(request)
        else:
            pipeline.run_closed_loop(
                request,
                action_provider=OracleObservationActionProvider(()),
                observation_provider=OracleVerificationObservationProvider({}),
                task_executor=OracleGroundedTaskExecutor({}),
                outcome_model_provider=OracleActionOutcomeModelProvider({}),
                canonical_log=log,
                max_cycles=1,
            )

    assert log.latest_watermark().global_commit_seq == 0


def test_information_gain_selects_discriminative_view_not_fixed_order():
    hypotheses = (uuid4(), uuid4(), uuid4())
    prior = {hypotheses[0]: 0.45, hypotheses[1]: 0.40, hypotheses[2]: 0.15}
    uninformative = action_candidate(hypotheses, informative=False, cost=0.0)
    informative = action_candidate(hypotheses, informative=True, cost=0.01)
    plan = InformationGainPlanner().select(prior, (uninformative, informative))

    assert plan.should_act
    assert plan.selected_action_id == informative.action_id
    assert plan.scores[0].expected_information_gain > plan.scores[1].expected_information_gain


def test_information_gain_rejects_actions_scored_on_a_different_hypothesis_set():
    hypotheses = (uuid4(), uuid4(), uuid4())
    prior = {hypotheses[0]: 0.45, hypotheses[1]: 0.40, hypotheses[2]: 0.15}
    incomplete_action = ObservationActionCandidate(
        action_type=ObservationActionType.MICRO_VERIFY,
        label="incomplete provider output",
        observation_likelihood_model_id="oracle-rgbd@0.1",
        calibration_domain="symbolic-household-v0",
        outcome_likelihoods={
            "seen": {hypotheses[0]: 0.8, hypotheses[1]: 0.2},
            "not_seen": {hypotheses[0]: 0.2, hypotheses[1]: 0.8},
        },
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    with pytest.raises(ValueError, match="current hypotheses"):
        InformationGainPlanner().select(prior, (incomplete_action,))


def test_direction_three_pipeline_connects_ambiguity_to_active_observation(
    metadata_factory, entity_factory
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    cycle = DirectionThreePipeline().decide(request, (action,))

    assert cycle.search_result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert cycle.observation_plan is not None
    assert cycle.observation_plan.selected_action_id == action.action_id


@pytest.mark.parametrize(
    "invalid_update",
    (
        {
            "action_type": ObservationActionType.TOUCH,
            "safety_approval": None,
        },
        {"injected_extra": "not-declared"},
    ),
    ids=("missing-touch-safety-approval", "injected-extra"),
)
def test_decide_revalidates_observation_actions(invalid_update, metadata_factory, entity_factory):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    forged = action_candidate(hypotheses, informative=True).model_copy(update=invalid_update)

    with pytest.raises(ValueError, match=r"invalid provider observation action|fields outside"):
        DirectionThreePipeline().decide(request, (forged,))


def test_common_pipeline_rejects_fusion_grounding_drift_without_a_write(
    metadata_factory, entity_factory
):
    class GroundingDriftFusion(JointPosteriorFusion):
        def fuse(self, request):
            result = super().fuse(request)
            first = result.candidates[0]
            return result.model_copy(
                update={
                    "candidates": (
                        first.model_copy(update={"location_id": uuid4()}),
                        *result.candidates[1:],
                    )
                }
            )

    request = joint_request(metadata_factory, entity_factory)
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match="candidate grounding must match"):
        DirectionThreePipeline(fusion=GroundingDriftFusion()).run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=log,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize(
    "mutation",
    ("schema", "query", "model", "posterior-support", "hard-constraints"),
)
def test_pipeline_binds_fusion_result_to_request(metadata_factory, entity_factory, mutation):
    class MutatedFusion(JointPosteriorFusion):
        def fuse(self, request):
            result = super().fuse(request)
            if mutation == "schema":
                return result.model_copy(
                    update={
                        "metadata": result.metadata.model_copy(
                            update={"schema_name": "cpswm.NotGroundedSearchResult"}
                        )
                    }
                )
            if mutation == "query":
                return result.model_copy(update={"query_id": uuid4()})
            if mutation == "model":
                return result.model_copy(update={"fusion_model_version": "wrong@9"})
            if mutation == "posterior-support":
                posterior = dict(result.posterior_by_candidate_id)
                posterior[uuid4()] = posterior.pop(next(iter(posterior)))
                return result.model_copy(update={"posterior_by_candidate_id": posterior})
            constraints = dict(result.hard_constraint_evaluations_by_candidate_id)
            constraints.pop(next(iter(constraints)))
            return result.model_copy(
                update={"hard_constraint_evaluations_by_candidate_id": constraints}
            )

    request = joint_request(metadata_factory, entity_factory, ambiguous=True)

    with pytest.raises(ValueError, match=r"fusion result|grounded fusion result"):
        DirectionThreePipeline(fusion=MutatedFusion()).decide(request)


def test_touch_requires_explicit_authorization_and_safety_gate():
    hypotheses = (uuid4(), uuid4())
    common = {
        "action_type": ObservationActionType.TOUCH,
        "label": "touch object surface",
        "observation_likelihood_model_id": "oracle-tactile@0.1",
        "calibration_domain": "symbolic-household-v0",
        "outcome_likelihoods": {
            "soft": {hypotheses[0]: 0.9, hypotheses[1]: 0.1},
            "hard": {hypotheses[0]: 0.1, hypotheses[1]: 0.9},
        },
        "motion_cost": 0.0,
        "time_cost": 0.0,
        "interruption_cost": 0.0,
        "privacy_cost": 0.0,
        "safety_cost": 0.0,
    }
    with pytest.raises(ValidationError, match="approved safety gate"):
        ObservationActionCandidate(**common)

    approved = ObservationActionCandidate(
        **common,
        safety_approval=ObservationSafetyApproval(
            authorization_granted=True,
            affordance_safe=True,
            assessor_version="oracle-safety@0.1",
            calibration_domain="symbolic-household-v0",
        ),
    )
    assert approved.safety_approval is not None
    assert approved.safety_approval.approved


def test_s3_1_oracle_loop_observes_refuses_premature_commit_and_writes_success(
    metadata_factory, entity_factory, interval
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    target_id = hypotheses[0]
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    observation = VerificationObservation(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.VerificationObservation",
                "source_type": SourceType.SIMULATION,
            }
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods={
            hypotheses[0]: 0.9,
            hypotheses[1]: 0.1,
            hypotheses[2]: 0.2,
        },
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    success = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=uuid4(),
        action_type=RobotActionType.GRASP,
        target_entity=next(
            item.entity for item in request.candidates if item.candidate_id == target_id
        ),
        attempted_location_id=next(
            item.location_id for item in request.candidates if item.candidate_id == target_id
        ),
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.SUCCESS: 1.0},
        task_goal_satisfied_probability=1.0,
    )
    resolved_target = (
        JointPosteriorFusion()
        .fuse(
            DirectionThreePipeline._request_after_observation(
                request,
                JointPosteriorFusion().fuse(request),
                observation,
            )
        )
        .candidates[0]
    )
    log = AppendOnlyTransactionLog()
    trace = DirectionThreePipeline().run_closed_loop(
        request,
        action_provider=OracleObservationActionProvider((action,)),
        observation_provider=OracleVerificationObservationProvider({action.action_id: observation}),
        task_executor=OracleGroundedTaskExecutor(
            {target_id: task_execution(resolved_target, success)}
        ),
        outcome_model_provider=OracleActionOutcomeModelProvider({}),
        canonical_log=log,
    )

    assert trace.cycles[0].search_result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert trace.cycles[1].search_result.resolution_status == ResolutionStatus.RESOLVED
    assert trace.selected_target_candidate_id == target_id
    assert trace.termination_reason == "task_success_feedback_committed"
    assert trace.observation_commit_sequences == (1,)
    assert trace.feedback_commit_sequences == (2,)
    assert log.latest_watermark().global_commit_seq == 2


def test_s3_1_oracle_loop_uses_not_found_as_uncertain_evidence_and_replans(
    metadata_factory, entity_factory, interval
):
    request = joint_request(metadata_factory, entity_factory)
    first_result = JointPosteriorFusion().fuse(request)
    first_id = first_result.candidates[0].candidate_id
    second_id = next(
        item.candidate_id
        for item in first_result.candidates
        if item.kind == CandidateKind.OBJECT_INSTANCE and item.candidate_id != first_id
    )
    entity_by_id = {
        item.candidate_id: item.entity
        for item in request.candidates
        if item.kind == CandidateKind.OBJECT_INSTANCE
    }
    not_found = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=uuid4(),
        action_type=RobotActionType.SEARCH,
        target_entity=entity_by_id[first_id],
        attempted_location_id=next(
            item.location_id for item in first_result.candidates if item.candidate_id == first_id
        ),
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=uuid4(),
    )
    recovered = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=uuid4(),
        action_type=RobotActionType.GRASP,
        target_entity=entity_by_id[second_id],
        attempted_location_id=next(
            item.location_id for item in first_result.candidates if item.candidate_id == second_id
        ),
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.SUCCESS: 1.0},
        task_goal_satisfied_probability=1.0,
    )
    search_opportunity = execution_opportunity(request.metadata, not_found.action_id)
    search_opportunity = search_opportunity.model_copy(
        update={
            "metadata": search_opportunity.metadata.model_copy(
                update={"record_id": not_found.observation_opportunity_id}
            )
        }
    )
    first_target = next(item for item in first_result.candidates if item.candidate_id == first_id)
    second_target = next(item for item in first_result.candidates if item.candidate_id == second_id)
    search_model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={
            RobotActionOutcome.NOT_FOUND: 0.001,
            RobotActionOutcome.UNKNOWN: 0.999,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.NOT_FOUND: 0.999,
            RobotActionOutcome.UNKNOWN: 0.001,
        },
        calibration_domain="symbolic-household-v0",
        model_version="oracle-search-outcome@0.1",
    )
    trace = DirectionThreePipeline().run_closed_loop(
        request,
        action_provider=OracleObservationActionProvider(()),
        observation_provider=OracleVerificationObservationProvider({}),
        task_executor=OracleGroundedTaskExecutor(
            {
                first_id: task_execution(
                    first_target,
                    not_found,
                    opportunities=(search_opportunity,),
                ),
                second_id: task_execution(second_target, recovered),
            }
        ),
        outcome_model_provider=OracleActionOutcomeModelProvider(
            {RobotActionType.SEARCH: search_model}
        ),
        canonical_log=AppendOnlyTransactionLog(),
    )

    assert trace.selected_target_candidate_id == second_id
    assert trace.termination_reason == "task_success_feedback_committed"
    assert [item.outcome_distribution for item in trace.execution_feedback] == [
        {RobotActionOutcome.NOT_FOUND: 1.0},
        {RobotActionOutcome.SUCCESS: 1.0},
    ]
    assert trace.feedback_commit_sequences == (1, 2)


def test_oracle_observation_rejects_planning_update_model_drift(metadata_factory, entity_factory):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    drifted = VerificationObservation(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.VerificationObservation",
                "source_type": SourceType.SIMULATION,
            }
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods={
            hypotheses[0]: 0.8,
            hypotheses[1]: 0.2,
            hypotheses[2]: 0.2,
        },
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    provider = OracleVerificationObservationProvider({action.action_id: drifted})
    with pytest.raises(ValueError, match="differ from the planned"):
        provider.observe(action, JointPosteriorFusion().fuse(request))


def test_oracle_loop_rejects_cross_trace_verification_evidence(metadata_factory, entity_factory):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    observation = VerificationObservation(
        metadata=metadata_factory(
            schema_name="cpswm.VerificationObservation",
            source_type=SourceType.SIMULATION,
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods={
            hypotheses[0]: 0.9,
            hypotheses[1]: 0.1,
            hypotheses[2]: 0.2,
        },
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    with pytest.raises(ValueError, match="trace must match"):
        DirectionThreePipeline().run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider((action,)),
            observation_provider=OracleVerificationObservationProvider(
                {action.action_id: observation}
            ),
            task_executor=OracleGroundedTaskExecutor({}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=AppendOnlyTransactionLog(),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("action", "selected action"),
        ("model", "observation models"),
        ("domain", "calibration domains"),
        ("outcome", "absent from the planned"),
        ("coverage", "cover every candidate"),
    ),
)
def test_common_pipeline_rejects_unbound_provider_observations_without_a_write(
    metadata_factory, entity_factory, mutation, message
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    observation = VerificationObservation(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.VerificationObservation",
                "source_type": SourceType.SIMULATION,
            }
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods=action.outcome_likelihoods["phone_seen"],
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    if mutation == "action":
        observation = observation.model_copy(update={"action_id": uuid4()})
    elif mutation == "model":
        observation = observation.model_copy(
            update={"observation_likelihood_model_id": "drifted-model@9"}
        )
    elif mutation == "domain":
        observation = observation.model_copy(update={"calibration_domain": "unvalidated-domain"})
    elif mutation == "outcome":
        observation = observation.model_copy(update={"outcome_label": "invented"})
    else:
        likelihoods = dict(observation.candidate_likelihoods)
        likelihoods.pop(next(iter(likelihoods)))
        observation = observation.model_copy(update={"candidate_likelihoods": likelihoods})
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match=message):
        run_observation_only(request, action, observation, log)

    assert log.latest_watermark().global_commit_seq == 0


def test_common_pipeline_rejects_invalid_provider_action_without_a_write(
    metadata_factory, entity_factory
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    incomplete = {
        outcome: dict(likelihoods) for outcome, likelihoods in action.outcome_likelihoods.items()
    }
    incomplete["phone_seen"].pop(hypotheses[-1])
    forged = action.model_copy(update={"outcome_likelihoods": incomplete})
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match="invalid provider observation action"):
        DirectionThreePipeline().run_closed_loop(
            request,
            action_provider=StaticActionProvider((forged,)),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=log,
            max_cycles=1,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize("mutation", ("name", "version"))
def test_verification_observation_requires_canonical_schema_label_without_a_write(
    metadata_factory, entity_factory, mutation
):
    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    metadata_update = (
        {"schema_name": "cpswm.ExecutionFeedbackRecord"}
        if mutation == "name"
        else {"schema_version": "9.9.9"}
    )
    observation = VerificationObservation(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.VerificationObservation",
                "source_type": SourceType.SIMULATION,
                **metadata_update,
            }
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods=action.outcome_likelihoods["phone_seen"],
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match=f"schema {mutation}"):
        run_observation_only(request, action, observation, log)

    assert log.latest_watermark().global_commit_seq == 0


def test_common_pipeline_validates_posterior_before_observation_commit(
    metadata_factory, entity_factory
):
    class FailingFusion(JointPosteriorFusion):
        def __init__(self):
            self.calls = 0

        def fuse(self, request):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("synthetic posterior failure")
            return super().fuse(request)

    request = joint_request(metadata_factory, entity_factory, ambiguous=True)
    hypotheses = tuple(item.candidate_id for item in request.candidates)
    action = action_candidate(hypotheses, informative=True, cost=0.0)
    observation = VerificationObservation(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.VerificationObservation",
                "source_type": SourceType.SIMULATION,
            }
        ),
        action_id=action.action_id,
        observation_opportunity_id=uuid4(),
        outcome_label="phone_seen",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods=action.outcome_likelihoods["phone_seen"],
        observation_likelihood_model_id=action.observation_likelihood_model_id,
        calibration_domain=action.calibration_domain,
    )
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match="synthetic posterior failure"):
        DirectionThreePipeline(fusion=FailingFusion()).run_closed_loop(
            request,
            action_provider=StaticActionProvider((action,)),
            observation_provider=StaticObservationProvider(observation),
            task_executor=OracleGroundedTaskExecutor({}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=log,
            max_cycles=1,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("action", "executed action ID"),
        ("target_none", "bound target entity"),
        ("location", "executed target location"),
        ("opportunity", "undeclared observation opportunity"),
    ),
)
def test_execution_feedback_must_bind_real_execution_context_without_a_write(
    metadata_factory, entity_factory, interval, mutation, message
):
    request = joint_request(metadata_factory, entity_factory)
    result = JointPosteriorFusion().fuse(request)
    target = next(item for item in result.candidates if item.kind == CandidateKind.OBJECT_INSTANCE)
    action_id = uuid4()
    opportunity = execution_opportunity(request.metadata, action_id)
    feedback = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=action_id,
        action_type=RobotActionType.SEARCH,
        target_entity=target.entity,
        attempted_location_id=target.location_id,
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    execution = task_execution(target, feedback, opportunities=(opportunity,))
    if mutation == "action":
        feedback = feedback.model_copy(update={"action_id": uuid4()})
    elif mutation == "target_none":
        feedback = feedback.model_copy(update={"target_entity": None})
    elif mutation == "location":
        feedback = feedback.model_copy(update={"attempted_location_id": uuid4()})
    else:
        feedback = feedback.model_copy(update={"observation_opportunity_id": uuid4()})
    execution = execution.model_copy(update={"feedback_records": (feedback,)})
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match=message):
        DirectionThreePipeline().run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({target.candidate_id: execution}),
            outcome_model_provider=OracleActionOutcomeModelProvider({}),
            canonical_log=log,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("version", "model version"),
        ("domain", "calibration domain"),
        ("outcome", "cover every realized"),
    ),
)
def test_execution_outcome_model_is_validated_before_atomic_write(
    metadata_factory, entity_factory, interval, mutation, message
):
    request = joint_request(metadata_factory, entity_factory)
    result = JointPosteriorFusion().fuse(request)
    target = next(item for item in result.candidates if item.kind == CandidateKind.OBJECT_INSTANCE)
    action_id = uuid4()
    opportunity = execution_opportunity(request.metadata, action_id)
    feedback = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=action_id,
        action_type=RobotActionType.SEARCH,
        target_entity=target.entity,
        attempted_location_id=target.location_id,
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    execution = task_execution(target, feedback, opportunities=(opportunity,))
    model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={
            RobotActionOutcome.NOT_FOUND: 0.2,
            RobotActionOutcome.UNKNOWN: 0.8,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.NOT_FOUND: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        calibration_domain="symbolic-household-v0",
        model_version="oracle-search-outcome@0.1",
    )
    if mutation == "version":
        model = model.model_copy(update={"model_version": "wrong@9"})
    elif mutation == "domain":
        model = model.model_copy(update={"calibration_domain": "wrong-domain"})
    else:
        model = model.model_copy(
            update={
                "p_outcome_given_target_present": {RobotActionOutcome.UNKNOWN: 1.0},
                "p_outcome_given_target_absent": {RobotActionOutcome.UNKNOWN: 1.0},
            }
        )
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match=message):
        DirectionThreePipeline().run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({target.candidate_id: execution}),
            outcome_model_provider=OracleActionOutcomeModelProvider(
                {RobotActionType.SEARCH: model}
            ),
            canonical_log=log,
        )

    assert log.latest_watermark().global_commit_seq == 0


def test_execution_posterior_failure_leaves_no_partial_batch(
    metadata_factory, entity_factory, interval
):
    class FailingFusion(JointPosteriorFusion):
        def __init__(self):
            self.calls = 0

        def fuse(self, request):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("synthetic execution posterior failure")
            return super().fuse(request)

    request = joint_request(metadata_factory, entity_factory)
    target = next(
        item
        for item in JointPosteriorFusion().fuse(request).candidates
        if item.kind == CandidateKind.OBJECT_INSTANCE
    )
    action_id = uuid4()
    opportunity = execution_opportunity(request.metadata, action_id)
    feedback = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=action_id,
        action_type=RobotActionType.SEARCH,
        target_entity=target.entity,
        attempted_location_id=target.location_id,
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    execution = task_execution(target, feedback, opportunities=(opportunity,))
    model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={RobotActionOutcome.NOT_FOUND: 1.0},
        p_outcome_given_target_absent={RobotActionOutcome.NOT_FOUND: 1.0},
        calibration_domain="symbolic-household-v0",
        model_version="oracle-search-outcome@0.1",
    )
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match="synthetic execution posterior failure"):
        DirectionThreePipeline(fusion=FailingFusion()).run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({target.candidate_id: execution}),
            outcome_model_provider=OracleActionOutcomeModelProvider(
                {RobotActionType.SEARCH: model}
            ),
            canonical_log=log,
        )

    assert log.latest_watermark().global_commit_seq == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("opportunity_name", "observation opportunity schema name"),
        ("opportunity_version", "observation opportunity schema version"),
        ("feedback_name", "execution feedback schema name"),
        ("feedback_version", "execution feedback schema version"),
        ("opportunity_time", "recorded time must match opportunity time"),
        ("feedback_time", "recorded time must fall within valid time"),
        ("feedback_before_opportunity", "cannot precede its observation opportunity"),
    ),
)
def test_execution_records_require_schema_and_time_consistency_without_a_write(
    metadata_factory, entity_factory, interval, mutation, message
):
    request = joint_request(metadata_factory, entity_factory)
    target = next(
        item
        for item in JointPosteriorFusion().fuse(request).candidates
        if item.kind == CandidateKind.OBJECT_INSTANCE
    )
    action_id = uuid4()
    opportunity = execution_opportunity(request.metadata, action_id)
    feedback = ExecutionFeedbackRecord(
        metadata=request.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
            }
        ),
        action_id=action_id,
        action_type=RobotActionType.SEARCH,
        target_entity=target.entity,
        attempted_location_id=target.location_id,
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    if mutation == "opportunity_name":
        opportunity = opportunity.model_copy(
            update={
                "metadata": opportunity.metadata.model_copy(
                    update={"schema_name": "cpswm.ExecutionFeedbackRecord"}
                )
            }
        )
    elif mutation == "opportunity_version":
        opportunity = opportunity.model_copy(
            update={"metadata": opportunity.metadata.model_copy(update={"schema_version": "9.9.9"})}
        )
    elif mutation == "feedback_name":
        feedback = feedback.model_copy(
            update={
                "metadata": feedback.metadata.model_copy(
                    update={"schema_name": "cpswm.VerificationObservation"}
                )
            }
        )
    elif mutation == "feedback_version":
        feedback = feedback.model_copy(
            update={"metadata": feedback.metadata.model_copy(update={"schema_version": "9.9.9"})}
        )
    elif mutation == "opportunity_time":
        opportunity = opportunity.model_copy(
            update={"opportunity_time": opportunity.opportunity_time + timedelta(seconds=1)}
        )
    elif mutation == "feedback_time":
        feedback = feedback.model_copy(
            update={
                "metadata": feedback.metadata.model_copy(
                    update={"recorded_time": interval.end + timedelta(days=100)}
                )
            }
        )
    else:
        opportunity_time = interval.start + timedelta(minutes=2)
        opportunity = opportunity.model_copy(
            update={
                "metadata": opportunity.metadata.model_copy(
                    update={"recorded_time": opportunity_time}
                ),
                "opportunity_time": opportunity_time,
            }
        )
        feedback = feedback.model_copy(
            update={
                "metadata": feedback.metadata.model_copy(
                    update={"recorded_time": interval.start + timedelta(minutes=1)}
                )
            }
        )
    valid_opportunity = execution_opportunity(request.metadata, action_id)
    valid_feedback = feedback.model_copy(
        update={
            "metadata": feedback.metadata.model_copy(
                update={
                    "schema_name": "cpswm.ExecutionFeedbackRecord",
                    "schema_version": "0.1.0",
                    "recorded_time": interval.start,
                }
            ),
            "observation_opportunity_id": valid_opportunity.metadata.record_id,
        }
    )
    execution = task_execution(
        target,
        valid_feedback,
        opportunities=(valid_opportunity,),
    )
    execution = execution.model_copy(
        update={
            "observation_opportunities": (opportunity,),
            "feedback_records": (feedback,),
        }
    )
    model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={RobotActionOutcome.NOT_FOUND: 1.0},
        p_outcome_given_target_absent={RobotActionOutcome.NOT_FOUND: 1.0},
        calibration_domain="symbolic-household-v0",
        model_version="oracle-search-outcome@0.1",
    )
    log = AppendOnlyTransactionLog()

    with pytest.raises(ValueError, match=message):
        DirectionThreePipeline().run_closed_loop(
            request,
            action_provider=OracleObservationActionProvider(()),
            observation_provider=OracleVerificationObservationProvider({}),
            task_executor=OracleGroundedTaskExecutor({target.candidate_id: execution}),
            outcome_model_provider=OracleActionOutcomeModelProvider(
                {RobotActionType.SEARCH: model}
            ),
            canonical_log=log,
        )

    assert log.latest_watermark().global_commit_seq == 0


def test_uncertain_not_found_feedback_is_canonical_and_reduces_presence_belief(
    metadata_factory, interval, entity_factory
):
    feedback = ExecutionFeedbackRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ExecutionFeedbackRecord", source_type=SourceType.ACTION
        ),
        action_id=uuid4(),
        action_type=RobotActionType.SEARCH,
        target_entity=entity_factory(EntityType.OBJECT_INSTANCE),
        attempted_location_id=uuid4(),
        valid_time=interval,
        outcome_distribution={
            RobotActionOutcome.NOT_FOUND: 0.8,
            RobotActionOutcome.UNKNOWN: 0.2,
        },
        observation_opportunity_id=uuid4(),
        diagnostics={"occlusion": "partial"},
    )
    model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={
            RobotActionOutcome.NOT_FOUND: 0.2,
            RobotActionOutcome.UNKNOWN: 0.8,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.NOT_FOUND: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        calibration_domain="symbolic-household-v0",
        model_version="search-outcome@0.1",
    )
    log = AppendOnlyTransactionLog()
    commit = log.append([feedback], idempotency_key="search-feedback")
    update = ExecutionFeedbackProjector().update_target_presence(0.7, feedback, model)

    assert commit.watermark.global_commit_seq == 1
    assert update.posterior_target_present < update.prior_target_present
    assert update.posterior_target_present > 0.0


@pytest.mark.parametrize(
    ("action_type", "outcome"),
    [
        (RobotActionType.GRASP, RobotActionOutcome.GRASP_FAILED),
        (RobotActionType.TRANSFER, RobotActionOutcome.OBJECT_SLIPPED),
    ],
)
def test_manipulation_failures_are_uncertain_action_evidence(
    metadata_factory, interval, entity_factory, action_type, outcome
):
    record = ExecutionFeedbackRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ExecutionFeedbackRecord", source_type=SourceType.ACTION
        ),
        action_id=uuid4(),
        action_type=action_type,
        target_entity=entity_factory(EntityType.OBJECT_INSTANCE),
        valid_time=interval,
        outcome_distribution={outcome: 0.75, RobotActionOutcome.UNKNOWN: 0.25},
    )
    assert record.outcome_distribution[outcome] == 0.75
    assert len(record.outcome_distribution) == 2


def test_not_found_without_observation_opportunity_is_rejected(metadata_factory, interval):
    with pytest.raises(ValidationError, match="observation opportunity"):
        ExecutionFeedbackRecord(
            metadata=metadata_factory(
                schema_name="cpswm.ExecutionFeedbackRecord",
                source_type=SourceType.ACTION,
            ),
            action_id=uuid4(),
            action_type=RobotActionType.SEARCH,
            valid_time=interval,
            outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        )


@pytest.mark.parametrize("missing_field", ("target_entity", "attempted_location_id"))
def test_not_found_requires_a_bound_proposition(
    metadata_factory, interval, entity_factory, missing_field
):
    values = {
        "target_entity": entity_factory(EntityType.OBJECT_INSTANCE),
        "attempted_location_id": uuid4(),
    }
    values[missing_field] = None
    with pytest.raises(ValidationError, match="requires a bound"):
        ExecutionFeedbackRecord(
            metadata=metadata_factory(
                schema_name="cpswm.ExecutionFeedbackRecord",
                source_type=SourceType.ACTION,
            ),
            action_id=uuid4(),
            action_type=RobotActionType.SEARCH,
            valid_time=interval,
            outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
            observation_opportunity_id=uuid4(),
            **values,
        )


def test_feedback_projector_rejects_unmodeled_realized_outcome(
    metadata_factory, interval, entity_factory
):
    feedback = ExecutionFeedbackRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ExecutionFeedbackRecord",
            source_type=SourceType.ACTION,
        ),
        action_id=uuid4(),
        action_type=RobotActionType.GRASP,
        target_entity=entity_factory(EntityType.OBJECT_INSTANCE),
        attempted_location_id=uuid4(),
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.GRASP_FAILED: 1.0},
    )
    model = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.GRASP,
        p_outcome_given_target_present={
            RobotActionOutcome.SUCCESS: 0.5,
            RobotActionOutcome.UNKNOWN: 0.5,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.SUCCESS: 0.5,
            RobotActionOutcome.UNKNOWN: 0.5,
        },
        calibration_domain="symbolic-household-v0",
        model_version="incomplete-grasp@0.1",
    )

    with pytest.raises(ValueError, match="cover every realized feedback outcome"):
        ExecutionFeedbackProjector().update_target_presence(0.7, feedback, model)


def test_action_success_cannot_overstate_task_goal_completion(metadata_factory, interval):
    with pytest.raises(ValidationError, match="cannot exceed action success"):
        ExecutionFeedbackRecord(
            metadata=metadata_factory(
                schema_name="cpswm.ExecutionFeedbackRecord",
                source_type=SourceType.ACTION,
            ),
            action_id=uuid4(),
            action_type=RobotActionType.NAVIGATE,
            valid_time=interval,
            outcome_distribution={
                RobotActionOutcome.SUCCESS: 0.5,
                RobotActionOutcome.UNKNOWN: 0.5,
            },
            task_goal_satisfied_probability=0.8,
        )


def test_memory_reliability_uses_evidence_not_raw_age(metadata_factory):
    common = {
        "metadata": metadata_factory(schema_name="cpswm.MemoryReliabilityRequest"),
        "memory_record_id": uuid4(),
        "prior_current_probability": 0.7,
        "factor_evidence": {
            MemoryEvidenceFactor.ORIGINAL_OBSERVATION: MemoryFactorEvidence(
                p_evidence_given_current=0.9,
                p_evidence_given_not_current=0.3,
                model_version="observation-quality@0.1",
                calibration_domain="symbolic-household-v0",
            ),
            MemoryEvidenceFactor.TRANSITION_SURVIVAL: MemoryFactorEvidence(
                p_evidence_given_current=0.8,
                p_evidence_given_not_current=0.4,
                model_version="person-object-transition@0.1",
                calibration_domain="symbolic-household-v0",
            ),
        },
        "stale_after_seconds": 3600.0,
    }
    recent = MemoryReliabilityProjector().project(
        MemoryReliabilityRequest(**common, seconds_since_last_direct_observation=60.0)
    )
    old = MemoryReliabilityProjector().project(
        MemoryReliabilityRequest(**common, seconds_since_last_direct_observation=864000.0)
    )

    assert old.posterior_current_probability == pytest.approx(recent.posterior_current_probability)
    assert recent.status == MemoryReliabilityStatus.FRESH
    assert old.status == MemoryReliabilityStatus.STALE
    assert old.lifecycle_action == MemoryLifecycleAction.VERIFY_BEFORE_HIGH_RISK_USE
    assert not old.age_used_as_direct_reliability_evidence


@pytest.mark.parametrize(
    ("p_current", "p_not_current", "expected"),
    (
        (1e-320, 1.0, 0.0),
        (1.0, 1e-320, 1.0),
    ),
)
def test_memory_reliability_extreme_likelihood_ratios_are_numerically_stable(
    metadata_factory, p_current, p_not_current, expected
):
    request = MemoryReliabilityRequest(
        metadata=metadata_factory(schema_name="cpswm.MemoryReliabilityRequest"),
        memory_record_id=uuid4(),
        prior_current_probability=0.5,
        factor_evidence={
            MemoryEvidenceFactor.OBSERVATION_OPPORTUNITY: MemoryFactorEvidence(
                p_evidence_given_current=p_current,
                p_evidence_given_not_current=p_not_current,
                model_version="extreme-evidence@0.1",
                calibration_domain="numeric-stress-test",
            )
        },
        seconds_since_last_direct_observation=1.0,
        stale_after_seconds=3600.0,
    )

    result = MemoryReliabilityProjector().project(request)

    assert result.posterior_current_probability == pytest.approx(expected, abs=1e-300)
    assert abs(result.contributions[0].log_likelihood_ratio) < 1000.0


def test_verified_counterevidence_can_contradict_without_deleting_history(
    metadata_factory,
):
    request = MemoryReliabilityRequest(
        metadata=metadata_factory(schema_name="cpswm.MemoryReliabilityRequest"),
        memory_record_id=uuid4(),
        prior_current_probability=0.7,
        factor_evidence={
            MemoryEvidenceFactor.OBSERVATION_OPPORTUNITY: MemoryFactorEvidence(
                p_evidence_given_current=0.05,
                p_evidence_given_not_current=0.90,
                model_version="visibility-aware-absence@0.1",
                calibration_domain="symbolic-household-v0",
            )
        },
        seconds_since_last_direct_observation=100.0,
        stale_after_seconds=3600.0,
        explicit_contradiction=True,
    )
    result = MemoryReliabilityProjector().project(request)
    assert result.status == MemoryReliabilityStatus.CONTRADICTED
    assert result.lifecycle_action == MemoryLifecycleAction.MARK_CONTRADICTED
    assert result.memory_record_id == request.memory_record_id


@pytest.mark.parametrize(
    "entrypoint",
    (
        "run_grounded_search_vertical_slice.py",
        "run_grounded_search_oracle_closed_loop.py",
    ),
)
def test_direction_three_cli_runs_directly_without_pythonpath(entrypoint):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "apps" / "direction_three" / entrypoint),
        ],
        cwd=PROJECT_ROOT.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.lstrip().startswith("{")
