"""Four-level adapter surface and the D0 replay pilot.

No external dataset is selected here. D1-D4 are explicit adapter interfaces and
remain unavailable until the user chooses a source or collection route.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cpswm.contracts import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    ExecutionFeedbackRecord,
    ObservationOpportunityRecord,
    OcclusionState,
    ProjectTwoDataMaturity,
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayDatasetManifest,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayManifestEntry,
    ProjectTwoReplayStep,
    ReplayFieldAvailability,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    ValidTimeInterval,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    ActionGeneratedCase,
    StructureTwoActionScenarioGenerator,
    new_sealed_secret,
)
from cpswm.system.reproducibility import content_sha256


class ProjectTwoDatasetAdapter(ABC):
    maturity: ProjectTwoDataMaturity

    @abstractmethod
    def build(self) -> ProjectTwoReplayDataset:
        raise NotImplementedError


class UnavailableProjectTwoDatasetAdapter(ProjectTwoDatasetAdapter):
    """Explicit D1-D4 placeholder; missing fields never shrink the contract."""

    def __init__(self, maturity: ProjectTwoDataMaturity, reason: str) -> None:
        self.maturity = maturity
        self.reason = reason

    def build(self) -> ProjectTwoReplayDataset:
        raise RuntimeError(f"{self.maturity.value} unavailable: {self.reason}")


class D0SyntheticOracleReplayAdapter(ProjectTwoDatasetAdapter):
    maturity = ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE

    def __init__(
        self,
        *,
        validation_seeds: tuple[int, ...] = (101, 103),
        test_seeds: tuple[int, ...] = (211, 223),
        max_steps_per_episode: int = 32,
        sealed_secret: str | None = None,
    ) -> None:
        if set(validation_seeds) & set(test_seeds):
            raise ValueError("validation and test seeds must be disjoint")
        self.validation_seeds = validation_seeds
        self.test_seeds = test_seeds
        self.max_steps_per_episode = max_steps_per_episode
        self.generator = StructureTwoActionScenarioGenerator(
            sealed_secret=sealed_secret or new_sealed_secret(),
            include_open_world_unknown_events=True,
        )

    def build(self) -> ProjectTwoReplayDataset:
        pairs = [
            *((seed, ProjectTwoDatasetSplit.VALIDATION) for seed in self.validation_seeds),
            *((seed, ProjectTwoDatasetSplit.TEST) for seed in self.test_seeds),
        ]
        converted = [
            self._convert(self.generator.generate(seed), split, seed) for seed, split in pairs
        ]
        episodes = tuple(item[0] for item in converted)
        truth = tuple(item[1] for item in converted)
        entries = tuple(
            ProjectTwoReplayManifestEntry(
                episode_id=item.episode_id,
                household_id=item.household_id,
                scene_id=item.scene_id,
                object_instance_id=item.steps[0].object_instance_id,
                object_family=item.object_family,
                split=item.split,
                maturity=item.maturity,
                source_hash=item.source_hash,
                visible_content_hash=content_sha256(item),
            )
            for item in episodes
        )
        manifest = ProjectTwoReplayDatasetManifest(
            dataset_id=uuid4(),
            dataset_version="project-two-d0-pilot@0.2",
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
            entries=entries,
        )
        return ProjectTwoReplayDataset(manifest=manifest, episodes=episodes, evaluator_store=truth)

    def _convert(
        self, case: ActionGeneratedCase, split: ProjectTwoDatasetSplit, seed: int
    ) -> tuple[ProjectTwoReplayEpisode, ProjectTwoEvaluatorTruthEnvelope]:
        visible = case.visible
        anchor = self._anchor_metadata(case)
        source_hash = content_sha256(f"project-two-d0-pilot|{seed}|{visible.case_id}|{split.value}")
        steps: list[ProjectTwoReplayStep] = []
        truths: dict[UUID, ProjectTwoEvaluatorStepTruth] = {}
        for obs in visible.days[: self.max_steps_per_episode]:
            step_id = uuid4()
            truth = case.truth_by_day[obs.day]
            timestamp = (
                obs.after.detection_time
                if obs.after is not None and obs.after.detection_time is not None
                else datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=obs.day)
            )
            opportunity = self._opportunity(case, obs, timestamp)
            attempted = obs.after.detected_location_id if obs.after is not None else None
            feedback = ()
            if attempted is not None:
                success = 0.8 if obs.day % 3 else 0.25
                feedback = (self._feedback(case, obs.day, timestamp, attempted, success),)
            steps.append(
                ProjectTwoReplayStep(
                    step_id=step_id,
                    timestamp=timestamp,
                    valid_time=ValidTimeInterval(
                        start=timestamp, end=timestamp + timedelta(hours=1)
                    ),
                    object_instance_id=visible.object_instance_id,
                    object_category="household_object",
                    before=obs.before,
                    after=obs.after,
                    source_location_id=(obs.before.detected_location_id if obs.before else None),
                    attempted_location_id=attempted,
                    # No post-action detector is present in D0. Even when the
                    # executor reports high success probability, a certain
                    # observed landing point is unavailable rather than copied
                    # from the pre-action transition endpoint.
                    observed_destination_location_id=None,
                    visibility_probability=0.85 if obs.after is not None else 0.35,
                    occlusion_state=OcclusionState.CLEAR
                    if obs.after is not None
                    else OcclusionState.UNKNOWN,
                    detection_confidence=0.9 if obs.after is not None else None,
                    actor_evidence=obs.actor_evidence,
                    mechanism_evidence=obs.mechanism_evidence,
                    ordered_role_evidence=obs.role_evidence,
                    execution_feedback=feedback,
                    observation_opportunity=opportunity,
                    unavailable_fields=(
                        "real_sensor_calibration",
                        "robot_pose_covariance",
                        "post_action_destination_observation",
                    ),
                )
            )
            truths[step_id] = ProjectTwoEvaluatorStepTruth(
                step_id=step_id,
                true_actor=truth.true_actor,
                true_mechanism=truth.mechanism,
                true_location=truth.true_location_after,
                true_owner_habit_location=truth.true_owner_habit_location,
                event_chain_truth=("pick_up", "carry", "place"),
            )
        episode = ProjectTwoReplayEpisode(
            episode_id=visible.case_id,
            household_id=anchor.household_id,
            scene_id=f"scene-{split.value}-{seed}",
            session_id=anchor.session_id,
            trace_id=anchor.trace_id,
            object_family=f"family-{split.value}-{seed}",
            owner_actor_key=visible.owner_actor,
            resident_actor_keys=(visible.owner_actor, visible.guest_actor, "unknown_actor"),
            dataset_version="project-two-d0-pilot@0.2",
            source_uri=f"d0://sealed/{visible.case_id}",
            source_hash=source_hash,
            provenance=(
                "generated:StructureTwoActionScenarioGenerator",
                "adapter:D0SyntheticOracleReplayAdapter",
            ),
            maturity=self.maturity,
            split=split,
            steps=tuple(steps),
            field_availability={
                "actor_evidence": ReplayFieldAvailability.PARTIAL,
                "mechanism_evidence": ReplayFieldAvailability.PARTIAL,
                "ordered_role_evidence": ReplayFieldAvailability.PARTIAL,
                "real_sensor_calibration": ReplayFieldAvailability.UNAVAILABLE,
                "post_action_destination_observation": ReplayFieldAvailability.UNAVAILABLE,
                "robot_pose_covariance": ReplayFieldAvailability.UNAVAILABLE,
            },
        )
        evaluator_payload = {
            "episode_id": episode.episode_id,
            "dataset_version": episode.dataset_version,
            "source_hash": source_hash,
            "truth_by_step": truths,
        }
        envelope = ProjectTwoEvaluatorTruthEnvelope(
            episode_id=episode.episode_id,
            dataset_version=episode.dataset_version,
            source_hash=source_hash,
            evaluator_content_hash=content_sha256(evaluator_payload),
            truth_by_step=truths,
        )
        return episode, envelope

    @staticmethod
    def _opportunity(
        case: ActionGeneratedCase, obs, timestamp: datetime
    ) -> ObservationOpportunityRecord:
        anchor = D0SyntheticOracleReplayAdapter._anchor_metadata(case)
        opportunity_id = obs.after.observation_opportunity_id if obs.after is not None else uuid4()
        return ObservationOpportunityRecord(
            metadata=anchor.model_copy(
                update={
                    "record_id": opportunity_id,
                    "schema_name": "cpswm.ObservationOpportunityRecord",
                    "recorded_time": timestamp,
                }
            ),
            observation_action_id=opportunity_id,
            opportunity_time=timestamp,
            selected=True,
            selection_probability=0.8,
            p_visible_given_state=0.85,
            p_detect_given_visible=0.9,
            likelihood_model_id="d0-visible@0.2",
        )

    @staticmethod
    def _feedback(
        case: ActionGeneratedCase, day: int, timestamp: datetime, attempted: UUID, success: float
    ) -> ExecutionFeedbackRecord:
        anchor = D0SyntheticOracleReplayAdapter._anchor_metadata(case)
        meta = BaseRecordMetadata(
            schema_name="cpswm.ExecutionFeedbackRecord",
            schema_version="0.1.0",
            household_id=anchor.household_id,
            session_id=anchor.session_id,
            trace_id=anchor.trace_id,
            recorded_time=timestamp + timedelta(minutes=20),
            source_type=SourceType.ACTION,
            source_id="d0-replay-executor",
        )
        return ExecutionFeedbackRecord(
            metadata=meta,
            action_id=uuid4(),
            action_type=RobotActionType.PLACE,
            target_entity=EntityRef(
                entity_id=case.visible.object_instance_id, entity_type=EntityType.OBJECT_INSTANCE
            ),
            attempted_location_id=attempted,
            valid_time=ValidTimeInterval(
                start=meta.recorded_time, end=meta.recorded_time + timedelta(minutes=1)
            ),
            outcome_distribution={
                RobotActionOutcome.SUCCESS: success,
                RobotActionOutcome.OBJECT_SLIPPED: 1.0 - success,
            },
            task_goal_satisfied_probability=min(success, 0.7),
        )

    @staticmethod
    def _anchor_metadata(case: ActionGeneratedCase) -> BaseRecordMetadata:
        for day in case.visible.days:
            for detection in (day.before, day.after):
                if detection is not None:
                    return detection.metadata
        raise ValueError("D0 case has no robot-visible metadata anchor")


def adapter_tiers() -> dict[ProjectTwoDataMaturity, type[ProjectTwoDatasetAdapter]]:
    return {
        ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE: D0SyntheticOracleReplayAdapter,
        ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY: UnavailableProjectTwoDatasetAdapter,
        ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY: UnavailableProjectTwoDatasetAdapter,
        ProjectTwoDataMaturity.D3_HOUSEHOLD_EXECUTION: UnavailableProjectTwoDatasetAdapter,
        ProjectTwoDataMaturity.D4_EMBODIED_ROBOT_EXECUTION: UnavailableProjectTwoDatasetAdapter,
    }


__all__ = [
    "D0SyntheticOracleReplayAdapter",
    "ProjectTwoDatasetAdapter",
    "UnavailableProjectTwoDatasetAdapter",
    "adapter_tiers",
]
