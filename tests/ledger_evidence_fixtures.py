"""Builders for evidence/receipt pairs that satisfy the round-4 contracts.

Both the round-3 and round-4 suites need honest evidence to attack, and after
P0-2 an honest receipt binds ten fields plus an authority MAC.  Hand-writing
that in every test invites fixtures that quietly drift from the contract, so it
is built once here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cpswm.system.attestation import DOMAIN_RUN_RECEIPT, AttestationAuthority
from cpswm.system.progress_ledger.contracts import (
    EvidenceArtifactPayload,
    EvidenceKind,
    RunReceipt,
    code_snapshot_digest,
)

#: The key a real deployment would keep outside the candidate's reach.
TEST_AUTHORITY = AttestationAuthority(key_id="cpswm-governance-authority", secret=b"\xa5" * 32)

_STARTED = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
_FINISHED = datetime(2026, 8, 22, 9, 4, tzinfo=UTC)

#: Extra payload/receipt content each runtime kind must carry.
_KIND_DETAILS: dict[EvidenceKind, dict[str, object]] = {
    EvidenceKind.REPLAY: {
        "replay_log_sha256": "3" * 64,
        "replayed_transaction_count": 128,
        "divergence_count": 0,
    },
    EvidenceKind.REAL_DATA: {"recording_session_ids": ("sess-1",)},
    EvidenceKind.EMBODIED: {
        "robot_platform": "sim-only-harness",
        "trial_count": 20,
        "safety_incident_count": 0,
        "operator_id": "operator-1",
    },
}

SCHEMA_BY_KIND: dict[EvidenceKind, str] = {
    EvidenceKind.SYNTHETIC: "synthetic_report_json_v1",
    EvidenceKind.REPLAY: "replay_manifest_json_v1",
    EvidenceKind.REAL_DATA: "real_data_manifest_json_v1",
    EvidenceKind.EMBODIED: "embodied_run_json_v1",
}


def head_commit_and_snapshot(repo_root: Path) -> tuple[str, str]:
    """``(commit_sha, code_snapshot_sha256)`` for HEAD, or a synthetic pair.

    A test repository created under ``tmp_path`` has no git history, so the
    fallback returns a well-formed commit that will *not* resolve -- which is
    exactly the case the validator must treat as unverified rather than fine.
    """

    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        tree = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD^{tree}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "0" * 40, "2" * 64
    if commit.returncode != 0 or tree.returncode != 0:
        return "0" * 40, "2" * 64
    return commit.stdout.strip(), code_snapshot_digest(tree.stdout.strip())


def build_payload(
    *,
    module_id: str = "M05",
    kind: EvidenceKind = EvidenceKind.SYNTHETIC,
    git_commit_sha: str = "0" * 40,
    code_snapshot_sha256: str = "2" * 64,
    **overrides: object,
) -> EvidenceArtifactPayload:
    """A payload whose ``artifact_sha256`` is its own canonical digest."""

    fields: dict[str, object] = {
        "module_id": module_id,
        "evidence_kind": kind,
        "dataset_id": "ds-1",
        "run_id": "run-1",
        "git_commit_sha": git_commit_sha,
        "config_sha256": "1" * 64,
        "code_snapshot_sha256": code_snapshot_sha256,
        "case_count": 12,
        "result_status": "passed",
        "covered_module_ids": (module_id,),
        "artifact_sha256": "0" * 64,
    }
    if kind in _KIND_DETAILS:
        fields["dataset_manifest_sha256"] = "4" * 64
        fields.update(_KIND_DETAILS[kind])
    fields.update(overrides)
    payload = EvidenceArtifactPayload.model_validate(fields)
    return payload.model_copy(update={"artifact_sha256": payload.canonical_payload_sha256()})


def build_receipt(
    payload: EvidenceArtifactPayload,
    *,
    file_sha256: str,
    authority: AttestationAuthority | None = TEST_AUTHORITY,
    argv: tuple[str, ...] = ("pytest", "-q", "tests/"),
    **overrides: object,
) -> RunReceipt:
    """A receipt bound to ``payload``, attested unless ``authority`` is None."""

    fields: dict[str, object] = {
        "run_id": payload.run_id,
        "module_id": payload.module_id,
        "evidence_kind": payload.evidence_kind,
        "artifact_sha256": file_sha256,
        "dataset_id": payload.dataset_id,
        "dataset_manifest_sha256": payload.dataset_manifest_sha256,
        "config_sha256": payload.config_sha256,
        "code_snapshot_sha256": payload.code_snapshot_sha256,
        "git_commit_sha": payload.git_commit_sha,
        "command_argv": argv,
        "command": shlex.join(argv),
        "exit_code": 0,
        "started_at": _STARTED,
        "finished_at": _FINISHED,
        "result_status": payload.result_status,
    }
    fields.update(overrides)
    if "command_argv" in overrides and "command" not in overrides:
        fields["command"] = shlex.join(fields["command_argv"])  # type: ignore[arg-type]
    receipt = RunReceipt.model_validate(fields)
    if authority is None:
        return receipt
    signature = authority.sign(DOMAIN_RUN_RECEIPT, receipt.attested_content())
    return receipt.model_copy(update={"attestation": signature})


def write_evidence(
    repo: Path,
    payload: EvidenceArtifactPayload,
    *,
    authority: AttestationAuthority | None = TEST_AUTHORITY,
    evidence_name: str = "m05.json",
    receipt_name: str = "m05_receipt.json",
    **receipt_overrides: object,
) -> dict[str, object]:
    """Write the artifact + receipt files and return the ledger entry dict."""

    (repo / "evidence").mkdir(exist_ok=True)
    evidence_path = repo / "evidence" / evidence_name
    evidence_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    file_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    receipt = build_receipt(
        payload, file_sha256=file_sha256, authority=authority, **receipt_overrides
    )
    (repo / "evidence" / receipt_name).write_text(
        json.dumps(json.loads(receipt.model_dump_json()), indent=2), encoding="utf-8"
    )
    return {
        "path": f"evidence/{evidence_name}",
        "kind": payload.evidence_kind.value,
        "description": f"{payload.evidence_kind.value} report",
        "content_sha256": file_sha256,
        "artifact_schema": SCHEMA_BY_KIND[payload.evidence_kind],
        "run_receipt": f"evidence/{receipt_name}",
    }


def make_git_repo(repo: Path) -> tuple[str, str]:
    """Initialise ``repo`` as a git repository with one commit.

    The commit binding is only meaningful when the validator can resolve the
    named commit *in the repository it is validating*, so a test that exercises
    it needs a real object database rather than a bare directory.
    """

    env = {
        "GIT_AUTHOR_NAME": "cpswm-test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "cpswm-test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "PATH": os.environ.get("PATH", ""),
    }
    for argv in (
        ["git", "-C", str(repo), "init", "-q", "-b", "main"],
        ["git", "-C", str(repo), "add", "-A"],
        ["git", "-C", str(repo), "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(argv, check=True, capture_output=True, env=env, timeout=30)
    return head_commit_and_snapshot(repo)


def make_source_tree(repo: Path) -> None:
    """A minimal implementation + test pair so path checks are satisfied."""

    (repo / "src").mkdir(exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_mod.py").write_text("def test_x(): pass\n", encoding="utf-8")
