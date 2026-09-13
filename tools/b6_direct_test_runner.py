"""Directly execute the frozen B6 delivery tests when pytest is unavailable.

The output explicitly identifies this as a compatibility runner, not a pytest
run.  It expands the frozen parametrizations and module-scoped fixture used by
the six delivery modules and emits both JSON and JUnit evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import itertools
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "1d24099a025c9d7c00a59e4c78c593703924b0eb"
MODULES = (
    "test_structure_two_joint_consumption_components",
    "test_structure_two_ciav",
    "test_structure_two_ciav_negative_observation_layers",
    "test_structure_two_w3_native_posterior_projection",
    "test_project_two_ciav_interactive_development",
    "test_project_two_ciav_break_even",
)


def git_blob(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode()
    return hashlib.sha1(header + payload).hexdigest()


def source_identity() -> dict[str, object]:
    tree = json.loads((ROOT / "REMOTE_TREE_MANIFEST.json").read_text())["tree"]
    expected = {row["path"]: row["sha"] for row in tree if row["type"] == "blob"}
    actual = {
        str(path.relative_to(ROOT)): git_blob(path)
        for path in sorted((ROOT / "src").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    mismatches = {
        path: {"expected": expected.get(path), "actual": sha}
        for path, sha in actual.items()
        if expected.get(path) != sha
    }
    return {
        "expected_sha": SOURCE_SHA,
        "source_file_count": len(actual),
        "exact_blob_matches": len(actual) - len(mismatches),
        "mismatches": mismatches,
    }


def parameter_cases(function):
    rows = [({}, "")]
    for names, values in getattr(function, "__b6_parametrize__", ()):
        expanded = []
        for current, suffix in rows:
            for index, supplied in enumerate(values):
                supplied = supplied if len(names) > 1 else (supplied,)
                if len(names) > 1 and not isinstance(supplied, (tuple, list)):
                    raise TypeError(f"invalid parameter row for {function.__name__}")
                mapping = dict(zip(names, supplied, strict=True))
                expanded.append(({**current, **mapping}, f"{suffix}[{index}]"))
        rows = expanded
    return rows


def execute() -> list[dict[str, object]]:
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]
    import b6_pytest_shim as shim

    sys.modules["pytest"] = shim
    # Two frozen cases spawn a clean interpreter with a PYTHONPATH containing
    # only src/tests.  Append the audit tools directory for those child calls so
    # their test-module imports can resolve the audit-only pytest shim without
    # placing a pytest.py file in the real tests directory.
    original_subprocess_run = subprocess.run

    def subprocess_run_with_audit_shim(*args, **kwargs):
        environment = kwargs.get("env")
        if environment is not None:
            environment = dict(environment)
            current = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = os.pathsep.join(
                part for part in (current, str(ROOT / "tools")) if part
            )
            kwargs["env"] = environment
        return original_subprocess_run(*args, **kwargs)

    subprocess.run = subprocess_run_with_audit_shim
    results = []
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        fixtures = {
            name: value
            for name, value in vars(module).items()
            if callable(value) and getattr(value, "__b6_fixture__", False)
        }
        fixture_cache = {}
        tests = sorted(
            (name, value)
            for name, value in vars(module).items()
            if name.startswith("test_") and callable(value)
        )
        for function_name, function in tests:
            for parameters, suffix in parameter_cases(function):
                case_name = f"{module_name}::{function_name}{suffix}"
                arguments = dict(parameters)
                for name in inspect.signature(function).parameters:
                    if name in arguments:
                        continue
                    if name not in fixtures:
                        raise RuntimeError(f"unsupported fixture {name!r} in {case_name}")
                    if name not in fixture_cache:
                        fixture_cache[name] = fixtures[name]()
                    arguments[name] = fixture_cache[name]
                started = time.perf_counter()
                try:
                    function(**arguments)
                except BaseException as error:
                    results.append(
                        {
                            "case": case_name,
                            "status": "failed",
                            "seconds": time.perf_counter() - started,
                            "exception": type(error).__name__,
                            "message": str(error),
                            "traceback": traceback.format_exc(),
                        }
                    )
                else:
                    results.append(
                        {
                            "case": case_name,
                            "status": "passed",
                            "seconds": time.perf_counter() - started,
                        }
                    )
    subprocess.run = original_subprocess_run
    return results


def write_junit(path: Path, results: list[dict[str, object]], seconds: float) -> None:
    failures = sum(row["status"] == "failed" for row in results)
    suite = ET.Element(
        "testsuite",
        name="B6 direct compatibility runner (not pytest)",
        tests=str(len(results)),
        failures=str(failures),
        errors="0",
        skipped="0",
        time=f"{seconds:.9f}",
    )
    for row in results:
        module, name = str(row["case"]).split("::", 1)
        case = ET.SubElement(
            suite,
            "testcase",
            classname=module,
            name=name,
            time=f"{float(row['seconds']):.9f}",
        )
        if row["status"] == "failed":
            failure = ET.SubElement(
                case,
                "failure",
                type=str(row.get("exception", "failure")),
                message=str(row.get("message", "")),
            )
            failure.text = str(row.get("traceback", ""))
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    results = execute()
    seconds = time.perf_counter() - started
    identity = source_identity()
    passed = sum(row["status"] == "passed" for row in results)
    record = {
        "runner": "direct compatibility runner; explicitly not pytest",
        "frozen_code_sha": SOURCE_SHA,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(ROOT),
        "command": sys.argv,
        "environment": {
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
        },
        "source_identity": identity,
        "counts": {
            "collected": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "not_run": 0,
        },
        "seconds": seconds,
        "results": results,
    }
    (args.output_dir / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    write_junit(args.output_dir / "junit.xml", results, seconds)
    print(json.dumps({"counts": record["counts"], "seconds": seconds, "identity": identity}))
    return int(passed != len(results) or bool(identity["mismatches"]))


if __name__ == "__main__":
    raise SystemExit(main())
