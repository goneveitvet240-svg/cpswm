"""Composed fixed-frame surface development using disclosed synthetic geometry.

The detector/masks and position variation are controlled fixtures. SDK references
and audit positions are changed together only in a temporary fixture, not in real
captures. This tests actual public reconstruction/private joins, not the historical
CLI's independent simulation acceptance. Process-boundary tests explicitly stub
subprocess execution and never launch Unity.
PYTEST_DONT_REWRITE: preserve implementation-bound imported fixture decoders.
"""

# Imported pytest fixtures intentionally share the argument names they register.
# ruff: noqa: F811

import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import run_instance_affinity_controls as controls
import run_soft_position_development as task
from test_instance_affinity_controls_driver import controls_built, parent  # noqa: F401
from test_offline_frontend_diagnostic import complete_batch, seal, write_json  # noqa: F401
from test_run_instance_affinity import batch, built  # noqa: F401


@pytest.fixture(scope="module")
def position_batch(batch, tmp_path_factory):
    root = tmp_path_factory.mktemp("position-three-dimensional-fixture")
    directory = root / "collection"
    shutil.copytree(batch.directory, directory)
    audit = json.loads((directory / "runtime-partition-audit.json").read_text())
    for house in range(1, 13):
        # Deliberate fixture reference variation, not a physical simulator claim.
        h = house / 8.0
        displacement = np.array([h, 0.7 * h**2, 0.9 * h**3])
        folder = directory / f"house-{house:02d}/unity-logs/evaluator_only"
        for path in sorted((folder / "sdk-events").glob("*.json")):
            event = json.loads(path.read_text())
            for obj in event["metadata"]["objects"]:
                for position in (obj["position"], obj["axisAlignedBoundingBox"]["center"]):
                    for axis, delta in zip("xyz", displacement, strict=True):
                        position[axis] = float(position[axis] + delta)
            write_json(path, event)
        for row in audit["instances"]:
            if row["house_index"] == house:
                row["position_m"] = (np.asarray(row["position_m"]) + displacement).tolist()
                row["aabb_center_m"] = (np.asarray(row["aabb_center_m"]) + displacement).tolist()
    write_json(directory / "runtime-partition-audit.json", audit)
    pin = seal(directory)
    return SimpleNamespace(directory=directory, inputs=task.inventory(directory), pin=pin)


def build_position(position_batch, batch, parent):
    return task.build(
        position_batch.directory,
        batch.public,
        parent.directory / "experiment",
        parent.report,
        {"test_fixture": "manually-varied-3D-SDK-references-not-real-simulation"},
        position_batch.inputs,
    )


@pytest.fixture(scope="module")
def position_built(position_batch, batch, parent):
    return build_position(position_batch, batch, parent)


@pytest.fixture(scope="module")
def pinned_controls(controls_built, tmp_path_factory):
    directory = tmp_path_factory.mktemp("position-pinned-controls")
    task.save_or_verify(directory / "experiment", controls_built, verify=False)
    files = task.inventory(directory / "experiment")
    ledger = [
        dict(
            phase=phase,
            source_sha="a" * 40,
            exit_code=0,
            output_sha256=files,
            argv=["do-not-execute-untrusted-ledger-command"],
        )
        for phase in ("run", "verify")
    ]
    write_json(directory / "case-results.json", ledger)
    pin = task.digest(directory / "case-results.json")
    report, binding = task.verify_controls(directory, ledger_pin=pin, source=controls.ROOT)
    return SimpleNamespace(directory=directory, pin=pin, report=report, binding=binding)


