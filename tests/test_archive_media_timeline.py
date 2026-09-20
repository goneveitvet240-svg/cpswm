import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_natural_hands import FakeHands
from test_natural_vision import fixture_detector, prediction
from test_structure_two_continuous_input import raw_for, setup

from cpswm.contracts.base import SourceType
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256


def raw_media(raw, time):
    env = raw.envelope()
    env = env.model_copy(
        update={
            "metadata": env.metadata.model_copy(
                update={
                    "source_type": SourceType.IMPORT,
                    "source_id": "https://example.test/source.mp4",
                }
            ),
            "clock_domain": "archive-import-acquisition-utc",
        }
    )
    receipt = dict(
        source_url=env.metadata.source_id,
        source_sha256="a" * 64,
        crop_xywh=[0, 0, 4, 4],
        sampling_grid_time_seconds=time,
        sampling_fps=2,
        time_semantics="resampled_grid_not_original_exposure",
        payload_sha256=env.payload.payload_sha256,
        observation_id=str(env.identity.observation_id),
    )
    return replace(
        raw,
        envelope_json=env.model_dump_json(),
        capture_receipt_sha256=content_sha256(receipt),
        archive_sampling_json=json.dumps(receipt),
    )


def test_media_association_does_not_depend_on_inference_wall_clock_and_restores(tmp_path):
    _, _, _, transition = setup(False)
    t = transition.after.detection_time
    a = raw_media(raw_for(transition, capture=t, arrival=t), 0.0)
    b = raw_media(
        raw_for(transition, capture=t + timedelta(seconds=30), arrival=t + timedelta(seconds=30)),
        0.5,
    )
    detector = fixture_detector(a, prediction())
    p = NaturalVisionEvidenceProducer(detector, FakeHands(detector))
    p.infer((a, b), cutoff=t + timedelta(seconds=30))
    first, second = [a for a, _ in p.interactions()]
    assert first.media_time == 0 and second.media_time == 0.5
    assert any(d.status == "ASSOCIATED_GEOMETRIC" for d in second.detections)
    store = ContinuousStateStore(
        tmp_path / "state.sqlite", source_identity="c" * 64, dependency_identity="d" * 64
    )
    store.save(p.checkpoint_state())
    state = store.load()
    store.close()
    restored = NaturalVisionEvidenceProducer(detector, FakeHands(detector))
    restored.restore_state(state)
    assert restored.hand_object_evidence() == p.hand_object_evidence()
    assert restored.interactions() == p.interactions()


@pytest.mark.parametrize(
    "field,value",
    [
        ("sampling_grid_time_seconds", -1),
        ("sampling_fps", 0),
        ("payload_sha256", "b" * 64),
        ("observation_id", "wrong"),
        ("crop_xywh", [0, 0, 9, 9]),
        ("time_semantics", "real_exposure"),
        ("source_url", "https://example.test/other"),
    ],
)
def test_rejects_bad_sampling_even_with_recomputed_receipt(field, value):
    _, _, _, transition = setup(False)
    raw = raw_media(raw_for(transition), 0.0)
    receipt = json.loads(raw.archive_sampling_json)
    receipt[field] = value
    bad = replace(
        raw,
        archive_sampling_json=json.dumps(receipt),
        capture_receipt_sha256=content_sha256(receipt),
    )
    detector = fixture_detector(raw, prediction())
    p = NaturalVisionEvidenceProducer(detector, FakeHands(detector))
    before = p.checkpoint_state()
    with pytest.raises(ValueError):
        p.infer((bad,), cutoff=raw.envelope().arrival_time)
    assert p.checkpoint_state() == before


def test_timeline_change_cannot_reuse_old_receipt():
    _, _, _, transition = setup(False)
    raw = raw_media(raw_for(transition), 0.0)
    receipt = json.loads(raw.archive_sampling_json)
    receipt["sampling_grid_time_seconds"] = 1.0
    with pytest.raises(ValueError):
        replace(raw, archive_sampling_json=json.dumps(receipt)).envelope()
