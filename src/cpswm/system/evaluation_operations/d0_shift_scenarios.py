"""Reproducible paired scenarios for the D0 shift-cause death test.

The generator deliberately separates robot-visible inputs from evaluator-only
factor bindings.  Candidate methods receive :class:`D0ShiftCaseInput` only;
the true cause and latent-factor fingerprints live in
:class:`D0ShiftCaseTruth` and are used only by the benchmark evaluator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
)
from cpswm.contracts.base import (
    ContractModel,
    NonNegativeInt,
    PositiveInt,
    Probability,
    require_aware,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.synthetic_routines import (
    ObjectRoutineSpec,
    RoutineChangeKind,
    RoutineChangeSpec,
    RoutineGenerationConfig,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (
    CameraFrustum,
    IncidentalObservationPolicy,
    LocationGeometry,
    RobotPose,
    RobotTaskTrajectorySample,
    SymbolicSimulationResult,
    SymbolicWorldModelSimulator,
)

from .shift_attribution import (
    IdentifiabilityStatus,
    ShiftAttributionCase,
    ShiftCause,
    ShiftCausePrediction,
)


class D0FactorName(StrEnum):
    """Latent factor families varied by the paired D0 benchmark."""

    OBSERVATION_PROCESS = "observation_process"
    ACTOR_MIXTURE = "actor_mixture"
    IDENTITY_ASSOCIATION = "identity_association"
    OWNER_HABIT_REGIME = "owner_habit_regime"
    TRANSIENT_NOISE = "transient_noise"


_CAUSE_TO_FACTOR = {
    ShiftCause.OBSERVATION_POLICY: D0FactorName.OBSERVATION_PROCESS,
    ShiftCause.ACTOR_MIXTURE: D0FactorName.ACTOR_MIXTURE,
    ShiftCause.IDENTITY_ASSOCIATION: D0FactorName.IDENTITY_ASSOCIATION,
    ShiftCause.OWNER_HABIT_REGIME: D0FactorName.OWNER_HABIT_REGIME,
    ShiftCause.TRANSIENT_NOISE: D0FactorName.TRANSIENT_NOISE,
}


class D0ShiftScenarioConfig(ContractModel):
    """Versioned inputs for the first paired D0 benchmark suite."""

    suite_name: str = Field(default="d0-shift-attribution", min_length=1)
    start_time: datetime = datetime(2026, 8, 13, tzinfo=UTC)
    duration_days: PositiveInt = 8
    change_day: NonNegativeInt = 4
    random_seed: NonNegativeInt = 20260813
    paired_noise_seed: NonNegativeInt = 20260814
    control_selection_probability: float = Field(default=1.0, gt=0.0, le=1.0)
    shifted_selection_probability: float = Field(default=0.25, gt=0.0, le=1.0)
    field_of_view_coverage: Probability = 1.0
    p_visible_given_state: Probability = 1.0
    p_detect_given_visible: Probability = 1.0
    household_id: UUID = UUID(int=101)
    owner_id: UUID = UUID(int=102)
    guest_id: UUID = UUID(int=103)
    object_id: UUID = UUID(int=104)
    desk_id: UUID = UUID(int=105)
    sofa_id: UUID = UUID(int=106)
    primary_target_id: UUID = UUID(int=107)
    primary_task_id: UUID = UUID(int=108)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_design(self) -> D0ShiftScenarioConfig:
        if self.change_day <= 0 or self.change_day >= self.duration_days:
            raise ValueError("change_day must leave non-empty pre/post periods")
        if self.control_selection_probability == self.shifted_selection_probability:
            raise ValueError("D0-O requires distinct observation probabilities")
        entity_ids = (
            self.household_id,
            self.owner_id,
            self.guest_id,
            self.object_id,
            self.desk_id,
            self.sofa_id,
            self.primary_target_id,
            self.primary_task_id,
        )
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("D0 scenario entity IDs must be unique")
        return self


class D0FactorFingerprints(ContractModel):
    """Evaluator-only hashes of the independently controlled latent factors."""

    observation_process: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor_mixture: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_association: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_habit_regime: str = Field(pattern=r"^[0-9a-f]{64}$")
    transient_noise: str = Field(pattern=r"^[0-9a-f]{64}$")

    def changed_from(self, other: D0FactorFingerprints) -> tuple[D0FactorName, ...]:
        changed = [
            factor
            for factor in D0FactorName
            if getattr(self, factor.value) != getattr(other, factor.value)
        ]
        return tuple(changed)


class D0VisibleSimulationRun(ContractModel):
    """Robot-visible simulation projection with all privileged truth removed."""

    visible_run_id: UUID
    visible_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_time: datetime
    duration_days: int = Field(gt=0)
    random_seed: int = Field(ge=0)
    observation_opportunities: tuple[ObservationOpportunityRecord, ...] = Field(min_length=1)
    detection_results: tuple[ObservationDetectionResult, ...] = Field(min_length=1)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        return require_aware(value, "start_time")

    @model_validator(mode="after")
    def validate_projection(self) -> D0VisibleSimulationRun:
        expected_hash = content_sha256(self.content_payload())
        if self.visible_content_sha256 != expected_hash:
            raise ValueError("visible_content_sha256 does not match visible run content")
        expected_id = content_uuid("d0-visible-run", self.content_payload())
        if self.visible_run_id != expected_id:
            raise ValueError("visible_run_id does not match visible run content")

        opportunity_ids = {item.metadata.record_id for item in self.observation_opportunities}
        result_opportunity_ids = {
            item.observation_opportunity_id for item in self.detection_results
        }
        if len(opportunity_ids) != len(self.observation_opportunities):
            raise ValueError("visible run contains duplicate observation opportunities")
        if result_opportunity_ids != opportunity_ids:
            raise ValueError("visible run must bind one result to every opportunity")
        if len(self.detection_results) != len(opportunity_ids):
            raise ValueError("visible run requires exactly one result per opportunity")
        result_ids = [item.metadata.record_id for item in self.detection_results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("visible run contains duplicate detection results")
        return self

    def content_payload(self) -> dict[str, object]:
        return self.model_dump(
            mode="json",
            exclude={"visible_run_id", "visible_content_sha256"},
        )

    @classmethod
    def from_simulation(cls, simulation: SymbolicSimulationResult) -> D0VisibleSimulationRun:
        """Project a privileged simulation into the only input a model may read."""

        payload = {
            "start_time": simulation.start_time,
            "duration_days": simulation.duration_days,
            "random_seed": simulation.random_seed,
            "observation_opportunities": simulation.observation_opportunities,
            "detection_results": simulation.detection_results,
        }
        return cls(
            **payload,
            visible_run_id=content_uuid("d0-visible-run", payload),
            visible_content_sha256=content_sha256(payload),
        )

    @classmethod
    def from_records(
        cls,
        *,
        start_time: datetime,
        duration_days: int,
        random_seed: int,
        observation_opportunities: tuple[ObservationOpportunityRecord, ...],
        detection_results: tuple[ObservationDetectionResult, ...],
    ) -> D0VisibleSimulationRun:
        """Build a validated visible run from a time-local policy splice."""

        payload = {
            "start_time": start_time,
            "duration_days": duration_days,
            "random_seed": random_seed,
            "observation_opportunities": observation_opportunities,
            "detection_results": detection_results,
        }
        return cls(
            **payload,
            visible_run_id=content_uuid("d0-visible-run", payload),
            visible_content_sha256=content_sha256(payload),
        )


class D0ShiftCaseInput(ContractModel):
    """Public paired input consumed by a shift-attribution method."""

    case_id: str = Field(min_length=1)
    input_version: str = Field(default="d0-shift-input@0.2", min_length=1)
    change_time: datetime
    target_person_id: UUID
    control_run: D0VisibleSimulationRun
    shifted_run: D0VisibleSimulationRun
    control_actor_evidence: tuple[ActorResponsibilityEvidence, ...] = ()
    shifted_actor_evidence: tuple[ActorResponsibilityEvidence, ...] = ()

    @field_validator("change_time")
    @classmethod
    def validate_change_time(cls, value: datetime) -> datetime:
        return require_aware(value, "change_time")

    @model_validator(mode="after")
    def validate_window(self) -> D0ShiftCaseInput:
        for name, run in (
            ("control", self.control_run),
            ("shifted", self.shifted_run),
        ):
            run_end = run.start_time + timedelta(days=run.duration_days)
            if not run.start_time < self.change_time < run_end:
                raise ValueError(f"change_time must fall inside the {name} run")
        self._validate_actor_evidence(
            self.control_run,
            self.control_actor_evidence,
            "control",
        )
        self._validate_actor_evidence(
            self.shifted_run,
            self.shifted_actor_evidence,
            "shifted",
        )
        control_sessions = self._stream_identity(self.control_run, "session_id")
        shifted_sessions = self._stream_identity(self.shifted_run, "session_id")
        control_traces = self._stream_identity(self.control_run, "trace_id")
        shifted_traces = self._stream_identity(self.shifted_run, "trace_id")
        if control_sessions != shifted_sessions:
            raise ValueError("paired D0 runs must share one normalized session identity")
        if control_traces != shifted_traces:
            raise ValueError("paired D0 runs must share one normalized trace identity")
        return self

    @staticmethod
    def _stream_identity(run: D0VisibleSimulationRun, field_name: str) -> frozenset[UUID]:
        values = frozenset(
            getattr(item.metadata, field_name) for item in run.observation_opportunities
        ) | frozenset(getattr(item.metadata, field_name) for item in run.detection_results)
        if len(values) != 1:
            raise ValueError(f"each D0 visible run must have exactly one normalized {field_name}")
        return values

    @staticmethod
    def _validate_actor_evidence(
        run: D0VisibleSimulationRun,
        evidence: tuple[ActorResponsibilityEvidence, ...],
        name: str,
    ) -> None:
        evidence_ids = [item.metadata.record_id for item in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(f"{name} actor evidence IDs must be unique")
        detection_by_id = {item.metadata.record_id: item for item in run.detection_results}
        for item in evidence:
            detection = detection_by_id.get(item.source_detection_result_id)
            if detection is None:
                raise ValueError(f"{name} actor evidence references unknown detection")
            if detection.outcome != ObservationOutcome.DETECTED:
                raise ValueError(f"{name} actor evidence requires a detected result")
            if detection.detected_object_instance_id != item.object_instance_id:
                raise ValueError(f"{name} actor evidence object does not match detection")
            if detection.detection_time != item.evidence_time:
                raise ValueError(f"{name} actor evidence time does not match detection")
            if detection.metadata.household_id != item.metadata.household_id:
                raise ValueError(f"{name} actor evidence household does not match detection")


class D0ShiftCaseTruth(ContractModel):
    """Evaluator-only cause label and single-factor intervention audit."""

    case_id: str = Field(min_length=1)
    true_cause: ShiftCause
    identifiability_status: IdentifiabilityStatus = IdentifiabilityStatus.IDENTIFIABLE
    acceptable_cause_set: tuple[ShiftCause, ...] = ()
    intervention_available: bool = False
    control_factors: D0FactorFingerprints
    shifted_factors: D0FactorFingerprints

    @model_validator(mode="after")
    def validate_single_factor_intervention(self) -> D0ShiftCaseTruth:
        if self.true_cause == ShiftCause.UNRESOLVED:
            raise ValueError("D0 truth must identify a concrete shift cause")
        changed = self.shifted_factors.changed_from(self.control_factors)
        expected = (_CAUSE_TO_FACTOR[self.true_cause],)
        if changed != expected:
            rendered = ", ".join(item.value for item in changed) or "none"
            raise ValueError(
                f"D0 pair must change exactly the factor bound to true_cause; changed: {rendered}"
            )
        return self

    @property
    def changed_factors(self) -> tuple[D0FactorName, ...]:
        return self.shifted_factors.changed_from(self.control_factors)


class D0GeneratedCase(ContractModel):
    """Benchmark-side container; never pass this object to a candidate model."""

    model_input: D0ShiftCaseInput
    evaluator_truth: D0ShiftCaseTruth

    @model_validator(mode="after")
    def validate_case_binding(self) -> D0GeneratedCase:
        if self.model_input.case_id != self.evaluator_truth.case_id:
            raise ValueError("D0 input and evaluator truth case IDs do not match")
        return self

    def bind_prediction(self, prediction: ShiftCausePrediction) -> ShiftAttributionCase:
        """Bind a model output to hidden truth only after inference has finished."""

        return ShiftAttributionCase(
            case_id=self.evaluator_truth.case_id,
            true_cause=self.evaluator_truth.true_cause,
            identifiability_status=self.evaluator_truth.identifiability_status,
            acceptable_cause_set=self.evaluator_truth.acceptable_cause_set,
            intervention_available=self.evaluator_truth.intervention_available,
            prediction=prediction,
        )


class D0ShiftSuite(ContractModel):
    suite_id: UUID
    suite_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generator_version: str = Field(min_length=1)
    scenario_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor_evidence_track: ActorEvidenceTrack | None = None
    cases: tuple[D0GeneratedCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suite(self) -> D0ShiftSuite:
        case_ids = [case.model_input.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("D0 suite case IDs must be unique")
        expected_hash = content_sha256(self.content_payload())
        if self.suite_content_sha256 != expected_hash:
            raise ValueError("suite_content_sha256 does not match D0 suite content")
        if self.suite_id != content_uuid("d0-shift-suite", self.content_payload()):
            raise ValueError("suite_id does not match D0 suite content")
        return self

    def content_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"suite_id", "suite_content_sha256"})


class D0ShiftScenarioGenerator:
    """Build D0-O, D0-A, and D0-H as deterministic single-factor pairs."""

    generator_version = "d0-shift-scenarios@0.3"

    def generate(
        self,
        config: D0ShiftScenarioConfig | None = None,
        *,
        actor_evidence_track: ActorEvidenceTrack | None = None,
    ) -> D0ShiftSuite:
        config = config or D0ShiftScenarioConfig()
        config_sha256 = content_sha256(config)
        control_config = self._routine_config(config)
        control_policy = self._policy(
            config,
            policy_id="d0-logged-observation-control@0.1",
            selection_probability=config.control_selection_probability,
        )
        observation_shift_policy = self._policy(
            config,
            policy_id="d0-logged-observation-shift@0.1",
            selection_probability=config.shifted_selection_probability,
        )
        actor_shift_config = self._routine_config(
            config,
            change=RoutineChangeSpec(
                change_id=UUID(int=201),
                kind=RoutineChangeKind.GUEST_CONTAMINATION,
                object_instance_id=config.object_id,
                start_day=config.change_day,
                target_location_id=config.sofa_id,
                actor_override_id=config.guest_id,
            ),
        )
        habit_shift_config = self._routine_config(
            config,
            change=RoutineChangeSpec(
                change_id=UUID(int=202),
                kind=RoutineChangeKind.ABRUPT_CHANGE,
                object_instance_id=config.object_id,
                start_day=config.change_day,
                target_location_id=config.sofa_id,
            ),
        )

        cases = (
            self._build_case(
                ordinal=0,
                scenario_config_sha256=config_sha256,
                config=config,
                actor_evidence_track=actor_evidence_track,
                true_cause=ShiftCause.OBSERVATION_POLICY,
                control_config=control_config,
                shifted_config=control_config,
                control_policy=control_policy,
                shifted_policy=observation_shift_policy,
            ),
            self._build_case(
                ordinal=1,
                scenario_config_sha256=config_sha256,
                config=config,
                actor_evidence_track=actor_evidence_track,
                true_cause=ShiftCause.ACTOR_MIXTURE,
                control_config=control_config,
                shifted_config=actor_shift_config,
                control_policy=control_policy,
                shifted_policy=control_policy,
            ),
            self._build_case(
                ordinal=2,
                scenario_config_sha256=config_sha256,
                config=config,
                actor_evidence_track=actor_evidence_track,
                true_cause=ShiftCause.OWNER_HABIT_REGIME,
                control_config=control_config,
                shifted_config=habit_shift_config,
                control_policy=control_policy,
                shifted_policy=control_policy,
            ),
        )
        payload = {
            "generator_version": self.generator_version,
            "scenario_config_sha256": config_sha256,
            "actor_evidence_track": actor_evidence_track,
            "cases": cases,
        }
        return D0ShiftSuite(
            **payload,
            suite_id=content_uuid("d0-shift-suite", payload),
            suite_content_sha256=content_sha256(payload),
        )

    def _build_case(
        self,
        *,
        ordinal: int,
        scenario_config_sha256: str,
        config: D0ShiftScenarioConfig,
        actor_evidence_track: ActorEvidenceTrack | None,
        true_cause: ShiftCause,
        control_config: RoutineGenerationConfig,
        shifted_config: RoutineGenerationConfig,
        control_policy: IncidentalObservationPolicy,
        shifted_policy: IncidentalObservationPolicy,
    ) -> D0GeneratedCase:
        generator = SyntheticRoutineGenerator()
        simulator = SymbolicWorldModelSimulator()
        control_plan = generator.generate(control_config)
        shifted_plan = generator.generate(shifted_config)
        if true_cause == ShiftCause.OBSERVATION_POLICY:
            control, shifted = simulator.run_paired(
                control_plan,
                (control_policy, shifted_policy),
                paired_noise_seed=config.paired_noise_seed,
            )
        else:
            control = simulator.run(control_plan, control_policy)
            shifted = simulator.run(shifted_plan, shifted_policy)
        change_time = config.start_time + timedelta(days=config.change_day)
        control_visible = D0VisibleSimulationRun.from_simulation(control)
        shifted_visible = D0VisibleSimulationRun.from_simulation(shifted)
        control_observation_factor = self._observation_schedule_factor(
            control_policy, control_policy, config.change_day
        )
        shifted_observation_factor = self._observation_schedule_factor(
            shifted_policy, shifted_policy, config.change_day
        )
        if true_cause == ShiftCause.OBSERVATION_POLICY:
            shifted_visible = self._splice_visible_run(
                before=control,
                after=shifted,
                change_time=change_time,
            )
            shifted_observation_factor = self._observation_schedule_factor(
                control_policy, shifted_policy, config.change_day
            )
        control_actor_evidence = self._actor_evidence(
            simulation=control,
            actor_id=config.owner_id,
            config=config,
            track=actor_evidence_track,
            change_time=change_time,
        )
        shifted_actor_id = (
            config.guest_id if true_cause == ShiftCause.ACTOR_MIXTURE else config.owner_id
        )
        shifted_actor_evidence = self._actor_evidence(
            simulation=shifted,
            actor_id=shifted_actor_id,
            config=config,
            track=actor_evidence_track,
            change_time=change_time,
        )
        if true_cause == ShiftCause.OBSERVATION_POLICY:
            shifted_detection_ids = {
                item.metadata.record_id for item in shifted_visible.detection_results
            }
            shifted_actor_evidence = tuple(
                item
                for item in shifted_actor_evidence
                if item.source_detection_result_id in shifted_detection_ids
            )
        case_id = str(
            content_uuid(
                "d0-case",
                {
                    "suite_version": self.generator_version,
                    "scenario_config_sha256": scenario_config_sha256,
                    "ordinal": ordinal,
                },
            )
        )
        return D0GeneratedCase(
            model_input=D0ShiftCaseInput(
                case_id=case_id,
                change_time=change_time,
                target_person_id=config.owner_id,
                control_run=control_visible,
                shifted_run=shifted_visible,
                control_actor_evidence=control_actor_evidence,
                shifted_actor_evidence=shifted_actor_evidence,
            ),
            evaluator_truth=D0ShiftCaseTruth(
                case_id=case_id,
                true_cause=true_cause,
                identifiability_status=(
                    IdentifiabilityStatus.NON_IDENTIFIABLE
                    if actor_evidence_track is None
                    and true_cause in {ShiftCause.ACTOR_MIXTURE, ShiftCause.OWNER_HABIT_REGIME}
                    else IdentifiabilityStatus.IDENTIFIABLE
                ),
                acceptable_cause_set=(
                    (ShiftCause.ACTOR_MIXTURE, ShiftCause.OWNER_HABIT_REGIME)
                    if actor_evidence_track is None
                    and true_cause in {ShiftCause.ACTOR_MIXTURE, ShiftCause.OWNER_HABIT_REGIME}
                    else (true_cause,)
                ),
                intervention_available=(
                    actor_evidence_track is None
                    and true_cause in {ShiftCause.ACTOR_MIXTURE, ShiftCause.OWNER_HABIT_REGIME}
                ),
                control_factors=self._factor_fingerprints(
                    control_config,
                    observation_process=control_observation_factor,
                ),
                shifted_factors=self._factor_fingerprints(
                    shifted_config,
                    observation_process=shifted_observation_factor,
                ),
            ),
        )

    def _routine_config(
        self,
        config: D0ShiftScenarioConfig,
        *,
        change: RoutineChangeSpec | None = None,
    ) -> RoutineGenerationConfig:
        return RoutineGenerationConfig(
            household_id=config.household_id,
            start_time=config.start_time,
            duration_days=config.duration_days,
            random_seed=config.random_seed,
            object_routines=(
                ObjectRoutineSpec(
                    object_instance_id=config.object_id,
                    default_actor_id=config.owner_id,
                    initial_location_id=config.desk_id,
                    habitual_location_id=config.desk_id,
                    placement_hour=9,
                    activity_key="daily-reading",
                    context_key="weekday|morning",
                ),
            ),
            changes=((change,) if change is not None else ()),
        )

    def _policy(
        self,
        config: D0ShiftScenarioConfig,
        *,
        policy_id: str,
        selection_probability: float,
    ) -> IncidentalObservationPolicy:
        trajectory = tuple(
            RobotTaskTrajectorySample(
                sample_time=config.start_time + timedelta(days=day, hours=10),
                pose=RobotPose(
                    frame_id="household_map",
                    x_m=0.0,
                    y_m=0.0,
                    z_m=1.0,
                    yaw_degrees=0.0,
                    pitch_degrees=-10.0,
                ),
                camera_frustum=CameraFrustum(
                    horizontal_fov_degrees=120.0,
                    vertical_fov_degrees=120.0,
                    max_range_m=10.0,
                ),
            )
            for day in range(config.duration_days)
        )
        geometry = (
            LocationGeometry(
                location_id=config.desk_id,
                frame_id="household_map",
                x_m=2.0,
                y_m=-0.5,
                z_m=0.7,
            ),
            LocationGeometry(
                location_id=config.sofa_id,
                frame_id="household_map",
                x_m=2.5,
                y_m=0.5,
                z_m=0.7,
            ),
        )
        return IncidentalObservationPolicy(
            policy_id=policy_id,
            primary_task_id=config.primary_task_id,
            primary_task_goal="deliver the household reading tablet",
            primary_target_object_id=config.primary_target_id,
            scheduled_observation_object_id=config.object_id,
            selection_probability=selection_probability,
            field_of_view_coverage=config.field_of_view_coverage,
            p_visible_given_state=config.p_visible_given_state,
            p_detect_given_visible=config.p_detect_given_visible,
            robot_task_trajectory=trajectory,
            location_geometry=geometry,
        )

    def _factor_fingerprints(
        self,
        config: RoutineGenerationConfig,
        *,
        observation_process: dict[str, object],
    ) -> D0FactorFingerprints:
        return D0FactorFingerprints(
            observation_process=content_sha256(observation_process),
            actor_mixture=content_sha256(self._actor_factor(config)),
            identity_association=content_sha256(
                {
                    "object_instance_ids": sorted(
                        str(item.object_instance_id) for item in config.object_routines
                    ),
                    "identity_model": "oracle-stable-identity@0.1",
                }
            ),
            owner_habit_regime=content_sha256(self._owner_habit_factor(config)),
            transient_noise=content_sha256(
                {
                    "random_seed": config.random_seed,
                    "noise_model": "common-deterministic-stream@0.1",
                }
            ),
        )

    def _actor_evidence(
        self,
        *,
        simulation: SymbolicSimulationResult,
        actor_id: UUID,
        config: D0ShiftScenarioConfig,
        track: ActorEvidenceTrack | None,
        change_time: datetime,
    ) -> tuple[ActorResponsibilityEvidence, ...]:
        if track is None:
            return ()
        posterior, reference_prior = self._actor_posterior(actor_id, config, track)
        evidence: list[ActorResponsibilityEvidence] = []
        for detection in simulation.detection_results:
            if (
                detection.outcome != ObservationOutcome.DETECTED
                or detection.detection_time is None
                or detection.detection_time < change_time
                or detection.detected_object_instance_id is None
            ):
                continue
            evidence.append(
                ActorResponsibilityEvidence(
                    metadata=detection.metadata.model_copy(
                        update={
                            "record_id": content_uuid(
                                "d0-actor-evidence",
                                {
                                    "detection_result_id": detection.metadata.record_id,
                                    "track": track,
                                    "posterior": posterior,
                                    "reference_prior": reference_prior,
                                },
                            ),
                            "schema_name": "cpswm.ActorResponsibilityEvidence",
                            "source_id": "m12.d0-actor-evidence-simulator",
                            "model_version": f"d0-actor-evidence@0.2:{track.value}",
                        }
                    ),
                    source_detection_result_id=detection.metadata.record_id,
                    object_instance_id=detection.detected_object_instance_id,
                    evidence_time=detection.detection_time,
                    actor_posterior=posterior,
                    reference_actor_prior=reference_prior,
                    evidence_cluster_id=content_uuid(
                        "d0-actor-evidence-cluster",
                        {
                            "detection_result_id": detection.metadata.record_id,
                            "evidence_model": f"d0-actor-evidence@0.2:{track.value}",
                        },
                    ),
                    evidence_track=track,
                    evidence_model_id=f"d0-actor-evidence@0.2:{track.value}",
                )
            )
        return tuple(evidence)

    @staticmethod
    def _actor_posterior(
        actor_id: UUID,
        config: D0ShiftScenarioConfig,
        track: ActorEvidenceTrack,
    ) -> tuple[dict[str, float], dict[str, float]]:
        support = (str(config.owner_id), str(config.guest_id), "unknown_actor")
        reference_prior = {actor: 1.0 / len(support) for actor in support}
        if track == ActorEvidenceTrack.ORACLE:
            return (
                {actor: (1.0 if actor == str(actor_id) else 0.0) for actor in support},
                reference_prior,
            )
        other = config.guest_id if actor_id == config.owner_id else config.owner_id
        return (
            {
                str(actor_id): 0.8,
                str(other): 0.1,
                "unknown_actor": 0.1,
            },
            reference_prior,
        )

    @staticmethod
    def _observation_schedule_factor(
        before: IncidentalObservationPolicy,
        after: IncidentalObservationPolicy,
        change_day: int,
    ) -> dict[str, object]:
        return {
            "change_day": change_day,
            "before": before.model_dump(mode="python", exclude={"policy_id"}),
            "after": after.model_dump(mode="python", exclude={"policy_id"}),
        }

    @staticmethod
    def _splice_visible_run(
        *,
        before: SymbolicSimulationResult,
        after: SymbolicSimulationResult,
        change_time: datetime,
    ) -> D0VisibleSimulationRun:
        opportunities = tuple(
            item for item in before.observation_opportunities if item.opportunity_time < change_time
        ) + tuple(
            item for item in after.observation_opportunities if item.opportunity_time >= change_time
        )
        results = tuple(
            item for item in before.detection_results if item.metadata.recorded_time < change_time
        ) + tuple(
            item for item in after.detection_results if item.metadata.recorded_time >= change_time
        )
        return D0VisibleSimulationRun.from_records(
            start_time=before.start_time,
            duration_days=before.duration_days,
            random_seed=before.random_seed,
            observation_opportunities=opportunities,
            detection_results=results,
        )

    @staticmethod
    def _actor_factor(config: RoutineGenerationConfig) -> dict[str, object]:
        return {
            "default_actors": [
                {
                    "object_instance_id": str(item.object_instance_id),
                    "actor_id": str(item.default_actor_id),
                }
                for item in config.object_routines
            ],
            "actor_overrides": [
                {
                    "object_instance_id": str(change.object_instance_id),
                    "start_day": change.start_day,
                    "end_day": change.end_day,
                    "actor_override_id": str(change.actor_override_id),
                }
                for change in config.changes
                if change.actor_override_id is not None
            ],
        }

    @staticmethod
    def _owner_habit_factor(config: RoutineGenerationConfig) -> dict[str, object]:
        return {
            "base_habits": [
                {
                    "object_instance_id": str(item.object_instance_id),
                    "owner_id": str(item.default_actor_id),
                    "habitual_location_id": str(item.habitual_location_id),
                    "activity_key": item.activity_key,
                    "context_key": item.context_key,
                }
                for item in config.object_routines
            ],
            "owner_regime_changes": [
                {
                    "kind": change.kind.value,
                    "object_instance_id": str(change.object_instance_id),
                    "start_day": change.start_day,
                    "end_day": change.end_day,
                    "target_location_id": str(change.target_location_id),
                    "transition_days": change.transition_days,
                    "period_days": change.period_days,
                }
                for change in config.changes
                if change.actor_override_id is None
            ],
        }