def test_actual_public_private_join_four_modes_and_all_frame_populations(position_built):
    report = json.loads(position_built["report.json"])
    assert len(report["frames"]) == 96 and len({r["action_id"] for r in report["frames"]}) == 96
    assert report["models_fitted"] == 4
    assert report["training_attempted"] is report["training_performed"] is True
    for flag in (
        "calibrated",
        "natural_factor_completed",
        "world_identity_assigned",
        "formal_position_reference_selected",
        "orientation_observed",
        "runtime_authority",
    ):
        assert report[flag] is False
    expected_modes = {f"{e}/{r}" for e in task.ESTIMATORS for r in task.REFERENCES}
    assert set(report["model_status"]) == set(report["results"]) == expected_modes
    for name in expected_modes:
        status = report["model_status"][name]
        assert status["status"] == "fitted"
        model = json.loads(position_built[f"models/{name}.json"])
        assert task.position.restore(model, status["sha256"]) == model
        assert model["estimator"] + "/" + model["reference_kind"] == name
        first_house = report["results"][name]["by_house"]["1"]
        assert first_house["seeds"] == first_house["houses"] == first_house["objects"] == 0
        assert first_house["raw"]["euclidean_rmse_m"] is None
        for split in ("train", "validation"):
            row = report["results"][name]["by_split"][split]
            assert row["seeds"] > row["object_frames"] >= row["objects"] > 0
            assert row["corrected"]["mean_nll"] is not None
    void_with_prediction = 0
    for ordinal, descriptor in enumerate(report["frames"]):
        assert descriptor["house_index"] == ordinal // 8 + 1
        assert descriptor["split"] == ("train" if ordinal < 64 else "validation")
        prefix = descriptor["prefix"]
        public = json.loads(position_built[f"{prefix}/public.json"])
        private = json.loads(position_built[f"{prefix}/labels.json"])
        corrected = json.loads(position_built[f"{prefix}/corrected.json"])
        assert len(public["observations"]) == len(private["labels"]) == len(corrected) // 2
        assert private["readout_sha256"] == task.content_sha256(public)
        if ordinal < 8:
            assert public["seeds"] == private["labels"] == corrected == []
        for obs, label in zip(public["observations"], private["labels"], strict=True):
            assert (obs["measurement_id"], obs["estimator"]) == (
                label["measurement_id"],
                label["estimator"],
            )
            if obs["available"] and not label["eligible"]:
                matches = [
                    c
                    for c in corrected
                    if c["measurement_id"] == obs["measurement_id"]
                    and c["estimator"] == obs["estimator"]
                ]
                assert len(matches) == 2 and all(
                    c["corrected_world_point_m"] is not None for c in matches
                )
                void_with_prediction += 1
    assert void_with_prediction > 0


