from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    EvidenceRef,
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
    SourceType,
)
from cpswm.world_model.habits_transitions import HierarchicalDirichletHabitModel
from cpswm_gt import (
    GTHabitRegimeKind,
    GTPlacementEvent,
    GroundTruthHabitTrajectory,
)
from simobs import SelectiveObservationSample, simulate_location_observation


def habit_evidence(
    metadata_factory,
    now,
    *,
    object_id: UUID,
    location_id: UUID,
    actor_posterior: dict[str, float],
    evidence_source: HabitEvidenceSource = HabitEvidenceSource.DIRECT_OBSERVATION,
    source_type: SourceType = SourceType.SIMULATION,
    context_key: str = "weekday|breakfast",
) -> HabitLearningEvidence:
    return HabitLearningEvidence(
        metadata=metadata_factory(
            schema_name="cpswm.HabitLearningEvidence",
            source_type=source_type,
        ),
        object_instance_id=object_id,
        location_id=location_id,
        event_time=now,
        context_key=context_key,
        actor_posterior=actor_posterior,
        evidence_source=evidence_source,
        proposed_training_weight=1.0,
        source_record_ids=(uuid4(),),
    )


def observation_opportunity(
    metadata_factory,
    now,
    *,
    selected: bool,
    selection_probability: float = 1.0,
    p_visible_given_state: float = 1.0,
    p_detect_given_visible: float = 1.0,
) -> ObservationOpportunityRecord:
    return ObservationOpportunityRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationOpportunityRecord",
            source_type=SourceType.SIMULATION,
        ),
        observation_action_id=uuid4(),
        opportunity_time=now,
        selected=selected,
        selection_probability=selection_probability,
        p_visible_given_state=p_visible_given_state,
        p_detect_given_visible=p_detect_given_visible,
        likelihood_model_id="controlled-sim@0.1",
    )


def test_not_observed_never_becomes_negative_evidence(metadata_factory, now):
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=False,
        selection_probability=0.4,
        p_visible_given_state=0.0,
        p_detect_given_visible=0.9,
    )
    record = simulate_location_observation(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        observation_opportunity=opportunity,
        detected_object_instance_id=uuid4(),
        detected_location_id=uuid4(),
        sample=SelectiveObservationSample(
            selected=False, target_present=True, detection_draw=0.0
        ),
    )

    assert not record.supports_negative_evidence
    assert record.negative_evidence_strength == 0.0


def test_verified_absence_uses_detection_opportunity(metadata_factory, now):
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=True,
        selection_probability=0.4,
        p_visible_given_state=0.8,
        p_detect_given_visible=0.75,
    )
    record = simulate_location_observation(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        observation_opportunity=opportunity,
        detected_object_instance_id=uuid4(),
        detected_location_id=uuid4(),
        sample=SelectiveObservationSample(
            selected=True, target_present=False, detection_draw=0.0
        ),
    )

    assert record.supports_negative_evidence
    assert record.negative_evidence_strength == pytest.approx(0.6)


def test_ambiguous_result_cannot_smuggle_truth_through_evidence_refs(
    metadata_factory, now
):
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=True,
        p_visible_given_state=0.0,
    )

    ambiguous = simulate_location_observation(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        observation_opportunity=opportunity,
        detected_object_instance_id=uuid4(),
        detected_location_id=uuid4(),
        sample=SelectiveObservationSample(
            selected=True, target_present=True, detection_draw=0.0
        ),
    )
    payload = ambiguous.model_dump(mode="python")
    payload["evidence_refs"] = (
        EvidenceRef(
            evidence_type="ground_truth",
            source_record_id=uuid4(),
            locator="object/location/event-time",
        ),
    )

    with pytest.raises(ValidationError, match="privileged evidence references"):
        ObservationDetectionResult.model_validate(payload)


