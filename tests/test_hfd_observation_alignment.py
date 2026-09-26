"""First review: real fixture decode, source correspondence and downstream effects."""

import hashlib
import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
from test_full_hfd_training import fixture_archive

from cpswm.data_preflight import full_hfd_training as intake_module
from cpswm.data_preflight import hfd_observation_alignment as module
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.perception_mapping.natural_vision import (
    DetectionCandidate,
    NaturalVisionEvidenceProducer,
    VisualFrame,
    decode_rgb,
)
from cpswm.system.reproducibility import content_sha256

NOW = datetime(2026, 9, 26, 12, 30, tzinfo=UTC)


def fixture(tmp_path, monkeypatch):
    archive, metadata, intake = fixture_archive(tmp_path, monkeypatch)
    intake_module.inspect_full_training(archive, metadata, intake)
    output = tmp_path / "aligned"
    args = dict(archive=archive, metadata=metadata, intake=intake, output=output, imported_at=NOW)
    report = module.align_hfd_training(**args)
    return args, report


def runtime_pin(root):
    return hashlib.sha256((root / "runtime/manifest.json").read_bytes()).hexdigest()


def test_exact_original_frames_independent_decode_and_reconstruction(tmp_path, monkeypatch):
    args, report = fixture(tmp_path, monkeypatch)
    assert report["selected_frames"] == 6
    assert len(report["selected_trials"]) == 2
    assert report["complete_proposal_targets"] == 0
    assert not report["native_publication_authorized"]
    assert module.align_hfd_training(**args, verify=True) == report
    observations = module.load_runtime_observations(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )
    labels = [
        json.loads(line)
        for line in (args["output"] / "evaluator/author_supervision.jsonl").read_text().splitlines()
    ]
    for (_, raw), label in zip(observations, labels, strict=True):
        env, pixels = decode_rgb(raw, cutoff=raw.envelope().arrival_time)
        reader = cv2.VideoCapture(str(args["intake"] / f"raw/{label['trial']}/head_cam.mp4"))
        for _ in range(label["author_frame"]["frame_index"] + 1):
            ok, bgr = reader.read()
            assert ok
        reader.release()
        assert np.array_equal(pixels, bgr[:, :, ::-1])
        assert raw.archive_timeline()[1] == label["author_frame"]["timestamp_seconds"]
        assert env.capture_time >= NOW  # Import time, never the author clock as UTC.
        assert label["actor_identity"] is None and label["full_proposal_target"] is None
        assert label["temporal_error_bound_seconds"] is None
    with pytest.raises(FileExistsError):
        module.align_hfd_training(**args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_frame_index", True),
        ("original_frame_index", -1),
        ("original_frame_index", 3),
        ("source_frame_count", 0),
        ("media_time_seconds", 0.2),
        ("author_clock_seconds", float("inf")),
        ("author_clock_origin_seconds", True),
        ("source_clock_sha256", "bad"),
        ("human_action", "interact"),
        ("time_semantics", "exact_contact_time"),
    ],
)
def test_resealed_receipt_cannot_change_clock_or_add_answers(tmp_path, monkeypatch, field, value):
    args, _ = fixture(tmp_path, monkeypatch)
    raw = module.load_runtime_observations(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )[0][1]
    receipt = json.loads(raw.archive_sampling_json)
    receipt[field] = value
    bad = replace(
        raw,
        archive_sampling_json=json.dumps(receipt),
        capture_receipt_sha256=content_sha256(receipt),
    )
    with pytest.raises(ValueError):
        bad.envelope()


@pytest.mark.parametrize(
    "count,expected", [(2, (0, 1)), (3, (0, 1, 2)), (8, (0, 2, 4, 7)), (327, (0, 108, 217, 326))]
)
def test_fixed_original_index_schedule(count, expected):
    assert module.uniform_indices(count) == expected


