"""Trusted CLI-side loader for the comparison audit, using only the Python stdlib.

The CLI compiles this sibling file directly, before importing any project code.
This guard never asks an already imported cpswm module to authenticate itself.
The trust boundary is the invoked CLI, Python/stdlib and process integrity; this
is not an independently signed source release or protection from arbitrary code
execution inside the interpreter.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import marshal
import sys
from pathlib import Path
from types import CodeType, ModuleType


class ExecutionSourceError(RuntimeError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ExecutionSource(importlib.abc.MetaPathFinder):
    def __init__(self, cli: str, entry_code: CodeType, guard_bytes: bytes):
        self.cli = Path(cli).resolve()
        self.root = self.cli.parents[2]
        self.guard_file = self.cli.with_name("_structure_two_audit_source.py")
        if self.cli.name not in {
            "run_structure_two_comparison_audit.py",
            "summarize_structure_two_comparison_audit.py",
        }:
            raise ExecutionSourceError(f"UNRECOGNIZED_CLI: {self.cli}")
        if Path(entry_code.co_filename).resolve() != self.cli:
            raise ExecutionSourceError(f"CLI_ORIGIN_MISMATCH: {entry_code.co_filename}")
        expected_entry = compile(
            self.cli.read_bytes(), entry_code.co_filename, "exec", dont_inherit=True
        )
        if entry_code != expected_entry:
            raise ExecutionSourceError(f"CLI_CODE_DIFFERS_FROM_SOURCE: {self.cli}")
        if self.guard_file.read_bytes() != guard_bytes:
            raise ExecutionSourceError(f"GUARD_SOURCE_CHANGED: {self.guard_file}")
        preloaded = sorted(n for n in sys.modules if n == "cpswm" or n.startswith("cpswm."))
        if preloaded:
            details = {n: str(getattr(sys.modules[n], "__file__", None)) for n in preloaded}
            raise ExecutionSourceError(f"PRELOADED_LOCAL_MODULES: {details}")
        self.sources = self._read_sources()
        self.records: dict[str, dict] = {}
        self.modules: dict[str, ModuleType] = {}
        self.loaders: dict[str, CapturedSourceLoader] = {}
        # Resolve actual import selection, not the spelling of PYTHONPATH.
        self._resolve("cpswm", None)
        sys.meta_path.insert(0, self)

    def _read_sources(self) -> dict[Path, bytes]:
        paths = set((self.root / "src").rglob("*.py"))
        paths.update((self.root / "configs").rglob("*.json"))
        paths.update(
            self.cli.parent / name
            for name in (
                "run_structure_two_comparison_audit.py",
                "summarize_structure_two_comparison_audit.py",
                "_structure_two_audit_source.py",
            )
        )
        result = {}
        for path in sorted(paths):
            if path.resolve() != path:
                raise ExecutionSourceError(f"LOCAL_SOURCE_SYMLINK: {path} -> {path.resolve()}")
            result[path] = path.read_bytes()
        return result

    def require_root(self, root: Path) -> None:
        if root.resolve() != self.root:
            raise ExecutionSourceError(
                f"REPOSITORY_ROOT_MISMATCH: declared={root.resolve()} executing={self.root}"
            )

    def _resolve(self, fullname: str, path):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        base = self.root / "src" / Path(*fullname.split("."))
        expected = (
            base / "__init__.py"
            if (base / "__init__.py") in self.sources
            else base.with_suffix(".py")
        )
        origin = Path(spec.origin).resolve() if spec and spec.origin else None
        if origin != expected or expected not in self.sources:
            raise ExecutionSourceError(
                f"LOCAL_IMPORT_ORIGIN_MISMATCH: module={fullname} "
                f"expected={expected} actual={origin}"
            )
        return spec, expected

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "cpswm" and not fullname.startswith("cpswm."):
            return None
        spec, expected = self._resolve(fullname, path)
        loader = CapturedSourceLoader(self, fullname, expected)
        self.loaders[fullname] = loader
        # Preserve package locations, but never execute PathFinder's loader/pyc.
        return importlib.util.spec_from_file_location(
            fullname,
            expected,
            loader=loader,
            submodule_search_locations=list(spec.submodule_search_locations)
            if spec.submodule_search_locations is not None
            else None,
        )

    def check_file(self, path: Path) -> None:
        if path.resolve() != path or path.read_bytes() != self.sources[path]:
            raise ExecutionSourceError(f"EXECUTION_SOURCE_DRIFT: {path}")

    def checkpoint(self) -> None:
        if self not in sys.meta_path or sys.meta_path[0] is not self:
            raise ExecutionSourceError("LOCAL_IMPORT_GUARD_REPLACED")
        changed = self._read_sources()
        if changed != self.sources:
            paths = sorted(
                p
                for p in self.sources.keys() | changed.keys()
                if self.sources.get(p) != changed.get(p)
            )
            raise ExecutionSourceError(f"EXECUTION_SOURCE_DRIFT: {paths[:5]}")
        names = {n for n in sys.modules if n == "cpswm" or n.startswith("cpswm.")}
        if names != set(self.modules):
            raise ExecutionSourceError(
                f"UNTRACKED_LOCAL_MODULES: {sorted(names ^ self.modules.keys())}"
            )
        for name, module in self.modules.items():
            loader = self.loaders[name]
            spec = getattr(module, "__spec__", None)
            if (
                sys.modules.get(name) is not module
                or spec is None
                or spec.loader is not loader
                or getattr(module, "__file__", None) != str(loader.path)
                or spec.origin != str(loader.path)
                or (
                    spec.submodule_search_locations is not None
                    and list(getattr(module, "__path__", [])) != [str(loader.path.parent)]
                )
            ):
                raise ExecutionSourceError(f"LOADED_MODULE_IDENTITY_CHANGED: {name}")

    def require_bindings(self, claimed: dict[str, str]) -> None:
        """Tie the replay's declared hashes directly to the bytes actually loaded.

        Disk checks alone cannot establish this relationship if files change
        between phases. This comparison is owned by the CLI-side loader.
        """
        for path, raw in self.sources.items():
            relative = path.relative_to(self.root).as_posix()
            if claimed.get(relative) != digest(raw):
                raise ExecutionSourceError(f"EXECUTED_BYTES_BINDING_MISMATCH: {relative}")

    def identity(self) -> dict:
        self.checkpoint()
        return {
            "policy": "captured_local_source_compilation_v1",
            "declared_root": str(self.root),
            "cli": str(self.cli),
            "cli_sha256": digest(self.sources[self.cli]),
            "guard_sha256": digest(self.sources[self.guard_file]),
            "interpreter": sys.executable,
            "python": sys.version,
            "local_bytecode_cache_used": False,
            "preloaded_local_modules_allowed": False,
            "loaded_modules": dict(sorted(self.records.items())),
            "scope": "cpswm imports and entry source; trusted Python/stdlib and process integrity",
        }


class CapturedSourceLoader(importlib.abc.Loader):
    def __init__(self, guard: ExecutionSource, name: str, path: Path):
        self.guard, self.name, self.path = guard, name, path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        self.guard.check_file(self.path)
        raw = self.guard.sources[self.path]
        code = compile(raw, str(self.path), "exec", dont_inherit=True)
        self.guard.modules[self.name] = module
        self.guard.records[self.name] = {
            "path": str(self.path.relative_to(self.guard.root)),
            "source_sha256": digest(raw),
            "compiled_code_sha256": digest(marshal.dumps(code)),
        }
        exec(code, module.__dict__)
        self.guard.check_file(self.path)


def bootstrap(cli: str, entry_code: CodeType, guard_bytes: bytes) -> ExecutionSource:
    return ExecutionSource(cli, entry_code, guard_bytes)
