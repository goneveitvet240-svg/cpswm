"""Versioned M31 benchmark manifest for reproducible long-horizon runs."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, PositiveInt


class EvaluationTrack(StrEnum):
    ORACLE = "oracle"
    CONTROLLED_NOISE = "controlled_noise"
    REAL_PERCEPTION = "real_perception"


class BenchmarkTaskFamily(StrEnum):
    OBJECT_RETRIEVAL = "object_retrieval"
    MEMORY_ACCURACY = "memory_accuracy"
    HABIT_PREDICTION = "habit_prediction"
    MEMORY_CALIBRATION = "memory_calibration"
    ADAPTATION = "adaptation"
    EXPLANATION = "explanation"
    HIDDEN_EVENT_INFERENCE = "hidden_event_inference"
    CONTINUAL_IDENTITY = "continual_identity"
    EMBODIED_UTILITY = "embodied_utility"


class DatasetSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    PUBLIC_TEST = "public_test"
    HIDDEN_TEST = "hidden_test"


class BenchmarkBudget(ContractModel):
    """F0 limits backed by records in the robot-visible simulation stream.

    Query-result and user-question limits belong in a later manifest version
    once those records are part of the evaluated input. Keeping unsupported
    limits here would make a configured number look like measured usage.
    """

    max_selected_observation_actions: NonNegativeInt
    max_selected_verifications: NonNegativeInt

    @model_validator(mode="after")
    def validate_nested_limits(self) -> BenchmarkBudget:
        if self.max_selected_verifications > self.max_selected_observation_actions:
            raise ValueError(
                "max_selected_verifications cannot exceed max_selected_observation_actions"
            )
        return self


class BenchmarkManifest(ContractModel):
    """Everything required to identify one comparable M31 evaluation."""

    manifest_id: str = Field(min_length=1)
    manifest_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    routine_plan_id: UUID
    routine_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_policy_id: str = Field(min_length=1)
    observation_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_target_object_id: UUID
    scheduled_observation_object_id: UUID
    simulator_version: str = Field(min_length=1)
    expected_simulation_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    household_ids: tuple[UUID, ...] = Field(min_length=1)
    person_ids: tuple[UUID, ...] = Field(min_length=1)
    object_instance_ids: tuple[UUID, ...] = Field(min_length=1)
    location_ids: tuple[UUID, ...] = Field(min_length=1)
    duration_days: PositiveInt
    session_duration_hours: float = Field(gt=0.0)
    tracks: tuple[EvaluationTrack, ...] = Field(min_length=1)
    task_families: tuple[BenchmarkTaskFamily, ...] = Field(min_length=1)
    household_splits: dict[UUID, DatasetSplit] = Field(min_length=1)
    random_seed: NonNegativeInt
    budget: BenchmarkBudget
    metric_names: tuple[str, ...] = Field(min_length=1)
    oracle_reader_modules: tuple[str, ...] = (
        "cpswm.system.world_model_simulator",
        "cpswm.system.evaluation_operations",
    )

    @model_validator(mode="after")
    def validate_manifest(self) -> BenchmarkManifest:
        unique_fields = (
            "household_ids",
            "person_ids",
            "object_instance_ids",
            "location_ids",
            "tracks",
            "task_families",
            "metric_names",
        )
        for field_name in unique_fields:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        if set(self.household_splits) != set(self.household_ids):
            raise ValueError("household_splits must assign every and only listed household")
        if any(not name.strip() for name in self.metric_names):
            raise ValueError("metric_names must be non-empty")
        if any(not module.strip() for module in self.oracle_reader_modules):
            raise ValueError("oracle_reader_modules must be non-empty")
        if self.primary_target_object_id not in self.object_instance_ids:
            raise ValueError("primary target object must be listed in the benchmark")
        if self.scheduled_observation_object_id not in self.object_instance_ids:
            raise ValueError("scheduled observation object must be listed in the benchmark")
        return self

    @property
    def content_sha256(self) -> str:
        return self.manifest_sha256

    def _identity_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"manifest_sha256"})
