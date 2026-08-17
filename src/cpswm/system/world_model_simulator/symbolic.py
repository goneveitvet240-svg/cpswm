"""Reproducible M29-L0 truth execution and robot-visible observation projection."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from math import atan2, degrees, hypot
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from cpswm.contracts import (
    BaseRecordMetadata,
    IncidentalObservationContext,
    ObservationDetectionResult,
    ObservationMode,
    ObservationOpportunityRecord,
    OcclusionState,
    SourceType,
)
from cpswm.contracts.base import ContractModel, Probability, require_aware
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.synthetic_routines import RoutineChangeKind, RoutinePlan
from cpswm_gt import (
    GroundTruthHabitTrajectory,
    GTHabitRegimeKind,
    GTPlacementEvent,
)
from simobs import SelectiveObservationSample, simulate_location_observation

from .benchmark_access import (
    BenchmarkGroundTruthCapability,
    require_benchmark_ground_truth_capability,
)


def _stable_uuid(*parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, "cpswm:" + ":".join(str(part) for part in parts))


def _reject_live_model_extras(value: object, path: str) -> None:
    """Reject fields injected into an already-built Pydantic model.

    ``model_copy(update=...)`` deliberately skips validation.  A simulator
    entry point is therefore a contract boundary, not merely a type hint.
    """

    if isinstance(value, BaseModel):
        declared_fields = set(type(value).model_fields)
        live_fields = set(vars(value))
        pydantic_extras = getattr(value, "__pydantic_extra__", None) or {}
        unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
        if unexpected_fields:
            names = ", ".join(sorted(unexpected_fields))
            raise ValueError(f"{path} contains unexpected field(s): {names}")
        for field_name in declared_fields:
            _reject_live_model_extras(getattr(value, field_name), f"{path}.{field_name}")
    elif isinstance(value, dict):
        for key, nested in value.items():
            _reject_live_model_extras(nested, f"{path}[{key!r}]")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_live_model_extras(nested, f"{path}[{index}]")


def detection_result_record_id(result: ObservationDetectionResult) -> UUID:
    """Bind a simulated detection record ID to its complete realized content.

    ``metadata.record_id`` is excluded to avoid a circular hash. Every other
    metadata and result field is included, so two different realized outcomes
    cannot silently reuse the same record identity.
    """

    payload = result.model_dump(mode="json")
    payload["metadata"].pop("record_id")
    return content_uuid("detection-result", payload)


def simulation_run_identity(
    *,
    observation_policy_id: str,
    observation_policy_sha256: str,
    simulator_version: str,
    start_time: datetime,
    duration_days: int,
    random_seed: int,
    primary_target_object_id: UUID,
    scheduled_observation_object_id: UUID,
    initial_target_location_id: UUID,
) -> UUID:
    """Return a public run ID independent of a hidden future schedule."""

    return content_uuid(
        "simulation-run",
        {
            "observation_policy_id": observation_policy_id,
            "observation_policy_sha256": observation_policy_sha256,
            "simulator_version": simulator_version,
            "start_time": start_time,
            "duration_days": duration_days,
            "random_seed": random_seed,
            "primary_target_object_id": primary_target_object_id,
            "scheduled_observation_object_id": scheduled_observation_object_id,
            # Initial world state is observable environment input; future plan
            # events and their cardinality are deliberately excluded.
            "initial_target_location_id": initial_target_location_id,
        },
    )


class RobotPose(ContractModel):
    """Robot camera pose on the primary-task trajectory."""

    frame_id: str = Field(min_length=1)
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_degrees: float = Field(ge=-180.0, le=180.0)
    pitch_degrees: float = Field(default=0.0, ge=-90.0, le=90.0)


class CameraFrustum(ContractModel):
    """Finite pinhole-style field of view used at one trajectory sample."""

    horizontal_fov_degrees: float = Field(gt=0.0, le=360.0)
    vertical_fov_degrees: float = Field(gt=0.0, le=180.0)
    max_range_m: float = Field(gt=0.0)


class RobotTaskTrajectorySample(ContractModel):
    """One robot pose and camera frustum emitted by the primary task."""

    sample_time: datetime
    pose: RobotPose
    camera_frustum: CameraFrustum

    @field_validator("sample_time")
    @classmethod
    def validate_sample_time(cls, value: datetime) -> datetime:
        return require_aware(value, "sample_time")


class LocationGeometry(ContractModel):
    """Public map point used for geometric frustum intersection."""

    location_id: UUID
    frame_id: str = Field(min_length=1)
    x_m: float
    y_m: float
    z_m: float = 0.0


class IncidentalObservationPolicy(ContractModel):
    policy_id: str = Field(min_length=1)
    primary_task_id: UUID
    primary_task_goal: str = Field(min_length=1)
    primary_target_object_id: UUID
    scheduled_observation_object_id: UUID
    selection_probability: float = Field(gt=0.0, le=1.0)
    field_of_view_coverage: Probability
    p_visible_given_state: Probability
    p_detect_given_visible: Probability
    occlusion_state: OcclusionState = OcclusionState.CLEAR
    additional_action_cost: float = Field(default=0.0, ge=0.0)
    frame_id: str = Field(default="household_map", min_length=1)
    likelihood_model_id: str = Field(default="controlled-noise@0.1", min_length=1)
    minimum_verification_strength: float = Field(default=0.5, gt=0.0, le=1.0)
    robot_task_trajectory: tuple[RobotTaskTrajectorySample, ...] = Field(min_length=1)
    location_geometry: tuple[LocationGeometry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_visibility(self) -> IncidentalObservationPolicy:
        if self.occlusion_state == OcclusionState.FULL and self.p_visible_given_state > 0:
            raise ValueError("full occlusion requires zero visibility probability")
        sample_times = [sample.sample_time for sample in self.robot_task_trajectory]
        if sample_times != sorted(sample_times) or len(sample_times) != len(set(sample_times)):
            raise ValueError("robot task trajectory samples must have unique chronological times")
        location_ids = [item.location_id for item in self.location_geometry]
        if len(location_ids) != len(set(location_ids)):
            raise ValueError("location geometry must define each location once")
        if any(
            sample.pose.frame_id != self.frame_id for sample in self.robot_task_trajectory
        ) or any(item.frame_id != self.frame_id for item in self.location_geometry):
            raise ValueError("trajectory and location geometry must use policy frame_id")
        return self


class SymbolicSimulationResult(ContractModel):
    simulation_run_id: UUID
    simulation_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_policy_id: str = Field(min_length=1)
    observation_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_target_object_id: UUID
    scheduled_observation_object_id: UUID
    initial_target_location_id: UUID
    simulator_version: str = Field(min_length=1)
    start_time: datetime
    duration_days: int = Field(gt=0)
    random_seed: int = Field(ge=0)
    observation_opportunities: tuple[ObservationOpportunityRecord, ...]
    detection_results: tuple[ObservationDetectionResult, ...]

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_content_and_output_bindings(self) -> SymbolicSimulationResult:
        expected_hash = content_sha256(self.content_payload())
        if self.simulation_content_sha256 != expected_hash:
            raise ValueError("simulation_content_sha256 does not match simulation content")
        expected_run_id = simulation_run_identity(
            observation_policy_id=self.observation_policy_id,
            observation_policy_sha256=self.observation_policy_sha256,
            simulator_version=self.simulator_version,
            start_time=self.start_time,
            duration_days=self.duration_days,
            random_seed=self.random_seed,
            primary_target_object_id=self.primary_target_object_id,
            scheduled_observation_object_id=self.scheduled_observation_object_id,
            initial_target_location_id=self.initial_target_location_id,
        )
        if self.simulation_run_id != expected_run_id:
            raise ValueError("simulation run ID does not match public inputs")
        opportunities = self.observation_opportunities
        results = self.detection_results
        opportunity_ids = [item.metadata.record_id for item in opportunities]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("simulation contains duplicate observation opportunities")
        result_ids = [item.metadata.record_id for item in results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("simulation contains duplicate detection result IDs")

        result_opportunity_ids = [item.observation_opportunity_id for item in results]
        if len(result_opportunity_ids) != len(set(result_opportunity_ids)):
            raise ValueError("one opportunity cannot have multiple detection results")
        if set(result_opportunity_ids) != set(opportunity_ids):
            raise ValueError("every observation opportunity requires exactly one result")

        opportunity_by_id = {item.metadata.record_id: item for item in opportunities}
        for opportunity in opportunities:
            if (
                opportunity.metadata.schema_name != "cpswm.ObservationOpportunityRecord"
                or opportunity.metadata.schema_version != "0.1.0"
            ):
                raise ValueError("opportunity metadata schema does not match its contract")
        for result in results:
            opportunity = opportunity_by_id[result.observation_opportunity_id]
            if (
                result.metadata.schema_name != "cpswm.ObservationDetectionResult"
                or result.metadata.schema_version != "0.1.0"
            ):
                raise ValueError("result metadata schema does not match its contract")
            if result.metadata.record_id != detection_result_record_id(result):
                raise ValueError("detection result record ID does not match realized content")
            if result.metadata.household_id != opportunity.metadata.household_id:
                raise ValueError("result and opportunity household IDs do not match")
            if result.metadata.session_id != opportunity.metadata.session_id:
                raise ValueError("result and opportunity session IDs do not match")
            if result.metadata.trace_id != opportunity.metadata.trace_id:
                raise ValueError("result and opportunity trace IDs do not match")
            if opportunity.metadata.recorded_time != opportunity.opportunity_time:
                raise ValueError("opportunity metadata time does not match opportunity time")
            if result.metadata.recorded_time != opportunity.opportunity_time:
                raise ValueError("result metadata time does not match opportunity time")
            if (
                result.detection_time is not None
                and result.detection_time != opportunity.opportunity_time
            ):
                raise ValueError("detection time does not match opportunity time")
            if not opportunity.selected and result.outcome != "not_observed":
                raise ValueError("unselected observation action requires a not_observed result")
            if opportunity.selected and result.outcome == "not_observed":
                raise ValueError("selected observation action cannot have a not_observed result")
            if (
                result.detected_object_instance_id is not None
                and result.detected_object_instance_id != self.scheduled_observation_object_id
            ):
                raise ValueError("detected object does not match scheduled observation object")
        if any(
            opportunity.incidental_context is not None
            and opportunity.incidental_context.candidate_entity_ids
            for opportunity in opportunities
        ):
            raise ValueError("observation opportunity must not expose candidate identities")
        return self

    def content_payload(self) -> dict:
        """Return every public run input/output field except the hash itself."""

        return self.model_dump(
            mode="json",
            exclude={"simulation_content_sha256"},
        )


class PrivilegedSymbolicSimulationView(ContractModel):
    """Evaluator-only pairing of a public run with its hidden trajectory.

    This type is intentionally not exported from the package ``__init__``.
    Creation additionally requires the nominal benchmark capability exposed by
    :mod:`cpswm.system.world_model_simulator.benchmark_access`.
    """

    visible_result: SymbolicSimulationResult
    routine_plan_id: UUID
    routine_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privileged_simulation_id: UUID
    privileged_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth: GroundTruthHabitTrajectory

    @model_validator(mode="after")
    def validate_binding(self) -> PrivilegedSymbolicSimulationView:
        if self.ground_truth.simulation_run_id != self.visible_result.simulation_run_id:
            raise ValueError("ground-truth simulation run ID does not match simulation")
        payload = self.content_payload()
        if self.privileged_content_sha256 != content_sha256(payload):
            raise ValueError("privileged content hash does not match view content")
        if self.privileged_simulation_id != content_uuid("privileged-simulation", payload):
            raise ValueError("privileged simulation ID does not match view content")
        return self

    def content_payload(self) -> dict:
        return self.model_dump(
            mode="json",
            exclude={"privileged_simulation_id", "privileged_content_sha256"},
        )


class SymbolicWorldModelSimulator:
    """Execute planned placements and expose only finite observation records."""

    _REGIME_MAP = {
        RoutineChangeKind.STATIONARY_ROUTINE: GTHabitRegimeKind.STABLE,
        RoutineChangeKind.PERIODIC_CONTEXT: GTHabitRegimeKind.CONTEXTUAL,
        RoutineChangeKind.ISOLATED_ANOMALY: GTHabitRegimeKind.TEMPORARY_EXCEPTION,
        RoutineChangeKind.TEMPORARY_EXCEPTION: GTHabitRegimeKind.TEMPORARY_EXCEPTION,
        RoutineChangeKind.GUEST_CONTAMINATION: GTHabitRegimeKind.TEMPORARY_EXCEPTION,
        RoutineChangeKind.GRADUAL_DRIFT: GTHabitRegimeKind.GRADUAL_CHANGE,
        RoutineChangeKind.ABRUPT_CHANGE: GTHabitRegimeKind.ABRUPT_CHANGE,
        RoutineChangeKind.HOUSEHOLD_TRANSITION: GTHabitRegimeKind.ABRUPT_CHANGE,
    }
    simulator_version = "symbolic-simulator@0.8"

    def run(
        self,
        plan: RoutinePlan,
        policy: IncidentalObservationPolicy,
    ) -> SymbolicSimulationResult:
        """Return only the robot-visible run for ordinary callers."""

        plan, policy = self._revalidate_inputs(plan, policy)
        policy_sha256 = content_sha256(policy)
        observation_stream_id = content_uuid(
            "observation-stream",
            {
                "household_id": plan.household_id,
                "start_time": plan.start_time,
                "duration_days": plan.duration_days,
                "random_seed": plan.random_seed,
                "observation_policy_sha256": policy_sha256,
                "simulator_version": self.simulator_version,
            },
        )
        visible = self._run_with_observation_stream(
            plan,
            policy,
            observation_stream_id=observation_stream_id,
        )
        return visible

    def run_privileged(
        self,
        plan: RoutinePlan,
        policy: IncidentalObservationPolicy,
        *,
        capability: BenchmarkGroundTruthCapability,
    ) -> PrivilegedSymbolicSimulationView:
        """Return a benchmark-only truth pairing after capability validation."""

        require_benchmark_ground_truth_capability(capability)
        plan, policy = self._revalidate_inputs(plan, policy)
        policy_sha256 = content_sha256(policy)
        observation_stream_id = content_uuid(
            "observation-stream",
            {
                "household_id": plan.household_id,
                "start_time": plan.start_time,
                "duration_days": plan.duration_days,
                "random_seed": plan.random_seed,
                "observation_policy_sha256": policy_sha256,
                "simulator_version": self.simulator_version,
            },
        )
        visible = self._run_with_observation_stream(
            plan,
            policy,
            observation_stream_id=observation_stream_id,
        )
        truth = self._ground_truth_for_plan(
            plan,
            simulation_run_id=visible.simulation_run_id,
            capability=capability,
        )
        payload = {
            "visible_result": visible,
            "routine_plan_id": plan.plan_id,
            "routine_plan_sha256": plan.content_sha256,
            "ground_truth": truth,
        }
        return PrivilegedSymbolicSimulationView(
            **payload,
            privileged_simulation_id=content_uuid("privileged-simulation", payload),
            privileged_content_sha256=content_sha256(payload),
        )

    def run_paired(
        self,
        plan: RoutinePlan,
        policies: tuple[IncidentalObservationPolicy, ...],
        *,
        paired_noise_seed: int,
    ) -> tuple[SymbolicSimulationResult, ...]:
        """Run policy potential outcomes against the same exogenous draws.

        ``paired_noise_seed`` is deliberately independent of each policy's
        content hash.  The same opportunity ``U_t`` and detection ``U_t`` are
        therefore reused across every policy, while each returned simulation
        remains bound to its own policy hash.  Policies must share the sensing
        clock and scheduled object so sequence numbers denote the same units.
        """

        if len(policies) < 2:
            raise ValueError("paired simulation requires at least two policies")
        if paired_noise_seed < 0:
            raise ValueError("paired_noise_seed must be non-negative")
        validated_policies: list[IncidentalObservationPolicy] = []
        validated_plan: RoutinePlan | None = None
        for policy in policies:
            candidate_plan, candidate_policy = self._revalidate_inputs(plan, policy)
            validated_plan = candidate_plan
            validated_policies.append(candidate_policy)
        assert validated_plan is not None
        plan = validated_plan
        policies = tuple(validated_policies)
        schedules = {self._paired_schedule_signature(plan, policy) for policy in policies}
        if len(schedules) != 1:
            raise ValueError(
                "paired policies must share the opportunity clock and scheduled object"
            )
        observation_stream_id = content_uuid(
            "paired-observation-stream",
            {
                "household_id": plan.household_id,
                "start_time": plan.start_time,
                "duration_days": plan.duration_days,
                "paired_noise_seed": paired_noise_seed,
                "schedule_signature": next(iter(schedules)),
                "simulator_version": self.simulator_version,
            },
        )
        return tuple(
            self._run_with_observation_stream(
                plan,
                policy,
                observation_stream_id=observation_stream_id,
            )
            for policy in policies
        )

    @staticmethod
    def _revalidate_inputs(
        plan: RoutinePlan,
        policy: IncidentalObservationPolicy,
    ) -> tuple[RoutinePlan, IncidentalObservationPolicy]:
        """Rebuild untrusted live models before using them to create outputs."""

        _reject_live_model_extras(plan, "routine plan")
        _reject_live_model_extras(policy, "observation policy")
        try:
            validated_plan = RoutinePlan.model_validate(
                plan.model_dump(mode="python", round_trip=True, warnings=False)
            )
            validated_policy = IncidentalObservationPolicy.model_validate(
                policy.model_dump(mode="python", round_trip=True, warnings=False)
            )
        except (AttributeError, TypeError, ValidationError) as error:
            raise ValueError(f"invalid simulator input: {error}") from error
        return validated_plan, validated_policy

    def _run_with_observation_stream(
        self,
        plan: RoutinePlan,
        policy: IncidentalObservationPolicy,
        *,
        observation_stream_id: UUID,
    ) -> SymbolicSimulationResult:
        policy_sha256 = content_sha256(policy)
        if policy.scheduled_observation_object_id not in plan.initial_object_locations:
            raise ValueError("scheduled observation object requires an explicit initial location")
        initial_target_location_id = plan.initial_object_locations[
            policy.scheduled_observation_object_id
        ]
        simulation_run_id = simulation_run_identity(
            observation_policy_id=policy.policy_id,
            observation_policy_sha256=policy_sha256,
            simulator_version=self.simulator_version,
            start_time=plan.start_time,
            duration_days=plan.duration_days,
            random_seed=plan.random_seed,
            primary_target_object_id=policy.primary_target_object_id,
            scheduled_observation_object_id=policy.scheduled_observation_object_id,
            initial_target_location_id=initial_target_location_id,
        )
        # The caller selects either a policy-bound stream (ordinary run) or an
        # explicitly paired exogenous stream (counterfactual policy comparison).
        session_id = _stable_uuid("simulation-session", observation_stream_id)
        trace_id = _stable_uuid("simulation-trace", observation_stream_id)
        rng = random.Random(int.from_bytes(observation_stream_id.bytes, "big"))

        opportunities: list[ObservationOpportunityRecord] = []
        detection_results: list[ObservationDetectionResult] = []
        location_geometry = {item.location_id: item for item in policy.location_geometry}
        target_object_id = policy.scheduled_observation_object_id
        if initial_target_location_id not in location_geometry:
            raise ValueError("location geometry must cover the public initial target location")

        run_end = plan.start_time + timedelta(days=plan.duration_days)
        for sequence_no, trajectory_sample in enumerate(policy.robot_task_trajectory):
            opportunity_time = trajectory_sample.sample_time
            if not plan.start_time <= opportunity_time < run_end:
                raise ValueError("robot task trajectory sample is outside simulation")
            opportunity_id = _stable_uuid(
                "observation-opportunity", observation_stream_id, sequence_no
            )
            opportunity_metadata = BaseRecordMetadata(
                record_id=opportunity_id,
                schema_name="cpswm.ObservationOpportunityRecord",
                schema_version="0.1.0",
                household_id=plan.household_id,
                session_id=session_id,
                recorded_time=opportunity_time,
                source_type=SourceType.SIMULATION,
                source_id="m29.symbolic-world-model-simulator",
                model_version=self.simulator_version,
                trace_id=trace_id,
            )
            context = IncidentalObservationContext(
                primary_task_id=policy.primary_task_id,
                primary_task_goal=policy.primary_task_goal,
                observation_mode=ObservationMode.INCIDENTAL,
                frame_id=policy.frame_id,
                candidate_entity_ids=(),
                field_of_view_coverage=policy.field_of_view_coverage,
                occlusion_state=policy.occlusion_state,
                additional_action_cost=policy.additional_action_cost,
                selection_probability=policy.selection_probability,
                observation_likelihood_model_id=policy.likelihood_model_id,
                observed_time=opportunity_time,
            )
            selected = rng.random() < policy.selection_probability
            realized_location_id = self._location_at(
                plan,
                policy.scheduled_observation_object_id,
                opportunity_time,
            )
            realized_geometry = location_geometry.get(realized_location_id)
            geometrically_visible = (
                realized_geometry is not None
                and self._location_in_camera_frustum(
                    trajectory_sample,
                    realized_geometry,
                )
            )
            # This is a calibrated property of the sensing opportunity, not a
            # report of the hidden realized target state. Geometry gates the
            # private ``target_present`` sample below. Encoding the realized
            # frustum intersection here would leak an undetected relocation.
            potential_visibility = policy.field_of_view_coverage * policy.p_visible_given_state
            opportunity = ObservationOpportunityRecord(
                metadata=opportunity_metadata,
                observation_action_id=_stable_uuid(
                    "observation-action", observation_stream_id, sequence_no
                ),
                opportunity_time=opportunity_time,
                selected=selected,
                selection_probability=policy.selection_probability,
                p_visible_given_state=potential_visibility,
                p_detect_given_visible=policy.p_detect_given_visible,
                likelihood_model_id=policy.likelihood_model_id,
                incidental_context=context,
            )
            opportunities.append(opportunity)
            result_metadata = opportunity_metadata.model_copy(
                update={
                    "record_id": _stable_uuid(
                        "detection-result", observation_stream_id, sequence_no
                    ),
                    "schema_name": "cpswm.ObservationDetectionResult",
                }
            )
            detection_result = simulate_location_observation(
                metadata=result_metadata,
                observation_opportunity=opportunity,
                sample=SelectiveObservationSample(
                    selected=selected,
                    target_present=(geometrically_visible and policy.field_of_view_coverage > 0.0),
                    detection_draw=rng.random(),
                ),
                detected_object_instance_id=(policy.scheduled_observation_object_id),
                detected_location_id=realized_location_id,
                minimum_verification_strength=policy.minimum_verification_strength,
            )
            detection_result = detection_result.model_copy(
                update={
                    "metadata": detection_result.metadata.model_copy(
                        update={"record_id": detection_result_record_id(detection_result)}
                    )
                }
            )
            detection_results.append(detection_result)

        result_payload = dict(
            simulation_run_id=simulation_run_id,
            observation_policy_id=policy.policy_id,
            observation_policy_sha256=policy_sha256,
            primary_target_object_id=policy.primary_target_object_id,
            scheduled_observation_object_id=policy.scheduled_observation_object_id,
            initial_target_location_id=initial_target_location_id,
            simulator_version=self.simulator_version,
            start_time=plan.start_time,
            duration_days=plan.duration_days,
            random_seed=plan.random_seed,
            observation_opportunities=tuple(opportunities),
            detection_results=tuple(detection_results),
        )
        visible = SymbolicSimulationResult(
            **result_payload,
            simulation_content_sha256=content_sha256(result_payload),
        )
        return visible

    def _ground_truth_for_plan(
        self,
        plan: RoutinePlan,
        *,
        simulation_run_id: UUID,
        capability: BenchmarkGroundTruthCapability,
    ) -> GroundTruthHabitTrajectory:
        """Materialize truth only on the explicitly capability-gated path."""

        require_benchmark_ground_truth_capability(capability)
        return GroundTruthHabitTrajectory(
            simulation_run_id=simulation_run_id,
            events=tuple(
                GTPlacementEvent(
                    gt_event_id=event.event_id,
                    event_time=event.event_time,
                    actor_gt_entity_id=event.actor_id,
                    object_gt_entity_id=event.object_instance_id,
                    source_location_gt_entity_id=event.source_location_id,
                    destination_location_gt_entity_id=event.destination_location_id,
                    context_key=event.context_key,
                    regime_id=event.regime_id,
                    regime_kind=self._REGIME_MAP[event.regime_kind],
                )
                for event in plan.events
                if event.destination_location_id is not None
            ),
        )

    @staticmethod
    def _paired_schedule_signature(
        plan: RoutinePlan,
        policy: IncidentalObservationPolicy,
    ) -> str:
        return content_sha256(
            {
                "scheduled_observation_object_id": policy.scheduled_observation_object_id,
                "robot_task_trajectory": policy.robot_task_trajectory,
                "location_geometry": policy.location_geometry,
            }
        )

    @staticmethod
    def _location_in_camera_frustum(
        sample: RobotTaskTrajectorySample,
        location: LocationGeometry,
    ) -> bool:
        """Return whether a map point intersects this camera frustum."""

        dx = location.x_m - sample.pose.x_m
        dy = location.y_m - sample.pose.y_m
        dz = location.z_m - sample.pose.z_m
        planar_distance = hypot(dx, dy)
        distance = hypot(planar_distance, dz)
        if distance > sample.camera_frustum.max_range_m:
            return False
        yaw_delta = (degrees(atan2(dy, dx)) - sample.pose.yaw_degrees + 180) % 360 - 180
        pitch = degrees(atan2(dz, planar_distance))
        pitch_delta = pitch - sample.pose.pitch_degrees
        # Azimuth is undefined directly above/below the camera. In that
        # degenerate direction only the vertical frustum constrains the point.
        horizontally_visible = (
            planar_distance <= 1e-12
            or abs(yaw_delta) <= sample.camera_frustum.horizontal_fov_degrees / 2
        )
        return (
            horizontally_visible
            and abs(pitch_delta) <= sample.camera_frustum.vertical_fov_degrees / 2
        )

    @staticmethod
    def _location_at(
        plan: RoutinePlan,
        object_instance_id: UUID,
        query_time: datetime,
    ) -> UUID:
        """Return object state using only the initial state and past events."""

        location_id = plan.initial_object_locations[object_instance_id]
        for event in plan.events:
            if event.event_time > query_time:
                break
            if (
                event.object_instance_id == object_instance_id
                and event.destination_location_id is not None
            ):
                location_id = event.destination_location_id
        return location_id
