from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from cpswm.contracts import EventType, ObservationOutcome
from cpswm.system.counterfactual_event_hypergraph import (
    BernertRamparany2021SequenceBaseline,
    CounterfactualEventHypergraphEngine,
    DamenHogg2012AMGGlobalMAPBaseline,
)
from cpswm.system.synthetic_routines import (
    ObjectRoutineSpec,
    RoutineEventType,
    RoutineGenerationConfig,
    RoutinePlan,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (
    CameraFrustum,
    IncidentalObservationPolicy,
    LocationGeometry,
    RobotPose,
    RobotTaskTrajectorySample,
    SymbolicWorldModelSimulator,
)
from cpswm.system.world_model_simulator.benchmark_access import (
    issue_benchmark_ground_truth_capability,
)
from cpswm_gt import GTInteractionEventType


def uid(value: int) -> UUID:
    return UUID(int=value)


def handoff_config() -> RoutineGenerationConfig:
    return RoutineGenerationConfig(
        household_id=uid(1),
        start_time=datetime(2026, 8, 21, tzinfo=UTC),
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


def endpoint_policy() -> IncidentalObservationPolicy:
    start = handoff_config().start_time
    trajectory = tuple(
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
    )
    return IncidentalObservationPolicy(
        policy_id="m30-handoff-endpoints@0.1",
        primary_task_id=uid(10),
        primary_task_goal="deliver breakfast tray",
        primary_target_object_id=uid(5),
        scheduled_observation_object_id=uid(4),
        selection_probability=1.0,
        field_of_view_coverage=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        robot_task_trajectory=trajectory,
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


def test_m30_v03_generates_complete_handoff_chain_and_privileged_truth_projection():
    plan = SyntheticRoutineGenerator().generate(handoff_config())

    assert plan.generator_version == "synthetic-routines@0.3"
    assert tuple(event.event_type for event in plan.events) == (
        RoutineEventType.PICK_UP,
        RoutineEventType.CARRY,
        RoutineEventType.HANDOFF,
        RoutineEventType.PLACE,
    )
    assert {event.event_chain_id for event in plan.events} == {plan.events[0].event_chain_id}
    assert tuple(event.sequence_no for event in plan.events) == (0, 1, 2, 3)
    assert plan.events[2].actor_id == uid(2)
    assert plan.events[2].recipient_actor_id == uid(3)
    assert plan.events[-1].actor_id == uid(3)
    assert plan.events[-1].destination_location_id == uid(8)

    benchmark_view = SymbolicWorldModelSimulator().run_privileged(
        plan,
        endpoint_policy(),
        capability=issue_benchmark_ground_truth_capability(),
    )
    assert tuple(
        result.detected_location_id for result in benchmark_view.visible_result.detection_results
    ) == (uid(6), uid(8))
    assert all(
        result.outcome == ObservationOutcome.DETECTED
        for result in benchmark_view.visible_result.detection_results
    )
    assert len(benchmark_view.ground_truth.events) == 1
    assert benchmark_view.ground_truth.events[0].actor_gt_entity_id == uid(3)
    assert tuple(event.event_type for event in benchmark_view.ground_truth.interaction_events) == (
        GTInteractionEventType.PICK_UP,
        GTInteractionEventType.CARRY,
        GTInteractionEventType.HANDOFF,
        GTInteractionEventType.PLACE,
    )


def test_m30_v03_contract_rejects_an_incomplete_handoff_chain():
    plan = SyntheticRoutineGenerator().generate(handoff_config())
    payload = plan.model_dump(mode="python")
    payload["events"] = tuple(
        event for event in payload["events"] if event["event_type"] != RoutineEventType.HANDOFF
    )

    with pytest.raises(ValidationError, match="event-chain sequence numbers"):
        RoutinePlan.model_validate(payload)


def test_m30_v03_rejects_a_chain_that_would_begin_before_the_generated_day():
    routine = (
        handoff_config()
        .object_routines[0]
        .model_copy(update={"placement_hour": 0, "placement_minute": 8})
    )

    with pytest.raises(ValidationError, match="begin before the generated day"):
        RoutineGenerationConfig.model_validate(
            handoff_config().model_copy(update={"object_routines": (routine,)}).model_dump()
        )


def test_frozen_m30_v02_asset_keeps_its_original_identity_and_placement_semantics():
    benchmark_dir = Path(__file__).resolve().parents[1] / "benchmarks" / "oam_phm_f0"
    config = RoutineGenerationConfig.model_validate_json(
        (benchmark_dir / "book_on_sofa_routine_v0.2.json").read_text(encoding="utf-8")
    )
    plan = SyntheticRoutineGenerator().generate(config)

    assert plan.generator_version == "synthetic-routines@0.2"
    assert str(plan.plan_id) == "00fb7f52-5845-5bbd-b6f7-f4443537f022"
    assert plan.content_sha256 == "ea4cf80aca652a596b01ad00caf1f91ba60067130b3c1d7f6993cce1b08bfc15"
    assert all(event.event_type == RoutineEventType.PLACE for event in plan.events)


def _predicted_signature(steps):
    return tuple((step.event_type, step.actor_key, step.recipient_actor_key) for step in steps)


def _truth_signature(interaction_events):
    event_type_map = {
        GTInteractionEventType.PICK_UP: EventType.PICK_UP,
        GTInteractionEventType.CARRY: EventType.CARRY,
        GTInteractionEventType.HANDOFF: EventType.TRANSFER,
        GTInteractionEventType.PLACE: EventType.PLACE,
    }
    return tuple(
        (
            event_type_map[event.event_type],
            str(event.actor_gt_entity_id),
            (
                str(event.recipient_actor_gt_entity_id)
                if event.recipient_actor_gt_entity_id is not None
                else None
            ),
        )
        for event in interaction_events
    )


def test_full_chain_exposes_what_prior_art_covers_and_what_cheh_still_must_prove():
    plan = SyntheticRoutineGenerator().generate(handoff_config())
    benchmark_view = SymbolicWorldModelSimulator().run_privileged(
        plan,
        endpoint_policy(),
        capability=issue_benchmark_ground_truth_capability(),
    )
    before, after = benchmark_view.visible_result.detection_results
    actor_keys = (str(uid(2)), str(uid(3)))
    truth = _truth_signature(benchmark_view.ground_truth.interaction_events)

    compatible = BernertRamparany2021SequenceBaseline().predict(
        before=before,
        after=after,
        known_actor_keys=actor_keys,
    )
    assert len(compatible.possible_sequences) == 4
    assert compatible.entailed_responsible_actor_key is None
    assert truth in {
        _predicted_signature(sequence.steps) for sequence in compatible.possible_sequences
    }

    amg_map = DamenHogg2012AMGGlobalMAPBaseline().predict(
        before=before,
        after=after,
        actor_event_likelihoods={str(uid(2)): 0.9, str(uid(3)): 0.6},
        direct_event_likelihood=0.8,
        handoff_event_likelihood=0.2,
    )
    assert amg_map.candidate_count == 4
    assert amg_map.maximizing_responsible_actor_keys
    assert amg_map.map_tie_count >= 1
    assert _predicted_signature(amg_map.selected_sequence.steps) != truth

    tied_amg_map = DamenHogg2012AMGGlobalMAPBaseline().predict(
        before=before,
        after=after,
        actor_event_likelihoods={str(uid(2)): 0.5, str(uid(3)): 0.5},
        direct_event_likelihood=0.8,
        handoff_event_likelihood=0.2,
    )
    assert set(tied_amg_map.maximizing_responsible_actor_keys) == set(actor_keys)
    assert tied_amg_map.map_tie_count == 2

    retuned_amg_map = DamenHogg2012AMGGlobalMAPBaseline().predict(
        before=before,
        after=after,
        actor_event_likelihoods={str(uid(2)): 0.8, str(uid(3)): 0.7},
        direct_event_likelihood=0.3,
        handoff_event_likelihood=0.7,
        handoff_role_likelihoods={
            (str(uid(2)), str(uid(3))): 0.9,
            (str(uid(3)), str(uid(2))): 0.1,
        },
    )
    assert _predicted_signature(retuned_amg_map.selected_sequence.steps) == truth

    cheh = CounterfactualEventHypergraphEngine().branch(
        before=before,
        after=after,
        actor_prior={str(uid(2)): 0.5, str(uid(3)): 0.5},
        unresolved_probability=0.1,
        handoff_fraction=0.4,
    )
    assert truth in {
        _predicted_signature(hypothesis.steps) for hypothesis in cheh.latest.hypotheses
    }
    assert sum(
        hypothesis.posterior_probability for hypothesis in cheh.latest.hypotheses
    ) + cheh.latest.unresolved_probability == pytest.approx(1.0)
