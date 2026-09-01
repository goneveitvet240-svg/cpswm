"""Typed, split-safe configuration for registered Structure Two D0 runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cpswm.contracts import ContractModel

from .project_two_dataset_adapters import D0SyntheticOracleReplayAdapter


class D0SyntheticReplayExperimentConfig(ContractModel):
    """Machine-readable D0 design; it contains no caller-supplied result flags."""

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_version: str = Field(min_length=1)
    adapter: Literal["D0SyntheticOracleReplayAdapter"]
    evidence_stage: str = Field(min_length=1)
    confirmatory: bool
    train_seed_start: int | None = None
    train_seed_count: int = Field(default=0, ge=0)
    validation_seed_start: int
    validation_seed_count: int = Field(gt=0)
    test_seed_start: int
    test_seed_count: int = Field(gt=0)
    steps_per_episode: int = Field(gt=0)
    object_family_bucket_count: int = Field(gt=0)
    development_uuid_seal_secret: str = Field(min_length=1)
    split_keys: tuple[str, ...] = Field(min_length=1)
    truth_store: str = Field(min_length=1)
    external_dataset_selected: bool
    retained_capabilities: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _split_and_scope(self) -> D0SyntheticReplayExperimentConfig:
        if bool(self.train_seed_count) != (self.train_seed_start is not None):
            raise ValueError("train seed start and positive count must be declared together")
        train = set(self.train_seeds)
        validation = set(self.validation_seeds)
        test = set(self.test_seeds)
        if train & validation or train & test or validation & test:
            raise ValueError("configured train/validation/sealed-test seed ranges overlap")
        if self.confirmatory and not train:
            raise ValueError("confirmatory learned-baseline runs require a training split")
        required_split_keys = {
            "household_id",
            "scene_id",
            "object_instance_id",
            "object_family",
        }
        if not required_split_keys.issubset(self.split_keys):
            raise ValueError("D0 config omits a required disjointness split key")
        required_capabilities = {
            "hidden_event_inference",
            "multi_actor_reasoning",
            "open_world_unknowns",
            "reversible_attribution",
            "embodied_execution_feedback",
        }
        if not required_capabilities.issubset(self.retained_capabilities):
            raise ValueError("D0 config narrows a required Structure Two capability")
        if self.truth_store != "separate_evaluator_envelope":
            raise ValueError("D0 evaluator truth must remain in a separate envelope")
        if self.external_dataset_selected:
            raise ValueError("synthetic D0 config cannot claim an external dataset")
        return self

    @property
    def train_seeds(self) -> tuple[int, ...]:
        if self.train_seed_start is None:
            return ()
        return tuple(range(self.train_seed_start, self.train_seed_start + self.train_seed_count))

    @property
    def validation_seeds(self) -> tuple[int, ...]:
        return tuple(
            range(
                self.validation_seed_start,
                self.validation_seed_start + self.validation_seed_count,
            )
        )

    @property
    def test_seeds(self) -> tuple[int, ...]:
        return tuple(range(self.test_seed_start, self.test_seed_start + self.test_seed_count))

    @classmethod
    def load(cls, path: Path) -> D0SyntheticReplayExperimentConfig:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def build_adapter(self) -> D0SyntheticOracleReplayAdapter:
        return D0SyntheticOracleReplayAdapter(
            train_seeds=self.train_seeds,
            validation_seeds=self.validation_seeds,
            test_seeds=self.test_seeds,
            max_steps_per_episode=self.steps_per_episode,
            dataset_version=self.dataset_version,
            object_family_bucket_count=self.object_family_bucket_count,
            sealed_secret=self.development_uuid_seal_secret,
        )


__all__ = ["D0SyntheticReplayExperimentConfig"]
