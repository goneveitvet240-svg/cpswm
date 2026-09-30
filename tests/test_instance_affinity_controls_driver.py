"""Matched controlled pairs, complete output forgery and original-anchor guards.

The reused synthetic masks/detector are disclosed development fixtures. The
subprocess boundary test substitutes only process execution to inspect argv;
real history reconstruction is exercised separately in the frozen CLI audit.
PYTEST_DONT_REWRITE: source-bound fixture detector keeps its original code.
"""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import run_instance_affinity as parent_task
import run_instance_affinity_controls as task
from test_offline_frontend_diagnostic import complete_batch, write_json  # noqa: F401
from test_run_instance_affinity import batch, built  # noqa: F401


@pytest.fixture(scope="module")
def parent(built, tmp_path_factory):  # noqa: F811
    directory = tmp_path_factory.mktemp("feature-control-parent")
    parent_task.save_or_verify(directory / "experiment", built, verify=False)
    files = task.inventory(directory / "experiment")
    cases = [
        dict(
            phase=p,
            exit_code=0,
            source_sha="a" * 40,
            output_sha256=files,
            argv=["never-execute-this-ledger-value"],
        )
        for p in ("run", "verify")
    ]
    write_json(directory / "case-results.json", cases)
    pin = task.digest(directory / "case-results.json")
    report, binding = task.verify_parent(directory, ledger_pin=pin, source=task.ROOT)
    return SimpleNamespace(directory=directory, pin=pin, report=report, binding=binding)


@pytest.fixture(scope="module")
def controls_built(parent):
    return task.build(parent.directory / "experiment", parent.report, parent.binding)


def test_matched_three_fits_and_every_public_void_score(parent, controls_built):
    report = json.loads(controls_built["report.json"])
    assert report["modes"] == list(task.controls.MODES)
    assert report["combined_exact_parent_model_and_predictions"] is True
    assert len(report["frames"]) == 96 and len(report["by_house"]) == 12
    assert len(controls_built) == 292
    parent_model = json.loads((parent.directory / "experiment/model.json").read_text())
    records = task.load_public(parent.directory / "experiment", parent.report)
    for mode in task.controls.MODES:
        model = json.loads(controls_built[f"models/{mode}.json"])
        task.controls.restore(model, report["model_pins"][mode])
        inner = model["inner_checkpoint"]
        assert inner["class_counts"] == parent_model["class_counts"]
        assert inner["prevalence"] == parent_model["prevalence"]
        for record in records:
            import io

            p = np.load(
                io.BytesIO(controls_built[f"{record['prefix']}/{mode}.npy"]), allow_pickle=False
            )
            assert np.isfinite(p[record["valid"]]).all()
            assert np.isnan(p[~record["valid"]]).all()
            assert len(p) == len(record["pairs"])
    for split in ("train", "validation"):
        row = report["by_split"][split]
        assert row["void_pairs"] > 0 and row["negative_pairs"] > 0
        for mode in task.METHODS:
            assert row["methods"][mode]["same_instance"]["pairs"] == row["positive_pairs"]
            assert row["methods"][mode]["different_instance"]["pairs"] == row["negative_pairs"]
    empty = report["by_house"]["1"]
    for method in task.METHODS:
        for group in task.CLASSES:
            assert empty["methods"][method][group] == dict(pairs=0, bce=None, brier=None)
    combined = json.loads(controls_built["models/combined.json"])["inner_checkpoint"]
    assert task.encoded(combined) == (parent.directory / "experiment/model.json").read_bytes()


