"""Composed controlled RGB-D training, plus original-pin and fresh-result guards.

Fixture detector and rendered masks are explicit synthetic supervision. They do
not establish real simulation quality or satisfy the historical asset audit.
PYTEST_DONT_REWRITE: source-bound fixture decoder retains its implementation.
"""

import copy
import json
import shutil
import sys
from types import SimpleNamespace

import diagnose_offline_frontend as frontend
import numpy as np
import pytest
import run_instance_affinity as task
from test_offline_frontend_diagnostic import (  # noqa: F401
    complete_batch,
    decoder_factory_with_empty_first_house,
    seal,
    write_json,
)


@pytest.fixture(scope="module")
def batch(complete_batch, tmp_path_factory):  # noqa: F811
    original = complete_batch
    root = tmp_path_factory.mktemp("affinity-composed")
    directory = root / "collection"
    shutil.copytree(original.directory, directory)
    # Coherent controlled labels with two visible eligible objects and void floor.
    # No real image or held-out dataset is used to construct this learning fixture.
    colors = [dict(name="a", color=[1, 2, 3]), dict(name="b", color=[4, 5, 6])]
    for house in sorted(directory.glob("house-*")):
        private = house / "unity-logs/evaluator_only"
        for offset in range(4, 12):
            info_path = private / f"instances/{offset:03d}.json"
            info = json.loads(info_path.read_text())
            seg_path = private / f"instances/{offset:03d}-segmentation.npy"
            segmentation = np.load(seg_path, allow_pickle=False)
            h, w = segmentation.shape[:2]
            segmentation[:] = 0
            segmentation[: h * 3 // 4, : w // 2] = [1, 2, 3]
            segmentation[: h * 3 // 4, w // 2 :] = [4, 5, 6]
            arrays = {
                r["array_key"]: np.all(
                    segmentation == (colors[0 if r["object_id"] == "a" else 1]["color"]), axis=2
                )
                if r["object_id"] in ("a", "b")
                else np.zeros((h, w), dtype=bool)
                for r in info["catalog"]
            }
            np.save(seg_path, segmentation, allow_pickle=False)
            np.savez_compressed(private / f"instances/{offset:03d}-masks.npz", **arrays)
            info["colors"] = colors
            write_json(info_path, info)
            sdk_path = private / f"sdk-events/{offset:03d}.json"
            sdk = json.loads(sdk_path.read_text())
            sdk["metadata"]["colors"] = colors
            write_json(sdk_path, sdk)
    pin = seal(directory)
    inputs = frontend.inventory(directory)
    cache = root / "frontends"
    cache.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(frontend, "ROOT", original.current)
        for method in task.METHODS:
            documents = frontend.diagnose(
                directory,
                decoder_factory=decoder_factory_with_empty_first_house([]),
                input_inventory=inputs,
                capture_config=original.config,
                detector_kind=method,
            )
            frontend.save_or_verify(cache / method, documents, verify=False)
    cases = [
        dict(
            phase=phase,
            detector=method,
            source_sha="a" * 40,
            exit_code=0,
            output_sha256=frontend.inventory(cache / method),
        )
        for phase in ("run", "verify")
        for method in task.METHODS
    ]
    write_json(cache / "case-results.json", cases)
    kwargs = dict(
        ledger_pin=frontend.digest(cache / "case-results.json"),
        source=original.current,
        input_inventory=inputs,
        capture_config=original.config,
    )
    public, binding = task.verify_frontends(cache, **kwargs)
    return SimpleNamespace(
        root=root,
        directory=directory,
        inputs=inputs,
        cache=cache,
        kwargs=kwargs,
        public=public,
        binding=binding,
        pin=pin,
        source=original.current,
    )


@pytest.fixture(scope="module")
def built(batch):
    return task.build(
        batch.directory, batch.public, input_inventory=batch.inputs, frontend_binding=batch.binding
    )


def test_actual_controlled_learning_retains_all_frames_and_reload(built):
    report = json.loads(built["report.json"])
    model = json.loads(built["model.json"])
    assert len(report["frames"]) == 96 and len(report["by_house"]) == 12
    assert report["training_performed"] is True
    assert (
        not report["observation_likelihood_written"]
        and not report["world_instance_identity_assigned"]
    )
    assert report["by_house"]["1"]["model"] == dict(pairs=0, bce=None, brier=None)
    for split in ("train", "validation"):
        row = report["by_split"][split]
        assert row["positive_pairs"] > 0 and row["negative_pairs"] > 0 and row["void_pairs"] > 0
        assert row["raw_candidate_pairs"] == 2 * row["unique_pairs"]
        assert sum(row["void_reasons"].values()) == row["void_pairs"]
        assert row["model"]["bce"] < row["training_frequency_constant"]["bce"]
    training = report["by_split"]["train"]
    assert model["prevalence"] == training["positive_pairs"] / training["model"]["pairs"]
    assert task.checkpoint_sha256(model) == report["model_sha256"]
    assert report["source_files"] == task.source_identity(task.ROOT)


def test_validation_labels_cannot_change_model_or_any_predictions(batch, built, monkeypatch):
    actual_labels, actual_public, actual_predict = (
        task.private_labels,
        task.public_frame,
        task.predict,
    )
    events = []

    def public(*args, **kwargs):
        events.append("public")
        return actual_public(*args, **kwargs)

    def labels(directory, record, audit):
        assert events.count("public") == 96
        result = actual_labels(directory, record, audit)
        if record["split"] == "validation":
            assert events.count("predict") == 192
            result["targets"] = result["targets"].copy()
            selected = result["targets"] != -1
            result["targets"][selected] = 1 - result["targets"][selected]
        else:
            assert events.count("predict") == 0
        return result

    def predict(*args, **kwargs):
        events.append("predict")
        return actual_predict(*args, **kwargs)

    monkeypatch.setattr(task, "public_frame", public)
    monkeypatch.setattr(task, "private_labels", labels)
    monkeypatch.setattr(task, "predict", predict)
    changed = task.build(
        batch.directory, batch.public, input_inventory=batch.inputs, frontend_binding=batch.binding
    )
    assert changed["model.json"] == built["model.json"]
    assert all(changed[name] == raw for name, raw in built.items() if name.endswith("/scores.npy"))
    assert changed["report.json"] != built["report.json"]


def test_pinned_cache_and_source_can_move_unchanged(batch, tmp_path):
    moved, source = tmp_path / "frontends", tmp_path / "source"
    shutil.copytree(batch.cache, moved)
    shutil.copytree(batch.source, source)
    public, binding = task.verify_frontends(moved, **dict(batch.kwargs, source=source))
    assert public == batch.public and binding == batch.binding


@pytest.mark.parametrize(
    "attack",
    ["ledger_pin", "public_and_self_hash", "source", "numeric_status", "incomplete_ledger"],
)
def test_cached_outputs_require_original_external_ledger(batch, tmp_path, attack):
    moved, source = tmp_path / "frontends", tmp_path / "source"
    shutil.copytree(batch.cache, moved)
    shutil.copytree(batch.source, source)
    kwargs = dict(batch.kwargs, source=source)
    if attack == "ledger_pin":
        kwargs["ledger_pin"] = "0" * 64
    elif attack == "source":
        (source / "tools/changed.py").write_text("# changed historical inference source\n")
    elif attack == "public_and_self_hash":
        path = moved / "fasterrcnn/public.json"
        public = json.loads(path.read_text())
        public[8]["frame"]["frame"]["candidates"] = []
        write_json(path, public)
        report = json.loads((moved / "fasterrcnn/report.json").read_text())
        report["public_predictions_sha256"] = task.content_sha256(public)
        write_json(moved / "fasterrcnn/report.json", report)
        ledger = json.loads((moved / "case-results.json").read_text())
        for row in ledger:
            if row["detector"] == "fasterrcnn":
                row["output_sha256"] = task.inventory(moved / "fasterrcnn")
        write_json(moved / "case-results.json", ledger)
    else:
        ledger = json.loads((moved / "case-results.json").read_text())
        if attack == "numeric_status":
            ledger[0]["exit_code"] = False
        else:
            ledger.pop()
        write_json(moved / "case-results.json", ledger)
        # A caller can pin this invalid ledger; structural validation still rejects.
        kwargs["ledger_pin"] = task.digest(moved / "case-results.json")
    with pytest.raises(ValueError):
        task.verify_frontends(moved, **kwargs)


def test_full_saved_artifact_changes_are_rejected_against_fresh_result(built, tmp_path):
    output = tmp_path / "saved"
    task.save_or_verify(output, built, verify=False)
    task.save_or_verify(output, built, verify=True)
    original = task.inventory(output)
    forged = copy.deepcopy(built)
    report = json.loads(forged["report.json"])
    model = json.loads(forged["model.json"])
    model["bias"] += 2.0
    forged["model.json"] = task.encoded(model)
    report["model_sha256"] = task.checkpoint_sha256(model)
    import hashlib

    report["members"]["model.json"] = hashlib.sha256(forged["model.json"]).hexdigest()
    forged["report.json"] = task.encoded(report)
    for name, raw in forged.items():
        (output / name).write_bytes(raw)
    attacked = task.inventory(output)
    assert attacked != original
    with pytest.raises(ValueError, match="fresh trained outputs differ"):
        task.save_or_verify(output, built, verify=True)
    assert task.inventory(output) == attacked


def test_scoring_void_house_is_null_and_invalid_labelled_score_rejected():
    assert task.scores(np.array([-1, -1]), [None, 0.5]) == dict(pairs=0, bce=None, brier=None)
    assert task.scores(np.array([1, 0]), [0.5, 0.5])["brier"] == 0.25
    with pytest.raises(ValueError, match="no public prediction"):
        task.scores(np.array([1]), [None])


def test_cli_verify_reconstructs_and_preserves_venv_entrypoint(tmp_path, monkeypatch):
    sdk = tmp_path / "sdk-env/bin/python"
    sdk.parent.mkdir(parents=True)
    sdk.symlink_to(sys.executable)
    paths = {
        name: tmp_path / name
        for name in (
            "collection",
            "capture-source",
            "archive",
            "binary",
            "frontends",
            "frontend-source",
            "output",
        )
    }
    paths["sdk-python"] = sdk
    argv = ["run_instance_affinity.py"]
    for name, path in paths.items():
        argv.extend(["--" + name, str(path)])
    argv.extend(["--inventory-sha256", "a" * 64, "--frontend-ledger-sha256", "b" * 64, "--verify"])
    calls = []
    inventory = {"inventory.json": "a" * 64}

    def history(directory, **kwargs):
        calls.append("history")
        assert directory == paths["collection"]
        assert kwargs["sdk_python"] == sdk.absolute() and kwargs["sdk_python"] != sdk.resolve()
        assert kwargs["pin"] == "a" * 64
        return inventory, {"source_files": {}}

    def frontend(*args, **kwargs):
        calls.append("frontend")
        assert kwargs["ledger_pin"] == "b" * 64
        return {}, {"pin": "b" * 64}

    def rebuild(directory, public, **kwargs):
        calls.append("fresh_build")
        assert kwargs["input_inventory"] == inventory
        return {"record.json": b'{"fresh":true}\n'}

    monkeypatch.setattr(task, "verify_historical_collection", history)
    monkeypatch.setattr(task, "verify_frontends", frontend)
    monkeypatch.setattr(task, "build", rebuild)
    monkeypatch.setattr(sys, "argv", argv)
    task.save_or_verify(paths["output"], {"record.json": b'{"fresh":true}\n'}, verify=False)
    task.main()
    assert calls == ["history", "frontend", "fresh_build", "frontend"]
    (paths["output"] / "record.json").write_bytes(b'{"fresh":false}\n')
    with pytest.raises(ValueError, match="fresh trained outputs differ"):
        task.main()
    assert (paths["output"] / "record.json").read_bytes() == b'{"fresh":false}\n'
