import json
from types import SimpleNamespace

import numpy as np
import pytest
from run_simulator_repeatability import action_at, geometry_delta, image_delta, plan, summarize
from unity_repeatability_worker import wrap_response


def test_complete_plan_has_all_cells_and_counterbalanced_routes():
    cells = plan()
    assert len(cells) == len({r["name"] for r in cells}) == 16
    assert len({(r["site"], r["size"], r["route"], r["repeat"]) for r in cells}) == 16
    assert [r["route"] for r in cells[:4]] == ["direct", "rotate", "rotate", "direct"]
    assert all(action_at(r["route"], i) == ("Pass", 0.0) for r in cells for i in range(1, 8))
    assert action_at("rotate", 0) == ("RotateLeft", 45.0)
    assert action_at("direct", 0) == ("Pass", 0.0)


@pytest.mark.parametrize(
    "route,index", [("unknown", 0), ("direct", 8), ("direct", -1), ("direct", True)]
)
def test_outside_fixed_capture_schedule_rejected(route, index):
    with pytest.raises(ValueError, match="undeclared"):
        action_at(route, index)


def test_complete_summary_requires_failed_or_missing_cells_to_be_resolved():
    rows = [dict(cell=c, frames=[{}] * 8) for c in plan()]
    assert summarize(rows)["frames"] == 128
    with pytest.raises(ValueError, match="matrix"):
        summarize(rows[:-1])
    rows[-1] = rows[0]
    with pytest.raises(ValueError, match="matrix"):
        summarize(rows)


def test_rgb_variation_does_not_create_mask_or_success_claims():
    a = np.zeros((2, 2, 3), dtype=np.uint8)
    b = a.copy()
    b[0, 0] = [30, 60, 90]
    mask = np.zeros((2, 2), dtype=bool)
    d = image_delta(a, b, mask)
    assert d["mean_abs_byte"] == 15 and d["changed_pixel_fraction"] == 0.25
    assert d["target_region_mean_abs_byte"] is None and not d["equal"]
    mask[0, 0] = True
    assert image_delta(a, b, mask)["target_region_mean_abs_byte"] == 60


def test_full_sdk_geometry_reports_other_object_drift():
    def metadata(x):
        return dict(
            objects=[
                dict(
                    objectId="tomato",
                    objectType="Tomato",
                    assetId="T5",
                    position=dict(x=x, y=0, z=0),
                    rotation=dict(x=0, y=0, z=0),
                )
            ]
        )

    assert geometry_delta(metadata(0), metadata(0.125)) == dict(
        max_object_translation=0.125, max_object_rotation=0
    )
    with pytest.raises(ValueError, match="object set"):
        geometry_delta(metadata(0), dict(objects=[]))


def test_metadata_observer_returns_exact_same_public_object(tmp_path):
    public = dict(action_id="a", success=True, rgb_npy="public", error="", capture_time="now")
    callback = wrap_response(lambda identity, event: public, tmp_path)
    event = SimpleNamespace(metadata=dict(objects=[dict(objectId="private-tomato")]))
    assert callback("a", event) is public
    assert "private-tomato" not in json.dumps(public)
    private = json.loads((tmp_path / "evaluator_only/full_metadata/000.json").read_text())
    assert private == dict(action_id="a", metadata=event.metadata)
