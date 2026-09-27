"""Second review: plausible re-sealed supervision, evidence consumers, lifecycle."""

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
import run_visor_pixel_probe as cli  # noqa: E402
from test_visor_pixel_supervision import fixture_pixel, tiny_training  # noqa: E402

from cpswm.data_preflight import visor_contact_supervision as source_module  # noqa: E402
from cpswm.data_preflight import visor_pixel_probe as probe  # noqa: E402
from cpswm.data_preflight import visor_pixel_supervision as pixel  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402


def test_complete_self_consistent_forged_supervision_rejected_and_retry(tmp_path, monkeypatch):
    source, contact, out, sources = fixture_pixel(tmp_path, monkeypatch)
    expected = pixel.prepare(source, contact, out)
    altered = copy.deepcopy(sources)
    doc = json.loads(altered["P01_01.json"])
    doc["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    altered["P01_01.json"] = pixel.encoded(doc)
    forged = pixel.compile_targets(source_module._derive(altered))
    manifest = json.loads(forged["manifest.json"])
    assert all(pixel.sha(forged[k]) == v["sha256"] for k, v in manifest["members"].items())
    assert manifest["summary"]["pixels"]["contact"] != expected["summary"]["pixels"]["contact"]
    for k, v in forged.items():
        (out / k).write_bytes(v)
    with pytest.raises(ValueError, match="recomputation"):
        pixel.load_component(source, contact, out, count=5)
    for k, v in pixel.compile_targets(source_module._derive(sources)).items():
        (out / k).write_bytes(v)
    assert pixel.load_component(source, contact, out, count=5)["summary"] == expected["summary"]


def test_after_verification_rewrite_cannot_change_returned_training_targets(tmp_path, monkeypatch):
    source, contact, out, _ = fixture_pixel(tmp_path, monkeypatch)
    m = pixel.prepare(source, contact, out)
    original = pixel._verify_artifacts

    def swap(path, artifacts):
        original(path, artifacts)
        if path == out:
            (out / m["rows"][0]["targets"]["contact"]).write_bytes(b"forged after check")

    monkeypatch.setattr(pixel, "_verify_artifacts", swap)
    batch = pixel.load_component(source, contact, out, count=5)
    assert torch.any(probe.labels_from_png(batch["targets"][0])[1] == 1)
    with pytest.raises(ValueError):
        pixel.load_component(source, contact, out, count=5)


def test_label_intervention_changes_only_targets_not_rgb_input(tmp_path, monkeypatch):
    _, _, _, sources = fixture_pixel(tmp_path, monkeypatch)
    original = source_module._derive(sources)
    changed = copy.deepcopy(sources)
    doc = json.loads(changed["P01_01.json"])
    doc["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    changed["P01_01.json"] = pixel.encoded(doc)
    other = source_module._derive(changed)
    assert all(other[k] == v for k, v in original.items() if k.startswith("runtime/"))
    a, b = pixel.compile_targets(original), pixel.compile_targets(other)
    assert any(a[k] != b[k] for k in a if k.endswith("/contact.png"))
    assert all(a[k] == b[k] for k in a if k.endswith("/hand.png"))


def test_plausible_checkpoint_mutation_rejected_by_external_pin():
    f, t = tiny_training()
    _, raw = probe.fit(f, t, "a" * 64)
    pin = probe.sha(raw)
    doc = json.loads(raw)
    doc["bias"][0] += 1
    forged = pixel.encoded(doc)
    assert probe.state_digest(probe.restore_head(forged, probe.sha(forged))) != probe.state_digest(
        probe.restore_head(raw, pin)
    )
    with pytest.raises(ValueError, match="fixed execution digest"):
        probe.restore_head(forged, pin)


def test_complete_forged_report_rejected_by_recomputed_probe_consumer(tmp_path, monkeypatch):
    f, t = tiny_training()

    def compute(*_):
        report, raw = probe.fit(f, t, "a" * 64)
        report.update(verification_extra_sgd_updates=2, original_detector_unchanged=True)
        return {"head.json": raw, "report.json": pixel.encoded(report)}

    monkeypatch.setattr(cli, "probe", compute)
    source, contact, packet = [tmp_path / n for n in ("source", "contact", "pixel")]
    output = tmp_path / "result"
    cli.run_probe(source, contact, packet, None, output)
    report = json.loads((output / "report.json").read_bytes())
    report["after"][0]["objective"] = 0
    (output / "report.json").write_bytes(pixel.encoded(report))
    with pytest.raises(ValueError, match="recomputation"):
        cli.run_probe(source, contact, packet, None, output, True)
    for k, v in compute().items():
        (output / k).write_bytes(v)
    cli.run_probe(source, contact, packet, None, output, True)
    with pytest.raises(ValueError):
        ProposalSample.model_validate(report)


def test_atomic_target_write_failure_leaves_no_success_and_retry(tmp_path, monkeypatch):
    source, contact, out, _ = fixture_pixel(tmp_path, monkeypatch)
    original = Path.write_bytes

    def fail(path, raw):
        if any(p.startswith(".visor-pixel-") for p in path.parts):
            raise OSError("injected disk failure")
        return original(path, raw)

    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError):
        pixel.prepare(source, contact, out)
    assert not out.exists() and not list(tmp_path.glob(".visor-pixel-*"))
    monkeypatch.setattr(Path, "write_bytes", original)
    assert pixel.prepare(source, contact, out)["summary"]["frames"] == 5


@pytest.mark.parametrize("kind", ["extra", "omitted", "symbolic", "hard"])
def test_target_package_closure_and_alias_rejection(tmp_path, monkeypatch, kind):
    import os

    source, contact, out, _ = fixture_pixel(tmp_path, monkeypatch)
    m = pixel.prepare(source, contact, out)
    p = out / m["rows"][0]["targets"]["hand"]
    if kind == "extra":
        (out / "untrusted.json").write_text("{}")
    elif kind == "omitted":
        p.unlink()
    else:
        q = tmp_path / "alias.png"
        q.write_bytes(p.read_bytes())
        p.unlink()
        if kind == "symbolic":
            p.symlink_to(q)
        else:
            os.link(q, p)
    with pytest.raises(ValueError):
        pixel.load_component(source, contact, out, count=5)