class FixtureDetector:
    """Explicit synthetic detector; actual frozen-weight execution is separate."""

    def __init__(self, weights_path, household_id, session_id, trace_id):
        self._scope = (household_id, session_id, trace_id)

    def infer(self, raw, *, cutoff):
        from uuid import uuid5

        env, pixels = decode_rgb(raw, cutoff=cutoff)
        timeline = raw.archive_timeline()
        return VisualFrame(
            observation_id=env.identity.observation_id,
            household_id=self._scope[0],
            session_id=self._scope[1],
            trace_id=self._scope[2],
            sensor_id=env.sensor.sensor_id,
            frame_id=env.frame_id,
            capture_time=env.capture_time,
            arrival_time=env.arrival_time,
            inference_cutoff=cutoff,
            input_sha256=hashlib.sha256(raw.payload_bytes).hexdigest(),
            receipt_sha256=raw.capture_receipt_sha256,
            model_id="synthetic-fixture",
            weights_sha256="a" * 64,
            torch_version="fixture",
            torchvision_version="fixture",
            minimum_score=0.5,
            width=pixels.shape[1],
            height=pixels.shape[0],
            candidates=(
                DetectionCandidate(
                    uuid5(env.identity.observation_id, "person"), "person", 0.8, (0, 0, 12, 24)
                ),
                DetectionCandidate(
                    uuid5(env.identity.observation_id, "cup"), "cup", 0.8, (20, 10, 30, 20)
                ),
            ),
            archive_sequence_id=timeline[0],
            archive_media_time=timeline[1],
        )


def frontend_module():
    path = Path(__file__).resolve().parents[1] / "tools/run_hfd_pixel_frontend.py"
    spec = importlib.util.spec_from_file_location("hfd_frontend", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_runtime_isolated_labels_full_candidates_and_core_action_consequences(
    tmp_path, monkeypatch
):
    args, _ = fixture(tmp_path, monkeypatch)
    root = args["output"]
    frontend = frontend_module()
    monkeypatch.setattr(frontend, "FasterNaturalAppearanceDetector", FixtureDetector)
    # Deny reads of *any* evaluator or author files during frontend execution.
    original = Path.open

    def guarded(path, *a, **kw):
        if "evaluator" in path.parts or path.name in {"human_activity.npy", "task_info.json"}:
            raise AssertionError("runtime accessed answers")
        return original(path, *a, **kw)

    monkeypatch.setattr(Path, "open", guarded)
    result = frontend.run(
        root / "runtime", runtime_pin(root), tmp_path / "unused", tmp_path / "run"
    )
    assert result["input_frames"] == 6
    assert result["memory_writes"] == result["executed_actions"] == 0
    assert result["proposal_network_training_steps"] == 0
    assert len(result["sequences"]) == 2
    for row in result["sequences"]:
        assert row["core_ledger_unchanged"] and not row["execution_traces"]
        assert row["support"]["status"] == "COMPLETE_SUPPORT_GENERATED"
        assert row["support"]["candidate_count"] > 1


def test_original_timeline_restore_late_failure_retry_and_model_input(tmp_path, monkeypatch):
    args, _ = fixture(tmp_path, monkeypatch)
    rows = module.load_runtime_observations(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )[:3]
    a, b, c = [r[1] for r in rows]
    scope = a.envelope().identity
    detector = FixtureDetector(None, scope.household_id, scope.session_id, scope.trace_id)
    producer = NaturalVisionEvidenceProducer(detector)
    cutoff = c.envelope().arrival_time + timedelta(seconds=1)
    producer.infer((a, c), cutoff=cutoff)
    before = producer.checkpoint_state()
    bad = replace(b, capture_receipt_sha256="0" * 64)
    with pytest.raises(ValueError):
        producer.infer((a, c, bad), cutoff=cutoff)
    assert producer.checkpoint_state() == before
    producer.infer((a, c, b), cutoff=cutoff)
    assert [r[0].media_time for r in producer.interactions()] == [0, 0.1, 0.2]
    restored = NaturalVisionEvidenceProducer(detector)
    restored.restore_state(producer.checkpoint_state())
    assert restored.frames() == producer.frames()
    assert restored.interactions() == producer.interactions()
    for f in producer.frames():
        model_input = ProposalPixelObservation.from_frame(f).model_input()
        assert not {"trial", "author_outcome", "human_action", "wrench_resampled"} & set(
            model_input
        )
