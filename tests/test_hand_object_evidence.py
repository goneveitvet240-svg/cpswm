from dataclasses import replace
from uuid import uuid4

import pytest
from test_natural_hands import components

from cpswm.perception_mapping.hand_object_evidence import measure_hand_object_evidence
from cpswm.perception_mapping.interaction_evidence import CausalInstanceAssociator
from cpswm.perception_mapping.natural_vision import (
    DetectionCandidate,
    NaturalVisionEvidenceProducer,
)


def frames():
    raw, detector, hands = components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    visual = replace(
        producer.frames()[0],
        candidates=(
            DetectionCandidate(uuid4(), "person", 0.8, (0.0, 0.0, 3.0, 4.0)),
            DetectionCandidate(uuid4(), "person", 0.7, (0.0, 1.0, 4.0, 4.0)),
            DetectionCandidate(uuid4(), "cup", 0.9, (2.0, 2.0, 3.0, 3.0)),
        ),
    )
    associated = CausalInstanceAssociator().update(visual, sequence_id="s", media_time=0.0)
    return visual, producer.hand_frames()[0], associated


def test_preserves_two_people_without_fabricating_role_or_contact():
    visual, hands, associated = frames()
    result = measure_hand_object_evidence(visual, hands, associated)
    (row,) = result.measurements
    assert row.person_assignment_status == "AMBIGUOUS"
    assert len(row.compatible_person_tracks) == 2
    assert row.minimum_landmark_to_box_px == 1.0
    assert row.landmarks_inside_object_box == 0
    assert "UNRESOLVED" in result.status
    assert not hasattr(row, "probability")


def test_overlap_is_geometry_only_and_missing_hands_stays_empty():
    visual, hands, associated = frames()
    moved = replace(
        hands, candidates=(replace(hands.candidates[0], landmarks_xy_pixels=((2.5, 2.5),) * 21),)
    )
    (row,) = measure_hand_object_evidence(visual, moved, associated).measurements
    assert row.minimum_landmark_to_box_px == 0 and row.landmarks_inside_object_box == 21
    assert (
        measure_hand_object_evidence(visual, replace(hands, candidates=()), associated).measurements
        == ()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_sha256", "b" * 64),
        ("capture_receipt_sha256", "c" * 64),
        ("observation_id", uuid4()),
        ("width", 999),
    ],
)
def test_rejects_cross_source_hands(field, value):
    visual, hands, associated = frames()
    with pytest.raises(ValueError, match="same source"):
        measure_hand_object_evidence(visual, replace(hands, **{field: value}), associated)


def test_rejects_forged_association_despite_retained_visual_hash():
    visual, hands, associated = frames()
    altered = replace(
        associated,
        detections=tuple(replace(d, box_xyxy=(0.0, 0.0, 4.0, 4.0)) for d in associated.detections),
    )
    with pytest.raises(ValueError, match="differs"):
        measure_hand_object_evidence(visual, hands, altered)


def test_same_producer_derived_evidence_survives_restore():
    raw, detector, hands = components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    restored = NaturalVisionEvidenceProducer(detector, hands)
    restored.restore_state(producer.checkpoint_state())
    assert producer.hand_object_evidence() == restored.hand_object_evidence()
    assert (
        producer.hand_object_evidence()[0].observation_id == raw.envelope().identity.observation_id
    )
