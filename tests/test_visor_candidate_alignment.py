"""First review: geometry arithmetic, full denominators and input boundaries."""

import copy
import json
from datetime import UTC, datetime

import numpy as np
import pytest
from test_visor_contact_supervision import fixture_sources

from cpswm.data_preflight import visor_candidate_alignment as alignment
from cpswm.data_preflight import visor_contact_supervision as source_module


def fixture_packet(tmp_path, monkeypatch):
    source, packet, _ = fixture_sources(tmp_path, monkeypatch)
    source_module.prepare_contact_package(source, packet)
    manifest = (packet / "runtime/manifest.json").read_bytes()
    rows = json.loads(manifest)["frames"]
    doc = {
        "format": "visor_frontend_candidates_v1",
        "profile": copy.deepcopy(alignment.PROFILE),
        "runtime_manifest_sha256": alignment.sha(manifest),
        "environment": {"test": True},
        "imported_at": "2026-09-27T00:00:00+00:00",
        "records": [],
    }
    for i, row in enumerate(rows):
        doc["records"].append(
            {
                "input": row,
                "hands": [
                    {
                        "id": f"h-{i}",
                        "points": [[2, 2]] * 21,
                        "side": "Left",
                        "score": 0.8,
                        "region_id": "full",
                    },
                    {
                        "id": f"h-dup-{i}",
                        "points": [[3, 3]] * 21,
                        "side": "Right",
                        "score": 0.7,
                        "region_id": "person",
                    },
                ]
                if i != 4
                else [],
                "objects": [
                    {"id": f"o-{i}", "box": [0, 0, 21, 21], "category": "cup", "score": 0.9},
                    {"id": f"o-dup-{i}", "box": [0, 0, 22, 22], "category": "bowl", "score": 0.8},
                    {"id": f"o-away-{i}", "box": [30, 30, 40, 40], "category": "cup", "score": 0.9},
                ],
            }
        )
    prediction = tmp_path / "prediction.json"
    prediction.write_bytes(alignment.encoded(doc))
    return source, packet, prediction, doc


def evaluate_fixture(source, packet, prediction):
    return alignment.evaluate(source, packet, prediction, alignment.sha(prediction.read_bytes()))


def test_full_geometry_denominator_unknowns_and_duplicate_candidates(tmp_path, monkeypatch):
    source, packet, prediction, _ = fixture_packet(tmp_path, monkeypatch)
    result = evaluate_fixture(source, packet, prediction)
    assert result == evaluate_fixture(source, packet, prediction)
    assert result["summary"]["frames"] == 5
    assert result["summary"]["relations"] == 4
    assert result["summary"]["frames_without_hand_candidates"] == 1
    first = result["frames"][0]
    assert len(first["hand_pairs"]) == 2 and len(first["object_pairs"]) == 3
    assert first["hand_pairs"][0]["landmarks_in_mask"] == 21
    assert first["relations"][0]["geometric_pair_count"] == 4
    assert first["relations"][0]["assigned_candidate_label"] is None
    assert first["object_pairs"][-1]["intersection_pixels"] == 0
    assert [f["relations"][0]["binary_contact_target"] for f in result["frames"][:4]] == [
        True,
        False,
        None,
        None,
    ]
    assert result["frames"][-1]["relations"] == []
    assert result["summary"]["assigned_candidate_labels"] == 0


def test_box_pixel_center_arithmetic_independent_reference():
    mask = np.zeros((4, 4), dtype=bool)
    mask[1:3, 1:3] = True
    for box in [[1, 1, 3, 3], [-2, -2, 2, 2], [1.5, 1.5, 2.5, 2.5], [6, 6, 7, 7], [0, 0, 0, 0]]:
        selected = {
            (x, y)
            for x in range(4)
            for y in range(4)
            if box[0] <= x + 0.5 < box[2] and box[1] <= y + 0.5 < box[3]
        }
        inter = sum(mask[y, x] for x, y in selected)
        result = alignment.box_overlap(mask, box)
        assert result["intersection_pixels"] == inter
        assert result["box_pixels"] == len(selected)
        assert result["box_mask_iou"] == inter / (len(selected) + 4 - inter)


