"""Collect read-only metadata for the independent W1 audit.

The script writes JSON to stdout.  It deliberately records both Git blob bytes
and checkout bytes because Windows ``core.autocrlf`` can make them differ.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

DELIVERY_SHA = "21870b0bcd6c23d43518a27fcc1c4b538b3912b7"
PRODUCTION_SHA = "6fcff45c71eff3f3457d0b6eac6cd872102db89d"
CODE_FILES = (
    "tools/structure_two_pytest_runtime.py",
    "tools/structure_two_unified_acceptance.py",
    "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py",
    "tests/test_structure_two_runtime_cache_identity.py",
    "tests/test_structure_two_engineering_trust_checkpoint.py",
)
W1_PAYLOAD_FILES = (
    "tests/test_structure_two_evidence_versions.py",
    "tests/test_structure_two_evidence_supplement.py",
    "tests/test_structure_two_entry_portability.py",
)
STATE_FILES = (
    "docs/reviews/data/structure_two_unified_acceptance_runs/r6_runtime86_protected/state.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/r6_native115_accepted/state.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/r6_history_trace_accepted/state.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_isolated_comparison_archive/r6_comparison_accepted/state.json",
)
OUTER_COMMAND_FILES = (
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_execution_records/runtime86_accepted.command.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_execution_records/runtime86_protected.command.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_execution_records/native115_accepted.command.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_execution_records/history_trace_accepted.command.json",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_execution_records/comparison_accepted.command.json",
)
HISTORICAL_JUNIT_FILES = (
    "docs/reviews/data/structure_two_unified_acceptance_runs/r6_runtime86_protected/runtime86.xml",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_native115_accepted/window1_protection.xml",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_history_trace_accepted/history_trace.xml",
    "docs/reviews/data/structure_two_unified_acceptance_runs/"
    "r6_isolated_comparison_archive/r6_comparison_accepted/"
    "window2_comparison_and_forgery.xml",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(root: Path, argv: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    completed = subprocess.run(
        argv,
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
    )
    return {
        "argv": argv,
        "cwd": str(root),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.decode("utf-8", errors="replace"),
        "stderr": completed.stderr.decode("utf-8", errors="replace"),
    }


def git(root: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    if check and completed.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({completed.returncode}): "
            + completed.stderr.decode("utf-8", errors="replace")
        )
    return completed.stdout


def newline_summary(data: bytes) -> dict[str, object]:
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    cr = data.count(b"\r")
    return {
        "bytes": len(data),
        "sha256": sha256(data),
        "crlf_sequences": crlf,
        "bare_lf_sequences": lf - crlf,
        "bare_cr_sequences": cr - crlf,
        "ends_with_lf": data.endswith(b"\n"),
    }


def git_config(root: Path, key: str) -> dict[str, object]:
    completed = subprocess.run(
        ["git", "config", "--show-origin", "--get", key],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return {
        "exit_code": completed.returncode,
        "value": completed.stdout.decode("utf-8", errors="replace").strip() or None,
        "stderr": completed.stderr.decode("utf-8", errors="replace").strip() or None,
    }


def source_rows(root: Path, reported: dict[str, str]) -> dict[str, object]:
    rows: dict[str, object] = {}
    for relative in (*CODE_FILES, *W1_PAYLOAD_FILES, "pyproject.toml", "uv.lock"):
        working = (root / relative).read_bytes()
        delivery_blob = git(root, "show", f"{DELIVERY_SHA}:{relative}")
        production_blob = git(root, "show", f"{PRODUCTION_SHA}:{relative}")
        blob_oid = git(root, "rev-parse", f"{DELIVERY_SHA}:{relative}").decode().strip()
        rows[relative] = {
            "working_copy": newline_summary(working),
            "delivery_git_blob": {
                **newline_summary(delivery_blob),
                "git_blob_oid_sha1": blob_oid,
            },
            "production_git_blob_sha256": sha256(production_blob),
            "delivery_equals_production": delivery_blob == production_blob,
            "working_equals_git_blob": working == delivery_blob,
            "reported_final_sha256": reported.get(relative),
            "reported_matches_git_blob": (
                reported.get(relative) == sha256(delivery_blob) if relative in reported else None
            ),
        }
    return rows


def state_summary(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    before = value.get("source_before")
    after = value.get("source_after")
    return {
        "status": value.get("status"),
        "source_head": before.get("head") if isinstance(before, dict) else None,
        "source_manifest_sha256": before.get("sha256") if isinstance(before, dict) else None,
        "source_file_count": len(before.get("files", {})) if isinstance(before, dict) else None,
        "source_before_equals_after": before == after,
        "stages": [
            {
                "name": row.get("name"),
                "argv": row.get("argv"),
                "exit_code": row.get("exit_code"),
                "pytest_counts": row.get("pytest_counts"),
            }
            for row in value.get("stages", [])
        ],
    }


def junit_summary(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    outer = root.attrib
    totals = {key: int(outer.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")}
    if not totals["tests"] and suites:
        totals = {
            key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
    return {
        "path": str(path),
        "sha256": sha256(path.read_bytes()),
        **totals,
    }


def import_probe(root: Path) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    code = (
        "import json,cpswm,tools.structure_two_unified_acceptance as u;"
        "print(json.dumps({'cpswm':cpswm.__file__,'acceptance':u.__file__,"
        "'w1_tests':u.W1_TESTS}))"
    )
    result = run(root, [sys.executable, "-c", code], env=env)
    if result["exit_code"] == 0:
        result["payload"] = json.loads(str(result["stdout"]))
    return result


def checkout_summary(root: Path, reported: dict[str, str]) -> dict[str, object]:
    return {
        "root": str(root),
        "head": git(root, "rev-parse", "HEAD").decode().strip(),
        "tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
        "status_porcelain_v2": git(root, "status", "--porcelain=v2").decode(
            "utf-8", errors="replace"
        ),
        "git_config": {
            key: git_config(root, key) for key in ("core.autocrlf", "core.eol", "core.safecrlf")
        },
        "check_attr": git(root, "check-attr", "-a", "--", *CODE_FILES).decode(
            "utf-8", errors="replace"
        ),
        "ls_files_eol": git(root, "ls-files", "--eol", "--", *CODE_FILES, *W1_PAYLOAD_FILES).decode(
            "utf-8", errors="replace"
        ),
        "sources": source_rows(root, reported),
        "import_probe": import_probe(root),
    }


def load_command(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "sha256": sha256(path.read_bytes()),
        "argv": value.get("argv"),
        "cwd": value.get("cwd"),
        "start": value.get("start"),
        "end": value.get("end"),
        "seconds": value.get("seconds"),
        "exit_code": value.get("exit_code"),
        "environment": value.get("environment"),
    }


def verify_delivery_inventory(root: Path) -> dict[str, object]:
    path = root / "docs/reviews/pc_a/w1_cache_repair_2026-09-12/artifact_inventory.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    missing: list[str] = []
    mismatches: list[dict[str, object]] = []
    for relative, expected in value["files"].items():
        completed = subprocess.run(
            ["git", "show", f"{DELIVERY_SHA}:{relative}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            missing.append(relative)
            continue
        actual = sha256(completed.stdout)
        if actual != expected["sha256"] or len(completed.stdout) != expected["bytes"]:
            mismatches.append(
                {
                    "path": relative,
                    "expected_sha256": expected["sha256"],
                    "actual_sha256": actual,
                    "expected_bytes": expected["bytes"],
                    "actual_bytes": len(completed.stdout),
                }
            )
    return {
        "path": str(path),
        "inventory_git_blob_sha256": sha256(
            git(root, "show", f"{DELIVERY_SHA}:{path.relative_to(root).as_posix()}")
        ),
        "code_sha": value.get("code_sha"),
        "expected_file_count": len(value["files"]),
        "matched_file_count": len(value["files"]) - len(missing) - len(mismatches),
        "missing": missing,
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lf-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    lf_root = args.lf_root.resolve()
    evidence_root = args.evidence_root.resolve()

    final_environment = json.loads(
        (
            root
            / "docs/reviews/pc_a/w1_cache_repair_2026-09-12/final_fixed_code_and_environment.json"
        ).read_text(encoding="utf-8")
    )
    reported_hashes = final_environment["files"]
    delivery_diff = git(root, "diff", "--name-status", PRODUCTION_SHA, DELIVERY_SHA)
    production_paths = ("src", "tools", "apps", "configs", "tests", "pyproject.toml", "uv.lock")
    production_diff = git(
        root, "diff", "--name-status", PRODUCTION_SHA, DELIVERY_SHA, "--", *production_paths
    )
    is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PRODUCTION_SHA, DELIVERY_SHA], cwd=root
    ).returncode

    package_rows = sorted(
        (
            {"name": item.metadata["Name"], "version": item.version}
            for item in importlib.metadata.distributions()
        ),
        key=lambda item: (str(item["name"]).lower(), str(item["version"])),
    )
    interpreter = Path(sys.executable)
    raw_root = evidence_root / "raw"
    windows_commands = {
        path.stem.removesuffix(".command"): load_command(path)
        for path in sorted(raw_root.glob("*.command.json"))
    }
    wsl_logs = {}
    for label in ("wsl_status", "wsl_list_verbose"):
        for stream in ("stdout", "stderr"):
            path = raw_root / f"{label}.{stream}.log"
            data = path.read_bytes() if path.exists() else b""
            text = data.decode("utf-16le", errors="replace").strip("\x00\r\n ")
            if not text:
                text = data.decode("utf-8", errors="replace").strip()
            wsl_logs[f"{label}.{stream}"] = {
                "bytes": len(data),
                "sha256": sha256(data),
                "decoded": text,
            }

    result = {
        "schema": "cpswm.pc-b.w1-independent-audit-metadata@1",
        "collected_utc": datetime.now(UTC).isoformat(),
        "scope": "read-only W1 audit; no W1 production changes and no scientific authorization",
        "delivery_sha": DELIVERY_SHA,
        "production_sha": PRODUCTION_SHA,
        "production_is_ancestor_of_delivery": is_ancestor == 0,
        "delivery_commit": git(
            root, "show", "-s", "--format=%H%n%P%n%T%n%aI%n%cI%n%s", DELIVERY_SHA
        )
        .decode("utf-8", errors="replace")
        .splitlines(),
        "production_commit": git(
            root, "show", "-s", "--format=%H%n%P%n%T%n%aI%n%cI%n%s", PRODUCTION_SHA
        )
        .decode("utf-8", errors="replace")
        .splitlines(),
        "delivery_vs_production": {
            "name_status_count": len(delivery_diff.splitlines()),
            "name_status_sha256": sha256(delivery_diff),
            "all_changes_under_docs": all(
                line.split(b"\t")[-1].startswith(b"docs/") for line in delivery_diff.splitlines()
            ),
            "production_like_diff": production_diff.decode("utf-8", errors="replace"),
        },
        "historical_reported_environment": final_environment,
        "current_windows_environment": {
            "platform": platform.platform(),
            "os_name": os.name,
            "python_executable": sys.executable,
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "interpreter_sha256": sha256(interpreter.read_bytes()),
            "packages": package_rows,
            "allowlisted_environment": {
                key: os.environ.get(key)
                for key in (
                    "PYTHONPATH",
                    "PYTHONHASHSEED",
                    "PYTHONDONTWRITEBYTECODE",
                    "PYTEST_ADDOPTS",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                    "PYTEST_PLUGINS",
                )
            },
        },
        "crlf_checkout": checkout_summary(root, reported_hashes),
        "lf_checkout": checkout_summary(lf_root, reported_hashes),
        "historical_states": {relative: state_summary(root / relative) for relative in STATE_FILES},
        "historical_outer_commands": {
            relative: load_command(root / relative) for relative in OUTER_COMMAND_FILES
        },
        "historical_junit": {
            relative: junit_summary(root / relative) for relative in HISTORICAL_JUNIT_FILES
        },
        "delivery_artifact_inventory_verification": verify_delivery_inventory(root),
        "current_windows_commands": windows_commands,
        "current_junit": {
            name: junit_summary(evidence_root / name)
            for name in (
                "windows_w1_fair_subset.junit.xml",
                "windows_lf_w1_fair_subset.junit.xml",
                "windows_lf_utf8_platform_diagnostic.junit.xml",
                "windows_lf_utf8_fair_compatible_subset.junit.xml",
                "windows_lf_utf8_cache_boundary_subset.junit.xml",
                "windows_lf_utf8_entry_cache_matrix.junit.xml",
            )
        },
        "wsl_raw_logs": wsl_logs,
        "cache_fairness": {
            "used_dash_B": False,
            "set_python_dont_write_bytecode": False,
            "cleared_caches_before_current_runs": False,
            "disabled_pytest_cacheprovider": False,
            "note": "All current test runs used ordinary Python/pytest cache behavior.",
        },
    }
    payload = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(payload)


if __name__ == "__main__":
    main()
