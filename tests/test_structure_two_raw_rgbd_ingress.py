"""Raw boundary tests; synthetic unit pixels are not claimed as real perception."""

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pytest

from cpswm.perception_mapping.adapters.rgbd_capture import adapt_raw_rgbd_capture

NOW = datetime(2026, 9, 13, tzinfo=UTC)
IDENTITY = UUID("00000000-0000-4000-8000-000000000123")


def fixture():
    stream = io.BytesIO()
    np.savez(
        stream,
        rgb=np.arange(18, dtype=np.uint8).reshape(2, 3, 3),
        depth=np.ones((2, 3), dtype=np.float32),
    )
    raw = stream.getvalue()
    receipt = dict(
        run_id="actual-run",
        step_index=3,
        request={"action": "Pass"},
        request_time=NOW.isoformat(),
        received_at=(NOW + timedelta(seconds=1)).isoformat(),
        last_action_success=True,
        sensor_file="000003.npz",
        sensor_sha256=hashlib.sha256(raw).hexdigest(),
        depth_unit="m",
        status="RAW_OBSERVATION_CANDIDATE_NOT_METHOD_AUTHORIZATION",
    )
    return receipt, raw


def call(receipt=None, raw=None, **changes):
    base, payload = fixture()
    encoded = json.dumps(base if receipt is None else receipt).encode()
    kwargs = dict(
        receipt_bytes=encoded,
        sensor_bytes=payload if raw is None else raw,
        expected_receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        expected_run_id="actual-run",
        household_id=IDENTITY,
        session_id=IDENTITY,
        trace_id=IDENTITY,
        sensor_id="camera",
        frame_id="camera-optical",
        delivered_at=NOW + timedelta(seconds=3),
        cutoff=NOW + timedelta(seconds=4),
    )
    kwargs.update(changes)
    return adapt_raw_rgbd_capture(**kwargs)


def test_arrays_clocks_identity_and_mutable_consumer_are_separated():
    rows = call()
    assert len(rows) == 2
    assert [r.envelope().sensor.modality for r in rows] == ["rgb", "depth"]
    for row in rows:
        env = row.envelope()
        assert env.capture_time == NOW + timedelta(seconds=1)
        assert env.arrival_time == NOW + timedelta(seconds=3)
        assert not env.oracle_channel and env.oracle_payload is None
        assert "request" not in row.envelope_json
        assert env.payload.payload_uri is None
        with pytest.raises(ValueError, match="frozen"):
            env.sensor.sensor_id = "mutated"
        object.__setattr__(env.sensor, "sensor_id", "mutated")
        assert row.envelope().sensor.sensor_id != "mutated"
        assert np.load(io.BytesIO(row.payload_bytes), allow_pickle=False).size > 0
    assert [r.envelope().identity.observation_id for r in rows] == [
        r.envelope().identity.observation_id for r in call()
    ]
    assert rows[0].envelope().identity.observation_id != rows[1].envelope().identity.observation_id


@pytest.mark.parametrize(
    "change",
    [
        {"expected_run_id": "other"},
        {"sensor_id": ""},
        {"frame_id": ""},
        {"expected_receipt_sha256": "0" * 64},
        {"sensor_bytes": b"forged"},
        {"delivered_at": NOW},
        {"cutoff": NOW},
        {"delivered_at": datetime(2026, 9, 13)},
    ],
)
def test_rejects_foreign_tampered_or_unreleased_input(change):
    with pytest.raises(ValueError):
        call(**change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("step_index", True),
        ("sensor_file", "../000003.npz"),
        ("depth_unit", "mm"),
        ("last_action_success", 1),
        ("status", "trusted"),
    ],
)
def test_resealed_invalid_receipts_are_not_authority(field, value):
    receipt, raw = fixture()
    receipt[field] = value
    with pytest.raises(ValueError):
        call(receipt, raw)


def test_complete_metadata_cannot_become_model_payload():
    receipt, raw = fixture()
    receipt["objects"] = [{"actor": "owner"}]
    with pytest.raises(ValueError):
        call(receipt, raw)


def test_failed_action_pixels_do_not_claim_success_and_duplicate_fields_rejected():
    receipt, raw = fixture()
    receipt["last_action_success"] = False
    assert len(call(receipt, raw)) == 2
    encoded = json.dumps(receipt).encode()
    duplicate = encoded[:-1] + b', "step_index":3}'
    with pytest.raises(ValueError, match="duplicate"):
        call(receipt_bytes=duplicate, expected_receipt_sha256=hashlib.sha256(duplicate).hexdigest())


def test_arrays_cannot_smuggle_extra_truth_even_with_updated_hash():
    receipt, _ = fixture()
    stream = io.BytesIO()
    np.savez(
        stream,
        rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        depth=np.ones((2, 3), dtype=np.float32),
        actor_truth=np.array([1]),
    )
    raw = stream.getvalue()
    receipt["sensor_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        call(receipt, raw)
