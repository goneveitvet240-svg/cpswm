"""Split-safe unified episode contract for direction structure three.

Robot-visible episode data and evaluator-only truth are structurally separate.
The split gate groups by household/scene/time lineage, object trajectory, and
nearby video intervals so a model cannot see adjacent frames or the same object
history on both sides of an evaluation boundary.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ContractModel,
    EvidenceChannel,
    ObservationActionType,
    RobotActionOutcome,
    RobotActionType,
)
from cpswm.contracts.base import require_aware
from cpswm.system.reproducibility import content_sha256

DIRECTION_THREE_DATASET_VERSION = "direction-three-episode@0.1"


class DirectionThreeDatasetSplit(StrEnum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    VALIDATION = "validation"
    TEST = "test"


class DirectionThreeRiskLevel(StrEnum):
    ORDINARY = "ordinary"
    PRIVATE = "private"
    FRAGILE = "fragile"
    MEDICATION = "medication"
    HAZARDOUS = "hazardous"


class DirectionThreeTruthDimension(StrEnum):
    IDENTITY = "identity"
    LOCATION = "location"
    PERSON = "person"
    EVENT = "event"
    HABIT = "habit"


class DirectionThreeChannelAvailability(ContractModel):
    """Explicit six-channel availability; missing is never negative evidence."""

    available: dict[EvidenceChannel, bool]

    @model_validator(mode="after")
    def _all_channels_explicit(self) -> DirectionThreeChannelAvailability:
        if set(self.available) != set(EvidenceChannel):
            raise ValueError("direction-three availability must cover all six channels")
        return self


class DirectionThreeVisibleEpisode(ContractModel):
    """One method-visible episode with no evaluator target or oracle state."""

    dataset_version: str = DIRECTION_THREE_DATASET_VERSION
    episode_id: UUID
    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    split: DirectionThreeDatasetSplit
    split_group_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    household_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    trajectory_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    timestamp: datetime
    object_instance_ids: tuple[str, ...] = Field(min_length=1)
    actor_ids: tuple[str, ...] = ()
    activity_ids: tuple[str, ...] = ()
    observed_source_location_ids: tuple[str, ...] = ()
    observed_target_location_ids: tuple[str, ...] = ()
    room_ids: tuple[str, ...] = ()
    container_ids: tuple[str, ...] = ()
    pose_refs: tuple[str, ...] = ()
    visibility: float | None = Field(default=None, ge=0.0, le=1.0)
    occlusion: float | None = Field(default=None, ge=0.0, le=1.0)
    distance_m: float | None = Field(default=None, ge=0.0)
    query_text: str = Field(min_length=1)
    hard_constraints: tuple[str, ...] = ()
    soft_constraints: tuple[str, ...] = ()
    candidate_ids: tuple[UUID, ...] = Field(min_length=2)
    unknown_candidate_id: UUID
    channel_availability: DirectionThreeChannelAvailability
    observation_action: ObservationActionType | None = None
    observation_outcome: str | None = None
    observation_selection_probability: float | None = Field(default=None, gt=0.0, le=1.0)
    execution_action: RobotActionType | None = None
    execution_outcome_distribution: dict[RobotActionOutcome, float] = Field(default_factory=dict)
    risk_level: DirectionThreeRiskLevel = DirectionThreeRiskLevel.ORDINARY
    source_record_refs: tuple[str, ...] = ()

    @field_validator("timestamp")
    @classmethod
    def _aware_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @model_validator(mode="after")
    def _visible_bindings(self) -> DirectionThreeVisibleEpisode:
        if self.dataset_version != DIRECTION_THREE_DATASET_VERSION:
            raise ValueError("unsupported direction-three dataset version")
        if self.frame_end < self.frame_start:
            raise ValueError("frame_end cannot precede frame_start")
        if len(self.object_instance_ids) != len(set(self.object_instance_ids)):
            raise ValueError("object instance ids must be unique within an episode")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("candidate ids must be unique")
        if self.unknown_candidate_id not in self.candidate_ids:
            raise ValueError("candidate support must include the explicit unknown id")
        observation_fields = (
            self.observation_action,
            self.observation_outcome,
            self.observation_selection_probability,
        )
        if any(value is None for value in observation_fields) and any(
            value is not None for value in observation_fields
        ):
            raise ValueError(
                "observation action, outcome, and selection probability must appear together"
            )
        if self.execution_action is None and self.execution_outcome_distribution:
            raise ValueError("execution outcomes require an execution action")
        if self.execution_action is not None and not self.execution_outcome_distribution:
            raise ValueError("execution actions require an outcome distribution")
        if self.execution_outcome_distribution:
            if any(
                not isfinite(value) or value < 0.0 or value > 1.0
                for value in self.execution_outcome_distribution.values()
            ):
                raise ValueError("execution outcome probabilities must be finite and in [0, 1]")
            if abs(sum(self.execution_outcome_distribution.values()) - 1.0) > 1e-6:
                raise ValueError("execution outcome distribution must sum to one")
        return self


class DirectionThreeEvaluatorTruth(ContractModel):
    """Evaluator-only target and five-dimensional world truth."""

    episode_id: UUID
    source_hash: str = Field(min_length=1)
    true_target_candidate_id: UUID | None = None
    target_is_unknown: bool = False
    truth_by_dimension: dict[DirectionThreeTruthDimension, str]
    expected_terminal_outcome: RobotActionOutcome | None = None
    expected_recovery_required: bool = False

    @model_validator(mode="after")
    def _truth_bindings(self) -> DirectionThreeEvaluatorTruth:
        if set(self.truth_by_dimension) != set(DirectionThreeTruthDimension):
            raise ValueError("evaluator truth must cover all five diagnostic dimensions")
        if self.target_is_unknown == (self.true_target_candidate_id is not None):
            raise ValueError(
                "truth must declare exactly one of a known target id or target_is_unknown"
            )
        return self


class DirectionThreeDatasetEntry(ContractModel):
    episode_id: UUID
    split: DirectionThreeDatasetSplit
    split_group_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    household_id: str = Field(min_length=1)
    trajectory_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    source_hash: str = Field(min_length=1)
    visible_content_hash: str = Field(min_length=1)
    evaluator_content_hash: str = Field(min_length=1)


class DirectionThreeDatasetManifest(ContractModel):
    dataset_name: str = Field(min_length=1)
    dataset_version: str = DIRECTION_THREE_DATASET_VERSION
    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    adjacent_frame_exclusion: int = Field(default=96, ge=0)
    entries: tuple[DirectionThreeDatasetEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _manifest_bindings(self) -> DirectionThreeDatasetManifest:
        if self.dataset_version != DIRECTION_THREE_DATASET_VERSION:
            raise ValueError("unsupported direction-three manifest version")
        ids = [entry.episode_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("manifest episode ids must be unique")
        return self


class DirectionThreeEpisodeDataset(ContractModel):
    manifest: DirectionThreeDatasetManifest
    episodes: tuple[DirectionThreeVisibleEpisode, ...] = Field(min_length=1)
    evaluator_store: tuple[DirectionThreeEvaluatorTruth, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _dataset_bindings(self) -> DirectionThreeEpisodeDataset:
        entries = {entry.episode_id: entry for entry in self.manifest.entries}
        episodes = {episode.episode_id: episode for episode in self.episodes}
        truth = {item.episode_id: item for item in self.evaluator_store}
        if len(episodes) != len(self.episodes) or len(truth) != len(self.evaluator_store):
            raise ValueError("episode and evaluator ids must be unique")
        if set(entries) != set(episodes) or set(entries) != set(truth):
            raise ValueError("manifest, visible episodes, and evaluator truth must join exactly")
        for episode_id, episode in episodes.items():
            entry = entries[episode_id]
            evaluator = truth[episode_id]
            if episode.split != entry.split:
                raise ValueError("manifest split must match the visible episode")
            bound_fields = (
                "split_group_id",
                "scene_id",
                "household_id",
                "trajectory_id",
                "video_id",
                "frame_start",
                "frame_end",
            )
            if any(getattr(episode, field) != getattr(entry, field) for field in bound_fields):
                raise ValueError("manifest lineage must match the visible episode")
            if evaluator.source_hash != entry.source_hash:
                raise ValueError("evaluator and manifest source hashes must match")
            if entry.visible_content_hash != content_sha256(episode):
                raise ValueError("visible episode content hash mismatch")
            evaluator_payload = evaluator.model_dump(mode="python")
            if entry.evaluator_content_hash != content_sha256(evaluator_payload):
                raise ValueError("evaluator truth content hash mismatch")
            if (
                evaluator.true_target_candidate_id is not None
                and evaluator.true_target_candidate_id not in episode.candidate_ids
            ):
                raise ValueError("known evaluator target must be in visible candidate support")
        _reject_split_leakage(self.manifest)
        return self

    def visible_episodes(
        self, split: DirectionThreeDatasetSplit
    ) -> tuple[DirectionThreeVisibleEpisode, ...]:
        return tuple(episode for episode in self.episodes if episode.split == split)

    def truth_for(self, episode_id: UUID) -> DirectionThreeEvaluatorTruth:
        return next(item for item in self.evaluator_store if item.episode_id == episode_id)


class DirectionThreeDatasetAudit(ContractModel):
    dataset_version: str
    episode_count: int = Field(ge=0)
    split_counts: dict[DirectionThreeDatasetSplit, int]
    source_counts: dict[str, int]
    risk_counts: dict[DirectionThreeRiskLevel, int]
    unknown_target_count: int = Field(ge=0)
    channel_available_counts: dict[EvidenceChannel, int]
    observation_action_counts: dict[ObservationActionType, int]
    execution_outcome_counts: dict[RobotActionOutcome, int]
    checks_passed: tuple[str, ...]
    ready: bool


def _reject_split_leakage(manifest: DirectionThreeDatasetManifest) -> None:
    entries = manifest.entries
    for field in ("household_id", "scene_id", "split_group_id", "trajectory_id"):
        splits_by_value: dict[str, set[DirectionThreeDatasetSplit]] = {}
        for entry in entries:
            splits_by_value.setdefault(getattr(entry, field), set()).add(entry.split)
        leaked = sorted(value for value, splits in splits_by_value.items() if len(splits) > 1)
        if leaked:
            raise ValueError(f"cross-split {field} leakage: {leaked}")

    for index, left in enumerate(entries):
        for right in entries[index + 1 :]:
            if left.split == right.split or left.video_id != right.video_id:
                continue
            gap = max(
                right.frame_start - left.frame_end,
                left.frame_start - right.frame_end,
            )
            if gap <= manifest.adjacent_frame_exclusion:
                raise ValueError(
                    f"cross-split adjacent video leakage: {left.episode_id} and {right.episode_id}"
                )


def audit_direction_three_dataset(
    dataset: DirectionThreeEpisodeDataset,
) -> DirectionThreeDatasetAudit:
    return DirectionThreeDatasetAudit(
        dataset_version=dataset.manifest.dataset_version,
        episode_count=len(dataset.episodes),
        split_counts=dict(Counter(episode.split for episode in dataset.episodes)),
        source_counts=dict(Counter(episode.source_name for episode in dataset.episodes)),
        risk_counts=dict(Counter(episode.risk_level for episode in dataset.episodes)),
        unknown_target_count=sum(item.target_is_unknown for item in dataset.evaluator_store),
        channel_available_counts={
            channel: sum(
                episode.channel_availability.available[channel] for episode in dataset.episodes
            )
            for channel in EvidenceChannel
        },
        observation_action_counts=dict(
            Counter(
                episode.observation_action
                for episode in dataset.episodes
                if episode.observation_action is not None
            )
        ),
        execution_outcome_counts=dict(
            Counter(
                outcome
                for episode in dataset.episodes
                for outcome, probability in episode.execution_outcome_distribution.items()
                if probability > 0.0
            )
        ),
        checks_passed=(
            "manifest_join_coverage",
            "visible_evaluator_truth_isolation",
            "household_scene_time_group_isolation",
            "trajectory_isolation",
            "adjacent_video_frame_isolation",
            "six_channel_missingness_explicit",
            "content_integrity",
        ),
        ready=True,
    )