def test_public_all_first_train_only_fit_and_predictions_before_validation(
    position_batch,
    batch,
    parent,
    position_built,
    monkeypatch,
):
    actual_public, actual_collect = task.public_readout, task.collect_public
    actual_private, actual_fit = task.private_readout, task.position.fit
    actual_diagnose = task.diagnose
    events, saved_records = [], []

    def public(*args, **kwargs):
        result = actual_public(*args, **kwargs)
        events.append("public")
        return result

    def collect(*args, **kwargs):
        records = actual_collect(*args, **kwargs)
        saved_records.extend(records)
        return records

    def private(directory, record, *args):
        assert events.count("public") == 96
        result = actual_private(directory, record, *args)
        if record["split"] == "train":
            assert events.count("fit") == 0
            events.append("train")
        else:
            assert events.count("train") == 64 and events.count("fit") == 4
            assert events.count("diagnose") == 1
            assert len(saved_records) == 96 and all("corrected" in r for r in saved_records)
            events.append("validation")
            # A deliberate post-prediction test intervention, never a claimed SDK truth.
            for label in result["labels"]:
                if label["eligible"]:
                    for reference in task.REFERENCES:
                        label["targets"][reference] = (
                            np.asarray(label["targets"][reference]) + np.array([1.0, -2.0, 3.0])
                        ).tolist()
        return result

    def fit(residuals, members, **kwargs):
        assert events.count("train") == 64 and "validation" not in events
        assert kwargs["partition"] == "train" and all(m["house_index"] <= 8 for m in members)
        events.append("fit")
        return actual_fit(residuals, members, **kwargs)

    def diagnose(models, public_records, *, model_pins):
        assert events.count("public") == 96 and events.count("train") == 64
        assert events.count("fit") == 4 and "validation" not in events
        assert all("corrected" in r for r in saved_records)
        assert all(("labels" in r) == (r["split"] == "train") for r in saved_records)
        assert len(public_records) == len(saved_records) == 96
        observation_keys = {
            "measurement_id",
            "estimator",
            "estimator_pin",
            "domain_id",
            "frame_id",
            "action_id",
            "valid_at",
            "world_point_m",
            "seed_id",
            "available",
            "reason",
        }
        for projected, original in zip(public_records, saved_records, strict=True):
            assert set(projected) == {"house_index", "sdk_index", "action_id", "observations"}
            assert projected == {
                "house_index": original["house_index"],
                "sdk_index": original["sdk_index"],
                "action_id": original["action_id"],
                "observations": original["public"]["observations"],
            }
            assert all(set(obs) == observation_keys for obs in projected["observations"])
        assert model_pins == {
            name: task.position.checkpoint_sha256(model) for name, model in models.items()
        }
        events.append("diagnose")
        return actual_diagnose(models, public_records, model_pins=model_pins)

    monkeypatch.setattr(task, "public_readout", public)
    monkeypatch.setattr(task, "collect_public", collect)
    monkeypatch.setattr(task, "private_readout", private)
    monkeypatch.setattr(task.position, "fit", fit)
    monkeypatch.setattr(task, "diagnose", diagnose)
    changed = build_position(position_batch, batch, parent)
    assert events == (
        ["public"] * 96 + ["train"] * 64 + ["fit"] * 4 + ["diagnose"] + ["validation"] * 32
    )
    assert changed["report.json"] != position_built["report.json"]
    for name, raw in position_built.items():
        if (
            name.startswith("models/")
            or name.endswith(("/public.json", "/corrected.json"))
            or name == "controlled-position-consumption.json"
        ):
            assert changed[name] == raw


def test_explicit_planar_reference_intervention_preserves_rank_failure(batch, parent, monkeypatch):
    # The original fixture actually has rank three. This explicit private-boundary
    # intervention tests failure retention, not same-SDK physical reference truth.
    # The separate positive path above uses the real coherent SDK/audit join.
    actual = task.private_readout

    def planar(directory, record, *args):
        result = actual(directory, record, *args)
        uniform = {
            o["measurement_id"]: o["world_point_m"]
            for o in record["public"]["observations"]
            if o["estimator"] == "uniform"
        }
        for label in result["labels"]:
            if label["eligible"]:
                point = np.asarray(uniform[label["measurement_id"]])
                u, v = label["pixel_uv"]
                target = (point - np.array([u * 0.02, 0.0, v * 0.02])).tolist()
                label["targets"] = {r: target.copy() for r in task.REFERENCES}
        return result

    monkeypatch.setattr(task, "private_readout", planar)
    documents = task.build(
        batch.directory,
        batch.public,
        parent.directory / "experiment",
        parent.report,
        {"test_fixture": "explicit-planar-private-intervention"},
        batch.inputs,
    )
    report = json.loads(documents["report.json"])
    failures = {
        name for name, status in report["model_status"].items() if status["status"] == "fit_failed"
    }
    assert {"uniform/" + r for r in task.REFERENCES} <= failures
    assert len(report["frames"]) == 96
    for name in failures:
        failure = json.loads(documents[f"models/{name}.json"])
        assert failure == report["model_status"][name]
        assert "rank" in failure["reason"] or "positive definite" in failure["reason"]
        assert failure["training_seeds"] > 0
        assert f"training/{name}/residuals.npy" in documents
        assert f"training/{name}/members.json" in documents
        errors = np.load(
            io.BytesIO(documents[f"training/{name}/residuals.npy"]), allow_pickle=False
        )
        assert np.linalg.matrix_rank(errors - errors.mean(axis=0)) < 3
    for row in report["frames"]:
        corrected = json.loads(documents[f"{row['prefix']}/corrected.json"])
        for item in corrected:
            if item["estimator"] + "/" + item["reference_kind"] in failures:
                assert not item["model_available"]
                assert item["model_sha256"] is item["corrected_world_point_m"] is None