def test_validation_labels_only_after_all_three_public_predictions(
    parent, controls_built, monkeypatch
):
    old_load, old_predict = task.load_targets, task.controls.predict
    predicted = []

    def predict(*args, **kwargs):
        predicted.append(args[0]["mode"])
        return old_predict(*args, **kwargs)

    def targets(directory, record):
        y = old_load(directory, record)
        if record["split"] == "validation":
            assert len(predicted) == 288
            y = y.copy()
            keep = y != -1
            y[keep] = 1 - y[keep]
        else:
            assert not predicted
        return y

    monkeypatch.setattr(task, "load_targets", targets)
    monkeypatch.setattr(task.controls, "predict", predict)
    changed = task.build(parent.directory / "experiment", parent.report, parent.binding)
    assert changed["report.json"] != controls_built["report.json"]
    assert all(
        changed[name] == raw for name, raw in controls_built.items() if name != "report.json"
    )


def test_exact_parent_result_survives_path_relocation(parent, tmp_path):
    moved = tmp_path / "moved inputs with spaces"
    shutil.copytree(parent.directory, moved)
    report, binding = task.verify_parent(moved, ledger_pin=parent.pin, source=task.ROOT)
    assert report == parent.report and binding == parent.binding
    assert task.build(moved / "experiment", report, binding) == task.build(
        parent.directory / "experiment", parent.report, parent.binding
    )


@pytest.mark.parametrize(
    "attack",
    ["pin", "self_signed", "missing_frame", "source", "status_bool", "incomplete", "partition"],
)
def test_parent_external_anchor_and_structural_rejection(parent, tmp_path, attack):
    moved = tmp_path / "parent"
    shutil.copytree(parent.directory, moved)
    pin, source = parent.pin, task.ROOT
    cases = json.loads((moved / "case-results.json").read_text())
    if attack == "pin":
        pin = "0" * 64
    elif attack == "source":
        source = tmp_path / "wrong-source"
        (source / "src").mkdir(parents=True)
        (source / "src/fake.py").write_text("changed = True\n")
    elif attack == "status_bool":
        cases[0]["exit_code"] = False
    elif attack == "incomplete":
        cases.pop()
    else:
        if attack == "missing_frame":
            (moved / "experiment/frames/001/targets.npy").unlink()
        elif attack == "partition":
            r = json.loads((moved / "experiment/report.json").read_text())
            r["frames"][0]["split"] = "validation"
            (moved / "experiment/report.json").write_bytes(task.encoded(r))
        else:
            p = moved / "experiment/frames/008/features.npy"
            x = np.load(p, allow_pickle=False)
            x[:, 0] = 0.99
            np.save(p, x, allow_pickle=False)
            r = json.loads((moved / "experiment/report.json").read_text())
            r["members"]["frames/008/features.npy"] = task.digest(p)
            (moved / "experiment/report.json").write_bytes(task.encoded(r))
        for case in cases:
            case["output_sha256"] = task.inventory(moved / "experiment")
    write_json(moved / "case-results.json", cases)
    if attack in ("status_bool", "incomplete", "missing_frame", "partition"):
        # These malformed candidates fail even with the caller pinning them.
        pin = task.digest(moved / "case-results.json")
    with pytest.raises(ValueError):
        task.verify_parent(moved, ledger_pin=pin, source=source)


