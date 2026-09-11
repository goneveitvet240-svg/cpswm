#!/usr/bin/env python3
"""Audit retained Git records in isolated historical source snapshots.

The optional first-failure rerun checks numeric/semantic fields, explicitly
excluding the two legacy run-local UUID chains. It never grants currentness.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

# Establish execution provenance before importing project dependencies.
import types
from pathlib import Path

_bootstrap_path = (
    Path(__file__).resolve().parents[2] / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parents[2])

from cpswm.system.evaluation_operations.structure_two_evidence_versions import (  # noqa: E402
    git_bytes,
    historical_entries,
    verify_historical_record,
)

ROOT = Path(__file__).resolve().parents[2]
PROBE = """
import json
from pathlib import Path
from cpswm.system.structure_two_production_system import build_production_assembly_manifest
print(json.dumps(build_production_assembly_manifest(Path.cwd())))
"""
FIRST_RUN = """
import json
from pathlib import Path
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (  # noqa: E402
    run_p5_three_arm_death_test,
)
print(json.dumps(run_p5_three_arm_death_test(repository_root=Path.cwd())))
"""


def snapshot(commit: str) -> Path:
    parent = ROOT / ".checkout" / "evidence-history"
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=commit + "-", dir=parent))
    data = subprocess.check_output(
        ["git", "archive", commit, "src", "configs", "pyproject.toml", "uv.lock"], cwd=ROOT
    )
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(directory, filter="data")
    return directory


def child(directory: Path, code: str) -> dict:
    environment = {**os.environ, "PYTHONPATH": str(directory / "src")}
    bootstrap = ROOT / "apps/evaluation_runner/structure_two_source_bootstrap.py"
    prelude = (
        "import types, sys\nfrom pathlib import Path\n"
        "boot = types.ModuleType('_cpswm_source_bootstrap')\n"
        "sys.modules[boot.__name__] = boot\n"
        f"exec(compile({bootstrap.read_bytes()!r}, {str(bootstrap)!r}, 'exec'), boot.__dict__)\n"
        "boot.establish(Path.cwd())\n"
    )
    code = prelude + code
    return json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=directory,
            env=environment,
            text=True,
            stderr=subprocess.PIPE,
        )
    )


def legacy_projection(payload: dict) -> dict:
    value = json.loads(json.dumps(payload))
    value.pop("content_sha256")
    for row in value["test_episode_metrics"]:
        row.pop("ciav_receipt_chain_sha256")
        row.pop("typed_action_chain_sha256")
    return value


def verify_history_report(stored: dict, expected: dict) -> None:
    def normalise(value: dict) -> str:
        # Temporary extraction directory names are execution-local diagnostics,
        # not source or scientific identity. All verdicts and metrics remain bound.
        return re.sub(
            r"/[^\"\\]*?/\.checkout/evidence-history/[0-9a-f]{40}(?:-[^/\"\\]+)?/",
            "<historical-snapshot>/",
            json.dumps(value, sort_keys=True),
        )

    if normalise(stored) != normalise(expected):
        raise ValueError("historical source audit differs from fresh snapshot/replay checks")


FAILED_REPLAY_IDENTITY = (
    "4103bea1942bf1541d574103de5fcf136f50ce1e",
    "benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json",
    "post_open_failed_replay",
)
FIRST_FAILURE_IDENTITY = (
    "557ff9ceec267e1f37ebbdc3a27a9364b8b482b8",
    "benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json",
    "first_git_record_of_failure",
)


def require_completed_replay(report: dict) -> None:
    rows = report["records"]
    required = [
        row
        for row in rows
        if (row["record_commit"], row["git_path"], row["lifecycle"]) == FAILED_REPLAY_IDENTITY
    ]
    if (
        len(rows) != 11
        or len(required) != 1
        or required[0].get("numerical_recomputation_performed") is not True
        or required[0].get("full_artifact_recomputation_matches") is not True
        or report["coverage"]["numerical_recomputations_completed"] != 1
    ):
        raise ValueError("required historical failed replay did not actually complete")


def build_history_report(*, recompute_first_failure: bool, recompute_failed_replay: bool) -> dict:
    rows = []
    assemblies = {}
    for entry in historical_entries(ROOT):
        record = verify_historical_record(ROOT, entry)
        payload = json.loads((ROOT / entry["path"]).read_text())
        commit = entry["record_commit"]
        if commit not in assemblies:
            try:
                assemblies[commit] = child(snapshot(commit), PROBE)
            except subprocess.CalledProcessError as error:
                assemblies[commit] = {"content_sha256": None, "source_import_error": error.stderr}
        assembly = assemblies[commit]
        mismatches = []
        for name, binding in payload["source_binding"].items():
            if isinstance(binding, dict) and "path" in binding:
                actual = hashlib.sha256(git_bytes(ROOT, commit, binding["path"])).hexdigest()
                if actual != binding["sha256"]:
                    mismatches.append(name)
        assembly_match = (
            payload["source_binding"]["production_assembly_manifest_sha256"]
            == assembly["content_sha256"]
        )
        record.update(
            {
                "source_comparison_commit": commit,
                "source_import_error": assembly.get("source_import_error"),
                "direct_binding_mismatches_at_record_commit": mismatches,
                "transitive_assembly_matches_record_commit": assembly_match,
                "source_version_recoverable_at_record_commit": not mismatches and assembly_match,
                "numerical_recomputation_performed": False,
                "evidence_boundary": (
                    "LOCAL_GIT_RECORD_AND_MATCHED_SOURCE_SNAPSHOT"
                    if not mismatches and assembly_match
                    else "LOCAL_GIT_RECORD_ONLY_SOURCE_SNAPSHOT_NOT_ESTABLISHED"
                ),
            }
        )
        identity = (entry["record_commit"], entry["git_path"], entry["lifecycle"])
        record["git_path"] = entry["git_path"]
        record["lifecycle"] = entry["lifecycle"]
        if identity == FAILED_REPLAY_IDENTITY and recompute_failed_replay:
            if not record["source_version_recoverable_at_record_commit"]:
                raise ValueError("historical failed replay has no recoverable source snapshot")
            fresh = child(snapshot(commit), FIRST_RUN)
            record["numerical_recomputation_performed"] = True
            record["full_artifact_recomputation_matches"] = payload == fresh
            if payload != fresh:
                raise ValueError("historical failed replay full recomputation disagrees")
        if (
            identity == FIRST_FAILURE_IDENTITY
            and recompute_first_failure
            and not assembly.get("source_import_error")
        ):
            fresh = child(snapshot(commit), FIRST_RUN)
            record["numerical_recomputation_performed"] = True
            record["all_fields_except_legacy_uuid_chains_match"] = legacy_projection(
                payload
            ) == legacy_projection(fresh)
            record["excluded_legacy_run_identity_fields"] = [
                "test_episode_metrics/*/ciav_receipt_chain_sha256",
                "test_episode_metrics/*/typed_action_chain_sha256",
                "content_sha256",
            ]
            if not record["all_fields_except_legacy_uuid_chains_match"]:
                raise ValueError("historical first-failure numerical/source replay disagrees")
        if (
            identity == FIRST_FAILURE_IDENTITY
            and recompute_first_failure
            and assembly.get("source_import_error")
        ):
            record["requested_historical_rerun_blocked"] = True
            record["evidence_boundary"] = "LOCAL_GIT_RECORD_ONLY_HISTORICAL_SOURCE_IMPORT_FAILED"
        rows.append(record)
        print(json.dumps(record), flush=True)
    report = {
        "protocol": "structure-two-historical-local-git-audit@0.2",
        "authority": "LOCAL_GIT_AND_EXPLICIT_RECOMPUTATION_ONLY",
        "first_use_or_unseen_status_established": False,
        "independent_custody_established": False,
        "records": rows,
    }
    report["coverage"] = {
        "git_byte_records_completed": len(rows),
        "source_snapshots_recoverable": sum(
            row["source_version_recoverable_at_record_commit"] for row in rows
        ),
        "numerical_recomputations_completed": sum(
            row["numerical_recomputation_performed"] for row in rows
        ),
        "required_replay_requested": recompute_failed_replay,
    }
    if recompute_failed_replay:
        require_completed_replay(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute-first-failure", action="store_true")
    parser.add_argument("--recompute-failed-replay", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args()
    report = build_history_report(
        recompute_first_failure=bool(args.verify) or args.recompute_first_failure,
        recompute_failed_replay=bool(args.verify) or args.recompute_failed_replay,
    )
    if args.verify:
        require_completed_replay(report)
        verify_history_report(json.loads(args.verify.read_text()), report)
        print(
            "11 Git byte records checked; source recovery recorded; "
            "1 required full failed replay completed",
            flush=True,
        )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"completed_coverage": report["coverage"]}), flush=True)


if __name__ == "__main__":
    main()
