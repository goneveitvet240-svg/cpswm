#!/usr/bin/env python3
"""Run an immutable pytest selection and record version-bound evidence.

The runner never uses a shell, refuses to overwrite an earlier run, and can
derive the R7 test paths directly from its preserved command manifest.  Test
scratch data stays beside the dedicated worktree under ``F:\\庞惟\\codex``;
only the compact log, JUnit document, and result manifest are deliverables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
KEY_SOURCE_FILES = (
    "src/cpswm/system/prototype_spine.py",
    "src/cpswm/system/structure_two_particle_workspace.py",
    "src/cpswm/system/structure_two_semantic_identity.py",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def run_capture(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.decode("utf-8", errors="backslashreplace").rstrip(),
        "stderr": completed.stderr.decode("utf-8", errors="backslashreplace").rstrip(),
    }


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def selected_paths(args: argparse.Namespace, root: Path) -> tuple[list[str], dict[str, Any]]:
    paths = list(args.test)
    provenance: dict[str, Any] = {"mode": "explicit", "manifest": None}
    if args.manifest is not None:
        manifest = args.manifest.resolve()
        payload = manifest.read_bytes()
        parsed = json.loads(payload)
        command = parsed.get("command")
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise ValueError("pytest source manifest has no string command array")
        manifest_paths = [item for item in command if item.startswith("tests/")]
        if not manifest_paths:
            raise ValueError("pytest source manifest contains no tests/ paths")
        paths.extend(manifest_paths)
        provenance = {
            "mode": "parsed_command_manifest",
            "manifest": str(manifest),
            "manifest_repository_relative": manifest.relative_to(root).as_posix(),
            "manifest_sha256": sha256_bytes(payload),
            "original_command": command,
            "original_exit_code": parsed.get("exit_code"),
            "original_base_sha": parsed.get("base_sha"),
        }
    paths = list(dict.fromkeys(paths))
    if not paths:
        raise ValueError("at least one test path or command manifest is required")
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"selected test paths are absent: {missing}")
    return paths, provenance


def source_inventory(root: Path, selected: Sequence[str]) -> dict[str, Any]:
    source_paths = sorted((root / "src").rglob("*.py"))
    key_paths = [root / path for path in (*KEY_SOURCE_FILES, *selected)]
    rows = [
        (path.relative_to(root).as_posix(), sha256_file(path))
        for path in source_paths
        if path.is_file()
    ]
    aggregate = sha256_bytes(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return {
        "python_source_file_count": len(rows),
        "python_source_inventory_sha256": aggregate,
        "key_files": {
            path.relative_to(root).as_posix(): {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in key_paths
            if path.is_file()
        },
    }


def junit_counts(path: Path) -> dict[str, int | None]:
    if not path.is_file():
        return {
            "tests": None,
            "failures": None,
            "errors": None,
            "skipped_total": None,
            "skipped_non_xfail": None,
            "xfailed": None,
        }
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = [case.find("skipped") for case in cases if case.find("skipped") is not None]
    xfailed = sum(
        node is not None and node.attrib.get("type") == "pytest.xfail" for node in skipped
    )
    return {
        "tests": len(cases),
        "failures": failures,
        "errors": errors,
        "skipped_total": len(skipped),
        "skipped_non_xfail": len(skipped) - xfailed,
        "xfailed": xfailed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--extra-pytest-arg", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not SAFE_NAME.fullmatch(args.name):
        raise ValueError("evidence name contains unsafe characters")
    if args.workers < 0:
        raise ValueError("worker count cannot be negative")

    root = repository_root()
    selected, provenance = selected_paths(args, root)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{args.name}.stdout.log"
    stderr_path = output_dir / f"{args.name}.stderr.log"
    junit_path = output_dir / f"{args.name}.junit.xml"
    result_path = output_dir / f"{args.name}.result.json"
    outputs = (stdout_path, stderr_path, junit_path, result_path)
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite first-run evidence: {existing}")

    scratch = root.parent / "_cpswm_test_scratch" / args.name
    if scratch.exists():
        raise FileExistsError(f"refusing to reuse test scratch directory: {scratch}")
    scratch.mkdir(parents=True)

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        "-ra",
        "-p",
        "no:cacheprovider",
        f"--basetemp={scratch / 'basetemp'}",
        f"--junitxml={junit_path}",
    ]
    if args.workers:
        command.extend(("-n", str(args.workers)))
    command.extend(args.extra_pytest_arg)
    command.extend(selected)

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(root / "src"),
            "PYTHONHASHSEED": str(args.seed),
            "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    recorded_environment = {
        key: environment[key]
        for key in (
            "PYTHONPATH",
            "PYTHONHASHSEED",
            "PYTHONPYCACHEPREFIX",
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
        )
    }

    git_before = {
        "head": run_capture(("git", "rev-parse", "HEAD"), root),
        "tree": run_capture(("git", "rev-parse", "HEAD^{tree}"), root),
        "status": run_capture(("git", "status", "--porcelain=v2", "--untracked-files=all"), root),
    }
    source_before = source_inventory(root, selected)
    package_versions = run_capture(
        (sys.executable, "-m", "pip", "show", "pytest", "pytest-xdist"), root
    )
    started_at = utc_now()
    started = time.perf_counter()
    print(
        f"START {args.name}: {len(selected)} paths, seed={args.seed}, "
        f"workers={args.workers}, HEAD={git_before['head']['stdout']}",
        flush=True,
    )
    with stdout_path.open("xb") as stdout_stream, stderr_path.open("xb") as stderr_stream:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
        )
        last_notice = 0
        while process.poll() is None:
            elapsed = int(time.perf_counter() - started)
            if elapsed - last_notice >= 30:
                print(f"RUNNING {args.name}: {elapsed}s elapsed", flush=True)
                last_notice = elapsed
            time.sleep(1)
        returncode = process.returncode
    duration = time.perf_counter() - started
    finished_at = utc_now()

    source_after = source_inventory(root, selected)
    git_after = {
        "head": run_capture(("git", "rev-parse", "HEAD"), root),
        "tree": run_capture(("git", "rev-parse", "HEAD^{tree}"), root),
        "status": run_capture(("git", "status", "--porcelain=v2", "--untracked-files=all"), root),
    }
    result: dict[str, Any] = {
        "schema_version": "pc-b-pytest-evidence-v1",
        "name": args.name,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "duration_seconds": round(duration, 6),
        "returncode": returncode,
        "cwd": str(root),
        "command": command,
        "command_windows": subprocess.list2cmdline(command),
        "environment_overrides": recorded_environment,
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "package_versions": package_versions,
        "selection": {
            "path_count": len(selected),
            "paths": selected,
            "provenance": provenance,
        },
        "git_before": git_before,
        "git_after": git_after,
        "head_unchanged": git_before["head"]["stdout"] == git_after["head"]["stdout"],
        "tree_unchanged": git_before["tree"]["stdout"] == git_after["tree"]["stdout"],
        "source_before": source_before,
        "source_after": source_after,
        "source_unchanged": source_before == source_after,
        "junit_counts": junit_counts(junit_path),
        "artifacts": {
            path.name: {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in (stdout_path, stderr_path, junit_path)
            if path.is_file()
        },
        "scratch_directory": str(scratch),
    }
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with result_path.open("xb") as result_stream:
        result_stream.write(encoded)
    print(
        f"FINISH {args.name}: exit={returncode}, duration={duration:.2f}s, "
        f"junit={result['junit_counts']}, source_unchanged={result['source_unchanged']}, "
        f"result_sha256={sha256_bytes(encoded)}",
        flush=True,
    )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
