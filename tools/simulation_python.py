"""Run isolated simulation modules with explicit, relocatable vendor paths.

LIBERO's top-level package is a namespace omitted by its setup.py find_packages.
Explicit paths also avoid depending on .pth processing (hidden files are skipped
by recent CPython on macOS). Upstream source is never patched by this launcher.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT.parent


def main() -> None:
    expected = (STACK / "envs/libero").resolve()
    if Path(sys.prefix).resolve() != expected:
        raise RuntimeError(f"Use {expected}/bin/python; actual prefix is {sys.prefix}")
    paths = [
        ROOT / "src",
        STACK / "vendor/openpi/src",
        STACK / "vendor/openpi/packages/openpi-client/src",
        STACK / "vendor/openpi/third_party/libero",
        STACK / "vendor/sam2",
    ]
    for path in paths:
        if not path.is_dir():
            raise FileNotFoundError(path)
    sys.path[:0] = list(map(str, paths))
    for key, suffix in {
        "MPLCONFIGDIR": "matplotlib",
        "NUMBA_CACHE_DIR": "numba",
        "HF_HOME": "huggingface",
        "OPENPI_DATA_HOME": "openpi",
    }.items():
        os.environ.setdefault(key, str(STACK / "cache" / suffix))
    os.environ.setdefault("JAX_PLATFORMS", "cpu")
    if len(sys.argv) < 2:
        raise SystemExit("usage: simulation_python.py [-m MODULE | SCRIPT] [ARGS...]")
    sys.argv = sys.argv[1:]
    if sys.argv[0] == "-m":
        sys.argv = sys.argv[1:]
        runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)
    else:
        runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
