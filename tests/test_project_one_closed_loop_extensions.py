from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from cpswm.contracts import (
    AuditableEvidencePath,
    BaselineClosureGate,
    EntityType,
    EvidencePathEdge,
    EvidencePathNode,
    EvidencePathNodeKind,
    EvidencePathRelation,
    EvidenceRef,
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    QueryCandidate,
    RetrievalCoverage,
    SourceType,
    WorldModelQueryResult,
)
from cpswm.system.evaluation_operations import (
    CalibrationUtilityCase,
    CalibrationUtilityEvaluator,
    FairAblationArm,
    FairAblationManifest,
    ModelBudget,
    ObservationBudget,
    TuningBudget,
)
from cpswm.world_model.grounded_search import ActionUtilityPlanner
from cpswm.world_model.habits_transitions import (
    CauseEvidenceFrame,
    CauseFactorizedBOCPD,
    ChangeCause,
    HierarchicalDirichletHabitModel,
    ObservationPropensityCorrector,
    PropensityCorrectionMode,
)


def _habit_evidence(metadata, *, object_id, location_id, actor_posterior, opportunity_id=None):
    return HabitLearningEvidence(
        metadata=metadata,
        object_instance_id=object_id,
        location_id=location_id,
        event_time=metadata.recorded_time,
        context_key="weekday|breakfast",
        actor_posterior=actor_posterior,
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        source_record_ids=(uuid4(),),
        observation_opportunity_id=opportunity_id,
    )


def test_habit_baseline_binds_propensity_and_isolates_nonresident_mass(metadata_factory):
    resident = str(uuid4())
    guest = str(uuid4())
    object_id = uuid4()
    kitchen = uuid4()
    guest_room = uuid4()
    model = HierarchicalDirichletHabitModel(
        locations=(kitchen, guest_room),
        resident_actor_keys=(resident,),
        actor_residual_weight=0.75,
    )
    resident_metadata = metadata_factory(
        schema_name="cpswm.HabitLearningEvidence",
        source_type=SourceType.SIMULATION,
    )
    guest_metadata = resident_metadata.model_copy(update={"record_id": uuid4()})

    model.update(
        _habit_evidence(
            resident_metadata,
            object_id=object_id,
            location_id=kitchen,
            actor_posterior={resident: 1.0},
        )
    )
    guest_audit = model.update_audited(
        _habit_evidence(
            guest_metadata,
            object_id=object_id,
            location_id=guest_room,
            actor_posterior={guest: 1.0},
        )
    )
    prediction = model.predict(
        household_id=resident_metadata.household_id,
        person_id=resident,
        object_instance_id=object_id,
        context_key="weekday|breakfast",
    )

    assert guest_audit.resident_mass == 0.0
    assert guest_audit.isolated_nonresident_mass == 1.0
    assert model.isolated_nonresident_count(
        household_id=resident_metadata.household_id,
        object_instance_id=object_id,
        location_id=guest_room,
    ) == pytest.approx(1.0)
    assert prediction.probabilities[kitchen] > prediction.probabilities[guest_room]
    assert prediction.actor_residual


def test_habit_opportunity_correction_is_source_bound(metadata_factory):
    actor = str(uuid4())
    object_id = uuid4()
    location_id = uuid4()
    opportunity_metadata = metadata_factory(
        schema_name="cpswm.ObservationOpportunityRecord",
        source_type=SourceType.SIMULATION,
    )
    opportunity = ObservationOpportunityRecord(
        metadata=opportunity_metadata,
        observation_action_id=uuid4(),
        opportunity_time=opportunity_metadata.recorded_time,
        selected=True,
        selection_probability=0.5,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        likelihood_model_id="opportunity-model@0.1",
    )
    evidence_metadata = opportunity_metadata.model_copy(
        update={
            "record_id": uuid4(),
            "schema_name": "cpswm.HabitLearningEvidence",
        }
    )
    evidence = _habit_evidence(
        evidence_metadata,
        object_id=object_id,
        location_id=location_id,
        actor_posterior={actor: 1.0},
        opportunity_id=opportunity_metadata.record_id,
    )
    model = HierarchicalDirichletHabitModel(locations=(location_id, uuid4()))

    audit = model.update_from_opportunity(
        evidence,
        opportunity,
        ObservationPropensityCorrector(mode=PropensityCorrectionMode.INVERSE),
    )

    assert audit.raw_observation_propensity == pytest.approx(0.5)
    assert audit.propensity_weight == pytest.approx(2.0)
    assert model.known_person_count(
        household_id=evidence_metadata.household_id,
        person_id=actor,
        object_instance_id=object_id,
        location_id=location_id,
    ) == pytest.approx(2.0)


