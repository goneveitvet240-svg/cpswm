"""Trusted process configuration for content-addressed neural checkpoint files.

An evidence record can name an artifact, but cannot register a filesystem path.
The configured producer supplies the directory; moving identical bytes does not
change model identity. This is local deployment configuration, not a signature.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from threading import RLock

_LOCK = RLock()
_ARTIFACT_DIRECTORIES: dict[str, Path] = {}


def checkpoint_artifact_id(manifest_sha256: str) -> str:
    if type(manifest_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None:
        raise ValueError("checkpoint artifact requires a manifest SHA256")
    return "sha256:" + manifest_sha256


def register_checkpoint_artifact(directory: Path, *, manifest_sha256: str) -> str:
    """Called by trusted producer construction after loading its actual model.

    Recheck file content before replacing an older location. Failed registration
    leaves an existing good mapping intact. The consumer rechecks bytes on use.
    """
    key = checkpoint_artifact_id(manifest_sha256)
    directory = directory.resolve(strict=True)
    data = (directory / "manifest.json").read_bytes()
    if sha256(data).hexdigest() != manifest_sha256:
        raise ValueError("configured checkpoint manifest changed")
    descriptor = json.loads(data)
    if sha256((directory / "weights.pt").read_bytes()).hexdigest() != descriptor["weights_sha256"]:
        raise ValueError("configured checkpoint weights changed")
    with _LOCK:
        _ARTIFACT_DIRECTORIES[key] = directory
    return key


def resolve_checkpoint_artifact(reference: str, *, manifest_sha256: str) -> Path:
    """No path in the proof, path search, network download or implicit fallback."""
    expected = checkpoint_artifact_id(manifest_sha256)
    if reference != expected:
        raise ValueError("checkpoint artifact reference differs from its manifest")
    with _LOCK:
        directory = _ARTIFACT_DIRECTORIES.get(expected)
        if directory is None:
            raise ValueError("checkpoint artifact is not configured in this process")
        return directory
