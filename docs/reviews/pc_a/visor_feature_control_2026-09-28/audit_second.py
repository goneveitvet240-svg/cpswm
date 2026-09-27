"""Second local review: source forgery, isolation and consequential report consumers."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
import run_visor_feature_control as cli  # noqa: E402
from test_visor_feature_control import second_sources  # noqa: E402
from test_visor_pixel_supervision import tiny_training  # noqa: E402

from cpswm.data_preflight import visor_contact_supervision as contact  # noqa: E402
from cpswm.data_preflight import visor_control_data as data  # noqa: E402
from cpswm.data_preflight import visor_feature_control as control  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402


def driver_fixture(monkeypatch):
    features, targets = tiny_training()

    def row(i):
        return {"ordinal": i, "rgb_sha256": str(i), "pixel_sha256": str(i), "key": str(i)}

    train = {
        "inputs": [(row(i), bytes([i])) for i in range(8)],
        "targets": targets[:8],
        "manifest_sha256": "a" * 64,
    }
    dev = {
        "inputs": [(row(i), bytes([i])) for i in range(8, 11)],
        "targets": targets[8:11],
        "manifest_sha256": "b" * 64,
        "source_report": {},
        "source_pins": {},
        "summary": {},
        "pixel_manifest": b"{}",
    }
    monkeypatch.setattr(cli, "load_component", lambda *a, **k: train)
    monkeypatch.setattr(cli, "derive_component", lambda *a: dev)
    model = torch.nn.Linear(1, 1)
    model.requires_grad_(False)
    monkeypatch.setattr(
        cli,
        "FasterNaturalAppearanceDetector",
        lambda **k: SimpleNamespace(
            _model=model, weights_sha256="c" * 64, _versions=["fixture", "fixture"]
        ),
    )
    seen = []

    def extract(model, rgb):
        seen.append(rgb[0])
        return features[rgb[0]]

    monkeypatch.setattr(cli, "extract_rgb", extract)
    monkeypatch.setattr(cli, "labels_from_png", lambda t: t)
    return features, targets, train, dev, seen


def test_driver_complete_positive_path_permutation_and_dev_label_noninterference(monkeypatch):
    f, t, _, dev, seen = driver_fixture(monkeypatch)
    original = cli.compute(None, None, None, None, None)
    r = json.loads(original["report.json"])
    assert seen == list(range(11))
    assert r["training_updates"] == 256 and r["original_detector_unchanged"]
    for name in ("feature_16", "feature_128"):
        raw = original[name + ".json"]
        head = control.restore(raw, control.sha(raw))
        assert r["rows"]["cyclic_wrong_image"][name] == [
            control.measure(head, f[j], t[i]) for i, j in [(8, 9), (9, 10), (10, 8)]
        ]
    for target in dev["targets"]:
        target[target != 255] = 1 - target[target != 255]
    changed = cli.compute(None, None, None, None, None)
    r2 = json.loads(changed["report.json"])
    assert all(original[k] == changed[k] for k in original if k != "report.json")
    assert r["updates"] == r2["updates"]
    assert r["constant_probabilities"] == r2["constant_probabilities"]
    assert r["rows"]["train"] == r2["rows"]["train"]
    assert r["rows"]["separate_video"] != r2["rows"]["separate_video"]
    with pytest.raises(ValueError):
        ProposalSample.model_validate(r)


def test_forged_but_complete_heads_report_rejected_then_valid_retry(tmp_path, monkeypatch):
    driver_fixture(monkeypatch)
    args = [tmp_path / n for n in ["source", "contact", "pixel", "diagnostic", "weights"]]
    out = tmp_path / "run"
    cli.run(*args, out)
    saved = {p.name: p.read_bytes() for p in out.iterdir()}
    report = json.loads(saved["report.json"])
    for name in report["checkpoint_digests"]:
        doc = json.loads(saved[name])
        doc["bias"][0] += 1
        raw = control.encoded(doc)
        control.restore(raw, control.sha(raw))  # Plausible complete model, internally valid.
        (out / name).write_bytes(raw)
        report["checkpoint_digests"][name] = control.sha(raw)
    report["summary"]["separate_video"]["feature_128"]["objective_equal_frame"] = 0.01
    (out / "report.json").write_bytes(control.encoded(report))
    with pytest.raises(ValueError, match="recomputation"):
        cli.run(*args, out, verify=True)
    for name, raw in saved.items():
        (out / name).write_bytes(raw)
    cli.run(*args, out, verify=True)


def test_complete_forged_diagnostic_source_cannot_self_enroll(tmp_path, monkeypatch):
    root, source = second_sources(tmp_path, monkeypatch)
    valid = data.derive_component(root)
    forged = copy.deepcopy(source)
    d = json.loads(forged["P01_03.json"])
    d["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    forged["P01_03.json"] = contact.encoded(d)
    self_consistent = contact._derive(forged, video="P01_03")
    m = json.loads(self_consistent["manifest.json"])
    assert all(contact._sha(self_consistent[k]) == v["sha256"] for k, v in m["members"].items())
    (root / "P01_03.json").write_bytes(forged["P01_03.json"])
    with pytest.raises(ValueError, match="enrolled"):
        data.derive_component(root)
    (root / "P01_03.json").write_bytes(source["P01_03.json"])
    assert data.derive_component(root) == valid


def test_atomic_failure_cleanup_and_retry(tmp_path, monkeypatch):
    # This tests only commit lifecycle; numerical producer is covered above.
    monkeypatch.setattr(cli, "compute", lambda *a: {"report.json": b"{}", "head.json": b"{}"})
    args = [tmp_path / n for n in ["source", "contact", "pixel", "diagnostic", "weights"]]
    out = tmp_path / "run"
    original = Path.write_bytes

    def fail(path, raw):
        if any(p.startswith(".feature-control-") for p in path.parts):
            raise OSError("injected failure")
        return original(path, raw)

    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError):
        cli.run(*args, out)
    assert not out.exists() and not list(tmp_path.glob(".feature-control-*"))
    monkeypatch.setattr(Path, "write_bytes", original)
    cli.run(*args, out)
    cli.run(*args, out, verify=True)


@pytest.mark.parametrize("kind", ["extra", "missing", "symlink", "hardlink"])
def test_result_closure_and_alias_rejection(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(cli, "compute", lambda *a: {"report.json": b"{}", "head.json": b"{}"})
    args = [tmp_path / n for n in ["source", "contact", "pixel", "diagnostic", "weights"]]
    out = tmp_path / "run"
    cli.run(*args, out)
    p = out / "head.json"
    if kind == "extra":
        (out / "extra").write_bytes(b"")
    elif kind == "missing":
        p.unlink()
    else:
        q = tmp_path / "alias"
        q.write_bytes(p.read_bytes())
        p.unlink()
        if kind == "symlink":
            p.symlink_to(q)
        else:
            p.hardlink_to(q)
    with pytest.raises(ValueError):
        cli.run(*args, out, verify=True)
