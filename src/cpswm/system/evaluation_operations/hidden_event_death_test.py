"""Matched multi-seed death test for hidden object-relocation event chains.

The benchmark keeps evaluator-only event-chain truth separate from robot-visible
endpoints and actor evidence.  It evaluates two different questions:

1. can a method identify the complete physical chain and responsible actor; and
2. can it incorporate delayed/corrective evidence without discarding history?

The second question is intentionally not inferred from final accuracy.  A
stateless baseline is rerun from the same accumulated evidence for a fair final
comparison, but that rerun is recorded as such rather than called a revision.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import product
from math import isclose
from random import Random
from typing import TypeVar
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    EventMechanismEvidence,
    EventType,
    HiddenEventEvidenceTrack,
    ObservationDetectionResult,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
)
from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.counterfactual_event_hypergraph import (
    AMGConstrainedMAPPrediction,
    BernertRamparany2021SequenceBaseline,
    CounterfactualEventHypergraphEngine,
    DamenHogg2012AMGGlobalMAPBaseline,
    DamenHogg2012AMGMatchedEvidenceBaseline,
    HiddenEventEvidence,
    HiddenEventStep,
    IndependentEventCandidateBaseline,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    Top1EventGraphBaseline,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.system.synthetic_routines import (
    ObjectRoutineSpec,
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
)
from cpswm.system.world_model_simulator.benchmark_access import (
    issue_benchmark_ground_truth_capability,
)
from cpswm_gt import GTInteractionEvent, GTInteractionEventType

DistributionKeyT = TypeVar("DistributionKeyT")


class HiddenEventFamily(StrEnum):
    CLEAN_DIRECT = "clean_direct"
    CLEAN_HANDOFF = "clean_handoff"
    DELAYED_DIRECT = "delayed_direct"
    DELAYED_HANDOFF = "delayed_handoff"
    IDENTITY_NOISE_DIRECT = "identity_noise_direct"
    IDENTITY_NOISE_HANDOFF = "identity_noise_handoff"
    DUPLICATE_CLUSTER_DIRECT = "duplicate_cluster_direct"
    DUPLICATE_CLUSTER_HANDOFF = "duplicate_cluster_handoff"
    UNKNOWN_DIRECT = "unknown_direct"
    UNKNOWN_HANDOFF = "unknown_handoff"

    @property
    def is_handoff(self) -> bool:
        return self.value.endswith("handoff")

    @property
    def uses_unknown_actor(self) -> bool:
        return self in {self.UNKNOWN_DIRECT, self.UNKNOWN_HANDOFF}

    @property
    def has_late_evidence(self) -> bool:
        return self not in {self.CLEAN_DIRECT, self.CLEAN_HANDOFF}

    @property
    def has_duplicate_submission(self) -> bool:
        return self in {
            self.DUPLICATE_CLUSTER_DIRECT,
            self.DUPLICATE_CLUSTER_HANDOFF,
        }


class HiddenEventSplit(StrEnum):
    VALIDATION = "validation"
    TEST = "test"


class HiddenEventMethod(StrEnum):
    CHEH = "cheh"
    ORRER = "orrer"
    BERNERT_RAMPARANY_2021 = "bernert_ramparany_2021_adaptation"
    DAMEN_HOGG_2012 = "damen_hogg_2012_amg_map_adaptation"
    DAMEN_HOGG_2012_MATCHED = "damen_hogg_2012_matched_open_world_evidence"
    TOP1_EVENT_GRAPH = "top1_event_graph"
    INDEPENDENT_CANDIDATES = "independent_event_candidates"


class HiddenEventSignatureStep(ContractModel):
    event_type: EventType
    actor_key: str = Field(min_length=1)
    recipient_actor_key: str | None = None


class HiddenEventCaseInput(ContractModel):
    """Robot-visible inputs; this contract deliberately contains no truth."""

    case_id: str = Field(min_length=1)
    family: HiddenEventFamily
    split: HiddenEventSplit
    seed: int = Field(ge=0)
    before: ObservationDetectionResult
    after: ObservationDetectionResult
    known_actor_keys: tuple[str, str]
    actor_prior: dict[str, Probability]
    initial_evidence: tuple[ActorResponsibilityEvidence, ...] = ()
    late_evidence: tuple[ActorResponsibilityEvidence, ...] = ()
    initial_mechanism_evidence: tuple[EventMechanismEvidence, ...] = ()
    late_mechanism_evidence: tuple[EventMechanismEvidence, ...] = ()
    initial_role_evidence: tuple[RoleBindingEvidence, ...] = ()
    late_role_evidence: tuple[RoleBindingEvidence, ...] = ()
    duplicate_submission: ActorResponsibilityEvidence | None = None

    @model_validator(mode="after")
    def validate_case_input(self) -> HiddenEventCaseInput:
        expected_support = {*self.known_actor_keys, "unknown_actor"}
        if set(self.actor_prior) != expected_support:
            raise ValueError("actor_prior must cover two known actors and unknown_actor")
        if not isclose(sum(self.actor_prior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("actor_prior must sum to one")
        evidence = (*self.initial_evidence, *self.late_evidence)
        if any(set(item.actor_posterior) != expected_support for item in evidence):
            raise ValueError("every actor evidence posterior must match actor_prior support")
        if self.family.has_late_evidence != bool(self.late_evidence):
            raise ValueError("family late-evidence semantics do not match the evidence stream")
        if self.family.has_late_evidence != bool(self.late_mechanism_evidence):
            raise ValueError("family timing must also govern mechanism evidence")
        role_evidence = (*self.initial_role_evidence, *self.late_role_evidence)
        if self.family.is_handoff != bool(role_evidence):
            raise ValueError("only handoff families require ordered-role evidence")
        if self.family.has_late_evidence and self.family.is_handoff:
            if not self.late_role_evidence:
                raise ValueError("late handoff families require late role evidence")
        elif self.family.is_handoff and not self.initial_role_evidence:
            raise ValueError("clean handoff families require initial role evidence")
        if self.family.has_duplicate_submission != (self.duplicate_submission is not None):
            raise ValueError("family duplicate semantics do not match duplicate_submission")
        return self


class HiddenEventCaseTruth(ContractModel):
    """Evaluator-only truth obtained through the simulator benchmark capability."""

    case_id: str = Field(min_length=1)
    signature: tuple[HiddenEventSignatureStep, ...] = Field(min_length=3)
    responsible_actor_key: str = Field(min_length=1)
    within_closed_known_actor_assumption: bool


class HiddenEventGeneratedCase(ContractModel):
    model_input: HiddenEventCaseInput
    evaluator_truth: HiddenEventCaseTruth

    @model_validator(mode="after")
    def validate_binding(self) -> HiddenEventGeneratedCase:
        if self.model_input.case_id != self.evaluator_truth.case_id:
            raise ValueError("hidden-event model input and evaluator truth are misbound")
        return self


class HiddenEventSuite(ContractModel):
    generator_version: str = Field(min_length=1)
    cases: tuple[HiddenEventGeneratedCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suite(self) -> HiddenEventSuite:
        case_ids = [case.model_input.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("hidden-event suite case IDs must be unique")
        if {case.model_input.split for case in self.cases} != {
            HiddenEventSplit.VALIDATION,
            HiddenEventSplit.TEST,
        }:
            raise ValueError("hidden-event suite requires validation and test cases")
        return self


class HiddenEventTuningSelection(ContractModel):
    method: HiddenEventMethod
    selected_parameters: dict[str, float]
    validation_case_count: int = Field(ge=1)
    candidate_configuration_count: int = Field(ge=1)
    validation_exact_chain_rate: Probability
    validation_responsible_actor_accuracy: Probability


class HiddenEventCaseResult(ContractModel):
    case_id: str = Field(min_length=1)
    family: HiddenEventFamily
    split: HiddenEventSplit
    method: HiddenEventMethod
    within_closed_known_actor_assumption: bool
    supported: bool
    unsupported_reason: str | None = None
    pre_selected_signature: tuple[HiddenEventSignatureStep, ...] | None = None
    final_selected_signature: tuple[HiddenEventSignatureStep, ...] | None = None
    final_emitted_signatures: tuple[tuple[HiddenEventSignatureStep, ...], ...] = ()
    pre_responsible_actor_key: str | None = None
    final_responsible_actor_key: str | None = None
    pre_exact_chain: bool | None = None
    final_exact_chain: bool | None = None
    truth_in_final_emitted_set: bool | None = None
    pre_responsible_actor_correct: bool | None = None
    final_responsible_actor_correct: bool | None = None
    update_mode: str = Field(min_length=1)
    append_only_revision_count: int = Field(ge=0)
    reactivated_hypothesis_count: int = Field(default=0, ge=0)
    duplicate_submission_rejected: bool | None = None

    @model_validator(mode="after")
    def validate_result(self) -> HiddenEventCaseResult:
        if self.supported and self.unsupported_reason is not None:
            raise ValueError("supported result cannot carry an unsupported_reason")
        if not self.supported and not self.unsupported_reason:
            raise ValueError("unsupported result requires an explicit reason")
        return self


class HiddenEventMethodReport(ContractModel):
    method: HiddenEventMethod
    in_assumption_case_count: int = Field(ge=0)
    out_of_assumption_case_count: int = Field(ge=0)
    unsupported_case_count: int = Field(ge=0)
    final_exact_chain_rate: Probability | None = None
    final_truth_set_coverage: Probability | None = None
    responsibility_decision_coverage: Probability | None = None
    responsibility_accuracy_when_decided: Probability | None = None
    overall_responsibility_accuracy: Probability | None = None
    late_responsibility_recovery_rate: Probability | None = None
    append_only_revision_rate: Probability | None = None
    unknown_actor_truth_set_coverage: Probability | None = None
    duplicate_submission_rejection_rate: Probability | None = None
    reactivation_case_rate: Probability | None = None


class HiddenEventDeathTestReport(ContractModel):
    suite_generator_version: str = Field(min_length=1)
    validation_case_count: int = Field(ge=1)
    test_case_count: int = Field(ge=1)
    tuning: tuple[HiddenEventTuningSelection, ...]
    test_results: tuple[HiddenEventCaseResult, ...] = Field(min_length=1)
    method_reports: tuple[HiddenEventMethodReport, ...] = Field(min_length=1)
    scientific_status: str = Field(min_length=1)


class M30HiddenEventSuiteGenerator:
    """Generate paired direct/handoff cases with controlled evidence timing."""

    generator_version = "m30-hidden-event-death-test@0.2"
    default_families = tuple(HiddenEventFamily)

    def generate(
        self,
        *,
        validation_seeds: tuple[int, ...] = (0, 1),
        test_seeds: tuple[int, ...] = (2, 3, 4, 5, 6, 7),
        families: tuple[HiddenEventFamily, ...] = default_families,
    ) -> HiddenEventSuite:
        if not validation_seeds or not test_seeds:
            raise ValueError("death test requires non-empty validation and test seeds")
        if set(validation_seeds) & set(test_seeds):
            raise ValueError("validation and test seeds must be disjoint")
        if not families:
            raise ValueError("death test requires at least one scenario family")
        cases = tuple(
            self._generate_case(family=family, split=split, seed=seed)
            for split, seeds in (
                (HiddenEventSplit.VALIDATION, validation_seeds),
                (HiddenEventSplit.TEST, test_seeds),
            )
            for seed, family in product(seeds, families)
        )
        return HiddenEventSuite(generator_version=self.generator_version, cases=cases)

    def _generate_case(
        self,
        *,
        family: HiddenEventFamily,
        split: HiddenEventSplit,
        seed: int,
    ) -> HiddenEventGeneratedCase:
        family_index = list(HiddenEventFamily).index(family)
        base = 100_000 + seed * 10_000 + family_index * 100
        household_id = UUID(int=base + 1)
        owner_id = UUID(int=base + 2)
        second_actor_id = UUID(int=base + 3)
        unknown_actor_id = UUID(int=base + 4)
        object_id = UUID(int=base + 5)
        target_object_id = UUID(int=base + 6)
        source_location_id = UUID(int=base + 7)
        handoff_location_id = UUID(int=base + 8)
        destination_location_id = UUID(int=base + 9)
        task_id = UUID(int=base + 10)
        start = datetime(2026, 8, 1, tzinfo=UTC) + timedelta(days=seed * 12 + family_index)

        final_actor_id = (
            unknown_actor_id
            if family.uses_unknown_actor
            else (second_actor_id if family.is_handoff else owner_id)
        )
        routine = ObjectRoutineSpec(
            object_instance_id=object_id,
            default_actor_id=(owner_id if family.is_handoff else final_actor_id),
            handoff_recipient_actor_id=(final_actor_id if family.is_handoff else None),
            handoff_location_id=(handoff_location_id if family.is_handoff else None),
            initial_location_id=source_location_id,
            habitual_location_id=destination_location_id,
            placement_hour=9,
            activity_key=f"m30-{family.value}",
            context_key="weekday|morning",
        )
        config = RoutineGenerationConfig(
            household_id=household_id,
            start_time=start,
            duration_days=1,
            random_seed=seed,
            object_routines=(routine,),
        )
        policy = IncidentalObservationPolicy(
            policy_id=f"m30-hidden-death-test-{family.value}@0.1",
            primary_task_id=task_id,
            primary_task_goal="deliver household item",
            primary_target_object_id=target_object_id,
            scheduled_observation_object_id=object_id,
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
                for location_id, y_m in (
                    (source_location_id, -0.5),
                    (handoff_location_id, 0.0),
                    (destination_location_id, 0.5),
                )
            ),
        )
        plan = SyntheticRoutineGenerator().generate(config)
        benchmark_view = SymbolicWorldModelSimulator().run_privileged(
            plan,
            policy,
            capability=issue_benchmark_ground_truth_capability(),
        )
        before, after = benchmark_view.visible_result.detection_results
        known_actor_keys = (str(owner_id), str(second_actor_id))
        actor_prior = {
            known_actor_keys[0]: 0.45,
            known_actor_keys[1]: 0.45,
            "unknown_actor": 0.10,
        }
        truth_actor_key = "unknown_actor" if family.uses_unknown_actor else str(final_actor_id)
        other_key = (
            known_actor_keys[1] if truth_actor_key == known_actor_keys[0] else known_actor_keys[0]
        )
        evidence_stream = self._make_evidence_stream(
            family=family,
            seed=seed,
            after=after,
            actor_prior=actor_prior,
            truth_actor_key=truth_actor_key,
            other_key=other_key,
        )
        structured_evidence_stream = self._make_structured_evidence_stream(
            family=family,
            seed=seed,
            after=after,
            actor_keys=tuple(actor_prior),
            truth_initial_actor_key=(str(owner_id) if family.is_handoff else truth_actor_key),
            truth_responsible_actor_key=truth_actor_key,
        )
        truth_signature = self._truth_signature(
            benchmark_view.ground_truth.interaction_events,
            unknown_actor_id=unknown_actor_id if family.uses_unknown_actor else None,
        )
        case_id = f"{split.value}-s{seed:02d}-{family.value}"
        return HiddenEventGeneratedCase(
            model_input=HiddenEventCaseInput(
                case_id=case_id,
                family=family,
                split=split,
                seed=seed,
                before=before,
                after=after,
                known_actor_keys=known_actor_keys,
                actor_prior=actor_prior,
                initial_evidence=evidence_stream[0],
                late_evidence=evidence_stream[1],
                initial_mechanism_evidence=structured_evidence_stream[0],
                late_mechanism_evidence=structured_evidence_stream[1],
                initial_role_evidence=structured_evidence_stream[2],
                late_role_evidence=structured_evidence_stream[3],
                duplicate_submission=evidence_stream[2],
            ),
            evaluator_truth=HiddenEventCaseTruth(
                case_id=case_id,
                signature=truth_signature,
                responsible_actor_key=truth_actor_key,
                within_closed_known_actor_assumption=not family.uses_unknown_actor,
            ),
        )

    def _make_evidence_stream(
        self,
        *,
        family: HiddenEventFamily,
        seed: int,
        after: ObservationDetectionResult,
        actor_prior: dict[str, float],
        truth_actor_key: str,
        other_key: str,
    ) -> tuple[
        tuple[ActorResponsibilityEvidence, ...],
        tuple[ActorResponsibilityEvidence, ...],
        ActorResponsibilityEvidence | None,
    ]:
        assert after.detected_object_instance_id is not None
        assert after.detection_time is not None
        evidence_time = after.detection_time
        detected_object_id = after.detected_object_instance_id

        def posterior(truth: float, other: float, unknown: float) -> dict[str, float]:
            values = {actor: 0.0 for actor in actor_prior}
            if truth_actor_key == "unknown_actor":
                values["unknown_actor"] = truth
                values[other_key] = other
                remaining_key = next(
                    actor for actor in actor_prior if actor not in {"unknown_actor", other_key}
                )
                values[remaining_key] = 1.0 - truth - other
            else:
                values[truth_actor_key] = truth
                values[other_key] = other
                values["unknown_actor"] = unknown
            return values

        # The seed changes evidence strength while preserving the family-level
        # semantics.  This avoids calling mere UUID/time replication a
        # multi-seed test and remains deterministic for exact reruns.
        random = Random(f"{seed}:{family.value}")
        correct_truth = random.uniform(0.82, 0.90)
        wrong_truth = random.uniform(0.08, 0.12)
        correction_truth = random.uniform(0.91, 0.95)
        if truth_actor_key == "unknown_actor":
            correct = posterior(correct_truth, 0.07, 1.0 - correct_truth - 0.07)
        else:
            correct = posterior(correct_truth, 0.96 - correct_truth, 0.04)
        wrong = posterior(wrong_truth, 0.96 - wrong_truth, 0.04)
        correction = posterior(correction_truth, 0.98 - correction_truth, 0.02)

        def evidence(
            label: str,
            distribution: dict[str, float],
            *,
            cluster_id: UUID | None = None,
        ) -> ActorResponsibilityEvidence:
            identity = {
                "after": str(after.metadata.record_id),
                "family": family.value,
                "label": label,
            }
            record_id = content_uuid("m30-actor-evidence-record", identity)
            actual_cluster_id = cluster_id or content_uuid("m30-actor-evidence-cluster", identity)
            return ActorResponsibilityEvidence(
                metadata=BaseRecordMetadata(
                    record_id=record_id,
                    schema_name="cpswm.ActorResponsibilityEvidence",
                    schema_version="0.1.0",
                    household_id=after.metadata.household_id,
                    session_id=after.metadata.session_id,
                    recorded_time=evidence_time,
                    source_type=SourceType.MODEL,
                    source_id=f"controlled-{label}",
                    model_version="controlled-actor-evidence@0.1",
                    trace_id=after.metadata.trace_id,
                ),
                source_detection_result_id=after.metadata.record_id,
                object_instance_id=detected_object_id,
                evidence_time=evidence_time,
                actor_posterior=distribution,
                reference_actor_prior=actor_prior,
                evidence_cluster_id=actual_cluster_id,
                effective_sample_weight=1.0,
                evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
                evidence_model_id="controlled-actor-evidence@0.1",
            )

        if family in {HiddenEventFamily.CLEAN_DIRECT, HiddenEventFamily.CLEAN_HANDOFF}:
            return (evidence("initial-correct", correct),), (), None
        if family in {
            HiddenEventFamily.IDENTITY_NOISE_DIRECT,
            HiddenEventFamily.IDENTITY_NOISE_HANDOFF,
        }:
            return (
                (evidence("initial-wrong", wrong),),
                (evidence("late-correction", correction),),
                None,
            )
        late = evidence("late-correct", correct)
        if family.has_duplicate_submission:
            duplicate = late.model_copy(
                update={
                    "metadata": late.metadata.model_copy(
                        update={
                            "record_id": content_uuid(
                                "m30-actor-evidence-record",
                                {
                                    "after": str(after.metadata.record_id),
                                    "family": family.value,
                                    "label": "duplicate-wrapper",
                                },
                            ),
                            "source_id": "controlled-duplicate-wrapper",
                        }
                    )
                }
            )
            return (), (late,), duplicate
        return (), (late,), None

    def _make_structured_evidence_stream(
        self,
        *,
        family: HiddenEventFamily,
        seed: int,
        after: ObservationDetectionResult,
        actor_keys: tuple[str, ...],
        truth_initial_actor_key: str,
        truth_responsible_actor_key: str,
    ) -> tuple[
        tuple[EventMechanismEvidence, ...],
        tuple[EventMechanismEvidence, ...],
        tuple[RoleBindingEvidence, ...],
        tuple[RoleBindingEvidence, ...],
    ]:
        assert after.detected_object_instance_id is not None
        assert after.detection_time is not None
        detected_object_id = after.detected_object_instance_id
        evidence_time = after.detection_time
        random = Random(f"structured:{seed}:{family.value}")
        truth_strength = random.uniform(0.82, 0.90)
        true_mechanism = (
            EventMechanism.HANDOFF_RELOCATION
            if family.is_handoff
            else EventMechanism.DIRECT_RELOCATION
        )
        other_mechanism = (
            EventMechanism.DIRECT_RELOCATION
            if family.is_handoff
            else EventMechanism.HANDOFF_RELOCATION
        )

        def metadata(label: str, schema_name: str) -> BaseRecordMetadata:
            identity = {
                "after": str(after.metadata.record_id),
                "family": family.value,
                "label": label,
            }
            return BaseRecordMetadata(
                record_id=content_uuid("m30-structured-evidence-record", identity),
                schema_name=schema_name,
                schema_version="0.1.0",
                household_id=after.metadata.household_id,
                session_id=after.metadata.session_id,
                recorded_time=evidence_time,
                source_type=SourceType.MODEL,
                source_id=f"controlled-{label}",
                model_version="controlled-structured-event-evidence@0.1",
                trace_id=after.metadata.trace_id,
            )

        mechanism_identity = {
            "after": str(after.metadata.record_id),
            "family": family.value,
            "kind": "mechanism",
        }
        mechanism = EventMechanismEvidence(
            metadata=metadata("mechanism-correct", "cpswm.EventMechanismEvidence"),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=detected_object_id,
            evidence_time=evidence_time,
            mechanism_posterior={
                true_mechanism: truth_strength,
                other_mechanism: 1.0 - truth_strength,
            },
            reference_mechanism_prior={
                EventMechanism.DIRECT_RELOCATION: 0.5,
                EventMechanism.HANDOFF_RELOCATION: 0.5,
            },
            evidence_cluster_id=content_uuid("m30-structured-evidence-cluster", mechanism_identity),
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="controlled-mechanism-evidence@0.1",
        )
        role: RoleBindingEvidence | None = None
        if family.is_handoff:
            role_keys = tuple(
                ordered_role_key(initiator, recipient)
                for initiator, recipient in product(actor_keys, repeat=2)
                if initiator != recipient
            )
            truth_role = ordered_role_key(truth_initial_actor_key, truth_responsible_actor_key)
            residual = (1.0 - truth_strength) / (len(role_keys) - 1)
            role_identity = {
                "after": str(after.metadata.record_id),
                "family": family.value,
                "kind": "ordered-role",
            }
            role = RoleBindingEvidence(
                metadata=metadata("ordered-role-correct", "cpswm.RoleBindingEvidence"),
                source_detection_result_id=after.metadata.record_id,
                object_instance_id=detected_object_id,
                evidence_time=evidence_time,
                ordered_role_posterior={
                    key: truth_strength if key == truth_role else residual for key in role_keys
                },
                reference_ordered_role_prior={key: 1.0 / len(role_keys) for key in role_keys},
                evidence_cluster_id=content_uuid("m30-structured-evidence-cluster", role_identity),
                evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
                evidence_model_id="controlled-role-evidence@0.1",
            )
        if family.has_late_evidence:
            return (), (mechanism,), (), ((role,) if role is not None else ())
        return (mechanism,), (), ((role,) if role is not None else ()), ()

    @staticmethod
    def _truth_signature(
        interaction_events: Iterable[GTInteractionEvent],
        *,
        unknown_actor_id: UUID | None,
    ) -> tuple[HiddenEventSignatureStep, ...]:
        event_type_map = {
            GTInteractionEventType.PICK_UP: EventType.PICK_UP,
            GTInteractionEventType.CARRY: EventType.CARRY,
            GTInteractionEventType.HANDOFF: EventType.TRANSFER,
            GTInteractionEventType.PLACE: EventType.PLACE,
        }

        def actor_key(actor_id: UUID) -> str:
            if unknown_actor_id is not None and actor_id == unknown_actor_id:
                return "unknown_actor"
            return str(actor_id)

        return tuple(
            HiddenEventSignatureStep(
                event_type=event_type_map[event.event_type],
                actor_key=actor_key(event.actor_gt_entity_id),
                recipient_actor_key=(
                    actor_key(event.recipient_actor_gt_entity_id)
                    if event.recipient_actor_gt_entity_id is not None
                    else None
                ),
            )
            for event in interaction_events
        )


class HiddenEventMatchedDeathTest:
    """Tune on validation seeds and score matched methods on held-out seeds."""

    cheh_handoff_grid = (0.2, 0.5, 0.8)
    cheh_retraction_grid = (0.0, 0.01)
    amg_handoff_grid = (0.2, 0.5, 0.8)
    matched_evidence_power_grid = (0.5, 1.0, 2.0)

    def run(self, suite: HiddenEventSuite) -> HiddenEventDeathTestReport:
        all_validation = tuple(
            case for case in suite.cases if case.model_input.split == HiddenEventSplit.VALIDATION
        )
        tuning_validation = tuple(
            case
            for case in all_validation
            if case.evaluator_truth.within_closed_known_actor_assumption
        )
        test = tuple(
            case for case in suite.cases if case.model_input.split == HiddenEventSplit.TEST
        )
        if not tuning_validation or not test:
            raise ValueError("death test requires validation and test cases")
        cheh_tuning = self._tune_cheh(tuning_validation)
        orrer_tuning = self._tune_orrer(all_validation)
        amg_tuning = self._tune_amg(tuning_validation)
        matched_amg_tuning = self._tune_matched_amg(all_validation)
        tuning = (cheh_tuning, orrer_tuning, amg_tuning, matched_amg_tuning)
        parameters_by_method = {
            HiddenEventMethod.CHEH: cheh_tuning.selected_parameters,
            HiddenEventMethod.ORRER: orrer_tuning.selected_parameters,
            HiddenEventMethod.DAMEN_HOGG_2012: amg_tuning.selected_parameters,
            HiddenEventMethod.DAMEN_HOGG_2012_MATCHED: (matched_amg_tuning.selected_parameters),
        }
        results = tuple(
            self._evaluate_case(case, method, parameters_by_method.get(method, {}))
            for method in HiddenEventMethod
            for case in test
        )
        reports = tuple(self._aggregate_method(method, results) for method in HiddenEventMethod)
        return HiddenEventDeathTestReport(
            suite_generator_version=suite.generator_version,
            validation_case_count=len(all_validation),
            test_case_count=len(test),
            tuning=tuning,
            test_results=results,
            method_reports=reports,
            scientific_status=self._scientific_status(reports),
        )

    def _tune_cheh(
        self, validation: Sequence[HiddenEventGeneratedCase]
    ) -> HiddenEventTuningSelection:
        candidates = tuple(product(self.cheh_handoff_grid, self.cheh_retraction_grid))
        scored = []
        for handoff_fraction, retraction_threshold in candidates:
            parameters = {
                "handoff_fraction": handoff_fraction,
                "retraction_threshold": retraction_threshold,
            }
            results = tuple(
                self._evaluate_case(case, HiddenEventMethod.CHEH, parameters) for case in validation
            )
            scored.append((self._tuning_score(results), parameters))
        score, parameters = max(
            scored,
            key=lambda item: (
                item[0][0],
                item[0][1],
                -abs(item[1]["handoff_fraction"] - 0.5),
                -item[1]["retraction_threshold"],
            ),
        )
        return HiddenEventTuningSelection(
            method=HiddenEventMethod.CHEH,
            selected_parameters=parameters,
            validation_case_count=len(validation),
            candidate_configuration_count=len(candidates),
            validation_exact_chain_rate=score[0],
            validation_responsible_actor_accuracy=score[1],
        )

    def _tune_orrer(
        self, validation: Sequence[HiddenEventGeneratedCase]
    ) -> HiddenEventTuningSelection:
        candidates = tuple(product(self.cheh_handoff_grid, self.cheh_retraction_grid))
        scored = []
        for handoff_fraction, retraction_threshold in candidates:
            parameters = {
                "handoff_fraction": handoff_fraction,
                "retraction_threshold": retraction_threshold,
            }
            results = tuple(
                self._evaluate_case(case, HiddenEventMethod.ORRER, parameters)
                for case in validation
            )
            scored.append((self._tuning_score(results), parameters))
        score, parameters = max(
            scored,
            key=lambda item: (
                item[0][0],
                item[0][1],
                -abs(item[1]["handoff_fraction"] - 0.5),
                -item[1]["retraction_threshold"],
            ),
        )
        return HiddenEventTuningSelection(
            method=HiddenEventMethod.ORRER,
            selected_parameters=parameters,
            validation_case_count=len(validation),
            candidate_configuration_count=len(candidates),
            validation_exact_chain_rate=score[0],
            validation_responsible_actor_accuracy=score[1],
        )

    def _tune_amg(
        self, validation: Sequence[HiddenEventGeneratedCase]
    ) -> HiddenEventTuningSelection:
        scored = []
        for handoff_likelihood in self.amg_handoff_grid:
            parameters = {"handoff_event_likelihood": handoff_likelihood}
            results = tuple(
                self._evaluate_case(case, HiddenEventMethod.DAMEN_HOGG_2012, parameters)
                for case in validation
            )
            scored.append((self._tuning_score(results), parameters))
        score, parameters = max(
            scored,
            key=lambda item: (
                item[0][0],
                item[0][1],
                -abs(item[1]["handoff_event_likelihood"] - 0.5),
            ),
        )
        return HiddenEventTuningSelection(
            method=HiddenEventMethod.DAMEN_HOGG_2012,
            selected_parameters=parameters,
            validation_case_count=len(validation),
            candidate_configuration_count=len(self.amg_handoff_grid),
            validation_exact_chain_rate=score[0],
            validation_responsible_actor_accuracy=score[1],
        )

    def _tune_matched_amg(
        self, validation: Sequence[HiddenEventGeneratedCase]
    ) -> HiddenEventTuningSelection:
        scored = []
        for evidence_power in self.matched_evidence_power_grid:
            parameters = {"evidence_power": evidence_power}
            results = tuple(
                self._evaluate_case(case, HiddenEventMethod.DAMEN_HOGG_2012_MATCHED, parameters)
                for case in validation
            )
            scored.append((self._tuning_score(results), parameters))
        score, parameters = max(
            scored,
            key=lambda item: (
                item[0][0],
                item[0][1],
                -abs(item[1]["evidence_power"] - 1.0),
            ),
        )
        return HiddenEventTuningSelection(
            method=HiddenEventMethod.DAMEN_HOGG_2012_MATCHED,
            selected_parameters=parameters,
            validation_case_count=len(validation),
            candidate_configuration_count=len(self.matched_evidence_power_grid),
            validation_exact_chain_rate=score[0],
            validation_responsible_actor_accuracy=score[1],
        )

    @staticmethod
    def _tuning_score(results: Sequence[HiddenEventCaseResult]) -> tuple[float, float]:
        exact = sum(result.final_exact_chain is True for result in results) / len(results)
        actor = sum(result.final_responsible_actor_correct is True for result in results) / len(
            results
        )
        return exact, actor

    def _evaluate_case(
        self,
        case: HiddenEventGeneratedCase,
        method: HiddenEventMethod,
        parameters: dict[str, float],
    ) -> HiddenEventCaseResult:
        if not case.evaluator_truth.within_closed_known_actor_assumption and method in {
            HiddenEventMethod.BERNERT_RAMPARANY_2021,
            HiddenEventMethod.DAMEN_HOGG_2012,
        }:
            return self._unsupported_result(
                case,
                method,
                "closed-known-actor adaptation cannot represent unknown_actor",
            )
        if method == HiddenEventMethod.CHEH:
            return self._evaluate_cheh(case, parameters)
        if method == HiddenEventMethod.ORRER:
            return self._evaluate_orrer(case, parameters)
        if method == HiddenEventMethod.BERNERT_RAMPARANY_2021:
            return self._evaluate_bernert(case)
        if method == HiddenEventMethod.DAMEN_HOGG_2012_MATCHED:
            return self._evaluate_matched_amg(case, parameters)
        return self._evaluate_stateless(case, method, parameters)

    def _evaluate_cheh(
        self,
        case: HiddenEventGeneratedCase,
        parameters: dict[str, float],
    ) -> HiddenEventCaseResult:
        data = case.model_input
        engine = CounterfactualEventHypergraphEngine()
        history = engine.branch(
            before=data.before,
            after=data.after,
            actor_prior=data.actor_prior,
            unresolved_probability=0.1,
            handoff_fraction=parameters["handoff_fraction"],
        )
        for evidence in data.initial_evidence:
            history = engine.revise_actor_responsibility(
                history,
                evidence,
                retraction_threshold=parameters["retraction_threshold"],
            )
        pre_selected = history.latest.map_hypothesis
        for evidence in data.late_evidence:
            history = engine.revise_actor_responsibility(
                history,
                evidence,
                retraction_threshold=parameters["retraction_threshold"],
            )
        duplicate_rejected = None
        if data.duplicate_submission is not None:
            try:
                engine.revise_actor_responsibility(
                    history,
                    data.duplicate_submission,
                    retraction_threshold=parameters["retraction_threshold"],
                )
            except ValueError:
                duplicate_rejected = True
            else:
                duplicate_rejected = False
        final_selected = history.latest.map_hypothesis
        final_signatures = tuple(
            self._signature(hypothesis.steps) for hypothesis in history.latest.active_hypotheses
        )
        return self._result(
            case=case,
            method=HiddenEventMethod.CHEH,
            pre_signature=(
                self._signature(pre_selected.steps) if pre_selected is not None else None
            ),
            final_signature=(
                self._signature(final_selected.steps) if final_selected is not None else None
            ),
            emitted=final_signatures,
            pre_actor=(pre_selected.responsible_actor_key if pre_selected is not None else None),
            final_actor=(
                final_selected.responsible_actor_key if final_selected is not None else None
            ),
            update_mode="append_only_revision",
            append_only_revision_count=len(history.revisions) - 1,
            duplicate_rejected=duplicate_rejected,
        )

    def _evaluate_orrer(
        self,
        case: HiddenEventGeneratedCase,
        parameters: dict[str, float],
    ) -> HiddenEventCaseResult:
        data = case.model_input
        engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
        history = engine.branch(
            before=data.before,
            after=data.after,
            actor_prior=data.actor_prior,
            unresolved_probability=0.1,
            handoff_fraction=parameters["handoff_fraction"],
        )
        threshold = parameters["retraction_threshold"]
        for actor_evidence in data.initial_evidence:
            history = engine.revise_actor_responsibility(
                history, actor_evidence, retraction_threshold=threshold
            )
        for mechanism_evidence in data.initial_mechanism_evidence:
            history = engine.revise_event_mechanism(
                history, mechanism_evidence, retraction_threshold=threshold
            )
        for role_evidence in data.initial_role_evidence:
            history = engine.revise_role_binding(
                history, role_evidence, retraction_threshold=threshold
            )
        pre_selected = history.latest.map_hypothesis
        reactivated_count = 0
        late_evidence_stream: tuple[HiddenEventEvidence, ...] = (
            *data.late_evidence,
            *data.late_mechanism_evidence,
            *data.late_role_evidence,
        )
        for late_evidence in late_evidence_stream:
            previously_retracted = {
                item.hypothesis_id
                for item in history.latest.hypotheses
                if item.status.value == "retracted"
            }
            history = engine.reactivate_with_evidence(
                history, late_evidence, retraction_threshold=threshold
            )
            reactivated_count += sum(
                item.hypothesis_id in previously_retracted and item.status.value == "active"
                for item in history.latest.hypotheses
            )
        duplicate_rejected = None
        if data.duplicate_submission is not None:
            try:
                engine.reactivate_with_evidence(
                    history,
                    data.duplicate_submission,
                    retraction_threshold=threshold,
                )
            except ValueError:
                duplicate_rejected = True
            else:
                duplicate_rejected = False
        final_selected = history.latest.map_hypothesis
        final_signatures = tuple(
            self._signature(hypothesis.steps) for hypothesis in history.latest.active_hypotheses
        )
        return self._result(
            case=case,
            method=HiddenEventMethod.ORRER,
            pre_signature=(
                self._signature(pre_selected.steps) if pre_selected is not None else None
            ),
            final_signature=(
                self._signature(final_selected.steps) if final_selected is not None else None
            ),
            emitted=final_signatures,
            pre_actor=(pre_selected.responsible_actor_key if pre_selected is not None else None),
            final_actor=(
                final_selected.responsible_actor_key if final_selected is not None else None
            ),
            update_mode="open_world_append_only_reversible_revision",
            append_only_revision_count=len(history.revisions) - 1,
            reactivated_hypothesis_count=reactivated_count,
            duplicate_rejected=duplicate_rejected,
        )

    def _evaluate_bernert(self, case: HiddenEventGeneratedCase) -> HiddenEventCaseResult:
        data = case.model_input
        prediction = BernertRamparany2021SequenceBaseline().predict(
            before=data.before,
            after=data.after,
            known_actor_keys=data.known_actor_keys,
        )
        emitted = tuple(
            self._signature(sequence.steps) for sequence in prediction.possible_sequences
        )
        actor = prediction.entailed_responsible_actor_key
        return self._result(
            case=case,
            method=HiddenEventMethod.BERNERT_RAMPARANY_2021,
            pre_signature=None,
            final_signature=None,
            emitted=emitted,
            pre_actor=actor,
            final_actor=actor,
            update_mode="static_compatible_sequence_set",
            append_only_revision_count=0,
            duplicate_rejected=None,
        )

    def _evaluate_matched_amg(
        self,
        case: HiddenEventGeneratedCase,
        parameters: dict[str, float],
    ) -> HiddenEventCaseResult:
        data = case.model_input
        actor_pre = self._accumulate_actor_evidence(data.actor_prior, data.initial_evidence)
        actor_final = self._accumulate_actor_evidence(actor_pre, data.late_evidence)
        mechanism_prior = {
            EventMechanism.DIRECT_RELOCATION: 0.5,
            EventMechanism.HANDOFF_RELOCATION: 0.5,
        }
        mechanism_pre = self._accumulate_mechanism_evidence(
            mechanism_prior, data.initial_mechanism_evidence
        )
        mechanism_final = self._accumulate_mechanism_evidence(
            mechanism_pre, data.late_mechanism_evidence
        )
        role_keys = tuple(
            ordered_role_key(initiator, recipient)
            for initiator, recipient in product(data.actor_prior, repeat=2)
            if initiator != recipient
        )
        role_prior = {key: 1.0 / len(role_keys) for key in role_keys}
        role_pre = self._accumulate_role_evidence(role_prior, data.initial_role_evidence)
        role_final = self._accumulate_role_evidence(role_pre, data.late_role_evidence)
        power = parameters["evidence_power"]
        pre_prediction = self._matched_amg_prediction(
            data=data,
            actor_belief=self._power_distribution(actor_pre, power),
            mechanism_belief=self._power_distribution(mechanism_pre, power),
            role_belief=self._power_distribution(role_pre, power),
        )
        final_prediction = self._matched_amg_prediction(
            data=data,
            actor_belief=self._power_distribution(actor_final, power),
            mechanism_belief=self._power_distribution(mechanism_final, power),
            role_belief=self._power_distribution(role_final, power),
        )
        pre_signature = self._signature(pre_prediction.selected_sequence.steps)
        final_signature = self._signature(final_prediction.selected_sequence.steps)
        return self._result(
            case=case,
            method=HiddenEventMethod.DAMEN_HOGG_2012_MATCHED,
            pre_signature=pre_signature,
            final_signature=final_signature,
            emitted=(final_signature,),
            pre_actor=pre_prediction.selected_sequence.responsible_actor_key,
            final_actor=final_prediction.selected_sequence.responsible_actor_key,
            update_mode=("full_rerun" if data.family.has_late_evidence else "single_fit"),
            append_only_revision_count=0,
            duplicate_rejected=None,
        )

    def _matched_amg_prediction(
        self,
        *,
        data: HiddenEventCaseInput,
        actor_belief: dict[str, float],
        mechanism_belief: dict[EventMechanism, float],
        role_belief: dict[str, float],
    ) -> AMGConstrainedMAPPrediction:
        role_likelihoods = {
            (initiator, recipient): self._open_probability(
                role_belief[ordered_role_key(initiator, recipient)]
            )
            for initiator, recipient in product(data.actor_prior, repeat=2)
            if initiator != recipient
        }
        return DamenHogg2012AMGMatchedEvidenceBaseline().predict_matched(
            before=data.before,
            after=data.after,
            actor_event_likelihoods={
                actor: self._open_probability(probability)
                for actor, probability in actor_belief.items()
            },
            mechanism_likelihoods={
                mechanism: self._open_probability(probability)
                for mechanism, probability in mechanism_belief.items()
            },
            handoff_role_likelihoods=role_likelihoods,
        )

    def _evaluate_stateless(
        self,
        case: HiddenEventGeneratedCase,
        method: HiddenEventMethod,
        parameters: dict[str, float],
    ) -> HiddenEventCaseResult:
        data = case.model_input
        pre_belief = self._accumulate_actor_evidence(data.actor_prior, data.initial_evidence)
        final_belief = self._accumulate_actor_evidence(pre_belief, data.late_evidence)
        pre_signature, pre_actor, pre_emitted = self._stateless_prediction(
            data=data,
            method=method,
            actor_belief=pre_belief,
            parameters=parameters,
        )
        final_signature, final_actor, final_emitted = self._stateless_prediction(
            data=data,
            method=method,
            actor_belief=final_belief,
            parameters=parameters,
        )
        del pre_emitted
        return self._result(
            case=case,
            method=method,
            pre_signature=pre_signature,
            final_signature=final_signature,
            emitted=final_emitted,
            pre_actor=pre_actor,
            final_actor=final_actor,
            update_mode=("full_rerun" if data.late_evidence else "single_fit"),
            append_only_revision_count=0,
            duplicate_rejected=None,
        )

    def _stateless_prediction(
        self,
        *,
        data: HiddenEventCaseInput,
        method: HiddenEventMethod,
        actor_belief: dict[str, float],
        parameters: dict[str, float],
    ) -> tuple[
        tuple[HiddenEventSignatureStep, ...],
        str,
        tuple[tuple[HiddenEventSignatureStep, ...], ...],
    ]:
        if method == HiddenEventMethod.TOP1_EVENT_GRAPH:
            top1_prediction = Top1EventGraphBaseline().predict(
                before=data.before,
                after=data.after,
                actor_prior=actor_belief,
            )
            signature = self._signature(top1_prediction.steps)
            return signature, top1_prediction.responsible_actor_key, (signature,)
        if method == HiddenEventMethod.INDEPENDENT_CANDIDATES:
            independent_prediction = IndependentEventCandidateBaseline().predict(
                before=data.before,
                after=data.after,
                actor_confidence=actor_belief,
            )
            selected = sorted(
                independent_prediction.candidates,
                key=lambda item: (-item.independent_confidence, item.responsible_actor_key),
            )[0]
            return (
                self._signature(selected.steps),
                selected.responsible_actor_key,
                tuple(self._signature(item.steps) for item in independent_prediction.candidates),
            )
        if method != HiddenEventMethod.DAMEN_HOGG_2012:
            raise ValueError(f"unsupported stateless method: {method}")
        known_belief = self._normalize_known_actor_belief(actor_belief, data.known_actor_keys)
        handoff_likelihood = parameters["handoff_event_likelihood"]
        role_likelihoods = {
            (actor, recipient): self._open_probability(known_belief[recipient])
            for actor, recipient in (
                (data.known_actor_keys[0], data.known_actor_keys[1]),
                (data.known_actor_keys[1], data.known_actor_keys[0]),
            )
        }
        amg_prediction = DamenHogg2012AMGGlobalMAPBaseline().predict(
            before=data.before,
            after=data.after,
            actor_event_likelihoods={
                actor: self._open_probability(probability)
                for actor, probability in known_belief.items()
            },
            direct_event_likelihood=1.0 - handoff_likelihood,
            handoff_event_likelihood=handoff_likelihood,
            handoff_role_likelihoods=role_likelihoods,
        )
        signature = self._signature(amg_prediction.selected_sequence.steps)
        return signature, amg_prediction.selected_sequence.responsible_actor_key, (signature,)

    def _result(
        self,
        *,
        case: HiddenEventGeneratedCase,
        method: HiddenEventMethod,
        pre_signature: tuple[HiddenEventSignatureStep, ...] | None,
        final_signature: tuple[HiddenEventSignatureStep, ...] | None,
        emitted: tuple[tuple[HiddenEventSignatureStep, ...], ...],
        pre_actor: str | None,
        final_actor: str | None,
        update_mode: str,
        append_only_revision_count: int,
        duplicate_rejected: bool | None,
        reactivated_hypothesis_count: int = 0,
    ) -> HiddenEventCaseResult:
        truth = case.evaluator_truth
        return HiddenEventCaseResult(
            case_id=case.model_input.case_id,
            family=case.model_input.family,
            split=case.model_input.split,
            method=method,
            within_closed_known_actor_assumption=truth.within_closed_known_actor_assumption,
            supported=True,
            pre_selected_signature=pre_signature,
            final_selected_signature=final_signature,
            final_emitted_signatures=emitted,
            pre_responsible_actor_key=pre_actor,
            final_responsible_actor_key=final_actor,
            pre_exact_chain=(pre_signature == truth.signature if pre_signature else None),
            final_exact_chain=(final_signature == truth.signature if final_signature else None),
            truth_in_final_emitted_set=truth.signature in emitted,
            pre_responsible_actor_correct=(
                pre_actor == truth.responsible_actor_key if pre_actor is not None else None
            ),
            final_responsible_actor_correct=(
                final_actor == truth.responsible_actor_key if final_actor is not None else None
            ),
            update_mode=update_mode,
            append_only_revision_count=append_only_revision_count,
            reactivated_hypothesis_count=reactivated_hypothesis_count,
            duplicate_submission_rejected=duplicate_rejected,
        )

    @staticmethod
    def _unsupported_result(
        case: HiddenEventGeneratedCase,
        method: HiddenEventMethod,
        reason: str,
    ) -> HiddenEventCaseResult:
        return HiddenEventCaseResult(
            case_id=case.model_input.case_id,
            family=case.model_input.family,
            split=case.model_input.split,
            method=method,
            within_closed_known_actor_assumption=(
                case.evaluator_truth.within_closed_known_actor_assumption
            ),
            supported=False,
            unsupported_reason=reason,
            update_mode="unsupported",
            append_only_revision_count=0,
        )

    @staticmethod
    def _signature(
        steps: Iterable[HiddenEventStep],
    ) -> tuple[HiddenEventSignatureStep, ...]:
        return tuple(
            HiddenEventSignatureStep(
                event_type=step.event_type,
                actor_key=step.actor_key,
                recipient_actor_key=step.recipient_actor_key,
            )
            for step in steps
        )

    @staticmethod
    def _accumulate_actor_evidence(
        prior: dict[str, float],
        evidence: Sequence[ActorResponsibilityEvidence],
    ) -> dict[str, float]:
        belief = dict(prior)
        for item in evidence:
            weighted = {
                actor: belief[actor]
                * item.actor_likelihood_ratios[actor] ** item.effective_sample_weight
                for actor in belief
            }
            total = sum(weighted.values())
            belief = (
                {actor: value / total for actor, value in weighted.items()}
                if total > 0.0
                else dict(prior)
            )
        return belief

    @staticmethod
    def _accumulate_mechanism_evidence(
        prior: dict[EventMechanism, float],
        evidence: Sequence[EventMechanismEvidence],
    ) -> dict[EventMechanism, float]:
        belief = dict(prior)
        for item in evidence:
            weighted = {
                mechanism: belief[mechanism]
                * item.mechanism_likelihood_ratios[mechanism] ** item.effective_sample_weight
                for mechanism in belief
            }
            total = sum(weighted.values())
            belief = {mechanism: value / total for mechanism, value in weighted.items()}
        return belief

    @staticmethod
    def _accumulate_role_evidence(
        prior: dict[str, float],
        evidence: Sequence[RoleBindingEvidence],
    ) -> dict[str, float]:
        belief = dict(prior)
        for item in evidence:
            weighted = {
                role: belief[role]
                * item.ordered_role_likelihood_ratios[role] ** item.effective_sample_weight
                for role in belief
            }
            total = sum(weighted.values())
            belief = {role: value / total for role, value in weighted.items()}
        return belief

    @staticmethod
    def _power_distribution(
        distribution: dict[DistributionKeyT, float], power: float
    ) -> dict[DistributionKeyT, float]:
        weighted = {key: value**power for key, value in distribution.items()}
        total = sum(weighted.values())
        return {key: value / total for key, value in weighted.items()}

    @staticmethod
    def _normalize_known_actor_belief(
        belief: dict[str, float], known_actor_keys: tuple[str, str]
    ) -> dict[str, float]:
        total = sum(belief[actor] for actor in known_actor_keys)
        return {actor: belief[actor] / total for actor in known_actor_keys}

    @staticmethod
    def _open_probability(value: float) -> float:
        return min(0.999, max(0.001, value))

    def _aggregate_method(
        self,
        method: HiddenEventMethod,
        results: Sequence[HiddenEventCaseResult],
    ) -> HiddenEventMethodReport:
        method_results = [result for result in results if result.method == method]
        in_assumption = [
            result
            for result in method_results
            if result.within_closed_known_actor_assumption and result.supported
        ]
        out_assumption = [
            result for result in method_results if not result.within_closed_known_actor_assumption
        ]
        late = [
            result
            for result in in_assumption
            if result.family.has_late_evidence and result.pre_responsible_actor_correct is False
        ]
        decided = [
            result for result in in_assumption if result.final_responsible_actor_key is not None
        ]
        unknown_supported = [result for result in out_assumption if result.supported]
        duplicates = [
            result
            for result in method_results
            if result.family.has_duplicate_submission and result.supported
        ]
        late_supported = [
            result
            for result in in_assumption
            if result.family.has_late_evidence and result.supported
        ]
        return HiddenEventMethodReport(
            method=method,
            in_assumption_case_count=len(in_assumption),
            out_of_assumption_case_count=len(out_assumption),
            unsupported_case_count=sum(not result.supported for result in method_results),
            final_exact_chain_rate=self._boolean_rate(in_assumption, "final_exact_chain"),
            final_truth_set_coverage=self._boolean_rate(
                in_assumption, "truth_in_final_emitted_set"
            ),
            responsibility_decision_coverage=(
                len(decided) / len(in_assumption) if in_assumption else None
            ),
            responsibility_accuracy_when_decided=self._boolean_rate(
                decided, "final_responsible_actor_correct"
            ),
            overall_responsibility_accuracy=self._boolean_rate(
                in_assumption, "final_responsible_actor_correct", none_is_false=True
            ),
            late_responsibility_recovery_rate=self._boolean_rate(
                late, "final_responsible_actor_correct"
            ),
            append_only_revision_rate=(
                sum(result.append_only_revision_count > 0 for result in late_supported)
                / len(late_supported)
                if late_supported
                else None
            ),
            unknown_actor_truth_set_coverage=self._boolean_rate(
                unknown_supported, "truth_in_final_emitted_set"
            ),
            duplicate_submission_rejection_rate=self._boolean_rate(
                duplicates, "duplicate_submission_rejected"
            ),
            reactivation_case_rate=(
                sum(result.reactivated_hypothesis_count > 0 for result in late_supported)
                / len(late_supported)
                if late_supported
                else None
            ),
        )

    @staticmethod
    def _boolean_rate(
        results: Sequence[HiddenEventCaseResult],
        field_name: str,
        *,
        none_is_false: bool = False,
    ) -> float | None:
        if none_is_false:
            return (
                sum(getattr(result, field_name) is True for result in results) / len(results)
                if results
                else None
            )
        available = [
            getattr(result, field_name)
            for result in results
            if getattr(result, field_name) is not None
        ]
        return sum(value is True for value in available) / len(available) if available else None

    @staticmethod
    def _scientific_status(reports: Sequence[HiddenEventMethodReport]) -> str:
        orrer = next(report for report in reports if report.method == HiddenEventMethod.ORRER)
        matched_amg = next(
            report
            for report in reports
            if report.method == HiddenEventMethod.DAMEN_HOGG_2012_MATCHED
        )
        if (
            orrer.final_exact_chain_rate is not None
            and matched_amg.final_exact_chain_rate is not None
            and orrer.final_exact_chain_rate > matched_amg.final_exact_chain_rate
        ):
            return (
                "ORRER held-out exact-chain advantage observed over the matched open-world AMG "
                "adaptation; long-term contamination and action utility remain untested"
            )
        return (
            "ORRER mechanism capability is implemented but superiority over the matched "
            "open-world AMG adaptation is not established; retain the full project scope and "
            "test reversible long-term contamination and action utility next"
        )
