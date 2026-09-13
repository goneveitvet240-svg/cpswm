"""Run the frozen 38-path/812-node selection with complete local evidence."""

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
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
FROZEN_COMMAND = ROOT / (
    "docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/post_lock/"
    "r7_exact_812_postlock_crlf_seed0.command.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _junit_counts(path: Path) -> dict[str, int | float] | None:
    if not path.exists():
        return None
    root = ElementTree.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites:
        return None
    return {
        "tests": sum(int(item.attrib.get("tests", 0)) for item in suites),
        "failures": sum(int(item.attrib.get("failures", 0)) for item in suites),
        "errors": sum(int(item.attrib.get("errors", 0)) for item in suites),
        "skipped": sum(int(item.attrib.get("skipped", 0)) for item in suites),
        "time_seconds": sum(float(item.attrib.get("time", 0.0)) for item in suites),
    }


def _failed_nodeids(path: Path) -> tuple[str, ...]:
    """Recover pytest node IDs for failed/error cases from a prior JUnit file."""

    root = ElementTree.parse(path).getroot()
    nodeids: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        parts = case.attrib["classname"].split(".")
        module_path: Path | None = None
        class_parts: list[str] = []
        for end in range(len(parts), 0, -1):
            candidate = ROOT.joinpath(*parts[:end]).with_suffix(".py")
            if candidate.exists():
                module_path = candidate
                class_parts = parts[end:]
                break
        if module_path is None:
            raise ValueError(f"cannot map JUnit classname to a test file: {case.attrib!r}")
        relative = module_path.relative_to(ROOT).as_posix()
        suffix = "::".join((*class_parts, case.attrib["name"]))
        nodeids.append(f"{relative}::{suffix}")
    return tuple(nodeids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", default="b4_exact_812_final_linux_py312_seed0")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--hash-seed", default="0")
    parser.add_argument(
        "--test",
        action="append",
        default=[],
        help="select a test path/node explicitly instead of the frozen 812 paths",
    )
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument(
        "--failed-from-junit",
        type=Path,
        help="rerun only failure/error nodes recorded by a prior JUnit file",
    )
    args = parser.parse_args()
    if args.failed_from_junit is not None and args.test:
        parser.error("--failed-from-junit and --test are mutually exclusive")

    frozen = json.loads(FROZEN_COMMAND.read_text(encoding="utf-8"))
    test_paths = tuple(
        ROOT / item for item in frozen["command"] if item.startswith("tests/")
    )
    missing = tuple(str(path.relative_to(ROOT)) for path in test_paths if not path.exists())
    if missing:
        raise SystemExit("missing frozen tests: " + ", ".join(missing))

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{args.name}.stdout.log"
    stderr_path = output_dir / f"{args.name}.stderr.log"
    junit_path = output_dir / f"{args.name}.junit.xml"
    result_path = output_dir / f"{args.name}.result.json"
    basetemp = output_dir / f".{args.name}.tmp"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    if args.collect_only:
        command.append("--collect-only")
    else:
        command.extend(("-n", str(args.workers)))
    selected: tuple[str, ...]
    if args.failed_from_junit is not None:
        selected = _failed_nodeids(args.failed_from_junit.resolve())
        if not selected:
            raise SystemExit("the supplied JUnit file contains no failure/error nodes")
    elif args.test:
        selected = tuple(args.test)
        missing_selected = tuple(
            item.split("::", 1)[0]
            for item in selected
            if not (ROOT / item.split("::", 1)[0]).exists()
        )
        if missing_selected:
            raise SystemExit("missing selected tests: " + ", ".join(missing_selected))
    else:
        selected = tuple(str(path) for path in test_paths)
    command.extend(
        (
            "--basetemp",
            str(basetemp),
            "--junitxml",
            str(junit_path),
            *selected,
        )
    )
    environment = dict(os.environ)
    inherited_pythonpath = environment.get("PYTHONPATH")
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join(
                (
                    str(ROOT / "src"),
                    str(ROOT / "tests"),
                    *((inherited_pythonpath,) if inherited_pythonpath else ()),
                )
            ),
            "PYTHONHASHSEED": args.hash_seed,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stderr:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
            text=True,
        )
    finished_at = datetime.now(UTC)
    payload = {
        "schema": "cpswm.pc-b.command-evidence@1",
        "name": args.name,
        "base_sha": "c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c",
        "classification": "repair-side Linux LF engineering regression",
        "command": command,
        "cwd": str(ROOT),
        "environment_overrides": {
            key: environment[key]
            for key in (
                "PYTHONPATH",
                "PYTHONHASHSEED",
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
            )
        },
        "selected_test_paths": len(args.test) if args.test else len(test_paths),
        "selected_nodeids": len(selected) if args.failed_from_junit is not None else None,
        "failed_from_junit": (
            str(args.failed_from_junit.resolve())
            if args.failed_from_junit is not None
            else None
        ),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": time.perf_counter() - started,
        "returncode": completed.returncode,
        "platform": platform.platform(),
        "runner": {"executable": sys.executable, "version": sys.version},
        "source_sha256": {
            path.name: _sha256(path)
            for path in (
                ROOT / "src/cpswm/system/prototype_spine.py",
                ROOT / "src/cpswm/system/structure_two_particle_workspace.py",
                ROOT / "src/cpswm/system/structure_two_semantic_identity.py",
            )
        },
        "junit": _junit_counts(junit_path),
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (stdout_path, stderr_path, junit_path)
            if path.exists()
        },
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
