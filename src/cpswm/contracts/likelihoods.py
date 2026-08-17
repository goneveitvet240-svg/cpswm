"""Observation-likelihood contracts shared by M09, M10, M16, and M24."""

from __future__ import annotations

from math import isclose
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EvidenceRef,
    Probability,
    ProbabilityInterval,
    ValidTimeInterval,
)


class Pose3D(ContractModel):
    frame_id: str = Field(min_length=1)
    x: float
    y: float
    z: float
    qx: float
    qy: float
    qz: float
    qw: float

    @model_validator(mode="after")
    def validate_quaternion(self) -> Pose3D:
        norm_sq = self.qx**2 + self.qy**2 + self.qz**2 + self.qw**2
        if not isclose(norm_sq, 1.0, rel_tol=0.0, abs_tol=1e-5):
            raise ValueError("pose quaternion must be normalized")
        return self


class ObservationLikelihoodRequest(ContractModel):
    metadata: BaseRecordMetadata
    hypothesis_ref: UUID
    state_hypothesis: JsonValue
    viewpoint_pose: Pose3D
    sensor_profile_id: str = Field(min_length=1)
    scene_snapshot_id: UUID
    perception_model_version: str = Field(min_length=1)
    observation_space: tuple[str, ...] = Field(min_length=1)
    valid_time: ValidTimeInterval


class ObservationLikelihoodModel(ContractModel):
    metadata: BaseRecordMetadata
    request_id: UUID
    p_visible_given_state: Probability
    p_detect_given_visible_state: Probability
    p_false_positive: Probability
    label_confusion_distribution: dict[str, Probability] = Field(default_factory=dict)
    p_observation_given_state_action: dict[str, Probability]
    uncertainty: ProbabilityInterval | None = None
    calibration_domain: str = Field(min_length=1)
    validity_scope: ValidTimeInterval
    geometry_model_version: str = Field(min_length=1)
    perception_model_version: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def validate_distributions(self) -> ObservationLikelihoodModel:
        if self.label_confusion_distribution:
            total = sum(self.label_confusion_distribution.values())
            if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("label_confusion_distribution must sum to 1")
        total = sum(self.p_observation_given_state_action.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("p_observation_given_state_action must sum to 1")
        return self

    @property
    def p_detect_given_state_action(self) -> float:
        """Geometric visibility times detector response."""

        return self.p_visible_given_state * self.p_detect_given_visible_state
