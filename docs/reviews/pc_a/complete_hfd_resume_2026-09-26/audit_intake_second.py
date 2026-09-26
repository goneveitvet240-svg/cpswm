"""Second local audit: complete forged packets, numeric data and late custody faults."""

import hashlib
import json
import os
import socket
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_full_hfd_training import fixture_archive, npy  # noqa: E402

from cpswm.data_preflight import full_hfd_training as module  # noqa: E402


def verify(archive, metadata, output):
    return module.inspect_full_training(archive, metadata, output, verify=True)


@pytest.mark.parametrize("kind", ("fifo", "socket", "hardlink", "directory_link"))
def test_otherwise_complete_packet_rejects_alias_or_special_member(tmp_path, monkeypatch, kind):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    baseline = module.inspect_full_training(archive, metadata, output)
    alias = output / "extra"
    sock = None
    if kind == "fifo":
        os.mkfifo(alias)
    elif kind == "socket":
        sock = socket.socket(socket.AF_UNIX)
        with monkeypatch.context() as local:
            local.chdir(output)
            sock.bind("extra")
    elif kind == "hardlink":
        os.link(output / "raw/trial0000/head_cam.mp4", alias)
    else:
        alias.symlink_to(output / "raw", target_is_directory=True)
    try:
        with pytest.raises(ValueError, match=r"packet|alias|link|special|regular"):
            verify(archive, metadata, output)
    finally:
        if sock is not None:
            sock.close()
        alias.unlink()
    assert verify(archive, metadata, output) == baseline


@pytest.mark.parametrize("verification", (False, True))
@pytest.mark.parametrize("kind", ("raw", "extra"))
def test_fault_after_final_content_check_cannot_return_an_accepted_packet(
    tmp_path, monkeypatch, verification, kind
):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    baseline = None
    if verification:
        baseline = module.inspect_full_training(archive, metadata, output)
    original = module.check_members
    calls = 0
    backup = None
    changed = output / ("raw/trial0000/human_activity.npy" if kind == "raw" else "late.json")

    def corrupted(root, members):
        nonlocal calls, backup
        original(root, members)
        calls += 1
        if calls == 2:
            backup = changed.read_bytes() if changed.exists() else None
            changed.write_bytes(npy(np.array([0, 3, 3])) if kind == "raw" else b"{}\n")

    with monkeypatch.context() as fault:
        fault.setattr(module, "check_members", corrupted)
        with pytest.raises(ValueError, match=r"packet|artifact|member|changed"):
            module.inspect_full_training(archive, metadata, output, verify=verification)
    if not verification:
        assert not (output / "manifest.json").exists()
        # A failed directory is retained, and a fresh explicit destination works.
        retried = module.inspect_full_training(archive, metadata, tmp_path / "safe-retry")
        assert retried["report"]["accepted_trials"] == 2
    else:
        if backup is None:
            changed.unlink()
        else:
            changed.write_bytes(backup)
        assert verify(archive, metadata, output) == baseline


@pytest.mark.parametrize(
    "kind",
    (
        "string_force",
        "complex_clock",
        "complex_force",
        "unsigned_camera_clock",
        "unsigned_force_clock",
        "non_object_metadata",
    ),
)
def test_bad_numeric_or_schema_trial_is_quarantined_with_its_full_denominator(
    tmp_path, monkeypatch, kind
):
    def change(values):
        prefix = "training_set/trial0000/"
        if kind == "string_force":
            values[prefix + "wrench.npy"] = npy(np.full((4, 6), "missing"))
        elif kind == "complex_clock":
            values[prefix + "head_cam_ts.npy"] = npy(np.array([1j, 0.1 + 2j, 0.2 + 3j]))
        elif kind == "complex_force":
            values[prefix + "wrench_resampled.npy"] = npy(np.ones((3, 6), dtype=complex) * 1j)
        elif kind == "unsigned_camera_clock":
            values[prefix + "head_cam_ts.npy"] = npy(np.array([250, 5, 10], dtype=np.uint8))
        elif kind == "unsigned_force_clock":
            values[prefix + "wrench_ts.npy"] = npy(np.array([250, 5, 10, 15], dtype=np.uint8))
        else:
            values[prefix + "task_info.json"] = b"[]\n"

    archive, metadata, output = fixture_archive(tmp_path, monkeypatch, mutate=change)
    report = module.inspect_full_training(archive, metadata, output)
    assert report["report"]["enrolled_trials"] == 2
    assert report["report"]["accepted_trials"] == 1
    assert report["report"]["accepted_success_trials"] == 0
    assert report["report"]["quarantined_trials"][0]["trial"] == "trial0000"
    assert (output / "raw/trial0000/head_cam.mp4").is_file()
    assert not (output / "evaluator/trial0000/author_rows.jsonl").exists()
    assert verify(archive, metadata, output) == report


