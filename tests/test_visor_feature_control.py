"""Matched-budget math and source-bound video development fixtures."""

import copy
import io
import json
import zipfile

import pytest
import torch
from test_visor_pixel_supervision import fixture_pixel, tiny_training

from cpswm.data_preflight import visor_contact_supervision as contact
from cpswm.data_preflight import visor_control_data as data
from cpswm.data_preflight import visor_feature_control as control


def second_sources(tmp_path, monkeypatch):
    _, _, _, sources = fixture_pixel(tmp_path, monkeypatch)
    d = json.loads(sources.pop("P01_01.json"))
    for frame in d["video_annotations"]:
        frame["image"] = {k: v.replace("P01_01", "P01_03") for k, v in frame["image"].items()}
    sources["P01_03.json"] = contact.encoded(d)
    buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(sources.pop("P01_01.zip"))) as old,
        zipfile.ZipFile(buf, "w") as new,
    ):
        for name in old.namelist():
            new.writestr(name.replace("P01_01", "P01_03"), old.read(name))
    sources["P01_03.zip"] = buf.getvalue()
    root = tmp_path / "second"
    root.mkdir()
    for name, raw in sources.items():
        (root / name).write_bytes(raw)
    monkeypatch.setattr(data, "SOURCES", tuple((k, contact._sha(v)) for k, v in sources.items()))
    return root, sources


def test_second_video_full_derivation_and_rgb_target_separation(tmp_path, monkeypatch):
    root, _ = second_sources(tmp_path, monkeypatch)
    batch = data.derive_component(root)
    assert batch["source_report"]["video"] == "P01_03"
    assert batch["source_report"]["frames"] == len(batch["inputs"]) == 5
    assert batch["summary"]["pixels"]["contact"]["0"] > 0
    assert batch["summary"]["pixels"]["contact"]["1"] > 0
    assert all(
        "contact" not in json.dumps(r) and "P01_03" not in json.dumps(r) for r, _ in batch["inputs"]
    )
    assert batch == data.derive_component(root)


@pytest.mark.parametrize("attack", ["label", "zip", "missing", "extra", "symlink", "hardlink"])
def test_second_source_boundary(tmp_path, monkeypatch, attack):
    root, _ = second_sources(tmp_path, monkeypatch)
    p = root / "P01_03.json"
    if attack == "label":
        d = json.loads(p.read_bytes())
        d["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
        p.write_bytes(contact.encoded(d))
    elif attack == "zip":
        (root / "P01_03.zip").write_bytes(b"forged")
    elif attack == "missing":
        p.unlink()
    elif attack == "extra":
        (root / "self-enrollment.json").write_bytes(b"{}")
    else:
        q = tmp_path / "external.json"
        q.write_bytes(p.read_bytes())
        p.unlink()
        if attack == "symlink":
            p.symlink_to(q)
        else:
            p.hardlink_to(q)
    with pytest.raises(ValueError):
        data.derive_component(root)


@pytest.mark.parametrize("field", ["rgb_sha256", "pixel_sha256"])
def test_cross_video_reencoding_overlap_rejected(field):
    a = {"rgb_sha256": "a", "pixel_sha256": "b"}
    b = {"rgb_sha256": "c", "pixel_sha256": "d"}
    data.require_disjoint([(a, b"")], [(b, b""), (b, b"")])
    b[field] = a[field]
    with pytest.raises(ValueError, match="overlap"):
        data.require_disjoint([(a, b"")], [(b, b""), (b, b"")])


def test_analytic_constant_uses_frame_average_not_pooled_pixels():
    t1 = torch.tensor([[[1, 255, 255, 255]], [[1, 1, 0, 0]]], dtype=torch.uint8)
    t2 = torch.tensor([[[0, 0, 0, 0]], [[1, 0, 0, 0]]], dtype=torch.uint8)
    head, p = control.analytic_constant([t1, t2])
    assert p == [0.5, 0.375]
    assert not head.weight.any() and not any(x.requires_grad for x in head.parameters())
    logits = head.bias[:, None, None].expand_as(t1).detach().clone().requires_grad_()
    loss = sum(control.masked_loss(logits, t)[0] for t in [t1, t2]) / 2
    loss.backward()
    assert torch.allclose(logits.grad.sum((1, 2)), torch.zeros(2), atol=1e-7)


def test_bias_updates_ignore_image_but_feature_updates_depend_on_it():
    f, t = tiny_training()
    changed = copy.deepcopy(f[0])
    changed["feature"] *= -2
    for arm in ["bias", "feature"]:
        a, b = control.new_head(arm), control.new_head(arm)
        ra = control.step_once(a, f[0], t[0])
        rb = control.step_once(b, changed, t[0])
        assert (ra["after"] == rb["after"]) == (arm == "bias")
        if arm == "bias":
            assert not a.weight.any() and a.weight.grad is None


def test_all_fixed_budgets_restore_full_outputs_and_next_update():
    torch.set_num_threads(2)
    f, t = tiny_training()
    heads, artifacts, report = control.train_controls(f[:8], t[:8])
    assert set(heads) == {"feature_16", "feature_128", "bias_16", "bias_128", "analytic_constant"}
    assert report["training_updates"] == 256 and report["verification_extra_updates"] == 8
    for arm in ("feature", "bias"):
        assert [r["ordinal"] for r in report["updates"][arm]] == list(range(8)) * 16
        assert all(
            r["gradient_norm"] > 0 and r["before"] != r["after"] for r in report["updates"][arm]
        )
    assert all(r["full_outputs_equal"] and r["next_update_equal"] for r in report["recovery"])
    for key, raw in artifacts.items():
        loaded = control.restore(raw, control.sha(raw))
        assert control.measure(loaded, f[0], t[0]) == control.measure(heads[key[:-5]], f[0], t[0])
    assert all(x["feature"].grad is None for x in f)


@pytest.mark.parametrize(
    "attack", ["arm", "shape", "nan", "budget", "bool_budget", "bias_weight", "config"]
)
def test_complete_checkpoint_internal_constraints_even_with_matching_digest(attack):
    d = json.loads(control.save_head(control.new_head("bias"), "bias", 16))
    if attack == "arm":
        d["arm"] = "unknown"
    if attack == "shape":
        d["weight"] = [0]
    if attack == "nan":
        d["bias"][0] = float("nan")
    if attack == "budget":
        d["step"] = 64
    if attack == "bool_budget":
        d["step"] = True
    if attack == "bias_weight":
        d["weight"][0][0][0][0] = 1
    if attack == "config":
        d["config"]["lr"] = 0.2
    raw = json.dumps(d).encode()
    with pytest.raises(ValueError):
        control.restore(raw, control.sha(raw))


def test_class_measurements_ignore_void_and_expose_missing_class():
    f, _ = tiny_training()
    target = torch.full((2, 4, 6), 255, dtype=torch.uint8)
    target[0, 0, 0] = 0
    target[0, 0, 1] = 1
    target[1, 1, 1] = 1
    row = control.measure(control.new_head("bias"), f[0], target)
    s = control.summarize([row, row])
    assert s["frames"] == 2
    assert s["axes"]["hand"]["positive_pixels"] == 2
    assert s["axes"]["contact"]["negative_pixels"] == 0
    assert s["axes"]["contact"]["negative_bce_equal_frame"] is None
    assert s["axes"]["hand"]["positive_bce_equal_frame"] == pytest.approx(0.69314718)
