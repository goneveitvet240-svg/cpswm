"""Run the first matched M30 handoff case against CHEH and direct prior-art baselines."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.contracts import EventType  # noqa: E402
from cpswm.system.counterfactual_event_hypergraph import (  # noqa: E402
    BernertRamparany2021SequenceBaseline,
    CounterfactualEventHypergraphEngine,
    DamenHogg2012AMGGlobalMAPBaseline,
)
from cpswm.system.synthetic_routines import (  # noqa: E402
    ObjectRoutineSpec,
    RoutineGenerationConfig,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (  # noqa: E402
    CameraFrustum,
    IncidentalObservationPolicy,
    LocationGeometry,
    RobotPose,
    RobotTaskTrajectorySample,
    SymbolicWorldModelSimulator,
)
from cpswm.system.world_model_simulator.benchmark_access import (  # noqa: E402
    issue_benchmark_ground_truth_capability,
)
from cpswm_gt import GTInteractionEventType  # noqa: E402


def uid(value: int) -> UUID:
    return UUID(int=value)


def build_case() -> tuple[RoutineGenerationConfig, IncidentalObservationPolicy]:
    start = datetime(2026, 8, 21, tzinfo=UTC)
    config = RoutineGenerationConfig(
        household_id=uid(1),
        start_time=start,
        duration_days=1,
        random_seed=20260821,
        object_routines=(
            ObjectRoutineSpec(
                object_instance_id=uid(4),
                default_actor_id=uid(2),
                handoff_recipient_actor_id=uid(3),
                handoff_location_id=uid(7),
                initial_location_id=uid(6),
                habitual_location_id=uid(8),
                placement_hour=9,
                activity_key="shared-breakfast",
                context_key="weekday|morning",
            ),
        ),
    )
    policy = IncidentalObservationPolicy(
        policy_id="m30-handoff-endpoints@0.1",
        primary_task_id=uid(10),
        primary_task_goal="deliver breakfast tray",
        primary_target_object_id=uid(5),
        scheduled_observation_object_id=uid(4),
        selection_probability=1.0,
        field_of_view_coverage=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        robot_task_trajectory=tuple(
            RobotTaskTrajectorySample(
                sample_time=start + timedelta(hours=hour),
                pose=RobotPose(
                    frame_id="household_map",
                    x_m=0.0,
                    y_m=0.0,
                    z_m=1.0,
                    yaw_degrees=0.0,
                ),
                camera_frustum=CameraFrustum(
                    horizontal_fov_degrees=160.0,
                    vertical_fov_degrees=160.0,
                    max_range_m=10.0,
                ),
            )
            for hour in (8, 10)
        ),
        location_geometry=tuple(
            LocationGeometry(
                location_id=location_id,
                frame_id="household_map",
                x_m=2.0,
                y_m=y_m,
                z_m=0.5,
            )
            for location_id, y_m in ((uid(6), -0.5), (uid(7), 0.0), (uid(8), 0.5))
        ),
    )
    return config, policy


def predicted_signature(steps) -> tuple[tuple[str, str, str | None], ...]:
    return tuple(
        (
            step.event_type.value,
            step.actor_key,
            step.recipient_actor_key,
        )
        for step in steps
    )


def truth_signature(interaction_events) -> tuple[tuple[str, str, str | None], ...]:
    event_type_map = {
        GTInteractionEventType.PICK_UP: EventType.PICK_UP,
        GTInteractionEventType.CARRY: EventType.CARRY,
        GTInteractionEventType.HANDOFF: EventType.TRANSFER,
        GTInteractionEventType.PLACE: EventType.PLACE,
    }
    return tuple(
        (
            event_type_map[event.event_type].value,
            str(event.actor_gt_entity_id),
            (
                str(event.recipient_actor_gt_entity_id)
                if event.recipient_actor_gt_entity_id is not None
                else None
            ),
        )
        for event in interaction_events
    )


def run() -> dict[str, object]:
    config, policy = build_case()
    plan = SyntheticRoutineGenerator().generate(config)
    view = SymbolicWorldModelSimulator().run_privileged(
        plan,
        policy,
        capability=issue_benchmark_ground_truth_capability(),
    )
    before, after = view.visible_result.detection_results
    owner = str(uid(2))
    recipient = str(uid(3))
    actors = (owner, recipient)
    truth = truth_signature(view.ground_truth.interaction_events)

    compatible = BernertRamparany2021SequenceBaseline().predict(
        before=before,
        after=after,
        known_actor_keys=actors,
    )
    amg = DamenHogg2012AMGGlobalMAPBaseline().predict(
        before=before,
        after=after,
        actor_event_likelihoods={owner: 0.8, recipient: 0.7},
        direct_event_likelihood=0.3,
        handoff_event_likelihood=0.7,
        handoff_role_likelihoods={
            (owner, recipient): 0.9,
            (recipient, owner): 0.1,
        },
    )
    cheh = CounterfactualEventHypergraphEngine().branch(
        before=before,
        after=after,
        actor_prior={owner: 0.5, recipient: 0.5},
        unresolved_probability=0.1,
        handoff_fraction=0.4,
    )

    compatible_signatures = {
        predicted_signature(sequence.steps) for sequence in compatible.possible_sequences
    }
    cheh_signatures = {
        predicted_signature(hypothesis.steps) for hypothesis in cheh.latest.hypotheses
    }
    return {
        "generator_version": config.generator_version,
        "routine_plan_id": str(plan.plan_id),
        "routine_plan_sha256": plan.content_sha256,
        "truth_signature": truth,
        "bernert_ramparany_2021_adaptation": {
            "candidate_count": len(compatible.possible_sequences),
            "truth_in_candidates": truth in compatible_signatures,
            "entailed_responsible_actor_key": compatible.entailed_responsible_actor_key,
        },
        "damen_hogg_2012_amg_map_adaptation": {
            "candidate_count": amg.candidate_count,
            "top1_exact_chain": predicted_signature(amg.selected_sequence.steps) == truth,
            "selected_signature": predicted_signature(amg.selected_sequence.steps),
        },
        "cheh": {
            "candidate_count": len(cheh.latest.hypotheses),
            "truth_in_candidates": truth in cheh_signatures,
            "normalized_total_mass": cheh.latest.unresolved_probability
            + sum(item.posterior_probability for item in cheh.latest.hypotheses),
            "unresolved_probability": cheh.latest.unresolved_probability,
        },
        "scientific_status": (
            "mechanism case passed; direct-baseline superiority and paper innovation not proved"
        ),
    }


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
