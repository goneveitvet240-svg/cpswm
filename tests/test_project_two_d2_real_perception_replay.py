from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cpswm.contracts import EventMechanism, ProjectTwoDataMaturity
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_real_perception import (
    AnnotationSourceKind,
    D2AnnotationSubmission,
    D2EvaluatorAdjudication,
    D2RealPerceptionConverter,
    D2RealPerceptionRawEpisode,
    PerceptionFrameReference,
    PerceptionModality,
    annotation_agreement_report,
    build_d2_example_batch,
    materialize_d2_example_batch,
)


def _raw_fixture() -> D2RealPerceptionRawEpisode:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=2
    ).build()
    episode = dataset.episodes[0]
    frames = {
        step.step_id: (
            PerceptionFrameReference(
                frame_id=f"rgbd-{step.step_id}",
                timestamp=step.timestamp,
                modality=PerceptionModality.RGBD,
                rgb_uri=f"fixture://rgb/{step.step_id}.png",
                depth_uri=f"fixture://depth/{step.step_id}.npy",
                sensor_id="fixture-rgbd",
            ),
        )
        for step in episode.steps
    }
    return D2RealPerceptionRawEpisode(
        episode=episode.model_copy(
            update={
                "dataset_version": "d2-real-perception-fixture@0.1",
                "maturity": ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
                "source_evidence_maturity": ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
                "provenance": (*episode.provenance, "fixture:not-real-collection"),
            }
        ),
        frames_by_step=frames,
    )


def test_raw_rgbd_record_converts_to_same_project_two_replay_episode_contract():
    converted = D2RealPerceptionConverter().convert_visible(_raw_fixture())
    assert converted.maturity is ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE
    assert converted.source_evidence_maturity is ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE
    assert all(step.perception_frames[0].depth_uri for step in converted.steps)
    assert all(step.perception_frames[0].rgb_uri for step in converted.steps)


def test_unmapped_actor_and_mechanism_become_unknown_not_known_labels():
    submission = D2AnnotationSubmission(
        annotation_id=uuid4(),
        step_id=uuid4(),
        annotator_id="annotator-a",
        source_kind=AnnotationSourceKind.HUMAN,
        recorded_at=datetime.now(UTC),
        actor_label="visitor-not-in-resident-roster",
        mechanism_label="teleport_magic",
        role_initiator_label=None,
        role_recipient_label=None,
        confidence=0.7,
    )
    normalized = D2RealPerceptionConverter.normalize_annotation(
        submission, resident_actor_keys=("owner", "guest", "unknown_actor")
    )
    assert normalized.actor_label == "unknown_actor"
    assert normalized.mechanism_label is EventMechanism.UNKNOWN_MECHANISM
    assert {"actor", "mechanism"}.issubset(normalized.unresolved_axes)


def test_disagreement_is_retained_and_llm_cannot_be_evaluator_truth():
    step_id = uuid4()
    common = dict(
        step_id=step_id,
        recorded_at=datetime.now(UTC),
        mechanism_label="direct_relocation",
        role_initiator_label=None,
        role_recipient_label=None,
        confidence=0.8,
    )
    first = D2AnnotationSubmission(
        annotation_id=uuid4(), annotator_id="a", source_kind="human", actor_label="owner", **common
    )
    second = D2AnnotationSubmission(
        annotation_id=uuid4(), annotator_id="b", source_kind="human", actor_label="guest", **common
    )
    report = annotation_agreement_report((first, second))
    assert report.disagreement_step_ids == (step_id,)
    assert report.actor_exact_agreement == 0.0

    with pytest.raises(ValueError, match="human"):
        D2EvaluatorAdjudication(
            step_id=step_id,
            adjudicator_id="fixture-llm",
            source_kind=AnnotationSourceKind.LLM_CANDIDATE,
            recorded_at=datetime.now(UTC),
            actor_label="owner",
            mechanism_label="direct_relocation",
            location_id=uuid4(),
            owner_habit_location_id=uuid4(),
            event_chain=("pick_up", "place"),
            source_annotation_ids=(first.annotation_id, second.annotation_id),
        )


def test_d2_example_batch_is_explicit_fixture_with_split_hash_and_agreement_reports(tmp_path):
    dataset, submissions = build_d2_example_batch(max_steps_per_episode=4)
    assert len(dataset.episodes) >= 4
    assert all(item.perception_frames for episode in dataset.episodes for item in episode.steps)
    assert all("claim:not-real-collection" in item.provenance for item in dataset.episodes)
    assert all(
        item.maturity is ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE for item in dataset.episodes
    )
    report = materialize_d2_example_batch(tmp_path, max_steps_per_episode=4)
    assert report["collection_status"]["actual_collected_episode_count"] == 0
    assert report["collection_status"]["fixture_episode_count"] == len(dataset.episodes)
    assert (tmp_path / "annotation_agreement.json").exists()
    assert (tmp_path / "split_manifest.json").exists()
    assert (tmp_path / "raw_perception.jsonl").exists()
    assert (tmp_path / "collection_protocol.json").exists()
    assert submissions


def test_real_d2_human_labels_never_become_model_visible_actor_evidence():
    raw = _raw_fixture()
    step = raw.episode.steps[0]
    stripped_step = step.model_copy(update={"actor_evidence": None})
    real_episode = raw.episode.model_copy(
        update={
            "maturity": ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
            "source_evidence_maturity": ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
            "steps": (stripped_step, *raw.episode.steps[1:]),
        }
    )
    human = D2AnnotationSubmission(
        annotation_id=uuid4(),
        step_id=step.step_id,
        annotator_id="evaluator-only-human",
        source_kind=AnnotationSourceKind.HUMAN,
        recorded_at=step.timestamp,
        actor_label=real_episode.owner_actor_key,
        mechanism_label=EventMechanism.DIRECT_RELOCATION,
        role_initiator_label=None,
        role_recipient_label=None,
        confidence=1.0,
    )
    converted = D2RealPerceptionConverter().convert_visible(
        D2RealPerceptionRawEpisode(
            episode=real_episode,
            frames_by_step=raw.frames_by_step,
            annotations_by_step={step.step_id: (human,)},
        )
    )

    assert converted.steps[0].actor_evidence is None


def test_conflicting_fixture_annotations_are_order_invariant_and_fail_closed():
    raw = _raw_fixture()
    step = raw.episode.steps[0]
    episode = raw.episode.model_copy(
        update={"steps": (step.model_copy(update={"actor_evidence": None}), *raw.episode.steps[1:])}
    )
    common = dict(
        step_id=step.step_id,
        recorded_at=step.timestamp,
        mechanism_label=EventMechanism.DIRECT_RELOCATION,
        role_initiator_label=None,
        role_recipient_label=None,
        confidence=0.8,
        source_kind=AnnotationSourceKind.HUMAN,
    )
    first = D2AnnotationSubmission(
        annotation_id=uuid4(), annotator_id="a", actor_label="owner", **common
    )
    second = D2AnnotationSubmission(
        annotation_id=uuid4(), annotator_id="b", actor_label="unknown_actor", **common
    )

    def convert(order):  # type: ignore[no-untyped-def]
        return D2RealPerceptionConverter().convert_visible(
            D2RealPerceptionRawEpisode(
                episode=episode,
                frames_by_step=raw.frames_by_step,
                annotations_by_step={step.step_id: order},
            )
        )

    forward = convert((first, second))
    reverse = convert((second, first))
    assert forward == reverse
    assert forward.steps[0].actor_evidence is None