def test_cause_factorized_bocpd_detects_simultaneous_actor_and_habit_change(now):
    neutral = {cause: 0.99 for cause in ChangeCause}
    no_change = {cause: 0.01 for cause in ChangeCause}
    frames = [
        CauseEvidenceFrame(
            timestamp=now + timedelta(days=index),
            continuation_likelihoods=neutral,
            changepoint_likelihoods=no_change,
            evidence_record_ids=(f"frame-{index}",),
        )
        for index in range(2)
    ]
    frames.append(
        CauseEvidenceFrame(
            timestamp=now + timedelta(days=2),
            continuation_likelihoods={
                cause: (0.01 if cause in {ChangeCause.ACTOR, ChangeCause.HABIT} else 0.99)
                for cause in ChangeCause
            },
            changepoint_likelihoods={
                cause: (1.0 if cause in {ChangeCause.ACTOR, ChangeCause.HABIT} else 0.01)
                for cause in ChangeCause
            },
            evidence_record_ids=("frame-2",),
        )
    )

    result = CauseFactorizedBOCPD(hazard_probability=0.05).run(
        tuple(frames), detection_threshold=0.5
    )

    assert result.detected_change_time_by_cause[ChangeCause.ACTOR] == frames[-1].timestamp
    assert result.detected_change_time_by_cause[ChangeCause.HABIT] == frames[-1].timestamp
    assert result.detected_change_time_by_cause[ChangeCause.OBSERVATION] is None
    assert result.detected_change_time_by_cause[ChangeCause.NOISE] is None


