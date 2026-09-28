"""Fixed collection schedule, ground-truth exclusion and failure denominators."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_camera_measurement_grid as grid


def test_grid_has_six_prespecified_initializations_and_66_views_without_result_selection():
    original = grid.original_house()
    saved = json.dumps(original, sort_keys=True)
    for site in grid.SITES:
        for x in grid.XS:
            h = grid.grid_house(original, site, x)
            assert h["metadata"]["agent"] == h["metadata"]["agentPoses"]["default"]
            assert h["metadata"]["agent"]["position"]["x"] == x
            assert h["metadata"]["agent"]["rotation"]["y"] == 195
            assert h["metadata"]["agent"]["horizon"] == 30
            assert [grid.action_at(i) for i in range(11)] == [("Pass", 0)] + [
                ("RotateRight", 15)
            ] * 10
    assert len(grid.XS) * len(grid.SITES) * len(grid.HEADINGS) == 66
    assert json.dumps(original, sort_keys=True) == saved


@pytest.mark.parametrize("index", [-1, 11, True, "1", 1.1])
def test_outside_grid_actions_rejected(index):
    with pytest.raises(ValueError, match="outside fixed schedule"):
        grid.action_at(index)


def test_both_decoders_receive_exactly_same_raw_tuple_without_evaluator_metadata(monkeypatch):
    from uuid import uuid4

    from test_structure_two_adaptive_runtime import _adaptive_system_and_transition
    from test_structure_two_continuous_input import raw_for

    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    _, transition = _adaptive_system_and_transition()
    import hashlib
    import io
    from dataclasses import replace

    import numpy as np

    raw = raw_for(transition)
    buffer = io.BytesIO()
    np.save(buffer, np.zeros((320, 320, 3), dtype=np.uint8), allow_pickle=False)
    payload = buffer.getvalue()
    env = raw.envelope()
    env = env.model_copy(
        update={
            "payload": env.payload.model_copy(
                update={
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
            )
        }
    )
    raw = replace(raw, envelope_json=env.model_dump_json(), payload_bytes=payload)
    records = ((None, ObservationDelivery(uuid4(), (raw,), True, "", raw.envelope().arrival_time)),)
    seen = []

    class PixelOnly:
        binding_sha256 = "f" * 64

        def __init__(self, **kwargs):
            assert set(kwargs) == {
                "weights_path",
                "category",
                "sources",
                "detector_kind",
                "household_id",
                "session_id",
                "trace_id",
            }

        def measurements(self, observations, *, cutoff):
            assert observations == (raw,)
            seen.append(observations)
            return ()

    monkeypatch.setattr(grid, "PixelCategoryOutcomeDecoder", PixelOnly)
    grid.measure_public(records, weights={"ssdlite": Path("one"), "fasterrcnn": Path("two")})
    assert seen[0] is seen[1]


def test_failed_cell_is_preserved_and_every_other_declared_cell_is_attempted(tmp_path, monkeypatch):
    attempted = []

    def capture(directory, **kwargs):
        attempted.append((kwargs["site"], kwargs["x"]))
        if kwargs["x"] == 1.05:
            raise RuntimeError("fixture collection failure")

    monkeypatch.setattr(grid, "capture_case", capture)
    monkeypatch.setattr(
        grid,
        "analyze_case",
        lambda *args, **kw: dict(site=kw["site"], camera_x=kw["x"], frame_count=11),
    )
    args = SimpleNamespace(
        mode="run",
        image_size=320,
        output=tmp_path / "grid",
        sdk_python=Path("sdk"),
        binary=Path("binary"),
        ssdlite_weights=Path("one"),
        fasterrcnn_weights=Path("two"),
    )
    with pytest.raises(SystemExit):
        grid.main(args)
    assert attempted == [(s, x) for s in grid.SITES for x in grid.XS]
    plan = json.loads((args.output / "grid.json").read_text())
    assert len(plan) == 6 and sum(x["status"] == "FAILED" for x in plan) == 2
    assert not (args.output / "summary.json").exists()
