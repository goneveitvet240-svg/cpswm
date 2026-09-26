"""Second A review: plausible forged positives, output consumers and lifecycle."""

import copy
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_visor_contact_supervision import fixture_sources  # noqa: E402

from cpswm.data_preflight import visor_contact_supervision as module  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402


def test_complete_plausible_forgery_passes_self_hashes_but_not_source_consumer(
    tmp_path, monkeypatch
):
    root, packet, source = fixture_sources(tmp_path, monkeypatch)
    module.prepare_contact_package(root, packet)
    forged = copy.deepcopy(source)
    doc = json.loads(forged["P01_01.json"])
    # Replace an unknown relation by a fully valid contact to an existing object.
    doc["video_annotations"][2]["annotations"][-1]["in_contact_object"] = "object"
    forged["P01_01.json"] = module.encoded(doc)
    full_forgery = module._derive(forged)
    manifest = json.loads(full_forgery["manifest.json"])
    assert manifest["report"]["binary_labeled_relations"] == 3
    for name, receipt in manifest["members"].items():
        assert module._sha(full_forgery[name]) == receipt["sha256"]
        assert len(full_forgery[name]) == receipt["bytes"]
    for name, raw in full_forgery.items():
        (packet / name).write_bytes(raw)
    # The public learning consumer must independently reconstruct actual labels.
    with pytest.raises(ValueError, match="recomputation"):
        module.load_contact_component(root, packet)
    for name, raw in module._derive(source).items():
        (packet / name).write_bytes(raw)
    assert len(module.load_contact_component(root, packet)["targets"]) == 4


def test_alternate_labels_cannot_leak_into_input_bytes(tmp_path, monkeypatch):
    _, _, source = fixture_sources(tmp_path, monkeypatch)
    original = module._derive(source)
    changed = copy.deepcopy(source)
    doc = json.loads(changed["P01_01.json"])
    doc["video_annotations"][0]["annotations"][-1]["in_contact_object"] = "hand-not-in-contact"
    changed["P01_01.json"] = module.encoded(doc)
    result = module._derive(changed)
    assert all(result[k] == v for k, v in original.items() if k.startswith("runtime/"))
    assert (
        result["supervision/contact_targets.json"] != original["supervision/contact_targets.json"]
    )


def test_verified_learning_read_returns_source_values_despite_postcheck_file_rewrite(
    tmp_path, monkeypatch
):
    root, packet, _ = fixture_sources(tmp_path, monkeypatch)
    module.prepare_contact_package(root, packet)
    real = module._verify_artifacts

    def aftercheck(output, artifacts):
        real(output, artifacts)
        rows = json.loads((output / "supervision/contact_targets.json").read_bytes())
        rows[0]["binary_contact_target"] = False
        (output / "supervision/contact_targets.json").write_bytes(module.encoded(rows))

    monkeypatch.setattr(module, "_verify_artifacts", aftercheck)
    loaded = module.load_contact_component(root, packet)
    assert loaded["targets"][0]["binary_contact_target"] is True
    with pytest.raises(ValueError):
        module.load_contact_component(root, packet)


def test_atomic_failure_leaves_no_success_and_legal_retry_works(tmp_path, monkeypatch):
    root, packet, _ = fixture_sources(tmp_path, monkeypatch)
    original = Path.write_bytes
    count = 0

    def fail(self, data):
        nonlocal count
        if any(p.startswith(".visor-staging-") for p in self.parts):
            count += 1
            if count == 2:
                raise OSError("injected disk failure")
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError, match="disk failure"):
        module.prepare_contact_package(root, packet)
    assert not packet.exists() and not list(tmp_path.glob(".visor-staging-*"))
    monkeypatch.setattr(Path, "write_bytes", original)
    assert module.prepare_contact_package(root, packet)["report"]["frames"] == 5


def test_duplicate_zip_is_not_a_valid_positive(tmp_path, monkeypatch):
    _, _, source = fixture_sources(tmp_path, monkeypatch)
    raw = io.BytesIO(source["P01_01.zip"])
    with zipfile.ZipFile(raw, "a") as archive:
        first = archive.namelist()[0]
        with pytest.warns(UserWarning):
            archive.writestr(first, archive.read(first))
    source["P01_01.zip"] = raw.getvalue()
    with pytest.raises(ValueError, match="duplicate"):
        module._derive(source)


def test_component_supervision_cannot_masquerade_as_full_native_proposal(tmp_path, monkeypatch):
    root, packet, _ = fixture_sources(tmp_path, monkeypatch)
    module.prepare_contact_package(root, packet)
    loaded = module.load_contact_component(root, packet)
    assert loaded["targets"][0]["binary_contact_target"] is True
    with pytest.raises(ValueError):
        ProposalSample.model_validate(loaded)
    for target in loaded["targets"]:
        with pytest.raises(ValueError):
            ProposalSample.model_validate(target)
    for key in (
        "action_authorized",
        "ledger_authorized",
        "native_publication_authorized",
        "full_proposal_training_ready",
        "exact_contact_release_gold",
        "person_identity_gold",
        "runtime_pose_noise_calibrated",
    ):
        assert loaded["report"][key] is False
    assert loaded["report"]["native_operation_labels"] == []
    assert loaded["report"]["new_optimizer_steps"] == 0


@pytest.mark.parametrize("change", ["late_alias", "late_mutation"])
def test_late_packet_change_is_not_verified(tmp_path, monkeypatch, change):
    root, packet, _ = fixture_sources(tmp_path, monkeypatch)
    module.prepare_contact_package(root, packet)
    real = module.packet_inventory
    n = 0

    def inventory(path):
        nonlocal n
        if path == packet:
            n += 1
            if n == 2:
                target = packet / "runtime/manifest.json"
                if change == "late_mutation":
                    target.write_bytes(b"{}")
                else:
                    raw = target.read_bytes()
                    outside = tmp_path / "aliased"
                    outside.write_bytes(raw)
                    target.unlink()
                    target.symlink_to(outside)
        return real(path)

    monkeypatch.setattr(module, "packet_inventory", inventory)
    with pytest.raises(ValueError):
        module.load_contact_component(root, packet)


def test_author_unsorted_records_keep_exact_all_frame_correspondence(tmp_path, monkeypatch):
    _, _, source = fixture_sources(tmp_path, monkeypatch)
    original = module._derive(source)
    changed = copy.deepcopy(source)
    doc = json.loads(changed["P01_01.json"])
    doc["video_annotations"] = list(reversed(doc["video_annotations"]))
    changed["P01_01.json"] = module.encoded(doc)
    result = module._derive(changed)
    for name, raw in original.items():
        if name != "manifest.json":
            assert result[name] == raw
    assert (
        json.loads(result["manifest.json"])["report"]
        == json.loads(original["manifest.json"])["report"]
    )
