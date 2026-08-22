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


#: Directories whose ``.py`` files determine executable behaviour.
PROVENANCE_CODE_DIRECTORIES: tuple[str, ...] = ("src", "apps")
#: Directories whose data assets act as benchmark authority anchors.
PROVENANCE_ASSET_DIRECTORIES: tuple[str, ...] = ("benchmarks",)
#: Individual files that configure the build or dependency set.
PROVENANCE_ROOT_FILES: tuple[str, ...] = ("pyproject.toml",)

#: Marker appended to ``code_version`` when the working tree is not clean.
DIRTY_WORKING_TREE_SUFFIX = "+dirty"
#: ``code_version`` used when the tree carries no resolvable Git identity.
UNVERSIONED_CODE_VERSION = "unversioned:no-git"


def provenance_files(repository_root: str | Path) -> tuple[Path, ...]:
    """Return every file whose content is bound into ``source_tree_sha256``.

    Coverage spans executable code (``src``, ``apps``) *and* the checked-in
    benchmark assets that act as evaluation authority anchors.  Binding only
    ``src`` would let an entry-point script or a manifest asset change without
    changing the recorded source identity.
    """

    root = Path(repository_root).resolve()
    candidates: list[Path] = []
    for directory in PROVENANCE_CODE_DIRECTORIES:
        candidates.extend((root / directory).rglob("*.py"))
    for directory in PROVENANCE_ASSET_DIRECTORIES:
        candidates.extend((root / directory).rglob("*.json"))
    for name in PROVENANCE_ROOT_FILES:
        path = root / name
        if path.is_file():
            candidates.append(path)
    covered = [
        path
        for path in candidates
        if path.is_file() and "__pycache__" not in path.relative_to(root).parts
    ]
    return tuple(sorted(covered, key=lambda item: item.relative_to(root).as_posix()))


def is_provenance_path(repository_root: str | Path, relative_path: str) -> bool:
    """Return whether ``relative_path`` contributes to ``source_tree_sha256``."""

    root = Path(repository_root).resolve()
    return (root / relative_path).resolve() in {path.resolve() for path in provenance_files(root)}


def source_tree_sha256(repository_root: str | Path) -> str:
    root = Path(repository_root).resolve()
    candidates = provenance_files(root)
    if not candidates:
        raise RuntimeProvenanceError(f"no source files found below {root}")
    digest = hashlib.sha256()
    for path in candidates:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 of a single file's bytes."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_working_tree_dirty(repository_root: str | Path) -> bool:
    """Return whether any provenance-covered file differs from Git HEAD.

    Documentation and scratch files are ignored on purpose: they cannot change
    ``source_tree_sha256`` and therefore cannot change behaviour.  Any change to
    a covered path makes the recorded ``code_version`` a claim about a commit
    the running code is not actually on, so it must be reported.
    """

    root = Path(repository_root).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeProvenanceError("cannot resolve the repository working-tree state") from error
    for line in result.stdout.splitlines():
        entry = line[3:].strip() if len(line) > 3 else ""
        if not entry:
            continue
        # Renames are reported as "old -> new"; both sides matter.
        for candidate in entry.split(" -> "):
            cleaned = candidate.strip().strip('"')
            if cleaned and is_provenance_path(root, cleaned):
                return True
    return False


def git_head_code_version(repository_root: str | Path) -> str:
    """Return the Git identity of the running tree, marked when it is dirty.

    A bare commit SHA recorded from a modified working tree is a false claim:
    a reviewer checking out that commit will not obtain the code that produced
    the artifact.  The dirty marker keeps the record honest instead.
    """

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
    suffix = DIRTY_WORKING_TREE_SUFFIX if git_working_tree_dirty(root) else ""
    return f"git:{revision}{suffix}"


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


#: VersionBundle fields this module can measure from the running tree.
MEASURED_VERSION_FIELDS: tuple[str, ...] = (
    "code_version",
    "source_tree_sha256",
    "configuration_hash",
)
#: VersionBundle fields the caller declares and this module cannot measure.
DECLARED_VERSION_FIELDS: tuple[str, ...] = ("model_versions",)


def verify_replay_provenance(
    manifest: ReplayManifest,
    *,
    runtime_versions: VersionBundle,
    repository_root: str | Path | None,
    active_configuration: JsonValue | None,
    model_version_registry: dict[str, str] | None = None,
) -> None:
    """Verify measured provenance and, when possible, declared model versions.

    ``MEASURED_VERSION_FIELDS`` are recomputed from the running tree, so a
    mismatch is detectable without trusting the caller.  ``model_versions``
    cannot be measured from source alone: without ``model_version_registry`` it
    is only checked for manifest/runtime *consistency* and remains a
    self-declared field.  Supply a registry to turn it into a verified one.
    """

    if manifest.execution_mode != ExecutionMode.REPLAY:
        raise RuntimeProvenanceError("ReplayRunner requires execution_mode=replay")
    if repository_root is None or active_configuration is None:
        raise RuntimeProvenanceError(
            "strict replay requires repository_root and active_configuration"
        )
    # Measure independently: do not seed the comparison with caller-supplied
    # values, or the corresponding fields can never disagree.
    measured = build_version_bundle(
        repository_root,
        configuration=active_configuration,
        model_versions={},
    )
    for field_name in MEASURED_VERSION_FIELDS:
        if getattr(runtime_versions, field_name) != getattr(measured, field_name):
            raise RuntimeProvenanceError(
                f"runtime VersionBundle {field_name} does not match the running "
                "source/configuration"
            )
    if model_version_registry is not None:
        for name, declared in runtime_versions.model_versions.items():
            if model_version_registry.get(name) != declared:
                raise RuntimeProvenanceError(
                    f"declared model version for {name!r} is not in the trusted registry"
                )
        for name in model_version_registry:
            if name not in runtime_versions.model_versions:
                raise RuntimeProvenanceError(
                    f"runtime VersionBundle omits registered model {name!r}"
                )
    for field_name in (*MEASURED_VERSION_FIELDS, *DECLARED_VERSION_FIELDS):
        if getattr(manifest, field_name) != getattr(runtime_versions, field_name):
            raise RuntimeProvenanceError(
                f"ReplayManifest {field_name} does not match the active runtime"
            )
