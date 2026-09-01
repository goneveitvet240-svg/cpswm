from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts.base import EntityType, EvidenceRef
from cpswm.contracts.events import EventType
from cpswm.contracts.grounded_search import (
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    DynamicObjectState,
    EvidenceChannel,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ObservationActionType,
    ResolutionStatus,
    RobotActionType,
    StaticGeometryAnchor,
    VerificationModality,
)
from cpswm.contracts.likelihoods import Pose3D
from cpswm.contracts.llm_roles import build_query_compiler_provenance
from cpswm.system.evaluation_operations.direction_three_external_audit import (
    REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS,
    selected_direction_three_external_audit,
    validate_external_audit_run_coverage,
)
from cpswm.system.evaluation_operations.real_data_adapters.findingdory_layered_ingress import (
    FindingDoryAcquisitionBackend,
    load_findingdory_layered_artifact,
    materialize_findingdory_rows,
)
from cpswm.world_model.grounded_search.embodiment_platforms import (
    DualPlatformBinding,
    EmbodimentPlatform,
    PlatformRuntimeDescriptor,
    validate_dual_platform_parity,
)
from cpswm.world_model.grounded_search.layered_map import LayeredSemanticMap
from cpswm.world_model.grounded_search.multi_parse_query import (
    MultiParseGroundingFusion,
    MultiParseGroundingRequest,
    MultiParseQueryPosterior,
    ParseGroundingRequest,
    QueryParseHypothesis,
)
from cpswm.world_model.grounded_search.probabilistic_instance_graph import (
    InstanceAssociationEvidence,
    InstanceAssociationPrior,
    ProbabilisticDynamicInstanceGraph,
    ProbabilisticInstanceGraphUpdate,
    UnassignedDynamicObservation,
)
from cpswm.world_model.grounded_search.revision_aware_evidence import (
    EvidenceClaimKind,
    EvidenceClaimStatus,
    EvidenceProposalSource,
    EvidenceRevisionAction,
    EvidenceRevisionRecord,
    HabitEvidenceActivation,
    NeuroSymbolicEvidenceProposal,
    RevisionAwareEvidenceGraph,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pose(*, frame_id: str = "map", x: float = 0.0) -> Pose3D:
    return Pose3D(
        frame_id=frame_id,
        x=x,
        y=0.0,
        z=0.5,
        qx=0.0,
        qy=0.0,
        qz=0.0,
        qw=1.0,
    )


def _compiled_query(utterance: str, signature: str, *, abstain: bool = False):
    source_record_id = uuid4()
    evidence = EvidenceRef(
        evidence_type="user_utterance",
        source_record_id=source_record_id,
    )
    return CompiledSemanticQuery(
        utterance=utterance,
        category_candidates=(signature,),
        soft_constraints=(signature,),
        compiler_model_version="test-multi-parse-compiler@1",
        unknown_terms=((signature,) if abstain else ()),
        abstain=abstain,
        input_evidence_refs=(evidence,),
        invocation_provenance=build_query_compiler_provenance(
            provider="test",
            model="compiler",
            version="1",
            temperature=0.0,
            prompt_template_version="test@1",
            prompt=f"{utterance}:{signature}",
            input_evidence_refs=(source_record_id,),
        ),
    )


def _channels(high: float, low: float) -> dict[EvidenceChannel, ChannelEvidence]:
    values = (high, low, high, low, high, low)
    return {
        channel: ChannelEvidence(
            likelihood_given_candidate=value,
            model_version=f"{channel.value}@1",
            calibration_domain="test-home",
        )
        for channel, value in zip(EvidenceChannel, values, strict=True)
    }


def _grounding_request(
    metadata_factory,
    query: CompiledSemanticQuery,
    *,
    candidate_ids,
    entities,
    locations,
    prefer_first: bool,
) -> JointPosteriorRequest:
    first_scores = _channels(0.95, 0.90) if prefer_first else _channels(0.20, 0.25)
    second_scores = _channels(0.20, 0.25) if prefer_first else _channels(0.95, 0.90)
    candidates = (
        JointCandidateEvidence(
            candidate_id=candidate_ids[0],
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=entities[0],
            location_id=locations[0],
            prior_probability=0.45,
            channel_evidence=first_scores,
        ),
        JointCandidateEvidence(
            candidate_id=candidate_ids[1],
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=entities[1],
            location_id=locations[1],
            prior_probability=0.45,
            channel_evidence=second_scores,
        ),
        JointCandidateEvidence(
            candidate_id=candidate_ids[2],
            kind=CandidateKind.UNKNOWN,
            prior_probability=0.10,
            channel_evidence=_channels(0.10, 0.10),
        ),
    )
    return JointPosteriorRequest(
        metadata=metadata_factory(schema_name="cpswm.MultiParseGroundingRequest"),
        compiled_query=query,
        candidates=candidates,
        top_k=3,
        resolution_threshold=0.70,
        ambiguity_margin=0.12,
        unknown_threshold=0.45,
    )


def test_s3_dg_09d_marginalizes_competing_parses_and_preserves_unknown(
    metadata_factory,
    entity_factory,
):
    utterance = "把我晚上用的那个东西找来"
    phone_parse = QueryParseHypothesis(
        semantic_signature="phone-at-night",
        probability=0.55,
        compiled_query=_compiled_query(utterance, "phone"),
    )
    glasses_parse = QueryParseHypothesis(
        semantic_signature="glasses-at-night",
        probability=0.35,
        compiled_query=_compiled_query(utterance, "glasses"),
    )
    posterior = MultiParseQueryPosterior(
        utterance=utterance,
        hypotheses=(phone_parse, glasses_parse),
        unparsed_probability=0.10,
        compiler_ensemble_version="compiler-ensemble@1",
        calibration_domain="test-home",
    )
    candidate_ids = (uuid4(), uuid4(), uuid4())
    entities = (
        entity_factory(EntityType.OBJECT_INSTANCE),
        entity_factory(EntityType.OBJECT_INSTANCE),
    )
    locations = (uuid4(), uuid4())
    request = MultiParseGroundingRequest(
        parse_posterior=posterior,
        grounding_requests=(
            ParseGroundingRequest(
                parse_id=phone_parse.parse_id,
                request=_grounding_request(
                    metadata_factory,
                    phone_parse.compiled_query,
                    candidate_ids=candidate_ids,
                    entities=entities,
                    locations=locations,
                    prefer_first=True,
                ),
            ),
            ParseGroundingRequest(
                parse_id=glasses_parse.parse_id,
                request=_grounding_request(
                    metadata_factory,
                    glasses_parse.compiled_query,
                    candidate_ids=candidate_ids,
                    entities=entities,
                    locations=locations,
                    prefer_first=False,
                ),
            ),
        ),
    )

    result = MultiParseGroundingFusion().fuse(request)

    assert len(result.parse_results) == 2
    assert result.grounded_parse_probability == pytest.approx(0.90)
    assert result.unresolved_language_probability == pytest.approx(0.10)
    assert result.unknown_probability >= 0.10
    assert sum(result.posterior_by_candidate_id.values()) == pytest.approx(1.0)
    assert (
        result.posterior_by_candidate_id[candidate_ids[0]]
        > result.posterior_by_candidate_id[candidate_ids[1]]
    )


def test_s3_dg_09d_routes_abstaining_parse_mass_to_unknown(
    metadata_factory,
    entity_factory,
):
    utterance = "找那个玩意"
    groundable = QueryParseHypothesis(
        semantic_signature="known-parse",
        probability=0.70,
        compiled_query=_compiled_query(utterance, "known"),
    )
    abstaining = QueryParseHypothesis(
        semantic_signature="unresolved-parse",
        probability=0.20,
        compiled_query=_compiled_query(utterance, "玩意", abstain=True),
    )
    candidates = (uuid4(), uuid4(), uuid4())
    request = MultiParseGroundingRequest(
        parse_posterior=MultiParseQueryPosterior(
            utterance=utterance,
            hypotheses=(groundable, abstaining),
            unparsed_probability=0.10,
            compiler_ensemble_version="compiler-ensemble@1",
            calibration_domain="test-home",
        ),
        grounding_requests=(
            ParseGroundingRequest(
                parse_id=groundable.parse_id,
                request=_grounding_request(
                    metadata_factory,
                    groundable.compiled_query,
                    candidate_ids=candidates,
                    entities=(entity_factory(), entity_factory()),
                    locations=(uuid4(), uuid4()),
                    prefer_first=True,
                ),
            ),
        ),
    )

    result = MultiParseGroundingFusion().fuse(request)

    assert result.unresolved_language_probability == pytest.approx(0.30)
    assert result.unknown_probability >= 0.30


def test_s3_dg_10d_gates_dynamic_map_mutation_and_deduplicates_evidence(
    entity_factory,
):
    layered_map = LayeredSemanticMap()
    anchor = StaticGeometryAnchor(
        semantic_label="table",
        geometry_ref="mesh://table",
        frame_id="map",
    )
    layered_map.add_static_anchor(anchor)
    existing = entity_factory(EntityType.OBJECT_INSTANCE)
    graph = ProbabilisticDynamicInstanceGraph(layered_map)
    graph.register_instance(
        DynamicObjectState(
            object_instance=existing,
            anchor_id=anchor.anchor_id,
            pose=_pose(),
            state_probability=1.0,
        )
    )
    cluster_id = uuid4()
    update = ProbabilisticInstanceGraphUpdate(
        prior=InstanceAssociationPrior(
            existing_instance_probabilities={existing.entity_id: 0.80},
            new_instance_probability=0.10,
            unknown_probability=0.10,
        ),
        observation=UnassignedDynamicObservation(
            evidence_cluster_id=cluster_id,
            anchor_id=anchor.anchor_id,
            pose=_pose(x=0.2),
            evidence_refs=(_evidence_ref("rgbd_reid_observation"),),
        ),
        evidence=InstanceAssociationEvidence(
            existing_instance_likelihoods={existing.entity_id: 0.95},
            new_instance_likelihood=0.10,
            unknown_likelihood=0.05,
            model_version="reid-graph@1",
            calibration_domain="test-home",
        ),
        proposed_new_instance=entity_factory(EntityType.OBJECT_INSTANCE),
    )

    result = graph.update(update)

    assert result.resolution_status is ResolutionStatus.RESOLVED
    assert result.resolved_instance_id == existing.entity_id
    assert not result.created_new_instance
    assert layered_map.dynamic_revision == 2
    with pytest.raises(ValueError, match="evidence cluster"):
        graph.update(update)

    unknown_result = graph.update(
        ProbabilisticInstanceGraphUpdate(
            prior=InstanceAssociationPrior(
                existing_instance_probabilities={existing.entity_id: 0.10},
                new_instance_probability=0.10,
                unknown_probability=0.80,
            ),
            observation=UnassignedDynamicObservation(
                evidence_cluster_id=uuid4(),
                anchor_id=anchor.anchor_id,
                pose=_pose(x=0.4),
                evidence_refs=(_evidence_ref("rgbd_unknown_observation"),),
            ),
            evidence=InstanceAssociationEvidence(
                existing_instance_likelihoods={existing.entity_id: 0.10},
                new_instance_likelihood=0.10,
                unknown_likelihood=0.99,
                model_version="reid-graph@1",
                calibration_domain="test-home",
            ),
            proposed_new_instance=entity_factory(EntityType.OBJECT_INSTANCE),
        )
    )
    assert unknown_result.resolution_status is ResolutionStatus.UNKNOWN
    assert unknown_result.resolved_instance_id is None
    assert layered_map.dynamic_revision == 2


def _evidence_ref(kind: str) -> EvidenceRef:
    return EvidenceRef(evidence_type=kind, source_record_id=uuid4())


def test_s3_dg_14d_retraction_removes_derived_habit_from_active_projection():
    graph = RevisionAwareEvidenceGraph()
    authorization_scope = uuid4()
    object_id = uuid4()
    person = NeuroSymbolicEvidenceProposal(
        claim_kind=EvidenceClaimKind.PERSON,
        object_instance_id=object_id,
        actor_posterior={"alice": 1.0},
        proposal_probability=0.85,
        proposal_source=EvidenceProposalSource.VLM,
        model_version="person-vlm@1",
        calibration_domain="authorized-household",
        evidence_cluster_ids=(uuid4(),),
        evidence_refs=(_evidence_ref("person_track"),),
        authorization_scope_id=authorization_scope,
    )
    graph.append_proposal(person)
    person_verification = EvidenceRevisionRecord(
        claim_id=person.claim_id,
        parent_revision_id=None,
        action=EvidenceRevisionAction.VERIFY,
        verified_probability=0.90,
        verifier_model_version="person-verifier@1",
        calibration_domain="authorized-household",
        evidence_refs=(_evidence_ref("person_verification"),),
        authorization_scope_id=authorization_scope,
    )
    graph.append_revision(person_verification)

    destination = uuid4()
    event = NeuroSymbolicEvidenceProposal(
        claim_kind=EvidenceClaimKind.EVENT,
        object_instance_id=object_id,
        actor_posterior={"alice": 0.80, "unknown": 0.20},
        event_type=EventType.PLACE,
        destination_location_id=destination,
        proposal_probability=0.75,
        proposal_source=EvidenceProposalSource.VLM,
        model_version="event-vlm@1",
        calibration_domain="authorized-household",
        evidence_cluster_ids=(uuid4(),),
        evidence_refs=(_evidence_ref("place_event"),),
        source_person_claim_ids=(person.claim_id,),
        authorization_scope_id=authorization_scope,
    )
    graph.append_proposal(event)
    unverified_activation = HabitEvidenceActivation(
        source_event_claim_id=event.claim_id,
        source_event_revision_id=uuid4(),
        actor_key="alice",
        object_instance_id=object_id,
        location_id=destination,
        context_key="night",
        soft_count=0.60,
        model_version="habit-projector@1",
        calibration_domain="authorized-household",
        observation_opportunity_id=uuid4(),
        evidence_refs=(_evidence_ref("habit_projection"),),
    )
    with pytest.raises(ValueError, match="currently verified"):
        graph.append_habit_activation(unverified_activation)

    event_verification = EvidenceRevisionRecord(
        claim_id=event.claim_id,
        parent_revision_id=None,
        action=EvidenceRevisionAction.VERIFY,
        verified_probability=0.90,
        verifier_model_version="event-verifier@1",
        calibration_domain="authorized-household",
        evidence_refs=(_evidence_ref("event_verification"),),
        authorization_scope_id=authorization_scope,
    )
    graph.append_revision(event_verification)
    activation = unverified_activation.model_copy(
        update={"source_event_revision_id": event_verification.revision_id}
    )
    graph.append_habit_activation(activation)
    assert len(graph.active_habit_activations()) == 1

    person_retraction = EvidenceRevisionRecord(
        claim_id=person.claim_id,
        parent_revision_id=person_verification.revision_id,
        action=EvidenceRevisionAction.RETRACT,
        verified_probability=0.0,
        verifier_model_version="person-verifier@1",
        calibration_domain="authorized-household",
        evidence_refs=(_evidence_ref("person_retraction"),),
        authorization_scope_id=authorization_scope,
    )
    graph.append_revision(person_retraction)
    assert graph.active_habit_activations() == ()

    person_reactivation = EvidenceRevisionRecord(
        claim_id=person.claim_id,
        parent_revision_id=person_retraction.revision_id,
        action=EvidenceRevisionAction.REACTIVATE,
        verified_probability=0.88,
        verifier_model_version="person-verifier@2",
        calibration_domain="authorized-household",
        evidence_refs=(_evidence_ref("person_reactivation"),),
        authorization_scope_id=authorization_scope,
    )
    graph.append_revision(person_reactivation)
    assert len(graph.active_habit_activations()) == 1

    graph.append_revision(
        EvidenceRevisionRecord(
            claim_id=event.claim_id,
            parent_revision_id=event_verification.revision_id,
            action=EvidenceRevisionAction.RETRACT,
            verified_probability=0.0,
            verifier_model_version="event-verifier@1",
            calibration_domain="authorized-household",
            evidence_refs=(_evidence_ref("event_retraction"),),
            authorization_scope_id=authorization_scope,
        )
    )
    assert graph.projection(event.claim_id).status is EvidenceClaimStatus.RETRACTED
    assert graph.active_habit_activations() == ()
    assert len(graph.revision_log) == 5


def _platform_descriptor(
    platform: EmbodimentPlatform,
    actions: tuple[RobotActionType, ...],
) -> PlatformRuntimeDescriptor:
    return PlatformRuntimeDescriptor(
        platform=platform,
        runtime_version=f"{platform.value}@1",
        adapter_version="shared-action-adapter@1",
        runtime_environment_hash=(
            "a" if platform is EmbodimentPlatform.HABITAT_FINDINGDORY else "b"
        )
        * 64,
        supported_observation_actions=(
            ObservationActionType.MOVE_VIEWPOINT,
            ObservationActionType.MICRO_VERIFY,
        ),
        supported_robot_actions=actions,
        supported_modalities=(VerificationModality.RGBD, VerificationModality.POINT_CLOUD),
        observation_action_bindings={
            ObservationActionType.MOVE_VIEWPOINT: "native/move_viewpoint",
            ObservationActionType.MICRO_VERIFY: "native/micro_verify",
        },
        robot_action_bindings={action: f"native/{action.value}" for action in actions},
        modality_bindings={
            VerificationModality.RGBD: "sensors/rgbd",
            VerificationModality.POINT_CLOUD: "sensors/points",
        },
        sidecar_protocol_version="direction-three-sidecar@1",
        frame_registry_version="frame-registry@1",
        action_outcome_model_versions={action: f"{action.value}-outcome@1" for action in actions},
        calibration_domains={action: platform.value for action in actions},
    )


def test_s3_dg_11e_requires_semantic_parity_across_isolated_platforms():
    actions = (
        RobotActionType.SEARCH,
        RobotActionType.NAVIGATE,
        RobotActionType.GRASP,
        RobotActionType.PLACE,
    )
    binding = DualPlatformBinding(
        habitat=_platform_descriptor(EmbodimentPlatform.HABITAT_FINDINGDORY, actions),
        isaac_ros=_platform_descriptor(EmbodimentPlatform.ISAAC_ROS, actions),
        shared_task_manifest_hash="c" * 64,
        action_semantics_version="direction-three-actions@1",
        required_observation_actions=(ObservationActionType.MOVE_VIEWPOINT,),
        required_robot_actions=actions,
        required_modalities=(VerificationModality.RGBD,),
    )
    assert validate_dual_platform_parity(binding).parity_satisfied

    with pytest.raises(ValidationError, match="missing a required robot action"):
        DualPlatformBinding(
            habitat=binding.habitat,
            isaac_ros=_platform_descriptor(EmbodimentPlatform.ISAAC_ROS, actions[:-1]),
            shared_task_manifest_hash="c" * 64,
            action_semantics_version="direction-three-actions@1",
            required_observation_actions=(ObservationActionType.MOVE_VIEWPOINT,),
            required_robot_actions=actions,
            required_modalities=(VerificationModality.RGBD,),
        )


def test_s3_dg_12c_registry_is_complete_but_cannot_fake_reproduction_readiness():
    audit = selected_direction_three_external_audit()

    assert {entry.system_id for entry in audit.entries} == set(
        REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS
    )
    assert not audit.ready_for_sealed_comparison
    with pytest.raises(ValueError, match="audit is incomplete"):
        validate_external_audit_run_coverage(audit, ())


def test_s3_dg_13d_materializes_and_verifies_immutable_pinned_jsonl(tmp_path):
    fixture = PROJECT_ROOT / "tests/fixtures/direction_three/findingdory_metadata_sample.jsonl"
    rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
    destination = tmp_path / "findingdory-pinned.jsonl"
    manifest = materialize_findingdory_rows(
        rows,
        destination,
        dataset_revision="a" * 40,
        source_split="train",
        acquisition_backend=FindingDoryAcquisitionBackend.PROVIDED_PINNED_ROWS,
    )

    result = load_findingdory_layered_artifact(destination, manifest)

    assert result.batch.audit.accepted_rows == len(rows)
    assert result.batch.audit.rejected_rows == 0
    assert not result.batch.audit.real_official_rows_ingested
    assert result.manifest.normalized_row_count == len(rows)

    hub_result = load_findingdory_layered_artifact(
        destination,
        manifest.model_copy(
            update={"acquisition_backend": FindingDoryAcquisitionBackend.HUGGINGFACE_DATASETS}
        ),
    )
    assert hub_result.batch.audit.real_official_rows_ingested
    assert hub_result.batch.audit.source_kind.value == "pinned_hub_artifact"
    with pytest.raises(FileExistsError, match="immutable"):
        materialize_findingdory_rows(
            rows,
            destination,
            dataset_revision="a" * 40,
            source_split="train",
            acquisition_backend=FindingDoryAcquisitionBackend.PROVIDED_PINNED_ROWS,
        )

    destination.write_text(destination.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_findingdory_layered_artifact(destination, manifest)
