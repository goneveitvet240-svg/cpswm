from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import EvidenceRef, ObservationMode, ObservationOutcome, SourceType
from cpswm.system.evaluation_operations import (
    EvaluationReport,
    EvaluationRunner,
)
from cpswm.system.household_memory_benchmark import (
    BenchmarkBudget,
    BenchmarkManifest,
    BenchmarkTaskFamily,
    DatasetSplit,
    EvaluationTrack,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.synthetic_routines import (
    ObjectRoutineSpec,
    RoutineChangeKind,
    RoutineChangeSpec,
    RoutineEventType,
    RoutineGenerationConfig,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (
    CameraFrustum,
    IncidentalObservationPolicy,
    LocationGeometry,
    RobotPose,
    RobotTaskTrajectorySample,
    SymbolicWorldModelSimulator,
    detection_result_record_id,
)
from cpswm.system.world_model_simulator.benchmark_access import (
    issue_benchmark_ground_truth_capability,
)


def uid(value: int) -> UUID:
    return UUID(int=value)


def build_policy(**updates) -> IncidentalObservationPolicy:
    start_time = datetime(2026, 8, 13, tzinfo=UTC)
    policy = IncidentalObservationPolicy(
        policy_id="cup-search-incidental@0.3",
        primary_task_id=uid(9),
        primary_task_goal="find yesterday's drinking cup",
        primary_target_object_id=uid(5),
        scheduled_observation_object_id=uid(4),
        selection_probability=1.0,
        field_of_view_coverage=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        additional_action_cost=0.0,
        robot_task_trajectory=tuple(
            RobotTaskTrajectorySample(
                sample_time=start_time + timedelta(days=day, hours=10),
                pose=RobotPose(
                    frame_id="household_map",
                    x_m=0.0,
                    y_m=0.0,
                    z_m=1.0,
                    yaw_degrees=0.0,
                ),
                camera_frustum=CameraFrustum(
                    horizontal_fov_degrees=120.0,
                    vertical_fov_degrees=120.0,
                    max_range_m=10.0,
                ),
            )
            for day in range(3)
        ),
        location_geometry=(
            LocationGeometry(
                location_id=uid(6),
                frame_id="household_map",
                x_m=2.0,
                y_m=-0.5,
                z_m=0.5,
            ),
            LocationGeometry(
                location_id=uid(7),
                frame_id="household_map",
                x_m=2.0,
                y_m=0.5,
                z_m=0.5,
            ),
        ),
    )
    return policy.model_copy(update=updates)


def run_benchmark_view(plan, policy):
    return SymbolicWorldModelSimulator().run_privileged(
        plan,
        policy,
        capability=issue_benchmark_ground_truth_capability(),
    )


def build_manifest(plan=None, policy=None) -> BenchmarkManifest:
    plan = plan or SyntheticRoutineGenerator().generate(build_routine_config())
    policy = policy or build_policy()
    expected_simulation = SymbolicWorldModelSimulator().run(plan, policy)
    payload = {
        "manifest_id": "oam-phm-f0-book-on-sofa",
        "manifest_version": "0.4.0",
        "routine_plan_id": plan.plan_id,
        "routine_plan_sha256": plan.content_sha256,
        "observation_policy_id": policy.policy_id,
        "observation_policy_sha256": content_sha256(policy),
        "primary_target_object_id": policy.primary_target_object_id,
        "scheduled_observation_object_id": policy.scheduled_observation_object_id,
        "simulator_version": SymbolicWorldModelSimulator.simulator_version,
        "expected_simulation_content_sha256": (expected_simulation.simulation_content_sha256),
        "household_ids": (uid(1),),
        "person_ids": (uid(2), uid(3)),
        "object_instance_ids": (uid(4), uid(5)),
        "location_ids": (uid(6), uid(7)),
        "duration_days": 3,
        "session_duration_hours": 1.0,
        "tracks": (EvaluationTrack.CONTROLLED_NOISE,),
        "task_families": (
            BenchmarkTaskFamily.MEMORY_ACCURACY,
            BenchmarkTaskFamily.HABIT_PREDICTION,
            BenchmarkTaskFamily.ADAPTATION,
            BenchmarkTaskFamily.EXPLANATION,
            BenchmarkTaskFamily.EMBODIED_UTILITY,
        ),
        "household_splits": {uid(1): DatasetSplit.PUBLIC_TEST},
        "random_seed": 20260813,
        "budget": BenchmarkBudget(
            max_selected_observation_actions=20,
            max_selected_verifications=2,
        ),
        "metric_names": (
            "controlled_observation_recall",
            "anomaly_observation_recall",
            "incidental_context_coverage",
            "declared_primary_task_additional_action_cost_total",
        ),
    }
    provisional = BenchmarkManifest(
        **payload,
        manifest_sha256="0" * 64,
    )
    return provisional.model_copy(
        update={"manifest_sha256": content_sha256(provisional._identity_payload())}
    )


def update_manifest(manifest: BenchmarkManifest, **updates) -> BenchmarkManifest:
    payload = manifest.model_dump(mode="python", exclude={"manifest_sha256"})
    payload.update(updates)
    provisional = BenchmarkManifest(
        **payload,
        manifest_sha256="0" * 64,
    )
    return provisional.model_copy(
        update={"manifest_sha256": content_sha256(provisional._identity_payload())}
    )


def rehash_simulation(simulation, **updates):
    """Build an adversarial model_copy with a matching content hash.

    This deliberately bypasses construction-time validation so evaluator-entry
    validation, rather than a test helper, is what must reject bad bindings.
    """

    mutated = simulation.model_copy(update=updates)
    return mutated.model_copy(
        update={"simulation_content_sha256": content_sha256(mutated.content_payload())}
    )


def rehash_benchmark_view(view, *, visible_updates=None, **updates):
    """Rehash a privileged test view after an intentional adversarial update."""

    visible = rehash_simulation(view.visible_result, **(visible_updates or {}))
    mutated = view.model_copy(update={"visible_result": visible, **updates})
    payload = mutated.content_payload()
    return mutated.model_copy(
        update={
            "privileged_simulation_id": content_uuid("privileged-simulation", payload),
            "privileged_content_sha256": content_sha256(payload),
        }
    )


def view_with_visible_result(plan, policy, visible_result):
    """Bind an intentionally mutated public result into a rehashed oracle view."""

    view = run_benchmark_view(plan, policy)
    mutated = view.model_copy(update={"visible_result": visible_result})
    payload = mutated.content_payload()
    return mutated.model_copy(
        update={
            "privileged_simulation_id": content_uuid("privileged-simulation", payload),
            "privileged_content_sha256": content_sha256(payload),
        }
    )


def rebind_detection_result(result, **updates):
    """Apply adversarial updates while keeping the result content ID valid."""

    mutated = result.model_copy(update=updates)
    return mutated.model_copy(
        update={
            "metadata": mutated.metadata.model_copy(
                update={"record_id": detection_result_record_id(mutated)}
            )
        }
    )


def build_routine_config() -> RoutineGenerationConfig:
    return RoutineGenerationConfig(
        household_id=uid(1),
        start_time=datetime(2026, 8, 13, tzinfo=UTC),
        duration_days=3,
        random_seed=20260813,
        object_routines=(
            ObjectRoutineSpec(
                object_instance_id=uid(4),  # Book_17
                default_actor_id=uid(2),  # owner
                initial_location_id=uid(6),  # desk
                habitual_location_id=uid(6),
                placement_hour=9,
                activity_key="reading",
                context_key="weekday|morning",
            ),
        ),
        changes=(
            RoutineChangeSpec(
                change_id=uid(8),
                kind=RoutineChangeKind.ISOLATED_ANOMALY,
                object_instance_id=uid(4),
                start_day=1,
                target_location_id=uid(7),  # sofa
            ),
        ),
    )


def test_f0_book_on_sofa_slice_is_replayable_and_gt_isolated():
    generator = SyntheticRoutineGenerator()
    first_plan = generator.generate(build_routine_config())
    replay_plan = generator.generate(build_routine_config())
    assert first_plan == replay_plan
    assert [
        event.destination_location_id
        for event in first_plan.events
        if event.event_type == RoutineEventType.PLACE
    ] == [
        uid(6),
        uid(7),
        uid(6),
    ]

    policy = build_policy()
    manifest = build_manifest(first_plan, policy)
    simulator = SymbolicWorldModelSimulator()
    first_run = simulator.run(first_plan, policy)
    replay_run = simulator.run(replay_plan, policy)

    assert first_run == replay_run
    assert all(
        result.outcome == ObservationOutcome.DETECTED for result in first_run.detection_results
    )
    sofa_result = first_run.detection_results[1]
    sofa_opportunity = first_run.observation_opportunities[1]
    assert sofa_result.detected_location_id == uid(7)
    assert sofa_opportunity.incidental_context is not None
    assert sofa_opportunity.incidental_context.observation_mode == ObservationMode.INCIDENTAL
    assert sofa_opportunity.incidental_context.primary_task_goal == policy.primary_task_goal
    assert sofa_opportunity.incidental_context.candidate_entity_ids == ()
    for record in (sofa_opportunity, sofa_result):
        assert "ground_truth" not in record.model_dump_json()
        assert "gt_" not in record.model_dump_json()

    evaluator = EvaluationRunner()
    first_report = evaluator.evaluate(
        manifest,
        run_benchmark_view(first_plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    replay_report = evaluator.evaluate(
        manifest,
        run_benchmark_view(replay_plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    assert first_report == replay_report
    assert not first_report.ground_truth_leakage_detected
    assert first_report.metric_value("anomaly_observation_recall") == 1.0
    assert first_report.metric_value("incidental_context_coverage") == 1.0
    assert first_report.metric_value("declared_primary_task_additional_action_cost_total") == 0.0


def test_benchmark_manifest_rejects_split_leakage():
    manifest = build_manifest()
    payload = manifest.model_dump()
    payload["household_splits"] = {
        uid(1): DatasetSplit.TRAIN,
        uid(99): DatasetSplit.HIDDEN_TEST,
    }
    with pytest.raises(ValidationError):
        BenchmarkManifest.model_validate(payload)


def test_f0_budget_rejects_unmeasured_legacy_limits_and_incoherent_caps():
    with pytest.raises(ValidationError, match="max_query_results"):
        BenchmarkBudget.model_validate(
            {
                "max_selected_observation_actions": 2,
                "max_selected_verifications": 1,
                "max_query_results": 5,
            }
        )
    with pytest.raises(
        ValidationError,
        match="max_selected_verifications cannot exceed",
    ):
        BenchmarkBudget(
            max_selected_observation_actions=1,
            max_selected_verifications=2,
        )


def test_evaluator_rejects_a_simulation_with_a_different_seed():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy(policy_id="seed-binding-test")
    manifest = build_manifest(plan, policy)
    view = run_benchmark_view(plan, policy)
    mismatched = rehash_benchmark_view(view, visible_updates={"random_seed": 7})

    with pytest.raises(ValueError, match=r"random seed|run ID"):
        EvaluationRunner().evaluate(
            manifest,
            mismatched,
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_checked_in_f0_benchmark_assets_produce_the_implemented_report():
    repository_root = Path(__file__).resolve().parents[1]
    benchmark_dir = repository_root / "benchmarks" / "oam_phm_f0"
    manifest = BenchmarkManifest.model_validate_json(
        (benchmark_dir / "book_on_sofa_manifest_v0.4.json").read_text(encoding="utf-8")
    )
    routine_config = RoutineGenerationConfig.model_validate_json(
        (benchmark_dir / "book_on_sofa_routine_v0.2.json").read_text(encoding="utf-8")
    )
    policy = IncidentalObservationPolicy.model_validate_json(
        (benchmark_dir / "book_on_sofa_policy_v0.3.json").read_text(encoding="utf-8")
    )

    plan = SyntheticRoutineGenerator().generate(routine_config)
    report = EvaluationRunner().evaluate(
        manifest, run_benchmark_view(plan, policy), track=EvaluationTrack.CONTROLLED_NOISE
    )

    assert report.metric_value("anomaly_observation_recall") == 1.0
    assert report.metric_value("declared_primary_task_additional_action_cost_total") == 0.0
    assert not report.ground_truth_leakage_detected


def test_ambiguous_observation_does_not_expose_truth_identity_location_or_time():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy(
        policy_id="zero-visibility@0.1",
        p_visible_given_state=0.0,
    )
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result

    result = simulation.detection_results[0]
    opportunity = simulation.observation_opportunities[0]
    truth = view.ground_truth.events[0]
    assert result.outcome == ObservationOutcome.AMBIGUOUS
    assert result.detected_object_instance_id is None
    assert result.detected_location_id is None
    assert result.detection_time is None
    assert not hasattr(opportunity, "object_instance_id")
    assert not hasattr(opportunity, "candidate_location_id")
    assert opportunity.opportunity_time != truth.event_time
    assert opportunity.incidental_context.candidate_entity_ids == ()


def test_observation_clock_is_independent_of_hidden_truth_event_cardinality():
    config = build_routine_config()
    hidden_routine = ObjectRoutineSpec(
        object_instance_id=uid(10),
        default_actor_id=uid(2),
        initial_location_id=uid(6),
        habitual_location_id=uid(7),
        placement_hour=8,
        activity_key="hidden-control",
        context_key="hidden|morning",
    )
    expanded_config = config.model_copy(
        update={"object_routines": (*config.object_routines, hidden_routine)}
    )
    generator = SyntheticRoutineGenerator()
    base_plan = generator.generate(config)
    expanded_plan = generator.generate(expanded_config)
    policy = build_policy(
        policy_id="zero-visibility-fixed-clock@0.1",
        selection_probability=0.5,
        p_visible_given_state=0.0,
    )

    base = SymbolicWorldModelSimulator().run(base_plan, policy)
    expanded = SymbolicWorldModelSimulator().run(expanded_plan, policy)

    assert len(base_plan.events) == 9
    assert len(expanded_plan.events) == 18
    assert sum(event.event_type == RoutineEventType.PLACE for event in base_plan.events) == 3
    assert sum(event.event_type == RoutineEventType.PLACE for event in expanded_plan.events) == 6
    assert tuple(item.opportunity_time for item in base.observation_opportunities) == (
        tuple(item.opportunity_time for item in expanded.observation_opportunities)
    )
    assert base.observation_opportunities == expanded.observation_opportunities
    assert base.detection_results == expanded.detection_results
    assert base.model_dump_json() == expanded.model_dump_json()
    assert len(base.observation_opportunities) == 3
    assert len(expanded.observation_opportunities) == 3
    for opportunity, result in zip(
        (*base.observation_opportunities, *expanded.observation_opportunities),
        (*base.detection_results, *expanded.detection_results),
        strict=True,
    ):
        assert result.outcome == (
            ObservationOutcome.AMBIGUOUS
            if opportunity.selected
            else ObservationOutcome.NOT_OBSERVED
        )
        assert result.detected_object_instance_id is None
        assert result.detected_location_id is None
        assert result.detection_time is None


def test_undetected_target_relocation_does_not_leak_through_opportunity_visibility():
    base_config = build_routine_config().model_copy(update={"changes": ()})
    relocated_routine = base_config.object_routines[0].model_copy(
        update={"habitual_location_id": uid(7)}
    )
    relocated_config = base_config.model_copy(update={"object_routines": (relocated_routine,)})
    generator = SyntheticRoutineGenerator()
    base_plan = generator.generate(base_config)
    relocated_plan = generator.generate(relocated_config)
    policy = build_policy(
        policy_id="zero-detection-hidden-relocation@0.1",
        p_detect_given_visible=0.0,
        location_geometry=(
            LocationGeometry(
                location_id=uid(6),
                frame_id="household_map",
                x_m=2.0,
                y_m=0.0,
                z_m=0.5,
            ),
            # The hidden relocated state lies behind the same primary-task
            # camera; a failed detection must not reveal that intersection.
            LocationGeometry(
                location_id=uid(7),
                frame_id="household_map",
                x_m=-2.0,
                y_m=0.0,
                z_m=0.5,
            ),
        ),
    )

    base = SymbolicWorldModelSimulator().run(base_plan, policy)
    relocated = SymbolicWorldModelSimulator().run(relocated_plan, policy)

    assert base.simulation_run_id == relocated.simulation_run_id
    assert all(
        item.outcome == ObservationOutcome.AMBIGUOUS
        for item in (*base.detection_results, *relocated.detection_results)
    )
    assert base.observation_opportunities == relocated.observation_opportunities
    assert base.detection_results == relocated.detection_results
    assert base.model_dump_json() == relocated.model_dump_json()


def test_future_hidden_destination_without_geometry_does_not_change_pre_event_run():
    original = build_routine_config()
    base_routine = original.object_routines[0].model_copy(
        update={"habitual_location_id": uid(6), "placement_hour": 23}
    )
    future_routine = base_routine.model_copy(update={"habitual_location_id": uid(11)})
    base_config = original.model_copy(
        update={
            "duration_days": 1,
            "object_routines": (base_routine,),
            "changes": (),
        }
    )
    future_config = base_config.model_copy(update={"object_routines": (future_routine,)})
    generator = SyntheticRoutineGenerator()
    base_plan = generator.generate(base_config)
    future_plan = generator.generate(future_config)
    policy = build_policy(
        policy_id="future-destination-noninterference@0.1",
        robot_task_trajectory=(build_policy().robot_task_trajectory[0],),
        location_geometry=(build_policy().location_geometry[0],),
    )

    base = SymbolicWorldModelSimulator().run(base_plan, policy)
    future = SymbolicWorldModelSimulator().run(future_plan, policy)

    assert base.model_dump_json() == future.model_dump_json()


def test_controlled_recall_ignores_unrelated_hidden_truth_events():
    config = build_routine_config()
    hidden_routine = ObjectRoutineSpec(
        object_instance_id=uid(10),
        default_actor_id=uid(2),
        initial_location_id=uid(6),
        habitual_location_id=uid(7),
        placement_hour=8,
        activity_key="hidden-control",
        context_key="hidden|morning",
    )
    expanded_config = config.model_copy(
        update={"object_routines": (*config.object_routines, hidden_routine)}
    )
    generator = SyntheticRoutineGenerator()
    base_plan = generator.generate(config)
    expanded_plan = generator.generate(expanded_config)
    policy = build_policy()
    simulator = SymbolicWorldModelSimulator()
    base_manifest = build_manifest(base_plan, policy)
    expanded_manifest = update_manifest(
        build_manifest(expanded_plan, policy),
        object_instance_ids=(uid(4), uid(5), uid(10)),
    )

    base_report = EvaluationRunner().evaluate(
        base_manifest,
        run_benchmark_view(base_plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    expanded_report = EvaluationRunner().evaluate(
        expanded_manifest,
        run_benchmark_view(expanded_plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    base_recall = next(
        metric
        for metric in base_report.metrics
        if metric.metric_name == "controlled_observation_recall"
    )
    expanded_recall = next(
        metric
        for metric in expanded_report.metrics
        if metric.metric_name == "controlled_observation_recall"
    )
    base_anomaly = next(
        metric
        for metric in base_report.metrics
        if metric.metric_name == "anomaly_observation_recall"
    )
    expanded_anomaly = next(
        metric
        for metric in expanded_report.metrics
        if metric.metric_name == "anomaly_observation_recall"
    )

    assert (base_recall.value, base_recall.sample_count) == (1.0, 3)
    assert (expanded_recall.value, expanded_recall.sample_count) == (1.0, 3)
    assert (base_anomaly.value, base_anomaly.sample_count) == (1.0, 1)
    assert (expanded_anomaly.value, expanded_anomaly.sample_count) == (1.0, 1)


def test_observation_queries_causal_state_before_a_future_placement():
    config = build_routine_config()
    late_routine = config.object_routines[0].model_copy(
        update={
            "habitual_location_id": uid(7),
            "placement_hour": 23,
        }
    )
    config = config.model_copy(update={"object_routines": (late_routine,), "changes": ()})
    plan = SyntheticRoutineGenerator().generate(config)
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result

    first_truth = view.ground_truth.events[0]
    first_opportunity = simulation.observation_opportunities[0]
    first_result = simulation.detection_results[0]
    assert first_opportunity.opportunity_time == (config.start_time + timedelta(hours=10))
    assert first_truth.event_time == config.start_time + timedelta(hours=23)
    assert first_truth.destination_location_gt_entity_id == uid(7)
    assert first_result.outcome == ObservationOutcome.DETECTED
    assert first_result.detected_location_id == uid(6)
    assert first_result.detection_time < first_truth.event_time

    manifest = build_manifest(plan, policy)
    report = EvaluationRunner().evaluate(
        manifest,
        view,
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    assert not report.ground_truth_leakage_detected


def test_detection_result_identity_changes_with_realized_target_state():
    config = build_routine_config().model_copy(update={"changes": ()})
    changed_routine = config.object_routines[0].model_copy(update={"habitual_location_id": uid(7)})
    changed_config = config.model_copy(update={"object_routines": (changed_routine,)})
    generator = SyntheticRoutineGenerator()
    base_plan = generator.generate(config)
    changed_plan = generator.generate(changed_config)
    policy = build_policy()

    base = SymbolicWorldModelSimulator().run(base_plan, policy)
    changed = SymbolicWorldModelSimulator().run(changed_plan, policy)

    assert tuple(item.metadata.record_id for item in base.observation_opportunities) == tuple(
        item.metadata.record_id for item in changed.observation_opportunities
    )
    assert tuple(item.detected_location_id for item in base.detection_results) != tuple(
        item.detected_location_id for item in changed.detection_results
    )
    assert tuple(item.metadata.record_id for item in base.detection_results) != tuple(
        item.metadata.record_id for item in changed.detection_results
    )
    for result in (*base.detection_results, *changed.detection_results):
        assert result.metadata.record_id == detection_result_record_id(result)


def test_evaluator_rejects_stale_detection_result_identity():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    original = simulation.detection_results[0]
    stale_identity = original.model_copy(update={"detected_location_id": uid(7)})
    assert stale_identity.metadata.record_id != detection_result_record_id(stale_identity)
    tampered_simulation = rehash_simulation(
        simulation,
        detection_results=(
            stale_identity,
            *simulation.detection_results[1:],
        ),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(tampered_simulation.simulation_content_sha256),
    )

    with pytest.raises(ValueError, match="record ID does not match realized content"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered_simulation),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_evaluator_rejects_detection_for_a_non_scheduled_object():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    original = simulation.detection_results[0]
    tampered = original.model_copy(update={"detected_object_instance_id": uid(5)})
    tampered = tampered.model_copy(
        update={
            "metadata": tampered.metadata.model_copy(
                update={"record_id": detection_result_record_id(tampered)}
            )
        }
    )
    tampered_simulation = rehash_simulation(
        simulation,
        detection_results=(tampered, *simulation.detection_results[1:]),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(tampered_simulation.simulation_content_sha256),
    )

    with pytest.raises(ValueError, match="scheduled observation object"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered_simulation),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_evaluator_rejects_candidate_identity_on_an_opportunity():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    original = simulation.observation_opportunities[0]
    context = original.incidental_context.model_copy(
        update={"candidate_entity_ids": (policy.scheduled_observation_object_id,)}
    )
    tampered = original.model_copy(update={"incidental_context": context})
    tampered_simulation = rehash_simulation(
        simulation,
        observation_opportunities=(
            tampered,
            *simulation.observation_opportunities[1:],
        ),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(tampered_simulation.simulation_content_sha256),
    )

    with pytest.raises(ValueError, match="must not expose candidate identities"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered_simulation),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_content_bound_plan_simulation_and_evaluation_ids_change():
    generator = SyntheticRoutineGenerator()
    config = build_routine_config()
    base_plan = generator.generate(config)
    no_change_plan = generator.generate(config.model_copy(update={"changes": ()}))
    assert base_plan.plan_id != no_change_plan.plan_id

    base_policy = build_policy()
    changed_policy = base_policy.model_copy(update={"p_detect_given_visible": 0.5})
    simulator = SymbolicWorldModelSimulator()
    base_simulation = simulator.run(base_plan, base_policy)
    changed_simulation = simulator.run(base_plan, changed_policy)
    assert base_simulation.simulation_run_id != changed_simulation.simulation_run_id

    manifest = build_manifest(base_plan, base_policy)
    report = EvaluationRunner().evaluate(
        manifest, run_benchmark_view(base_plan, base_policy), track=EvaluationTrack.CONTROLLED_NOISE
    )
    changed_manifest = update_manifest(
        manifest,
        metric_names=("controlled_observation_recall",),
    )
    changed_report = EvaluationRunner().evaluate(
        changed_manifest,
        run_benchmark_view(base_plan, base_policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    assert report.evaluation_run_id != changed_report.evaluation_run_id


@pytest.mark.parametrize(
    ("simulation_updates", "manifest_updates"),
    (
        ({"random_seed": 42}, {"random_seed": 42}),
        (
            {"start_time": datetime(2026, 8, 13, 1, tzinfo=UTC)},
            {},
        ),
        (
            {"primary_target_object_id": uid(4)},
            {"primary_target_object_id": uid(4)},
        ),
    ),
)
def test_simulation_run_id_rejects_self_consistent_projected_input_tampering(
    simulation_updates,
    manifest_updates,
):
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    tampered = rehash_simulation(simulation, **simulation_updates)
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=tampered.simulation_content_sha256,
        **manifest_updates,
    )

    with pytest.raises(ValueError, match="simulation run ID"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_simulation_run_id_rejects_self_consistent_scheduled_target_tampering():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    tampered_results = tuple(
        rebind_detection_result(
            result,
            detected_object_instance_id=(
                uid(5)
                if result.outcome == ObservationOutcome.DETECTED
                else result.detected_object_instance_id
            ),
        )
        for result in simulation.detection_results
    )
    tampered = rehash_simulation(
        simulation,
        scheduled_observation_object_id=uid(5),
        detection_results=tampered_results,
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        scheduled_observation_object_id=uid(5),
        expected_simulation_content_sha256=tampered.simulation_content_sha256,
    )

    with pytest.raises(ValueError, match="simulation run ID"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


@pytest.mark.parametrize(
    ("manifest_update", "simulation_update", "message"),
    (
        ({"duration_days": 4}, {}, "duration"),
        (
            {
                "budget": BenchmarkBudget(
                    max_selected_observation_actions=0,
                    max_selected_verifications=0,
                )
            },
            {},
            "selected observation action budget",
        ),
        ({}, {"ground_truth": "mismatched"}, "ground-truth simulation run ID"),
        ({"observation_policy_id": "other-policy"}, {}, "policy ID"),
        (
            {"scheduled_observation_object_id": uid(5)},
            {},
            "scheduled observation object",
        ),
        ({"manifest_version": "9.9.9"}, {}, "manifest version"),
    ),
)
def test_evaluator_rejects_incomplete_manifest_bindings(
    manifest_update, simulation_update, message
):
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    manifest = update_manifest(build_manifest(plan, policy), **manifest_update)
    if simulation_update.get("ground_truth") == "mismatched":
        view = rehash_benchmark_view(
            view,
            ground_truth=view.ground_truth.model_copy(update={"simulation_run_id": uuid4()}),
        )
        simulation_update = {}
    if simulation_update:
        simulation = rehash_simulation(simulation, **simulation_update)
        view = view_with_visible_result(plan, policy, simulation)

    with pytest.raises(ValueError, match=message):
        EvaluationRunner().evaluate(manifest, view, track=EvaluationTrack.CONTROLLED_NOISE)


def test_duplicate_detection_from_a_low_recall_run_is_rejected():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    manifest = build_manifest(plan, policy)
    ambiguous_results = tuple(
        rebind_detection_result(
            result,
            outcome=ObservationOutcome.AMBIGUOUS,
            detected_object_instance_id=None,
            detected_location_id=None,
            detection_time=None,
        )
        for result in simulation.detection_results[1:]
    )
    low_recall = rehash_simulation(
        simulation,
        detection_results=(simulation.detection_results[0], *ambiguous_results),
    )
    manifest = update_manifest(
        manifest,
        expected_simulation_content_sha256=low_recall.simulation_content_sha256,
    )
    low_recall_view = view_with_visible_result(plan, policy, low_recall)
    report = EvaluationRunner().evaluate(
        manifest, low_recall_view, track=EvaluationTrack.CONTROLLED_NOISE
    )
    assert report.metric_value("controlled_observation_recall") == pytest.approx(1 / 3)

    duplicate = rebind_detection_result(
        low_recall.detection_results[0],
        metadata=low_recall.detection_results[0].metadata.model_copy(
            update={"source_id": "adversarial-duplicate"}
        ),
    )
    duplicated = rehash_simulation(
        low_recall,
        detection_results=(*low_recall.detection_results, duplicate),
    )

    with pytest.raises(ValueError, match="multiple detection results"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, duplicated),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_recall_with_no_anomaly_truth_is_undefined():
    config = build_routine_config().model_copy(update={"changes": ()})
    plan = SyntheticRoutineGenerator().generate(config)
    policy = build_policy()
    manifest = build_manifest(plan, policy)

    report = EvaluationRunner().evaluate(
        manifest, run_benchmark_view(plan, policy), track=EvaluationTrack.CONTROLLED_NOISE
    )
    metric = next(
        item for item in report.metrics if item.metric_name == "anomaly_observation_recall"
    )
    assert metric.value is None
    assert metric.sample_count == 0


def test_evaluator_rejects_a_verification_over_budget():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    manifest = update_manifest(
        build_manifest(plan, policy),
        budget=BenchmarkBudget(
            max_selected_observation_actions=20,
            max_selected_verifications=0,
        ),
    )
    opportunity = simulation.observation_opportunities[0]
    context = opportunity.incidental_context.model_copy(
        update={"observation_mode": ObservationMode.MICRO_VERIFY}
    )
    opportunity = opportunity.model_copy(update={"incidental_context": context})
    simulation = rehash_simulation(
        simulation,
        observation_opportunities=(
            opportunity,
            *simulation.observation_opportunities[1:],
        ),
    )
    manifest = update_manifest(
        manifest,
        expected_simulation_content_sha256=simulation.simulation_content_sha256,
    )

    with pytest.raises(ValueError, match="selected verification budget"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, simulation),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_unselected_verification_does_not_consume_selected_budgets():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy(selection_probability=0.5)
    simulation = SymbolicWorldModelSimulator().run(plan, policy)

    opportunities = []
    for opportunity in simulation.observation_opportunities:
        context = opportunity.incidental_context.model_copy(
            update={"observation_mode": ObservationMode.MICRO_VERIFY}
        )
        opportunities.append(
            opportunity.model_copy(update={"incidental_context": context, "selected": False})
        )
    results = tuple(
        rebind_detection_result(
            result,
            outcome=ObservationOutcome.NOT_OBSERVED,
            detected_object_instance_id=None,
            detected_location_id=None,
            detection_time=None,
            negative_evidence_strength=0.0,
        )
        for result in simulation.detection_results
    )
    simulation = rehash_simulation(
        simulation,
        observation_opportunities=tuple(opportunities),
        detection_results=results,
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=simulation.simulation_content_sha256,
        budget=BenchmarkBudget(
            max_selected_observation_actions=0,
            max_selected_verifications=0,
        ),
    )

    EvaluationRunner().evaluate(
        manifest,
        view_with_visible_result(plan, policy, simulation),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )


def test_declared_action_cost_counts_only_selected_observation_actions():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy(selection_probability=0.5, additional_action_cost=2.0)
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    opportunities = tuple(
        opportunity.model_copy(update={"selected": index != 1})
        for index, opportunity in enumerate(simulation.observation_opportunities)
    )
    results = tuple(
        rebind_detection_result(
            result,
            outcome=(
                ObservationOutcome.NOT_OBSERVED if index == 1 else ObservationOutcome.DETECTED
            ),
            detected_object_instance_id=(
                None if index == 1 else policy.scheduled_observation_object_id
            ),
            detected_location_id=(
                None
                if index == 1
                else view.ground_truth.events[index].destination_location_gt_entity_id
            ),
            detection_time=(None if index == 1 else opportunities[index].opportunity_time),
            negative_evidence_strength=0.0,
        )
        for index, result in enumerate(simulation.detection_results)
    )
    simulation = rehash_simulation(
        simulation,
        observation_opportunities=opportunities,
        detection_results=results,
    )
    selected_count = sum(item.selected for item in opportunities)
    assert selected_count == 2
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=simulation.simulation_content_sha256,
    )

    report = EvaluationRunner().evaluate(
        manifest,
        view_with_visible_result(plan, policy, simulation),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    metric = next(
        item
        for item in report.metrics
        if item.metric_name == "declared_primary_task_additional_action_cost_total"
    )

    assert metric.value == 4.0
    assert metric.sample_count == 2
    with pytest.raises(KeyError):
        report.metric_value("primary_task_additional_action_cost")


def test_evaluator_rejects_truncated_results_by_content_hash():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    truncated = simulation.model_copy(
        update={"detection_results": simulation.detection_results[:-1]}
    )

    with pytest.raises(
        ValueError,
        match=r"simulation content hash|every observation opportunity requires",
    ):
        EvaluationRunner().evaluate(
            manifest,
            rehash_benchmark_view(
                run_benchmark_view(plan, policy),
                visible_updates={"detection_results": truncated.detection_results},
            ),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_evaluator_requires_one_result_per_opportunity_after_rehash():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    truncated = rehash_simulation(
        simulation,
        detection_results=simulation.detection_results[:-1],
    )

    with pytest.raises(ValueError, match="exactly one result"):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, truncated),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_evaluator_rejects_ground_truth_tampering_by_content_hash():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    view = run_benchmark_view(plan, policy)
    first_truth = view.ground_truth.events[0].model_copy(
        update={"destination_location_gt_entity_id": uid(7)}
    )
    tampered_truth = view.ground_truth.model_copy(
        update={"events": (first_truth, *view.ground_truth.events[1:])}
    )
    tampered = view.model_copy(update={"ground_truth": tampered_truth})

    with pytest.raises(ValueError, match=r"privileged (?:simulation )?content hash"):
        EvaluationRunner().evaluate(
            manifest,
            tampered,
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_manifest_rejects_self_consistent_tampered_simulation_hash():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    first_chain_id = view.ground_truth.interaction_events[0].event_chain_id
    truncated = rehash_benchmark_view(
        view,
        visible_updates={
            "observation_opportunities": simulation.observation_opportunities[:1],
            "detection_results": simulation.detection_results[:1],
        },
        ground_truth=view.ground_truth.model_copy(
            update={
                "events": view.ground_truth.events[:1],
                "interaction_events": tuple(
                    event
                    for event in view.ground_truth.interaction_events
                    if event.event_chain_id == first_chain_id
                ),
            }
        ),
    )

    with pytest.raises(ValueError, match="does not match benchmark manifest"):
        EvaluationRunner().evaluate(manifest, truncated, track=EvaluationTrack.CONTROLLED_NOISE)


def test_evaluator_revalidates_ground_truth_after_model_copy():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    view = run_benchmark_view(plan, policy)
    duplicate_id_event = view.ground_truth.events[1].model_copy(
        update={"gt_event_id": view.ground_truth.events[0].gt_event_id}
    )
    invalid_truth = view.ground_truth.model_copy(
        update={
            "events": (
                view.ground_truth.events[0],
                duplicate_id_event,
                *view.ground_truth.events[2:],
            )
        }
    )
    tampered = rehash_benchmark_view(view, ground_truth=invalid_truth)

    with pytest.raises(ValueError, match="ground-truth habit event ids"):
        EvaluationRunner().evaluate(manifest, tampered, track=EvaluationTrack.CONTROLLED_NOISE)


def test_evaluator_revalidates_duplicate_manifest_metrics_after_model_copy():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    duplicated = manifest.model_copy(
        update={"metric_names": (*manifest.metric_names, "controlled_observation_recall")}
    )

    with pytest.raises(ValueError, match="metric_names must not contain duplicates"):
        EvaluationRunner().evaluate(
            duplicated, run_benchmark_view(plan, policy), track=EvaluationTrack.CONTROLLED_NOISE
        )


@pytest.mark.parametrize(
    ("binding", "message"),
    (
        ("household_id", "household IDs do not match"),
        ("session_id", "session IDs do not match"),
        ("trace_id", "trace IDs do not match"),
        ("metadata_time", "result metadata time does not match"),
        ("detection_time", "detection time does not match"),
    ),
)
def test_evaluator_rejects_cross_context_or_time_detection_results(binding, message):
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    simulation = SymbolicWorldModelSimulator().run(plan, policy)
    result = simulation.detection_results[0]
    if binding == "household_id":
        result = result.model_copy(
            update={"metadata": result.metadata.model_copy(update={"household_id": uid(99)})}
        )
    elif binding == "session_id":
        result = result.model_copy(
            update={"metadata": result.metadata.model_copy(update={"session_id": uuid4()})}
        )
    elif binding == "trace_id":
        result = result.model_copy(
            update={"metadata": result.metadata.model_copy(update={"trace_id": uuid4()})}
        )
    elif binding == "metadata_time":
        result = result.model_copy(
            update={
                "metadata": result.metadata.model_copy(
                    update={"recorded_time": result.metadata.recorded_time + timedelta(seconds=1)}
                )
            }
        )
    else:
        result = result.model_copy(
            update={"detection_time": result.detection_time + timedelta(seconds=1)}
        )
    result = rebind_detection_result(result)
    tampered = rehash_simulation(
        simulation,
        detection_results=(result, *simulation.detection_results[1:]),
    )

    with pytest.raises(ValueError, match=message):
        EvaluationRunner().evaluate(
            manifest,
            view_with_visible_result(plan, policy, tampered),
            track=EvaluationTrack.CONTROLLED_NOISE,
        )


def test_leakage_detector_finds_exact_gt_event_reference_with_self_consistent_inputs():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    gt_event_id = view.ground_truth.events[0].gt_event_id
    original = simulation.detection_results[0]
    leaking = original.model_copy(
        update={
            # Sensor evidence references are legal contract values; it is the
            # evaluator's responsibility to identify a privileged GT link.
            "metadata": original.metadata.model_copy(update={"source_type": SourceType.SENSOR}),
            "evidence_refs": (
                EvidenceRef(
                    evidence_type="sensor-frame",
                    source_record_id=gt_event_id,
                    locator=f"frame:12/gt_event/{gt_event_id}",
                ),
            ),
        }
    )
    leaking = rebind_detection_result(leaking)
    leaking_simulation = rehash_simulation(
        simulation,
        detection_results=(leaking, *simulation.detection_results[1:]),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(leaking_simulation.simulation_content_sha256),
    )

    report = EvaluationRunner().evaluate(
        manifest,
        view_with_visible_result(plan, policy, leaking_simulation),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )

    assert report.ground_truth_leakage_detected
    assert any("value references a gt_event_id" in reason for reason in report.failure_reasons)
    assert any(
        "detection_results[0].evidence_refs[0]" in reason for reason in report.failure_reasons
    )


def test_leakage_detector_scans_metadata_string_carriers():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    gt_event_id = view.ground_truth.events[0].gt_event_id
    original = simulation.detection_results[0]
    leaking = original.model_copy(
        update={
            "metadata": original.metadata.model_copy(
                update={"source_id": f"gt_event:{gt_event_id}"}
            )
        }
    )
    leaking = rebind_detection_result(leaking)
    leaking_simulation = rehash_simulation(
        simulation,
        detection_results=(leaking, *simulation.detection_results[1:]),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(leaking_simulation.simulation_content_sha256),
    )

    report = EvaluationRunner().evaluate(
        manifest,
        view_with_visible_result(plan, policy, leaking_simulation),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )

    assert report.ground_truth_leakage_detected
    assert any(
        "detection_results[0].metadata.source_id" in reason and "privileged ground truth" in reason
        for reason in report.failure_reasons
    )


def test_leakage_detector_recognizes_compact_gt_event_uuid_encoding():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    gt_event_id = view.ground_truth.events[0].gt_event_id
    original = simulation.detection_results[0]
    leaking = rebind_detection_result(
        original.model_copy(
            update={
                "metadata": original.metadata.model_copy(
                    update={
                        "source_type": SourceType.SENSOR,
                        "source_id": f"sensor-frame:{gt_event_id.hex}",
                    }
                )
            }
        )
    )
    leaking_simulation = rehash_simulation(
        simulation,
        detection_results=(leaking, *simulation.detection_results[1:]),
    )
    manifest = update_manifest(
        build_manifest(plan, policy),
        expected_simulation_content_sha256=(leaking_simulation.simulation_content_sha256),
    )

    report = EvaluationRunner().evaluate(
        manifest,
        view_with_visible_result(plan, policy, leaking_simulation),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )

    assert report.ground_truth_leakage_detected
    assert any(
        "metadata.source_id" in reason and "embeds a gt_event_id" in reason
        for reason in report.failure_reasons
    )


def test_leakage_detector_scans_visible_result_top_level_carriers():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    gt_event_id = plan.events[0].event_id
    policy = build_policy(policy_id=f"policy:{gt_event_id.hex}")
    view = run_benchmark_view(plan, policy)

    report = EvaluationRunner().evaluate(
        build_manifest(plan, policy),
        view,
        track=EvaluationTrack.CONTROLLED_NOISE,
    )

    assert report.ground_truth_leakage_detected
    assert any(
        "visible_result.observation_policy_id" in reason and "embeds a gt_event_id" in reason
        for reason in report.failure_reasons
    )


def test_recall_matching_maximizes_cardinality_instead_of_greedy_latest_truth():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    simulation = view.visible_result
    start = simulation.start_time
    truth_template = view.ground_truth.events[0]
    truth = (
        truth_template.model_copy(update={"gt_event_id": uid(101), "event_time": start}),
        truth_template.model_copy(
            update={"gt_event_id": uid(102), "event_time": start + timedelta(hours=9)}
        ),
    )
    detection_template = simulation.detection_results[0]
    detections = [
        detection_template.model_copy(
            update={
                "metadata": detection_template.metadata.model_copy(update={"record_id": uid(201)}),
                "detection_time": start + timedelta(hours=10),
            }
        ),
        detection_template.model_copy(
            update={
                "metadata": detection_template.metadata.model_copy(update={"record_id": uid(202)}),
                "detection_time": start + timedelta(hours=11),
            }
        ),
    ]

    matched = EvaluationRunner._match_unique_truth_events(
        detections,
        truth,
        maximum_delay=timedelta(hours=10),
    )

    assert matched == {uid(101), uid(102)}


def test_evaluation_report_self_hash_rejects_round_trip_mutation():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    manifest = build_manifest(plan, policy)
    report = EvaluationRunner().evaluate(
        manifest,
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    report_type = type(report)

    assert report_type.model_validate(report.model_dump(mode="python")) == report
    tampered = report.model_copy(update={"observation_policy_id": "tampered-policy"})
    with pytest.raises(ValidationError, match="evaluation_report_sha256"):
        report_type.model_validate(tampered.model_dump(mode="python"))


def rehash_evaluation_report(report, **updates):
    mutated = report.model_copy(update=updates)
    return mutated.model_copy(
        update={"evaluation_report_sha256": content_sha256(mutated.content_payload())}
    )


def test_evaluation_report_rejects_self_consistent_run_identity_tampering():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    report = EvaluationRunner().evaluate(
        build_manifest(plan, policy),
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    forged_run_id = uid(999)
    forged_metrics = tuple(
        metric.model_copy(
            update={
                "evaluation_run_id": forged_run_id,
                "metric_id": content_uuid(
                    "metric",
                    {
                        "evaluation_run_id": forged_run_id,
                        "name": metric.metric_name,
                    },
                ),
            }
        )
        for metric in report.metrics
    )
    forged = rehash_evaluation_report(
        report,
        evaluation_run_id=forged_run_id,
        metrics=forged_metrics,
    )

    with pytest.raises(ValidationError, match="evaluation_run_id"):
        EvaluationReport.model_validate(forged.model_dump(mode="python"))


def test_evaluation_report_rejects_metric_binding_and_duplicate_names():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    report = EvaluationRunner().evaluate(
        build_manifest(plan, policy),
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    wrong_run_metric = report.metrics[0].model_copy(update={"simulation_run_id": uid(777)})
    wrong_binding = rehash_evaluation_report(
        report,
        metrics=(wrong_run_metric, *report.metrics[1:]),
    )
    duplicate = rehash_evaluation_report(
        report,
        metrics=(report.metrics[0], report.metrics[0], *report.metrics[1:]),
    )

    with pytest.raises(ValidationError, match="simulation_run_id"):
        EvaluationReport.model_validate(wrong_binding.model_dump(mode="python"))
    with pytest.raises(ValidationError, match="metric names must be unique"):
        EvaluationReport.model_validate(duplicate.model_dump(mode="python"))


@pytest.mark.parametrize(
    ("value", "sample_count", "message"),
    (
        (2.0, 3, r"\[0, 1\]"),
        (1.0, 0, "undefined"),
        (None, 3, r"\[0, 1\]"),
    ),
)
def test_evaluation_report_rejects_invalid_recall_semantics(
    value,
    sample_count,
    message,
):
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    report = EvaluationRunner().evaluate(
        build_manifest(plan, policy),
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    invalid_metric = report.metrics[0].model_copy(
        update={"value": value, "sample_count": sample_count}
    )
    invalid_report = rehash_evaluation_report(
        report,
        metrics=(invalid_metric, *report.metrics[1:]),
    )

    with pytest.raises(ValidationError, match=message):
        EvaluationReport.model_validate(invalid_report.model_dump(mode="python"))


@pytest.mark.parametrize(
    "change_kind",
    (
        RoutineChangeKind.PERIODIC_CONTEXT,
        RoutineChangeKind.GRADUAL_DRIFT,
        RoutineChangeKind.ABRUPT_CHANGE,
    ),
)
def test_contextual_or_persistent_change_is_not_scored_as_anomaly(change_kind):
    config = build_routine_config()
    change = config.changes[0].model_copy(update={"kind": change_kind})
    plan = SyntheticRoutineGenerator().generate(config.model_copy(update={"changes": (change,)}))
    policy = build_policy()
    manifest = build_manifest(plan, policy)

    report = EvaluationRunner().evaluate(
        manifest,
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    anomaly_metric = next(
        metric for metric in report.metrics if metric.metric_name == "anomaly_observation_recall"
    )

    assert anomaly_metric.value is None
    assert anomaly_metric.sample_count == 0


def test_zero_field_of_view_coverage_never_emits_a_detection():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy(field_of_view_coverage=0.0)

    visible = SymbolicWorldModelSimulator().run(plan, policy)

    assert visible.observation_opportunities
    assert all(
        result.outcome != ObservationOutcome.DETECTED for result in visible.detection_results
    )
    assert all(
        opportunity.p_visible_given_state == 0.0
        for opportunity in visible.observation_opportunities
    )


def test_camera_frustum_excludes_target_outside_primary_task_view():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    away_pose = RobotPose(
        frame_id="household_map",
        x_m=0.0,
        y_m=0.0,
        z_m=1.0,
        yaw_degrees=180.0,
    )
    policy = build_policy(
        robot_task_trajectory=tuple(
            sample.model_copy(update={"pose": away_pose})
            for sample in build_policy().robot_task_trajectory
        )
    )

    visible = SymbolicWorldModelSimulator().run(plan, policy)

    assert all(
        result.outcome != ObservationOutcome.DETECTED for result in visible.detection_results
    )


def test_vertical_camera_frustum_does_not_apply_undefined_azimuth():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    upward_sample = RobotTaskTrajectorySample(
        sample_time=build_policy().robot_task_trajectory[0].sample_time,
        pose=RobotPose(
            frame_id="household_map",
            x_m=0.0,
            y_m=0.0,
            z_m=0.0,
            yaw_degrees=180.0,
            pitch_degrees=90.0,
        ),
        camera_frustum=CameraFrustum(
            horizontal_fov_degrees=1.0,
            vertical_fov_degrees=1.0,
            max_range_m=3.0,
        ),
    )
    policy = build_policy(
        robot_task_trajectory=(upward_sample,),
        location_geometry=(
            LocationGeometry(
                location_id=uid(6),
                frame_id="household_map",
                x_m=0.0,
                y_m=0.0,
                z_m=2.0,
            ),
            build_policy().location_geometry[1],
        ),
    )

    visible = SymbolicWorldModelSimulator().run(plan, policy)

    assert visible.detection_results[0].outcome == ObservationOutcome.DETECTED


def test_public_simulator_api_requires_explicit_capability_for_truth():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    simulator = SymbolicWorldModelSimulator()

    visible = simulator.run(plan, policy)
    assert "ground_truth" not in visible.model_dump(mode="python")

    with pytest.raises(PermissionError, match="capability"):
        simulator.run_privileged(plan, policy, capability=object())

    import cpswm.system.world_model_simulator as public_api

    assert not hasattr(public_api, "PrivilegedSymbolicSimulationView")
    assert not hasattr(public_api, "issue_benchmark_ground_truth_capability")


def test_simulator_revalidates_model_copy_inputs_before_execution():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    simulator = SymbolicWorldModelSimulator()

    invalid_probability = build_policy().model_copy(update={"field_of_view_coverage": 2.0})
    with pytest.raises(ValueError, match="invalid simulator input"):
        simulator.run(plan, invalid_probability)

    injected_truth = build_policy().model_copy(
        update={"ground_truth_event_count": len(plan.events)}
    )
    with pytest.raises(ValueError, match="unexpected field"):
        simulator.run(plan, injected_truth)


def test_evaluator_rejects_mislabeled_visible_record_schema():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    view = run_benchmark_view(plan, policy)
    original = view.visible_result.detection_results[0]
    mislabeled = rebind_detection_result(
        original,
        metadata=original.metadata.model_copy(
            update={
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "schema_version": "9.9.9",
            }
        ),
    )
    results = (mislabeled, *view.visible_result.detection_results[1:])
    tampered = rehash_benchmark_view(
        view,
        visible_updates={"detection_results": results},
    )

    with pytest.raises(ValueError, match="metadata schema"):
        EvaluationRunner().evaluate(
            build_manifest(plan, policy),
            tampered,
            track=EvaluationTrack.CONTROLLED_NOISE,
        )
