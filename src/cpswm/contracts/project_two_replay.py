"""Provenance-safe replay contracts for project-two action evaluation.

Evaluator truth is stored in a separate envelope. Model-facing episodes cannot
carry truth-like aliases at their import boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, Probability, ValidTimeInterval, require_aware
from .grounded_search import ExecutionFeedbackRecord
from .habit_learning import (
    ActorResponsibilityEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    OcclusionState,
)
from .hidden_event_evidence import EventMechanism, EventMechanismEvidence, RoleBindingEvidence

PROJECT_TWO_REPLAY_SCHEMA_VERSION = "0.2.0"
TRUTH_FIELD_ALIASES = frozenset(
    {
        "true_actor",
        "true_mechanism",
        "true_location",
        "true_location_after",
        "true_owner_habit_location",
        "latent_state",
        "event_chain_truth",
        "oracle_truth",
        "evaluator_truth",
        "ground_truth",
    }
)


class ProjectTwoDataMaturity(StrEnum):
    D0_SYNTHETIC_ORACLE = "d0_synthetic_oracle"
    D1_SIMULATOR_ANNOTATED_REPLAY = "d1_simulator_annotated_replay"
    D2_REAL_PERCEPTION_REPLAY = "d2_real_perception_replay"
    D3_HOUSEHOLD_EXECUTION = "d3_household_execution"
    D4_EMBODIED_ROBOT_EXECUTION = "d4_embodied_robot_execution"


class ProjectTwoDatasetSplit(StrEnum):
    VALIDATION = "validation"
    TEST = "test"


class ReplayFieldAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"


class PerceptionModality(StrEnum):
    RGB = "rgb"
    RGBD = "rgbd"


class PerceptionFrameReference(ContractModel):
    """Immutable reference to raw sensor material; pixels stay outside JSONL."""

    frame_id: str = Field(min_length=1)
    timestamp: datetime
    modality: PerceptionModality
    rgb_uri: str = Field(min_length=1)
    depth_uri: str | None = None
    sensor_id: str = Field(min_length=1)
    rgb_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    depth_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("timestamp")
    @classmethod
    def _frame_aware(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @model_validator(mode="after")
    def _depth_required_for_rgbd(self) -> PerceptionFrameReference:
        if self.modality is PerceptionModality.RGBD and not self.depth_uri:
            raise ValueError("RGB-D frame requires depth_uri")
        if self.modality is PerceptionModality.RGB and self.depth_uri is not None:
            raise ValueError("RGB-only frame cannot carry depth_uri")
        return self


class ObjectTrackObservation(ContractModel):
    """Detector/tracker output retained as visible evidence, never evaluator truth."""

    frame_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    object_instance_id: UUID
    object_category: str = Field(min_length=1)
    detection_confidence: Probability
    visibility_probability: Probability
    occlusion_state: OcclusionState
    bounding_box_xyxy: tuple[float, float, float, float] | None = None


class ProjectTwoReplayStep(ContractModel):
    """One time-ordered, model-visible replay unit; never contains truth."""

    step_id: UUID
    timestamp: datetime
    valid_time: ValidTimeInterval
    object_instance_id: UUID
    object_category: str = Field(min_length=1)
    before: ObservationDetectionResult | None = None
    after: ObservationDetectionResult | None = None
    source_location_id: UUID | None = None
    attempted_location_id: UUID | None = None
    observed_destination_location_id: UUID | None = None
    visibility_probability: Probability
    occlusion_state: OcclusionState
    detection_confidence: Probability | None = None
    actor_evidence: ActorResponsibilityEvidence | None = None
    mechanism_evidence: EventMechanismEvidence | None = None
    ordered_role_evidence: RoleBindingEvidence | None = None
    execution_feedback: tuple[ExecutionFeedbackRecord, ...] = ()
    observation_opportunity: ObservationOpportunityRecord | None = None
    action_opportunity: bool = True
    unavailable_fields: tuple[str, ...] = ()
    perception_frames: tuple[PerceptionFrameReference, ...] = ()
    object_tracks: tuple[ObjectTrackObservation, ...] = ()

    @field_validator("timestamp")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @model_validator(mode="after")
    def _semantic_checks(self) -> ProjectTwoReplayStep:
        if not self.valid_time.contains(self.timestamp):
            raise ValueError("step timestamp must lie inside valid_time")
        if self.after is not None and self.before is None:
            raise ValueError("after observation requires a before observation")
        if self.before is not None and self.source_location_id != self.before.detected_location_id:
            raise ValueError("source_location_id must match the visible before observation")
        for feedback in self.execution_feedback:
            if feedback.attempted_location_id != self.attempted_location_id:
                raise ValueError("feedback attempted location must match replay attempted_location")
        # Success probability cannot synthesize a certain landing point.
        if self.observed_destination_location_id is not None:
            if (
                self.after is None
                or self.after.detected_location_id != self.observed_destination_location_id
            ):
                raise ValueError("observed destination must be supported by a visible detection")
        frame_ids = {frame.frame_id for frame in self.perception_frames}
        if len(frame_ids) != len(self.perception_frames):
            raise ValueError("duplicate perception frame id")
        if any(track.frame_id not in frame_ids for track in self.object_tracks):
            raise ValueError("object track must reference a perception frame")
        if any(track.object_instance_id != self.object_instance_id for track in self.object_tracks):
            raise ValueError("object track instance must match replay step")
        return self


class ProjectTwoReplayEpisode(ContractModel):
    episode_id: UUID
    household_id: UUID
    scene_id: str = Field(min_length=1)
    session_id: UUID
    trace_id: UUID
    object_family: str = Field(min_length=1)
    owner_actor_key: str = Field(min_length=1)
    resident_actor_keys: tuple[str, ...] = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: tuple[str, ...] = Field(min_length=1)
    maturity: ProjectTwoDataMaturity
    split: ProjectTwoDatasetSplit
    steps: tuple[ProjectTwoReplayStep, ...] = Field(min_length=1)
    field_availability: dict[str, ReplayFieldAvailability] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _episode_checks(self) -> ProjectTwoReplayEpisode:
        if self.owner_actor_key not in self.resident_actor_keys:
            raise ValueError("owner actor must be present in resident_actor_keys")
        if len(set(self.resident_actor_keys)) != len(self.resident_actor_keys):
            raise ValueError("resident_actor_keys must be unique")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("duplicate replay step id")
        if [step.timestamp for step in self.steps] != sorted(step.timestamp for step in self.steps):
            raise ValueError("replay steps must preserve timestamp order")
        feedback_ids = [
            item.metadata.record_id for step in self.steps for item in step.execution_feedback
        ]
        if len(feedback_ids) != len(set(feedback_ids)):
            raise ValueError("duplicate execution feedback record id")
        for step in self.steps:
            for record in (step.before, step.after, *step.execution_feedback):
                if record is None:
                    continue
                meta = record.metadata
                if (meta.household_id, meta.session_id, meta.trace_id) != (
                    self.household_id,
                    self.session_id,
                    self.trace_id,
                ):
                    raise ValueError("record identity does not match replay episode")
        reject_truth_leakage(self.model_dump(mode="python"))
        return self


class ProjectTwoReplayManifestEntry(ContractModel):
    episode_id: UUID
    household_id: UUID
    scene_id: str
    object_instance_id: UUID
    object_family: str
    split: ProjectTwoDatasetSplit
    maturity: ProjectTwoDataMaturity
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectTwoReplayDatasetManifest(ContractModel):
    schema_name: str = "cpswm.ProjectTwoReplayDatasetManifest"
    schema_version: str = PROJECT_TWO_REPLAY_SCHEMA_VERSION
    dataset_id: UUID
    dataset_version: str = Field(min_length=1)
    created_at: datetime
    entries: tuple[ProjectTwoReplayManifestEntry, ...] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def _created_aware(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")

    @model_validator(mode="after")
    def _split_firewall(self) -> ProjectTwoReplayDatasetManifest:
        if self.schema_version != PROJECT_TWO_REPLAY_SCHEMA_VERSION:
            raise ValueError("unsupported replay manifest schema version")
        if len({entry.episode_id for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate episode id in manifest")
        for field in (
            "household_id",
            "scene_id",
            "object_instance_id",
            "object_family",
        ):
            validation = {
                getattr(e, field)
                for e in self.entries
                if e.split is ProjectTwoDatasetSplit.VALIDATION
            }
            test = {
                getattr(e, field) for e in self.entries if e.split is ProjectTwoDatasetSplit.TEST
            }
            if validation & test:
                raise ValueError(f"cross-split {field} leakage")
        return self


class ProjectTwoEvaluatorStepTruth(ContractModel):
    step_id: UUID
    true_actor: str = Field(min_length=1)
    true_mechanism: EventMechanism
    true_location: UUID
    true_owner_habit_location: UUID
    event_chain_truth: tuple[str, ...] = Field(min_length=1)


class ProjectTwoEvaluatorTruthEnvelope(ContractModel):
    """Evaluator-only store; method adapters must never accept this type."""

    episode_id: UUID
    dataset_version: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_by_step: dict[UUID, ProjectTwoEvaluatorStepTruth] = Field(min_length=1)


def reject_truth_leakage(payload: Any, path: str = "model_input") -> None:
    """Reject evaluator/oracle aliases recursively before model dispatch."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).strip().lower()
            if normalized in TRUTH_FIELD_ALIASES or normalized.startswith("oracle_"):
                raise ValueError(f"evaluator truth leakage at {path}.{key}")
            reject_truth_leakage(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            reject_truth_leakage(value, f"{path}[{index}]")


__all__ = [
    name
    for name in globals()
    if name.startswith("ProjectTwo")
    or name
    in {
        "PROJECT_TWO_REPLAY_SCHEMA_VERSION",
        "ReplayFieldAvailability",
        "PerceptionModality",
        "PerceptionFrameReference",
        "ObjectTrackObservation",
        "TRUTH_FIELD_ALIASES",
        "reject_truth_leakage",
    }
]
