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

_BOOTSTRAP_CODE = sys._getframe().f_code
STATE_MODULE = "_cpswm_source_bootstrap"
FORMAL_ENTRIES = frozenset(
    {
        "conftest.py",
        "apps/evaluation_runner/probe_structure_two_execution_source.py",
        "apps/evaluation_runner/run_structure_two_evidence_repair.py",
        "apps/evaluation_runner/audit_structure_two_evidence_history.py",
        "apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py",
        *(
            f"apps/evaluation_runner/run_structure_two_p5_{name}.py"
            for name in (
                "three_arm_death_test",
                "readout_posthoc_diagnostic",
                "debt_replay_confirmation",
                "readout_prior_factorial",
                "unseen_d0_holdout",
            )
        ),
    }
)


def require_entry(frame, loader) -> None:
    """Check the executing module code, including nested functions, before identity.

    File, -m, runpy and spawn may execute the same module code. The launch
    mechanism is not authority: the actual frame must equal captured compilation.
    Caller-selected strings (-c), foreign filenames and unchecked stale pyc fail.
    Python/stdlib and in-process integrity remain trusted.
    """
    bootstrap = "apps/evaluation_runner/structure_two_source_bootstrap.py"
    if (
        compile(loader.sources[bootstrap], _BOOTSTRAP_CODE.co_filename, "exec", dont_inherit=True)
        != _BOOTSTRAP_CODE
    ):
        raise ValueError("formal bootstrap executing loader differs from frozen source")
    filename = frame.f_code.co_filename
    if filename.startswith("<"):
        raise ValueError("formal bootstrap refuses unsupported execution entry")
    path = Path(filename).absolute()
    try:
        relative = path.relative_to(loader.root).as_posix()
    except ValueError as error:
        raise ValueError("formal bootstrap refuses foreign execution entry") from error
    if (
        relative not in FORMAL_ENTRIES
        or frame.f_code.co_name != "<module>"
        or Path(frame.f_globals.get("__file__", "")).absolute() != path
        or frame.f_code != compile(loader.sources[relative], filename, "exec", dont_inherit=True)
    ):
        raise ValueError("formal bootstrap executing entry differs from frozen source")


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
        self.entry_verified = False
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
        if not self.entry_verified:
            raise ValueError("formal bootstrap entry has not been verified")
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
        return {"policy": "frozen-source-and-entry-compile@2", "inventory_sha256": self.digest}


def establish(root: Path) -> FrozenSourceLoader:
    existing = globals().get("guard")
    if existing is not None:
        require_entry(sys._getframe(1), existing)
        existing.require(root)
        return existing
    if any(name == "cpswm" or name.startswith("cpswm.") for name in sys.modules):
        raise ValueError("formal bootstrap must precede every project dependency import")
    guard = FrozenSourceLoader(root)
    require_entry(sys._getframe(1), guard)
    guard.entry_verified = True
    globals()["guard"] = guard
    sys.meta_path.insert(0, guard)
    return guard
