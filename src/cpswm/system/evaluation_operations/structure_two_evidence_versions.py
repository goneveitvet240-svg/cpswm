"""Separate local Git history from source-bound, post-open P5 recomputation.

Git proves retained bytes relative to this checkout's history. Neither Git nor
an unkeyed digest proves execution time, first access, or independent custody.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from cpswm.system.reproducibility import content_sha256

HISTORY_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_evidence_history_v0_1.json"
)
CURRENT_DIRECTORY: Final = Path("benchmarks/structure_two/evidence_repair_2026_09_11/current")
COMMON_BASE: Final = "09eb4d48e1c11082e90ca18332d04333e6b5b47a"


_RUNTIME_ROOT: Final = Path(__file__).resolve().parents[4]


def _execution_inventory(root: Path) -> dict[str, str]:
    paths = [*root.glob("src/cpswm/**/*.py"), *root.glob("configs/**/*.json")]
    paths.extend(root / name for name in ("pyproject.toml", "uv.lock"))
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


_RUNTIME_INVENTORY: Final = _execution_inventory(_RUNTIME_ROOT)


def require_execution_source(root: Path) -> None:
    """Refuse to attest changed on-disk source using an already imported runtime."""
    if root.resolve() != _RUNTIME_ROOT or _execution_inventory(root) != _RUNTIME_INVENTORY:
        raise ValueError("execution source changed since process import; start a fresh process")


def current_evidence_context() -> dict[str, Any]:
    return {
        "artifact_version": "0.2",
        "lifecycle": "POST_OPEN_CURRENT_SOURCE_REPLAY",
        "first_execution_established": False,
        "previously_unseen_established": False,
        "confirmatory": False,
        "independent_custody_established": False,
        "historical_results_superseded": False,
        "common_base_commit": COMMON_BASE,
        "source_identity": "source_binding.production_assembly_manifest_sha256",
        "run_identity_is_semantic_identity": False,
    }


def require_current_output(root: Path, output: Path) -> Path:
    """Fail before execution if a CLI could overwrite historical evidence."""
    root = root.resolve()
    target = output if output.is_absolute() else root / output
    expected_parent = root / CURRENT_DIRECTORY
    if not target.resolve().is_relative_to(expected_parent) or any(
        p.is_symlink() for p in (target, *target.parents) if p.is_relative_to(root)
    ):
        raise ValueError("current output must stay in the versioned current evidence directory")
    return target


def historical_entries(root: Path) -> list[dict[str, str]]:
    payload = json.loads((root / HISTORY_CONFIG).read_text(encoding="utf-8"))
    entries: list[dict[str, str]] = payload["entries"]
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("historical evidence id duplicated")
    return entries


def git_bytes(root: Path, commit: str, path: str) -> bytes:
    if (
        len(commit) != 40
        or any(c not in "0123456789abcdef" for c in commit)
        or Path(path).is_absolute()
        or ".." in Path(path).parts
    ):
        raise ValueError("unsafe historical Git reference")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, COMMON_BASE], cwd=root, check=True
    )
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=root)


def verify_historical_record(root: Path, entry: Mapping[str, str]) -> dict[str, Any]:
    """Check exact Git bytes and self-consistency, without granting currentness."""
    path = root / entry["path"]
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("historical artifact path is not local")
    expected = git_bytes(root, entry["record_commit"], entry["git_path"])
    if path.read_bytes() != expected:
        raise ValueError("historical artifact differs from pinned Git record")
    payload = json.loads(expected)
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != content_sha256(unsigned):
        raise ValueError("historical artifact content hash mismatch")
    return {
        "id": entry["id"],
        "record_commit": entry["record_commit"],
        "artifact_content_sha256": payload["content_sha256"],
        "local_git_bytes_verified": True,
        "content_self_consistency_verified": True,
        "current_source_recomputation_verified": False,
        "first_execution_established": False,
        "independent_custody_established": False,
    }


def require_frozen_p5_inputs(root: Path) -> None:
    """Do not let rewriting a trigger and its expected hash replace old evidence."""
    paths = sorted(root.glob("configs/project_two_experiments/structure_two_p5*_v0_1.json"))
    paths.extend(
        root / path
        for path in (
            "configs/project_two_datasets/d0_multiseed_readout_v0_5.json",
            "configs/project_two_datasets/d0_unseen_p5_holdout_v0_6.json",
            "configs/project_two_experiments/structure_two_action_readout_v0_6_preregistration.json",
            "benchmarks/structure_two/structure_two_p5_readout_posthoc_diagnostic_v0_1.json",
        )
    )
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if path.read_bytes() != git_bytes(root, COMMON_BASE, relative):
            raise ValueError(f"frozen P5 input differs from common-base Git record: {relative}")
    failed = "benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json"
    commit = "4103bea1942bf1541d574103de5fcf136f50ce1e"
    if (root / failed).read_bytes() != git_bytes(root, commit, failed):
        raise ValueError("retained failed replay differs from pinned historical Git record")
