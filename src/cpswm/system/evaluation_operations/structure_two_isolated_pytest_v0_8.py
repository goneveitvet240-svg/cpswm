"""Start verifier-owned pytest without Python startup customization hooks."""

from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from collections.abc import Mapping, Sequence
from pathlib import Path

_BOOTSTRAP = """
import pathlib
import sys

runtime_root = pathlib.Path(sys.argv[1]).resolve(strict=True)
trusted_source_root = sys.argv[2]
sys.path.insert(0, str(runtime_root))
import pytest

if trusted_source_root:
    sys.path.insert(0, str(pathlib.Path(trusted_source_root).resolve(strict=True)))
raise SystemExit(pytest.main(sys.argv[3:]))
""".strip()


def isolated_pytest_environment(
    *,
    temporary_directory: Path,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an allowlisted environment with all pytest/Python hook inputs reset."""

    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_ADDOPTS": "",
        "PYTEST_PLUGINS": "",
        "PYTHONPATH": "",
        "PYTHONSTARTUP": "",
        "TMPDIR": str(temporary_directory),
    }
    for name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if extra:
        protected_names = frozenset(environment)
        if any(name in protected_names or name.startswith(("PYTHON", "PYTEST")) for name in extra):
            raise ValueError("isolated pytest control environment cannot be overridden")
        environment.update(extra)
    return environment


def run_isolated_pytest_v0_8(
    *,
    nodes: Sequence[str],
    working_directory: Path,
    junit_path: Path,
    timeout_seconds: int,
    trusted_source_root: Path | None = None,
    extra_environment: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run pytest under ``-I -S`` before adding any repository-controlled path.

    ``-S`` prevents ``site``, ``.pth``, ``sitecustomize`` and ``usercustomize``
    processing. ``-I`` additionally ignores Python environment/path injection.
    Pytest is imported from the interpreter's installation directory before the
    separately supplied, verifier-owned source root is placed on ``sys.path``.
    """

    runtime_root = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    if not (runtime_root / "pytest" / "__init__.py").is_file():
        raise ValueError("isolated pytest runtime package is unavailable")
    source_argument = (
        str(trusted_source_root.resolve(strict=True)) if trusted_source_root is not None else ""
    )
    arguments = (
        "-vv" if verbose else "-q",
        "-p",
        "no:cacheprovider",
        "--noconftest",
        "-c",
        os.devnull,
        *nodes,
        "--junitxml",
        str(junit_path),
    )
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            _BOOTSTRAP,
            str(runtime_root),
            source_argument,
            *arguments,
        ),
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env=isolated_pytest_environment(
            temporary_directory=working_directory,
            extra=extra_environment,
        ),
    )


__all__ = [
    "isolated_pytest_environment",
    "run_isolated_pytest_v0_8",
]
