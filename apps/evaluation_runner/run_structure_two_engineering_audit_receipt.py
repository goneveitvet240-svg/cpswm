#!/usr/bin/env python3
"""Execute the local engineering audit matrix and write a source-bound receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT: Final = (
    ROOT / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
    "engineering_audit_receipt.json"
)
P0_MANIFEST: Final = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_2.json"
COMMANDS: Final = {
    "p0_adversarial_tests": (
        ".venv/bin/pytest",
        "-q",
        "tests/test_structure_two_trusted_ablation_authorization.py",
        "tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py",
        "tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py",
    ),
    "core_pytest": (
        ".venv/bin/pytest",
        "-n",
        "auto",
        "-q",
        "--ignore=tests/test_structure_two_engineering_trust_checkpoint.py",
    ),
    "mypy_src": (".venv/bin/mypy", "src"),
    "ruff_lint": (".venv/bin/ruff", "check", "src", "tests", "apps"),
    "ruff_format": (".venv/bin/ruff", "format", "--check", "src", "tests", "apps"),
    "compileall": (".venv/bin/python", "-m", "compileall", "-q", "src", "apps", "tests"),
    # Generated audit logs are outputs of this very command matrix.  Excluding
    # them prevents an old failing ``git_diff_check.stdout.log`` from reporting
    # its own quoted whitespace diagnostics forever.  Source, tests, configs,
    # docs, manifests, receipts, and checkpoints remain inside the check.
    "git_diff_check": (
        "git",
        "diff",
        "--check",
        "--",
        ".",
        ":(exclude)benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
        "engineering_audit_logs/*.log",
    ),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    log_dir = output.parent / "engineering_audit_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(P0_MANIFEST.read_text(encoding="utf-8"))
    runs: list[dict[str, object]] = []
    for command_id, argv in COMMANDS.items():
        start = _now()
        completed = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False)
        end = _now()
        stdout_path = log_dir / f"{command_id}.stdout.log"
        stderr_path = log_dir / f"{command_id}.stderr.log"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        runs.append(
            {
                "command_id": command_id,
                "argv": list(argv),
                "start_timestamp": start,
                "end_timestamp": end,
                "exit_code": completed.returncode,
                "stdout_path": stdout_path.relative_to(ROOT).as_posix(),
                "stdout_sha256": _sha256_file(stdout_path),
                "stderr_path": stderr_path.relative_to(ROOT).as_posix(),
                "stderr_sha256": _sha256_file(stderr_path),
            }
        )
        print(f"{command_id}={completed.returncode}", flush=True)
    payload: dict[str, object] = {
        "protocol": "structure-two-engineering-audit-receipt@1.0",
        "authority": "LOCAL_EXECUTION_ONLY",
        "source_manifest_path": P0_MANIFEST.relative_to(ROOT).as_posix(),
        "source_manifest_file_sha256": _sha256_file(P0_MANIFEST),
        "source_manifest_sha256": manifest["manifest_sha256"],
        "command_runs": runs,
        "all_commands_passed": all(run["exit_code"] == 0 for run in runs),
        "claim_boundary": (
            "This receipt binds local command outputs to the current source manifest. It does "
            "not establish independent custody, historical authenticity, or external validity."
        ),
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if payload["all_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
