#!/usr/bin/env python3
"""Collect reproducible, non-secret metadata for the W3 PC-B repair run.

The output path is intentionally mandatory.  Repository revisions, interpreter
details, imports, dependencies, file digests, Git state, and line-ending
settings are measured at execution time; no tested revision is embedded here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_MODULES = (
    "cpswm",
    "cpswm.system.prototype_spine",
    "cpswm.system.structure_two_particle_workspace",
    "pytest",
)

DEFAULT_FILES = (
    "src/cpswm/system/prototype_spine.py",
    "src/cpswm/system/structure_two_particle_workspace.py",
    "tests/test_structure_two_w3_r6_pc_b_review.py",
    "tests/dual_pc_review/test_w3_five_boundaries_repair.py",
    "docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/collect_repair_metadata.py",
)

# Deliberately small and immutable: never serialize os.environ wholesale.
ENVIRONMENT_VALUE_ALLOWLIST = (
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_SHA",
    "PYTHONHASHSEED",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "SOURCE_DATE_EPOCH",
    "TZ",
)

GIT_EOL_CONFIG_KEYS = (
    "core.autocrlf",
    "core.eol",
    "core.safecrlf",
    "core.attributesfile",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def decode_output(payload: bytes) -> str:
    return payload.decode("utf-8", errors="backslashreplace")


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    include_stdout: bool = True,
) -> tuple[dict[str, Any], bytes]:
    """Run a command without a shell and retain failures as evidence."""

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return (
            {
                "command": list(command),
                "cwd": str(cwd),
                "ok": False,
                "returncode": None,
                "duration_seconds": round(time.perf_counter() - started, 6),
                "stdout_byte_count": 0,
                "stdout_sha256": sha256_bytes(b""),
                "stderr": f"{type(exc).__name__}: {exc}",
            },
            b"",
        )

    stdout = completed.stdout
    stderr = completed.stderr
    result: dict[str, Any] = {
        "command": list(command),
        "cwd": str(cwd),
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "stdout_byte_count": len(stdout),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr": decode_output(stderr).rstrip("\r\n"),
    }
    if include_stdout:
        result["stdout"] = decode_output(stdout).rstrip("\r\n")
    return result, stdout


def default_repository_root() -> Path:
    # .../docs/reviews/pc_b/<review>/collector.py -> repository root
    return Path(__file__).resolve().parents[4]


def discover_repository_root(candidate: Path) -> tuple[Path, dict[str, Any]]:
    candidate = candidate.resolve()
    result, stdout = run_command(
        ("git", "rev-parse", "--show-toplevel"), cwd=candidate
    )
    if result["ok"]:
        rendered = decode_output(stdout).strip()
        if rendered:
            return Path(rendered).resolve(), result
    return candidate, result


def file_summary(path: Path, *, repo_root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
    }
    if not path.is_file():
        summary["error"] = "file does not exist or is not a regular file"
        return summary

    try:
        payload = path.read_bytes()
    except OSError as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        return summary

    crlf_count = payload.count(b"\r\n")
    all_lf_count = payload.count(b"\n")
    all_cr_count = payload.count(b"\r")
    summary.update(
        {
            "size_bytes": len(payload),
            "sha256": sha256_bytes(payload),
            "line_endings": {
                "crlf": crlf_count,
                "lf_without_preceding_cr": all_lf_count - crlf_count,
                "cr_without_following_lf": all_cr_count - crlf_count,
            },
        }
    )

    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        summary["repository_relative_path"] = None
        return summary

    relative_text = relative.as_posix()
    summary["repository_relative_path"] = relative_text
    tracked, _ = run_command(
        ("git", "ls-files", "--error-unmatch", "--", relative_text),
        cwd=repo_root,
    )
    summary["git_tracked"] = tracked
    raw_blob, _ = run_command(
        ("git", "hash-object", "--no-filters", "--", relative_text),
        cwd=repo_root,
    )
    filtered_blob, _ = run_command(
        ("git", "hash-object", "--", relative_text), cwd=repo_root
    )
    summary["git_raw_blob"] = raw_blob
    summary["git_filtered_blob"] = filtered_blob
    return summary


def import_summary(module_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"module": module_name}
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception as exc:
        result["resolution"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    else:
        result["resolution"] = {
            "ok": spec is not None,
            "origin": getattr(spec, "origin", None),
            "loader": type(spec.loader).__name__ if spec and spec.loader else None,
            "submodule_search_locations": (
                [str(path) for path in spec.submodule_search_locations]
                if spec and spec.submodule_search_locations is not None
                else None
            ),
            "error": None if spec is not None else "no import specification found",
        }
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # Import failures are evidence, not fabricated success.
        result.update(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return result

    module_file = getattr(module, "__file__", None)
    module_spec = getattr(module, "__spec__", None)
    result.update(
        {
            "ok": True,
            "file": str(Path(module_file).resolve()) if module_file else None,
            "package": getattr(module, "__package__", None),
            "spec_origin": getattr(module_spec, "origin", None),
        }
    )
    if module_file:
        try:
            payload = Path(module_file).read_bytes()
        except OSError as exc:
            result["file_digest_error"] = f"{type(exc).__name__}: {exc}"
        else:
            result["file_size_bytes"] = len(payload)
            result["file_sha256"] = sha256_bytes(payload)
    return result


def distribution_inventory() -> dict[str, Any]:
    items: list[dict[str, str | None]] = []
    errors: list[str] = []
    try:
        distributions: Iterable[importlib.metadata.Distribution] = (
            importlib.metadata.distributions()
        )
        for distribution in distributions:
            try:
                name = distribution.metadata.get("Name") or distribution.name
                items.append({"name": name, "version": distribution.version})
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    items.sort(key=lambda item: ((item["name"] or "").casefold(), item["version"] or ""))
    return {"count": len(items), "items": items, "errors": errors}


def git_metadata(repo_root: Path, relative_files: Sequence[str]) -> dict[str, Any]:
    version, _ = run_command(("git", "--version"), cwd=repo_root)
    head, _ = run_command(("git", "rev-parse", "--verify", "HEAD"), cwd=repo_root)
    tree, _ = run_command(
        ("git", "rev-parse", "--verify", "HEAD^{tree}"), cwd=repo_root
    )
    branch, _ = run_command(
        ("git", "symbolic-ref", "--quiet", "--short", "HEAD"), cwd=repo_root
    )

    status, status_bytes = run_command(
        (
            "git",
            "status",
            "--porcelain=v2",
            "--branch",
            "--untracked-files=all",
            "-z",
        ),
        cwd=repo_root,
        include_stdout=False,
    )
    status["porcelain_v2_entries"] = [
        decode_output(entry) for entry in status_bytes.split(b"\0") if entry
    ]

    combined_diff, combined_diff_bytes = run_command(
        ("git", "diff", "--binary", "--no-ext-diff", "HEAD", "--"),
        cwd=repo_root,
        include_stdout=False,
    )
    staged_diff, _ = run_command(
        ("git", "diff", "--binary", "--no-ext-diff", "--cached", "HEAD", "--"),
        cwd=repo_root,
        include_stdout=False,
    )
    unstaged_diff, _ = run_command(
        ("git", "diff", "--binary", "--no-ext-diff", "--"),
        cwd=repo_root,
        include_stdout=False,
    )
    combined_diff["coverage_note"] = (
        "Hashes staged and unstaged tracked-file differences against HEAD; "
        "untracked paths are represented by the porcelain status hash, not diff bytes."
    )

    configs: dict[str, dict[str, Any]] = {}
    for key in GIT_EOL_CONFIG_KEYS:
        config, _ = run_command(
            ("git", "config", "--show-origin", "--get-all", key), cwd=repo_root
        )
        config["state"] = "set" if config["returncode"] == 0 else "unset_or_error"
        configs[key] = config

    attributes: dict[str, Any]
    if relative_files:
        attributes, _ = run_command(
            (
                "git",
                "check-attr",
                "-z",
                "text",
                "eol",
                "working-tree-encoding",
                "--",
                *relative_files,
            ),
            cwd=repo_root,
        )
    else:
        attributes = {
            "command": [],
            "cwd": str(repo_root),
            "ok": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "note": "no repository-relative files were requested",
        }

    return {
        "version": version,
        "head": head,
        "head_tree": tree,
        "branch": branch,
        "status": status,
        "diff_against_head": combined_diff,
        "staged_diff_against_head": staged_diff,
        "unstaged_diff": unstaged_diff,
        "working_state_sha256": sha256_bytes(
            status_bytes + b"\0--TRACKED-DIFF--\0" + combined_diff_bytes
        ),
        "working_state_hash_scope": (
            "raw porcelain-v2 status bytes plus raw tracked diff-against-HEAD bytes"
        ),
        "eol_config": configs,
        "attributes": attributes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Explicit JSON output path (required; no implicit evidence file is used).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repository_root(),
        help="Repository candidate; Git top-level discovery is recorded and used when valid.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="extra_files",
        help="Additional repository-relative or absolute file to hash (repeatable).",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        dest="extra_modules",
        help="Additional import to resolve and summarize (repeatable).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root, discovery = discover_repository_root(args.repo_root)

    requested_files = list(dict.fromkeys((*DEFAULT_FILES, *args.extra_files)))
    paths: list[Path] = []
    relative_files: list[str] = []
    for requested in requested_files:
        candidate = Path(requested)
        path = candidate if candidate.is_absolute() else repo_root / candidate
        path = path.resolve()
        paths.append(path)
        try:
            relative_files.append(path.relative_to(repo_root).as_posix())
        except ValueError:
            pass

    collector_payload = Path(__file__).resolve().read_bytes()
    metadata: dict[str, Any] = {
        "schema_version": "pc-b-w3-repair-metadata-v1",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "collector": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_bytes(collector_payload),
            "size_bytes": len(collector_payload),
        },
        "repository": {
            "requested_root": str(args.repo_root.resolve()),
            "resolved_root": str(repo_root),
            "git_top_level_discovery": discovery,
        },
        "runtime": {
            "executable": sys.executable,
            "version": sys.version,
            "version_info": list(sys.version_info),
            "implementation": platform.python_implementation(),
            "implementation_version": platform.python_version(),
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "byteorder": sys.byteorder,
            "default_encoding": sys.getdefaultencoding(),
            "filesystem_encoding": sys.getfilesystemencoding(),
        },
        "operating_system": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "architecture": list(platform.architecture()),
        },
        "environment": {
            "policy": "Only values for the fixed allowlist are serialized.",
            "allowlist": list(ENVIRONMENT_VALUE_ALLOWLIST),
            "values": {
                key: os.environ[key]
                for key in ENVIRONMENT_VALUE_ALLOWLIST
                if key in os.environ
            },
        },
        "imports": [
            import_summary(module_name)
            for module_name in dict.fromkeys((*DEFAULT_MODULES, *args.extra_modules))
        ],
        "installed_distributions": distribution_inventory(),
        "files": [file_summary(path, repo_root=repo_root) for path in paths],
        "git": git_metadata(repo_root, tuple(dict.fromkeys(relative_files))),
    }

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output_path.write_bytes(encoded)
    print(f"wrote {output_path} ({len(encoded)} bytes, sha256={sha256_bytes(encoded)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
