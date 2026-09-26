"""Explicit tiny fixtures exercise source binding, full forgery and quarantine."""

import hashlib
import io
import json
import tarfile

import cv2
import numpy as np
import pytest

from cpswm.data_preflight import full_hfd_training as module


def npy(value):
    stream = io.BytesIO()
    np.save(stream, value, allow_pickle=False)
    return stream.getvalue()


def video(tmp_path):
    path = tmp_path / "fixture.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (48, 32))
    assert writer.isOpened()
    try:
        for i in range(3):
            writer.write(np.full((32, 48, 3), i * 70, dtype=np.uint8))
    finally:
        writer.release()
    return path.read_bytes()


def fixture_archive(tmp_path, monkeypatch, *, mutate=None, additions=()):
    outcomes = {
        f"trial{i:04d}": {
            "robot": "Kinova Gen3",
            "task": "human to robot handover",
            "outcome": 0 if i == 0 else 3,
        }
        for i in range(2)
    }
    values = {}
    movie = video(tmp_path)
    for i, (trial, outcome) in enumerate(outcomes.items()):
        arrays = {
            "head_cam_ts": np.array([0.0, 0.1, 0.2]),
            "wrench_ts": np.array([0.0, 0.05, 0.1, 0.2]),
            "human_activity": np.array([0, 2, 3] if i == 0 else [0, 6, 6]),
            "robot_actions": np.array([0, 2, 3]),
            "wrench": np.zeros((4, 6)),
            "wrench_resampled": np.zeros((3, 6)),
        }
        prefix = f"training_set/{trial}/"
        values.update({prefix + name + ".npy": npy(value) for name, value in arrays.items()})
        values[prefix + "task_info.json"] = module.encoded(
            {k: outcome[k] for k in ("robot", "task")}
        )
        values[prefix + "head_cam.mp4"] = movie
        values[prefix + "flow/derived.jpg"] = b"ignored derived feature, never a raw observation"
    if mutate is not None:
        mutate(values)
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for name, value in [*values.items(), *additions]:
            info = tarfile.TarInfo(name)
            info.size = len(value)
            stream.addfile(info, io.BytesIO(value))
    payload = archive.read_bytes()
    # Test-only replacement of the trusted fixture root. The public CLI cannot
    # select these roots and continues to require the 9.2 GB published archive.
    monkeypatch.setattr(module, "ARCHIVE_BYTES", len(payload))
    monkeypatch.setattr(module, "ARCHIVE_MD5", hashlib.md5(payload).hexdigest())
    monkeypatch.setattr(module, "load_author_metadata", lambda _: (outcomes, {"fixture": "a" * 64}))
    return archive, tmp_path / "metadata", tmp_path / "packet"


def test_complete_fixture_positive_and_failure_both_remain_source_bound(tmp_path, monkeypatch):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    result = module.inspect_full_training(archive, metadata, output)
    assert result["report"]["accepted_trials"] == 2
    assert result["report"]["accepted_success_trials"] == 1
    assert result["report"]["accepted_frames"] == 6
    assert not result["report"]["native_publication_authorized"]
    assert not result["report"]["full_proposal_training_ready"]
    assert not result["report"]["exact_contact_release_gold"]
    assert len(result["raw_members"]) == 16 and len(result["evaluator_files"]) == 2
    assert module.inspect_full_training(archive, metadata, output, verify=True) == result
    with pytest.raises(FileExistsError):
        module.inspect_full_training(archive, metadata, output)


