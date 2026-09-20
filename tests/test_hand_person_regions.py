"""ROI boundary tests use synthetic outputs, never stand in for real accuracy."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_natural_hands import components

from cpswm.perception_mapping.natural_hands import (
    ROI_PROFILE,
    NaturalHandDetector,
    person_regions,
    validate_hand_regions,
)
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer
from cpswm.system.continuous_state_store import ContinuousStateStore


def roi_components():
    raw, visual_detector, old = components()
    hands = object.__new__(NaturalHandDetector)
    hands._scope = old._scope
    hands.binding = (*old.binding, ROI_PROFILE)
    hands.uses_person_regions = True
    hands._mp = SimpleNamespace(Image=lambda **kw: kw["data"], ImageFormat=SimpleNamespace(SRGB=1))
    hands._model = SimpleNamespace(
        detect=lambda image: SimpleNamespace(
            hand_landmarks=[[SimpleNamespace(x=0.25, y=0.75)] * 21],
            handedness=[[SimpleNamespace(category_name="Right", score=0.8)]],
        )
    )
    return raw, visual_detector, hands


def test_roi_mapping_and_overlaps_keep_provenance():
    raw, detector, hands = roi_components()
    cutoff = raw.envelope().arrival_time
    visual = detector.infer(raw, cutoff=cutoff)
    visual = replace(
        visual, candidates=(replace(visual.candidates[0], box_xyxy=(1.0, 1.0, 2.0, 2.0)),)
    )
    frame = hands.infer_with_visual(raw, visual, cutoff=cutoff)
    assert [c.landmarks_xy_pixels[0] for c in frame.candidates] == [(1.0, 3.0), (0.75, 2.25)]
    assert len({c.region_id for c in frame.candidates}) == 2
    validate_hand_regions(frame, visual)
    assert len(person_regions(replace(visual, candidates=()))) == 1
    with pytest.raises(ValueError, match="duplicate"):
        person_regions(replace(visual, candidates=visual.candidates * 2))


@pytest.mark.parametrize(
    "field,value",
    [
        ("receipt_sha256", "c" * 64),
        ("sensor_id", "other"),
        ("frame_id", "other"),
        ("input_sha256", "b" * 64),
        ("observation_id", uuid4()),
    ],
)
def test_wrong_visual_source_rejected(field, value):
    raw, detector, hands = roi_components()
    cutoff = raw.envelope().arrival_time
    visual = detector.infer(raw, cutoff=cutoff)
    with pytest.raises(ValueError, match="source"):
        hands.infer_with_visual(raw, replace(visual, **{field: value}), cutoff=cutoff)


@pytest.mark.parametrize("corruption", ["source", "region", "candidate"])
def test_roi_checkpoint_roundtrip_and_atomic_rejection(tmp_path, corruption):
    raw, detector, hands = roi_components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    state = producer.checkpoint_state()
    store = ContinuousStateStore(
        tmp_path / "state.sqlite", source_identity="a" * 64, dependency_identity="b" * 64
    )
    store.save(state)
    loaded = store.load()
    store.close()
    producer.restore_state(loaded)
    assert producer.checkpoint_state() == state
    bad = deepcopy(state)
    hand = bad["hand_frames"][0]
    if corruption == "source":
        hand = replace(hand, visual_source_sha256="c" * 64)
    elif corruption == "region":
        hand = replace(hand, regions_evaluated=())
    else:
        hand = replace(hand, candidates=(replace(hand.candidates[0], region_id=uuid4()),))
    bad["hand_frames"] = (hand,)
    with pytest.raises(ValueError, match="ROI"):
        producer.restore_state(bad)
    assert producer.checkpoint_state() == state
