"""First review: target meanings, isolation, real gradients and state restoration."""

import io
import json

import numpy as np
import pytest
import torch
from PIL import Image
from test_visor_contact_supervision import fixture_sources

from cpswm.data_preflight import visor_contact_supervision as source_module
from cpswm.data_preflight import visor_pixel_probe as probe
from cpswm.data_preflight import visor_pixel_supervision as pixel


def fixture_pixel(tmp_path, monkeypatch):
    def change(doc):
        for frame in doc["video_annotations"]:
            for entity in frame["annotations"]:
                if entity["name"] in source_module.HANDS:
                    entity["segments"] = [[[30, 0], [40, 0], [40, 10], [30, 10]]]

    source, contact, sources = fixture_sources(tmp_path, monkeypatch, mutate=change)
    source_module.prepare_contact_package(source, contact)
    output = tmp_path / "pixel"
    return source, contact, output, sources


def entity(name, x, contact=None):
    result = {"name": name, "segments": [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1]]]}
    if contact is not None:
        result["in_contact_object"] = contact
    return result


def test_target_axes_unknown_hand_still_positive_unannotated_stays_void():
    frame = {
        "annotations": [
            entity("cup", 0),
            entity("left hand", 3, "object"),
            entity("right hand", 6, "inconclusive"),
        ]
    }
    a, c = pixel.pixel_targets(frame, 10, 4)
    assert (a["hand"][:2, :2] == 0).all()
    assert (a["hand"][:2, 3:5] == 1).all() and (a["contact"][:2, 3:5] == 1).all()
    assert (a["hand"][:2, 6:8] == 1).all() and (a["contact"][:2, 6:8] == 255).all()
    assert (a["hand"][2:, :] == 255).all()
    assert c["pixels"]["contact"] == {"0": 0, "1": 4, "255": 36}


def test_conflicts_are_void_and_author_order_has_no_effect():
    entities = [
        entity("cup", 0),
        entity("left hand", 0, "object"),
        entity("right hand", 4, "hand-not-in-contact"),
        entity("left hand", 4, "object"),
        entity("right hand", 7, "inconclusive"),
        entity("left hand", 7, "object"),
    ]
    a, c = pixel.pixel_targets({"annotations": entities}, 10, 4)
    b, d = pixel.pixel_targets({"annotations": list(reversed(entities))}, 10, 4)
    assert c == d and all(np.array_equal(a[k], b[k]) for k in pixel.AXES)
    assert (a["hand"][:2, :2] == 255).all() and (a["contact"][:2, :2] == 255).all()
    assert (a["hand"][:2, 4:6] == 1).all() and (a["contact"][:2, 4:6] == 255).all()
    assert (a["contact"][:2, 7:9] == 255).all()


def test_full_source_packet_create_replay_and_consume(tmp_path, monkeypatch):
    source, contact, out, _ = fixture_pixel(tmp_path, monkeypatch)
    m = pixel.prepare(source, contact, out)
    assert m == pixel.prepare(source, contact, out, verify=True)
    assert m["summary"]["frames"] == 5 and m["summary"]["contact_supervised_frames"] == 2
    assert m["summary"]["hand_supervised_frames"] == 5
    batch = pixel.load_component(source, contact, out, count=5)
    assert len(batch["inputs"]) == len(batch["targets"]) == 5
    assert [set(t) for t in batch["targets"]] == [{"hand", "contact"}] * 5
    assert "in_contact_object" not in json.dumps([row for row, _ in batch["inputs"]])
    for i, t in enumerate(batch["targets"]):
        a = probe.labels_from_png(t)
        assert a.shape == (2, 1080, 1920)
        if i in (2, 3, 4):
            assert torch.all(a[1] == 255)
    with pytest.raises(ValueError):
        pixel.load_component(source, contact, out)
    with pytest.raises(FileExistsError):
        pixel.prepare(source, contact, out)


