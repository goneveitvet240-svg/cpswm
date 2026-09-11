"""Establish source loading before tests/conftest imports project dependencies."""

# Establish execution provenance before importing project dependencies.
import sys
import types
from pathlib import Path

_bootstrap_path = (
    Path(__file__).resolve().parent / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parent)