@pytest.mark.parametrize("attack", ("rows", "raw", "outcome", "authority", "omission", "extra"))
def test_complete_resealed_packet_forgery_is_checked_against_author_bytes(
    tmp_path, monkeypatch, attack
):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    original = module.inspect_full_training(archive, metadata, output)
    payload = json.loads((output / "manifest.json").read_bytes())
    changed = None
    backup = None
    if attack in {"rows", "raw"}:
        relative = (
            "evaluator/trial0000/author_rows.jsonl"
            if attack == "rows"
            else "raw/trial0000/human_activity.npy"
        )
        changed = output / relative
        backup = changed.read_bytes()
        replacement = (output / relative.replace("trial0000", "trial0001")).read_bytes()
        changed.write_bytes(replacement)
        index = "evaluator_files" if attack == "rows" else "raw_members"
        payload[index][relative].update(
            bytes=len(replacement), sha256=hashlib.sha256(replacement).hexdigest()
        )
    elif attack == "outcome":
        payload["report"]["trials"][0]["outcome"] = 3
        payload["report"]["accepted_success_trials"] = 0
    elif attack == "authority":
        payload["report"].update(
            native_publication_authorized=True, exact_contact_release_gold=True
        )
    elif attack == "omission":
        payload["report"]["trials"] = payload["report"]["trials"][:1]
        payload["report"]["accepted_trials"] = 1
    else:
        changed = output / "evaluator/trial0002/author_rows.jsonl"
        changed.parent.mkdir()
        changed.write_bytes(b"{}\n")
        payload["evaluator_files"]["evaluator/trial0002/author_rows.jsonl"] = {
            "bytes": 3,
            "sha256": hashlib.sha256(b"{}\n").hexdigest(),
        }
    (output / "manifest.json").write_bytes(module.encoded(payload))
    with pytest.raises(ValueError):
        module.inspect_full_training(archive, metadata, output, verify=True)
    if changed is not None:
        if backup is None:
            changed.unlink()
        else:
            changed.write_bytes(backup)
    (output / "manifest.json").write_bytes(module.encoded(original))
    assert module.inspect_full_training(archive, metadata, output, verify=True) == original


@pytest.mark.parametrize(
    "bad", ("missing", "duplicate", "traversal", "unknown_trial", "cross_root")
)
def test_unsafe_or_incomplete_archive_is_not_an_accepted_packet(tmp_path, monkeypatch, bad):
    def change(values):
        if bad == "missing":
            del values["training_set/trial0000/wrench.npy"]
        elif bad == "traversal":
            values["training_set/../../outside"] = b"attack"
        elif bad == "unknown_trial":
            values["training_set/trial0900/head_cam.mp4"] = b"attack"
        elif bad == "cross_root":
            values["test_set/trial0000/head_cam.mp4"] = b"attack"

    additions = [("training_set/trial0000/wrench.npy", b"duplicate")] if bad == "duplicate" else ()
    archive, metadata, output = fixture_archive(
        tmp_path, monkeypatch, mutate=change, additions=additions
    )
    with pytest.raises(ValueError):
        module.inspect_full_training(archive, metadata, output)
    assert not (output / "manifest.json").exists()
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("bad", ("clock", "video", "labels", "metadata"))
def test_invalid_trial_is_preserved_and_quarantined_without_hiding_denominator(
    tmp_path, monkeypatch, bad
):
    def change(values):
        prefix = "training_set/trial0000/"
        if bad == "clock":
            values[prefix + "head_cam_ts.npy"] = npy(np.array([0.0, 0.1, 0.1]))
        elif bad == "video":
            values[prefix + "head_cam.mp4"] = b"invalid video bytes"
        elif bad == "labels":
            values[prefix + "human_activity.npy"] = npy(np.array([0, 2, 100]))
        else:
            values[prefix + "task_info.json"] = module.encoded(
                {"task": "other", "robot": "Kinova Gen3"}
            )

    archive, metadata, output = fixture_archive(tmp_path, monkeypatch, mutate=change)
    result = module.inspect_full_training(archive, metadata, output)
    assert result["report"]["enrolled_trials"] == 2
    assert result["report"]["accepted_trials"] == 1
    assert len(result["report"]["quarantined_trials"]) == 1
    assert result["report"]["quarantined_trials"][0]["trial"] == "trial0000"
    assert (output / "raw/trial0000/head_cam.mp4").exists()
    assert not (output / "evaluator/trial0000/author_rows.jsonl").exists()
    assert module.inspect_full_training(archive, metadata, output, verify=True) == result


def test_partial_or_different_download_cannot_create_accepted_output(tmp_path, monkeypatch):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    archive.write_bytes(archive.read_bytes()[:-8])
    with pytest.raises(ValueError, match="published author"):
        module.inspect_full_training(archive, metadata, output)
    assert not output.exists()
