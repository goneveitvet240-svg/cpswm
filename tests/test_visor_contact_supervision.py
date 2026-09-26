"""Source-bound contact component fixtures; no benchmark accuracy claims."""

import copy
import hashlib
import io
import json
import zipfile

import pytest
from PIL import Image

from cpswm.data_preflight import visor_contact_supervision as module


def fixture_sources(tmp_path, monkeypatch, mutate=None, zip_mutate=None):
    frames = []
    rgb = {}
    for i, contact in enumerate(("object", *module.SPECIAL, None)):
        name = f"P01_01_frame_{i + 1:010d}.jpg"
        entity = {
            "id": "object",
            "name": "cup",
            "class_id": 1,
            "exhaustive": "n",
            "segments": [[[0, 0], [20, 0], [20, 20]]],
        }
        entities = [entity]
        if contact is not None:
            entities.append(
                {
                    **copy.deepcopy(entity),
                    "id": "hand",
                    "name": "left hand",
                    "class_id": 300,
                    "in_contact_object": contact,
                }
            )
        frames.append(
            {
                "image": {
                    "name": name,
                    "image_path": "P01_01/" + name,
                    "video": "P01_01",
                    "subsequence": "P01_01_seq_00001",
                },
                "annotations": entities,
            }
        )
        image = Image.new("RGB", (1920, 1080), (i * 20, 10, 30))
        buf = io.BytesIO()
        image.save(buf, format="JPEG")
        rgb[name] = buf.getvalue()
    doc = {"info": {"Dataset Name": "VISOR"}, "video_annotations": frames}
    if mutate:
        mutate(doc)
    if zip_mutate:
        zip_mutate(rgb)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, raw in rgb.items():
            archive.writestr(name, raw)
    sources = {
        "P01_01.json": module.encoded(doc),
        "P01_01.zip": buf.getvalue(),
        "correct.json": b"{}",
        "README.txt": b"fixture only",
        "author_converter.py.txt": b"fixture only",
    }
    root = tmp_path / "source"
    root.mkdir()
    for name, raw in sources.items():
        (root / name).write_bytes(raw)
    # Trusted test-only sources; production CLI has no way to supply new pins.
    monkeypatch.setattr(
        module,
        "ENROLLED_SOURCES",
        tuple((k, hashlib.sha256(v).hexdigest()) for k, v in sources.items()),
    )
    return root, tmp_path / "packet", sources


def test_all_states_no_hand_and_rgb_only_lane_roundtrip(tmp_path, monkeypatch):
    root, output, _ = fixture_sources(tmp_path, monkeypatch)
    result = module.prepare_contact_package(root, output)
    assert result == module.prepare_contact_package(root, output, verify=True)
    loaded = module.load_contact_component(root, output)
    assert [t["binary_contact_target"] for t in loaded["targets"]] == [True, False, None, None]
    assert loaded["report"]["frames_without_annotated_hand"] == 1
    assert len(loaded["inputs"]) == 5
    assert loaded["targets"][0]["contact_segment_exhaustive"] == "n"
    for row in loaded["inputs"]:
        assert set(row) == {
            "key",
            "ordinal",
            "rgb",
            "rgb_sha256",
            "pixel_sha256",
            "width",
            "height",
        }
    assert {t["key"] for t in loaded["targets"]} < {r["key"] for r in loaded["inputs"]}
    assert not loaded["report"]["full_proposal_training_ready"]
    with pytest.raises(FileExistsError):
        module.prepare_contact_package(root, output)


@pytest.mark.parametrize(
    "attack",
    [
        "foreign_video",
        "duplicate_frame",
        "duplicate_mask",
        "dangling",
        "self_contact",
        "bool_contact",
        "missing_contact",
        "nan_polygon",
        "bool_class",
        "dense",
        "known_correction",
    ],
)
def test_malformed_annotation_rejected_before_output(tmp_path, monkeypatch, attack):
    def mutate(d):
        f = d["video_annotations"][0]
        e = f["annotations"][-1]
        if attack == "foreign_video":
            f["image"]["video"] = "P02_01"
        if attack == "duplicate_frame":
            d["video_annotations"][1] = copy.deepcopy(f)
        if attack == "duplicate_mask":
            f["annotations"].append(copy.deepcopy(e))
        if attack == "dangling":
            e["in_contact_object"] = "absent"
        if attack == "self_contact":
            e["in_contact_object"] = "hand"
        if attack == "bool_contact":
            e["in_contact_object"] = True
        if attack == "missing_contact":
            del e["in_contact_object"]
        if attack == "nan_polygon":
            e["segments"][0][0][0] = "NaN"
        if attack == "bool_class":
            e["class_id"] = True
        if attack == "dense":
            f["type"] = 0

    root, output, source = fixture_sources(tmp_path, monkeypatch, mutate=mutate)
    if attack == "known_correction":
        source["correct.json"] = b'{"P01_01_frame_0000000001.jpg":{"left hand":"object"}}'
        (root / "correct.json").write_bytes(source["correct.json"])
        monkeypatch.setattr(
            module, "ENROLLED_SOURCES", tuple((k, module._sha(v)) for k, v in source.items())
        )
    with pytest.raises(ValueError):
        module.prepare_contact_package(root, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".visor-staging-*"))


