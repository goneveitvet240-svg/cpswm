"""Trusted local entry bootstrap: compile frozen project source, never consume pyc.

This module uses only stdlib. Entry points compile its bytes before importing any
cpswm dependency. It is a local execution guard, not an attestation service.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path

STATE_MODULE = "_cpswm_source_bootstrap"


def inventory(root: Path) -> dict[str, bytes]:
    paths = [
        *root.glob("src/cpswm/**/*.py"),
        *root.glob("configs/**/*.json"),
        *root.glob("apps/**/*.py"),
    ]
    paths.extend(root / name for name in ("pyproject.toml", "uv.lock"))
    if (root / "conftest.py").exists():
        paths.append(root / "conftest.py")
    # rglob does not descend through directory symlinks; reject those explicitly.
    for directory in (root / "src/cpswm", root / "configs", root / "apps"):
        if directory.exists():
            for path in (directory, *directory.rglob("*")):
                if path.is_symlink():
                    raise ValueError("execution source refuses symlinks")
    result = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise ValueError("execution source requires regular local files")
        result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


class FrozenSourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.pid = os.getpid()
        self.sources = inventory(self.root)
        self.loaded = {}
        self.digest = hashlib.sha256(
            json.dumps(
                {p: hashlib.sha256(b).hexdigest() for p, b in self.sources.items()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "cpswm" and not fullname.startswith("cpswm."):
            return None
        stem = "src/" + fullname.replace(".", "/")
        package = stem + "/__init__.py"
        relative = package if package in self.sources else stem + ".py"
        if relative not in self.sources:
            raise ImportError(f"project module is absent from frozen source: {fullname}")
        return importlib.util.spec_from_file_location(
            fullname,
            self.root / relative,
            loader=self,
            submodule_search_locations=[str(self.root / stem)] if relative == package else None,
        )

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path = Path(module.__spec__.origin)
        relative = path.relative_to(self.root).as_posix()
        source = self.sources[relative]
        if path.is_symlink() or path.read_bytes() != source:
            raise ValueError("execution source changed before module loading")
        # compile consumes precisely the snapshotted bytes, not timestamp-based pyc.
        code = compile(source, str(path), "exec", dont_inherit=True)
        self.loaded[module.__name__] = (module, relative)
        exec(code, module.__dict__)

    def execute_application(self, module, path: Path) -> None:
        self.require(self.root)
        relative = path.relative_to(self.root).as_posix()
        if not relative.startswith("apps/") or relative not in self.sources:
            raise ValueError("application helper is outside frozen source")
        exec(compile(self.sources[relative], str(path), "exec", dont_inherit=True), module.__dict__)
        self.require(self.root)

    def require(self, root: Path) -> dict[str, str]:
        if os.getpid() != self.pid or root.resolve() != self.root:
            raise ValueError("formal execution source belongs to another process or root")
        if not any(item is self for item in sys.meta_path):
            raise ValueError("formal source loader was removed")
        if inventory(self.root) != self.sources:
            raise ValueError("execution source changed since formal bootstrap")
        for name, module in tuple(sys.modules.items()):
            if (name == "cpswm" or name.startswith("cpswm.")) and (
                name not in self.loaded or self.loaded[name][0] is not module
            ):
                raise ValueError("project module was not loaded by the formal source loader")
        return {"policy": "frozen-source-compile-no-pyc@1", "inventory_sha256": self.digest}


def establish(root: Path) -> FrozenSourceLoader:
    existing = globals().get("guard")
    if existing is not None:
        existing.require(root)
        return existing
    if any(name == "cpswm" or name.startswith("cpswm.") for name in sys.modules):
        raise ValueError("formal bootstrap must precede every project dependency import")
    guard = FrozenSourceLoader(root)
    globals()["guard"] = guard
    sys.meta_path.insert(0, guard)
    return guard
