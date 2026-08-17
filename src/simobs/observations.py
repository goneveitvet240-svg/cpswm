"""Synthetic observations after visibility, noise, and missingness."""

from __future__ import annotations

from uuid import UUID

from pydantic import JsonValue, model_validator

from cpswm.contracts.base import BaseRecordMetadata, ContractModel, SourceType


class SyntheticObservation(ContractModel):
    metadata: BaseRecordMetadata
    observation_type: str
    payload: JsonValue
    noise_profile_id: str
    oracle_channel: bool = False
    ground_truth_refs: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_channel(self) -> SyntheticObservation:
        if self.metadata.source_type != SourceType.SIMULATION:
            raise ValueError("SyntheticObservation must have source_type=simulation")
        if self.ground_truth_refs and not self.oracle_channel:
            raise ValueError("non-oracle observations cannot carry ground-truth references")
        return self