@pytest.mark.parametrize("attack", ["missing", "extra", "escape", "wrong_pixels"])
def test_zip_closure_and_actual_decoding(tmp_path, monkeypatch, attack):
    def mutate(rgb):
        key = next(iter(rgb))
        if attack == "missing":
            del rgb[key]
        if attack == "extra":
            rgb["P01_01/extra.jpg"] = rgb[key]
        if attack == "escape":
            rgb["../escaped.jpg"] = rgb.pop(key)
        if attack == "wrong_pixels":
            rgb[key] = b"not a jpeg"

    root, output, _ = fixture_sources(tmp_path, monkeypatch, zip_mutate=mutate)
    with pytest.raises((ValueError, OSError)):
        module.prepare_contact_package(root, output)
    assert not output.exists()


@pytest.mark.parametrize("attack", ["contact", "source", "authority", "omission", "rgb", "extra"])
def test_fully_resealed_pack_cannot_replace_frozen_author_evidence(tmp_path, monkeypatch, attack):
    root, output, _ = fixture_sources(tmp_path, monkeypatch)
    original = module.prepare_contact_package(root, output)
    saved = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    manifest = copy.deepcopy(original)
    if attack == "authority":
        manifest["report"]["native_publication_authorized"] = True
    elif attack == "source":
        manifest["sources"]["P01_01.json"] = "a" * 64
    elif attack == "extra":
        (output / "extra.json").write_bytes(b"{}")
    else:
        relative = "supervision/contact_targets.json"
        if attack == "rgb":
            paths = sorted(output.glob("runtime/frames/*"))
            relative = str(paths[0].relative_to(output))
            paths[0].write_bytes(paths[1].read_bytes())
        elif attack == "omission":
            (output / relative).unlink()
            del manifest["members"][relative]
        else:
            rows = json.loads((output / relative).read_bytes())
            rows[1]["binary_contact_target"] = True
            rows[1]["state"] = "author_contact_with_segment"
            rows[1]["contact_segment_id"] = "object"
            rows[1]["author_raw_contact"] = "object"
            rows[1]["contact_segment_name"] = "cup"
            (output / relative).write_bytes(module.encoded(rows))
        if (output / relative).exists():
            raw = (output / relative).read_bytes()
            manifest["members"][relative] = {"sha256": module._sha(raw), "bytes": len(raw)}
    (output / "manifest.json").write_bytes(module.encoded(manifest))
    with pytest.raises(ValueError):
        module.load_contact_component(root, output)
    for p in output.rglob("*"):
        if p.is_file() and str(p.relative_to(output)) not in saved:
            p.unlink()
    for name, raw in saved.items():
        (output / name).write_bytes(raw)
    assert module.prepare_contact_package(root, output, verify=True) == original


def test_source_forgery_cannot_be_enrolled_by_own_receipt(tmp_path, monkeypatch):
    root, output, _ = fixture_sources(tmp_path, monkeypatch)
    raw = (root / "P01_01.json").read_bytes()
    d = json.loads(raw)
    d["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    (root / "P01_01.json").write_bytes(module.encoded(d))
    (root / "self_enrollment.json").write_bytes(
        module.encoded({"P01_01.json": module._sha(module.encoded(d))})
    )
    with pytest.raises(ValueError, match="enrolled"):
        module.prepare_contact_package(root, output)
    assert not output.exists()
    (root / "P01_01.json").write_bytes(raw)
    assert module.prepare_contact_package(root, output)["report"]["frames"] == 5


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_packet_aliases_not_accepted(tmp_path, monkeypatch, alias):
    root, output, _ = fixture_sources(tmp_path, monkeypatch)
    module.prepare_contact_package(root, output)
    path = output / "supervision/contact_targets.json"
    external = tmp_path / "external"
    external.write_bytes(path.read_bytes())
    path.unlink()
    if alias == "symlink":
        path.symlink_to(external)
    else:
        path.hardlink_to(external)
    with pytest.raises(ValueError):
        module.load_contact_component(root, output)


def test_dangling_output_symlink_is_not_replaced(tmp_path, monkeypatch):
    root, output, _ = fixture_sources(tmp_path, monkeypatch)
    output.symlink_to(tmp_path / "missing-destination", target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        module.prepare_contact_package(root, output)
    assert output.is_symlink()
    assert not (tmp_path / "missing-destination").exists()