def test_active_verification_optimizes_terminal_decision_utility():
    hypotheses = (uuid4(), uuid4())
    action = ObservationActionCandidate(
        action_type=ObservationActionType.MICRO_VERIFY,
        label="inspect the likely location",
        observation_likelihood_model_id="utility-test@0.1",
        calibration_domain="test",
        outcome_likelihoods={
            "first": {hypotheses[0]: 0.9, hypotheses[1]: 0.1},
            "second": {hypotheses[0]: 0.1, hypotheses[1]: 0.9},
        },
        motion_cost=0.05,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    utilities = {
        hypotheses[0]: {hypotheses[0]: 1.0, hypotheses[1]: 0.0},
        hypotheses[1]: {hypotheses[0]: 0.0, hypotheses[1]: 1.0},
    }

    plan = ActionUtilityPlanner().select(
        {hypotheses[0]: 0.5, hypotheses[1]: 0.5},
        (action,),
        terminal_decision_utilities=utilities,
    )

    assert plan.should_act
    assert plan.selected_action_id == action.action_id
    assert plan.scores[0].baseline_decision_utility == pytest.approx(0.5)
    assert plan.scores[0].expected_decision_utility == pytest.approx(0.9)
    assert plan.scores[0].net_value == pytest.approx(0.35)


def test_query_audit_path_requires_a_passed_baseline_gate(metadata_factory, entity_factory):
    source_record_id = uuid4()
    evidence_ref = EvidenceRef(
        evidence_type="direct_observation",
        source_record_id=source_record_id,
    )
    root_id = uuid4()
    source_id = uuid4()
    path = AuditableEvidencePath(
        path_id=uuid4(),
        candidate_rank=1,
        root_candidate_node_id=root_id,
        nodes=(
            EvidencePathNode(
                node_id=root_id,
                node_kind=EvidencePathNodeKind.CANDIDATE,
                claim_code="candidate_location",
            ),
            EvidencePathNode(
                node_id=source_id,
                node_kind=EvidencePathNodeKind.SOURCE,
                claim_code="observed_location",
                source_record_id=source_record_id,
                evidence_refs=(evidence_ref,),
            ),
        ),
        edges=(
            EvidencePathEdge(
                source_node_id=root_id,
                target_node_id=source_id,
                relation=EvidencePathRelation.SUPPORTS,
            ),
        ),
    )
    candidate = QueryCandidate(
        rank=1,
        entity=entity_factory(EntityType.OBJECT_INSTANCE),
        posterior_probability=0.8,
        evidence_refs=(evidence_ref,),
        evidence_path_id=path.path_id,
    )
    gate_evidence = EvidenceRef(evidence_type="evaluation_report", source_record_id=uuid4())
    gate = BaselineClosureGate(
        habit_replay_stable=True,
        actor_contamination_bounded=True,
        cheh_provenance_complete=True,
        shift_attribution_validated=True,
        utility_policy_noninferior=True,
        schemas_frozen=True,
        evidence_refs=(gate_evidence,),
    )
    payload = {
        "metadata": metadata_factory(schema_name="cpswm.WorldModelQueryResult"),
        "query_id": uuid4(),
        "projection_id": uuid4(),
        "candidates": (candidate,),
        "retrieval_coverage": RetrievalCoverage(events_scanned=1),
        "evidence_paths": (path,),
    }

    with pytest.raises(ValueError, match="passed baseline closure gate"):
        WorldModelQueryResult(
            **payload,
            baseline_closure_gate=gate.model_copy(update={"utility_policy_noninferior": False}),
        )
    result = WorldModelQueryResult(**payload, baseline_closure_gate=gate)
    assert result.evidence_paths[0].source_record_ids == {source_record_id}


def test_fair_ablation_enforces_matched_budgets_and_joint_metrics():
    observation_budget = ObservationBudget(
        maximum_observation_actions=10,
        maximum_user_interruptions=2,
        maximum_observation_cost=5.0,
        maximum_elapsed_time_seconds=60.0,
    )
    model_budget = ModelBudget(
        maximum_train_compute_units=100.0,
        maximum_inference_compute_units=10.0,
        maximum_persistent_memory_bytes=1_000_000,
        maximum_latency_ms=100.0,
        maximum_parameter_count=1_000,
    )
    tuning_budget = TuningBudget(
        maximum_trials=20,
        maximum_compute_units=200.0,
        validation_split_sha256="a" * 64,
        objective_name="action_utility",
    )

    def arm(arm_id):
        return FairAblationArm(
            arm_id=arm_id,
            model_version=f"{arm_id}@0.1",
            components=(arm_id,),
            observation_budget=observation_budget,
            model_budget=model_budget,
            tuning_budget=tuning_budget,
            independent_tuning_run_id=uuid4(),
            observation_trace_sha256="b" * 64,
            test_split_sha256="c" * 64,
        )

    baseline = arm("retuned-threshold")
    utility = arm("decision-utility")
    manifest = FairAblationManifest(
        experiment_id=uuid4(), baseline_arm_id=baseline.arm_id, arms=(baseline, utility)
    )
    assert len(manifest.arms) == 2
    with pytest.raises(ValueError, match="same model budget"):
        FairAblationManifest(
            experiment_id=uuid4(),
            baseline_arm_id=baseline.arm_id,
            arms=(
                baseline,
                utility.model_copy(
                    update={
                        "model_budget": model_budget.model_copy(
                            update={"maximum_parameter_count": 999}
                        )
                    }
                ),
            ),
        )

    report = CalibrationUtilityEvaluator().evaluate(
        (
            CalibrationUtilityCase(
                case_id="success",
                predicted_success_probability=0.8,
                success=True,
                realized_action_utility=1.0,
                oracle_action_utility=1.0,
                elapsed_time_seconds=2.0,
                observation_actions=1,
            ),
            CalibrationUtilityCase(
                case_id="failure",
                predicted_success_probability=0.2,
                success=False,
                realized_action_utility=-0.2,
                oracle_action_utility=0.5,
                elapsed_time_seconds=4.0,
                user_interruptions=1,
                observation_actions=1,
            ),
        )
    )
    assert report.brier_score == pytest.approx(0.04)
    assert report.mean_action_utility == pytest.approx(0.4)
    assert report.mean_true_environment_regret == pytest.approx(0.35)