def test_complete_source_resealed_quarantine_promotion_is_rejected_and_original_still_works(
    tmp_path, monkeypatch
):
    def broken(values):
        values["training_set/trial0000/head_cam.mp4"] = b"author's broken video"

    archive, metadata, output = fixture_archive(tmp_path, monkeypatch, mutate=broken)
    original = module.inspect_full_training(archive, metadata, output)
    forged = json.loads(module.encoded(original))
    relative = "raw/trial0000/head_cam.mp4"
    target = output / relative
    saved = target.read_bytes()
    target.write_bytes((output / "raw/trial0001/head_cam.mp4").read_bytes())
    # This produces a fully parseable packet, complete rows, counts and hashes;
    # its raw bytes no longer match the unchanged trusted author's archive.
    forged["raw_members"][relative].update(
        bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest()
    )
    forged["report"], forged["evaluator_files"] = module.build_report(
        output, module.load_author_metadata(metadata)[0], write_rows=True
    )
    assert forged["report"]["accepted_trials"] == 2
    assert forged["report"]["accepted_success_trials"] == 1
    (output / "manifest.json").write_bytes(module.encoded(forged))
    with pytest.raises(ValueError, match=r"source|member|packet"):
        verify(archive, metadata, output)
    target.write_bytes(saved)
    (output / "evaluator/trial0000/author_rows.jsonl").unlink()
    (output / "manifest.json").write_bytes(module.encoded(original))
    assert verify(archive, metadata, output) == original


def test_different_valid_videos_cannot_be_cross_paired_under_complete_resealing(
    tmp_path, monkeypatch
):
    other = tmp_path / "other.mp4"
    writer = cv2.VideoWriter(str(other), cv2.VideoWriter_fourcc(*"mp4v"), 10, (48, 32))
    assert writer.isOpened()
    try:
        for i in range(3):
            writer.write(np.full((32, 48, 3), 240 - i * 30, dtype=np.uint8))
    finally:
        writer.release()

    def change(values):
        values["training_set/trial0001/head_cam.mp4"] = other.read_bytes()

    archive, metadata, output = fixture_archive(tmp_path, monkeypatch, mutate=change)
    original = module.inspect_full_training(archive, metadata, output)
    forged = json.loads(module.encoded(original))
    names = [f"raw/trial{i:04d}/head_cam.mp4" for i in range(2)]
    saved = [(output / name).read_bytes() for name in names]
    assert saved[0] != saved[1]
    for name, raw in zip(names, reversed(saved), strict=True):
        (output / name).write_bytes(raw)
        forged["raw_members"][name].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (output / "manifest.json").write_bytes(module.encoded(forged))
    with pytest.raises(ValueError):
        verify(archive, metadata, output)
    for name, raw in zip(names, saved, strict=True):
        (output / name).write_bytes(raw)
    (output / "manifest.json").write_bytes(module.encoded(original))
    assert verify(archive, metadata, output) == original


def test_all_scientific_authority_flags_cannot_be_promoted_by_a_complete_manifest(
    tmp_path, monkeypatch
):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    original = module.inspect_full_training(archive, metadata, output)
    forged = json.loads(module.encoded(original))
    for key in (
        "independent_reannotation",
        "exact_contact_release_gold",
        "global_person_identity_gold",
        "our_frontend_pose_calibration",
        "full_proposal_training_ready",
        "native_publication_authorized",
        "runtime_label_injection",
        "validation_or_test_split_read",
    ):
        assert forged["report"][key] is False
        forged["report"][key] = True
    forged["report"]["new_optimizer_steps"] = 1
    (output / "manifest.json").write_bytes(module.encoded(forged))
    with pytest.raises(ValueError, match=r"source|packet"):
        verify(archive, metadata, output)
    (output / "manifest.json").write_bytes(module.encoded(original))
    assert verify(archive, metadata, output) == original


@pytest.mark.parametrize("kind", ("duplicate_json_key", "decoded_count"))
def test_valid_container_with_bad_pairing_retains_raw_and_quarantines_trial(
    tmp_path, monkeypatch, kind
):
    def change(values):
        prefix = "training_set/trial0000/"
        if kind == "duplicate_json_key":
            values[prefix + "task_info.json"] = (
                b'{"robot":"Kinova Gen3","robot":"Kinova Gen3","task":"human to robot handover"}'
            )
        else:
            values[prefix + "head_cam_ts.npy"] = npy(np.array([0.0, 0.1, 0.2, 0.3]))
            values[prefix + "human_activity.npy"] = npy(np.array([0, 2, 3, 3]))
            values[prefix + "robot_actions.npy"] = npy(np.array([0, 2, 3, 3]))
            values[prefix + "wrench_resampled.npy"] = npy(np.zeros((4, 6)))

    archive, metadata, output = fixture_archive(tmp_path, monkeypatch, mutate=change)
    result = module.inspect_full_training(archive, metadata, output)
    assert result["report"]["accepted_trials"] == 1
    assert result["report"]["enrolled_trials"] == 2
    assert (output / "raw/trial0000/head_cam.mp4").is_file()
    assert verify(archive, metadata, output) == result