def test_all_void_training_is_retained_as_four_fit_failures(
    position_batch, batch, parent, monkeypatch
):
    actual = task.private_readout

    def no_labels(*args, **kwargs):
        result = actual(*args, **kwargs)
        for row in result["labels"]:
            row.update(
                eligible=False,
                void_reason="controlled_all_void",
                object_id=None,
                targets={reference: None for reference in task.REFERENCES},
            )
        return result

    monkeypatch.setattr(task, "private_readout", no_labels)
    documents = build_position(position_batch, batch, parent)
    report = json.loads(documents["report.json"])
    assert report["training_attempted"] is True and report["training_performed"] is False
    assert report["models_fitted"] == 0 and len(report["frames"]) == 96
    for status in report["model_status"].values():
        assert status["status"] == "fit_failed" and status["training_seeds"] == 0
    for result in report["results"].values():
        assert result["by_split"]["train"]["seeds"] == 0
        assert result["by_split"]["train"]["corrected"] is None
    assert all(f["supervised_seeds"] == 0 for f in report["frames"])


def test_complete_model_corrected_and_report_resigning_loses_to_fresh_rebuild(
    position_batch,
    batch,
    parent,
    position_built,
    tmp_path,
):
    target = tmp_path / "saved"
    task.save_or_verify(target, position_built, verify=False)
    fresh = build_position(position_batch, batch, parent)
    assert fresh == position_built
    task.save_or_verify(target, fresh, verify=True)
    forged = copy.deepcopy(position_built)
    report = json.loads(forged["report.json"])
    models = {}
    for name, status in report["model_status"].items():
        model = json.loads(forged[f"models/{name}.json"])
        model["bias"] = (np.asarray(model["bias"]) + np.array([0.5, -0.75, 1.0])).tolist()
        pin = task.position.checkpoint_sha256(model)
        task.position.restore(model, pin)
        status["sha256"] = pin
        models[name] = model
        forged[f"models/{name}.json"] = task.encoded(model)
    records = []
    for descriptor in report["frames"]:
        prefix = descriptor["prefix"]
        public = json.loads(forged[f"{prefix}/public.json"])
        labels = json.loads(forged[f"{prefix}/labels.json"])
        corrected = json.loads(forged[f"{prefix}/corrected.json"])
        obs = {(o["measurement_id"], o["estimator"]): o for o in public["observations"]}
        for item in corrected:
            name = item["estimator"] + "/" + item["reference_kind"]
            source = obs[item["measurement_id"], item["estimator"]]
            item["model_sha256"] = report["model_status"][name]["sha256"]
            item["corrected_world_point_m"] = (
                None
                if not item["available"]
                else (
                    np.asarray(source["world_point_m"]) - np.asarray(models[name]["bias"])
                ).tolist()
            )
        forged[f"{prefix}/corrected.json"] = task.encoded(corrected)
        # Use a stable public-metadata identity solely for complete forged summaries.
        records.append(
            dict(
                **descriptor,
                public=public,
                labels=labels,
                record={"public_metadata": public["provenance"]},
            )
        )
    for name, model in models.items():
        estimator, reference = name.split("/")
        report["results"][name] = dict(
            by_split={
                s: task.summarize_rows(
                    task.paired_rows([r for r in records if r["split"] == s], estimator, reference),
                    model,
                )
                for s in ("train", "validation")
            },
            by_house={
                str(h): task.summarize_rows(
                    task.paired_rows(
                        [r for r in records if r["house_index"] == h], estimator, reference
                    ),
                    model,
                )
                for h in range(1, 13)
            },
        )
    report["members"] = {
        n: hashlib.sha256(raw).hexdigest() for n, raw in forged.items() if n != "report.json"
    }
    forged["report.json"] = task.encoded(report)
    for name, raw in forged.items():
        (target / name).write_bytes(raw)
    attacked = task.inventory(target)
    with pytest.raises(ValueError, match="fresh trained outputs differ"):
        task.save_or_verify(target, fresh, verify=True)
    assert task.inventory(target) == attacked
    after = tmp_path / "legal-after-forgery"
    task.save_or_verify(after, fresh, verify=False)
    task.save_or_verify(after, fresh, verify=True)


