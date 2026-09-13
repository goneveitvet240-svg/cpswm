#!/usr/bin/env python3
"""Run one command without a shell and preserve an immutable evidence triplet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--expected-exit", type=int, default=0)
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Explicit NAME=VALUE override passed to the child (repeatable).",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    cwd = args.cwd.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "command": output_dir / f"{args.name}.command.json",
        "stdout": output_dir / f"{args.name}.stdout.log",
        "stderr": output_dir / f"{args.name}.stderr.log",
    }
    collisions = [str(path) for path in outputs.values() if path.exists()]
    if collisions:
        raise FileExistsError(f"refusing to overwrite evidence: {collisions}")

    overrides: dict[str, str] = {}
    for item in args.env:
        if "=" not in item:
            raise ValueError(f"environment override lacks '=': {item!r}")
        name, value = item.split("=", 1)
        if not name or name in overrides:
            raise ValueError(f"invalid or duplicate environment name: {name!r}")
        overrides[name] = value
    child_env = os.environ.copy()
    child_env.update(overrides)

    runner_path = Path(sys.executable).resolve()
    runner_payload = runner_path.read_bytes()
    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()
    launch_error: str | None = None
    try:
        completed = subprocess.run(
            args.command,
            cwd=cwd,
            env=child_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except OSError as exc:
        returncode = 127
        stdout = b""
        stderr = f"{type(exc).__name__}: {exc}\n".encode()
        launch_error = f"{type(exc).__name__}: {exc}"
    finished_at = datetime.now(UTC)

    with outputs["stdout"].open("xb") as stream:
        stream.write(stdout)
    with outputs["stderr"].open("xb") as stream:
        stream.write(stderr)

    record = {
        "schema": "cpswm.pc-b.command-evidence@1",
        "name": args.name,
        "command": args.command,
        "cwd": str(cwd),
        "environment_overrides": overrides,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": round(time.perf_counter() - started_perf, 6),
        "returncode": returncode,
        "expected_exit": args.expected_exit,
        "outcome_as_expected": returncode == args.expected_exit,
        "launch_error": launch_error,
        "platform": platform.platform(),
        "runner": {
            "executable": str(runner_path),
            "version": sys.version,
            "sha256": sha256(runner_payload),
            "size_bytes": len(runner_payload),
        },
        "artifacts": {
            "stdout": {
                "path": str(outputs["stdout"]),
                "bytes": len(stdout),
                "sha256": sha256(stdout),
            },
            "stderr": {
                "path": str(outputs["stderr"]),
                "bytes": len(stderr),
                "sha256": sha256(stderr),
            },
        },
    }
    encoded = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with outputs["command"].open("xb") as stream:
        stream.write(encoded)
    print(
        json.dumps(
            {
                "name": args.name,
                "returncode": returncode,
                "expected_exit": args.expected_exit,
                "duration_seconds": record["duration_seconds"],
                "command_record_sha256": sha256(encoded),
            },
            ensure_ascii=False,
        )
    )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
