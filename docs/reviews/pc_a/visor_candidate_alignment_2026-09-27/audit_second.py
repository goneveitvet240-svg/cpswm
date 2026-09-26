"""Second review: complete forgery, downstream consumer and lifecycle evidence."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_visor_candidate_alignment import save_new  # noqa: E402
from test_visor_candidate_alignment import evaluate_fixture, fixture_packet  # noqa: E402

from cpswm.data_preflight import visor_candidate_alignment as alignment  # noqa: E402
from cpswm.data_preflight import visor_contact_supervision as source_module  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402


def test_plausible_complete_prediction_forgery_cannot_self_enroll(tmp_path, monkeypatch):
    source, packet, prediction, doc = fixture_packet(tmp_path, monkeypatch)
    original = prediction.read_bytes()
    pinned = alignment.sha(original)
    # Fully well-shaped record, all 5 frames present; changed geometry gives new output.
    doc["records"][0]["hands"][0]["points"] = [[100, 100]] * 21
    prediction.write_bytes(alignment.encoded(doc))
    self_pinned_result = evaluate_fixture(source, packet, prediction)
    assert self_pinned_result["frames"][0]["relations"][0]["geometric_pair_count"] == 2
    with pytest.raises(ValueError, match="external execution pin"):
        alignment.evaluate(source, packet, prediction, pinned)
    prediction.write_bytes(original)
    assert (
        alignment.evaluate(source, packet, prediction, pinned)["frames"][0]["relations"][0][
            "geometric_pair_count"
        ]
        == 4
    )


def test_complete_resealed_author_forgery_rejected_by_geometry_consumer(tmp_path, monkeypatch):
    source, packet, prediction, _ = fixture_packet(tmp_path, monkeypatch)
    sources = {name: (source / name).read_bytes() for name, _ in source_module.ENROLLED_SOURCES}
    original = source_module._derive(sources)
    labels = json.loads(sources["P01_01.json"])
    labels["video_annotations"][2]["annotations"][-1]["in_contact_object"] = "object"
    sources["P01_01.json"] = alignment.encoded(labels)
    forged = source_module._derive(sources)
    manifest = json.loads(forged["manifest.json"])
    assert all(alignment.sha(forged[k]) == v["sha256"] for k, v in manifest["members"].items())
    for name, raw in forged.items():
        (packet / name).write_bytes(raw)
    with pytest.raises(ValueError, match="recomputation"):
        evaluate_fixture(source, packet, prediction)
    for name, raw in original.items():
        (packet / name).write_bytes(raw)
    assert (
        evaluate_fixture(source, packet, prediction)["frames"][2]["relations"][0][
            "binary_contact_target"
        ]
        is None
    )


def test_postverify_label_swap_never_changes_returned_supervision(tmp_path, monkeypatch):
    source, packet, prediction, _ = fixture_packet(tmp_path, monkeypatch)
    original = alignment._verify_artifacts

    def drift(path, artifacts):
        original(path, artifacts)
        (packet / "supervision/contact_targets.json").write_bytes(b"[]")

    monkeypatch.setattr(alignment, "_verify_artifacts", drift)
    result = evaluate_fixture(source, packet, prediction)
    assert result["summary"]["relations"] == 4
    assert result["frames"][0]["relations"][0]["binary_contact_target"] is True
    with pytest.raises(ValueError):
        evaluate_fixture(source, packet, prediction)


def test_altered_labels_leave_all_runtime_bytes_and_observations_identical(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    source, packet, _, _ = fixture_packet(tmp_path, monkeypatch)
    sources = {name: (source / name).read_bytes() for name, _ in source_module.ENROLLED_SOURCES}
    first = source_module._derive(sources)
    labels = json.loads(sources["P01_01.json"])
    labels["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    labels["video_annotations"][0]["annotations"][0]["segments"] = [
        [[200, 200], [210, 200], [210, 210]]
    ]
    sources["P01_01.json"] = alignment.encoded(labels)
    second = source_module._derive(sources)
    assert all(second[k] == v for k, v in first.items() if k.startswith("runtime/"))
    rows = alignment.runtime_frames(
        packet / "runtime", alignment.sha(first["runtime/manifest.json"])
    )
    row, raw = rows[0]
    when = datetime(2026, 9, 27, tzinfo=UTC)
    assert alignment.observation(row, raw, when) == alignment.observation(
        row, second[row["rgb"]], when
    )


def test_public_result_consumer_recomputes_complete_plausible_forgery(tmp_path, monkeypatch):
    source, packet, prediction, _ = fixture_packet(tmp_path, monkeypatch)
    expected = evaluate_fixture(source, packet, prediction)
    forged = copy.deepcopy(expected)
    forged["frames"][0]["hand_pairs"][0]["landmarks_in_mask"] = 0
    path = tmp_path / "result.json"
    save_new(path, forged)
    with pytest.raises(ValueError, match="recomputed alignment"):
        alignment.verify_alignment(
            source, packet, prediction, alignment.sha(prediction.read_bytes()), path
        )
    path.write_bytes(alignment.encoded(expected))
    assert (
        alignment.verify_alignment(
            source, packet, prediction, alignment.sha(prediction.read_bytes()), path
        )
        == expected
    )
    with pytest.raises((ValueError, TypeError)):
        ProposalSample.model_validate(expected)


def test_publish_failure_no_result_then_retry_and_no_overwrite(tmp_path, monkeypatch):
    import os

    target = tmp_path / "result.json"
    original = os.link

    def fail(*args):
        raise OSError("injected before publication")

    monkeypatch.setattr(os, "link", fail)
    with pytest.raises(OSError):
        save_new(target, {"complete": True})
    assert not target.exists() and not list(tmp_path.glob(".visor-result-*"))
    monkeypatch.setattr(os, "link", original)
    save_new(target, {"complete": True})
    assert target.stat().st_nlink == 1
    with pytest.raises(FileExistsError):
        save_new(target, {"forged": True})
    assert json.loads(target.read_bytes()) == {"complete": True}


def test_no_detection_is_not_negative_contact(tmp_path, monkeypatch):
    source, packet, prediction, doc = fixture_packet(tmp_path, monkeypatch)
    for row in doc["records"]:
        row["hands"], row["objects"] = [], []
    prediction.write_bytes(alignment.encoded(doc))
    result = evaluate_fixture(source, packet, prediction)
    assert result["summary"]["frames"] == 5 and result["summary"]["relations"] == 4
    assert result["frames"][0]["relations"][0]["binary_contact_target"] is True
    assert result["frames"][0]["relations"][0]["geometric_pair_count"] == 0
    assert result["summary"]["assigned_candidate_labels"] == 0


def test_unique_overlap_person_false_positive_then_valid_object_retry(tmp_path, monkeypatch):
    source, packet, prediction, doc = fixture_packet(tmp_path, monkeypatch)
    first = doc["records"][0]
    first["hands"] = first["hands"][:1]
    first["objects"] = first["objects"][:1]
    first["objects"][0]["category"] = "person"
    prediction.write_bytes(alignment.encoded(doc))
    result = evaluate_fixture(source, packet, prediction)
    row = result["frames"][0]
    assert row["object_pairs"][0]["intersection_pixels"] > 0
    assert row["relations"][0]["geometric_pair_count"] == 0
    first["objects"][0]["category"] = "cup"
    prediction.write_bytes(alignment.encoded(doc))
    row = evaluate_fixture(source, packet, prediction)["frames"][0]
    assert row["relations"][0]["geometric_pair_count"] == 1
    assert row["relations"][0]["assigned_candidate_label"] is None