@pytest.mark.parametrize("attack", ["pin", "self_signed", "status", "schedule", "source"])
def test_controls_external_pin_and_structure(pinned_controls, tmp_path, attack):
    moved = tmp_path / "controls"
    shutil.copytree(pinned_controls.directory, moved)
    pin, source = pinned_controls.pin, controls.ROOT
    ledger = json.loads((moved / "case-results.json").read_text())
    if attack == "pin":
        pin = "0" * 64
    elif attack == "source":
        source = tmp_path / "different-source"
        (source / "tools").mkdir(parents=True)
        (source / "tools/fake.py").write_text("# not the source\n")
    else:
        report = json.loads((moved / "experiment/report.json").read_text())
        if attack == "status":
            ledger[0]["exit_code"] = False
        elif attack == "schedule":
            report["frames"][0]["split"] = "validation"
        else:
            report["overall"]["unique_pairs"] += 1
        write_json(moved / "experiment/report.json", report)
        for case in ledger:
            case["output_sha256"] = task.inventory(moved / "experiment")
        write_json(moved / "case-results.json", ledger)
        if attack in ("status", "schedule"):
            pin = task.digest(moved / "case-results.json")
    with pytest.raises(ValueError):
        task.verify_controls(moved, ledger_pin=pin, source=source)


def test_controls_relocation_and_explicit_fresh_subprocess(pinned_controls, tmp_path, monkeypatch):
    moved = tmp_path / "relocated-controls"
    shutil.copytree(pinned_controls.directory, moved)
    assert task.verify_controls(moved, ledger_pin=pinned_controls.pin, source=controls.ROOT) == (
        pinned_controls.report,
        pinned_controls.binding,
    )
    source = tmp_path / "source with spaces"
    (source / "tools").mkdir(parents=True)
    (source / "tools/run_instance_affinity_controls.py").write_text("# explicit fixture process\n")
    entry = tmp_path / "venv/bin/python"
    entry.parent.mkdir(parents=True)
    entry.symlink_to(Path(sys.executable).resolve())
    args = SimpleNamespace(
        controls_source=source,
        controls_results=moved,
        controls_ledger_sha256=pinned_controls.pin,
        historical_python=entry,
        sdk_python=entry,
        affinity_ledger_sha256="a" * 64,
        inventory_sha256="b" * 64,
        frontend_ledger_sha256="c" * 64,
        **{
            k: tmp_path / k
            for k in (
                "affinity_results",
                "affinity_source",
                "collection",
                "capture_source",
                "archive",
                "binary",
                "frontends",
                "frontend_source",
            )
        },
    )
    calls = []

    def process(argv, **kwargs):
        calls.append(argv)
        assert argv[0] == str(entry.absolute()) != str(entry.resolve())
        assert argv[argv.index("--sdk-python") + 1] == str(entry.absolute())
        assert argv[-1] == "--verify" and "do-not-execute-untrusted-ledger-command" not in argv
        assert kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
        assert kwargs["cwd"] == source and kwargs["timeout"] == 1800
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(task.subprocess, "run", process)
    monkeypatch.setattr(
        task, "verify_controls", lambda *a, **k: (pinned_controls.report, pinned_controls.binding)
    )
    task.fresh_controls(args, pinned_controls.binding)
    assert len(calls) == 1
    monkeypatch.setattr(
        task.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1)
    )
    with pytest.raises(ValueError, match="historical controls fresh refit failed"):
        task.fresh_controls(args, pinned_controls.binding)


