"""Focused object-map lineage and pinned external-code checks (no GPU required)."""

import ast
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from cpswm.perception_mapping.external_object_sequence import (
    records_from_mapping,
    reference_fallback,
    validate_configuration,
)

ROOT = Path(__file__).resolve().parents[1]


def test_all_vendored_symbols_match_declared_upstream_bodies():
    source = (ROOT / "tools/external_components/conceptgraph_object_kernel.py").read_text()
    nodes = {
        n.name: n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
    }
    manifest = json.loads(
        (ROOT / "docs/reviews/pc_a/object_memory_integration_2026-10-10/SOURCES.json").read_text()
    )
    assert len(manifest["symbols"]) == 13
    for item in manifest["symbols"]:
        node = nodes[item["symbol"]]
        body = "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
        assert sha256(body.encode()).hexdigest() == item["body_sha256"]


def test_mapping_does_not_turn_stale_or_late_points_into_current_initial_query():
    def candidate(key, score):
        return dict(
            candidate_id=key,
            category="bottle",
            detector_score=score,
            native_index=0,
            world_point_m=[1, 2, 3],
            selected_pixel_uv=[2, 3],
        )

    first, late = candidate("initial", 0.9), candidate("late", 0.95)
    frames = [dict(candidates=[first]), dict(candidates=[late])]
    obj = dict(anchor_id="initial", observations=[dict(frame=0, candidate=0)])
    new = dict(anchor_id="late", observations=[dict(frame=1, candidate=0)])
    steps = [
        dict(objects=[obj], association=None, diagnostics=[]),
        dict(objects=[obj, new], association=None, diagnostics=[]),
    ]
    result = records_from_mapping(
        [{}, {}], frames, dict(steps=steps, model_sha256="a" * 64, spatial="iou")
    )
    tracks = {t["anchor_id"]: t for t in result[-1]["tracks"]}
    assert tracks["initial"]["world_point_m"] is None
    assert tracks["initial"]["query_eligible"] is True
    assert tracks["late"]["world_point_m"] == [1, 2, 3]
    assert tracks["late"]["query_eligible"] is False


@pytest.mark.parametrize(
    "mapped_point,reference_point,expected",
    [
        ([1, 2, 3], [4, 5, 6], [1, 2, 3]),
        (None, [4, 5, 6], [4, 5, 6]),
        (None, None, None),
    ],
)
def test_hybrid_only_fills_absent_support_without_mutating_history(
    mapped_point, reference_point, expected
):
    mapped = dict(
        tracks=[dict(anchor_id="first", world_point_m=mapped_point, status="CG", map_object={})]
    )
    reference = dict(tracks=[dict(anchor_id="first", world_point_m=reference_point, status="REF")])
    original = deepcopy((mapped, reference))
    result = reference_fallback(mapped, reference)
    assert result["tracks"][0]["world_point_m"] == expected
    assert (mapped, reference) == original


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"python": "relative", "weights": "relative", "spatial": "iou"},
        {"python": "/x", "weights": "/x", "spatial": "oracle"},
    ],
)
def test_incomplete_or_privileged_backend_configuration_rejected(bad):
    with pytest.raises(ValueError):
        validate_configuration(bad)


def test_forged_complete_model_file_rejected(tmp_path):
    p = tmp_path / "model.bin"
    p.write_bytes(b"not a pinned pretrained checkpoint")
    with pytest.raises(ValueError, match="checkpoint differs"):
        validate_configuration(dict(python=str(p), weights=str(p), spatial="iou"))


def test_reference_point_preserved_inside_a_matched_mixed_mask():
    mapped = dict(
        tracks=[
            dict(
                anchor_id="first",
                current_candidate_id="mask",
                world_point_m=[1, 2, 3],
                status="CG_MATCHED",
                map_object={},
            )
        ]
    )
    reference = dict(
        tracks=[
            dict(
                anchor_id="first",
                current_candidate_id="mask",
                world_point_m=[4, 5, 6],
                selected_feature_ids=[10],
                status="VERIFIED",
            )
        ]
    )
    result = reference_fallback(mapped, reference)
    assert result["tracks"][0]["world_point_m"] == [4, 5, 6]
    assert result["tracks"][0]["selected_feature_ids"] == [10]
    reference["tracks"][0]["current_candidate_id"] = "conflicting-mask"
    assert reference_fallback(mapped, reference)["tracks"][0]["world_point_m"] == [1, 2, 3]