def test_simulation_opportunity_cannot_smuggle_truth_through_evidence_refs(
    metadata_factory, now
):
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=True,
    )
    payload = opportunity.model_dump(mode="python")
    payload["evidence_refs"] = (
        EvidenceRef(
            evidence_type="ground_truth",
            source_record_id=uuid4(),
            locator="object/location/event-time",
        ),
    )

    with pytest.raises(ValidationError, match="privileged evidence references"):
        ObservationOpportunityRecord.model_validate(payload)


def test_model_prediction_cannot_train_habit_model(metadata_factory, now):
    person_id = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    model = HierarchicalDirichletHabitModel(
        locations=(desk_id, kitchen_id),
        common_prior={desk_id: 0.5, kitchen_id: 0.5},
    )
    evidence = habit_evidence(
        metadata_factory,
        now,
        object_id=object_id,
        location_id=kitchen_id,
        actor_posterior={str(person_id): 1.0},
        evidence_source=HabitEvidenceSource.MODEL_PREDICTION,
        source_type=SourceType.MODEL,
    )

    before = model.predict(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        context_key=evidence.context_key,
    )
    assert not model.update(evidence)
    after = model.predict(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        context_key=evidence.context_key,
    )

    assert before.probabilities == after.probabilities
    assert model.known_person_count(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        location_id=kitchen_id,
    ) == 0.0


def test_soft_actor_update_does_not_assign_unknown_mass_to_person(
    metadata_factory, now
):
    person_a = uuid4()
    person_b = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    model = HierarchicalDirichletHabitModel(locations=(desk_id, kitchen_id))
    evidence = habit_evidence(
        metadata_factory,
        now,
        object_id=object_id,
        location_id=kitchen_id,
        actor_posterior={
            str(person_a): 0.5,
            str(person_b): 0.25,
            "unknown_actor": 0.25,
        },
        evidence_source=HabitEvidenceSource.INFERRED_EVENT,
        source_type=SourceType.INFERENCE,
    )

    assert model.update(evidence)
    assert model.known_person_count(
        household_id=evidence.metadata.household_id,
        person_id=person_a,
        object_instance_id=object_id,
        location_id=kitchen_id,
    ) == pytest.approx(0.5)
    assert model.known_person_count(
        household_id=evidence.metadata.household_id,
        person_id=person_b,
        object_instance_id=object_id,
        location_id=kitchen_id,
    ) == pytest.approx(0.25)
    assert model.known_person_count(
        household_id=evidence.metadata.household_id,
        person_id="unknown_actor",
        object_instance_id=object_id,
        location_id=kitchen_id,
    ) == 0.0


def test_personal_evidence_moves_prediction_away_from_common_prior(
    metadata_factory, now
):
    person_id = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    model = HierarchicalDirichletHabitModel(
        locations=(desk_id, kitchen_id),
        common_prior={desk_id: 0.8, kitchen_id: 0.2},
        common_prior_strength=2.0,
    )
    evidence = habit_evidence(
        metadata_factory,
        now,
        object_id=object_id,
        location_id=kitchen_id,
        actor_posterior={str(person_id): 1.0},
    )

    prior_prediction = model.predict(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        context_key=evidence.context_key,
    )
    for _ in range(3):
        model.update(evidence)
    personalized = model.predict(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        context_key=evidence.context_key,
    )

    assert prior_prediction.probabilities[desk_id] == pytest.approx(0.8)
    assert personalized.probabilities[kitchen_id] > prior_prediction.probabilities[kitchen_id]


def test_habit_evidence_requires_normalized_actor_posterior(
    metadata_factory, now
):
    with pytest.raises(ValidationError):
        habit_evidence(
            metadata_factory,
            now,
            object_id=uuid4(),
            location_id=uuid4(),
            actor_posterior={str(uuid4()): 0.6, "unknown_actor": 0.3},
        )


