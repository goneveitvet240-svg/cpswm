"""Fail-closed, atomic output handling for protocol report CLIs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class ProtectedReportOutputError(ValueError):
    """Raised when a report output targets protected protocol input assets."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def write_report_atomic(
    rendered: str,
    *,
    output_path: Path,
    config_path: Path,
    repository_root: Path,
    force: bool = False,
) -> Path:
    """Write a complete report atomically without risking benchmark assets.

    ``benchmarks/`` is immutable through these CLIs, output may never alias the
    input config, and an existing output requires an explicit ``force=True``.
    The no-force path uses an atomic hard-link publish, so a concurrent creator
    cannot be silently overwritten between the existence check and publish.
    """

    output = output_path.resolve(strict=False)
    config = config_path.resolve(strict=False)
    benchmarks = (repository_root / "benchmarks").resolve(strict=False)
    if output == config:
        raise ProtectedReportOutputError("output path must not equal the input config path")
    if _is_within(output, benchmarks):
        raise ProtectedReportOutputError("report output under benchmarks/ is protected")
    if output.exists() and not force:
        raise FileExistsError(f"output already exists; pass --force to replace it: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o644)
        if force:
            os.replace(temporary_path, output)
            temporary_path = None
        else:
            try:
                os.link(temporary_path, output)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"output already exists; pass --force to replace it: {output}"
                ) from exc
        return output
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