def test_masked_loss_matches_reference_and_void_has_zero_gradient():
    logits = torch.zeros((2, 2, 2), requires_grad=True)
    labels = torch.tensor([[[0, 1], [255, 255]], [[1, 255], [255, 255]]], dtype=torch.uint8)
    loss, s = probe.masked_loss(logits, labels)
    assert float(loss.detach()) == pytest.approx(2 * np.log(2))
    assert s["hand"]["pixels"] == 2 and s["contact"]["pixels"] == 1
    loss.backward()
    assert torch.equal(logits.grad[labels == 255], torch.zeros(5))
    assert logits.grad[0, 0, 0].item() == 0.25 and logits.grad[0, 0, 1].item() == -0.25
    assert logits.grad[1, 0, 0].item() == -0.5
    logits2 = torch.ones((2, 2, 2), requires_grad=True)
    loss, s = probe.masked_loss(logits2, torch.full((2, 2, 2), 255, dtype=torch.uint8))
    loss.backward()
    assert float(loss.detach()) == 0 and not torch.any(logits2.grad)
    assert all(r["loss"] is None for r in s.values())


@pytest.mark.parametrize("kind", ["shape", "label", "nan"])
def test_invalid_loss_inputs_rejected(kind):
    logits = torch.zeros((2, 2, 2))
    target = torch.zeros((2, 2, 2), dtype=torch.uint8)
    if kind == "shape":
        target = target[:1]
    elif kind == "label":
        target[0, 0, 0] = 2
    else:
        logits[0, 0, 0] = float("nan")
    with pytest.raises(ValueError):
        probe.masked_loss(logits, target)


def tiny_training():
    # Frozen 256-channel tensors; real torch optimizer and full numeric gradients.
    features = [
        {
            "feature": torch.tensor([[[[2.0, 1.0, -1.0], [2.0, 1.0, -1.0]]]])
            .expand(1, 256, 2, 3)
            .clone()
            * ((i + 1) / 100),
            "original": (4, 6),
            "padded": (4, 8),
            "resized": (4, 6),
        }
        for i in range(16)
    ]
    target = torch.tensor(
        [[[1, 1, 0, 0, 255, 255]] * 4, [[1, 0, 255, 255, 255, 255]] * 4], dtype=torch.uint8
    )
    return features, [target.clone() for _ in features]


def test_real_updates_complete_checkpoint_and_next_update_restore():
    torch.set_num_threads(2)
    features, targets = tiny_training()
    report, raw = probe.fit(features, targets, "a" * 64)
    assert report["optimizer_steps"] == 16
    assert all(e["gradient_norm"] > 0 and e["before"] != e["after"] for e in report["updates"])
    assert report["restored_full_outputs_equal"] and report["restored_next_update_equal"]
    assert report["after"] != report["before"]
    head = probe.restore_head(raw, probe.sha(raw))
    assert probe.measurements(head, features, targets) == report["after"]
    assert all(f["feature"].grad is None for f in features)


def test_unoptimized_neighbor_targets_cannot_change_training_weights():
    f, t = tiny_training()
    first, raw = probe.fit(f, t, "a" * 64)
    for labels in t[8:]:
        labels[labels != 255] = 1 - labels[labels != 255]
    second, changed = probe.fit(f, t, "a" * 64)
    assert raw == changed and first["updates"] == second["updates"]
    assert first["after"][8:] != second["after"][8:]


def test_transform_padding_is_cropped_before_original_resize():
    head = probe.head_new(1)
    with torch.no_grad():
        head.weight.fill_(1)
    feat = {
        "feature": torch.tensor([[[[1.0, 1.0, 100.0, 100.0], [1.0, 1.0, 100.0, 100.0]]]]),
        "padded": (2, 4),
        "resized": (2, 2),
        "original": (4, 4),
    }
    out = probe.logits_image(head, feat)
    assert out.shape == (2, 4, 4) and torch.all(out == 1)


def test_png_invalid_label_rejected():
    image = Image.fromarray(np.full((2, 2), 2, dtype=np.uint8))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    with pytest.raises(ValueError):
        probe.labels_from_png({"hand": buf.getvalue(), "contact": buf.getvalue()})
