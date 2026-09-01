"""D2 raw-perception, dual-annotation, and adjudication conversion protocol."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from math import isclose
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    ContractModel,
    EventMechanism,
    EventMechanismEvidence,
    HiddenEventEvidenceTrack,
    ObjectTrackObservation,
    PerceptionFrameReference,
    PerceptionModality,
    ProjectTwoDataMaturity,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.reproducibility import content_sha256


def _argmax_label[LabelT](values: Mapping[LabelT, float]) -> LabelT:
    return max(values, key=values.__getitem__)


class AnnotationSourceKind(StrEnum):
    HUMAN = "human"
    LLM_CANDIDATE = "llm_candidate"


class D2AnnotationSubmission(ContractModel):
    annotation_id: UUID
    step_id: UUID
    annotator_id: str = Field(min_length=1)
    source_kind: AnnotationSourceKind
    recorded_at: datetime
    actor_label: str | None
    mechanism_label: str | EventMechanism | None
    role_initiator_label: str | None
    role_recipient_label: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

    @field_validator("recorded_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value


class D2NormalizedAnnotation(ContractModel):
    source: D2AnnotationSubmission
    actor_label: str
    mechanism_label: EventMechanism
    ordered_role_label: str | None = None
    unresolved_axes: frozenset[str] = frozenset()


class D2EvaluatorAdjudication(ContractModel):
    """Human-only evaluator label stored outside visible replay."""

    step_id: UUID
    adjudicator_id: str = Field(min_length=1)
    source_kind: AnnotationSourceKind
    recorded_at: datetime
    actor_label: str = Field(min_length=1)
    mechanism_label: EventMechanism
    location_id: UUID
    owner_habit_location_id: UUID
    event_chain: tuple[str, ...] = Field(min_length=1)
    source_annotation_ids: tuple[UUID, ...] = Field(min_length=1)
    unresolved_axes: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def _human_truth_only(self) -> D2EvaluatorAdjudication:
        if self.source_kind is not AnnotationSourceKind.HUMAN:
            raise ValueError("evaluator truth adjudication must be human")
        return self


class D2AnnotationAgreementReport(ContractModel):
    compared_step_count: int = Field(ge=0)
    actor_exact_agreement: float = Field(ge=0.0, le=1.0)
    mechanism_exact_agreement: float = Field(ge=0.0, le=1.0)
    role_exact_agreement: float = Field(ge=0.0, le=1.0)
    disagreement_step_ids: tuple[UUID, ...]
    unresolved_step_ids: tuple[UUID, ...]


class D2RealPerceptionRawEpisode(ContractModel):
    """Collector output prior to attaching raw frame and tracking references."""

    episode: ProjectTwoReplayEpisode
    frames_by_step: dict[UUID, tuple[PerceptionFrameReference, ...]]
    tracks_by_step: dict[UUID, tuple[ObjectTrackObservation, ...]] = Field(default_factory=dict)
    annotations_by_step: dict[UUID, tuple[D2AnnotationSubmission, ...]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _identity_and_maturity(self) -> D2RealPerceptionRawEpisode:
        if self.episode.maturity not in {
            ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
            ProjectTwoDataMaturity.D0_5_SEMI_SYNTHETIC,
            ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
        }:
            raise ValueError("raw perception episode must declare its actual source maturity")
        step_ids = {step.step_id for step in self.episode.steps}
        for mapping in (self.frames_by_step, self.tracks_by_step, self.annotations_by_step):
            if set(mapping) - step_ids:
                raise ValueError("raw perception mapping contains unknown step id")
        if set(self.frames_by_step) != step_ids:
            raise ValueError("every D2 replay step requires an explicit frame tuple")
        return self


def annotation_agreement_report(
    submissions: tuple[D2AnnotationSubmission, ...],
) -> D2AnnotationAgreementReport:
    grouped: dict[UUID, list[D2AnnotationSubmission]] = defaultdict(list)
    for item in submissions:
        if item.source_kind is AnnotationSourceKind.HUMAN:
            grouped[item.step_id].append(item)
    compared = {key: values for key, values in grouped.items() if len(values) >= 2}
    if not compared:
        return D2AnnotationAgreementReport(
            compared_step_count=0,
            actor_exact_agreement=0.0,
            mechanism_exact_agreement=0.0,
            role_exact_agreement=0.0,
            disagreement_step_ids=(),
            unresolved_step_ids=tuple(sorted(grouped, key=str)),
        )

    def same(values: list[D2AnnotationSubmission], attribute: str) -> bool:
        return len({getattr(value, attribute) for value in values}) == 1

    actor = sum(same(values, "actor_label") for values in compared.values())
    mechanism = sum(same(values, "mechanism_label") for values in compared.values())
    role = sum(
        len({(value.role_initiator_label, value.role_recipient_label) for value in values}) == 1
        for values in compared.values()
    )
    disagreements = tuple(
        sorted(
            (
                key
                for key, values in compared.items()
                if not (
                    same(values, "actor_label")
                    and same(values, "mechanism_label")
                    and len(
                        {
                            (value.role_initiator_label, value.role_recipient_label)
                            for value in values
                        }
                    )
                    == 1
                )
            ),
            key=str,
        )
    )
    unresolved = tuple(
        sorted(
            (
                key
                for key, values in grouped.items()
                if len(values) < 2
                or any(
                    value.actor_label is None or value.mechanism_label is None for value in values
                )
            ),
            key=str,
        )
    )
    n = len(compared)
    return D2AnnotationAgreementReport(
        compared_step_count=n,
        actor_exact_agreement=actor / n,
        mechanism_exact_agreement=mechanism / n,
        role_exact_agreement=role / n,
        disagreement_step_ids=disagreements,
        unresolved_step_ids=unresolved,
    )


class D2RealPerceptionConverter:
    """Convert raw sensor references and annotations into the common replay contract."""

    @staticmethod
    def normalize_annotation(
        submission: D2AnnotationSubmission, *, resident_actor_keys: tuple[str, ...]
    ) -> D2NormalizedAnnotation:
        unresolved: set[str] = set()
        actor = submission.actor_label or "unknown_actor"
        if actor not in resident_actor_keys:
            actor = "unknown_actor"
            unresolved.add("actor")
        try:
            mechanism = EventMechanism(submission.mechanism_label or "")
        except (ValueError, TypeError):
            mechanism = EventMechanism.UNKNOWN_MECHANISM
            unresolved.add("mechanism")
        role = None
        if submission.role_initiator_label and submission.role_recipient_label:
            if (
                submission.role_initiator_label in resident_actor_keys
                and submission.role_recipient_label in resident_actor_keys
                and submission.role_initiator_label != submission.role_recipient_label
            ):
                role = ordered_role_key(
                    submission.role_initiator_label, submission.role_recipient_label
                )
            else:
                unresolved.add("role")
        elif mechanism is EventMechanism.HANDOFF_RELOCATION:
            unresolved.add("role")
        return D2NormalizedAnnotation(
            source=submission,
            actor_label=actor,
            mechanism_label=mechanism,
            ordered_role_label=role,
            unresolved_axes=frozenset(unresolved),
        )

    def convert_visible(self, raw: D2RealPerceptionRawEpisode) -> ProjectTwoReplayEpisode:
        steps = []
        for step in raw.episode.steps:
            update: dict[str, object] = {
                "perception_frames": raw.frames_by_step[step.step_id],
                "object_tracks": raw.tracks_by_step.get(step.step_id, ()),
            }
            submissions = raw.annotations_by_step.get(step.step_id, ())
            selected = (
                None
                if step.unified_evidence is not None
                else self._select_visible_annotation(raw.episode.maturity, submissions)
            )
            if selected is not None:
                normalized = self.normalize_annotation(
                    selected, resident_actor_keys=raw.episode.resident_actor_keys
                )
                update.update(
                    self._evidence_update(step, normalized, raw.episode.resident_actor_keys)
                )
            steps.append(step.model_copy(update=update))
        return ProjectTwoReplayEpisode.model_validate(
            raw.episode.model_copy(update={"steps": tuple(steps)}).model_dump(mode="python")
        )

    @classmethod
    def _select_visible_annotation(
        cls,
        maturity: ProjectTwoDataMaturity,
        submissions: tuple[D2AnnotationSubmission, ...],
    ) -> D2AnnotationSubmission | None:
        """Keep evaluator-grade human labels out of real model-facing replay."""

        if not submissions:
            return None
        real_track = maturity in {
            ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
            ProjectTwoDataMaturity.D3_HOUSEHOLD_EXECUTION,
            ProjectTwoDataMaturity.D4_EMBODIED_ROBOT_EXECUTION,
        }
        candidates = tuple(
            item
            for item in submissions
            if not real_track or item.source_kind is AnnotationSourceKind.LLM_CANDIDATE
        )
        if not candidates:
            return None
        semantic_labels = {
            (
                item.actor_label,
                str(item.mechanism_label),
                item.role_initiator_label,
                item.role_recipient_label,
            )
            for item in candidates
        }
        if len(semantic_labels) != 1:
            return None
        return min(candidates, key=lambda item: str(item.annotation_id))

    @staticmethod
    def _evidence_update(
        step: ProjectTwoReplayStep,
        annotation: D2NormalizedAnnotation,
        actors: tuple[str, ...],
    ) -> dict[str, object]:
        detection = step.after or step.before
        if detection is None:
            return {}
        is_llm = annotation.source.source_kind is AnnotationSourceKind.LLM_CANDIDATE
        anchor = detection.metadata.model_copy(
            update={
                "record_id": uuid5(annotation.source.annotation_id, "compiled-evidence"),
                "schema_name": (
                    "cpswm.D2LLMCandidateEvidence"
                    if is_llm
                    else "cpswm.D0FixtureHumanAnnotationEvidence"
                ),
                "source_type": SourceType.MODEL,
                "source_id": f"annotation:{annotation.source.annotator_id}",
                "recorded_time": annotation.source.recorded_at,
            }
        )
        actor_prior = {actor: 1.0 / len(actors) for actor in actors}
        actor_posterior = D2RealPerceptionConverter._soft_label(actors, annotation.actor_label)
        mechanisms = tuple(EventMechanism)
        mechanism_prior = {value: 1.0 / len(mechanisms) for value in mechanisms}
        update: dict[str, object] = {
            "actor_evidence": ActorResponsibilityEvidence(
                metadata=anchor,
                source_detection_result_id=detection.metadata.record_id,
                object_instance_id=step.object_instance_id,
                evidence_time=annotation.source.recorded_at,
                actor_posterior=actor_posterior,
                reference_actor_prior=actor_prior,
                evidence_cluster_id=annotation.source.annotation_id,
                effective_sample_weight=max(annotation.source.confidence, 1e-6),
                evidence_track=(
                    ActorEvidenceTrack.MODEL if is_llm else ActorEvidenceTrack.CONTROLLED_NOISE
                ),
                evidence_model_id="d2-human-annotation-compiler@0.1",
            ),
            "mechanism_evidence": EventMechanismEvidence(
                metadata=anchor.model_copy(
                    update={"record_id": uuid5(annotation.source.annotation_id, "mechanism")}
                ),
                source_detection_result_id=detection.metadata.record_id,
                object_instance_id=step.object_instance_id,
                evidence_time=annotation.source.recorded_at,
                mechanism_posterior=D2RealPerceptionConverter._soft_label(
                    mechanisms, annotation.mechanism_label
                ),
                reference_mechanism_prior=mechanism_prior,
                evidence_cluster_id=annotation.source.annotation_id,
                effective_sample_weight=max(annotation.source.confidence, 1e-6),
                evidence_track=(
                    HiddenEventEvidenceTrack.MODEL
                    if is_llm
                    else HiddenEventEvidenceTrack.CONTROLLED_NOISE
                ),
                evidence_model_id="d2-human-annotation-compiler@0.1",
            ),
        }
        if annotation.ordered_role_label:
            initiator, recipient = annotation.ordered_role_label.split("=>")
            alternatives = tuple(ordered_role_key(a, b) for a in actors for b in actors if a != b)
            update["ordered_role_evidence"] = RoleBindingEvidence(
                metadata=anchor.model_copy(
                    update={"record_id": uuid5(annotation.source.annotation_id, "role")}
                ),
                source_detection_result_id=detection.metadata.record_id,
                object_instance_id=step.object_instance_id,
                evidence_time=annotation.source.recorded_at,
                ordered_role_posterior=D2RealPerceptionConverter._soft_label(
                    alternatives, ordered_role_key(initiator, recipient)
                ),
                reference_ordered_role_prior={key: 1.0 / len(alternatives) for key in alternatives},
                evidence_cluster_id=annotation.source.annotation_id,
                effective_sample_weight=max(annotation.source.confidence, 1e-6),
                evidence_track=(
                    HiddenEventEvidenceTrack.MODEL
                    if is_llm
                    else HiddenEventEvidenceTrack.CONTROLLED_NOISE
                ),
                evidence_model_id="d2-human-annotation-compiler@0.1",
            )
        return update

    @staticmethod
    def _soft_label[LabelT](support: Iterable[LabelT], selected: LabelT) -> dict[LabelT, float]:
        support = tuple(support)
        if len(support) == 1:
            return {support[0]: 1.0}
        remainder = 0.2 / (len(support) - 1)
        result = {key: (0.8 if key == selected else remainder) for key in support}
        assert isclose(sum(result.values()), 1.0, abs_tol=1e-9)
        return result

    @staticmethod
    def convert_evaluator_truth(
        episode: ProjectTwoReplayEpisode,
        adjudications: tuple[D2EvaluatorAdjudication, ...],
    ) -> ProjectTwoEvaluatorTruthEnvelope:
        by_step = {item.step_id: item for item in adjudications}
        if set(by_step) != {step.step_id for step in episode.steps}:
            raise ValueError("human adjudication must cover exactly every replay step")
        truth = {
            step_id: ProjectTwoEvaluatorStepTruth(
                step_id=step_id,
                true_actor=item.actor_label,
                true_mechanism=item.mechanism_label,
                true_location=item.location_id,
                true_owner_habit_location=item.owner_habit_location_id,
                event_chain_truth=item.event_chain,
            )
            for step_id, item in by_step.items()
        }
        payload = {
            "episode_id": episode.episode_id,
            "dataset_version": episode.dataset_version,
            "source_hash": episode.source_hash,
            "truth_by_step": truth,
        }
        return ProjectTwoEvaluatorTruthEnvelope(
            **payload, evaluator_content_hash=content_sha256(payload)
        )


D2_EXAMPLE_VERSION = "project-two-d2-real-perception-example-fixture@0.1"


def build_d2_example_batch(
    *, max_steps_per_episode: int = 12
) -> tuple[ProjectTwoReplayDataset, tuple[D2AnnotationSubmission, ...]]:
    """Build a runnable sensor-shaped fixture; it makes no real-collection claim."""

    from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
        D0SyntheticOracleReplayAdapter,
        SuppliedReplayDatasetAdapter,
    )

    source = D0SyntheticOracleReplayAdapter(
        validation_seeds=(5101, 5102),
        test_seeds=(6101, 6102, 6103),
        max_steps_per_episode=max_steps_per_episode,
        dataset_version="d2-perception-source-fixture@0.1",
        object_family_bucket_count=2,
        sealed_secret="project-two-d2-real-perception-example-fixture",
    ).build()
    episodes = []
    envelopes = []
    all_submissions: list[D2AnnotationSubmission] = []
    converter = D2RealPerceptionConverter()
    truth_by_id = {item.episode_id: item for item in source.evaluator_store}
    global_index = 0
    for episode in source.episodes:
        source_hash = content_sha256(
            {
                "upstream_hash": episode.source_hash,
                "dataset_version": D2_EXAMPLE_VERSION,
                "fixture": True,
            }
        )
        converted_base = episode.model_copy(
            update={
                "dataset_version": D2_EXAMPLE_VERSION,
                "source_uri": f"d2-fixture://sensor-shaped/{episode.episode_id}",
                "source_hash": source_hash,
                "maturity": ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
                "source_evidence_maturity": ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
                "provenance": (
                    "fixture:derived-from-visible-controlled-noise",
                    "adapter:D2RealPerceptionReplayAdapter",
                    "claim:not-real-collection",
                    "truth_source:separate-d0-synthetic-fixture",
                ),
            }
        )
        frames_by_step = {}
        tracks_by_step = {}
        annotations_by_step = {}
        for step in converted_base.steps:
            modality = PerceptionModality.RGBD if global_index % 2 == 0 else PerceptionModality.RGB
            frame_id = f"fixture-frame-{step.step_id}"
            frames_by_step[step.step_id] = (
                PerceptionFrameReference(
                    frame_id=frame_id,
                    timestamp=step.timestamp,
                    modality=modality,
                    rgb_uri=f"fixture://rgb/{step.step_id}.png",
                    depth_uri=(
                        f"fixture://depth/{step.step_id}.npy"
                        if modality is PerceptionModality.RGBD
                        else None
                    ),
                    sensor_id=(
                        "fixture-rgbd-01"
                        if modality is PerceptionModality.RGBD
                        else "fixture-rgb-01"
                    ),
                ),
            )
            tracks_by_step[step.step_id] = (
                ObjectTrackObservation(
                    frame_id=frame_id,
                    track_id=f"track-{step.object_instance_id}",
                    object_instance_id=step.object_instance_id,
                    object_category=step.object_category,
                    detection_confidence=step.detection_confidence or 0.25,
                    visibility_probability=step.visibility_probability,
                    occlusion_state=step.occlusion_state,
                    bounding_box_xyxy=(10.0, 20.0, 110.0, 160.0),
                ),
            )
            actor_label = (
                _argmax_label(step.actor_evidence.actor_posterior)
                if step.actor_evidence is not None
                else "unknown_actor"
            )
            mechanism_label = (
                _argmax_label(step.mechanism_evidence.mechanism_posterior).value
                if step.mechanism_evidence is not None
                else EventMechanism.UNKNOWN_MECHANISM.value
            )
            role_key = (
                _argmax_label(step.ordered_role_evidence.ordered_role_posterior)
                if step.ordered_role_evidence is not None
                else None
            )
            role_parts = role_key.split("=>") if role_key else (None, None)
            submissions = []
            reviewers = ("fixture-reviewer-a", "fixture-reviewer-b")
            for annotator_index, annotator in enumerate(reviewers):
                reviewed_actor = (
                    "unknown_actor"
                    if annotator_index == 1 and global_index % 5 == 0
                    else actor_label
                )
                submissions.append(
                    D2AnnotationSubmission(
                        annotation_id=uuid5(step.step_id, f"annotation:{annotator}"),
                        step_id=step.step_id,
                        annotator_id=annotator,
                        source_kind=AnnotationSourceKind.HUMAN,
                        recorded_at=step.timestamp,
                        actor_label=reviewed_actor,
                        mechanism_label=mechanism_label,
                        role_initiator_label=role_parts[0],
                        role_recipient_label=role_parts[1],
                        confidence=0.75,
                        notes="fixture review derived only from visible controlled-noise evidence",
                    )
                )
            annotations_by_step[step.step_id] = tuple(submissions)
            all_submissions.extend(submissions)
            global_index += 1
        raw = D2RealPerceptionRawEpisode(
            episode=converted_base,
            frames_by_step=frames_by_step,
            tracks_by_step=tracks_by_step,
            annotations_by_step=annotations_by_step,
        )
        converted = converter.convert_visible(raw)
        episodes.append(converted)
        source_truth = truth_by_id[episode.episode_id]
        payload = {
            "episode_id": converted.episode_id,
            "dataset_version": D2_EXAMPLE_VERSION,
            "source_hash": source_hash,
            "truth_by_step": source_truth.truth_by_step,
        }
        envelopes.append(
            source_truth.model_copy(
                update={**payload, "evaluator_content_hash": content_sha256(payload)}
            )
        )
    dataset = SuppliedReplayDatasetAdapter(
        dataset_version=D2_EXAMPLE_VERSION,
        episodes=tuple(episodes),
        evaluator_store=tuple(envelopes),
        adapter_provenance="sensor-shaped example fixture; no real capture claim",
        maturity=ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
    ).build()
    return dataset, tuple(all_submissions)


def materialize_d2_example_batch(
    output_dir: Path, *, max_steps_per_episode: int = 12
) -> dict[str, object]:
    from cpswm.system.evaluation_operations.project_two_replay_importer import (
        export_project_two_replay_dataset,
    )

    dataset, submissions = build_d2_example_batch(max_steps_per_episode=max_steps_per_episode)
    report = export_project_two_replay_dataset(dataset, output_dir)
    agreement = annotation_agreement_report(submissions)
    submissions_by_step: dict[UUID, list[D2AnnotationSubmission]] = defaultdict(list)
    for submission in submissions:
        submissions_by_step[submission.step_id].append(submission)
    raw_episodes = tuple(
        D2RealPerceptionRawEpisode(
            episode=episode,
            frames_by_step={step.step_id: step.perception_frames for step in episode.steps},
            tracks_by_step={step.step_id: step.object_tracks for step in episode.steps},
            annotations_by_step={
                step.step_id: tuple(submissions_by_step[step.step_id]) for step in episode.steps
            },
        )
        for episode in dataset.episodes
    )
    (output_dir / "raw_perception.jsonl").write_text(
        "\n".join(item.model_dump_json() for item in raw_episodes) + "\n",
        encoding="utf-8",
    )
    (output_dir / "annotations.jsonl").write_text(
        "\n".join(item.model_dump_json() for item in submissions) + "\n",
        encoding="utf-8",
    )
    (output_dir / "annotation_agreement.json").write_text(
        agreement.model_dump_json(indent=2), encoding="utf-8"
    )
    split_manifest = {
        "dataset_version": dataset.manifest.dataset_version,
        "split_episode_ids": {
            split: [str(item.episode_id) for item in dataset.episodes if item.split.value == split]
            for split in ("validation", "test")
        },
        "split_keys": ["household_id", "scene_id", "object_instance_id", "object_family"],
        "manifest_content_hash": content_sha256(dataset.manifest),
    }
    (output_dir / "split_manifest.json").write_text(
        json.dumps(split_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    collection_protocol = {
        "schema": "cpswm.D2RealPerceptionRawEpisode",
        "schema_version": "0.1.0",
        "required_visible_axes": [
            "RGB or RGB-D frame reference",
            "timestamp/household/scene/session",
            "object instance/category and detector track",
            "source/attempted/observed destination",
            "visibility/occlusion/detection confidence",
            "actor/role/mechanism annotation or unknown",
            "execution feedback and observation opportunity",
        ],
        "review_policy": "two human submissions; retain disagreement; explicit adjudication",
        "llm_policy": "llm_candidate may be visible evidence only; never evaluator truth",
        "truth_store": "physically separate evaluator_truth.jsonl",
        "example_claim": "fixture:not-real-collection",
    }
    (output_dir / "collection_protocol.json").write_text(
        json.dumps(collection_protocol, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    collection_status = {
        "actual_collected_episode_count": 0,
        "fixture_episode_count": len(dataset.episodes),
        "fixture_step_count": sum(len(item.steps) for item in dataset.episodes),
        "claim": "executable schema/example only; no physical RGB/RGB-D capture performed",
    }
    report.update(
        {
            "annotation_agreement": agreement.model_dump(mode="json"),
            "split_manifest": split_manifest,
            "collection_status": collection_status,
            "collection_protocol": collection_protocol,
        }
    )
    report["additional_content_hashes"] = {
        name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in (
            "raw_perception.jsonl",
            "annotations.jsonl",
            "annotation_agreement.json",
            "split_manifest.json",
            "collection_protocol.json",
        )
    }
    (output_dir / "d2_evidence_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


__all__ = [
    "D2_EXAMPLE_VERSION",
    "AnnotationSourceKind",
    "D2AnnotationAgreementReport",
    "D2AnnotationSubmission",
    "D2EvaluatorAdjudication",
    "D2NormalizedAnnotation",
    "D2RealPerceptionConverter",
    "D2RealPerceptionRawEpisode",
    "ObjectTrackObservation",
    "PerceptionFrameReference",
    "PerceptionModality",
    "annotation_agreement_report",
    "build_d2_example_batch",
    "materialize_d2_example_batch",
]
