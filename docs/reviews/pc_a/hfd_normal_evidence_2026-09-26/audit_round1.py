"""First local audit: late file mutation must not publish a trustworthy packet."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_full_hfd_training import fixture_archive, npy  # noqa: E402

from cpswm.data_preflight import full_hfd_training as module  # noqa: E402


def test_late_extra_artifact_cannot_leave_an_acceptance_manifest(tmp_path, monkeypatch):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    original = module.build_report

    def changed(root, outcomes, *, write_rows):
        value = original(root, outcomes, write_rows=write_rows)
        (root / "unregistered-labels.jsonl").write_bytes(b"{}\n")
        return value

    monkeypatch.setattr(module, "build_report", changed)
    with pytest.raises(ValueError, match=r"artifact|packet"):
        module.inspect_full_training(archive, metadata, output)
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("verify", (False, True))
def test_mutation_after_initial_member_check_cannot_return_success(tmp_path, monkeypatch, verify):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    if verify:
        module.inspect_full_training(archive, metadata, output)
    original = module.build_report

    def changed(root, outcomes, *, write_rows):
        value = original(root, outcomes, write_rows=write_rows)
        (root / "raw/trial0000/human_activity.npy").write_bytes(npy(np.array([0, 3, 3])))
        return value

    monkeypatch.setattr(module, "build_report", changed)
    with pytest.raises(ValueError, match=r"member|source|packet|artifact"):
        module.inspect_full_training(archive, metadata, output, verify=verify)
    if not verify:
        assert not (output / "manifest.json").exists()


def test_packet_member_alias_cannot_escape_its_source_bound_directory(tmp_path, monkeypatch):
    archive, metadata, output = fixture_archive(tmp_path, monkeypatch)
    module.inspect_full_training(archive, metadata, output)
    source = output / "raw/trial0000/human_activity.npy"
    external = tmp_path / "mutable-external.npy"
    source.rename(external)
    source.symlink_to(external)
    with pytest.raises(ValueError, match=r"link|alias|packet"):
        module.inspect_full_training(archive, metadata, output, verify=True)
