"""Fresh process startup and frozen public API compatibility for production entrypoints."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize(
    "module",
    [
        "cpswm.system.prototype_spine",
        "cpswm.system.structure_two_particle_workspace",
        "cpswm.system.structure_two_production_system",
        "cpswm.system.structure_two_joint_consumption",
        "cpswm.system.structure_two_conditional_updates",
    ],
)
def test_production_module_can_be_first_project_import(module: str) -> None:
    run(f"import importlib; importlib.import_module({module!r})")


def test_lazy_package_preserves_every_frozen_export_and_defining_object() -> None:
    old = subprocess.check_output(
        [
            "git",
            "show",
            "6b97e41afdb701eb197f23656d3796a6cd11e5e1:src/cpswm/system/evaluation_operations/__init__.py",
        ],
        cwd=ROOT,
        text=True,
    )
    expected = {
        a.asname or a.name: (n.module, a.name)
        for n in ast.parse(old).body
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    code = "import importlib; import cpswm.system.evaluation_operations as p; "
    code += "expected=" + repr(expected) + "; assert set(p.__all__)==set(expected); "
    code += "assert set(expected).issubset(dir(p)); "
    code += "assert all(getattr(p,n) is getattr(importlib.import_module('.'+m,p.__name__),a) "
    code += "for n,(m,a) in expected.items())"
    run(code)


def test_production_first_import_can_execute_a_public_synthetic_transition() -> None:
    # This tests a real default production call with an explicitly synthetic
    # fixture, not a real RGB-D semantic adapter or the full scientific loop.
    run(
        "from cpswm.system.structure_two_production_system import StructureTwoProductionSystem; "
        "import sys; sys.path.insert(0, 'tests'); "
        "from test_structure_two_production_system import _system_and_transition; "
        "system, transition = _system_and_transition(); "
        "assert isinstance(system, StructureTwoProductionSystem); "
        "result=system.process_transition(transition); "
        "assert result.belief_snapshot.map_version>=1; "
        "assert result.decision.evidence_source_record_ids"
    )
