"""Run the structure-one/structure-two core prototype on one synthetic case."""

from __future__ import annotations

import json
from uuid import uuid4

from cpswm.contracts import ObservationOpportunityRecord
from cpswm.system.evaluation_operations import StructureTwoActionScenarioGenerator
from cpswm.system.prototype_spine import CorePrototypeSpine, PrototypeTransition


def main() -> None:
    case = StructureTwoActionScenarioGenerator().generate(7).visible
    spine = CorePrototypeSpine(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations,
        authorization_scope_id=uuid4(),
    )
    outputs = []
    for observation in case.days:
        if observation.before is None or observation.after is None:
            continue
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
        outputs.append(
            {
                "day": observation.day,
                "regime": result.active_regime,
                "state_conclusion": result.decision.conclusion.value,
                "ccrr_conclusion": result.decision.ccrr_conclusion,
                "owner_mass": result.actor_posterior.get(case.owner_actor, 0.0),
                "propensity_weight": result.propensity.applied_weight,
                "suggested_location": str(result.suggested_location_id),
                "habit_distribution": {
                    str(key): value for key, value in result.habit_prediction.probabilities.items()
                },
                "map_version": result.belief_snapshot.map_version,
            }
        )
    print(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
