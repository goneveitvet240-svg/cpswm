"""First review: contiguous source selection and the real downstream component path."""

import hashlib
import importlib.util
import io
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import ClassVar
from uuid import uuid5

import cv2
import numpy as np
import pytest
from test_full_hfd_training import fixture_archive, npy
from test_hfd_observation_alignment import NOW, FixtureDetector, runtime_pin

from cpswm.data_preflight import full_hfd_training as intake_module
from cpswm.data_preflight import hfd_observation_alignment as module
from cpswm.perception_mapping.natural_hands import HAND_MODEL_SHA256, HandCandidate, HandFrame
from cpswm.perception_mapping.natural_vision import DetectionCandidate, decode_rgb


def dense_fixture(tmp_path, monkeypatch, *, count=20, sampling="continuous"):
    movie = tmp_path / "dense.mp4"
    writer = cv2.VideoWriter(str(movie), cv2.VideoWriter_fourcc(*"mp4v"), 30, (48, 32))
    assert writer.isOpened()
    for i in range(count):
        writer.write(np.full((32, 48, 3), i * 7 % 255, dtype=np.uint8))
    writer.release()

    def mutate(values):
        for trial in range(2):
            base = f"training_set/trial{trial:04d}/"
            origin = trial * 10
            arrays = {
                "head_cam_ts": origin + np.arange(count) / 30,
                "wrench_ts": origin + np.arange(count + 1) / 30,
                "human_activity": np.zeros(count, dtype=int),
                "robot_actions": np.zeros(count, dtype=int),
                "wrench": np.zeros((count + 1, 6)),
                "wrench_resampled": np.zeros((count, 6)),
            }
            values.update({base + name + ".npy": npy(value) for name, value in arrays.items()})
            values[base + "head_cam.mp4"] = movie.read_bytes()

    archive, metadata, intake = fixture_archive(tmp_path, monkeypatch, mutate=mutate)
    intake_module.inspect_full_training(archive, metadata, intake)
    args = dict(
        archive=archive,
        metadata=metadata,
        intake=intake,
        output=tmp_path / "aligned",
        imported_at=NOW,
        sampling=sampling,
    )
    report = module.align_hfd_training(**args)
    return args, report


@pytest.mark.parametrize("count", (2, 3, 4, 5, 7, 16, 20, 249, 584))
def test_fixed_contiguous_windows_retain_endpoints_and_deduplicate_source(count):
    windows = module.sample_windows(count, "continuous")
    assert 1 <= len(windows) <= 4
    assert len(set(windows)) == len(windows)
    assert windows[0][0] == 0 and windows[-1][-1] == count - 1
    assert all(w == tuple(range(w[0], w[0] + min(count, 4))) for w in windows)
    assert all(0 <= i < count for w in windows for i in w)


def test_source_reconstruction_and_original_pixels_cover_declared_windows(tmp_path, monkeypatch):
    args, report = dense_fixture(tmp_path, monkeypatch)
    assert report["selected_frames"] == 32 and report["selected_windows"] == 8
    assert report["frame_presentations"] == 32
    assert module.align_hfd_training(**args, verify=True) == report
    windows = module.load_runtime_windows(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )
    assert len(windows) == 8 and all(len(rows) == 4 for _, rows in windows)
    for _, rows in windows:
        receipts = [json.loads(raw.archive_sampling_json) for _, raw in rows]
        assert [r["original_frame_index"] for r in receipts] == list(
            range(receipts[0]["original_frame_index"], receipts[0]["original_frame_index"] + 4)
        )
        reader = cv2.VideoCapture(str(args["intake"] / "raw/trial0000/head_cam.mp4"))
        frames = []
        while True:
            ok, bgr = reader.read()
            if not ok:
                break
            frames.append(bgr[:, :, ::-1])
        reader.release()
        for (_, raw), receipt in zip(rows, receipts, strict=True):
            assert np.array_equal(
                np.load(io.BytesIO(raw.payload_bytes), allow_pickle=False),
                frames[receipt["original_frame_index"]],
            )


