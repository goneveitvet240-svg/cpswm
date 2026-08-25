#!/usr/bin/env python3
"""Generate the deterministic pre-data/LLM P0 content manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO / "benchmarks" / "p0_checkpoint" / "content_manifest_v0_1.json"


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
        "schema_version": "p0-checkpoint-content-manifest@0.1",
        "generated_for_date": "2026-08-25",
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
