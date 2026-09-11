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


def _write(path: Path, value: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _minimal_repository(root: Path) -> Path:
    _write(root / "pyproject.toml", "[project]\nname='fixture'\nversion='0'\n")
    _write(root / "uv.lock", "version = 1\n")
    _write(root / ".python-version", "3.13\n")
    _write(root / "src/package.py")
    _write(root / "apps/runner.py")
    _write(root / "configs/config.json", "{}\n")
    _write(root / "tests/test_unit.py", "def test_ok():\n    assert True\n")
    _write(root / "benchmarks/stable_fixture.json", '{"ok": true}\n')
    for relative in MODULE.LEGACY_TEST_FIXTURE_PATHS:
        _write(root / relative, (ROOT / relative).read_text())
    return root


def _scope(payload: dict[str, object], name: str) -> dict[str, object]:
    scopes = payload["scopes"]
    assert isinstance(scopes, dict)
    scope = scopes[name]
    assert isinstance(scope, dict)
    return scope


def test_p0_checkpoint_v0_1_is_self_consistent_but_not_claimed_immutable() -> None:
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == "p0-checkpoint-content-manifest@0.1"
    _assert_self_consistent(stored)
    audit = audit_v0_1_git_baseline()
    assert audit["current_matches_git_baseline"] is True
    assert audit["external_cryptographic_anchor_present"] is False
    assert audit["immutable_frozen_snapshot_claim_allowed"] is False
    assert audit["status"] == "CURRENT_SELF_CONSISTENT_COPY_NOT_VERIFIABLY_IMMUTABLE"
    stored_audit = json.loads(
        (ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1_git_baseline_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored_audit == audit


def test_historical_p0_checkpoint_v0_2_remains_self_consistent() -> None:
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_2.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == "p0-checkpoint-content-manifest@0.2"
    _assert_self_consistent(stored)


def test_p0_checkpoint_v0_3_is_current_and_self_consistent() -> None:
    expected = build_manifest()
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == expected
    _assert_self_consistent(stored)


def test_checkpoint_manifest_has_all_seven_required_hash_scopes() -> None:
    scopes = build_manifest()["scopes"]
    assert isinstance(scopes, dict)
    assert set(scopes) == {
        "code",
        "config",
        "data_schema",
        "split_manifest",
        "test_contract",
        "test_fixture_contract",
        "toolchain_contract",
    }
    assert all(item["file_count"] > 0 for item in scopes.values())


def test_test_contract_covers_code_and_structured_fixtures(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    _write(root / "conftest.py", "pytest_plugins = ()\n")
    _write(root / "tests/cases/input.json", "{}\n")
    _write(root / "tests/cases/events.jsonl", '{"event": 1}\n')
    payload = build_manifest(repository_root=root)
    files = {row["path"] for row in _scope(payload, "test_contract")["files"]}
    assert files == {
        "conftest.py",
        "tests/cases/events.jsonl",
        "tests/cases/input.json",
        "tests/test_unit.py",
    }


def test_test_contract_detects_fixture_add_modify_and_delete(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    baseline = build_manifest(repository_root=root)
    fixture = root / "tests/fixture.json"
    _write(fixture, '{"version": 1}\n')
    added = build_manifest(repository_root=root)
    _write(fixture, '{"version": 2}\n')
    modified = build_manifest(repository_root=root)
    fixture.unlink()
    deleted = build_manifest(repository_root=root)
    baseline_scope = _scope(baseline, "test_contract")
    added_scope = _scope(added, "test_contract")
    modified_scope = _scope(modified, "test_contract")
    assert added_scope["file_count"] == int(baseline_scope["file_count"]) + 1
    assert added_scope["content_sha256"] != baseline_scope["content_sha256"]
    assert modified_scope["content_sha256"] != added_scope["content_sha256"]
    assert deleted == baseline


def test_test_contract_excludes_caches_and_compiled_python(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    baseline = build_manifest(repository_root=root)
    _write(root / "tests/__pycache__/test_unit.cpython-313.pyc", "compiled")
    _write(root / "tests/.pytest_cache/v/cache/nodeids", "[]\n")
    _write(root / "tests/orphan.pyc", "compiled")
    _write(root / "tests/orphan.pyo", "compiled")
    assert build_manifest(repository_root=root) == baseline


def test_test_contract_rejects_symlink(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    target = root / "outside.py"
    _write(target)
    (root / "tests/linked.py").symlink_to(target)
    with pytest.raises(ValueError, match="test contract refuses symlink"):
        build_manifest(repository_root=root)


def test_test_contract_rejects_root_conftest_symlink(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    (root / "conftest.py").symlink_to(root / "tests/conftest.py")
    with pytest.raises(ValueError, match=r"test contract refuses symlink: conftest\.py"):
        build_manifest(repository_root=root)


def test_test_fixture_contract_detects_add_modify_and_delete(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    baseline = build_manifest(repository_root=root)
    fixture = root / "benchmarks/cases/expected.json"
    _write(fixture, '{"version": 1}\n')
    added = build_manifest(repository_root=root)
    _write(fixture, '{"version": 2}\n')
    modified = build_manifest(repository_root=root)
    fixture.unlink()
    deleted = build_manifest(repository_root=root)
    baseline_scope = _scope(baseline, "test_fixture_contract")
    added_scope = _scope(added, "test_fixture_contract")
    modified_scope = _scope(modified, "test_fixture_contract")
    assert added_scope["file_count"] == int(baseline_scope["file_count"]) + 1
    assert added_scope["content_sha256"] != baseline_scope["content_sha256"]
    assert modified_scope["content_sha256"] != added_scope["content_sha256"]
    assert deleted == baseline


def test_test_fixture_contract_excludes_cycles_and_defers_manifests_to_split_scope(
    tmp_path: Path,
) -> None:
    root = _minimal_repository(tmp_path)
    _write(root / "benchmarks/cases/frozen_split.json", '{"split": [1]}\n')
    for relative in MODULE.TEST_FIXTURE_EXCLUDED_PATHS:
        _write(root / relative, '{"excluded": true}\n')
    _write(
        root / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
        "engineering_audit_logs/fake.json",
        '{"excluded": true}\n',
    )
    payload = build_manifest(repository_root=root)
    fixture_files = {row["path"] for row in _scope(payload, "test_fixture_contract")["files"]}
    split_files = {row["path"] for row in _scope(payload, "split_manifest")["files"]}
    assert fixture_files == {
        "benchmarks/stable_fixture.json",
        *(path.as_posix() for path in MODULE.LEGACY_TEST_FIXTURE_PATHS),
    }
    assert "benchmarks/cases/frozen_split.json" in split_files
    assert not fixture_files & split_files
    assert (
        not {relative.as_posix() for relative in MODULE.TEST_FIXTURE_EXCLUDED_PATHS} & fixture_files
    )


def test_test_fixture_contract_rejects_file_and_directory_symlinks(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    outside = root / "outside"
    _write(outside / "payload.json", '{"outside": true}\n')
    (root / "benchmarks/linked.json").symlink_to(outside / "payload.json")
    with pytest.raises(ValueError, match="manifest scope refuses symlink"):
        build_manifest(repository_root=root)
    (root / "benchmarks/linked.json").unlink()
    (root / "benchmarks/linked-directory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="test fixture contract refuses symlink"):
        build_manifest(repository_root=root)


def test_every_non_circular_benchmark_json_is_in_split_or_fixture_scope() -> None:
    payload = build_manifest(repository_root=ROOT)
    covered = {
        row["path"]
        for scope_name in ("split_manifest", "test_fixture_contract")
        for row in _scope(payload, scope_name)["files"]
        if row["path"].startswith("benchmarks/")
    }
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "benchmarks").rglob("*.json")
        if path.relative_to(ROOT) not in MODULE.TEST_FIXTURE_EXCLUDED_PATHS
        and not any(
            part in MODULE.TEST_FIXTURE_EXCLUDED_DIRECTORIES
            for part in path.relative_to(ROOT).parts
        )
    }
    assert covered == expected


def test_v0_3_self_consistency_rejects_fixture_reclassified_as_circular() -> None:
    stored = build_manifest()
    fixture_files = stored["scopes"]["test_fixture_contract"]["files"]
    assert fixture_files
    fixture_files[0]["path"] = next(iter(MODULE.TEST_FIXTURE_EXCLUDED_PATHS)).as_posix()
    with pytest.raises(ValueError, match="test fixture contract entry violates"):
        verify_manifest_snapshot(stored)


def test_toolchain_contract_detects_edit_and_optional_file_addition(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    baseline = build_manifest(repository_root=root)
    _write(root / "pyproject.toml", "[project]\nname='changed'\nversion='0'\n")
    edited = build_manifest(repository_root=root)
    _write(root / "ruff.toml", "line-length = 100\n")
    optional_added = build_manifest(repository_root=root)
    baseline_scope = _scope(baseline, "toolchain_contract")
    edited_scope = _scope(edited, "toolchain_contract")
    optional_scope = _scope(optional_added, "toolchain_contract")
    assert edited_scope["content_sha256"] != baseline_scope["content_sha256"]
    assert optional_scope["file_count"] == int(edited_scope["file_count"]) + 1
    assert optional_scope["content_sha256"] != edited_scope["content_sha256"]


def test_toolchain_contract_rejects_missing_required_file(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    (root / "uv.lock").unlink()
    with pytest.raises(ValueError, match=r"required toolchain file is missing: uv\.lock"):
        build_manifest(repository_root=root)


def test_toolchain_contract_rejects_symlink(tmp_path: Path) -> None:
    root = _minimal_repository(tmp_path)
    (root / ".python-version").unlink()
    (root / ".python-version").symlink_to(root / "uv.lock")
    with pytest.raises(ValueError, match="toolchain contract refuses symlink"):
        build_manifest(repository_root=root)


def test_self_consistency_check_rejects_unrehashed_entry_tampering() -> None:
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["scopes"]["code"]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="scope hash mismatch"):
        verify_manifest_snapshot(stored)


def test_v0_3_self_consistency_rejects_unsafe_or_unsorted_paths() -> None:
    stored = build_manifest()
    test_files = stored["scopes"]["test_contract"]["files"]
    assert test_files
    test_files[0]["path"] = "../outside.py"
    with pytest.raises(ValueError, match="entry path is unsafe"):
        verify_manifest_snapshot(stored)


def test_git_baseline_audit_detects_forged_numstat_fields() -> None:
    live = audit_v0_1_git_baseline()
    stored_path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_1_git_baseline_audit.json"
    forged = json.loads(stored_path.read_text(encoding="utf-8"))
    forged["git_diff_added_lines"] = int(forged["git_diff_added_lines"]) + 1
    assert forged != live


@pytest.mark.parametrize("fixture_index", [0, 5, 16])
def test_required_legacy_fixtures_are_pinned_and_cannot_be_missing(
    tmp_path: Path, fixture_index: int
) -> None:
    root = _minimal_repository(tmp_path)
    payload = build_manifest(root)
    verify_manifest_snapshot(payload)
    included = {
        row["path"]: row["sha256"] for row in _scope(payload, "test_fixture_contract")["files"]
    }
    for path, digest in MODULE.LEGACY_TEST_FIXTURE_HASHES.items():
        assert included[path.as_posix()] == digest
    path = root / MODULE.LEGACY_TEST_FIXTURE_PATHS[fixture_index]
    path.write_text("{}\n")
    with pytest.raises(ValueError, match="differs from historical pinned"):
        build_manifest(root)
    path.unlink()
    with pytest.raises(ValueError, match="required legacy test fixture is missing"):
        build_manifest(root)