def test_complete_models_predictions_and_metrics_forgery_rejected(parent, controls_built, tmp_path):
    forged = copy.deepcopy(controls_built)
    report = json.loads(forged["report.json"])
    records = task.load_public(parent.directory / "experiment", parent.report)
    for r in records:
        r["targets"] = task.load_targets(parent.directory / "experiment", r)
        r["predictions"] = {}
    for mode in task.controls.MODES:
        model = json.loads(forged[f"models/{mode}.json"])
        model["inner_checkpoint"]["bias"] += 1.0
        model["inner_sha256"] = task.baseline.checkpoint_sha256(model["inner_checkpoint"])
        pin = task.controls.checkpoint_sha256(model)
        task.controls.restore(model, pin)
        forged[f"models/{mode}.json"] = task.encoded(model)
        report["model_pins"][mode] = pin
        for r in records:
            p = np.asarray(
                [
                    np.nan if v is None else v
                    for v in task.controls.predict(model, r["features"], r["valid"])
                ],
                dtype=np.float64,
            )
            r["predictions"][mode] = p
            r["predictions"]["training_frequency_constant"] = np.where(
                r["valid"], model["inner_checkpoint"]["prevalence"], np.nan
            )
            forged[f"{r['prefix']}/{mode}.npy"] = task.array_bytes(p)
    for frame, r in zip(report["frames"], records, strict=True):
        frame["summary"] = task.summarize([r])
    report["by_house"] = {
        str(h): task.summarize([r for r in records if r["house_index"] == h]) for h in range(1, 13)
    }
    report["by_split"] = {
        s: task.summarize([r for r in records if r["split"] == s]) for s in ("train", "validation")
    }
    for split, row in report["by_split"].items():
        row["house_macro"] = task.house_macro(
            [report["by_house"][str(h)] for h in range(1, 13) if (h <= 8) == (split == "train")]
        )
    report["overall"] = task.summarize(records)
    report["members"] = {
        n: hashlib.sha256(b).hexdigest() for n, b in forged.items() if n != "report.json"
    }
    forged["report.json"] = task.encoded(report)
    target = tmp_path / "complete-forged-output"
    task.save_or_verify(target, forged, verify=False)
    with pytest.raises(ValueError, match="fresh trained outputs differ"):
        task.save_or_verify(
            target,
            task.build(parent.directory / "experiment", parent.report, parent.binding),
            verify=True,
        )
    assert task.inventory(target) == {n: hashlib.sha256(b).hexdigest() for n, b in forged.items()}
    positive = tmp_path / "legal-after-attack"
    task.save_or_verify(positive, controls_built, verify=False)
    task.save_or_verify(positive, controls_built, verify=True)


def test_missing_class_and_house_macro_denominator():
    result = task.class_scores(np.array([1, -1]), np.array([0.75, 0.1]))
    assert result["different_instance"] == dict(pairs=0, bce=None, brier=None)
    assert result["same_instance"] == dict(pairs=1, bce=-np.log(0.75), brier=0.0625)
    house = {"methods": {m: result for m in task.METHODS}}
    macro = task.house_macro([house])
    for m in task.METHODS:
        assert macro[m]["different_instance"] == dict(houses=0, bce=None, brier=None)
        assert macro[m]["same_instance"]["houses"] == 1


def test_fresh_parent_uses_explicit_arguments_and_preserves_venv(parent, tmp_path, monkeypatch):
    source = tmp_path / "historical source"
    (source / "tools").mkdir(parents=True)
    (source / "tools/run_instance_affinity.py").write_text("# explicit process boundary fixture\n")
    entry = tmp_path / "venv/bin/python"
    entry.parent.mkdir(parents=True)
    entry.symlink_to(Path(sys.executable).resolve())
    args = SimpleNamespace(
        affinity_source=source,
        affinity_results=parent.directory,
        historical_python=entry,
        sdk_python=entry,
        affinity_ledger_sha256=parent.pin,
        inventory_sha256="a" * 64,
        frontend_ledger_sha256="b" * 64,
        **{
            k: tmp_path / k
            for k in (
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
        assert argv[0] == str(entry.absolute()) and argv[0] != str(entry.resolve())
        assert argv[-1] == "--verify" and "never-execute-this-ledger-value" not in argv
        assert argv[argv.index("--sdk-python") + 1] == str(entry.absolute())
        assert kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
        assert kwargs["timeout"] == 1800 and kwargs["cwd"] == source
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(task.subprocess, "run", process)
    monkeypatch.setattr(task, "verify_parent", lambda *a, **k: (parent.report, parent.binding))
    task.fresh_parent(args, parent.binding)
    assert len(calls) == 1
    monkeypatch.setattr(
        task.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1)
    )
    with pytest.raises(ValueError, match="historical affinity fresh refit failed"):
        task.fresh_parent(args, parent.binding)
