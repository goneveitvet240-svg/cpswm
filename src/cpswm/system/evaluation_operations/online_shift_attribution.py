"""Held-out single-stream task for online shift detection and attribution.

The three paired D0 cases remain controlled causal diagnostics.  This module
removes the control run and the known change time from candidate input, varies
households/seeds/objects, and includes simultaneous changes.  Labels and split
metadata stay benchmark-side.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import ActorEvidenceTrack, ActorResponsibilityEvidence
from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt, Probability
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.synthetic_routines import (
    RoutineChangeKind,
    RoutineChangeSpec,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import SymbolicWorldModelSimulator

from .d0_shift_scenarios import (
    D0ShiftScenarioConfig,
    D0ShiftScenarioGenerator,
    D0VisibleSimulationRun,
)
from .shift_attribution import IdentifiabilityStatus, ShiftCause


class OnlineShiftSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class OnlineShiftFamily(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    HABIT = "habit"
    OBSERVATION_ACTOR = "observation_actor"
    OBSERVATION_HABIT = "observation_habit"


_FAMILY_CAUSES = {
    OnlineShiftFamily.OBSERVATION: (ShiftCause.OBSERVATION_POLICY,),
    OnlineShiftFamily.ACTOR: (ShiftCause.ACTOR_MIXTURE,),
    OnlineShiftFamily.HABIT: (ShiftCause.OWNER_HABIT_REGIME,),
    OnlineShiftFamily.OBSERVATION_ACTOR: (
        ShiftCause.OBSERVATION_POLICY,
        ShiftCause.ACTOR_MIXTURE,
    ),
    OnlineShiftFamily.OBSERVATION_HABIT: (
        ShiftCause.OBSERVATION_POLICY,
        ShiftCause.OWNER_HABIT_REGIME,
    ),
}


class OnlineShiftSuiteConfig(ContractModel):
    start_time: datetime = datetime(2026, 9, 1, tzinfo=UTC)
    duration_days: PositiveInt = 10
    seeds: tuple[NonNegativeInt, ...] = Field(
        default=(1103, 2207, 3301, 4409, 5519, 6619), min_length=6
    )
    case_id_salt: str = Field(default="online-shift-heldout@0.1", min_length=1)
    shuffle_seed: NonNegativeInt = 20260814

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_suite_design(self) -> OnlineShiftSuiteConfig:
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("online suite seeds must be unique")
        if self.duration_days < 8:
            raise ValueError("online suite needs enough pre/post observations")
        return self


class OnlineShiftCaseInput(ContractModel):
    """The only object a candidate method may read."""

    case_id: UUID
    input_version: str = Field(default="online-shift-input@0.1", min_length=1)
    target_person_id: UUID
    observation_stream: D0VisibleSimulationRun
    actor_evidence: tuple[ActorResponsibilityEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_binding(self) -> OnlineShiftCaseInput:
        detection_ids = {
            result.metadata.record_id for result in self.observation_stream.detection_results
        }
        if any(
            item.source_detection_result_id not in detection_ids for item in self.actor_evidence
        ):
            raise ValueError("online actor evidence must cite the visible stream")
        return self


class OnlineShiftCaseTruth(ContractModel):
    """Evaluator-only change point, causes, family, and held-out split."""

    case_id: UUID
    split: OnlineShiftSplit
    family: OnlineShiftFamily
    change_time: datetime
    true_causes: tuple[ShiftCause, ...] = Field(min_length=1)
    identifiability_status: IdentifiabilityStatus
    acceptable_cause_sets: tuple[tuple[ShiftCause, ...], ...] = Field(min_length=1)
    intervention_available: bool
    scenario_seed: NonNegativeInt
    object_id: UUID

    @field_validator("change_time")
    @classmethod
    def validate_change_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("change_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_truth(self) -> OnlineShiftCaseTruth:
        if len(self.true_causes) != len(set(self.true_causes)):
            raise ValueError("online true causes must be unique")
        if ShiftCause.UNRESOLVED in self.true_causes:
            raise ValueError("online latent causes must be concrete")
        if set(self.true_causes) != set(_FAMILY_CAUSES[self.family]):
            raise ValueError("online family and cause set disagree")
        if not any(
            set(self.true_causes).issubset(set(acceptable))
            for acceptable in self.acceptable_cause_sets
        ):
            raise ValueError("acceptable cause sets must cover the latent causes")
        return self


class OnlineShiftGeneratedCase(ContractModel):
    model_input: OnlineShiftCaseInput
    evaluator_truth: OnlineShiftCaseTruth

    @model_validator(mode="after")
    def validate_binding(self) -> OnlineShiftGeneratedCase:
        if self.model_input.case_id != self.evaluator_truth.case_id:
            raise ValueError("online input and truth case IDs do not match")
        run = self.model_input.observation_stream
        if (
            not run.start_time
            < self.evaluator_truth.change_time
            < (run.start_time + timedelta(days=run.duration_days))
        ):
            raise ValueError("online hidden change time must lie within the stream")
        return self


class OnlineShiftSuite(ContractModel):
    suite_id: UUID
    suite_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generator_version: str = Field(min_length=1)
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[OnlineShiftGeneratedCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suite(self) -> OnlineShiftSuite:
        case_ids = [case.model_input.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("online suite case IDs must be unique")
        payload = self.content_payload()
        if self.suite_content_sha256 != content_sha256(payload):
            raise ValueError("online suite content hash mismatch")
        if self.suite_id != content_uuid("online-shift-suite", payload):
            raise ValueError("online suite ID mismatch")
        return self

    def content_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"suite_id", "suite_content_sha256"})


class OnlineShiftPrediction(ContractModel):
    case_id: UUID
    predicted_change_time: datetime | None = None
    cause_probabilities: dict[ShiftCause, Probability] = Field(min_length=1)
    model_version: str = Field(min_length=1)

    @field_validator("predicted_change_time")
    @classmethod
    def validate_prediction_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("predicted_change_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_probabilities(self) -> OnlineShiftPrediction:
        if ShiftCause.UNRESOLVED in self.cause_probabilities:
            raise ValueError("online causes use independent probabilities, not unresolved")
        return self

    def predicted_causes(self, threshold: float = 0.5) -> frozenset[ShiftCause]:
        return frozenset(
            cause
            for cause, probability in self.cause_probabilities.items()
            if probability >= threshold
        )


class OnlineShiftAttributionCase(ContractModel):
    truth: OnlineShiftCaseTruth
    prediction: OnlineShiftPrediction

    @model_validator(mode="after")
    def validate_binding(self) -> OnlineShiftAttributionCase:
        if self.truth.case_id != self.prediction.case_id:
            raise ValueError("online prediction case ID mismatch")
        return self


class OnlineShiftReport(ContractModel):
    sample_count: int = Field(ge=1)
    change_detection_rate: Probability
    mean_absolute_change_time_error_hours: float = Field(ge=0.0)
    exact_cause_set_accuracy: Probability
    cause_micro_precision: Probability
    cause_micro_recall: Probability
    cause_micro_f1: Probability
    false_owner_habit_change_rate: Probability


class OnlineShiftEvaluator:
    def evaluate(
        self, cases: Sequence[OnlineShiftAttributionCase], *, threshold: float = 0.5
    ) -> OnlineShiftReport:
        if not cases:
            raise ValueError("online evaluation requires cases")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("online cause threshold must lie in [0, 1]")
        detected = [case for case in cases if case.prediction.predicted_change_time]
        errors = [
            abs((case.prediction.predicted_change_time - case.truth.change_time).total_seconds())
            / 3600.0
            for case in detected
            if case.prediction.predicted_change_time is not None
        ]
        predicted = [case.prediction.predicted_causes(threshold) for case in cases]
        truth = [frozenset(case.truth.true_causes) for case in cases]
        true_positive = sum(len(p & t) for p, t in zip(predicted, truth, strict=True))
        false_positive = sum(len(p - t) for p, t in zip(predicted, truth, strict=True))
        false_negative = sum(len(t - p) for p, t in zip(predicted, truth, strict=True))
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        non_habit = [
            prediction
            for prediction, latent in zip(predicted, truth, strict=True)
            if ShiftCause.OWNER_HABIT_REGIME not in latent
        ]
        false_habit = (
            sum(ShiftCause.OWNER_HABIT_REGIME in item for item in non_habit) / len(non_habit)
            if non_habit
            else 0.0
        )
        return OnlineShiftReport(
            sample_count=len(cases),
            change_detection_rate=len(detected) / len(cases),
            mean_absolute_change_time_error_hours=sum(errors) / len(errors) if errors else 0.0,
            exact_cause_set_accuracy=sum(p == t for p, t in zip(predicted, truth, strict=True))
            / len(cases),
            cause_micro_precision=precision,
            cause_micro_recall=recall,
            cause_micro_f1=f1,
            false_owner_habit_change_rate=false_habit,
        )


class OnlineShiftSuiteGenerator:
    generator_version = "online-shift-suite@0.1"

    def generate(self, config: OnlineShiftSuiteConfig | None = None) -> OnlineShiftSuite:
        config = config or OnlineShiftSuiteConfig()
        descriptors = [
            (seed_index, seed, family)
            for seed_index, seed in enumerate(config.seeds)
            for family in OnlineShiftFamily
        ]
        random.Random(config.shuffle_seed).shuffle(descriptors)
        cases = tuple(
            self._case(
                config=config,
                opaque_ordinal=ordinal,
                seed_index=seed_index,
                seed=seed,
                family=family,
            )
            for ordinal, (seed_index, seed, family) in enumerate(descriptors)
        )
        payload = {
            "generator_version": self.generator_version,
            "config_sha256": content_sha256(config),
            "cases": cases,
        }
        return OnlineShiftSuite(
            **payload,
            suite_id=content_uuid("online-shift-suite", payload),
            suite_content_sha256=content_sha256(payload),
        )

    def _case(
        self,
        *,
        config: OnlineShiftSuiteConfig,
        opaque_ordinal: int,
        seed_index: int,
        seed: int,
        family: OnlineShiftFamily,
    ) -> OnlineShiftGeneratedCase:
        scenario = self._scenario_config(config, seed_index, seed)
        d0_generator = D0ShiftScenarioGenerator()
        if family in {
            OnlineShiftFamily.OBSERVATION,
            OnlineShiftFamily.ACTOR,
            OnlineShiftFamily.HABIT,
        }:
            d0_suite = d0_generator.generate(
                scenario, actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE
            )
            cause = _FAMILY_CAUSES[family][0]
            source = next(
                case for case in d0_suite.cases if case.evaluator_truth.true_cause == cause
            )
            stream = source.model_input.shifted_run
            actor_evidence = source.model_input.shifted_actor_evidence
        else:
            stream, actor_evidence = self._combination_stream(
                scenario,
                actor_change=family == OnlineShiftFamily.OBSERVATION_ACTOR,
            )

        case_id = content_uuid(
            "opaque-online-shift-case",
            {
                "salt": config.case_id_salt,
                "shuffle_seed": config.shuffle_seed,
                "opaque_ordinal": opaque_ordinal,
            },
        )
        split = self._split(seed_index, len(config.seeds))
        true_causes = _FAMILY_CAUSES[family]
        return OnlineShiftGeneratedCase(
            model_input=OnlineShiftCaseInput(
                case_id=case_id,
                target_person_id=scenario.owner_id,
                observation_stream=stream,
                actor_evidence=actor_evidence,
            ),
            evaluator_truth=OnlineShiftCaseTruth(
                case_id=case_id,
                split=split,
                family=family,
                change_time=scenario.start_time + timedelta(days=scenario.change_day),
                true_causes=true_causes,
                identifiability_status=IdentifiabilityStatus.IDENTIFIABLE,
                acceptable_cause_sets=(true_causes,),
                intervention_available=False,
                scenario_seed=seed,
                object_id=scenario.object_id,
            ),
        )

    @staticmethod
    def _scenario_config(
        config: OnlineShiftSuiteConfig, seed_index: int, seed: int
    ) -> D0ShiftScenarioConfig:
        base = 10_000 + seed_index * 100
        change_day = 3 + seed_index % (config.duration_days - 6)
        shifted_probability = (0.15, 0.25, 0.35)[seed_index % 3]
        return D0ShiftScenarioConfig(
            suite_name="online-shift-source",
            start_time=config.start_time + timedelta(days=seed_index * 20),
            duration_days=config.duration_days,
            change_day=change_day,
            random_seed=seed,
            paired_noise_seed=seed + 100_000,
            control_selection_probability=0.9,
            shifted_selection_probability=shifted_probability,
            household_id=UUID(int=base + 1),
            owner_id=UUID(int=base + 2),
            guest_id=UUID(int=base + 3),
            object_id=UUID(int=base + 4),
            desk_id=UUID(int=base + 5),
            sofa_id=UUID(int=base + 6),
            primary_target_id=UUID(int=base + 7),
            primary_task_id=UUID(int=base + 8),
        )

    @staticmethod
    def _split(seed_index: int, seed_count: int) -> OnlineShiftSplit:
        if seed_index < seed_count // 2:
            return OnlineShiftSplit.TRAIN
        if seed_index == seed_count // 2:
            return OnlineShiftSplit.VALIDATION
        return OnlineShiftSplit.TEST

    @staticmethod
    def _combination_stream(
        config: D0ShiftScenarioConfig, *, actor_change: bool
    ) -> tuple[D0VisibleSimulationRun, tuple[ActorResponsibilityEvidence, ...]]:
        generator = D0ShiftScenarioGenerator()
        change = RoutineChangeSpec(
            change_id=UUID(int=301 if actor_change else 302),
            kind=(
                RoutineChangeKind.GUEST_CONTAMINATION
                if actor_change
                else RoutineChangeKind.ABRUPT_CHANGE
            ),
            object_instance_id=config.object_id,
            start_day=config.change_day,
            target_location_id=config.sofa_id,
            actor_override_id=config.guest_id if actor_change else None,
        )
        routine_config = generator._routine_config(config, change=change)
        plan = SyntheticRoutineGenerator().generate(routine_config)
        control_policy = generator._policy(
            config,
            policy_id="online-combination-control@0.1",
            selection_probability=config.control_selection_probability,
        )
        shifted_policy = generator._policy(
            config,
            policy_id="online-combination-shift@0.1",
            selection_probability=config.shifted_selection_probability,
        )
        control, shifted = SymbolicWorldModelSimulator().run_paired(
            plan,
            (control_policy, shifted_policy),
            paired_noise_seed=config.paired_noise_seed,
        )
        change_time = config.start_time + timedelta(days=config.change_day)
        stream = generator._splice_visible_run(
            before=control, after=shifted, change_time=change_time
        )
        evidence = generator._actor_evidence(
            simulation=shifted,
            actor_id=config.guest_id if actor_change else config.owner_id,
            config=config,
            track=ActorEvidenceTrack.CONTROLLED_NOISE,
            change_time=change_time,
        )
        visible_detection_ids = {result.metadata.record_id for result in stream.detection_results}
        return stream, tuple(
            item for item in evidence if item.source_detection_result_id in visible_detection_ids
        )
