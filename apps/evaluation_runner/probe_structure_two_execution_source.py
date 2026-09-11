#!/usr/bin/env python3
"""Run the previously opened A1+B1 direct-P5 matched development death test."""

from __future__ import annotations

import json

# Establish execution provenance before importing project dependencies.
import sys
import types
from pathlib import Path

_bootstrap_path = (
    Path(__file__).resolve().parents[2] / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parents[2])

from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig  # noqa: E402
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (  # noqa: E402
    _load_config,
    _source_binding,
)

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    binding = _source_binding(root, _load_config(root))
    print(
        json.dumps(
            {
                "loaded_owner_evidence_threshold": PrototypeLoopConfig().owner_evidence_threshold,
                "source_binding": binding,
                "diagnostic_only": True,
            },
            sort_keys=True,
        )
    )