def test_ground_truth_habit_trajectory_requires_chronological_events(now):
    actor_id = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    later = GTPlacementEvent(
        event_time=now + timedelta(hours=1),
        actor_gt_entity_id=actor_id,
        object_gt_entity_id=object_id,
        source_location_gt_entity_id=desk_id,
        destination_location_gt_entity_id=kitchen_id,
        context_key="weekday|breakfast",
        regime_id="routine-a",
        regime_kind=GTHabitRegimeKind.STABLE,
    )
    earlier = later.model_copy(
        update={"gt_event_id": uuid4(), "event_time": now}
    )

    with pytest.raises(ValidationError):
        GroundTruthHabitTrajectory(
            simulation_run_id=uuid4(),
            events=(later, earlier),
        )


def test_selective_observation_is_replayable_and_gt_free(metadata_factory, now):
    object_id = uuid4()
    location_id = uuid4()
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=True,
        selection_probability=0.25,
        p_visible_given_state=0.9,
        p_detect_given_visible=0.8,
    )
    kwargs = {
        "metadata": metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        "observation_opportunity": opportunity,
        "detected_object_instance_id": object_id,
        "detected_location_id": location_id,
        "sample": SelectiveObservationSample(
            selected=True,
            target_present=True,
            detection_draw=0.1,
        ),
    }

    first = simulate_location_observation(**kwargs)
    replay = simulate_location_observation(**kwargs)

    assert first == replay
    assert first.outcome == ObservationOutcome.DETECTED
    assert "ground_truth" not in first.model_dump_json()


def test_unselected_opportunity_cannot_update_personal_habit(
    metadata_factory, now
):
    person_id = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    opportunity = observation_opportunity(
        metadata_factory,
        now,
        selected=False,
        selection_probability=0.25,
    )
    observation = simulate_location_observation(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        observation_opportunity=opportunity,
        detected_object_instance_id=object_id,
        detected_location_id=kitchen_id,
        sample=SelectiveObservationSample(
            selected=False,
            target_present=True,
            detection_draw=0.0,
        ),
    )
    model = HierarchicalDirichletHabitModel(locations=(desk_id, kitchen_id))

    assert observation.outcome == ObservationOutcome.NOT_OBSERVED
    assert model.known_person_count(
        household_id=observation.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        location_id=kitchen_id,
    ) == 0.0


def test_detected_placement_updates_habit_without_world_model_gt_import(
    metadata_factory, now
):
    person_id = uuid4()
    object_id = uuid4()
    desk_id = uuid4()
    kitchen_id = uuid4()
    gt_event = GTPlacementEvent(
        event_time=now,
        actor_gt_entity_id=person_id,
        object_gt_entity_id=object_id,
        source_location_gt_entity_id=desk_id,
        destination_location_gt_entity_id=kitchen_id,
        context_key="weekday|breakfast",
        regime_id="routine-a",
        regime_kind=GTHabitRegimeKind.STABLE,
    )
    opportunity = observation_opportunity(metadata_factory, now, selected=True)
    observation = simulate_location_observation(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationDetectionResult",
            source_type=SourceType.SIMULATION,
        ),
        observation_opportunity=opportunity,
        detected_object_instance_id=object_id,
        detected_location_id=kitchen_id,
        sample=SelectiveObservationSample(
            selected=True,
            target_present=(
                gt_event.destination_location_gt_entity_id == kitchen_id
            ),
            detection_draw=0.0,
        ),
    )
    assert observation.outcome == ObservationOutcome.DETECTED

    evidence = HabitLearningEvidence(
        metadata=metadata_factory(
            schema_name="cpswm.HabitLearningEvidence",
            source_type=SourceType.SIMULATION,
        ),
        object_instance_id=object_id,
        location_id=kitchen_id,
        event_time=now,
        context_key=gt_event.context_key,
        actor_posterior={str(person_id): 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        source_record_ids=(observation.metadata.record_id,),
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    model = HierarchicalDirichletHabitModel(locations=(desk_id, kitchen_id))
    model.update(evidence)
    prediction = model.predict(
        household_id=evidence.metadata.household_id,
        person_id=person_id,
        object_instance_id=object_id,
        context_key=evidence.context_key,
    )

    assert prediction.probabilities[kitchen_id] > prediction.probabilities[desk_id]
