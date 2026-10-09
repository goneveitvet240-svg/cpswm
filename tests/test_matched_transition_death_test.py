"""Frozen-input and attack checks for the matched transition experiment."""

from __future__ import annotations

import base64
import gzip
import io
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import numpy as np
import pytest
import run_matched_transition_death_test as driver
from test_natural_mask_surface import model, wires

pytest.importorskip("torch")


def frozen_panel(tmp_path):
    scope = tuple(uuid4() for _ in range(3))
    detector, _ = model(scope)
    observations, cutoff = wires(scope)
    frame = detector.infer_surface(observations, cutoff=cutoff)
    action_id = str(uuid4())
    raw = dict(
        action_id=action_id,
        action="Pass",
        degrees=0.0,
        decision_time=(cutoff - timedelta(seconds=1)).isoformat(),
        received_at=cutoff.isoformat(),
        success=True,
        error="",
        observations=[
            dict(
                envelope_json=row.envelope_json,
                payload_base64=base64.b64encode(row.payload_bytes).decode(),
                capture_receipt_sha256=row.capture_receipt_sha256,
                depth_unit=row.depth_unit,
            )
            for row in observations
        ],
    )
    prediction = {"detector": frame.record}
    root = tmp_path / "source"
    folder = root / "public/000"
    folder.mkdir(parents=True)
    driver.save(folder / "raw.json", raw)
    driver.save(folder / "prediction.json", prediction)
    (folder / "masks.npy.gz").write_bytes(gzip.compress(frame.masks_npy, mtime=0))
    item = dict(
        index=0,
        action_id=action_id,
        raw="public/000/raw.json",
        raw_sha256=driver.digest(folder / "raw.json"),
        prediction="public/000/prediction.json",
        prediction_sha256=driver.digest(folder / "prediction.json"),
        masks="public/000/masks.npy.gz",
        masks_sha256=driver.digest(folder / "masks.npy.gz"),
    )
    manifest = dict(
        schema=driver.SCHEMA,
        capture_result_sha256="a" * 64,
        schedule=[dict(action="Pass", degrees=0.0)],
        queries=[dict(category="bottle", ordinal=0)],
        budget=1,
        physical_dispatches=1,
        frames=[item],
        detector_runs=1,
        inference_truth_isolation="SDK artifacts are evaluator-only",
    )
    manifest["input_sha256"] = driver.content_sha256(manifest)
    manifest_path = tmp_path / "manifest.json"
    driver.save(manifest_path, manifest)
    return root, manifest_path, manifest, raw, prediction, frame.masks_npy, observations, cutoff


def test_frozen_replay_is_byte_deterministic(tmp_path, monkeypatch):
    root, manifest_path, *_ = frozen_panel(tmp_path)
    monkeypatch.setattr(driver, "_head_sha", lambda: "candidate")
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    driver.replay(root, manifest_path, first, arm="candidate", expected_sha="candidate")
    driver.replay(root, manifest_path, second, arm="candidate", expected_sha="candidate")
    assert first.read_bytes() == second.read_bytes()
    result = driver.load(first)
    assert result["detector_runs"] == 0
    assert result["source_physical_dispatches"] == 1
    assert result["steps"][0]["reports"][0]["status"] == "reported"


@pytest.mark.parametrize("attack", ["payload", "mask", "candidate_order"])
def test_complete_frozen_input_attack_is_rejected(tmp_path, attack):
    _, _, _, raw, prediction, masks, *_ = frozen_panel(tmp_path)
    if attack == "payload":
        raw = deepcopy(raw)
        raw["observations"][0]["payload_base64"] = base64.b64encode(b"replacement").decode()
    elif attack == "mask":
        array = np.load(io.BytesIO(masks), allow_pickle=False)
        array = array.copy()
        array[0, 0, 0] = 1.0 - array[0, 0, 0]
        wire = io.BytesIO()
        np.save(wire, array, allow_pickle=False)
        masks = wire.getvalue()
    else:
        prediction = deepcopy(prediction)
        prediction["detector"]["candidates"][0]["native_index"] = 1
    with pytest.raises(ValueError):
        driver._validate_frozen_frame(raw, prediction, masks)


def test_rehashed_mask_substitution_and_source_sha_are_rejected(tmp_path, monkeypatch):
    root, manifest_path, manifest, _raw, _prediction, masks, observations, cutoff = frozen_panel(
        tmp_path
    )
    array = np.load(io.BytesIO(masks), allow_pickle=False).copy()
    array[0, 0, 0] = 1.0 - array[0, 0, 0]
    wire = io.BytesIO()
    np.save(wire, array, allow_pickle=False)
    attack = root / "public/000/complete-replacement.npy.gz"
    attack.write_bytes(gzip.compress(wire.getvalue(), mtime=0))
    attacked = deepcopy(manifest)
    attacked["frames"][0]["masks"] = str(attack.relative_to(root))
    attacked["frames"][0]["masks_sha256"] = sha256(attack.read_bytes()).hexdigest()
    attacked["input_sha256"] = driver.content_sha256(
        {key: value for key, value in attacked.items() if key != "input_sha256"}
    )
    detector = driver.FrozenDetector(root, attacked)
    with pytest.raises(ValueError, match="mask bytes"):
        detector.infer_surface(observations, cutoff=cutoff)

    monkeypatch.setattr(driver, "_head_sha", lambda: "wrong")
    with pytest.raises(ValueError, match="source checkout"):
        driver.replay(
            root,
            manifest_path,
            tmp_path / "forbidden.json",
            arm="candidate",
            expected_sha="candidate",
        )


def test_ambiguity_control_is_explicit_and_rebinds_native_masks(tmp_path):
    root, _, manifest, _, _, _, observations, cutoff = frozen_panel(tmp_path)
    candidate = driver.load(root / manifest["frames"][0]["prediction"])["detector"]["candidates"][0]
    detector = driver.FrozenDetector(
        root,
        manifest,
        duplicate_frame=0,
        duplicate_candidate=candidate["candidate_id"],
    )
    frame = detector.infer_surface(observations, cutoff=cutoff)
    array = np.load(io.BytesIO(frame.masks_npy), allow_pickle=False)
    assert frame.record["adversarial_control"]["type"] == "complete_duplicate_native_candidate"
    assert len(frame.record["candidates"]) == len(array) == 2
    assert frame.record["masks_npy_sha256"] == sha256(frame.masks_npy).hexdigest()
