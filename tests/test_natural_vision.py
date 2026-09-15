"""Boundary tests use synthetic pixels/model outputs; real inference is separate."""

import hashlib
import io
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import numpy as np
import pytest
from test_structure_two_continuous_input import raw_for, setup

from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector, decode_rgb


@pytest.fixture
def raw():
    _, _, _, transition = setup(False)
    return raw_for(transition)


def with_pixels(raw, pixels):
    wire = io.BytesIO()
    np.save(wire, pixels, allow_pickle=False)
    payload = wire.getvalue()
    env = raw.envelope()
    env = env.model_copy(
        update={
            "payload": env.payload.model_copy(
                update={
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
            )
        }
    )
    return replace(raw, envelope_json=env.model_dump_json(), payload_bytes=payload)


def test_decode_real_wire_shape_and_detachment(raw):
    env, pixels = decode_rgb(raw, cutoff=raw.envelope().arrival_time)
    assert pixels.shape == (4, 4, 3) and pixels.dtype == np.uint8
    pixels[:] = 255
    assert not decode_rgb(raw, cutoff=env.arrival_time)[1].any()


@pytest.mark.parametrize(
    "kind", ["float", "gray", "channels", "trailing", "hash", "future", "unit", "receipt"]
)
def test_bad_wire_rejected(raw, kind):
    when = raw.envelope().arrival_time
    if kind == "float":
        raw = with_pixels(raw, np.zeros((4, 4, 3), np.float32))
    if kind == "gray":
        raw = with_pixels(raw, np.zeros((4, 4), np.uint8))
    if kind == "channels":
        raw = with_pixels(raw, np.zeros((4, 4, 4), np.uint8))
    if kind == "hash":
        raw = replace(raw, payload_bytes=raw.payload_bytes + b"x")
    if kind == "future":
        when -= timedelta(seconds=1)
    if kind == "unit":
        raw = replace(raw, depth_unit="m")
    if kind == "receipt":
        raw = replace(raw, capture_receipt_sha256="z" * 64)
    if kind == "trailing":
        payload = raw.payload_bytes + b"x"
        env = raw.envelope()
        env = env.model_copy(
            update={
                "payload": env.payload.model_copy(
                    update={
                        "payload_sha256": hashlib.sha256(payload).hexdigest(),
                        "size_bytes": len(payload),
                    }
                )
            }
        )
        raw = replace(raw, envelope_json=env.model_dump_json(), payload_bytes=payload)
    with pytest.raises(ValueError):
        decode_rgb(raw, cutoff=when)


def test_wrong_weight_rejected_without_loading_model(tmp_path):
    weights = tmp_path / "fake.pth"
    weights.write_bytes(b"not pretrained weights")
    with pytest.raises(ValueError, match="pinned"):
        NaturalAppearanceDetector(
            weights_path=weights, household_id=uuid4(), session_id=uuid4(), trace_id=uuid4()
        )


def fixture_detector(raw, prediction):
    import torch

    detector = object.__new__(NaturalAppearanceDetector)
    env = raw.envelope()
    detector._scope = (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
    detector._torch = torch
    detector._versions = ("fixture", "fixture")
    detector._categories = ("background", "person", "cup")
    detector._minimum_score = 0.5

    class FixtureModel:
        calls = 0

        def __call__(self, tensors):
            self.calls += 1
            assert tensors[0].shape == (3, 4, 4)
            return [prediction]

    detector._model = FixtureModel()
    return detector


def prediction(**updates):
    import torch

    data = {
        "boxes": torch.tensor([[0.0, 0.0, 3.0, 3.0]]),
        "scores": torch.tensor([0.75]),
        "labels": torch.tensor([1]),
    }
    data.update(updates)
    return data


def test_frame_candidates_are_not_identity_pose_or_negative_evidence(raw):
    detector = fixture_detector(raw, prediction())
    frame = detector.infer(raw, cutoff=raw.envelope().arrival_time)
    assert frame.candidates[0].category == "person"
    assert frame.identity_status == "UNRESOLVED" and frame.pose_status == "NOT_ESTIMATED"
    assert frame.calibration_status == "UNCALIBRATED_CANDIDATES_ONLY"
    assert not frame.negative_observation_authorized
    assert frame.input_sha256 == hashlib.sha256(raw.payload_bytes).hexdigest()
    assert detector.infer(raw, cutoff=frame.inference_cutoff) == frame


def test_scope_and_future_rejected_before_inference(raw):
    detector = fixture_detector(raw, prediction())
    detector._scope = (uuid4(), uuid4(), uuid4())
    with pytest.raises(ValueError, match="scope"):
        detector.infer(raw, cutoff=raw.envelope().arrival_time)
    assert detector._model.calls == 0


@pytest.mark.parametrize("kind", ["nan", "outside", "degenerate", "label", "length", "score"])
def test_bad_model_output_rejected(raw, kind):
    import torch

    p = prediction()
    if kind == "nan":
        p["scores"][0] = float("nan")
    if kind == "outside":
        p["boxes"][0, 2] = 5
    if kind == "degenerate":
        p["boxes"][0, 2] = 0
    if kind == "label":
        p["labels"][0] = 99
    if kind == "length":
        p["labels"] = torch.tensor([], dtype=torch.int64)
    if kind == "score":
        p["scores"][0] = 1.1
    detector = fixture_detector(raw, p)
    with pytest.raises(ValueError):
        detector.infer(raw, cutoff=raw.envelope().arrival_time)


def test_no_detection_does_not_authorize_absence(raw):
    import torch

    detector = fixture_detector(raw, prediction(scores=torch.tensor([0.1])))
    result = detector.infer(raw, cutoff=raw.envelope().arrival_time)
    assert result.candidates == () and not result.negative_observation_authorized


def test_producer_connects_to_continuous_stream_without_fabricating_memory(raw):
    from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    probe, _, _, transition = setup(False)
    raw = raw_for(transition)
    producer = NaturalVisionEvidenceProducer(fixture_detector(raw, prediction()))
    scope = raw.envelope().identity
    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="legacy_component_diagnostic",
        household_id=scope.household_id,
        session_id=scope.session_id,
        trace_id=scope.trace_id,
        producer=producer,
    )
    when = raw.envelope().arrival_time
    before = probe.system.core.current_snapshot
    stream.admit((raw,), received_at=when)
    assert stream.advance(cutoff=when).status == "INSUFFICIENT_SEMANTIC_EVIDENCE"
    assert len(producer.frames()) == 1
    assert stream.advance(cutoff=when).status == "INSUFFICIENT_SEMANTIC_EVIDENCE"
    assert producer._detector._model.calls == 1
    assert probe.system.core.current_snapshot == before and not stream.execution_traces()


def test_producer_rejects_history_changes_and_keeps_journal_atomic(raw):
    from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer

    p = NaturalVisionEvidenceProducer(fixture_detector(raw, prediction()))
    when = raw.envelope().arrival_time
    p.infer((raw,), cutoff=when)
    before = p.frames()
    for prefix in ((), (raw, raw)):
        with pytest.raises(ValueError):
            p.infer(prefix, cutoff=when)
    with pytest.raises(ValueError):
        p.infer((raw,), cutoff=when - timedelta(seconds=1))
    assert p.frames() == before and p._detector._model.calls == 1
    assert p.infer((raw,), cutoff=when) is None


def test_alternative_detector_keeps_distinct_candidate_and_restore_binding(raw):
    from cpswm.perception_mapping.natural_vision import (
        FasterNaturalAppearanceDetector,
        NaturalVisionEvidenceProducer,
    )

    original = fixture_detector(raw, prediction())
    alternative = object.__new__(FasterNaturalAppearanceDetector)
    alternative.__dict__.update(original.__dict__)
    when = raw.envelope().arrival_time
    first, second = original.infer(raw, cutoff=when), alternative.infer(raw, cutoff=when)
    assert first.observation_id == second.observation_id
    assert first.input_sha256 == second.input_sha256
    assert first.model_id != second.model_id
    assert first.weights_sha256 != second.weights_sha256
    assert first.candidates[0].candidate_id != second.candidates[0].candidate_id
    assert second.calibration_status == "UNCALIBRATED_CANDIDATES_ONLY"
    old = NaturalVisionEvidenceProducer(original).checkpoint_state()
    with pytest.raises(ValueError, match="configuration changed"):
        NaturalVisionEvidenceProducer(alternative).restore_state(old)


def test_native_resize_roundoff_is_counted_without_accepting_real_overflow(raw):
    import torch

    epsilon = float(np.spacing(np.float32(4)))
    data = prediction(boxes=torch.tensor([[-epsilon, 0.0, 4.0 + epsilon, 4.0]]))
    detector = fixture_detector(raw, data)
    frame = detector.infer(raw, cutoff=raw.envelope().arrival_time)
    assert frame.candidates[0].box_xyxy == (0.0, 0.0, 4.0, 4.0)
    assert frame.resize_roundoff_clamps == 1
    assert float(data["boxes"][0, 0]) < 0  # original output is not mutated
    data["boxes"][0, 2] = 4.0 + 4 * epsilon
    with pytest.raises(ValueError, match="numerical resize bound"):
        detector.infer(raw, cutoff=raw.envelope().arrival_time)
