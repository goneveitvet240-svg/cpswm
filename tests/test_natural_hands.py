"""Synthetic boundary checks. Actual pixel model evidence is recorded separately."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from test_natural_vision import fixture_detector, prediction
from test_structure_two_continuous_input import raw_for, setup

from cpswm.perception_mapping.natural_hands import (
    HAND_MODEL_SHA256,
    HandCandidate,
    HandFrame,
    NaturalHandDetector,
)
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer
from cpswm.system.continuous_state_store import ContinuousStateStore


class FakeHands:
    def __init__(self, detector):
        self._scope = detector._scope
        self.binding = (HAND_MODEL_SHA256, "test-fixture", 4, 0.5, 0.5)
        self.fail = False

    def infer(self, raw, *, cutoff):
        if self.fail:
            raise RuntimeError("hand inference failure")
        env = raw.envelope()
        return HandFrame(
            env.identity.observation_id,
            env.capture_time,
            env.payload.payload_sha256,
            raw.capture_receipt_sha256,
            self.binding,
            4,
            4,
            (HandCandidate(uuid4(), ((1.0, 2.0),) * 21, "Right", 0.9),),
        )


def components():
    _, _, _, transition = setup(False)
    raw = raw_for(transition)
    detector = fixture_detector(raw, prediction())
    hands = FakeHands(detector)
    return raw, detector, hands


def test_wrong_hand_weight_rejected_before_import(tmp_path):
    p = tmp_path / "fake.task"
    p.write_bytes(b"fake")
    with pytest.raises(ValueError, match="pinned"):
        NaturalHandDetector(model_path=p, scope=(uuid4(), uuid4(), uuid4()))


@pytest.mark.parametrize(
    "change",
    [
        {"handedness": "person_A"},
        {"handedness_score": float("nan")},
        {"landmarks_xy_pixels": ((0.0, 0.0),) * 20},
        {"landmarks_xy_pixels": ((float("inf"), 0.0),) * 21},
    ],
)
def test_bad_candidate_rejected(change):
    base = HandCandidate(uuid4(), ((0.0, 0.0),) * 21, "Right", 0.5)
    with pytest.raises(ValueError):
        replace(base, **change)


def test_hand_failure_is_atomic_and_retry_is_possible():
    raw, detector, hands = components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    checkpoint = producer.checkpoint_state()
    hands.fail = True
    with pytest.raises(RuntimeError, match="hand inference"):
        producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    assert producer.checkpoint_state() == checkpoint
    hands.fail = False
    assert producer.infer((raw,), cutoff=raw.envelope().arrival_time) is None
    assert len(producer.hand_frames()) == 1
    state = producer.checkpoint_state()
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    assert producer.checkpoint_state() == state


def test_durable_roundtrip_and_configuration_rejection(tmp_path):
    raw, detector, hands = components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    path = tmp_path / "state.sqlite"
    store = ContinuousStateStore(path, source_identity="a" * 64, dependency_identity="b" * 64)
    store.save(producer.checkpoint_state())
    store.close()
    restored = NaturalVisionEvidenceProducer(detector, hands)
    store = ContinuousStateStore(path, source_identity="a" * 64, dependency_identity="b" * 64)
    state = store.load()
    restored.restore_state(state)
    store.close()
    assert restored.hand_frames() == producer.hand_frames()
    assert "NO_PERSON_CONTACT" in restored.hand_frames()[0].semantic_status
    incompatible = NaturalVisionEvidenceProducer(detector)
    before = incompatible.checkpoint_state()
    with pytest.raises(ValueError, match="hand model"):
        incompatible.restore_state(state)
    assert incompatible.checkpoint_state() == before


@pytest.mark.parametrize(
    "kind",
    [
        "missing_hands",
        "missing_visual",
        "empty_hands",
        "wrong_observation",
        "wrong_model",
        "wrong_pixels",
        "wrong_receipt",
        "wrong_dimensions",
        "wrong_interactions",
        "wrong_visual",
        "hand_privilege",
        "future_cutoff",
        "changed_raw",
    ],
)
def test_malformed_restore_is_rejected_without_partial_mutation(kind):
    from copy import deepcopy
    from datetime import timedelta

    raw, detector, hands = components()
    producer = NaturalVisionEvidenceProducer(detector, hands)
    producer.infer((raw,), cutoff=raw.envelope().arrival_time)
    before = producer.checkpoint_state()
    state = deepcopy(before)
    hand = state["hand_frames"][0]
    if kind == "missing_hands":
        state.pop("hand_frames")
    elif kind == "missing_visual":
        state.pop("frames")
        state["interactions"] = ("partially-applied",)
    elif kind == "empty_hands":
        state["hand_frames"] = ()
    elif kind == "wrong_observation":
        state["hand_frames"] = (replace(hand, observation_id=uuid4()),)
    elif kind == "wrong_model":
        state["hand_frames"] = (replace(hand, model_binding=("0" * 64, "other", 4, 0.5, 0.5)),)
    elif kind == "wrong_pixels":
        state["hand_frames"] = (replace(hand, input_sha256="0" * 64),)
    elif kind == "wrong_receipt":
        state["hand_frames"] = (replace(hand, capture_receipt_sha256="0" * 64),)
    elif kind == "wrong_dimensions":
        state["hand_frames"] = (replace(hand, width=999),)
    elif kind == "wrong_interactions":
        state["interactions"] = ()
    elif kind == "wrong_visual":
        state["frames"] = (replace(state["frames"][0], observation_id=uuid4()),)
    elif kind == "hand_privilege":
        state["hand_frames"] = (replace(hand, semantic_status="CALIBRATED_ACTOR"),)
    elif kind == "future_cutoff":
        state["cutoff"] -= timedelta(seconds=1)
    elif kind == "changed_raw":
        state["prefix"] = (replace(raw, payload_bytes=raw.payload_bytes + b"changed"),)
    with pytest.raises(ValueError):
        producer.restore_state(state)
    assert producer.checkpoint_state() == before
