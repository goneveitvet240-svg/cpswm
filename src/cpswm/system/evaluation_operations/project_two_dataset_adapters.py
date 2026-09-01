"""Four-level adapter surface and the D0 replay pilot.

No external dataset is selected here. D1-D4 are explicit adapter interfaces and
remain unavailable until the user chooses a source or collection route.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import combinations
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts import (
    BaseRecordMetadata,
    DetectionFailureReason,
    EntityRef,
    EntityType,
    EvidenceProductionMode,
    ExecutionFeedbackRecord,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
    OpenSetEvidenceSupport,
    ProjectTwoDataMaturity,
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayDatasetManifest,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayManifestEntry,
    ProjectTwoReplayStep,
    ReplayContractCompatibility,
    ReplayFieldAvailability,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    UnifiedEvidenceContract,
    ValidTimeInterval,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    ActionDayObservation,
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


class SuppliedReplayDatasetAdapter(ProjectTwoDatasetAdapter):
    """Executable D1/D2 import boundary for user-selected replay sources.

    It accepts the same typed ``ProjectTwoReplayEpisode`` and evaluator-only
    truth envelopes as D0.  Dataset-specific parsing stays outside the inference
    stack and must finish before this firewall is crossed.
    """

    def __init__(
        self,
        *,
        maturity: ProjectTwoDataMaturity,
        dataset_version: str,
        episodes: Sequence[ProjectTwoReplayEpisode],
        evaluator_store: Sequence[ProjectTwoEvaluatorTruthEnvelope],
        adapter_provenance: str,
    ) -> None:
        if maturity not in {
            ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
            ProjectTwoDataMaturity.D0_5_SEMI_SYNTHETIC,
            ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
            ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
        }:
            raise ValueError("supplied replay adapter requires D0-development through D2")
        if not episodes or not evaluator_store:
            raise ValueError("supplied adapter requires visible episodes and separate truth")
        if not adapter_provenance.strip():
            raise ValueError("adapter provenance is required")
        self.maturity = maturity
        self.dataset_version = dataset_version
        self.episodes = tuple(episodes)
        self.evaluator_store = tuple(evaluator_store)
        self.adapter_provenance = adapter_provenance

    def build(self) -> ProjectTwoReplayDataset:
        if any(item.maturity is not self.maturity for item in self.episodes):
            raise ValueError("every replay episode must declare the adapter maturity")
        if any(item.dataset_version != self.dataset_version for item in self.episodes):
            raise ValueError("episode dataset version does not match adapter")
        truth_by_id = {item.episode_id: item for item in self.evaluator_store}
        if set(truth_by_id) != {item.episode_id for item in self.episodes}:
            raise ValueError("visible replay and evaluator store episode ids must match")
        for episode in self.episodes:
            truth = truth_by_id[episode.episode_id]
            if (
                truth.dataset_version != episode.dataset_version
                or truth.source_hash != episode.source_hash
            ):
                raise ValueError("truth envelope provenance does not match visible replay")
        entries = tuple(
            ProjectTwoReplayManifestEntry(
                episode_id=item.episode_id,
                household_id=item.household_id,
                scene_id=item.scene_id,
                object_instance_id=item.steps[0].object_instance_id,
                object_family=item.object_family,
                split=item.split,
                maturity=item.maturity,
                source_evidence_maturity=item.source_evidence_maturity,
                unified_evidence_record_ids=tuple(
                    step.unified_evidence.metadata.record_id
                    for step in item.steps
                    if step.unified_evidence is not None
                ),
                source_hash=item.source_hash,
                visible_content_hash=content_sha256(item),
            )
            for item in self.episodes
        )
        manifest = ProjectTwoReplayDatasetManifest(
            dataset_id=uuid5(
                NAMESPACE_URL,
                f"{self.dataset_version}|{self.adapter_provenance}|"
                + "|".join(sorted(item.source_hash for item in self.episodes)),
            ),
            dataset_version=self.dataset_version,
            created_at=min(step.timestamp for item in self.episodes for step in item.steps),
            entries=entries,
        )
        return ProjectTwoReplayDataset(
            manifest=manifest,
            episodes=self.episodes,
            evaluator_store=self.evaluator_store,
        )


class D1SimulatorAnnotatedReplayAdapter(SuppliedReplayDatasetAdapter):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            maturity=ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
            **kwargs,
        )


class D2RealPerceptionReplayAdapter(SuppliedReplayDatasetAdapter):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            maturity=ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
            **kwargs,
        )


class D0SyntheticOracleReplayAdapter(ProjectTwoDatasetAdapter):
    maturity = ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE

    def __init__(
        self,
        *,
        train_seeds: tuple[int, ...] = (),
        validation_seeds: tuple[int, ...] = (101, 103),
        test_seeds: tuple[int, ...] = (211, 223),
        max_steps_per_episode: int = 32,
        dataset_version: str = "project-two-d0-pilot@0.2",
        object_family_bucket_count: int = 1,
        sealed_secret: str | None = None,
        scenario_duration_days: int = 32,
        guest_window: tuple[int, int] = (7, 14),
        abrupt_day: int = 17,
        recurrence_day: int = 26,
        observation_coverage: float = 0.7,
        unknown_event_days: tuple[int, ...] = (1,),
    ) -> None:
        if not validation_seeds or not test_seeds:
            raise ValueError("validation and test seeds must both be non-empty")
        seed_sets = {
            ProjectTwoDatasetSplit.TRAIN: set(train_seeds),
            ProjectTwoDatasetSplit.VALIDATION: set(validation_seeds),
            ProjectTwoDatasetSplit.TEST: set(test_seeds),
        }
        for left, right in combinations(ProjectTwoDatasetSplit, 2):
            if seed_sets[left] & seed_sets[right]:
                raise ValueError(f"{left.value} and {right.value} seeds must be disjoint")
        if max_steps_per_episode < 1:
            raise ValueError("max_steps_per_episode must be positive")
        if not dataset_version.strip():
            raise ValueError("dataset_version must be non-empty")
        if object_family_bucket_count < 1:
            raise ValueError("object_family_bucket_count must be positive")
        self.train_seeds = train_seeds
        self.validation_seeds = validation_seeds
        self.test_seeds = test_seeds
        self.max_steps_per_episode = max_steps_per_episode
        self.dataset_version = dataset_version
        self.object_family_bucket_count = object_family_bucket_count
        self.generator = StructureTwoActionScenarioGenerator(
            duration_days=scenario_duration_days,
            guest_window=guest_window,
            abrupt_day=abrupt_day,
            recurrence_day=recurrence_day,
            observation_coverage=observation_coverage,
            sealed_secret=sealed_secret or new_sealed_secret(),
            include_open_world_unknown_events=True,
            unknown_event_days=unknown_event_days,
        )

    def build(self) -> ProjectTwoReplayDataset:
        pairs = [
            *((seed, ProjectTwoDatasetSplit.TRAIN) for seed in self.train_seeds),
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
                source_evidence_maturity=item.source_evidence_maturity,
                unified_evidence_record_ids=tuple(
                    step.unified_evidence.metadata.record_id
                    for step in item.steps
                    if step.unified_evidence is not None
                ),
                source_hash=item.source_hash,
                visible_content_hash=content_sha256(item),
            )
            for item in episodes
        )
        manifest = ProjectTwoReplayDatasetManifest(
            dataset_id=uuid5(NAMESPACE_URL, self.dataset_version),
            dataset_version=self.dataset_version,
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
            entries=entries,
        )
        return ProjectTwoReplayDataset(manifest=manifest, episodes=episodes, evaluator_store=truth)

    def _convert(
        self, case: ActionGeneratedCase, split: ProjectTwoDatasetSplit, seed: int
    ) -> tuple[ProjectTwoReplayEpisode, ProjectTwoEvaluatorTruthEnvelope]:
        visible = case.visible
        anchor = self._anchor_metadata(case)
        source_hash = content_sha256(
            f"{self.dataset_version}|{seed}|{visible.case_id}|{split.value}"
        )
        steps: list[ProjectTwoReplayStep] = []
        truths: dict[UUID, ProjectTwoEvaluatorStepTruth] = {}
        for obs in visible.days[: self.max_steps_per_episode]:
            step_id = uuid5(visible.case_id, f"replay-step:{obs.day}")
            truth = case.truth_by_day[obs.day]
            timestamp = (
                obs.after.detection_time
                if obs.after is not None and obs.after.detection_time is not None
                else datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=obs.day)
            )
            opportunity = self._opportunity(case, obs, timestamp)
            unified_evidence = self._unified_evidence(
                case=case,
                obs=obs,
                timestamp=timestamp,
                opportunity=opportunity,
            )
            attempted = obs.after.detected_location_id if obs.after is not None else None
            feedback: tuple[ExecutionFeedbackRecord, ...] = ()
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
                    unified_evidence=unified_evidence,
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
            object_family=(f"family-{split.value}-{seed % self.object_family_bucket_count:02d}"),
            owner_actor_key=visible.owner_actor,
            resident_actor_keys=(visible.owner_actor, visible.guest_actor, "unknown_actor"),
            dataset_version=self.dataset_version,
            source_uri=f"d0://sealed/{visible.case_id}",
            source_hash=source_hash,
            provenance=(
                "generated:StructureTwoActionScenarioGenerator",
                "adapter:D0SyntheticOracleReplayAdapter",
                f"family_bucket_count:{self.object_family_bucket_count}",
            ),
            maturity=self.maturity,
            source_evidence_maturity=self.maturity,
            contract_compatibility=ReplayContractCompatibility.FULL_REPLAY_CONTRACT,
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
        case: ActionGeneratedCase, obs: ActionDayObservation, timestamp: datetime
    ) -> ObservationOpportunityRecord:
        anchor = D0SyntheticOracleReplayAdapter._anchor_metadata(case)
        opportunity_id = (
            obs.after.observation_opportunity_id
            if obs.after is not None
            else uuid5(case.visible.case_id, f"observation-opportunity:{obs.day}")
        )
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
    def _unified_evidence(
        *,
        case: ActionGeneratedCase,
        obs: ActionDayObservation,
        timestamp: datetime,
        opportunity: ObservationOpportunityRecord,
    ) -> UnifiedEvidenceContract:
        anchor = D0SyntheticOracleReplayAdapter._anchor_metadata(case)
        target = str(case.visible.object_instance_id)
        detected_location = (
            str(obs.after.detected_location_id)
            if obs.after is not None and obs.after.detected_location_id is not None
            else None
        )
        known_locations = tuple(
            dict.fromkeys(
                str(value)
                for value in (
                    obs.before.detected_location_id if obs.before is not None else None,
                    obs.after.detected_location_id if obs.after is not None else None,
                )
                if value is not None
            )
        )
        location_keys = (*known_locations, "unknown_location")
        location_posterior = {key: 0.0 for key in location_keys}
        if detected_location is None:
            location_posterior["unknown_location"] = 1.0
        else:
            location_posterior[detected_location] = 0.9
            location_posterior["unknown_location"] = 0.1
        actor_posterior = (
            dict(obs.actor_evidence.actor_posterior)
            if obs.actor_evidence is not None
            else {
                case.visible.owner_actor: 0.0,
                case.visible.guest_actor: 0.0,
                "unknown_actor": 1.0,
            }
        )
        actor_posterior.setdefault("unknown_actor", 0.0)
        return UnifiedEvidenceContract(
            metadata=anchor.model_copy(
                update={
                    "record_id": uuid5(case.visible.case_id, f"unified-evidence:{obs.day}"),
                    "schema_name": "cpswm.UnifiedEvidenceContract",
                    "recorded_time": timestamp,
                    "source_type": SourceType.SIMULATION,
                    "source_id": "d0-visible-evidence-adapter",
                }
            ),
            valid_time=ValidTimeInterval(start=timestamp, end=timestamp + timedelta(hours=1)),
            object_instance_id=case.visible.object_instance_id,
            object_posterior={
                target: 0.9 if detected_location else 0.2,
                "unknown_object": 0.1 if detected_location else 0.8,
            },
            location_posterior=location_posterior,
            detected_object_key=target if detected_location else None,
            detected_location_key=detected_location,
            actor_posterior=actor_posterior,
            observation_opportunity=opportunity,
            selected_for_observation=opportunity.selected,
            selection_probability=opportunity.selection_probability,
            field_of_view_coverage=opportunity.p_visible_given_state,
            occlusion_state=(OcclusionState.CLEAR if detected_location else OcclusionState.UNKNOWN),
            detection_outcome=(
                ObservationOutcome.DETECTED
                if detected_location
                else ObservationOutcome.NOT_OBSERVED
            ),
            detection_failure_reason=(
                DetectionFailureReason.NOT_APPLICABLE
                if detected_location
                else DetectionFailureReason.OUT_OF_VIEW
            ),
            production_mode=EvidenceProductionMode.DIRECT,
            evidence_cluster_id=uuid5(case.visible.case_id, f"unified-cluster:{obs.day}"),
            correlation_group_id=f"d0-day:{obs.day}",
            effective_sample_weight=0.8,
            open_set_support=OpenSetEvidenceSupport(
                actor_keys=tuple(actor_posterior),
                object_instance_ids=(case.visible.object_instance_id,),
                location_keys=location_keys,
                mechanism_keys=("direct_relocation", "handoff_relocation", "unknown_mechanism"),
            ),
        )

    @staticmethod
    def _feedback(
        case: ActionGeneratedCase, day: int, timestamp: datetime, attempted: UUID, success: float
    ) -> ExecutionFeedbackRecord:
        anchor = D0SyntheticOracleReplayAdapter._anchor_metadata(case)
        meta = BaseRecordMetadata(
            record_id=uuid5(case.visible.case_id, f"execution-feedback-record:{day}"),
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
            action_id=uuid5(case.visible.case_id, f"execution-feedback:{day}"),
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
        ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE: SuppliedReplayDatasetAdapter,
        ProjectTwoDataMaturity.D0_5_SEMI_SYNTHETIC: SuppliedReplayDatasetAdapter,
        ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY: D1SimulatorAnnotatedReplayAdapter,
        ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY: D2RealPerceptionReplayAdapter,
        ProjectTwoDataMaturity.D3_HOUSEHOLD_EXECUTION: UnavailableProjectTwoDatasetAdapter,
        ProjectTwoDataMaturity.D4_EMBODIED_ROBOT_EXECUTION: UnavailableProjectTwoDatasetAdapter,
    }


__all__ = [
    "D0SyntheticOracleReplayAdapter",
    "D1SimulatorAnnotatedReplayAdapter",
    "D2RealPerceptionReplayAdapter",
    "ProjectTwoDatasetAdapter",
    "SuppliedReplayDatasetAdapter",
    "UnavailableProjectTwoDatasetAdapter",
    "adapter_tiers",
]
