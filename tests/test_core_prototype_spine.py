from __future__ import annotations

from uuid import uuid4

import pytest

from cpswm.contracts import ObservationOpportunityRecord
from cpswm.system.evaluation_operations import StructureTwoActionScenarioGenerator
from cpswm.system.prototype_spine import CorePrototypeSpine, PrototypeTransition


def test_core_prototype_runs_one_transition_end_to_end():
    case = StructureTwoActionScenarioGenerator().generate(3).visible
    observation = next(
        item for item in case.days if item.before is not None and item.after is not None
    )
    assert observation.after is not None
    opportunity = ObservationOpportunityRecord(
        metadata=observation.after.metadata.model_copy(
            update={
                "record_id": observation.after.observation_opportunity_id,
                "schema_name": "cpswm.ObservationOpportunityRecord",
            }
        ),
        observation_action_id=uuid4(),
        opportunity_time=observation.after.detection_time,
        selected=True,
        selection_probability=0.8,
        p_visible_given_state=0.9,
        p_detect_given_visible=0.9,
        likelihood_model_id="prototype-observation@0.1",
    )
    evidence = tuple(
        item
        for item in (
            observation.actor_evidence,
            observation.mechanism_evidence,
            observation.role_evidence,
        )
        if item is not None
    )
    spine = CorePrototypeSpine(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations,
        authorization_scope_id=uuid4(),
    )

    result = spine.process_transition(
        PrototypeTransition(
            opportunity=opportunity,
            before=observation.before,
            after=observation.after,
            actor_prior={
                case.owner_actor: 0.4,
                case.guest_actor: 0.3,
                "unknown_actor": 0.3,
            },
            evidence=evidence,
            context_key="weekday|home",
            context_value=float(observation.day),
        )
    )

    assert sum(result.actor_posterior.values()) == pytest.approx(1.0)
    assert sum(result.habit_prediction.probabilities.values()) == pytest.approx(1.0)
    assert result.suggested_location_id in case.locations
    assert result.belief_snapshot.map_version >= 1
    assert result.habit_update.applied
