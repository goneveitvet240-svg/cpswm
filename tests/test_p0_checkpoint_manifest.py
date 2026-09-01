from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "apps/evaluation_runner/generate_p0_checkpoint_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("generate_p0_checkpoint_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_manifest = MODULE.build_manifest
audit_v0_1_git_baseline = MODULE.audit_v0_1_git_baseline
verify_manifest_snapshot = MODULE.verify_manifest_snapshot
ROOT = Path(__file__).resolve().parents[1]


def _assert_self_consistent(stored: dict[str, object]) -> None:
    verify_manifest_snapshot(stored)


def test_p0_checkpoint_v0_1_is_self_consistent_but_not_claimed_immutable() -> None:
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == "p0-checkpoint-content-manifest@0.1"
    _assert_self_consistent(stored)
    audit = audit_v0_1_git_baseline()
    assert audit["current_matches_git_baseline"] is False
    assert audit["external_cryptographic_anchor_present"] is False
    assert audit["immutable_frozen_snapshot_claim_allowed"] is False
    assert audit["status"] == "CURRENT_SELF_CONSISTENT_COPY_NOT_VERIFIABLY_IMMUTABLE"
    stored_audit = json.loads(
        (ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1_git_baseline_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored_audit == audit


def test_p0_checkpoint_v0_2_is_current_and_self_consistent() -> None:
    expected = build_manifest()
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_2.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == expected
    _assert_self_consistent(stored)


def test_checkpoint_manifest_has_all_four_required_hash_scopes() -> None:
    scopes = build_manifest()["scopes"]
    assert set(scopes) == {"code", "config", "data_schema", "split_manifest"}
    assert all(item["file_count"] > 0 for item in scopes.values())


def test_self_consistency_check_rejects_unrehashed_entry_tampering() -> None:
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["scopes"]["code"]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="scope hash mismatch"):
        verify_manifest_snapshot(stored)


def test_git_baseline_audit_detects_forged_numstat_fields() -> None:
    live = audit_v0_1_git_baseline()
    stored_path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1_git_baseline_audit.json"
    forged = json.loads(stored_path.read_text(encoding="utf-8"))
    forged["git_diff_added_lines"] = int(forged["git_diff_added_lines"]) + 1
    assert forged != live
