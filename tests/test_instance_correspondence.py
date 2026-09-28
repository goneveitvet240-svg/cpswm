"""Complete SDK instance export and private-label isolation, with precise attacks."""

import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import run_instance_correspondence_diagnostic as task
from unity_instance_audit_worker import export_instances, wrap_response


def event_fixture():
    segmentation = np.zeros((4, 4, 3), dtype=np.uint8)
    segmentation[:2] = (100, 0, 0)
    segmentation[2:] = (0, 100, 0)
    objects = [
        dict(objectId="Apple|one", objectType="Apple", assetId="Apple_1"),
        dict(objectId="Tomato|two", objectType="Tomato", assetId="Tomato_2"),
        dict(objectId="Bottle|absent", objectType="Bottle", assetId="Bottle_3"),
    ]
    colors = [
        dict(name="Apple|one", color=[100, 0, 0]),
        dict(name="Tomato|two", color=[0, 100, 0]),
        dict(name="Bottle|absent", color=[0, 0, 100]),
    ]
    return SimpleNamespace(
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
        instance_segmentation_frame=segmentation,
        instance_masks={
            row["name"]: np.all(segmentation == row["color"], axis=2) for row in colors
        },
        metadata=dict(objects=objects, colors=colors),
    )


def exported(tmp_path):
    event = event_fixture()
    export_instances(event, tmp_path, 0, "fixture-action")
    info = json.loads((tmp_path / "000.json").read_text())
    with np.load(tmp_path / "000-masks.npz", allow_pickle=False) as data:
        masks = {k: data[k].copy() for k in data.files}
    return event, info, masks


def test_all_objects_including_invisible_are_reconstructed_from_colors(tmp_path):
    event, info, masks = exported(tmp_path)
    rows = task.reconstruct_catalog(
        info["catalog"],
        info["colors"],
        masks,
        event.instance_segmentation_frame,
        event.metadata["objects"],
    )
    assert len(rows) == 3
    assert {r["object_id"]: r["pixels"] for r in rows} == {
        "Apple|one": 8,
        "Tomato|two": 8,
        "Bottle|absent": 0,
    }
    assert next(r for r in rows if r["object_id"] == "Bottle|absent")["bbox"] is None


def test_optional_worker_returns_exact_public_response_without_instance_fields(tmp_path):
    event = event_fixture()
    public = dict(action_id="fixture-action", rgb_npy="public-pixels", success=True, error="")
    calls = []

    def responder(identity, actual):
        assert identity == "fixture-action" and actual is event
        calls.append(identity)
        return public

    wrapped = wrap_response(responder, tmp_path)
    result = wrapped("fixture-action", event)
    assert result is public and calls == ["fixture-action"]
    assert set(result) == {"action_id", "rgb_npy", "success", "error"}
    assert (tmp_path / "evaluator_only/instances/000.json").exists()


@pytest.mark.parametrize(
    "attack",
    [
        "drop_object",
        "duplicate_object",
        "drop_array",
        "same_count_mask",
        "category",
        "asset",
        "segmentation_type",
    ],
)
def test_complete_but_wrong_instance_evidence_is_rejected(tmp_path, attack):
    event, info, masks = exported(tmp_path)
    catalog = deepcopy(info["catalog"])
    segmentation = event.instance_segmentation_frame.copy()
    if attack == "drop_object":
        masks.pop(catalog.pop()["array_key"])
    elif attack == "duplicate_object":
        catalog[-1] = deepcopy(catalog[0])
    elif attack == "drop_array":
        masks.pop(catalog[0]["array_key"])
    elif attack == "same_count_mask":
        key = catalog[0]["array_key"]
        masks[key] = ~masks[key]
        assert masks[key].sum() == 8
    elif attack == "category":
        catalog[0]["object_type"] = "Tomato"
    elif attack == "asset":
        catalog[0]["asset_id"] = "invented"
    else:
        segmentation = segmentation.astype(float)
    with pytest.raises(ValueError):
        task.reconstruct_catalog(
            catalog, info["colors"], masks, segmentation, event.metadata["objects"]
        )


def test_snapshot_plan_is_fixed_and_failures_do_not_hide_other_cases(tmp_path, monkeypatch):
    attempted = []

    def capture(directory, **kwargs):
        attempted.append((kwargs["site"], kwargs["size"]))
        if kwargs["size"] == 320:
            raise ValueError("controlled collection failure")

    monkeypatch.setattr(task, "capture", capture)
    monkeypatch.setattr(task, "analyze", lambda *a, **kw: {})
    args = SimpleNamespace(
        mode="run",
        output=tmp_path / "run",
        sdk_python=None,
        binary=None,
        ssdlite_weights=None,
        fasterrcnn_weights=None,
    )
    with pytest.raises(SystemExit):
        task.main(args)
    assert attempted == [("south", 320), ("south", 640), ("north", 640)]
    plan = json.loads((args.output / "matrix.json").read_text())
    assert [r["status"] for r in plan] == ["FAILED", "COMPLETE", "COMPLETE"]
    assert not (args.output / "summary.json").exists()
