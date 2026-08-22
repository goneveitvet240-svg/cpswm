"""End-to-end propensity correction through real observation records."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from test_f0_long_horizon_vertical_slice import build_policy, build_routine_config

from cpswm.contracts import (
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationOpportunityRecord,
    SourceType,
)
from cpswm.system.synthetic_routines import SyntheticRoutineGenerator
from cpswm.system.world_model_simulator import SymbolicWorldModelSimulator
from cpswm.world_model.habits_transitions import (
    HierarchicalDirichletHabitModel,
    ObservationPropensityCorrector,
    PositivityViolation,
    PropensityCorrectionMode,
)


def _evidence(
    metadata,
    *,
    object_id: UUID,
    location_id: UUID,
    event_time,
    source_record_id: UUID,
    opportunity_id: UUID,
) -> HabitLearningEvidence:
    return HabitLearningEvidence(
        metadata=metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.HabitLearningEvidence",
            }
        ),
        object_instance_id=object_id,
        location_id=location_id,
        event_time=event_time,
        context_key="weekday|morning",
        actor_posterior={HierarchicalDirichletHabitModel.UNKNOWN_ACTOR: 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        source_record_ids=(source_record_id,),
        observation_opportunity_id=opportunity_id,
    )


def _household_desk_probability(
    metadata_factory,
    now,
    *,
    desk_id: UUID,
    sofa_id: UUID,
    object_id: UUID,
    observations: tuple[tuple[UUID, float], ...],
    mode: PropensityCorrectionMode,
) -> float:
    model = HierarchicalDirichletHabitModel(
        locations=(desk_id, sofa_id),
        common_prior_strength=0.0,
    )
    corrector = ObservationPropensityCorrector(mode=mode)
    household_id = None

    for location_id, selection_probability in observations:
        opportunity = ObservationOpportunityRecord(
            metadata=metadata_factory(
                schema_name="cpswm.ObservationOpportunityRecord",
                source_type=SourceType.SIMULATION,
            ),
            observation_action_id=uuid4(),
            opportunity_time=now,
            selected=True,
            selection_probability=selection_probability,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            likelihood_model_id="route-bias-fixture@0.1",
        )
        household_id = opportunity.metadata.household_id
        evidence = _evidence(
            opportunity.metadata,
            object_id=object_id,
            location_id=location_id,
            event_time=now,
            source_record_id=uuid4(),
            opportunity_id=opportunity.metadata.record_id,
        )
        correction = corrector.weight_for_opportunity(opportunity)
        assert model.update(evidence, weight_multiplier=correction.applied_weight)

    assert household_id is not None
    prediction = model.predict(
        household_id=household_id,
        person_id=HierarchicalDirichletHabitModel.UNKNOWN_ACTOR,
        object_instance_id=object_id,
        context_key="weekday|morning",
    )
    return prediction.probabilities[desk_id]


def test_f0_uniform_observation_policy_is_exactly_unchanged_by_inverse_correction():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    simulation = SymbolicWorldModelSimulator().run(plan, build_policy())
    desk_id = UUID(int=6)
    sofa_id = UUID(int=7)
    raw_model = HierarchicalDirichletHabitModel(locations=(desk_id, sofa_id))
    corrected_model = HierarchicalDirichletHabitModel(locations=(desk_id, sofa_id))
    raw = ObservationPropensityCorrector(mode=PropensityCorrectionMode.NONE)
    corrected = ObservationPropensityCorrector(mode=PropensityCorrectionMode.INVERSE)

    for opportunity, detection in zip(
        simulation.observation_opportunities,
        simulation.detection_results,
        strict=True,
    ):
        assert detection.detected_object_instance_id is not None
        assert detection.detected_location_id is not None
        assert detection.detection_time is not None
        evidence = _evidence(
            detection.metadata,
            object_id=detection.detected_object_instance_id,
            location_id=detection.detected_location_id,
            event_time=detection.detection_time,
            source_record_id=detection.metadata.record_id,
            opportunity_id=opportunity.metadata.record_id,
        )
        raw_weight = raw.weight_for_opportunity(opportunity)
        corrected_weight = corrected.weight_for_opportunity(opportunity)
        assert raw_weight.applied_weight == pytest.approx(1.0)
        assert corrected_weight.applied_weight == pytest.approx(1.0)
        assert raw_model.update(evidence, weight_multiplier=raw_weight.applied_weight)
        assert corrected_model.update(
            evidence,
            weight_multiplier=corrected_weight.applied_weight,
        )

    prediction_kwargs = {
        "household_id": plan.household_id,
        "person_id": HierarchicalDirichletHabitModel.UNKNOWN_ACTOR,
        "object_instance_id": simulation.scheduled_observation_object_id,
        "context_key": "weekday|morning",
    }
    raw_prediction = raw_model.predict(**prediction_kwargs)
    corrected_prediction = corrected_model.predict(**prediction_kwargs)

    assert raw_prediction.probabilities == corrected_prediction.probabilities
    assert raw_prediction.probabilities[desk_id] == pytest.approx(0.625)
    assert raw.weighted_count == corrected.weighted_count == 3
    assert raw.clipped_fraction == corrected.clipped_fraction == 0.0


def test_real_opportunity_records_remove_opposite_route_bias(metadata_factory, now):
    desk_id = uuid4()
    sofa_id = uuid4()
    object_id = uuid4()
    robot_a = ((desk_id, 0.9),) * 9 + ((sofa_id, 0.1),)
    robot_b = ((desk_id, 0.1),) + ((sofa_id, 0.9),) * 9

    a_raw = _household_desk_probability(
        metadata_factory,
        now,
        desk_id=desk_id,
        sofa_id=sofa_id,
        object_id=object_id,
        observations=robot_a,
        mode=PropensityCorrectionMode.NONE,
    )
    b_raw = _household_desk_probability(
        metadata_factory,
        now,
        desk_id=desk_id,
        sofa_id=sofa_id,
        object_id=object_id,
        observations=robot_b,
        mode=PropensityCorrectionMode.NONE,
    )
    a_corrected = _household_desk_probability(
        metadata_factory,
        now,
        desk_id=desk_id,
        sofa_id=sofa_id,
        object_id=object_id,
        observations=robot_a,
        mode=PropensityCorrectionMode.INVERSE,
    )
    b_corrected = _household_desk_probability(
        metadata_factory,
        now,
        desk_id=desk_id,
        sofa_id=sofa_id,
        object_id=object_id,
        observations=robot_b,
        mode=PropensityCorrectionMode.INVERSE,
    )

    assert a_raw == pytest.approx(0.9, abs=1e-3)
    assert b_raw == pytest.approx(0.1, abs=1e-3)
    assert abs(a_raw - b_raw) == pytest.approx(0.8, abs=1e-3)
    assert a_corrected == pytest.approx(0.5, abs=1e-3)
    assert b_corrected == pytest.approx(0.5, abs=1e-3)
    assert abs(a_corrected - b_corrected) == pytest.approx(0.0, abs=1e-3)


def test_failed_corrections_do_not_pollute_weight_audit_counts():
    inverse = ObservationPropensityCorrector(mode=PropensityCorrectionMode.INVERSE)
    stabilized = ObservationPropensityCorrector(
        mode=PropensityCorrectionMode.STABILIZED,
        minimum_propensity=0.5,
    )

    with pytest.raises(PositivityViolation):
        inverse.weight_for(0.0)
    with pytest.raises(ValueError, match="observe_propensities"):
        stabilized.weight_for(0.1)

    assert inverse.weighted_count == 0
    assert inverse.clipped_fraction == 0.0
    assert stabilized.weighted_count == 0
    assert stabilized.clipped_fraction == 0.0


@pytest.mark.parametrize("invalid_multiplier", [float("nan"), float("inf")])
def test_dirichlet_rejects_non_finite_weight_multiplier(
    metadata_factory,
    now,
    invalid_multiplier,
):
    desk_id = uuid4()
    sofa_id = uuid4()
    object_id = uuid4()
    metadata = metadata_factory(
        schema_name="cpswm.HabitLearningEvidence",
        source_type=SourceType.SIMULATION,
    )
    evidence = _evidence(
        metadata,
        object_id=object_id,
        location_id=desk_id,
        event_time=now,
        source_record_id=uuid4(),
        opportunity_id=uuid4(),
    )
    model = HierarchicalDirichletHabitModel(locations=(desk_id, sofa_id))

    with pytest.raises(ValueError, match="finite"):
        model.update(evidence, weight_multiplier=invalid_multiplier)
