"""Runtime provenance resolution and strict replay verification."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from cpswm.foundation.persistence_replay import (
    AppendOnlyTransactionLog,
    ExecutionMode,
    ReplayManifest,
)
from cpswm.foundation.persistence_replay.contracts import content_hash

from .contracts import VersionBundle


class RuntimeProvenanceError(ValueError):
    """Raised when declared replay provenance differs from the running code."""


def source_tree_sha256(repository_root: str | Path) -> str:
    root = Path(repository_root).resolve()
    candidates = list((root / "src").rglob("*.py"))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        candidates.append(pyproject)
    digest = hashlib.sha256()
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if not candidates:
        raise RuntimeProvenanceError(f"no source files found below {root}")
    return digest.hexdigest()


def git_head_code_version(repository_root: str | Path) -> str:
    root = Path(repository_root).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeProvenanceError("cannot resolve the repository Git HEAD") from error
    revision = result.stdout.strip()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise RuntimeProvenanceError("Git HEAD is not a full 40-character SHA")
    return f"git:{revision}"


def build_version_bundle(
    repository_root: str | Path,
    *,
    configuration: JsonValue,
    model_versions: dict[str, str],
) -> VersionBundle:
    return VersionBundle(
        code_version=git_head_code_version(repository_root),
        source_tree_sha256=source_tree_sha256(repository_root),
        configuration_hash=content_hash(configuration),
        model_versions=model_versions,
    )


def build_replay_manifest(
    input_log: AppendOnlyTransactionLog,
    *,
    versions: VersionBundle,
    schema_version: str,
    random_seed: int,
    created_at: datetime,
    numeric_tolerance: float = 0.0,
    through_commit_seq: int | None = None,
) -> ReplayManifest:
    through = (
        input_log.latest_watermark().global_commit_seq
        if through_commit_seq is None
        else through_commit_seq
    )
    return ReplayManifest(
        input_watermark=input_log.watermark_at(through),
        input_log_sha256=input_log.fingerprint(through_commit_seq=through),
        schema_version=schema_version,
        code_version=versions.code_version,
        source_tree_sha256=versions.source_tree_sha256,
        model_versions=versions.model_versions,
        configuration_hash=versions.configuration_hash,
        random_seed=random_seed,
        execution_mode=ExecutionMode.REPLAY,
        numeric_tolerance=numeric_tolerance,
        created_at=created_at,
    )


def verify_replay_provenance(
    manifest: ReplayManifest,
    *,
    runtime_versions: VersionBundle,
    repository_root: str | Path | None,
    active_configuration: JsonValue | None,
) -> None:
    if manifest.execution_mode != ExecutionMode.REPLAY:
        raise RuntimeProvenanceError("ReplayRunner requires execution_mode=replay")
    if repository_root is None or active_configuration is None:
        raise RuntimeProvenanceError(
            "strict replay requires repository_root and active_configuration"
        )
    actual = build_version_bundle(
        repository_root,
        configuration=active_configuration,
        model_versions=runtime_versions.model_versions,
    )
    if runtime_versions != actual:
        raise RuntimeProvenanceError(
            "runtime VersionBundle does not match the running source/configuration"
        )
    expected_fields = (
        "code_version",
        "source_tree_sha256",
        "configuration_hash",
        "model_versions",
    )
    for field_name in expected_fields:
        if getattr(manifest, field_name) != getattr(runtime_versions, field_name):
            raise RuntimeProvenanceError(
                f"ReplayManifest {field_name} does not match the active runtime"
            )
