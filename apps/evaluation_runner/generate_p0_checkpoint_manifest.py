#!/usr/bin/env python3
"""Generate the deterministic pre-data/LLM P0 content manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO / "benchmarks" / "p0_checkpoint" / "content_manifest_v0_2.json"


def _files(patterns: tuple[str, ...]) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in REPO.glob(pattern) if path.is_file())
    return tuple(sorted(paths, key=lambda item: item.relative_to(REPO).as_posix()))


def _digest(paths: tuple[Path, ...]) -> tuple[str, list[dict[str, str]]]:
    entries = []
    aggregate = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(REPO).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return aggregate.hexdigest(), entries


def build_manifest() -> dict[str, object]:
    scopes = {
        "code": _files(("src/**/*.py", "apps/**/*.py")),
        "config": _files(("configs/**/*.json", "configs/**/*.yaml", "configs/**/*.yml")),
        "data_schema": _files(
            (
                "src/cpswm/contracts/**/*.py",
                "src/cpswm/system/evaluation_operations/project_one_dataset.py",
                "src/cpswm/system/evaluation_operations/project_two_dataset.py",
                "src/cpswm/system/evaluation_operations/project_two_dataset_adapters.py",
            )
        ),
        "split_manifest": tuple(
            path
            for path in _files(("benchmarks/**/*.json", "configs/**/*.json"))
            if path != DEFAULT_OUTPUT
            and ("manifest" in path.name.lower() or "split" in path.name.lower())
        ),
    }
    payload: dict[str, object] = {
        "schema_version": "p0-checkpoint-content-manifest@0.2",
        "generated_for_date": "2026-09-05",
        "hash_algorithm": "sha256(path\\0file_sha256\\n)",
        "scopes": {},
    }
    scope_payload = {}
    for name, paths in scopes.items():
        digest, entries = _digest(paths)
        scope_payload[name] = {
            "content_sha256": digest,
            "file_count": len(entries),
            "files": entries,
        }
    payload["scopes"] = scope_payload
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def verify_manifest_snapshot(payload: dict[str, object]) -> None:
    """Verify a stored snapshot internally without comparing it to today's tree."""

    scopes = payload.get("scopes")
    if not isinstance(scopes, dict):
        raise ValueError("P0 manifest scopes are missing")
    for name, raw_scope in scopes.items():
        if not isinstance(raw_scope, dict) or not isinstance(raw_scope.get("files"), list):
            raise ValueError(f"P0 manifest scope is malformed: {name}")
        files = raw_scope["files"]
        aggregate = hashlib.sha256()
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError(f"P0 manifest entry is malformed: {name}")
            relative = entry.get("path")
            digest = entry.get("sha256")
            if not isinstance(relative, str) or not isinstance(digest, str):
                raise ValueError(f"P0 manifest entry fields are malformed: {name}")
            aggregate.update(relative.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(digest.encode("ascii"))
            aggregate.update(b"\n")
        if raw_scope.get("file_count") != len(files):
            raise ValueError(f"P0 manifest file count mismatch: {name}")
        if raw_scope.get("content_sha256") != aggregate.hexdigest():
            raise ValueError(f"P0 manifest scope hash mismatch: {name}")
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