def test_empty_metrics_do_not_invent_errors_or_samples():
    result = task.summarize_rows([], None)
    assert result["seeds"] == result["frames"] == result["houses"] == result["objects"] == 0
    assert result["raw"]["mean_nll"] is result["raw"]["euclidean_rmse_m"] is None
    assert result["corrected"] is None


def test_cli_verify_calls_complete_fresh_build_and_never_overwrites_mismatch(tmp_path, monkeypatch):
    # Explicit composition-boundary substitutes: real rebuild/save checks are above.
    path_names = (
        "controls-results",
        "controls-source",
        "affinity-results",
        "affinity-source",
        "historical-python",
        "collection",
        "capture-source",
        "archive",
        "sdk-python",
        "binary",
        "frontends",
        "frontend-source",
        "output",
    )
    paths = {name: tmp_path / name for name in path_names}
    argv = ["run_soft_position_development.py"]
    for name, path in paths.items():
        argv.extend(["--" + name, str(path)])
    for name, pin in (
        ("controls-ledger-sha256", "a" * 64),
        ("affinity-ledger-sha256", "b" * 64),
        ("inventory-sha256", "c" * 64),
        ("frontend-ledger-sha256", "d" * 64),
    ):
        argv.extend(["--" + name, pin])
    argv.append("--verify")
    calls = []
    parent_binding = {"parent": "bound"}
    controls_binding = {"controls": "bound"}
    frontend_binding = {"frontends": "bound"}

    def controls_checked(directory, **kwargs):
        assert directory == paths["controls-results"] and kwargs["ledger_pin"] == "a" * 64
        calls.append("controls")
        return {"parent_binding": parent_binding}, controls_binding

    def affinity_checked(directory, **kwargs):
        assert directory == paths["affinity-results"] and kwargs["ledger_pin"] == "b" * 64
        calls.append("affinity")
        return {}, parent_binding

    def frontend_checked(directory, **kwargs):
        assert directory == paths["frontends"] and kwargs["ledger_pin"] == "d" * 64
        calls.append("frontends")
        return {}, frontend_binding

    def history(args, expected):
        assert expected == controls_binding
        calls.append("history_fresh")

    expected = {"report.json": task.encoded(dict(models_fitted=4, scope="cli-composition-fixture"))}

    def build(*args):
        calls.append("fresh_build")
        assert args[-1] == {"inventory.json": "c" * 64}
        assert args[-2]["controls"] == controls_binding
        return expected

    task.save_or_verify(paths["output"], expected, verify=False)
    real_inventory = task.inventory
    monkeypatch.setattr(
        task,
        "inventory",
        lambda path: (
            {"inventory.json": "c" * 64} if path == paths["collection"] else real_inventory(path)
        ),
    )
    monkeypatch.setattr(task, "_json", lambda path: {})
    monkeypatch.setattr(task, "verify_controls", controls_checked)
    monkeypatch.setattr(task, "fresh_controls", history)
    monkeypatch.setattr(task, "verify_affinity", affinity_checked)
    monkeypatch.setattr(task, "verify_frontends", frontend_checked)
    monkeypatch.setattr(task, "build", build)
    monkeypatch.setattr(sys, "argv", argv)
    task.main()
    assert calls == [
        "controls",
        "history_fresh",
        "affinity",
        "frontends",
        "fresh_build",
        "controls",
        "affinity",
        "frontends",
    ]
    (paths["output"] / "report.json").write_bytes(b'{"models_fitted":0}\n')
    with pytest.raises(ValueError, match="fresh trained outputs differ"):
        task.main()
    assert (paths["output"] / "report.json").read_bytes() == b'{"models_fitted":0}\n'
