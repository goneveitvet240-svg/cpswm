"""Publish a fully verified JSON without replacing or truncating any existing inode."""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from cpswm.system.evaluation_operations.structure_two_evidence_versions import (
    require_current_output,
    require_execution_source,
)


def _open_parent(root: Path, target: Path) -> int:
    relative = target.relative_to(root)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            with suppress(FileExistsError):
                os.mkdir(component, dir_fd=fd)
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _same_parent(root: Path, target: Path, held: int) -> None:
    fresh = _open_parent(root, target)
    try:
        a, b = os.fstat(held), os.fstat(fresh)
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
            raise ValueError("publication parent changed after validation")
    finally:
        os.close(fresh)


def publish_verified_json(
    root: Path,
    output: Path,
    payload: Mapping[str, Any],
    *,
    verify: Callable[[Mapping[str, Any]], None],
) -> Path:
    """Verify first; fsync a new inode; link it atomically with no replacement.

    Existing targets (including identical files and hard links) always fail.
    A killed process may leave a hidden .partial file, never a partial .json.
    Held directory descriptors prevent a path swap from redirecting writes.
    """
    root = root.resolve()
    target = require_current_output(root, output)
    require_execution_source(root)
    raw = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    verify(json.loads(raw))
    require_execution_source(root)
    target = require_current_output(root, output)
    fd = _open_parent(root, target)
    temporary = ".partial-" + uuid.uuid4().hex
    inode: tuple[int, int] | None = None
    linked = False
    try:
        file_fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(file_fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("publication staging inode is not a regular file")
            inode = (info.st_dev, info.st_ino)
        require_execution_source(root)
        require_current_output(root, target)
        _same_parent(root, target, fd)
        os.link(temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        linked = True
        _same_parent(root, target, fd)
        require_execution_source(root)
        published = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        if (published.st_dev, published.st_ino) != inode:
            raise ValueError("publication target changed before completion")
        os.fsync(fd)
        return target
    except BaseException:
        if linked:
            try:
                current = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == inode:
                    os.unlink(target.name, dir_fd=fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=fd)
        os.close(fd)