def test_overlap_is_counted_as_shared_source_not_independent_frames(tmp_path, monkeypatch):
    args, report = dense_fixture(tmp_path, monkeypatch, count=7)
    windows = module.load_runtime_windows(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )
    assert report["selected_frames"] == 14 and report["frame_presentations"] == 32
    assert len({key for _, rows in windows for key, _ in rows}) == 14
    assert sum(len(rows) for _, rows in windows) == 32


class TwoPeopleDetector(FixtureDetector):
    def infer(self, raw, *, cutoff):
        frame = super().infer(raw, cutoff=cutoff)
        return replace(
            frame,
            candidates=(
                *frame.candidates,
                DetectionCandidate(
                    uuid5(frame.observation_id, "second"), "person", 0.8, (33, 0, 47, 30)
                ),
            ),
        )


class FixtureHands:
    instances: ClassVar[list] = []
    fail = False

    def __init__(self, model_path, scope, person_rois):
        self._scope = scope
        self.binding = (HAND_MODEL_SHA256, "controlled-fixture", 4, 0.5, 0.5)
        self.closed = False
        self.instances.append(self)

    def infer(self, raw, *, cutoff):
        if self.fail:
            raise RuntimeError("injected hand failure")
        env, pixels = decode_rgb(raw, cutoff=cutoff)
        return HandFrame(
            env.identity.observation_id,
            env.capture_time,
            hashlib.sha256(raw.payload_bytes).hexdigest(),
            raw.capture_receipt_sha256,
            self.binding,
            pixels.shape[1],
            pixels.shape[0],
            (
                HandCandidate(
                    uuid5(env.identity.observation_id, "fixture-hand"),
                    ((6.0, 12.0),) * 21,
                    "Right",
                    0.9,
                ),
            ),
        )

    def close(self):
        self.closed = True


def frontend_module():
    tools = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location(
        "hfd_continuous_frontend", tools / "run_hfd_continuous_frontend.py"
    )
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_continuous_frontend_hand_geometry_association_and_memory_consequences(
    tmp_path, monkeypatch
):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    front = frontend_module()
    monkeypatch.setattr(front, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(front, "NaturalHandDetector", FixtureHands)
    monkeypatch.setattr(FixtureHands, "instances", [])
    original = Path.open

    def guard(path, *a, **kw):
        if "evaluator" in path.parts or path.name in {"human_activity.npy", "task_info.json"}:
            raise AssertionError("runtime accessed author answers")
        return original(path, *a, **kw)

    monkeypatch.setattr(Path, "open", guard)
    result = front.run(
        args["output"] / "runtime",
        runtime_pin(args["output"]),
        tmp_path / "weights",
        tmp_path / "hands",
        tmp_path / "run",
    )
    assert result["unique_input_frames"] == 32 and result["frame_presentations"] == 32
    assert result["associations_per_presentation"]["ASSOCIATED_GEOMETRIC"] > 0
    assert result["role_alternatives"] > 0
    assert result["regional_hand_candidates"] == 32 and result["hand_object_measurements"] == 32
    assert all(
        r["perception_restore_equal"] and r["core_ledger_unchanged"] for r in result["windows"]
    )
    assert all(r["support"]["status"] == "COMPLETE_SUPPORT_GENERATED" for r in result["windows"])
    assert (
        result["memory_writes"]
        == result["executed_actions"]
        == result["natural_semantic_publications"]
        == 0
    )
    assert len(FixtureHands.instances) == 2 and all(h.closed for h in FixtureHands.instances)


def test_hand_failure_closes_resource_and_has_no_success_manifest(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    front = frontend_module()
    monkeypatch.setattr(front, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(front, "NaturalHandDetector", FixtureHands)
    monkeypatch.setattr(FixtureHands, "instances", [])
    monkeypatch.setattr(FixtureHands, "fail", True)
    with pytest.raises(RuntimeError, match="injected hand failure"):
        front.run(
            args["output"] / "runtime",
            runtime_pin(args["output"]),
            tmp_path / "weights",
            tmp_path / "hands",
            tmp_path / "run",
        )
    assert not (tmp_path / "run/result.json").exists()
    assert all(h.closed for h in FixtureHands.instances)


def test_sparse_package_cannot_be_relabelled_as_continuous_by_frontend(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch, sampling="sparse")
    with pytest.raises(ValueError, match="continuous windows require"):
        module.load_runtime_windows(
            args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
        )
