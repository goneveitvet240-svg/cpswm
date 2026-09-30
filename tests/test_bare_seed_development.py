"""Paired bare seed checks, with controlled pixel data and independent moment formulae."""

import copy
import json
from typing import ClassVar

import numpy as np
import pytest
import run_bare_seed_development as task
from test_offline_frontend_evaluation import frame_args
from test_soft_position_dataset import build, labels


def test_direct_seed_uses_original_pixel_not_aggregated_point(tmp_path):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    rows = task.public_points(readout)
    neighborhoods = {n["neighborhood_id"]: n for n in readout["neighborhoods"]}
    assert len(rows) == len(readout["seeds"])
    for row in rows:
        n = neighborhoods[row["neighborhood_id"]]
        i = n["pixels_uv"].index(row["pixel_uv"])
        assert row["world_point_m"] == n["world_points_m"][i]
    joined = task.join_labels(rows, labels(args, record, model, pin, readout), 1, "train")
    assert len(joined) == len(rows)
    assert not any("estimator" in r for r in joined)
    assert any(not r["eligible"] for r in joined)


@pytest.mark.parametrize(
    "field", ["seed_id", "measurement_id", "object_id", "targets", "eligible", "pixel_uv"]
)
def test_paired_labels_cannot_silently_change_denominator(tmp_path, field):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    private = labels(args, record, model, pin, readout)
    private["labels"][1][field] = "forged"
    with pytest.raises(ValueError, match="paired estimator"):
        task.join_labels(task.public_points(readout), private, 1, "train")


def test_duplicate_seed_and_grid_pixel_rejected(tmp_path):
    args = frame_args(tmp_path)
    _, _, _, readout = build(args)
    forged = copy.deepcopy(readout)
    forged["seeds"].append(forged["seeds"][0])
    with pytest.raises(ValueError, match="duplicate"):
        task.public_points(forged)
    forged = copy.deepcopy(readout)
    forged["neighborhoods"][0]["pixels_uv"][1] = forged["neighborhoods"][0]["pixels_uv"][0]
    with pytest.raises(ValueError, match="duplicate"):
        task.public_points(forged)


def rows(values, split="train", house=1):
    return [
        dict(residual=v, member=dict(split=split, house_index=house, measurement_id=str(i)))
        for i, v in enumerate(values)
    ]


def test_bare_fit_train_only_and_unbiased_full_covariance():
    x = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0], [1.0, 2.0, 3.0]]
    )
    model = task.fit_bare(rows(x.tolist()), "sdk_aabb_center_m")
    assert model["status"] == "fitted" and model["estimator"] == "bare_seed"
    np.testing.assert_allclose(model["bias"], np.sum(x, axis=0) / 5)
    manual = sum(np.outer(row - x.mean(0), row - x.mean(0)) for row in x) / 4
    np.testing.assert_allclose(model["covariance"], manual)
    assert not model["runtime_authority"] and not model["calibrated"]
    with pytest.raises(ValueError, match="original train"):
        task.fit_bare(rows(x.tolist(), split="validation", house=9), "sdk_aabb_center_m")


@pytest.mark.parametrize(
    "values", [[], [[0.0, 0.0, 0.0]] * 3, [[float(i), 0.0, 0.0] for i in range(5)]]
)
def test_rank_and_sample_failures_never_fabricate_covariance(values):
    model = task.fit_bare(rows(values), "sdk_transform_position_m")
    assert model["status"] == "fit_failed" and model["covariance"] is None and model["bias"] is None


def test_controlled_bundle_keeps_empty_frames_and_fit_failures(tmp_path):
    args = frame_args(tmp_path)
    record, model, pin, readout = build(args)
    lab = labels(args, record, model, pin, readout)
    files = {}
    frames = []
    for i in range(96):
        house = i // 8 + 1
        split = "train" if i < 64 else "validation"
        pub = copy.deepcopy(readout)
        pub["provenance"]["provenance"]["source_sha256"] = f"{i:064x}"
        ll = copy.deepcopy(lab)
        ll.update(house_index=house, split=split)
        for row in ll["labels"]:
            row.update(house_index=house, split=split)
        if i not in (0, 64):
            pub.update(neighborhoods=[], seeds=[])
            ll["labels"] = []
        files[f"frames/{i:03d}/public.json"] = pub
        files[f"frames/{i:03d}/labels.json"] = ll
        frames.append(dict(house_index=house, split=split, action_id=f"fixture-action-{i}"))
    eligible = [r for r in lab["labels"] if r["estimator"] == "soft_affinity" and r["eligible"]]
    counts = dict(
        seeds=len(eligible),
        frames=1,
        houses=1,
        objects=len({r["object_id"] for r in eligible}),
        object_frames=len({r["object_id"] for r in eligible}),
    )

    class Bundle:
        report: ClassVar[dict] = {
            "frames": frames,
            "results": {
                e + "/" + ref: {"by_split": {s: counts for s in ("train", "validation")}}
                for e in ("soft_affinity", "uniform")
                for ref in task.REFERENCES
            },
        }
        binding: ClassVar[dict] = {"explicit_fixture": True}

        def __init__(self):
            self.calls = []

        def load_json(self, path):
            if path.endswith("labels.json"):
                assert sum(p.endswith("public.json") for p in self.calls) == 96
            self.calls.append(path)
            return copy.deepcopy(files[path])

        def assert_unchanged(self):
            pass

    bundle = Bundle()
    artifacts = task.build(bundle)
    report = json.loads(artifacts["report.json"])
    assert len(artifacts) == 103 and len(report["frames"]) == 96
    assert sum(f["seeds"] == 0 for f in report["frames"]) == 94
    assert report["frames"][0]["supervised_seeds"] == len(eligible)
    assert all(
        report["results"][r]["by_split"]["validation"]["seeds"] == len(eligible)
        for r in task.REFERENCES
    )
    assert all(v["status"] == "fit_failed" for v in report["model_status"].values())
