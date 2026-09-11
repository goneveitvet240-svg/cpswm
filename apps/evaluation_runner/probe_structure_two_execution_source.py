#!/usr/bin/env python3
"""Exercise supported local source-entry loading; no scientific experiment is run."""

from __future__ import annotations

import argparse
import json
import os

# Establish execution provenance before importing project dependencies.
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
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


def probe() -> dict:
    root = Path(__file__).resolve().parents[2]
    binding = _source_binding(root, _load_config(root))
    return {
        "loaded_owner_evidence_threshold": PrototypeLoopConfig().owner_evidence_threshold,
        "source_binding": binding,
        "diagnostic_only": True,
        "pid": os.getpid(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spawn", action="store_true")
    args = parser.parse_args()
    if args.spawn:
        with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
            result = pool.submit(probe).result()
        result["parent_pid"] = os.getpid()
    else:
        result = probe()
    print(json.dumps(result, sort_keys=True))
