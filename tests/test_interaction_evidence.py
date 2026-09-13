"""Synthetic boundary/algorithm tests, not empirical tracking/calibration evidence."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cpswm.perception_mapping.interaction_evidence import (
    CalibrationArtifact,
    CalibrationExample,
    CausalInstanceAssociator,
    evaluate_calibration,
    fit_calibration,
    role_readout,
)
from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame


def frame(previous=None, boxes=((0, 0, 40, 90), (60, 0, 100, 90)), categories=None):
    now = datetime.now(UTC)
    base = previous or VisualFrame(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        "camera",
        "pixels",
        now,
        now,
        now,
        "a" * 64,
        "b" * 64,
        "fixture",
        "c" * 64,
        "test",
        "test",
        0.5,
        100,
        100,
        (),
    )
    return replace(
        base,
        observation_id=uuid4(),
        candidates=tuple(
            DetectionCandidate(uuid4(), cat, 0.8, box)
            for box, cat in zip(boxes, categories or ["person"] * len(boxes), strict=True)
        ),
    )


def test_unique_association_and_replay():
    tracker = CausalInstanceAssociator()
    first = frame()
    a = tracker.update(first, sequence_id="clip", media_time=0)
    b = tracker.update(frame(first), sequence_id="clip", media_time=0.2)
    assert [d.track_id for d in a.detections] == [d.track_id for d in b.detections]
    assert all(d.status == "ASSOCIATED_GEOMETRIC" for d in b.detections)
    assert tracker.update(first, sequence_id="clip", media_time=0) == a
    # Returned dataclasses cannot mutate retained state even via forced mutation.
    object.__setattr__(a.detections[0], "track_id", uuid4())
    assert tracker.update(first, sequence_id="clip", media_time=0) != a


def test_competing_boxes_branch_instead_of_merging_people():
    tracker = CausalInstanceAssociator()
    first = frame(boxes=((0, 0, 60, 90), (40, 0, 100, 90)))
    a = tracker.update(first, sequence_id="clip", media_time=0)
    b = tracker.update(
        frame(first, boxes=((20, 0, 80, 90),) * 2), sequence_id="clip", media_time=0.2
    )
    assert all(
        d.status == "AMBIGUOUS_NEW_BRANCH" and len(d.alternatives) == 2 for d in b.detections
    )
    assert not {d.track_id for d in a.detections} & {d.track_id for d in b.detections}
    assert len({d.track_id for d in b.detections}) == 2


@pytest.mark.parametrize("gap", [2, 100])
def test_gap_does_not_reidentify(gap):
    tracker = CausalInstanceAssociator()
    f = frame()
    a = tracker.update(f, sequence_id="clip", media_time=0)
    b = tracker.update(frame(f), sequence_id="clip", media_time=gap)
    assert not {d.track_id for d in a.detections} & {d.track_id for d in b.detections}


@pytest.mark.parametrize(
    "attack", ["time", "sequence", "scope", "camera", "duplicate", "box", "score", "rewrite"]
)
def test_reject_is_atomic_and_legal_retry_succeeds(attack):
    tracker = CausalInstanceAssociator()
    f = frame()
    a = tracker.update(f, sequence_id="clip", media_time=0)
    good = frame(f)
    bad, seq, time = good, "clip", 0.2
    if attack == "time":
        time = 0
    if attack == "sequence":
        seq = "other"
    if attack == "scope":
        bad = replace(good, session_id=uuid4())
    if attack == "camera":
        bad = replace(good, sensor_id="another")
    if attack == "duplicate":
        bad = replace(good, candidates=(good.candidates[0],) * 2)
    if attack == "box":
        bad = replace(good, candidates=(replace(good.candidates[0], box_xyxy=(-1, 0, 40, 90)),))
    if attack == "score":
        bad = replace(good, candidates=(replace(good.candidates[0], detector_score=float("nan")),))
    if attack == "rewrite":
        bad = replace(good, observation_id=f.observation_id)
    with pytest.raises(ValueError):
        tracker.update(bad, sequence_id=seq, media_time=time)
    b = tracker.update(good, sequence_id="clip", media_time=0.2)
    assert [d.track_id for d in a.detections] == [d.track_id for d in b.detections]


def test_no_object_no_roles_and_observation_request_changes():
    tracker = CausalInstanceAssociator()
    f = frame()
    a = tracker.update(f, sequence_id="clip", media_time=0)
    r = role_readout(None, a)
    assert not r.role_alternatives and not r.memory_write_authorized
    assert r.next_observation_request == "obtain_closer_object_view"
    b = tracker.update(
        frame(
            f,
            boxes=((0, 0, 40, 90), (60, 0, 100, 90), (30, 40, 70, 55)),
            categories=("person", "person", "cup"),
        ),
        sequence_id="clip",
        media_time=0.2,
    )
    assert role_readout(a, b).next_observation_request == "observe_hands_and_object"


def test_ordered_roles_remain_ambiguous_and_retract_on_identity_break():
    tracker = CausalInstanceAssociator()
    f = frame(
        boxes=((0, 0, 55, 90), (45, 0, 100, 90), (40, 40, 60, 55)),
        categories=("person", "person", "cup"),
    )
    a = tracker.update(f, sequence_id="clip", media_time=0)
    g = replace(
        f,
        observation_id=uuid4(),
        candidates=tuple(replace(d, candidate_id=uuid4()) for d in f.candidates),
    )
    b = tracker.update(g, sequence_id="clip", media_time=0.2)
    r = role_readout(a, b)
    assert len(r.role_alternatives) == 2
    assert not r.memory_write_authorized
    c = tracker.update(replace(g, observation_id=uuid4()), sequence_id="clip", media_time=3)
    assert not role_readout(b, c).role_alternatives


def examples(seq="fit", digest="a"):
    # Labels below are math fixtures, explicitly not real-data calibration results.
    return tuple(
        CalibrationExample(
            str(i),
            seq,
            digest * 64,
            "fixture-score-v1",
            score,
            label,
            "f" * 64,
            "independent_annotation",
        )
        for i, (score, label) in enumerate(((0.1, False), (0.3, False), (0.6, True), (0.9, True)))
    )


def test_fit_heldout_and_signature_guard():
    artifact = fit_calibration(examples())
    result = evaluate_calibration(artifact, examples("holdout", "b"))
    assert result["count"] == 4 and 0 <= result["calibrated_brier"] <= 1
    with pytest.raises(ValueError, match="another model"):
        artifact.probability(0.5, model_signature="other")
    with pytest.raises(ValueError, match="leakage"):
        evaluate_calibration(artifact, examples())
    with pytest.raises(ValueError, match="leakage"):
        evaluate_calibration(artifact, examples("renamed", "a"))


@pytest.mark.parametrize("attack", ["one_class", "duplicate", "model", "pseudo", "nan", "artifact"])
def test_bad_calibration_inputs(attack):
    data = examples()
    with pytest.raises(ValueError):
        if attack == "one_class":
            data = tuple(replace(e, label=True) for e in data)
        if attack == "duplicate":
            data = (data[0],) * 4
        if attack == "model":
            data = (replace(data[0], model_signature="wrong"), *data[1:])
        if attack == "pseudo":
            data = (replace(data[0], annotation_source="prediction"), *data[1:])
        if attack == "nan":
            data = (replace(data[0], score=float("nan")), *data[1:])
        if attack == "artifact":
            CalibrationArtifact("x", ("a",), ("b",), float("nan"), 0, 4, "a" * 64)
        else:
            fit_calibration(data)