def test_polygon_union_clipping_does_not_mutate_author_coordinates():
    segments = [
        [[-1.1, -1.1], [1, -1.1], [1, 1], [-1.1, 1]],
        [[3, 3], [5.1, 3], [5.1, 5.1], [3, 5.1]],
    ]
    before = copy.deepcopy(segments)
    mask = alignment.mask_pixels(segments, 4, 4)
    assert mask.sum() == 5 and mask[0, 0] and mask[3, 3]
    assert segments == before
    assert alignment.box_overlap(np.zeros((4, 4), dtype=bool), [0, 0, 0, 0])["box_mask_iou"] is None


def test_rgb_snapshot_is_label_free_and_has_no_physical_clock(tmp_path, monkeypatch):
    _, packet, _, _ = fixture_packet(tmp_path, monkeypatch)
    manifest = (packet / "runtime/manifest.json").read_bytes()
    rows = alignment.runtime_frames(packet / "runtime", alignment.sha(manifest))
    row, raw = rows[0]
    obs = alignment.observation(row, raw, datetime(2026, 9, 27, tzinfo=UTC))
    assert obs.archive_timeline() is None
    assert obs.envelope().clock_domain == "import-time-not-exposure"
    assert "in_contact_object" not in obs.envelope_json
    assert np.load(__import__("io").BytesIO(obs.payload_bytes), allow_pickle=False).shape == (
        1080,
        1920,
        3,
    )
    (packet / row["rgb"]).write_bytes(b"changed after validated snapshot")
    assert alignment.observation(row, raw, datetime(2026, 9, 27, tzinfo=UTC)) == obs
    with pytest.raises(ValueError):
        alignment.runtime_frames(packet / "runtime", alignment.sha(manifest))


@pytest.mark.parametrize(
    "kind",
    [
        "missing_frame",
        "extra_frame",
        "swap_frames",
        "wrong_image",
        "wrong_profile",
        "unknown_field",
        "duplicate_candidate",
        "nan_score",
        "bool_score",
        "infinite_point",
        "bad_points",
        "outside_box",
    ],
)
def test_complete_pinned_but_malformed_prediction_rejected(tmp_path, monkeypatch, kind):
    source, packet, prediction, doc = fixture_packet(tmp_path, monkeypatch)
    row = doc["records"][0]
    if kind == "missing_frame":
        doc["records"].pop()
    elif kind == "extra_frame":
        doc["records"].append(copy.deepcopy(row))
    elif kind == "swap_frames":
        doc["records"][:2] = doc["records"][1::-1]
    elif kind == "wrong_image":
        row["input"]["rgb_sha256"] = "a" * 64
    elif kind == "wrong_profile":
        doc["profile"]["minimum_score"] = 0.1
    elif kind == "unknown_field":
        row["contact"] = True
    elif kind == "duplicate_candidate":
        row["hands"][1]["id"] = row["hands"][0]["id"]
    elif kind == "nan_score":
        row["hands"][0]["score"] = float("nan")
    elif kind == "bool_score":
        row["hands"][0]["score"] = True
    elif kind == "infinite_point":
        row["hands"][0]["points"][0][0] = float("inf")
    elif kind == "bad_points":
        row["hands"][0]["points"].pop()
    elif kind == "outside_box":
        row["objects"][0]["box"][0] = -1
    prediction.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        evaluate_fixture(source, packet, prediction)


@pytest.mark.parametrize("kind", ["image_swap", "alias", "extra", "manifest_forgery"])
def test_rgb_only_runtime_rejects_modified_or_aliased_sources(tmp_path, monkeypatch, kind):
    _, packet, _, doc = fixture_packet(tmp_path, monkeypatch)
    runtime = packet / "runtime"
    manifest = (runtime / "manifest.json").read_bytes()
    first, second = [packet / r["input"]["rgb"] for r in doc["records"][:2]]
    if kind == "image_swap":
        first.write_bytes(second.read_bytes())
    elif kind == "alias":
        first.unlink()
        first.symlink_to(second)
    elif kind == "extra":
        (runtime / "labels.json").write_text("{}")
    else:
        (runtime / "manifest.json").write_text("{}")
    with pytest.raises(ValueError):
        alignment.runtime_frames(runtime, alignment.sha(manifest))
