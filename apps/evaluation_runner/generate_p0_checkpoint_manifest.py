#!/usr/bin/env python3
"""Generate the deterministic pre-data/LLM P0 content manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Final

REPO: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_RELATIVE: Final = Path("benchmarks/p0_checkpoint/content_manifest_v0_3.json")
DEFAULT_OUTPUT: Final = REPO / DEFAULT_OUTPUT_RELATIVE
SCHEMA_VERSION: Final = "p0-checkpoint-content-manifest@0.3"
REQUIRED_SCOPE_NAMES: Final = frozenset(
    {
        "code",
        "config",
        "data_schema",
        "split_manifest",
        "test_contract",
        "test_fixture_contract",
        "toolchain_contract",
    }
)
TEST_CACHE_DIRECTORIES: Final = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis"}
)
TEST_COMPILED_SUFFIXES: Final = frozenset({".pyc", ".pyo"})
REQUIRED_TOOLCHAIN_FILES: Final = ("pyproject.toml", "uv.lock", ".python-version")
OPTIONAL_TOOLCHAIN_FILES: Final = (
    "pytest.ini",
    "pytest.toml",
    "mypy.ini",
    ".mypy.ini",
    "ruff.toml",
    ".ruff.toml",
    "tox.ini",
    "setup.cfg",
    "setup.py",
    ".coveragerc",
)
TEST_FIXTURE_EXCLUDED_DIRECTORIES: Final = frozenset({"engineering_audit_logs"})
TEST_FIXTURE_EXCLUDED_PATHS: Final = frozenset(
    {
        DEFAULT_OUTPUT_RELATIVE,
        Path(
            "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
            "engineering_audit_receipt.json"
        ),
        Path(
            "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
            "engineering_checkpoint.json"
        ),
    }
)


def _normalise_root(repository_root: Path | None) -> Path:
    root = (REPO if repository_root is None else repository_root).resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")
    return root


def _files(root: Path, patterns: tuple[str, ...]) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_symlink():
                raise ValueError(f"manifest scope refuses symlink: {path.relative_to(root)}")
            if path.is_file():
                paths.add(path)
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _test_contract_files(root: Path) -> tuple[Path, ...]:
    """Inventory pytest tests, fixtures, and repository-root discovery hooks."""

    test_root = root / "tests"
    if not test_root.is_dir() or test_root.is_symlink():
        raise ValueError("tests must be a real directory for the test contract")
    paths: list[Path] = []
    for path in test_root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"test contract refuses symlink: {relative.as_posix()}")
        if any(part in TEST_CACHE_DIRECTORIES for part in relative.parts):
            continue
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"test contract refuses non-regular file: {relative.as_posix()}")
        if path.suffix.casefold() in TEST_COMPILED_SUFFIXES:
            continue
        paths.append(path)
    root_conftest = root / "conftest.py"
    if root_conftest.is_symlink():
        raise ValueError("test contract refuses symlink: conftest.py")
    if root_conftest.exists():
        mode = root_conftest.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError("test contract refuses non-regular file: conftest.py")
        paths.append(root_conftest)
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _toolchain_contract_files(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for relative_string in (*REQUIRED_TOOLCHAIN_FILES, *OPTIONAL_TOOLCHAIN_FILES):
        path = root / relative_string
        if path.is_symlink():
            raise ValueError(f"toolchain contract refuses symlink: {relative_string}")
        if path.exists():
            mode = path.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"toolchain contract requires regular file: {relative_string}")
            paths.append(path)
        elif relative_string in REQUIRED_TOOLCHAIN_FILES:
            raise ValueError(f"required toolchain file is missing: {relative_string}")
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _test_fixture_contract_files(
    root: Path, *, split_manifest_paths: tuple[Path, ...]
) -> tuple[Path, ...]:
    """Inventory stable benchmark JSON consumed as test fixtures.

    Manifest/split documents already belong to ``split_manifest``. The current
    P0 manifest and its downstream receipt/checkpoint are deliberately excluded
    to avoid a self-referential hash cycle.
    """

    benchmark_root = root / "benchmarks"
    if not benchmark_root.is_dir() or benchmark_root.is_symlink():
        raise ValueError("benchmarks must be a real directory for the test fixture contract")
    split_paths = set(split_manifest_paths)
    paths: list[Path] = []
    for path in benchmark_root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"test fixture contract refuses symlink: {relative.as_posix()}")
        if any(part in TEST_FIXTURE_EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            continue
        if path.suffix.casefold() != ".json":
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(
                f"test fixture contract refuses non-regular JSON: {relative.as_posix()}"
            )
        if relative in TEST_FIXTURE_EXCLUDED_PATHS or path in split_paths:
            continue
        paths.append(path)
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _digest(root: Path, paths: tuple[Path, ...]) -> tuple[str, list[dict[str, str]]]:
    entries = []
    aggregate = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return aggregate.hexdigest(), entries


def build_manifest_scope_contract() -> dict[str, object]:
    return {
        "test_contract": {
            "roots": ["tests", "conftest.py if present"],
            "included": "all regular test/fixture files and root pytest discovery hook",
            "excluded_cache_directories": sorted(TEST_CACHE_DIRECTORIES),
            "excluded_compiled_suffixes": sorted(TEST_COMPILED_SUFFIXES),
            "symlink_policy": "REJECT",
        },
        "test_fixture_contract": {
            "root": "benchmarks",
            "included": ("all regular benchmark JSON not already covered by split_manifest"),
            "excluded_directories": sorted(TEST_FIXTURE_EXCLUDED_DIRECTORIES),
            "excluded_circular_paths": sorted(
                path.as_posix() for path in TEST_FIXTURE_EXCLUDED_PATHS
            ),
            "symlink_policy": "REJECT",
        },
        "toolchain_contract": {
            "required_files": list(REQUIRED_TOOLCHAIN_FILES),
            "optional_files_if_present": list(OPTIONAL_TOOLCHAIN_FILES),
            "symlink_policy": "REJECT",
        },
    }


def build_manifest(repository_root: Path | None = None) -> dict[str, object]:
    root = _normalise_root(repository_root)
    split_manifest_paths = tuple(
        path
        for path in _files(root, ("benchmarks/**/*.json", "configs/**/*.json"))
        if path.relative_to(root) != DEFAULT_OUTPUT_RELATIVE
        and ("manifest" in path.name.lower() or "split" in path.name.lower())
    )
    scopes = {
        "code": _files(root, ("src/**/*.py", "apps/**/*.py")),
        "config": _files(root, ("configs/**/*.json", "configs/**/*.yaml", "configs/**/*.yml")),
        "data_schema": _files(
            root,
            (
                "src/cpswm/contracts/**/*.py",
                "src/cpswm/system/evaluation_operations/project_one_dataset.py",
                "src/cpswm/system/evaluation_operations/project_two_dataset.py",
                "src/cpswm/system/evaluation_operations/project_two_dataset_adapters.py",
            ),
        ),
        "split_manifest": split_manifest_paths,
        "test_fixture_contract": _test_fixture_contract_files(
            root,
            split_manifest_paths=split_manifest_paths,
        ),
        "test_contract": _test_contract_files(root),
        "toolchain_contract": _toolchain_contract_files(root),
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_for_date": "2026-09-10",
        "hash_algorithm": "sha256(path\\0file_sha256\\n)",
        "scope_contract": build_manifest_scope_contract(),
        "scopes": {},
    }
    scope_payload = {}
    for name, paths in scopes.items():
        digest, entries = _digest(root, paths)
        scope_payload[name] = {
            "content_sha256": digest,
            "file_count": len(entries),
            "files": entries,
        }
    payload["scopes"] = scope_payload
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _safe_manifest_path(value: object, *, scope_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"P0 manifest entry path is malformed: {scope_name}")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"P0 manifest entry path is unsafe: {scope_name}")
    return value


def verify_manifest_snapshot(payload: dict[str, object]) -> None:
    """Verify a stored snapshot internally without comparing it to today's tree."""

    schema_version = payload.get("schema_version")
    if schema_version not in {
        "p0-checkpoint-content-manifest@0.1",
        "p0-checkpoint-content-manifest@0.2",
        SCHEMA_VERSION,
    }:
        raise ValueError("P0 manifest schema version is unsupported")
    scopes = payload.get("scopes")
    if not isinstance(scopes, dict):
        raise ValueError("P0 manifest scopes are missing")
    if schema_version == SCHEMA_VERSION:
        if set(scopes) != REQUIRED_SCOPE_NAMES:
            raise ValueError("P0 v0.3 manifest scope coverage mismatch")
        if payload.get("scope_contract") != build_manifest_scope_contract():
            raise ValueError("P0 v0.3 scope contract mismatch")
    for name, raw_scope in scopes.items():
        if not isinstance(name, str):
            raise ValueError("P0 manifest scope name is malformed")
        if not isinstance(raw_scope, dict) or not isinstance(raw_scope.get("files"), list):
            raise ValueError(f"P0 manifest scope is malformed: {name}")
        files = raw_scope["files"]
        aggregate = hashlib.sha256()
        previous_path: str | None = None
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError(f"P0 manifest entry is malformed: {name}")
            relative = _safe_manifest_path(entry.get("path"), scope_name=name)
            digest = entry.get("sha256")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError(f"P0 manifest entry digest is malformed: {name}")
            if previous_path is not None and relative <= previous_path:
                raise ValueError(f"P0 manifest entries are duplicated or unsorted: {name}")
            previous_path = relative
            if schema_version == SCHEMA_VERSION and name == "test_contract":
                relative_path = PurePosixPath(relative)
                if (
                    not relative_path.parts
                    or (relative != "conftest.py" and relative_path.parts[0] != "tests")
                    or any(part in TEST_CACHE_DIRECTORIES for part in relative_path.parts)
                    or relative_path.suffix.casefold() in TEST_COMPILED_SUFFIXES
                ):
                    raise ValueError("P0 v0.3 test contract entry violates its declared scope")
            if schema_version == SCHEMA_VERSION and name == "test_fixture_contract":
                relative_path = PurePosixPath(relative)
                if (
                    not relative_path.parts
                    or relative_path.parts[0] != "benchmarks"
                    or relative_path.suffix.casefold() != ".json"
                    or any(
                        part in TEST_FIXTURE_EXCLUDED_DIRECTORIES for part in relative_path.parts
                    )
                    or Path(relative) in TEST_FIXTURE_EXCLUDED_PATHS
                    or "manifest" in relative_path.name.casefold()
                    or "split" in relative_path.name.casefold()
                ):
                    raise ValueError(
                        "P0 v0.3 test fixture contract entry violates its declared scope"
                    )
            if schema_version == SCHEMA_VERSION and name == "toolchain_contract":
                allowed = {*REQUIRED_TOOLCHAIN_FILES, *OPTIONAL_TOOLCHAIN_FILES}
                if relative not in allowed:
                    raise ValueError("P0 v0.3 toolchain entry violates its declared scope")
            aggregate.update(relative.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(digest.encode("ascii"))
            aggregate.update(b"\n")
        if raw_scope.get("file_count") != len(files):
            raise ValueError(f"P0 manifest file count mismatch: {name}")
        if raw_scope.get("content_sha256") != aggregate.hexdigest():
            raise ValueError(f"P0 manifest scope hash mismatch: {name}")
        if schema_version == SCHEMA_VERSION and name == "toolchain_contract":
            included = {entry["path"] for entry in files}
            if not set(REQUIRED_TOOLCHAIN_FILES).issubset(included):
                raise ValueError("P0 v0.3 toolchain contract omits a required file")
    if schema_version == SCHEMA_VERSION:
        split_files = {entry["path"] for entry in scopes["split_manifest"]["files"]}
        fixture_files = {entry["path"] for entry in scopes["test_fixture_contract"]["files"]}
        if split_files & fixture_files:
            raise ValueError("P0 v0.3 split and test fixture scopes overlap")
    stored_hash = payload.get("manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if stored_hash != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        raise ValueError("P0 manifest hash mismatch")


def audit_v0_1_git_baseline() -> dict[str, object]:
    """Report Git drift without upgrading a self-hash into immutability evidence."""

    relative = "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    current = (REPO / relative).read_bytes()
    baseline = subprocess.run(
        ("git", "show", f"HEAD:{relative}"),
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    current_hash = hashlib.sha256(current).hexdigest()
    baseline_hash = hashlib.sha256(baseline).hexdigest()
    matches = current_hash == baseline_hash
    numstat = subprocess.run(
        ("git", "diff", "--numstat", "HEAD", "--", relative),
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if matches:
        if numstat:
            raise ValueError("P0 v0.1 Git hashes match but numstat reports drift")
        added_lines = deleted_lines = 0
    else:
        rows = numstat.splitlines()
        if len(rows) != 1:
            raise ValueError("P0 v0.1 Git numstat must contain exactly one changed file")
        added, deleted, changed_path = rows[0].split("\t", maxsplit=2)
        if changed_path != relative or not added.isdigit() or not deleted.isdigit():
            raise ValueError("P0 v0.1 Git numstat is malformed or binary")
        added_lines = int(added)
        deleted_lines = int(deleted)
    return {
        "protocol": "p0-checkpoint-v0.1-git-baseline-audit@0.1",
        "git_reference": f"HEAD:{relative}",
        "git_baseline_file_sha256": baseline_hash,
        "current_file_sha256": current_hash,
        "current_matches_git_baseline": matches,
        "git_diff_added_lines": added_lines,
        "git_diff_deleted_lines": deleted_lines,
        "external_cryptographic_anchor_present": False,
        "immutable_frozen_snapshot_claim_allowed": False,
        "status": "CURRENT_SELF_CONSISTENT_COPY_NOT_VERIFIABLY_IMMUTABLE",
        "claim_boundary": (
            "Internal SHA-256 consistency detects accidental corruption only. It does "
            "not prove immutability because an attacker can rewrite the file and "
            "recompute every unkeyed hash."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(payload["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
